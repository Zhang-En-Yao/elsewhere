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
class Who:
    """Written only by the mind; the engine passes it along but never reads it
    to decide anything."""

    card: str = ""
    # Kept as its own labelled line: folded into `card` it measured as no effect.
    manner: str = ""

    #: Everything this person carries from one day to the next, in their own
    #: words: rewritten whole by `settle`, at most `NOTEBOOK_CHARACTERS` long.
    notebook: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Who":
        return cls(card=data.get("card", ""), manner=data.get("manner", ""),
                   notebook=data.get("notebook", ""))


@dataclass
class Where:
    place: str = ""                # place id
    home: str = ""                 # "" for a newcomer

    #: What they have been doing, oldest first; read by `settle` and `stir`.
    lately: List[str] = field(default_factory=list)

    @property
    def doing(self) -> str:
        return self.lately[-1] if self.lately else ""

    def log(self, what: str, keep: int = 8) -> None:
        if what:
            self.lately.append(what)
            del self.lately[:-keep]

    def to_dict(self) -> dict:
        return {"place": self.place, "home": self.home,
                "lately": list(self.lately)}

    @classmethod
    def from_dict(cls, data: dict) -> "Where":
        return cls(place=data.get("place", ""), home=data.get("home", ""),
                   lately=list(data.get("lately", [])))


@dataclass
class When:
    """Hours into the world. Presence is derived from `left_at` (`Being.present`)."""
    arrived_at: Optional[float] = None    # None: present from the start
    left_at: Optional[float] = None

    #: How long the chronicle was the last time they looked up: what came
    #: after, and reached them, is new to them. A count, not an hour, because a
    #: step can take no time and events at the same hour fall either side of it.
    seen_through: int = 0
    #: How many of their notes they had when they last settled: the rest are
    #: their day, not yet gone over.
    settled_through: int = 0

    #: Set by the being itself in `act`; the only thing that schedules it.
    wake_at: Optional[float] = None
    #: Ignore ambient events until `wake_at`; see `schedule.rouse`.
    absorbed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "When":
        return cls(arrived_at=data.get("arrived_at"), left_at=data.get("left_at"),
                   seen_through=int(data.get("seen_through", 0)),
                   settled_through=int(data.get("settled_through", 0)),
                   wake_at=data.get("wake_at"),
                   absorbed=bool(data.get("absorbed", False)))


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
    def from_dict(cls, data: dict) -> "Being":
        return cls(id=data["id"], name=data["name"], mind=data.get("mind", "model"),
                   who=Who.from_dict(data.get("who", {})),
                   where=Where.from_dict(data.get("where", {})),
                   when=When.from_dict(data.get("when", {})))


@dataclass
class Place:
    id: str
    name: str
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Place":
        return cls(id=data["id"], name=data["name"],
                   description=data.get("description", ""))


@dataclass
class Map:
    """Adjacency is stored once per unordered pair, so ways are always two-way."""

    ways: List[List[str]] = field(default_factory=list)
    #: Where the one road to and from the world touches down; "" if there is none.
    road: str = ""

    def beside(self, place_id: str) -> List[str]:
        neighbours = set()
        for one_endpoint, other_endpoint in self.ways:
            if one_endpoint == place_id:
                neighbours.add(other_endpoint)
            elif other_endpoint == place_id:
                neighbours.add(one_endpoint)
        return sorted(neighbours)

    def joins(self, place_id: str, other_id: str) -> bool:
        return other_id in self.beside(place_id)

    def to_dict(self) -> dict:
        return {"ways": [list(way) for way in self.ways], "road": self.road}

    @classmethod
    def from_dict(cls, data: dict) -> "Map":
        return cls(ways=[list(way) for way in data.get("ways", [])],
                   road=data.get("road", ""))


def ways_from_neighbours(neighbours: Dict[str, List[str]]) -> List[List[str]]:
    """Fold a seed's per-place neighbour lists into deduplicated `ways`."""
    seen = set()
    ways: List[List[str]] = []
    for place_id, others in neighbours.items():
        for other in others:
            pair = tuple(sorted((place_id, other)))
            if pair in seen or place_id == other:
                continue
            seen.add(pair)
            ways.append(list(pair))
    return sorted(ways)
