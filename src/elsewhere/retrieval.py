"""The one judgement the engine keeps: what comes to mind right now.

Everything else in Elsewhere is decided by a mind. This is not, and it cannot
be. A model asked "do you still remember the flood?" while the flood is sitting
in its context will always say yes; a model that is not given the flood cannot
say anything about it at all. Forgetting is therefore not an opinion - it is
what the engine declines to hand over.

What it declines to hand over is decided by ACT-R's declarative memory, used at
its own parameters. The activation equation is Anderson,
Bothell, Byrne, Douglass, Lebiere & Qin (2004), "An integrated theory of the
mind"; the base-level term inside it is Anderson & Schooler (1991), "Reflections
of the Environment in Memory":

    A_i = B_i + SUM_k W_k * S_ki                 activation of a memory
    B_i = ln SUM_j (t - t_j) ** -d               how often, and how lately
    S_ki = S * how near the cue is to it         what this moment points at

`d` (0.5) and `S` (2.0) are ACT-R's published defaults - `:bll` and `:mas` -
and `W` is the attentional weight, which sums to one over the sources of the
moment and so is one when the moment is one thing.

One deviation, and it is named rather than hidden: in symbolic ACT-R the
associative strength is `S_ki = S - ln(fan_k)`, the fan being how many chunks
a cue term appears in. Elsewhere's memories have no slots and no terms, only
sentences, so the strength is read off a sentence embedder instead. That is
the standard substitution when ACT-R is run over distributed representations,
and it is the only thing here that is not the published equation.

There is no retrieval threshold, and so no number in this file that had to be
picked. ACT-R's `:rt` is fitted per task, and its default means nothing at this
world's timescale: it was written for a laboratory where the unit is a second,
not a town where it is a day. Retrieval is instead what ACT-R's is - a
*request*, answered with the most active memories and not with all of them.
What does not come back is forgotten for the purposes of the next thought,
whether or not it is still on disk.

Nothing here weighs a memory by how much it mattered. A memory carries no
importance number, because a person does not carry one. What a memory is worth
is how often anybody has had cause to think of it, which is the base-level
term, and which is Anderson & Schooler's whole claim about why memory decays
the way it does.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Protocol, Sequence, TypeVar

from . import HOURS_PER_DAY
from .world.entities import Belief
from .world.memories import Memory


class Held(Protocol):
    """Anything a person carries that the activation equation can read.

    A memory is one. So is a belief, which is why there is no second copy of
    this equation for beliefs: the question "how near is this to coming to
    mind" is the same question about both, and ACT-R does not care what kind
    of chunk it is looking at.
    """

    @property
    def at(self) -> float:
        """When it was first laid down, in hours into the world."""

    @property
    def told(self) -> List[float]:
        """Every occasion it has come up, its own laying-down first."""

    @property
    def embedding(self) -> List[float]:
        """Where it reads from; empty when no embedder could be reached."""


H = TypeVar("H", bound=Held)

#: ACT-R `:bll`, the base-level decay exponent. Human forgetting is a power
#: law - steep early, long-tailed afterwards - and this is Anderson &
#: Schooler's published value.
DECAY = 0.5

#: ACT-R `:mas`, the maximum associative strength: how far the thing somebody
#: is looking at can raise a memory that is otherwise gone. This is what lets
#: a memory come back years later because a room smelled right, and it is why
#: there is no second mechanism in this file for that case.
MAX_STRENGTH = 2.0

#: ACT-R `:ans`, the logistic retrieval noise. Nothing in the engine branches
#: on it - retrieval here is deterministic, because there is no dice roll left
#: anywhere in this world to seed. It exists so an activation can be shown to
#: a reader as the chance of the thing coming to mind, which is what an
#: activation means.
NOISE = 0.4

#: How many memories a prompt can hold. A budget, not a claim about anybody:
#: ACT-R's own retrieval returns exactly one chunk, and asking for six is this
#: engine admitting that a mind here thinks in paragraphs rather than in single
#: chunks. The number is what fits.
CONTEXT_MEMORIES = 6


def nearness(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine between two places in meaning. 0.0 when either is missing."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def familiarity(memory: Held, at: float) -> float:
    """How familiar this is: how often it has come up, and how lately.

    ACT-R calls this base-level activation, B_i.

        B = ln( SUM over every occasion of (now - then) ** -d )

    One term per occasion, which is why `Memory.told` keeps the occasions and
    not a tally: three tellings in one week and three a year apart are not the
    same memory afterwards, and a count cannot tell them apart.

    `at` and the occasions are both hours into the world, so this moves
    continuously - a memory is slightly further away at dusk than at noon.
    """
    told = memory.told or [memory.at]
    total = 0.0
    for then in told:
        if then > at:
            # Not yet. An occasion that has not happened cannot be why
            # something comes to mind, and clamping its age to an hour
            # instead would make it the freshest thing there.
            continue
        days = max((at - then) / HOURS_PER_DAY, 1.0 / 24.0)
        total += days ** -DECAY
    if total <= 0.0:
        return -math.inf
    return math.log(total)


def spread(memory: Held, cue: Optional[Sequence[float]]) -> float:
    """SUM_k W_k * S_ki: how far what is in front of them raises this.

    The moment is one source, so its attentional weight is the whole of it,
    and the strength is ACT-R's maximum scaled by how near the memory is to
    what the moment is about. A memory the moment does not point at is not
    pushed down for it - ACT-R spreads activation, it does not subtract it.
    """
    if not cue or not memory.embedding:
        return 0.0
    return MAX_STRENGTH * max(nearness(memory.embedding, cue), 0.0)


def activation(memory: Held, at: float,
               cue: Optional[Sequence[float]] = None) -> float:
    """A_i: how near this is to coming to mind, here, now."""
    return familiarity(memory, at) + spread(memory, cue)


def chance(value: float) -> float:
    """An activation as what it means: the chance of it coming to mind.

    For a reader, not for the engine. Nothing branches on this.
    """
    if value == -math.inf:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value / NOISE))


def recallable(memories: Iterable[H], at: float,
               cue: Optional[Sequence[float]] = None,
               limit: int = CONTEXT_MEMORIES) -> List[H]:
    """What this person has within reach, most active first.

    Anything not in this list is, for the purposes of the next thought,
    forgotten - whether or not it is still on disk. That is the whole of
    forgetting in Elsewhere: not a curve with a floor under it, but a request
    that came back with something else.

    `cue` is where the moment reads from - the room they are standing in, the
    person they have turned to, the words today left them with - and it enters
    as ACT-R's spreading activation, which is an addition and not a re-ranking.
    So a memory the moment points straight at can come back over a fresher one
    that it does not, and something long out of reach can return because of
    where somebody is standing. There is no separate mechanism for that case
    and no similarity threshold anywhere in this file.
    """
    ranked = sorted(
        ((t, activation(t, at, cue)) for t in memories),
        key=lambda pair: pair[1], reverse=True)
    return [t for t, a in ranked[:limit] if a > -math.inf]


def out_of_reach(memory: Memory, memories: Iterable[Memory], at: float,
                 cue: Optional[Sequence[float]] = None,
                 limit: int = CONTEXT_MEMORIES) -> bool:
    """Whether this would not come back, asked here, now.

    Always asked against the rest of what this person has, because that is
    what the question means. A memory is not out of reach on its own account;
    it is out of reach because five others came back before it.
    """
    return memory not in recallable(memories, at, cue, limit)


def on_faith(belief: Belief, store, at: float,
             cue: Optional[Sequence[float]] = None) -> bool:
    """Whether this is now held for no reason they can still reach.

    They believe it as firmly as they ever did; what has gone is the memory it
    grew out of. Asked rather than stored, because the answer is only ever a
    fact about right now - and a belief can stop being held on faith, if
    something in the world points back at where it came from.

    The belief itself is the cue when nothing else is, which is the honest
    reading of the question: a person trying to say why they think this is
    thinking about the belief, and if the memory does not come back to them
    then, it is not coming back.

    A belief that never recorded an origin is not counted: nothing was lost,
    it was simply never written down.
    """
    if not belief.origin:
        return False
    within = recallable(store, at, cue if cue else belief.embedding)
    return not any(t is not None and t in within
                   for t in (store.get(i) for i in belief.origin))
