"""Event-driven scheduling, after Concordia's interrupt scheduler.

Each being and the world itself set their own timer. The world jumps to the
earliest one; anything that reaches somebody pulls their timer to now, and what
to do about it, even nothing, is theirs to say when they are asked. There is no
step size.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from ..domain.world import World


def due_from(world: World, duration: Optional[float]) -> Optional[float]:
    """A positive duration from now, else no timer."""
    return world.current + duration if duration is not None and duration > 0.0 else None


def interrupt(world: World, being_ids: Iterable[str]) -> None:
    """Pull timers to now. Timers only ever move earlier."""
    for being_id in being_ids:
        being = world.beings.get(being_id)
        if being is None or not being.present:
            continue
        if being.clock.due_at is None or being.clock.due_at > world.current:
            being.clock.due_at = world.current


def being_due(world: World, being_id: str) -> bool:
    being = world.beings.get(being_id)
    return (being is not None and being.present and being.mind == "model"
            and being.clock.due_at is not None and being.clock.due_at <= world.current)


def world_due(world: World) -> bool:
    return world.due_at is not None and world.due_at <= world.current


def timers(world: World) -> List[float]:
    found = [world.due_at] if world.due_at is not None else []
    found += [being.clock.due_at for being in world.beings.values()
              if being.present and being.clock.due_at is not None]
    return found


def next_at(world: World) -> Optional[float]:
    """None means no timer is set anywhere."""
    pending = timers(world)
    return min(pending) if pending else None


def advance_to_next_due(world: World) -> Optional[float]:
    """Jump to the earliest timer. Anyone without a timer is woken at that
    moment too, so an unusable answer doesn't stall them forever. Returns the
    new time, or None if nothing is scheduled."""
    moment = next_at(world)
    if moment is None:
        return None
    if moment > world.current:
        world.current = moment
    for being in world.beings.values():
        if being.present and being.clock.due_at is None:
            being.clock.due_at = world.current
    if world.due_at is None:
        world.due_at = world.current
    return world.current
