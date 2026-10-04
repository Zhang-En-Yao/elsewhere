"""What the TUI shows, as pure functions of a loaded `World`; no curses here."""

from __future__ import annotations

import functools
import json
import lzma
import plistlib
import re
import time
import unicodedata
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from . import cartography
from .. import bookmark
from ... import REAL_TIME_PER_VIRTUAL_TIME, VIRTUAL_TIME_PER_DAY
from ...adapters import storage
from ...domain import geography, perspective
from ...domain.calendar import DAWN, DUSK, SECONDS_PER_HOUR, clock_of, day_of, real_of
from ...domain.chronicle import Category
from ...domain.memory import episodes_of_event, episodes_of_engram
from ...domain.world import World
from ...harness import memory
from ...harness.schemas import SELF_SCHEMA_CHARACTERS

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

    #: (column, text, tone): drawn over the line in their own tone. Lost if
    #: the line has to be wrapped, so only for lines drawn to fit.
    spans: Tuple[Tuple[int, str, str], ...] = ()


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
    #: Where Enter goes from a row: (view name, row key), or None.
    link: Callable[[World, str], Optional[Tuple[str, str]]]


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
    return "day " + str(day_of(at)) + ", " + clock_of(at)


def span(duration: float) -> str:
    """In the largest unit that fits."""
    hours = real_of(abs(duration)) / SECONDS_PER_HOUR
    if hours < 1.0 / 60:
        return "%.0fs" % (hours * 3600)
    if hours < 1.0:
        return "%.0fmin" % (hours * 60)
    if hours < 48.0:
        return "%.1fh" % hours
    return "%.1f days" % (abs(duration) / VIRTUAL_TIME_PER_DAY)


#: The launchd job `scripts/schedule.sh install` writes; only ever read here.
AGENT = Path.home() / "Library" / "LaunchAgents" / "com.elsewhere.continue.plist"

#: How each run of `elsewhere continue` starts its lines in the job's log.
LOGGED = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d)\]")


@dataclass(frozen=True)
class Agent:
    """The launchd job that runs `elsewhere continue` on this world."""
    every: float                   # seconds between runs
    log: Optional[Path]


