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
    confidence: float = 0.4        # only ever rises: holding it again tightens
                                   # the grip, and nothing loosens it
    origin: List[str] = field(default_factory=list)   # trace ids, at most 3

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Belief":
        return cls(belief=d["belief"], confidence=float(d.get("confidence", 0.4)),
                   origin=list(d.get("origin", [])))


@dataclass
class Being:
    """Someone the world holds a place for. Not necessarily a person.

    The fields are grouped by who writes them, because that is the division
    the rest of the engine is built on: a mind says who it is and what it is
    carrying, and the engine keeps only what it needs to run the next step.
    Nothing below is read by the engine to decide what a being would do.
    """

    # Which being this is. Set when they are made and not touched again.
    id: str
    name: str
    kind: str = "person"           # person | companion | presence
    mind: str = "model"            # model | player - whose answers these are
    premise: str = ""              # why this being is in the world at all:
                                   # the author's reason, never shown to them

    # What a mind is handed before it is asked anything. Prose, because the
    # thing that reads it is a language model. Written at seed or on arrival;
    # nothing rewrites either of them yet.
    card: str = ""                 # who they are, written to them as "you"
    voice: str = ""                # how they talk - a small model cannot
                                   # infer this from a biography

    # What a mind says about itself. All of it comes back changed from
    # `reflect`, except regards, which so far only the seed writes.
    mood: str = "even"             # a word, not a number
    wants: List[str] = field(default_factory=list)
    beliefs: List[Belief] = field(default_factory=list)
    regards: Dict[str, Regard] = field(default_factory=dict)   # by being id

    # Where they are. Both are place ids, and the engine owns both.
    place: str = ""                # moved on a `go`, and nowhere else
    home: str = ""                 # where they sleep; "" for a newcomer, and
                                   # nothing has given anyone one yet

    # What the engine keeps in order to run the next step.
    present: bool = True           # in the world at all
    doing: str = ""                # what they are doing now: their words when
                                   # they chose it, the engine's when it moved
                                   # them

    # Hours into the world, never days - see the note on the clock in
    # `elsewhere/__init__`.
    arrived_at: Optional[float] = None    # None: they were here when it started
    left_at: Optional[float] = None       # when they took the road; None: still here
    reflected_at: Optional[float] = None  # when they last went over a day of their own

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
    def from_dict(cls, d: dict) -> "Being":
        return cls(
            id=d["id"], name=d["name"], card=d.get("card", ""),
            voice=d.get("voice", ""), place=d.get("place", ""),
            home=d.get("home", ""), mood=d.get("mood", "even"),
            wants=list(d.get("wants", [])),
            regards={k: Regard.from_dict(v)
                     for k, v in d.get("regards", {}).items()},
            beliefs=[Belief.from_dict(b) for b in d.get("beliefs", [])],
            kind=d.get("kind", "person"), premise=d.get("premise", ""),
            mind=d.get("mind", "model"), present=bool(d.get("present", True)),
            arrived_at=d.get("arrived_at"), left_at=d.get("left_at"),
            reflected_at=d.get("reflected_at"),
            doing=d.get("doing", ""),
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
