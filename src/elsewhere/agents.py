"""Every model call a person, the town or the road makes, and how its answer
is written into the world."""

from __future__ import annotations

from typing import List, Optional, Sequence

from . import prompts, retrieval, schedule, schemas
from .backends import (Call, Settings, Transcript, ask, get as get_backend,
                       embed)
from .world.chronicle import (ARRIVAL, CONVERSATION, DEPARTURE, Event,
                              OCCURRENCE)
from .world.entities import Being, When, Where, Who
from .world.memories import Memory
from . import HOURS_PER_DAY
from .world.store import clock_at, date_at, season_at
from .schemas import CallName


def _settings(configuration, name: CallName) -> Settings:
    return configuration[name]


def vectorize(configuration, account: str) -> List[float]:
    """Empty when no embedder is configured or it fails; retrieval then falls
    back to activation alone."""
    settings = configuration.get("embed")
    if settings is None or not account.strip():
        return []
    got = embed([account], settings)
    return got[0] if got else []


def _others_here(world, being: Being) -> List[Being]:
    return [p for p in world.beings_at(being.where.place) if p.id != being.id]


def held_beliefs(being: Being, at: float, limit: int = 3) -> List:
    return retrieval.recallable(being.who.beliefs, at, limit=limit)


def vantage(world, being: Being, event: Event) -> str:
    told = (event.data.get("vantage") or {}).get(being.id)
    if told:
        return told
    if being.id in event.involved:
        return "in the middle of it"
    place = world.places.get(event.place or "")
    here = world.places.get(being.where.place)
    if place and here and here.id == place.id:
        return f"right there, at {place.name}"
    if here:
        return f"at {here.name}, and it reached you from there"
    return "nearby"


