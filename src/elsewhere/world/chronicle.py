"""Append-only event history, one JSON line per event."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional


OCCURRENCE = "occurrence"          # something that befalls the town
ARRIVAL = "arrival"
DEPARTURE = "departure"
CONVERSATION = "conversation"

PRESENCE_CHANGES = frozenset({ARRIVAL, DEPARTURE})

#: Categories the engine acts on. A world may record events under any other
#: category name; misspelling one of these silently disables its logic.
ENGINE_CATEGORIES = frozenset({OCCURRENCE, CONVERSATION}) | PRESENCE_CHANGES


@dataclass
class Event:
    #: Its place in the chronicle, counting from 1: the third thing that ever
    #: happened here is "3". Append-only, so it never changes.
    id: str
    at: float                      # hours into the world
    category: str                  # ENGINE_CATEGORIES or a world-specific name
    account: str
    place: Optional[str] = None

    #: `involved`: who it happened to. `informed`: everyone it got to, who are
    #: shown it the next time they look up (`agents.unseen`).
    involved: List[str] = field(default_factory=list)
    informed: List[str] = field(default_factory=list)

    #: Category-specific extras, e.g. speaker or per-person viewpoints.
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        return cls(id=data["id"], at=float(data["at"]), category=data["category"],
                   account=data["account"], place=data.get("place"),
                   involved=list(data.get("involved", [])),
                   informed=list(data.get("informed", [])),
                   data=dict(data.get("data", {})))


class Chronicle:

    def __init__(self, path: Path):
        self.path = Path(path)
        self._events: Optional[List[Event]] = None

    def append(self, event: Event) -> Event:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        if self._events is not None:
            self._events.append(event)
        return event

    def all(self) -> List[Event]:
        if self._events is None:
            self._events = list(self.read())
        return self._events

    def read(self) -> Iterator[Event]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    yield Event.from_dict(json.loads(line))

    def get(self, event_id: str) -> Optional[Event]:
        for event in self.all():
            if event.id == event_id:
                return event
        return None

    def __len__(self) -> int:
        return len(self.all())
