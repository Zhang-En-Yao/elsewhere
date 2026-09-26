"""Where a world lives on disk, and the lock that stops two ticks at once.

    <world>/
      world.json            clock, places, counters
      beings/<id>.json      one card per being
      chronicle.jsonl       append-only history
      memories/<id>.jsonl   one file per being
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
from .entities import Being, Map, Place
from .memories import MemoryStore

#: The year is the idealised Hindu one, because the town's history is dated in
#: it: twelve months of thirty tithis, two months to a season, six seasons,
#: three hundred and sixty days. The months run amanta - a month begins the
#: day after the new moon, so its waxing half comes first and it ends in the
#: dark - which is the reckoning the festival dates in `seed.py` are given in.
DAYS_PER_MONTH = 30
TITHIS_PER_PAKSHA = DAYS_PER_MONTH // 2
MONTHS = ("Chaitra", "Vaishakha", "Jyeshtha", "Ashadha",
          "Shravana", "Bhadrapada", "Ashvina", "Kartika",
          "Margashirsha", "Pausha", "Magha", "Phalguna")

#: Six seasons, two months each, named in plain words rather than as Vasanta
#: and Grishma and the rest: a mind told "the rains" knows what is falling on
#: it, and one told "Varsha" has to know the calendar first.
SEASONS = ("spring", "the heat", "the rains", "autumn", "the cold", "the dry")
DAYS_PER_SEASON = DAYS_PER_MONTH * 2
DAYS_PER_YEAR = DAYS_PER_MONTH * len(MONTHS)

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


def date_at(at: float) -> str:
    """The date in the world's own calendar: 'Kartika 1 waxing'.

    The two days a lunar month is actually named after get said rather than
    numbered, because a full moon and a new moon are things anybody in the
    world can see for themselves.
    """
    day = (day_of(at) - 1) % DAYS_PER_YEAR
    month = MONTHS[day // DAYS_PER_MONTH]
    tithi = day % DAYS_PER_MONTH + 1
    if tithi == TITHIS_PER_PAKSHA:
        return f"the full moon of {month}"
    if tithi == DAYS_PER_MONTH:
        return f"the new moon of {month}"
    if tithi < TITHIS_PER_PAKSHA:
        return f"{month} {tithi} waxing"
    return f"{month} {tithi - TITHIS_PER_PAKSHA} waning"


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

    #: Which places touch which, and where the road out leaves from. The
    #: town's geography, kept once, rather than an adjacency list on each
    #: place that had already drifted out of agreement with itself.
    map: Map = field(default_factory=Map)

    beings: Dict[str, Being] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)
    closed: bool = False           # set by `elsewhere end`; `cli.open_live` reads it
    last_tick_at: Optional[float] = None  # wall clock of the last step lived, epoch s
    news_seen: int = 0                    # chronicle length the last time you looked
    #: The town and the road keep a timer each, the same as a person does, and
    #: set it themselves in their own answer: "nothing today, and nothing
    #: worth asking about for a week". How long a quiet stretch a town gets is
    #: the town's to say; there are no gap constants in the engine.
    town_wake_at: Optional[float] = None
    road_wake_at: Optional[float] = None
    chronicle: Chronicle = None          # type: ignore[assignment]
    _memories: Dict[str, MemoryStore] = field(default_factory=dict)

    # -- time -------------------------------------------------------------
    # Everything below is worked out from `at`. None of it is stored, and none
    # of it names a part of the day: the engine knows what hour it is and
    # whether the sun is up, and stops there.
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
    def date(self) -> str:
        return date_at(self.at)

    @property
    def year(self) -> int:
        return (self.day_index - 1) // DAYS_PER_YEAR + 1

    def label(self) -> str:
        return f"Year {self.year}, {self.date}, {self.clock} ({self.season})"

    def advance(self, hours: float) -> None:
        self.at += hours

    # -- ids ---------------------------------------------------------------
    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}{n:04d}"

    # -- lookups -----------------------------------------------------------
    def memories(self, being_id: str) -> MemoryStore:
        store = self._memories.get(being_id)
        if store is None:
            store = MemoryStore(self.root / "memories" / f"{being_id}.jsonl")
            self._memories[being_id] = store
        return store

    def beings_at(self, place_id: str) -> List[Being]:
        return [p for p in self.beings.values()
                if p.where.place == place_id and p.present]

    def being_by_name(self, name: str) -> Optional[Being]:
        low = name.strip().lower()
        for p in self.beings.values():
            if p.name.lower() == low or p.id == name:
                return p
        for p in self.beings.values():
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
    def record(self, category: str, account: str, *, place: Optional[str] = None,
               involved: Optional[List[str]] = None,
               reached: Optional[List[str]] = None,
               data: Optional[dict] = None) -> Event:
        event = Event(id=self.next_id("ev"), at=self.at,
                      category=category, account=account, place=place,
                      involved=list(involved or []), reached=list(reached or []),
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
        "closed": world.closed,
        "last_tick_at": world.last_tick_at, "news_seen": world.news_seen,
        "town_wake_at": world.town_wake_at, "road_wake_at": world.road_wake_at,
        "places": {k: v.to_dict() for k, v in world.places.items()},
        "map": world.map.to_dict(),
    })
    for being in world.beings.values():
        _atomic_write(world.root / "beings" / f"{being.id}.json", being.to_dict())
    for store in world._memories.values():
        store.save()


def load(root) -> World:
    root = Path(root)
    meta_path = root / "world.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"no world at {root}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    schema = int(meta.get("schema", 0))
    if schema > SCHEMA_VERSION:
        raise ValueError(f"{root} was written by a newer Elsewhere")
    if schema < SCHEMA_VERSION:
        # There is no conversion, on purpose. A bump here means a world that
        # worked differently - not a file that was laid out differently - and
        # filling in the difference would silently invent history nobody
        # lived. Worlds that old are read as a record, not resumed.
        raise ValueError(
            f"{root} was written by Elsewhere schema {schema}, which was a "
            f"differently made world. This one cannot read it.")
    world = World(
        root=root, name=meta.get("name", "Elsewhere"), at=float(meta["at"]),
        counters=dict(meta.get("counters", {})),
        closed=bool(meta.get("closed", False)),
        last_tick_at=meta.get("last_tick_at"), news_seen=int(meta.get("news_seen", 0)),
        town_wake_at=meta.get("town_wake_at"),
        road_wake_at=meta.get("road_wake_at"),
        places={k: Place.from_dict(v) for k, v in meta.get("places", {}).items()},
        map=Map.from_dict(meta.get("map", {})),
    )
    world.chronicle = Chronicle(root / "chronicle.jsonl")
    for path in sorted((root / "beings").glob("*.json")):
        being = Being.from_dict(json.loads(path.read_text(encoding="utf-8")))
        world.beings[being.id] = being
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
