"""Terminal access to a world whose judgements are not yours and not mine.

P0 commands: make one, look at it, and check that whatever is supposed to be
thinking can actually be reached.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import agents, config, retrieval, schedule, schemas, seed
from .backends import Call, Settings, Transcript, ask, get as get_backend
from .world import chronicle, store
from .world.store import World, clock_at, day_of

DEFAULT_ROOT = Path("world")


# helpers - shared by more than one command, none of them a command itself

def open_world(arguments) -> World:
    """Load an existing world, or exit if it doesn't exist."""
    root = Path(arguments.world)
    if not store.exists(root):
        sys.exit(f"No world at {root}. Run: elsewhere init --world {root}")
    return store.load(root)


def open_live(arguments):
    """Load a world and ensure it's still active (not closed)."""
    world = open_world(arguments)
    if world.closed:
        sys.exit(f"{world.name} has ended. Nothing more happens here.")
    return world


def transcript_for(world: World) -> Transcript:
    """Return the JSONL transcript path for the current world day."""
    return Transcript(world.root / "transcript" / f"day{day_of(world.at):05d}.jsonl")


def when(at: float) -> str:
    """Format a world timestamp as human-readable 'day N, HH:MM'."""
    return f"day {day_of(at)}, {clock_at(at)}"


def heading(text: str) -> str:
    """Format a section heading with an underline."""
    return f"\n{text}\n{'-' * len(text)}"


def name(world, person_id: str) -> str:
    """Look up a being's name by ID, or return the ID if not found."""
    being = world.beings.get(person_id)
    return being.name if being else person_id


def print_report(world, report) -> None:
    """Format and print a tick() report: what happened and who said/did what."""
    if report.idle:
        print(f"\n{report.label}\n  (nothing in the world is scheduled)")
        return
    # How far the clock moved, which is now different every step and is the
    # one number that says whose hour it was.
    print(f"\n{report.label}  (+{report.hours:g}h)")
    if report.occurrence is not None:
        occurrence = report.occurrence
        print(f"  * {occurrence.account}")
        for trace in occurrence.kept:
            print(f"      {name(world, trace.owner)} kept [{trace.feeling}] {trace.trace}")
    if report.arrival is not None:
        arrival = report.arrival
        print(f"  + {arrival.account}")
        for trace in arrival.kept:
            print(f"      {name(world, trace.owner)} kept [{trace.feeling}] {trace.trace}")
    for departure in report.departures:
        event = world.chronicle.get(departure.event_id)
        print(f"  - {event.account if event else name(world, departure.being_id) + ' left.'}")
        if departure.because:
            print(f'      "{departure.because}"')
        for trace in departure.kept:
            print(f"      {name(world, trace.owner)} kept [{trace.feeling}] {trace.trace}")
    talked = {talk.speaker for talk in report.talks} | {talk.listener for talk in report.talks}
    talked |= {departure.being_id for departure in report.departures}
    for person_id, decision in sorted(report.decisions.items()):
        being = world.beings[person_id]
        if person_id in talked:
            continue
        what = being.where.doing or decision.doing or decision.action
        why = (f'  - "{decision.because}"' if decision.because
               else ("  (no answer)" if not decision.answered else ""))
        print(f"  {being.name:<7} {what:<34}{why}")
    for talk in report.talks:
        for said in talk.turns:
            print(f"  {name(world, said.speaker):<7} to {name(world, said.listener)}: "
                  f"\"{said.line}\"")
            if said.reshaped:
                print(f"  {'':<7}   ({name(world, said.speaker)}'s memory was "
                      f"\"{said.reshaped[0]}\"; now \"{said.reshaped[1]}\")")
            heard = {trace.owner for trace in said.kept}
            for trace in said.kept:
                print(f"  {'':<7}   {name(world, trace.owner)} kept [{trace.feeling}] {trace.trace}")
            event = world.chronicle.get(said.event_id)
            for person_id in (event.reached if event else []):
                if person_id not in heard and person_id != said.speaker:
                    print(f"  {'':<7}   {name(world, person_id)} kept nothing of it")
    for person_id, reflection in report.reflections.items():
        line = reflection.get("thought") or ""
        extra = (f' -> now believes "{reflection["belief"]}"'
                 if reflection.get("belief") else "")
        # A reckoning happens when the person says they are stopping, which
        # is whatever hour that turns out to be.
        print(f"  {name(world, person_id):<7} stops, and is left with: \"{line}\"{extra}")
    if report.silent:
        print(f"  ({report.silent} mind(s) gave no usable answer and stayed put)")


