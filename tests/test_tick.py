"""The town moving on its own, offline against a scripted stub."""

import io
import contextlib
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import agents, cli, schedule, schemas, seed, tick
from elsewhere.schemas import CallName
from elsewhere.backends import Settings, register
from elsewhere.configuration import DEFAULTS, configure
from elsewhere.backends.stub import StubBackend
from elsewhere.world import chronicle, store

CALLS = tuple(CallName)[:-1]    # every call but the probe
STAY = {"because": "", "doing": "", "action": "", "target": "",
        "again_in_hours": 6.0, "settling": False}


def configuration():
    return {name: Settings(backend="stub", model="stub") for name in CALLS}


class TownTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "world"
        self.world = seed.build(self.root)
        self.stub = StubBackend({CallName.ACT: STAY})
        register(self.stub)

    def tearDown(self):
        self.temporary.cleanup()

    def say(self, call, answer):
        self.stub.set(call, answer)

    def acts(self, **by_being):
        for pid, answer in by_being.items():
            self.stub.answers[f"act|{pid}"] = answer

    def calls_for(self, name):
        return [call for call in self.stub.calls if call.name == name]


class TestTime(TownTest):
    def test_a_step_is_as_long_as_the_next_thing_due(self):
        tick.tick(self.world, configuration())              # the opening step
        was = self.world.at
        report = tick.tick(self.world, configuration())
        self.assertEqual(self.world.at, was + 6.0)
        self.assertEqual(report.hours, 6.0)

    def test_a_step_is_as_long_as_whoever_asked_for_the_least(self):
        tick.tick(self.world, configuration())
        self.acts(havvah={**STAY, "again_in_hours": 1.5})
        tick.tick(self.world, configuration())              # Havvah now wants 1.5h
        was = self.world.at
        report = tick.tick(self.world, configuration())
        self.assertEqual(report.hours, 1.5)
        self.assertEqual(self.world.at, was + 1.5)
        # and only she was asked
        asked = [call.about for call in self.calls_for(CallName.ACT)[-1:]]
        self.assertEqual(asked, ["havvah"])

    def test_somebody_absorbed_is_not_woken_by_what_is_not_about_them(self):
        tick.tick(self.world, configuration())
        for pid in ("bezalel", "havvah", "lilith"):
            self.world.beings[pid].where.place = "bethel"
        deep = self.world.beings["lilith"]
        deep.when.absorbed = True
        deep.when.wake_at = self.world.at + 100.0
        schedule.rouse(self.world, ["lilith"], about=["havvah"])
        self.assertEqual(deep.when.wake_at, self.world.at + 100.0,
                         "it was not about her")
        schedule.rouse(self.world, ["lilith"], about=["lilith"])
        self.assertEqual(deep.when.wake_at, self.world.at,
                         "and a thing that happens to her is not maskable")

    def test_a_world_nobody_scheduled_stops_rather_than_inventing_an_hour(self):
        self.say(CallName.ACT, {"because": "", "action": "", "target": ""})
        self.say(CallName.STIR, {"happens": False})
        self.say(CallName.ARRIVE, {"happens": False})
        tick.tick(self.world, configuration())              # everyone answers, nobody says when
        was = self.world.at
        report = tick.tick(self.world, configuration())
        self.assertTrue(report.idle)
        self.assertEqual(self.world.at, was, "the engine does not pick an hour for them")

    def test_everyone_is_asked_once(self):
        tick.tick(self.world, configuration())
        asked = sorted(call.about for call in self.calls_for(CallName.ACT))
        self.assertEqual(asked, sorted(self.world.beings))

    def test_a_mind_that_gives_nothing_stays_put(self):
        self.acts(havvah="I would rather not say")
        before = self.world.beings["havvah"].where.place
        report = tick.tick(self.world, configuration())
        self.assertEqual(self.world.beings["havvah"].where.place, before)
        self.assertEqual(report.unanswered, 1)


class TestChoices(TownTest):
    def test_the_grammar_only_offers_what_is_there(self):
        tick.tick(self.world, configuration())
        havvah_call = next(call for call in self.calls_for(CallName.ACT) if call.about == "havvah")
        options = havvah_call.schema["properties"]["target"]["enum"]
        # Havvah is alone at the garden, next to Beth El, Marah and the Boatyard.
        self.assertEqual(sorted(options),
                         ["", "Beth El", "Marah", "The Boatyard"])

    def test_going_somewhere(self):
        self.acts(havvah={"because": "the seedbed can wait", "action": "move",
                         "target": "Beth El"})
        report = tick.tick(self.world, configuration())
        self.assertEqual(self.world.beings["havvah"].where.place, "bethel")
        self.assertIn(("havvah", "garden", "bethel"), report.moves)
        self.assertEqual(report.decisions["havvah"].because, "the seedbed can wait")


