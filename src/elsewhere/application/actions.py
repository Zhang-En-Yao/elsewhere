"""Every action anything in the world can take, each checked against what can
be reached before it is done. Nothing here asks a mind; `server` puts each of
these on the MCP server, and that is the only way they are called.

Being actions: stay, move, talk, say, leave, wait.
World actions: occur, admit, and wait with no being.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Tuple

from . import reachability, schedule
from ..domain.chronicle import Category, Event
from ..domain.entities import Being, Clock, Identity, Location
from ..domain.memory import SelfSchema
from ..domain.world import World


class Refused(ValueError):
    """What was asked for cannot be reached; the message says why."""


class Reach(str, Enum):
    """How far an occurrence is noticed."""

    THERE = "the people there"
    TOWN = "the whole town"

    def __str__(self) -> str:
        return self.value


def present(world: World, being_id: str) -> Being:
    being = world.beings.get(being_id)
    if being is None:
        raise Refused(f"there is nobody called {being_id!r} in {world.name}")
    if not being.present:
        raise Refused(f"{being.name} has left {world.name}")
    return being


def stay(world: World, being_id: str, doing: str = "") -> None:
    present(world, being_id).activity.log(doing.strip() or "stayed where they were")


def move(world: World, being_id: str, to: str) -> str:
    being = present(world, being_id)
    if to not in world.places:
        raise Refused(f"there is no place called {to!r}")
    if not world.map.joins(being.location.place, to):
        raise Refused(f"no way runs from {being.location.place} to {to}")
    origin = being.location.place
    being.location.place = to
    being.activity.log(f"went to {world.places[to].name}")
    return origin


def talk(world: World, being_id: str, to: str) -> bool:
    """Somebody turns to somebody else. False when they are not there to be
    turned to, which is a thing that happened, not a refusal."""
    being = present(world, being_id)
    addressee = world.beings.get(to)
    if addressee is None or addressee.id == being.id:
        raise Refused(f"there is nobody called {to!r} to talk to")
    if not addressee.present or addressee.location.place != being.location.place:
        being.activity.log(f"went looking for {addressee.name}, who had gone")
        return False
    # Being sought out is something that happens to you.
    schedule.interrupt(world, [addressee.id])
    return True


def say(world: World, being_id: str, to: str, utterance: str) -> Event:
    """One thing said out loud. Everyone there is informed, the speaker too,
    so the next turn is a reply to it."""
    speaker = present(world, being_id)
    listener = present(world, to)
    if listener.location.place != speaker.location.place:
        raise Refused(f"{listener.name} is not where {speaker.name} is")
    utterance = utterance.strip()
    if not utterance:
        raise Refused("nothing was said")
    here = [being.id for being in world.beings_at(speaker.location.place)]
    perspectives = {
        other: (
            f"face to face with {speaker.name}"
            if other == listener.id
            else f"nearby, within earshot of {speaker.name} and {listener.name}"
        )
        for other in here
        if other != speaker.id
    }
    return world.record(
        Category.CONVERSATION,
        f'{speaker.name} said to {listener.name}: "{utterance}"',
        place=speaker.location.place,
        involved=[speaker.id, listener.id],
        informed=here,
        data={
            "speaker": speaker.id,
            "listener": listener.id,
            "utterance": utterance,
            "perspectives": perspectives,
        },
    )


def leave(world: World, being_id: str, reason: str = "") -> Event:
    """Somebody takes the road out, and is never asked anything again."""
    being = present(world, being_id)
    if not reachability.may_leave(world, being):
        raise Refused(f"the road does not go out from where {being.name} is standing")
    place = world.places.get(being.location.place)
    where = place.name if place else "the road"
    informed = [resident.id for resident in world.beings.values() if resident.present]
    perspectives = {}
    for other in informed:
        if other == being.id:
            perspectives[other] = f"on the road out of {world.name}, looking back"
        elif world.beings[other].location.place == being.location.place:
            perspectives[other] = f"right there, at {where}"
        else:
            whereabouts = world.places.get(world.beings[other].location.place)
            perspectives[other] = (
                f"at {whereabouts.name}, and word of it reached you there"
                if whereabouts
                else "and word of it reached you"
            )
    event = world.record(
        Category.DEPARTURE,
        f"{being.name} took the road out of {world.name} and did not come back.",
        place=being.location.place,
        involved=[being.id],
        informed=informed,
        data={"reason": reason.strip(), "being": being.id, "perspectives": perspectives},
    )
    schedule.interrupt(world, [other for other in informed if other != being.id])
    being.clock.left_at = world.current
    being.activity.log("took the road out of town")
    return event


def wait(
    world: World, duration: Optional[float], being_id: Optional[str] = None
) -> Optional[float]:
    """Sets the one timer of a being, or of the world when no being is named:
    the only thing that says when they are next asked. No positive duration
    leaves no timer. Returns when it falls due."""
    at = schedule.due_from(world, duration)
    if being_id is None:
        world.due_at = at
        return at
    being = present(world, being_id)
    being.clock.due_at = at
    return at


def occur(
    world: World, what: str, where: str, who: str = "", extent: str = Reach.THERE, why_now: str = ""
) -> Event:
    """Something happens to the town that nobody in it chose. Something that
    happens to somebody happens where they are."""
    what = what.strip()
    if not what:
        raise Refused("nothing was said to happen")
    try:
        noticed = Reach(extent)
    except ValueError:
        raise Refused(f"reach is one of {', '.join(map(str, Reach))}") from None
    residents = [resident for resident in world.beings.values() if resident.present]
    subject = present(world, who) if who else None
    place = world.places.get(subject.location.place if subject else where)
    if place is None:
        raise Refused(f"there is no place called {where!r}")

    informed = (
        [resident.id for resident in residents]
        if noticed == Reach.TOWN
        else [resident.id for resident in world.beings_at(place.id)]
    )
    perspectives = {
        other: (
            f"right there, at {place.name}"
            if world.beings[other].location.place == place.id
            else f"at {world.places[world.beings[other].location.place].name}, "
            f"and word of it reached you there"
        )
        for other in informed
    }
    event = world.record(
        Category.OCCURRENCE,
        what,
        place=place.id,
        involved=[subject.id] if subject is not None else [],
        informed=informed,
        data={"why_now": why_now.strip(), "reach": str(noticed), "perspectives": perspectives},
    )
    schedule.interrupt(world, event.informed)
    return event


def unused_id(world: World, name: str) -> str:
    slug = "".join(character for character in name.lower() if character.isalnum()) or "someone"
    candidate, suffix = slug, 2
    while candidate in world.beings:
        candidate, suffix = f"{slug}{suffix}", suffix + 1
    return candidate


def admit(
    world: World,
    name: str,
    from_where: str = "",
    biography: str = "",
    idiolect: str = "",
    why_now: str = "",
) -> Tuple[Being, Event]:
    """Somebody comes up the road, carrying nothing of this place, and lives
    the day they arrived."""
    name = name.strip()
    if not name:
        raise Refused("nobody was named")
    if not reachability.may_admit(world):
        raise Refused(f"no road comes into {world.name}")
    place = world.places[world.map.road]
    origin = from_where.strip()
    being = Being(
        id=unused_id(world, name),
        name=name,
        identity=Identity(
            biography=biography.strip(),
            self_schema=SelfSchema(at=world.current, idiolect=idiolect.strip()),
        ),
        location=Location(place=place.id, home=""),
        # Nothing that happened here before they came is theirs to see.
        clock=Clock(arrived_at=world.current, perceived_through=len(world.chronicle)),
    )
    world.beings[being.id] = being

    account = being.name
    if origin:
        account += f", from {origin},"
    account += f" came up the road into {world.name}."

    informed = [resident.id for resident in world.beings.values() if resident.present]
    perspectives = {}
    for other in informed:
        if other == being.id:
            perspectives[other] = f"at the top of the road, seeing {world.name} for the first time"
        elif world.beings[other].location.place == place.id:
            perspectives[other] = f"right there, at {place.name}"
        else:
            whereabouts = world.places.get(world.beings[other].location.place)
            perspectives[other] = (
                f"at {whereabouts.name}, and word of it reached you there"
                if whereabouts
                else "and word of it reached you"
            )
    event = world.record(
        Category.ARRIVAL,
        account,
        place=place.id,
        involved=[being.id],
        informed=informed,
        data={
            "why_now": why_now.strip(),
            "from_where": origin,
            "being": being.id,
            "perspectives": perspectives,
        },
    )
    schedule.interrupt(world, event.informed)
    return being, event
