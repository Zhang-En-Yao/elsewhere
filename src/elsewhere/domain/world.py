"""The world: the clock, the town, the people in it, and its records.

The append-only records (the chronicle, and each person's episodes, engrams
and self-schemas) are reached through `Records`, which `adapters.storage` provides; nothing in
here touches disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Generic, List, Optional, Protocol, TypeVar

from .. import VIRTUAL_TIME_PER_DAY
from .calendar import (DAWN, SECONDS_PER_HOUR, DUSK, clock_of, date_of, day_of, real_of,
                       season_of, year_of)
from .chronicle import Event
from .entities import Being, Map, Place
from .memory import Engram, Episode, SelfSchema

Item = TypeVar("Item")


class Log(Protocol, Generic[Item]):
    """One append-only record: nothing in it is ever revised."""

    def append(self, item: Item) -> Item: ...

    def all(self) -> List[Item]: ...

    def __len__(self) -> int: ...


class Records(Protocol):
    """Where the world's append-only records are kept."""

    @property
    def chronicle(self) -> Log[Event]: ...

    def episodes(self, being_id: str) -> Log[Episode]: ...

    def engrams(self, being_id: str) -> Log[Engram]: ...

    def self_schemas(self, being_id: str) -> Log[SelfSchema]: ...


@dataclass
class World:
    records: Records
    name: str = "Elsewhere"
    current: float = 0.0                  # virtual time since the world began
    places: Dict[str, Place] = field(default_factory=dict)

    map: Map = field(default_factory=Map)

    beings: Dict[str, Being] = field(default_factory=dict)
    closed: bool = False           # set by `elsewhere end`; `cli.open_live` reads it
    last_tick_at: Optional[float] = None  # wall clock of the last step lived, epoch s
    #: Set by the world agent's own answer, like `Clock.due_at` for a being.
    due_at: Optional[float] = None

    @property
    def chronicle(self) -> Log[Event]:
        return self.records.chronicle

    def episodes(self, being_id: str) -> Log[Episode]:
        return self.records.episodes(being_id)

    def engrams(self, being_id: str) -> Log[Engram]:
        return self.records.engrams(being_id)

    def self_schemas(self, being_id: str) -> Log[SelfSchema]:
        return self.records.self_schemas(being_id)

    @property
    def day(self) -> int:
        return day_of(self.current)

    @property
    def hour(self) -> float:
        return real_of(self.current % VIRTUAL_TIME_PER_DAY) / SECONDS_PER_HOUR

    @property
    def clock(self) -> str:
        return clock_of(self.current)

    @property
    def daylight(self) -> bool:
        return DAWN <= self.hour < DUSK

    @property
    def season(self) -> str:
        return season_of(self.current)

    @property
    def date(self) -> str:
        return date_of(self.current)

    @property
    def year(self) -> int:
        return year_of(self.current)

    def label(self) -> str:
        return f"{self.date} {self.year}, {self.clock} ({self.season})"

    def event(self, event_id: str) -> Optional[Event]:
        for event in self.chronicle.all():
            if event.id == event_id:
                return event
        return None

    def beings_at(self, place_id: str) -> List[Being]:
        return [being for being in self.beings.values()
                if being.location.place == place_id and being.present]

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
        event = Event(id=str(len(self.chronicle) + 1), at=self.current,
                      category=category, account=account, place=place,
                      involved=list(involved or []), informed=list(informed or []),
                      data=dict(data or {}))
        return self.chronicle.append(event)
