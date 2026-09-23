"""People and places, described the way a person would be described.

The v0.1 world gave everyone five floats. This one gives them a paragraph,
because the thing that reads them is a language model and a paragraph is what
it can actually use. The few numbers that remain are the ones the engine has
to sort by.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class Regard:
    """How one person holds another, and one-way by construction.

    A's regard for B and B's regard for A are separate objects that never
    have to agree, and nothing in the engine reconciles them.

    There is no number here for how close they are. The engine cannot score a
    relationship without scoring it the same way for everybody, and how a
    person fades is already decided one memory at a time in ``retrieval.py``.
    So a regard is what they would say about them and the last hour they
    spoke - a sentence and a fact, neither of them a weight.
    """
    account: str = ""              # what they would say about them, in their words
    last_seen_at: float = 0.0      # hours into the world; 0 if they never have

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Regard":
        return cls(account=d.get("account", ""),
                   last_seen_at=float(d.get("last_seen_at", 0.0)))


@dataclass
class Belief:
    belief: str
    confidence: float = 0.4
    origin: List[str] = field(default_factory=list)   # trace ids, at most 3

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Belief":
        return cls(belief=d["belief"], confidence=float(d.get("confidence", 0.4)),
                   origin=list(d.get("origin", [])))


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
    regards: Dict[str, Regard] = field(default_factory=dict)
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

    def regard(self, other_id: str) -> Regard:
        r = self.regards.get(other_id)
        if r is None:
            r = Regard()
            self.regards[other_id] = r
        return r

    def to_dict(self) -> dict:
        d = asdict(self)
        d["regards"] = {k: v.to_dict() for k, v in self.regards.items()}
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
            regards={k: Regard.from_dict(v)
                     for k, v in d.get("regards", {}).items()},
            beliefs=[Belief.from_dict(b) for b in d.get("beliefs", [])],
            kind=d.get("kind", "person"), note=d.get("note", ""),
            mind=d.get("mind", "model"), present=bool(d.get("present", True)),
            arrived_at=d.get("arrived_at"), left_at=d.get("left_at"),
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
