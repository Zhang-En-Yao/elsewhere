"""One step of the world, and the machinery that decides how many are owed.

Everyone decides at once, then the world resolves what they decided: people
move, and anyone who went to speak to someone still standing in the same place
does. A conversation is an event; everyone who heard it gets their own version
of it through perceive, exactly like the flood.

Nothing here judges anything. The engine only settles what is physically so -
who is where, who could hear whom.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import agents, schemas
from .backends import Transcript
from .world.chronicle import CONVERSATION
from .world.entities import Being
from .world.memories import Trace

#: How much world time one step covers. Everyone decides once per step, so
#: this is the grain of the simulation - not a named part of the day, just how
#: far the clock moves before anybody is asked anything again.
STEP_HOURS = 6.0


@dataclass
class Talk:
    speaker: str
    listener: str
    line: str
    event_id: str
    kept: List[Trace] = field(default_factory=list)
    reshaped: Optional[Tuple[str, str]] = None      # (was, now) if the telling changed it


@dataclass
class Occurrence:
    event_id: str
    account: str
    kept: List[Trace] = field(default_factory=list)


@dataclass
class Arrival:
    being_id: str
    event_id: str
    account: str
    kept: List[Trace] = field(default_factory=list)


@dataclass
class Departure:
    being_id: str
    event_id: str
    because: str = ""
    kept: List[Trace] = field(default_factory=list)


@dataclass
class TickReport:
    label: str
    decisions: Dict[str, agents.Decision] = field(default_factory=dict)
    moves: List[Tuple[str, str, str]] = field(default_factory=list)   # who, from, to
    talks: List[Talk] = field(default_factory=list)
    missed: List[Tuple[str, str]] = field(default_factory=list)       # who, sought
    silent: int = 0                                                    # minds that gave nothing
    occurrence: Optional[Occurrence] = None
    arrival: Optional[Arrival] = None
    departures: List[Departure] = field(default_factory=list)
    reflections: Dict[str, dict] = field(default_factory=dict)


def _meet(world, a: Being, b: Being) -> None:
    """Both of them now know when this was. Nothing else is inferred from it."""
    for x, y in ((a, b), (b, a)):
        x.regard(y.id).last_seen_at = world.at


def converse(world, speaker: Being, listener: Being, config,
             transcript: Optional[Transcript] = None) -> Optional[Talk]:
    """Someone says something; everyone in earshot keeps their own version."""
    line, drawn = agents.speak(world, speaker, listener, config, transcript)
    _meet(world, speaker, listener)
    if line is None:
        speaker.doing = f"sat with {listener.name}, saying little"
        listener.doing = f"sat with {speaker.name}"
        return None

    place = world.places.get(speaker.place)
    here = [p.id for p in world.beings_at(speaker.place)]
    vantage = {pid: (f"face to face with {speaker.name}" if pid == listener.id
                     else f"nearby, within earshot of {speaker.name} and {listener.name}")
               for pid in here if pid != speaker.id}
    event = world.record(
        CONVERSATION,
        f'{speaker.name} said to {listener.name}: "{line}"',
        place=speaker.place,
        involved=[speaker.id, listener.id],
        reached=here,
        data={"speaker": speaker.id, "listener": listener.id, "line": line,
              "drawn_on": drawn.id if drawn else None, "vantage": vantage},
    )
    speaker.doing = f"talked with {listener.name}"
    listener.doing = f"listened to {speaker.name}"

    # Telling it changes it. The speaker's own memory comes back reshaped.
    reshaped = None
    if drawn is not None:
        before = drawn.trace
        if agents.recall(world, speaker, drawn, config, transcript):
            reshaped = (before, drawn.trace)

    # The speaker already has what they said; the people who heard it do not.
    kept = []
    for pid in here:
        if pid == speaker.id:
            continue
        trace = agents.perceive(world, world.beings[pid], event, config, transcript)
        if trace is not None:
            kept.append(trace)
    return Talk(speaker.id, listener.id, line, event.id, kept, reshaped)


def tick(world, config, transcript: Optional[Transcript] = None,
         hours: float = STEP_HOURS) -> TickReport:
    """Live one step of the world."""
    world.advance(hours)
    report = TickReport(label=world.label())

    # 0. First, whatever happens to the town rather than in it - so people can
    #    respond to it in the same step, and so somebody who has just walked
    #    up the road gets a life today instead of standing there until the
    #    engine next feels like asking. Both are rates now, not hours.
    if agents.may_direct(world):
        event = agents.direct(world, config, transcript)
        if event is not None:
            kept = agents.perceive_all(world, event, config, transcript)
            report.occurrence = Occurrence(event.id, event.account, kept)
    if agents.may_arrive(world):
        event = agents.arrive(world, config, transcript)
        if event is not None:
            kept = agents.perceive_all(world, event, config, transcript)
            report.arrival = Arrival(event.involved[0], event.id, event.account, kept)

    minds = sorted((p for p in world.beings.values()
                    if p.present and p.mind == "model"), key=lambda p: p.id)

    # 1. Everyone decides, from where they stand, before anyone moves.
    for being in minds:
        decision = agents.act(world, being, config, transcript)
        report.decisions[being.id] = decision
        if not decision.answered:
            report.silent += 1

    # 2. Movement, and whoever is not coming back. Someone who leaves is gone
    #    before the conversations, so a person who went to find them finds the
    #    road instead.
    for being in minds:
        d = report.decisions[being.id]
        if d.action == schemas.LEAVE:
            event, kept = agents.depart(world, being, d.because, config, transcript)
            report.departures.append(Departure(being.id, event.id, d.because, kept))
        elif d.action == "go" and d.target is not None and d.target in world.places:
            before = being.place
            being.place = d.target
            being.doing = f"walked to {world.places[d.target].name}"
            report.moves.append((being.id, before, d.target))
        elif d.action != "talk":
            # Nothing moved, so what this looked like is whatever they said it
            # looked like. The engine has nothing to add and does not try.
            being.doing = d.doing or "stayed where they were"

    # 3. Conversations, among people still in the same place.
    minds = [p for p in minds if p.present]
    engaged = set()
    for being in minds:
        d = report.decisions[being.id]
        if d.action != "talk" or being.id in engaged:
            continue
        other = world.beings.get(d.target or "")
        if other is None:
            continue
        if not other.present or other.place != being.place:
            being.doing = f"went looking for {other.name}, who had gone"
            report.missed.append((being.id, other.id))
            continue
        if other.id in engaged:
            being.doing = f"waited to speak with {other.name}"
            continue
        talk = converse(world, being, other, config, transcript)
        engaged |= {being.id, other.id}
        if talk is not None:
            report.talks.append(talk)

    # 4. Whoever is a day on from their own last reckoning goes over it. Not
    #    everyone at once, and not because it got dark.
    for being in minds:
        if not agents.may_reflect(world, being):
            continue
        answer = agents.reflect(world, being, config, transcript)
        if answer is not None:
            report.reflections[being.id] = answer

    return report


# --------------------------------------------------------------------------
# how much time is owed

def owed_steps(last_tick_at: Optional[float], now: float,
               step_hours: float = STEP_HOURS) -> int:
    if last_tick_at is None:
        return 0
    return max(0, int((now - last_tick_at) // (step_hours * 3600)))


def settle_clock(last_tick_at: Optional[float], now: float, ran: int, owed: int,
                 step_hours: float = STEP_HOURS) -> float:
    """Where the wall clock stands after living `ran` of `owed` steps.

    If the backlog was capped, the rest is not lived later - the town simply
    slept through it. Carrying it forward would mean a laptop that sleeps for
    a week wakes up and spends an hour of model calls catching up.
    """
    if last_tick_at is None or ran < owed:
        return now
    return last_tick_at + ran * step_hours * 3600
