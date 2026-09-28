"""What the TUI shows, as pure functions of a loaded `World`; no curses here."""

from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, List, NamedTuple, Optional

from .. import agents, schedule
from . import cartography
from ..schemas import NOTEBOOK_CHARACTERS
from ..world import chronicle, geography
from ..world.store import DAWN, DUSK, World, clock_at, day_at

#: `rule` is a divider drawn to the available width, not text.
TONES = ("plain", "dim", "bold", "accent", "warn", "rule")

# Escapes, not literals: keeps the source ASCII, and backslashes are not
# allowed inside f-string expressions before 3.12.
DASH = "\u2014"
NOTHING = DASH
ELLIPSIS = "\u2026"


@dataclass(frozen=True)
class Line:
    text: str = ""
    tone: str = "plain"

    #: Column that wrapped continuation lines hang under; 0 means the line's
    #: own indent.
    under: int = 0


@dataclass(frozen=True)
class Row:
    """An empty `key` cannot be selected."""
    key: str
    text: str = ""
    tone: str = "plain"


class View(NamedTuple):
    name: str
    title: str
    rows: Callable[[World], List[Row]]
    #: Given the pane's width, for what is drawn rather than wrapped.
    detail: Callable[[World, str, int], List[Line]]


# Measured with unicodedata, since wide characters take two columns.
def width(text: str) -> int:
    total = 0
    for character in text:
        if unicodedata.combining(character):
            continue
        total += 2 if unicodedata.east_asian_width(character) in "WF" else 1
    return total


def pad(text: str, columns: int) -> str:
    return text + " " * max(0, columns - width(text))


def clip(text: str, columns: int) -> str:
    if columns <= 0:
        return ""
    if width(text) <= columns:
        return text
    kept, used = [], 0
    for character in text:
        step = 0 if unicodedata.combining(character) else (
            2 if unicodedata.east_asian_width(character) in "WF" else 1)
        if used + step > columns - 1:
            break
        kept.append(character)
        used += step
    return "".join(kept) + ELLIPSIS


def fit(text: str, columns: int) -> int:
    """How many characters of `text` fit in `columns`."""
    used = 0
    for index, character in enumerate(text):
        step = 0 if unicodedata.combining(character) else (
            2 if unicodedata.east_asian_width(character) in "WF" else 1)
        if used + step > columns:
            return index
        used += step
    return len(text)


def wrap(line: Line, columns: int) -> List[Line]:
    """Slices rather than re-joining words, so column-aligned spacing survives."""
    if columns <= 0 or line.tone == "rule" or width(line.text) <= columns:
        return [line]
    indent = len(line.text) - len(line.text.lstrip(" "))
    hang = " " * min(line.under or indent, max(0, columns - 12))
    wrapped: List[Line] = []
    rest, floor = line.text, indent + 1
    while width(rest) > columns:
        limit = fit(rest, columns)
        space = rest.rfind(" ", floor, limit + 1)
        if space < floor:
            # A word longer than the pane: hard cut.
            space = max(limit, floor)
            wrapped.append(Line(rest[:space], line.tone))
            rest = hang + rest[space:].lstrip(" ")
        else:
            wrapped.append(Line(rest[:space], line.tone))
            rest = hang + rest[space + 1:].lstrip(" ")
        floor = len(hang) + 1
    wrapped.append(Line(rest, line.tone))
    return wrapped


def timestamp(at: float) -> str:
    return "day " + str(day_at(at)) + ", " + clock_at(at)


def span(hours: float) -> str:
    """In the largest unit that fits."""
    hours = abs(hours)
    if hours < 1.0:
        return "%.0fmin" % (hours * 60)
    if hours < 48.0:
        return "%.1fh" % hours
    return "%.1f days" % (hours / 24.0)


