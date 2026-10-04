"""One step of the world: advance to whatever is next due, let the world and
everyone due at that moment decide, and make what they decided as calls on
the MCP server.

Each turn, a mind is asked and its answer is turned into a call
(`harness.being`, `harness.world`), the method named by the harness itself.
The call goes to the server over an in-process MCP session, and the server is
the only thing that changes the world. The world only throws events; whoever
they reach decides, in the same step, what to do about them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, NamedTuple, Optional, Tuple

import anyio
from mcp import Client

from .. import REAL_TIME_PER_VIRTUAL_TIME, server
from ..adapters.backends import Transcript
from ..application import reachability, schedule
from ..domain.entities import Being
from ..domain.world import World
from ..server import Tool
from . import being as being_agent, world as world_agent
from .decision import Decision


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
    reason: str = ""


class Move(NamedTuple):
    being_id: str
    origin: str
    destination: str


class Miss(NamedTuple):
    """A being went looking for another and did not find them."""
    being_id: str
    sought: str


@dataclass
class Stir:
    """The world's turn: what it decided, and what came of it."""
    decision: Decision
    occurrence: Optional[Occurrence] = None
    arrival: Optional[Arrival] = None


@dataclass
class Refusal:
    """A call the server would not make, and why."""
    caller: str                    # a being id, or "world"
    tool: str
    complaint: str


@dataclass
class TickReport:
    label: str
    elapsed: float = 0.0
    #: No timer was set anywhere, so the clock did not move.
    idle: bool = False
    #: The world's turn, if it had one this step.
    stir: Optional[Stir] = None
    #: Each due being's turn, by being id.
    decisions: Dict[str, Decision] = field(default_factory=dict)
    moves: List[Move] = field(default_factory=list)
    departures: List[Departure] = field(default_factory=list)
    talks: List[Talk] = field(default_factory=list)
    missed: List[Miss] = field(default_factory=list)
    #: Who went over their day and laid it down as engrams.
    consolidated: List[str] = field(default_factory=list)
    refusals: List[Refusal] = field(default_factory=list)

    @property
    def unanswered(self) -> int:
        """How many minds gave no usable answer this step."""
        return sum(decision.defaulted for decision in self.decisions.values())


#: Ceiling on model calls per exchange; most end earlier when someone has
#: nothing to say.
TURNS = 4

#: Who the world's own calls are made for, in a report.
WORLD = "world"


@dataclass
class Step:
    """One step's connection to the server, and what it has come to so far."""
    world: World
    configuration: dict
    transcript: Optional[Transcript]
    client: Client
    report: TickReport

    async def call(self, tool: str, arguments: dict, caller: str) -> Optional[dict]:
        """The tool's result, or None when the server refused it."""
        result = await self.client.call_tool(str(tool), arguments)
        text = "".join(getattr(block, "text", "") for block in result.content)
        if result.is_error:
            complaint = text.removeprefix(f"Error executing tool {tool}: ")
            self.report.refusals.append(Refusal(caller, str(tool), complaint))
            return None
        return json.loads(text) if text else {}

    async def stay(self, being: Being, doing: str) -> None:
        await self.call(Tool.STAY, {"being": being.id, "doing": doing}, being.id)


async def converse(step: Step, initiator: Being, respondent: Being) -> Optional[Talk]:
    talk = Talk(between=(initiator.id, respondent.id))
    speaker, listener = initiator, respondent
    for _ in range(TURNS):
        utterance = being_agent.speak(step.world, speaker, listener, step.configuration,
                                      step.transcript)
        if utterance is None:
            break
        said = await step.call(Tool.SAY, {"being": speaker.id, "to": listener.id,
                                          "utterance": utterance}, speaker.id)
        if said is None:
            break
        talk.turns.append(Turn(speaker.id, listener.id, utterance, said["event"]))
        speaker, listener = listener, speaker
        if not speaker.present or speaker.location.place != listener.location.place:
            break

    if not talk.turns:
        await step.stay(initiator, f"sat with {respondent.name}, saying little")
        await step.stay(respondent, f"sat with {initiator.name}")
        return None
    await step.stay(initiator, f"talked with {respondent.name}")
    await step.stay(respondent, f"talked with {initiator.name}")
    return talk