class TestConversation(TownTest):
    def setUp(self):
        super().setUp()
        for pid in ("havvah", "bezalel"):
            self.world.beings[pid].where.place = "yard"

    def test_something_said_reaches_whoever_is_there(self):
        self.world.beings["lilith"].where.place = "yard"
        self.acts(havvah={"because": "he was on the roof that night",
                         "action": "talk", "target": "Bezalel"})
        self.say(CallName.SPEAK, {"utterance": "You were up there. Could you feel it?"})
        self.stub.answers["speak|bezalel"] = {"noted": "she asked if I could feel it",
                                                "utterance": "Feel what?"}

        report = tick.tick(self.world, configuration())

        self.assertEqual(len(report.talks), 1)
        talk = report.talks[0]
        self.assertEqual(talk.between, ("havvah", "bezalel"))
        event = self.world.chronicle.get(talk.turns[0].event_id)
        self.assertIn("Could you feel it?", event.account)
        self.assertEqual(sorted(event.informed), ["bezalel", "havvah", "lilith"])
        kept = self.world.notes("bezalel").about(event.id)
        self.assertEqual([note.account for note in kept], ["she asked if I could feel it"],
                         "he kept his own version of it, in the answer he gave")
        stood = dict((event.id, where) for event, where in agents.unseen(
            self.world, self.world.beings["lilith"]))
        self.assertIn("within earshot", stood[event.id],
                      "and she overheard it, and will see it when she looks up")

    def test_the_other_one_answers(self):
        self.acts(havvah={"because": "", "action": "talk", "target": "Bezalel"})
        self.say(CallName.SPEAK, {"utterance": "You were up there. Could you feel it?"})
        talk = tick.tick(self.world, configuration()).talks[0]
        self.assertGreater(len(talk.turns), 1)
        self.assertEqual([turn.speaker for turn in talk.turns[:2]], ["havvah", "bezalel"])
        # Each turn is an event, so Bezalel is answering what she said.
        his = [call for call in self.calls_for(CallName.SPEAK) if call.about == "bezalel"]
        self.assertIn("Could you feel it?", his[0].user)

    def test_an_exchange_ends_when_somebody_has_nothing_to_say(self):
        self.acts(havvah={"because": "", "action": "talk", "target": "Bezalel"})
        self.stub.answers["speak|havvah"] = {"utterance": "Cold."}
        self.stub.answers["speak|bezalel"] = {"utterance": ""}
        talk = tick.tick(self.world, configuration()).talks[0]
        self.assertEqual(len(talk.turns), 1, "he had nothing; that is the end of it")

    def test_the_speaker_brings_what_they_carry(self):
        self.acts(havvah={"because": "", "action": "talk", "target": "Bezalel"})
        self.say(CallName.SPEAK, {"utterance": "Cold."})
        tick.tick(self.world, configuration())
        call = self.calls_for(CallName.SPEAK)[0]
        self.assertIn(self.world.beings["havvah"].who.notebook, call.user)
        self.assertNotIn(self.world.beings["bezalel"].who.notebook, call.user,
                         "and not what the other one carries")

    def test_you_cannot_talk_to_someone_who_just_left(self):
        self.acts(havvah={"because": "", "action": "talk", "target": "Bezalel"},
                  bezalel={"because": "the roof", "action": "move",
                          "target": "Beth El"})
        report = tick.tick(self.world, configuration())
        self.assertEqual(report.talks, [])
        self.assertIn(("havvah", "bezalel"), report.missed)
        self.assertIn("who had gone", self.world.beings["havvah"].where.doing)

    def test_two_beings_reaching_for_each_other_have_one_conversation(self):
        self.acts(havvah={"because": "", "action": "talk", "target": "Bezalel"},
                  bezalel={"because": "", "action": "talk", "target": "Havvah"})
        self.say(CallName.SPEAK, {"utterance": "Evening."})
        report = tick.tick(self.world, configuration())
        self.assertEqual(len(report.talks), 1)


class TestStayingPut(TownTest):

    def test_the_verbs_are_only_what_the_engine_can_resolve(self):
        self.assertEqual(set(schemas.ALWAYS_OFFERED), {"move", "talk"})
        offered = schemas.act_grammar([], [])["properties"]["action"]["enum"]
        self.assertEqual(offered, ["", "move", "talk"],
                         "there is no verb for doing nothing; that is an empty action")
        self.assertNotIn("enum", schemas.ACT["properties"]["doing"])

    def test_staying_put_is_described_rather_than_categorised(self):
        self.stub.answers["act|havvah"] = {
            "because": "nothing I could name",
            "doing": "sitting in the doorway with the seed trays, not sorting them",
            "action": "", "target": ""}
        tick.tick(self.world, configuration())
        self.assertEqual(
            self.world.beings["havvah"].where.doing,
            "sitting in the doorway with the seed trays, not sorting them")

    def test_a_mind_that_says_nothing_still_gets_a_plain_sentence(self):
        tick.tick(self.world, configuration())      # the stub's doing is ""
        self.assertEqual(self.world.beings["havvah"].where.doing,
                         "stayed where they were")


