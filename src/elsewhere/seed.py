"""A small beginning: four people, one town, and a fire they were all near.

The town's history is authored - somebody has to write the first page. What
nobody authors is what any of it meant: the opening memories are produced by
running the backstory past each person the same way every later event will be.
A world created with no mind available simply starts with four people who
remember nothing, which is an honest state to start from.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from . import agents, config as config_mod
from .world.chronicle import Chronicle
from .world.entities import Person, Place
from .world.store import World, save

START_DAY = 121          # year 2, day 1: the town already has a past


def _place(world: World, pid: str, name: str, description: str, tags, neighbours):
    world.places[pid] = Place(id=pid, name=name, description=description,
                              tags=list(tags), neighbours=list(neighbours))


def _clear(root: Path) -> None:
    """A new world starts with an empty past.

    The chronicle is append-only by design, which means building a world into
    a directory that already holds one would quietly give it two histories.
    Transcripts are left alone: they are a record of questions asked, not part
    of the world.
    """
    import shutil

    (root / "chronicle.jsonl").unlink(missing_ok=True)
    (root / "world.json").unlink(missing_ok=True)
    for sub in ("people", "memories"):
        shutil.rmtree(root / sub, ignore_errors=True)


def build(root, name: str = "Wend") -> World:
    root = Path(root)
    _clear(root)
    world = World(root=root, name=name, day=1, phase=0)
    world.chronicle = Chronicle(root / "chronicle.jsonl")

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

    people = [
        Person(
            id="p_alice",
            voice="Short, careful sentences. You leave the important part unsaid.", name="Alice", age=34, occupation="weaver",
            place="house", home="house", mood="watchful",
            card=("You weave, and you are good at it, and you do not much like "
                  "being looked at while you work. You startle easily and you "
                  "know it. You were near the market the night it burned and you "
                  "have never been able to put that down. You are warmer with "
                  "people than you let them see."),
            wants=["finish the piece on the loom", "not be asked about the fire"],
        ),
        Person(
            id="p_bram",
            voice="Plain and practical. You remember what your hands were doing, never how you felt.", name="Bram", age=41, occupation="carpenter",
            place="workshop", home="workshop", mood="even",
            card=("You make things that hold. You are steady to the point of "
                  "being dull about it, and you would rather repair something "
                  "than discuss it. You rebuilt the market after the fire and "
                  "that is, to you, the end of the story."),
            wants=["get the roof at the long table sorted before winter"],
        ),
        Person(
            id="p_carol",
            voice="Quick and a little sharp. You talk about what things mean for later.", name="Carol", age=27, occupation="herbalist",
            place="hill", home="square", mood="restless",
            card=("You know the plants on the hill better than anyone and you "
                  "are not sure you will be here next year. You notice change "
                  "before other people do and it makes you impatient with them. "
                  "The fire is when you first understood you could leave."),
            wants=["walk the hill road as far as it goes, one day"],
        ),
        Person(
            id="p_david",
            voice="As few words as possible. Most things are not worth mentioning, and you do not.", name="David", age=63, occupation="miller",
            place="market", home="market", mood="flat",
            card=("You mill grain, you have milled grain for forty years, and "
                  "you will mill grain tomorrow. You do not keep much. People "
                  "assume you are hiding something behind the silence and there "
                  "is nothing behind it at all."),
            wants=["nothing out of the ordinary"],
        ),
    ]
    for person in people:
        world.people[person.id] = person

    # Who already knows whom, in their own words. One-sided on both sides.
    def tie(a: str, b: str, note: str, closeness: float):
        world.people[a].tie(b).note = note
        world.people[a].tie(b).closeness = closeness
        world.people[a].tie(b).last_seen_day = 1

    tie("p_alice", "p_bram", "We built the long table together. He is easy to be quiet with.", 0.7)
    tie("p_bram", "p_alice", "She works too late. Good hands.", 0.68)
    tie("p_alice", "p_carol", "Young. Always about to go somewhere.", 0.45)
    tie("p_carol", "p_alice", "She is kind and she will never leave this town.", 0.44)
    tie("p_alice", "p_david", "He was there the night of the fire and never speaks of it.", 0.35)
    tie("p_david", "p_alice", "The weaver. Keeps herself to herself.", 0.38)
    tie("p_bram", "p_carol", "Restless. Not unkind.", 0.35)
    tie("p_carol", "p_bram", "He would rebuild this town brick by brick and never ask why.", 0.33)
    tie("p_bram", "p_david", "Forty years at the mill. Reliable.", 0.55)
    tie("p_david", "p_bram", "Good with a saw. Talks when there is something to say.", 0.58)
    tie("p_carol", "p_david", "He has been here forever and has nothing to show for it.", 0.25)
    tie("p_david", "p_carol", "The herb girl.", 0.26)

    # ---- the first page of the chronicle ---------------------------------
    # Where each of them stood is part of what happened, so it is written into
    # the chronicle - as a position and nothing more. "Close enough to feel the
    # heat" is already a perception, and a small model will copy it straight
    # into the memory it is supposed to be forming for itself.
    world.day, world.phase = 18, 2                              # evening
    world.record("gathering",
                 "Alice and Bram built the long table, and the town ate outside.",
                 where="square", who=["p_alice", "p_bram"],
                 present=["p_alice", "p_bram", "p_david"],
                 tags=["gathering", "town", "building"],
                 data={"vantage": {
                     "p_alice": "at one end of the table",
                     "p_bram": "at the other end of the table",
                     "p_david": "at the far corner, near the door",
                 }})
    world.day, world.phase = 68, 3                              # night
    world.record("fire", "The old market burned down.",
                 where="market", who=[],
                 present=["p_alice", "p_bram", "p_carol", "p_david"],
                 tags=["fire", "loss", "town"],
                 data={"vantage": {
                     "p_alice": "across the street from the market",
                     "p_bram": "on the roof of the workshop next door",
                     "p_carol": "on the hill road above the town",
                     "p_david": "at the edge of the crowd in the square",
                 }})
    world.day, world.phase = 92, 1                              # afternoon
    world.record("building",
                 "The market was rebuilt with green timber that never stopped "
                 "smelling.",
                 where="market", who=["p_bram"],
                 present=["p_bram", "p_david", "p_alice"],
                 tags=["town", "work", "building"],
                 data={"vantage": {
                     "p_bram": "on the scaffold at the market",
                     "p_david": "on the road between the river and the market",
                     "p_alice": "in the street outside the market",
                 }})

    world.day, world.phase = START_DAY, 0
    # The town starts settled: nobody is owed, so the road waits a year before
    # it is worth asking who is on it.
    world.road_asked_on = START_DAY
    return world


def remember_backstory(world: World, config, transcript=None) -> List:
    """Put the town's history past each person, so the first memories are theirs."""
    made = []
    here_now = {p.id: p.place for p in world.people.values()}
    for event in world.chronicle.all():
        day_before = world.day
        world.day = event.day
        for person in world.people.values():
            if person.id not in event.present:
                continue
            person.place = event.where or person.place
            trace = agents.perceive(world, person, event, config, transcript)
            if trace is not None:
                made.append(trace)
        world.day = day_before
    for person in world.people.values():
        person.place = here_now[person.id]
    return made


def create(root, name: str = "Wend", remember: bool = True,
           transcript=None) -> World:
    world = build(root, name=name)
    config_mod.write_default(root)
    if remember:
        remember_backstory(world, config_mod.load(root), transcript)
    world.news_seen = len(world.chronicle)     # the backstory is not news
    save(world)
    return world