async def live(world: World, configuration, transcript: Optional[Transcript],
               client: Client) -> TickReport:
    before = world.current
    after = schedule.advance_to_next_due(world)
    if after is None:
        return TickReport(label=world.label(), idle=True)
    report = TickReport(label=world.label(), elapsed=after - before)
    step = Step(world, configuration, transcript, client, report)

    # 0. The world first, so what happens to the town can be answered in the
    #    same step and a newcomer lives the day they arrive.
    if schedule.world_due(world):
        decision = world_agent.stir(world, configuration, transcript)
        report.stir = stir = Stir(decision)
        await step.call(Tool.WAIT, {"duration": decision.duration}, WORLD)
        if decision.tool is not None:
            result = await step.call(decision.tool, decision.arguments, WORLD)
            if result is not None and decision.tool == Tool.OCCUR:
                stir.occurrence = Occurrence(result["event"], result["account"])
            elif result is not None and decision.tool == Tool.ADMIT:
                stir.arrival = Arrival(result["being"], result["event"], result["account"])

    # 1. Whoever is due decides, before anyone moves.
    due = [world.beings[being_id] for being_id in sorted(world.beings)
           if schedule.being_due(world, being_id)]
    for being in due:
        decision = being_agent.act(world, being, configuration, transcript)
        report.decisions[being.id] = decision
        await step.call(Tool.WAIT, {"being": being.id, "duration": decision.duration}, being.id)

    # 2. Everything but talk. Departures happen before conversations, so
    #    anyone looking for the leaver finds them gone.
    for being in due:
        decision = report.decisions[being.id]
        if decision.tool == Tool.TALK or decision.tool is None:
            continue
        result = await step.call(decision.tool, decision.arguments, being.id)
        if result is None:
            if decision.tool != Tool.STAY:
                await step.stay(being, decision.doing)     # refused: they stay put
        elif decision.tool == Tool.LEAVE:
            report.departures.append(Departure(being.id, result["event"],
                                               decision.arguments.get("reason", "")))
        elif decision.tool == Tool.MOVE:
            report.moves.append(Move(being.id, result["from"], result["to"]))

    # 3. Conversations, among people still in the same place.
    due = [being for being in due if being.present]
    engaged: set = set()
    for being in due:
        decision = report.decisions[being.id]
        if decision.tool != Tool.TALK or being.id in engaged:
            continue
        addressee = world.beings.get(decision.arguments.get("to", ""))
        if addressee is not None and addressee.id in engaged \
                and addressee in reachability.companions(world, being):
            await step.stay(being, f"waited to speak with {addressee.name}")
            continue
        result = await step.call(Tool.TALK, decision.arguments, being.id)
        if result is None or addressee is None:
            continue
        if not result["met"]:
            report.missed.append(Miss(being.id, addressee.id))
            continue
        talk = await converse(step, being, addressee)
        engaged |= {being.id, addressee.id}
        if talk is not None:
            report.talks.append(talk)

    # 4. Whoever is stopping for the day sleeps on it. Memory, not an action:
    #    it never reaches the server.
    for being in due:
        if not being.present or not report.decisions[being.id].sleep:
            continue
        if being_agent.consolidate(world, being, configuration, transcript):
            report.consolidated.append(being.id)

    return report


def tick(world: World, configuration, transcript: Optional[Transcript] = None) -> TickReport:
    """Lives one step, over a fresh MCP session with this world's server."""
    async def run() -> TickReport:
        async with Client(server.build(world)) as client:
            return await live(world, configuration, transcript, client)
    return anyio.run(run)


def backlog(last_tick_at: Optional[float], now: float) -> float:
    """World time the wall clock says has gone unlived since the last step:
    a world day per real day."""
    if last_tick_at is None:
        return 0.0
    return max(0.0, (now - last_tick_at) / REAL_TIME_PER_VIRTUAL_TIME)


def reconcile(last_tick_at: Optional[float], now: float,
              lived: float, backlog: float) -> float:
    """A capped backlog is dropped rather than carried forward."""
    if last_tick_at is None or lived < backlog:
        return now
    return last_tick_at + lived * REAL_TIME_PER_VIRTUAL_TIME
