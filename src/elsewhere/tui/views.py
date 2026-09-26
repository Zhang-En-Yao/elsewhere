"""What a window on the world shows, worked out with no terminal in the room.

Everything here is a pure function of a loaded `World`. A view answers two
questions - what is there to look at, and what is worth saying about the one
being looked at - and hands back lines. Nothing in this file imports curses,
draws anything, or reads a key.

That division is not tidiness. It is what makes a window testable: a view is
checked by asking it for its lines and reading them, and `screen.py` is left
with the only question it is any good at, which is where on a terminal each
line goes.

A line carries a tone and not a colour, for the same reason a memory carries
no weight: what `dim` is worth is the terminal's business, and this file has
no opinion about it.

One thing the views do that the printed commands do not: they show what would
*not* come back. `elsewhere person` prints what is within reach and stops,
because a printed page has to stop somewhere. A window has room to put the
rest underneath it, dimmed, under a line saying where reach ended - and that
is this project's one claim about memory, made visible in a single screen.
"""

from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, List, NamedTuple, Optional

from .. import retrieval, schedule
from ..world import chronicle
from ..world.store import DAWN, DUSK, World, clock_at, day_of

#: Tones a line can carry. `rule` is not text at all but a divider the drawer
#: fills out to whatever width it happens to have.
TONES = ("plain", "dim", "bold", "accent", "warn", "rule")

# Written as escapes, and never inside an f-string expression: the rest of this
# source is ASCII, and a backslash in an f-string is a syntax error before 3.12.
DASH = "\u2014"
NOTHING = DASH
CUT = "\u2026"


@dataclass(frozen=True)
class Line:
    """One line of something to look at, and how much it wants noticing."""
    text: str = ""
    tone: str = "plain"

    #: The column the remainder sits under, when the line has to be wrapped.
    #: A column and not an extra indent, because what it is nearly always set
    #: to is where the value after a label begins: a wrapped sentence that
    #: goes on under itself reads as one thing, and one that goes on under its
    #: own label reads as a second label. Zero means the line's own indent.
    under: int = 0


@dataclass(frozen=True)
class Row:
    """Something in the left-hand list. An empty `key` cannot be landed on."""
    key: str
    text: str = ""
    tone: str = "plain"


class View(NamedTuple):
    """A tab: what it is called, what is in its list, and what one of them is."""
    name: str
    title: str
    rows: Callable[[World], List[Row]]
    detail: Callable[[World, str], List[Line]]


# -- how wide a line is ----------------------------------------------------
# A world can be seeded in any language, and a name that measures two columns
# while counting as one character wrecks every column in the list. So width is
# asked of unicodedata rather than of len().

def width(text: str) -> int:
    """How many terminal columns this occupies."""
    total = 0
    for character in text:
        if unicodedata.combining(character):
            continue
        total += 2 if unicodedata.east_asian_width(character) in "WF" else 1
    return total


def pad(text: str, columns: int) -> str:
    """Left-justify to a column count, measured the way a terminal measures."""
    return text + " " * max(0, columns - width(text))


def clip(text: str, columns: int) -> str:
    """Cut to fit, leaving a mark where something was cut off."""
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
    return "".join(kept) + CUT


def _cut(text: str, columns: int) -> int:
    """The largest index whose text still fits in that many columns."""
    used = 0
    for index, character in enumerate(text):
        step = 0 if unicodedata.combining(character) else (
            2 if unicodedata.east_asian_width(character) in "WF" else 1)
        if used + step > columns:
            return index
        used += step
    return len(text)


def wrap(line: Line, columns: int) -> List[Line]:
    """One line as however many it takes, each still carrying its tone.

    The line is sliced, never split into words and joined back up. Half of
    what is on screen is held in columns a space wide - a name, then what they
    are doing - and a wrapper that normalises whitespace on the way past would
    take every one of those apart.
    """
    if columns <= 0 or line.tone == "rule" or width(line.text) <= columns:
        return [line]
    indent = len(line.text) - len(line.text.lstrip(" "))
    # The remainder begins under whatever it is a remainder of, unless that
    # would leave no room to say anything after it.
    hang = " " * min(line.under or indent, max(0, columns - 12))
    out: List[Line] = []
    rest, floor = line.text, indent + 1
    while width(rest) > columns:
        at = _cut(rest, columns)
        space = rest.rfind(" ", floor, at + 1)
        if space < floor:
            # A word longer than the pane. Cut it, rather than loop forever.
            space = max(at, floor)
            out.append(Line(rest[:space], line.tone))
            rest = hang + rest[space:].lstrip(" ")
        else:
            out.append(Line(rest[:space], line.tone))
            rest = hang + rest[space + 1:].lstrip(" ")
        floor = len(hang) + 1
    out.append(Line(rest, line.tone))
    return out


