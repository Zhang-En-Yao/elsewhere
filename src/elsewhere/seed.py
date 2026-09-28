"""The starting world: three people, one town, and four past events.

The history is authored, and so is the page each person starts with; what the
history left in them is not. The backstory has reached everyone and nobody has
looked at it yet, so the first thing each of them does on the first morning is
see it, note what they keep of it, and go over that the first evening - like
any later day.

Events are canonical Hindu myths (Ganga's descent, the churning, Matsya's
deluge, Govardhan lifted), each dated on its own festival in the Hindu calendar.
Places are what those events left behind, each named for a Jewish place whose
story is the same (e.g. Penuel: seeing God and living). The people carry names
fitting their part: Bezalel built the boat and the house, Havvah kept the fish
and the garden, Lilith stands where the road goes out.

Events are written plainly, not as myth.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import HOURS_PER_DAY, configuration
from .world.chronicle import Chronicle
from .world.entities import (Being, Place, Where, Who,
                             ways_from_neighbours)
from .world.pages import Page
from .world.store import (DAYS_PER_MONTH, DAYS_PER_YEAR, TITHIS_PER_PAKSHA,
                          World, save)


def moment(year: int, month: int, tithi: int, paksha: str, hour: float) -> float:
    """`tithi` is 1-15 within the `paksha` ("waxing" first, amanta months)."""
    if paksha not in ("waxing", "waning"):
        raise ValueError(f"a fortnight waxes or wanes: {paksha!r}")
    if not 1 <= tithi <= TITHIS_PER_PAKSHA:
        raise ValueError(f"a fortnight is {TITHIS_PER_PAKSHA} days: {tithi}")
    day = ((year - 1) * DAYS_PER_YEAR + (month - 1) * DAYS_PER_MONTH + tithi
           + (TITHIS_PER_PAKSHA if paksha == "waning" else 0))
    return (day - 1) * HOURS_PER_DAY + hour


DESCENT = moment(1, 3, 10, "waxing", 11.0)     # Jyeshtha 10 waxing: Ganga Dussehra
CHURNING = moment(1, 12, 14, "waning", 2.0)    # Phalguna 14 waning: Maha Shivaratri
DELUGE = moment(2, 1, 3, "waxing", 4.0)        # Chaitra 3 waxing: Matsya Jayanti
LIFTING = moment(2, 8, 1, "waxing", 14.0)      # Kartika 1 waxing: Govardhan Puja

#: Chaitra 1 waxing: new year's morning, two years of past behind it.
START_AT = moment(3, 1, 1, "waxing", 8.0)
START_DAY = int(START_AT // HOURS_PER_DAY) + 1


def add_place(world: World, neighbours: dict, place_id: str, name: str,
              description: str, adjacent, road: bool = False):
    world.places[place_id] = Place(id=place_id, name=name, description=description)
    neighbours[place_id] = list(adjacent)
    if road:
        world.map.road = place_id


def add_being(world: World, being_id: str, name: str, card: str, manner: str,
              notebook: str, place: str, home: str) -> None:
    world.beings[being_id] = Being(
        id=being_id, name=name,
        who=Who(card=card, manner=manner, notebook=notebook),
        where=Where(place=place, home=home),
    )


def clear(root: Path) -> None:
    """Needed because the chronicle is append-only. Transcripts are kept."""
    import shutil

    (root / "chronicle.jsonl").unlink(missing_ok=True)
    (root / "world.json").unlink(missing_ok=True)
    for directory in ("beings", "notes", "pages"):
        shutil.rmtree(root / directory, ignore_errors=True)


def build(root, name: str = "Nod") -> World:
    root = Path(root)
    clear(root)
    world = World(root=root, name=name, at=0.0)
    world.chronicle = Chronicle(root / "chronicle.jsonl")
    neighbours: dict = {}

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
           ["penuel", "sinai"], road=True)
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
        notebook=("The seams over the stern end are opening, and the rains are "
                  "not waiting. I want them closed over Beth El before the rains "
                  "come back.\n"
                  "Havvah: seven days under the hill and she never once asked "
                  "how. She is easy to be quiet with. Saw her yesterday.\n"
                  "Lilith: restless. Not unkind. Not seen her since the week "
                  "before last."),
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
        notebook=("Somebody was at the garden's edge again and I did not look "
                  "up. I want the new seedbed through one more season, and not "
                  "to be asked about the water.\n"
                  "Bezalel: he works too late. Good hands. Yesterday.\n"
                  "Lilith: young. Always about to go somewhere. Six days since."),
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
        notebook=("The road past Mizpah goes somewhere and nobody here has "
                  "asked where. One day I will walk it as far as it goes.\n"
                  "Havvah: she is kind and she will never leave this place. Six "
                  "days since I saw her.\n"
                  "Bezalel: he would rebuild this whole place plank by plank "
                  "and never ask why. Not since the week before last."),
        place="mizpah", home="sinai",
    )

    # Viewpoints are bare positions: descriptive phrasing gets copied verbatim
    # into what people write.
    world.at = DESCENT
    world.record("descent",
                         "The river came down. It came out of the sky onto the "
                         "ledge under Mizpah and it would have opened the ground, "
                         "except that it came down onto a man's head first and out "
                         "of his hair in seven streams. It ran on down the valley "
                         "across ash that had lain there longer than anybody could "
                         "say, and where it touched the ash there was nothing left "
                         "owing to them. It has run here ever since, and it is what "
                         "filled Marah.",
                         place="penuel", involved=[],
                         informed=["p_bezalel", "p_havvah", "p_lilith"],
                         data={"viewpoints": {
                             "p_bezalel": "down in the dry channel it came into, walking his cut stone out of it",
                             "p_havvah": "further down the valley, watching the dust go dark all at once",
                             "p_lilith": "up on Mizpah, nearest to where it came down, wet through",
                         }})
    world.at = CHURNING
    world.record("churning",
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
                         informed=["p_bezalel", "p_havvah", "p_lilith"],
                         data={"viewpoints": {
                             "p_bezalel": "on the bank, taking a turn on the snake when the near side was short-handed",
                             "p_havvah": "well back from the water, on the high side, out of the way of both crowds",
                             "p_lilith": "down at the edge of it, as close as she was let, watching the near side's feet",
                         }})
    world.at = DELUGE
    world.record("flood",
                         "The fish Havvah had kept since it was small - out of the "
                         "jar, out of the trough, out of the tank, and into Marah "
                         "when there was nowhere left to put it - came back and said "
                         "the water was coming, and it came before morning. It went "
                         "over the ring of stones, over the valley, over everything "
                         "anybody had built. The boat was tied to the fish's horn and "
                         "went aground on Mizpah, and the water did not go down for "
                         "three days.",
                         place="marah", involved=["p_havvah", "p_bezalel"],
                         informed=["p_bezalel", "p_havvah", "p_lilith"],
                         data={"viewpoints": {
                             "p_bezalel": "in the boat he had built, at the rope, with the horn in front of him",
                             "p_havvah": "in the stern of the boat, with the seed she had been told to bring",
                             "p_lilith": "on Mizpah, above all of it, watching the valley go under and then the boat come up to her",
                         }})
    world.at = LIFTING
    world.record("lifting",
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
                         informed=["p_bezalel", "p_lilith", "p_havvah"],
                         data={"viewpoints": {
                             "p_bezalel": "underneath it, one hand on a post he had driven that morning and did not need",
                             "p_lilith": "at the edge of it, out in the rain, looking up at the underside of the hill",
                             "p_havvah": "underneath it, with what she had got out of the beds in her skirt",
                         }})

    world.at = START_AT
    # The page they were written with is the first page they wrote.
    for being in world.beings.values():
        world.pages(being.id).append(Page(at=world.at, notebook=being.who.notebook))
    # Everything starts due; from here on every timer is set by its owner.
    world.town_wake_at = START_AT
    world.road_wake_at = START_AT
    for being in world.beings.values():
        being.when.wake_at = START_AT
    return world


def create(root, name: str = "Nod") -> World:
    configuration.write_default(root)
    world = build(root, name=name)
    world.read_through = len(world.chronicle)     # the backstory is not news
    world.last_tick_at = time.time()           # nothing is owed from before it began
    save(world)
    return world