def looks_up(world: World, being) -> Line:
    absorbed = ("; deep enough in it that what happens nearby is not their "
                "business" if being.when.absorbed else "")
    wake_at = being.when.wake_at
    if wake_at is None:
        return Line("  looks up    whenever the world next stirs; they did not say",
                    "dim", under=14)
    away = wake_at - world.at
    if away <= 0:
        return Line("  looks up    now" + absorbed, under=14)
    return Line("  looks up    in " + span(away) + absorbed, under=14)


WORLD_KEY = "~world"
GONE_KEY = "~gone"


def world_rows(world: World) -> List[Row]:
    rows = [Row(WORLD_KEY, world.name + ", as a whole", "accent"), Row("")]
    for place in world.places.values():
        here = world.beings_at(place.id)
        who = ", ".join(being.name for being in here) if here else NOTHING
        rows.append(Row(place.id, pad(clip(place.name, 20), 21) + who,
                        "plain" if here else "dim"))
    gone = [being for being in world.beings.values() if not being.present]
    if gone:
        rows += [Row(""),
                 Row(GONE_KEY, "%d who are no longer here" % len(gone), "dim")]
    return rows


def overview_detail(world: World) -> List[Line]:
    lines = [Line(world.name, "bold"),
           Line("  " + world.label()),
           Line("  the sun %s   (up at %02.0f:00, down at %02.0f:00)"
                % ("is up" if world.daylight else "is down", DAWN, DUSK), "dim"),
           Line()]
    if world.closed:
        lines += [Line("  This world has ended. Nothing more happens in it, and "
                     "all that did stays readable.", "warn", under=2), Line()]
    present = [being for being in world.beings.values() if being.present]
    lines += [Line("  what there is", "bold"),
            Line("    %d here, %d gone"
                 % (len(present), len(world.beings) - len(present))),
            Line("    %d places, %d ways between them"
                 % (len(world.places), len(world.map.ways))),
            Line("    %d events on record" % len(world.chronicle)),
            Line()]
    lines.append(Line("  what is next due", "bold"))
    due = schedule.next_at(world)
    if due is None:
        lines.append(Line("    nothing. Every mind declined to say when it wanted "
                        "asking again, and the engine is not going to decide "
                        "that for them.", "warn", under=4))
    else:
        lines.append(Line("    the world moves next in "
                        + span(max(0.0, due - world.at)) + " of its own time"))
    for label, timer in (("the town", world.town_wake_at),
                         ("the road", world.road_wake_at)):
        if timer is None:
            lines.append(Line("    " + pad(label, 10) + "no timer set", "dim"))
        else:
            lines.append(Line("    " + pad(label, 10) + "asked again in "
                            + span(max(0.0, timer - world.at)), "dim"))
    if world.last_tick_at is not None:
        lines += [Line(),
                Line("  out here", "bold"),
                Line("    a step was last lived "
                     + span((time.time() - world.last_tick_at) / 3600.0)
                     + " ago by the wall clock", "dim", under=4)]
    unseen = len(world.chronicle) - world.read_through
    lines += [Line(),
            Line("  %d events since you last looked" % unseen if unseen
                 else "  you have read everything that has happened", "dim")]
    return lines


def gone_detail(world: World) -> List[Line]:
    """Beings who left, as they were when they went."""
    gone = sorted((being for being in world.beings.values() if not being.present),
                  key=lambda being: being.when.left_at or 0.0)
    lines = [Line("No longer here", "bold"),
           Line("  Nothing has touched what they hold since they went. The "
                "world has no idea what has become of them and will not "
                "pretend to.", "dim", under=2),
           Line()]
    for being in gone:
        left = being.when.left_at
        lines.append(Line("  " + pad(being.name, 9)
                        + (timestamp(left) if left else "gone at some point")))
        lines.append(Line("           a page of %d characters, as it was then"
                        % len(being.who.notebook), "dim"))
    return lines


