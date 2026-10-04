"""A world on disk, and the lock that allows one tick at a time. The only
module that reads or writes a world's files.

    <world>/
      world.json            clock, places, the map, the world's timer
      configuration.json    which mind answers which call site (`harness.configuration`)
      beings/<id>.json      one file per being, the self-schema they carry included
      chronicle.jsonl       append-only history
      episodes/<id>.jsonl   every episode one being has encoded, append-only
      engrams/<id>.jsonl    every engram one being has consolidated, append-only
      self_schemas/<id>.jsonl every self-schema one being has held, append-only
      transcript/<day>.jsonl every question put to a mind, and its answer
      tick.lock             held while a tick is running
"""

from __future__ import annotations

import fcntl
import json
import shutil
from pathlib import Path
from typing import Callable, Dict, Generic, Iterator, List, Optional, TypeVar

from .. import SCHEMA_VERSION
from ..domain.chronicle import Event
from ..domain.entities import Being, Map, Place
from ..domain.memory import Engram, Episode, SelfSchema
from ..domain.world import World

Item = TypeVar("Item")


class Annals(Generic[Item]):
    """One JSON line per item, appended, never revised; read once, then kept."""

    def __init__(self, path: Path, decode: Callable[[dict], Item]):
        self.path = Path(path)
        self.decode = decode
        self._items: Optional[List[Item]] = None

    def append(self, item: Item) -> Item:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")  # type: ignore[attr-defined]
        if self._items is not None:
            self._items.append(item)
        return item

    def all(self) -> List[Item]:
        if self._items is None:
            self._items = list(self.read())
        return list(self._items)

    def read(self) -> Iterator[Item]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    yield self.decode(json.loads(line))

    def __len__(self) -> int:
        return len(self.all())


class Archive:
    """`domain.world.Records`, kept as JSON lines under one directory."""

    def __init__(self, root) -> None:
        self.root = Path(root)
        self._chronicle: Annals[Event] = Annals(self.root / "chronicle.jsonl", Event.from_dict)
        self._episodes: Dict[str, Annals[Episode]] = {}
        self._engrams: Dict[str, Annals[Engram]] = {}
        self._self_schemas: Dict[str, Annals[SelfSchema]] = {}

    @property
    def chronicle(self) -> Annals[Event]:
        return self._chronicle

    def episodes(self, being_id: str) -> Annals[Episode]:
        if being_id not in self._episodes:
            self._episodes[being_id] = Annals(self.root / "episodes" / f"{being_id}.jsonl",
                                             Episode.from_dict)
        return self._episodes[being_id]

    def engrams(self, being_id: str) -> Annals[Engram]:
        if being_id not in self._engrams:
            self._engrams[being_id] = Annals(self.root / "engrams" / f"{being_id}.jsonl",
                                            Engram.from_dict)
        return self._engrams[being_id]

    def self_schemas(self, being_id: str) -> Annals[SelfSchema]:
        if being_id not in self._self_schemas:
            self._self_schemas[being_id] = Annals(
                self.root / "self_schemas" / f"{being_id}.jsonl", SelfSchema.from_dict)
        return self._self_schemas[being_id]


def create(root) -> World:
    """An empty world at `root`, with whatever records were there cleared away."""
    root = Path(root)
    (root / "chronicle.jsonl").unlink(missing_ok=True)
    (root / "world.json").unlink(missing_ok=True)
    for directory in ("beings", "episodes", "engrams", "self_schemas"):
        shutil.rmtree(root / directory, ignore_errors=True)
    return World(records=Archive(root))


def root(world: World) -> Path:
    if not isinstance(world.records, Archive):
        raise TypeError("this world is not kept on disk")
    return world.records.root


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def save(world: World) -> None:
    directory = root(world)
    atomic_write(directory / "world.json", {
        "schema": SCHEMA_VERSION, "name": world.name, "current": world.current,
        "closed": world.closed,
        "last_tick_at": world.last_tick_at,
        "due_at": world.due_at,
        "places": {place_id: place.to_dict() for place_id, place in world.places.items()},
        "map": world.map.to_dict(),
    })
    for being in world.beings.values():
        atomic_write(directory / "beings" / f"{being.id}.json", being.to_dict())


def load(root) -> World:
    root = Path(root)
    path = root / "world.json"
    if not path.exists():
        raise FileNotFoundError(f"no world at {root}")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    schema = int(metadata.get("schema", 0))
    if schema > SCHEMA_VERSION:
        raise ValueError(f"{root} was written by a newer Elsewhere")
    if schema < SCHEMA_VERSION:
        # No migration on purpose: a schema bump means the world worked
        # differently, and converting would invent history.
        raise ValueError(
            f"{root} was written by Elsewhere schema {schema}, which was a "
            f"differently made world. This one cannot read it.")
    world = World(
        records=Archive(root), name=metadata.get("name", "Elsewhere"),
        current=float(metadata["current"]),
        closed=bool(metadata.get("closed", False)),
        last_tick_at=metadata.get("last_tick_at"),
        due_at=metadata.get("due_at"),
        places={place_id: Place.from_dict(place)
                for place_id, place in metadata.get("places", {}).items()},
        map=Map.from_dict(metadata.get("map", {})),
    )
    for file in sorted((root / "beings").glob("*.json")):
        being = Being.from_dict(json.loads(file.read_text(encoding="utf-8")))
        world.beings[being.id] = being
    return world


def exists(root) -> bool:
    return (Path(root) / "world.json").exists()



class Locked(RuntimeError):
    """Another tick is already running in this world."""


class Lock:
    """One tick at a time, even under cron: an operating-system lock on `tick.lock`,
    released when the holder exits, however it exits."""

    def __init__(self, root):
        self.path = Path(root) / "tick.lock"

    def __enter__(self) -> "Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close()
            raise Locked(f"a tick is already running ({self.path})") from None
        return self

    def __exit__(self, *exception) -> None:
        self.file.close()
