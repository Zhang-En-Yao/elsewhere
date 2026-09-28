"""Every model call a person, the town or the road makes, and how its answer
is written into the world."""

from __future__ import annotations

from dataclasses import dataclass
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
from .schemas import Action, CallName


@dataclass
class Decision:
    being_id: str
    action: Optional[Action] = None   # None: nothing for the engine to resolve
    target: Optional[str] = None      # place id or person id, resolved
    because: str = ""
    doing: str = ""
    settling: bool = False
    answered: bool = True             # False when the mind gave nothing usable


# Helpers.

def call_settings(configuration, name: CallName) -> Settings:
    return configuration[name]


def vectorize(configuration, account: str) -> List[float]:
    """Empty when no embedder is configured or it fails; retrieval then falls
    back to activation alone."""
    settings = configuration.get("embed")
    if settings is None or not account.strip():
        return []
    got = embed([account], settings)
    return got[0] if got else []


def held_beliefs(being: Being, at: float, limit: int = 3) -> List:
    return retrieval.recallable(being.who.beliefs, at, limit=limit)


def companions_present(world, being: Being) -> List[Being]:
    return [b for b in world.beings_at(being.where.place) if b.id != being.id]


def when_label(world) -> str:
    light = "light" if world.daylight else "dark"
    return f"{world.clock} and {light}, {world.season}, {world.date}"


def next_wake_at(world, answer: Optional[dict]) -> Optional[float]:
    """None when the answer gave nothing usable, leaving no timer."""
    hours = schedule.in_hours(answer, "ask_again_in_hours")
    return world.at + hours if hours is not None else None


def viewpoint(world, being: Being, event: Event) -> str:
    told = (event.data.get("viewpoints") or {}).get(being.id)
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


# Shared by `stir` and `arrive`: both give the model the same recent slice
# of the chronicle.
TOWN_RECENT_EVENTS = 8

MAX_BELIEFS = 6


def may_stir(world) -> bool:
    return schedule.town_due(world)


def may_leave(world, being: Being) -> bool:
    return bool(world.map.road) and being.where.place == world.map.road


def may_arrive(world) -> bool:
    return schedule.road_due(world)


def may_reflect(world, being: Being, settling: bool) -> bool:
    """Only when they say they are stopping for the day, and only if anything
    has happened to them since they last reflected."""
    if not settling:
        return False
    since = being.when.reflected_at if being.when.reflected_at is not None else -1.0
    return any(t.at > since for t in world.memories(being.id))


def short_of_somebody(world) -> bool:
    lost = sum(1 for p in world.beings.values() if not p.present)
    taken = sum(1 for e in world.chronicle.all() if e.category == ARRIVAL)
    return lost > taken


def free_being_id(world, name: str) -> str:
    slug = "".join(ch for ch in name.lower() if ch.isalnum()) or "someone"
    candidate, n = f"p_{slug}", 2
    while candidate in world.beings:
        candidate, n = f"p_{slug}{n}", n + 1
    return candidate


def perceive_all(world, event: Event, configuration,
                 transcript: Optional[Transcript] = None) -> List[Memory]:
    out = []
    for being in world.beings.values():
        if not being.present or being.id not in event.informed:
            continue
        memory = perceive(world, being, event, configuration, transcript)
        if memory is not None:
            out.append(memory)
    return out


# Call sites.

def perceive(world, being: Being, event: Event, configuration,
             transcript: Optional[Transcript] = None) -> Optional[Memory]:
    settings = call_settings(configuration, CallName.PERCEIVE)
    memories = world.memories(being.id)
    cue = vectorize(configuration, event.account)
    context = retrieval.recallable(memories, world.at, cue)

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
            viewpoint=viewpoint(world, being, event),
            others=[world.beings[pid] for pid in event.informed
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
        occasions=[world.at],
    )
    memories.add(memory)
    return memory


