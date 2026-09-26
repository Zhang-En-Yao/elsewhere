"""Terminal access to a world whose judgements are not yours and not mine.

P0 commands: make one, look at it, and check that whatever is supposed to be
thinking can actually be reached.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import agents, retrieval, schedule, schemas, seed
from .backends import Transcript, ask, probe
from .configuration import MINDS, configure, load_configuration, path_of
from .world import chronicle, store
from .world.store import World, clock_at, day_of

DEFAULT_ROOT = Path("world")

# What used to override the configuration from the environment. They do
# nothing now, and saying so is better than letting somebody believe they do.
ABANDONED = {
    "ELSEWHERE_BACKEND": "backend",
    "ELSEWHERE_MODEL": "model",
    "ELSEWHERE_OPENAI_BASE": "base",
    "ELSEWHERE_HTTP_TIMEOUT": "timeout",
}


# helpers - shared by more than one command, none of them a command itself

def open_world(arguments) -> World:
    """Load an existing world, or exit if it doesn't exist."""
    root = Path(arguments.world)
    if not store.exists(root):
        sys.exit(f"No world at {root}. Run: elsewhere --world {root} initialize")
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


def report_lines(world, report) -> List[str]:
    """A tick() report as lines: what happened, and who said or did what.

    Lines rather than prints, because two things show a step now - a terminal
    and a window (`tui/screen.py`) - and a report that formats itself in one
    place cannot say two different things about the same step.
    """
    if report.idle:
        return [report.label, "  (nothing in the world is scheduled)"]
    out: List[str] = []
    # How far the clock moved, which is now different every step and is the
    # one number that says whose hour it was.
    out.append(f"{report.label}  (+{report.hours:g}h)")
    if report.occurrence is not None:
        occurrence = report.occurrence
        out.append(f"  * {occurrence.account}")
        for memory in occurrence.kept:
            out.append(f"      {name(world, memory.owner)} kept "
                       f"[{memory.feeling}] {memory.account}")
    if report.arrival is not None:
        arrival = report.arrival
        out.append(f"  + {arrival.account}")
        for memory in arrival.kept:
            out.append(f"      {name(world, memory.owner)} kept "
                       f"[{memory.feeling}] {memory.account}")
    for departure in report.departures:
        event = world.chronicle.get(departure.event_id)
        out.append(f"  - {event.account if event else name(world, departure.being_id) + ' left.'}")
        if departure.because:
            out.append(f'      "{departure.because}"')
        for memory in departure.kept:
            out.append(f"      {name(world, memory.owner)} kept "
                       f"[{memory.feeling}] {memory.account}")
    talked = {talk.speaker for talk in report.talks} | {talk.listener for talk in report.talks}
    talked |= {departure.being_id for departure in report.departures}
    for person_id, decision in sorted(report.decisions.items()):
        being = world.beings[person_id]
        if person_id in talked:
            continue
        what = being.where.doing or decision.doing or decision.action
        why = (f'  - "{decision.because}"' if decision.because
               else ("  (no answer)" if not decision.answered else ""))
        out.append(f"  {being.name:<7} {what:<34}{why}")
    for talk in report.talks:
        for said in talk.turns:
            out.append(f"  {name(world, said.speaker):<7} to {name(world, said.listener)}: "
                       f"\"{said.line}\"")
            if said.reshaped:
                out.append(f"  {'':<7}   ({name(world, said.speaker)}'s memory was "
                           f"\"{said.reshaped[0]}\"; now \"{said.reshaped[1]}\")")
            heard = {memory.owner for memory in said.kept}
            for memory in said.kept:
                out.append(f"  {'':<7}   {name(world, memory.owner)} kept "
                           f"[{memory.feeling}] {memory.account}")
            event = world.chronicle.get(said.event_id)
            for person_id in (event.reached if event else []):
                if person_id not in heard and person_id != said.speaker:
                    out.append(f"  {'':<7}   {name(world, person_id)} kept nothing of it")
    for person_id, reflection in report.reflections.items():
        line = reflection.get("thought") or ""
        extra = (f' -> now believes "{reflection["belief"]}"'
                 if reflection.get("belief") else "")
        # A reckoning happens when the person says they are stopping, which
        # is whatever hour that turns out to be.
        out.append(f"  {name(world, person_id):<7} stops, and is left with: "
                   f"\"{line}\"{extra}")
    if report.silent:
        out.append(f"  ({report.silent} mind(s) gave no usable answer and stayed put)")
    return out


