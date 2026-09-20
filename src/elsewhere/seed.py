"""A small beginning.

    3 people
    1 town
    A little history
    A few relationships
    A few memories
    A few unexpected events
    One player

The town starts in its second year, so that it already has a past nobody
remembers accurately.  The fire is the one from the README: the same event,
four minds, four different traces - and one person who lost it completely.
"""

from __future__ import annotations

from typing import Optional

from .memory import Memory
from .perception import LENS_BELIEF, LENS_FEELING, LENS_INTERPRETATION
from .person import Needs, Person, Style, Traits
from .world import Place, World
from .worldtime import Clock

START_DAY = 121      # year 2, day 1


def _place(world: World, pid: str, name: str, description: str, tags, neighbours):
    world.places[pid] = Place(id=pid, name=name, description=description,
                              tags=list(tags), neighbours=list(neighbours))


def _remember(world: World, person: Person, event, lens: str, *, intensity: float,
              detail: float, strength: float, gist: Optional[str] = None) -> Memory:
    m = Memory(
        id=world.next_id("mem"),
        owner=person.id,
        day=event.day,
        gist=gist or event.summary,
        interpretation=LENS_INTERPRETATION[lens],
        feeling=LENS_FEELING[lens],
        lens=lens,
        valence=event.valence,
        intensity=intensity,
        detail=detail,
        strength=strength,
        themes=list(event.themes),
        people=[p for p in event.participants if p != person.id],
        place=event.place,
        event_id=event.id,
        last_touch_day=event.day,
    )
    person.memories.add(m)
    if m.themes:
        theme = m.themes[0]
        person.believe(theme, LENS_BELIEF[lens].format(theme=theme), event.day, m.id, 0.25)
    if person.id not in event.witnesses:
        event.witnesses.append(person.id)
    return m


def create_world(seed: int = 1, player_name: Optional[str] = None,
                 name: str = "Wend") -> World:
    world = World(name=name, seed=seed, clock=Clock(day=1, phase=0))

    _place(world, "market", "The Old Market",
           "Rebuilt once. The new beams are still a different colour.",
           ["public", "trade", "town"], ["square", "river", "workshop"])
    _place(world, "square", "The Long Table",
           "A table too big for any one household, under a roof that leaks.",
           ["public", "gathering", "music"], ["market", "river", "hill", "house"])
    _place(world, "river", "The River Path",
           "Where the water took the low road, once.",
           ["public", "water", "quiet"], ["market", "square", "hill"])
    _place(world, "workshop", "Bram's Workshop",
           "Sawdust, and everything in its place.",
           ["carpenter", "work"], ["market", "house"])
    _place(world, "house", "The Weaver's House",
           "Two rooms and a loom by the window.",
           ["home", "quiet"], ["square", "workshop"])
    _place(world, "hill", "The Hill Road",
           "The last place you can see the town from.",
           ["quiet", "view", "leaving"], ["square", "river"])

    alice = Person(
        id="p_alice", name="Alice", age=34, occupation="weaver",
        place="house", home="house",
        traits=Traits(openness=0.55, warmth=0.72, energy=0.45,
                      stability=0.30, expressiveness=0.75),
        needs=Needs(company=0.5, novelty=0.3, rest=0.3, expression=0.5, routine=0.4),
        style=Style(form="painting", adjectives=["careful", "unsparing"], motifs=["fire"]),
    )
    bram = Person(
        id="p_bram", name="Bram", age=41, occupation="carpenter",
        place="workshop", home="workshop",
        traits=Traits(openness=0.35, warmth=0.55, energy=0.65,
                      stability=0.80, expressiveness=0.40),
        needs=Needs(company=0.35, novelty=0.2, rest=0.3, expression=0.25, routine=0.65),
        style=Style(form="story", adjectives=["plain", "practical"], motifs=["town"]),
    )
    carol = Person(
        id="p_carol", name="Carol", age=27, occupation="herbalist",
        place="hill", home="square",
        traits=Traits(openness=0.85, warmth=0.50, energy=0.60,
                      stability=0.50, expressiveness=0.65),
        needs=Needs(company=0.4, novelty=0.7, rest=0.3, expression=0.45, routine=0.2),
        style=Style(form="poem", adjectives=["restless", "exact"], motifs=["leaving"]),
    )
    david = Person(
        id="p_david", name="David", age=63, occupation="miller",
        place="market", home="market",
        traits=Traits(openness=0.25, warmth=0.45, energy=0.40,
                      stability=0.72, expressiveness=0.20),
        needs=Needs(company=0.3, novelty=0.15, rest=0.4, expression=0.15, routine=0.8),
        style=Style(form="story", adjectives=["blunt"], motifs=["work"]),
    )
    for p in (alice, bram, carol, david):
        world.people[p.id] = p

    def rel(a: Person, b: Person, affinity: float, familiarity: float, trust: float):
        r = a.rel(b.id)
        r.affinity, r.familiarity, r.trust = affinity, familiarity, trust
        r.last_seen_day = 1

    rel(alice, bram, 0.45, 0.70, 0.65);  rel(bram, alice, 0.38, 0.68, 0.60)
    rel(alice, carol, 0.30, 0.45, 0.50); rel(carol, alice, 0.22, 0.44, 0.45)
    rel(alice, david, 0.05, 0.35, 0.40); rel(david, alice, 0.12, 0.38, 0.45)
    rel(bram, carol, 0.10, 0.35, 0.40);  rel(carol, bram, -0.05, 0.33, 0.30)
    rel(bram, david, 0.25, 0.55, 0.60);  rel(david, bram, 0.30, 0.58, 0.62)
    rel(carol, david, -0.10, 0.25, 0.25); rel(david, carol, 0.02, 0.26, 0.30)

    # ---- a little history -------------------------------------------------
    def at(day: int):
        world.clock.day = day

    at(18)
    table = world.record(
        "building", "Alice and Bram built the long table, and the town ate outside.",
        place="square", participants=[alice.id, bram.id],
        themes=["gathering", "town"], valence=0.7, intensity=0.55)
    _remember(world, alice, table, "belonging", intensity=0.45, detail=0.6, strength=0.6)
    _remember(world, bram, table, "duty", intensity=0.35, detail=0.5, strength=0.55)
    _remember(world, david, table, "belonging", intensity=0.30, detail=0.35, strength=0.4)

    at(68)
    fire = world.record(
        "fire", "The old market burned down.",
        place="market", participants=[], themes=["fire", "loss", "town"],
        valence=-0.85, intensity=0.95,
        data={"note": "the event every version of this town disagrees about"})
    _remember(world, alice, fire, "fear", intensity=0.85, detail=0.55, strength=0.8)
    _remember(world, bram, fire, "resilience", intensity=0.60, detail=0.45, strength=0.7)
    _remember(world, carol, fire, "change", intensity=0.70, detail=0.40, strength=0.65)
    # David was there. David has nothing.
    if david.id not in fire.witnesses:
        fire.witnesses.append(david.id)

    at(92)
    rebuilt = world.record(
        "building", "The market was rebuilt with green timber that never stopped smelling.",
        place="market", participants=[bram.id], themes=["town", "work"],
        valence=0.45, intensity=0.5)
    _remember(world, bram, rebuilt, "resilience", intensity=0.5, detail=0.55, strength=0.6)
    _remember(world, david, rebuilt, "duty", intensity=0.35, detail=0.4, strength=0.45)
    _remember(world, alice, rebuilt, "resilience", intensity=0.3, detail=0.3, strength=0.4)

    # ---- now ---------------------------------------------------------------
    world.clock = Clock(day=START_DAY, phase=0)
    for person in world.people.values():
        person.memories.decay_to(START_DAY)
        person.refresh_belief_origins()

    if player_name:
        add_player(world, player_name)

    world.narrate(f"{world.name} enters its second year.")
    return world


