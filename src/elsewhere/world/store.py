"""Where a world lives on disk, and the lock that stops two ticks at once.

    <world>/
      world.json            clock, places, counters
      people/<id>.json      one card per person
      chronicle.jsonl       append-only history
      memories/<id>.jsonl   one file per person
      transcript/<day>.jsonl every question put to a mind, and its answer
      tick.lock             held while a tick is running
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .. import HOURS_PER_DAY, SCHEMA_VERSION
from .chronicle import Chronicle, Event
from .entities import Person, Place
from .memories import TraceStore

DAYS_PER_SEASON = 30
SEASONS = ("spring", "summer", "autumn", "winter")
DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)

#: The sun does not negotiate. This is the one thing about the hour that the
#: engine states as a fact, because it is one - it is dark or it is not. What
#: being dark is worth doing about is nobody's business but the person's.
DAWN, DUSK = 6.0, 20.0


def season_at(at: float) -> str:
    day = int(at // HOURS_PER_DAY) + 1
    return SEASONS[((day - 1) // DAYS_PER_SEASON) % len(SEASONS)]


def day_of(at: float) -> int:
    """Which day of the world a moment falls on. Worked out, never stored."""
    return int(at // HOURS_PER_DAY) + 1


def clock_at(at: float) -> str:
    """The reading on a clock face: '03:40'. A number, not a name."""
    hour = at % HOURS_PER_DAY
    h = int(hour)
    return f"{h:02d}:{int((hour - h) * 60):02d}"


class Locked(RuntimeError):
    """Another tick is already running in this world."""


@dataclass
class World:
    root: Path
    name: str = "Elsewhere"
    at: float = 0.0                       # hours since the world began
    places: Dict[str, Place] = field(default_factory=dict)
    people: Dict[str, Person] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)
    closed: bool = False
    closed_on: Optional[int] = None
    last_tick_at: Optional[float] = None  # wall clock of the last step lived, epoch s
    news_seen: int = 0                    # chronicle length the last time you looked
    road_asked_at: Optional[float] = None  # when the road was last asked who was coming
    directed_at: Optional[float] = None    # when the town was last asked if anything happens
    chronicle: Chronicle = None          # type: ignore[assignment]
    _traces: Dict[str, TraceStore] = field(default_factory=dict)

    # -- time -------------------------------------------------------------
    # Everything below is worked out from `at`. None of it is stored, and none
    # of it names a part of the day: the engine knows what hour it is and
    # whether the sun is up, and stops there.
    @property
    def days(self) -> float:
        """Hours as days, for arithmetic that is easier to read in days."""
        return self.at / HOURS_PER_DAY

    @property
    def day_index(self) -> int:
        """Which day of the world this is. A count, not a stored field."""
        return int(self.at // HOURS_PER_DAY) + 1

    @property
    def hour(self) -> float:
        return self.at % HOURS_PER_DAY

    @property
    def clock(self) -> str:
        return clock_at(self.at)

    @property
    def daylight(self) -> bool:
        return DAWN <= self.hour < DUSK

    @property
    def season(self) -> str:
        return season_at(self.at)

    @property
    def year(self) -> int:
        return (self.day_index - 1) // DAYS_PER_YEAR + 1

    def label(self) -> str:
        doy = (self.day_index - 1) % DAYS_PER_YEAR + 1
        return f"Year {self.year}, day {doy}, {self.clock} ({self.season})"

    def advance(self, hours: float) -> None:
        self.at += hours

    # -- ids ---------------------------------------------------------------
    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}{n:04d}"

    # -- lookups -----------------------------------------------------------
    def traces(self, person_id: str) -> TraceStore:
        store = self._traces.get(person_id)
        if store is None:
            store = TraceStore(self.root / "memories" / f"{person_id}.jsonl")
            self._traces[person_id] = store
        return store

    def people_at(self, place_id: str) -> List[Person]:
        return [p for p in self.people.values()
                if p.place == place_id and p.present]

    def person_by_name(self, name: str) -> Optional[Person]:
        low = name.strip().lower()
        for p in self.people.values():
            if p.name.lower() == low or p.id == name:
                return p
        for p in self.people.values():
            if p.name.lower().startswith(low):
                return p
        return None

    def place_by_name(self, name: str) -> Optional[Place]:
        low = name.strip().lower()
        for pl in self.places.values():
            if pl.name.lower() == low or pl.id == name:
                return pl
        for pl in self.places.values():
            if low and low in pl.name.lower():
                return pl
        return None

    # -- recording ---------------------------------------------------------
    def record(self, kind: str, what: str, *, where: Optional[str] = None,
               who: Optional[List[str]] = None, present: Optional[List[str]] = None,
               tags: Optional[List[str]] = None, data: Optional[dict] = None) -> Event:
        event = Event(id=self.next_id("ev"), at=self.at,
                      kind=kind, what=what, where=where, who=list(who or []),
                      present=list(present or []), tags=list(tags or []),
                      data=dict(data or {}))
        return self.chronicle.append(event)


# --------------------------------------------------------------------------

def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def save(world: World) -> None:
    _atomic_write(world.root / "world.json", {
        "schema": SCHEMA_VERSION, "name": world.name, "at": world.at,
        "counters": world.counters,
        "closed": world.closed, "closed_on": world.closed_on,
        "last_tick_at": world.last_tick_at, "news_seen": world.news_seen,
        "road_asked_at": world.road_asked_at, "directed_at": world.directed_at,
        "places": {k: v.to_dict() for k, v in world.places.items()},
    })
    for person in world.people.values():
        _atomic_write(world.root / "people" / f"{person.id}.json", person.to_dict())
    for store in world._traces.values():
        store.save()


def load(root) -> World:
    root = Path(root)
    meta_path = root / "world.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"no world at {root}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if int(meta.get("schema", 0)) > SCHEMA_VERSION:
        raise ValueError(f"{root} was written by a newer Elsewhere")
    # A world written before the clock went continuous kept a whole day and a
    # quarter of it. Read it once, in hours, and it is never seen again.
    if "at" in meta:
        at = float(meta["at"])
    else:
        at = float(meta.get("day", 1)) * HOURS_PER_DAY + int(meta.get("phase", 0)) * 6.0
    road = meta.get("road_asked_at")
    if road is None and meta.get("road_asked_on") is not None:
        road = float(meta["road_asked_on"]) * HOURS_PER_DAY
    world = World(
        root=root, name=meta.get("name", "Elsewhere"), at=at,
        counters=dict(meta.get("counters", {})),
        closed=bool(meta.get("closed", False)), closed_on=meta.get("closed_on"),
        last_tick_at=meta.get("last_tick_at"), news_seen=int(meta.get("news_seen", 0)),
        road_asked_at=road, directed_at=meta.get("directed_at"),
        places={k: Place.from_dict(v) for k, v in meta.get("places", {}).items()},
    )
    world.chronicle = Chronicle(root / "chronicle.jsonl")
    for path in sorted((root / "people").glob("*.json")):
        person = Person.from_dict(json.loads(path.read_text(encoding="utf-8")))
        world.people[person.id] = person
    return world


def exists(root) -> bool:
    return (Path(root) / "world.json").exists()


class tick_lock:
    """A directory-based lock: one tick at a time, even under cron."""

    def __init__(self, root, stale_after: float = 900.0):
        self.path = Path(root) / "tick.lock"
        self.stale_after = stale_after

    def __enter__(self) -> "tick_lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.mkdir(self.path)
        except FileExistsError:
            age = time.time() - self.path.stat().st_mtime
            if age < self.stale_after:
                raise Locked(f"a tick has been running for {age:.0f}s "
                             f"({self.path})") from None
            # The previous tick died. Take it over rather than stalling forever.
            os.utime(self.path, None)
        (self.path / "pid").write_text(str(os.getpid()), encoding="utf-8")
        return self

    def __exit__(self, *exc) -> None:
        try:
            (self.path / "pid").unlink(missing_ok=True)
            self.path.rmdir()
        except OSError:
            pass
        return None
