import io
import contextlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import cli


def run(*argv) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cli.main(list(argv))
    return out.getvalue()


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.world = str(Path(self.tmp.name) / "world.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_world_can_be_made_left_and_returned_to(self):
        self.assertIn("exists", run("--world", self.world, "init", "--player", "You"))
        run("--world", self.world, "advance", "--days", "30", "--away")
        status = run("--world", self.world, "status")
        self.assertIn("Wend", status)
        timeline = run("--world", self.world, "timeline", "--limit", "5")
        self.assertIn("day", timeline)

    def test_one_event_many_versions(self):
        run("--world", self.world, "init")
        run("--world", self.world, "advance", "--days", "5")
        out = run("--world", self.world, "event", "ev0002")
        self.assertIn("History says", out)
        self.assertIn("Memory says", out)
        self.assertIn("nothing. They were there.", out)

    def test_a_memory_from_a_real_life_enters_the_world(self):
        run("--world", self.world, "init", "--player", "You")
        out = run("--world", self.world, "remember", "the night bus in the rain",
                  "--themes", "travel,rain")
        self.assertIn("It is in the world now.", out)

    def test_a_world_can_be_ended_from_outside(self):
        run("--world", self.world, "init", "--player", "You")
        run("--world", self.world, "advance", "--days", "20")
        archive = str(Path(self.tmp.name) / "worlds")
        out = run("--world", self.world, "end", "--archive", archive, "-y")
        self.assertIn("ends.", out)
        self.assertIn("Who they turned out to be", out)
        self.assertFalse(Path(self.world).exists(), "the running world is gone")

        kept = list(Path(archive).glob("*.json"))
        self.assertEqual(len(kept), 1)

        # It can still be read, but no more time passes in it.
        self.assertIn("day", run("--world", str(kept[0]), "timeline", "--limit", "3"))
        with self.assertRaises(SystemExit):
            run("--world", str(kept[0]), "advance", "--days", "1")

    def test_person_view(self):
        run("--world", self.world, "init")
        run("--world", self.world, "advance", "--days", "40")
        out = run("--world", self.world, "person", "Alice")
        self.assertIn("what they believe now", out)
        self.assertIn("memory:", out)


if __name__ == "__main__":
    unittest.main()
