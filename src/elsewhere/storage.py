"""Saving a world, so that it can be left and returned to."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import SCHEMA_VERSION
from .world import World

DEFAULT_PATH = Path("world.json")


def save(world: World, path: os.PathLike | str = DEFAULT_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = world.to_dict()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def load(path: os.PathLike | str = DEFAULT_PATH) -> World:
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    schema = int(data.get("schema", 0))
    if schema > SCHEMA_VERSION:
        raise ValueError(
            f"{path} was written by a newer Elsewhere (schema {schema} > {SCHEMA_VERSION})"
        )
    return World.from_dict(data)


def exists(path: os.PathLike | str = DEFAULT_PATH) -> bool:
    return Path(path).exists()
