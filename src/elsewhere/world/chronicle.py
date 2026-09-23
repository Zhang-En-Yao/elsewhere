"""History: append-only, never revised, never consulted by anyone's memory.

One line of JSON per event. This file is the only thing in Elsewhere that
claims to be true.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional


# ---------------------------------------------------------------------------
# What the engine writes, in three kinds. They are not sorted by how large a
# thing was, but by what the sentence is about: something objective, a being's
# existence in the world, or one being reaching another.

#: Objective. Nobody chose it and nobody did it - the town is asked, about
#: once a day, whether anything befalls it, and the answer is usually no.
#: The only category with no one behind it.
OCCURRENCE = "occurrence"

#: A being's existence in the world beginning, and ending. These two are the
#: only categories that change who there is left to ask anything of, which is
#: why the engine counts them rather than reading them.
#:
#: They are not mirror images, whatever the chronicle makes them look like.
#: Coming is the world's doing - the road is asked who is on it, the same way
#: the town is asked whether anything happens. Going is the person's own,
#: answered in `act` like any other thing they decided to do. What makes them
#: one kind is not who caused them but what they change: afterwards there is
#: somebody here who was not, or there is not somebody who was.
ARRIVAL = "arrival"
DEPARTURE = "departure"

#: One being reaching another. There is exactly one way to do that here, and
#: it is words. Standing beside somebody changes what each of them holds
#: about the other - see tick._meet - but it is not an event and nothing is
#: written down about it.
CONVERSATION = "conversation"

#: The two that the road's arithmetic treats as one question: when did who is
#: here last change?
PRESENCE_CHANGES = frozenset({ARRIVAL, DEPARTURE})

#: All four, and not the whole vocabulary, on purpose. A world's own past
#: belongs to that world - this one has a flood, a gathering and a building,
#: another would have a fire or a harvest - and none of that needs the
#: engine's permission to be written down. Only these four carry machinery,
#: and spelling one wrong raises nothing: it quietly stops a gate from ever
#: firing again.
ENGINE_CATEGORIES = frozenset({OCCURRENCE, CONVERSATION}) | PRESENCE_CHANGES


@dataclass
class Event:
    id: str
    at: float                      # hours into the world
    category: str                  # one of ENGINE_CATEGORIES, or whatever this
                                   # world calls a thing that happened in it
    account: str                   # one sentence, in the chronicle's voice and
                                   # nobody else's: what anyone would agree happened
    place: Optional[str] = None

    #: The two lists are not the same list, and the difference is the whole
    #: reason both exist. `involved` is who it happened to - the people the
    #: account is about. `reached` is everyone it got as far as, whether they
    #: were standing in it or heard about it later, and it is the list that
    #: decides who is asked what they made of it.
    involved: List[str] = field(default_factory=list)
    reached: List[str] = field(default_factory=list)

    #: Keys for retrieval, not categories for a reader. These are what a later
    #: memory is matched against to decide whether this is still in reach.
    cues: List[str] = field(default_factory=list)

    #: Whatever only this category needs: who spoke, why they went, where each
    #: person was standing. Nothing here is required and nothing is promised.
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(id=d["id"], at=float(d["at"]), category=d["category"],
                   account=d["account"], place=d.get("place"),
                   involved=list(d.get("involved", [])),
                   reached=list(d.get("reached", [])),
                   cues=list(d.get("cues", [])), data=dict(d.get("data", {})))


class Chronicle:
    """An append-only log on disk, read whole and written one line at a time."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._events: Optional[List[Event]] = None

    def append(self, event: Event) -> Event:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        if self._events is not None:
            self._events.append(event)
        return event

    def all(self) -> List[Event]:
        if self._events is None:
            self._events = list(self._read())
        return self._events

    def _read(self) -> Iterator[Event]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield Event.from_dict(json.loads(line))

    def get(self, event_id: str) -> Optional[Event]:
        for e in self.all():
            if e.id == event_id:
                return e
        return None

    def since(self, day: int) -> List[Event]:
        return [e for e in self.all() if e.day >= day]

    def __len__(self) -> int:
        return len(self.all())
