"""Minds.

A mind decides what a person does next.  That is all it does: it never
touches the world directly, and it never sees more than the person could.

Swapping the mind is how Elsewhere can go from a rule engine to a language
model without the world knowing the difference.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol


@dataclass
class Action:
    kind: str                       # rest | talk | travel | work | create | reflect | contemplate | wander | tend | idle
    target: Optional[str] = None    # person id, place id, artifact id
    detail: str = ""
    data: Dict = field(default_factory=dict)


@dataclass
class View:
    """What a person can see from where they are standing.

    Deliberately partial.  Nobody in Elsewhere gets the world object.
    """
    day: int
    phase: str
    season: str
    place_id: str
    place_name: str
    people_here: List = field(default_factory=list)       # List[Person]
    artifacts_here: List = field(default_factory=list)    # List[Artifact]
    reachable_places: List = field(default_factory=list)  # List[Place]
    recent_events: List = field(default_factory=list)     # List[Event] they witnessed


@dataclass
class Scene:
    """Everything a person could draw on while saying one thing out loud."""
    speaker: object                 # Person
    listener: object                # Person
    topic: object = None            # Memory, or None for small talk
    place_name: str = ""
    phase: str = "afternoon"
    season: str = "spring"
    day: int = 0
    familiarity: float = 0.0
    affinity: float = 0.0


class Mind(Protocol):
    kind: str

    def decide(self, person, view: View, rng: random.Random) -> Action:
        ...

    def speak(self, scene: Scene, rng: random.Random) -> str:
        """One line, in this person's voice. Optional; RuleMind is the floor."""
        ...


_REGISTRY: Dict[str, "Mind"] = {}


def register(kind: str, mind: "Mind") -> None:
    _REGISTRY[kind] = mind


def get_mind(kind: str) -> "Mind":
    if kind not in _REGISTRY:
        from .rules import RuleMind
        register("rules", RuleMind())
        if kind not in _REGISTRY:
            return _REGISTRY["rules"]
    return _REGISTRY[kind]


def get_speech(person, scene: "Scene", rng: random.Random) -> Optional[str]:
    """Ask this person's mind for a line, and never let that fail a tick."""
    mind = get_mind(person.mind_kind)
    speak = getattr(mind, "speak", None)
    if speak is None:
        from .rules import RuleMind
        speak = RuleMind().speak
    try:
        line = speak(scene, rng)
    except Exception:
        return None
    line = (line or "").strip()
    return line or None


def _bootstrap() -> None:
    from .rules import RuleMind
    from .player import PlayerMind
    register("rules", RuleMind())
    register("player", PlayerMind())


_bootstrap()
