"""What `seed.build` says about the four events, as each one is taken in."""

import contextlib
import io
import itertools
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import backends, seed
from elsewhere.backends import Settings, register
from elsewhere.backends.stub import StubBackend
from elsewhere.schemas import CallName


class MakingAWorldTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"
        # Distinct memories per person, so "3 of 3" counts people, not copies.
        counted = itertools.count()
        register(StubBackend({
            CallName.PERCEIVE: lambda call: {
                "stuck": True, "feeling": "fear", "means": "",
                "account": f"what {call.about} made of it ({next(counted)})"},
        }))

    def tearDown(self):
        self.tmp.cleanup()
        backends.bootstrap()          # the dial tone back, for whoever is next

    def configuration(self):
        settings = Settings(backend="stub", model="stub")
        return {name: settings for name in CallName}

    def test_a_world_built_in_silence_says_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            seed.build(self.root, configuration=self.configuration())
        self.assertEqual(out.getvalue(), "")

    def test_each_event_is_accounted_for_as_it_is_taken_in(self):
        said = []
        seed.build(self.root, configuration=self.configuration(), say=said.append)
        self.assertEqual(len(said), 4)
        for line, category in zip(said, ("descent", "churning", "flood", "lifting")):
            self.assertIn(category, line)
            self.assertIn("3 of 3 kept", line)

    def test_with_no_mind_there_is_nothing_to_account_for(self):
        said = []
        seed.build(self.root, configuration=None, say=said.append)
        self.assertEqual(said, [])

    def test_what_stuck_is_what_comes_back(self):
        world = seed.build(self.root, configuration=self.configuration())
        event = world.chronicle.all()[0]
        kept = seed.remember(world, event, self.configuration())
        self.assertEqual(len(kept), len(event.reached))
        self.assertEqual(sorted(memory.owner for memory in kept),
                         sorted(event.reached))

    def test_a_mind_that_keeps_nothing_is_not_counted_as_having_kept(self):
        register(StubBackend({CallName.PERCEIVE: {"stuck": False}}))
        said = []
        world = seed.build(self.root, configuration=self.configuration(),
                           say=said.append)
        self.assertIn("0 of 3 kept", said[0])
        self.assertEqual(seed.remember(world, world.chronicle.all()[0],
                                       self.configuration()), [])


if __name__ == "__main__":
    unittest.main()
