"""History: what actually happened.

An ``Event`` is the objective record.  What each person keeps of it lives in
``memory.py`` and will rarely agree with this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Event:
    id: str
    day: int
    phase: int
    kind: str                      # "conversation", "fire", "festival", ...
    summary: str                   # neutral, chronicle voice
    place: Optional[str] = None
    participants: List[str] = field(default_factory=list)   # person ids
    witnesses: List[str] = field(default_factory=list)      # person ids present
    themes: List[str] = field(default_factory=list)
    valence: float = 0.0           # -1 grim .. +1 joyful
    intensity: float = 0.3         # 0 mundane .. 1 unforgettable
    data: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "day": self.day, "phase": self.phase, "kind": self.kind,
            "summary": self.summary, "place": self.place,
            "participants": list(self.participants), "witnesses": list(self.witnesses),
            "themes": list(self.themes), "valence": self.valence,
            "intensity": self.intensity, "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            id=d["id"], day=d["day"], phase=d["phase"], kind=d["kind"],
            summary=d["summary"], place=d.get("place"),
            participants=list(d.get("participants", [])),
            witnesses=list(d.get("witnesses", [])),
            themes=list(d.get("themes", [])),
            valence=float(d.get("valence", 0.0)),
            intensity=float(d.get("intensity", 0.3)),
            data=dict(d.get("data", {})),
        )


# Unexpected things that happen to a town.  Weight is relative likelihood per day.
WORLD_EVENTS = [
    # (kind, weight, valence, intensity, themes, template)
    ("fire", 0.6, -0.85, 0.95, ["fire", "loss", "town"],
     "A fire broke out at {place} and burned through the night."),
    ("storm", 1.4, -0.4, 0.6, ["weather", "fear", "town"],
     "A storm came down over {place}; roofs and nerves were tested."),
    ("stranger_arrives", 1.6, 0.25, 0.5, ["arrival", "stranger", "change"],
     "A traveller nobody recognised arrived at {place}."),
    ("market_day", 3.0, 0.35, 0.3, ["town", "gathering", "trade"],
     "It was market day at {place}; the town gathered to trade and gossip."),
    ("first_snow", 0.8, 0.45, 0.5, ["weather", "wonder", "season"],
     "The first snow of the year settled over {place}."),
    ("good_harvest", 1.0, 0.6, 0.5, ["harvest", "relief", "town"],
     "The harvest came in well; {place} smelled of grain for days."),
    ("illness", 0.5, -0.6, 0.7, ["illness", "fear", "care"],
     "A fever went through the houses near {place}."),
    ("birdsong", 2.2, 0.2, 0.15, ["quiet", "season"],
     "Nothing much happened at {place}. The birds were loud."),
    ("flood", 0.4, -0.7, 0.8, ["water", "loss", "town"],
     "The river rose and took the low road past {place}."),
    ("music_night", 1.2, 0.55, 0.45, ["music", "gathering", "joy"],
     "Someone started playing at {place} and half the town stayed until late."),
]
