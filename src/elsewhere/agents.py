"""Every model call a person, the town or the road makes, and how its answer
is written into the world."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import prompts, recollection, schedule, schemas
from .backends import Call, Settings, Transcript, ask, embed, get as get_backend
from .world.chronicle import ARRIVAL, DEPARTURE, Event, OCCURRENCE
from .world.entities import Being, When, Where, Who
from .world.notes import Note
from .world.pages import Page
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


def companions_present(world, being: Being) -> List[Being]:
    return [other for other in world.beings_at(being.where.place) if other.id != being.id]


def when_label(world) -> str:
    light = "light" if world.daylight else "dark"
    return f"{world.clock} and {light}, {world.season}, {world.date}"


def next_wake_at(world, answer: Optional[dict]) -> Optional[float]:
    """None when the answer gave nothing usable, leaving no timer."""
    hours = schedule.in_hours(answer)
    return world.at + hours if hours is not None else None


def viewpoint(world, being: Being, event: Event) -> str:
    recorded = (event.data.get("viewpoints") or {}).get(being.id)
    if recorded:
        return recorded
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

#: Budgets for one prompt: how many new events are put in front of somebody
#: at once (older unseen ones are gone before they ever saw them), and how
#: many of today's notes.
NEW_EVENTS = 12
DAY_NOTES = 12


def unseen(world, being: Being) -> List[Tuple[Event, str]]:
    """What reached this person since they last looked up, each with where
    they stood, oldest first. The only time anybody is shown the chronicle."""
    reached = [event for event in world.chronicle.all()[being.when.seen_through:]
               if being.id in event.informed]
    return [(event, viewpoint(world, being, event))
            for event in reached[-NEW_EVENTS:]]


def day_notes(world, being: Being) -> List[Note]:
    """What they have kept of today, in their own words: their notes since
    they last settled."""
    return world.notes(being.id).all()[being.when.settled_through:][-DAY_NOTES:]


def vectorize(configuration, text: str) -> List[float]:
    """Empty when no embedder is configured or it fails; recollection then
    ranks by BM25 alone."""
    settings = configuration.get("embed")
    if settings is None or not text.strip():
        return []
    vectors = embed([text], settings)
    return vectors[0] if vectors else []


def embedder_of(configuration) -> str:
    settings = configuration.get("embed")
    return f"{settings.backend}/{settings.model}" if settings is not None else ""


def recall(world, being: Being, configuration, cue: str) -> Optional[Note]:
    """One earlier note the moment points at; never one from today, which is
    already in front of them."""
    earlier = world.notes(being.id).all()[:being.when.settled_through]
    return recollection.recall(earlier, cue, vectorize(configuration, cue),
                               embedder_of(configuration))


def keep_note(world, being: Being, configuration, answer: dict,
              shown: List[Tuple[Event, str]]) -> None:
    """Write down what they said they kept, and mark what they were shown as
    seen either way: nothing is shown twice."""
    noted = (answer.get("noted") or "").strip()
    if noted:
        world.notes(being.id).append(Note(
            at=world.at, account=noted, event_ids=[event.id for event, _ in shown],
            embedding=vectorize(configuration, noted),
            embedded_by=embedder_of(configuration)))
    being.when.seen_through = len(world.chronicle)


def may_stir(world) -> bool:
    return schedule.town_due(world)


def may_leave(world, being: Being) -> bool:
    return bool(world.map.road) and being.where.place == world.map.road


def may_arrive(world) -> bool:
    return schedule.road_due(world)


def unused_id(world, name: str) -> str:
    slug = "".join(character for character in name.lower() if character.isalnum()) or "someone"
    candidate, suffix = slug, 2
    while candidate in world.beings:
        candidate, suffix = f"{slug}{suffix}", suffix + 1
    return candidate


# Call sites.

def act(world, being: Being, configuration,
        transcript: Optional[Transcript] = None) -> Decision:
    settings = call_settings(configuration, CallName.ACT)
    place = world.places.get(being.where.place)
    destinations = [world.places[neighbour]
                    for neighbour in world.map.beside(being.where.place)
                    if neighbour in world.places]
    companions = companions_present(world, being)
    shown = unseen(world, being)
    cue = " ".join([event.account for event, _ in shown]
                   + ([f"{place.name}. {place.description}"] if place else []))

    can_leave = may_leave(world, being)
    call = Call(
        name=CallName.ACT,
        system=prompts.ACT_SYSTEM,
        user=prompts.act_user(being, when_label(world), place, companions,
                              [destination.name for destination in destinations],
                              shown, day_notes(world, being),
                              recall(world, being, configuration, cue),
                              home_name=(world.places[being.where.home].name
                                         if being.where.home in world.places else ""),
                              may_leave=can_leave),
        schema=schemas.act_grammar([destination.name for destination in destinations],
                                   [companion.name for companion in companions],
                                   may_leave=can_leave),
        about=being.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    # Set before the None check: no usable answer means no timer, see
    # `schedule.advance_to_next_due`.
    schedule.set_timer(being, world, answer)
    if answer is None:
        return Decision(being.id, None, None, "", answered=False)
    keep_note(world, being, configuration, answer, shown)

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
        destination = next((destination for destination in destinations
                            if destination.name == name), None)
        action, target = (action, destination.id) if destination else (None, None)
    elif action == Action.TALK:
        companion = next((companion for companion in companions
                          if companion.name == name), None)
        action, target = (action, companion.id) if companion else (None, None)
    return Decision(being.id, action, target, because, doing, settling=settling)


def speak(world, speaker: Being, listener: Being, configuration,
          transcript: Optional[Transcript] = None) -> Optional[str]:
    """What they say, or None when they have nothing."""
    settings = call_settings(configuration, CallName.SPEAK)
    place = world.places.get(speaker.where.place)
    shown = unseen(world, speaker)
    cue = " ".join([listener.name] + [event.account for event, _ in shown])
    call = Call(
        name=CallName.SPEAK,
        system=prompts.SPEAK_SYSTEM,
        user=prompts.speak_user(speaker, listener, when_label(world),
                                place.name if place else "somewhere",
                                shown, day_notes(world, speaker),
                                recall(world, speaker, configuration, cue)),
        schema=schemas.grammar(CallName.SPEAK),
        about=speaker.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    if answer is None:
        return None
    keep_note(world, speaker, configuration, answer, shown)
    utterance = (answer.get("utterance") or "").strip().strip('"').strip()
    return utterance or None


def settle(world, being: Being, configuration,
           transcript: Optional[Transcript] = None) -> bool:
    """Ask them to go over what they kept of today, in their own notes, and
    write the page they carry into tomorrow; every page is kept. Without a
    usable answer nothing changes, so the same day is gone over next time."""
    settings = call_settings(configuration, CallName.SETTLE)
    today = day_notes(world, being)
    cue = " ".join([note.account for note in today] + being.where.lately)
    call = Call(
        name=CallName.SETTLE,
        system=prompts.SETTLE_SYSTEM,
        user=prompts.settle_user(being, when_label(world), today,
                                 lately=being.where.lately,
                                 recalled=recall(world, being, configuration, cue)),
        schema=schemas.grammar(CallName.SETTLE),
        about=being.id,
    )
    answer = ask(get_backend(settings.backend), call, settings, transcript)
    notebook = ((answer or {}).get("notebook") or "").strip()
    if not notebook:
        return False
    being.who.notebook = notebook
    being.when.settled_through = len(world.notes(being.id))
    world.pages(being.id).append(Page(at=world.at, notebook=notebook))
    return True


def stir(world, configuration,
         transcript: Optional[Transcript] = None) -> Optional[Event]:
    settings = call_settings(configuration, CallName.STIR)
    recent = world.chronicle.all()[-TOWN_RECENT_EVENTS:]
    places = {place.name: place for place in world.places.values()}
    residents = [resident for resident in world.beings.values() if resident.present]
    call = Call(
        name=CallName.STIR,
        system=prompts.STIR_SYSTEM,
        user=prompts.stir_user(world, recent),
        schema=schemas.stir_grammar(list(places),
                                    sorted({resident.name for resident in residents})),
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

    who = next((resident for resident in residents
                if resident.name == (answer.get("who") or "")), None)
    place = places.get(answer.get("where") or "")
    if who is not None:
        place = world.places.get(who.where.place, place)
    if place is None:
        return None

    informed = ([resident.id for resident in residents]
                if answer.get("reach") == "the whole town"
                else [resident.id for resident in world.beings_at(place.id)])
    viewpoints = {being_id: (f"right there, at {place.name}"
                             if world.beings[being_id].where.place == place.id
                             else f"at {world.places[world.beings[being_id].where.place].name}, "
                                  f"and word of it reached you there")
                  for being_id in informed}
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
    if not answer or not answer.get("happens"):
        return None

    name = (answer.get("name") or "").strip()
    if not name:
        return None
    place = world.places[world.map.road]

    origin = (answer.get("from_where") or "").strip()
    being = Being(
        id=unused_id(world, name),
        name=name,
        who=Who(card=(answer.get("card") or "").strip(),
                manner=(answer.get("manner") or "").strip()),
        where=Where(place=place.id, home=""),
        # Nothing that happened here before they came is theirs to see.
        when=When(arrived_at=world.at, seen_through=len(world.chronicle)),
    )
    world.beings[being.id] = being

    account = being.name
    if origin:
        account += f", from {origin},"
    account += f" came up the road into {world.name}."

    informed = [resident.id for resident in world.beings.values() if resident.present]
    viewpoints = {}
    for being_id in informed:
        if being_id == being.id:
            viewpoints[being_id] = f"at the top of the road, seeing {world.name} for the first time"
        elif world.beings[being_id].where.place == place.id:
            viewpoints[being_id] = f"right there, at {place.name}"
        else:
            whereabouts = world.places.get(world.beings[being_id].where.place)
            viewpoints[being_id] = (f"at {whereabouts.name}, and word of it reached you there"
                                    if whereabouts else "and word of it reached you")
    return world.record(
        ARRIVAL, account, place=place.id, involved=[being.id], informed=informed,
        data={"why_now": (answer.get("why_now") or "").strip(),
              "from_where": origin, "being": being.id, "viewpoints": viewpoints},
    )


def leave(world, being: Being, because: str) -> Event:
    place = world.places.get(being.where.place)
    where = place.name if place else "the road"
    informed = [resident.id for resident in world.beings.values() if resident.present]
    viewpoints = {}
    for being_id in informed:
        if being_id == being.id:
            viewpoints[being_id] = f"on the road out of {world.name}, looking back"
        elif world.beings[being_id].where.place == being.where.place:
            viewpoints[being_id] = f"right there, at {where}"
        else:
            whereabouts = world.places.get(world.beings[being_id].where.place)
            viewpoints[being_id] = (f"at {whereabouts.name}, and word of it reached you there"
                                    if whereabouts else "and word of it reached you")
    return world.record(
        DEPARTURE,
        f"{being.name} took the road out of {world.name} and did not come back.",
        place=being.where.place, involved=[being.id], informed=informed,
        data={"because": because, "being": being.id, "viewpoints": viewpoints},
    )
