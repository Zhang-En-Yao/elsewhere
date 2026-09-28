# How Elsewhere is put together

Two rules. Everything below follows from them.

```
The engine   decides what can be reached      — never what anything meant
A mind       decides what anything meant      — never what can be reached
```

A model asked "do you still remember the flood?" with the flood sitting in its
context will always say yes. So the engine never asks that question. It
decides what goes in front of a mind at all — the page that person carries,
their own notes from today, what has just reached them, and one older note the
moment points at — and whatever a mind is shown, it is free to make anything of.

```
Nothing on the engine's side is an algorithm
```

What is left on the engine's side is reading a timer, checking a map, counting
who is present, filtering the chronicle for what reached somebody, and one
search run by libraries — BM25 in SQLite's FTS5 and cosine distance in
sqlite-vec, fused by Reciprocal Rank Fusion — to say which older note a moment
points at. There is no equation anywhere that says what a being remembers, how long a
memory lasts, how much quiet a town gets, how often the road is worth asking,
or when a day ends. Each of those is a question put to a mind.

Nothing continuous is cut into buckets on the way past, either. A memory has
no weight, a belief has no confidence, a feeling has no vocabulary, and the
clock has no step.

## The records

```
World.chronicle            one append-only ledger          "The old market burned down."
World.notes(being_id)      every note they ever made       what a moment was to them, as it happened
World.pages(being_id)      every page they ever wrote      what they carried, each night
Being.who.notebook         the newest of those pages       what they carry now
```

[`world/chronicle.py`](../src/elsewhere/world/chronicle.py) holds the
`Chronicle`: one line of JSON per `Event`, appended, never revised, and the
only thing in Elsewhere that claims to be true. Every event says who it
`informed`, and where each of them stood (`data["viewpoints"]`).

The other three are the subjective record, and like the chronicle nothing in
them is ever revised or thrown away:

- [`world/notes.py`](../src/elsewhere/world/notes.py) holds `Notes`: what
  somebody kept of a moment, in their own words, written in the `noted` field
  of the `act` or `speak` answer they gave right after it reached them, with the
  ids of the events it was a note of and its embedding.
- [`world/pages.py`](../src/elsewhere/world/pages.py) holds `Pages`: every page
  a person has written, one per `settle`, starting from the page `seed` wrote
  them with.
- `Who.notebook` ([`world/entities.py`](../src/elsewhere/world/entities.py)) is
  the newest page: everything one person carries from one day to the next —
  what keeps coming back to them, what they want, what they hold true, how
  they see the people they know, whatever of the past is still with them.

Only minds write any of it. What somebody lost is lost to them and not to the
world.

Nobody reads another person's notebook. To learn something, a person has to be
told, and what they get is the event of being told — which they then write
into their own page, or don't.

## Modules

