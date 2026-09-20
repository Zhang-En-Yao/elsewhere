"""From event to memory.

'The same event leaves different traces in different minds.'

Nothing here is a copy.  Each person gets their own version of what happened,
or no version at all.
"""

from __future__ import annotations

import random
import re
from typing import List, Optional

from .memory import Memory
from .person import Person
from .util import clamp, jitter, weighted_choice

ENCODE_THRESHOLD = 0.12
TOLD_MARKER = " told me about "
_TOLD_RE = re.compile(r"^.*?\btold\b\s+\S+\s+about\s+", re.IGNORECASE)
_OUT_OF_RE = re.compile(r",\s*out of\s+.*$", re.IGNORECASE)

LENS_FEELING = {
    "fear": "fear",
    "resilience": "steadiness",
    "change": "restlessness",
    "loss": "grief",
    "wonder": "awe",
    "duty": "resolve",
    "belonging": "warmth",
}

LENS_INTERPRETATION = {
    "fear": "I was frightened that day, and it did not leave quickly.",
    "resilience": "We got through it. That is what I kept.",
    "change": "That was when I understood things would not stay as they were.",
    "loss": "Something ended there, even if nobody said so out loud.",
    "wonder": "I had not thought the world would do that.",
    "duty": "There was work to be done, so I did it.",
    "belonging": "What I remember is who was standing beside me.",
}

LENS_BELIEF = {
    "fear": "{theme} is not safe, whatever people say.",
    "resilience": "whatever {theme} takes, this place puts itself back together.",
    "change": "{theme} is a sign that nothing here is permanent.",
    "loss": "{theme} takes more than it gives back.",
    "wonder": "{theme} is worth stopping for.",
    "duty": "{theme} is handled by the people who show up.",
    "belonging": "{theme} is something we go through together.",
}


MISHEARD = [
    "I came away thinking {core}. I am not certain that is what was meant.",
    "What I took from it was {core} - though it may have been the opposite.",
    "{Core}, or that is how it sounded to me.",
]


def strip_framing(line: str) -> str:
    """Drop the throat-clearing and the sign-off, keep what was actually said.

    People do not carry away "I do not much like bringing this up" - they carry
    away the sentence in the middle, if they carry anything.
    """
    from .mind.rules import CLOSERS, OPENERS

    openers = {o.rstrip(".").lower() for group in OPENERS.values() for o in group}
    closers = {c.rstrip(".").lower() for group in CLOSERS.values() for c in group if c}
    parts = [p.strip() for p in line.replace("\n", " ").split(". ") if p.strip()]
    if len(parts) > 1 and parts[0].rstrip(".").lower() in openers:
        parts = parts[1:]
    if len(parts) > 1 and parts[-1].rstrip(".").lower() in closers:
        parts = parts[:-1]
    return ". ".join(parts).rstrip(".")


def distort_line(line: str, misunderstood: bool, rng: random.Random) -> str:
    """Turn what was said into what the listener will carry around.

    Nobody keeps the sentence. They keep a shorter, flatter version of it, and
    when it was misheard the shape survives while the point does not.
    """
    core = strip_framing(line)
    if not core:
        return line
    upper = core[:1].upper() + core[1:]
    lower = core[:1].lower() + core[1:]
    if not misunderstood:
        return upper + "."
    return rng.choice(MISHEARD).format(core=lower, Core=upper)


def core_of(memory) -> str:
    """What a story is about, with the chain of tellers stripped off.

    Without this, a rumour grows a new narrator every time it is passed on,
    and a town of four people produces sentences nobody could say out loud.
    """
    text = memory.text()
    text = _TOLD_RE.sub("", text, count=1)
    text = _OUT_OF_RE.sub("", text)
    return text.strip() or memory.text()


def choose_lens(person: Person, valence: float, themes: List[str],
                rng: random.Random) -> str:
    t, n = person.traits, person.needs
    negative = max(0.0, -valence)
    positive = max(0.0, valence)
    weights = [
        ("fear", 0.15 + 2.0 * negative * (1.0 - t.stability)),
        ("resilience", 0.15 + 1.4 * negative * t.stability + 0.4 * t.warmth),
        ("change", 0.25 + 1.2 * t.openness * n.novelty + 0.5 * abs(valence)),
        ("loss", 0.10 + 1.6 * negative * (0.4 + t.warmth * 0.8)),
        ("wonder", 0.15 + 1.8 * positive * t.openness),
        ("duty", 0.15 + 1.2 * n.routine * (1.0 - t.openness)),
        ("belonging", 0.15 + 1.5 * t.warmth * (1.0 if set(themes) & {"gathering", "town", "music", "care"} else 0.4)),
    ]
    return weighted_choice(rng, weights)


def salience_for(person: Person, event, rng: random.Random) -> float:
    """How much of this lands on this particular person."""
    s = event.intensity
    if person.id in event.participants:
        s += 0.35
    for other in event.participants:
        if other == person.id:
            continue
        rel = person.relationships.get(other)
        if rel:
            s += 0.25 * abs(rel.affinity) * rel.familiarity
    if set(event.themes) & set(person.style.motifs):
        s += 0.15
    for topic in person.beliefs:
        if topic in event.themes:
            s += 0.10
    # Someone who is easily shaken keeps hold of frightening things.
    if event.valence < 0:
        s += 0.25 * (1.0 - person.traits.stability) * abs(event.valence)
    s += 0.30 * person.traits.openness * event.intensity
    return clamp(s + jitter(rng, 0.12), 0.0, 1.5)


