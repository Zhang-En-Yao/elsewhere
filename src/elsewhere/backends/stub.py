"""A backend that does not think at all.

It answers every call with the smallest valid thing, so the plumbing - storage,
retrieval, the tick loop, the CLI - can be tested without a model, a key, or a
second of latency. It is not a rule engine pretending to be a person; it is a
dial tone.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional

from . import Call

DEFAULTS: Dict[str, dict] = {
    "perceive": {"weight": "nothing"},
    "act": {"because": "", "doing": "", "action": "stay", "target": ""},
    "speak": {"line": "..."},
    "recall": {"trace": "", "changed": False},
    "reflect": {},
    "direct": {"happens": False},
    "arrive": {"comes": False},
}


class StubBackend:
    name = "stub"

    def __init__(self, answers: Optional[Dict[str, object]] = None,
                 script_from_env: bool = False):
        #: keyed by "<call>|<person id>" or just "<call>". The value may be a
        #: dict, a raw string (to send back something unusable on purpose), a
        #: callable taking the Call, or a list that is worked through in order.
        self.answers: Dict[str, object] = dict(answers or {})
        self.calls: list = []
        self._taken: Dict[str, int] = defaultdict(int)
        # Only the registered default reads the environment. A stub a test
        # builds for itself stays exactly what the test said it was.
        script = os.environ.get("ELSEWHERE_STUB") if script_from_env else None
        if script:
            self.answers.update(json.loads(Path(script).read_text(encoding="utf-8")))

    def set(self, call_name: str, answer) -> None:
        self.answers[call_name] = answer

    def complete(self, call: Call, model: str, temperature: float,
                 extra: Optional[dict] = None) -> str:
        self.calls.append(call)
        key = f"{call.name}|{call.about}"
        answer = self.answers.get(key, self.answers.get(
            call.name, DEFAULTS.get(call.name, {})))
        if isinstance(answer, list):
            taken = self._taken[key]
            self._taken[key] += 1
            answer = answer[taken % len(answer)] if answer else {}
        if callable(answer):
            answer = answer(call)
        if isinstance(answer, str):
            return answer                          # let a test send back garbage
        return json.dumps(answer, ensure_ascii=False)
