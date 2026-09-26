"""A person's memories. Only minds write the words; the engine records when a
memory came up, and `retrieval` decides whether it can be reached."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional


@dataclass
class Memory:
    id: str
    owner: str
    at: float                      # hours into the world
    account: str
    means: str = ""
    feeling: str = "none"

    #: Used only by spreading activation in `retrieval`; empty if no embedder.
    embedding: List[float] = field(default_factory=list)

    #: Mutually exclusive with `origin`.
    event_id: Optional[str] = None

    #: Source memories, for a thought written by `reflect`.
    origin: List[str] = field(default_factory=list)

    #: Every hour it came up, laying-down first. Occasions rather than a count,
    #: because decay in `retrieval` sums a term per occasion.
    told: List[float] = field(default_factory=list)

    #: Earlier wordings, newest last.
    history: List[str] = field(default_factory=list)

    @property
    def recalls(self) -> int:
        return max(0, len(self.told) - 1)

    def came_up(self, at: float, limit: int = 24) -> None:
        self.told.append(at)
        del self.told[:-limit]

    def rewrite(self, new_account: str, at: float, means: str = "",
                feeling: str = "", embedding: Optional[List[float]] = None) -> None:
        if new_account and new_account != self.account:
            self.history.append(self.account)
            del self.history[:-4]
            self.account = new_account
            # Keep the stale vector if the embedder was unreachable.
            if embedding:
                self.embedding = list(embedding)
        if means:
            self.means = means
        if feeling:
            self.feeling = feeling
        self.came_up(at)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Rounded: full precision costs ~14KB per memory for nothing.
        d["embedding"] = [round(x, 5) for x in self.embedding]
        d["told"] = [round(x, 2) for x in self.told]
        return {k: v for k, v in d.items()
                if v not in (None, [], "") or k in ("id", "owner", "at", "account")}

    @classmethod
    def from_dict(cls, d: dict) -> "Memory":
        return cls(
            id=d["id"], owner=d["owner"], at=float(d["at"]), account=d["account"],
            means=d.get("means", ""), feeling=d.get("feeling", "none"),
            embedding=[float(x) for x in d.get("embedding", [])],
            event_id=d.get("event_id"),
            origin=list(d.get("origin", [])),
            told=[float(x) for x in d.get("told", [])],
            history=list(d.get("history", [])),
        )


class MemoryStore:

    def __init__(self, path: Path):
        self.path = Path(path)
        self.memories: List[Memory] = list(self._read())
        self._dirty = False

    def _read(self) -> Iterator[Memory]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield Memory.from_dict(json.loads(line))

    def add(self, memory: Memory) -> Memory:
        self.memories.append(memory)
        self._dirty = True
        return memory

    def get(self, memory_id: str) -> Optional[Memory]:
        for t in self.memories:
            if t.id == memory_id:
                return t
        return None

    def touch(self) -> None:
        self._dirty = True

    def about_event(self, event_id: str) -> List[Memory]:
        return [t for t in self.memories if t.event_id == event_id]

    def save(self, force: bool = False) -> None:
        if not (self._dirty or force):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for t in self.memories:
                fh.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")
        tmp.replace(self.path)
        self._dirty = False

    def __len__(self) -> int:
        return len(self.memories)

    def __iter__(self):
        return iter(self.memories)
