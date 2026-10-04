"""Where somebody stood when an event reached them."""

from __future__ import annotations

from .chronicle import Event
from .entities import Being
from .world import World


def of(world: World, being: Being, event: Event) -> str:
    """The position a being took the event from: the one recorded with the
    event when it happened, else worked out from where they are."""
    recorded = (event.data.get("perspectives") or {}).get(being.id)
    if recorded:
        return recorded
    if being.id in event.involved:
        return "in the middle of it"
    place = world.places.get(event.place or "")
    here = world.places.get(being.location.place)
    if place and here and here.id == place.id:
        return f"right there, at {place.name}"
    if here:
        return f"at {here.name}, and it reached you from there"
    return "nearby"
