"""Memory: what an experience became.

A memory in Elsewhere is not a copy of an event.  It is a lossy, biased,
emotionally weighted trace that keeps changing after the event is over.

Three things decay at different speeds:

    detail     - who said what, in what order        (fades fast)
    strength   - whether the memory can be reached   (fades)
    feeling    - what it felt like                   (fades slowest)

So a person ends up remembering that they were frightened long after they
have lost the details of what frightened them.  When even that is gone the
memory goes dormant - but the belief, the relationship and the small change
of character it already caused remain.  That residue is the point.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, fields
from typing import Dict, Iterable, List, Optional

from .util import clamp

try:                                   # dataclasses sentinel, by any name
    from dataclasses import MISSING as _MISSING
except ImportError:                    # pragma: no cover
    _MISSING = object()

FORGET_THRESHOLD = 0.06
DORMANT_FLOOR = 0.02
BASE_DECAY = 0.018          # per day, before resistance
DETAIL_DECAY_FACTOR = 1.8
FEELING_DECAY_FACTOR = 0.08

# How a person framed the experience.  The same event, different lens.
LENSES = ("fear", "resilience", "change", "loss", "wonder", "duty", "belonging")


@dataclass
class Memory:
    id: str
    owner: str
    day: int
    gist: str                       # what they would say happened
    interpretation: str             # what they think it meant
    feeling: str                    # one word
    lens: str = "change"
    valence: float = 0.0
    intensity: float = 0.4          # emotional charge, decays slowly
    detail: float = 0.8             # decays fast
    strength: float = 0.6           # retrievability
    themes: List[str] = field(default_factory=list)
    people: List[str] = field(default_factory=list)
    place: Optional[str] = None
    event_id: Optional[str] = None
    source: str = "experienced"     # experienced | told | art | introduced | dream
    recalls: int = 0
    last_touch_day: int = 0
    dormant: bool = False
    returned_on: Optional[int] = None
    distortions: List[str] = field(default_factory=list)
    heard: Optional[str] = None     # the words they think they were given

    # -- retrieval -------------------------------------------------------
    @property
    def resistance(self) -> float:
        """Emotion and rehearsal are what keep a memory reachable.

        The curve is deliberately steep: an ordinary afternoon is gone in a
        month or two, while something that mattered can survive years of not
        being thought about.
        """
        return 0.25 + 3.6 * (self.intensity ** 1.5) + 0.35 * math.log1p(self.recalls)

    def decay_to(self, day: int) -> None:
        dt = day - self.last_touch_day
        if dt <= 0:
            return
        self.last_touch_day = day
        k = BASE_DECAY * dt / max(self.resistance, 0.2)
        self.strength *= math.exp(-k)
        self.detail *= math.exp(-k * DETAIL_DECAY_FACTOR)
        self.intensity *= math.exp(-k * FEELING_DECAY_FACTOR)
        if self.strength < FORGET_THRESHOLD and not self.dormant:
            self.dormant = True
            self.detail = 0.0
            self.strength = DORMANT_FLOOR

    def recall(self, day: int, rng: Optional[random.Random] = None) -> None:
        """Remembering is not reading.  It is rewriting."""
        self.decay_to(day)
        self.dormant = False
        self.recalls += 1
        self.strength = clamp(self.strength + 0.18 * (1.0 - self.strength) + 0.05)
        self.last_touch_day = day
        if rng is not None and rng.random() < 0.18 * (1.0 - self.detail):
            self._drift(rng)

    def _drift(self, rng: random.Random) -> None:
        """Each retelling moves the memory a little away from the event."""
        roll = rng.random()
        if roll < 0.45:
            self.intensity = clamp(self.intensity * rng.uniform(1.05, 1.35))
            self.distortions.append("grew larger in the retelling")
        elif roll < 0.8:
            self.valence = clamp(self.valence + rng.uniform(-0.25, 0.25), -1.0, 1.0)
            self.distortions.append("changed colour over time")
        else:
            self.detail = clamp(self.detail * 0.6)
            self.distortions.append("lost its details")

    def text(self) -> str:
        """What this person can actually produce when asked."""
        if self.dormant:
            return "(forgotten)"
        if self.detail > 0.30:
            return self.gist
        if self.detail > 0.08:
            return f"something about the {self._subject()}"
        return f"a feeling of {self.feeling}, with no clear source"

    def _subject(self) -> str:
        if self.themes:
            return self.themes[0]
        return "that time"

    def cues(self) -> set:
        c = set(self.themes)
        if self.place:
            c.add(self.place)
        return c

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> dict:
        """Write only what differs from the defaults.

        A world that has run for years is mostly memories; keeping them small
        is what makes it cheap to leave and come back to.
        """
        always = ("id", "owner", "day", "gist")
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in always:
                out[f.name] = value
                continue
            default = f.default if f.default is not _MISSING else None
            if isinstance(value, list):
                if value:
                    out[f.name] = list(value)
            elif isinstance(value, float):
                if abs(value - float(default or 0.0)) > 1e-6:
                    out[f.name] = round(value, 4)
            elif value != default:
                out[f.name] = value
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "Memory":
        return cls(**d)


@dataclass
class MemoryStore:
    memories: List[Memory] = field(default_factory=list)
    forgotten: int = 0          # memories that left no retrievable trace at all

    def __len__(self) -> int:
        return len(self.memories)

    def __iter__(self):
        return iter(self.memories)

    def add(self, memory: Memory) -> Memory:
        self.memories.append(memory)
        return memory

    def get(self, memory_id: str) -> Optional[Memory]:
        for m in self.memories:
            if m.id == memory_id:
                return m
        return None

    def active(self) -> List[Memory]:
        return [m for m in self.memories if not m.dormant]

    def dormant(self) -> List[Memory]:
        return [m for m in self.memories if m.dormant]

    def about_event(self, event_id: str) -> Optional[Memory]:
        for m in self.memories:
            if m.event_id == event_id:
                return m
        return None

    def by_theme(self, theme: str) -> List[Memory]:
        return [m for m in self.active() if theme in m.themes]

    def strongest(self, n: int = 3, min_intensity: float = 0.0) -> List[Memory]:
        pool = [m for m in self.active() if m.intensity >= min_intensity]
        return sorted(pool, key=lambda m: m.strength * (0.5 + m.intensity), reverse=True)[:n]

    def decay_to(self, day: int) -> List[Memory]:
        """Advance every memory to ``day``.  Returns the ones just forgotten."""
        newly_forgotten = []
        for m in self.memories:
            was = m.dormant
            m.decay_to(day)
            if m.dormant and not was:
                newly_forgotten.append(m)
        return newly_forgotten

    def resurface(self, cues: Iterable[str], day: int, rng: random.Random) -> Optional[Memory]:
        """A place or a word can hand back something long gone.

        'A memory that unexpectedly returns years later.'
        """
        cue_set = set(cues)
        candidates = [m for m in self.dormant() if m.cues() & cue_set]
        if not candidates:
            return None
        m = max(candidates, key=lambda x: x.intensity)
        if rng.random() > 0.12 + 0.4 * m.intensity:
            return None
        m.dormant = False
        m.strength = clamp(0.25 + 0.3 * m.intensity)
        m.detail = clamp(m.detail + 0.15)
        m.last_touch_day = day
        m.returned_on = day
        m.distortions.append("came back unbidden")
        return m

    def conflate(self, rng: random.Random) -> Optional[Memory]:
        """Two faded memories that share a theme can become one.

        This is how a town ends up with a story nobody actually lived.
        """
        faded = [m for m in self.active() if m.detail < 0.4]
        if len(faded) < 2:
            return None
        a = rng.choice(faded)
        partners = [m for m in faded if m is not a and set(m.themes) & set(a.themes)]
        if not partners:
            return None
        b = rng.choice(partners)
        a.gist = f"{a.gist} -- and somehow, in the same breath, {b.gist.lower()}"
        a.intensity = clamp(max(a.intensity, b.intensity) * 1.1)
        a.themes = sorted(set(a.themes) | set(b.themes))
        a.distortions.append("merged with another memory")
        b.dormant = True
        b.strength = DORMANT_FLOOR
        return a

    def prune(self, keep_dormant: int = 20) -> int:
        """Let go of what has no trace left.

        A pruned memory is not undone: the belief, the relationship and the
        change of character it already caused stay behind.
        """
        dormant = [m for m in self.memories if m.dormant]
        if len(dormant) <= keep_dormant:
            return 0
        dormant.sort(key=lambda m: m.intensity)
        drop = set(id(m) for m in dormant[: len(dormant) - keep_dormant])
        before = len(self.memories)
        self.memories = [m for m in self.memories if id(m) not in drop]
        removed = before - len(self.memories)
        self.forgotten += removed
        return removed

    def to_dict(self) -> dict:
        return {"memories": [m.to_dict() for m in self.memories],
                "forgotten": self.forgotten}

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryStore":
        return cls(memories=[Memory.from_dict(m) for m in d.get("memories", [])],
                   forgotten=int(d.get("forgotten", 0)))
