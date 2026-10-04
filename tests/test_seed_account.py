"""What `seed.build` leaves: a town, a past nobody has looked at yet, and a page each."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere.adapters import backends
from elsewhere.harness import memory, tick
from elsewhere.interface import seed
from elsewhere.adapters.backends import Settings, register
from elsewhere.adapters.backends.stub import StubBackend
from elsewhere.harness.schemas import CallName


class MakingAWorldTest(unittest.TestCase):

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "world"
        self.stub = StubBackend()
        register(self.stub)

    def tearDown(self):
        self.temporary.cleanup()
        backends.bootstrap()  # the dial tone back, for whoever is next

    def configuration(self):
        settings = Settings(backend="stub", model="stub")
        return {name: settings for name in (*CallName, "embed")}

    def test_making_a_world_asks_no_mind_anything(self):
        seed.build(self.root)
        self.assertEqual(self.stub.calls, [])

    def test_each_of_them_starts_with_the_self_schema_they_were_written_with(self):
        world = seed.build(self.root)
        for being in world.beings.values():
            self.assertFalse(being.identity.self_schema.empty)
            self.assertEqual(
                world.self_schemas(being.id).all(),
                [being.identity.self_schema],
                "and it is the first one they hold",
            )
            self.assertEqual(world.episodes(being.id).all(), [], "and nothing encoded yet")
            self.assertEqual(world.engrams(being.id).all(), [], "and nothing laid down")

    def test_the_past_has_reached_them_and_they_have_not_looked_at_it(self):
        world = seed.build(self.root)
        for being in world.beings.values():
            seen = memory.percepts(world, being)
            self.assertEqual(
                [event.id for event, _ in seen], [event.id for event in world.chronicle.all()]
            )
            for event, stood in seen:
                self.assertEqual(stood, event.data["perspectives"][being.id])

    def test_the_first_morning_is_when_they_look_back_on_it(self):
        world = seed.build(self.root)
        self.stub.set(
            CallName.ACT,
            {"encoded": "the rope, and the horn in front of me", "action": "", "duration": 21600},
        )
        tick.tick(world, self.configuration())
        havvah = next(
            call for call in self.stub.calls if call.name == CallName.ACT and call.mind == "havvah"
        )
        for event in world.chronicle.all():
            self.assertIn(event.account, havvah.user)
            self.assertIn(event.data["perspectives"]["havvah"], havvah.user)
        episodes = world.episodes("havvah").all()
        self.assertEqual(len(episodes), 1, "one thing kept of all of it, in her words")
        self.assertEqual(episodes[0].event_ids, [event.id for event in world.chronicle.all()])


if __name__ == "__main__":
    unittest.main()