# create - the only commands that make a world

def command_init(arguments) -> None:
    """Create a new world with initial characters, places, and backstory."""
    root = Path(arguments.world)
    if store.exists(root) and not arguments.force:
        sys.exit(f"{root} already holds a world. Use --force to start over.")
    started = time.time()
    tape = Transcript(root / "transcript" / "init.jsonl")
    world = seed.create(root, name=arguments.name, remember=not arguments.blank,
                        transcript=tape)
    world.last_tick_at = time.time()
    store.save(world)
    remembered = sum(len(world.traces(being.id)) for being in world.beings.values())
    output = [
        f"{world.name} exists. {world.label()}",
        f"  {len(world.beings)} people, {len(world.places)} places, {len(world.chronicle)} events already behind them",
        f"  {remembered} of those events left a mark on somebody ({time.time() - started:.1f}s)",
    ]
    if remembered == 0 and not arguments.blank:
        output.append("  (nothing stuck - is a model reachable? try: elsewhere doctor)")
    output.append(f"  config at {root / 'config.json'}")
    print("\n".join(output))


# read-only views - load the world, never change what happened in it

def command_status(arguments) -> None:
    """Show world status: where everyone is, and what they remember."""
    world = open_world(arguments)
    print(f"{world.name} - {world.label()}")
    print(f"  chronicle: {len(world.chronicle)} events")
    for place in world.places.values():
        here = world.beings_at(place.id)
        if not here:
            continue
        print(f"  {place.name}: " +
              ", ".join(f"{being.name} ({being.where.doing or 'just here'})"
                        for being in here))
    gone = [being for being in world.beings.values() if not being.present]
    if gone:
        print("  gone: " + ", ".join(
            f"{being.name} ({when(being.when.left_at)})" if being.when.left_at
            else being.name
            for being in sorted(gone, key=lambda being: being.when.left_at or 0)))
    total = 0
    for being in world.beings.values():
        trace_store = world.traces(being.id)
        # Somebody who left is counted as they were the moment they went. The
        # world has no idea what has happened to them since and will not
        # pretend to by going on fading things nobody here can see.
        at = world.at if being.present else (being.when.left_at or world.at)
        traces = list(trace_store)
        live = retrieval.recallable(traces, at)
        total += len(traces)
        mark = "" if being.present else "  (left)"
        print(f"  {being.name:<8} {len(live)} within reach, "
              f"{len(traces) - len(live)} not coming to mind{mark}")
    print(f"  {total} traces in total")