def world_detail(world: World, key: str) -> List[Line]:
    if key == WORLD_KEY:
        return overview_detail(world)
    if key == GONE_KEY:
        return gone_detail(world)
    place = world.places.get(key)
    if place is None:
        return [Line("Nowhere.", "dim")]
    lines = [Line(place.name, "bold")]
    if place.description:
        lines.append(Line("  " + place.description, under=2))
    lines.append(Line())
    beside = [world.places[other].name for other in world.map.beside(place.id)
              if other in world.places]
    lines.append(Line("  ways out    " + (", ".join(beside) if beside else "none"),
                    "dim", under=14))
    if world.map.road == place.id:
        lines.append(Line("  the road out of the world leaves from here, and comes "
                        "back in at it", "accent", under=2))
    lines.append(Line())
    here = world.beings_at(place.id)
    lines.append(Line("  who is here" if here else "  nobody is here", "bold"))
    for being in here:
        lines.append(Line("    " + pad(being.name, 9)
                        + (being.where.doing or "just here"), under=13))
    events = [event for event in world.chronicle.all() if event.place == place.id]
    if events:
        lines += [Line(), Line("  what happened here", "bold")]
        for event in events[-6:]:
            lines.append(Line("    " + pad(timestamp(event.at), 16) + event.account,
                            under=4))
    return lines


def being_rows(world: World) -> List[Row]:
    present = sorted((being for being in world.beings.values() if being.present),
                     key=lambda being: being.name)
    gone = sorted((being for being in world.beings.values() if not being.present),
                  key=lambda being: being.when.left_at or 0.0)
    rows: List[Row] = []
    for being in present:
        place = world.places.get(being.where.place)
        rows.append(Row(being.id, pad(being.name, 9)
                        + (place.name if place else NOTHING)))
    if gone:
        rows.append(Row(""))
        for being in gone:
            left = being.when.left_at
            rows.append(Row(being.id, pad(being.name, 9) + "left "
                            + (timestamp(left) if left else "at some point"), "dim"))
    return rows


def being_detail(world: World, key: str) -> List[Line]:
    being = world.beings.get(key)
    if being is None:
        return [Line("Nobody.", "dim")]
    lines = [Line(being.name, "bold")]
    if being.mind == "player":
        lines.append(Line("  this one answers for themselves", "accent"))
    if being.who.card:
        lines.append(Line("  " + being.who.card, under=2))
    if being.who.manner:
        lines.append(Line("  " + being.who.manner, "dim", under=2))
    lines.append(Line())
    if not being.present:
        # Nothing reaches somebody who left, so this is how they stood then.
        lines += [Line("  left on     " + timestamp(being.when.left_at or world.at),
                     "warn", under=14),
                Line("  What follows is how they stood then.", "dim", under=2)]
    else:
        place = world.places.get(being.where.place)
        home = world.places.get(being.where.home)
        lines.append(Line("  at          " + (place.name if place else NOTHING),
                        under=14))
        lines.append(Line("  sleeps      " + (home.name if home else "nowhere yet"),
                        "dim", under=14))
        if being.where.doing:
            lines.append(Line("  doing       " + being.where.doing, under=14))
        lines.append(looks_up(world, being))
    if being.when.arrived_at:
        lines.append(Line("  came up the road on " + timestamp(being.when.arrived_at),
                        "dim", under=2))
    earlier = being.where.lately[:-1]
    if earlier:
        lines += [Line(), Line("  what they had been doing before that", "bold")]
        for what in reversed(earlier):
            lines.append(Line("    " + what, "dim", under=4))
    lines += [Line(), Line("  what they carry, %d of %d characters"
                         % (len(being.who.notebook), NOTEBOOK_CHARACTERS), "bold")]
    for line in (being.who.notebook or "nothing yet").splitlines():
        lines.append(Line("    " + line, under=4))
    lines.append(Line("    the newest of %d pages they have written; every one is kept"
                    % len(world.pages(being.id)), "dim", under=4))
    today = agents.day_notes(world, being)
    lines += [Line(), Line("  what they have kept of today, not gone over yet" if today
                         else "  nothing kept since they last went over their day", "bold")]
    for note in today:
        lines.append(Line("    " + pad(timestamp(note.at), 16) + note.account, under=4))
    lines.append(Line("    %d notes in all; every one is kept"
                    % len(world.notes(being.id)), "dim", under=4))
    return lines


