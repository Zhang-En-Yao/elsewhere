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

from . import agents, config as config_mod, retrieval, schemas, seed
from .backends import Call, Settings, Transcript, ask, get as get_backend
from .world import chronicle, store
from .world.store import World, clock_at, day_of

DEFAULT_ROOT = Path("world")


def open_world(args) -> World:
    root = Path(args.world)
    if not store.exists(root):
        sys.exit(f"No world at {root}. Run: elsewhere init --world {root}")
    return store.load(root)


def transcript_for(world: World) -> Transcript:
    return Transcript(world.root / "transcript" / f"day{day_of(world.at):05d}.jsonl")


def when(at: float) -> str:
    """A moment, for a person to read: 'day 121, 18:00'."""
    return f"day {day_of(at)}, {clock_at(at)}"


def heading(text: str) -> str:
    return f"\n{text}\n{'-' * len(text)}"


# --------------------------------------------------------------------------

def cmd_init(args) -> None:
    root = Path(args.world)
    if store.exists(root) and not args.force:
        sys.exit(f"{root} already holds a world. Use --force to start over.")
    started = time.time()
    tape = Transcript(root / "transcript" / "init.jsonl")
    world = seed.create(root, name=args.name, remember=not args.blank,
                        transcript=tape)
    world.last_tick_at = time.time()
    store.save(world)
    remembered = sum(len(world.traces(p.id)) for p in world.people.values())
    print(f"{world.name} exists. {world.label()}")
    print(f"  {len(world.people)} people, {len(world.places)} places, "
          f"{len(world.chronicle)} events already behind them")
    print(f"  {remembered} of those events left a mark on somebody "
          f"({time.time() - started:.1f}s)")
    if remembered == 0 and not args.blank:
        print("  (nothing stuck - is a model reachable? try: elsewhere doctor)")
    print(f"  config at {root / 'config.json'}")


def cmd_status(args) -> None:
    world = open_world(args)
    print(f"{world.name} - {world.label()}")
    print(f"  chronicle: {len(world.chronicle)} events")
    for place in world.places.values():
        here = world.people_at(place.id)
        if not here:
            continue
        print(f"  {place.name}: " +
              ", ".join(f"{p.name} ({p.last_action or 'just here'})" for p in here))
    gone = [p for p in world.people.values() if not p.present]
    if gone:
        print("  gone: " + ", ".join(
            f"{p.name} ({when(p.left_at)})" if p.left_at else p.name
            for p in sorted(gone, key=lambda p: p.left_at or 0)))
    total = 0
    for person in world.people.values():
        store_ = world.traces(person.id)
        # Somebody who left is counted as they were the moment they went. The
        # world has no idea what has happened to them since and will not
        # pretend to by going on fading things nobody here can see.
        at = world.at if person.present else (person.left_at or world.at)
        live = [t for t in store_ if not retrieval.dormant(t, at)]
        total += len(store_)
        mark = "" if person.present else "  (left)"
        print(f"  {person.name:<8} {len(live)} within reach, "
              f"{len(store_) - len(live)} out of reach{mark}")
    print(f"  {total} traces in total")


def cmd_person(args) -> None:
    world = open_world(args)
    person = world.person_by_name(args.name)
    if person is None:
        sys.exit(f"Nobody here is called {args.name!r}")
    print(heading(f"{person.name}, {person.age}, {person.occupation}"))
    print(f"  {person.card}")
    at = world.at if person.present else (person.left_at or world.at)
    if not person.present:
        print(f"\n  Left on {when(at)}. What follows is how they stood "
              f"then; nothing here has touched it since.")
    else:
        print(f"\n  mood: {person.mood}   at: "
              f"{world.places[person.place].name if person.place in world.places else '-'}")
    if person.arrived_at:
        print(f"  came up the road on {when(person.arrived_at)}")
    if person.wants:
        print("  wants: " + "; ".join(person.wants))
    if person.beliefs:
        print("\n  holds to be true")
        for b in sorted(person.beliefs, key=lambda b: -b.confidence):
            lost = "  (cannot say why any more)" if b.origin_lost else ""
            print(f"    [{b.confidence:.2f}] {b.text}{lost}")
    known = [(world.people[i], t) for i, t in
             sorted(person.ties.items(), key=lambda kv: -kv[1].closeness)
             if i in world.people]
    print("\n  who they know" if known else "\n  they know nobody here yet")
    for other, tie in known:
        gone = "  (gone)" if not other.present else ""
        print(f"    {other.name:<8} {tie.note or '-'}{gone}")
    traces = list(world.traces(person.id))
    within = retrieval.recallable(traces, at, limit=args.limit)
    print(f"\n  memory: {len(traces)} traces, "
          f"{sum(1 for t in traces if retrieval.dormant(t, at))} out of reach")
    for t in within:
        print(f"    {when(t.at):<18} [{t.feeling}] {t.trace}")
        if t.means:
            print(f"          ~ {t.means}")
        print(f"          weight {t.salience:.2f}  reach "
              f"{retrieval.reach(t, at):.2f}  "
              f"tags {', '.join(t.tags) or '-'}")


