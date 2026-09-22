"""P3/P4: things happen to the town, telling changes what is told, nights change what is held."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import agents, seed, tick as tick_mod
from elsewhere.backends import Settings, register
from elsewhere.backends.stub import StubBackend
from elsewhere.world.memories import Trace

CALLS = ("perceive", "act", "speak", "recall", "reflect", "direct", "arrive")
STAY = {"because": "", "action": "stay", "target": ""}
QUIET = {"why_now": "", "what": "", "where": "The Old Market", "who": "",
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

    def to_phase(self, name):
        """Put the clock one phase before `name`, so the next tick lands on it.
        (Landing on morning rolls the day over; advance_clock does that.)"""
        order = ["morning", "afternoon", "evening", "night"]
        self.world.phase = (order.index(name) - 1) % 4


class TestDirector(Town):
    def test_asked_once_a_day_in_the_morning(self):
        for _ in range(4):
            tick_mod.tick(self.world, config())
        self.assertEqual(len(self.calls("direct")), 1)
        # the seed starts at morning; the first tick is afternoon, so the one
        # call came at the next morning
        self.assertEqual(self.world.phase_name, "morning")

    def test_it_can_only_name_what_exists(self):
        self.to_phase("morning")
        tick_mod.tick(self.world, config())
        schema = self.calls("direct")[0].schema
        self.assertIn("The Hill Road", schema["properties"]["where"]["enum"])
        self.assertEqual(schema["properties"]["who"]["enum"],
                         ["", "Alice", "Bram", "Carol", "David"])

    def test_most_days_nothing_happens(self):
        self.to_phase("morning")
        before = len(self.world.chronicle)
        report = tick_mod.tick(self.world, config())
        self.assertIsNone(report.happening)
        self.assertEqual(len(self.world.chronicle), before)

    def test_something_happening_to_someone_happens_where_they_are(self):
        self.stub.set("direct", {"why_now": "the roof", "what": "A beam cracked overhead.",
                                 "where": "The Hill Road", "who": "Bram",
                                 "reach": "the people there", "tags": ["roof"],
                                 "happens": True})
        self.stub.answers["perceive|p_bram"] = {"trace": "the crack before the dust",
                                                "means": "", "feeling": "fear",
                                                "tags": ["roof"], "weight": "stays"}
        self.to_phase("morning")
        report = tick_mod.tick(self.world, config())
        event = self.world.chronicle.get(report.happening.event_id)
        self.assertEqual(event.where, "workshop", "Bram is in his workshop, not on the hill")
        self.assertEqual(event.kind, "happening")
        self.assertEqual([t.owner for t in report.happening.kept], ["p_bram"])

    def test_something_the_whole_town_notices_reaches_everyone(self):
        self.stub.set("direct", {"why_now": "", "what": "A storm broke over the town.",
                                 "where": "The Old Market", "who": "",
                                 "reach": "the whole town", "tags": ["storm"],
                                 "happens": True})
        self.to_phase("morning")
        report = tick_mod.tick(self.world, config())
        event = self.world.chronicle.get(report.happening.event_id)
        self.assertEqual(sorted(event.present), sorted(self.world.people))
        perceived = sorted(c.about for c in self.calls("perceive"))
        self.assertEqual(perceived, sorted(self.world.people))
        carol = next(c for c in self.calls("perceive") if c.about == "p_carol")
        self.assertIn("word of it reached you", carol.user)

    def test_the_town_gets_quiet_days_between_happenings(self):
        self.stub.set("direct", {"why_now": "", "what": "A goat got loose.",
                                 "where": "The Old Market", "who": "",
                                 "reach": "the people there", "tags": [], "happens": True})
        self.to_phase("morning")
        tick_mod.tick(self.world, config())
        for _ in range(4):                       # through to the next morning
            tick_mod.tick(self.world, config())
        self.assertEqual(len(self.calls("direct")), 1,
                         "the next morning is inside the quiet gap; nobody asks")


class TestRecall(Town):
    def setUp(self):
        super().setUp()
        for pid in ("p_alice", "p_bram"):
            self.world.people[pid].place = "workshop"
        self.fire = Trace(id="mem9001", owner="p_alice", day=68,
                          trace="the heat on my face from across the street",
                          feeling="fear", salience=0.95, tags=["fire"], last_touched=68)
        self.world.traces("p_alice").add(self.fire)
        self.stub.answers["act|p_alice"] = {"because": "", "action": "talk", "target": "Bram"}
        self.stub.set("speak", {"about": "1", "line": "That night."})

    def test_telling_it_changes_it(self):
        self.stub.set("recall", {"trace": "heat, and not being able to look away",
                                 "means": "", "feeling": "fear"})
        report = tick_mod.tick(self.world, config())
        self.assertEqual(self.fire.trace, "heat, and not being able to look away")
        self.assertEqual(self.fire.history, ["the heat on my face from across the street"])
        self.assertEqual(self.fire.recalls, 1, "one telling, counted once")
        self.assertIsNotNone(report.talks[0].reshaped)

    def test_the_mind_is_told_how_old_and_how_clear(self):
        self.stub.set("recall", {"trace": "", "means": "", "feeling": "none"})
        tick_mod.tick(self.world, config())
        user = self.calls("recall")[0].user
        self.assertIn("days old", user)
        self.assertIn("the heat on my face", user)

    def test_an_empty_or_identical_answer_leaves_it_alone(self):
        self.stub.set("recall", {"trace": "the heat on my face from across the street"})
        tick_mod.tick(self.world, config())
        self.assertEqual(self.fire.history, [])

    def test_small_talk_recalls_nothing(self):
        self.stub.set("speak", {"about": "nothing in particular", "line": "Cold."})
        tick_mod.tick(self.world, config())
        self.assertEqual(self.calls("recall"), [])


class TestReflect(Town):
    def setUp(self):
        super().setUp()
        self.today = Trace(id="mem9100", owner="p_carol", day=self.world.day,
                           trace="the glow over the roofs", feeling="unease",
                           salience=0.7, tags=["fire", "leaving"],
                           last_touched=self.world.day)

    def night(self):
        self.to_phase("night")
        return tick_mod.tick(self.world, config())

    def test_only_those_whose_day_left_something_lie_awake(self):
        self.world.traces("p_carol").add(self.today)
        self.night()
        self.assertEqual([c.about for c in self.calls("reflect")], ["p_carol"])

    def test_a_belief_remembers_where_it_came_from(self):
        self.world.traces("p_carol").add(self.today)
        self.stub.set("reflect", {"thought": "nobody went down", "belief": "Nobody here will ever leave",
                                  "belief_from": "1", "want": "go before winter", "mood": "restless"})
        self.night()
        carol = self.world.people["p_carol"]
        belief = next(b for b in carol.beliefs if "leave" in b.text)
        self.assertEqual(belief.origin, ["mem9100"])
        self.assertEqual(carol.wants[0], "go before winter")
        self.assertEqual(carol.mood, "restless")

    def test_the_same_belief_twice_is_held_harder_not_written_twice(self):
        self.world.traces("p_carol").add(self.today)
        self.stub.set("reflect", {"belief": "Nobody here will ever leave", "belief_from": "1"})
        self.night()

        # The next night, something new stays with her and she arrives at the
        # same place in different words.
        self.world.day += 1
        self.world.traces("p_carol").add(Trace(
            id="mem9101", owner="p_carol", day=self.world.day, trace="the road again",
            salience=0.4, tags=["leaving"], last_touched=self.world.day))
        self.stub.set("reflect", {"belief": "nobody here will ever leave this town",
                                  "belief_from": "1"})
        self.night()

        beliefs = [b for b in self.world.people["p_carol"].beliefs
                   if "leave" in b.text.lower()]
        self.assertEqual(len(beliefs), 1)
        self.assertEqual(beliefs[0].text, "Nobody here will ever leave", "the first wording stays")
        self.assertGreater(beliefs[0].confidence, 0.5)
        self.assertEqual(beliefs[0].origin, ["mem9100", "mem9101"])

    def test_a_belief_can_outlive_its_reasons(self):
        self.world.traces("p_carol").add(self.today)
        self.stub.set("reflect", {"belief": "Nobody here will ever leave", "belief_from": "1"})
        self.night()
        carol = self.world.people["p_carol"]
        self.today.salience = 0.15            # it did not, in the end, weigh much
        self.world.day += 400
        agents.refresh_origins(self.world, carol)
        belief = next(b for b in carol.beliefs if "leave" in b.text)
        self.assertTrue(belief.origin_lost)
        self.assertIn(belief, carol.beliefs, "and she still holds it")


if __name__ == "__main__":
    unittest.main()
