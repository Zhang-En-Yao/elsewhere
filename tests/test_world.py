import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import simulation, storage
from elsewhere.seed import create_world, invite_companion


class TestSeedWorld(unittest.TestCase):
    def test_the_fire_is_remembered_differently(self):
        world = create_world(seed=1)
        fire = next(e for e in world.history if e.kind == "fire")
        versions = {}
        for person in world.people.values():
            m = person.memories.about_event(fire.id)
            if m is not None:
                versions[person.name] = m.lens
        self.assertGreaterEqual(len(set(versions.values())), 3,
                                "the same event should leave different traces")
        self.assertNotIn("David", versions, "David forgets the fire entirely")
        self.assertIn(world.people["p_david"].id, fire.witnesses,
                      "he was still there; history keeps that")

    def test_history_outlives_the_details(self):
        world = create_world(seed=1)
        simulation.advance(world, days=400)
        fire = next(e for e in world.history if e.kind == "fire")
        self.assertEqual(fire.summary, "The old market burned down.")
        alice = world.people["p_alice"]
        m = alice.memories.about_event(fire.id)
        self.assertIsNotNone(m)
        self.assertNotEqual(m.text(), fire.summary,
                            "what she has left should no longer match the record")


class TestSimulation(unittest.TestCase):
    def test_same_seed_same_world(self):
        a, b = create_world(seed=7), create_world(seed=7)
        simulation.advance(a, days=60)
        simulation.advance(b, days=60)
        self.assertEqual([e.summary for e in a.history],
                         [e.summary for e in b.history])

    def test_different_seed_different_world(self):
        a, b = create_world(seed=7), create_world(seed=8)
        simulation.advance(a, days=60)
        simulation.advance(b, days=60)
        self.assertNotEqual([e.summary for e in a.history],
                            [e.summary for e in b.history])

    def test_the_world_produces_a_life(self):
        world = create_world(seed=3)
        before = len(world.history)
        simulation.advance(world, days=200)
        self.assertGreater(len(world.history), before + 50)
        self.assertTrue(world.artifacts, "people should have made something")
        for person in world.people.values():
            self.assertTrue(person.memories.active())
            self.assertTrue(person.beliefs)

    def test_a_belief_outlives_the_memory_that_caused_it(self):
        world = create_world(seed=5)
        alice = world.people["p_alice"]
        memory = alice.memories.strongest(1)[0]
        alice.believe("leaving", "people go, and they do not come back",
                      world.clock.day, memory.id, 0.5)
        conviction = alice.beliefs["leaving"].conviction

        memory.intensity = 0.05          # nothing keeps this one in reach
        memory.strength = 0.2
        alice.memories.decay_to(world.clock.day + 400)
        alice.refresh_belief_origins()

        self.assertTrue(memory.dormant)
        self.assertIn("leaving", alice.beliefs, "the belief is still hers")
        self.assertEqual(alice.beliefs["leaving"].conviction, conviction)
        self.assertTrue(alice.beliefs["leaving"].origin_forgotten,
                        "she can no longer say where it came from")

    def test_leaving_and_coming_back(self):
        world = create_world(seed=2, player_name="You")
        player = world.people["p_player"]
        player.present = False
        before = len(world.history)
        simulation.advance(world, days=30)
        self.assertGreater(len(world.history), before)
        self.assertEqual(player.last_action, "", "the player did nothing while away")


class TestStorage(unittest.TestCase):
    def test_round_trip(self):
        world = create_world(seed=11, player_name="You")
        simulation.advance(world, days=90)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "world.json"
            storage.save(world, path)
            restored = storage.load(path)
        self.assertEqual(restored.clock.day, world.clock.day)
        self.assertEqual(len(restored.history), len(world.history))
        for pid, person in world.people.items():
            other = restored.people[pid]
            self.assertEqual(len(other.memories), len(person.memories))
            self.assertEqual(other.beliefs.keys(), person.beliefs.keys())

    def test_a_saved_world_keeps_going_the_same_way(self):
        world = create_world(seed=13)
        simulation.advance(world, days=20)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "world.json"
            storage.save(world, path)
            reloaded = storage.load(path)
        simulation.advance(world, days=20)
        simulation.advance(reloaded, days=20)
        self.assertEqual([e.summary for e in world.history],
                         [e.summary for e in reloaded.history])


class TestCompanions(unittest.TestCase):
    def test_something_that_was_never_alive_can_enter(self):
        world = create_world(seed=4)
        momo = invite_companion(world, "Momo", "A cat who slept on the windowsill.")
        simulation.advance(world, days=60)
        self.assertTrue(momo.memories.active(), "it should have a life of its own now")
        known_by = [p.name for p in world.people.values()
                    if p.id != momo.id and p.knows(momo.id)]
        self.assertTrue(known_by, "someone should have met it")


if __name__ == "__main__":
    unittest.main()
