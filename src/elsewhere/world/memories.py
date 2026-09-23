"""Traces: what a person has, as opposed to what happened.

A trace is written by a mind and rewritten by a mind. The engine never edits
the words. It only records when the trace was last touched, and decides - in
``retrieval.py`` - whether it can be reached at all.

That division is the whole point. Asking a model "do you still remember this?"
while the memory sits in its context is not a question; it is a leading one.
Forgetting has to be something the engine does by not handing it over.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional


@dataclass
class Trace:
    id: str
    owner: str
    at: float                      # hours into the world, when it was laid down
    trace: str                     # what they would say happened
    means: str = ""                # what they think it meant
    feeling: str = "none"
    salience: float = 0.4          # the mind's own weighting, never the engine's
    tags: List[str] = field(default_factory=list)
    source: str = "witnessed"      # witnessed | told | made | seen | carried_in
    event_id: Optional[str] = None
    about: List[str] = field(default_factory=list)   # person ids in it
    place: Optional[str] = None
    touched_at: float = 0.0
    recalls: int = 0
    heard: Optional[str] = None    # the words they think they were given
    history: List[str] = field(default_factory=list)  # earlier wordings, newest last

    def rewrite(self, new_trace: str, at: float, means: str = "",
                feeling: str = "") -> None:
        """A mind has looked at this again and it came back different."""
        if new_trace and new_trace != self.trace:
            self.history.append(self.trace)
            del self.history[:-4]
            self.trace = new_trace
        if means:
            self.means = means
        if feeling:
            self.feeling = feeling
        self.touched_at = at
        self.recalls += 1

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items()
                if v not in (None, [], "") or k in ("id", "owner", "at", "trace")}

    @classmethod
    def from_dict(cls, d: dict) -> "Trace":
        return cls(
            id=d["id"], owner=d["owner"], at=float(d["at"]), trace=d["trace"],
            means=d.get("means", ""), feeling=d.get("feeling", "none"),
            salience=float(d.get("salience", 0.4)), tags=list(d.get("tags", [])),
            source=d.get("source", "witnessed"), event_id=d.get("event_id"),
            about=list(d.get("about", [])), place=d.get("place"),
            touched_at=float(d.get("touched_at", d["at"])),
            recalls=int(d.get("recalls", 0)), heard=d.get("heard"),
            history=list(d.get("history", [])),
        )


class TraceStore:
    """One file per person. Loaded whole, written whole, small enough to."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.traces: List[Trace] = list(self._read())
        self._dirty = False

    def _read(self) -> Iterator[Trace]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield Trace.from_dict(json.loads(line))

    def add(self, trace: Trace) -> Trace:
        self.traces.append(trace)
        self._dirty = True
        return trace

    def get(self, trace_id: str) -> Optional[Trace]:
        for t in self.traces:
            if t.id == trace_id:
                return t
        return None

    def touch(self) -> None:
        self._dirty = True

    def about_event(self, event_id: str) -> List[Trace]:
        return [t for t in self.traces if t.event_id == event_id]

    def save(self, force: bool = False) -> None:
        if not (self._dirty or force):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for t in self.traces:
                fh.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")
        tmp.replace(self.path)
        self._dirty = False

    def __len__(self) -> int:
        return len(self.traces)

    def __iter__(self):
        return iter(self.traces)
