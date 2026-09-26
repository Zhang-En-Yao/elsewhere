"""People and places.

A `Being` is split in three:

    who     everything a mind wrote        the engine never reads it to decide
    where   where the world has them       owned by the engine
    when    the engine's clock on them     hours into the world
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class Regard:
    """One-way: A's regard for B and B's for A are independent."""
    account: str = ""
    last_seen_at: float = 0.0      # 0 if they never have

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Regard":
        return cls(account=d.get("account", ""),
                   last_seen_at=float(d.get("last_seen_at", 0.0)))


@dataclass
class Belief:
    """No confidence score: its strength is its `held` occasions, read by
    `retrieval` with the same equation as `Memory.told`."""
    claim: str
    origin: List[str] = field(default_factory=list)   # memory ids, at most 3

    held: List[float] = field(default_factory=list)

    embedding: List[float] = field(default_factory=list)

    #: Lets a Belief stand in for a Memory in `retrieval`.
    @property
    def told(self) -> List[float]:
        return self.held

    @property
    def at(self) -> float:
        return self.held[0] if self.held else 0.0

    def came_up(self, at: float, limit: int = 24) -> None:
        self.held.append(at)
        del self.held[:-limit]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["embedding"] = [round(x, 5) for x in self.embedding]
        d["held"] = [round(x, 2) for x in self.held]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Belief":
        return cls(claim=d["claim"], origin=list(d.get("origin", [])),
                   held=[float(x) for x in d.get("held", [])],
                   embedding=[float(x) for x in d.get("embedding", [])])


@dataclass
class Who:
    """Written only by the mind; the engine passes it along but never reads it
    to decide anything."""

    card: str = ""
    # Kept as its own labelled line: folded into `card` it measured as no effect.
    manner: str = ""
    thought: str = ""

    wants: List[str] = field(default_factory=list)
    beliefs: List[Belief] = field(default_factory=list)
    regards: Dict[str, Regard] = field(default_factory=dict)   # by being id

    def regard(self, other_id: str) -> Regard:
        r = self.regards.get(other_id)
        if r is None:
            r = Regard()
            self.regards[other_id] = r
        return r

    def to_dict(self) -> dict:
        return {"card": self.card, "manner": self.manner,
                "thought": self.thought, "wants": list(self.wants),
                "beliefs": [b.to_dict() for b in self.beliefs],
                "regards": {k: v.to_dict() for k, v in self.regards.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "Who":
        return cls(card=d.get("card", ""), manner=d.get("manner", ""),
                   thought=d.get("thought", ""), wants=list(d.get("wants", [])),
                   beliefs=[Belief.from_dict(b) for b in d.get("beliefs", [])],
                   regards={k: Regard.from_dict(v)
                            for k, v in d.get("regards", {}).items()})


@dataclass
class Where:
    place: str = ""                # place id
    home: str = ""                 # "" for a newcomer

    #: What they have been doing, oldest first; read by `reflect` and `direct`.
    lately: List[str] = field(default_factory=list)

    @property
    def doing(self) -> str:
        return self.lately[-1] if self.lately else ""

    def now(self, what: str, keep: int = 8) -> None:
        if what:
            self.lately.append(what)
            del self.lately[:-keep]

    def to_dict(self) -> dict:
        return {"place": self.place, "home": self.home,
                "lately": list(self.lately)}

    @classmethod
    def from_dict(cls, d: dict) -> "Where":
        return cls(place=d.get("place", ""), home=d.get("home", ""),
                   lately=list(d.get("lately", [])))


@dataclass
class When:
    """Hours into the world. Presence is derived from `left_at` (`Being.present`)."""
    arrived_at: Optional[float] = None    # None: present from the start
    left_at: Optional[float] = None
    reflected_at: Optional[float] = None

    #: Set by the being itself in `act`; the only thing that schedules it.
    wake_at: Optional[float] = None
    #: Ignore ambient events until `wake_at`; see `schedule.rouse`.
    absorbed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "When":
        return cls(arrived_at=d.get("arrived_at"), left_at=d.get("left_at"),
                   reflected_at=d.get("reflected_at"), wake_at=d.get("wake_at"),
                   absorbed=bool(d.get("absorbed", False)))


@dataclass
class Being:

    id: str
    name: str
    mind: str = "model"            # model | player

    who: Who = field(default_factory=Who)
    where: Where = field(default_factory=Where)
    when: When = field(default_factory=When)

    @property
    def present(self) -> bool:
        return self.when.left_at is None

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "mind": self.mind,
                "who": self.who.to_dict(), "where": self.where.to_dict(),
                "when": self.when.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "Being":
        return cls(id=d["id"], name=d["name"], mind=d.get("mind", "model"),
                   who=Who.from_dict(d.get("who", {})),
                   where=Where.from_dict(d.get("where", {})),
                   when=When.from_dict(d.get("when", {})))


@dataclass
class Place:
    id: str
    name: str
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Place":
        return cls(id=d["id"], name=d["name"],
                   description=d.get("description", ""))


@dataclass
class Map:
    """Adjacency is stored once per unordered pair, so ways are always two-way."""

    ways: List[List[str]] = field(default_factory=list)
    #: Where the road out of the world leaves; "" if there is none.
    road_out: str = ""

    def beside(self, place_id: str) -> List[str]:
        out = set()
        for a, b in self.ways:
            if a == place_id:
                out.add(b)
            elif b == place_id:
                out.add(a)
        return sorted(out)

    def joins(self, a: str, b: str) -> bool:
        return b in self.beside(a)

    def to_dict(self) -> dict:
        return {"ways": [list(w) for w in self.ways], "road_out": self.road_out}

    @classmethod
    def from_dict(cls, d: dict) -> "Map":
        return cls(ways=[list(w) for w in d.get("ways", [])],
                   road_out=d.get("road_out", ""))


def ways_from_neighbours(neighbours: Dict[str, List[str]]) -> List[List[str]]:
    """Fold a seed's per-place neighbour lists into deduplicated `ways`."""
    seen = set()
    out: List[List[str]] = []
    for place_id, others in neighbours.items():
        for other in others:
            key = tuple(sorted((place_id, other)))
            if key in seen or place_id == other:
                continue
            seen.add(key)
            out.append(list(key))
    return sorted(out)
