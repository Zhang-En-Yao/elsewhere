"""Replay a recorded transcript instead of asking anything.

This is what makes a world driven by a stochastic model testable: run it once
against a real model, keep the tape, and every later run of the same scenario
is exact, offline and free. It is the moral equivalent of a random seed for a
system that no longer has one.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, Optional

from . import Call


class ReplayBackend:
    name = "replay"

    def __init__(self, transcript: Path, strict: bool = True):
        self.strict = strict
        self.rows: Dict[str, Deque[dict]] = defaultdict(deque)
        for line in Path(transcript).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("ok"):
                self.rows[f"{row['call']}|{row.get('about', '')}"].append(row)

    def complete(self, call: Call, model: str, temperature: float,
                 extra: Optional[dict] = None) -> str:
        queue = self.rows.get(f"{call.name}|{call.about}")
        if not queue:
            queue = self.rows.get(f"{call.name}|")
        if not queue:
            if self.strict:
                raise LookupError(
                    f"the tape has nothing for {call.name} / {call.about!r}")
            return ""
        return queue.popleft()["raw"]
