# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Elsewhere is a persistent artificial-life simulation: a small town of beings who act,
talk, remember, and forget on their own clock, driven by an LLM for anything that
requires judgement. The engine only decides what can be *reached*; every question of
meaning — what stuck, what it meant, what got said — is handed to a model. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before making structural
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
make world          # initialize ./world (3 beings, 1 town, a flood), then `make schedule`
make tick           # live one step now (TICKS=3 for three)
make watch           # read-only TUI window onto the world
make news            # what happened since you last looked
make schedule / make unschedule / make status   # launchd agent that runs the world while you're away
make doctor           # can the configured minds be reached?
make live             # put a model on this Mac via MLX and check every call site can reach it
```

## Architecture

Two rules everything else follows from:

```
The engine   decides what can be reached      — never what anything meant
A mind       decides what anything meant      — never what can be reached
```

The code is in clean-architecture layers, each importing only those inside it
(enforced by [`tests/test_layers.py`](tests/test_layers.py)): `domain/` (what the world
is made of, no IO) ← `application/` (the engine: `reachability`, `schedule`, `actions`) ←
`server/` (every action as a tool on one MCP server, the official `mcp` SDK's
`MCPServer`) ← `harness/` (the minds) ← `interface/` (cli, tui, seed); `adapters/`
(storage, backends, retrieval) depends only on `domain/`.

The harness is everything between a model and the world. It decides what each mind is
shown and keeps what it keeps ([`harness/memory.py`](src/elsewhere/harness/memory.py)),
asks, and turns the answer into a tool call made over an in-process MCP session —
the server is the only thing that changes the world, and it checks reachability itself.
Two agents, never mixed: a being ([`harness/being.py`](src/elsewhere/harness/being.py):
`act`, `speak`, `consolidate`) and the objective world
([`harness/world.py`](src/elsewhere/harness/world.py): `stir`, which comes to `occur`,
`admit` or nothing). The world never acts for a being: it throws events, and each being
they reach decides in its own `act` what to do about them. The harness names every MCP
method itself from the answer (`action: "move"` → `tools/call move`); no model is shown
the server's tool list or picks from it. Nothing outside the world decides a turn.

The objective record is an append-only chronicle of `Event`s
([`domain/chronicle.py`](src/elsewhere/domain/chronicle.py)); each event is shown to
somebody once (`memory.percepts`), in the next `act`/`speak` they answer. The subjective
record is theirs alone and never revised, laid out as the multi-store model lays out a
mind: what they kept of a moment is an `Episode` in their own words, written in that same
answer's `encoded` field (`episodes/<id>.jsonl`, [`domain/memory.py`](src/elsewhere/domain/memory.py)) —
the short-term store. At night `consolidate` — put to their sleep in the third person,
not to them — goes over the day's episodes, never the chronicle, and lays them down as
`Engram`s (a few weighted `Gist`s each — short propositions, `engrams/<id>.jsonl`) and rewrites
`Identity.self_schema` (idiolect, traits, concerns, assumptions, impressions; at most
`schemas.SELF_SCHEMA_CHARACTERS`, every version in `self_schemas/<id>.jsonl`).
`Identity.biography` is never rewritten. Memory never goes through the server. The engine has
no memory algorithm of its own: which engram a moment brings back
([`adapters/retrieval.py`](src/elsewhere/adapters/retrieval.py)) is BM25 (SQLite FTS5) and
embeddings (sqlite-vec) fused by RRF — library-ranked, not hand-ranked — and how much of
it comes back is the published power law of forgetting, keeping the gists the mind
weighted heaviest. Each call site has a schema in
[`harness/schemas.py`](src/elsewhere/harness/schemas.py) used as both a decoding grammar
and an inbound check. [`harness/tick.py`](src/elsewhere/harness/tick.py)/[`application/schedule.py`](src/elsewhere/application/schedule.py)
run the world with no fixed step size: every being and the world set their own timer
(always through the `wait` tool), and the world advances to whichever is soonest.
[`adapters/backends/`](src/elsewhere/adapters/backends/) is a `Backend` protocol with one
module per way of reaching a mind; `make test` runs against
[`adapters/backends/stub.py`](src/elsewhere/adapters/backends/stub.py) only.

Full explanation, including why each piece is shaped this way, is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — read it before structural changes, don't
re-derive it from the modules.

## Conventions

- No hand-rolled logic where a needed behavior already has a standard-library or
  well-established package solution — prefer the native/existing tool over reimplementing it.
- Naming — for every name: variables, parameters, functions, classes, and the throwaway
  ones in loops, comprehensions and lambdas:
  - Precise, not colloquial: a name states what the thing is, in the domain's own term
    (`destination`, not `p`; `elapsed`, not `took`; `load_vector_extension`, not
    `vector_search`, for something that reports whether it loaded).
  - No abbreviations, even for a one-line variable: `exception` not `exc`/`e`, `file`
    not `fh`, `data` not `d`, `being` not `p`, `temporary` not `tmp`. Only names fixed
    by an outside standard are exempt: `id`, `json`, a published algorithm's own symbol
    (RRF's `k`), screen coordinates `x`/`y`, the `pid` file.
  - One word where possible. A name that needs three or four words is carrying context
    that belongs to its module, class or method — move it there
    (`configuration.load`, not `configuration.load_configuration`), or split the function.
  - Parallel concepts get parallel names: same part of speech, same word order, same
    suffix (`day_of`/`season_of`/`date_of`/`clock_of`; `initiator`/`respondent`;
    `Turn`/`Talk`/`Arrival`/`Departure` all nouns).
  - One concept, one word, everywhere (`being`, never `person` in one module and
    `being` in the next; `retrieve`/`retrieved`, never also `recall` or `brought_back`) —
    and one word, one concept (`consolidate` is the night's work on a day, not also a
    cursor or a clock).
  - Memory is named in the terms of memory research, each cited where it is defined
    (`Episode`, `Engram`, `Gist`, `short_term`, `consolidate`, `self_schema`, `idiolect`,
    `traits`, `concerns`), not in metaphors (`note`, `notebook`, `page`).
- Code may repeat itself; prefer duplication over premature abstraction.
- When a string is used as an identifier, use an `Enum` or a value pulled from a growable
  counter/registry — not an ad-hoc conventional constant.
- When a task needs a specific algorithm, use a published one from the relevant field
  (cite it, as ARCHITECTURE.md cites MemGPT for the self-schema) rather than inventing one.
- No leading underscore on a name unless it is a class method guarding real encapsulation
  (cached/lazily-initialized state, a thread-locked resource, a polymorphic hook a
  subclass overrides) or the plain name would collide with an attribute of the same
  meaning (e.g. `App._stamp()` stays underscored because `self.stamp` already holds its
  result). A module-level helper, or a class method that is just decomposed logic with no
  state to protect, gets a plain name — Python has no real access control, so the
  underscore should mean something when it's there.

## Testing notes

`make test` type-checks before running anything, deliberately: the mistake tests cannot
catch is an attribute that stops existing in code nothing calls — tests only reach code
that runs, while mypy reads all of it. Plain `python3 -m unittest discover -s tests`
skips that check. mypy config in `pyproject.toml` is
deliberately not strict — it exists to catch stale attributes, not to enforce full typing.
