"""When anything is next asked anything: the world's only clock discipline.

There is no step size anywhere in this engine. Nothing decides on everybody's
behalf, on one clock, how often a life needs attending to.

This is a small version of Concordia's interrupt-driven scheduler
(``concordia/components/game_master/interrupt_scheduling.py``). Every entity in
the world carries exactly one timer and sets it itself: a person says how long
they expect to be at what they are doing, the town says how long before it is
worth asking whether anything happens to it, the road says the same. The world
advances to whichever of those comes first - by however far it is to the next
thing that wants attention. A town where everybody is asleep skips the night in
one move; a town where something is happening is asked again in minutes.

Two rules, and they are the whole module:

    the world advances to the earliest timer, and never past it
    anything that reaches somebody pulls their timer to now

The second is Concordia's non-maskable interrupt, and it is why a fire does
not have to wait for the person it is about to finish mending a net.

A timer nobody set is not a timer. An entity whose mind gave no usable
duration is woken with whoever is next - it said nothing, so the engine
supplies nothing on its behalf beyond letting it round again.
"""

from __future__ import annotations

from typing import Iterable, List, Optional


def in_hours(answer: Optional[dict], key: str = "for_hours") -> Optional[float]:
    """A duration out of an answer, or nothing at all.

    Nothing is parsed: the schema asks for a number of hours, so there is no
    format and no parser. What is checked is only that a number arrived and
    that it points forwards - a duration of zero is an entity asking to be
    woken before it has finished answering, which is not a duration.
    """
    if not answer:
        return None
    value = answer.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    hours = float(value)
    return hours if hours > 0.0 else None


def timers(world) -> List[float]:
    """Every timer set in this world, whoever set it."""
    out = [t for t in (world.town_wake_at, world.road_wake_at) if t is not None]
    out += [p.when.wake_at for p in world.beings.values()
            if p.present and p.when.wake_at is not None]
    return out


def next_at(world) -> Optional[float]:
    """When the world next has something to do, or None if it has nothing.

    None is a real answer and not a failure to find one: it means every mind
    in the world declined to say when it wanted to be asked again, and the
    engine is not going to decide that for them. `elsewhere catchup` says so
    and stops rather than inventing a day.
    """
    set_ = timers(world)
    return min(set_) if set_ else None


def due(world, at: Optional[float] = None) -> List:
    """The beings whose own timer has come round, in a settled order."""
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
    """Something has reached these people. Whoever it is about looks up.

    Concordia's interrupt, and its mask with it. A person does not go on
    mending a net through a fire because they said four hours before it
    started - but somebody who said they were absorbed does go on through two
    people talking across the yard. A thing that happens *to* them is
    non-maskable, here as there.

    It only ever moves a timer earlier.
    """
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
    """Take this person at their word about how long they will be.

    A mind that gave nothing usable gets no timer of its own and comes round
    when the world next stirs - which is `advance` below, not a number.
    """
    hours = in_hours(answer)
    being.when.wake_at = world.at + hours if hours is not None else None
    being.when.absorbed = bool(answer and answer.get("absorbed"))


def advance(world) -> Optional[float]:
    """Move the clock to the next thing that wants attention.

    Returns where it moved to, or None when nothing in the world is scheduled.
    Anyone with no timer of their own is woken at that same moment: they have
    not asked for any particular hour, so they get whichever one the world was
    going to be at anyway. That is what keeps a world moving when a small
    model answers a question about hours with a sentence.
    """
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