def print_report(world, report) -> None:
    """The same report, on a terminal, with a blank line above it."""
    print()
    for line in report_lines(world, report):
        print(line)


# create - the only commands that make a world

def command_initialize(arguments) -> None:
    """Create a new world with initial characters, places, and backstory."""
    root = Path(arguments.world)
    if store.exists(root) and not arguments.force:
        sys.exit(f"{root} already holds a world. Use --force to start over.")
    started = time.time()
    transcript = Transcript(root / "transcript" / "init.jsonl")
    world = seed.create(root, name=arguments.name, remember=not arguments.blank,
                        transcript=transcript)
    world.last_tick_at = time.time()
    store.save(world)
    remembered = sum(len(world.memories(being.id)) for being in world.beings.values())
    output = [
        f"{world.name} exists. {world.label()}",
        f"  {len(world.beings)} people, {len(world.places)} places, {len(world.chronicle)} events already behind them",
        f"  {remembered} memories formed from them ({time.time() - started:.1f}s)",
    ]
    if remembered == 0 and not arguments.blank:
        output.append("  (nothing stuck - is a model reachable? try: elsewhere doctor)")
    output.append(f"  configuration at {path_of(root)}")
    print("\n".join(output))


# read-only views - load the world, never change what happened in it

def command_status(arguments) -> None:
    """Show world status: where everyone is, and what they remember."""
    world = open_world(arguments)
    print(f"{world.name} - {world.label()}" + ("  (ended)" if world.closed else ""))
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
        memory_store = world.memories(being.id)
        # Somebody who left is counted as they were the moment they went. The
        # world has no idea what has happened to them since and will not
        # pretend to by going on fading things nobody here can see.
        at = world.at if being.present else (being.when.left_at or world.at)
        memories = list(memory_store)
        live = retrieval.recallable(memories, at)
        total += len(memories)
        mark = "" if being.present else "  (left)"
        print(f"  {being.name:<8} {len(live)} within reach, "
              f"{len(memories) - len(live)} not coming to mind{mark}")
    print(f"  {total} memories in total")


