"""A backend that does not think at all.

It answers every call with the smallest valid thing, so the plumbing - storage,
retrieval, the tick loop, the CLI - can be tested without a model, a key, or a
second of latency. It is not a rule engine pretending to be a person; it is a
dial tone.
"""

from __future__ import annotations

import json
from typing import Callable, Dict, Optional

from . import Call

DEFAULTS: Dict[str, dict] = {
    "perceive": {"stuck": False},
    "act": {"action": "stay", "because": "stub"},
    "speak": {"line": "..."},
    "recall": {"trace": "", "changed": False},
    "reflect": {},
    "direct": {"happens": False},
}


class StubBackend:
    name = "stub"

    def __init__(self, answers: Optional[Dict[str, object]] = None):
        #: per call name, either a dict or a callable taking the Call
        self.answers: Dict[str, object] = dict(answers or {})
        self.calls: list = []

    def set(self, call_name: str, answer) -> None:
        self.answers[call_name] = answer

    def complete(self, call: Call, model: str, temperature: float,
                 extra: Optional[dict] = None) -> str:
        self.calls.append(call)
        answer = self.answers.get(call.name, DEFAULTS.get(call.name, {}))
        if isinstance(answer, Callable):           # type: ignore[arg-type]
            answer = answer(call)
        if isinstance(answer, str):
            return answer                          # let a test send back garbage
        return json.dumps(answer, ensure_ascii=False)
