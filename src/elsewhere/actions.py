"""Doing things, and what doing things leaves behind.

Every action here is available to every person, including the player.  The
world resolves them the same way whoever asked.
"""

from __future__ import annotations

import random
from typing import Optional

from . import art
from .memory import Memory
from .mind import Action, Scene, get_speech
from .perception import (LENS_BELIEF, LENS_FEELING, LENS_INTERPRETATION,
                         choose_lens, core_of, encode_artifact, encode_event,
                         encode_told)
from .person import Person
from .util import clamp, jitter

TREND_DRIFT = {
    "fear": [("stability", -0.005)],
    "resilience": [("stability", 0.005)],
    "wonder": [("openness", 0.006)],
    "belonging": [("warmth", 0.005)],
    "loss": [("warmth", 0.002), ("energy", -0.004)],
    "change": [("openness", 0.004), ("routine_need", 0.0)],
    "duty": [("energy", 0.002)],
}


# --------------------------------------------------------------------------
# helpers

def broadcast(world, event, rng: random.Random) -> None:
    """Hand the event to everyone who was there, in their own terms."""
    for person in world.people_at(event.place):
        if not person.present:
            continue
        sub_rng = world.rng_for(world.clock.day, world.clock.phase, person.id, event.id)
        encode_event(person, event, world.clock.day, sub_rng, world.next_id("mem"))
        if person.id not in event.witnesses:
            event.witnesses.append(person.id)


def compatibility(a: Person, b: Person) -> float:
    warm = 1.0 - abs(a.traits.warmth - b.traits.warmth)
    open_ = 1.0 - abs(a.traits.openness - b.traits.openness)
    energy = 1.0 - abs(a.traits.energy - b.traits.energy)
    return clamp(0.45 * warm + 0.35 * open_ + 0.20 * energy)


def cues_for_place(world, place_id: str):
    place = world.places.get(place_id)
    cues = {place_id}
    if place:
        cues |= set(place.tags)
    return cues


# --------------------------------------------------------------------------
# individual actions

def do_rest(world, person: Person, rng: random.Random) -> None:
    person.needs.rest = clamp(person.needs.rest - 0.55)
    person.feel(0.05, 0.1)
    person.last_action = "rested"
    if rng.random() < 0.14:
        cues = set()
        for m in person.memories.dormant():
            cues |= m.cues()
        returned = person.memories.resurface(cues, world.clock.day, rng)
        if returned is not None:
            world.narrate(f"{person.name} dreamt of something long forgotten: "
                          f"{returned.text()}")
            if returned.intensity >= 0.5:
                world.record(
                    "memory_returned",
                    f"Something came back to {person.name} in the night: {returned.text()}.",
                    place=person.place, participants=[person.id],
                    themes=returned.themes, valence=returned.valence, intensity=0.3,
                    data={"memory": returned.id},
                )


def do_work(world, person: Person, rng: random.Random) -> None:
    person.needs.routine = clamp(person.needs.routine - 0.45)
    person.needs.rest = clamp(person.needs.rest + 0.12)
    person.feel(0.05, 0.05)
    person.last_action = "worked"


def do_wander(world, person: Person, rng: random.Random) -> None:
    person.needs.novelty = clamp(person.needs.novelty - 0.2)
    person.last_action = "wandered"
    returned = person.memories.resurface(cues_for_place(world, person.place),
                                         world.clock.day, rng)
    if returned is not None:
        world.narrate(f"{person.name} was caught out by a memory at "
                      f"{world.places[person.place].name}.")


def do_travel(world, person: Person, action: Action, rng: random.Random) -> None:
    place = world.places.get(action.target or "")
    if place is None or place.id == person.place:
        return do_wander(world, person, rng)
    person.place = place.id
    person.needs.novelty = clamp(person.needs.novelty - 0.35)
    person.needs.rest = clamp(person.needs.rest + 0.08)
    person.last_action = f"walked to {place.name}"
    returned = person.memories.resurface(cues_for_place(world, place.id),
                                         world.clock.day, rng)
    if returned is not None:
        world.narrate(f"At {place.name}, {person.name} remembered {returned.text()}.")
        if returned.intensity >= 0.5:
            world.record(
                "memory_returned",
                f"At {place.name}, {person.name} remembered {returned.text()}.",
                place=place.id, participants=[person.id], themes=returned.themes,
                valence=returned.valence, intensity=0.3, data={"memory": returned.id},
            )


def worth_telling(world, memory) -> bool:
    """People tell each other about things that happened, not about talking."""
    if memory.event_id:
        event = world.event(memory.event_id)
        if event is not None and event.kind == "conversation":
            return False
    return True