def command_being(arguments) -> None:
    """Show detailed view of one being: who they are, what they remember, who they know."""
    world = open_world(arguments)
    being = world.being_by_name(arguments.name)
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
        store = list(world.memories(being.id))
        for belief in retrieval.recallable(being.who.beliefs, at,
                                            limit=len(being.who.beliefs)):
            lost = ("  (cannot say why any more)"
                    if retrieval.on_faith(belief, world.memories(being.id), at) else "")
            held = len(belief.held) or 1
            print(f"    [held {held}x] {belief.claim}{lost}")
    known = [(world.beings[person_id], regard) for person_id, regard in
             sorted(being.who.regards.items(), key=lambda pair: -pair[1].last_seen_at)
             if person_id in world.beings]
    print("\n  who they know" if known else "\n  they know nobody here yet")
    for other, regard in known:
        gone = "  (gone)" if not other.present else ""
        print(f"    {other.name:<8} {regard.account or '-'}{gone}")
    memories = list(world.memories(being.id))
    within = retrieval.recallable(memories, at, limit=arguments.limit)
    print(f"\n  memory: {len(memories)} memories, "
          f"{max(0, len(memories) - len(within))} that would not come back")
    for memory in within:
        print(f"    {when(memory.at):<18} [{memory.feeling}] {memory.account}")
        if memory.means:
            print(f"          ~ {memory.means}")
        told = len(memory.told) or 1
        print(f"          come up {told}x  "
              f"{retrieval.chance(retrieval.activation(memory, at)):.0%} it comes to mind")
        # Earlier wordings. The only place the world shows that a memory
        # moved, which is the whole claim this project makes about memory.
        for was in reversed(memory.history):
            print(f"          was: \"{was}\"")
        # Something they arrived at themselves rather than a version of
        # something that happened. What it was a thought about is the only
        # thing that makes it readable a year later.
        for source in memory.origin:
            came = world.memories(being.id).get(source)
            if came is not None:
                print(f"          out of: \"{came.account}\"")


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
        memories = world.memories(being.id).about_event(event.id)
        if not memories:
            if being.id in event.reached:
                print(f"    {being.name:<8} - nothing. They were there.")
            continue
        mine = list(world.memories(being.id))
        for memory in memories:
            within = memory in retrieval.recallable(mine, world.at)
            odds = retrieval.chance(retrieval.activation(memory, world.at))
            state = (f"{odds:.0%} it comes to mind" if within
                     else "something else comes back instead")
            print(f"    {being.name:<8} \"{memory.account}\"")
            if memory.means:
                print(f"    {'':<8}   {memory.feeling}: {memory.means}")
            print(f"    {'':<8}   ({state}, come up {len(memory.told) or 1}x)")
            for was in reversed(memory.history):
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
            for memory in world.memories(person_id).about_event(event.id):
                print(f"      {name(world, person_id)} kept [{memory.feeling}] {memory.account}")
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


def command_watch(arguments) -> None:
    """Sit with the world: one window, open while it goes on without you.

    The printed views each answer one question and stop, which is right for a
    command and wrong for sitting with a world - what is worth seeing is a
    memory in reach beside the same memory out of reach, and the hour somebody
    arrived beside what everyone turned out to have kept of it. The window is
    the same views with room to put two of those side by side.

    It only reads. Nothing on any key in it writes anything under the world's
    directory, which is why there is no key that lets the world go on and none
    that marks the news read - `elsewhere continue` and `elsewhere news` are
    worth having typed. Run either in another terminal, or leave the schedule
    running behind it, and the window picks the change up by itself.
    """
    root = Path(arguments.world)
    if not store.exists(root):
        sys.exit(f"No world at {root}. Run: elsewhere --world {root} initialize")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        # A window has nowhere to be. The printed views do, and they pipe.
        sys.exit("watch needs a terminal. For a pipe or a log: elsewhere news")
    try:
        from .tui import screen
    except ImportError as exception:
        sys.exit(f"no curses on this Python, so no window: {exception}")
    try:
        screen.run(root)
    except ValueError as exception:
        # A world an older Elsewhere wrote. Says so rather than a traceback.
        sys.exit(str(exception))


# time passing - move the world's clock forward