# -- saying when, and how long ---------------------------------------------

def when(at: float) -> str:
    """A world timestamp as a person would say it."""
    return "day " + str(day_of(at)) + ", " + clock_at(at)


def span(hours: float) -> str:
    """A length of time, in the largest unit that does not lie about it."""
    hours = abs(hours)
    if hours < 1.0:
        return "%.0fmin" % (hours * 60)
    if hours < 48.0:
        return "%.1fh" % hours
    return "%.1f days" % (hours / 24.0)


def _looks_up(world: World, being) -> Line:
    """When they next expect to look up from what they are doing."""
    absorbed = ("; deep enough in it that what happens nearby is not their "
                "business" if being.when.absorbed else "")
    wake = being.when.wake_at
    if wake is None:
        return Line("  looks up    whenever the world next stirs; they did not say",
                    "dim", under=14)
    away = wake - world.at
    if away <= 0:
        return Line("  looks up    now" + absorbed, under=14)
    return Line("  looks up    in " + span(away) + absorbed, under=14)


def _memory_lines(world: World, being, memory, at: float,
                  tone: str = "plain") -> List[Line]:
    """One memory, and everything that shows it has been lived with."""
    odds = retrieval.chance(retrieval.activation(memory, at))
    out = [Line("    " + pad(when(memory.at), 16) +
                "[" + memory.feeling + "] " + memory.account, tone, under=4)]
    if memory.means:
        out.append(Line("        ~ " + memory.means, "dim", under=10))
    out.append(Line("        come up %dx, %.0f%% it comes to mind"
                    % (len(memory.told) or 1, odds * 100), "dim"))
    # Earlier wordings: the only evidence anywhere that a memory moved, which
    # is the one thing this whole project is about.
    for was in reversed(memory.history):
        out.append(Line("        was: \"" + was + "\"", "accent", under=13))
    for source in memory.origin:
        came = world.memories(being.id).get(source)
        if came is not None:
            out.append(Line("        out of: \"" + came.account + "\"",
                            "dim", under=16))
    return out


# -- the town: the world itself, its places, and who is no longer in it ----

WORLD_KEY = "~world"
GONE_KEY = "~gone"


def town_rows(world: World) -> List[Row]:
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


def _world_detail(world: World) -> List[Line]:
    """The world's own state: its clock, and every timer set in it."""
    out = [Line(world.name, "bold"),
           Line("  " + world.label()),
           Line("  the sun %s   (up at %02.0f:00, down at %02.0f:00)"
                % ("is up" if world.daylight else "is down", DAWN, DUSK), "dim"),
           Line()]
    if world.closed:
        out += [Line("  This world has ended. Nothing more happens in it, and "
                     "all that did stays readable.", "warn", under=2), Line()]
    present = [being for being in world.beings.values() if being.present]
    kept = sum(len(world.memories(being.id)) for being in world.beings.values())
    out += [Line("  what there is", "bold"),
            Line("    %d here, %d gone"
                 % (len(present), len(world.beings) - len(present))),
            Line("    %d places, %d ways between them"
                 % (len(world.places), len(world.map.ways))),
            Line("    %d events on record, %d memories made of them"
                 % (len(world.chronicle), kept)),
            Line()]
    # Every timer in the world, which is the only thing that says when anything
    # next happens. There is no step size to report, because there is none.
    out.append(Line("  what is next due", "bold"))
    due = schedule.next_at(world)
    if due is None:
        out.append(Line("    nothing. Every mind declined to say when it wanted "
                        "asking again, and the engine is not going to decide "
                        "that for them.", "warn", under=4))
    else:
        out.append(Line("    the world moves next in "
                        + span(max(0.0, due - world.at)) + " of its own time"))
    for label, timer in (("the town", world.town_wake_at),
                         ("the road", world.road_wake_at)):
        if timer is None:
            out.append(Line("    " + pad(label, 10) + "no timer set", "dim"))
        else:
            out.append(Line("    " + pad(label, 10) + "asked again in "
                            + span(max(0.0, timer - world.at)), "dim"))
    if world.last_tick_at is not None:
        out += [Line(),
                Line("  out here", "bold"),
                Line("    a step was last lived "
                     + span((time.time() - world.last_tick_at) / 3600.0)
                     + " ago by the wall clock", "dim", under=4)]
    unseen = len(world.chronicle) - world.news_seen
    out += [Line(),
            Line("  %d events since you last looked" % unseen if unseen
                 else "  you have read everything that has happened", "dim")]
    return out


