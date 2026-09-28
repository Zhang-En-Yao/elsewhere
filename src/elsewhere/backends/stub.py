"""A backend that answers every call with a minimal valid answer, for tests."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional

from . import Call, Settings
from ..schemas import CallName

DEFAULTS: Dict[str, dict] = {
    CallName.ACT: {"because": "", "doing": "", "action": "", "target": "",
            "again_in_hours": 6.0, "settling": False, "absorbed": False},
    CallName.SPEAK: {"utterance": "..."},
    # An empty page is no answer, so by default nobody's page changes.
    CallName.SETTLE: {"notebook": ""},
    CallName.STIR: {"happens": False, "again_in_hours": 24.0},
    CallName.ARRIVE: {"happens": False, "again_in_hours": 24.0},
}


class StubBackend:
    name = "stub"

    #: Deterministic hash vectors: identical text matches, but nothing is
    #: semantically near anything else.
    def embed(self, texts, settings: Optional[Settings] = None):
        import hashlib
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = [byte / 127.5 - 1.0 for byte in digest[:32]]
            norm = sum(component * component for component in vector) ** 0.5 or 1.0
            vectors.append([component / norm for component in vector])
        return vectors

    def __init__(self, answers: Optional[Dict[str, object]] = None,
                 script_from_env: bool = False):
        #: keyed by "<call>|<person id>" or "<call>". Values: dict, raw string,
        #: callable taking the Call, or a list cycled in order.
        self.answers: Dict[str, object] = dict(answers or {})
        self.calls: list = []
        self._taken: Dict[str, int] = defaultdict(int)
        # Only the registered default reads ELSEWHERE_STUB.
        script = os.environ.get("ELSEWHERE_STUB") if script_from_env else None
        if script:
            self.answers.update(json.loads(Path(script).read_text(encoding="utf-8")))

    def set(self, call_name: str, answer) -> None:
        self.answers[call_name] = answer

    def complete(self, call: Call, settings: Settings) -> str:
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
            return answer
        return json.dumps(answer, ensure_ascii=False)
