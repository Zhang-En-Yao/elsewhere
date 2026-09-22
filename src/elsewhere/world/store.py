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

from .. import SCHEMA_VERSION
from .chronicle import Chronicle, Event
from .entities import Person, Place
from .memories import TraceStore

PHASES = ("morning", "afternoon", "evening", "night")
DAYS_PER_SEASON = 30
SEASONS = ("spring", "summer", "autumn", "winter")
DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)


def season_of(day: int) -> str:
    return SEASONS[((day - 1) // DAYS_PER_SEASON) % len(SEASONS)]


class Locked(RuntimeError):
    """Another tick is already running in this world."""


@dataclass
class World:
    root: Path
    name: str = "Elsewhere"
    day: int = 1
    phase: int = 0
    places: Dict[str, Place] = field(default_factory=dict)
    people: Dict[str, Person] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)
    closed: bool = False
    closed_on: Optional[int] = None
    last_tick_at: Optional[float] = None  # wall clock of the last phase lived, epoch s
    news_seen: int = 0                    # chronicle length the last time you looked
    road_asked_on: Optional[int] = None   # the day the road was last asked who was coming
    chronicle: Chronicle = None          # type: ignore[assignment]
    _traces: Dict[str, TraceStore] = field(default_factory=dict)

    # -- time -------------------------------------------------------------
    @property
    def phase_name(self) -> str:
        return PHASES[self.phase]

    @property
    def season(self) -> str:
        return SEASONS[((self.day - 1) // DAYS_PER_SEASON) % len(SEASONS)]

    @property
    def year(self) -> int:
        return (self.day - 1) // DAYS_PER_YEAR + 1

    def label(self) -> str:
        doy = (self.day - 1) % DAYS_PER_YEAR + 1
        return f"Year {self.year}, day {doy} ({self.season} {self.phase_name})"

    def advance_clock(self) -> None:
        self.phase += 1
        if self.phase >= len(PHASES):
            self.phase = 0
            self.day += 1

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
        event = Event(id=self.next_id("ev"), day=self.day, phase=self.phase_name,
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
        "schema": SCHEMA_VERSION, "name": world.name, "day": world.day,
        "phase": world.phase, "counters": world.counters,
        "closed": world.closed, "closed_on": world.closed_on,
        "last_tick_at": world.last_tick_at, "news_seen": world.news_seen,
        "road_asked_on": world.road_asked_on,
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
    world = World(
        root=root, name=meta.get("name", "Elsewhere"), day=int(meta.get("day", 1)),
        phase=int(meta.get("phase", 0)), counters=dict(meta.get("counters", {})),
        closed=bool(meta.get("closed", False)), closed_on=meta.get("closed_on"),
        last_tick_at=meta.get("last_tick_at"), news_seen=int(meta.get("news_seen", 0)),
        road_asked_on=meta.get("road_asked_on"),
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
