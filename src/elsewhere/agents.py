"""The places where the world asks a mind a question.

Each function here does the same four things: gather what this person could
possibly draw on, ask, check the answer is usable, and write the consequence
into the ledger. None of them decide anything themselves - if a mind declines
to answer, the person simply had nothing, which is allowed.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from . import prompts, retrieval, schemas
from .backends import Call, Settings, Transcript, ask, get as get_backend
from .world.chronicle import Event
from .world.entities import Person
from .world.memories import Trace
from .world.store import season_of

#: How many memories a person may lay down in one day that they will still
#: have years later. Models have no sense of scarcity; the engine supplies it.
HEAVY_PER_DAY = 1
HEAVY = 0.7


def _settings(config, name: str) -> Settings:
    return config[name]


def _others_here(world, person: Person) -> List[Person]:
    return [p for p in world.people_at(person.place) if p.id != person.id]


def _heavy_today(world, person: Person) -> int:
    store = world.traces(person.id)
    return sum(1 for t in store
               if t.day == world.day and t.salience >= HEAVY)


def vantage(world, person: Person, event: Event) -> str:
    """Where this person stood when it happened. World state, not interpretation.

    Nobody perceives "the market burned down". They perceive what reaches them
    from where they are - heat from across the street, a glow seen from a hill,
    a story the next morning. The engine knows where people were; saying so is
    its job. What they make of it is not.
    """
    told = (event.data.get("vantage") or {}).get(person.id)
    if told:
        return told
    if person.id in event.who:
        return "in the middle of it"
    place = world.places.get(event.where or "")
    here = world.places.get(person.place)
    if place and here and here.id == place.id:
        return f"right there, at {place.name}"
    if here:
        return f"at {here.name}, and it reached you from there"
    return "nearby"


def perceive(world, person: Person, event: Event, config,
             transcript: Optional[Transcript] = None) -> Optional[Trace]:
    """Ask what this event leaves in this person. Usually the answer is nothing."""
    settings = _settings(config, "perceive")
    store = world.traces(person.id)
    cues = retrieval.cues_from(event.tags, [event.where or ""])
    context = retrieval.recallable(store, world.day, cues)

    place = world.places.get(event.where or "")
    call = Call(
        name="perceive",
        system=prompts.PERCEIVE_SYSTEM,
        user=prompts.perceive_user(
            person=person,
            what_happened=event.what,
            where=place.name if place else "nowhere in particular",
            when=f"{event.phase} in {season_of(event.day)}",
            vantage=vantage(world, person, event),
            others=[world.people[pid] for pid in event.present
                    if pid != person.id and pid in world.people],
            traces=context,
            part_of_it=person.id in event.who,
        ),
        schema=schemas.grammar("perceive"),
        about=person.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return None

    weight = answer.get("weight")
    if weight is None:                              # an older tape, or a lenient backend
        weight = "ordinary" if answer.get("stuck") else "nothing"
    if weight == "nothing":
        return None

    text = (answer.get("trace") or "").strip()
    if not text:
        return None

    salience = schemas.weight_to_salience(weight)
    if salience >= HEAVY and _heavy_today(world, person) >= HEAVY_PER_DAY:
        # They have already had their day. This one keeps its words and loses
        # its claim on the rest of their life.
        salience = 0.5

    trace = Trace(
        id=world.next_id("mem"),
        owner=person.id,
        day=world.day,
        trace=text,
        means=(answer.get("means") or "").strip(),
        feeling=answer.get("feeling", "none"),
        salience=salience,
        tags=[t.strip().lower() for t in (answer.get("tags") or []) if t.strip()][:6],
        source="witnessed" if person.id in event.present else "told",
        event_id=event.id,
        about=[w for w in event.who if w != person.id],
        place=event.where,
        last_touched=world.day,
    )
    store.add(trace)
    return trace


def perceive_all(world, event: Event, config,
                 transcript: Optional[Transcript] = None) -> List[Trace]:
    """Hand the event to everyone who was there, one mind at a time."""
    out = []
    for person in world.people.values():
        if not person.present or person.id not in event.present:
            continue
        trace = perceive(world, person, event, config, transcript)
        if trace is not None:
            out.append(trace)
    return out


# --------------------------------------------------------------------------
# act

from dataclasses import dataclass as _dataclass


@_dataclass
class Decision:
    person_id: str
    action: str = "stay"
    target: Optional[str] = None      # place id or person id, resolved
    because: str = ""
    answered: bool = True             # False when the mind gave nothing usable


def when_label(world) -> str:
    from .world.store import DAYS_PER_YEAR
    doy = (world.day - 1) % DAYS_PER_YEAR + 1
    return f"{world.phase_name} in {world.season}, day {doy}"


def act(world, person: Person, config,
        transcript: Optional[Transcript] = None) -> Decision:
    """Ask what this person does next. The grammar only offers what exists."""
    settings = _settings(config, "act")
    place = world.places.get(person.place)
    others = _others_here(world, person)
    reachable = [world.places[n] for n in (place.neighbours if place else [])
                 if n in world.places]
    store = world.traces(person.id)
    cues = retrieval.cues_from(place.tags if place else [], [person.place])
    context = retrieval.recallable(store, world.day, cues, limit=4)

    call = Call(
        name="act",
        system=prompts.ACT_SYSTEM,
        user=prompts.act_user(person, when_label(world), place, others,
                              [p.name for p in reachable], context,
                              home_name=(world.places[person.home].name
                                         if person.home in world.places else "")),
        schema=schemas.act_grammar([p.name for p in reachable],
                                   [o.name for o in others]),
        about=person.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return Decision(person.id, "stay", None, "", answered=False)

    action = answer.get("action", "stay")
    name = (answer.get("target") or "").strip()
    because = (answer.get("because") or "").strip()
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
    return Decision(person.id, action, target, because)


# --------------------------------------------------------------------------
# speak

def speak(world, speaker: Person, listener: Person, config,
          transcript: Optional[Transcript] = None):
    """One thing said out loud. Returns (line, trace drawn on) or (None, None).

    Bringing something up is rehearsal: the trace it came from is touched and
    stays within reach longer. Rewriting it in the telling is recall's job (P3).
    """
    settings = _settings(config, "speak")
    store = world.traces(speaker.id)
    cues = retrieval.cues_from([listener.id], [speaker.place])
    for t in store:
        if listener.id in t.about:
            cues |= set(t.tags)
    topics = retrieval.recallable(store, world.day, cues, limit=3)
    place = world.places.get(speaker.place)

    call = Call(
        name="speak",
        system=prompts.SPEAK_SYSTEM,
        user=prompts.speak_user(speaker, listener, when_label(world),
                                place.name if place else "somewhere", topics),
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
        drawn.last_touched = world.day
        drawn.recalls += 1
        store.touch()
    return line, drawn


# --------------------------------------------------------------------------
# direct

#: Scarcity the director cannot supply for itself: whatever it proposes, the
#: town gets at least this many quiet days between happenings.
DIRECTOR_MIN_GAP_DAYS = 2
DIRECTOR_RECENT_EVENTS = 8


def last_happening_day(world) -> Optional[int]:
    for e in reversed(world.chronicle.all()):
        if e.kind == "happening":
            return e.day
    return None


def direct(world, config, transcript: Optional[Transcript] = None) -> Optional[Event]:
    """Ask the town whether anything happens to it today. Usually nothing does."""
    last = last_happening_day(world)
    if last is not None and world.day - last < DIRECTOR_MIN_GAP_DAYS:
        return None
    settings = _settings(config, "direct")
    recent = world.chronicle.all()[-DIRECTOR_RECENT_EVENTS:]
    places = {p.name: p for p in world.places.values()}
    people = {p.name: p for p in world.people.values() if p.present}
    call = Call(
        name="direct",
        system=prompts.DIRECT_SYSTEM,
        user=prompts.direct_user(world, recent),
        schema=schemas.direct_grammar(list(places), list(people)),
        about="town",
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if not answer or not answer.get("happens"):
        return None
    what = (answer.get("what") or "").strip()
    if not what:
        return None

    who = people.get(answer.get("who") or "")
    place = places.get(answer.get("where") or "")
    if who is not None:
        # Something that happens to someone happens where they are standing.
        place = world.places.get(who.place, place)
    if place is None:
        return None

    here = [p.id for p in world.people_at(place.id)]
    if answer.get("reach") == "the whole town":
        present = [p.id for p in world.people.values() if p.present]
        vantage = {pid: (f"right there, at {place.name}" if pid in here
                         else f"at {world.places[world.people[pid].place].name}, "
                              f"and word of it reached you there")
                   for pid in present}
    else:
        present = here
        vantage = {pid: f"right there, at {place.name}" for pid in present}
    return world.record(
        "happening", what, where=place.id,
        who=[who.id] if who is not None else [],
        present=present,
        tags=[t.strip().lower() for t in (answer.get("tags") or []) if t.strip()][:5],
        data={"why_now": (answer.get("why_now") or "").strip(),
              "reach": answer.get("reach"), "vantage": vantage},
    )


# --------------------------------------------------------------------------
# reflect

MAX_BELIEFS = 6


def _same_belief(a: str, b: str) -> bool:
    from .evals import words
    wa, wb = words(a), words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5


def refresh_origins(world, person: Person) -> None:
    """Bookkeeping: can this person still reach the memories a belief came from?"""
    store = world.traces(person.id)
    for belief in person.beliefs:
        if not belief.origin:
            continue
        alive = [t for t in (store.get(i) for i in belief.origin)
                 if t is not None and not retrieval.dormant(t, world.day)]
        belief.origin_lost = not alive


def reflect(world, person: Person, config,
            transcript: Optional[Transcript] = None) -> Optional[dict]:
    """Night: what this person is left with. Only asked of people whose day left something."""
    store = world.traces(person.id)
    today = [t for t in store if t.day == world.day]
    if not today:
        return None
    today = sorted(today, key=lambda t: -t.salience)[:3]
    older = [t for t in retrieval.recallable(store, world.day, limit=4) if t not in today][:3]
    settings = _settings(config, "reflect")
    call = Call(
        name="reflect",
        system=prompts.REFLECT_SYSTEM,
        user=prompts.reflect_user(person, today, older),
        schema=schemas.reflect_grammar(len(today)),
        about=person.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return None

    text = (answer.get("belief") or "").strip().rstrip(".")
    source = answer.get("belief_from") or ""
    origin = [today[int(source) - 1].id] if source.isdigit() and 1 <= int(source) <= len(today) else []
    if text:
        from .world.entities import Belief

        existing = next((b for b in person.beliefs if _same_belief(b.text, text)), None)
        if existing is not None:
            # Holding it again: the old wording stays, the grip tightens.
            existing.confidence = min(0.95, existing.confidence + 0.1)
            for trace_id in origin:
                if trace_id not in existing.origin and len(existing.origin) < 3:
                    existing.origin.append(trace_id)
        else:
            person.beliefs.append(Belief(text=text, confidence=0.5, day=world.day,
                                         origin=origin))
            if len(person.beliefs) > MAX_BELIEFS:
                person.beliefs.sort(key=lambda b: -b.confidence)
                del person.beliefs[MAX_BELIEFS:]

    want = (answer.get("want") or "").strip().rstrip(".")
    if want and (not person.wants or person.wants[0] != want):
        person.wants = [want] + [w for w in person.wants if w != want][:1]
    mood = (answer.get("mood") or "").strip().lower()
    if mood and len(mood.split()) <= 3:
        person.mood = mood
    refresh_origins(world, person)
    return answer


# --------------------------------------------------------------------------
# recall

def recall(world, person: Person, trace: Trace, config,
           transcript: Optional[Transcript] = None) -> bool:
    """The trace has just been brought up; ask how it comes back now.

    The words are the mind's. The engine only keeps the older wording in the
    trace's history, so what it used to be is not lost to anyone reading.
    """
    settings = _settings(config, "recall")
    age = max(0, world.day - trace.day)
    call = Call(
        name="recall",
        system=prompts.RECALL_SYSTEM,
        user=prompts.recall_user(person, trace, age, retrieval.reach(trace, world.day)),
        schema=schemas.grammar("recall"),
        about=person.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return False
    new = (answer.get("trace") or "").strip()
    if not new or new == trace.trace:
        return False
    trace.rewrite(new, world.day, means=(answer.get("means") or "").strip(),
                  feeling=answer.get("feeling") or "")
    # rewrite() counts a recall; speak() already counted this one.
    trace.recalls -= 1
    world.traces(person.id).touch()
    return True
