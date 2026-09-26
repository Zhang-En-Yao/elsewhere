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
from elsewhere.world.memories import Memory

CALLS = ("perceive", "act", "speak", "recall", "reflect", "direct", "arrive")
STAY = {"because": "", "doing": "", "action": "stay", "target": "",
        "for_hours": 6.0, "settling": False}
QUIET = {"why_now": "", "what": "", "where": "Beth El", "who": "",
         "reach": "the people there", "happens": False,
         "ask_again_in_hours": 24.0}


def configuration():
    return {n: Settings(backend="stub", model="stub") for n in CALLS}


class Town(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.world = seed.build(Path(self.tmp.name) / "world")
        self.stub = StubBackend({"act": STAY, "perceive": {"stuck": False},
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
            tick_mod.tick(self.world, configuration())
        self.assertEqual(len(self.calls("direct")), 1,
                         "asked on the first step, then not again inside the day")
        tick_mod.tick(self.world, configuration())
        self.assertEqual(len(self.calls("direct")), 2,
                         "a day on, it is worth asking again")

    def test_it_can_only_name_what_exists(self):
        tick_mod.tick(self.world, configuration())
        schema = self.calls("direct")[0].schema
        self.assertIn("Mizpah", schema["properties"]["where"]["enum"])
        self.assertEqual(schema["properties"]["who"]["enum"],
                         ["", "Bezalel", "Havvah", "Lilith"])

    def test_most_days_nothing_happens(self):
        before = len(self.world.chronicle)
        report = tick_mod.tick(self.world, configuration())
        self.assertIsNone(report.occurrence)
        self.assertEqual(len(self.world.chronicle), before)

    def test_something_happening_to_someone_happens_where_they_are(self):
        self.stub.set("direct", {"why_now": "the roof", "what": "A beam cracked overhead.",
                                 "where": "Mizpah", "who": "Bezalel",
                                 "reach": "the people there",                                  "happens": True})
        self.stub.answers["perceive|p_bezalel"] = {"account": "the crack before the dust",
                                                "means": "", "feeling": "fear",
                                                "stuck": True}
        report = tick_mod.tick(self.world, configuration())
        event = self.world.chronicle.get(report.occurrence.event_id)
        self.assertEqual(event.place, "yard", "Bezalel is in his own yard, not on the ridge")
        self.assertEqual(event.category, chronicle.OCCURRENCE)
        self.assertEqual([t.owner for t in report.occurrence.kept], ["p_bezalel"])

    def test_something_the_whole_town_notices_reaches_everyone(self):
        self.stub.set("direct", {"why_now": "", "what": "A storm broke over the town.",
                                 "where": "Beth El", "who": "",
                                 "reach": "the whole town",                                  "happens": True})
        report = tick_mod.tick(self.world, configuration())
        event = self.world.chronicle.get(report.occurrence.event_id)
        self.assertEqual(sorted(event.reached), sorted(self.world.beings))
        perceived = sorted(c.about for c in self.calls("perceive"))
        self.assertEqual(perceived, sorted(self.world.beings))
        lilith = next(c for c in self.calls("perceive") if c.about == "p_lilith")
        self.assertIn("word of it reached you", lilith.user)

    def test_the_town_says_itself_how_long_a_quiet_stretch_it_gets(self):
        # There used to be two constants here - asked about once a day, and
        # never inside two days of the last happening - and both were this
        # project deciding how eventful a town is. The town answers it.
        self.stub.set("direct", {"why_now": "", "what": "A goat got loose.",
                                 "where": "Beth El", "who": "",
                                 "reach": "the people there", "happens": True,
                                 "ask_again_in_hours": 336.0})
        tick_mod.tick(self.world, configuration())
        self.assertEqual(len(self.calls("direct")), 1)
        self.assertEqual(self.world.town_wake_at, self.world.at + 336.0)
        for _ in range(8):                       # two days further on
            tick_mod.tick(self.world, configuration())
        self.assertEqual(len(self.calls("direct")), 1,
                         "it said a fortnight, and a fortnight is what it gets")
        for name in ("DIRECTOR_MIN_GAP", "DIRECTOR_EVERY"):
            self.assertFalse(hasattr(agents, name))


class TestRecall(Town):
    def setUp(self):
        super().setUp()
        for pid in ("p_bezalel", "p_havvah"):
            self.world.beings[pid].where.place = "yard"
        self.flood = Memory(id="mem9001", owner="p_havvah", at=68 * 24, told=[68 * 24],
                           account="the water in the doorway before I could move anything",
                           feeling="fear")
        self.world.memories("p_havvah").add(self.flood)
        self.stub.answers["act|p_havvah"] = {"because": "", "action": "talk", "target": "Bezalel"}
        self.stub.set("speak", {"about": "1", "line": "That night."})

    def test_telling_it_changes_it(self):
        self.stub.set("recall", {"account": "water, and not being able to look away",
                                 "means": "", "feeling": "fear"})
        report = tick_mod.tick(self.world, configuration())
        self.assertEqual(self.flood.account, "water, and not being able to look away")
        self.assertEqual(self.flood.history,
                         ["the water in the doorway before I could move anything"])
        # She has the floor twice in one exchange, so she brings it up twice,
        # and both occasions are counted. A tally of "tellings" could not tell
        # those two apart from two a year apart; `told` can.
        self.assertEqual(self.flood.recalls, 2)
        self.assertIsNotNone(report.talks[0].turns[0].reshaped)

    def test_the_mind_is_told_how_old_and_how_often_and_not_how_clear(self):
        self.stub.set("recall", {"account": "", "means": "", "feeling": "none"})
        tick_mod.tick(self.world, configuration())
        user = self.calls("recall")[0].user
        self.assertIn("days old", user)
        self.assertIn("told", user)
        self.assertIn("the water in the doorway", user)
        # How hazy it is after all that is the mind's to judge, not a reach
        # value cut into three buckets at two numbers this project chose.
        for verdict in ("still clear", "hazy", "barely there"):
            self.assertNotIn(verdict, user)

    def test_the_one_sentence_shaped_like_the_answer_is_kept_out(self):
        # `thought` is a short first-person fragment and so is a rewritten
        # memory. With it in the prompt a small model hands it straight back.
        self.world.beings["p_havvah"].who.thought = "I did not look up"
        self.stub.set("recall", {"account": "", "means": "", "feeling": "none"})
        tick_mod.tick(self.world, configuration())
        user = self.calls("recall")[0].user
        self.assertNotIn("I did not look up", user)
        self.assertIn("the water in the doorway", user, "the memory is still there")

    def test_an_empty_or_identical_answer_leaves_it_alone(self):
        self.stub.set("recall", {"account": "the water in the doorway before I could move anything"})
        tick_mod.tick(self.world, configuration())
        self.assertEqual(self.flood.history, [])

    def test_small_talk_recalls_nothing(self):
        self.stub.set("speak", {"about": "nothing in particular", "line": "Cold."})
        tick_mod.tick(self.world, configuration())
        self.assertEqual(self.calls("recall"), [])


class TestReflect(Town):
    def setUp(self):
        super().setUp()
        self.today = Memory(id="mem9100", owner="p_lilith", at=self.world.at,
                           told=[self.world.at],
                           account="the valley disappearing under the water", feeling="unease")

    def reckoning(self):
        """Live the step in which this person stops for the day."""
        self.stub.answers["act|p_lilith"] = {**STAY, "settling": True}
        return tick_mod.tick(self.world, configuration())

    def test_only_whoever_is_stopping_goes_over_their_day(self):
        # Not everyone at nightfall, and not everyone a day on from their own
        # last one. Lilith said she was settling; the other two did not, and
        # the clock has no opinion about either of them.
        self.world.memories("p_lilith").add(self.today)
        self.world.memories("p_havvah").add(Memory(
            id="mem9110", owner="p_havvah", at=self.world.at, account="a long day", told=[self.world.at]))
        self.reckoning()
        self.assertEqual([c.about for c in self.calls("reflect")], ["p_lilith"])

    def test_and_only_if_the_day_left_them_something(self):
        self.reckoning()                          # nothing has happened to her
        self.assertEqual(self.calls("reflect"), [])

    def test_a_belief_remembers_where_it_came_from(self):
        self.world.memories("p_lilith").add(self.today)
        self.stub.set("reflect", {"thought": "nobody went down", "belief": "Nobody here will ever leave",
                                  "belief_from": "1", "belief_again": "",
                                  "want": "go before winter"})
        self.reckoning()
        lilith = self.world.beings["p_lilith"]
        belief = next(b for b in lilith.who.beliefs if "leave" in b.claim)
        self.assertEqual(belief.origin, ["mem9100"])
        self.assertEqual(lilith.who.wants[0], "go before winter")
        self.assertEqual(lilith.who.thought, "nobody went down")

    def test_the_same_belief_twice_is_held_harder_not_written_twice(self):
        self.world.memories("p_lilith").add(self.today)
        self.stub.set("reflect", {"belief": "Nobody here will ever leave",
                                  "belief_from": "1", "belief_again": ""})
        self.reckoning()

        # A day on, something new stays with her and she arrives at the same
        # place in different words. Whether that is the same belief is hers to
        # say: it comes back as `belief_again`, pointing at the one she already
        # holds. No word-overlap ratio would have got this - these two wordings
        # share no word longer than three letters.
        self.world.at += 1 * 24
        self.world.memories("p_lilith").add(Memory(
            id="mem9101", owner="p_lilith", at=self.world.at,
            account="the road again",
            told=[self.world.at]))
        self.stub.set("reflect", {"belief": "you die in the town you were born in",
                                  "belief_from": "1", "belief_again": "1"})
        self.reckoning()

        beliefs = [b for b in self.world.beings["p_lilith"].who.beliefs
                   if "leave" in b.claim.lower()]
        self.assertEqual(len(beliefs), 1)
        self.assertEqual(beliefs[0].claim, "Nobody here will ever leave",
                         "the first wording stays")
        self.assertEqual(len(beliefs[0].held), 2,
                         "held twice, which is the only thing that holds it")
        self.assertEqual(beliefs[0].origin, ["mem9100", "mem9101"])

    def test_what_they_thought_becomes_something_they_can_remember(self):
        # A thought used to live only on the being, as one sentence
        # overwritten at every reckoning, so it could never come back later,
        # never be worn down by not coming back, and never be said out loud.
        self.world.memories("p_lilith").add(self.today)
        self.stub.set("reflect", {"thought": "Nobody went down to look",
                                  "belief": "", "belief_again": ""})
        self.reckoning()
        thoughts = [t for t in self.world.memories("p_lilith")
                    if t.account == "Nobody went down to look"]
        self.assertEqual(len(thoughts), 1)
        self.assertEqual(thoughts[0].origin, ["mem9100"],
                         "and it remembers what it was a thought about")
        self.assertEqual(thoughts[0].told, [self.world.at])

    def test_what_they_did_is_something_to_go_over(self):
        # Until `lately` existed only what the world had done to somebody was
        # written down, so a week on a roof left nothing to reflect on.
        self.world.memories("p_lilith").add(self.today)
        self.world.beings["p_lilith"].where.now("walking the ridge path again")
        self.reckoning()
        user = self.calls("reflect")[0].user
        self.assertIn("What you have been doing", user)
        self.assertIn("walking the ridge path again", user)

    def test_how_one_person_holds_another_can_change(self):
        # `Regard.account` used to be written once by the seed and never
        # again, so two people could live a year side by side and neither
        # would change a word about the other.
        self.world.memories("p_lilith").add(self.today)
        before = self.world.beings["p_lilith"].who.regard("p_havvah").account
        self.stub.set("reflect", {"thought": "", "belief": "", "belief_again": "",
                                  "about_someone": "Havvah",
                                  "now_say": "She has not looked at me since the water."})
        self.reckoning()
        now = self.world.beings["p_lilith"].who.regard("p_havvah").account
        self.assertEqual(now, "She has not looked at me since the water.")
        self.assertNotEqual(now, before)
        # and only her own account moved; Havvah's of her is untouched
        self.assertNotEqual(self.world.beings["p_havvah"].who.regard("p_lilith").account, now)

    def test_only_somebody_who_exists_can_be_thought_about(self):
        self.world.memories("p_lilith").add(self.today)
        self.reckoning()
        schema = self.calls("reflect")[0].schema
        self.assertIn("Havvah", schema["properties"]["about_someone"]["enum"])
        self.assertIn("", schema["properties"]["about_someone"]["enum"])
        self.assertNotIn("Nobody", schema["properties"]["about_someone"]["enum"])

    def test_a_belief_can_outlive_its_reasons(self):
        self.world.memories("p_lilith").add(self.today)
        self.stub.set("reflect", {"belief": "Nobody here will ever leave",
                                  "belief_from": "1", "belief_again": ""})
        self.reckoning()
        lilith = self.world.beings["p_lilith"]
        # Years pass, nobody ever brings that day up again, and enough
        # ordinary days come after it that when she asks herself why she
        # believes this, other things come back instead.
        self.world.at += 400 * 24
        for i in range(retrieval.CONTEXT_MEMORIES):
            self.world.memories("p_lilith").add(Memory(
                id=f"mem92{i:02d}", owner="p_lilith", at=self.world.at,
                account="an ordinary day",
                told=[self.world.at]))
        belief = next(b for b in lilith.who.beliefs if "leave" in b.claim)
        self.assertTrue(retrieval.on_faith(belief, self.world.memories("p_lilith"),
                                           self.world.at))
        self.assertIn(belief, lilith.who.beliefs, "and she still holds it")


if __name__ == "__main__":
    unittest.main()