def _gone_detail(world: World) -> List[Line]:
    """Everyone the road took, as they stood the hour they went."""
    gone = sorted((being for being in world.beings.values() if not being.present),
                  key=lambda being: being.when.left_at or 0.0)
    out = [Line("No longer here", "bold"),
           Line("  Nothing has touched what they hold since they went. The "
                "world has no idea what has become of them and will not "
                "pretend to.", "dim", under=2),
           Line()]
    for being in gone:
        left = being.when.left_at
        out.append(Line("  " + pad(being.name, 9)
                        + (when(left) if left else "gone at some point")))
        out.append(Line("           %d memories, held as they were then"
                        % len(world.memories(being.id)), "dim"))
    return out


def town_detail(world: World, key: str) -> List[Line]:
    if key == WORLD_KEY:
        return _world_detail(world)
    if key == GONE_KEY:
        return _gone_detail(world)
    place = world.places.get(key)
    if place is None:
        return [Line("Nowhere.", "dim")]
    out = [Line(place.name, "bold")]
    if place.description:
        out.append(Line("  " + place.description, under=2))
    out.append(Line())
    beside = [world.places[other].name for other in world.map.beside(place.id)
              if other in world.places]
    out.append(Line("  ways out    " + (", ".join(beside) if beside else "none"),
                    "dim", under=14))
    if world.map.road_out == place.id:
        out.append(Line("  the road out of the world leaves from here, and comes "
                        "back in at it", "accent", under=2))
    out.append(Line())
    here = world.beings_at(place.id)
    out.append(Line("  who is here" if here else "  nobody is here", "bold"))
    for being in here:
        out.append(Line("    " + pad(being.name, 9)
                        + (being.where.doing or "just here"), under=13))
        if being.who.thought:
            out.append(Line("             keeps coming back to: \""
                            + being.who.thought + "\"", "dim", under=13))
    events = [event for event in world.chronicle.all() if event.place == place.id]
    if events:
        out += [Line(), Line("  what happened here", "bold")]
        for event in events[-6:]:
            out.append(Line("    " + pad(when(event.at), 16) + event.account,
                            under=4))
    return out


# -- the people ------------------------------------------------------------

def people_rows(world: World) -> List[Row]:
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
                            + (when(left) if left else "at some point"), "dim"))
    return rows


def person_detail(world: World, key: str, most: int = 60) -> List[Line]:
    being = world.beings.get(key)
    if being is None:
        return [Line("Nobody.", "dim")]
    # Somebody who left is read as they stood the hour they went. Going on
    # fading what they hold would be this world inventing a life for them off
    # the edge of its own map.
    at = world.at if being.present else (being.when.left_at or world.at)
    out = [Line(being.name, "bold")]
    if being.mind == "player":
        out.append(Line("  this one answers for themselves", "accent"))
    if being.who.card:
        out.append(Line("  " + being.who.card, under=2))
    if being.who.manner:
        out.append(Line("  " + being.who.manner, "dim", under=2))
    out.append(Line())
    if not being.present:
        out += [Line("  left on     " + when(at), "warn", under=14),
                Line("  What follows is how they stood then.", "dim", under=2)]
    else:
        place = world.places.get(being.where.place)
        home = world.places.get(being.where.home)
        out.append(Line("  at          " + (place.name if place else NOTHING),
                        under=14))
        out.append(Line("  sleeps      " + (home.name if home else "nowhere yet"),
                        "dim", under=14))
        if being.where.doing:
            out.append(Line("  doing       " + being.where.doing, under=14))
        out.append(_looks_up(world, being))
        if being.who.thought:
            out.append(Line("  comes back  \"" + being.who.thought + "\"",
                            "accent", under=14))
    if being.when.arrived_at:
        out.append(Line("  came up the road on " + when(being.when.arrived_at),
                        "dim", under=2))
    earlier = being.where.lately[:-1]
    if earlier:
        out += [Line(), Line("  what they had been doing before that", "bold")]
        for what in reversed(earlier):
            out.append(Line("    " + what, "dim", under=4))
    if being.who.wants:
        out += [Line(), Line("  wants", "bold")]
        for want in being.who.wants:
            out.append(Line("    " + want, under=4))
    if being.who.beliefs:
        out += [Line(), Line("  holds to be true", "bold")]
        for belief in retrieval.recallable(being.who.beliefs, at,
                                          limit=len(being.who.beliefs)):
            out.append(Line("    [held %dx] %s"
                            % (len(belief.held) or 1, belief.claim), under=4))
            if retrieval.on_faith(belief, world.memories(being.id), at):
                # As firmly held as ever, with nothing left to point at.
                out.append(Line("        held on faith now: what it grew out of "
                                "does not come back to them any more",
                                "warn", under=8))
    known = [(world.beings[person_id], regard)
             for person_id, regard in sorted(being.who.regards.items(),
                                             key=lambda pair: -pair[1].last_seen_at)
             if person_id in world.beings]
    out += [Line(), Line("  who they know" if known
                         else "  they know nobody here yet", "bold")]
    for other, regard in known:
        out.append(Line("    " + pad(other.name, 9) + (regard.account or NOTHING)
                        + ("" if other.present else "   (gone)"), under=13))
        if regard.last_seen_at:
            out.append(Line("             last stood with them "
                            + when(regard.last_seen_at), "dim"))
    memories = list(world.memories(being.id))
    reach = retrieval.recallable(memories, at)
    within = retrieval.recallable(memories, at, limit=most)
    out += [Line(), Line("  memory: %d in all, %d of them within reach right now"
                         % (len(memories), len(reach)), "bold", under=2)]
    # In reach first, then the line where reach ran out, then the rest. The
    # order is the activation order either side of it, so the line falls
    # exactly where the engine stops handing things over.
    said_where = False
    for memory in within:
        if memory not in reach and not said_where:
            out.append(Line("    " + DASH + " below here, nothing the engine "
                            "would hand over if they were asked now " + DASH,
                            "dim", under=4))
            said_where = True
        out += _memory_lines(world, being, memory, at,
                             "plain" if memory in reach else "dim")
    return out


