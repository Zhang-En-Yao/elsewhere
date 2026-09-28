"""The `elsewhere` command line."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import List, Optional

from . import agents, configuration, recollection, schedule, schemas, seed
from .backends import Transcript, ask, embed, probe
from .schemas import CallName
from .configuration import MINDS, configure
from .world import chronicle, store
from .world.store import World, clock_at, day_at

DEFAULT_ROOT = Path("world")


# helpers

def open_world(arguments) -> World:
    root = Path(arguments.world)
    if not store.exists(root):
        sys.exit(f"No world at {root}. Run: elsewhere --world {root} initialize")
    return store.load(root)


def open_live(arguments):
    world = open_world(arguments)
    if world.closed:
        sys.exit(f"{world.name} has ended. Nothing more happens here.")
    return world


def catch_up(world: World, limit: int = 8, output=print) -> None:
    """Live the hours the wall clock says are owed, reporting each step via `output`."""
    from .tick import owed_hours, reconcile, tick

    stamp = time.strftime("%Y-%m-%d %H:%M")
    try:
        with store.TickLock(world.root):
            now = time.time()
            if world.last_tick_at is None:
                world.last_tick_at = now
                store.save(world)
                output(f"[{stamp}] clock started for {world.name}")
                return
            owed = owed_hours(world.last_tick_at, now)
            ahead = schedule.next_at(world)
            if ahead is not None and world.at + owed < ahead:
                output(f"[{stamp}] checked; nothing is due for "
                    f"{ahead - world.at - owed:.1f}h of world time")
                return
            settings = configuration.load(world.root)
            ok, message = probe(settings[CallName.ACT])
            if not ok:
                output(f"[{stamp}] {owed:.1f}h owed, but the minds are {message}; "
                    f"{world.name} waits")
                return
            # `limit` bounds model calls, not world time.
            began, steps = world.at, 0
            while world.at - began < owed and steps < limit:
                report = tick(world, settings, transcript_for(world))
                steps += 1
                store.save(world)
                output(f"[{stamp}]")
                for line in report_lines(world, report):
                    output(line)
                if report.idle:
                    break
            lived = world.at - began
            world.last_tick_at = reconcile(world.last_tick_at, now, lived, owed)
            store.save(world)
            if lived < owed:
                output(f"[{stamp}] {owed - lived:.1f}h more were owed; "
                    f"{world.name} slept through them")
    except store.Locked as exception:
        output(f"[{stamp}] skipped: {exception}")


def transcript_for(world: World) -> Transcript:
    return Transcript(world.root / "transcript" / f"day{day_at(world.at):05d}.jsonl")


def timestamp(at: float) -> str:
    return f"day {day_at(at)}, {clock_at(at)}"


def heading(text: str) -> str:
    return f"\n{text}\n{'-' * len(text)}"


def name_of(world, being_id: str) -> str:
    being = world.beings.get(being_id)
    return being.name if being else being_id


def report_lines(world, report) -> List[str]:
    """Shared by the terminal and the TUI so both describe a step the same way."""
    if report.idle:
        return [report.label, "  (nothing in the world is scheduled)"]
    lines: List[str] = []
    lines.append(f"{report.label}  (+{report.hours:g}h)")
    if report.occurrence is not None:
        lines.append(f"  * {report.occurrence.account}")
    if report.arrival is not None:
        lines.append(f"  + {report.arrival.account}")
    for departure in report.departures:
        event = world.chronicle.get(departure.event_id)
        lines.append(f"  - {event.account if event else name_of(world, departure.being_id) + ' left.'}")
        if departure.because:
            lines.append(f'      "{departure.because}"')
    talked = {talk.speaker for talk in report.talks} | {talk.listener for talk in report.talks}
    talked |= {departure.being_id for departure in report.departures}
    for being_id, decision in sorted(report.decisions.items()):
        being = world.beings[being_id]
        if being_id in talked:
            continue
        what = being.where.doing or decision.doing or (decision.action or '')
        why = (f'  - "{decision.because}"' if decision.because
               else ("  (no answer)" if not decision.answered else ""))
        lines.append(f"  {being.name:<7} {what:<34}{why}")
    for talk in report.talks:
        for turn in talk.turns:
            lines.append(f"  {name_of(world, turn.speaker):<7} to {name_of(world, turn.listener)}: "
                       f"\"{turn.utterance}\"")
    for being_id in report.settled:
        lines.append(f"  {name_of(world, being_id):<7} stops for the day, and goes over it")
    if report.unanswered:
        lines.append(f"  ({report.unanswered} mind(s) gave no usable answer and stayed put)")
    return lines


def print_report(world, report) -> None:
    print()
    for line in report_lines(world, report):
        print(line)


# create

def command_initialize(arguments) -> None:
    root = Path(arguments.world)
    if store.exists(root) and not arguments.force:
        sys.exit(f"{root} already holds a world. Use --force to start over.")
    world = seed.create(root, name=arguments.name)
    print("\n".join([
        f"{world.name} exists. {world.label()}",
        f"  {len(world.beings)} people, {len(world.places)} places, "
        f"{len(world.chronicle)} events already behind them, which each of them "
        f"sees the first time they look up",
        f"  configuration at {configuration.locate(root)}; check it with: elsewhere doctor",
    ]))


# read-only views

def command_status(arguments) -> None:
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
            f"{being.name} ({timestamp(being.when.left_at)})" if being.when.left_at
            else being.name
            for being in sorted(gone, key=lambda being: being.when.left_at or 0)))
    for being in world.beings.values():
        mark = "" if being.present else "  (left)"
        print(f"  {being.name:<8} a page of {len(being.who.notebook)} characters, "
              f"{len(agents.day_notes(world, being))} notes from today, "
              f"{len(world.notes(being.id))} kept in all{mark}")


def command_person(arguments) -> None:
    world = open_world(arguments)
    being = world.being_by_name(arguments.name)
    if being is None:
        sys.exit(f"Nobody here is called {arguments.name!r}")
    print(heading(being.name))
    print(f"  {being.who.card}")
    if not being.present:
        print(f"\n  Left on {timestamp(being.when.left_at or world.at)}. What follows is "
              f"how they stood then; nothing here has touched it since.")
    else:
        print(f"\n  at: "
              f"{world.places[being.where.place].name if being.where.place in world.places else '-'}")
    if being.when.arrived_at:
        print(f"  came up the road on {timestamp(being.when.arrived_at)}")
    pages = world.pages(being.id).all()
    if arguments.pages:
        print(f"\n  every page they have written ({len(pages)})")
        for page in pages:
            print(f"\n    {timestamp(page.at)}")
            for line in page.notebook.splitlines():
                print(f"      {line}")
    else:
        print(f"\n  what they carry  (the newest of {len(pages)} pages; --pages for all)")
        for line in (being.who.notebook or "nothing yet").splitlines():
            print(f"    {line}")
    today = agents.day_notes(world, being)[-arguments.limit:]
    print("\n  what they have kept of today, not gone over yet" if today
          else "\n  nothing kept since they last went over their day")
    for note in today:
        print(f"    {timestamp(note.at):<18} {note.account}")
    print(f"\n  {len(world.notes(being.id))} notes in all, every one kept")


def command_timeline(arguments) -> None:
    world = open_world(arguments)
    print(heading(f"{world.name}: what happened"))
    for event in world.chronicle.all()[-arguments.limit:]:
        print(f"  {event.id:>4}  {timestamp(event.at):<18} {event.category:<12} {event.account}")


def command_event(arguments) -> None:
    world = open_world(arguments)
    event = world.chronicle.get(arguments.event_id)
    if event is None:
        sys.exit(f"No event {arguments.event_id}")
    place = world.places.get(event.place or "")
    print(heading(f"Event {event.id} - {timestamp(event.at)}, {event.category}, "
                  f"at {place.name if place else '-'}"))
    print(f"  History says:  {event.account}")
    if not event.informed:
        print("\n  It reached nobody.")
        return
    print("\n  What it left in people:")
    for being_id in event.informed:
        being = world.beings.get(being_id)
        if being is None:
            continue
        print(f"    {being.name:<8} they were {agents.viewpoint(world, being, event)}")
        notes = world.notes(being_id).about(event.id)
        if not notes:
            seen = being.when.seen_through > world.chronicle.all().index(event)
            print(f"    {'':<8} {'kept nothing of it' if seen else 'has not seen it yet'}")
        for note in notes:
            print(f"    {'':<8} kept: \"{note.account}\"")


def command_news(arguments) -> None:
    world = open_world(arguments)
    events = world.chronicle.all()[world.read_through:]
    print(f"{world.name} - {world.label()}")
    if not events:
        print("  Nothing has happened since you last looked.")
    for event in events:
        place = world.places.get(event.place or "")
        print(f"\n  {timestamp(event.at)}, {place.name if place else '-'}")
        marks = {chronicle.OCCURRENCE: "* ", chronicle.ARRIVAL: "+ ",
                 chronicle.DEPARTURE: "- "}
        print(f"    {marks.get(event.category, '')}{event.account}")
        for being_id in event.informed:
            for note in world.notes(being_id).about(event.id):
                print(f"      {name_of(world, being_id)} kept: {note.account}")
    print("\n  Now:")
    for being in sorted(world.beings.values(), key=lambda being: being.name):
        if not being.present:
            continue
        place = world.places.get(being.where.place)
        print(f"    {being.name:<7} at {place.name if place else '-':<20} "
              f"{being.where.doing or ''}")
    if not arguments.peek:
        world.read_through = len(world.chronicle)
        store.save(world)


def command_watch(arguments) -> None:
    """Read-only TUI; it never writes under the world's directory."""
    root = Path(arguments.world)
    if not store.exists(root):
        sys.exit(f"No world at {root}. Run: elsewhere --world {root} initialize")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.exit("watch needs a terminal. For a pipe or a log: elsewhere news")
    try:
        from .tui import screen
    except ImportError as exception:
        sys.exit(f"no curses on this Python, so no window: {exception}")
    try:
        screen.run(root)
    except ValueError as exception:
        # A world written by an older, incompatible version.
        sys.exit(str(exception))


