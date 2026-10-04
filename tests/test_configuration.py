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

from elsewhere.interface import cli, seed
from elsewhere.harness.schemas import CallName
from elsewhere.harness import configuration
from elsewhere.harness.configuration import DEFAULTS, MINDS, configure

SOURCE = Path(__file__).resolve().parents[1] / "src" / "elsewhere"

# The only environment variables the code may read.
ALLOWED = {"ELSEWHERE_OPENAI_KEY", "ELSEWHERE_STUB"}


class ConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "world"

    def tearDown(self):
        self.temporary.cleanup()

    def test_nothing_else_is_read_from_the_environment(self):
        read = set()
        for path in SOURCE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(
                r"os\.(?:environ\.get\(|environ\[|getenv\()\s*(\S{0,40})", text
            ):
                name = re.match(r"[\"']([A-Z_]+)[\"']", match.group(1))
                self.assertIsNotNone(
                    name,
                    f"{path.name}: environment read without " f"a literal name: {match.group(0)!r}",
                )
                read.add(name.group(1))
        self.assertIn("ELSEWHERE_OPENAI_KEY", read)  # the scan sees reads at all
        self.assertLessEqual(read, ALLOWED)

    def test_the_environment_cannot_override_the_file(self):
        configure(self.root, "mlx", "mlx-community/gemma-4-E2B-it-qat-4bit")
        before = os.environ.get("ELSEWHERE_MODEL")
        os.environ["ELSEWHERE_MODEL"] = "something-else"
        try:
            self.assertEqual(
                configuration.load(self.root)[CallName.ACT].model,
                "mlx-community/gemma-4-E2B-it-qat-4bit",
            )
        finally:
            if before is None:
                os.environ.pop("ELSEWHERE_MODEL", None)
            else:
                os.environ["ELSEWHERE_MODEL"] = before

    def test_configure_changes_the_minds_and_leaves_the_embedder(self):
        configure(self.root, "openai", "some-model", endpoint="http://gpu-box:8000/v1")
        loaded = configuration.load(self.root)
        self.assertEqual(loaded["embed"].model, DEFAULTS["embed"]["model"])
        for name in MINDS:
            self.assertEqual(
                (loaded[name].backend, loaded[name].model, loaded[name].endpoint),
                ("openai", "some-model", "http://gpu-box:8000/v1"),
            )
        configure(
            self.root, "mlx", "mlx-community/gemma-4-E2B-it-qat-4bit"
        )  # back home: endpoint goes
        self.assertEqual(configuration.load(self.root)[CallName.ACT].endpoint, "")

    def test_extra_stays_with_the_backend_it_was_written_for(self):
        # enable_thinking goes to an MLX chat template; an OpenAI-compatible server refuses it.
        configuration.locate(self.root).parent.mkdir(parents=True)
        configuration.locate(self.root).write_text(
            json.dumps(
                {
                    "agents": {
                        "act": {**DEFAULTS[CallName.ACT], "options": {"enable_thinking": True}}
                    }
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            configuration.load(self.root)[CallName.ACT].options, {"enable_thinking": True}
        )
        configure(self.root, "openai", "some-model")
        self.assertEqual(configuration.load(self.root)[CallName.ACT].options, {})

    def test_an_older_file_on_another_backend_gets_no_default_extra(self):
        configuration.locate(self.root).parent.mkdir(parents=True)
        configuration.locate(self.root).write_text(
            json.dumps({"agents": {"act": {"backend": "openai", "model": "m"}}}), encoding="utf-8"
        )
        self.assertEqual(configuration.load(self.root)[CallName.ACT].options, {})

    def test_a_world_keeps_a_configuration_written_before_it(self):
        configure(self.root, "stub", "stub", calls=list(DEFAULTS))
        seed.create(self.root)
        self.assertEqual(configuration.load(self.root)[CallName.ACT].backend, "stub")

    def test_what_the_file_leaves_out_comes_from_the_defaults(self):
        configuration.locate(self.root).parent.mkdir(parents=True)
        configuration.locate(self.root).write_text(
            json.dumps({"agents": {"act": {"model": "bigger"}}}), encoding="utf-8"
        )
        loaded = configuration.load(self.root)
        self.assertEqual(loaded[CallName.ACT].model, "bigger")
        self.assertEqual(loaded[CallName.ACT].backend, DEFAULTS[CallName.ACT]["backend"])
        self.assertEqual(loaded[CallName.SPEAK].model, DEFAULTS[CallName.SPEAK]["model"])

    def test_doctor_says_which_file_it_read(self):
        configure(self.root, "stub", "stub", calls=list(DEFAULTS))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--world", str(self.root), "doctor"])
        self.assertIn(f"Reading {configuration.locate(self.root)}", out.getvalue())
        self.assertIn("stub/stub", out.getvalue())


if __name__ == "__main__":
    unittest.main()
