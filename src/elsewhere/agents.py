"""The places where the world asks a mind a question.

Each function here does the same four things: gather what this person could
possibly draw on, ask, check the answer is usable, and write the consequence
into the ledger. None of them decide anything themselves - if a mind declines
to answer, the person simply had nothing, which is allowed.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from . import prompts, retrieval, schemas
from .backends import Call, Settings, Transcript, ask, get as get_backend
from .world.chronicle import Event
from .world.entities import Person
from .world.memories import Trace

#: How many memories a person may lay down in one day that they will still
#: have years later. Models have no sense of scarcity; the engine supplies it.
HEAVY_PER_DAY = 1
HEAVY = 0.7


def _settings(config, name: str) -> Settings:
    return config[name]


def _others_here(world, person: Person) -> List[Person]:
    return [p for p in world.people_at(person.place) if p.id != person.id]


def _heavy_today(world, person: Person) -> int:
    store = world.traces(person.id)
    return sum(1 for t in store
               if t.day == world.day and t.salience >= HEAVY)


def perceive(world, person: Person, event: Event, config,
             transcript: Optional[Transcript] = None) -> Optional[Trace]:
    """Ask what this event leaves in this person. Usually the answer is nothing."""
    settings = _settings(config, "perceive")
    store = world.traces(person.id)
    cues = retrieval.cues_from(event.tags, [event.where or ""])
    context = retrieval.recallable(store, world.day, cues)

    place = world.places.get(event.where or "")
    call = Call(
        name="perceive",
        system=prompts.PERCEIVE_SYSTEM,
        user=prompts.perceive_user(
            person=person,
            what_happened=event.what,
            where=place.name if place else "nowhere in particular",
            when=f"{world.phase_name} in {world.season}",
            others=_others_here(world, person),
            traces=context,
            part_of_it=person.id in event.who,
        ),
        schema=schemas.grammar("perceive"),
        about=person.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None or not answer.get("stuck"):
        return None

    text = (answer.get("trace") or "").strip()
    if not text:
        return None

    salience = schemas.weight_to_salience(answer.get("weight"))
    if salience >= HEAVY and _heavy_today(world, person) >= HEAVY_PER_DAY:
        # They have already had their day. This one keeps its words and loses
        # its claim on the rest of their life.
        salience = 0.5

    trace = Trace(
        id=world.next_id("mem"),
        owner=person.id,
        day=world.day,
        trace=text,
        means=(answer.get("means") or "").strip(),
        feeling=answer.get("feeling", "none"),
        salience=salience,
        tags=[t.strip().lower() for t in (answer.get("tags") or []) if t.strip()][:6],
        source="witnessed" if person.id in event.present else "told",
        event_id=event.id,
        about=[w for w in event.who if w != person.id],
        place=event.where,
        last_touched=world.day,
    )
    store.add(trace)
    return trace


def perceive_all(world, event: Event, config,
                 transcript: Optional[Transcript] = None) -> List[Trace]:
    """Hand the event to everyone who was there, one mind at a time."""
    out = []
    for person in world.people.values():
        if not person.present or person.id not in event.present:
            continue
        trace = perceive(world, person, event, config, transcript)
        if trace is not None:
            out.append(trace)
    return out
