"""P1: the town moves on its own. All of it offline, against a scripted stub."""

import io
import contextlib
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import cli, schedule, schemas, seed, tick as tick_mod
from elsewhere.backends import Settings, register
from elsewhere.configuration import DEFAULTS, configure
from elsewhere.backends.stub import StubBackend
from elsewhere.world import chronicle, store
from elsewhere.world.memories import Memory

CALLS = ("perceive", "act", "speak", "recall", "reflect", "direct", "arrive")
STAY = {"because": "", "doing": "", "action": "stay", "target": "",
        "for_hours": 6.0, "settling": False}


def configuration():
    return {name: Settings(backend="stub", model="stub") for name in CALLS}


class TownTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"
        self.world = seed.build(self.root)
        self.stub = StubBackend({"act": STAY, "perceive": {"stuck": False}})
        register(self.stub)

    def tearDown(self):
        self.tmp.cleanup()

    def say(self, call, answer):
        self.stub.set(call, answer)

    def acts(self, **by_being):
        for pid, answer in by_being.items():
            self.stub.answers[f"act|{pid}"] = answer

    def calls_for(self, name):
        return [c for c in self.stub.calls if c.name == name]


class TestTime(TownTest):
    def test_a_step_is_as_long_as_the_next_thing_due(self):
        # There is no step size. Everyone answered "six hours" because that is
        # what the stub says; the clock moved six because of that and for no
        # other reason.
        tick_mod.tick(self.world, configuration())              # the opening step
        was = self.world.at
        report = tick_mod.tick(self.world, configuration())
        self.assertEqual(self.world.at, was + 6.0)
        self.assertEqual(report.hours, 6.0)

    def test_a_step_is_as_long_as_whoever_asked_for_the_least(self):
        tick_mod.tick(self.world, configuration())
        self.acts(p_eve={**STAY, "for_hours": 1.5})
        tick_mod.tick(self.world, configuration())              # Eve now wants 1.5h
        was = self.world.at
        report = tick_mod.tick(self.world, configuration())
        self.assertEqual(report.hours, 1.5)
        self.assertEqual(self.world.at, was + 1.5)
        # and only she was asked anything: the others said six and meant it
        asked = [c.about for c in self.calls_for("act")[-1:]]
        self.assertEqual(asked, ["p_eve"])

    def test_somebody_absorbed_is_not_woken_by_what_is_not_about_them(self):
        # Concordia's interrupt mask, with one bit. Without it every
        # conversation anywhere woke everybody in earshot, and nobody in this
        # town could concentrate on anything.
        tick_mod.tick(self.world, configuration())
        for pid in ("p_adam", "p_eve", "p_lilith"):
            self.world.beings[pid].where.place = "shelter"
        deep = self.world.beings["p_lilith"]
        deep.when.absorbed = True
        deep.when.wake_at = self.world.at + 100.0
        schedule.rouse(self.world, ["p_lilith"], about=["p_eve"])
        self.assertEqual(deep.when.wake_at, self.world.at + 100.0,
                         "it was not about her")
        schedule.rouse(self.world, ["p_lilith"], about=["p_lilith"])
        self.assertEqual(deep.when.wake_at, self.world.at,
                         "and a thing that happens to her is not maskable")

    def test_a_world_nobody_scheduled_stops_rather_than_inventing_an_hour(self):
        self.say("act", {"because": "", "action": "stay", "target": ""})
        self.say("direct", {"happens": False})
        self.say("arrive", {"comes": False})
        tick_mod.tick(self.world, configuration())              # everyone answers, nobody says when
        was = self.world.at
        report = tick_mod.tick(self.world, configuration())
        self.assertTrue(report.idle)
        self.assertEqual(self.world.at, was, "the engine does not pick an hour for them")

    def test_everyone_is_asked_once(self):
        tick_mod.tick(self.world, configuration())
        asked = sorted(c.about for c in self.calls_for("act"))
        self.assertEqual(asked, sorted(self.world.beings))

    def test_a_mind_that_gives_nothing_stays_put(self):
        self.acts(p_eve="I would rather not say")
        before = self.world.beings["p_eve"].where.place
        report = tick_mod.tick(self.world, configuration())
        self.assertEqual(self.world.beings["p_eve"].where.place, before)
        self.assertEqual(report.silent, 1)


