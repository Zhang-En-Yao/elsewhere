# How Elsewhere v2 is put together

The rewrite exists to enforce one split, and everything below follows from it:

```
The engine   decides what can be reached      — never what anything meant
A mind       decides what anything meant      — never what can be reached
```

A model asked "do you still remember the flood?" with the flood sitting in its
context will always say yes. So the engine never asks that question. It
decides, on its own, what goes in front of a mind at all; whatever a mind is
shown, it is free to make anything of.

## The two records

```
World.chronicle          one append-only ledger    "The old market burned down."
World.traces(person_id)  one store per person       {"trace": "...", "means": "...", ...}
```

[`world/chronicle.py`](../src/elsewhere/world/chronicle.py) holds the
`Chronicle`: one line of JSON per `Event`, appended, never revised, and the
only thing in Elsewhere that claims to be true.

[`world/memories.py`](../src/elsewhere/world/memories.py) holds the `Trace`:
one person's own account of what an event left in them. A trace is written by
a mind and rewritten by a mind (`Trace.rewrite`, called from `recall`). The
engine touches exactly one thing on it itself — `last_touched`, the day
somebody last had reason to think of it — and reads that back in
[`retrieval.py`](../src/elsewhere/retrieval.py) to decide whether it can still
be handed over. It never edits the words.

Nobody reads another person's traces. To learn something, a person has to be
told, and what they get is a new trace of *being told*, not a copy of the
speaker's.

## Modules

