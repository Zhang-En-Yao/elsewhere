"""The acceptance test for the whole idea.

One fire. Four people standing in the same street. If this world is worth
building, what comes out the other side is four different things and one
person holding nothing at all.

Run offline against the stub, which proves the pipeline. Run it against a real
model to find out whether the model is any good at the only job that matters:

    ELSEWHERE_LIVE=1 ELSEWHERE_BACKEND=ollama ELSEWHERE_MODEL=gemma4:26b-a4b \\
        python -m unittest tests.test_fire
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import agents, config as config_mod, retrieval, seed
from elsewhere.backends import Settings, Transcript
from elsewhere.backends import register
from elsewhere.backends.stub import StubBackend

# What four people might plausibly come back with. The stub is not pretending
# to be a mind; it is standing in for one so the plumbing can be checked.
SCRIPT = {
    "p_alice": {"stuck": True, "weight": "marks",
                "trace": "standing in the street with my hands full of nothing",
                "means": "I still cannot be near it after dark",
                "feeling": "fear", "tags": ["fire", "market", "night"]},
    "p_bram": {"stuck": True, "weight": "stays",
               "trace": "the beams went first, then the roof came in",
               "means": "we put it back up by spring",
               "feeling": "resolve", "tags": ["fire", "market", "building"]},
    "p_carol": {"stuck": True, "weight": "stays",
                "trace": "watching it from the hill road and not going down",
                "means": "that was when I understood I could leave",
                "feeling": "unease", "tags": ["fire", "leaving"]},
    "p_david": {"stuck": False},
}


def scripted(call):
    return SCRIPT.get(call.about, {"stuck": False})


class TestTheFire(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"
        self.world = seed.build(self.root)
        self.fire = next(e for e in self.world.chronicle.all() if e.kind == "fire")
        self.backend = StubBackend({"perceive": scripted})
        register(self.backend)
        self.config = {name: Settings(backend="stub", model="stub")
                       for name in ("perceive", "act", "speak", "recall",
                                    "reflect", "direct")}

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_event_four_people_four_outcomes(self):
        self.world.day = self.fire.day
        made = agents.perceive_all(self.world, self.fire, self.config)

        self.assertEqual(len(made), 3, "three of them kept something")
        kept = {t.owner: t for t in made}
        self.assertNotIn("p_david", kept, "David was there and has nothing")
        self.assertIn("p_david", self.fire.present, "history still knows he was there")

        texts = {t.trace for t in made}
        self.assertEqual(len(texts), 3, "no two of them kept the same thing")
        feelings = {t.feeling for t in made}
        self.assertEqual(len(feelings), 3, "and it did not feel the same to any of them")

        self.assertGreater(kept["p_alice"].salience, kept["p_carol"].salience,
                           "it marked her more than it marked Carol")
        for trace in made:
            self.assertEqual(trace.event_id, self.fire.id)
            self.assertEqual(trace.place, "market")

    def test_they_diverge_further_as_it_fades(self):
        self.world.day = self.fire.day
        agents.perceive_all(self.world, self.fire, self.config)
        later = self.fire.day + 300

        reachable = {}
        for pid in ("p_alice", "p_bram", "p_carol", "p_david"):
            traces = list(self.world.traces(pid))
            reachable[pid] = retrieval.recallable(traces, later, cues={"fire"})

        self.assertTrue(reachable["p_alice"], "it marked her; she still has it")
        self.assertFalse(reachable["p_david"], "he never had it to lose")

    def test_nobody_gets_two_unforgettable_days_in_one_day(self):
        self.world.day = self.fire.day
        self.backend.set("perceive", lambda call: SCRIPT["p_alice"])
        first = agents.perceive(self.world, self.world.people["p_alice"],
                                self.fire, self.config)
        second = agents.perceive(self.world, self.world.people["p_alice"],
                                 self.fire, self.config)
        self.assertGreaterEqual(first.salience, 0.7)
        self.assertLess(second.salience, 0.7,
                        "the engine supplies the scarcity the model lacks")

    def test_a_mind_that_says_nothing_leaves_nothing(self):
        self.world.day = self.fire.day
        self.backend.set("perceive", "sorry, I can't help with that")
        made = agents.perceive_all(self.world, self.fire, self.config)
        self.assertEqual(made, [])

    def test_the_whole_thing_is_written_down(self):
        self.world.day = self.fire.day
        tape = self.root / "transcript" / "test.jsonl"
        agents.perceive_all(self.world, self.fire, self.config, Transcript(tape))
        rows = tape.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(rows), 4, "every person was asked, on the record")


@unittest.skipUnless(os.environ.get("ELSEWHERE_LIVE"),
                     "set ELSEWHERE_LIVE=1 and a backend to judge a real model")
class TestTheFireForReal(unittest.TestCase):
    """The same fire, put to whatever model is configured.

    This is the quality ruler: a model that gives four near-identical answers
    here cannot carry this world, however well it writes.
    """

    def test_four_people_do_not_sound_like_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "world"
            world = seed.build(root)
            config_mod.write_default(root)
            config = config_mod.load(root)
            fire = next(e for e in world.chronicle.all() if e.kind == "fire")
            world.day = fire.day
            made = agents.perceive_all(world, fire, config,
                                       Transcript(root / "live.jsonl"))
            for trace in made:
                print(f"\n  {world.people[trace.owner].name}: {trace.trace}"
                      f"\n    ({trace.feeling}, weight {trace.salience}) {trace.means}")
            self.assertGreaterEqual(len(made), 2, "somebody should keep something")
            self.assertEqual(len({t.trace for t in made}), len(made),
                             "four people should not produce the same sentence")
            self.assertLessEqual(len(made), 3,
                                 "if everyone keeps everything, the weighting is broken")


if __name__ == "__main__":
    unittest.main()
