"""People.

'What matters is not only what they know.  It is what their experiences have
made them become.'

A person is a small bundle of dispositions plus everything that has happened
to them.  The dispositions drift; the memories decay; the relationships are
one-sided on both sides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .memory import MemoryStore
from .util import approach, clamp

TRAIT_NAMES = ("openness", "warmth", "energy", "stability", "expressiveness")
NEED_NAMES = ("company", "novelty", "rest", "expression", "routine")

ART_FORMS = ("painting", "song", "story", "poem")


@dataclass
class Traits:
    openness: float = 0.5
    warmth: float = 0.5
    energy: float = 0.5
    stability: float = 0.5
    expressiveness: float = 0.5

    def drift(self, name: str, delta: float) -> None:
        setattr(self, name, clamp(getattr(self, name) + delta))

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> "Traits":
        return cls(**d)


@dataclass
class Needs:
    company: float = 0.4
    novelty: float = 0.3
    rest: float = 0.3
    expression: float = 0.2
    routine: float = 0.3

    def bump(self, name: str, delta: float) -> None:
        setattr(self, name, clamp(getattr(self, name) + delta))

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> "Needs":
        return cls(**d)


@dataclass
class Relationship:
    other: str
    affinity: float = 0.0        # -1 .. 1, how they feel about them
    familiarity: float = 0.0     # 0 .. 1, how well they think they know them
    trust: float = 0.3
    last_seen_day: int = 0
    impressions: List[str] = field(default_factory=list)

    def note(self, impression: str, limit: int = 5) -> None:
        self.impressions.append(impression)
        if len(self.impressions) > limit:
            self.impressions.pop(0)

    def fade(self, days: int) -> None:
        """People you do not see become people you used to know."""
        if days <= 0:
            return
        self.familiarity = clamp(self.familiarity * (0.995 ** days))
        self.affinity = self.affinity * (0.998 ** days)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["impressions"] = list(self.impressions)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Relationship":
        return cls(**d)


@dataclass
class Belief:
    topic: str
    statement: str
    conviction: float = 0.3
    day_formed: int = 0
    based_on: List[str] = field(default_factory=list)   # memory ids
    origin_forgotten: bool = False

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["based_on"] = list(self.based_on)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Belief":
        return cls(**d)


@dataclass
class Style:
    """How this person turns experience into something other people can see."""
    form: str = "story"
    adjectives: List[str] = field(default_factory=lambda: ["plain"])
    motifs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["adjectives"] = list(self.adjectives)
        d["motifs"] = list(self.motifs)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Style":
        return cls(**d)


@dataclass
class Person:
    id: str
    name: str
    age: int = 30
    occupation: str = "villager"
    place: str = ""
    home: str = ""
    traits: Traits = field(default_factory=Traits)
    needs: Needs = field(default_factory=Needs)
    style: Style = field(default_factory=Style)
    memories: MemoryStore = field(default_factory=MemoryStore)
    relationships: Dict[str, Relationship] = field(default_factory=dict)
    beliefs: Dict[str, Belief] = field(default_factory=dict)
    mood: float = 0.0                 # -1 .. 1, slow moving
    mind_kind: str = "rules"          # rules | player | llm
    is_player: bool = False
    present: bool = True              # a player can leave the world
    kind: str = "person"              # person | companion | remembered  (see README)
    note: str = ""                    # why this being is here at all
    last_action: str = ""
    last_created_day: int = 0
    seed_salt: str = ""

    # -- relationships ---------------------------------------------------
    def rel(self, other_id: str) -> Relationship:
        r = self.relationships.get(other_id)
        if r is None:
            r = Relationship(other=other_id)
            self.relationships[other_id] = r
        return r

    def knows(self, other_id: str) -> bool:
        r = self.relationships.get(other_id)
        return bool(r and r.familiarity > 0.05)

    # -- inner life ------------------------------------------------------
    def feel(self, valence: float, weight: float = 0.2) -> None:
        self.mood = clamp(approach(self.mood, valence, weight), -1.0, 1.0)

    def believe(self, topic: str, statement: str, day: int, memory_id: Optional[str],
                conviction_delta: float = 0.15) -> Belief:
        b = self.beliefs.get(topic)
        if b is None:
            b = Belief(topic=topic, statement=statement, conviction=0.25, day_formed=day)
            self.beliefs[topic] = b
        # Conviction approaches certainty without ever getting there.
        b.conviction = clamp(b.conviction + conviction_delta * (1.0 - b.conviction))
        if b.conviction < 0.55:
            b.statement = statement      # still deciding what this means
        # Only the first few memories count as the origin. Later rehearsals
        # keep the belief strong without giving it a new reason to exist, so
        # a belief can end up with no reachable source at all.
        if memory_id and memory_id not in b.based_on and len(b.based_on) < 3:
            b.based_on.append(memory_id)
        return b

    def refresh_belief_origins(self) -> None:
        """A belief can outlive every memory that produced it."""
        for b in self.beliefs.values():
            if not b.based_on:
                continue
            alive = [mid for mid in b.based_on
                     if (m := self.memories.get(mid)) is not None and not m.dormant]
            b.origin_forgotten = not alive

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "age": self.age,
            "occupation": self.occupation, "place": self.place, "home": self.home,
            "traits": self.traits.to_dict(), "needs": self.needs.to_dict(),
            "style": self.style.to_dict(), "memories": self.memories.to_dict(),
            "relationships": {k: v.to_dict() for k, v in self.relationships.items()},
            "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
            "mood": self.mood, "mind_kind": self.mind_kind, "is_player": self.is_player,
            "present": self.present, "kind": self.kind, "note": self.note,
            "last_action": self.last_action,
            "last_created_day": self.last_created_day,
            "seed_salt": self.seed_salt,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Person":
        return cls(
            id=d["id"], name=d["name"], age=d.get("age", 30),
            occupation=d.get("occupation", "villager"),
            place=d.get("place", ""), home=d.get("home", ""),
            traits=Traits.from_dict(d.get("traits", {})),
            needs=Needs.from_dict(d.get("needs", {})),
            style=Style.from_dict(d.get("style", {})),
            memories=MemoryStore.from_dict(d.get("memories", {})),
            relationships={k: Relationship.from_dict(v)
                           for k, v in d.get("relationships", {}).items()},
            beliefs={k: Belief.from_dict(v) for k, v in d.get("beliefs", {}).items()},
            mood=d.get("mood", 0.0), mind_kind=d.get("mind_kind", "rules"),
            is_player=d.get("is_player", False), present=d.get("present", True),
            kind=d.get("kind", "person"), note=d.get("note", ""),
            last_action=d.get("last_action", ""),
            last_created_day=int(d.get("last_created_day", 0)),
            seed_salt=d.get("seed_salt", ""),
        )