def agent(world: World) -> Optional[Agent]:
    """None unless the job is installed, and for this world."""
    try:
        job = plistlib.loads(AGENT.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    arguments = [str(argument) for argument in job.get("ProgramArguments", [])]
    if "--world" not in arguments[:-1]:
        return None
    target = Path(arguments[arguments.index("--world") + 1])
    if target.resolve() != storage.root(world).resolve():
        return None
    log = job.get("StandardOutPath")
    return Agent(every=float(job.get("StartInterval", 0)), log=Path(log) if log else None)


def last_run(job: Agent) -> str:
    """When the job last wrote to its log, as it wrote it; "" if never."""
    if job.log is None:
        return ""
    try:
        tail = job.log.read_bytes()[-8192:].decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    for line in reversed(tail):
        found = LOGGED.match(line)
        if found:
            return found.group(1)
    return ""


def upcoming(world: World) -> List[Tuple[float, List[str]]]:
    """Every timer set, grouped by the time it falls due, soonest first."""
    timers: Dict[float, List[str]] = {}
    for being in sorted(world.beings.values(), key=lambda being: being.name):
        if being.present and being.clock.due_at is not None:
            timers.setdefault(being.clock.due_at, []).append(being.name)
    if world.due_at is not None:
        timers.setdefault(world.due_at, []).append("the world")
    return sorted(timers.items())


def by_clock(world: World, at: float) -> Optional[float]:
    """The wall-clock moment `continue` may first live `at`: a world day is
    owed per real day, counted from the last step lived."""
    if world.last_tick_at is None:
        return None
    return world.last_tick_at + max(0.0, at - world.current) * REAL_TIME_PER_VIRTUAL_TIME


def wall(moment: Optional[float], now: float) -> str:
    if moment is None:
        return NOTHING
    if moment <= now:
        return "now"
    days = (time.localtime(moment).tm_yday - time.localtime(now).tm_yday) % 366
    if days == 0:
        return time.strftime("%H:%M", time.localtime(moment))
    if days == 1:
        return time.strftime("tomorrow %H:%M", time.localtime(moment))
    return time.strftime("%b %d %H:%M", time.localtime(moment))


def next_lines(world: World, indent: str, shown: int = 3) -> List[Line]:
    """What falls due next, by the world's clock and the wall's, and whether
    anything is running `continue` to live it."""
    now = time.time()
    groups = upcoming(world)
    if not groups:
        return [Line(indent + "nothing: no timer is set anywhere, and the engine "
                     "will not pick one for them", "warn", under=len(indent))]
    lines = []
    for at, names in groups[:shown]:
        when = "now" if at <= world.current else wall(by_clock(world, at), now)
        lines.append(Line(indent + pad(when, 16) + pad(timestamp(at), 16) + ", ".join(names),
                          under=len(indent) + 32))
    if len(groups) > shown:
        lines.append(Line(indent + "and %d more after that" % (len(groups) - shown), "dim"))
    job = agent(world)
    last = last_run(job) if job else ""
    if job is None:
        lines.append(Line(indent + "not scheduled, so none of it happens: `make schedule`",
                          "warn", under=len(indent)))
    elif not last:
        lines.append(Line(indent + "scheduled every " + span(job.every / REAL_TIME_PER_VIRTUAL_TIME)
                          + ", never ran: `make status`", "warn", under=len(indent)))
    else:
        lines.append(Line(indent + "`continue` every " + span(job.every / REAL_TIME_PER_VIRTUAL_TIME)
                          + ", last ran " + last, "dim", under=len(indent)))
    return lines


def looks_up(world: World, being) -> Line:
    due_at = being.clock.due_at
    if due_at is None:
        return Line("  looks up    whenever the world next stirs; they did not say",
                    "dim", under=14)
    away = due_at - world.current
    if away <= 0:
        return Line("  looks up    now", under=14)
    return Line("  looks up    in " + span(away), under=14)


#: The logo in braille at a few widths, smallest first, each as the frames of
#: one beat of its wings, as `scripts/logo.py` drew it from docs/logo.jpg.
LOGO = "logo.json.xz"


@functools.lru_cache(maxsize=1)
def drawings() -> List[List[List[str]]]:
    """Every size of the logo, each a list of frames of lines; read once."""
    try:
        packed = resources.files(__package__).joinpath(LOGO).read_bytes()
        return json.loads(lzma.decompress(packed).decode("utf-8"))
    except (OSError, lzma.LZMAError, ValueError):
        return []


@functools.lru_cache(maxsize=8)
def logo(columns: int, rows: int) -> List[List[str]]:
    """The frames of the largest drawing of the logo that fits; none if even
    the smallest does not. Cached: the window asks again for every frame."""
    fitting: List[List[str]] = []
    for frames in drawings():
        if all(len(lines) <= rows and max(map(width, lines)) <= columns for lines in frames):
            fitting = frames
    return fitting


@functools.lru_cache(maxsize=8)
def widest(columns: int, rows: int) -> int:
    """Columns taken by the widest frame of `logo(columns, rows)`."""
    return max((width(line) for lines in logo(columns, rows) for line in lines), default=0)


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
    lines += next_lines(world, "    ", shown=6)
    if world.last_tick_at is not None:
        lines += [Line(),
                Line("  out here", "bold"),
                Line("    a step was last lived "
                     + span((time.time() - world.last_tick_at) / REAL_TIME_PER_VIRTUAL_TIME)
                     + " ago by the wall clock", "dim", under=4)]
    unread = len(world.chronicle) - bookmark.load(world)
    lines += [Line(),
            Line("  %d events since you last looked" % unread if unread
                 else "  you have read everything that has happened", "dim")]
    return lines


def gone_detail(world: World) -> List[Line]:
    """Beings who left, as they were when they went."""
    gone = sorted((being for being in world.beings.values() if not being.present),
                  key=lambda being: being.clock.left_at or 0.0)
    lines = [Line("No longer here", "bold"),
           Line("  Nothing has touched what they hold since they went. The "
                "world has no idea what has become of them and will not "
                "pretend to.", "dim", under=2),
           Line()]
    for being in gone:
        left = being.clock.left_at
        lines.append(Line("  " + pad(being.name, 9)
                        + (timestamp(left) if left else "gone at some point")))
        lines.append(Line("           a self-schema of %d characters, as it was then"
                        % being.identity.self_schema.characters, "dim"))
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
                        + (being.activity.doing or "just here"), under=13))
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
                  key=lambda being: being.clock.left_at or 0.0)
    rows: List[Row] = []
    for being in present:
        place = world.places.get(being.location.place)
        rows.append(Row(being.id, pad(being.name, 9)
                        + (place.name if place else NOTHING)))
    if gone:
        rows.append(Row(""))
        for being in gone:
            left = being.clock.left_at
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
    if being.identity.biography:
        lines.append(Line("  " + being.identity.biography, under=2))
    if being.identity.self_schema.idiolect:
        lines.append(Line("  " + being.identity.self_schema.idiolect, "dim", under=2))
    lines.append(Line())
    if not being.present:
        # Nothing reaches somebody who left, so this is how they stood then.
        lines += [Line("  left on     " + timestamp(being.clock.left_at or world.current),
                     "warn", under=14),
                Line("  What follows is how they stood then.", "dim", under=2)]
    else:
        place = world.places.get(being.location.place)
        home = world.places.get(being.location.home)
        lines.append(Line("  at          " + (place.name if place else NOTHING),
                        under=14))
        lines.append(Line("  sleeps      " + (home.name if home else "nowhere yet"),
                        "dim", under=14))
        if being.activity.doing:
            lines.append(Line("  doing       " + being.activity.doing, under=14))
        lines.append(looks_up(world, being))
    if being.clock.arrived_at:
        lines.append(Line("  came up the road on " + timestamp(being.clock.arrived_at),
                        "dim", under=2))
    earlier = being.activity.doings[:-1]
    if earlier:
        lines += [Line(), Line("  what they had been doing before that", "bold")]
        for what in reversed(earlier):
            lines.append(Line("    " + what, "dim", under=4))
    self_schema = being.identity.self_schema
    lines += [Line(), Line("  who they take themselves to be, %d of %d characters"
                         % (self_schema.characters, SELF_SCHEMA_CHARACTERS), "bold")]
    labelled = ([("trait", trait) for trait in self_schema.traits]
                + [("concern", concern) for concern in self_schema.concerns]
                + [("assumption", assumption) for assumption in self_schema.assumptions]
                + [("impression", impression.being + ": " + impression.impression)
                   for impression in self_schema.impressions])
    for label, line in labelled:
        lines.append(Line("    " + pad(label, 12) + line, under=16))
    if not labelled:
        lines.append(Line("    nothing yet", under=4))
    lines.append(Line("    the newest of %d self-schemas they have held; every one is kept"
                    % len(world.self_schemas(being.id)), "dim", under=4))
    today = memory.short_term(world, being)
    lines += [Line(), Line("  what they have encoded today, not slept on yet" if today
                         else "  nothing encoded since they last slept", "bold")]
    for episode in today:
        lines.append(Line("    " + pad(timestamp(episode.at), 16) + episode.account, under=4))
    engrams = world.engrams(being.id).all()
    lines += [Line(), Line("  what sleep has laid down", "bold")]
    for engram in reversed(engrams[-8:]):
        lines.append(Line("    " + pad(timestamp(engram.at), 16)
                        + " ... ".join(gist.proposition for gist in engram.gists), under=4))
        for episode in episodes_of_engram(world.episodes(being.id).all(), engram):
            lines.append(Line("      " + pad("", 16) + "from " + timestamp(episode.at) + ": "
                            + episode.account, "dim", under=26))
    lines.append(Line("    %d episodes and %d engrams in all; every one is kept"
                    % (len(world.episodes(being.id)), len(engrams)), "dim", under=4))
    return lines