# time passing


def command_continue(arguments) -> None:
    world = open_live(arguments)
    catch_up(world, arguments.max)


def command_tick(arguments) -> None:
    from .tick import tick

    world = open_live(arguments)
    settings = configuration.load(world.root)
    try:
        with store.TickLock(world.root):
            for _ in range(arguments.n):
                report = tick(world, settings, transcript_for(world))
                store.save(world)
                print_report(world, report)
            world.last_tick_at = time.time()
            store.save(world)
    except store.Locked as exception:
        sys.exit(f"Not now: {exception}")


# ending

def command_end(arguments) -> None:
    try:
        with store.TickLock(Path(arguments.world)):
            # Load under the lock so a running step finishes and saves first.
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


# development

def command_doctor(arguments) -> None:
    root = Path(arguments.world)
    path = configuration.locate(root)
    settings = configuration.load(root)
    print(f"Reading {path}" if path.exists()
          else f"No {path} yet; these are the defaults it would be written with")
    print(heading("Minds"))
    seen = set()
    for name, setting in settings.items():
        if name == "embed":
            continue                      # probed separately below
        key = (setting.backend, setting.model, setting.endpoint)
        if key in seen:
            print(f"  {name:<9} {setting.backend}/{setting.model:<18} (same model as above)")
            continue
        seen.add(key)
        ok, verdict = probe(setting)
        print(f"  {name:<9} {setting.backend}/{setting.model:<18} {verdict}")
    embed_settings = settings.get("embed")
    if embed_settings is not None:
        print(heading("What brings a note back"))
        started = time.time()
        vectors = embed(["the water came up over the waterline"], embed_settings)
        with closing(sqlite3.connect(":memory:")) as connection:
            extension = recollection.load_vector_extension(connection)
        print(f"  embed     {embed_settings.backend}/{embed_settings.model:<18} "
              + (f"ok ({len(vectors[0])} dimensions, {time.time() - started:.1f}s)" if vectors
                 else "unreachable - recollection falls back on BM25 alone"))
        print("  vectors   sqlite-vec " + ("ok" if extension else
              "not installed - recollection falls back on BM25 alone "
              "(pip install -e '.[recall]')"))
    print(f'\n  Set "backend": "stub" in {path} to run without any of this.')