def command_being(arguments) -> None:
    """Show detailed view of one being: who they are, what they remember, who they know."""
    world = open_world(arguments)
    being = world.being_byname(arguments.name)
    if being is None:
        sys.exit(f"Nobody here is called {arguments.name!r}")
    print(heading(being.name))
    print(f"  {being.who.card}")
    at = world.at if being.present else (being.when.left_at or world.at)
    if not being.present:
        print(f"\n  Left on {when(at)}. What follows is how they stood "
              f"then; nothing here has touched it since.")
    else:
        print(f"\n  at: "
              f"{world.places[being.where.place].name if being.where.place in world.places else '-'}")
        if being.who.thought:
            print(f"  keeps coming back to: {being.who.thought}")
    if being.when.arrived_at:
        print(f"  came up the road on {when(being.when.arrived_at)}")
    if being.who.wants:
        print("  wants: " + "; ".join(being.who.wants))
    if being.who.beliefs:
        print("\n  holds to be true")
        store = list(world.traces(being.id))
        for belief in retrieval.recallable(being.who.beliefs, at,
                                            limit=len(being.who.beliefs)):
            lost = ("  (cannot say why any more)"
                    if retrieval.on_faith(belief, world.traces(being.id), at) else "")
            held = len(belief.held) or 1
            print(f"    [held {held}x] {belief.claim}{lost}")
    known = [(world.beings[person_id], regard) for person_id, regard in
             sorted(being.who.regards.items(), key=lambda pair: -pair[1].last_seen_at)
             if person_id in world.beings]
    print("\n  who they know" if known else "\n  they know nobody here yet")
    for other, regard in known:
        gone = "  (gone)" if not other.present else ""
        print(f"    {other.name:<8} {regard.account or '-'}{gone}")
    traces = list(world.traces(being.id))
    within = retrieval.recallable(traces, at, limit=arguments.limit)
    print(f"\n  memory: {len(traces)} traces, "
          f"{max(0, len(traces) - len(within))} that would not come back")
    for trace in within:
        print(f"    {when(trace.at):<18} [{trace.feeling}] {trace.trace}")
        if trace.means:
            print(f"          ~ {trace.means}")
        told = len(trace.told) or 1
        print(f"          come up {told}x  "
              f"{retrieval.chance(retrieval.activation(trace, at)):.0%} it comes to mind")
        # Earlier wordings. The only place the world shows that a memory
        # moved, which is the whole claim this project makes about memory.
        for was in reversed(trace.history):
            print(f"          was: \"{was}\"")
        # Something they arrived at themselves rather than a version of
        # something that happened. What it was a thought about is the only
        # thing that makes it readable a year later.
        for source in trace.origin:
            came = world.traces(being.id).get(source)
            if came is not None:
                print(f"          out of: \"{came.trace}\"")


def command_timeline(arguments) -> None:
    """Show all events in chronological order (most recent by default)."""
    world = open_world(arguments)
    print(heading(f"{world.name}: what happened"))
    for event in world.chronicle.all()[-arguments.limit:]:
        print(f"  {event.id}  {when(event.at):<18} {event.category:<12} {event.account}")


def command_event(arguments) -> None:
    """Show one event and what it left in each being who experienced it."""
    world = open_world(arguments)
    event = world.chronicle.get(arguments.event_id)
    if event is None:
        sys.exit(f"No event {arguments.event_id}")
    place = world.places.get(event.place or "")
    print(heading(f"{event.id} - {when(event.at)}, {event.category}, "
                  f"at {place.name if place else '-'}"))
    print(f"  History says:  {event.account}")
    print("\n  What it left in people:")
    for being in world.beings.values():
        traces = world.traces(being.id).about_event(event.id)
        if not traces:
            if being.id in event.reached:
                print(f"    {being.name:<8} - nothing. They were there.")
            continue
        mine = list(world.traces(being.id))
        for trace in traces:
            within = trace in retrieval.recallable(mine, world.at)
            odds = retrieval.chance(retrieval.activation(trace, world.at))
            state = (f"{odds:.0%} it comes to mind" if within
                     else "something else comes back instead")
            print(f"    {being.name:<8} \"{trace.trace}\"")
            if trace.means:
                print(f"    {'':<8}   {trace.feeling}: {trace.means}")
            print(f"    {'':<8}   ({state}, come up {len(trace.told) or 1}x)")
            for was in reversed(trace.history):
                print(f"    {'':<8}   was: \"{was}\"")


def command_news(arguments) -> None:
    """Show new events since last time you checked (marks them as read by default)."""
    world = open_world(arguments)
    events = world.chronicle.all()[world.news_seen:]
    print(f"{world.name} - {world.label()}")
    if not events:
        print("  Nothing has happened since you last looked.")
    for event in events:
        place = world.places.get(event.place or "")
        print(f"\n  {when(event.at)}, {place.name if place else '-'}")
        mark = {chronicle.OCCURRENCE: "* ", chronicle.ARRIVAL: "+ ",
                chronicle.DEPARTURE: "- "}
        print(f"    {mark.get(event.category, '')}{event.account}")
        for person_id in event.reached:
            for trace in world.traces(person_id).about_event(event.id):
                print(f"      {name(world, person_id)} kept [{trace.feeling}] {trace.trace}")
    print("\n  Now:")
    for being in sorted(world.beings.values(), key=lambda person: person.name):
        if not being.present:
            continue
        place = world.places.get(being.where.place)
        print(f"    {being.name:<7} at {place.name if place else '-':<20} "
              f"{being.where.doing or ''}")
    if not arguments.peek:
        world.news_seen = len(world.chronicle)
        store.save(world)