def perceive(world, being: Being, event: Event, configuration,
             transcript: Optional[Transcript] = None) -> Optional[Memory]:
    settings = _settings(configuration, CallName.PERCEIVE)
    being_memories = world.memories(being.id)
    cue = vectorize(configuration, event.account)
    context = retrieval.recallable(being_memories, world.at, cue)

    place = world.places.get(event.place or "")
    call = Call(
        name=CallName.PERCEIVE,
        system=prompts.PERCEIVE_SYSTEM,
        user=prompts.perceive_user(
            being=being,
            what_happened=event.account,
            where=place.name if place else "nowhere in particular",
            when=f"{clock_at(event.at)} on {date_at(event.at)}, in {season_at(event.at)}",
            at=world.at,
            vantage=vantage(world, being, event),
            others=[world.beings[pid] for pid in event.reached
                    if pid != being.id and pid in world.beings],
            memories=context,
            part_of_it=being.id in event.involved,
        ),
        schema=schemas.grammar(CallName.PERCEIVE),
        about=being.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return None

    if not answer.get("stuck"):
        return None

    text = (answer.get("account") or "").strip()
    if not text:
        return None

    memory = Memory(
        id=world.next_id("mem"),
        owner=being.id,
        at=world.at,
        account=text,
        means=(answer.get("means") or "").strip(),
        feeling=answer.get("feeling", "none"),
        embedding=vectorize(configuration, text),
        event_id=event.id,
        told=[world.at],
    )
    being_memories.add(memory)
    return memory


def perceive_all(world, event: Event, configuration,
                 transcript: Optional[Transcript] = None) -> List[Memory]:
    out = []
    for being in world.beings.values():
        if not being.present or being.id not in event.reached:
            continue
        memory = perceive(world, being, event, configuration, transcript)
        if memory is not None:
            out.append(memory)
    return out


from dataclasses import dataclass as _dataclass


@_dataclass
class Decision:
    being_id: str
    action: str = "stay"
    target: Optional[str] = None      # place id or person id, resolved
    because: str = ""
    doing: str = ""
    settling: bool = False
    answered: bool = True             # False when the mind gave nothing usable


def when_label(world) -> str:
    light = "light" if world.daylight else "dark"
    return f"{world.clock} and {light}, {world.season}, {world.date}"


def act(world, being: Being, configuration,
        transcript: Optional[Transcript] = None) -> Decision:
    settings = _settings(configuration, CallName.ACT)
    place = world.places.get(being.where.place)
    others = _others_here(world, being)
    reachable = [world.places[n] for n in world.map.beside(being.where.place)
                 if n in world.places]
    being_memories = world.memories(being.id)
    cue = vectorize(configuration, ". ".join(x for x in (
        f"{place.name}. {place.description}" if place else "",
        being.who.thought, "; ".join(being.who.wants)) if x))
    context = retrieval.recallable(being_memories, world.at, cue, limit=4)

    going = may_leave(world, being)
    call = Call(
        name=CallName.ACT,
        system=prompts.ACT_SYSTEM,
        user=prompts.act_user(being, when_label(world), world.at, place, others,
                              [p.name for p in reachable], context,
                              home_name=(world.places[being.where.home].name
                                         if being.where.home in world.places else ""),
                              may_leave=going,
                              beliefs=held_beliefs(being, world.at)),
        schema=schemas.act_grammar([p.name for p in reachable],
                                   [o.name for o in others], may_leave=going),
        about=being.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    # Set before the None check: no usable answer means no timer, see
    # `schedule.advance_to_next_due`.
    schedule.set_timer(being, world, answer)
    if answer is None:
        return Decision(being.id, "stay", None, "", answered=False)

    action = answer.get("action", "stay")
    name = (answer.get("target") or "").strip()
    because = (answer.get("because") or "").strip()
    doing = (answer.get("doing") or "").strip()
    target = None
    if action == "go":
        match = next((p for p in reachable if p.name == name), None)
        target = match.id if match else None
    elif action == "talk":
        match = next((o for o in others if o.name == name), None)
        target = match.id if match else None
    if action in ("go", "talk") and target is None:
        # Only reachable with a lenient backend; the grammar forbids it.
        action = "stay"
    if action == schemas.LEAVE and not going:
        action = "stay"
    return Decision(being.id, action, target, because, doing,
                    settling=bool(answer.get("settling")))


def speak(world, speaker: Being, listener: Being, configuration,
          transcript: Optional[Transcript] = None):
    """Returns (line, memory drawn on) or (None, None)."""
    settings = _settings(configuration, CallName.SPEAK)
    speaker_memories = world.memories(speaker.id)
    regard = speaker.who.regards.get(listener.id)
    cue = vectorize(configuration, " ".join(x for x in (
        listener.name, regard.account if regard else "",
        world.places[speaker.where.place].name if speaker.where.place in world.places else "",
    ) if x))
    topics = retrieval.recallable(speaker_memories, world.at, cue, limit=3)
    place = world.places.get(speaker.where.place)

    call = Call(
        name=CallName.SPEAK,
        system=prompts.SPEAK_SYSTEM,
        user=prompts.speak_user(speaker, listener, when_label(world),
                                place.name if place else "somewhere", topics,
                                beliefs=held_beliefs(speaker, world.at)),
        schema=schemas.speak_grammar(len(topics)),
        about=speaker.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return None, None
    line = (answer.get("line") or "").strip().strip('"').strip()
    if not line:
        return None, None

    drawn = None
    about = answer.get("about", "")
    if about.isdigit() and 1 <= int(about) <= len(topics):
        drawn = topics[int(about) - 1]
        drawn.came_up(world.at)
        speaker_memories.touch()
    return line, drawn


DIRECTOR_RECENT_EVENTS = 8


def may_direct(world) -> bool:
    return schedule.town_due(world)


def direct(world, configuration,
           transcript: Optional[Transcript] = None) -> Optional[Event]:
    settings = _settings(configuration, CallName.DIRECT)
    recent = world.chronicle.all()[-DIRECTOR_RECENT_EVENTS:]
    places = {p.name: p for p in world.places.values()}
    beings = {p.name: p for p in world.beings.values() if p.present}
    call = Call(
        name=CallName.DIRECT,
        system=prompts.DIRECT_SYSTEM,
        user=prompts.direct_user(world, recent),
        schema=schemas.direct_grammar(list(places), list(beings)),
        about="town",
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    # Set before anything else so the timer holds even if the rest is unusable.
    world.town_wake_at = _asked_again(world, answer)
    if not answer or not answer.get("happens"):
        return None
    what = (answer.get("what") or "").strip()
    if not what:
        return None

    who = beings.get(answer.get("who") or "")
    place = places.get(answer.get("where") or "")
    if who is not None:
        place = world.places.get(who.where.place, place)
    if place is None:
        return None

    here = [p.id for p in world.beings_at(place.id)]
    if answer.get("reach") == "the whole town":
        reached = [p.id for p in world.beings.values() if p.present]
        vantage = {pid: (f"right there, at {place.name}" if pid in here
                         else f"at {world.places[world.beings[pid].where.place].name}, "
                              f"and word of it reached you there")
                   for pid in reached}
    else:
        reached = here
        vantage = {pid: f"right there, at {place.name}" for pid in reached}
    return world.record(
        OCCURRENCE, what, place=place.id,
        involved=[who.id] if who is not None else [],
        reached=reached,
        data={"why_now": (answer.get("why_now") or "").strip(),
              "reach": answer.get("reach"), "vantage": vantage},
    )


TOWN_FLOOR = 2
TOWN_CEILING = 8


def _asked_again(world, answer: Optional[dict]) -> Optional[float]:
    """None when the answer gave nothing usable, leaving no timer."""
    hours = schedule.in_hours(answer, "ask_again_in_hours")
    return world.at + hours if hours is not None else None


def leaving_place(world):
    return world.places.get(world.map.road_out)


def may_leave(world, being: Being) -> bool:
    if not world.map.road_out or being.where.place != world.map.road_out:
        return False
    return sum(1 for p in world.beings.values() if p.present) > TOWN_FLOOR


def depart(world, being: Being, because: str, configuration,
           transcript: Optional[Transcript] = None):
    """Returns (event, memories it left in people)."""
    place = world.places.get(being.where.place)
    where = place.name if place else "the road"
    reached = [p.id for p in world.beings.values() if p.present]
    vantage = {}
    for pid in reached:
        if pid == being.id:
            vantage[pid] = f"on the road out of {world.name}, looking back"
        elif world.beings[pid].where.place == being.where.place:
            vantage[pid] = f"right there, at {where}"
        else:
            other = world.places.get(world.beings[pid].where.place)
            vantage[pid] = (f"at {other.name}, and word of it reached you there"
                            if other else "and word of it reached you")
    event = world.record(
        DEPARTURE,
        f"{being.name} took the road out of {world.name} and did not come back.",
        place=being.where.place, involved=[being.id], reached=reached,
        data={"because": because, "person": being.id, "vantage": vantage},
    )
    kept = perceive_all(world, event, configuration, transcript)
    being.when.left_at = world.at
    being.where.now("took the road out of town")
    return event, kept


def short_of_somebody(world) -> bool:
    lost = sum(1 for p in world.beings.values() if not p.present)
    taken = sum(1 for e in world.chronicle.all() if e.category == ARRIVAL)
    return lost > taken


def may_arrive(world) -> bool:
    here = sum(1 for p in world.beings.values() if p.present)
    if here >= TOWN_CEILING:
        return False
    return schedule.road_due(world)


def _free_being_id(world, name: str) -> str:
    slug = "".join(ch for ch in name.lower() if ch.isalnum()) or "someone"
    candidate, n = f"p_{slug}", 2
    while candidate in world.beings:
        candidate, n = f"p_{slug}{n}", n + 1
    return candidate


def arrive(world, configuration,
           transcript: Optional[Transcript] = None) -> Optional[Event]:
    settings = _settings(configuration, CallName.ARRIVE)
    recent = world.chronicle.all()[-DIRECTOR_RECENT_EVENTS:]
    call = Call(
        name=CallName.ARRIVE,
        system=prompts.ARRIVE_SYSTEM,
        user=prompts.arrive_user(world, recent),
        schema=schemas.grammar(CallName.ARRIVE),
        about="road",
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    world.road_wake_at = _asked_again(world, answer)
    if not answer or not answer.get("comes"):
        return None

    name = (answer.get("name") or "").strip()
    if not name or any(p.name.lower() == name.lower() for p in world.beings.values()):
        return None
    place = leaving_place(world) or next(iter(world.places.values()), None)
    if place is None:
        return None

    came_from = (answer.get("from_where") or "").strip()
    being = Being(
        id=_free_being_id(world, name),
        name=name,
        who=Who(card=(answer.get("card") or "").strip(),
                manner=(answer.get("manner") or "").strip()),
        where=Where(place=place.id, home=""),
        when=When(arrived_at=world.at),
    )
    world.beings[being.id] = being

    said = being.name
    if came_from:
        said += f", from {came_from},"
    said += f" came up the road into {world.name}."

    reached = [p.id for p in world.beings.values() if p.present]
    vantage = {}
    for pid in reached:
        if pid == being.id:
            vantage[pid] = f"at the top of the road, seeing {world.name} for the first time"
        elif world.beings[pid].where.place == place.id:
            vantage[pid] = f"right there, at {place.name}"
        else:
            other = world.places.get(world.beings[pid].where.place)
            vantage[pid] = (f"at {other.name}, and word of it reached you there"
                            if other else "and word of it reached you")
    return world.record(
        ARRIVAL, said, place=place.id, involved=[being.id], reached=reached,
        data={"why_now": (answer.get("why_now") or "").strip(),
              "from_where": came_from, "person": being.id, "vantage": vantage},
    )


MAX_BELIEFS = 6


def may_reflect(world, being: Being, settling: bool) -> bool:
    """Only when they say they are stopping for the day, and only if anything
    has happened to them since they last reflected."""
    if not settling:
        return False
    since = being.when.reflected_at if being.when.reflected_at is not None else -1.0
    return any(t.at > since for t in world.memories(being.id))


def reflect(world, being: Being, configuration,
            transcript: Optional[Transcript] = None) -> Optional[dict]:
    being_memories = world.memories(being.id)
    since = being.when.reflected_at if being.when.reflected_at is not None else -1.0
    being.when.reflected_at = world.at
    today = [t for t in being_memories if t.at > since]
    if not today:
        return None
    today = retrieval.recallable(today, world.at, limit=3)
    cue = vectorize(configuration, " ".join(t.account for t in today))
    older = [t for t in retrieval.recallable(being_memories, world.at, cue, limit=7)
             if t not in today][:3]
    holds = held_beliefs(being, world.at, limit=MAX_BELIEFS)
    known = [world.beings[i].name for i in being.who.regards
             if i in world.beings]
    known += [p.name for p in _others_here(world, being)
              if p.name not in known]
    settings = _settings(configuration, CallName.REFLECT)
    call = Call(
        name=CallName.REFLECT,
        system=prompts.REFLECT_SYSTEM,
        user=prompts.reflect_user(being, today, older, holds, world.at,
                                  lately=being.where.lately),
        schema=schemas.reflect_grammar(len(today), len(holds), known),
        about=being.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return None

    text = (answer.get("belief") or "").strip().rstrip(".")
    source = answer.get("belief_from") or ""
    origin = [today[int(source) - 1].id] if source.isdigit() and 1 <= int(source) <= len(today) else []
    if text:
        from .world.entities import Belief

        again = answer.get("belief_again") or ""
        existing = (holds[int(again) - 1]
                    if again.isdigit() and 1 <= int(again) <= len(holds) else None)
        if existing is not None:
            # Restated: keep the old wording, record another occasion of holding it.
            existing.came_up(world.at)
            for memory_id in origin:
                if memory_id not in existing.origin and len(existing.origin) < 3:
                    existing.origin.append(memory_id)
        else:
            being.who.beliefs.append(Belief(claim=text, origin=origin,
                                        held=[world.at],
                                        embedding=vectorize(configuration, text)))
            if len(being.who.beliefs) > MAX_BELIEFS:
                keep = set(id(b) for b in
                           retrieval.recallable(being.who.beliefs, world.at,
                                                limit=MAX_BELIEFS))
                being.who.beliefs = [b for b in being.who.beliefs if id(b) in keep]

    whom = (answer.get("about_someone") or "").strip()
    now_say = (answer.get("now_say") or "").strip()
    if whom and now_say:
        other = world.being_by_name(whom)
        if other is not None and other.id != being.id:
            being.who.regard(other.id).account = now_say

    want = (answer.get("want") or "").strip().rstrip(".")
    if want and (not being.who.wants or being.who.wants[0] != want):
        being.who.wants = [want] + [w for w in being.who.wants if w != want][:1]

    thought = (answer.get("thought") or "").strip()
    if thought:
        being.who.thought = thought
            # Stored as a memory too, so it can be recalled, decay and be spoken.
        being_memories.add(Memory(
            id=world.next_id("mem"),
            owner=being.id,
            at=world.at,
            account=thought,
            means="", feeling="",
            embedding=vectorize(configuration, thought),
            origin=[t.id for t in today],
            told=[world.at],
        ))
    return answer


def recall(world, being: Being, memory: Memory, configuration,
           transcript: Optional[Transcript] = None) -> bool:
    """Ask how a just-mentioned memory comes back now; the old wording is kept
    in the memory's history."""
    settings = _settings(configuration, CallName.RECALL)
    age = max(0, int((world.at - memory.at) // HOURS_PER_DAY))
    call = Call(
        name=CallName.RECALL,
        system=prompts.RECALL_SYSTEM,
        user=prompts.recall_user(being, memory, age, world.at),
        schema=schemas.grammar(CallName.RECALL),
        about=being.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return False
    new = (answer.get("account") or "").strip()
    if not new or new == memory.account:
        return False
    memory.rewrite(new, world.at, means=(answer.get("means") or "").strip(),
                  feeling=answer.get("feeling") or "",
                  embedding=vectorize(configuration, new))
    # rewrite() logs the occasion; speak() already logged this one.
    del memory.told[-1:]
    world.memories(being.id).touch()
    return True
