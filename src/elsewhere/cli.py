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
from .world import store
from .world.store import World

DEFAULT_ROOT = Path("world")


def open_world(args) -> World:
    root = Path(args.world)
    if not store.exists(root):
        sys.exit(f"No world at {root}. Run: elsewhere init --world {root}")
    return store.load(root)


def transcript_for(world: World) -> Transcript:
    return Transcript(world.root / "transcript" / f"day{world.day:05d}.jsonl")


def heading(text: str) -> str:
    return f"\n{text}\n{'-' * len(text)}"


# --------------------------------------------------------------------------

def cmd_init(args) -> None:
    root = Path(args.world)
    if store.exists(root) and not args.force:
        sys.exit(f"{root} already holds a world. Use --force to start over.")
    started = time.time()
    world = seed.create(root, name=args.name, remember=not args.blank)
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
    total = 0
    for person in world.people.values():
        store_ = world.traces(person.id)
        live = [t for t in store_ if not retrieval.dormant(t, world.day)]
        total += len(store_)
        print(f"  {person.name:<8} {len(live)} within reach, "
              f"{len(store_) - len(live)} out of reach")
    print(f"  {total} traces in total")


def cmd_person(args) -> None:
    world = open_world(args)
    person = world.person_by_name(args.name)
    if person is None:
        sys.exit(f"Nobody here is called {args.name!r}")
    print(heading(f"{person.name}, {person.age}, {person.occupation}"))
    print(f"  {person.card}")
    print(f"\n  mood: {person.mood}   at: "
          f"{world.places[person.place].name if person.place in world.places else '-'}")
    if person.wants:
        print("  wants: " + "; ".join(person.wants))
    if person.beliefs:
        print("\n  holds to be true")
        for b in sorted(person.beliefs, key=lambda b: -b.confidence):
            lost = "  (cannot say why any more)" if b.origin_lost else ""
            print(f"    [{b.confidence:.2f}] {b.text}{lost}")
    print("\n  who they know")
    for other_id, tie in sorted(person.ties.items(), key=lambda kv: -kv[1].closeness):
        other = world.people.get(other_id)
        if other is None:
            continue
        print(f"    {other.name:<8} {tie.note or '-'}")
    traces = list(world.traces(person.id))
    within = retrieval.recallable(traces, world.day, limit=args.limit)
    print(f"\n  memory: {len(traces)} traces, "
          f"{sum(1 for t in traces if retrieval.dormant(t, world.day))} out of reach")
    for t in within:
        print(f"    day {t.day:<5} [{t.feeling}] {t.trace}")
        if t.means:
            print(f"          ~ {t.means}")
        print(f"          weight {t.salience:.2f}  reach "
              f"{retrieval.reach(t, world.day):.2f}  "
              f"tags {', '.join(t.tags) or '-'}")


def cmd_timeline(args) -> None:
    world = open_world(args)
    print(heading(f"{world.name}: what happened"))
    for e in world.chronicle.all()[-args.limit:]:
        print(f"  {e.id}  day {e.day:<5} {e.kind:<12} {e.what}")


def cmd_event(args) -> None:
    world = open_world(args)
    event = world.chronicle.get(args.event_id)
    if event is None:
        sys.exit(f"No event {args.event_id}")
    place = world.places.get(event.where or "")
    print(heading(f"{event.id} - day {event.day}, {event.kind}, "
                  f"at {place.name if place else '-'}"))
    print(f"  History says:  {event.what}")
    print(f"  tags: {', '.join(event.tags) or '-'}")
    print("\n  What it left in people:")
    for person in world.people.values():
        traces = world.traces(person.id).about_event(event.id)
        if not traces:
            if person.id in event.present:
                print(f"    {person.name:<8} - nothing. They were there.")
            continue
        for t in traces:
            state = ("out of reach" if retrieval.dormant(t, world.day)
                     else f"reach {retrieval.reach(t, world.day):.2f}")
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
    print(f"{len(made)} of {len(event.present)} people kept something.")
    for trace in made:
        print(f"  {world.people[trace.owner].name:<8} [{trace.feeling}] {trace.trace}")


def cmd_eval(args) -> None:
    """Run a scenario N times against the configured minds and report."""
    from . import evals

    if args.scenario != "fire":
        sys.exit("the only scenario so far is: fire")
    tape_dir = Path(".elsewhere") / "eval"
    print(f"Putting the fire to four people, {args.n} times. Tapes in {tape_dir}/")
    samples, world, fire = evals.run_fire(args.n, tape_dir)
    print(evals.report(samples, world, fire))


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

    p = sub.add_parser("eval", help="measure the minds over N runs of a scenario")
    p.add_argument("scenario", nargs="?", default="fire")
    p.add_argument("-n", type=int, default=5)
    p.set_defaults(func=cmd_eval)

    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
