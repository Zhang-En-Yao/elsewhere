"""P1: the town moves on its own. All of it offline, against a scripted stub."""

import io
import contextlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import cli, seed, tick as tick_mod
from elsewhere.backends import Settings, register
from elsewhere.backends.stub import StubBackend
from elsewhere.world import store
from elsewhere.world.memories import Trace

CALLS = ("perceive", "act", "speak", "recall", "reflect", "direct", "arrive")
STAY = {"because": "", "action": "stay", "target": ""}


def config():
    return {name: Settings(backend="stub", model="stub") for name in CALLS}


class TownTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"
        self.world = seed.build(self.root)
        self.stub = StubBackend({"act": STAY, "perceive": {"weight": "nothing"}})
        register(self.stub)

    def tearDown(self):
        self.tmp.cleanup()

    def say(self, call, answer):
        self.stub.set(call, answer)

    def acts(self, **by_person):
        for pid, answer in by_person.items():
            self.stub.answers[f"act|{pid}"] = answer

    def calls_for(self, name):
        return [c for c in self.stub.calls if c.name == name]


class TestTime(TownTest):
    def test_a_tick_is_one_phase(self):
        day, phase = self.world.day, self.world.phase
        tick_mod.tick(self.world, config())
        self.assertEqual((self.world.day, self.world.phase), (day, phase + 1))

    def test_everyone_is_asked_once(self):
        tick_mod.tick(self.world, config())
        asked = sorted(c.about for c in self.calls_for("act"))
        self.assertEqual(asked, sorted(self.world.people))

    def test_a_mind_that_gives_nothing_stays_put(self):
        self.acts(p_eve="I would rather not say")
        before = self.world.people["p_eve"].place
        report = tick_mod.tick(self.world, config())
        self.assertEqual(self.world.people["p_eve"].place, before)
        self.assertEqual(report.silent, 1)


class TestChoices(TownTest):
    def test_the_grammar_only_offers_what_is_there(self):
        tick_mod.tick(self.world, config())
        eve_call = next(c for c in self.calls_for("act") if c.about == "p_eve")
        options = eve_call.schema["properties"]["target"]["enum"]
        # Eve is at the garden: next to the shelter and the waterline, and alone.
        self.assertEqual(sorted(options), ["", "The Shelter", "The Waterline"])

    def test_going_somewhere(self):
        self.acts(p_eve={"because": "the seedbed can wait", "action": "go",
                         "target": "The Shelter"})
        report = tick_mod.tick(self.world, config())
        self.assertEqual(self.world.people["p_eve"].place, "shelter")
        self.assertIn(("p_eve", "garden", "shelter"), report.moves)
        self.assertEqual(report.decisions["p_eve"].because, "the seedbed can wait")