def go_on(world: World, most: int = 8, say=print) -> None:
    """Live the hours the wall clock says are owed, and say what happened.

    `say` is where the account of it goes, a line at a time, and it defaults
    to the terminal that asked. It is a seam rather than a setting: what lives
    a step and what shows a step are different questions, and `report_lines`
    below is the answer to the second one for anybody who needs it.
    """
    from .tick import owed_hours, settle_clock, tick

    stamp = time.strftime("%Y-%m-%d %H:%M")
    try:
        with store.tick_lock(world.root):
            now = time.time()
            if world.last_tick_at is None:
                world.last_tick_at = now
                store.save(world)
                say(f"[{stamp}] clock started for {world.name}")
                return
            owed = owed_hours(world.last_tick_at, now)
            # How far ahead the world is already scheduled. Nothing is owed
            # until the wall clock has caught up with the last thing somebody
            # said they would be doing.
            ahead = schedule.next_at(world)
            if ahead is not None and world.at + owed < ahead:
                say(f"[{stamp}] checked; nothing is due for "
                    f"{ahead - world.at - owed:.1f}h of world time")
                return
            configuration = load_configuration(world.root)
            ok, message = probe(configuration["act"])
            if not ok:
                # The world waits rather than going on without minds.
                say(f"[{stamp}] {owed:.1f}h owed, but the minds are {message}; "
                    f"{world.name} waits")
                return
            # Live as much of the backlog as the people in it asked to be
            # woken for, in whatever steps they asked for - which is why there
            # is no step size here either. `most` is a bound on model calls,
            # not on time.
            began, steps = world.at, 0
            while world.at - began < owed and steps < most:
                report = tick(world, configuration, transcript_for(world))
                steps += 1
                store.save(world)
                say(f"[{stamp}]")
                for line in report_lines(world, report):
                    say(line)
                if report.idle:
                    break
            lived = world.at - began
            world.last_tick_at = settle_clock(world.last_tick_at, now, lived, owed)
            store.save(world)
            if lived < owed:
                say(f"[{stamp}] {owed - lived:.1f}h more were owed; "
                    f"{world.name} slept through them")
    except store.Locked as exception:
        say(f"[{stamp}] skipped: {exception}")


def command_continue(arguments) -> None:
    """Let the world go on: live the hours the wall clock says are owed."""
    go_on(open_live(arguments), arguments.max)


def _command_tick(arguments) -> None:
    """[DEV] Advance the world N steps by hand, ignoring the wall clock."""
    from .tick import tick

    world = open_live(arguments)
    configuration = load_configuration(world.root)
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


# ending - the one way a world stops for good

def command_end(arguments) -> None:
    """End the world: nothing more happens in it, and all that did stays readable."""
    try:
        with store.tick_lock(Path(arguments.world)):
            # Loaded under the lock, so a step that was running has finished
            # and saved before this looks at the world.
            world = open_world(arguments)
            if world.closed:
                print(f"{world.name} had already ended.")
                return
            world.closed = True
            store.save(world)
    except store.Locked as exception:
        sys.exit(f"Not now: {exception}")
    print(f"{world.name} has ended. {world.label()}")
    print(f"  {len(world.chronicle)} events are on record; status, person, timeline "
          f"and event still read them.")
    print("  If it was scheduled: make unschedule")


# development - diagnostics and prompt tuning; internal

def _command_doctor(arguments) -> None:
    """[DEV] Diagnostic: check if model backends are reachable and working."""
    root = Path(arguments.world)
    path = path_of(root)
    configuration = load_configuration(root)
    print(f"Reading {path}" if path.exists()
          else f"No {path} yet; these are the defaults it would be written with")
    print(heading("Minds"))
    seen = set()
    for name, settings in configuration.items():
        if name == "embed":
            continue                      # not a mind; probed on its own below
        key = (settings.backend, settings.model, settings.base)
        if key in seen:
            print(f"  {name:<9} {settings.backend}/{settings.model:<18} (same model as above)")
            continue
        seen.add(key)
        ok, verdict = probe(settings)
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
    print(f'\n  Set "backend": "stub" in {path} to run without any of this.')


def command_configure(arguments) -> None:
    """Point the minds at one backend and model, in the world's configuration."""
    root = Path(arguments.world)
    try:
        path = configure(root, arguments.backend, arguments.model, arguments.base,
                         arguments.call or MINDS)
    except KeyError as exception:
        sys.exit(str(exception.args[0]))
    where = f" at {arguments.base}" if arguments.base else ""
    print(f"{', '.join(arguments.call or MINDS)} -> "
          f"{arguments.backend}/{arguments.model}{where}")
    print(f"  written to {path}; check it with: elsewhere --world {root} doctor")


