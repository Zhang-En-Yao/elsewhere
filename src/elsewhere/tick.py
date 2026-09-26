"""One step of the world, and the machinery that decides how many are owed.

A step is not a length of time. The world advances to whatever is next due - a
person whose two hours of mending are up, a town that said to ask it again in
a fortnight - and everyone due at that moment decides at once, before anyone
moves. The grain of the simulation is therefore set by the people in it and
not by this file.

What this file does is settle what is physically so. People move; anyone who
went to speak to somebody still standing in the same place does. A conversation
is an exchange of events, and everyone who heard one gets their own version of
it through `perceive`, exactly as they would an event of any other kind - and
being spoken to wakes them, whatever they had meant to be doing for the next
four hours.

Nothing here judges anything else: who is where, who could hear whom, and what
time it is by the time anybody is asked again.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import agents, schedule, schemas
from .backends import Transcript
from .world.chronicle import CONVERSATION
from .world.entities import Being
from .world.memories import Memory



@dataclass
class Said:
    """One thing said out loud, and what it left in whoever heard it."""
    speaker: str
    listener: str
    line: str
    event_id: str
    kept: List[Memory] = field(default_factory=list)
    reshaped: Optional[Tuple[str, str]] = None      # (was, now) if the telling changed it


@dataclass
class Talk:
    """An exchange: turns, alternating, until one of them has nothing."""
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
    #: How far the clock moved to get here. Whatever the next thing due was,
    #: which is different every step and is nobody's decision but theirs.
    hours: float = 0.0
    #: True when nothing in the world had a timer set: every mind declined to
    #: say when it wanted to be asked again, so the engine has nothing to go
    #: on and says so rather than choosing an hour for them.
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


def _meet(world, a: Being, b: Being) -> None:
    """Both of them now know when this was. Nothing else is inferred from it."""
    for x, y in ((a, b), (b, a)):
        x.who.regard(y.id).last_seen_at = world.at


#: How many things may be said in one exchange before the engine stops it.
#: A budget on model calls, the same kind of number as `CONTEXT_MEMORIES`, and
#: not a claim that a conversation is four sentences long. An exchange ends
#: before this whenever somebody has nothing to say, which is what usually
#: ends one.
TURNS = 4


def _say(world, speaker: Being, listener: Being, configuration,
         transcript: Optional[Transcript] = None) -> Optional[Said]:
    """One turn: somebody says a thing, and everyone in earshot keeps a version."""
    line, drawn = agents.speak(world, speaker, listener, configuration, transcript)
    if line is None:
        return None

    here = [p.id for p in world.beings_at(speaker.where.place)]
    vantage = {pid: (f"face to face with {speaker.name}" if pid == listener.id
                     else f"nearby, within earshot of {speaker.name} and {listener.name}")
               for pid in here if pid != speaker.id}
    event = world.record(
        CONVERSATION,
        f'{speaker.name} said to {listener.name}: "{line}"',
        place=speaker.where.place,
        involved=[speaker.id, listener.id],
        reached=here,
        data={"speaker": speaker.id, "listener": listener.id, "line": line,
              "drawn_on": drawn.id if drawn else None, "vantage": vantage},
    )

    # Telling it changes it. The speaker's own memory comes back reshaped.
    reshaped = None
    if drawn is not None:
        before = drawn.account
        if agents.recall(world, speaker, drawn, configuration, transcript):
            reshaped = (before, drawn.account)

    # The speaker already has what they said; the people who heard it do not -
    # and the person they said it to is one of those people, which is what
    # makes the next turn a reply to this one rather than a second opening.
    kept = []
    for pid in here:
        if pid == speaker.id:
            continue
        memory = agents.perceive(world, world.beings[pid], event, configuration, transcript)
        if memory is not None:
            kept.append(memory)
    return Said(speaker.id, listener.id, line, event.id, kept, reshaped)


def converse(world, a: Being, b: Being, configuration,
             transcript: Optional[Transcript] = None) -> Optional[Talk]:
    """An exchange between two people, and what it leaves in everyone in earshot.

    A turn ends the exchange by having nothing to say, which is how most
    conversations end; `TURNS` is only the ceiling. Each turn is an event in
    its own right, so what a listener replies to is the memory `perceive` just
    wrote them of the line before - which is why somebody can answer what they
    thought they heard rather than what was said.
    """
    _meet(world, a, b)
    talk = Talk(between=(a.id, b.id))
    speaker, listener = a, b
    for _ in range(TURNS):
        said = _say(world, speaker, listener, configuration, transcript)
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
    """Live one step of the world: up to whatever is next due, and no further."""
    was = world.at
    moved = schedule.advance_to_next_due(world)
    if moved is None:
        # Nothing anywhere has a timer: every mind declined to say when it
        # wanted to be asked again, and the engine does not pick an hour on
        # their behalf.
        return TickReport(label=world.label(), idle=True)
    report = TickReport(label=world.label(), hours=world.at - was)

    # 0. First, whatever happens to the town rather than in it - so people
    #    can respond to it in the same step, and so somebody who has just
    #    walked up the road lives the day they arrived. Each keeps its own
    #    timer, set in its own answer.
    if agents.may_direct(world):
        event = agents.direct(world, configuration, transcript)
        if event is not None:
            # It wakes whoever it happened near, and pulls whoever it
            # happened *to* out of whatever they said they were deep in.
            schedule.rouse(world, event.reached, about=event.involved)
            kept = agents.perceive_all(world, event, configuration, transcript)
            report.occurrence = Occurrence(event.id, event.account, kept)
    if agents.may_arrive(world):
        event = agents.arrive(world, configuration, transcript)
        if event is not None:
            schedule.rouse(world, event.reached, about=event.involved)
            kept = agents.perceive_all(world, event, configuration, transcript)
            report.arrival = Arrival(event.involved[0], event.id, event.account, kept)

    # 1. Whoever is due decides, from where they stand, before anyone moves.
    #    Not everybody, and not because six hours went by: a person who said
    #    they would be asleep for eight is asleep for eight, unless something
    #    above woke them.
    minds = schedule.due(world)
    for being in minds:
        decision = agents.act(world, being, configuration, transcript)
        report.decisions[being.id] = decision
        if not decision.answered:
            report.silent += 1

    # 2. Movement, and whoever is not coming back. Someone who leaves is gone
    #    before the conversations, so a person who went to find them finds the
    #    road instead.
    for being in minds:
        d = report.decisions[being.id]
        if d.action == schemas.LEAVE:
            event, kept = agents.depart(world, being, d.because, configuration, transcript)
            schedule.rouse(world, [p for p in event.reached if p != being.id],
                           about=event.reached)
            report.departures.append(Departure(being.id, event.id, d.because, kept))
        elif d.action == "go" and d.target is not None and d.target in world.places:
            before = being.where.place
            being.where.place = d.target
            being.where.now(f"walked to {world.places[d.target].name}")
            report.moves.append((being.id, before, d.target))
        elif d.action != "talk":
            # Nothing moved, so what this looked like is whatever they said it
            # looked like. The engine has nothing to add and does not try.
            being.where.now(d.doing or "stayed where they were")

    # 3. Conversations, among people still in the same place. Somebody who is
    #    spoken to is spoken to whether or not their own hour had come round.
    minds = [p for p in minds if p.present]
    engaged = set()
    for being in minds:
        d = report.decisions[being.id]
        if d.action != "talk" or being.id in engaged:
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
            # Being talked to is the commonest reason in a town to stop
            # doing what you were doing - but only for the person who was
            # talked to. Somebody across the yard who said they were absorbed
            # goes on with it.
            schedule.rouse(world, [k.owner for k in talk.kept] + [other.id],
                           about=[other.id])

    # 4. Whoever said they were stopping goes over the day they are stopping
    #    at the end of. Not everyone at once, and not because of the hour.
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


# --------------------------------------------------------------------------
# how much time is owed
#
# A day here is a day there: the one thing about this world's clock that is a
# promise to the person running it rather than a detail. The world owes however
# many *hours* the wall clock has moved since it was last lived, and pays them
# off in whatever steps the people in it asked for.


def owed_hours(last_tick_at: Optional[float], now: float) -> float:
    """How much world time the wall clock says has gone unlived."""
    if last_tick_at is None:
        return 0.0
    return max(0.0, (now - last_tick_at) / 3600.0)


def settle_clock(last_tick_at: Optional[float], now: float,
                 lived: float, owed: float) -> float:
    """Where the wall clock stands after living `lived` of `owed` hours.

    If the backlog was capped, the rest is not lived later - the town simply
    slept through it. Carrying it forward would mean a laptop that sleeps for
    a week wakes up and spends an hour of model calls catching up.
    """
    if last_tick_at is None or lived < owed:
        return now
    return last_tick_at + lived * 3600.0
