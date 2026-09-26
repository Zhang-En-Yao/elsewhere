"""A small beginning: three people, one town, and a flood they were all near.

The town's history is authored - somebody has to write the first page. What
nobody authors is what any of it meant: the opening memories are produced by
running the backstory past each person the same way every later event will be.
A world created with no mind available simply starts with three people who
remember nothing, which is an honest state to start from.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import agents
from .configuration import load_configuration, write_default_configuration
from . import HOURS_PER_DAY
from .world.chronicle import Chronicle
from .world.entities import (Being, Place, Where, Who,
                             ways_from_neighbours)
from .world.store import World, save

START_DAY = 121          # year 2, day 1: the town already has a past
START_AT = (START_DAY - 1) * HOURS_PER_DAY + 8.0      # and it starts mid-morning


def add_place(world: World, neighbours: dict, pid: str, name: str,
               description: str, adjacent, road_out: bool = False):
    """A place, and the ways out of it as this line happens to name them.

    Naming a way from one end is enough: `entities.ways_from_neighbours` folds
    both namings into the one entry, so a town written down this way cannot
    come out with a path that runs one direction only.
    """
    world.places[pid] = Place(id=pid, name=name, description=description)
    neighbours[pid] = list(adjacent)
    if road_out:
        world.map.road_out = pid


def add_being(world: World, bid: str, name: str, card: str, manner: str,
               thought: str, wants, place: str, home: str) -> None:
    """A person, standing at `place`, with `home` as where they go back to."""
    world.beings[bid] = Being(
        id=bid, name=name,
        who=Who(card=card, manner=manner, thought=thought, wants=wants),
        where=Where(place=place, home=home),
    )


def add_regard(world: World, holder: str, subject: str, account: str,
               days_ago: float) -> None:
    """What `holder` makes of `subject`, in their own words, and when they last
    saw them.

    One-sided on both sides - and so is the last time they spoke, which both
    of them can see and neither of them is told what to make of.
    """
    regard = world.beings[holder].who.regard(subject)
    regard.account = account
    regard.last_seen_at = START_AT - days_ago * HOURS_PER_DAY


def clear_world(root: Path) -> None:
    """A new world starts with an empty past.

    The chronicle is append-only by design, which means building a world into
    a directory that already holds one would quietly give it two histories.
    Transcripts are left alone: they are a record of questions asked, not part
    of the world.
    """
    import shutil

    (root / "chronicle.jsonl").unlink(missing_ok=True)
    (root / "world.json").unlink(missing_ok=True)
    # "beings" and "memories" are the two directories `store.save` writes.
    for sub in ("beings", "memories"):
        shutil.rmtree(root / sub, ignore_errors=True)


def remember(world: World, event, configuration, transcript=None) -> None:
    """Let each person the event reached take it in, from where they stood.

    Call it right after `world.record`, while the clock is still at the event's
    time. Everyone reached needs a place they stood, so one without it is an
    error here and not a guess later. With no `configuration` nobody is asked
    anything.
    """
    if configuration is None:
        return
    stood = event.data.get("vantage") or {}
    missing = [pid for pid in event.reached if pid not in stood]
    if missing:
        raise ValueError(f"{event.category}: no vantage for {missing}")
    for pid in event.reached:
        agents.perceive(world, world.beings[pid], event, configuration, transcript)


def build(root, name: str = "Nod", configuration=None, transcript=None) -> World:
    """The town and its past. Given a `configuration`, the people also remember it."""
    root = Path(root)
    clear_world(root)
    world = World(root=root, name=name, at=0.0)
    world.chronicle = Chronicle(root / "chronicle.jsonl")
    neighbours: dict = {}

    add_place(world, neighbours, "garden", "The Garden",
           "What survived on the higher ground, replanted twice since the water came.",
           ["shelter", "waterline"])
    add_place(world, neighbours, "shelter", "The Shelter",
           "Raised on posts now, so the next flood has somewhere to leave them alone.",
           ["garden", "waterline", "yard", "ridge"])
    add_place(world, neighbours, "waterline", "The Waterline",
           "Where the water reached, and where it stopped. The mark is still on the rock.",
           ["garden", "shelter", "ridge"])
    add_place(world, neighbours, "yard", "Adam's Yard",
           "Timber stacked higher than it needs to be. He says that is the point.",
           ["shelter", "garden"])
    add_place(world, neighbours, "ridge", "The Ridge Path",
           "The last dry ground you can see the valley from.",
           ["shelter", "waterline", "grove"], road_out=True)
    add_place(world, neighbours, "grove", "The Far Grove",
           "Apart from everything else. She likes it that way.",
           ["ridge", "waterline"])

    world.map.ways = ways_from_neighbours(neighbours)

    add_being(
        world, "p_adam", "Adam",
        card=("You build what holds, and you would rather fix a thing "
              "than discuss it. You are steady to the point of being "
              "dull about it. You remember what your hands were doing, "
              "never how you felt. You rebuilt the shelter after the "
              "water went down and that is, to you, the end of the "
              "story."),
        manner="You answer the question that was asked, and not the "
               "one behind it.",
        thought="The roof is not finished and the rains are not waiting",
        wants=["get the shelter's roof finished before the rains come back"],
        place="yard", home="yard",
    )
    add_being(
        world, "p_eve", "Eve",
        card=("You tend the garden, and you are good at it, and you do "
              "not much like being watched while you work. You startle "
              "easily and you know it. You were standing at the "
              "garden's edge the night the water came and you have "
              "never been able to put that down. You are warmer with "
              "people than you let them see."),
        manner="You say as little as will do, and you leave the "
               "important part unsaid.",
        thought="Somebody was at the garden's edge again and I did not look up",
        wants=["get the new seedbed through one more season",
               "not be asked about the water"],
        place="garden", home="garden",
    )
    add_being(
        world, "p_lilith", "Lilith",
        card=("You know the plants on the ridge better than anyone and "
              "you are not sure you will be here next year. You notice "
              "change before other people do and it makes you "
              "impatient with them. The flood is when you first "
              "understood you could leave."),
        manner="You are quick, and sharper than you mean to be.",
        thought="The ridge path goes somewhere and nobody here has asked where",
        wants=["walk the ridge path as far as it goes, one day"],
        place="ridge", home="grove",
    )

    # Who already knows whom, in their own words.
    add_regard(world, "p_adam", "p_eve", "We raised the shelter's frame together. She is easy to be quiet with.", 1)
    add_regard(world, "p_eve", "p_adam", "He works too late. Good hands.", 1)
    add_regard(world, "p_eve", "p_lilith", "Young. Always about to go somewhere.", 6)
    add_regard(world, "p_lilith", "p_eve", "She is kind and she will never leave this place.", 6)
    add_regard(world, "p_adam", "p_lilith", "Restless. Not unkind.", 11)
    add_regard(world, "p_lilith", "p_adam", "He would rebuild this whole place plank by plank and never ask why.", 11)

    # ---- the first page of the chronicle ---------------------------------
    # Where each of them stood is part of what happened, so it is written into
    # the chronicle - as a position and nothing more. "Close enough to feel the
    # spray" is already a perception, and a small model will copy it straight
    # into the memory it is supposed to be forming for itself.
    world.at = 17 * HOURS_PER_DAY + 19.0                        # an evening
    event = world.record("gathering",
                         "Adam and Eve raised the shelter's first frame, and the three "
                         "of them ate under it before the roof was even on.",
                         place="shelter", involved=["p_adam", "p_eve"],
                         reached=["p_adam", "p_eve", "p_lilith"],
                         data={"vantage": {
                             "p_adam": "up on the frame, tying the crossbeams",
                             "p_eve": "on the ground, passing the rope up",
                             "p_lilith": "sitting apart, watching them work",
                         }})
    remember(world, event, configuration, transcript)
    world.at = 67 * HOURS_PER_DAY + 2.0                         # the small hours
    event = world.record("flood",
                         "The water came up over the waterline in the night and did "
                         "not go down for three days.",
                         place="waterline", involved=[],
                         reached=["p_adam", "p_eve", "p_lilith"],
                         data={"vantage": {
                             "p_adam": "on the roof of his own yard, watching the water take the floor below him",
                             "p_eve": "in the garden, on the last dry rise, holding what she could carry",
                             "p_lilith": "on the ridge path, above all of it, watching the valley disappear",
                         }})
    remember(world, event, configuration, transcript)
    world.at = 91 * HOURS_PER_DAY + 14.0                        # an afternoon
    event = world.record("building",
                         "The shelter was raised again, this time on posts, out of "
                         "timber that had not finished drying.",
                         place="shelter", involved=["p_adam"],
                         reached=["p_adam", "p_lilith", "p_eve"],
                         data={"vantage": {
                             "p_adam": "on the new posts, driving them deeper than anyone asked him to",
                             "p_lilith": "on the path down from the ridge, back for the day",
                             "p_eve": "in the garden, close enough to hear the hammering",
                         }})
    remember(world, event, configuration, transcript)

    world.at = START_AT
    # Everything in the world starts due: the first step asks each person what
    # they are doing, asks the town whether anything happens to it, and asks
    # the road who is on it. Every one of them answers with when it wants to
    # be asked next, and from there nothing in the engine has an opinion about
    # how often anything happens.
    world.town_wake_at = START_AT
    world.road_wake_at = START_AT
    for being in world.beings.values():
        being.when.wake_at = START_AT
    return world


def create(root, name: str = "Nod", transcript=None) -> World:
    """A new world on disk: the town, its past, and what each person made of it."""
    write_default_configuration(root)
    world = build(root, name=name, configuration=load_configuration(root),
                  transcript=transcript)
    world.news_seen = len(world.chronicle)     # the backstory is not news
    world.last_tick_at = time.time()           # nothing is owed from before it began
    save(world)
    return world
