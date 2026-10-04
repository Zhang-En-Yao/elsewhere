"""The being agent: the three questions put to one person's mind, and each
answer turned into what it comes to.

`act` comes to one tool call on the server (stay, move, talk or leave) and a
timer; `speak` to one line, which the step says with `Tool.SAY`;
`consolidate` to engrams and a new self-schema, which are memory and never
reach the server. None of these
decide anything themselves: a mind that gives nothing usable had nothing,
which is allowed.
"""

from __future__ import annotations

from typing import Optional

from ..adapters.backends import Call, Transcript, ask, get as get_backend
from ..application import reachability
from ..domain.entities import Being
from ..domain.memory import Engram, Gist, Impression, SelfSchema
from ..domain.world import World
from ..server import Tool
from . import memory, prompts, schemas
from .decision import Decision, duration_of
from .schemas import CallName


def time_of(world: World) -> str:
    light = "light" if world.daylight else "dark"
    return f"{world.clock} and {light}, {world.season}, {world.date}"


def check(name: CallName):
    return lambda data: schemas.validate(name, data)


def act(
    world: World, being: Being, configuration, transcript: Optional[Transcript] = None
) -> Decision:
    settings = configuration[CallName.ACT]
    place = world.places.get(being.location.place)
    destinations = reachability.destinations(world, being)
    companions = reachability.companions(world, being)
    percepts = memory.percepts(world, being)
    cue = " ".join(
        [event.account for event, _ in percepts]
        + ([f"{place.name}. {place.description}"] if place else [])
    )

    can_leave = reachability.may_leave(world, being)
    call = Call(
        name=CallName.ACT,
        system=prompts.ACT_SYSTEM,
        user=prompts.act_user(
            being,
            time_of(world),
            place,
            companions,
            [destination.name for destination in destinations],
            percepts,
            memory.short_term(world, being),
            memory.retrieve(world, being, configuration, cue),
            current=world.current,
            home=(
                world.places[being.location.home].name
                if being.location.home in world.places
                else ""
            ),
            may_leave=can_leave,
        ),
        schema=schemas.act_grammar(
            [destination.name for destination in destinations],
            [companion.name for companion in companions],
            may_leave=can_leave,
        ),
        mind=being.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript, check(CallName.ACT))
    if answer is None:
        # No usable answer leaves no timer either; see
        # `schedule.advance_to_next_due`.
        return Decision(Tool.STAY, {"being": being.id}, defaulted=True)
    memory.encode(world, being, answer, percepts)

    action = answer.get("action") or ""
    name = (answer.get("target") or "").strip()
    reason = (answer.get("reason") or "").strip()
    doing = (answer.get("doing") or "").strip()
    decision = Decision(
        Tool.STAY,
        {"being": being.id, "doing": doing},
        duration=duration_of(answer),
        reason=reason,
        doing=doing,
        sleep=bool(answer.get("sleep")),
    )

    # A move or a talk that names nobody real, or a leave from where there is
    # no road, is only reachable with a lenient backend; the grammar forbids
    # it, and what was not offered is not called.
    if action == Tool.LEAVE and can_leave:
        decision.tool, decision.arguments = Tool.LEAVE, {"being": being.id, "reason": reason}
    elif action == Tool.MOVE:
        destination = next(
            (destination for destination in destinations if destination.name == name), None
        )
        if destination is not None:
            decision.tool, decision.arguments = Tool.MOVE, {"being": being.id, "to": destination.id}
    elif action == Tool.TALK:
        companion = next((companion for companion in companions if companion.name == name), None)
        if companion is not None:
            decision.tool, decision.arguments = Tool.TALK, {"being": being.id, "to": companion.id}
    return decision


def speak(
    world: World,
    speaker: Being,
    listener: Being,
    configuration,
    transcript: Optional[Transcript] = None,
) -> Optional[str]:
    """What they say, or None when they have nothing."""
    settings = configuration[CallName.SPEAK]
    place = world.places.get(speaker.location.place)
    percepts = memory.percepts(world, speaker)
    cue = " ".join([listener.name] + [event.account for event, _ in percepts])
    call = Call(
        name=CallName.SPEAK,
        system=prompts.SPEAK_SYSTEM,
        user=prompts.speak_user(
            speaker,
            listener,
            time_of(world),
            place.name if place else "somewhere",
            percepts,
            memory.short_term(world, speaker),
            memory.retrieve(world, speaker, configuration, cue),
            current=world.current,
        ),
        schema=schemas.grammar(CallName.SPEAK),
        mind=speaker.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript, check(CallName.SPEAK))
    if answer is None:
        return None
    memory.encode(world, speaker, answer, percepts)
    utterance = (answer.get("utterance") or "").strip().strip('"').strip()
    return utterance or None


def consolidate(
    world: World, being: Being, configuration, transcript: Optional[Transcript] = None
) -> bool:
    """Their sleep goes over what they encoded today, in their own episodes:
    lays it down as engrams and rewrites the self-schema they carry into
    tomorrow. Not a question put to them - they are asleep - but their mind's
    all the same. Without a usable answer nothing changes, so the same day is
    gone over next time."""
    settings = configuration[CallName.CONSOLIDATE]
    today = memory.short_term(world, being)
    cue = " ".join([episode.account for episode in today] + being.activity.doings)
    call = Call(
        name=CallName.CONSOLIDATE,
        system=prompts.CONSOLIDATE_SYSTEM,
        user=prompts.consolidate_user(
            being,
            time_of(world),
            today,
            doings=being.activity.doings,
            retrieved=memory.retrieve(world, being, configuration, cue),
            current=world.current,
        ),
        schema=schemas.grammar(CallName.CONSOLIDATE),
        mind=being.id,
    )
    answer = ask(
        get_backend(settings.backend), call, settings, transcript, check(CallName.CONSOLIDATE)
    )
    if answer is None:
        return False
    written = answer["self_schema"]
    self_schema = SelfSchema(
        idiolect=written["idiolect"].strip(),
        traits=[line.strip() for line in written["traits"] if line.strip()],
        concerns=[line.strip() for line in written["concerns"] if line.strip()],
        assumptions=[line.strip() for line in written["assumptions"] if line.strip()],
        impressions=[
            Impression(
                being=impression["being"].strip(), impression=impression["impression"].strip()
            )
            for impression in written["impressions"]
            if impression["impression"].strip()
        ],
    )
    if self_schema.empty:
        return False
    # Weights outside 0 to 1 are only reachable without a grammar; held to it.
    engrams = [
        Engram(
            at=world.current,
            gists=[
                Gist(
                    proposition=laid["proposition"].strip(),
                    weight=min(1.0, max(0.0, laid["weight"])),
                )
                for laid in engram["gists"]
                if laid["proposition"].strip()
            ],
        )
        for engram in answer["engrams"]
    ]
    memory.store(
        world, being, configuration, self_schema, [engram for engram in engrams if engram.gists]
    )
    return True
