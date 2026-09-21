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
from .world.store import season_of

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


def vantage(world, person: Person, event: Event) -> str:
    """Where this person stood when it happened. World state, not interpretation.

    Nobody perceives "the market burned down". They perceive what reaches them
    from where they are - heat from across the street, a glow seen from a hill,
    a story the next morning. The engine knows where people were; saying so is
    its job. What they make of it is not.
    """
    told = (event.data.get("vantage") or {}).get(person.id)
    if told:
        return told
    if person.id in event.who:
        return "it happened to you"
    place = world.places.get(event.where or "")
    here = world.places.get(person.place)
    if place and here and here.id == place.id:
        return f"right there, at {place.name}"
    if here:
        return f"at {here.name}, and it reached you from there"
    return "nearby"


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
            when=f"{event.phase} in {season_of(event.day)}",
            vantage=vantage(world, person, event),
            others=[world.people[pid] for pid in event.present
                    if pid != person.id and pid in world.people],
            traces=context,
            part_of_it=person.id in event.who,
        ),
        schema=schemas.grammar("perceive"),
        about=person.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return None

    weight = answer.get("weight")
    if weight is None:                              # an older tape, or a lenient backend
        weight = "ordinary" if answer.get("stuck") else "nothing"
    if weight == "nothing":
        return None

    text = (answer.get("trace") or "").strip()
    if not text:
        return None

    salience = schemas.weight_to_salience(weight)
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
