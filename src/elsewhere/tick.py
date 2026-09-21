"""One phase of one day, and the machinery that decides how many are owed.

Everyone decides at once, then the world resolves what they decided: people
move, and anyone who went to speak to someone still standing in the same place
does. A conversation is an event; everyone who heard it gets their own version
of it through perceive, exactly like the fire.

Nothing here judges anything. The engine only settles what is physically so -
who is where, who could hear whom.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import agents
from .backends import Transcript
from .world.entities import Person
from .world.memories import Trace

PHASE_HOURS = 6.0
CLOSENESS_PER_MEETING = 0.02      # bookkeeping for retrieval, not a feeling


@dataclass
class Talk:
    speaker: str
    listener: str
    line: str
    event_id: str
    drawn_on: Optional[str] = None
    kept: List[Trace] = field(default_factory=list)


@dataclass
class TickReport:
    label: str
    decisions: Dict[str, agents.Decision] = field(default_factory=dict)
    moves: List[Tuple[str, str, str]] = field(default_factory=list)   # who, from, to
    talks: List[Talk] = field(default_factory=list)
    missed: List[Tuple[str, str]] = field(default_factory=list)       # who, sought
    silent: int = 0                                                    # minds that gave nothing


def _meet(world, a: Person, b: Person) -> None:
    for x, y in ((a, b), (b, a)):
        tie = x.tie(y.id)
        tie.last_seen_day = world.day
        tie.closeness = min(1.0, tie.closeness + CLOSENESS_PER_MEETING)


def converse(world, speaker: Person, listener: Person, config,
             transcript: Optional[Transcript] = None) -> Optional[Talk]:
    """Someone says something; everyone in earshot keeps their own version."""
    line, drawn = agents.speak(world, speaker, listener, config, transcript)
    _meet(world, speaker, listener)
    if line is None:
        speaker.last_action = f"sat with {listener.name}, saying little"
        listener.last_action = f"sat with {speaker.name}"
        return None

    place = world.places.get(speaker.place)
    here = [p.id for p in world.people_at(speaker.place)]
    vantage = {pid: (f"face to face with {speaker.name}" if pid == listener.id
                     else f"nearby, within earshot of {speaker.name} and {listener.name}")
               for pid in here if pid != speaker.id}
    event = world.record(
        "conversation",
        f'{speaker.name} said to {listener.name}: "{line}"',
        where=speaker.place,
        who=[speaker.id, listener.id],
        present=here,
        tags=list(drawn.tags) if drawn else ["talk"],
        data={"speaker": speaker.id, "listener": listener.id, "line": line,
              "drawn_on": drawn.id if drawn else None, "vantage": vantage},
    )
    speaker.last_action = f"talked with {listener.name}"
    listener.last_action = f"listened to {speaker.name}"

    # The speaker already has what they said; the people who heard it do not.
    kept = []
    for pid in here:
        if pid == speaker.id:
            continue
        trace = agents.perceive(world, world.people[pid], event, config, transcript)
        if trace is not None:
            kept.append(trace)
    return Talk(speaker.id, listener.id, line, event.id,
                drawn.id if drawn else None, kept)


LAST_ACTION = {"stay": "stayed where they were", "work": "worked",
               "rest": "rested"}


def tick(world, config, transcript: Optional[Transcript] = None) -> TickReport:
    """Live one phase."""
    world.advance_clock()
    report = TickReport(label=world.label())
    minds = sorted((p for p in world.people.values()
                    if p.present and p.mind == "model"), key=lambda p: p.id)

    # 1. Everyone decides, from where they stand, before anyone moves.
    for person in minds:
        decision = agents.act(world, person, config, transcript)
        report.decisions[person.id] = decision
        if not decision.answered:
            report.silent += 1

    # 2. Movement.
    for person in minds:
        d = report.decisions[person.id]
        if d.action == "go" and d.target in world.places:
            before = person.place
            person.place = d.target
            person.last_action = f"walked to {world.places[d.target].name}"
            report.moves.append((person.id, before, d.target))
        elif d.action in LAST_ACTION:
            person.last_action = LAST_ACTION[d.action]

    # 3. Conversations, among people still in the same place.
    engaged = set()
    for person in minds:
        d = report.decisions[person.id]
        if d.action != "talk" or person.id in engaged:
            continue
        other = world.people.get(d.target or "")
        if other is None:
            continue
        if other.place != person.place:
            person.last_action = f"went looking for {other.name}, who had gone"
            report.missed.append((person.id, other.id))
            continue
        if other.id in engaged:
            person.last_action = f"waited to speak with {other.name}"
            continue
        talk = converse(world, person, other, config, transcript)
        engaged |= {person.id, other.id}
        if talk is not None:
            report.talks.append(talk)

    return report


# --------------------------------------------------------------------------
# how much time is owed

def owed_phases(last_tick_at: Optional[float], now: float,
                phase_hours: float = PHASE_HOURS) -> int:
    if last_tick_at is None:
        return 0
    return max(0, int((now - last_tick_at) // (phase_hours * 3600)))


def settle_clock(last_tick_at: Optional[float], now: float, ran: int, owed: int,
                 phase_hours: float = PHASE_HOURS) -> float:
    """Where the wall clock stands after living `ran` of `owed` phases.

    If the backlog was capped, the rest is not lived later - the town simply
    slept through it. Carrying it forward would mean a laptop that sleeps for
    a week wakes up and spends an hour of model calls catching up.
    """
    if last_tick_at is None or ran < owed:
        return now
    return last_tick_at + ran * phase_hours * 3600