MARKS: Dict[str, str] = {Category.OCCURRENCE: "*", Category.ARRIVAL: "+",
         Category.DEPARTURE: "-", Category.CONVERSATION: "\""}

UNREAD = DASH + " since you last looked " + DASH


def chronicle_rows(world: World) -> List[Row]:
    """Oldest first, with a line where you stopped reading."""
    rows: List[Row] = []
    events = world.chronicle.all()
    read = bookmark.load(world)
    for index, event in enumerate(events):
        if index == read:
            rows.append(Row("", UNREAD, "accent"))
        rows.append(Row(event.id, MARKS.get(event.category, " ") + " "
                        + pad(timestamp(event.at), 16) + event.account))
    if not events:
        rows.append(Row("", "nothing has happened yet", "dim"))
    return rows


def event_detail(world: World, key: str) -> List[Line]:
    event = world.event(key)
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
        episodes = episodes_of_event(world.episodes(being.id).all(), event.id)
        for episode in episodes:
            lines.append(Line("    " + pad(being.name, 9) + "\"" + episode.account + "\"",
                            under=13))
        if not episodes:
            lines.append(Line("    " + pad(being.name, 9)
                            + ("nothing stayed." if being.clock.perceived_through > position
                               else "has not looked up since."), "dim", under=13))
        lines.append(Line("             they were " + perspective.of(world, being, event),
                        "dim", under=13))
    if not reached:
        lines.append(Line("    nobody was reached by it.", "dim"))
    return lines