def _command_remember(arguments) -> None:
    """[DEV] Re-run one event past all beings for prompt tuning.

    It is a development tool, but it is a *writing* one - it lays down memories
    and saves the world - so it is held to what every other writing command is
    held to. Under the lock, because a step running beside it would have one of
    the two overwrite the other; and not in a world that has ended, because
    `end` says nothing more happens there and a tuning run is still something
    happening.
    """
    try:
        with store.tick_lock(Path(arguments.world)):
            # Loaded under the lock, so a step that was running has finished
            # and saved before this looks at the world.
            world = open_live(arguments)
            event = world.chronicle.get(arguments.event_id)
            if event is None:
                sys.exit(f"No event {arguments.event_id}")
            configuration = load_configuration(world.root)
            made = agents.perceive_all(world, event, configuration,
                                       transcript_for(world))
            for being in world.beings.values():
                world.memories(being.id).save()
            store.save(world)
    except store.Locked as exception:
        sys.exit(f"Not now: {exception}")
    print(f"{len(made)} of {len(event.reached)} people kept something.")
    for memory in made:
        print(f"  {world.beings[memory.owner].name:<8} [{memory.feeling}] {memory.account}")


# cli wiring

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elsewhere", description="A persistent world that remembers.")
    parser.add_argument("--world", default=str(DEFAULT_ROOT), help="path to the world")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    subparser = subparsers.add_parser("initialize", help="make a small world")
    subparser.add_argument("--name", default="Nod")
    subparser.add_argument("--force", action="store_true")
    subparser.add_argument("--blank", action="store_true",
                            help="do not run the backstory past anyone")
    subparser.set_defaults(func=command_initialize)

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

    # The same views, in a window, for when you mean to sit with it rather
    # than ask it one question.
    subparser = subparsers.add_parser(
        "watch", help="sit with the world in a window; reads only")
    subparser.set_defaults(func=command_watch)

    # time passing
    subparser = subparsers.add_parser(
        "continue",
        help="let the world go on for however long you have been away")
    subparser.add_argument("--max", type=int, default=8,
                            help="most steps to live in one go; a bound on model calls, "
                                 "not on how far the clock may move")
    subparser.set_defaults(func=command_continue)

    subparser = subparsers.add_parser("tick", help="[DEV] manually advance N steps")
    subparser.add_argument("-n", type=int, default=1)
    subparser.set_defaults(func=_command_tick)

    # ending
    subparser = subparsers.add_parser(
        "end", help="end the world for good; what happened stays readable")
    subparser.set_defaults(func=command_end)

    # development (internal)
    subparser = subparsers.add_parser("doctor", help="[DEV] diagnose model backend connectivity")
    subparser.set_defaults(func=_command_doctor)

    subparser = subparsers.add_parser(
        "configure", help="point the minds at one backend and model")
    subparser.add_argument("--backend", required=True)
    subparser.add_argument("--model", required=True)
    subparser.add_argument("--base", help="where the server is, if not the default")
    subparser.add_argument("--call", action="append",
                           help="only this call site (repeatable); "
                                "default: every mind, not the embedder")
    subparser.set_defaults(func=command_configure)

    subparser = subparsers.add_parser(
        "remember", help="[DEV] re-run one event for prompt tuning")
    subparser.add_argument("event_id")
    subparser.set_defaults(func=_command_remember)

    return parser


def main(argument_list: Optional[List[str]] = None) -> int:
    arguments = build_parser().parse_args(argument_list)
    abandoned = [name for name in ABANDONED if name in os.environ]
    if abandoned:
        fields = ", ".join(f"{name} -> \"{ABANDONED[name]}\"" for name in abandoned)
        sys.exit(f"{', '.join(abandoned)} no longer does anything: the world runs on "
                 f"{path_of(arguments.world)} and nothing else. Unset it, and put "
                 f"what it said in that file instead ({fields}), or use "
                 f"elsewhere configure.")
    arguments.func(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