class TestConversation(TownTest):
    def setUp(self):
        super().setUp()
        for pid in ("p_eve", "p_adam"):
            self.world.people[pid].place = "yard"
        self.flood = Trace(id="mem9001", owner="p_eve", day=68,
                           trace="the water in the doorway before I could move anything",
                           means="", feeling="fear", salience=0.95,
                           tags=["flood", "waterline"], last_touched=68)
        self.world.traces("p_eve").add(self.flood)

    def test_something_said_is_something_someone_else_can_keep(self):
        self.acts(p_eve={"because": "he was on the roof that night",
                         "action": "talk", "target": "Adam"})
        self.say("speak", {"about": "1", "line": "You were up there. Could you feel it?"})
        self.stub.answers["perceive|p_adam"] = {
            "trace": "she asked if I could feel it", "means": "", "feeling": "unease",
            "tags": ["flood"], "weight": "ordinary"}

        report = tick_mod.tick(self.world, config())

        self.assertEqual(len(report.talks), 1)
        talk = report.talks[0]
        self.assertEqual((talk.speaker, talk.listener), ("p_eve", "p_adam"))
        event = self.world.chronicle.get(talk.event_id)
        self.assertIn("Could you feel it?", event.what)

        kept = self.world.traces("p_adam").about_event(event.id)
        self.assertEqual(len(kept), 1, "Adam kept his own version of it")
        self.assertEqual(kept[0].trace, "she asked if I could feel it")
        self.assertEqual(self.world.traces("p_eve").about_event(event.id), [],
                         "the speaker is not asked to perceive her own sentence")

    def test_saying_it_keeps_it_in_reach(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"})
        self.say("speak", {"about": "1", "line": "That night."})
        tick_mod.tick(self.world, config())
        self.assertEqual(self.flood.recalls, 1)
        self.assertEqual(self.flood.last_touched, self.world.day)

    def test_the_speaker_is_offered_what_they_can_reach(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"})
        self.say("speak", {"about": "nothing in particular", "line": "Cold."})
        tick_mod.tick(self.world, config())
        call = self.calls_for("speak")[0]
        self.assertIn("the water in the doorway", call.user)
        self.assertEqual(call.schema["properties"]["about"]["enum"],
                         ["nothing in particular", "1"])

    def test_you_cannot_talk_to_someone_who_just_left(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"},
                  p_adam={"because": "the roof", "action": "go",
                          "target": "The Shelter"})
        report = tick_mod.tick(self.world, config())
        self.assertEqual(report.talks, [])
        self.assertIn(("p_eve", "p_adam"), report.missed)
        self.assertIn("who had gone", self.world.people["p_eve"].last_action)

    def test_two_people_reaching_for_each_other_have_one_conversation(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"},
                  p_adam={"because": "", "action": "talk", "target": "Eve"})
        self.say("speak", {"about": "nothing in particular", "line": "Evening."})
        report = tick_mod.tick(self.world, config())
        self.assertEqual(len(report.talks), 1)

    def test_meeting_is_written_into_both_ties(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"})
        self.say("speak", {"about": "nothing in particular", "line": "Evening."})
        before = self.world.people["p_adam"].ties["p_eve"].closeness
        tick_mod.tick(self.world, config())
        tie = self.world.people["p_adam"].ties["p_eve"]
        self.assertEqual(tie.last_seen_day, self.world.day)
        self.assertGreater(tie.closeness, before)


class TestOwedTime(unittest.TestCase):
    def test_owed_phases(self):
        self.assertEqual(tick_mod.owed_phases(None, 1e9), 0)
        self.assertEqual(tick_mod.owed_phases(0, 5.9 * 3600), 0)
        self.assertEqual(tick_mod.owed_phases(0, 25 * 3600), 4)

    def test_a_capped_backlog_is_slept_through(self):
        self.assertEqual(tick_mod.settle_clock(0, 100 * 3600, ran=4, owed=16), 100 * 3600)

    def test_an_uncapped_backlog_keeps_its_remainder(self):
        self.assertEqual(tick_mod.settle_clock(0, 25 * 3600, ran=4, owed=4), 24 * 3600)


class TestCatchup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"
        self.env = os.environ.get("ELSEWHERE_BACKEND")
        os.environ["ELSEWHERE_BACKEND"] = "stub"
        register(StubBackend({"act": STAY, "perceive": {"weight": "nothing"}}))
        seed.create(self.root, remember=False)

    def tearDown(self):
        if self.env is None:
            os.environ.pop("ELSEWHERE_BACKEND", None)
        else:
            os.environ["ELSEWHERE_BACKEND"] = self.env
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--world", str(self.root), *argv])
        return out.getvalue()

    def set_last_tick(self, hours_ago):
        world = store.load(self.root)
        world.last_tick_at = time.time() - hours_ago * 3600
        store.save(world)

    def test_the_first_catchup_only_starts_the_clock(self):
        before = store.load(self.root)
        out = self.run_cli("catchup")
        after = store.load(self.root)
        self.assertIn("clock started", out)
        self.assertEqual((after.day, after.phase), (before.day, before.phase))

    def test_it_lives_what_is_owed(self):
        self.set_last_tick(13)
        before = store.load(self.root).phase
        self.run_cli("catchup")
        self.assertEqual(store.load(self.root).phase, before + 2)

    def test_it_never_lives_more_than_the_cap(self):
        self.set_last_tick(24 * 7)
        before = store.load(self.root).phase
        out = self.run_cli("catchup", "--max", "1")
        after = store.load(self.root)
        self.assertEqual(after.phase, before + 1)
        self.assertIn("slept through", out)
        self.assertLess(time.time() - after.last_tick_at, 60)

    def test_a_running_tick_is_not_joined(self):
        self.set_last_tick(13)
        with store.tick_lock(self.root):
            out = self.run_cli("catchup")
        self.assertIn("skipped", out)

    def test_news_is_what_you_have_not_seen(self):
        self.assertIn("Nothing has happened", self.run_cli("news"))


if __name__ == "__main__":
    unittest.main()
