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
from . import HOURS_PER_DAY
from .world.store import clock_at, season_at

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
               if world.at - t.at < HOURS_PER_DAY and t.salience >= HEAVY)


def vantage(world, person: Person, event: Event) -> str:
    """Where this person stood when it happened. World state, not interpretation.

    Nobody perceives "the water reached the waterline". They perceive what
    reaches them from where they are - the sound of it in the night, a light
    seen from the ridge, a story the next morning. The engine knows where
    people were; saying so is its job. What they make of it is not.
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
    context = retrieval.recallable(store, world.at, cues)

    place = world.places.get(event.where or "")
    call = Call(
        name="perceive",
        system=prompts.PERCEIVE_SYSTEM,
        user=prompts.perceive_user(
            person=person,
            what_happened=event.what,
            where=place.name if place else "nowhere in particular",
            when=f"{clock_at(event.at)} in {season_at(event.at)}",
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

    if answer.get("weight", "nothing") == "nothing":
        return None

    text = (answer.get("trace") or "").strip()
    if not text:
        return None

    salience = schemas.weight_to_salience(answer.get("weight"))
    if salience >= HEAVY and _heavy_today(world, person) >= HEAVY_PER_DAY:
        # They have already had their day. This one keeps its words and loses
        # its claim on the rest of their life.
        salience = 0.5

    trace = Trace(
        id=world.next_id("mem"),
        owner=person.id,
        at=world.at,
        trace=text,
        means=(answer.get("means") or "").strip(),
        feeling=answer.get("feeling", "none"),
        salience=salience,
        tags=[t.strip().lower() for t in (answer.get("tags") or []) if t.strip()][:6],
        source="witnessed" if person.id in event.present else "told",
        event_id=event.id,
        about=[w for w in event.who if w != person.id],
        place=event.where,
        touched_at=world.at,
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
    """The time, and whether the sun is up. Not what either of those means.

    A named quarter of the day would be the engine deciding that this hour is
    for working or for sleeping, the same for everybody. The clock and the
    light are facts; what this hour is worth doing with is read off the person.
    """
    from .world.store import DAYS_PER_YEAR
    doy = (world.day_index - 1) % DAYS_PER_YEAR + 1
    light = "light" if world.daylight else "dark"
    return f"{world.clock} and {light}, {world.season}, day {doy}"


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
    context = retrieval.recallable(store, world.at, cues, limit=4)

    going = may_leave(world, person)
    call = Call(
        name="act",
        system=prompts.ACT_SYSTEM,
        user=prompts.act_user(person, when_label(world), place, others,
                              [p.name for p in reachable], context,
                              home_name=(world.places[person.home].name
                                         if person.home in world.places else ""),
                              may_leave=going),
        schema=schemas.act_grammar([p.name for p in reachable],
                                   [o.name for o in others], may_leave=going),
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
    if action == schemas.LEAVE and not going:
        # Likewise: nobody walks out of the world from somewhere the road
        # does not go, however the answer got here.
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
    topics = retrieval.recallable(store, world.at, cues, limit=3)
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
        drawn.touched_at = world.at
        drawn.recalls += 1
        store.touch()
    return line, drawn


# --------------------------------------------------------------------------
# direct

#: Scarcity the director cannot supply for itself: whatever it proposes, the
#: town gets at least this many quiet days between happenings.
DIRECTOR_MIN_GAP = 2 * HOURS_PER_DAY    # quiet time the town gets between happenings
DIRECTOR_EVERY = HOURS_PER_DAY          # and how often it is asked at all
DIRECTOR_RECENT_EVENTS = 8


def last_happening_at(world) -> Optional[int]:
    for e in reversed(world.chronicle.all()):
        if e.kind == "happening":
            return e.at
    return None


def may_direct(world) -> bool:
    """Whether the town is worth asking, now.

    This used to be "in the morning", which meant the engine had decided that
    things happen to towns at a particular hour. It is a rate: about once a
    day, and never inside the quiet stretch after something already happened.
    """
    if (world.directed_at is not None
            and world.at - world.directed_at < DIRECTOR_EVERY):
        return False
    last = last_happening_at(world)
    return last is None or world.at - last >= DIRECTOR_MIN_GAP


def direct(world, config, transcript: Optional[Transcript] = None) -> Optional[Event]:
    """Ask the town whether anything happens to it. Usually nothing does."""
    world.directed_at = world.at
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
# the road, which runs both ways

#: Scarcity the road cannot supply for itself. A model asked "would she go?"
#: with her wants in front of it will eventually say yes; whether going is even
#: possible from here today is the engine's to answer, and it answers with
#: facts - where she is standing, what hour it is, how many are left, how long
#: since the last one went.
TOWN_FLOOR = 2                  # below this it stops being a town
TOWN_CEILING = 8                # above this it stops being one anybody knows
DEPARTURE_MIN_GAP = 45 * HOURS_PER_DAY
ARRIVAL_MIN_GAP = 30 * HOURS_PER_DAY        # while the town is short of somebody
ARRIVAL_SETTLED_GAP = 120 * HOURS_PER_DAY   # a year, when it is not


def _last_at_of(world, kinds: Sequence[str]) -> Optional[float]:
    for event in reversed(world.chronicle.all()):
        if event.kind in kinds:
            return event.at
    return None


def leaving_place(world):
    """Where the road goes out. A fact about the map, not about anybody."""
    for place in world.places.values():
        if "leaving" in place.tags:
            return place
    return None


def may_leave(world, person: Person) -> bool:
    """Whether this person could walk out of the world right now.

    Three facts, none of them about what they want, and none of them about
    what hour it is. There used to be a fourth - not at night - and it was the
    engine deciding that nobody in this town is the sort of person who leaves
    in the dark. Whether to walk out at three in the morning is exactly the
    kind of thing that should differ from one person to the next, so it is
    theirs to answer, in "because".
    """
    place = world.places.get(person.place)
    if place is None or "leaving" not in place.tags:
        return False
    if sum(1 for p in world.people.values() if p.present) <= TOWN_FLOOR:
        return False
    last = _last_at_of(world, ("departure",))
    return last is None or world.at - last >= DEPARTURE_MIN_GAP


def depart(world, person: Person, because: str, config,
           transcript: Optional[Transcript] = None):
    """Somebody takes the road. Returns (event, what it left in people).

    They are still present while it is happening, so the last thing in their
    file is the town from the top of the road. After that nobody asks them
    anything again - but what they have stays where it is, and so does every
    note the people they left behind wrote about them.
    """
    place = world.places.get(person.place)
    where = place.name if place else "the road"
    present = [p.id for p in world.people.values() if p.present]
    vantage = {}
    for pid in present:
        if pid == person.id:
            vantage[pid] = f"on the road out of {world.name}, looking back"
        elif world.people[pid].place == person.place:
            vantage[pid] = f"right there, at {where}"
        else:
            other = world.places.get(world.people[pid].place)
            vantage[pid] = (f"at {other.name}, and word of it reached you there"
                            if other else "and word of it reached you")
    event = world.record(
        "departure",
        f"{person.name} took the road out of {world.name} and did not come back.",
        where=person.place, who=[person.id], present=present,
        tags=["leaving", "road"],
        data={"because": because, "person": person.id, "vantage": vantage},
    )
    kept = perceive_all(world, event, config, transcript)
    person.present = False
    person.left_at = world.at
    person.last_action = "took the road out of town"
    return event, kept


def _road_anchor(world) -> float:
    """The last time the road was either asked or answered.

    Asking has to count, or a town that is owed somebody would put the question
    every morning until it got one, which is a model call a day for an answer
    that is almost always no.
    """
    moments = [d for d in (world.road_asked_at,
                           _last_at_of(world, ("arrival", "departure")))
               if d is not None]
    if moments:
        return max(moments)
    events = world.chronicle.all()             # a world written before this
    return events[0].at if events else world.at


def short_of_somebody(world) -> bool:
    """Has this town lost more people than it has taken in?"""
    lost = sum(1 for p in world.people.values() if not p.present)
    taken = sum(1 for e in world.chronicle.all() if e.kind == "arrival")
    return lost > taken


def may_arrive(world) -> bool:
    """Whether the road is worth asking this morning.

    A town that is down somebody notices strangers; one that is not takes
    somebody in about as often as the prompt says it would, which is once in a
    year. Either way the road can say no, and usually does - the engine is only
    deciding how often the question is worth the asking, and the two bounds
    within which a town is still a town.
    """
    here = sum(1 for p in world.people.values() if p.present)
    if here >= TOWN_CEILING:
        return False
    gap = ARRIVAL_MIN_GAP if short_of_somebody(world) else ARRIVAL_SETTLED_GAP
    return world.at - _road_anchor(world) >= gap


def _free_person_id(world, name: str) -> str:
    slug = "".join(ch for ch in name.lower() if ch.isalnum()) or "someone"
    candidate, n = f"p_{slug}", 2
    while candidate in world.people:
        candidate, n = f"p_{slug}{n}", n + 1
    return candidate


def arrive(world, config, transcript: Optional[Transcript] = None) -> Optional[Event]:
    """Ask the road whether anybody comes up it today. Usually nobody does."""
    world.road_asked_at = world.at
    settings = _settings(config, "arrive")
    recent = world.chronicle.all()[-DIRECTOR_RECENT_EVENTS:]
    call = Call(
        name="arrive",
        system=prompts.ARRIVE_SYSTEM,
        user=prompts.arrive_user(world, recent),
        schema=schemas.grammar("arrive"),
        about="road",
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if not answer or not answer.get("comes"):
        return None

    name = (answer.get("name") or "").strip()
    if not name or any(p.name.lower() == name.lower() for p in world.people.values()):
        return None
    place = leaving_place(world) or next(iter(world.places.values()), None)
    if place is None:
        return None

    age = answer.get("age")
    trade = (answer.get("trade") or "").strip()
    came_from = (answer.get("from_where") or "").strip()
    person = Person(
        id=_free_person_id(world, name),
        name=name,
        card=(answer.get("card") or "").strip(),
        voice=(answer.get("voice") or "").strip(),
        age=int(age) if isinstance(age, (int, float)) and 0 < age < 120 else None,
        occupation=trade,
        place=place.id,
        # Nowhere of their own yet. Somewhere to sleep is a thing they will
        # have to come by here, like anyone else.
        home="",
        mood="unsettled",
        arrived_at=world.at,
    )
    world.people[person.id] = person

    said = f"{person.name}"
    if trade:
        said += f", a {trade}"
    if came_from:
        said += f" from {came_from}"
    said += f", came up the road into {world.name}."

    present = [p.id for p in world.people.values() if p.present]
    vantage = {}
    for pid in present:
        if pid == person.id:
            vantage[pid] = f"at the top of the road, seeing {world.name} for the first time"
        elif world.people[pid].place == place.id:
            vantage[pid] = f"right there, at {place.name}"
        else:
            other = world.places.get(world.people[pid].place)
            vantage[pid] = (f"at {other.name}, and word of it reached you there"
                            if other else "and word of it reached you")
    return world.record(
        "arrival", said, where=place.id, who=[person.id], present=present,
        tags=["arrival", "road", "stranger"],
        data={"why_now": (answer.get("why_now") or "").strip(),
              "from_where": came_from, "person": person.id, "vantage": vantage},
    )


# --------------------------------------------------------------------------
# reflect

MAX_BELIEFS = 6
REFLECT_EVERY = HOURS_PER_DAY   # roughly once a day each, on their own clock


def may_reflect(world, person: Person) -> bool:
    """Whether this person is due to go over a day of their own.

    This used to be "everyone, at night". Now it is a rolling day per person,
    anchored on the last time *they* did it - so somebody who arrived at noon
    goes over their day at noon, and the town does not all fall quiet at once
    because the engine said the hour for it had come.
    """
    if (person.reflected_at is not None
            and world.at - person.reflected_at < REFLECT_EVERY):
        return False
    return any(world.at - t.at < REFLECT_EVERY for t in world.traces(person.id))

_STOP_WORDS = {"the", "and", "that", "with", "from", "into", "still", "this",
              "there", "their", "were", "was", "had", "have", "then", "they",
              "them", "about", "your", "you", "what", "when", "just", "like",
              "been", "over", "only"}


def _words(text: str) -> set:
    import re
    return {w for w in re.findall(r"[a-z']+", (text or "").lower())
           if len(w) > 3 and w not in _STOP_WORDS}


def _same_belief(a: str, b: str) -> bool:
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5


def refresh_origins(world, person: Person) -> None:
    """Bookkeeping: can this person still reach the memories a belief came from?"""
    store = world.traces(person.id)
    for belief in person.beliefs:
        if not belief.origin:
            continue
        alive = [t for t in (store.get(i) for i in belief.origin)
                 if t is not None and not retrieval.dormant(t, world.at)]
        belief.origin_lost = not alive


def reflect(world, person: Person, config,
            transcript: Optional[Transcript] = None) -> Optional[dict]:
    """What this person is left with, after a day of their own."""
    store = world.traces(person.id)
    person.reflected_at = world.at
    today = [t for t in store if world.at - t.at < REFLECT_EVERY]
    if not today:
        return None
    today = sorted(today, key=lambda t: -t.salience)[:3]
    older = [t for t in retrieval.recallable(store, world.at, limit=4) if t not in today][:3]
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
            person.beliefs.append(Belief(text=text, confidence=0.5, at=world.at,
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
    age = max(0, int((world.at - trace.at) // HOURS_PER_DAY))
    call = Call(
        name="recall",
        system=prompts.RECALL_SYSTEM,
        user=prompts.recall_user(person, trace, age, retrieval.reach(trace, world.at)),
        schema=schemas.grammar("recall"),
        about=person.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return False
    new = (answer.get("trace") or "").strip()
    if not new or new == trace.trace:
        return False
    trace.rewrite(new, world.at, means=(answer.get("means") or "").strip(),
                  feeling=answer.get("feeling") or "")
    # rewrite() counts a recall; speak() already counted this one.
    trace.recalls -= 1
    world.traces(person.id).touch()
    return True