def cmd_timeline(args) -> None:
    world = open_world(args)
    print(heading(f"{world.name}: what happened"))
    for e in world.chronicle.all()[-args.limit:]:
        print(f"  {e.id}  {when(e.at):<18} {e.category:<12} {e.account}")


def cmd_event(args) -> None:
    world = open_world(args)
    event = world.chronicle.get(args.event_id)
    if event is None:
        sys.exit(f"No event {args.event_id}")
    place = world.places.get(event.place or "")
    print(heading(f"{event.id} - {when(event.at)}, {event.category}, "
                  f"at {place.name if place else '-'}"))
    print(f"  History says:  {event.account}")
    print(f"  cues: {', '.join(event.cues) or '-'}")
    print("\n  What it left in people:")
    for person in world.people.values():
        traces = world.traces(person.id).about_event(event.id)
        if not traces:
            if person.id in event.reached:
                print(f"    {person.name:<8} - nothing. They were there.")
            continue
        for t in traces:
            state = ("out of reach" if retrieval.dormant(t, world.at)
                     else f"reach {retrieval.reach(t, world.at):.2f}")
            print(f"    {person.name:<8} \"{t.trace}\"")
            if t.means:
                print(f"    {'':<8}   {t.feeling}: {t.means}")
            print(f"    {'':<8}   ({state}, weight {t.salience:.2f})")


def cmd_doctor(args) -> None:
    """Can the things that are supposed to be thinking actually be reached?"""
    root = Path(args.world)
    config = config_mod.load(root) if store.exists(root) else {
        name: Settings.from_dict(s)
        for name, s in config_mod.default_config()["agents"].items()}
    print(heading("Minds"))
    probe = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    seen = {}
    for name, settings in config.items():
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
        except Exception as exc:
            verdict = f"unreachable: {type(exc).__name__}: {exc}"
        seen[key] = verdict
        print(f"  {name:<9} {settings.backend}/{settings.model:<18} {verdict}")
    print("\n  Set ELSEWHERE_BACKEND=stub to run without any of this.")


def cmd_remember(args) -> None:
    """Put one event past everyone again, by hand. Useful while tuning prompts."""
    world = open_world(args)
    event = world.chronicle.get(args.event_id)
    if event is None:
        sys.exit(f"No event {args.event_id}")
    config = config_mod.load(world.root)
    transcript = transcript_for(world)
    made = agents.perceive_all(world, event, config, transcript)
    for person in world.people.values():
        world.traces(person.id).save()
    store.save(world)
    print(f"{len(made)} of {len(event.reached)} people kept something.")
    for trace in made:
        print(f"  {world.people[trace.owner].name:<8} [{trace.feeling}] {trace.trace}")


# --------------------------------------------------------------------------
# time passing

def _name(world, pid: str) -> str:
    person = world.people.get(pid)
    return person.name if person else pid


def print_report(world, report) -> None:
    print(f"\n{report.label}")
    if report.occurrence is not None:
        h = report.occurrence
        print(f"  * {h.account}")
        for tr in h.kept:
            print(f"      {_name(world, tr.owner)} kept [{tr.feeling}] {tr.trace}")
    if report.arrival is not None:
        a = report.arrival
        print(f"  + {a.account}")
        for tr in a.kept:
            print(f"      {_name(world, tr.owner)} kept [{tr.feeling}] {tr.trace}")
    for d in report.departures:
        event = world.chronicle.get(d.event_id)
        print(f"  - {event.account if event else _name(world, d.person_id) + ' left.'}")
        if d.because:
            print(f'      "{d.because}"')
        for tr in d.kept:
            print(f"      {_name(world, tr.owner)} kept [{tr.feeling}] {tr.trace}")
    talked = {t.speaker for t in report.talks} | {t.listener for t in report.talks}
    talked |= {d.person_id for d in report.departures}
    for pid, d in sorted(report.decisions.items()):
        person = world.people[pid]
        if pid in talked:
            continue
        what = person.last_action or d.doing or d.action
        why = f'  - "{d.because}"' if d.because else ("  (no answer)" if not d.answered else "")
        print(f"  {person.name:<7} {what:<34}{why}")
    for t in report.talks:
        print(f"  {_name(world, t.speaker):<7} to {_name(world, t.listener)}: \"{t.line}\"")
        if t.reshaped:
            print(f"  {'':<7}   ({_name(world, t.speaker)}'s memory was \"{t.reshaped[0]}\"; "
                  f"now \"{t.reshaped[1]}\")")
        heard = {tr.owner for tr in t.kept}
        for tr in t.kept:
            print(f"  {'':<7}   {_name(world, tr.owner)} kept [{tr.feeling}] {tr.trace}")
        ev = world.chronicle.get(t.event_id)
        for pid in (ev.reached if ev else []):
            if pid not in heard and pid != t.speaker:
                print(f"  {'':<7}   {_name(world, pid)} kept nothing of it")
    for pid, r in report.reflections.items():
        line = r.get("thought") or ""
        extra = f' -> now believes "{r["belief"]}"' if r.get("belief") else ""
        print(f"  {_name(world, pid):<7} lies awake: \"{line}\"{extra}")
    if report.silent:
        print(f"  ({report.silent} mind(s) gave no usable answer and stayed put)")


