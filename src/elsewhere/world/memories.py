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

    #: Where this reads from, as a vector, written once when the words are.
    #: Not a summary and not for a reader - the only thing that ever looks at
    #: it is `retrieval.nearness`. Empty when no embedder could be reached,
    #: and then retrieval simply falls back on how reachable the memory is.
    embedding: List[float] = field(default_factory=list)
    source: str = "witnessed"      # witnessed | told | made | seen | carried_in
    event_id: Optional[str] = None
    about: List[str] = field(default_factory=list)   # person ids in it
    place: Optional[str] = None
    touched_at: float = 0.0

    #: Every hour it has come up, its own laying-down first, newest last.
    #: A count is not enough: three tellings in one week and three a year
    #: apart leave a memory in very different places, and the decay in
    #: `retrieval.py` sums a term per occasion rather than reading a number.
    #: Capped at the most recent few, which are the ones that carry weight -
    #: the oldest term in the sum is always the smallest.
    told: List[float] = field(default_factory=list)
    heard: Optional[str] = None    # the words they think they were given
    history: List[str] = field(default_factory=list)  # earlier wordings, newest last

    #: How many times it has been brought up, not counting being laid down.
    #: Derived, because `told` is what decay reads and two answers to the
    #: same question drift apart.
    @property
    def recalls(self) -> int:
        return max(0, len(self.told) - 1)

    def came_up(self, at: float, limit: int = 24) -> None:
        """It was brought up now. The occasion is kept, not a tally."""
        self.told.append(at)
        del self.told[:-limit]

    def rewrite(self, new_trace: str, at: float, means: str = "",
                feeling: str = "", embedding: Optional[List[float]] = None) -> None:
        """A mind has looked at this again and it came back different."""
        if new_trace and new_trace != self.trace:
            self.history.append(self.trace)
            del self.history[:-4]
            self.trace = new_trace
            # The words moved, so where they read from moved with them. An
            # embedder that could not be reached leaves the old vector rather
            # than none: stale is nearer the truth than absent.
            if embedding:
                self.embedding = list(embedding)
        if means:
            self.means = means
        if feeling:
            self.feeling = feeling
        self.touched_at = at
        self.came_up(at)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Five places. The vector is only ever compared with other vectors,
        # and full repr costs 14KB a memory for digits nothing can use.
        d["embedding"] = [round(x, 5) for x in self.embedding]
        d["told"] = [round(x, 2) for x in self.told]
        return {k: v for k, v in d.items()
                if v not in (None, [], "") or k in ("id", "owner", "at", "trace")}

    @classmethod
    def from_dict(cls, d: dict) -> "Trace":
        return cls(
            id=d["id"], owner=d["owner"], at=float(d["at"]), trace=d["trace"],
            means=d.get("means", ""), feeling=d.get("feeling", "none"),
            salience=float(d.get("salience", 0.4)),
            embedding=[float(x) for x in d.get("embedding", [])],
            source=d.get("source", "witnessed"), event_id=d.get("event_id"),
            about=list(d.get("about", [])), place=d.get("place"),
            touched_at=float(d.get("touched_at", d["at"])),
            told=[float(x) for x in d.get("told", [])], heard=d.get("heard"),
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
