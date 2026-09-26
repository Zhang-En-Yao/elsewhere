"""GPT and Gemini backends: base URL and API key."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere import backends
from elsewhere.backends import Call, Settings
from elsewhere.schemas import CallName, grammar

ANSWER = {"choices": [{"message": {"content": '{"ok": true}'}}]}


def call() -> Call:
    return Call(name=CallName.PROBE, system="s", user="u",
                schema=grammar(CallName.PROBE))


class HostedBackendTest(unittest.TestCase):
    def test_they_are_registered_under_their_own_names(self):
        self.assertEqual(backends.get("gpt").name, "gpt")
        self.assertEqual(backends.get("gemini").name, "gemini")
        self.assertEqual(backends.get("openai").name, "openai")     # still the local one

    def test_each_goes_to_its_own_address_with_its_own_key(self):
        cases = (("gpt", "OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions"),
                 ("gemini", "GEMINI_API_KEY",
                  "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"))
        for name, variable, url in cases:
            with self.subTest(name), \
                    mock.patch.dict(os.environ, {variable: "sk-test"}), \
                    mock.patch("elsewhere.backends.open_source.openai_compatible.post",
                               return_value=ANSWER) as post:
                raw = backends.get(name).complete(call(), Settings(backend=name, model="m"))
            self.assertEqual(raw, '{"ok": true}')
            self.assertEqual(post.call_args.args[0], url)
            self.assertEqual(post.call_args.args[3], {"authorization": "Bearer sk-test"})

    def test_a_base_in_the_configuration_still_wins(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}), \
                mock.patch("elsewhere.backends.open_source.openai_compatible.post",
                           return_value=ANSWER) as post:
            backends.get("gpt").complete(
                call(), Settings(backend="gpt", model="m", base="http://proxy:9/v1/"))
        self.assertEqual(post.call_args.args[0], "http://proxy:9/v1/chat/completions")

    def test_no_key_is_said_plainly_and_nothing_is_sent(self):
        for name, variable in (("gpt", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY")):
            with self.subTest(name):
                env = {k: v for k, v in os.environ.items() if k != variable}
                with mock.patch.dict(os.environ, env, clear=True), \
                        mock.patch("elsewhere.backends.open_source.openai_compatible.post") as post:
                    ok, message = backends.probe(Settings(backend=name, model="m"))
                self.assertFalse(ok)
                self.assertIn(variable, message)
                post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