# -- what happened ---------------------------------------------------------

MARKS = {chronicle.OCCURRENCE: "*", chronicle.ARRIVAL: "+",
         chronicle.DEPARTURE: "-", chronicle.CONVERSATION: "\""}

UNREAD = DASH + " since you last looked " + DASH


def chronicle_rows(world: World) -> List[Row]:
    """The ledger, oldest first, with a line where you stopped reading."""
    rows: List[Row] = []
    events = world.chronicle.all()
    for index, event in enumerate(events):
        if index == world.news_seen:
            rows.append(Row("", UNREAD, "accent"))
        rows.append(Row(event.id, MARKS.get(event.category, " ") + " "
                        + pad(when(event.at), 16) + event.account))
    if not events:
        rows.append(Row("", "nothing has happened yet", "dim"))
    return rows


def event_detail(world: World, key: str) -> List[Line]:
    event = world.chronicle.get(key)
    if event is None:
        return [Line("No such event.", "dim")]
    place = world.places.get(event.place or "")
    out = [Line(event.id + "  " + when(event.at) + "  " + event.category, "bold"),
           Line("  at " + (place.name if place else "nowhere in particular"),
                "dim"),
           Line(),
           Line("  History says: " + event.account, under=2)]
    why = event.data.get("why_now")
    if why:
        out.append(Line("  why then: " + str(why), "dim", under=2))
    reached = [world.beings[person_id].name for person_id in event.reached
               if person_id in world.beings]
    if reached:
        out.append(Line("  it got as far as: " + ", ".join(reached), "dim", under=2))
    out += [Line(), Line("  What it left in people", "bold")]
    vantage = event.data.get("vantage") or {}
    anybody = False
    for being in world.beings.values():
        stood = vantage.get(being.id)
        memories = world.memories(being.id).about_event(event.id)
        if not memories:
            if being.id in event.reached:
                anybody = True
                out.append(Line("    " + pad(being.name, 9)
                                + "nothing stayed.", "dim", under=13))
                if stood:
                    out.append(Line("             they were " + str(stood),
                                    "dim", under=13))
            continue
        anybody = True
        at = world.at if being.present else (being.when.left_at or world.at)
        mine = list(world.memories(being.id))
        for memory in memories:
            out.append(Line("    " + pad(being.name, 9) + "\"" + memory.account
                            + "\"", under=13))
            if stood:
                out.append(Line("             they were " + str(stood),
                                "dim", under=13))
            if memory.means:
                out.append(Line("             " + memory.feeling + ": "
                                + memory.means, "dim", under=13))
            if memory in retrieval.recallable(mine, at):
                odds = retrieval.chance(retrieval.activation(memory, at))
                out.append(Line("             %.0f%% it comes to mind"
                                % (odds * 100), "dim"))
            else:
                out.append(Line("             something else comes back instead",
                                "warn"))
            for was in reversed(memory.history):
                out.append(Line("             was: \"" + was + "\"",
                                "accent", under=18))
    if not anybody:
        out.append(Line("    nobody was reached by it.", "dim"))
    return out


VIEWS = (
    View("town", "Town", town_rows, town_detail),
    View("people", "People", people_rows, person_detail),
    View("history", "History", chronicle_rows, event_detail),
)
