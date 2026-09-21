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
reach for the obvious detail everyone would name. Reach for theirs."""


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
