"""The player's mind: whatever the player typed, or nothing at all.

'You are a resident, not an administrator.'  The player mind can only queue
actions that any other person could also take.
"""

from __future__ import annotations

import random
from typing import Dict, Optional

from . import Action, View

_QUEUE: Dict[str, Action] = {}


def queue(person_id: str, action: Action) -> None:
    _QUEUE[person_id] = action


def clear(person_id: str) -> None:
    _QUEUE.pop(person_id, None)


class PlayerMind:
    kind = "player"

    def decide(self, person, view: View, rng: random.Random) -> Action:
        action = _QUEUE.pop(person.id, None)
        if action is None:
            return Action(kind="idle")
        return action