class TestCategories(unittest.TestCase):
    """Categories are matched by string, so a typo fails silently."""

    def test_a_conversation_is_recorded_under_the_name_the_engine_knows(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        world = seed.build(Path(temporary.name) / "world")
        for pid in ("bezalel", "havvah"):
            world.beings[pid].where.place = "bethel"
        stub = StubBackend({CallName.ACT: STAY,
                            CallName.STIR: {"happens": False},
                            CallName.ARRIVE: {"happens": False},
                            CallName.SPEAK: {"utterance": "Cold."}})
        stub.answers["act|bezalel"] = {"because": "", "action": "talk", "target": "Havvah"}
        register(stub)
        tick.tick(world, configuration())
        said = [event for event in world.chronicle.all() if event.category == chronicle.CONVERSATION]
        self.assertEqual(len(said), tick.TURNS,
                         "one event per turn, and the stub always has a line")

    def test_the_three_kinds_account_for_everything_the_engine_writes(self):
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
        self.assertEqual(tick.owed_hours(None, 1e9), 0.0)
        self.assertEqual(tick.owed_hours(0, 5.9 * 3600), 5.9)
        self.assertEqual(tick.owed_hours(0, 25 * 3600), 25.0)
        self.assertEqual(tick.owed_hours(100 * 3600, 0), 0.0)

    def test_a_capped_backlog_is_slept_through(self):
        self.assertEqual(
            tick.reconcile(0, 100 * 3600, lived=24.0, owed=96.0), 100 * 3600)

    def test_an_uncapped_backlog_keeps_its_remainder(self):
        self.assertEqual(
            tick.reconcile(0, 25 * 3600, lived=24.0, owed=24.0), 24 * 3600)


class TestContinue(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "world"
        register(StubBackend({CallName.ACT: STAY}))
        # Configured to the stub so nothing reaches a real model.
        configure(self.root, "stub", "stub", calls=list(DEFAULTS))
        seed.create(self.root)

    def tearDown(self):
        self.temporary.cleanup()

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
        world = store.load(self.root)
        world.last_tick_at = None
        store.save(world)
        before = store.load(self.root)
        out = self.run_cli("continue")
        after = store.load(self.root)
        self.assertIn("clock started", out)
        self.assertEqual(after.at, before.at)

    def test_it_lives_what_is_owed(self):
        self.set_last_tick(13)
        before = store.load(self.root).at
        self.run_cli("continue")
        # Can overshoot by up to one step, which is not split.
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
        # Everyone is busy for six hours and only one has passed.
        self.run_cli("continue")                  # starts the clock
        self.set_last_tick(7)
        self.run_cli("continue")                  # lives up to the next thing due
        self.set_last_tick(1)
        out = self.run_cli("continue")
        self.assertIn("nothing is due", out)

    def test_a_running_tick_is_not_joined(self):
        self.set_last_tick(13)
        with store.TickLock(self.root):
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
        # nothing more happens in it, including a tuning run...
        for command in (("tick",), ("continue",), ("settle", "Havvah")):
            with self.assertRaises(SystemExit) as raised:
                self.run_cli(*command)
            self.assertIn("has ended", str(raised.exception))
        # ...but it can still be read.
        self.assertIn("(ended)", self.run_cli("status"))
        self.assertIn("had already ended", self.run_cli("end"))

    def test_a_running_tick_is_not_ended_underneath(self):
        with store.TickLock(self.root):
            with self.assertRaises(SystemExit) as raised:
                self.run_cli("end")
        self.assertIn("Not now", str(raised.exception))
        self.assertFalse(store.load(self.root).closed)

    def test_a_running_tick_is_not_written_over_by_a_tuning_run(self):
        with store.TickLock(self.root):
            with self.assertRaises(SystemExit) as raised:
                self.run_cli("settle", "Havvah")
        self.assertIn("Not now", str(raised.exception))

    def test_a_tuning_run_does_write_when_nothing_is_in_its_way(self):
        register(StubBackend({CallName.ACT: STAY, CallName.SETTLE: {
            "notebook": "The frame took both of us to hold."}}))
        out = self.run_cli("settle", "Havvah")
        self.assertIn("went over it", out)
        self.assertEqual(store.load(self.root).beings["havvah"].who.notebook,
                         "The frame took both of us to hold.",
                         "it took the lock and then wrote nothing")


if __name__ == "__main__":
    unittest.main()
