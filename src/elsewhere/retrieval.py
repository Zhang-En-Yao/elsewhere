"""What comes to mind: ACT-R declarative memory at its published parameters.

Anderson et al. (2004), "An integrated theory of the mind"; base level from
Anderson & Schooler (1991):

    A_i = B_i + SUM_k W_k * S_ki
    B_i = ln SUM_j (t - t_j) ** -d
    S_ki = S * cosine(cue, memory)

The one deviation: symbolic ACT-R uses `S - ln(fan)`; here memories are
sentences, so associative strength comes from an embedder instead.

There is no retrieval threshold. Recall returns the top `limit` by activation;
anything else is forgotten for the next prompt.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Protocol, Sequence, TypeVar

from . import HOURS_PER_DAY
from .world.entities import Belief
from .world.memories import Memory


class Held(Protocol):
    """A Memory or a Belief."""

    @property
    def at(self) -> float:
        ...

    @property
    def told(self) -> List[float]:
        ...

    @property
    def embedding(self) -> List[float]:
        ...


H = TypeVar("H", bound=Held)

#: ACT-R `:bll`, base-level decay.
DECAY = 0.5

#: ACT-R `:mas`, maximum associative strength.
MAX_STRENGTH = 2.0

#: ACT-R `:ans`. Only used by `chance` for display; retrieval is deterministic.
NOISE = 0.4

#: Prompt budget.
CONTEXT_MEMORIES = 6


def nearness(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity; 0.0 when either vector is missing."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def familiarity(memory: Held, at: float) -> float:
    """Base-level activation B_i, summed per occasion in `told`."""
    told = memory.told or [memory.at]
    total = 0.0
    for then in told:
        if then > at:
            # Future occasions don't count (clamping would make them freshest).
            continue
        days = max((at - then) / HOURS_PER_DAY, 1.0 / 24.0)
        total += days ** -DECAY
    if total <= 0.0:
        return -math.inf
    return math.log(total)


def spread(memory: Held, cue: Optional[Sequence[float]]) -> float:
    """Spreading activation with one source (W = 1). Never negative."""
    if not cue or not memory.embedding:
        return 0.0
    return MAX_STRENGTH * max(nearness(memory.embedding, cue), 0.0)


def activation(memory: Held, at: float,
               cue: Optional[Sequence[float]] = None) -> float:
    return familiarity(memory, at) + spread(memory, cue)


def chance(value: float) -> float:
    """Activation as a recall probability, for display only."""
    if value == -math.inf:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value / NOISE))


def recallable(memories: Iterable[H], at: float,
               cue: Optional[Sequence[float]] = None,
               limit: int = CONTEXT_MEMORIES) -> List[H]:
    """Most active first, at most `limit`; everything else counts as forgotten."""
    ranked = sorted(
        ((t, activation(t, at, cue)) for t in memories),
        key=lambda pair: pair[1], reverse=True)
    return [t for t, a in ranked[:limit] if a > -math.inf]


def out_of_reach(memory: Memory, memories: Iterable[Memory], at: float,
                 cue: Optional[Sequence[float]] = None,
                 limit: int = CONTEXT_MEMORIES) -> bool:
    return memory not in recallable(memories, at, cue, limit)


def on_faith(belief: Belief, store, at: float,
             cue: Optional[Sequence[float]] = None) -> bool:
    """True when none of the belief's origin memories can be recalled, cued by
    the belief itself unless a cue is given. Beliefs without an origin never
    count."""
    if not belief.origin:
        return False
    within = recallable(store, at, cue if cue else belief.embedding)
    return not any(t is not None and t in within
                   for t in (store.get(i) for i in belief.origin))
