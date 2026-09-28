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

The objective record is an append-only `Chronicle` of what happened
([`world/chronicle.py`](src/elsewhere/world/chronicle.py)); each event is shown to
somebody once (`agents.unseen`), in the next `act`/`speak` they answer. The subjective
record is theirs alone and never revised: what they kept of a moment is a note in their
own words, written in that same answer's `noted` field (`notes/<id>.jsonl`,
[`world/notes.py`](src/elsewhere/world/notes.py)); at night `settle` goes over the day's
notes — never the chronicle — and rewrites the one page they carry, `Who.notebook`, at
most `schemas.NOTEBOOK_CHARACTERS` long (every version kept in `pages/<id>.jsonl`). The
engine has no memory algorithm of its own; the one search it runs
([`recollection.py`](src/elsewhere/recollection.py), which older note a moment brings
back) is BM25 (SQLite FTS5) and embeddings (sqlite-vec) fused by RRF — library-ranked,
not hand-ranked. Every place a mind is consulted goes through
[`agents.py`](src/elsewhere/agents.py)'s five call sites, each with a schema in
[`schemas.py`](src/elsewhere/schemas.py) used as both a decoding grammar and an inbound
check. [`tick.py`](src/elsewhere/tick.py)/[`schedule.py`](src/elsewhere/schedule.py) run the
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
    suffix (`day_at`/`season_at`/`date_at`/`clock_at`; `initiator`/`respondent`;
    `Turn`/`Talk`/`Arrival`/`Departure` all nouns).
  - One concept, one word, everywhere (`being`, never `person` in one module and
    `being` in the next; `recall`/`recalled`, never also `brought_back`) — and one word,
    one concept (`settle` is the end of a day, not also a cursor or a clock).
- Code may repeat itself; prefer duplication over premature abstraction.
- When a string is used as an identifier, use an `Enum` or a value pulled from a growable
  counter/registry — not an ad-hoc conventional constant.
- When a task needs a specific algorithm, use a published one from the relevant field
  (cite it, as ARCHITECTURE.md cites MemGPT for the notebook) rather than inventing one.
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