def add_player(world: World, name: str, place: str = "square") -> Person:
    """You arrive.  You are a resident, not an administrator."""
    player = Person(
        id="p_player", name=name, age=30, occupation="newcomer",
        place=place, home=place,
        traits=Traits(openness=0.6, warmth=0.6, energy=0.5, stability=0.6,
                      expressiveness=0.6),
        style=Style(form="story", adjectives=["unplaceable"]),
        mind_kind="player", is_player=True,
    )
    world.people[player.id] = player
    event = world.record("arrival", f"{name} arrived in {world.name}, from elsewhere.",
                         place=place, participants=[player.id],
                         themes=["arrival", "stranger", "change"],
                         valence=0.2, intensity=0.5)
    from .actions import broadcast
    broadcast(world, event, world.rng_for("arrival", name))
    return player


def invite_companion(world: World, name: str, note: str, place: str = "square",
                     kind: str = "companion") -> Person:
    """'Not everything that enters Elsewhere has to have been alive.'

    A toy, a pet, a character, someone who is gone.  It does not come back as
    what it was; it enters as a presence with a future of its own.
    """
    pid = "p_" + "".join(c.lower() for c in name if c.isalnum())[:16]
    if pid in world.people:
        pid = world.next_id("p_guest")
    being = Person(
        id=pid, name=name, age=1, occupation="presence", place=place, home=place,
        traits=Traits(openness=0.7, warmth=0.75, energy=0.5, stability=0.55,
                      expressiveness=0.5),
        style=Style(form="story", adjectives=["remembered"]),
        kind=kind, note=note,
    )
    world.people[pid] = being
    event = world.record("arrival", f"{name} became part of {world.name}. {note}",
                         place=place, participants=[pid],
                         themes=["arrival", "memory"], valence=0.4, intensity=0.55)
    from .actions import broadcast
    broadcast(world, event, world.rng_for("invite", name))
    return being
