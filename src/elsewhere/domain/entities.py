"""People and places.

A `Being` is split in four, by who writes it and who reads it:

    identity   everything a mind wrote        the engine never reads it to decide
    location   where the world has them       owned by the engine
    activity   what they have been doing      owned by the engine
    clock      the engine's clock on them     time since the world began
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .memory import SelfSchema

#: How many of their doings are kept (Miller 1956, the span of immediate memory;
#: Cowan 2001 puts it nearer four): the oldest fall away as new ones are logged.
DOINGS_SPAN = 7


@dataclass
class Identity:
    """Written only by the mind; the engine passes it along but never reads it
    to decide anything."""

    #: Where they came from and who they were then; written once, never revised.
    biography: str = ""

    #: Who they take themselves to be now: rewritten whole by `consolidate`.
    self_schema: SelfSchema = field(default_factory=SelfSchema)

    def to_dict(self) -> dict:
        return {"biography": self.biography, "self_schema": self.self_schema.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "Identity":
        return cls(biography=data.get("biography", ""),
                   self_schema=SelfSchema.from_dict(data.get("self_schema", {})))


@dataclass
class Location:
    place: str = ""                # place id
    home: str = ""                 # "" for a newcomer

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Location":
        return cls(place=data.get("place", ""), home=data.get("home", ""))


@dataclass
class Activity:
    #: What they have been doing, oldest first, at most `DOINGS_SPAN`; read by
    #: `consolidate` and `stir`.
    doings: List[str] = field(default_factory=list)

    @property
    def doing(self) -> str:
        return self.doings[-1] if self.doings else ""

    def log(self, doing: str) -> None:
        if doing:
            self.doings.append(doing)
            del self.doings[:-DOINGS_SPAN]

    def to_dict(self) -> dict:
        return {"doings": list(self.doings)}

    @classmethod
    def from_dict(cls, data: dict) -> "Activity":
        return cls(doings=list(data.get("doings", [])))


@dataclass
class Clock:
    """Time since the world began. Presence is derived from `left_at` (`Being.present`)."""
    arrived_at: Optional[float] = None    # None: present from the start
    left_at: Optional[float] = None

    #: How long the chronicle was the last time they looked up: what came
    #: after, and reached them, is new to them. A count, not a time, because a
    #: step can take no time and events at the same time fall either side of it.
    perceived_through: int = 0
    #: How many episodes they had when they last consolidated: the rest are
    #: their short-term store, not yet slept on.
    consolidated_through: int = 0

    #: Set by the being itself in `act`; the only thing that schedules it.
    due_at: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Clock":
        return cls(arrived_at=data.get("arrived_at"), left_at=data.get("left_at"),
                   perceived_through=int(data.get("perceived_through", 0)),
                   consolidated_through=int(data.get("consolidated_through", 0)),
                   due_at=data.get("due_at"))


@dataclass
class Being:

    id: str
    name: str
    mind: str = "model"            # model | player

    identity: Identity = field(default_factory=Identity)
    location: Location = field(default_factory=Location)
    activity: Activity = field(default_factory=Activity)
    clock: Clock = field(default_factory=Clock)

    @property
    def present(self) -> bool:
        return self.clock.left_at is None

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "mind": self.mind,
                "identity": self.identity.to_dict(),
                "location": self.location.to_dict(),
                "activity": self.activity.to_dict(), "clock": self.clock.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "Being":
        return cls(id=data["id"], name=data["name"], mind=data.get("mind", "model"),
                   identity=Identity.from_dict(data.get("identity", {})),
                   location=Location.from_dict(data.get("location", {})),
                   activity=Activity.from_dict(data.get("activity", {})),
                   clock=Clock.from_dict(data.get("clock", {})))


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
    #: Place id to [x, y], scaled to a unit square; laid out once, by `geography`.
    positions: Dict[str, List[float]] = field(default_factory=dict)

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
        return {"ways": [list(way) for way in self.ways], "road": self.road,
                "positions": {place: list(point) for place, point in self.positions.items()}}

    @classmethod
    def from_dict(cls, data: dict) -> "Map":
        return cls(ways=[list(way) for way in data.get("ways", [])],
                   road=data.get("road", ""),
                   positions={place: [float(value) for value in point]
                              for place, point in data.get("positions", {}).items()})


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
