# How Elsewhere is put together

Two rules. Everything below follows from them.

```
The engine   decides what can be reached      — never what anything meant
A mind       decides what anything meant      — never what can be reached
```

A model asked "do you still remember the flood?" with the flood sitting in its
context will always say yes. So the engine never asks that question. It
decides, on its own, what goes in front of a mind at all; whatever a mind is
shown, it is free to make anything of.

```
Nothing on the engine's side is an algorithm invented here
```

What is left on the engine's side is either a published algorithm used at its
own parameters — ACT-R's declarative memory, in
[`retrieval.py`](../src/elsewhere/retrieval.py) — or it is not an algorithm at
all: reading a timer, checking a map, counting who is present. There is no
constant anywhere that says how long a memory lasts, how much quiet a town
gets, how often the road is worth asking, or when a day ends. Each of those is
either the equation's own answer or a question put to a mind.

Nothing continuous is cut into buckets on the way past, either. A memory has
no weight, a belief has no confidence, a feeling has no vocabulary, and the
clock has no step.

## The two records

```
World.chronicle            one append-only ledger    "The old market burned down."
World.memories(person_id)  one store per person      {"account": "...", "means": "...", ...}
```

[`world/chronicle.py`](../src/elsewhere/world/chronicle.py) holds the
`Chronicle`: one line of JSON per `Event`, appended, never revised, and the
only thing in Elsewhere that claims to be true.

[`world/memories.py`](../src/elsewhere/world/memories.py) holds the `Memory`:
one person's own account of what an event left in them, or a thought they
arrived at themselves. A memory is written by a mind and rewritten by a mind
(`Memory.rewrite`, called from `recall`). The engine records when it came up
and reads that back in [`retrieval.py`](../src/elsewhere/retrieval.py) to
decide whether it can be reached. It never edits the words.

Nobody reads another person's memories. To learn something, a person has to be
told, and what they get is a new memory of *being told*, not a copy of the
speaker's.

## Modules

