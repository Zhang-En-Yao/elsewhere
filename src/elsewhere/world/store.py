"""A world on disk, and the lock that allows one tick at a time.

    <world>/
      world.json            clock, places, the map
      beings/<id>.json      one card per being, notebook included
      chronicle.jsonl       append-only history
      notes/<id>.jsonl      every note one being has made, append-only
      pages/<id>.jsonl      every page one being has written, append-only
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
from .notes import Notes
from .pages import Pages

#: Idealised Hindu calendar, amanta months (waxing half first), matching the
#: festival dates in `seed.py`.
DAYS_PER_MONTH = 30
TITHIS_PER_PAKSHA = DAYS_PER_MONTH // 2
MONTHS = ("Chaitra", "Vaishakha", "Jyeshtha", "Ashadha",
          "Shravana", "Bhadrapada", "Ashvina", "Kartika",
          "Margashirsha", "Pausha", "Magha", "Phalguna")

#: Plain names rather than Sanskrit ones, so a model knows what they mean.
SEASONS = ("spring", "the heat", "the rains", "autumn", "the cold", "the dry")
DAYS_PER_SEASON = DAYS_PER_MONTH * 2
DAYS_PER_YEAR = DAYS_PER_MONTH * len(MONTHS)

DAWN, DUSK = 6.0, 20.0


def day_at(at: float) -> int:
    return int(at // HOURS_PER_DAY) + 1


def season_at(at: float) -> str:
    return SEASONS[((day_at(at) - 1) // DAYS_PER_SEASON) % len(SEASONS)]


def date_at(at: float) -> str:
    """E.g. 'Kartika 1 waxing'; full and new moons are named."""
    day = (day_at(at) - 1) % DAYS_PER_YEAR
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
    hours, fraction = divmod(at % HOURS_PER_DAY, 1.0)
    return f"{int(hours):02d}:{int(fraction * 60):02d}"


class Locked(RuntimeError):
    """Another tick is already running in this world."""


@dataclass
class World:
    root: Path
    name: str = "Elsewhere"
    at: float = 0.0                       # hours since the world began
    places: Dict[str, Place] = field(default_factory=dict)

    map: Map = field(default_factory=Map)

    beings: Dict[str, Being] = field(default_factory=dict)
    closed: bool = False           # set by `elsewhere end`; `cli.open_live` reads it
    last_tick_at: Optional[float] = None  # wall clock of the last step lived, epoch s
    read_through: int = 0                    # chronicle length the last time you looked
    #: Set by the town's and road's own answers, like `When.wake_at`.
    town_wake_at: Optional[float] = None
    road_wake_at: Optional[float] = None
    chronicle: Chronicle = None          # type: ignore[assignment]

    @property
    def day(self) -> int:
        return day_at(self.at)

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
        return (self.day - 1) // DAYS_PER_YEAR + 1

    def label(self) -> str:
        return f"Year {self.year}, {self.date}, {self.clock} ({self.season})"

    def advance(self, hours: float) -> None:
        self.at += hours

    def notes(self, being_id: str) -> Notes:
        return Notes(self.root / "notes" / f"{being_id}.jsonl")

    def pages(self, being_id: str) -> Pages:
        return Pages(self.root / "pages" / f"{being_id}.jsonl")

    def beings_at(self, place_id: str) -> List[Being]:
        return [being for being in self.beings.values()
                if being.where.place == place_id and being.present]

    def being_by_name(self, name: str) -> Optional[Being]:
        wanted = name.strip().lower()
        for being in self.beings.values():
            if being.name.lower() == wanted or being.id == name:
                return being
        for being in self.beings.values():
            if being.name.lower().startswith(wanted):
                return being
        return None

    def place_by_name(self, name: str) -> Optional[Place]:
        wanted = name.strip().lower()
        for place in self.places.values():
            if place.name.lower() == wanted or place.id == name:
                return place
        for place in self.places.values():
            if wanted and wanted in place.name.lower():
                return place
        return None

    def record(self, category: str, account: str, *, place: Optional[str] = None,
               involved: Optional[List[str]] = None,
               informed: Optional[List[str]] = None,
               data: Optional[dict] = None) -> Event:
        event = Event(id=str(len(self.chronicle) + 1), at=self.at,
                      category=category, account=account, place=place,
                      involved=list(involved or []), informed=list(informed or []),
                      data=dict(data or {}))
        return self.chronicle.append(event)


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def save(world: World) -> None:
    atomic_write(world.root / "world.json", {
        "schema": SCHEMA_VERSION, "name": world.name, "at": world.at,
        "closed": world.closed,
        "last_tick_at": world.last_tick_at, "read_through": world.read_through,
        "town_wake_at": world.town_wake_at, "road_wake_at": world.road_wake_at,
        "places": {place_id: place.to_dict() for place_id, place in world.places.items()},
        "map": world.map.to_dict(),
    })
    for being in world.beings.values():
        atomic_write(world.root / "beings" / f"{being.id}.json", being.to_dict())


def load(root) -> World:
    root = Path(root)
    path = root / "world.json"
    if not path.exists():
        raise FileNotFoundError(f"no world at {root}")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    schema = int(metadata.get("schema", 0))
    if schema > SCHEMA_VERSION:
        raise ValueError(f"{root} was written by a newer Elsewhere")
    if schema < SCHEMA_VERSION:
        # No migration on purpose: a schema bump means the world worked
        # differently, and converting would invent history.
        raise ValueError(
            f"{root} was written by Elsewhere schema {schema}, which was a "
            f"differently made world. This one cannot read it.")
    world = World(
        root=root, name=metadata.get("name", "Elsewhere"), at=float(metadata["at"]),
        closed=bool(metadata.get("closed", False)),
        last_tick_at=metadata.get("last_tick_at"),
        read_through=int(metadata.get("read_through", 0)),
        town_wake_at=metadata.get("town_wake_at"),
        road_wake_at=metadata.get("road_wake_at"),
        places={place_id: Place.from_dict(place)
                for place_id, place in metadata.get("places", {}).items()},
        map=Map.from_dict(metadata.get("map", {})),
    )
    world.chronicle = Chronicle(root / "chronicle.jsonl")
    for card in sorted((root / "beings").glob("*.json")):
        being = Being.from_dict(json.loads(card.read_text(encoding="utf-8")))
        world.beings[being.id] = being
    return world


def exists(root) -> bool:
    return (Path(root) / "world.json").exists()


class TickLock:
    """A directory-based lock: one tick at a time, even under cron."""

    def __init__(self, root, stale_after: float = 900.0):
        self.path = Path(root) / "tick.lock"
        self.stale_after = stale_after

    def __enter__(self) -> "TickLock":
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

    def __exit__(self, *exception) -> None:
        try:
            (self.path / "pid").unlink(missing_ok=True)
            self.path.rmdir()
        except OSError:
            pass
        return None
