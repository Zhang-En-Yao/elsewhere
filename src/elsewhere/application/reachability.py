"""What can be reached from where somebody stands: the only facts the engine
checks before anything is offered to a mind, and again before it is done."""

from __future__ import annotations

from typing import List

from ..domain.entities import Being, Place
from ..domain.world import World


def companions(world: World, being: Being) -> List[Being]:
    return [other for other in world.beings_at(being.location.place) if other.id != being.id]


def destinations(world: World, being: Being) -> List[Place]:
    return [
        world.places[neighbour]
        for neighbour in world.map.beside(being.location.place)
        if neighbour in world.places
    ]


def may_leave(world: World, being: Being) -> bool:
    """Does the road go out from where they are standing."""
    return bool(world.map.road) and being.location.place == world.map.road


def may_admit(world: World) -> bool:
    """Is there a road for anybody to come up."""
    return world.map.road in world.places
