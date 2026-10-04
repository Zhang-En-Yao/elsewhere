"""Where you stopped reading the chronicle.

This is the observer's, not the world's: nothing but the command line and the window
ever asks it, so it is kept beside the world (`bookmark.json`) and not in it. It is how
many events you had read the last time you looked.
"""

from __future__ import annotations

import json

from ..adapters import storage
from ..domain.world import World


def load(world: World) -> int:
    """How many events of the chronicle you have read; none, if you never looked."""
    path = storage.root(world) / "bookmark.json"
    if not path.exists():
        return 0
    return int(json.loads(path.read_text(encoding="utf-8")).get("read", 0))


def save(world: World, read: int) -> None:
    storage.atomic_write(storage.root(world) / "bookmark.json", {"read": read})