def do_talk(world, person: Person, action: Action, rng: random.Random) -> None:
    other = world.people.get(action.target or "")
    if other is None or other.id == person.id or other.place != person.place:
        return do_wander(world, person, rng)

    day = world.clock.day
    rel_a, rel_b = person.rel(other.id), other.rel(person.id)
    first_meeting = rel_a.familiarity < 0.02

    topic: Optional[Memory] = None
    strongest = [m for m in person.memories.strongest(5, min_intensity=0.2)
                 if worth_telling(world, m)][:3]
    if strongest and rng.random() < 0.12 + 0.35 * person.needs.expression:
        topic = rng.choice(strongest)
        topic.recall(day, rng)

    # Somebody has to say it out loud. The mind supplies the words - a template
    # from the rule engine, a model's line from an LLM mind - and the world
    # decides what survives the trip into the other person's head.
    said = None
    if topic is not None or person.is_player or other.is_player:
        place = world.places.get(person.place)
        scene = Scene(
            speaker=person, listener=other, topic=topic,
            place_name=place.name if place else "", phase=world.clock.phase_name,
            season=world.clock.season, day=day,
            familiarity=rel_a.familiarity, affinity=rel_a.affinity,
        )
        said = get_speech(person, scene, rng)
        if said and (person.is_player or other.is_player):
            world.narrate(f"{person.name}: \"{said}\"")
        # When the player speaks, the other side answers - otherwise playing
        # feels like talking at someone who is not there. The answer is small
        # talk: nothing is transmitted by it, so nothing is claimed by it.
        if said and person.is_player:
            answer = get_speech(other, Scene(
                speaker=other, listener=person, topic=None,
                place_name=scene.place_name, phase=scene.phase,
                season=scene.season, day=day,
                familiarity=rel_b.familiarity, affinity=rel_b.affinity), rng)
            if answer:
                world.narrate(f"{other.name}: \"{answer}\"")

    passed_on = None
    if topic is not None:
        passed_on = encode_told(other, person, topic, day, rng,
                                world.next_id("mem"), said=said)

    compat = compatibility(person, other)
    base = 0.05 * (compat - 0.45) * 2.0
    mood_gift = 0.02 * (person.mood + other.mood)
    # Two people never leave the same conversation with the same impression,
    # and nobody's feelings about anybody keep growing forever.
    for rel in (rel_a, rel_b):
        delta = (base + mood_gift + jitter(rng, 0.03)) * (1.0 - abs(rel.affinity))
        rel.affinity = clamp(rel.affinity + delta, -1.0, 1.0)
    for rel in (rel_a, rel_b):
        rel.familiarity = clamp(rel.familiarity + 0.06)
        rel.trust = clamp(rel.trust + 0.02 * (compat - 0.4))
        rel.last_seen_day = day
    person.needs.company = clamp(person.needs.company - 0.5)
    other.needs.company = clamp(other.needs.company - 0.35)
    person.needs.expression = clamp(person.needs.expression - (0.25 if topic else 0.05))
    person.last_action = f"talked with {other.name}"
    other.last_action = f"talked with {person.name}"

    notable = bool(passed_on) or first_meeting or rng.random() < 0.07
    if not notable:
        # Most conversations leave nothing behind, in the chronicle or anywhere else.
        return

    if passed_on is not None:
        summary = (f"{person.name} told {other.name} about "
                   f"{core_of(topic).rstrip('.').lower()}.")
        themes = list(topic.themes)
        valence = topic.valence * 0.6
        intensity = clamp(0.25 + 0.4 * topic.intensity)
        rel_a.note(f"told them about {themes[0] if themes else 'that time'}")
        rel_b.note(f"heard about {themes[0] if themes else 'that time'} from {person.name}")
    elif first_meeting:
        summary = f"{person.name} and {other.name} met for the first time."
        themes = ["meeting"]
        valence = 0.2
        intensity = 0.4
    else:
        summary = f"{person.name} and {other.name} sat together for a while."
        themes = ["company"]
        valence = 0.25 * compat
        intensity = 0.2

    event = world.record("conversation", summary, place=person.place,
                         participants=[person.id, other.id], themes=themes,
                         valence=valence, intensity=intensity,
                         data={"topic_memory": topic.id if topic else None,
                               "passed_on": passed_on.id if passed_on else None,
                               "said": said})
    broadcast(world, event, rng)


def do_tend(world, person: Person, action: Action, rng: random.Random) -> None:
    other = world.people.get(action.target or "")
    if other is None or other.place != person.place:
        return do_wander(world, person, rng)
    other.feel(0.4, 0.3)
    person.feel(0.15, 0.15)
    rel_a, rel_b = person.rel(other.id), other.rel(person.id)
    rel_a.affinity = clamp(rel_a.affinity + 0.04, -1.0, 1.0)
    rel_b.affinity = clamp(rel_b.affinity + 0.07, -1.0, 1.0)
    rel_b.trust = clamp(rel_b.trust + 0.05)
    rel_b.note(f"{person.name} stayed with me when it was bad")
    person.last_action = f"sat with {other.name}"
    event = world.record("care", f"{person.name} stayed with {other.name} a while.",
                         place=person.place, participants=[person.id, other.id],
                         themes=["care", "company"], valence=0.5, intensity=0.4)
    broadcast(world, event, rng)


