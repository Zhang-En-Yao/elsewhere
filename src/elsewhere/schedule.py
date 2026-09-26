"""Event-driven scheduling, after Concordia's interrupt scheduler.

The person, the town and the road each set their own timer. The world jumps to
the earliest one; anything that reaches somebody pulls their timer to now
(unless they are `absorbed` and it isn't about them). There is no step size.
"""

from __future__ import annotations

from typing import Iterable, List, Optional


def in_hours(answer: Optional[dict], key: str = "for_hours") -> Optional[float]:
    """A positive number of hours from the answer, else None."""
    if not answer:
        return None
    value = answer.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    hours = float(value)
    return hours if hours > 0.0 else None


def timers(world) -> List[float]:
    out = [t for t in (world.town_wake_at, world.road_wake_at) if t is not None]
    out += [p.when.wake_at for p in world.beings.values()
            if p.present and p.when.wake_at is not None]
    return out


def next_at(world) -> Optional[float]:
    """None means no timer is set anywhere."""
    set_ = timers(world)
    return min(set_) if set_ else None


def due(world, at: Optional[float] = None) -> List:
    when = world.at if at is None else at
    return sorted((p for p in world.beings.values()
                   if p.present and p.mind == "model"
                   and p.when.wake_at is not None and p.when.wake_at <= when),
                  key=lambda p: p.id)


def town_due(world, at: Optional[float] = None) -> bool:
    when = world.at if at is None else at
    return world.town_wake_at is not None and world.town_wake_at <= when


def road_due(world, at: Optional[float] = None) -> bool:
    when = world.at if at is None else at
    return world.road_wake_at is not None and world.road_wake_at <= when


def rouse(world, being_ids: Iterable[str], about: Iterable[str] = ()) -> None:
    """Pull timers to now. Absorbed people are only roused by events in
    `about`. Timers only ever move earlier."""
    theirs = set(about)
    for being_id in being_ids:
        being = world.beings.get(being_id)
        if being is None or not being.present:
            continue
        if being.when.absorbed and being_id not in theirs:
            continue
        if being.when.wake_at is None or being.when.wake_at > world.at:
            being.when.wake_at = world.at


def set_timer(being, world, answer: Optional[dict]) -> None:
    hours = in_hours(answer)
    being.when.wake_at = world.at + hours if hours is not None else None
    being.when.absorbed = bool(answer and answer.get("absorbed"))


def advance_to_next_due(world) -> Optional[float]:
    """Jump to the earliest timer. Anyone without a timer is woken at that
    moment too, so an unusable answer doesn't stall them forever. Returns the
    new time, or None if nothing is scheduled."""
    when = next_at(world)
    if when is None:
        return None
    if when > world.at:
        world.at = when
    for being in world.beings.values():
        if being.present and being.when.wake_at is None:
            being.when.wake_at = world.at
    if world.town_wake_at is None:
        world.town_wake_at = world.at
    if world.road_wake_at is None:
        world.road_wake_at = world.at
    return world.at