def encode_event(person: Person, event, day: int, rng: random.Random,
                 memory_id: str) -> Optional[Memory]:
    """Give this person their version of the event - or nothing at all."""
    s = salience_for(person, event, rng)
    if s < ENCODE_THRESHOLD:
        return None   # they were there; it did not stay
    valence = clamp(event.valence + 0.25 * person.mood + jitter(rng, 0.2), -1.0, 1.0)
    lens = choose_lens(person, valence, event.themes, rng)
    m = Memory(
        id=memory_id,
        owner=person.id,
        day=day,
        gist=event.summary,
        interpretation=LENS_INTERPRETATION[lens],
        feeling=LENS_FEELING[lens],
        lens=lens,
        valence=valence,
        intensity=clamp(0.25 + 0.75 * s),
        detail=clamp(0.45 + 0.5 * s + jitter(rng, 0.15)),
        strength=clamp(0.35 + 0.6 * s),
        themes=list(event.themes),
        people=[p for p in event.participants if p != person.id],
        place=event.place,
        event_id=event.id,
        source="experienced",
        last_touch_day=day,
    )
    person.memories.add(m)
    person.feel(valence, 0.25 * m.intensity)
    return m


def encode_told(listener: Person, speaker: Person, source: Memory, day: int,
                rng: random.Random, memory_id: str,
                said: Optional[str] = None) -> Optional[Memory]:
    """A memory passed through a conversation.

    'They may misunderstand you.'  Second-hand memories arrive thinner, and
    sometimes wrong.
    """
    trust = listener.rel(speaker.id).trust
    if rng.random() > 0.25 + 0.6 * trust * source.intensity:
        return None
    valence = clamp(source.valence * rng.uniform(0.55, 1.05) + jitter(rng, 0.25), -1.0, 1.0)
    lens = choose_lens(listener, valence, source.themes, rng)
    distortions = ["heard second-hand"]
    misunderstood = rng.random() < 0.35 * (1.0 - listener.traits.stability) + 0.15
    if misunderstood:
        valence = clamp(valence * -0.4 + jitter(rng, 0.3), -1.0, 1.0)
        distortions.append(f"misunderstood what {speaker.name} meant")
    heard = distort_line(said, misunderstood, rng) if said else None
    m = Memory(
        id=memory_id,
        owner=listener.id,
        day=day,
        gist=f"{speaker.name}{TOLD_MARKER}{core_of(source).rstrip('.').lower()}",
        interpretation=LENS_INTERPRETATION[lens],
        feeling=LENS_FEELING[lens],
        lens=lens,
        valence=valence,
        intensity=clamp(source.intensity * rng.uniform(0.3, 0.7)),
        detail=clamp(source.detail * rng.uniform(0.3, 0.6)),
        strength=clamp(0.25 + 0.4 * source.intensity),
        themes=list(source.themes),
        people=[speaker.id] + [p for p in source.people if p != listener.id],
        place=source.place,
        event_id=source.event_id,
        source="told",
        last_touch_day=day,
        distortions=distortions,
        heard=heard,
    )
    listener.memories.add(m)
    return m


def encode_artifact(viewer: Person, artifact, day: int, rng: random.Random,
                    memory_id: str) -> Memory:
    """Art becomes memory.  The viewer never gets the maker's version."""
    valence = clamp(jitter(rng, 0.5) + 0.3 * viewer.traits.openness, -1.0, 1.0)
    lens = choose_lens(viewer, valence, artifact.themes, rng)
    m = Memory(
        id=memory_id,
        owner=viewer.id,
        day=day,
        gist=f"the {artifact.form} called \"{artifact.title}\"",
        interpretation=LENS_INTERPRETATION[lens],
        feeling=LENS_FEELING[lens],
        lens=lens,
        valence=valence,
        intensity=clamp(0.3 + 0.5 * viewer.traits.openness + jitter(rng, 0.15)),
        detail=clamp(0.5 + jitter(rng, 0.2)),
        strength=clamp(0.4 + 0.3 * viewer.traits.openness),
        themes=list(artifact.themes),
        people=[artifact.creator],
        place=artifact.place,
        event_id=artifact.source_event,
        source="art",
        last_touch_day=day,
    )
    viewer.memories.add(m)
    viewer.traits.drift("openness", 0.004)
    return m


def encode_introduced(person: Person, text: str, themes: List[str], day: int,
                      rng: random.Random, memory_id: str,
                      intensity: float = 0.8, valence: float = 0.2,
                      place: Optional[str] = None) -> Memory:
    """A memory carried in from a real life and handed to someone here."""
    lens = choose_lens(person, valence, themes, rng)
    m = Memory(
        id=memory_id,
        owner=person.id,
        day=day,
        gist=text,
        interpretation=LENS_INTERPRETATION[lens],
        feeling=LENS_FEELING[lens],
        lens=lens,
        valence=valence,
        intensity=clamp(intensity),
        detail=0.9,
        strength=0.85,
        themes=list(themes),
        place=place,
        source="introduced",
        last_touch_day=day,
    )
    person.memories.add(m)
    return m
