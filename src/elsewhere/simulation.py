"""The loop.

'The world is not waiting for the player.'

One tick is one phase of one day.  Nothing in here knows or cares whether
anybody is currently watching.
"""

from __future__ import annotations

import random
from typing import List, Optional

from . import actions, culture
from .events import WORLD_EVENTS
from .mind import Action, View, get_mind
from .person import Person
from .util import clamp, weighted_choice
from .worldtime import PHASES

WORLD_EVENT_CHANCE = 0.55      # per day


# --------------------------------------------------------------------------

def build_view(world, person: Person) -> View:
    place = world.places.get(person.place)
    reachable = [world.places[p] for p in (place.neighbours if place else [])
                 if p in world.places]
    recent = [e for e in world.history[-12:] if person.id in e.witnesses]
    return View(
        day=world.clock.day,
        phase=world.clock.phase_name,
        season=world.clock.season,
        place_id=person.place,
        place_name=place.name if place else "nowhere",
        people_here=[p for p in world.people_at(person.place) if p.id != person.id],
        artifacts_here=world.artifacts_at(person.place),
        reachable_places=reachable,
        recent_events=recent,
    )


def drift_needs(person: Person, alone: bool, phase: str) -> None:
    n, t = person.needs, person.traits
    n.company = clamp(n.company + (0.07 if alone else 0.02) * (0.5 + t.warmth))
    n.novelty = clamp(n.novelty + 0.05 * (0.5 + t.openness))
    n.routine = clamp(n.routine + 0.05)
    strongest = person.memories.strongest(1, min_intensity=0.4)
    pressure = strongest[0].intensity if strongest else 0.0
    n.expression = clamp(n.expression + 0.008 + 0.025 * t.expressiveness * pressure)
    if phase in ("evening", "night"):
        n.rest = clamp(n.rest + 0.22)
    else:
        n.rest = clamp(n.rest + 0.10)
    person.mood = person.mood * 0.97      # moods come back to the middle


def daily_maintenance(world) -> None:
    """Forgetting, fading, and the slow work of being away from people."""
    day = world.clock.day
    for person in world.people.values():
        forgotten = person.memories.decay_to(day)
        for m in forgotten:
            if m.intensity > 0.5:
                world.narrate(f"{person.name} has lost hold of {m.gist}")
        if forgotten:
            person.refresh_belief_origins()
        for rel in person.relationships.values():
            if day - rel.last_seen_day > 0:
                rel.fade(1)
        if day % 5 == 0:
            person.memories.prune()


def maybe_world_event(world, rng: random.Random) -> None:
    if rng.random() > WORLD_EVENT_CHANCE:
        return
    kind, _, valence, intensity, themes, template = weighted_choice(
        rng, [(e, e[1]) for e in WORLD_EVENTS])
    public = [p for p in world.places.values() if "public" in p.tags] or \
        list(world.places.values())
    place = rng.choice(public)
    event = world.record(
        kind, template.format(place=place.name), place=place.id,
        themes=list(themes), valence=valence,
        intensity=clamp(intensity * rng.uniform(0.8, 1.15)),
    )
    if event.intensity >= 0.6:
        # Everyone in a town this small hears about a fire.
        for person in world.people.values():
            if not person.present:
                continue
            sub = world.rng_for(world.clock.day, person.id, event.id)
            from .perception import encode_event
            encode_event(person, event, world.clock.day, sub, world.next_id("mem"))
            if person.id not in event.witnesses:
                event.witnesses.append(person.id)
    else:
        actions.broadcast(world, event, rng)
    world.narrate(event.summary)


# --------------------------------------------------------------------------

def tick(world, mind_override: Optional[str] = None) -> None:
    """One phase of one day."""
    world.clock.advance()
    day, phase = world.clock.day, world.clock.phase
    day_rng = world.rng_for("day", day)

    if world.clock.is_new_day:
        daily_maintenance(world)
        culture.observe(world, day_rng)
        maybe_world_event(world, day_rng)
        if day % 30 == 0:
            culture.consider(world, day_rng)

    order = sorted(world.people.values(), key=lambda p: p.id)
    for person in order:
        if not person.present:
            continue
        rng = world.rng_for(day, phase, person.id)
        view = build_view(world, person)
        kind = person.mind_kind
        if mind_override and not person.is_player:
            kind = mind_override
        mind = get_mind(kind)
        try:
            action = mind.decide(person, view, rng)
        except Exception:
            action = Action("wander")
        actions.resolve(world, person, action, rng)
        drift_needs(person, alone=not view.people_here, phase=world.clock.phase_name)


def advance(world, days: int = 1, mind_override: Optional[str] = None,
            on_day=None) -> None:
    """Let time pass.  The player does not have to be here for this."""
    for _ in range(days * len(PHASES)):
        tick(world, mind_override=mind_override)
        if world.clock.is_new_day and on_day is not None:
            on_day(world)


def advance_phases(world, phases: int = 1, mind_override: Optional[str] = None) -> None:
    for _ in range(phases):
        tick(world, mind_override=mind_override)
