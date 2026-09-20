"""Command line access to a world you do not own.

    elsewhere init --player "You"
    elsewhere advance --days 30
    elsewhere event ev0002
    elsewhere play
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import seed as seedmod
from . import simulation, storage
from .mind import Action
from .mind import player as playermind
from .perception import encode_introduced
from .person import Person
from .world import World

DEFAULT_WORLD = Path("world.json")


# --------------------------------------------------------------------------
# formatting

def bar(value: float, width: int = 10, low: float = 0.0, high: float = 1.0) -> str:
    span = max(high - low, 1e-6)
    filled = int(round((value - low) / span * width))
    filled = max(0, min(width, filled))
    return "#" * filled + "." * (width - filled)


def heading(text: str) -> str:
    return f"\n{text}\n{'-' * len(text)}"


def load_world(args) -> World:
    path = Path(args.world)
    if not storage.exists(path):
        sys.exit(f"No world at {path}. Run: elsewhere init --world {path}")
    return storage.load(path)


def refuse_if_ended(world: World) -> None:
    if world.closed:
        sys.exit(f"{world.name} ended on day {world.closed_on}. "
                 f"Nothing more happens here. (You can still read it.)")


def require_person(world: World, name: str) -> Person:
    person = world.person_by_name(name)
    if person is None:
        sys.exit(f"Nobody here is called {name!r}. "
                 f"Try: {', '.join(p.name for p in world.people.values())}")
    return person


def memory_line(m, world: World) -> str:
    where = world.places[m.place].name if m.place in world.places else "-"
    flags = []
    if m.dormant:
        flags.append("forgotten")
    if m.source != "experienced":
        flags.append(m.source)
    if m.returned_on:
        flags.append(f"returned day {m.returned_on}")
    tail = f"  [{', '.join(flags)}]" if flags else ""
    heard = f"\n        heard as: \"{m.heard}\"" if m.heard else ""
    return (f"  day {m.day:<5} {m.feeling:<11} {m.text()}{heard}\n"
            f"        ~ {m.interpretation}\n"
            f"        strength {bar(m.strength, 8)} detail {bar(m.detail, 8)} "
            f"feeling {bar(m.intensity, 8)}  at {where}{tail}")


# --------------------------------------------------------------------------
# commands

def cmd_init(args) -> None:
    path = Path(args.world)
    if storage.exists(path) and not args.force:
        sys.exit(f"{path} already exists. Use --force to start a new world over it.")
    world = seedmod.create_world(seed=args.seed, player_name=args.player)
    storage.save(world, path)
    print(f"{world.name} exists. {world.clock.label()}")
    print(f"  {len(world.people)} people, {len(world.places)} places, "
          f"{len(world.history)} events already behind them.")
    print(f"  saved to {path}")
    print("\nTry:  elsewhere advance --days 30  then  elsewhere event ev0002")


def cmd_status(args) -> None:
    world = load_world(args)
    print(f"{world.name} - {world.clock.label()}")
    print(f"  history: {len(world.history)} events   "
          f"art: {len(world.artifacts)}   traditions: {len(world.traditions)}")
    for place in world.places.values():
        here = world.people_at(place.id)
        art_here = world.artifacts_at(place.id)
        if not here and not art_here:
            continue
        who = ", ".join(f"{p.name} ({p.last_action or 'just arrived'})" for p in here)
        print(f"  {place.name}: {who or '-'}")
        for a in art_here[:3]:
            print(f"      \"{a.title}\" ({a.form} by {world.people[a.creator].name})")
        if len(art_here) > 3:
            print(f"      and {len(art_here) - 3} other things people made")
    player = world.player()
    if player and not player.present:
        print(f"\n  {player.name} is not here. The world has been going on without them.")


def cmd_advance(args) -> None:
    world = load_world(args)
    refuse_if_ended(world)
    before = len(world.history)
    player = world.player()
    was_present = player.present if player else False
    if player and args.away:
        player.present = False
    simulation.advance(world, days=args.days, mind_override=args.mind)
    if player:
        player.present = was_present
    storage.save(world, Path(args.world))
    new = world.history[before:]
    print(f"{args.days} day(s) passed. {world.clock.label()}")
    notable = [e for e in new if e.intensity >= (0.0 if args.all else 0.35)]
    for e in notable[-args.limit:]:
        print(f"  day {e.day:<5} {e.summary}")
    print(f"\n  {len(new)} things happened; {len(notable)} of them mattered to someone.")
    print("  What is left of them is in people's heads: elsewhere person Alice")


def cmd_timeline(args) -> None:
    world = load_world(args)
    events = world.history
    if args.kind:
        events = [e for e in events if e.kind == args.kind]
    if args.days:
        cutoff = world.clock.day - args.days
        events = [e for e in events if e.day >= cutoff]
    print(heading(f"{world.name}: what happened"))
    for e in events[-args.limit:]:
        marker = "*" if e.intensity >= 0.6 else " "
        print(f"{marker} {e.id}  day {e.day:<5} {e.kind:<17} {e.summary}")
    print(f"\n({len(events)} events; history is not memory - try: elsewhere event {events[-1].id if events else 'ev0001'})")


def cmd_person(args) -> None:
    world = load_world(args)
    p = require_person(world, args.name)
    print(heading(f"{p.name}, {p.age}, {p.occupation}"))
    if p.note:
        print(f"  {p.note}")
    print(f"  at {world.places[p.place].name if p.place in world.places else '-'}"
          f"   mood {p.mood:+.2f}   last: {p.last_action or '-'}")
    print("\n  disposition")
    for trait in ("openness", "warmth", "energy", "stability", "expressiveness"):
        print(f"    {trait:<15}{bar(getattr(p.traits, trait))}")
    print("\n  needs")
    for need in ("company", "novelty", "rest", "expression", "routine"):
        print(f"    {need:<15}{bar(getattr(p.needs, need))}")

    print("\n  people")
    for rel in sorted(p.relationships.values(), key=lambda r: -r.familiarity):
        other = world.people.get(rel.other)
        if other is None:
            continue
        print(f"    {other.name:<10} affinity {rel.affinity:+.2f}  "
              f"knows {bar(rel.familiarity, 6)}  trust {bar(rel.trust, 6)}  "
              f"last seen day {rel.last_seen_day}")
        for impression in rel.impressions[-2:]:
            print(f"        - {impression}")

    if p.beliefs:
        print("\n  what they believe now")
        for b in sorted(p.beliefs.values(), key=lambda b: -b.conviction):
            origin = "  (they no longer remember why)" if b.origin_forgotten else ""
            print(f"    [{b.conviction:.2f}] {b.statement}{origin}")

    active = p.memories.active()
    print(f"\n  memory: {len(active)} reachable, {len(p.memories.dormant())} dormant, "
          f"{p.memories.forgotten} gone entirely")
    for m in p.memories.strongest(5):
        print(memory_line(m, world))


def cmd_memories(args) -> None:
    world = load_world(args)
    p = require_person(world, args.name)
    mems = list(p.memories)
    if args.about:
        mems = [m for m in mems if args.about in m.themes]
    if not args.all:
        mems = [m for m in mems if not m.dormant]
    mems.sort(key=lambda m: m.day)
    print(heading(f"What {p.name} has left"))
    for m in mems[-args.limit:]:
        print(memory_line(m, world))
    if not mems:
        print("  nothing.")


def cmd_event(args) -> None:
    world = load_world(args)
    e = world.event(args.event_id)
    if e is None:
        sys.exit(f"No event {args.event_id}. Try: elsewhere timeline")
    place = world.places[e.place].name if e.place in world.places else "-"
    print(heading(f"{e.id} - day {e.day}, {e.kind}, at {place}"))
    print(f"  History says:  {e.summary}")
    print(f"  themes: {', '.join(e.themes) or '-'}   "
          f"valence {e.valence:+.2f}   intensity {e.intensity:.2f}")

    said = e.data.get("said")
    if said:
        speaker = world.people.get(e.participants[0]) if e.participants else None
        who = speaker.name if speaker else "Someone"
        print(f"\n  What was said:")
        print(f"    {who}: \"{said}\"")
        passed = e.data.get("passed_on")
        for person in world.people.values():
            m = person.memories.get(passed) if passed else None
            if m is None:
                continue
            print(f"    {person.name} kept: \"{m.heard or m.text()}\"")
            if any("misunderstood" in d for d in m.distortions):
                print(f"    {'':<8} (not the way it was meant)")

    print("\n  Memory says:")
    for person in world.people.values():
        versions = [m for m in person.memories if m.event_id == e.id]
        if not versions:
            if person.id in e.witnesses:
                print(f"    {person.name:<8} - nothing. They were there.")
            continue
        for m in versions:
            state = "forgotten" if m.dormant else f"strength {m.strength:.2f}"
            how = "" if m.source == "experienced" else f", {m.source}"
            print(f"    {person.name:<8} \"{m.text()}\"")
            if m.heard:
                print(f"    {'':<8}   what they took away: \"{m.heard}\"")
            print(f"    {'':<8}   {m.feeling}: {m.interpretation}  ({state}{how})")
            for d in m.distortions[-2:]:
                print(f"    {'':<8}   ~ {d}")


def cmd_art(args) -> None:
    world = load_world(args)
    print(heading(f"What people in {world.name} have made"))
    if not world.artifacts:
        print("  nothing yet. Give them time: elsewhere advance --days 30")
        return
    for a in sorted(world.artifacts.values(), key=lambda a: -a.day)[:args.limit]:
        creator = world.people[a.creator].name
        seen = ", ".join(world.people[p].name for p in a.encountered_by if p in world.people)
        print(f"  {a.id}  day {a.day:<5} \"{a.title}\" - {a.form} by {creator}")
        print(f"        {a.description}")
        print(f"        themes: {', '.join(a.themes)}   seen by: {seen or 'no one yet'}")


def cmd_culture(args) -> None:
    world = load_world(args)
    print(heading(f"{world.name}: what has hardened into practice"))
    if not world.traditions:
        print("  no traditions yet. They need a shared memory and time.")
    for t in world.traditions.values():
        founders = ", ".join(world.people[f].name for f in t.founders if f in world.people)
        print(f"  {t.name}  (founded day {t.day_founded}, kept {t.observances}x)")
        print(f"    {t.practice}")
        print(f"    out of: {t.theme}   by: {founders}")
    print("\n  shared beliefs")
    tally = {}
    for person in world.people.values():
        for b in person.beliefs.values():
            tally.setdefault(b.statement, []).append(person.name)
    for statement, names in sorted(tally.items(), key=lambda kv: -len(kv[1])):
        if len(names) > 1:
            print(f"    {len(names)}x {statement}  ({', '.join(names)})")


def cmd_join(args) -> None:
    world = load_world(args)
    refuse_if_ended(world)
    if world.player():
        sys.exit("This world already has a player.")
    seedmod.add_player(world, args.name)
    storage.save(world, Path(args.world))
    print(f"{args.name} is in {world.name}, at The Long Table. Try: elsewhere play")


def cmd_invite(args) -> None:
    world = load_world(args)
    refuse_if_ended(world)
    being = seedmod.invite_companion(world, args.name, args.note)
    storage.save(world, Path(args.world))
    print(f"{being.name} is part of {world.name} now.")
    print("It does not come back as what it was. It continues from here.")


def cmd_remember(args) -> None:
    """Put something from a real life into the world."""
    world = load_world(args)
    refuse_if_ended(world)
    player = world.player()
    if player is None:
        sys.exit("No player in this world. Run: elsewhere join \"Your name\"")
    themes = [t.strip() for t in (args.themes or "memory").split(",") if t.strip()]
    rng = world.rng_for("remember", args.text)
    encode_introduced(player, args.text, themes, world.clock.day, rng,
                      world.next_id("mem"), intensity=args.intensity,
                      valence=args.valence, place=player.place)
    event = world.record("telling", f"{player.name} told them about {args.text}",
                         place=player.place, participants=[player.id],
                         themes=themes, valence=args.valence,
                         intensity=min(0.9, args.intensity))
    from .actions import broadcast
    broadcast(world, event, rng)
    storage.save(world, Path(args.world))
    heard = [world.people[w].name for w in event.witnesses
             if w != player.id and w in world.people]
    print("It is in the world now.")
    print(f"  heard by: {', '.join(heard) if heard else 'no one - you were alone'}")
    print("  What they do with it is not yours to decide.")


def final_account(world: World) -> None:
    """What a world amounts to once nothing more will happen in it."""
    days = world.clock.day
    years, spare = divmod(days, 120)

    remembered_events = set()
    for person in world.people.values():
        for m in person.memories.active():
            if m.event_id:
                remembered_events.add(m.event_id)

    print(heading(f"{world.name} ends."))
    print(f"  It lasted {years} years and {spare} days.")
    print(f"  {len(world.history)} things happened; {len(remembered_events)} of them "
          f"are still in somebody's head.")
    print(f"  {len(world.artifacts)} things were made. "
          f"{len(world.traditions)} of them hardened into practice.")

    print("\n  Who they turned out to be")
    for person in world.people.values():
        if person.is_player:
            continue
        lost = len(person.memories.dormant()) + person.memories.forgotten
        print(f"    {person.name}, {person.age}, {person.occupation}")
        strongest = person.memories.strongest(1)
        if strongest:
            m = strongest[0]
            print(f"      still carries: {m.text()}  ({m.feeling})")
        beliefs = sorted(person.beliefs.values(), key=lambda b: -b.conviction)
        if beliefs:
            b = beliefs[0]
            origin = " - and cannot say why" if b.origin_forgotten else ""
            print(f"      ends up believing: {b.statement}{origin}")
        print(f"      lost {lost} memories on the way")

    if world.traditions:
        print("\n  What outlived the reason for it")
        for t in world.traditions.values():
            kept = {0: "never kept since", 1: "kept once", 2: "kept twice"}.get(
                t.observances, f"kept {t.observances} times")
            print(f"    {t.name}, {kept}. {t.practice}")

    forgotten_days = [e for e in world.history
                      if e.intensity >= 0.5 and e.id not in remembered_events]
    if forgotten_days:
        print("\n  What happened and is now in nobody")
        for e in forgotten_days[:5]:
            print(f"    day {e.day:<5} {e.summary}")

    player = world.player()
    if player is not None:
        print(f"\n  Does anyone remember {player.name}?")
        for person in world.people.values():
            if person.id == player.id:
                continue
            rel = person.relationships.get(player.id)
            if rel is None or rel.familiarity < 0.03:
                heard_of = any(player.id in m.people for m in person.memories.active())
                print(f"    {person.name:<8} " +
                      ("only knows there was someone." if heard_of
                       else "never knew them."))
                continue
            if rel.familiarity > 0.5:
                how = "still knows them well"
            elif rel.familiarity > 0.2:
                how = "remembers them"
            else:
                how = "has almost forgotten them"
            gone = days - rel.last_seen_day
            print(f"    {person.name:<8} {how} (last saw them {gone} days ago, "
                  f"feels {rel.affinity:+.2f})")


def remove(path: Path) -> bool:
    """Delete a world file, or say plainly that it could not be deleted."""
    try:
        path.unlink()
        return True
    except OSError as exc:
        print(f"\n  Could not delete {path}: {exc.strerror}.")
        return False


def cmd_end(args) -> None:
    """Close a world. From the outside, which is the only place it is possible."""
    world = load_world(args)
    path = Path(args.world)
    if world.closed:
        final_account(world)
        print(f"\n  It had already ended on day {world.closed_on}.")
        return

    if not args.yes:
        what = "deleted" if args.delete else "archived"
        answer = input(f"End {world.name} on day {world.clock.day}? "
                       f"The file will be {what}. [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Nothing happened. The world is still running.")
            return

    world.record("ending", f"{world.name} stopped here.",
                 place=None, themes=["ending"], valence=0.0, intensity=1.0)
    world.closed = True
    world.closed_on = world.clock.day
    final_account(world)

    if args.delete:
        if not remove(path):
            print(f"\n  {path} could not be removed. Nothing was kept elsewhere, "
                  f"so the world is still in that file.")
            return
        print(f"\n  {path} is gone. Nothing of it is kept.")
        return

    destination = Path(args.archive) / f"{world.name.lower()}-day{world.clock.day}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    storage.save(world, destination)
    print(f"\n  Kept at {destination}")
    print(f"  You can still read it: elsewhere --world {destination} timeline")
    if path.resolve() != destination.resolve() and not remove(path):
        print(f"  {path} could not be removed - delete it yourself, or it will "
              f"carry on as if nothing had happened.")


# --------------------------------------------------------------------------
# interactive

PLAY_HELP = """
  look                 where you are, who is here
  go <place>           walk somewhere (costs time)
  talk <person>        say something (costs time)
  sit                  stay where you are (costs time)
  make                 make something out of what is on your mind (costs time)
  reflect              turn something over (costs time)
  rest                 stop (costs time)
  remember <text>      put a memory from your life into the world (costs time)
  who <person>         what you know about them - not what is true
  me                   yourself
  news                 what you have noticed lately
  help, quit
