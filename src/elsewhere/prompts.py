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

means: what they make of it, in a few words. Leave it empty if nothing.

feeling, tags: one feeling; two to four short tags for what it was about.

weight and stuck, last: now decide whether any of that survives the week.
Most of what happens to a person leaves nothing - an ordinary market day, talk
about the weather, someone walking past. Those are faint, and not stuck. Say
stuck only if this person, with this history, would still be carrying it in
a week. Something that happened to them, or that they were afraid of, or that
changed what they want, usually does.

Weight means how much of them it takes up:
  faint    - they would not mention it unprompted
  ordinary - they would bring it up this week and not next year
  stays    - they will still have it years from now
  marks    - it changes who they are

Almost nothing is "marks". Be sparing, or this person ends up with a hundred
unforgettable days and no life."""


def perceive_user(person: Person, what_happened: str, where: str, when: str,
                  others: Sequence[Person], traces: Sequence[Trace],
                  part_of_it: bool) -> str:
    return "\n\n".join([
        person_block(person),
        traces_block(traces),
        ties_block(person, others),
        f"It is {when}, at {where}.",
        ("This happened to you: " if part_of_it else "You saw this happen: ")
        + what_happened,
        "Does any of it stay with you?",
    ])
