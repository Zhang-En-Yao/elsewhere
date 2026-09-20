"""Culture: the point where enough people remember the same thing.

'Shared memories may become beliefs.  Traditions may become rituals.'

Nothing here is designed in advance.  A tradition appears when a theme has
soaked into enough minds and enough made things, and then it starts
producing events of its own - which produce more memories, which keep it
alive after everyone who was there has forgotten the original day.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from .util import clamp
from .worldtime import DAYS_PER_YEAR

MIN_PEOPLE = 3
MIN_SCORE = 8.0
MIN_YEARS_BETWEEN = 150   # days between anything new hardening
MIN_ARTIFACTS = 2
MAX_PER_CHECK = 1

LENS_RITUAL = {
    "fear": ("Vigil", ["keeps a watch through the night and says very little",
                       "leaves one lamp burning in every window"]),
    "resilience": ("Rebuilding", ["repairs one thing together that did not need repairing",
                                  "carries new timber to the place it happened"]),
    "change": ("Turning", ["walks the boundary of the town and names what is different",
                           "swaps trades with someone for a day"]),
    "loss": ("Remembrance", ["leaves something behind at the place it happened",
                             "says the names of what is gone, once, and then stops"]),
    "wonder": ("Watching", ["stops work early and looks at the sky",
                            "goes up the hill road and waits for dark"]),
    "duty": ("Day of Work", ["does the least wanted work first, and together",
                             "finishes someone else's job before their own"]),
    "belonging": ("Gathering", ["eats outside, whoever they are",
                                "sets one more place at the long table than there are people"]),
}

IGNORED_THEMES = {"company", "meeting", "life", "quiet"}


def theme_support(world, theme: str) -> Tuple[List[str], float, Optional[str], str]:
    """Who carries this theme, how strongly, where it started, and how they hold it."""
    carriers: List[str] = []
    score = 0.0
    lens_votes: Dict[str, float] = {}
    origin_place = None
    for person in world.people.values():
        personal = 0.0
        for m in person.memories.by_theme(theme):
            personal += m.strength * (0.5 + m.intensity)
            if m.intensity >= 0.35:
                # Only memories people actually feel get a say in how the
                # town ends up holding this.
                lens_votes[m.lens] = lens_votes.get(m.lens, 0.0) + \
                    m.strength * m.intensity
            origin_place = origin_place or m.place
        belief = person.beliefs.get(theme)
        if belief:
            personal += belief.conviction
        if personal > 0.25:
            carriers.append(person.id)
            score += personal
    for artifact in world.artifacts.values():
        if theme in artifact.themes:
            score += 1.0 + 0.3 * len(artifact.encountered_by)
            origin_place = origin_place or artifact.place
    lens = max(lens_votes, key=lens_votes.get) if lens_votes else "belonging"
    return carriers, score, origin_place, lens


def candidate_themes(world) -> List[str]:
    seen: Dict[str, int] = {}
    for person in world.people.values():
        for m in person.memories.active():
            for theme in m.themes:
                seen[theme] = seen.get(theme, 0) + 1
    for artifact in world.artifacts.values():
        for theme in artifact.themes:
            seen[theme] = seen.get(theme, 0) + 2
    return [t for t, _ in sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
            if t not in IGNORED_THEMES]


def consider(world, rng: random.Random) -> List:
    """Look for a shared memory that has hardened into a practice."""
    from .world import Tradition

    founded = []
    if world.traditions:
        newest = max(t.day_founded for t in world.traditions.values())
        if world.clock.day - newest < MIN_YEARS_BETWEEN:
            return founded
    existing = {t.theme for t in world.traditions.values()}
    for theme in candidate_themes(world)[:8]:
        if theme in existing:
            continue
        carriers, score, place, lens = theme_support(world, theme)
        if len(carriers) < MIN_PEOPLE or score < MIN_SCORE:
            continue
        # Culture needs more than shared feeling: someone has to have made
        # something out of it, and most of the town has to carry it.
        made_of_it = sum(1 for a in world.artifacts.values() if theme in a.themes)
        if made_of_it < MIN_ARTIFACTS:
            continue
        if len(carriers) < max(MIN_PEOPLE, int(0.6 * len(world.people))):
            continue
        origin_event = None
        for event in reversed(world.history):
            if theme in event.themes and event.intensity > 0.4:
                origin_event = event
                break
        word, practices = LENS_RITUAL.get(lens, LENS_RITUAL["belonging"])
        practice = rng.choice(practices)
        day_of_year = (origin_event.day - 1) % DAYS_PER_YEAR + 1 if origin_event \
            else (world.clock.day - 1) % DAYS_PER_YEAR + 1
        tradition = Tradition(
            id=world.next_id("trad"),
            name=f"The {word} of {theme.title()}",
            theme=theme,
            practice=f"On this day the town {practice}.",
            day_founded=world.clock.day,
            day_of_year=day_of_year,
            founders=list(carriers),
            origin_event=origin_event.id if origin_event else None,
        )
        world.traditions[tradition.id] = tradition
        world.record("tradition_founded",
                     f"What people remembered about {theme} became a practice: "
                     f"{tradition.name}. {tradition.practice}",
                     place=place, participants=list(carriers),
                     themes=[theme, "tradition"], valence=0.35, intensity=0.6,
                     data={"tradition": tradition.id})
        world.narrate(f"A tradition was born: {tradition.name}.")
        founded.append(tradition)
        if len(founded) >= MAX_PER_CHECK:
            break
    return founded


def observe(world, rng: random.Random) -> List:
    """Run whichever traditions fall on today."""
    from .actions import broadcast

    today = (world.clock.day - 1) % DAYS_PER_YEAR + 1
    observed = []
    for tradition in world.traditions.values():
        if tradition.day_of_year != today or tradition.day_founded >= world.clock.day:
            continue
        place = None
        origin = world.event(tradition.origin_event) if tradition.origin_event else None
        if origin is not None:
            place = origin.place
        if place is None:
            place = next(iter(world.places))
        tradition.observances += 1
        event = world.record(
            "tradition",
            f"{tradition.name} was kept again at {world.places[place].name}. "
            f"{tradition.practice}",
            place=place,
            participants=[p.id for p in world.people_at(place)],
            themes=[tradition.theme, "tradition", "gathering"],
            valence=0.4, intensity=clamp(0.45 + 0.03 * tradition.observances),
            data={"tradition": tradition.id},
        )
        # Keeping a tradition draws the town to it.
        for person in world.people.values():
            if person.present and not person.is_player:
                person.place = place
        broadcast(world, event, rng)
        observed.append(tradition)
    return observed
