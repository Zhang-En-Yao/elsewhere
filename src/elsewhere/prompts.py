"""What a mind is shown before it is asked anything.

A person is never handed the world. They are handed themselves, the room they
are standing in, and the few things they can currently bring to mind - which
is the retrieval layer's decision, not theirs.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from .world.entities import Person
from .world.memories import Trace


def person_block(person: Person) -> str:
    lines = [f"You are {person.name}."]
    if person.card:
        lines.append(person.card)
    facts = []
    if person.age:
        facts.append(f"{person.age} years old")
    if person.occupation:
        facts.append(person.occupation)
    if facts:
        lines.append(", ".join(facts).capitalize() + ".")
    if getattr(person, "voice", ""):
        lines.append(f"How you talk: {person.voice}")
    lines.append(f"Right now you feel {person.mood}.")
    if person.wants:
        lines.append("What you want at the moment: " + "; ".join(person.wants) + ".")
    if person.beliefs:
        held = sorted(person.beliefs, key=lambda b: -b.confidence)[:3]
        lines.append("What you hold to be true: " +
                     " ".join(f"{b.text}." for b in held))
    return "\n".join(lines)


def traces_block(traces: Sequence[Trace], header: str = "What you can bring to mind") -> str:
    if not traces:
        return f"{header}: nothing in particular."
    lines = [f"{header}:"]
    for t in traces:
        line = f"  - {t.trace}"
        if t.means:
            line += f" (what it meant to you: {t.means})"
        if t.feeling and t.feeling != "none":
            line += f" [{t.feeling}]"
        lines.append(line)
    return "\n".join(lines)


def ties_block(person: Person, others: Sequence[Person]) -> str:
    if not others:
        return "You are alone."
    lines = ["Who is here:"]
    for other in others:
        tie = person.ties.get(other.id)
        if tie is None or tie.closeness < 0.05:
            lines.append(f"  - {other.name}, who you do not know.")
        else:
            note = f" {tie.note}" if tie.note else ""
            lines.append(f"  - {other.name}.{note}")
    return "\n".join(lines)


PERCEIVE_SYSTEM = """You are one person in a small town, and something has just
happened near you. Decide what - if anything - it leaves in you.

Answer in this order.

trace: the fragment this person is left holding right now - an image, a thing
someone said, the part that frightened or moved them. Not a report. It may be
less than what happened, and it may be slightly wrong. It must be in their own
voice, a few words to one sentence, not a chronicle's.

means: what they make of it, in their own words, the way they would say it
out loud to someone. Not a lesson and not a moral - nobody says "a reminder of
the fragility of life" about their own week. Plenty of people make nothing of
things; leave it empty then.

feeling, tags: one feeling; two to four short tags for what it was about.

weight, last: how much of that survives in this person.
  nothing  - it is gone by tomorrow
  faint    - it might come back if something pointed at it
  ordinary - they will bring it up this week, and not next year
  stays    - they will still have it years from now
  marks    - it changes who they are

Weigh it by who this person is, not by how big the event was. The same fire
can mark one person for life and pass the next one by entirely - read who
they are before you decide. An ordinary day is nothing for almost everyone.

Almost nothing is "marks". Be sparing, or this person ends up with a hundred
unforgettable days and no life.

Other people were there too, and each of them kept something different: what
someone like this person notices first, from where they were standing. Do not
reach for the obvious detail everyone would name. Reach for theirs.

Most people do not yet know what a thing means to them. An empty "means" is
the usual answer. When there is one, it is something they would actually say
to a neighbour, not a lesson.

Three people, another town, another day - the form, not the content:

  A cart went over on the river bend and the horse had to be put down.

  Mira, who minds the neighbours' children. At her door, forty paces off.
    {"trace": "its eye was open the whole time they were deciding",
     "means": "", "feeling": "grief", "tags": ["horse", "river"], "weight": "stays"}

  Oskar, a trader who counts everything. Behind the cart, holding his own horse.
    {"trace": "two sacks of flour split open in the mud",
     "means": "someone is paying for that, and it is not me",
     "feeling": "unease", "tags": ["cart", "trade"], "weight": "faint"}

  Pell, an old ferryman who has seen it before. On the far bank.
    {"trace": "a cart on its side", "means": "", "feeling": "none",
     "tags": ["river"], "weight": "nothing"}"""


#: The example traces above, so the eval can tell a copied example from a memory.
PERCEIVE_EXAMPLE_TRACES = (
    "its eye was open the whole time they were deciding",
    "two sacks of flour split open in the mud",
    "a cart on its side",
)


def perceive_user(person: Person, what_happened: str, where: str, when: str,
                  others: Sequence[Person], traces: Sequence[Trace],
                  part_of_it: bool, vantage: str = "") -> str:
    """Scene first, person last.

    A small model weights the end of a prompt far more than the start. With the
    character card at the top, by the time it reaches the question the card
    has been drowned by the scene - and everyone answers as the same narrator.
    """
    parts = [
        f"It was {when}, at {where}.",
        ("What happened to you: " if part_of_it else "What happened: ")
        + what_happened,
        (f"You were {vantage}. That is where you stood, not what you noticed - "
         f"do not reuse its words.") if vantage else "",
        ties_block(person, others).replace("Who is here:", "Who else was there:"),
        traces_block(traces),
        person_block(person),
        f"Now answer as {person.name}, and only as {person.name}: how much of this "
        f"do you carry? For some people it is everything; for others, nothing at all.",
    ]
    return "\n\n".join(part for part in parts if part)


# --------------------------------------------------------------------------
# act: what someone does with the next few hours

ACT_SYSTEM = """You are one person in a small town, deciding what to do with
the next few hours. You are not narrating and not explaining yourself to anyone.