#: How many of the latest events the map shows under it.
RECENT = 6


def place_rows(world: World) -> List[Row]:
    rows = [Row(WORLD_KEY, world.name + ", as a whole", "accent"), Row("")]
    for place in world.places.values():
        here = world.beings_at(place.id)
        who = ", ".join(being.name for being in here) if here else NOTHING
        rows.append(Row(place.id, pad(clip(place.name, 16), 17) + who,
                        "plain" if here else "dim"))
    return rows


def view_detail(world: World, key: str, columns: int) -> List[Line]:
    """The map, then who is where and what happened lately: everywhere, or
    at the place looked at, whose name is in bold. One line each, so it
    all fits at once; the other views have the rest."""
    labels = {place.id: place.name for place in world.places.values()}
    positions = world.map.positions
    if not positions:
        # Made before places had positions: lay it out here, and keep none of it.
        positions = geography.layout(list(world.places), world.map.ways)
    rows = max(9, min(18, columns // 3))
    drawing, starts = cartography.draw(labels, positions, world.map.ways, columns, rows)
    lines = [Line(text) for text in drawing]
    if key in starts:
        row, column = starts[key]
        lines[row] = Line(lines[row].text, spans=((column, labels[key], "bold"),))
    place = world.places.get(key)
    if place is None:
        beings = sorted((being for being in world.beings.values() if being.present),
                        key=lambda being: being.name)
        events = world.chronicle.all()
    else:
        beings = world.beings_at(place.id)
        events = [event for event in world.chronicle.all() if event.place == place.id]
    if place is None:
        lines += [Line(), Line("Next", "bold")]
        lines += [Line(clip(line.text, columns), line.tone) for line in next_lines(world, "  ")]
    lines += [Line(), Line(place.name if place else "Beings", "bold")]
    for being in beings:
        where = world.places.get(being.location.place)
        text = "  " + pad(being.name, 9)
        if place is None:
            text += pad(clip(where.name if where else NOTHING, 14), 15)
        lines.append(Line(clip(text + (being.activity.doing or "just here"), columns)))
    if not beings:
        lines.append(Line("  nobody is here" if place else "  nobody is left", "dim"))
    lines += [Line(), Line("Lately" if place is None else "Lately, here", "bold")]
    order = {event.id: index for index, event in enumerate(world.chronicle.all())}
    read = bookmark.load(world)
    for event in events[-RECENT:]:
        text = "  " + MARKS.get(event.category, " ") + " " + pad(timestamp(event.at), 16)
        if place is None:
            where = world.places.get(event.place or "")
            text += pad(clip(where.name if where else NOTHING, 12), 13)
        unread = order[event.id] >= read
        lines.append(Line(clip(text + event.account, columns),
                          "plain" if unread else "dim"))
    if not events:
        lines.append(Line("  nothing yet", "dim"))
    return lines


def world_link(world: World, key: str) -> Optional[Tuple[str, str]]:
    """A place, or the world as a whole, is shown on the map."""
    if key == WORLD_KEY or key in world.places:
        return ("view", key)
    return None


def being_link(world: World, key: str) -> Optional[Tuple[str, str]]:
    """Somebody here is shown where they are; somebody gone is nowhere now."""
    being = world.beings.get(key)
    if being is None or not being.present or being.location.place not in world.places:
        return None
    return ("view", being.location.place)


def event_link(world: World, key: str) -> Optional[Tuple[str, str]]:
    """An event is shown where it happened."""
    event = world.event(key)
    if event is None or event.place not in world.places:
        return None
    return ("view", event.place or "")


def view_link(world: World, key: str) -> Optional[Tuple[str, str]]:
    """From the map, a place is read in full."""
    if key == WORLD_KEY or key in world.places:
        return ("world", key)
    return None


VIEWS = (
    View("world", "World", world_rows,
         lambda world, key, columns: world_detail(world, key), world_link),
    View("beings", "Beings", being_rows,
         lambda world, key, columns: being_detail(world, key), being_link),
    View("history", "History", chronicle_rows,
         lambda world, key, columns: event_detail(world, key), event_link),
    View("view", "View", place_rows, view_detail, view_link),
)
