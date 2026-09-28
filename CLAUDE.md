# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Elsewhere is a persistent artificial-life simulation: a small town of people who act,
talk, remember, and forget on their own clock, driven by an LLM for anything that
requires judgement. `v2` (current) is a from-scratch rewrite of `v0.1` (tagged `v0.1`):
v0.1 made every judgement — what stuck, what it meant, what got said — with a formula;
v2's engine only decides what can be *reached*, and hands every question of meaning to a
model. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before making structural
changes — it explains the design, not just the modules — and check
[docs/ROADMAP.md](docs/ROADMAP.md) before assuming something is missing by accident.

## Commands

```bash
make test          # typecheck, then run the full suite against the stub backend (no model, no key)
make typecheck      # mypy only (pip install -e ".[dev]" first — plain `make test` skips it silently if mypy isn't installed)
```

Run a single test:

```bash
python3 -m unittest tests.test_tick                          # one module
python3 -m unittest tests.test_tick.TestSomething.test_method # one test
```

Other commands operate on a live world under `./world` and need a reachable model
(`elsewhere doctor` checks this):

```bash
make world          # elsewhere --world world initialize — 3 people, 1 town, a flood
make tick           # live one step now (TICKS=3 for three)
make watch           # read-only TUI window onto the world
make news            # what happened since you last looked
make schedule / make unschedule / make schedule-status   # launchd agent that runs the world while you're away
make doctor           # can the configured minds be reached?
make live             # put a model on this Mac via MLX and check every call site can reach it
```

## Architecture

Two rules everything else follows from:

```
The engine   decides what can be reached      — never what anything meant
A mind       decides what anything meant      — never what can be reached
```

The engine keeps two records: an append-only `Chronicle` of what happened
([`world/chronicle.py`](src/elsewhere/world/chronicle.py)), and one `Memory` store per
person of what it meant to them ([`world/memories.py`](src/elsewhere/world/memories.py));
nobody reads another person's memories. Every place a mind is consulted goes through
[`agents.py`](src/elsewhere/agents.py)'s seven call sites, each with a schema in
[`schemas.py`](src/elsewhere/schemas.py) used as both a decoding grammar and an inbound
check. [`retrieval.py`](src/elsewhere/retrieval.py) is the one place the engine judges a
person's inner life — ACT-R's declarative memory, at its published parameters.
[`tick.py`](src/elsewhere/tick.py)/[`schedule.py`](src/elsewhere/schedule.py) run the
world with no fixed step size: every entity sets its own timer, and the world advances to
whichever is soonest. [`backends/`](src/elsewhere/backends/) is a `Backend` protocol with
one module per way of reaching a mind; `make test` runs against
[`backends/stub.py`](src/elsewhere/backends/stub.py) only.

Full explanation, including why each piece is shaped this way, is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — read it before structural changes, don't
re-derive it from the modules.

## Conventions

- No hand-rolled logic where a needed behavior already has a standard-library or
  well-established package solution — prefer the native/existing tool over reimplementing it.
- No abbreviated variable names.
- Code may repeat itself; prefer duplication over premature abstraction.
- When a string is used as an identifier, use an `Enum` or a value pulled from a growable
  counter/registry — not an ad-hoc conventional constant.
- When a task needs a specific algorithm, use a published one from the relevant field
  (cite it, as `retrieval.py` cites ACT-R) rather than inventing one.
- No leading underscore on a name unless it is a class method guarding real encapsulation
  (cached/lazily-initialized state, a thread-locked resource, a polymorphic hook a
  subclass overrides) or the plain name would collide with an attribute of the same
  meaning (e.g. `App._stamp()` stays underscored because `self.stamp` already holds its
  result). A module-level helper, or a class method that is just decomposed logic with no
  state to protect, gets a plain name — Python has no real access control, so the
  underscore should mean something when it's there.

## Testing notes

`make test` type-checks before running anything, deliberately — this codebase's
recurring mistake is an attribute that stopped existing in code nothing calls (e.g.
`Chronicle.since` reading a field that no longer existed for several commits, with 84
passing tests silent about it because nothing exercised that path). Plain `python3 -m
unittest discover -s tests` skips that check. mypy config in `pyproject.toml` is
deliberately not strict — it exists to catch stale attributes, not to enforce full typing.
