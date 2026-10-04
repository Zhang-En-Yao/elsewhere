"""An event: one thing that happened, as the one record that claims to be true."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import List, Optional


class Category(str, Enum):
    """The categories the engine writes and acts on. A world may record events
    under any other category name (the seed's backstory does)."""

    OCCURRENCE = "occurrence"          # something that befalls the town
    ARRIVAL = "arrival"
    DEPARTURE = "departure"
    CONVERSATION = "conversation"

    def __str__(self) -> str:
        return self.value


PRESENCE_CHANGES = frozenset({Category.ARRIVAL, Category.DEPARTURE})


@dataclass
class Event:
    #: Its place in the chronicle, counting from 1: the third thing that ever
    #: happened here is "3". Append-only, so it never changes.
    id: str
    at: float                      # time since the world began
    category: str                  # a `Category` or a world-specific name
    account: str
    place: Optional[str] = None

    #: `involved`: who it happened to. `informed`: everyone it got to, who are
    #: shown it the next time they look up (`harness.memory.percepts`).
    involved: List[str] = field(default_factory=list)
    informed: List[str] = field(default_factory=list)

    #: Category-specific extras, e.g. speaker or per-person perspectives.
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["category"] = str(self.category)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        return cls(id=data["id"], at=float(data["at"]), category=data["category"],
                   account=data["account"], place=data.get("place"),
                   involved=list(data.get("involved", [])),
                   informed=list(data.get("informed", [])),
                   data=dict(data.get("data", {})))