"""


def describe_place(world: World, player: Person) -> None:
    place = world.places[player.place]
    print(f"\n{place.name} - {world.clock.label()}")
    print(f"  {place.description}")
    others = [p for p in world.people_at(place.id) if p.id != player.id]
    if others:
        for p in others:
            print(f"  {p.name} is here, {p.last_action or 'doing nothing'}.")
    else:
        print("  You are alone.")
    for a in world.artifacts_at(place.id):
        print(f"  \"{a.title}\" ({a.form} by {world.people[a.creator].name}) is here.")
    print(f"  Ways out: {', '.join(world.places[n].name for n in place.neighbours)}")


def play_tick(world: World, player: Person, action: Action) -> None:
    before = len(world.history)
    log_before = len(world.log)
    playermind.queue(player.id, action)
    simulation.tick(world)
    said_something = False
    for e in world.history[before:]:
        if e.place == player.place or player.id in e.witnesses:
            print(f"  . {e.summary}")
            said_something = True
    for line in world.log[log_before:]:
        print(f"  . {line}")
        said_something = True
    if not said_something and player.last_action:
        print(f"  . You {player.last_action}. Nothing else happened that you noticed.")


def cmd_play(args) -> None:
    world = load_world(args)
    refuse_if_ended(world)
    player = world.player()
    if player is None:
        sys.exit("No player in this world. Run: elsewhere join \"Your name\"")
    player.present = True
    print(f"You are {player.name}, in {world.name}.")
    print(PLAY_HELP)
    describe_place(world, player)
    try:
        while True:
            try:
                raw = input("\n> ").strip()
            except EOFError:
                break
            if not raw:
                continue
            word, _, rest = raw.partition(" ")
            word = word.lower()
            rest = rest.strip()

            if word in ("quit", "exit"):
                break
            elif word == "help":
                print(PLAY_HELP)
            elif word == "look":
                describe_place(world, player)
            elif word == "me":
                args.name = player.name
                cmd_person_inline(world, player)
            elif word == "who":
                other = world.person_by_name(rest) if rest else None
                if other is None:
                    print("  Who?")
                else:
                    print_known(world, player, other)
            elif word == "news":
                for line in world.log[-8:]:
                    print(f"  {line}")
            elif word == "go":
                place = world.place_by_name(rest) if rest else None
                if place is None:
                    print("  You do not know how to get there.")
                else:
                    play_tick(world, player, Action("travel", place.id))
                    describe_place(world, player)
            elif word == "talk":
                other = world.person_by_name(rest) if rest else None
                if other is None or other.place != player.place:
                    print("  They are not here.")
                else:
                    play_tick(world, player, Action("talk", other.id))
            elif word == "make":
                play_tick(world, player, Action("create"))
            elif word == "reflect":
                play_tick(world, player, Action("reflect"))
            elif word == "rest":
                play_tick(world, player, Action("rest"))
            elif word == "sit":
                play_tick(world, player, Action("idle"))
            elif word == "remember":
                if not rest:
                    print("  Remember what?")
                    continue
                rng = world.rng_for("remember", rest, world.clock.day)
                encode_introduced(player, rest, ["memory"], world.clock.day, rng,
                                  world.next_id("mem"), intensity=0.8, valence=0.2,
                                  place=player.place)
                listeners = [p for p in world.people_at(player.place)
                             if p.id != player.id]
                if listeners:
                    event = world.record(
                        "telling", f"{player.name} told them about {rest}",
                        place=player.place, participants=[player.id],
                        themes=["memory"], valence=0.2, intensity=0.55)
                    from .actions import broadcast
                    broadcast(world, event, rng)
                    print(f"  You said it out loud. {', '.join(p.name for p in listeners)} "
                          f"heard some version of it.")
                else:
                    print("  You were alone. It is yours for now.")
                play_tick(world, player, Action("idle"))
            else:
                print("  You cannot do that here. (help)")
    finally:
        storage.save(world, Path(args.world))
        print(f"\nYou leave {world.name}. It keeps going.")


def print_known(world: World, player: Person, other: Person) -> None:
    rel = player.relationships.get(other.id)
    print(f"\n  {other.name}")
    if other.note:
        print(f"    {other.note}")
    if rel is None or rel.familiarity < 0.05:
        print("    You do not know them.")
        return
    print(f"    You feel: {rel.affinity:+.2f}   you think you know them: "
          f"{bar(rel.familiarity, 8)}")
    for impression in rel.impressions[-3:]:
        print(f"    - {impression}")
    print("    (This is what you think. It is not what they are.)")


def cmd_person_inline(world: World, p: Person) -> None:
    print(f"\n  {p.name}, {p.occupation}   mood {p.mood:+.2f}")
    for m in p.memories.strongest(3):
        print(f"    {m.feeling}: {m.text()}")
        print(f"      ~ {m.interpretation}")
    for b in list(p.beliefs.values())[:3]:
        print(f"    you believe: {b.statement}")


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="elsewhere",
        description="A persistent world that remembers.")
    ap.add_argument("--world", default=str(DEFAULT_WORLD), help="path to the world file")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a small world")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--player", default=None, help="join it yourself, by name")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status", help="where everyone is right now")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("advance", help="let time pass without you")
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--mind", default=None, choices=["rules", "llm"],
                   help="which mind the inhabitants use for these days")
    p.add_argument("--away", action="store_true",
                   help="leave the world entirely while it runs")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--all", action="store_true", help="include the unremarkable")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("timeline", help="what happened (history, not memory)")
    p.add_argument("--days", type=int, default=0)
    p.add_argument("--kind", default=None)
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_timeline)

    p = sub.add_parser("person", help="who someone has become")
    p.add_argument("name")
    p.set_defaults(func=cmd_person)

    p = sub.add_parser("memories", help="what someone has left of it")
    p.add_argument("name")
    p.add_argument("--about", default=None, help="filter by theme")
    p.add_argument("--all", action="store_true", help="include forgotten")
    p.add_argument("--limit", type=int, default=12)
    p.set_defaults(func=cmd_memories)

    p = sub.add_parser("event", help="one event, and every version of it")
    p.add_argument("event_id")
    p.set_defaults(func=cmd_event)

    p = sub.add_parser("art", help="what people made")
    p.add_argument("--limit", type=int, default=15)
    p.set_defaults(func=cmd_art)

    p = sub.add_parser("culture", help="traditions and shared beliefs")
    p.set_defaults(func=cmd_culture)

    p = sub.add_parser("join", help="enter the world as a resident")
    p.add_argument("name")
    p.set_defaults(func=cmd_join)

    p = sub.add_parser("invite", help="give something that mattered somewhere to continue")
    p.add_argument("name")
    p.add_argument("--note", default="Someone remembered it.",
                   help="why this presence is here")
    p.set_defaults(func=cmd_invite)

    p = sub.add_parser("remember", help="put a memory from your life into the world")
    p.add_argument("text")
    p.add_argument("--themes", default="memory")
    p.add_argument("--intensity", type=float, default=0.8)
    p.add_argument("--valence", type=float, default=0.2)
    p.set_defaults(func=cmd_remember)

    p = sub.add_parser("end", help="close a world for good")
    p.add_argument("--archive", default="worlds",
                   help="directory to keep the closed world in")
    p.add_argument("--delete", action="store_true",
                   help="do not keep it at all")
    p.add_argument("--yes", "-y", action="store_true", help="do not ask")
    p.set_defaults(func=cmd_end)

    p = sub.add_parser("play", help="live in it for a while")
    p.set_defaults(func=cmd_play)

    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