# time passing - move the world's clock forward; internal

def _command_catchup(arguments) -> None:
    """[INTERNAL] Live the hours the wall clock says are owed. Run by scripts/schedule.sh."""
    from .tick import owed_hours, settle_clock, tick
    from .backends import probe

    stamp = time.strftime("%Y-%m-%d %H:%M")
    world = open_live(arguments)
    try:
        with store.tick_lock(world.root):
            now = time.time()
            if world.last_tick_at is None:
                world.last_tick_at = now
                store.save(world)
                print(f"[{stamp}] clock started for {world.name}")
                return
            owed = owed_hours(world.last_tick_at, now)
            # How far ahead the world is already scheduled. Nothing is owed
            # until the wall clock has caught up with the last thing somebody
            # said they would be doing.
            ahead = schedule.next_at(world)
            if ahead is not None and world.at + owed < ahead:
                print(f"[{stamp}] checked; nothing is due for "
                      f"{ahead - world.at - owed:.1f}h of world time")
                return
            configuration = config.load(world.root)
            ok, message = probe(configuration["act"])
            if not ok:
                # The world waits rather than going on without minds.
                print(f"[{stamp}] {owed:.1f}h owed, but the minds are {message}; "
                      f"{world.name} waits")
                return
            # Live as much of the backlog as the people in it asked to be
            # woken for, in whatever steps they asked for - which is why there
            # is no step size here either. `--max` is a bound on model calls,
            # not on time.
            began, steps = world.at, 0
            while world.at - began < owed and steps < arguments.max:
                report = tick(world, configuration, transcript_for(world))
                steps += 1
                store.save(world)
                print(f"[{stamp}]", end="")
                print_report(world, report)
                if report.idle:
                    break
            lived = world.at - began
            world.last_tick_at = settle_clock(world.last_tick_at, now, lived, owed)
            store.save(world)
            if lived < owed:
                print(f"[{stamp}] {owed - lived:.1f}h more were owed; "
                      f"{world.name} slept through them")
    except store.Locked as exception:
        print(f"[{stamp}] skipped: {exception}")


def _command_tick(arguments) -> None:
    """[DEV] Advance the world N steps by hand, ignoring the wall clock."""
    from .tick import tick

    world = open_live(arguments)
    configuration = config.load(world.root)
    try:
        with store.tick_lock(world.root):
            for _ in range(arguments.n):
                report = tick(world, configuration, transcript_for(world))
                store.save(world)
                print_report(world, report)
            world.last_tick_at = time.time()
            store.save(world)
    except store.Locked as exception:
        sys.exit(f"Not now: {exception}")


# development - diagnostics and prompt tuning; internal

def _command_doctor(arguments) -> None:
    """[DEV] Diagnostic: check if model backends are reachable and working."""
    root = Path(arguments.world)
    configuration = config.load(root) if store.exists(root) else {
        name: Settings.from_dict(settings_dict)
        for name, settings_dict in config.default_config()["agents"].items()}
    print(heading("Minds"))
    probe = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    seen = {}
    for name, settings in configuration.items():
        if name == "embed":
            continue                      # not a mind; probed on its own below
        key = (settings.backend, settings.model)
        if key in seen:
            print(f"  {name:<9} {settings.backend}/{settings.model:<18} (same model as above)")
            continue
        call = Call(name="probe", system="Answer only with JSON.",
                    user='Reply exactly {"ok": true}.', schema=probe, about="doctor")
        started = time.time()
        try:
            raw = get_backend(settings.backend).complete(
                call, settings.model, 0.0, settings.extra)
            from .backends import extract_json
            parsed = extract_json(raw)
            verdict = (f"ok ({time.time() - started:.1f}s)" if parsed is not None
                       else f"answered, but not with JSON: {raw[:60]!r}")
        except Exception as exception:
            verdict = f"unreachable: {type(exception).__name__}: {exception}"
        seen[key] = verdict
        print(f"  {name:<9} {settings.backend}/{settings.model:<18} {verdict}")
    embed = configuration.get("embed")
    if embed is not None:
        print(heading("Where a memory reads from"))
        from .backends import place as place_in_meaning
        started = time.time()
        got = place_in_meaning(["the water came up over the waterline"], embed)
        if got:
            print(f"  embed     {embed.backend}/{embed.model:<18} "
                  f"ok ({len(got[0])} dims, {time.time() - started:.1f}s)")
        else:
            print(f"  embed     {embed.backend}/{embed.model:<18} "
                  f"unreachable - retrieval falls back on how reachable a "
                  f"memory is, which still works")
    print("\n  Set ELSEWHERE_BACKEND=stub to run without any of this.")


