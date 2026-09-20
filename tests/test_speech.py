import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import simulation
from elsewhere.mind import Scene, get_speech
from elsewhere.mind.llm import LLMMind
from elsewhere.mind.rules import RuleMind, compose_line
from elsewhere.perception import distort_line, encode_told, strip_framing
from elsewhere.seed import create_world


def scene_for(world, topic=None, familiarity=0.6):
    alice, bram = world.people["p_alice"], world.people["p_bram"]
    return Scene(speaker=alice, listener=bram, topic=topic,
                 place_name="The Old Market", phase="evening", season="winter",
                 familiarity=familiarity)


class TestVoice(unittest.TestCase):
    def setUp(self):
        self.world = create_world(seed=1)
        self.alice = self.world.people["p_alice"]
        self.topic = self.alice.memories.strongest(1)[0]

    def test_a_line_comes_out_at_every_stage_of_decay(self):
        mind = RuleMind()
        for detail in (0.9, 0.2, 0.01):
            self.topic.detail = detail
            line = mind.speak(scene_for(self.world, self.topic), random.Random(detail))
            self.assertTrue(line.endswith("."), line)
            self.assertGreater(len(line.split()), 4, line)

    def test_what_is_said_follows_what_is_left(self):
        mind = RuleMind()
        self.topic.detail = 0.9
        clear = mind.speak(scene_for(self.world, self.topic), random.Random(2))
        self.topic.detail = 0.01
        gone = mind.speak(scene_for(self.world, self.topic), random.Random(2))
        self.assertIn(self.topic.gist.rstrip(".").split(",")[0][:12].lower(), clear.lower())
        self.assertNotIn(self.topic.gist.rstrip("."), gone)
        self.assertIn(self.topic.feeling, gone)

    def test_nobody_narrates_themselves_in_the_third_person(self):
        table = next(m for m in self.alice.memories if "long table" in m.gist)
        table.detail = 0.9
        line = RuleMind().speak(scene_for(self.world, table), random.Random(3))
        self.assertNotIn("Alice and Bram", line)
        self.assertIn("you and i", line.lower())

    def test_strangers_hedge(self):
        self.topic.detail = 0.9
        close = compose_line(scene_for(self.world, self.topic, 0.8), random.Random(4))
        distant = compose_line(scene_for(self.world, self.topic, 0.01), random.Random(4))
        self.assertNotEqual(close, distant)
        self.assertTrue(distant.startswith(("You would not know", "We have not spoken",
                                            "I do not say this")))

    def test_small_talk_when_there_is_nothing_to_say(self):
        line = RuleMind().speak(scene_for(self.world, None), random.Random(5))
        self.assertTrue(line)

    def test_the_same_seed_says_the_same_thing(self):
        a = compose_line(scene_for(self.world, self.topic), random.Random(6))
        b = compose_line(scene_for(self.world, self.topic), random.Random(6))
        self.assertEqual(a, b)

    def test_a_model_mind_falls_back_to_words_rather_than_silence(self):
        mind = LLMMind()
        mind._client = None
        line = mind.speak(scene_for(self.world, self.topic), random.Random(7))
        self.assertTrue(line)

    def test_any_mind_can_be_asked_for_a_line(self):
        self.alice.mind_kind = "player"      # PlayerMind has no voice of its own
        line = get_speech(self.alice, scene_for(self.world, self.topic), random.Random(8))
        self.assertTrue(line)


class TestWhatArrives(unittest.TestCase):
    def test_framing_is_not_carried_away(self):
        line = ("I do not much like bringing this up. The old market burned down. "
                "I do not know why it stays with me.")
        self.assertEqual(strip_framing(line), "The old market burned down")

    def test_an_unframed_line_survives_whole(self):
        line = "The river took the low road again last night."
        self.assertEqual(strip_framing(line) + ".", line)

    def test_hearing_it_right_and_hearing_it_wrong(self):
        line = "I do not much like bringing this up. The old market burned down."
        right = distort_line(line, False, random.Random(1))
        wrong = distort_line(line, True, random.Random(1))
        self.assertEqual(right, "The old market burned down.")
        self.assertNotEqual(right, wrong)
        self.assertIn("burned down", wrong)

    def test_the_listener_keeps_the_words_they_think_they_got(self):
        world = create_world(seed=2)
        alice, bram = world.people["p_alice"], world.people["p_bram"]
        topic = alice.memories.strongest(1)[0]
        said = "You know how it went. The old market burned down."
        heard = None
        for attempt in range(60):
            m = encode_told(bram, alice, topic, world.clock.day,
                            random.Random(attempt), f"mem_t{attempt}", said=said)
            if m is not None:
                heard = m.heard
                break
        self.assertIsNotNone(heard)
        self.assertNotIn("You know how it went", heard)

    def test_conversations_in_a_running_world_are_spoken(self):
        world = create_world(seed=9)
        simulation.advance(world, days=120)
        spoken = [e for e in world.history
                  if e.kind == "conversation" and e.data.get("said")]
        self.assertTrue(spoken, "somebody should have said something out loud")
        kept = [m for p in world.people.values() for m in p.memories if m.heard]
        self.assertTrue(kept, "and somebody should be carrying words around")
        misheard = [m for m in kept
                    if any("misunderstood" in d for d in m.distortions)]
        self.assertTrue(misheard, "and somebody should have got it wrong")


if __name__ == "__main__":
    unittest.main()
