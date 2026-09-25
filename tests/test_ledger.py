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
from elsewhere.world.entities import Being
from elsewhere.world.memories import Trace


def trace(**kw):
    base = dict(id="m1", owner="p", at=100 * 24, trace="the water rose over the fields",
                means="I was frightened", feeling="fear", salience=0.7,
                place="waterline", touched_at=100 * 24)
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

    def test_what_the_moment_is_about_pulls_its_own_subject_forward(self):
        here, elsewhere = [1.0, 0.0], [0.0, 1.0]
        plain = trace(id="a", salience=0.5, embedding=elsewhere)
        cued = trace(id="b", salience=0.4, embedding=here)
        self.assertEqual(
            retrieval.recallable([plain, cued], 110 * 24, near=here, limit=2)[0].id, "b")
        # and with nothing to be about, the stronger memory is simply nearer
        self.assertEqual(
            retrieval.recallable([plain, cued], 110 * 24, limit=2)[0].id, "a")

    def test_a_memory_with_no_vector_is_ranked_not_dropped(self):
        # An embedder that was down when this was written must not cost
        # somebody the memory - it costs them only the pull towards it.
        no_vector = trace(id="a", salience=0.9)
        placed = trace(id="b", salience=0.2, embedding=[1.0, 0.0])
        got = retrieval.recallable([no_vector, placed], 110 * 24, near=[1.0, 0.0])
        self.assertEqual({t.id for t in got}, {"a", "b"})

    def test_nearness_survives_a_change_of_embedder(self):
        # Vectors of different width are not comparable, and saying so is
        # better than a number nobody can interpret.
        self.assertEqual(retrieval.nearness([1.0, 0.0], [1.0, 0.0, 0.0]), 0.0)
        self.assertEqual(retrieval.nearness([], [1.0]), 0.0)
        self.assertAlmostEqual(retrieval.nearness([1.0, 0.0], [1.0, 0.0]), 1.0)

    def test_something_out_of_reach_can_still_be_pointed_at(self):
        t = trace(salience=0.9, embedding=[1.0, 0.0])
        at = (100 + 900) * 24
        self.assertTrue(retrieval.dormant(t, at))
        self.assertIsNone(retrieval.cued_return([t], at, [0.0, 1.0]))
        self.assertIs(retrieval.cued_return([t], at, [1.0, 0.0]), t)

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


class TestTheAnswerIsNotInTheQuestion(unittest.TestCase):
    """`perceive` asks for a short fragment in their own voice. So is `thought`."""

    def being(self):
        return Being(id="p_adam", name="Adam", card="You build what holds.",
                     thought="The roof is not finished and the rains are not waiting",
                     wants=["finish the roof"])

    def test_perceive_is_not_shown_the_one_sentence_shaped_like_its_answer(self):
        being = self.being()
        asked = prompts.perceive_user(
            being=being, what_happened="The shelter came down in the night.",
            where="The Shelter", when="02:00 in spring", at=200 * 24,
            others=[], traces=[], part_of_it=True)
        self.assertNotIn(being.thought, asked)
        self.assertIn("You build what holds.", asked)     # who they are stays

    def test_every_other_call_still_is(self):
        being = self.being()
        self.assertIn(being.thought, prompts.being_block(being))
        self.assertIn(being.thought, prompts.reflect_user(being, [], []))


class TestMannerIsAFactNotASpecification(unittest.TestCase):
    """What survives a change of model is a fact about a person."""

    def test_the_seed_says_what_they_do_not_what_the_output_should_look_like(self):
        # "short sentences" is a note to whoever is rendering them, and would
        # have to be deleted out of every saved being the day the model gets
        # better. "you say as little as will do" is true of somebody.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        world = seed.build(Path(tmp.name) / "world")
        spec = ("sentence", "short", "terse", "brief", "plain and", "words,")
        for being in world.beings.values():
            self.assertTrue(being.manner, f"{being.name} has no manner")
            self.assertTrue(being.manner.startswith("You "),
                            f"{being.name}'s manner is not about them: {being.manner!r}")
            for word in spec:
                self.assertNotIn(word, being.manner.lower(),
                                 f"{being.name}'s manner specifies output: {being.manner!r}")

    def test_it_is_a_line_of_its_own_because_that_is_what_worked(self):
        being = Being(id="p", name="Eve", card="You tend the garden.",
                      manner="You say as little as will do.")
        block = prompts.being_block(being)
        self.assertIn("\nHow you talk: You say as little as will do.", block)
