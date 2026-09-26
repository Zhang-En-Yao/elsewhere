"""A small beginning: three people, one town, and four things that happened to it.

The town's history is authored - somebody has to write the first page. What
nobody authors is what any of it meant: the opening memories are produced by
running the backstory past each person the same way every later event will be.
A world created with no mind available simply starts with three people who
remember nothing, which is an honest state to start from.

It is written in that order too - the events first, and then a town that is
what they left behind. Nothing here is scenery that the story then had to be
fitted into.

WHAT HAPPENS is out of Hindu cosmology, and it is the canonical events
themselves rather than a village keeping their feast days: the Ganga coming
down out of the sky, taken on a head first so the fall would not open the
ground; the churning of the water, for the poison and then for the little that
was sweet; the deluge at the turn of the age, with the fish that outgrew every
vessel and the boat tied to its horn; and seven days of rain held off under a
hill lifted on one hand. They happen here, in this valley, to these three.

WHEN is the day each one's own tradition puts it on, which is why the world's
calendar is the idealised Hindu one - twelve months of thirty tithis, six
seasons, three hundred and sixty days (`world.store`). The descent is Jyeshtha
10 waxing, Ganga Dussehra. The churning is Phalguna 14 waning, Maha
Shivaratri, the night nobody sleeps, because of what was drunk that night. The
deluge is Chaitra 3 waxing, Matsya Jayanti. The lifting is Kartika 1 waxing,
Govardhan Puja, the Annakut day after Diwali night. The world then opens on
Chaitra 1 waxing - new year's morning, with the rains four months off.

WHERE is what those four left on the ground, in the order they made it, and
each one is named for the Jewish place whose own story is about the same thing
happening. The river came down on a ledge and did not kill the man who took
it: Penuel, where Jacob saw God face to face and lived. It filled a bitter
water with one sweet reach in it: Marah, whose water could not be drunk until
it could. The hill they stood up in that water to churn against is the same
hill that was later held over the town: Sinai, which a midrash has God hold
over Israel like an upturned vat. The boat came to rest on the high ground,
which is also where the road out goes: Mizpah, the watchpost, and the heap two
people left where they parted - and the peak the fish's boat is tied to is
called Naubandhana, the boat-binding. Then the three things the survivors made
from what was left: the hull itself, turned over on the one patch of ground
the lifted hill kept dry, which is Beth El, a house with a stone at its
corner; the ground it was built on, which is the Boatyard; and the seed that
was carried in it, which is Gan Eden, a garden called Eden in the land east of
it.

WHO is three people the events gave something to carry. Bezalel, "in the
shadow of God", built the tabernacle; here he built the boat and then the
house out of the boat. Havvah is "the living"; she kept the fish, and the
garden is the seed she brought off the boat. Lilith left a garden rather than
stay in one, and she is the one standing on the high ground when the boat came
up out of the water, and the one who may yet go.

None of it is narrated as myth. Every event below is written as plainly as
every event that comes after it, because the freight is not in the sentence -
it is in who it happened to, and where they were standing.
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
from .world.store import (DAYS_PER_MONTH, DAYS_PER_YEAR, TITHIS_PER_PAKSHA,
                          World, save)


def on(year: int, month: int, tithi: int, paksha: str, hour: float) -> float:
    """The world's clock at a date written in the world's own calendar.

    `month` is 1-12 as `store.MONTHS` runs, `tithi` is the 1-15 of a
    fortnight, and `paksha` is "waxing" or "waning" - waxing first, because
    these months begin the day after a new moon. The dates below are written
    this way rather than as day numbers so that a date which is meant to be
    Govardhan Puja reads as Kartika 1 waxing and can be checked against a
    calendar instead of against a comment.
    """
    if paksha not in ("waxing", "waning"):
        raise ValueError(f"a fortnight waxes or wanes: {paksha!r}")
    if not 1 <= tithi <= TITHIS_PER_PAKSHA:
        raise ValueError(f"a fortnight is {TITHIS_PER_PAKSHA} days: {tithi}")
    day = ((year - 1) * DAYS_PER_YEAR + (month - 1) * DAYS_PER_MONTH + tithi
           + (TITHIS_PER_PAKSHA if paksha == "waning" else 0))
    return (day - 1) * HOURS_PER_DAY + hour


# The town's past, each event on the day its own tradition puts it on.
DESCENT = on(1, 3, 10, "waxing", 11.0)     # Jyeshtha 10 waxing: Ganga Dussehra
CHURNING = on(1, 12, 14, "waning", 2.0)    # Phalguna 14 waning: Maha Shivaratri
DELUGE = on(2, 1, 3, "waxing", 4.0)        # Chaitra 3 waxing: Matsya Jayanti
LIFTING = on(2, 8, 1, "waxing", 14.0)      # Kartika 1 waxing: Govardhan Puja

#: Chaitra 1 waxing: new year's morning, two years of past behind it.
START_AT = on(3, 1, 1, "waxing", 8.0)
START_DAY = int(START_AT // HOURS_PER_DAY) + 1


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


def remember(world: World, event, configuration, transcript=None) -> list:
    """Let each person the event reached take it in, from where they stood.

    Call it right after `world.record`, while the clock is still at the event's
    time. Everyone reached needs a place they stood, so one without it is an
    error here and not a guess later. With no `configuration` nobody is asked
    anything. What comes back is what stuck, which is not everybody: a mind
    that gave nothing keeps nothing.
    """
    if configuration is None:
        return []
    stood = event.data.get("vantage") or {}
    missing = [pid for pid in event.reached if pid not in stood]
    if missing:
        raise ValueError(f"{event.category}: no vantage for {missing}")
    kept = []
    for pid in event.reached:
        memory = agents.perceive(world, world.beings[pid], event, configuration,
                                 transcript)
        if memory is not None:
            kept.append(memory)
    return kept


def unheard(line: str) -> None:
    """Where a line goes when nobody asked for one. `build` is a library call."""


def past(world: World, event, configuration, transcript, say) -> None:
    """Take an event in, and say how that went.

    The four events below are the whole wait in making a world - everybody
    reached is asked about each of them, one question at a time, and on a model
    running at home that is minutes. So a line per event, for whoever is
    watching a terminal.
    """
    started = time.time()
    kept = remember(world, event, configuration, transcript)
    if configuration is None:
        return                  # nobody was asked, so there was no wait to report
    say(f"  {event.category:<9} {len(kept)} of {len(event.reached)} kept "
        f"something of it  ({time.time() - started:.0f}s)")


def build(root, name: str = "Nod", configuration=None, transcript=None,
          say=unheard) -> World:
    """The town and its past. Given a `configuration`, the people also remember it."""
    root = Path(root)
    clear_world(root)
    world = World(root=root, name=name, at=0.0)
    world.chronicle = Chronicle(root / "chronicle.jsonl")
    neighbours: dict = {}

    # Every place here is what one of the four events left behind, which is
    # also the order they were made in: the river, the water it filled, the
    # hill that was put into it, the high ground the boat stopped on, and then
    # the three things the people made out of what was left.
    add_place(world, neighbours, "penuel", "Penuel",
           "The ledge the river came down onto, and the seven channels it "
           "went out of. You cannot hear anything else standing on it.",
           ["marah", "mizpah"])
    add_place(world, neighbours, "marah", "Marah",
           "The water. It is bitter the whole length of it except for one "
           "reach at the near end, which is not, and which is what the town "
           "drinks. A ring of stones out of the riverbed marks how far up it "
           "came the year it came over everything.",
           ["mizpah", "penuel", "sinai"])
    add_place(world, neighbours, "sinai", "Sinai",
           "The hill. It has been stood up in the water once and held over "
           "the town once, and it is back where it was both times. She knows "
           "what grows on it and nobody else goes up.",
           ["mizpah", "marah"])
    add_place(world, neighbours, "mizpah", "Mizpah",
           "The high ground, where the boat came aground when the water was "
           "over everything else, and where the road goes out. You can see "
           "the whole valley, and whoever is leaving it.",
           ["penuel", "sinai"], road_out=True)
    add_place(world, neighbours, "bethel", "Beth El",
           "The house: the boat, turned over and set on posts, on the one "
           "patch of ground here that has never been rained on. There is a "
           "standing stone at the corner that somebody slept against.",
           ["marah", "yard", "mizpah"])
    add_place(world, neighbours, "yard", "The Boatyard",
           "Where the boat was built, and where the offcuts still are, "
           "stacked higher than they need to be. He says that is the point.",
           ["bethel", "garden"])
    add_place(world, neighbours, "garden", "Gan Eden",
           "The garden, and the name is older than the town. Every seed in "
           "it came off the boat in her hands, and it has been put in twice "
           "since, because the seven days of rain took the first one apart.",
           ["bethel", "marah", "yard"])

    world.map.ways = ways_from_neighbours(neighbours)

    add_being(
        world, "p_bezalel", "Bezalel",
        card=("You build what holds, and you would rather fix a thing "
              "than discuss it. You are steady to the point of being "
              "dull about it. You remember what your hands were doing, "
              "never how you felt. You built the boat, and tied it to "
              "the horn, and when the rain was over you brought it down "
              "off Mizpah and turned it over and that is the house they "
              "live in, and you would sooner talk about the joinery of "
              "it than about the fish."),
        manner="You answer the question that was asked, and not the "
               "one behind it.",
        thought="The seams over the stern end are opening and the rains are not waiting",
        wants=["get the seams over Beth El closed before the rains come back"],
        place="yard", home="bethel",
    )
    add_being(
        world, "p_havvah", "Havvah",
        card=("You keep the garden alive, and you are good at it, and "
              "you do not much like being watched while you work. You "
              "startle easily and you know it. You kept the fish while "
              "it outgrew the jar and then the trough and then the tank, "
              "and it was you it came back and spoke to, and every "
              "living thing in the garden came off the boat in your "
              "hands. You have never once said the part about being "
              "spoken to out loud. You are warmer with people than you "
              "let them see."),
        manner="You say as little as will do, and you leave the "
               "important part unsaid.",
        thought="Somebody was at the garden's edge again and I did not look up",
        wants=["get the new seedbed through one more season",
               "not be asked about the water"],
        place="garden", home="garden",
    )
    add_being(
        world, "p_lilith", "Lilith",
        card=("You know what grows on Sinai better than anyone, and "
              "nobody else goes up it, and you are not sure you will be "
              "here next year. You notice change before other people do "
              "and it makes you impatient with them. You were standing "
              "on Mizpah when the boat came up out of the drowned valley "
              "and grounded at your feet, and that is when you "
              "understood that the valley has an outside."),
        manner="You are quick, and sharper than you mean to be.",
        thought="The road past Mizpah goes somewhere and nobody here has asked where",
        wants=["walk the road past Mizpah as far as it goes, one day"],
        place="mizpah", home="sinai",
    )

    # Who already knows whom, in their own words.
    add_regard(world, "p_bezalel", "p_havvah", "Seven days under the hill and she never once asked how. She is easy to be quiet with.", 1)
    add_regard(world, "p_havvah", "p_bezalel", "He works too late. Good hands.", 1)
    add_regard(world, "p_havvah", "p_lilith", "Young. Always about to go somewhere.", 6)
    add_regard(world, "p_lilith", "p_havvah", "She is kind and she will never leave this place.", 6)
    add_regard(world, "p_bezalel", "p_lilith", "Restless. Not unkind.", 11)
    add_regard(world, "p_lilith", "p_bezalel", "He would rebuild this whole place plank by plank and never ask why.", 11)

    # ---- the first page of the chronicle ---------------------------------
    # Where each of them stood is part of what happened, so it is written into
    # the chronicle - as a position and nothing more. "Close enough to feel the
    # spray" is already a perception, and a small model will copy it straight
    # into the memory it is supposed to be forming for itself.
    world.at = DESCENT
    event = world.record("descent",
                         "The river came down. It came out of the sky onto the "
                         "ledge under Mizpah and it would have opened the ground, "
                         "except that it came down onto a man's head first and out "
                         "of his hair in seven streams. It ran on down the valley "
                         "across ash that had lain there longer than anybody could "
                         "say, and where it touched the ash there was nothing left "
                         "owing to them. It has run here ever since, and it is what "
                         "filled Marah.",
                         place="penuel", involved=[],
                         reached=["p_bezalel", "p_havvah", "p_lilith"],
                         data={"vantage": {
                             "p_bezalel": "down in the dry channel it came into, walking his cut stone out of it",
                             "p_havvah": "further down the valley, watching the dust go dark all at once",
                             "p_lilith": "up on Mizpah, nearest to where it came down, wet through",
                         }})
    past(world, event, configuration, transcript, say)
    world.at = CHURNING
    event = world.record("churning",
                         "Marah was pulled one way and then the other all night, "
                         "around Sinai, which had been stood up in the middle of it "
                         "for them to pull against, by two crowds with a hold on "
                         "either end of a snake. What came up first was a poison and "
                         "everything in the water died of it; a man drank off the "
                         "rest of it and did not die, and his throat stayed blue. "
                         "What came up last was sweet, and there was very little of "
                         "it, and it is the near reach that the town drinks from "
                         "now. Nobody in the valley slept.",
                         place="marah", involved=[],
                         reached=["p_bezalel", "p_havvah", "p_lilith"],
                         data={"vantage": {
                             "p_bezalel": "on the bank, taking a turn on the snake when the near side was short-handed",
                             "p_havvah": "well back from the water, on the high side, out of the way of both crowds",
                             "p_lilith": "down at the edge of it, as close as she was let, watching the near side's feet",
                         }})
    past(world, event, configuration, transcript, say)
    world.at = DELUGE
    event = world.record("flood",
                         "The fish Havvah had kept since it was small - out of the "
                         "jar, out of the trough, out of the tank, and into Marah "
                         "when there was nowhere left to put it - came back and said "
                         "the water was coming, and it came before morning. It went "
                         "over the ring of stones, over the valley, over everything "
                         "anybody had built. The boat was tied to the fish's horn and "
                         "went aground on Mizpah, and the water did not go down for "
                         "three days.",
                         place="marah", involved=["p_havvah", "p_bezalel"],
                         reached=["p_bezalel", "p_havvah", "p_lilith"],
                         data={"vantage": {
                             "p_bezalel": "in the boat he had built, at the rope, with the horn in front of him",
                             "p_havvah": "in the stern of the boat, with the seed she had been told to bring",
                             "p_lilith": "on Mizpah, above all of it, watching the valley go under and then the boat come up to her",
                         }})
    past(world, event, configuration, transcript, say)
    world.at = LIFTING
    event = world.record("lifting",
                         "It rained for seven days without stopping, hard enough to "
                         "take the first of the new planting apart, and for those "
                         "seven days Sinai stood up off its own ground with the three "
                         "of them and their animals underneath it, and the ground "
                         "underneath it did not get wet. A boy was holding it up on "
                         "one hand. On the eighth day the rain stopped and he put it "
                         "back, and afterwards nobody could say whose boy he was. "
                         "The boat came down off Mizpah onto that dry ground after "
                         "the rain, and was turned over, and it is the house.",
                         place="bethel", involved=[],
                         reached=["p_bezalel", "p_lilith", "p_havvah"],
                         data={"vantage": {
                             "p_bezalel": "underneath it, one hand on a post he had driven that morning and did not need",
                             "p_lilith": "at the edge of it, out in the rain, looking up at the underside of the hill",
                             "p_havvah": "underneath it, with what she had got out of the beds in her skirt",
                         }})
    past(world, event, configuration, transcript, say)

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


def create(root, name: str = "Nod", transcript=None, say=unheard) -> World:
    """A new world on disk: the town, its past, and what each person made of it."""
    write_default_configuration(root)
    world = build(root, name=name, configuration=load_configuration(root),
                  transcript=transcript, say=say)
    world.news_seen = len(world.chronicle)     # the backstory is not news
    world.last_tick_at = time.time()           # nothing is owed from before it began
    save(world)
    return world
