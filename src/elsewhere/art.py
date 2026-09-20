"""Art: what a memory becomes when someone needs it to exist outside them.

'None of them has to be the definitive version.  They are different ways of
remembering.'
"""

from __future__ import annotations

import random
from typing import List

from .person import Person
from .util import clamp

TITLE_PATTERNS = {
    "painting": ["{Theme} at {Time}", "Smoke Over {Theme}", "{Adjective} {Theme}",
                 "What Was Left of {Theme}", "{Theme}, Unfinished"],
    "song": ["The {Theme} Song", "What {Theme} Took", "{Adjective} Winter",
             "A Tune for {Theme}", "Nobody Sings About {Theme}"],
    "story": ["The Night of the {Theme}", "How We Came Back from {Theme}",
              "{Adjective} Days", "The One Who Stayed", "Before {Theme}"],
    "poem": ["On {Theme}", "{Adjective}", "Lines Written After {Theme}",
             "Still, {Theme}", "For Those Who Were There"],
}

LENS_ADJECTIVE = {
    "fear": ["Thin", "Sleepless", "Blackened"],
    "resilience": ["Standing", "Rebuilt", "Stubborn"],
    "change": ["Turning", "Unsettled", "Moving"],
    "loss": ["Empty", "Quiet", "Missing"],
    "wonder": ["Bright", "Unlikely", "First"],
    "duty": ["Ordinary", "Early", "Kept"],
    "belonging": ["Shared", "Close", "Warm"],
}

FORM_VERB = {
    "painting": "painted", "song": "wrote a song about",
    "story": "wrote down the story of", "poem": "made a poem out of",
}


def make_title(person: Person, memory, rng: random.Random, form: str) -> str:
    theme = (memory.themes[0] if memory.themes else "it").title()
    adjective = rng.choice(LENS_ADJECTIVE.get(memory.lens, ["Plain"]))
    time_word = rng.choice(["Dusk", "Dawn", "Midwinter", "Harvest", "Night"])
    pattern = rng.choice(TITLE_PATTERNS.get(form, TITLE_PATTERNS["story"]))
    return pattern.format(Theme=theme, Adjective=adjective, Time=time_word)


def describe_work(person: Person, memory, form: str, title: str) -> str:
    from .perception import core_of

    feeling = memory.feeling
    adjectives = ", ".join(person.style.adjectives[:2]) or "plain"
    source = core_of(memory).rstrip(".")
    return (f"A {adjectives} {form} by {person.name}. "
            f"It came out of {source[:1].lower()}{source[1:]}, "
            f"and what it carries is {feeling}.")


def create(world, person: Person, memory, rng: random.Random):
    """Turn a memory into an object other people can run into."""
    from .world import Artifact

    form = person.style.form
    taken = {a.title for a in world.artifacts.values()}
    title = make_title(person, memory, rng, form)
    for _ in range(6):
        if title not in taken:
            break
        title = make_title(person, memory, rng, form)
    if title in taken:
        title = f"{title} (again)"
    artifact = Artifact(
        id=world.next_id("art"),
        creator=person.id,
        day=world.clock.day,
        form=form,
        title=title,
        description=describe_work(person, memory, form, title),
        place=person.place,
        themes=list(memory.themes) or ["life"],
        source_memory=memory.id,
        source_event=memory.event_id,
    )
    world.artifacts[artifact.id] = artifact

    memory.recall(world.clock.day, rng)
    person.needs.expression = clamp(person.needs.expression - 0.6)
    person.traits.drift("expressiveness", 0.006)
    for theme in artifact.themes[:2]:
        if theme not in person.style.motifs:
            person.style.motifs.append(theme)
    person.style.motifs = person.style.motifs[-5:]
    return artifact
