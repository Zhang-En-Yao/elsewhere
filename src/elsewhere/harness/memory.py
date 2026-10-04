"""What a being's mind is shown, and what it keeps: the harness's memory.

There is no memory model here, only budgets, a filter, a forgetting curve and
a search somebody else wrote, laid out the way the multi-store model lays out
a mind (Atkinson & Shiffrin 1968), with sleep doing the moving from one store
to the next (complementary learning systems: McClelland, McNaughton &
O'Reilly 1995):

    sensory      percepts             what reached them since they last looked up, shown once
    short-term   short_term           the episodes they encoded since they last consolidated
    long-term    Engram               gists, laid down by `consolidate` each night
    self         Identity.self_schema      who they take themselves to be, rewritten each night
    retrieved    retrieve             one engram the moment points at, fragmented by time

Writing any of it is the mind's: `encode` stores the episode an answer
carried, `store` what `consolidate` made of the day. None of this goes
through the server - it is what a mind holds, not what the world does.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional, Tuple

from .. import VIRTUAL_TIME_PER_DAY
from ..adapters import retrieval
from ..adapters.backends import embed
from ..domain import perspective
from ..domain.chronicle import Event
from ..domain.entities import Being
from ..domain.memory import Engram, Episode, SelfSchema
from ..domain.world import World

#: Memory spans (Miller 1956) for one prompt: how many new events are put in
#: front of somebody at once (older unseen ones are gone before they ever saw
#: them), and how many of the episodes in their short-term store.
SENSORY_SPAN = 12
SHORT_TERM_SPAN = 12


def percepts(world: World, being: Being) -> List[Tuple[Event, str]]:
    """What reached this person since they last looked up, each with where
    they stood, oldest first. The only time anybody is shown the chronicle."""
    reachable = [event for event in world.chronicle.all()[being.clock.perceived_through:]
                 if being.id in event.informed]
    return [(event, perspective.of(world, being, event))
            for event in reachable[-SENSORY_SPAN:]]


def short_term(world: World, being: Being) -> List[Episode]:
    """What they have encoded since they last consolidated, in their own
    words."""
    return world.episodes(being.id).all()[being.clock.consolidated_through:][-SHORT_TERM_SPAN:]


def vectorize(configuration, text: str) -> List[float]:
    """Empty when no embedder is configured or it fails; retrieval then ranks
    by BM25 alone."""
    settings = configuration.get("embed")
    if settings is None or not text.strip():
        return []
    vectors = embed([text], settings)
    return vectors[0] if vectors else []


def embedder_of(configuration) -> str:
    settings = configuration.get("embed")
    return f"{settings.backend}/{settings.model}" if settings is not None else ""


def retrieve(world: World, being: Being, configuration, cue: str) -> Optional[Engram]:
    """One engram the moment points at, with only the gists time has left it.
    Today is never among them: it is in the short-term store, in front of
    them already."""
    found = retrieval.search(world.engrams(being.id).all(), cue,
                             vectorize(configuration, cue), embedder_of(configuration))
    if found is None:
        return None
    return retrieval.fragment(found, (world.current - found.at) / VIRTUAL_TIME_PER_DAY)


def encode(world: World, being: Being, answer: dict,
           percepts: List[Tuple[Event, str]]) -> None:
    """Write down what they said they encoded, and mark what they were shown
    as perceived either way: nothing is shown twice."""
    encoded = (answer.get("encoded") or "").strip()
    if encoded:
        world.episodes(being.id).append(Episode(
            at=world.current, account=encoded, event_ids=[event.id for event, _ in percepts]))
    being.clock.perceived_through = len(world.chronicle)


def store(world: World, being: Being, configuration, self_schema: SelfSchema,
          engrams: List[Engram]) -> None:
    """What one night made of the day: the engrams, placed so they can be
    found by meaning, and the self-schema they carry from now on. Every
    version is kept, and the day it was made from is consolidated."""
    episodes = len(world.episodes(being.id))
    positions = list(range(episodes - len(short_term(world, being)), episodes))
    for engram in engrams:
        world.engrams(being.id).append(replace(
            engram, at=world.current, embedding=vectorize(configuration, engram.text),
            embedded_by=embedder_of(configuration), _episode_positions=positions))
    being.identity.self_schema = replace(self_schema, at=world.current)
    being.clock.consolidated_through = episodes
    world.self_schemas(being.id).append(being.identity.self_schema)
