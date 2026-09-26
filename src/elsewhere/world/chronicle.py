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
    id: str
    at: float                      # hours into the world
    category: str                  # ENGINE_CATEGORIES or a world-specific name
    account: str
    place: Optional[str] = None

    #: `involved`: who it happened to. `reached`: everyone it got to, who are
    #: then asked to perceive it.
    involved: List[str] = field(default_factory=list)
    reached: List[str] = field(default_factory=list)

    #: Category-specific extras, e.g. speaker or per-person vantage.
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(id=d["id"], at=float(d["at"]), category=d["category"],
                   account=d["account"], place=d.get("place"),
                   involved=list(d.get("involved", [])),
                   reached=list(d.get("reached", [])),
                   data=dict(d.get("data", {})))


class Chronicle:

    def __init__(self, path: Path):
        self.path = Path(path)
        self._events: Optional[List[Event]] = None

    def append(self, event: Event) -> Event:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        if self._events is not None:
            self._events.append(event)
        return event

    def all(self) -> List[Event]:
        if self._events is None:
            self._events = list(self._read())
        return self._events

    def _read(self) -> Iterator[Event]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield Event.from_dict(json.loads(line))

    def get(self, event_id: str) -> Optional[Event]:
        for e in self.all():
            if e.id == event_id:
                return e
        return None

    def __len__(self) -> int:
        return len(self.all())