| file | what it owns |
| --- | --- |
| [`world/chronicle.py`](../src/elsewhere/world/chronicle.py) | `Event`, `Chronicle` — the one thing that is true |
| [`world/entities.py`](../src/elsewhere/world/entities.py) | `Being` = `Who` + `Where` + `When`; `Place` (prose) and `Map` (the town's geography); `Regard`, `Belief` |
| [`world/memories.py`](../src/elsewhere/world/memories.py) | `Memory`, `MemoryStore` |
| [`world/store.py`](../src/elsewhere/world/store.py) | `World`, save/load, `tick_lock`, the calendar |
| [`schemas.py`](../src/elsewhere/schemas.py) | the seven answer shapes, used as a decoding grammar and as an inbound check |
| [`prompts.py`](../src/elsewhere/prompts.py) | the system/user prompt text for each call site |
| [`retrieval.py`](../src/elsewhere/retrieval.py) | ACT-R declarative memory — the one judgement the engine keeps |
| [`schedule.py`](../src/elsewhere/schedule.py) | one timer per entity, set by the entity, and the interrupt over it |
| [`agents.py`](../src/elsewhere/agents.py) | the seven call sites, and the road |
| [`tick.py`](../src/elsewhere/tick.py) | one step, in order; `owed_hours`/`settle_clock` for `continue` |
| [`config.py`](../src/elsewhere/config.py) | which backend and model answers which call site |
| [`backends/`](../src/elsewhere/backends/) | `Call`/`Settings`/`Transcript`/`ask()`, one module per way of reaching a mind |
| [`seed.py`](../src/elsewhere/seed.py) | the small beginning: three people, one town, a flood |
| [`cli.py`](../src/elsewhere/cli.py) | everything a resident can do from a terminal |

## The seven questions

Every place a mind is consulted goes through
[`agents.py`](../src/elsewhere/agents.py) and follows the same shape: gather
what this person could possibly draw on, ask, check the answer is usable, and
write the consequence into the ledger. None of these functions decide anything
themselves — if a mind declines to answer, or answers with nothing usable, the
person simply had nothing, which is allowed.

| call | asked | schema |
| --- | --- | --- |
| `perceive` | something happened in front of you — what, if anything, stays? | `PERCEIVE` |
| `act` | you are standing here — what do you do, for how long, and does anything reach you while you do it? | `ACT` |
| `speak` | you are talking to this person — what do you say, and what do you draw on? | `SPEAK` |
| `recall` | you are bringing this up years later — how does it come back now? | `RECALL` |
| `reflect` | you have stopped — what did the day leave you holding, and who is on your mind? | `REFLECT` |
| `direct` | does anything happen to the town — and when should you be asked again? | `DIRECT` |
| `arrive` | does anybody come up the road, who would they be, and when should you be asked again? | `ARRIVE` |

The schema is the contract. `schemas.grammar(name)` marks every field required
and is handed to the backend as a decoding constraint (Ollama's `format`,
vLLM's `guided_json`), so the shortest possible non-answer — an empty string, a
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
`speak_grammar` restricts `about` to the numbered things this person can bring
to mind; `direct_grammar` restricts `where`/`who` to real places and present
people; `reflect_grammar` restricts `belief_from`, `belief_again` and
`about_someone` to today's memories, the beliefs already held, and people who
exist. A model cannot answer with a place that is not adjacent, a person who
is not in the room, or a belief nobody holds.

[`backends.ask()`](../src/elsewhere/backends/__init__.py) puts a `Call` to a
backend: it tries once, and if the answer does not validate, hands the model
its own complaint and tries once more before giving up and returning `None`.
Every attempt — prompt, raw answer, whether it validated, how long it took — is
appended to a `Transcript`.

## The memory model

[`retrieval.py`](../src/elsewhere/retrieval.py) is the one place where the
engine, not a mind, decides something about a person's inner life: how near a
memory is to coming to mind. It is ACT-R's declarative memory.

```
A_i  = B_i + SUM_k W_k · S_ki                activation of a memory
B_i  = ln SUM_j (t − t_j) ** −d              how often, and how lately
S_ki = S · how near the cue is to it         what this moment points at
```

`d` = 0.5 and `S` = 2.0 are ACT-R's published defaults (`:bll`, `:mas`), from
Anderson, Bothell, Byrne, Douglass, Lebiere & Qin (2004); the base-level term
is Anderson & Schooler (1991). `W` is the attentional weight, which sums to one
over the sources of the moment, and the moment here is one thing.

One deviation, named rather than hidden: symbolic ACT-R sets `S_ki = S −
ln(fan_k)`, the fan being how many chunks a cue term appears in. Elsewhere's
memories have no slots and no terms, only sentences, so the strength is read
off a sentence embedder. That is the standard substitution when ACT-R is run
over distributed representations, and it is the only line in the file that is
not the published equation.

**There is no retrieval threshold, and so no number in the file that had to be
picked.** ACT-R's `:rt` is fitted per task and its default means nothing at
this world's timescale — it was written for a laboratory where the unit is a
second, not a town where it is a day. Retrieval is instead what ACT-R's is: a
*request*, answered with the most active memories and not with all of them.
What does not come back is forgotten for the purposes of the next thought,
whether or not it is still on disk.

Four things follow:

- **A memory carries no importance number.** What a memory is worth is how
  often anybody has had cause to think of it, which is the base-level term.
  `speak` and `recall` are the only call sites that rehearse anything, so what
  keeps a life in reach is that somebody brought it up.
- **A cue is not a second mechanism.** A moment that points straight at an old
  memory raises it through the spreading-activation term of the same equation,
  so something long out of reach can come back because of where somebody is
  standing — with no special case and no similarity threshold.
- **A belief is a chunk.** `Belief` keeps its occasions the way a memory does
  and is ranked by the same `base_level`, so which beliefs a person has in
  front of them is the retrieval layer's answer. `on_faith` — a belief held
  with nothing left to point at for why — asks whether the memories it grew out
  of come back when the person thinks about the belief itself.
- **A reflection is a memory.** `reflect`'s thought is written into the memory
  store carrying `Memory.origin`, the ids of the memories it was a thought
  about, so it can be brought to mind later, worn down by not being brought to
  mind, and said out loud. This is `generative_agents`' reflection, whose
  insights go back into associative memory with their evidence
  (`cognitive_modules/reflect.py`), rather than onto the persona.

**Every retrieval cue is text a mind wrote**, never a string the engine glued
together: `perceive` cues on the event's account, `act` on the room plus this
person's own thought and wants, `speak` on the listener and the speaker's own
account of them, `reflect` on today's own memories. Concordia's
`AllSimilarMemories` does something strictly better — an `open_question` that
summarises the situation, then a retrieval against the answer — at the cost of
one extra model call per retrieval, which is a doubling this engine has not
taken.

Whether two beliefs are the same belief said twice is the mind's: `REFLECT`
has a `belief_again` field, narrowed by grammar to the beliefs this person
already holds, because it is a question about meaning and no amount of word
overlap settles it.

## Scarcity, and who supplies it

A model has no sense of scarcity: asked "does something marking happen to this
person," or "would she leave," or "does anyone come up the road," it will
eventually say yes to all of them, because nothing in its context tells it
these things ought to be rare. What supplies the scarcity is that **the thing
being asked sets its own interval, in the same answer**:

- `ACT` carries `for_hours`, `settling` and `absorbed`. A person says how long
  they will be at what they are doing, whether this is them stopping for the
  day, and whether anything short of the roof coming off gets their attention
  while they do it.
- `DIRECT` and `ARRIVE` carry `ask_again_in_hours`. The town says how long a
  quiet stretch it is giving itself; the road says how long before it is worth
  asking again. Both are asked for whether or not anything happened, so a town
  that has just had a fire can take its fortnight.

Two numbers are the engine's, and neither is a rate: `TOWN_FLOOR` (2) and
`TOWN_CEILING` (8) — below two there is nobody to talk to, above eight it stops
being a town where everybody knows everybody. That is the author's design of
what kind of world this is.

Three more are budgets: `retrieval.CONTEXT_MEMORIES` (6) is how many memories a
prompt can hold, `agents.MAX_BELIEFS` (6) how many beliefs a file keeps, and
`tick.TURNS` (4) the most that may be said in one exchange.

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

1. **`schedule.advance`** moves the clock to the next thing due. Anyone with no
   timer of their own is woken at that same moment: a mind that gave no usable
   duration said nothing, so the engine supplies nothing on its behalf beyond
   letting it round again. If *nothing* anywhere has a timer, the step returns
   `idle` and the clock does not move.
2. **Whatever happens to the town rather than in it** — `direct` if the town's
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
   of them has nothing to say. Each turn is its own event, so what somebody
   answers is a reply to the memory `perceive` just wrote them of the line
   before: they can answer what they thought they heard.
6. **Whoever said they were stopping** goes over the day they are stopping at
   the end of. Their day is whatever has happened to them since they last did
   this, and it includes what they were doing as well as what was done to them
   (`Where.lately`).

`elsewhere tick -n` calls this directly. `elsewhere continue` is the scheduled
entry point, and the promise it keeps is that a day here is a day there:
`tick.owed_hours` works out how much world time the wall clock says has gone
unlived, and the loop pays it off in whatever steps the people in the world
asked for. `--max` bounds model calls, not time. `tick.settle_clock` decides
whether the rest of a longer backlog is carried forward or slept through; past
`--max` it is not, because carrying it forward would mean a laptop asleep for a
week wakes up and spends an hour catching up.

## Consequence

The engine does not resolve an action into an outcome. What somebody is doing
goes into `Where.lately` in their own words, and `direct` is shown it — so the
town can see that somebody has been on a roof for a fortnight and say what came
of it. That is the whole of how anything anybody does changes the world.

Full action resolution, which is Concordia's Game Master
(`components/game_master/event_resolution.py`), is not in this engine.

## The road

Leaving and arriving go through the same engine-decides/mind-decides split as
everything else, but the facts checked are about the map, not about wants:

- `agents.may_leave(world, person)` — does the road go out from where they are
  standing (`world.map.road_out`), and would there still be a town behind them
  (`TOWN_FLOOR`). Only if both hold does `leave` enter the grammar `act` is
  asked under. Whether to take it, and at what hour, is theirs.
- `agents.may_arrive(world)` — is the town at or above `TOWN_CEILING`, in which
  case there is nowhere to put anybody and the road is never asked; otherwise,
  has the road's own timer come round. `short_of_somebody` is a fact shown *to*
  the road rather than the engine's reason for asking it.

Whoever leaves is recorded as a `departure` event and perceived by everyone
still present, then marked by `When.left_at` and never asked anything again.
What they had, and every note anyone wrote about them, stays exactly as it was
the day they went — `elsewhere person <name>` reads them frozen, on their own
stopped clock. Whoever arrives is built from the road's own `arrive` answer,
dropped at the place the road comes in with no home of their own, and lives the
day they arrived.

## What a being is

```
Being
  id, name, mind                 the handle, and whose answers these are
  who:   Who                     card, manner, thought, wants, beliefs, regards
  where: Where                   place, home, lately   (doing = lately[-1])
  when:  When                    arrived_at, left_at, reflected_at,
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
`World.map` as one entry per way. A one-way path is not writable. `road_out`
lives there too: there is one edge to this world, and it belongs to the world
rather than to whichever place sits on it.

Every field on every one of these is read by something. A field nobody reads is
storage pretending to be design.

## Minds

[`backends/__init__.py`](../src/elsewhere/backends/__init__.py) defines the
`Backend` protocol (one method, `complete(call, model, temperature, extra) ->
str`) and a small registry. The engine never imports a specific backend;
`agents.py` always goes through `get_backend(settings.backend)`.

- [`backends/openai_compat.py`](../src/elsewhere/backends/openai_compat.py) —
  `OllamaBackend` (native `/api/chat`, schema as `format`), `OpenAICompatBackend`
  (any `/v1` server — LM Studio, llama-server — tries `response_format:
  json_schema` and falls back to plain `json_object`), `VLLMBackend`
  (`guided_json`). Written against `urllib`, so reaching a local or
  self-hosted model needs no dependency.
- [`backends/anthropic_backend.py`](../src/elsewhere/backends/anthropic_backend.py)
  — Claude, imported lazily. The schema is passed as a forced tool call.
- [`backends/stub.py`](../src/elsewhere/backends/stub.py) — answers every call
  with a fixed or scripted answer. This is what `make test` runs against; no
  model, no key, no latency.

An `Embedder` is a second, optional protocol on the same backends. It is the
only thing a model is asked for that is not an answer, and nothing requires it:
an embedder that is missing or down gives back an empty vector, and a memory is
then ranked on its history alone.

[`config.py`](../src/elsewhere/config.py) decides which backend and model
answer which of the seven call sites, written into each world as `config.json`
so it is editable rather than buried in code. The intent: the cheap, frequent
decisions (`act`) can run on something small and local, while the ones that
need judgement (`perceive`, `speak`, `reflect`) can be pointed at something
larger. `ELSEWHERE_BACKEND=stub` overrides every call site at once.

## Storage

```
<world>/
  world.json             clock, places, the map, counters, the town's and the road's timers
  beings/<id>.json       one being, as who / where / when
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

`SCHEMA_VERSION` refuses to read a world written by an older Elsewhere, and
there is no conversion. A bump means a world that *worked* differently, and
filling in the difference would silently invent history nobody lived.

## Determinism

There is no stored random seed, because there is no dice roll in the engine to
seed: every judgement is a mind's, and retrieval is a deterministic ranking
rather than a sample from ACT-R's noise distribution. What the engine keeps
instead is the transcript — every prompt and every answer, whether it
validated, how long it took — which is a durable record of why the town did
what it did, not a mechanism for replaying it. `make test`'s reproducibility
comes from [`backends/stub.py`](../src/elsewhere/backends/stub.py) instead.

## What is not here yet

Tracked in [`ROADMAP.md`](ROADMAP.md): letting a person be played rather than
modelled (P2), making things (P5), any structure above the individual (P6),
admitting a memory from outside the world, and ending a world at all. Action
resolution, above, is the other known gap.
