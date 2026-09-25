"""The one judgement the engine keeps: what can be reached right now.

Everything else in Elsewhere v2 is decided by a mind. This is not, and it
cannot be. A model asked "do you still remember the flood?" while the flood is
sitting in its context will always say yes; a model that is not given the
flood cannot say anything about it at all. Forgetting is therefore not an
opinion - it is what the engine declines to hand over.

So this file does three things and no more:

  * work out how reachable a trace is, from the weight its owner gave it and
    how long it has been since anyone touched it
  * choose the handful that go into the prompt, under a fixed budget
  * decide which ones have sunk below reach, and can only come back if
    something in the world points straight at them

The last of those is also asked about beliefs - whether the memories a belief
grew out of are still within reach - which is the same judgement, not a
fourth one.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence

from . import HOURS_PER_DAY
from .world.entities import Belief
from .world.memories import Trace

#: Anderson & Schooler (1991), "Reflections of the Environment in Memory":
#: the decay exponent of base-level activation. Human forgetting is a power
#: law, not an exponential - steep early, and a long tail afterwards - and
#: this is the published value, not one fitted here.
DECAY = 0.5

#: ACT-R's logistic retrieval noise, which turns an activation into the
#: chance of the thing coming to mind at all.
NOISE = 0.4

#: Below this it does not come to mind. A probability now, and readable as
#: one: less than one chance in sixteen.
FLOOR = 0.06

CONTEXT_TRACES = 6        # how many can be laid in front of a mind at once

#: The one number in this file that belongs to this world rather than to the
#: literature: how long a memory lasts, in days, once somebody has brought it
#: up. The ladder is the one v2 already ran on, so a memory its owner called
#: `stays` that has been mentioned once still goes quiet after about nine
#: months, and `faint` after a fortnight.
#:
#: Anchoring on the mentioned case rather than the unmentioned one is the
#: whole argument. In ACT-R a memory laid down once and never retrieved is a
#: very weak thing; holding *that* to nine months forces the constant up and
#: then every retrieval multiplies from an inflated base, which is how an
#: earlier draft of this had three tellings lasting eleven years. Anchored
#: here, the same law says what this world already believed: what nobody ever
#: speaks of lasts about a season.
LASTS_ONCE_TOLD = 480.0
BY_WEIGHT = 1.72


def lasts(salience: float) -> float:
    """Days a memory of this weight survives, once it has been mentioned."""
    return LASTS_ONCE_TOLD * max(salience, 1e-6) ** BY_WEIGHT


def _base(salience: float) -> float:
    """ACT-R's base-level constant, set by what its owner said it was worth.

    Solved rather than chosen: whatever makes a memory of this weight, laid
    down and mentioned once the next day, fall below `FLOOR` at `lasts()`.
    """
    span = lasts(salience)
    mentioned = span ** -DECAY + max(span - 1.0, 1.0 / 24.0) ** -DECAY
    return NOISE * math.log(FLOOR / (1.0 - FLOOR)) - math.log(mentioned)


def reach(trace: Trace, at: float) -> float:
    """The chance this comes to mind now: ACT-R base-level activation.

        B = base + ln( sum over every time it came up of (now - then) ** -d )
        P = 1 / (1 + exp(-B / noise))

    One term per occasion, which is why `Trace.told` keeps the occasions and
    not a tally: three tellings in one week and three a year apart are not
    the same memory afterwards, and a count cannot tell them apart.

    `at` is hours into the world and so are the occasions, so this moves
    continuously - a memory is slightly further away at dusk than at noon.
    """
    told = trace.told or [trace.at]
    total = 0.0
    for then in told:
        if then > at:
            # Not yet. The clock runs backwards over events already written -
            # see `seed.remember_backstory` - and an occasion that has not
            # happened cannot be why something comes to mind. Clamping its
            # age to an hour instead would make it the freshest thing there.
            continue
        days = max((at - then) / HOURS_PER_DAY, 1.0 / 24.0)
        total += days ** -DECAY
    if total <= 0.0:
        return 0.0
    activation = _base(trace.salience) + math.log(total)
    return 1.0 / (1.0 + math.exp(-activation / NOISE))


def dormant(trace: Trace, at: float) -> bool:
    return reach(trace, at) < FLOOR


def on_faith(belief: Belief, store, at: float) -> bool:
    """Whether this is now held for no reason they can still reach.

    They believe it as firmly as they ever did; what has gone is the memory
    it grew out of. Asked rather than stored, because the answer is only ever
    a fact about right now - and a belief can stop being held on faith, if
    something in the world points back at where it came from.

    A belief that never recorded an origin is not counted: nothing was lost,
    it was simply never written down.
    """
    if not belief.origin:
        return False
    return not any(t is not None and not dormant(t, at)
                   for t in (store.get(i) for i in belief.origin))


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


def recallable(traces: Iterable[Trace], at: float,
               near: Optional[Sequence[float]] = None,
               limit: int = CONTEXT_TRACES) -> List[Trace]:
    """What this person has within reach, most available first.

    Anything not in this list is, for the purposes of the next thought,
    forgotten - whether or not it is still on disk.

    `near` is where the moment reads from - the room, the person being spoken
    to - and it pulls what is like it forward. It is compared against the
    live set rather than against a number, because a raw cosine has no fixed
    meaning: this embedder puts two unrelated sentences at 0.45 and two close
    ones at 0.72, so a threshold would be a constant chosen to suit one model
    and silently wrong for the next. Spread across whatever this person can
    actually reach, the question becomes the answerable one - of the things
    still in reach, which are nearest to right now - and it survives changing
    the embedder underneath it.
    """
    live = [t for t in traces if not dormant(t, at)]
    if not live:
        return []
    weights = [0.0] * len(live)
    if near:
        raw = [nearness(t.embedding, near) for t in live]
        lo, hi = min(raw), max(raw)
        if hi - lo > 1e-9:
            weights = [(s - lo) / (hi - lo) for s in raw]
    ranked = sorted(zip(live, weights),
                    key=lambda p: reach(p[0], at) * (1.0 + 2.0 * p[1]),
                    reverse=True)
    return [t for t, _ in ranked[:limit]]


#: How near something already out of reach has to be before this moment counts
#: as pointing straight at it. Unlike `recallable`, this one cannot be spread
#: across a set: the question is about one memory and the answer has to be no
#: most of the time, so there is a number here and it belongs to the embedder
#: in use. Nothing in the engine calls `cued_return` yet - see ARCHITECTURE.
DIRECT_HIT = 0.7


def cued_return(traces: Iterable[Trace], at: float,
                near: Sequence[float]) -> Optional[Trace]:
    """Something out of reach that this exact moment points straight at.

    'A memory that unexpectedly returns years later.' It has to be a direct
    hit: general similarity is not enough to raise something already gone.
    """
    best, best_score = None, 0.0
    for trace in traces:
        if not dormant(trace, at):
            continue
        how_near = nearness(trace.embedding, near)
        if how_near < DIRECT_HIT:
            continue
        value = how_near * trace.salience
        if value > best_score:
            best, best_score = trace, value
    return best
