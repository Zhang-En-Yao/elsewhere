"""What one person holds: episodes as moments reach them, engrams and a
self-schema each night.

An episode is what somebody encoded of a moment, in their own words, written in
the same answer as what they did or said next (`act`, `speak`). The episodes
since they last consolidated are their short-term store; overnight `consolidate`
turns them into engrams - a few broken-off pieces of what happened, each weighted -
and rewrites the self-schema they carry. Every episode, engram and version of
the self-schema is kept: engrams are what `retrieval` searches, and the rest is
everything a person ever held, lost only to them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Sequence


@dataclass
class Episode:
    """Episodic memory (Tulving 1972): one moment, as they encoded it."""

    at: float  # time since the world began
    account: str

    #: The events that had just reached them when they encoded it, if any.
    event_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        return cls(
            at=float(data["at"]), account=data["account"], event_ids=list(data.get("event_ids", []))
        )


@dataclass
class Gist:
    """A gist trace (Brainerd & Reyna 1990, fuzzy-trace theory): one broken-off
    piece of what happened, kept as a short proposition (Kintsch & van Dijk
    1978) - who, what, to what - while the wording it came in fades."""

    proposition: str
    #: 0 to 1: how much of the memory hangs on this piece. Set by the mind in
    #: `consolidate`; the most heavily weighted are the last to be forgotten.
    weight: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Gist":
        return cls(proposition=data["proposition"], weight=float(data.get("weight", 0.0)))


@dataclass
class Engram:
    """A memory trace (Semon 1904; Josselyn & Tonegawa 2020): what one night's
    consolidation kept of something, as gists and nothing else."""

    at: float  # time since the world began, when it was consolidated
    gists: List[Gist] = field(default_factory=list)

    #: Used only by `retrieval`; empty if no embedder could be reached.
    embedding: List[float] = field(default_factory=list)
    #: Which embedder placed it: vectors from two embedders are not comparable.
    embedded_by: str = ""
    #: Where in their `episodes` the night that laid it down was looking. Kept
    #: only so a person looking at the world can trace it back (`episodes_of_engram`);
    #: never shown to the being, never searched, never part of the trace.
    _episode_positions: List[int] = field(default_factory=list)

    @property
    def text(self) -> str:
        """What `retrieval` searches and embeds: every gist, in the order laid down."""
        return " ".join(gist.proposition for gist in self.gists)

    def to_dict(self) -> dict:
        data = asdict(self)
        # Rounded: full precision costs ~14KB per engram for nothing.
        data["embedding"] = [round(component, 5) for component in self.embedding]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Engram":
        return cls(
            at=float(data["at"]),
            gists=[Gist.from_dict(gist) for gist in data.get("gists", [])],
            embedding=[float(component) for component in data.get("embedding", [])],
            embedded_by=data.get("embedded_by", ""),
            _episode_positions=[int(position) for position in data.get("_episode_positions", [])],
        )


@dataclass
class Impression:
    """Impression formation (Asch 1946): how they see one other person."""

    being: str  # the other person's name, as they know it
    impression: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Impression":
        return cls(being=data.get("being", ""), impression=data.get("impression", ""))


@dataclass
class SelfSchema:
    """Self-schema (Markus 1977): who they take themselves to be, rewritten
    whole each night by `consolidate`, at most `SELF_SCHEMA_CHARACTERS` long.
    Every version is kept, each with the time it was written."""

    at: float = 0.0  # time since the world began, when it was written
    #: How they talk (Bloch 1948). Kept as its own labelled line: folded into
    #: the biography it measured as no effect.
    idiolect: str = ""
    #: What they are like (Allport 1937): the dispositions they act from,
    #: whatever the day. Changes slower than anything else here.
    traits: List[str] = field(default_factory=list)
    #: Current concerns (Klinger 1975): what they are after and have not got.
    concerns: List[str] = field(default_factory=list)
    #: The assumptive world (Janoff-Bulman 1992): what they take to be true.
    assumptions: List[str] = field(default_factory=list)
    impressions: List[Impression] = field(default_factory=list)

    @property
    def characters(self) -> int:
        """How much of the budget it takes: every word they wrote, counted."""
        return (
            len(self.idiolect)
            + sum(len(trait) for trait in self.traits)
            + sum(len(concern) for concern in self.concerns)
            + sum(len(assumption) for assumption in self.assumptions)
            + sum(
                len(impression.being) + len(impression.impression)
                for impression in self.impressions
            )
        )

    @property
    def empty(self) -> bool:
        return self.characters == 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SelfSchema":
        return cls(
            at=float(data.get("at", 0.0)),
            idiolect=data.get("idiolect", ""),
            traits=list(data.get("traits", [])),
            concerns=list(data.get("concerns", [])),
            assumptions=list(data.get("assumptions", [])),
            impressions=[
                Impression.from_dict(impression) for impression in data.get("impressions", [])
            ],
        )


def episodes_of_engram(episodes: Sequence[Episode], engram: Engram) -> List[Episode]:
    """The episodes the night that laid an engram down went over."""
    return [
        episodes[position] for position in engram._episode_positions if position < len(episodes)
    ]


def episodes_of_event(episodes: Sequence[Episode], event_id: str) -> List[Episode]:
    """The episodes somebody encoded of one event."""
    return [episode for episode in episodes if event_id in episode.event_ids]
