"""Every note one person has made, one JSON line per note, never revised.

A note is what somebody kept of a moment, in their own words, written in the
same answer as what they did or said next (`act`, `speak`). The notes since
they last settled are their day; `settle` goes over them and writes the page
they carry. All of them are kept: they are what `recollection` searches.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, List


@dataclass
class Note:
    at: float                      # hours into the world
    account: str

    #: The events that had just reached them when they wrote it, if any.
    event_ids: List[str] = field(default_factory=list)

    #: Used only by `recollection`; empty if no embedder could be reached.
    embedding: List[float] = field(default_factory=list)
    #: Which embedder placed it: vectors from two embedders are not comparable.
    embedded_by: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        # Rounded: full precision costs ~14KB per note for nothing.
        data["embedding"] = [round(component, 5) for component in self.embedding]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Note":
        return cls(at=float(data["at"]), account=data["account"],
                   event_ids=list(data.get("event_ids", [])),
                   embedding=[float(component) for component in data.get("embedding", [])],
                   embedded_by=data.get("embedded_by", ""))


class Notes:

    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, note: Note) -> Note:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(note.to_dict(), ensure_ascii=False) + "\n")
        return note

    def all(self) -> List[Note]:
        return list(self.read())

    def read(self) -> Iterator[Note]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    yield Note.from_dict(json.loads(line))

    def about(self, event_id: str) -> List[Note]:
        return [note for note in self.read() if event_id in note.event_ids]

    def __len__(self) -> int:
        return len(self.all())
