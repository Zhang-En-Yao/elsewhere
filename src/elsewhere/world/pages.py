"""Every page one person has written, one JSON line per page, never revised.

The chronicle is what happened; this is what it was to them, each time they
wrote it down. Only the newest page is carried (`Who.notebook`); the rest are
kept so nothing a person ever held is lost to the world, only to them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, List


@dataclass
class Page:
    at: float                      # hours into the world
    notebook: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Page":
        return cls(at=float(data["at"]), notebook=data["notebook"])


class Pages:

    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, page: Page) -> Page:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(page.to_dict(), ensure_ascii=False) + "\n")
        return page

    def all(self) -> List[Page]:
        return list(self.read())

    def read(self) -> Iterator[Page]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    yield Page.from_dict(json.loads(line))

    def __len__(self) -> int:
        return len(self.all())
