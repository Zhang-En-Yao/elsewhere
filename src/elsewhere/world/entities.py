"""People and places, described the way a person would be described.

The v0.1 world gave everyone five floats. This one gives them a paragraph,
because the thing that reads them is a language model and a paragraph is what
it can actually use. The few numbers that remain are the ones the engine has
to sort by.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .. import HOURS_PER_DAY


def _hours(d: dict, key: str, was: str) -> Optional[float]:
    """Read a moment, converting a whole day written by an older world."""
    if d.get(key) is not None:
        return float(d[key])
    if d.get(was) is not None:
        return float(d[was]) * HOURS_PER_DAY
    return None


@dataclass
class Tie:
    """One person's account of another. Never symmetric."""
    note: str = ""                 # written by the model, in their words
    closeness: float = 0.0         # 0 unknown .. 1 lifelong, for retrieval
    last_seen_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Tie":
        seen = (float(d["last_seen_at"]) if "last_seen_at" in d
                else float(d.get("last_seen_day", 0)) * HOURS_PER_DAY)
        return cls(note=d.get("note", ""), closeness=float(d.get("closeness", 0.0)),
                   last_seen_at=seen)


@dataclass
class Belief:
    text: str
    confidence: float = 0.4
    at: float = 0.0
    origin: List[str] = field(default_factory=list)   # trace ids, at most 3
    origin_lost: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Belief":
        at = (float(d["at"]) if "at" in d
              else float(d.get("day", 0)) * HOURS_PER_DAY)
        return cls(text=d["text"], confidence=float(d.get("confidence", 0.4)),
                   at=at, origin=list(d.get("origin", [])),
                   origin_lost=bool(d.get("origin_lost", False)))


@dataclass
class Person:
    id: str
    name: str
    card: str = ""                 # who they are, in prose; the model may revise it
    voice: str = ""                # how they talk - a small model cannot infer this from a biography
    age: Optional[int] = None
    occupation: str = ""
    place: str = ""
    home: str = ""
    mood: str = "even"             # a word, not a number
    wants: List[str] = field(default_factory=list)
    ties: Dict[str, Tie] = field(default_factory=dict)
    beliefs: List[Belief] = field(default_factory=list)
    kind: str = "person"           # person | companion | presence
    note: str = ""                 # why this being is in the world at all
    mind: str = "model"            # model | player
    present: bool = True
    arrived_at: Optional[float] = None  # None: they were here when it started
    left_at: Optional[float] = None     # when they took the road; None: still here
    reflected_at: Optional[float] = None  # when they last went over a day of their own
    last_action: str = ""
    last_created_day: int = 0

    def tie(self, other_id: str) -> Tie:
        t = self.ties.get(other_id)
        if t is None:
            t = Tie()
            self.ties[other_id] = t
        return t

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ties"] = {k: v.to_dict() for k, v in self.ties.items()}
        d["beliefs"] = [b.to_dict() for b in self.beliefs]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Person":
        return cls(
            id=d["id"], name=d["name"], card=d.get("card", ""),
            voice=d.get("voice", ""), age=d.get("age"),
            occupation=d.get("occupation", ""), place=d.get("place", ""),
            home=d.get("home", ""), mood=d.get("mood", "even"),
            wants=list(d.get("wants", [])),
            ties={k: Tie.from_dict(v) for k, v in d.get("ties", {}).items()},
            beliefs=[Belief.from_dict(b) for b in d.get("beliefs", [])],
            kind=d.get("kind", "person"), note=d.get("note", ""),
            mind=d.get("mind", "model"), present=bool(d.get("present", True)),
            arrived_at=_hours(d, "arrived_at", "arrived_on"),
            left_at=_hours(d, "left_at", "left_on"),
            reflected_at=d.get("reflected_at"),
            last_action=d.get("last_action", ""),
            last_created_day=int(d.get("last_created_day", 0)),
        )


@dataclass
class Place:
    id: str
    name: str
    description: str = ""
    neighbours: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Place":
        return cls(id=d["id"], name=d["name"], description=d.get("description", ""),
                   neighbours=list(d.get("neighbours", [])),
                   tags=list(d.get("tags", [])))
