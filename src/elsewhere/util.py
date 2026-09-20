"""Small helpers shared across the world."""

from __future__ import annotations

import math
import random
from typing import Iterable, List, Sequence, TypeVar

T = TypeVar("T")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def approach(value: float, target: float, rate: float) -> float:
    """Move ``value`` a fraction ``rate`` of the way towards ``target``."""
    return value + (target - value) * clamp(rate)


def softmax_choice(rng: random.Random, options: Sequence[T], scores: Sequence[float],
                   temperature: float = 0.35) -> T:
    """Pick one option, favouring high scores but never being fully predictable.

    People are not optimisers.  Temperature is what keeps a town from
    becoming a schedule.
    """
    if not options:
        raise ValueError("no options to choose from")
    top = max(scores)
    weights = [math.exp((s - top) / max(temperature, 1e-3)) for s in scores]
    return rng.choices(list(options), weights=weights, k=1)[0]


def weighted_choice(rng: random.Random, pairs: Sequence[tuple]) -> T:
    """``pairs`` is a sequence of ``(item, weight)``."""
    items = [p[0] for p in pairs]
    weights = [max(0.0, float(p[1])) for p in pairs]
    if sum(weights) <= 0:
        return rng.choice(items)
    return rng.choices(items, weights=weights, k=1)[0]


def jitter(rng: random.Random, amount: float = 0.1) -> float:
    return (rng.random() - 0.5) * 2.0 * amount


def top_n(items: Iterable[T], key, n: int) -> List[T]:
    return sorted(items, key=key, reverse=True)[:n]


def join_names(names: Sequence[str]) -> str:
    names = list(names)
    if not names:
        return "no one"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f" and {names[-1]}"
