"""The world agent: the one question put to the world itself - its weather,
its accidents, and the road into it - and its answer turned into what it
comes to.

It is not a being. It sees what anyone could see (where people are, what they
have been doing, who has gone, what has happened lately) and never inside
anyone; it has no episodes and no self-schema. Its answer comes to at most
one tool call on the server - `occur` or `admit` - and its one timer.

It never acts for a being. What it does is throw an event: the event reaches
whoever it reaches, wakes them, and each of them decides for themselves, in
their own `act`, what to do about it.
"""

from __future__ import annotations

from typing import Optional

from ..adapters.backends import Call, Transcript, ask, get as get_backend
from ..application import reachability
from ..application.actions import Reach
from ..domain.world import World
from ..server import Tool
from . import prompts, schemas
from .decision import Decision, duration_of
from .schemas import CallName

#: How much of the chronicle the world is shown: the recent past, the same
#: for everyone.
RECENT_EVENTS = 8


def stir(world: World, configuration, transcript: Optional[Transcript] = None) -> Decision:
    settings = configuration[CallName.STIR]
    recent = world.chronicle.all()[-RECENT_EVENTS:]
    places = {place.name: place for place in world.places.values()}
    residents = [resident for resident in world.beings.values() if resident.present]
    can_admit = reachability.may_admit(world)
    call = Call(
        name=CallName.STIR,
        system=prompts.STIR_SYSTEM,
        user=prompts.stir_user(world, recent),
        schema=schemas.stir_grammar(
            list(places), sorted({resident.name for resident in residents}), may_admit=can_admit
        ),
        mind="world",
    )
    answer = ask(
        get_backend(settings.backend),
        call,
        settings,
        transcript,
        lambda data: schemas.validate(CallName.STIR, data),
    )
    if answer is None:
        return Decision(defaulted=True)

    why_now = (answer.get("why_now") or "").strip()
    # The timer holds whatever else the answer turns out to be.
    decision = Decision(duration=duration_of(answer), reason=why_now)
    action = answer.get("action") or ""
    if action == Tool.OCCUR:
        what = (answer.get("what") or "").strip()
        who = next(
            (resident for resident in residents if resident.name == (answer.get("who") or "")), None
        )
        place = places.get(answer.get("where") or "")
        if what and (who is not None or place is not None):
            decision.tool = Tool.OCCUR
            decision.arguments = {
                "what": what,
                "where": place.id if place is not None else "",
                "who": who.id if who is not None else "",
                "reach": answer.get("reach") or str(Reach.THERE),
                "why_now": why_now,
            }
    elif action == Tool.ADMIT and can_admit:
        name = (answer.get("name") or "").strip()
        if name:
            decision.tool = Tool.ADMIT
            decision.arguments = {
                "name": name,
                "from_where": (answer.get("from_where") or "").strip(),
                "biography": (answer.get("biography") or "").strip(),
                "idiolect": (answer.get("idiolect") or "").strip(),
                "why_now": why_now,
            }
    return decision
