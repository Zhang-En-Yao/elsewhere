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

@dataclass
class Turn:
    speaker: str
    listener: str
    utterance: str
    event_id: str


@dataclass
class Talk:
    between: Tuple[str, str]
    turns: List[Turn] = field(default_factory=list)

    @property
    def speaker(self) -> str:
        return self.between[0]

    @property
    def listener(self) -> str:
        return self.between[1]


@dataclass
class Occurrence:
    event_id: str
    account: str


@dataclass
class Arrival:
    being_id: str
    event_id: str
    account: str


@dataclass
class Departure:
    being_id: str
    event_id: str
    because: str = ""


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
    unanswered: int = 0                                                # minds that gave nothing
    occurrence: Optional[Occurrence] = None
    arrival: Optional[Arrival] = None
    departures: List[Departure] = field(default_factory=list)
    #: Who went over their day and wrote their page again.
    settled: List[str] = field(default_factory=list)


#: Ceiling on model calls per exchange; most end earlier when someone has
#: nothing to say.
TURNS = 4


def say(world, speaker: Being, listener: Being, configuration,
         transcript: Optional[Transcript] = None) -> Optional[Turn]:
    utterance = agents.speak(world, speaker, listener, configuration, transcript)
    if utterance is None:
        return None

    here = [being.id for being in world.beings_at(speaker.where.place)]
    viewpoints = {being_id: (f"face to face with {speaker.name}" if being_id == listener.id
                             else f"nearby, within earshot of {speaker.name} and {listener.name}")
                  for being_id in here if being_id != speaker.id}
    # Everyone here is informed, the speaker too, so the next turn is a reply
    # to what was said.
    event = world.record(
        CONVERSATION,
        f'{speaker.name} said to {listener.name}: "{utterance}"',
        place=speaker.where.place,
        involved=[speaker.id, listener.id],
        informed=here,
        data={"speaker": speaker.id, "listener": listener.id, "utterance": utterance,
              "viewpoints": viewpoints},
    )
    return Turn(speaker.id, listener.id, utterance, event.id)


def converse(world, initiator: Being, respondent: Being, configuration,
             transcript: Optional[Transcript] = None) -> Optional[Talk]:
    talk = Talk(between=(initiator.id, respondent.id))
    speaker, listener = initiator, respondent
    for _ in range(TURNS):
        turn = say(world, speaker, listener, configuration, transcript)
        if turn is None:
            break
        talk.turns.append(turn)
        speaker, listener = listener, speaker
        if not speaker.present or speaker.where.place != listener.where.place:
            break

    if not talk.turns:
        initiator.where.log(f"sat with {respondent.name}, saying little")
        respondent.where.log(f"sat with {initiator.name}")
        return None
    initiator.where.log(f"talked with {respondent.name}")
    respondent.where.log(f"talked with {initiator.name}")
    return talk


def tick(world, configuration, transcript: Optional[Transcript] = None) -> TickReport:
    before = world.at
    after = schedule.advance_to_next_due(world)
    if after is None:
        return TickReport(label=world.label(), idle=True)
    report = TickReport(label=world.label(), hours=after - before)

    # 0. Town and road first, so people can respond in the same step.
    if agents.may_stir(world):
        event = agents.stir(world, configuration, transcript)
        if event is not None:
            schedule.rouse(world, event.informed, about=event.involved)
            report.occurrence = Occurrence(event.id, event.account)
    if agents.may_arrive(world):
        event = agents.arrive(world, configuration, transcript)
        if event is not None:
            schedule.rouse(world, event.informed, about=event.involved)
            report.arrival = Arrival(event.involved[0], event.id, event.account)

    # 1. Whoever is due decides, before anyone moves.
    due = schedule.due(world)
    for being in due:
        decision = agents.act(world, being, configuration, transcript)
        report.decisions[being.id] = decision
        if not decision.answered:
            report.unanswered += 1

    # 2. Movement. Departures happen before conversations, so anyone looking
    #    for the leaver finds them gone.
    for being in due:
        decision = report.decisions[being.id]
        if decision.action == Action.LEAVE:
            event = agents.leave(world, being, decision.because)
            schedule.rouse(world, [being_id for being_id in event.informed if being_id != being.id],
                           about=event.informed)
            being.when.left_at = world.at
            being.where.log("took the road out of town")
            report.departures.append(Departure(being.id, event.id, decision.because))
        elif (decision.action == Action.MOVE and decision.target is not None
              and decision.target in world.places):
            origin = being.where.place
            being.where.place = decision.target
            being.where.log(f"went to {world.places[decision.target].name}")
            report.moves.append((being.id, origin, decision.target))
        elif decision.action != Action.TALK:
            being.where.log(decision.doing or "stayed where they were")

    # 3. Conversations, among people still in the same place.
    due = [being for being in due if being.present]
    engaged = set()
    for being in due:
        decision = report.decisions[being.id]
        if decision.action != Action.TALK or being.id in engaged:
            continue
        addressee = world.beings.get(decision.target or "")
        if addressee is None:
            continue
        if not addressee.present or addressee.where.place != being.where.place:
            being.where.log(f"went looking for {addressee.name}, who had gone")
            report.missed.append((being.id, addressee.id))
            continue
        if addressee.id in engaged:
            being.where.log(f"waited to speak with {addressee.name}")
            continue
        talk = converse(world, being, addressee, configuration, transcript)
        engaged |= {being.id, addressee.id}
        if talk is not None:
            report.talks.append(talk)
            # Only the one spoken to is roused; whoever overheard it has it
            # in front of them the next time they look up anyway.
            schedule.rouse(world, [addressee.id], about=[addressee.id])

    # 4. Whoever is stopping for the day goes over it.
    for being in due:
        if not being.present or not report.decisions[being.id].settling:
            continue
        if agents.settle(world, being, configuration, transcript):
            report.settled.append(being.id)

    return report


# wall-clock catch-up: one world hour per real hour
def owed_hours(last_tick_at: Optional[float], now: float) -> float:
    if last_tick_at is None:
        return 0.0
    return max(0.0, (now - last_tick_at) / 3600.0)


def reconcile(last_tick_at: Optional[float], now: float,
                 lived: float, owed: float) -> float:
    """A capped backlog is dropped rather than carried forward."""
    if last_tick_at is None or lived < owed:
        return now
    return last_tick_at + lived * 3600.0
