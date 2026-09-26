"""The configuration file alone decides which backend answers each call."""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import cli, seed
from elsewhere.schemas import CallName
from elsewhere.configuration import (DEFAULTS, MINDS, configure, load_configuration,
                                     path_of, write_default_configuration)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "elsewhere"

# The only environment variables the code may read.
ALLOWED = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
           "ELSEWHERE_OPENAI_KEY", "ELSEWHERE_STUB"}


class ConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"

    def tearDown(self):
        self.tmp.cleanup()

    def test_nothing_else_is_read_from_the_environment(self):
        read = set()
        for path in SOURCE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(
                    r"os\.(?:environ\.get\(|environ\[|getenv\()\s*(\S{0,40})", text):
                name = re.match(r"[\"']([A-Z_]+)[\"']", match.group(1))
                self.assertIsNotNone(name, f"{path.name}: environment read without "
                                           f"a literal name: {match.group(0)!r}")
                read.add(name.group(1))
        self.assertIn("ELSEWHERE_OPENAI_KEY", read)      # the scan sees reads at all
        self.assertLessEqual(read, ALLOWED)

    def test_the_environment_cannot_override_the_file(self):
        configure(self.root, "mlx", "mlx-community/gemma-4-E2B-it-qat-4bit")
        before = os.environ.get("ELSEWHERE_MODEL")
        os.environ["ELSEWHERE_MODEL"] = "something-else"
        try:
            self.assertEqual(load_configuration(self.root)[CallName.ACT].model,
                             "mlx-community/gemma-4-E2B-it-qat-4bit")
            with self.assertRaises(SystemExit) as raised:
                cli.main(["--world", str(self.root), "status"])
            self.assertIn("ELSEWHERE_MODEL no longer does anything",
                          str(raised.exception))
        finally:
            if before is None:
                os.environ.pop("ELSEWHERE_MODEL", None)
            else:
                os.environ["ELSEWHERE_MODEL"] = before

    def test_configure_changes_the_minds_and_leaves_the_embedder(self):
        configure(self.root, "openai", "some-model", base="http://gpu-box:8000/v1")
        loaded = load_configuration(self.root)
        for name in MINDS:
            self.assertEqual((loaded[name].backend, loaded[name].model,
                              loaded[name].base),
                             ("openai", "some-model", "http://gpu-box:8000/v1"))
        self.assertEqual(loaded["embed"].model, DEFAULTS["embed"]["model"])
        configure(self.root, "mlx", "mlx-community/gemma-4-E2B-it-qat-4bit")  # back home: base goes
        self.assertEqual(load_configuration(self.root)[CallName.ACT].base, "")

    def test_extra_stays_with_the_backend_it_was_written_for(self):
        # enable_thinking goes to an MLX chat template; the Claude SDK refuses it.
        path_of(self.root).parent.mkdir(parents=True)
        path_of(self.root).write_text(json.dumps({"agents": {"act": {
            **DEFAULTS[CallName.ACT], "extra": {"enable_thinking": True}}}}),
            encoding="utf-8")
        self.assertEqual(load_configuration(self.root)[CallName.ACT].extra,
                         {"enable_thinking": True})
        configure(self.root, "claude", "claude-sonnet-5")
        self.assertEqual(load_configuration(self.root)[CallName.ACT].extra, {})

    def test_an_older_file_on_another_backend_gets_no_default_extra(self):
        path_of(self.root).parent.mkdir(parents=True)
        path_of(self.root).write_text(json.dumps(
            {"agents": {"act": {"backend": "openai", "model": "m"}}}),
            encoding="utf-8")
        self.assertEqual(load_configuration(self.root)[CallName.ACT].extra, {})

    def test_a_world_keeps_a_configuration_written_before_it(self):
        configure(self.root, "stub", "stub", calls=list(DEFAULTS))
        seed.create(self.root)
        self.assertEqual(load_configuration(self.root)[CallName.ACT].backend, "stub")
        write_default_configuration(self.root)
        self.assertEqual(load_configuration(self.root)[CallName.ACT].backend, "stub")

    def test_what_the_file_leaves_out_comes_from_the_defaults(self):
        path_of(self.root).parent.mkdir(parents=True)
        path_of(self.root).write_text(json.dumps(
            {"agents": {"act": {"model": "bigger"}}}), encoding="utf-8")
        loaded = load_configuration(self.root)
        self.assertEqual(loaded[CallName.ACT].model, "bigger")
        self.assertEqual(loaded[CallName.ACT].backend, DEFAULTS[CallName.ACT]["backend"])
        self.assertEqual(loaded[CallName.SPEAK].model, DEFAULTS[CallName.SPEAK]["model"])

    def test_doctor_says_which_file_it_read(self):
        configure(self.root, "stub", "stub", calls=list(DEFAULTS))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--world", str(self.root), "doctor"])
        self.assertIn(f"Reading {path_of(self.root)}", out.getvalue())
        self.assertIn("stub/stub", out.getvalue())


if __name__ == "__main__":
    unittest.main()


class ReembedTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "world"
        configure(self.root, "stub", "stub", calls=list(DEFAULTS))
        seed.create(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_memory_and_belief_is_placed_again(self):
        from elsewhere.backends.stub import StubBackend
        from elsewhere.world import store
        from elsewhere.world.entities import Belief
        from elsewhere.world.memories import Memory

        world = store.load(self.root)
        being = next(iter(world.beings.values()))
        world.memories(being.id).add(Memory(id="mem-x", owner=being.id, at=0.0,
                                            account="the water came up",
                                            embedding=[0.5] * 768))
        being.who.beliefs.append(Belief(claim="the river keeps what it takes",
                                        embedding=[0.5] * 768))
        store.save(world)

        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["--world", str(self.root), "reembed"])

        world = store.load(self.root)
        being = world.beings[being.id]
        stub = StubBackend()
        memory = world.memories(being.id).get("mem-x")
        self.assertEqual(memory.embedding,
                         [round(x, 5) for x in stub.embed([memory.account])[0]])
        belief = being.who.beliefs[-1]
        self.assertEqual(belief.embedding,
                         [round(x, 5) for x in stub.embed([belief.claim])[0]])
