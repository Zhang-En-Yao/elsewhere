"""P3/P4: things happen to the town, telling changes what is told, nights change what is held."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import agents, retrieval, seed, tick as tick_mod
from elsewhere.backends import Settings, register
from elsewhere.backends.stub import StubBackend
from elsewhere.world import chronicle
from elsewhere.world.memories import Trace

CALLS = ("perceive", "act", "speak", "recall", "reflect", "direct", "arrive")
STAY = {"because": "", "doing": "", "action": "stay", "target": ""}
QUIET = {"why_now": "", "what": "", "where": "The Shelter", "who": "",
         "reach": "the people there", "tags": [], "happens": False}


def config():
    return {n: Settings(backend="stub", model="stub") for n in CALLS}


class Town(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.world = seed.build(Path(self.tmp.name) / "world")
        self.stub = StubBackend({"act": STAY, "perceive": {"weight": "nothing"},
                                 "direct": QUIET, "reflect": {}})
        register(self.stub)

    def tearDown(self):
        self.tmp.cleanup()

    def calls(self, name):
        return [c for c in self.stub.calls if c.name == name]

    def a_day_on(self):
        """Move the clock far enough that the once-a-day rates come round again."""
        self.world.at += 24


class TestDirector(Town):
    def test_asked_about_once_a_day_whatever_the_hour(self):
        for _ in range(4):                       # four steps: a whole day
            tick_mod.tick(self.world, config())
        self.assertEqual(len(self.calls("direct")), 1,
                         "asked on the first step, then not again inside the day")
        tick_mod.tick(self.world, config())
        self.assertEqual(len(self.calls("direct")), 2,
                         "a day on, it is worth asking again")

    def test_it_can_only_name_what_exists(self):
        tick_mod.tick(self.world, config())
        schema = self.calls("direct")[0].schema
        self.assertIn("The Ridge Path", schema["properties"]["where"]["enum"])
        self.assertEqual(schema["properties"]["who"]["enum"],
                         ["", "Adam", "Eve", "Lilith"])

    def test_most_days_nothing_happens(self):
        before = len(self.world.chronicle)
        report = tick_mod.tick(self.world, config())
        self.assertIsNone(report.occurrence)
        self.assertEqual(len(self.world.chronicle), before)

    def test_something_happening_to_someone_happens_where_they_are(self):
        self.stub.set("direct", {"why_now": "the roof", "what": "A beam cracked overhead.",
                                 "where": "The Ridge Path", "who": "Adam",
                                 "reach": "the people there", "tags": ["roof"],
                                 "happens": True})
        self.stub.answers["perceive|p_adam"] = {"trace": "the crack before the dust",
                                                "means": "", "feeling": "fear",
                                                "tags": ["roof"], "weight": "stays"}
        report = tick_mod.tick(self.world, config())
        event = self.world.chronicle.get(report.occurrence.event_id)
        self.assertEqual(event.place, "yard", "Adam is in his own yard, not on the ridge")
        self.assertEqual(event.category, chronicle.OCCURRENCE)
        self.assertEqual([t.owner for t in report.occurrence.kept], ["p_adam"])

    def test_something_the_whole_town_notices_reaches_everyone(self):
        self.stub.set("direct", {"why_now": "", "what": "A storm broke over the town.",
                                 "where": "The Shelter", "who": "",
                                 "reach": "the whole town", "tags": ["storm"],
                                 "happens": True})
        report = tick_mod.tick(self.world, config())
        event = self.world.chronicle.get(report.occurrence.event_id)
        self.assertEqual(sorted(event.reached), sorted(self.world.beings))
        perceived = sorted(c.about for c in self.calls("perceive"))
        self.assertEqual(perceived, sorted(self.world.beings))
        lilith = next(c for c in self.calls("perceive") if c.about == "p_lilith")
        self.assertIn("word of it reached you", lilith.user)

    def test_the_town_gets_quiet_days_between_happenings(self):
        self.stub.set("direct", {"why_now": "", "what": "A goat got loose.",
                                 "where": "The Shelter", "who": "",
                                 "reach": "the people there", "tags": [], "happens": True})
        tick_mod.tick(self.world, config())
        for _ in range(4):                       # a whole day further on
            tick_mod.tick(self.world, config())
        self.assertEqual(len(self.calls("direct")), 1,
                         "the next day is still inside the quiet gap; nobody asks")


class TestRecall(Town):
    def setUp(self):
        super().setUp()
        for pid in ("p_adam", "p_eve"):
            self.world.beings[pid].place = "yard"
        self.flood = Trace(id="mem9001", owner="p_eve", at=68 * 24,
                           trace="the water in the doorway before I could move anything",
                           feeling="fear", salience=0.95, tags=["flood"], touched_at=68 * 24)
        self.world.traces("p_eve").add(self.flood)
        self.stub.answers["act|p_eve"] = {"because": "", "action": "talk", "target": "Adam"}
        self.stub.set("speak", {"about": "1", "line": "That night."})

    def test_telling_it_changes_it(self):
        self.stub.set("recall", {"trace": "water, and not being able to look away",
                                 "means": "", "feeling": "fear"})
        report = tick_mod.tick(self.world, config())
        self.assertEqual(self.flood.trace, "water, and not being able to look away")
        self.assertEqual(self.flood.history,
                         ["the water in the doorway before I could move anything"])
        self.assertEqual(self.flood.recalls, 1, "one telling, counted once")
        self.assertIsNotNone(report.talks[0].reshaped)

    def test_the_mind_is_told_how_old_and_how_clear(self):
        self.stub.set("recall", {"trace": "", "means": "", "feeling": "none"})
        tick_mod.tick(self.world, config())
        user = self.calls("recall")[0].user
        self.assertIn("days old", user)
        self.assertIn("the water in the doorway", user)

    def test_an_empty_or_identical_answer_leaves_it_alone(self):
        self.stub.set("recall", {"trace": "the water in the doorway before I could move anything"})
        tick_mod.tick(self.world, config())
        self.assertEqual(self.flood.history, [])

    def test_small_talk_recalls_nothing(self):
        self.stub.set("speak", {"about": "nothing in particular", "line": "Cold."})
        tick_mod.tick(self.world, config())
        self.assertEqual(self.calls("recall"), [])


class TestReflect(Town):
    def setUp(self):
        super().setUp()
        self.today = Trace(id="mem9100", owner="p_lilith", at=self.world.at,
                           trace="the valley disappearing under the water", feeling="unease",
                           salience=0.7, tags=["flood", "leaving"],
                           touched_at=self.world.at)

    def reckoning(self):
        """Live the step in which this person's own day comes round."""
        return tick_mod.tick(self.world, config())

    def test_only_those_whose_day_left_something_go_over_it(self):
        self.world.traces("p_lilith").add(self.today)
        self.reckoning()
        self.assertEqual([c.about for c in self.calls("reflect")], ["p_lilith"])

    def test_a_belief_remembers_where_it_came_from(self):
        self.world.traces("p_lilith").add(self.today)
        self.stub.set("reflect", {"thought": "nobody went down", "belief": "Nobody here will ever leave",
                                  "belief_from": "1", "want": "go before winter", "mood": "restless"})
        self.reckoning()
        lilith = self.world.beings["p_lilith"]
        belief = next(b for b in lilith.beliefs if "leave" in b.belief)
        self.assertEqual(belief.origin, ["mem9100"])
        self.assertEqual(lilith.wants[0], "go before winter")
        self.assertEqual(lilith.mood, "restless")

    def test_the_same_belief_twice_is_held_harder_not_written_twice(self):
        self.world.traces("p_lilith").add(self.today)
        self.stub.set("reflect", {"belief": "Nobody here will ever leave", "belief_from": "1"})
        self.reckoning()

        # A day on, something new stays with her and she arrives at the same
        # place in different words.
        self.world.at += 1 * 24
        self.world.traces("p_lilith").add(Trace(
            id="mem9101", owner="p_lilith", at=self.world.at, trace="the road again",
            salience=0.4, tags=["leaving"], touched_at=self.world.at))
        self.stub.set("reflect", {"belief": "nobody here will ever leave this town",
                                  "belief_from": "1"})
        self.reckoning()

        beliefs = [b for b in self.world.beings["p_lilith"].beliefs
                   if "leave" in b.belief.lower()]
        self.assertEqual(len(beliefs), 1)
        self.assertEqual(beliefs[0].belief, "Nobody here will ever leave", "the first wording stays")
        self.assertGreater(beliefs[0].confidence, 0.5)
        self.assertEqual(beliefs[0].origin, ["mem9100", "mem9101"])

    def test_a_belief_can_outlive_its_reasons(self):
        self.world.traces("p_lilith").add(self.today)
        self.stub.set("reflect", {"belief": "Nobody here will ever leave", "belief_from": "1"})
        self.reckoning()
        lilith = self.world.beings["p_lilith"]
        self.today.salience = 0.15            # it did not, in the end, weigh much
        self.world.at += 400 * 24
        belief = next(b for b in lilith.beliefs if "leave" in b.belief)
        self.assertTrue(retrieval.on_faith(belief, self.world.traces("p_lilith"),
                                           self.world.at))
        self.assertIn(belief, lilith.beliefs, "and she still holds it")


if __name__ == "__main__":
    unittest.main()
