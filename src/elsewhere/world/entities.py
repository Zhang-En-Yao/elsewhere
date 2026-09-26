"""People and places, described the way a person would be described.

Everything here is prose, because the thing that reads it is a language model
and a paragraph is what a language model can actually use. The few numbers are
the ones the engine has to sort by.

A `Being` is three parts, and they are `ARCHITECTURE.md`'s dividing line made
into types rather than into comments:

    who     everything a mind wrote        the engine never reads it to decide
    where   where the world has them       the engine owns all of it
    when    the engine's clock on them     hours, and nothing that means anything

Putting the line in the type is what stops it drifting: crossing it means
typing `.who.`. It is `Concordia`'s answer scaled down - an `EntityAgent`
there is a name and a set of components, and every piece of state lives in the
component that reads it and serialises itself
(`concordia/agents/entity_agent.py`).

A `Place` is prose and nothing else. Which places touch which is not a fact
about a place; it is a fact about the town, and it lives in `Map`.
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
    """Something this person holds to be true, and when they last held it.

    There is no confidence number. What a belief is worth is the same thing a
    memory is worth: how often somebody has had cause to hold it, and how
    lately. So a belief keeps its occasions exactly as a memory does, and
    ``retrieval.base_level`` reads them with the same equation.

    ``origin`` is the memories it grew out of. When none of them can still be
    reached, the belief is held on faith - as firmly as ever, with nothing
    left to point at for why.

    The sentence is ``claim`` and not ``belief``, because ``belief.belief``
    says the word twice and then says nothing. A belief is a claim somebody
    holds; what makes it a belief is the holding, which is ``held``.
    """
    claim: str
    origin: List[str] = field(default_factory=list)   # memory ids, at most 3

    #: Every hour this has been arrived at, first one first. The same shape as
    #: ``Memory.told`` and read by the same function.
    held: List[float] = field(default_factory=list)

    #: Where this reads from. Only ``retrieval.on_faith`` looks at it, to ask
    #: whether thinking about the belief brings its reasons back.
    embedding: List[float] = field(default_factory=list)

    #: A belief is a thing a person carries, so it stands in for a memory
    #: wherever the retrieval layer wants one. These two are what that costs.
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
    """Everything a mind wrote about this being, and the only such place.

    Nothing in here is read by the engine to decide anything. It is handed to
    a mind before it is asked a question and it comes back changed; between
    those two moments the engine does not look at it.

    ``card`` and ``manner`` are given when the being is made; the rest is what
    living has written back. They are one object because they are the same
    kind of thing - somebody's account of themselves - and the difference is
    only how long it has been true.
    """

    #: Who they are, written to them as "you". Prose, because the thing that
    #: reads it is a language model.
    card: str = ""

    #: What they do when they open their mouth, as a fact about them and not
    #: as a specification for their output: "you say as little as will do",
    #: not "short sentences". A fact about a person still means something to a
    #: better model; a note to the renderer is something somebody has to go
    #: and delete out of every saved being on the day the model improves.
    #:
    #: It is a labelled line of its own, and that is load-bearing. The same
    #: sentence folded into `card` measured as nothing, and written town-wide
    #: into `SPEAK_SYSTEM` it made people wordier than no instruction at all.
    manner: str = ""

    #: The one thing from the day that keeps coming back, in their words. Not
    #: a word for how they feel - the thing itself, which carries the feeling
    #: and its cause.
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
    """Where the world has this being. All of it the engine's.

    ``lately`` belongs here rather than in `Who` because it is how they look
    from outside, which is a fact about the place they are standing in. Its
    words are theirs when they chose them and the engine's when it moved them.
    """
    place: str = ""                # a place id; moved on a `go`, nowhere else
    home: str = ""                 # where they sleep; "" for a newcomer

    #: What they have been doing, oldest first, capped at the last few.
    #:
    #: A list rather than one latest string because two things need to answer
    #: "what has this person been doing": `reflect`, so that a day includes
    #: what they did in it and not only what was done to them, and `direct`,
    #: which is how anything anybody does comes to have a consequence here.
    lately: List[str] = field(default_factory=list)

    #: The one they are at now. Derived, so it cannot disagree with the list.
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
    """The engine's clock on this being. Hours into the world, never days.

    Whether they are still here is not among them: it is `left_at is None`,
    and `Being.present` derives it, so the two cannot come apart.
    """
    arrived_at: Optional[float] = None    # None: they were here when it started
    left_at: Optional[float] = None       # when they took the road
    reflected_at: Optional[float] = None  # when they last went over a day

    #: When this being next expects to look up from what they are doing. They
    #: set it themselves, every time they decide anything, and it is the only
    #: thing that says when they are asked again - the engine has no step size
    #: and so no opinion about how often a life needs deciding.
    wake_at: Optional[float] = None

    #: Whether they said they were deep enough in it that what happens near
    #: them is not their business. Something that happens *to* them still
    #: reaches them; a conversation across the yard does not. Set in `act`,
    #: and it lasts as long as the timer beside it.
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
    """Someone the world holds a place for. Not necessarily a person.

    Three things at the top level, and they are the three the whole engine
    addresses a being by: which one this is, what to call them, and - because
    every question the world asks begins with it - whose answers these are.
    Everything else lives in the part of them it belongs to.
    """

    id: str
    name: str
    mind: str = "model"            # model | player - whose answers these are

    who: Who = field(default_factory=Who)
    where: Where = field(default_factory=Where)
    when: When = field(default_factory=When)

    @property
    def present(self) -> bool:
        """In the world at all. Derived, so it cannot contradict the date."""
        return self.when.left_at is None

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "mind": self.mind,
                "who": self.who.to_dict(), "where": self.where.to_dict(),
                "when": self.when.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "Being":
        # Three round-trips, each owned by the part it belongs to, so adding a
        # field to one of them cannot be silently dropped here on the next save.
        return cls(id=d["id"], name=d["name"], mind=d.get("mind", "model"),
                   who=Who.from_dict(d.get("who", {})),
                   where=Where.from_dict(d.get("where", {})),
                   when=When.from_dict(d.get("when", {})))


@dataclass
class Place:
    """Somewhere in the town. Prose, and nothing else.

    What a place is like is in its description, because that is the part a
    mind reads. Everything else about it - what it touches, whether the road
    out leaves from it - is a fact about the town rather than about the place,
    and lives in `Map`.
    """
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
    """Which places touch which, and where the road out of the world leaves.

    One entry per way, not two, so a way cannot exist in one direction only:
    walking from A to B and walking from B to A are the same fact, and a fact
    stored twice is a fact that is wrong half the time.

    The road out lives here for the same reason. There is one edge to this
    world, and it belongs to the world rather than to whichever place happens
    to sit on it.
    """

    #: Unordered pairs of place ids. Order inside a pair means nothing.
    ways: List[List[str]] = field(default_factory=list)

    #: The one place the road out of the town leaves from, and comes back in
    #: at. Empty in a world with no way out.
    road_out: str = ""

    def beside(self, place_id: str) -> List[str]:
        """Everywhere you can walk to from here, in a settled order."""
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
    """Every way named by either end, once. How a town is written down.

    A seed describes a town the way anybody would - "the garden touches the
    shelter and the waterline" - and this folds that into the one list. Naming
    a way from one end is enough; naming it from both is harmless. A one-way
    path is not writable, which is the point.
    """
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
