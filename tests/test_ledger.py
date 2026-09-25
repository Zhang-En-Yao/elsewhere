import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import prompts, retrieval, schemas, seed
from elsewhere.backends import Call, Settings, Transcript, ask, extract_json
from elsewhere.backends.stub import StubBackend
from elsewhere.world import store
from elsewhere.world.chronicle import CONVERSATION, Chronicle, Event
from elsewhere.world.entities import Being
from elsewhere.world.memories import Trace


def trace(**kw):
    base = dict(id="m1", owner="p", at=100 * 24, trace="the water rose over the fields",
                means="I was frightened", feeling="fear", salience=0.7,
                tags=["flood", "town"], place="waterline", touched_at=100 * 24)
    base.update(kw)
    return Trace(**base)


class TestWorldStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_world_survives_being_written_and_read(self):
        world = seed.build(self.root)
        world.traces("p_eve").add(trace(owner="p_eve", at=world.at))
        store.save(world)

        back = store.load(self.root)
        self.assertEqual(back.name, world.name)
        self.assertEqual(back.at, world.at)
        self.assertEqual(len(back.beings), len(world.beings))
        self.assertEqual(back.beings["p_eve"].card, world.beings["p_eve"].card)
        self.assertEqual(len(back.traces("p_eve")), 1)
        self.assertEqual(len(back.chronicle), len(world.chronicle))

    def test_the_chronicle_only_ever_grows(self):
        world = seed.build(self.root)
        before = len(world.chronicle)
        world.record("test", "something happened", place="shelter")
        store.save(world)
        lines = (self.root / "chronicle.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), before + 1)
        self.assertEqual(json.loads(lines[-1])["account"], "something happened")

    def test_two_ticks_cannot_run_at_once(self):
        self.root.mkdir(parents=True)
        with store.tick_lock(self.root):
            with self.assertRaises(store.Locked):
                with store.tick_lock(self.root):
                    pass
        with store.tick_lock(self.root):      # released, so it can be taken again
            pass


class TestRetrieval(unittest.TestCase):
    def test_what_mattered_stays_in_reach_for_a_year(self):
        t = trace(salience=0.95)
        self.assertFalse(retrieval.dormant(t, (100 + 365) * 24))

    def test_an_ordinary_day_does_not(self):
        t = trace(salience=0.15)
        self.assertTrue(retrieval.dormant(t, (100 + 120) * 24))

    def test_only_a_handful_can_be_brought_to_mind(self):
        traces = [trace(id=f"m{i}", salience=0.5, at=100 * 24 - i, touched_at=100 * 24 - i)
                  for i in range(20)]
        got = retrieval.recallable(traces, 100 * 24, limit=6)
        self.assertEqual(len(got), 6)
        self.assertEqual(got[0].id, "m0")          # freshest first, all else equal

    def test_a_cue_pulls_its_own_subject_forward(self):
        plain = trace(id="a", salience=0.5, tags=["garden"])
        cued = trace(id="b", salience=0.4, tags=["flood"])
        got = retrieval.recallable([plain, cued], 110 * 24, cues={"flood"}, limit=2)
        self.assertEqual(got[0].id, "b")

    def test_something_out_of_reach_can_still_be_pointed_at(self):
        t = trace(salience=0.9, tags=["flood"])
        at = (100 + 900) * 24
        self.assertTrue(retrieval.dormant(t, at))
        self.assertIsNone(retrieval.cued_return([t], at, {"harvest"}))
        self.assertIs(retrieval.cued_return([t], at, {"flood", "town", "waterline"}), t)

    def test_rewriting_keeps_the_older_wording(self):
        t = trace()
        t.rewrite("something about a flood", at=200 * 24, feeling="fear")
        self.assertEqual(t.trace, "something about a flood")
        self.assertEqual(t.history, ["the water rose over the fields"])
        self.assertEqual(t.recalls, 1)
        self.assertEqual(t.touched_at, 200 * 24)


class TestAnswers(unittest.TestCase):
    def test_json_is_found_inside_whatever_came_back(self):
        self.assertEqual(extract_json('{"stuck": true}'), {"stuck": True})
        self.assertEqual(extract_json('```json\n{"stuck": false}\n```'),
                         {"stuck": False})
        self.assertEqual(extract_json('Sure! {"stuck": true} Hope that helps.'),
                         {"stuck": True})
        self.assertEqual(extract_json('{"trace": "a } brace"}'),
                         {"trace": "a } brace"})
        self.assertIsNone(extract_json("I am a 125M parameter model and I ramble"))

    def test_a_bad_answer_is_complained_about_and_retried(self):
        attempts = []

        def answer(call):
            attempts.append(call.user)
            return {"weight": "a great deal"} if len(attempts) == 1 else {"weight": "stays"}

        backend = StubBackend({"perceive": answer})
        got = ask(backend, Call("perceive", "s", "u", schemas.PERCEIVE, "p_eve"),
                  Settings(backend="stub", model="stub"))
        self.assertEqual(got, {"weight": "stays"})
        self.assertEqual(len(attempts), 2)
        self.assertIn("not usable", attempts[1])

    def test_a_mind_that_never_makes_sense_is_simply_silent(self):
        backend = StubBackend({"perceive": "I am not going to answer that"})
        got = ask(backend, Call("perceive", "s", "u", schemas.PERCEIVE, "p"),
                  Settings(backend="stub", model="stub"))
        self.assertIsNone(got)

    def test_every_exchange_is_written_to_the_tape(self):
        with tempfile.TemporaryDirectory() as tmp:
            tape = Path(tmp) / "t.jsonl"
            backend = StubBackend({"perceive": {"stuck": True}})
            ask(backend, Call("perceive", "s", "u", schemas.PERCEIVE, "p_eve"),
                Settings(backend="stub", model="stub"), Transcript(tape))
            rows = [json.loads(l) for l in tape.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["ok"])
            self.assertEqual(rows[0]["about"], "p_eve")

    def test_a_feeling_is_not_chosen_from_a_list(self):
        # The engine never compares two feelings or sorts by one - it stores
        # them, prints them, and hands them back as text. A vocabulary here
        # would be a constraint on a person for nobody's benefit.
        for name in ("perceive", "recall"):
            self.assertNotIn("enum", schemas.BY_NAME[name]["properties"]["feeling"],
                             f"{name} is telling people what they may feel")
        clean, complaint = schemas.validate(
            "perceive", {"trace": "the sound of it", "weight": "stays",
                         "feeling": "something close to relief, but not quite"})
        self.assertIsNone(complaint)
        self.assertEqual(clean["feeling"], "something close to relief, but not quite")

    def test_the_weight_ladder_is_what_the_engine_sorts_by(self):
        self.assertGreater(schemas.weight_to_salience("marks"),
                           schemas.weight_to_salience("stays"))
        self.assertGreater(schemas.weight_to_salience("ordinary"),
                           schemas.weight_to_salience("faint"))


if __name__ == "__main__":
    unittest.main()


class TestVoiceIsShownNotDescribed(unittest.TestCase):
    """How somebody talks is in the chronicle, not in a field about them."""

    def chronicle(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        c = Chronicle(Path(tmp.name) / "chronicle.jsonl")
        return c

    def say(self, c, speaker, line, at):
        c.append(Event(id=f"ev{at:.0f}{speaker}", at=at, category=CONVERSATION,
                       account=f'{speaker} said: "{line}"',
                       data={"speaker": speaker, "line": line}))

    def test_a_being_is_handed_their_own_last_lines_oldest_first(self):
        c = self.chronicle()
        for i, line in enumerate(["It will hold.", "Deeper than it needs.", "No."]):
            self.say(c, "p_adam", line, 10.0 + i)
        self.say(c, "p_eve", "Not tonight.", 12.0)
        self.assertEqual(c.said_by("p_adam"),
                         ["It will hold.", "Deeper than it needs.", "No."])
        self.assertEqual(c.said_by("p_eve"), ["Not tonight."])
        self.assertEqual(c.said_by("p_nobody"), [])

    def test_it_reaches_past_a_repeat_rather_than_teaching_a_tic(self):
        # Three copies of one sentence shows somebody nothing about how they
        # sound. The point of the window is variety, so it widens to find it.
        c = self.chronicle()
        for i, line in enumerate(["Aye.", "Aye.", "Aye.", "The rains are coming."]):
            self.say(c, "p_adam", line, 10.0 + i)
        self.assertEqual(c.said_by("p_adam", limit=2), ["Aye.", "The rains are coming."])

    def test_nobody_is_shown_a_line_they_have_not_said_yet(self):
        # The backstory runs the clock backwards over events already written.
        c = self.chronicle()
        self.say(c, "p_adam", "It will hold.", 91 * 24)
        self.say(c, "p_adam", "The frame is up.", 17 * 24)
        self.assertEqual(c.said_by("p_adam", before=20 * 24), ["The frame is up."])
        self.assertEqual(c.said_by("p_adam", before=5 * 24), [])

    def test_the_lines_reach_the_prompt(self):
        being = Being(id="p_adam", name="Adam", card="You build what holds.")
        self.assertNotIn("said out loud", prompts.being_block(being))
        block = prompts.being_block(being, ["It will hold.", "Deeper than it needs."])
        self.assertIn("said out loud", block)
        self.assertIn('"It will hold."', block)
        self.assertIn('"Deeper than it needs."', block)

    def test_the_seed_gives_everybody_something_to_sound_like(self):
        # Nobody arrives in a world having never spoken.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        world = seed.build(Path(tmp.name) / "world")
        for pid in world.beings:
            self.assertTrue(world.chronicle.said_by(pid),
                            f"{pid} starts with no line of their own to sound like")