def _open_live(args):
    world = open_world(args)
    if world.closed:
        sys.exit(f"{world.name} has ended. Nothing more happens here.")
    return world


def cmd_tick(args) -> None:
    """Live N steps now, by hand."""
    from .tick import tick

    world = _open_live(args)
    config = config_mod.load(world.root)
    try:
        with store.tick_lock(world.root):
            for _ in range(args.n):
                report = tick(world, config, transcript_for(world))
                store.save(world)
                print_report(world, report)
            world.last_tick_at = time.time()
            store.save(world)
    except store.Locked as exc:
        sys.exit(f"Not now: {exc}")


def cmd_catchup(args) -> None:
    """The scheduled entry point: live whatever steps the wall clock says are owed."""
    from .tick import owed_steps, settle_clock, tick
    from .backends import probe

    stamp = time.strftime("%Y-%m-%d %H:%M")
    world = _open_live(args)
    try:
        with store.tick_lock(world.root):
            now = time.time()
            if world.last_tick_at is None:
                world.last_tick_at = now
                store.save(world)
                print(f"[{stamp}] clock started for {world.name}")
                return
            owed = owed_steps(world.last_tick_at, now, args.hours)
            if owed == 0:
                # A heartbeat, so "is the schedule running at all?" can be
                # answered from the log instead of by waiting six hours.
                due = world.last_tick_at + args.hours * 3600 - now
                print(f"[{stamp}] checked; next step in {due / 3600:.1f}h")
                return
            config = config_mod.load(world.root)
            ok, message = probe(config["act"])
            if not ok:
                # The world waits rather than going on without minds.
                print(f"[{stamp}] {owed} step(s) owed, but the minds are {message}; "
                      f"{world.name} waits")
                return
            ran = 0
            for _ in range(min(owed, args.max)):
                report = tick(world, config, transcript_for(world))
                ran += 1
                store.save(world)
                print(f"[{stamp}]", end="")
                print_report(world, report)
            world.last_tick_at = settle_clock(world.last_tick_at, now, ran, owed, args.hours)
            store.save(world)
            if ran < owed:
                print(f"[{stamp}] {owed - ran} more step(s) were owed; "
                      f"{world.name} slept through them")
    except store.Locked as exc:
        print(f"[{stamp}] skipped: {exc}")


def cmd_news(args) -> None:
    """What happened since you last looked."""
    world = open_world(args)
    events = world.chronicle.all()[world.news_seen:]
    print(f"{world.name} - {world.label()}")
    if not events:
        print("  Nothing has happened since you last looked.")
    for e in events:
        place = world.places.get(e.place or "")
        print(f"\n  {when(e.at)}, {place.name if place else '-'}")
        mark = {chronicle.OCCURRENCE: "* ", chronicle.ARRIVAL: "+ ",
                chronicle.DEPARTURE: "- "}
        print(f"    {mark.get(e.category, '')}{e.account}")
        for pid in e.reached:
            for t in world.traces(pid).about_event(e.id):
                print(f"      {_name(world, pid)} kept [{t.feeling}] {t.trace}")
    print("\n  Now:")
    for person in sorted(world.people.values(), key=lambda p: p.name):
        if not person.present:
            continue
        place = world.places.get(person.place)
        print(f"    {person.name:<7} at {place.name if place else '-':<20} "
              f"{person.last_action or ''}")
    if not args.peek:
        world.news_seen = len(world.chronicle)
        store.save(world)


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="elsewhere",
                                 description="A persistent world that remembers.")
    ap.add_argument("--world", default=str(DEFAULT_ROOT), help="path to the world")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="make a small world")
    p.add_argument("--name", default="Wend")
    p.add_argument("--force", action="store_true")
    p.add_argument("--blank", action="store_true",
                   help="do not run the backstory past anyone")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status", help="where everyone is, and how much they hold")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("person", help="who someone is now")
    p.add_argument("name")
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=cmd_person)

    p = sub.add_parser("timeline", help="what happened")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_timeline)

    p = sub.add_parser("event", help="one event, and what it left in people")
    p.add_argument("event_id")
    p.set_defaults(func=cmd_event)

    p = sub.add_parser("doctor", help="check the minds can be reached")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("remember", help="put one event past everyone again")
    p.add_argument("event_id")
    p.set_defaults(func=cmd_remember)

    p = sub.add_parser("tick", help="live N steps of the world now")
    p.add_argument("-n", type=int, default=1)
    p.set_defaults(func=cmd_tick)

    p = sub.add_parser("catchup", help="live the steps the wall clock says are owed")
    p.add_argument("--max", type=int, default=4, help="most steps to live in one go")
    p.add_argument("--hours", type=float, default=6.0, help="real hours per step")
    p.set_defaults(func=cmd_catchup)

    p = sub.add_parser("news", help="what happened since you last looked")
    p.add_argument("--peek", action="store_true", help="look without marking it read")
    p.set_defaults(func=cmd_news)

    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