because: first, in a few words and in your own voice, what is pulling at you
right now - a want, a worry, tiredness, someone you have been meaning to see.

action: then one of
  stay  - remain where you are, doing nothing in particular
  go    - walk to one of the places you can reach from here (target: the place)
  talk  - speak with someone who is here right now (target: their name)
  work  - get on with your trade
  rest  - sleep, or sit and do nothing

target: the place or the person, exactly as written in the options; empty for
stay, work and rest.

People mostly do ordinary things. They work in the day, rest at night, go home,
and talk when there is a reason to. Nobody seeks everyone out every few hours.

Three people, another town, another day - the form, not the content:

  Morning. Mira is at her door. Here: nobody. Can go to: the ford, the well.
    {"because": "the children arrive soon and the step needs scrubbing",
     "action": "work", "target": ""}

  Afternoon. Oskar is at the ford. Here: Mira. Can go to: the market.
    {"because": "she saw the cart go over; I want to know what she told the reeve",
     "action": "talk", "target": "Mira"}

  Night. Pell is at the ferry house. Here: nobody. Can go to: the far bank.
    {"because": "tired",
     "action": "rest", "target": ""}"""


def act_user(person: Person, when: str, place, others: Sequence[Person],
             reachable: Sequence[str], traces: Sequence[Trace]) -> str:
    here = ", ".join(o.name for o in others) if others else "nobody"
    parts = [
        f"It is {when}.",
        f"You are at {place.name}. {place.description}".strip() if place else "",
        f"Here with you: {here}.",
        f"From here you can go to: {', '.join(reachable) if reachable else 'nowhere'}.",
        ties_block(person, others) if others else "",
        traces_block(traces),
        person_block(person),
        f"Now decide as {person.name}: what do you do for the next few hours?",
    ]
    return "\n\n".join(part for part in parts if part)


# --------------------------------------------------------------------------
# speak: one thing said out loud to one person

SPEAK_SYSTEM = """You are one person in a small town, and you have turned to
someone to say something. Say one thing, the way this person actually talks.

about: first, which of the numbered things on your mind you are bringing up -
or "nothing in particular" for small talk.

line: then what you say. One or two short sentences, spoken out loud to the
person in front of you. No narration, no quotation marks, no name in front.
If what you remember is vague, say it vaguely - people say "that night, you
remember" far more often than they describe anything.

Three people, another town - the form, not the content:

  Mira, to Oskar, whom she barely knows. On her mind: 1. its eye was open the
  whole time they were deciding.
    {"about": "1", "line": "Did you see its eye? I keep seeing it."}

  Oskar, to the reeve. On his mind: 1. two sacks of flour split in the mud.
    {"about": "1", "line": "That flour was not mine. You will want to know whose it was."}

  Pell, to a stranger at the ferry. On his mind: nothing in particular.
    {"about": "nothing in particular", "line": "River's high. Mind your feet."}"""


def speak_user(person: Person, listener: Person, when: str, place_name: str,
               topics: Sequence[Trace]) -> str:
    tie = person.ties.get(listener.id)
    knows = f" {tie.note}" if tie and tie.note else ""
    lines = [
        f"It is {when}, at {place_name}.",
        f"You are talking to {listener.name}.{knows}",
    ]
    if topics:
        lines.append("On your mind:")
        for i, t in enumerate(topics, 1):
            extra = f" ({t.means})" if t.means else ""
            lines.append(f"  {i}. {t.trace}{extra}")
    else:
        lines.append("On your mind: nothing in particular.")
    lines.append(person_block(person))
    lines.append(f"What does {person.name} say to {listener.name}?")
    return "\n\n".join(lines)
