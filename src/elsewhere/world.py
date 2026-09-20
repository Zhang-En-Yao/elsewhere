"""The world itself: places, people, a chronicle, and the things people made.

The world owns the objective record.  It does not own anyone's mind.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import SCHEMA_VERSION
from .events import Event
from .person import Person
from .worldtime import Clock


@dataclass
class Place:
    id: str
    name: str
    description: str = ""
    neighbours: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["neighbours"] = list(self.neighbours)
        d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Place":
        return cls(**d)


@dataclass
class Artifact:
    """Something a person made out of something that happened to them."""
    id: str
    creator: str
    day: int
    form: str                      # painting | song | story | poem
    title: str
    description: str
    place: str
    themes: List[str] = field(default_factory=list)
    source_memory: Optional[str] = None
    source_event: Optional[str] = None
    encountered_by: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["themes"] = list(self.themes)
        d["encountered_by"] = list(self.encountered_by)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Artifact":
        return cls(**d)


@dataclass
class Tradition:
    """A shared memory that hardened into a practice."""
    id: str
    name: str
    theme: str
    practice: str
    day_founded: int
    day_of_year: int
    founders: List[str] = field(default_factory=list)
    origin_event: Optional[str] = None
    observances: int = 0

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["founders"] = list(self.founders)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Tradition":
        return cls(**d)


@dataclass
class World:
    name: str = "Elsewhere"
    seed: int = 1
    clock: Clock = field(default_factory=Clock)
    places: Dict[str, Place] = field(default_factory=dict)
    people: Dict[str, Person] = field(default_factory=dict)
    history: List[Event] = field(default_factory=list)
    artifacts: Dict[str, Artifact] = field(default_factory=dict)
    traditions: Dict[str, Tradition] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)      # narration of recent ticks
    closed: bool = False                              # no more time passes here
    closed_on: Optional[int] = None                   # the day it stopped

    # -- ids and randomness ----------------------------------------------
    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}{n:04d}"

    def rng_for(self, *parts) -> random.Random:
        """Deterministic per-tick randomness, without storing RNG state.

        The same seed and the same history always produce the same world.
        """
        key = "|".join([str(self.seed)] + [str(p) for p in parts])
        return random.Random(key)

    # -- lookups ----------------------------------------------------------
    def person_by_name(self, name: str) -> Optional[Person]:
        lowered = name.strip().lower()
        for p in self.people.values():
            if p.name.lower() == lowered or p.id == name:
                return p
        for p in self.people.values():
            if p.name.lower().startswith(lowered):
                return p
        return None

    def place_by_name(self, name: str) -> Optional[Place]:
        lowered = name.strip().lower()
        for pl in self.places.values():
            if pl.name.lower() == lowered or pl.id == name:
                return pl
        for pl in self.places.values():
            if lowered and lowered in pl.name.lower():
                return pl
        return None

    def people_at(self, place_id: str, include_absent: bool = False) -> List[Person]:
        return [p for p in self.people.values()
                if p.place == place_id and (include_absent or p.present)]

    def artifacts_at(self, place_id: str) -> List[Artifact]:
        return [a for a in self.artifacts.values() if a.place == place_id]

    def event(self, event_id: str) -> Optional[Event]:
        for e in self.history:
            if e.id == event_id:
                return e
        return None

    def player(self) -> Optional[Person]:
        for p in self.people.values():
            if p.is_player:
                return p
        return None

    # -- recording --------------------------------------------------------
    def record(self, kind: str, summary: str, *, place: Optional[str] = None,
               participants: Optional[List[str]] = None,
               witnesses: Optional[List[str]] = None,
               themes: Optional[List[str]] = None,
               valence: float = 0.0, intensity: float = 0.3,
               data: Optional[dict] = None) -> Event:
        ev = Event(
            id=self.next_id("ev"), day=self.clock.day, phase=self.clock.phase,
            kind=kind, summary=summary, place=place,
            participants=list(participants or []), witnesses=list(witnesses or []),
            themes=list(themes or []), valence=valence, intensity=intensity,
            data=dict(data or {}),
        )
        self.history.append(ev)
        return ev

    def narrate(self, line: str, keep: int = 400) -> None:
        self.log.append(f"[day {self.clock.day}] {line}")
        if len(self.log) > keep:
            del self.log[:-keep]

    # -- serialisation -----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "name": self.name,
            "seed": self.seed,
            "clock": self.clock.to_dict(),
            "places": {k: v.to_dict() for k, v in self.places.items()},
            "people": {k: v.to_dict() for k, v in self.people.items()},
            "history": [e.to_dict() for e in self.history],
            "artifacts": {k: v.to_dict() for k, v in self.artifacts.items()},
            "traditions": {k: v.to_dict() for k, v in self.traditions.items()},
            "counters": dict(self.counters),
            "log": list(self.log),
            "closed": self.closed,
            "closed_on": self.closed_on,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "World":
        return cls(
            name=d.get("name", "Elsewhere"),
            seed=int(d.get("seed", 1)),
            clock=Clock.from_dict(d.get("clock", {"day": 1, "phase": 0})),
            places={k: Place.from_dict(v) for k, v in d.get("places", {}).items()},
            people={k: Person.from_dict(v) for k, v in d.get("people", {}).items()},
            history=[Event.from_dict(e) for e in d.get("history", [])],
            artifacts={k: Artifact.from_dict(v) for k, v in d.get("artifacts", {}).items()},
            traditions={k: Tradition.from_dict(v) for k, v in d.get("traditions", {}).items()},
            counters=dict(d.get("counters", {})),
            log=list(d.get("log", [])),
            closed=bool(d.get("closed", False)),
            closed_on=d.get("closed_on"),
        )