| file | what it owns |
| --- | --- |
| [`world/chronicle.py`](../src/elsewhere/world/chronicle.py) | `Event`, `Chronicle` — the one thing that is true |
| [`world/entities.py`](../src/elsewhere/world/entities.py) | `Being` = `Who` + `Where` + `When`; `Place` (prose) and `Map` (the town's geography) |
| [`world/notes.py`](../src/elsewhere/world/notes.py) | `Note`, `Notes` — every note each person has made |
| [`world/pages.py`](../src/elsewhere/world/pages.py) | `Page`, `Pages` — every page each person has written |
| [`world/store.py`](../src/elsewhere/world/store.py) | `World`, save/load, `TickLock`, the calendar |
| [`schemas.py`](../src/elsewhere/schemas.py) | the five answer shapes, used as a decoding grammar and as an inbound check; `NOTEBOOK_CHARACTERS` |
| [`prompts.py`](../src/elsewhere/prompts.py) | the system/user prompt text for each call site |
| [`recollection.py`](../src/elsewhere/recollection.py) | which older note a moment brings back: BM25 + embeddings, fused by RRF |
| [`schedule.py`](../src/elsewhere/schedule.py) | one timer per entity, set by the entity, and the interrupt over it |
| [`agents.py`](../src/elsewhere/agents.py) | the five call sites, `unseen`/`day_notes`/`recall`, and the road |
| [`tick.py`](../src/elsewhere/tick.py) | one step, in order; `owed_hours`/`reconcile` for `continue` |
| [`configuration.py`](../src/elsewhere/configuration.py) | which backend and model answers which call site |
| [`backends/`](../src/elsewhere/backends/) | `Call`/`Settings`/`Transcript`/`ask()`, one module per way of reaching a mind |
| [`seed.py`](../src/elsewhere/seed.py) | the small beginning: three people, one town, a flood |
| [`cli.py`](../src/elsewhere/cli.py) | everything a resident can do from a terminal |
| [`tui/`](../src/elsewhere/tui/) | the same, in a window that only reads: `views.py` decides what to show, `screen.py` where to put it |

## The five questions

Every place a mind is consulted goes through
[`agents.py`](../src/elsewhere/agents.py) and follows the same shape: gather
what this person could possibly draw on, ask, check the answer is usable, and
write the consequence into the ledger. None of these functions decide anything
themselves — if a mind declines to answer, or answers with nothing usable, the
person simply had nothing, which is allowed.

| call | asked | schema |
| --- | --- | --- |
| `act` | this just reached you — what do you keep of it? You are standing here — what do you do, for how long, and does anything reach you while you do it? | `ACT` |
| `speak` | this was just said — what do you keep of it? You are talking to this person — what do you say? | `SPEAK` |
| `settle` | you have stopped for the day — here is what you kept of it; what is on your page now? | `SETTLE` |
| `stir` | does anything happen to the town — and when should you be asked again? | `STIR` |
| `arrive` | does anybody come up the road, who would they be, and when should you be asked again? | `ARRIVE` |

The schema is the contract. `schemas.grammar(name)` marks every field required
and is handed to the backend as a decoding constraint (llguidance's token
mask under MLX, `response_format` on a `/v1` server), so the shortest possible non-answer — an empty string, a
missing verdict — is unwritable rather than merely undesired.
`schemas.validate(name, data)` checks the same shape again on the way in,
leniently, because a backend without grammar support may omit fields.

Field order is load-bearing: keys are generated in the order the schema lists
them, so every schema puts the reasoning and the description first and the
decision last. A model that is asked for a verdict first commits to it in one
token, before it has written a word about what happened.

Some fields are narrowed further, per call, to what actually exists.
`act_grammar` restricts `target` to the places and people in reach and adds
`leave` only where `agents.may_leave` says the road goes out from here;
`stir_grammar` restricts `where`/`who` to real places and present people. A
model cannot answer with a place that is not adjacent or a person who is not
in the room. `SETTLE`'s `notebook` carries a `maxLength`, so the page's size is
part of the grammar as well as of the check.

[`backends.ask()`](../src/elsewhere/backends/__init__.py) puts a `Call` to a
backend: it tries once, and if the answer does not validate, hands the model
its own complaint and tries once more before giving up and returning `None`.
Every attempt — prompt, raw answer, whether it validated, how long it took — is
appended to a `Transcript`.

## The memory model

There is no memory model in the engine. There are three kinds of writing, a
size, a filter, and a search somebody else wrote. It is laid out the way
complementary learning systems theory lays out a mind (McClelland, McNaughton
& O'Reilly 1995): episodes written down fast as they happen, and folded slowly
into what somebody carries.

```
perception   agents.unseen          what reached them since they last looked up, shown once, at most NEW_EVENTS
day          agents.day_notes       their own notes since they last settled, at most DAY_NOTES
carried      Who.notebook           one page, rewritten each night, at most NOTEBOOK_CHARACTERS
recalled     agents.recall          one older note the moment points at
```

**The chronicle is shown once.** `unseen` is every event after
`When.seen_through` whose `informed` includes this person, each with where they
stood, newest `NEW_EVENTS` (12). It goes in front of the next `act` or `speak`
they are asked, and whatever the answer, `seen_through` moves past it: nobody
is shown the same event twice. `seen_through` is a position in the chronicle
rather than an hour, because a step can take no time and events at the same
hour can fall on either side of somebody looking up.

**What they keep of it is theirs.** The same answer carries `noted`: the
fragment they keep, in their own voice, or nothing — most of what happens
sticks to nobody, and what nobody noted is gone from them the moment they
looked away. A note is appended to `Notes` with the events it was a note of,
which is how `elsewhere event` can put every version of one event side by side.
Keeping it costs no call of its own, because it rides on an answer that was
being given anyway; the price is that somebody `absorbed` sees what happened
only when they next look up, which is also what absorbed means.

**The day is their notes.** `act` and `speak` are shown `day_notes` — what they
have kept since they last settled — and so is `settle`, which is shown nothing
else of the day but what they were doing (`Where.lately`). The chronicle is
never shown at night: the evening goes over what they kept, not over what
happened, so what they got wrong in the moment stays wrong.

**The page is rewritten each night.** `settle` takes the old page, the day's
notes and one recalled note, and takes back the whole page. This is MemGPT's
core memory (Packer et al. 2023, "MemGPT: Towards LLMs as Operating Systems"):
a fixed-size block of context the agent itself edits, where the size is the
constraint and what survives it is the agent's decision; done once a day over
the old page and the new notes, it is the recursive summarisation of Wang et
al. (2023). `NOTEBOOK_CHARACTERS` (1500) is the one number the world has about
what somebody can carry; what wears down, what gets misremembered and what
goes, is decided by the mind writing the page. `settled_through` then moves past
the day, and the page is appended to `Pages`.

**Something long gone can come back.** Every `act`, `speak` and `settle` asks
`recollection.recall` for one note from before today, cued by the moment:
what just reached them and where they are standing, for `act`; whom they are
talking to and what was just said, for `speak`; the day's own notes and what
they were doing, for `settle`. Two rankings, each published and each run by a
library: Okapi BM25 (Robertson & Zaragoza 2009) in SQLite's FTS5 over
Porter-stemmed words (Porter 1980), which is good at names; and cosine distance
between sentence embeddings in sqlite-vec, which is good at a thing said in
other words. They are fused by Reciprocal Rank Fusion (Cormack, Clarke &
Buettcher 2009) at the paper's k = 60. It is a request answered with the best
there is, not a gate — there is no threshold, so on a day that points at
nothing much, what comes back is only loosely related, the way a mind wanders.
Whether it belongs back on the page is theirs. Without an embedder or without
sqlite-vec, BM25 alone decides; a note placed by one embedder is never compared
with another's vectors (`Note.embedded_by`).

What follows:

- **A belief, a want, how one person sees another** are all lines on the page.
  Whether today changed any of them is the writer's call.
- **Telling changes what is told** without a call of its own: whoever speaks
  has their page in front of them, what they said is an event, the listener
  notes what they kept of it, and that evening each writes their page again.
- **A newcomer carries nothing.** `arrive` sets `seen_through` to the
  chronicle's length, so nothing from before they came reaches them.
- **Somebody who left is frozen.** Nothing informs someone who is not present,
  and nobody gone is asked anything.
- **A settle that gives nothing usable changes nothing** — the page stays, and
  so does the day, to be gone over next time.

Long-term memory in the weights — a LoRA adapter per person, trained on their
own pages and notes — is the next layer down, and is in the roadmap.

## Scarcity, and who supplies it

A model has no sense of scarcity: asked "does something marking happen to this
person," or "would she leave," or "does anyone come up the road," it will
eventually say yes to all of them, because nothing in its context tells it
these things ought to be rare. What supplies the scarcity is that **the thing
being asked sets its own interval, in the same answer**:

- Every call site but `SPEAK` and `SETTLE` carries the same `again_in_hours`.
  `ACT` adds `settling` and `absorbed`. A person says how long
  they will be at what they are doing, whether this is them stopping for the
  day, and whether anything short of the roof coming off gets their attention
  while they do it.
- In `STIR` and `ARRIVE`, the town says how long a
  quiet stretch it is giving itself; the road says how long before it is worth
  asking again. Both are asked for whether or not anything happened, so a town
  that has just had a fire can take its fortnight.

The engine puts no limit on the town's size: anybody may leave, even the last
of them, and the road is asked however many are already here.

Three more are budgets: `schemas.NOTEBOOK_CHARACTERS` (1500) is how much one
person can carry, `agents.NEW_EVENTS` and `agents.DAY_NOTES` (12 each) how much of a day is in front
of them before they go over it, and `tick.TURNS` (4) the most that may be said
in one exchange.

## One step

There is no step size. [`schedule.py`](../src/elsewhere/schedule.py) is a small
version of Concordia's interrupt-driven scheduler
(`concordia/components/game_master/interrupt_scheduling.py`): every entity in
the world carries exactly one timer and sets it itself, and the world advances
to whichever comes first. Two rules, and they are the whole module:

```
the world advances to the earliest timer, and never past it
anything that reaches somebody pulls their timer to now, unless they are absorbed
```

The second is Concordia's interrupt and its mask. `When.absorbed` is one bit
where Concordia's `InterruptMask` is a list of event-tag prefixes, because a
town has four kinds of event and a person does not think in prefixes. A thing
that happens *to* somebody is non-maskable, here as there.

[`tick.py`](../src/elsewhere/tick.py) lives one step, in a fixed order:

1. **`schedule.advance_to_next_due`** moves the clock to the next thing due. Anyone with no
   timer of their own is woken at that same moment: a mind that gave no usable
   duration said nothing, so the engine supplies nothing on its behalf beyond
   letting it round again. If *nothing* anywhere has a timer, the step returns
   `idle` and the clock does not move.
2. **Whatever happens to the town rather than in it** — `stir` if the town's
   timer has come round, `arrive` if the road's has. Both run before anyone
   decides what to do, so a happening can be reacted to in the same step and a
   newcomer lives the day they arrive.
3. **Whoever is due decides at once**, from wherever they are standing, before
   anyone moves. Not everybody — a person who said they would be asleep for
   eight hours is asleep for eight hours unless something woke them.
4. **The world settles what is physically so** — movement, and anyone whose
   action was `leave` is walked out and is no longer present for anything that
   follows.
5. **Conversation** — among people still in the same place, at most one
   exchange per person per step. An exchange is turns, alternating, until one
   of them has nothing to say. Each turn is its own event, informing everyone
   there, so the next turn is a reply to it. Only the one spoken to is roused;
   whoever overheard it finds it in front of them the next time they look up.
6. **Whoever said they were stopping** goes over the day they are stopping at
   the end of, with `settle`. Their day is what they kept of it in their own
   notes since they last did this, and what they were doing (`Where.lately`).

`elsewhere tick -n` calls this directly. `elsewhere continue` is the scheduled
entry point, and the promise it keeps is that a day here is a day there:
`tick.owed_hours` works out how much world time the wall clock says has gone
unlived, and the loop pays it off in whatever steps the people in the world
asked for. `--max` bounds model calls, not time. `tick.reconcile` decides
whether the rest of a longer backlog is carried forward or slept through; past
`--max` it is not, because carrying it forward would mean a laptop asleep for a
week wakes up and spends an hour catching up.

## Consequence

The engine does not resolve an action into an outcome. What somebody is doing
goes into `Where.lately` in their own words, and `stir` is shown it — so the
town can see that somebody has been on a roof for a fortnight and say what came
of it. That is the whole of how anything anybody does changes the world.

Full action resolution, which is Concordia's Game Master
(`components/game_master/event_resolution.py`), is not in this engine.

## The road

Leaving and arriving go through the same engine-decides/mind-decides split as
everything else, but the facts checked are about the map, not about wants:

- `agents.may_leave(world, person)` — does the road go out from where they are
  standing (`world.map.road`). Only if it does does `leave` enter the
  grammar `act` is asked under. Whether to take it, and at what hour, is theirs.
- `agents.may_arrive(world)` — has the road's own timer come round. Who has
  gone is a fact shown *to* the road rather than the engine's reason for
  asking it.

Whoever leaves is recorded as a `departure` event that informs everyone still
present, then marked by `When.left_at` and never asked anything again. Their
page, and every line anyone wrote about them, stays exactly as it was the day
they went. Whoever arrives is built from the road's own `arrive` answer,
dropped at the place the road comes in with no home of their own and an empty
page, and lives the day they arrived.

## What a being is

```
Being
  id, name, mind                 the handle, and whose answers these are
  who:   Who                     card, manner, notebook
  where: Where                   place, home, lately   (doing = lately[-1])
  when:  When                    arrived_at, left_at, seen_through, settled_through,
                                 wake_at, absorbed
  present                        a property: when.left_at is None
```

That is the opening split made into types instead of into comments. `who` holds
everything a mind wrote, and the engine never reads any of it to decide
anything — it hands it to a mind and takes back what comes. `where` and `when`
are the engine's entirely and mean nothing on their own. Crossing the line
means typing `.who.`.

This is Concordia's answer scaled down. An `EntityAgent` there is a name and a
set of components, and each component holds the state it reads and serialises
itself (`concordia/agents/entity_agent.py`); nothing is a field on the entity.

Two consequences worth naming:

- **`present` is derived**, not stored beside `left_at`, so the two cannot come
  apart.
- **`from_dict` is three round-trips**, each owned by the part it belongs to,
  so a field added to one of them cannot be silently dropped on the next save.

`Place` is prose and nothing else — an id, a name, a description. Which places
touch which is a fact about the town, not about a place, and lives in
`World.map` as one entry per way. A one-way path is not writable. `road`
lives there too: there is one edge to this world, and it belongs to the world
rather than to whichever place sits on it.

Every field on every one of these is read by something. A field nobody reads is
storage pretending to be design.

## Minds

[`backends/__init__.py`](../src/elsewhere/backends/__init__.py) defines the
`Backend` protocol (one method, `complete(call, settings) -> str`) and a small registry. The engine never imports a specific backend;
`agents.py` always goes through `get_backend(settings.backend)`.

- [`backends/open_source/`](../src/elsewhere/backends/open_source/) — open-source models
  you run yourself.
  - [`mlx.py`](../src/elsewhere/backends/open_source/mlx.py) — `MLXBackend`: the
    model runs in this process on Apple silicon through `mlx-lm`, with the schema
    compiled by `llguidance` into a per-token mask; embeddings through
    `mlx-embeddings`. Weights come from the Hugging Face hub and are cached. An
    optional extra, `pip install -e ".[mlx]"`, imported only when first called.
  - [`openai_compatible.py`](../src/elsewhere/backends/open_source/openai_compatible.py) —
    `OpenAICompatibleBackend` (any `/v1` server — LM Studio, llama-server, vLLM —
    written against `urllib`, so it needs no dependency; tries
    `response_format: json_schema` and falls back to plain `json_object`).
- [`backends/closed_source/`](../src/elsewhere/backends/closed_source/) — closed-source models
  somebody else runs, reached with a key.
  - [`claude.py`](../src/elsewhere/backends/closed_source/claude.py) — Claude,
    imported lazily. The schema is passed as a forced tool call.
  - [`gpt.py`](../src/elsewhere/backends/closed_source/gpt.py) and
    [`gemini.py`](../src/elsewhere/backends/closed_source/gemini.py) —
    `GPTBackend` and `GeminiBackend`: the same `/v1` dialect as
    `OpenAICompatibleBackend`, with each service's address and key filled in.
- [`backends/stub.py`](../src/elsewhere/backends/stub.py) — answers every call
  with a fixed or scripted answer. This is what `make test` runs against; no
  model, no key, no latency.

An embedder is the one thing a backend is asked for that is not an answer
(`backends.embed`), and nothing requires it: an embedder that is missing or
down gives back no vector, and recollection falls back on BM25.

[`configuration.py`](../src/elsewhere/configuration.py) decides which backend
and model answer which of the five call sites, written into each world as
`configuration.json`
so it is editable rather than buried in code. The intent: the cheap, frequent
decisions (`act`) can run on something small and local, while the ones that
need judgement (`speak`, `settle`) can be pointed at something larger. The
embedder is configured beside them as `embed`. The file is the only source:
nothing in the environment overrides it. Keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
`ELSEWHERE_OPENAI_KEY`) are the exception,
since they decide whether a mind can be reached rather than which one it is.
Tests write a stub configuration into their own temporary world.

## Storage

```
<world>/
  world.json             clock, places, the map, counters, the town's and the road's timers
  configuration.json     which mind answers which call site; the only place that says
  beings/<id>.json       one being, as who / where / when, notebook included
  chronicle.jsonl        append-only history
  notes/<id>.jsonl       every note one person has made, append-only
  pages/<id>.jsonl       every page one person has written, append-only
  transcript/<day>.jsonl every question put to a mind that day, and its answer
  tick.lock              a directory, held while a tick is running
```

[`world/store.py`](../src/elsewhere/world/store.py) is the only module that
touches disk. `save`/`load` round-trip a `World`; `TickLock` is a
directory-based lock (`os.mkdir` as the atomic primitive) so `cron`/`launchd`
firing twice cannot run two ticks at once — a lock older than 15 minutes is
taken over rather than left to stall the world forever.

`SCHEMA_VERSION` is written into every world, and a world written under any
other version is refused rather than converted. A bump means a world that
*worked* differently, and filling in the difference would silently invent
history nobody lived.

## Determinism

There is no stored random seed, because there is no dice roll in the engine to
seed: every judgement is a mind's. What the engine keeps
instead is the transcript — every prompt and every answer, whether it
validated, how long it took — which is a durable record of why the town did
what it did, not a mechanism for replaying it. `make test`'s reproducibility
comes from [`backends/stub.py`](../src/elsewhere/backends/stub.py) instead.

## What is not here yet

Tracked in [`ROADMAP.md`](ROADMAP.md), in the order it would be built: letting
you be one of the beings, admitting a memory from outside the world, making
things, long-term memory in the weights, somebody coming back, structure above
the individual, and taking leave of a world that has ended. Action resolution,
above, is the other known gap.
