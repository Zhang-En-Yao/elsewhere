"""One step of the world: advance to whatever is next due, and let everyone due
at that moment act."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import agents, schedule
from .schemas import Action
from .backends import Transcript
from .world.chronicle import CONVERSATION
from .world.entities import Being
from .world.memories import Memory

@dataclass
class Said:
    speaker: str
    listener: str
    utterance: str
    event_id: str
    kept: List[Memory] = field(default_factory=list)
    reshaped: Optional[Tuple[str, str]] = None      # (was, now)


@dataclass
class Talk:
    between: Tuple[str, str]
    turns: List[Said] = field(default_factory=list)

    @property
    def speaker(self) -> str:
        return self.between[0]

    @property
    def listener(self) -> str:
        return self.between[1]

    @property
    def kept(self) -> List[Memory]:
        return [t for turn in self.turns for t in turn.kept]


@dataclass
class Occurrence:
    event_id: str
    account: str
    kept: List[Memory] = field(default_factory=list)


@dataclass
class Arrival:
    being_id: str
    event_id: str
    account: str
    kept: List[Memory] = field(default_factory=list)


@dataclass
class Departure:
    being_id: str
    event_id: str
    because: str = ""
    kept: List[Memory] = field(default_factory=list)


@dataclass
class TickReport:
    label: str
    hours: float = 0.0
    #: No timer was set anywhere, so the clock did not move.
    idle: bool = False
    decisions: Dict[str, agents.Decision] = field(default_factory=dict)
    moves: List[Tuple[str, str, str]] = field(default_factory=list)   # who, from, to
    talks: List[Talk] = field(default_factory=list)
    missed: List[Tuple[str, str]] = field(default_factory=list)       # who, sought
    silent: int = 0                                                    # minds that gave nothing
    occurrence: Optional[Occurrence] = None
    arrival: Optional[Arrival] = None
    departures: List[Departure] = field(default_factory=list)
    reflections: Dict[str, dict] = field(default_factory=dict)


def meet(world, a: Being, b: Being) -> None:
    for x, y in ((a, b), (b, a)):
        x.who.regard(y.id).last_seen_at = world.at


#: Ceiling on model calls per exchange; most end earlier when someone has
#: nothing to say.
TURNS = 4


def say(world, speaker: Being, listener: Being, configuration,
         transcript: Optional[Transcript] = None) -> Optional[Said]:
    utterance, associated_memory = agents.speak(world, speaker, listener,
                                                configuration, transcript)
    if utterance is None:
        return None

    here = [p.id for p in world.beings_at(speaker.where.place)]
    viewpoints = {pid: (f"face to face with {speaker.name}" if pid == listener.id
                     else f"nearby, within earshot of {speaker.name} and {listener.name}")
               for pid in here if pid != speaker.id}
    event = world.record(
        CONVERSATION,
        f'{speaker.name} said to {listener.name}: "{utterance}"',
        place=speaker.where.place,
        involved=[speaker.id, listener.id],
        informed=here,
        data={"speaker": speaker.id, "listener": listener.id, "utterance": utterance,
              "drawn_on": associated_memory.id if associated_memory else None,
              "viewpoints": viewpoints},
    )

    reshaped = None
    if associated_memory is not None:
        before = associated_memory.account
        if agents.recall(world, speaker, associated_memory, configuration, transcript):
            reshaped = (before, associated_memory.account)

    # The listener perceives the utterance too, so the next turn replies to it.
    kept = []
    for pid in here:
        if pid == speaker.id:
            continue
        memory = agents.perceive(world, world.beings[pid], event, configuration, transcript)
        if memory is not None:
            kept.append(memory)
    return Said(speaker.id, listener.id, utterance, event.id, kept, reshaped)


def converse(world, a: Being, b: Being, configuration,
             transcript: Optional[Transcript] = None) -> Optional[Talk]:
    meet(world, a, b)
    talk = Talk(between=(a.id, b.id))
    speaker, listener = a, b
    for _ in range(TURNS):
        said = say(world, speaker, listener, configuration, transcript)
        if said is None:
            break
        talk.turns.append(said)
        speaker, listener = listener, speaker
        if not speaker.present or speaker.where.place != listener.where.place:
            break

    if not talk.turns:
        a.where.now(f"sat with {b.name}, saying little")
        b.where.now(f"sat with {a.name}")
        return None
    a.where.now(f"talked with {b.name}")
    b.where.now(f"talked with {a.name}")
    return talk


def tick(world, configuration, transcript: Optional[Transcript] = None) -> TickReport:
    was = world.at
    moved = schedule.advance_to_next_due(world)
    if moved is None:
        return TickReport(label=world.label(), idle=True)
    report = TickReport(label=world.label(), hours=world.at - was)

    # 0. Town and road first, so people can respond in the same step.
    if agents.may_stir(world):
        event = agents.stir(world, configuration, transcript)
        if event is not None:
            schedule.rouse(world, event.informed, about=event.involved)
            kept = agents.perceive_all(world, event, configuration, transcript)
            report.occurrence = Occurrence(event.id, event.account, kept)
    if agents.may_arrive(world):
        event = agents.arrive(world, configuration, transcript)
        if event is not None:
            schedule.rouse(world, event.informed, about=event.involved)
            kept = agents.perceive_all(world, event, configuration, transcript)
            report.arrival = Arrival(event.involved[0], event.id, event.account, kept)

    # 1. Whoever is due decides, before anyone moves.
    minds = schedule.due(world)
    for being in minds:
        decision = agents.act(world, being, configuration, transcript)
        report.decisions[being.id] = decision
        if not decision.answered:
            report.silent += 1

    # 2. Movement. Departures happen before conversations, so anyone looking
    #    for the leaver finds them gone.
    for being in minds:
        d = report.decisions[being.id]
        if d.action == Action.LEAVE:
            event = agents.leave(world, being, d.because)
            schedule.rouse(world, [p for p in event.informed if p != being.id],
                           about=event.informed)
            # Perceive before marking her gone, so she is still `present` for
            # her own last look at the town.
            kept = agents.perceive_all(world, event, configuration, transcript)
            being.when.left_at = world.at
            being.where.now("took the road out of town")
            report.departures.append(Departure(being.id, event.id, d.because, kept))
        elif d.action == Action.MOVE and d.target is not None and d.target in world.places:
            before = being.where.place
            being.where.place = d.target
            being.where.now(f"went to {world.places[d.target].name}")
            report.moves.append((being.id, before, d.target))
        elif d.action != Action.TALK:
            being.where.now(d.doing or "stayed where they were")

    # 3. Conversations, among people still in the same place.
    minds = [p for p in minds if p.present]
    engaged = set()
    for being in minds:
        d = report.decisions[being.id]
        if d.action != Action.TALK or being.id in engaged:
            continue
        other = world.beings.get(d.target or "")
        if other is None:
            continue
        if not other.present or other.where.place != being.where.place:
            being.where.now(f"went looking for {other.name}, who had gone")
            report.missed.append((being.id, other.id))
            continue
        if other.id in engaged:
            being.where.now(f"waited to speak with {other.name}")
            continue
        talk = converse(world, being, other, configuration, transcript)
        engaged |= {being.id, other.id}
        if talk is not None:
            report.talks.append(talk)
            # Only the listener is roused through `absorbed`.
            schedule.rouse(world, [k.owner for k in talk.kept] + [other.id],
                           about=[other.id])

    # 4. Whoever is settling reflects on their day.
    for being in minds:
        if not being.present:
            continue
        settling = being.id in report.decisions and report.decisions[being.id].settling
        if not agents.may_reflect(world, being, settling):
            continue
        answer = agents.reflect(world, being, configuration, transcript)
        if answer is not None:
            report.reflections[being.id] = answer

    return report


# wall-clock catch-up: one world hour per real hour
def owed_hours(last_tick_at: Optional[float], now: float) -> float:
    if last_tick_at is None:
        return 0.0
    return max(0.0, (now - last_tick_at) / 3600.0)


def settle_clock(last_tick_at: Optional[float], now: float,
                 lived: float, owed: float) -> float:
    """A capped backlog is dropped rather than carried forward."""
    if last_tick_at is None or lived < owed:
        return now
    return last_tick_at + lived * 3600.0
