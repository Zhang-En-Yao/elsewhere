"""Event-driven scheduling, after Concordia's interrupt scheduler.

The person, the town and the road each set their own timer. The world jumps to
the earliest one; anything that reaches somebody pulls their timer to now
(unless they are `absorbed` and it isn't about them). There is no step size.
"""

from __future__ import annotations

from typing import Iterable, List, Optional


def in_hours(answer: Optional[dict]) -> Optional[float]:
    """The answer's positive `again_in_hours`, else None."""
    if not answer:
        return None
    value = answer.get("again_in_hours")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    hours = float(value)
    return hours if hours > 0.0 else None


def timers(world) -> List[float]:
    found = [timer for timer in (world.town_wake_at, world.road_wake_at) if timer is not None]
    found += [being.when.wake_at for being in world.beings.values()
              if being.present and being.when.wake_at is not None]
    return found


def next_at(world) -> Optional[float]:
    """None means no timer is set anywhere."""
    pending = timers(world)
    return min(pending) if pending else None


def due(world, at: Optional[float] = None) -> List:
    moment = world.at if at is None else at
    return sorted((being for being in world.beings.values()
                   if being.present and being.mind == "model"
                   and being.when.wake_at is not None and being.when.wake_at <= moment),
                  key=lambda being: being.id)


def town_due(world, at: Optional[float] = None) -> bool:
    moment = world.at if at is None else at
    return world.town_wake_at is not None and world.town_wake_at <= moment


def road_due(world, at: Optional[float] = None) -> bool:
    moment = world.at if at is None else at
    return world.road_wake_at is not None and world.road_wake_at <= moment


def rouse(world, being_ids: Iterable[str], about: Iterable[str] = ()) -> None:
    """Pull timers to now. Absorbed people are only roused by events in
    `about`. Timers only ever move earlier."""
    concerned = set(about)
    for being_id in being_ids:
        being = world.beings.get(being_id)
        if being is None or not being.present:
            continue
        if being.when.absorbed and being_id not in concerned:
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
    moment = next_at(world)
    if moment is None:
        return None
    if moment > world.at:
        world.at = moment
    for being in world.beings.values():
        if being.present and being.when.wake_at is None:
            being.when.wake_at = world.at
    if world.town_wake_at is None:
        world.town_wake_at = world.at
    if world.road_wake_at is None:
        world.road_wake_at = world.at
    return world.at
