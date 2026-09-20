import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere.memory import Memory, MemoryStore


def make(intensity=0.5, strength=0.8, detail=0.8, day=0, themes=("fire",)):
    return Memory(id="m1", owner="p", day=day, gist="the market burned",
                  interpretation="it meant something", feeling="fear",
                  lens="fear", valence=-0.7, intensity=intensity,
                  detail=detail, strength=strength, themes=list(themes),
                  place="market", last_touch_day=day)


class TestDecay(unittest.TestCase):
    def test_detail_goes_before_strength(self):
        m = make()
        m.decay_to(60)
        self.assertLess(m.detail, m.strength,
                        "details should fade faster than the memory itself")

    def test_feeling_outlives_detail(self):
        m = make(intensity=0.9)
        m.decay_to(200)
        self.assertGreater(m.intensity, m.detail)

    def test_something_that_mattered_survives_a_year(self):
        m = make(intensity=0.9, strength=0.85)
        m.decay_to(365)
        self.assertFalse(m.dormant)

    def test_an_ordinary_afternoon_does_not(self):
        m = make(intensity=0.15, strength=0.4)
        m.decay_to(120)
        self.assertTrue(m.dormant)
        self.assertEqual(m.detail, 0.0)
        self.assertEqual(m.text(), "(forgotten)")

    def test_recall_keeps_it_alive(self):
        rehearsed, left_alone = make(intensity=0.4), make(intensity=0.4)
        for day in range(0, 200, 10):
            rehearsed.recall(day, random.Random(day))
        rehearsed.decay_to(365)
        left_alone.decay_to(365)
        self.assertGreater(rehearsed.strength, left_alone.strength)

    def test_vagueness_before_silence(self):
        m = make(intensity=0.7)
        m.decay_to(90)
        self.assertNotEqual(m.text(), m.gist)
        self.assertNotEqual(m.text(), "(forgotten)")


class TestStore(unittest.TestCase):
    def test_resurfacing_needs_a_cue(self):
        store = MemoryStore()
        m = make(intensity=0.95, strength=0.9)
        store.add(m)
        store.decay_to(4000)
        self.assertTrue(m.dormant)
        self.assertIsNone(store.resurface({"harvest"}, 4000, random.Random(1)))
        found = None
        for attempt in range(50):
            found = store.resurface({"fire"}, 4000, random.Random(attempt))
            if found:
                break
        self.assertIsNotNone(found, "a strong cue should eventually bring it back")
        self.assertFalse(m.dormant)
        self.assertEqual(m.returned_on, 4000)

    def test_conflation_makes_one_memory_out_of_two(self):
        store = MemoryStore()
        a, b = make(day=1), make(day=2)
        b.id = "m2"
        a.detail = b.detail = 0.2
        store.add(a)
        store.add(b)
        merged = store.conflate(random.Random(3))
        self.assertIsNotNone(merged)
        self.assertTrue(a.dormant or b.dormant)

    def test_pruning_forgets_completely(self):
        store = MemoryStore()
        for i in range(60):
            m = make(intensity=0.05, strength=0.3)
            m.id = f"m{i}"
            store.add(m)
        store.decay_to(400)
        removed = store.prune(keep_dormant=10)
        self.assertGreater(removed, 0)
        self.assertEqual(store.forgotten, removed)

    def test_round_trip(self):
        store = MemoryStore()
        store.add(make())
        restored = MemoryStore.from_dict(store.to_dict())
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored.memories[0].gist, "the market burned")
        self.assertAlmostEqual(restored.memories[0].intensity, 0.5, places=3)


if __name__ == "__main__":
    unittest.main()