def worth_making_something_of(world, memory) -> bool:
    """You do not paint the afternoon you spent painting."""
    if memory.dormant or memory.source == "art":
        return False
    if memory.event_id:
        event = world.event(memory.event_id)
        if event is not None and event.kind in ("creation", "encounter"):
            return False
    lowered = memory.gist.lower()
    if " made a " in lowered or " took in " in lowered:
        return False        # art about art about art
    return True


def do_create(world, person: Person, action: Action, rng: random.Random) -> None:
    memory = person.memories.get(action.target or "") if action.target else None
    if memory is None or not worth_making_something_of(world, memory):
        candidates = [m for m in person.memories.strongest(6, min_intensity=0.25)
                      if worth_making_something_of(world, m)]
        if not candidates:
            return do_reflect(world, person, rng)
        memory = candidates[0]
    artifact = art.create(world, person, memory, rng)
    person.last_created_day = world.clock.day
    person.last_action = f"made \"{artifact.title}\""
    event = world.record(
        "creation",
        f"{person.name} made a {artifact.form}, \"{artifact.title}\", "
        f"out of {core_of(memory).rstrip('.').lower()}.",
        place=person.place, participants=[person.id], themes=artifact.themes,
        valence=memory.valence * 0.5, intensity=0.45,
        data={"artifact": artifact.id, "memory": memory.id},
    )
    broadcast(world, event, rng)


def do_contemplate(world, person: Person, action: Action, rng: random.Random) -> None:
    artifact = world.artifacts.get(action.target or "")
    if artifact is None or artifact.place != person.place:
        return do_wander(world, person, rng)
    memory = encode_artifact(person, artifact, world.clock.day, rng, world.next_id("mem"))
    if person.id not in artifact.encountered_by:
        artifact.encountered_by.append(person.id)
    creator = world.people.get(artifact.creator)
    if creator is not None and creator.id != person.id:
        rel = person.rel(creator.id)
        rel.familiarity = clamp(rel.familiarity + 0.02)
        rel.note(f"made \"{artifact.title}\"")
    person.last_action = f"stood in front of \"{artifact.title}\""
    world.record("encounter",
                 f"{person.name} took in \"{artifact.title}\" at "
                 f"{world.places[artifact.place].name}.",
                 place=artifact.place, participants=[person.id],
                 themes=artifact.themes, valence=memory.valence, intensity=0.25,
                 data={"artifact": artifact.id})


def do_reflect(world, person: Person, rng: random.Random) -> None:
    day = world.clock.day
    candidates = person.memories.strongest(3)
    if not candidates:
        return do_rest(world, person, rng)
    focus = rng.choice(candidates)
    focus.recall(day, rng)
    person.needs.expression = clamp(person.needs.expression + 0.12 * focus.intensity)
    person.last_action = "sat with their own thoughts"

    # The same memory, understood differently later.
    if rng.random() < 0.28:
        lens = choose_lens(person, focus.valence, focus.themes, rng)
        if lens != focus.lens:
            focus.lens = lens
            focus.interpretation = LENS_INTERPRETATION[lens]
            focus.feeling = LENS_FEELING[lens]
            focus.distortions.append("came to mean something else")
            world.narrate(f"{person.name} came to see {focus.text()} differently.")

    if rng.random() < 0.12:
        merged = person.memories.conflate(rng)
        if merged is not None:
            world.narrate(f"Two of {person.name}'s memories have become one.")

    theme = focus.themes[0] if focus.themes else "life"
    statement = LENS_BELIEF[focus.lens].format(theme=theme)
    person.believe(theme, statement, day, focus.id,
                   conviction_delta=0.08 + 0.2 * focus.intensity)

    for other_id in focus.people:
        if other_id == person.id or other_id not in world.people:
            continue
        rel = person.rel(other_id)
        rel.affinity = clamp(rel.affinity + 0.03 * focus.valence, -1.0, 1.0)

    for trait, delta in TREND_DRIFT.get(focus.lens, []):
        if trait.endswith("_need"):
            continue
        person.traits.drift(trait, delta * (0.5 + focus.intensity))

    person.feel(focus.valence, 0.18)
    person.refresh_belief_origins()


def do_idle(world, person: Person, rng: random.Random) -> None:
    person.last_action = "did nothing in particular"


HANDLERS = {
    "rest": lambda w, p, a, r: do_rest(w, p, r),
    "work": lambda w, p, a, r: do_work(w, p, r),
    "wander": lambda w, p, a, r: do_wander(w, p, r),
    "reflect": lambda w, p, a, r: do_reflect(w, p, r),
    "idle": lambda w, p, a, r: do_idle(w, p, r),
    "travel": do_travel,
    "talk": do_talk,
    "tend": do_tend,
    "create": do_create,
    "contemplate": do_contemplate,
}


def resolve(world, person: Person, action: Action, rng: random.Random) -> None:
    handler = HANDLERS.get(action.kind)
    if handler is None:
        return do_wander(world, person, rng)
    handler(world, person, action, rng)