| file | what it owns |
| --- | --- |
| [`world/chronicle.py`](../src/elsewhere/world/chronicle.py) | `Event`, `Chronicle` — the one thing that is true |
| [`world/entities.py`](../src/elsewhere/world/entities.py) | `Being`, `Place`, `Regard` (one being's account of another, one-way), `Belief` |
| [`world/memories.py`](../src/elsewhere/world/memories.py) | `Trace`, `TraceStore` |
| [`world/store.py`](../src/elsewhere/world/store.py) | `World`, save/load, `tick_lock`, the calendar (`season_of`, phases) |
| [`schemas.py`](../src/elsewhere/schemas.py) | the seven answer shapes, used both as a decoding grammar and as an inbound check |
| [`prompts.py`](../src/elsewhere/prompts.py) | the system/user prompt text for each call site |
| [`retrieval.py`](../src/elsewhere/retrieval.py) | `reach`/`hold`/`dormant`/`recallable`/`on_faith` — the one judgement the engine keeps for itself |
| [`agents.py`](../src/elsewhere/agents.py) | the seven call sites: `perceive`, `act`, `speak`, `recall`, `reflect`, `direct`, `arrive`; plus the road (`may_leave`, `depart`, `may_arrive`, `arrive`) |
| [`tick.py`](../src/elsewhere/tick.py) | one phase, in order; `owed_phases`/`settle_clock` for `catchup` |
| [`config.py`](../src/elsewhere/config.py) | which backend and model answers which call site |
| [`backends/`](../src/elsewhere/backends/) | `Call`/`Settings`/`Transcript`/`ask()`, and one module per way of reaching a mind |
| [`seed.py`](../src/elsewhere/seed.py) | the small beginning: three people, one town, a flood |
| [`cli.py`](../src/elsewhere/cli.py) | everything a resident can do from a terminal |

## The seven questions

Every place a mind is consulted goes through
[`agents.py`](../src/elsewhere/agents.py) and follows the same shape: gather
what this person could possibly draw on, ask, check the answer is usable, and
write the consequence into the ledger. None of these functions decide
anything themselves — if a mind declines to answer, or answers with nothing
usable, the person simply had nothing, which is allowed.

| call | asked | schema |
| --- | --- | --- |
| `perceive` | something happened in front of you — what, if anything, stays? | [`PERCEIVE`](../src/elsewhere/schemas.py) |
| `act` | it is this hour and you are standing here — what do you do? | `ACT` |
| `speak` | you are talking to this person — what do you say, and what do you draw on? | `SPEAK` |
| `recall` | you are bringing this up years later — how does it come back now? | `RECALL` |
| `reflect` | the day is over — what did it leave you holding? | `REFLECT` |
| `direct` | does anything happen to the town today? | `DIRECT` |
| `arrive` | does anybody come up the road, and who would they be? | `ARRIVE` |

The schema is the contract. `schemas.grammar(name)` marks every field
required and is handed to the backend as a decoding constraint (Ollama's
`format`, vLLM's `guided_json`), so the shortest possible non-answer — an
empty string, a missing verdict — is unwritable rather than merely undesired.
`schemas.validate(name, data)` checks the same shape again on the way back
in, leniently, because a recorded tape or a lenient backend may not have had
the grammar applied.

[`backends.ask()`](../src/elsewhere/backends/__init__.py) is what actually
puts a `Call` to a backend: it tries once, and if the answer does not
validate, hands the model its own complaint and tries once more before giving
up and returning `None`. Every attempt — prompt, raw answer, whether it
validated, how long it took — is appended to a `Transcript`, which is the
world's replacement for a random seed (see *Determinism*, below).

Some fields are narrowed further than the base schema, per call, to what
actually exists: `act_grammar` restricts `target` to the places and people
actually in reach and adds the `leave` verb only where `agents.may_leave`
says the road goes out from here today; `speak_grammar` restricts `about` to
the numbered things this person can currently bring to mind; `direct_grammar`
restricts `where`/`who` to real places and present people. A model cannot
answer with a place that is not adjacent, a person who is not in the room, or
a departure from somewhere the road does not go — the grammar makes the wrong
answer unwritable instead of the engine repairing it afterwards.

## The memory model

[`retrieval.py`](../src/elsewhere/retrieval.py) is the one place left where
the engine, not a mind, decides something about a person's inner life: how
reachable a trace still is.

```
hold(trace)       = 0.25 + 3.6 · salience^1.5 + 0.35 · ln(1 + recalls)
reach(trace, day) = salience · exp(-age / (45 · hold))
dormant           = reach < 0.06
```

`salience` is the mind's own weighting of the trace — one of five words
(`nothing`/`faint`/`ordinary`/`stays`/`marks`, from `schemas.WEIGHTS`) mapped
onto a number the engine can sort by (`schemas.weight_to_salience`). Age is
days since the trace was last touched, not days since it was laid down —
bringing something up resets the clock. For a trace that is never mentioned
again, this works out to roughly:

| weight the mind gave it | out of reach after (never recalled) |
| --- | --- |
| marks (0.95) | ~445 days |
| stays (0.70) | ~260 days |
| ordinary (0.40) | ~99 days |
| faint (0.15) | ~19 days |

Below the floor a trace is **dormant, not deleted**: it stays on disk, but
`retrieval.recallable` — the function every call site actually uses to build
a prompt — will not offer it. Whatever is not in that list is, for the
purposes of the next thought, forgotten, whether or not it is still there to
be read by a human running `elsewhere person`.

What pulls one memory in front of another, among those still in reach, is
how near it is to what the moment is about — the room somebody is standing
in, the person they have turned to — as a cosine between embeddings, written
once when the words are. It used to be tag overlap, which meant retrieval
only worked when a mind happened to type the same word twice, and never
worked at all for `speak`, whose cue was the listener's id matched against
words a mind had typed. Nearness is spread across whatever that person can
currently reach rather than compared with a threshold, because a raw cosine
has no fixed meaning between one embedder and the next.

`retrieval.py` also defines `cued_return`, a direct-hit lookup meant for "a
memory that unexpectedly returns years later" when this moment points
straight at something dormant — but nothing in `agents.py` or `tick.py` calls
it yet. It is written, tested in isolation, and not wired into any call site.
It is also the one place with a bare cosine threshold, because a question
about one memory cannot be spread across a set.
That is an honest gap, not a subtlety worth reading into.

## Scarcity the engine supplies

A model has no sense of scarcity: asked "does something marking happen to
this person," or "would she leave," or "does anyone come up the road," it
will eventually say yes to all of them, every time, because nothing in its
context tells it these things ought to be rare. Every place this would
matter, `agents.py` answers with a fact instead of asking the question again:

- `HEAVY_PER_DAY` — at most one memory a day gets to survive on its own
  weight; a second "marks"-level trace on the same day keeps its words and
  loses its claim on the rest of the person's life (`_heavy_today`).
- `DIRECTOR_MIN_GAP_DAYS` — the town will not be asked whether something
  happens to it again within two days of the last happening.
- `DEPARTURE_MIN_GAP_DAYS` (45) / `ARRIVAL_MIN_GAP_DAYS` (30) — the road is
  not offered as a verb, and not asked whether anyone comes up it, more often
  than that.
- `TOWN_FLOOR` (2) — nobody may leave if doing so would take the town below
  this size.

None of these are about what anyone wants. Wanting to go, wanting something
to happen, is the mind's business and is asked for in the ordinary way; these
constants only gate whether the question is even on the table today.

## One phase

[`tick.py`](../src/elsewhere/tick.py) lives one phase, in a fixed order:

1. **Morning only** — `agents.direct` asks whether anything happens to the
   town today; `agents.arrive`, if the town is short of somebody, asks who
   comes up the road. Both run before anyone decides what to do, so a
   happening can be reacted to on the same day, and a newcomer gets to live
   the day they arrive instead of standing at the top of the road until
   tomorrow.
2. **Everyone decides at once** — every present, model-minded person is
   asked `act`, from wherever they are currently standing, before anyone
   moves. Nobody's decision can see anyone else's.
3. **The world settles what is physically so** — movement happens, and
   anyone whose action was `leave` is walked out through `agents.depart` and
   is no longer present for anything that follows *in this phase or ever
   again*.
4. **Conversation** — among people still in the same place after step 3, at
   most one conversation per person per phase (`converse`): the speaker's
   `speak` produces a line, `agents.recall` may reshape the speaker's own
   memory of what they drew on, and every listener present gets their own
   `perceive` of the exchange — the same machinery as perceiving an event,
   because a sentence someone hears is one.
5. **Night only** — whoever's day left something is asked `reflect`. Nothing
   is done for whoever is left over: whether a belief's origins are still in
   reach is asked when someone looks (`retrieval.on_faith`), not kept as a
   flag that has to be refreshed.

`elsewhere tick -n` calls this directly, `n` times. `elsewhere catchup` is the
scheduled entry point: `tick.owed_phases` works out how many phases the wall
clock says have passed since `world.last_tick_at` (default six real hours per
phase), runs at most `--max` of them, checks with `backends.probe` first that
a mind can actually be reached (a world waits rather than inventing a day
without one), and `tick.settle_clock` decides whether the rest of a longer
backlog is carried forward or simply slept through — carrying it forward
would mean a laptop asleep for a week wakes up and spends an hour on model
calls to catch up, so past `--max` it is not.

## The road

Leaving and arriving both go through the same engine-decides/mind-decides
split as everything else, but the facts checked are about the map and the
calendar, not about anyone's wants:

- `agents.may_leave(world, person)` — is there a road out from where they
  stand (`place.road_out`), is the town above `TOWN_FLOOR` (2), and has it been
  long enough since the last departure. Only if all three hold does `leave`
  even enter the grammar `act` is asked under. There used to be a fourth — not
  at night — and it was the engine deciding that nobody here is the sort of
  person who leaves in the dark, so it is theirs to answer instead.
- `agents.may_arrive(world)` — is the town at or above `TOWN_CEILING` (8), in
  which case the road is never worth asking; otherwise, has enough time passed
  since the road was last asked or answered (`world.road_asked_on`, via
  `_road_anchor`) — about a month (`ARRIVAL_MIN_GAP_DAYS`) while the town is
  short of somebody (`short_of_somebody`: more departed than have arrived),
  about a year (`ARRIVAL_SETTLED_GAP_DAYS`) once it is not. A town can
  therefore end up bigger than it began, up to the ceiling, and asking itself
  counts even when the answer is no — otherwise a town owed somebody would put
  the question every morning.

Whoever leaves is recorded as a `departure` event and perceived by everyone
still present, exactly like any other happening, then marked `present=False`
and never asked anything again. What they had, and every note anyone wrote
about them, stays exactly as it was the day they went — `elsewhere person
<name>` reads them frozen. Whoever arrives is built from the model's own
`arrive` answer (name, card, manner, trade, where they came from), dropped at
the place the road comes in with no `home` of their own yet, and lives the
day they arrived like anyone else.

## Minds

[`backends/__init__.py`](../src/elsewhere/backends/__init__.py) defines the
`Backend` protocol (one method, `complete(call, model, temperature, extra) ->
str`) and a small registry (`register`/`get`). The engine never imports a
specific backend directly; `agents.py` always goes through
`get_backend(settings.backend)`.

- [`backends/openai_compat.py`](../src/elsewhere/backends/openai_compat.py) —
  `OllamaBackend` (native `/api/chat`, schema as `format`), `OpenAICompatBackend`
  (any `/v1` server — LM Studio, llama-server — tries `response_format:
  json_schema` and falls back to plain `json_object`), `VLLMBackend`
  (`guided_json`). Written against `urllib`, so reaching a local or
  self-hosted model needs no dependency.
- [`backends/anthropic_backend.py`](../src/elsewhere/backends/anthropic_backend.py)
  — Claude, imported lazily; a world that never uses it never needs the
  `anthropic` package. The schema is passed as a forced tool call.
- [`backends/stub.py`](../src/elsewhere/backends/stub.py) — answers every
  call with the smallest valid thing, or with a scripted answer keyed by
  `"<call>|<person id>"`. This is what `make test` runs against; no model, no
  key, no latency.

[`config.py`](../src/elsewhere/config.py) decides which backend and model
answer which of the seven call sites, written into each world as
`config.json` at creation time so it is editable rather than buried in code.
The intent it is built around: the cheap, frequent decisions (`act`) can run
on something small and local, while the ones that need real judgement
(`perceive`, `speak`, `reflect`) can be pointed at something larger.
`ELSEWHERE_BACKEND=stub` overrides every call site at once, regardless of
`config.json` — how the tests and `--dry-run`-style runs work without
touching a model.

## Storage

```
<world>/
  world.json             clock, places, counters, closed flag
  people/<id>.json       one card per person
  chronicle.jsonl        append-only history
  memories/<id>.jsonl    one file per person, rewritten whole on save
  transcript/<day>.jsonl every question put to a mind that day, and its answer
  tick.lock              a directory, held while a tick is running
```

[`world/store.py`](../src/elsewhere/world/store.py) is the only module that
touches disk. `save`/`load` round-trip a `World`; `tick_lock` is a
directory-based lock (`os.mkdir` as the atomic primitive) so `cron`/`launchd`
firing twice cannot run two ticks at once — a lock older than 15 minutes is
taken over rather than left to stall the world forever.

## Determinism

There is no stored random seed, because there is no dice roll left in the
engine to seed — every place v0.1 rolled dice (whether something sticks, what
a person says), v2 asks a mind instead, and a stochastic model has no seed to
give back. What the engine keeps instead is the transcript: `backends.ask`
appends every prompt and every answer - whether it validated, how long it
took - to a `Transcript` (`world/transcript/day<NNN>.jsonl`), which is a
durable, readable record of why the town did what it did, not a mechanism for
replaying it. `make test`'s reproducibility comes from
[`backends/stub.py`](../src/elsewhere/backends/stub.py) instead: fixed or
scripted answers, no model, no latency.

## What is not here yet

The one remaining engine-side judgement that is written but unused is
`retrieval.cued_return` (above). Everything larger than that is a matter of
what has and has not been built yet, and is tracked in
[`ROADMAP.md`](ROADMAP.md) rather than here: letting a person be played
rather than modelled (P2), making things (P5), any structure above the
individual (P6), admitting a memory from outside the world rather than
re-running one already in it, and ending a world at all.
