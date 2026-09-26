"""The places where the world asks a mind a question.

Each function here does the same four things: gather what this person could
possibly draw on, ask, check the answer is usable, and write the consequence
into the ledger. None of them decide anything themselves - if a mind declines
to answer, the person simply had nothing, which is allowed.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from . import prompts, retrieval, schedule, schemas
from .backends import (Call, Settings, Transcript, ask, get as get_backend,
                       place as place_in_meaning)
from .world.chronicle import (ARRIVAL, CONVERSATION, DEPARTURE, Event,
                              OCCURRENCE)
from .world.entities import Being, When, Where, Who
from .world.memories import Memory
from . import HOURS_PER_DAY
from .world.store import clock_at, season_at


def _settings(config, name: str) -> Settings:
    return config[name]


def _placed(config, text: str) -> List[float]:
    """Where this reads from, or nothing at all.

    Nothing here is required to work. An embedder that is missing or down
    gives back an empty vector, `recallable` falls through to how reachable
    a memory is, and the world carries on slightly less pointedly - which is
    how it worked before there was an embedder.
    """
    settings = config.get("embed")
    if settings is None or not text.strip():
        return []
    got = place_in_meaning([text], settings)
    return got[0] if got else []


def _others_here(world, being: Being) -> List[Being]:
    return [p for p in world.beings_at(being.where.place) if p.id != being.id]


def held_beliefs(being: Being, at: float, limit: int = 3) -> List:
    """What this person holds, the most live of it first.

    The same equation that decides which memories come to mind decides which
    beliefs do, because a belief is a thing somebody carries and ACT-R does
    not care what kind of chunk it is looking at. What replaced a confidence
    number is what a confidence number was standing in for: how often somebody
    has arrived at this again, and how lately.
    """
    return retrieval.recallable(being.who.beliefs, at, limit=limit)


def vantage(world, being: Being, event: Event) -> str:
    """Where this person stood when it happened. World state, not interpretation.

    Nobody perceives "the water reached the waterline". They perceive what
    reaches them from where they are - the sound of it in the night, a light
    seen from the ridge, a story the next morning. The engine knows where
    people were; saying so is its job. What they make of it is not.
    """
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


def perceive(world, being: Being, event: Event, config,
             transcript: Optional[Transcript] = None) -> Optional[Memory]:
    """Ask what this event leaves in this person. Usually the answer is nothing."""
    settings = _settings(config, "perceive")
    store = world.memories(being.id)
    near = _placed(config, event.account)
    context = retrieval.recallable(store, world.at, near)

    place = world.places.get(event.place or "")
    call = Call(
        name="perceive",
        system=prompts.PERCEIVE_SYSTEM,
        user=prompts.perceive_user(
            being=being,
            what_happened=event.account,
            where=place.name if place else "nowhere in particular",
            when=f"{clock_at(event.at)} in {season_at(event.at)}",
            at=world.at,
            vantage=vantage(world, being, event),
            others=[world.beings[pid] for pid in event.reached
                    if pid != being.id and pid in world.beings],
            memories=context,
            part_of_it=being.id in event.involved,
        ),
        schema=schemas.grammar("perceive"),
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

    # Nothing is written down about how much this mattered. What decides
    # whether it is still here in a year is whether anybody ever brings it up,
    # which `retrieval` reads off `told`.
    memory = Memory(
        id=world.next_id("mem"),
        owner=being.id,
        at=world.at,
        account=text,
        means=(answer.get("means") or "").strip(),
        feeling=answer.get("feeling", "none"),
        embedding=_placed(config, text),
        event_id=event.id,
        told=[world.at],
    )
    store.add(memory)
    return memory


def perceive_all(world, event: Event, config,
                 transcript: Optional[Transcript] = None) -> List[Memory]:
    """Hand the event to everyone who was there, one mind at a time."""
    out = []
    for being in world.beings.values():
        if not being.present or being.id not in event.reached:
            continue
        memory = perceive(world, being, event, config, transcript)
        if memory is not None:
            out.append(memory)
    return out


# --------------------------------------------------------------------------
# act

from dataclasses import dataclass as _dataclass


@_dataclass
class Decision:
    being_id: str
    action: str = "stay"
    target: Optional[str] = None      # place id or person id, resolved
    because: str = ""
    doing: str = ""                   # what it looks like, in their words
    #: Whether this is them stopping for the day, which is the only thing
    #: anywhere that makes somebody go over one. How long they will be at it
    #: is not here: `schedule.set_timer` has already written it onto the
    #: being, and a second copy on the report is a second thing to keep true.
    settling: bool = False
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


def act(world, being: Being, config,
        transcript: Optional[Transcript] = None) -> Decision:
    """Ask what this person does next. The grammar only offers what exists."""
    settings = _settings(config, "act")
    place = world.places.get(being.where.place)
    others = _others_here(world, being)
    reachable = [world.places[n] for n in world.map.beside(being.where.place)
                 if n in world.places]
    store = world.memories(being.id)
    # What this moment reads from: the room, and what this person is already
    # carrying around in it. The room alone is prose an author wrote once and
    # the same for everybody standing in it; their thought and their wants are
    # their own sentences, and a memory near *those* is the one that would
    # actually come to somebody here.
    near = _placed(config, ". ".join(x for x in (
        f"{place.name}. {place.description}" if place else "",
        being.who.thought, "; ".join(being.who.wants)) if x))
    context = retrieval.recallable(store, world.at, near, limit=4)

    going = may_leave(world, being)
    call = Call(
        name="act",
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
    # Whatever they decided, they also said how long they will be at it, and
    # that is what says when they are asked anything again. A mind that gave
    # nothing usable is left without a timer and comes round with the rest of
    # the world - see `schedule.advance`.
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
        # Likewise: nobody walks out of the world from somewhere the road
        # does not go, however the answer got here.
        action = "stay"
    return Decision(being.id, action, target, because, doing,
                    settling=bool(answer.get("settling")))


# --------------------------------------------------------------------------
# speak

def speak(world, speaker: Being, listener: Being, config,
          transcript: Optional[Transcript] = None):
    """One thing said out loud. Returns (line, memory drawn on) or (None, None).

    Bringing something up is rehearsal: the memory it came from is touched and
    stays within reach longer. Rewriting it in the telling is recall's job (P3).
    """
    settings = _settings(config, "speak")
    store = world.memories(speaker.id)
    # Who is in front of them, in words: the listener's name and the speaker's
    # own account of them, which is text a mind wrote. Every retrieval cue in
    # this file is that, and never a string the engine glued together.
    regard = speaker.who.regards.get(listener.id)
    near = _placed(config, " ".join(x for x in (
        listener.name, regard.account if regard else "",
        world.places[speaker.where.place].name if speaker.where.place in world.places else "",
    ) if x))
    topics = retrieval.recallable(store, world.at, near, limit=3)
    place = world.places.get(speaker.where.place)

    call = Call(
        name="speak",
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
        store.touch()
    return line, drawn


# --------------------------------------------------------------------------
# direct

#: How much of the record the town is shown before it answers. A prompt
#: budget, not a rate.
DIRECTOR_RECENT_EVENTS = 8


def may_direct(world) -> bool:
    """Whether the town is worth asking, now. The town said when.

    How eventful a town is is the town's own answer: it sets its timer in
    `direct` below, and this only reads it.
    """
    return schedule.town_due(world)


def direct(world, config, transcript: Optional[Transcript] = None) -> Optional[Event]:
    """Ask the town whether anything happens to it. Usually nothing does."""
    settings = _settings(config, "direct")
    recent = world.chronicle.all()[-DIRECTOR_RECENT_EVENTS:]
    places = {p.name: p for p in world.places.values()}
    beings = {p.name: p for p in world.beings.values() if p.present}
    call = Call(
        name="direct",
        system=prompts.DIRECT_SYSTEM,
        user=prompts.direct_user(world, recent),
        schema=schemas.direct_grammar(list(places), list(beings)),
        about="town",
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    # However it answered, it also said when it is worth asking again - and
    # that is set before anything else, so that a town which says "not for a
    # fortnight" gets its fortnight whether or not the rest was usable.
    world.town_wake_at = _asked_again(world, answer)
    if not answer or not answer.get("happens"):
        return None
    what = (answer.get("what") or "").strip()
    if not what:
        return None

    who = beings.get(answer.get("who") or "")
    place = places.get(answer.get("where") or "")
    if who is not None:
        # Something that happens to someone happens where they are standing.
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


# --------------------------------------------------------------------------
# the road, which runs both ways

#: What size of thing this world is, which is the author's design and not a
#: rate the engine is guessing at: below two people there is nobody to talk
#: to, and above eight it stops being a town where everybody knows everybody.
#: These are the only two numbers left on the road. The three that went with
#: them - forty-five days between departures, thirty between askings of the
#: road, a hundred and twenty once the town was settled - were rates, and
#: rates are what the timers replaced.
TOWN_FLOOR = 2
TOWN_CEILING = 8


def _asked_again(world, answer: Optional[dict]) -> Optional[float]:
    """When whatever just answered wants to be asked again.

    None when it said nothing usable, which leaves it with no timer - and
    `schedule.advance` then brings it round with everyone else rather than
    the engine picking an interval on its behalf.
    """
    hours = schedule.in_hours(answer, "ask_again_in_hours")
    return world.at + hours if hours is not None else None


def leaving_place(world):
    """Where the road goes out. A fact about the map, not about anybody."""
    return world.places.get(world.map.road_out)


def may_leave(world, being: Being) -> bool:
    """Whether this person could walk out of the world right now.

    Two facts, and neither is about what anybody wants: the road goes out from
    where they are standing, and there would still be a town behind them.
    Whether to take it, and at what hour, is theirs.
    """
    if not world.map.road_out or being.where.place != world.map.road_out:
        return False
    return sum(1 for p in world.beings.values() if p.present) > TOWN_FLOOR


def depart(world, being: Being, because: str, config,
           transcript: Optional[Transcript] = None):
    """Somebody takes the road. Returns (event, what it left in people).

    They are still present while it is happening, so the last thing in their
    file is the town from the top of the road. After that nobody asks them
    anything again - but what they have stays where it is, and so does every
    note the people they left behind wrote about them.
    """
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
    kept = perceive_all(world, event, config, transcript)
    # Going is one fact, written once: they are not here *because* this is
    # when they went. `Being.present` reads it back.
    being.when.left_at = world.at
    being.where.now("took the road out of town")
    return event, kept


def short_of_somebody(world) -> bool:
    """Has this town lost more people than it has taken in?

    A fact about the town, shown to the road so it can make something of it.
    """
    lost = sum(1 for p in world.beings.values() if not p.present)
    taken = sum(1 for e in world.chronicle.all() if e.category == ARRIVAL)
    return lost > taken


def may_arrive(world) -> bool:
    """Whether the road is worth asking, now. The road said when.

    A town already at the ceiling is never asked, because there is nowhere to
    put anybody; otherwise the road keeps its own timer, the same as the town
    and the same as a person.
    """
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


def arrive(world, config, transcript: Optional[Transcript] = None) -> Optional[Event]:
    """Ask the road whether anybody comes up it today. Usually nobody does."""
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
        # Nowhere of their own yet. Somewhere to sleep is a thing they will
        # have to come by here, like anyone else. Nothing keeping them awake
        # either: they have not had a night here, and the engine does not get
        # to say what is on their mind.
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


# --------------------------------------------------------------------------
# reflect

MAX_BELIEFS = 6
def may_reflect(world, being: Being, settling: bool) -> bool:
    """Whether this person is going over their day, now.

    A day ends when the person says it does: `settling` comes back from `act`
    and means they are stopping, not that the clock reached an hour.

    The one thing the engine checks is that there is something to go over.
    Somebody who has been handed nothing since they last did this has nothing
    to be left with, and is not asked.
    """
    if not settling:
        return False
    since = being.when.reflected_at if being.when.reflected_at is not None else -1.0
    return any(t.at > since for t in world.memories(being.id))


def reflect(world, being: Being, config,
            transcript: Optional[Transcript] = None) -> Optional[dict]:
    """What this person is left with, after a day of their own."""
    store = world.memories(being.id)
    since = being.when.reflected_at if being.when.reflected_at is not None else -1.0
    being.when.reflected_at = world.at
    # Their day is whatever has happened to them since they last stopped and
    # went over one, which for somebody who was awake for thirty hours is
    # thirty hours.
    today = [t for t in store if t.at > since]
    if not today:
        return None
    # The most live of the day, by the same equation as everything else.
    today = retrieval.recallable(today, world.at, limit=3)
    # What the day was about, in the mind's own words, is the cue for what
    # older things come back beside it - so a reckoning connects today to the
    # past it actually points at.
    cue = _placed(config, " ".join(t.account for t in today))
    older = [t for t in retrieval.recallable(store, world.at, cue, limit=7)
             if t not in today][:3]
    holds = held_beliefs(being, world.at, limit=MAX_BELIEFS)
    known = [world.beings[i].name for i in being.who.regards
             if i in world.beings]
    known += [p.name for p in _others_here(world, being)
              if p.name not in known]
    settings = _settings(config, "reflect")
    call = Call(
        name="reflect",
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

        # Whether this is a thing they already hold is theirs to say: it is a
        # question about meaning, and no amount of word overlap settles it.
        again = answer.get("belief_again") or ""
        existing = (holds[int(again) - 1]
                    if again.isdigit() and 1 <= int(again) <= len(holds) else None)
        if existing is not None:
            # Holding it again. The old wording stays; what changes is that
            # there is now one more occasion of having held it, which is the
            # only thing anywhere that makes a belief harder to lose.
            existing.came_up(world.at)
            for memory_id in origin:
                if memory_id not in existing.origin and len(existing.origin) < 3:
                    existing.origin.append(memory_id)
        else:
            being.who.beliefs.append(Belief(claim=text, origin=origin,
                                        held=[world.at],
                                        embedding=_placed(config, text)))
            if len(being.who.beliefs) > MAX_BELIEFS:
                # What goes is whatever is furthest from coming to mind, which
                # is a belief nobody has arrived at in a long time.
                keep = set(id(b) for b in
                           retrieval.recallable(being.who.beliefs, world.at,
                                                limit=MAX_BELIEFS))
                being.who.beliefs = [b for b in being.who.beliefs if id(b) in keep]

    # How they now hold somebody. This is the only thing in the world that
    # ever rewrites a regard after the seed wrote it, which is why two people
    # could live a year beside each other and neither change a word about the
    # other.
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
        # And it is laid down like anything else they are left holding, so it
        # can be brought to mind later, worn down by not being brought to
        # mind, and said out loud. This is `generative_agents`' reflection,
        # whose insights go back into associative memory carrying the ids of
        # what they came from (`cognitive_modules/reflect.py`), rather than
        # onto the persona.
        store.add(Memory(
            id=world.next_id("mem"),
            owner=being.id,
            at=world.at,
            account=thought,
            means="", feeling="",
            embedding=_placed(config, thought),
            origin=[t.id for t in today],
            told=[world.at],
        ))
    return answer


# --------------------------------------------------------------------------
# recall

def recall(world, being: Being, memory: Memory, config,
           transcript: Optional[Transcript] = None) -> bool:
    """The memory has just been brought up; ask how it comes back now.

    The words are the mind's. The engine only files the older wording in the
    memory's history, so the earlier version is not lost to anyone reading.
    """
    settings = _settings(config, "recall")
    age = max(0, int((world.at - memory.at) // HOURS_PER_DAY))
    call = Call(
        name="recall",
        system=prompts.RECALL_SYSTEM,
        user=prompts.recall_user(being, memory, age, world.at),
        schema=schemas.grammar("recall"),
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
                  embedding=_placed(config, new))
    # rewrite() logs the occasion; speak() already logged this one.
    del memory.told[-1:]
    world.memories(being.id).touch()
    return True