def _command_remember(arguments) -> None:
    """[DEV] Re-run one event past all beings for prompt tuning."""
    world = open_world(arguments)
    event = world.chronicle.get(arguments.event_id)
    if event is None:
        sys.exit(f"No event {arguments.event_id}")
    configuration = config.load(world.root)
    transcript = transcript_for(world)
    made = agents.perceive_all(world, event, configuration, transcript)
    for being in world.beings.values():
        world.traces(being.id).save()
    store.save(world)
    print(f"{len(made)} of {len(event.reached)} people kept something.")
    for trace in made:
        print(f"  {world.beings[trace.owner].name:<8} [{trace.feeling}] {trace.trace}")


# cli wiring

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elsewhere", description="A persistent world that remembers.")
    parser.add_argument("--world", default=str(DEFAULT_ROOT), help="path to the world")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    subparser = subparsers.add_parser("init", help="make a small world")
    subparser.add_argument("--name", default="Wend")
    subparser.add_argument("--force", action="store_true")
    subparser.add_argument("--blank", action="store_true",
                            help="do not run the backstory past anyone")
    subparser.set_defaults(func=command_init)

    # read-only views
    subparser = subparsers.add_parser(
        "status", help="where everyone is, and how much they hold")
    subparser.set_defaults(func=command_status)

    subparser = subparsers.add_parser("person", help="who someone is now")
    subparser.add_argument("name")
    subparser.add_argument("--limit", type=int, default=8)
    subparser.set_defaults(func=command_being)

    subparser = subparsers.add_parser("timeline", help="what happened")
    subparser.add_argument("--limit", type=int, default=30)
    subparser.set_defaults(func=command_timeline)

    subparser = subparsers.add_parser(
        "event", help="one event, and what it left in people")
    subparser.add_argument("event_id")
    subparser.set_defaults(func=command_event)

    # The one view that writes: it remembers where you stopped reading.
    subparser = subparsers.add_parser(
        "news", help="what happened since you last looked")
    subparser.add_argument("--peek", action="store_true", help="look without marking it read")
    subparser.set_defaults(func=command_news)

    # time passing (internal)
    subparser = subparsers.add_parser(
        "catchup", help="[INTERNAL] live the hours the wall clock says are owed")
    subparser.add_argument("--max", type=int, default=8,
                            help="most steps to live in one go; a bound on model calls, "
                                 "not on how far the clock may move")
    subparser.set_defaults(func=_command_catchup)

    subparser = subparsers.add_parser("tick", help="[DEV] manually advance N steps")
    subparser.add_argument("-n", type=int, default=1)
    subparser.set_defaults(func=_command_tick)

    # development (internal)
    subparser = subparsers.add_parser("doctor", help="[DEV] diagnose model backend connectivity")
    subparser.set_defaults(func=_command_doctor)

    subparser = subparsers.add_parser(
        "remember", help="[DEV] re-run one event for prompt tuning")
    subparser.add_argument("event_id")
    subparser.set_defaults(func=_command_remember)

    return parser


def main(argument_list: Optional[List[str]] = None) -> int:
    arguments = build_parser().parse_args(argument_list)
    arguments.func(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