class TestChoices(TownTest):
    def test_the_grammar_only_offers_what_is_there(self):
        tick_mod.tick(self.world, configuration())
        eve_call = next(c for c in self.calls_for("act") if c.about == "p_eve")
        options = eve_call.schema["properties"]["target"]["enum"]
        # Eve is at the garden: next to the shelter and the waterline, and alone.
        # Adam's Yard is in reach from The Garden because the way between
        # them is one entry now. It used to be two lists, and the garden's
        # copy had lost it - so Adam could walk to Eve and Eve could not walk
        # back, and nothing anywhere could have noticed.
        self.assertEqual(sorted(options),
                         ["", "Adam's Yard", "The Shelter", "The Waterline"])

    def test_going_somewhere(self):
        self.acts(p_eve={"because": "the seedbed can wait", "action": "go",
                         "target": "The Shelter"})
        report = tick_mod.tick(self.world, configuration())
        self.assertEqual(self.world.beings["p_eve"].where.place, "shelter")
        self.assertIn(("p_eve", "garden", "shelter"), report.moves)
        self.assertEqual(report.decisions["p_eve"].because, "the seedbed can wait")


class TestConversation(TownTest):
    def setUp(self):
        super().setUp()
        for pid in ("p_eve", "p_adam"):
            self.world.beings[pid].where.place = "yard"
        self.flood = Memory(id="mem9001", owner="p_eve", at=68 * 24, told=[68 * 24],
                           account="the water in the doorway before I could move anything",
                           means="", feeling="fear")
        self.world.memories("p_eve").add(self.flood)

    def test_something_said_is_something_someone_else_can_keep(self):
        self.acts(p_eve={"because": "he was on the roof that night",
                         "action": "talk", "target": "Adam"})
        self.say("speak", {"about": "1", "line": "You were up there. Could you feel it?"})
        self.stub.answers["perceive|p_adam"] = {
            "account": "she asked if I could feel it", "means": "", "feeling": "unease",
            "stuck": True}

        report = tick_mod.tick(self.world, configuration())

        self.assertEqual(len(report.talks), 1)
        talk = report.talks[0]
        self.assertEqual(talk.between, ("p_eve", "p_adam"))
        opening = talk.turns[0]
        event = self.world.chronicle.get(opening.event_id)
        self.assertIn("Could you feel it?", event.account)

        kept = self.world.memories("p_adam").about_event(event.id)
        self.assertEqual(len(kept), 1, "Adam kept his own version of it")
        self.assertEqual(kept[0].account, "she asked if I could feel it")
        self.assertEqual(self.world.memories("p_eve").about_event(event.id), [],
                         "the speaker is not asked to perceive her own sentence")

    def test_the_other_one_answers(self):
        # It used to be one line in one direction: somebody said a thing,
        # everybody kept their version, and nobody ever answered anybody.
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"})
        self.say("speak", {"about": "nothing in particular", "line": "Cold."})
        talk = tick_mod.tick(self.world, configuration()).talks[0]
        self.assertGreater(len(talk.turns), 1)
        self.assertEqual([t.speaker for t in talk.turns[:2]], ["p_eve", "p_adam"])
        # Adam answers what he kept of her line, not the line itself: each
        # turn is an event, and he was handed a version of it first.
        his = [c for c in self.calls_for("speak") if c.about == "p_adam"]
        self.assertTrue(his)

    def test_an_exchange_ends_when_somebody_has_nothing_to_say(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"})
        self.stub.answers["speak|p_eve"] = {"about": "nothing in particular",
                                            "line": "Cold."}
        self.stub.answers["speak|p_adam"] = {"line": ""}
        talk = tick_mod.tick(self.world, configuration()).talks[0]
        self.assertEqual(len(talk.turns), 1, "he had nothing; that is the end of it")

    def test_saying_it_keeps_it_in_reach(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"})
        self.say("speak", {"about": "1", "line": "That night."})
        tick_mod.tick(self.world, configuration())
        self.assertEqual(self.flood.recalls, 2, "she had the floor twice")
        self.assertEqual(self.flood.told[-1], self.world.at)

    def test_the_speaker_is_offered_what_they_can_reach(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"})
        self.say("speak", {"about": "nothing in particular", "line": "Cold."})
        tick_mod.tick(self.world, configuration())
        call = self.calls_for("speak")[0]
        self.assertIn("the water in the doorway", call.user)
        self.assertEqual(call.schema["properties"]["about"]["enum"],
                         ["nothing in particular", "1"])

    def test_you_cannot_talk_to_someone_who_just_left(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"},
                  p_adam={"because": "the roof", "action": "go",
                          "target": "The Shelter"})
        report = tick_mod.tick(self.world, configuration())
        self.assertEqual(report.talks, [])
        self.assertIn(("p_eve", "p_adam"), report.missed)
        self.assertIn("who had gone", self.world.beings["p_eve"].where.doing)

    def test_two_beings_reaching_for_each_other_have_one_conversation(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"},
                  p_adam={"because": "", "action": "talk", "target": "Eve"})
        self.say("speak", {"about": "nothing in particular", "line": "Evening."})
        report = tick_mod.tick(self.world, configuration())
        self.assertEqual(len(report.talks), 1)

    def test_meeting_is_written_into_both_ties(self):
        self.acts(p_eve={"because": "", "action": "talk", "target": "Adam"})
        self.say("speak", {"about": "nothing in particular", "line": "Evening."})
        tick_mod.tick(self.world, configuration())
        for a, b in (("p_adam", "p_eve"), ("p_eve", "p_adam")):
            self.assertEqual(self.world.beings[a].who.regards[b].last_seen_at,
                             self.world.at)


class TestStayingPut(TownTest):
    """What somebody is doing is theirs to say, not the engine's to enumerate."""

    def test_the_verbs_are_only_what_the_engine_can_resolve(self):
        # Move somebody, put two in a conversation, take one out of the world.
        # Anything else is staying put, and what that looks like is free text.
        self.assertEqual(set(schemas.ACTIONS), {"stay", "go", "talk"})
        self.assertNotIn("enum", schemas.ACT["properties"]["doing"])

    def test_staying_put_is_described_rather_than_categorised(self):
        self.stub.answers["act|p_eve"] = {
            "because": "nothing I could name",
            "doing": "sitting in the doorway with the seed trays, not sorting them",
            "action": "stay", "target": ""}
        tick_mod.tick(self.world, configuration())
        self.assertEqual(
            self.world.beings["p_eve"].where.doing,
            "sitting in the doorway with the seed trays, not sorting them")

    def test_a_mind_that_says_nothing_still_gets_a_plain_sentence(self):
        tick_mod.tick(self.world, configuration())      # the stub's doing is ""
        self.assertEqual(self.world.beings["p_eve"].where.doing,
                         "stayed where they were")


class TestCategories(unittest.TestCase):
    """The engine's categories are matched by string, and a typo is silent."""

    def test_a_conversation_is_recorded_under_the_name_the_engine_knows(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        world = seed.build(Path(tmp.name) / "world")
        for pid in ("p_adam", "p_eve"):
            world.beings[pid].where.place = "shelter"
        stub = StubBackend({"act": STAY, "perceive": {"stuck": False},
                            "direct": {"happens": False}, "reflect": {},
                            "arrive": {"comes": False},
                            "speak": {"about": "nothing in particular", "line": "Cold."}})
        stub.answers["act|p_adam"] = {"because": "", "action": "talk", "target": "Eve"}
        register(stub)
        tick_mod.tick(world, configuration())
        said = [e for e in world.chronicle.all() if e.category == chronicle.CONVERSATION]
        self.assertEqual(len(said), tick_mod.TURNS,
                         "one event per turn, and the stub always has a line")

    def test_the_three_kinds_account_for_everything_the_engine_writes(self):
        # The taxonomy is the point: the world acting on people, a being's
        # presence starting or stopping, and beings reaching each other. A
        # fifth category that belongs to none of them is a category nobody
        # has decided the meaning of yet.
        world_acts = {chronicle.OCCURRENCE}
        exchanges = {chronicle.CONVERSATION}
        self.assertEqual(
            world_acts | chronicle.PRESENCE_CHANGES | exchanges,
            chronicle.ENGINE_CATEGORIES)
        self.assertEqual(
            len(world_acts) + len(chronicle.PRESENCE_CHANGES) + len(exchanges),
            len(chronicle.ENGINE_CATEGORIES), "the three kinds do not overlap")

    def test_the_names_stay_the_shape_a_string_match_needs(self):
        for name in chronicle.ENGINE_CATEGORIES:
            self.assertEqual(name, name.lower())
            self.assertTrue(name.isalpha(), f"{name!r} is matched by string")


class TestOwedTime(unittest.TestCase):
    def test_what_is_owed_is_hours_and_not_steps(self):
        # A day here is a day there, which is the promise. How many steps that
        # comes to is the town's business and differs from day to day.
        self.assertEqual(tick_mod.owed_hours(None, 1e9), 0.0)
        self.assertEqual(tick_mod.owed_hours(0, 5.9 * 3600), 5.9)
        self.assertEqual(tick_mod.owed_hours(0, 25 * 3600), 25.0)
        self.assertEqual(tick_mod.owed_hours(100 * 3600, 0), 0.0)

    def test_a_capped_backlog_is_slept_through(self):
        self.assertEqual(
            tick_mod.settle_clock(0, 100 * 3600, lived=24.0, owed=96.0), 100 * 3600)

    def test_an_uncapped_backlog_keeps_its_remainder(self):
        self.assertEqual(
            tick_mod.settle_clock(0, 25 * 3600, lived=24.0, owed=24.0), 24 * 3600)


class TestContinue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"
        register(StubBackend({"act": STAY, "perceive": {"stuck": False}}))
        # Said in the world's own configuration, the way anyone would, so
        # nothing here can reach a real model.
        configure(self.root, "stub", "stub", calls=list(DEFAULTS))
        seed.create(self.root, remember=False)

    def tearDown(self):
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

    def test_the_first_continue_only_starts_the_clock(self):
        before = store.load(self.root)
        out = self.run_cli("continue")
        after = store.load(self.root)
        self.assertIn("clock started", out)
        self.assertEqual(after.at, before.at)

    def test_it_lives_what_is_owed(self):
        self.set_last_tick(13)
        before = store.load(self.root).at
        self.run_cli("continue")
        # At least the thirteen hours the wall clock says. It may be a little
        # more, because a step is however long the person who wanted waking
        # soonest asked for and the last one cannot be cut in half.
        lived = store.load(self.root).at - before
        self.assertGreaterEqual(lived, 13)
        self.assertLess(lived, 13 + 6)

    def test_it_never_lives_more_than_the_cap(self):
        self.set_last_tick(24 * 7)
        before = store.load(self.root).at
        out = self.run_cli("continue", "--max", "1")
        after = store.load(self.root)
        self.assertLess(after.at - before, 24, "one step, whatever it was worth")
        self.assertIn("slept through", out)
        self.assertLess(time.time() - after.last_tick_at, 60)

    def test_nothing_is_owed_until_the_world_has_something_due(self):
        # Everyone has said they will be six hours at what they are doing and
        # the wall clock has moved one: there is nothing to live, and saying
        # so is a heartbeat.
        self.run_cli("continue")                  # starts the clock
        self.set_last_tick(7)
        self.run_cli("continue")                  # lives up to the next thing due
        self.set_last_tick(1)
        out = self.run_cli("continue")
        self.assertIn("nothing is due", out)

    def test_a_running_tick_is_not_joined(self):
        self.set_last_tick(13)
        with store.tick_lock(self.root):
            out = self.run_cli("continue")
        self.assertIn("skipped", out)

    def test_news_is_what_you_have_not_seen(self):
        self.assertIn("Nothing has happened", self.run_cli("news"))

    def test_an_ended_world_stays_ended_and_readable(self):
        before = store.load(self.root)
        out = self.run_cli("end")
        self.assertIn("has ended", out)
        after = store.load(self.root)
        self.assertTrue(after.closed)
        self.assertEqual(after.at, before.at)
        self.assertEqual(len(after.chronicle), len(before.chronicle))
        # nothing more happens in it...
        for command in ("tick", "continue"):
            with self.assertRaises(SystemExit) as raised:
                self.run_cli(command)
            self.assertIn("has ended", str(raised.exception))
        # ...but what did happen can still be read.
        self.assertIn("(ended)", self.run_cli("status"))
        self.assertIn("had already ended", self.run_cli("end"))

    def test_a_running_tick_is_not_ended_underneath(self):
        with store.tick_lock(self.root):
            with self.assertRaises(SystemExit) as raised:
                self.run_cli("end")
        self.assertIn("Not now", str(raised.exception))
        self.assertFalse(store.load(self.root).closed)


if __name__ == "__main__":
    unittest.main()
