"""History: append-only, never revised, never consulted by anyone's memory.

One line of JSON per event. This file is the only thing in Elsewhere that
claims to be true.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional

from .. import HOURS_PER_DAY


#: Only for reading what a world wrote before the clock went continuous.
_WAS_PHASE = {"morning": 0, "afternoon": 1, "evening": 2, "night": 3}


@dataclass
class Event:
    id: str
    at: float                                  # hours into the world
    kind: str
    what: str                                  # neutral, chronicle voice
    where: Optional[str] = None
    who: List[str] = field(default_factory=list)      # people it happened to
    present: List[str] = field(default_factory=list)  # people who were there
    tags: List[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        # Older worlds wrote a whole day and a named quarter of it.
        at = (float(d["at"]) if "at" in d else
              float(d["day"]) * HOURS_PER_DAY + _WAS_PHASE.get(d.get("phase"), 0) * 6.0)
        return cls(id=d["id"], at=at, kind=d["kind"],
                   what=d["what"], where=d.get("where"), who=list(d.get("who", [])),
                   present=list(d.get("present", [])), tags=list(d.get("tags", [])),
                   data=dict(d.get("data", {})))


class Chronicle:
    """An append-only log on disk, read whole and written one line at a time."""

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

    def since(self, day: int) -> List[Event]:
        return [e for e in self.all() if e.day >= day]

    def __len__(self) -> int:
        return len(self.all())
