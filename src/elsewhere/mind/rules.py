"""The default brain: dispositions, needs, and the time of day.

No optimisation, no planning - just a person who is a little more likely to
do what they are inclined to do.  Everything interesting in Elsewhere comes
from what these small choices accumulate into.
"""

from __future__ import annotations

import random

from ..util import softmax_choice
from . import Action, Scene, View


class RuleMind:
    kind = "rules"

    def decide(self, person, view: View, rng: random.Random) -> Action:
        t, n = person.traits, person.needs
        phase = view.phase
        night = phase == "night"
        evening = phase == "evening"
        morning = phase == "morning"
        working_hours = phase in ("morning", "afternoon")

        options = []
        scores = []

        def offer(action: Action, score: float) -> None:
            options.append(action)
            scores.append(score)

        # Sleep, or at least stop.
        offer(Action("rest"),
              0.20 + 1.7 * n.rest + (1.5 if night else -0.5))

        # The people who happen to be here.
        for other in view.people_here:
            if other.id == person.id or not other.present:
                continue
            rel = person.rel(other.id)
            unfamiliar = 1.0 - rel.familiarity
            score = (0.25
                     + 1.4 * n.company
                     + 0.8 * t.warmth
                     + 1.0 * rel.affinity
                     + 0.9 * t.openness * unfamiliar
                     - (1.1 if night else 0.0))
            offer(Action("talk", other.id), score)

            # Someone visibly unwell, and someone warm enough to notice.
            if other.mood < -0.25 and rel.affinity > 0.05:
                offer(Action("tend", other.id),
                      0.2 + 1.5 * t.warmth * rel.affinity + 0.8 * (-other.mood))

        # Somewhere else.
        for place in view.reachable_places:
            score = (0.15
                     + 1.2 * n.novelty * t.openness
                     + 0.6 * t.energy
                     - (1.6 if night else 0.0))
            if place.id == person.home and (night or evening):
                score += 1.8
            if person.occupation in place.tags and working_hours:
                score += 0.9
            offer(Action("travel", place.id), score)

        # The ordinary day.
        if working_hours:
            offer(Action("work"),
                  0.35 + 1.3 * n.routine + 0.6 * (1.0 - t.openness) + 0.4 * t.energy)

        # Something that will not leave them alone until it is made.
        rested_from_making = view.day - person.last_created_day >= 20
        if rested_from_making and n.expression > 0.55:
            strongest = [m for m in person.memories.strongest(4, min_intensity=0.35)
                         if m.source != "art"]
            if strongest:
                m = strongest[0]
                offer(Action("create", m.id, detail=person.style.form),
                      -0.8 + 1.9 * n.expression * t.expressiveness + 0.5 * m.intensity
                      - (0.6 if morning else 0.0))

        # Someone else's work, standing in a room.
        for artifact in view.artifacts_here:
            if artifact.creator == person.id or person.id in artifact.encountered_by:
                continue
            offer(Action("contemplate", artifact.id), 0.3 + 1.3 * t.openness)

        # Turning it over.
        if person.memories.active():
            offer(Action("reflect"),
                  0.15
                  + (0.9 if (night or evening) else 0.0) * (0.6 + t.stability)
                  + 0.7 * t.openness
                  + 0.6 * abs(person.mood))

        offer(Action("wander"), 0.30 + 0.3 * t.energy)

        temperature = 0.30 + 0.35 * t.openness
        return softmax_choice(rng, options, scores, temperature=temperature)

    def speak(self, scene: Scene, rng: random.Random) -> str:
        return compose_line(scene, rng)


# --------------------------------------------------------------------------
# Speech
#
# The rule engine does not invent language; it arranges it around whatever is
# left of the memory being offered. Which is why the same person telling the
# same story sounds different three years later - the sentence is built from a
# memory that has been decaying the whole time.

OPENERS = {
    "fear": ["I do not much like bringing this up",
             "You will think I never got over it",
             "I still do not sleep well about it"],
    "resilience": ["It was not as bad as people say now",
                   "We managed, is how I remember it",
                   "You know how it went"],
    "change": ["Things were different after that",
               "I date everything from then",
               "That was the turn, for me"],
    "loss": ["I do not talk about this often",
             "There is not much of it left now",
             "It took more than people counted"],
    "wonder": ["I have never seen anything like it since",
               "You would not have believed it",
               "I think about it more than I should"],
    "duty": ["Not much to tell, really",
             "There was work to do, so we did it",
             "Somebody had to see to it"],
    "belonging": ["You were about, that year",
                  "We were all out in it together",
                  "Half the town was standing there"],
}

CLOSERS = {
    "fear": ["I do not know why it stays with me.", ""],
    "resilience": ["It got put back together.", ""],
    "change": ["Nothing stayed the same after.", ""],
    "loss": ["That is all that is left of it.", ""],
    "wonder": ["I would go back just to see it again.", ""],
    "duty": ["That is all.", ""],
    "belonging": ["You remember it too, surely.", ""],
}

SMALL_TALK = [
    "Cold for the {season}, is it not.",
    "Quiet up here this {phase}.",
    "I have been at {place} all {phase}.",
    "You are about early.",
    "Nothing much doing today.",
    "I was just thinking I had not seen you.",
]

DISTANT = ["You would not know this, but ", "We have not spoken much, but ",
           "I do not say this to everyone, but "]


def in_the_room(text: str, scene: Scene) -> str:
    """The chronicle says "Alice and Bram built the table". Alice says "you and I".

    A person does not narrate themselves in the third person, so the names of
    whoever is standing here get turned back into pronouns.
    """
    speaker, listener = scene.speaker.name, scene.listener.name
    for pair in (f"{speaker} and {listener}", f"{listener} and {speaker}"):
        text = text.replace(pair, "you and I")
    text = text.replace(f"{speaker}'s", "my").replace(f"{listener}'s", "your")
    text = text.replace(speaker, "I").replace(listener, "you")
    return text


def compose_line(scene: Scene, rng: random.Random) -> str:
    """One line, built out of however much of the memory has survived."""
    topic = scene.topic
    if topic is None:
        return rng.choice(SMALL_TALK).format(
            season=scene.season, phase=scene.phase,
            place=scene.place_name or "the market")

    opener = rng.choice(OPENERS.get(topic.lens, OPENERS["change"]))
    closer = rng.choice(CLOSERS.get(topic.lens, [""]))

    if topic.detail > 0.30:
        body = in_the_room(topic.gist.rstrip("."), scene)
    elif topic.detail > 0.08:
        subject = topic.themes[0] if topic.themes else "it"
        body = rng.choice([
            f"there was something about the {subject}",
            f"it was to do with the {subject}, I am sure of that much",
            f"I have the {subject} and not much else",
        ])
    else:
        body = rng.choice([
            f"all I have left of it is the {topic.feeling}",
            f"I could not tell you what happened, only that it was {topic.feeling}",
            f"there is a {topic.feeling} in it somewhere, and no picture at all",
        ])

    body = body[:1].upper() + body[1:]
    prefix = rng.choice(DISTANT) if scene.familiarity < 0.15 else ""
    line = f"{prefix}{opener}. {body}."
    if prefix:
        line = line[:1].upper() + line[1:]
    return f"{line} {closer}".strip()