MARKS = {chronicle.OCCURRENCE: "*", chronicle.ARRIVAL: "+",
         chronicle.DEPARTURE: "-", chronicle.CONVERSATION: "\""}

UNREAD = DASH + " since you last looked " + DASH


def chronicle_rows(world: World) -> List[Row]:
    """Oldest first, with a line where you stopped reading."""
    rows: List[Row] = []
    events = world.chronicle.all()
    for index, event in enumerate(events):
        if index == world.read_through:
            rows.append(Row("", UNREAD, "accent"))
        rows.append(Row(event.id, MARKS.get(event.category, " ") + " "
                        + pad(timestamp(event.at), 16) + event.account))
    if not events:
        rows.append(Row("", "nothing has happened yet", "dim"))
    return rows


def event_detail(world: World, key: str) -> List[Line]:
    event = world.chronicle.get(key)
    if event is None:
        return [Line("No such event.", "dim")]
    place = world.places.get(event.place or "")
    lines = [Line("event " + event.id + "  " + timestamp(event.at) + "  " + event.category, "bold"),
           Line("  at " + (place.name if place else "nowhere in particular"),
                "dim"),
           Line(),
           Line("  History says: " + event.account, under=2)]
    why = event.data.get("why_now")
    if why:
        lines.append(Line("  why then: " + str(why), "dim", under=2))
    lines += [Line(), Line("  What it left in the beings it reached", "bold")]
    position = world.chronicle.all().index(event)
    reached = [world.beings[being_id] for being_id in event.informed
               if being_id in world.beings]
    for being in reached:
        notes = world.notes(being.id).about(event.id)
        for note in notes:
            lines.append(Line("    " + pad(being.name, 9) + "\"" + note.account + "\"",
                            under=13))
        if not notes:
            lines.append(Line("    " + pad(being.name, 9)
                            + ("nothing stayed." if being.when.seen_through > position
                               else "has not looked up since."), "dim", under=13))
        lines.append(Line("             they were " + agents.viewpoint(world, being, event),
                        "dim", under=13))
    if not reached:
        lines.append(Line("    nobody was reached by it.", "dim"))
    return lines


def place_rows(world: World) -> List[Row]:
    rows = []
    for place in world.places.values():
        here = world.beings_at(place.id)
        who = ", ".join(being.name for being in here) if here else NOTHING
        rows.append(Row(place.id, pad(clip(place.name, 16), 17) + who,
                        "plain" if here else "dim"))
    if not rows:
        rows.append(Row("", "there are no places", "dim"))
    return rows


def map_detail(world: World, key: str, columns: int) -> List[Line]:
    """The place looked at is in brackets."""
    labels = {place.id: ("[" + place.name + "]" if place.id == key else place.name)
              for place in world.places.values()}
    positions = world.map.positions
    if not positions:
        # Made before places had positions: lay it out here, and keep none of it.
        positions = geography.layout(list(world.places), world.map.ways)
    rows = max(9, min(18, columns // 3))
    return [Line(text) for text in
            cartography.draw(labels, positions, world.map.ways, columns, rows)]


VIEWS = (
    View("world", "World", world_rows,
         lambda world, key, columns: world_detail(world, key)),
    View("beings", "Beings", being_rows,
         lambda world, key, columns: being_detail(world, key)),
    View("history", "History", chronicle_rows,
         lambda world, key, columns: event_detail(world, key)),
    View("map", "Map", place_rows, map_detail),
)
