"""The configuration file is the only thing that decides which mind answers."""

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

# Everything the code is allowed to read from the environment. A key decides
# whether a mind can be reached, never which one; ELSEWHERE_STUB is only read
# by the stub, which nothing reaches unless the configuration names it.
ALLOWED = {"ANTHROPIC_API_KEY", "ELSEWHERE_OPENAI_KEY", "ELSEWHERE_STUB"}


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
        configure(self.root, "ollama", "phi4-mini")
        before = os.environ.get("ELSEWHERE_MODEL")
        os.environ["ELSEWHERE_MODEL"] = "something-else"
        try:
            self.assertEqual(load_configuration(self.root)[CallName.ACT].model, "phi4-mini")
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
        configure(self.root, "ollama", "phi4-mini")        # back home: base goes
        self.assertEqual(load_configuration(self.root)[CallName.ACT].base, "")

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