def act(world, being: Being, configuration,
        transcript: Optional[Transcript] = None) -> Decision:
    settings = call_settings(configuration, CallName.ACT)
    place = world.places.get(being.where.place)
    reachable_places = [world.places[p] for p in world.map.beside(being.where.place)
                        if p in world.places]
    memories = world.memories(being.id)
    cue = vectorize(configuration, ". ".join(part for part in (
        f"{place.name}. {place.description}" if place else "",
        being.who.thought, "; ".join(being.who.wants)) if part))
    companions = companions_present(world, being)
    context = retrieval.recallable(memories, world.at, cue, limit=4)

    can_leave = may_leave(world, being)
    call = Call(
        name=CallName.ACT,
        system=prompts.ACT_SYSTEM,
        user=prompts.act_user(being, when_label(world), world.at, place, companions,
                              [p.name for p in reachable_places], context,
                              home_name=(world.places[being.where.home].name
                                         if being.where.home in world.places else ""),
                              may_leave=can_leave,
                              beliefs=held_beliefs(being, world.at)),
        schema=schemas.act_grammar([p.name for p in reachable_places],
                                   [c.name for c in companions], may_leave=can_leave),
        about=being.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    # Set before the None check: no usable answer means no timer, see
    # `schedule.advance_to_next_due`.
    schedule.set_timer(being, world, answer)
    if answer is None:
        return Decision(being.id, None, None, "", answered=False)

    try:
        action = Action(answer.get("action") or "")
    except ValueError:
        # An empty or unknown action is nothing to resolve; unknown ones are
        # only reachable with a lenient backend, the grammar forbids them.
        action = None
    name = (answer.get("target") or "").strip()
    because = (answer.get("because") or "").strip()
    doing = (answer.get("doing") or "").strip()
    settling = bool(answer.get("settling"))

    # A move or a talk that names nobody real, or a leave from where there is
    # no road, is only reachable with a lenient backend; the grammar forbids it.
    target: Optional[str] = None
    if action == Action.LEAVE and not can_leave:
        action = None
    elif action == Action.MOVE:
        place = next((p for p in reachable_places if p.name == name), None)
        action, target = (action, place.id) if place else (None, None)
    elif action == Action.TALK:
        companion = next((c for c in companions if c.name == name), None)
        action, target = (action, companion.id) if companion else (None, None)
    return Decision(being.id, action, target, because, doing, settling=settling)


def speak(world, speaker: Being, listener: Being, configuration,
          transcript: Optional[Transcript] = None):
    """Returns (utterance, the memory it drew on) or (None, None)."""
    settings = call_settings(configuration, CallName.SPEAK)
    memories = world.memories(speaker.id)
    regard = speaker.who.regards.get(listener.id)
    cue = vectorize(configuration, " ".join(part for part in (
        listener.name, regard.account if regard else "",
        world.places[speaker.where.place].name if speaker.where.place in world.places else "",
    ) if part))
    associated_memories = retrieval.recallable(memories, world.at, cue, limit=3)
    place = world.places.get(speaker.where.place)

    call = Call(
        name=CallName.SPEAK,
        system=prompts.SPEAK_SYSTEM,
        user=prompts.speak_user(speaker, listener, when_label(world),
                                place.name if place else "somewhere", associated_memories,
                                beliefs=held_beliefs(speaker, world.at)),
        schema=schemas.speak_grammar(len(associated_memories)),
        about=speaker.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return None, None
    utterance = (answer.get("utterance") or "").strip().strip('"').strip()
    if not utterance:
        return None, None

    associated_memory = None
    memory_reference = answer.get("memory_reference", "")
    if memory_reference.isdigit() and 1 <= int(memory_reference) <= len(associated_memories):
        associated_memory = associated_memories[int(memory_reference) - 1]
        memories.rehearse(associated_memory, world.at)
    return utterance, associated_memory


def stir(world, configuration,
         transcript: Optional[Transcript] = None) -> Optional[Event]:
    settings = call_settings(configuration, CallName.STIR)
    recent = world.chronicle.all()[-TOWN_RECENT_EVENTS:]
    places = {p.name: p for p in world.places.values()}
    beings = [p for p in world.beings.values() if p.present]
    call = Call(
        name=CallName.STIR,
        system=prompts.STIR_SYSTEM,
        user=prompts.stir_user(world, recent),
        schema=schemas.stir_grammar(list(places), sorted({p.name for p in beings})),
        about="town",
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    # Set before anything else so the timer holds even if the rest is unusable.
    world.town_wake_at = next_wake_at(world, answer)
    if not answer or not answer.get("happens"):
        return None
    what = (answer.get("what") or "").strip()
    if not what:
        return None

    who = next((p for p in beings if p.name == (answer.get("who") or "")), None)
    place = places.get(answer.get("where") or "")
    if who is not None:
        place = world.places.get(who.where.place, place)
    if place is None:
        return None

    informed = ([p.id for p in world.beings.values() if p.present]
               if answer.get("reach") == "the whole town"
               else [p.id for p in world.beings_at(place.id)])
    viewpoints = {pid: (f"right there, at {place.name}"
                     if world.beings[pid].where.place == place.id
                     else f"at {world.places[world.beings[pid].where.place].name}, "
                          f"and word of it reached you there")
               for pid in informed}
    return world.record(
        OCCURRENCE, what, place=place.id,
        involved=[who.id] if who is not None else [],
        informed=informed,
        data={"why_now": (answer.get("why_now") or "").strip(),
              "reach": answer.get("reach"), "viewpoints": viewpoints},
    )


def arrive(world, configuration,
           transcript: Optional[Transcript] = None) -> Optional[Event]:
    settings = call_settings(configuration, CallName.ARRIVE)
    recent = world.chronicle.all()[-TOWN_RECENT_EVENTS:]
    call = Call(
        name=CallName.ARRIVE,
        system=prompts.ARRIVE_SYSTEM,
        user=prompts.arrive_user(world, recent),
        schema=schemas.grammar(CallName.ARRIVE),
        about="road",
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    world.road_wake_at = next_wake_at(world, answer)
    if not answer or not answer.get("comes"):
        return None

    name = (answer.get("name") or "").strip()
    if not name:
        return None
    place = world.places[world.map.road]

    came_from = (answer.get("from_where") or "").strip()
    being = Being(
        id=free_being_id(world, name),
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

    informed = [p.id for p in world.beings.values() if p.present]
    viewpoints = {}
    for pid in informed:
        if pid == being.id:
            viewpoints[pid] = f"at the top of the road, seeing {world.name} for the first time"
        elif world.beings[pid].where.place == place.id:
            viewpoints[pid] = f"right there, at {place.name}"
        else:
            other = world.places.get(world.beings[pid].where.place)
            viewpoints[pid] = (f"at {other.name}, and word of it reached you there"
                            if other else "and word of it reached you")
    return world.record(
        ARRIVAL, said, place=place.id, involved=[being.id], informed=informed,
        data={"why_now": (answer.get("why_now") or "").strip(),
              "from_where": came_from, "person": being.id, "viewpoints": viewpoints},
    )


def leave(world, being: Being, because: str, configuration,
           transcript: Optional[Transcript] = None):
    """Returns (event, memories it left in people)."""
    place = world.places.get(being.where.place)
    where = place.name if place else "the road"
    informed = [p.id for p in world.beings.values() if p.present]
    viewpoints = {}
    for pid in informed:
        if pid == being.id:
            viewpoints[pid] = f"on the road out of {world.name}, looking back"
        elif world.beings[pid].where.place == being.where.place:
            viewpoints[pid] = f"right there, at {where}"
        else:
            other = world.places.get(world.beings[pid].where.place)
            viewpoints[pid] = (f"at {other.name}, and word of it reached you there"
                            if other else "and word of it reached you")
    event = world.record(
        DEPARTURE,
        f"{being.name} took the road out of {world.name} and did not come back.",
        place=being.where.place, involved=[being.id], informed=informed,
        data={"because": because, "person": being.id, "viewpoints": viewpoints},
    )
    kept = perceive_all(world, event, configuration, transcript)
    being.when.left_at = world.at
    being.where.now("took the road out of town")
    return event, kept


def reflect(world, being: Being, configuration,
            transcript: Optional[Transcript] = None) -> Optional[dict]:
    memories = world.memories(being.id)
    since = being.when.reflected_at if being.when.reflected_at is not None else -1.0
    being.when.reflected_at = world.at
    today = [t for t in memories if t.at > since]
    if not today:
        return None
    today = retrieval.recallable(today, world.at, limit=3)
    cue = vectorize(configuration, " ".join(t.account for t in today))
    older = [t for t in retrieval.recallable(memories, world.at, cue, limit=7)
             if t not in today][:3]
    holds = held_beliefs(being, world.at, limit=MAX_BELIEFS)
    known = [world.beings[i].name for i in being.who.regards
             if i in world.beings]
    known += [p.name for p in companions_present(world, being)
              if p.name not in known]
    settings = call_settings(configuration, CallName.REFLECT)
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
    source = answer.get("origin_reference") or ""
    origin = [today[int(source) - 1].id] if source.isdigit() and 1 <= int(source) <= len(today) else []
    if text:
        from .world.entities import Belief

        again = answer.get("restated_reference") or ""
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
        memories.add(Memory(
            id=world.next_id("mem"),
            owner=being.id,
            at=world.at,
            account=thought,
            means="", feeling="",
            embedding=vectorize(configuration, thought),
            origin=[t.id for t in today],
            occasions=[world.at],
        ))
    return answer


def recall(world, being: Being, memory: Memory, configuration,
           transcript: Optional[Transcript] = None) -> bool:
    """Ask how a just-mentioned memory comes back now; the old wording is kept
    in the memory's history."""
    settings = call_settings(configuration, CallName.RECALL)
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
    del memory.occasions[-1:]
    world.memories(being.id).touch()
    return True