def command_configure(arguments) -> None:
    root = Path(arguments.world)
    try:
        path = configure(root, arguments.backend, arguments.model, arguments.endpoint,
                         arguments.call or MINDS)
    except KeyError as exception:
        sys.exit(str(exception.args[0]))
    where = f" at {arguments.endpoint}" if arguments.endpoint else ""
    print(f"{', '.join(arguments.call or MINDS)} -> "
          f"{arguments.backend}/{arguments.model}{where}")
    print(f"  written to {path}; check it with: elsewhere --world {root} doctor")


def command_settle(arguments) -> None:
    """Writes a notebook, so it takes the lock and refuses an ended world."""
    try:
        with store.TickLock(Path(arguments.world)):
            # Load under the lock so a running step finishes and saves first.
            world = open_live(arguments)
            being = world.being_by_name(arguments.name)
            if being is None or not being.present:
                sys.exit(f"Nobody here is called {arguments.name!r}")
            settled = agents.settle(world, being, configuration.load(world.root),
                                 transcript_for(world))
            store.save(world)
    except store.Locked as exception:
        sys.exit(f"Not now: {exception}")
    if not settled:
        print(f"{being.name} could not go over it; nothing changed.")
        return
    print(f"{being.name} went over it, and now carries:")
    for line in being.who.notebook.splitlines():
        print(f"  {line}")


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
    subparser.set_defaults(handler=command_initialize)

    # read-only views
    subparser = subparsers.add_parser(
        "status", help="where everyone is, and how much they carry")
    subparser.set_defaults(handler=command_status)

    subparser = subparsers.add_parser("person", help="who someone is now")
    subparser.add_argument("name")
    subparser.add_argument("--limit", type=int, default=8)
    subparser.add_argument("--pages", action="store_true",
                           help="every page they have written, oldest first")
    subparser.set_defaults(handler=command_person)

    subparser = subparsers.add_parser("timeline", help="what happened")
    subparser.add_argument("--limit", type=int, default=30)
    subparser.set_defaults(handler=command_timeline)

    subparser = subparsers.add_parser(
        "event", help="one event, and where it found people")
    subparser.add_argument("event_id")
    subparser.set_defaults(handler=command_event)

    # The one view that writes: it marks news as read.
    subparser = subparsers.add_parser(
        "news", help="what happened since you last looked")
    subparser.add_argument("--peek", action="store_true", help="look without marking it read")
    subparser.set_defaults(handler=command_news)

    subparser = subparsers.add_parser(
        "watch", help="sit with the world in a window; reads only")
    subparser.set_defaults(handler=command_watch)

    # time passing
    subparser = subparsers.add_parser(
        "continue",
        help="let the world go on for however long you have been away")
    subparser.add_argument("--max", type=int, default=8,
                            help="most steps to live in one go; a bound on model calls, "
                                 "not on how far the clock may move")
    subparser.set_defaults(handler=command_continue)

    subparser = subparsers.add_parser("tick", help="[DEV] manually advance N steps")
    subparser.add_argument("-n", type=int, default=1)
    subparser.set_defaults(handler=command_tick)

    # ending
    subparser = subparsers.add_parser(
        "end", help="end the world for good; what happened stays readable")
    subparser.set_defaults(handler=command_end)

    # development (internal)
    subparser = subparsers.add_parser("doctor", help="[DEV] diagnose model backend connectivity")
    subparser.set_defaults(handler=command_doctor)

    subparser = subparsers.add_parser(
        "configure", help="point the minds at one backend and model")
    subparser.add_argument("--backend", required=True)
    subparser.add_argument("--model", required=True)
    subparser.add_argument("--endpoint", help="where the server is, if not the default")
    subparser.add_argument("--call", action="append",
                           help="only this call site (repeatable); "
                                "default: every mind, not the embedder")
    subparser.set_defaults(handler=command_configure)

    subparser = subparsers.add_parser(
        "settle", help="[DEV] have one person go over their day now, for prompt tuning")
    subparser.add_argument("name")
    subparser.set_defaults(handler=command_settle)

    return parser


def main(argument_list: Optional[List[str]] = None) -> int:
    arguments = build_parser().parse_args(argument_list)
    arguments.handler(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
