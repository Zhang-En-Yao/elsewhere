# How Elsewhere is put together

Two rules. Everything below follows from them.

```
The engine   decides what can be reached      — never what anything meant
A mind       decides what anything meant      — never what can be reached
```

Both rules are made into structure. The engine is `application/` (what can be
reached, the timers, every action) behind an MCP server (`server/`) that holds
every action as a tool and is the only thing that changes the world. A mind is
reached only through the harness (`harness/`), which decides what it is shown,
keeps what it keeps, and turns its answer into one call on that server. Neither
side can do the other's job, because neither has the other's code.

A model asked "do you still remember the flood?" with the flood sitting in its
context will always say yes. So the engine never asks that question. It
decides what goes in front of a mind at all — the self-schema that person
carries, their own episodes from today, what has just reached them, and as
much of one old engram as time has left — and whatever a mind is shown, it is
free to make anything of.

```
Nothing on the engine's side is an algorithm
```

What is left on the engine's side is reading a timer, checking a map, counting
who is present, filtering the chronicle for what reached somebody, one search
run by libraries — BM25 in SQLite's FTS5 and cosine distance in sqlite-vec,
fused by Reciprocal Rank Fusion — to say which engram a moment points at, and
one published curve — the power law of forgetting — to say how much of it can
still be reached. That curve is about reach, not meaning: which pieces of a
memory are the ones that last was decided by a mind, the night it was laid
down. There is no equation anywhere that says what a being remembers, what
anything meant to them, how much quiet a town gets, how often the road is
worth asking, or when a day ends. Each of those is a question put to a mind.

Nothing continuous is cut into buckets on the way past, either. The only
numbers a memory carries are the weights a mind gave its gists; a belief has no
confidence, a feeling has no vocabulary, and the clock has no step.

## The records

```
World.chronicle               one append-only ledger             "The old market burned down."
World.episodes(being_id)      every episode they ever encoded    what a moment was to them, as it happened
World.engrams(being_id)       every engram sleep laid down       what a day hangs by, as gists
World.self_schemas(being_id)  every self-schema they ever held   who they took themselves to be, each night
Being.identity.self_schema         the newest of those                who they take themselves to be now
```

`World.chronicle` is one line of JSON per `Event`
([`domain/chronicle.py`](../src/elsewhere/domain/chronicle.py)), appended,
never revised, and the only thing in Elsewhere that claims to be true. Every event says who it
`informed`, and where each of them stood (`data["perspectives"]`).

The others are the subjective record, and like the chronicle nothing in
them is ever revised or thrown away:

- `World.episodes(being_id)` holds every `Episode`
  ([`domain/memory.py`](../src/elsewhere/domain/memory.py)): what somebody
  encoded of a moment, in their own words, written in the `encoded` field of
  the `act` or `speak` answer they gave right after it reached them, with the
  ids of the events it was of.
- `World.engrams(being_id)` holds every `Engram`: what one night's
  `consolidate` laid down of the day — a few `Gist`s, each a short
  proposition and the weight the mind gave it — with an embedding of them.
- `World.self_schemas(being_id)` holds every `SelfSchema` a person has held,
  one per `consolidate`, starting from the one `seed` wrote them with.
- `Identity.self_schema` ([`domain/entities.py`](../src/elsewhere/domain/entities.py))
  is the newest: who one person takes themselves to be from one day to the
  next — how they talk, what they are after, what they take to be true, how
  they see the people they know. `Identity.biography` beside it is where they came
  from, written once and never revised.

Only minds write any of it. What somebody lost is lost to them and not to the
world.

Nobody reads another person's self-schema. To learn something, a person has to
be told, and what they get is the event of being told — which they then
encode, and sleep on, or don't.

## Layers

```
domain/        what the world is made of                   imports nothing outside itself
application/   the engine: reachability, schedule, actions imports domain
server/        every action, as a tool on one MCP server   imports application, domain
adapters/      disk, the backends, retrieval               imports domain
harness/       the minds, and their answers made calls     imports all of the above
interface/     the command line, the window, the seed      imports anything
```

This is the dependency rule of clean architecture, kept to as few layers as
the two rules above need and no more abstraction than it takes: there are two
`Protocol`s in the whole engine, `domain.world.Records` (so the domain never
touches disk; `adapters.storage.Archive` is the one implementation) and
`adapters.backends.Backend` (one per way of reaching a model).
[`tests/test_layers.py`](../tests/test_layers.py) reads every import and fails
on one that reaches outward.

## Modules

| file | what it owns |
| --- | --- |
| [`domain/world.py`](../src/elsewhere/domain/world.py) | `World`, and the `Records` it keeps its logs in |
| [`domain/chronicle.py`](../src/elsewhere/domain/chronicle.py) | `Event`, `Category` — the one thing that is true |
| [`domain/entities.py`](../src/elsewhere/domain/entities.py) | `Being` = `Identity` + `Location` + `Activity` + `Clock`; `Place` (prose) and `Map` (the town's geography) |
| [`domain/memory.py`](../src/elsewhere/domain/memory.py) | `Episode`, `Engram` and its `Gist`s, `SelfSchema` and its `Impression`s — what each person holds |
| [`domain/perspective.py`](../src/elsewhere/domain/perspective.py) | `of`: where a being stood when an event reached them |
| [`domain/calendar.py`](../src/elsewhere/domain/calendar.py) | the clock read as days, dates and seasons |
| [`domain/geography.py`](../src/elsewhere/domain/geography.py) | where each place lies, laid out once from the ways when the world is made |
| [`application/reachability.py`](../src/elsewhere/application/reachability.py) | what can be reached: companions, destinations, `may_leave`, `may_admit` |
| [`application/schedule.py`](../src/elsewhere/application/schedule.py) | one timer per being and one for the world, and the interrupt over them |
| [`application/actions.py`](../src/elsewhere/application/actions.py) | every action, each checked before it is done; `Refused` |
| [`server/`](../src/elsewhere/server/__init__.py) | `Tool`, and `build(world)`: the MCP server with every action on it |
| [`harness/memory.py`](../src/elsewhere/harness/memory.py) | `percepts`/`short_term`/`retrieve`, and `encode`/`store` to write what a mind kept |
| [`harness/schemas.py`](../src/elsewhere/harness/schemas.py) | the four answer shapes, used as a decoding grammar and as an inbound check; `SELF_SCHEMA_CHARACTERS` |
| [`harness/prompts.py`](../src/elsewhere/harness/prompts.py) | the system/user prompt text for each call site |
| [`harness/being.py`](../src/elsewhere/harness/being.py) | the being agent: `act`, `speak`, `consolidate` |
| [`harness/world.py`](../src/elsewhere/harness/world.py) | the world agent: `stir` |
| [`harness/decision.py`](../src/elsewhere/harness/decision.py) | `Decision`: what a turn comes to, one tool call and a timer |
| [`harness/tick.py`](../src/elsewhere/harness/tick.py) | one step, in order, over an MCP session; `backlog`/`reconcile` for `continue` |
| [`harness/configuration.py`](../src/elsewhere/harness/configuration.py) | which backend and model answers which call site |
| [`adapters/storage.py`](../src/elsewhere/adapters/storage.py) | the world on disk: `Archive`, save/load, `Lock` |
| [`adapters/retrieval.py`](../src/elsewhere/adapters/retrieval.py) | which engram a moment brings back (BM25 + embeddings, fused by RRF), and how much of it is left (the power law of forgetting) |
| [`adapters/backends/`](../src/elsewhere/adapters/backends/) | `Call`/`Settings`/`Transcript`/`ask()`, one module per way of reaching a mind |
| [`interface/seed.py`](../src/elsewhere/interface/seed.py) | the small beginning: three people, one town, a flood |
| [`interface/cli.py`](../src/elsewhere/interface/cli.py) | everything a resident can do from a terminal |
| [`interface/tui/`](../src/elsewhere/interface/tui/) | the same, in a window that only reads: `views.py` decides what to show, `screen.py` where to put it, `cartography.py` draws `Map.positions` in characters (Bresenham lines) |

## Two agents

A being and the world are asked different questions by different modules, and
nothing is shared between them but the server they both call.

- **A being** ([`harness/being.py`](../src/elsewhere/harness/being.py)) is one
  person's mind. It is shown only what reached them, from where they stood,
  their own episodes, what comes back of their engrams, and their own
  self-schema; it encodes episodes, and its sleep lays down engrams and
  rewrites the self-schema.
- **The world** ([`harness/world.py`](../src/elsewhere/harness/world.py)) is
  the objective world: its weather, its accidents and the one road into it. It
  is shown what anyone could see — where people are, which places are beside
  which, what they have been doing, who has gone, the recent record — and
  never inside anyone. It has no memory of its own, and one timer. It never
  acts for a being.

What were the town and the road are one world agent: whether something
happens to the town and whether somebody comes up the road are the same
question about the same outside, and asking it twice let a town have its fire
and its stranger in one step.

## The four questions

Every place a mind is consulted follows the same shape: gather what this mind
could possibly draw on, ask, check the answer is usable, turn it into a tool
call, and make the call. None of these functions decide anything themselves —
if a mind declines to answer, or answers with nothing usable, it simply had
nothing, which is allowed.

| agent | call | asked | schema | comes to |
| --- | --- | --- | --- | --- |
| being | `act` | this just reached you — what do you encode of it? You are standing here — what do you do, for how long, and does anything reach you while you do it? | `ACT` | `stay`, `move`, `talk` or `leave`, then `wait` |
| being | `speak` | this was just said — what do you encode of it? You are talking to this person — what do you say? | `SPEAK` | `say` |
| being | `consolidate` | not a question put to them — they are asleep — but to what their sleep does: here are today's episodes; what is laid down, and who do they take themselves to be now? | `CONSOLIDATE` | engrams and a self-schema (memory: no call) |
| world | `stir` | does anything happen to the town, or does anybody come up the road — and when should you be asked again? | `STIR` | `occur`, `admit` or nothing, then `wait` |

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
`leave` only where `reachability.may_leave` says the road goes out from here;
`stir_grammar` restricts `where`/`who` to real places and present people, and
offers `admit` only where there is a road. A model cannot answer with a place
that is not adjacent or a person who is not in the room. The one limit JSON
Schema cannot say — `SELF_SCHEMA_CHARACTERS`, counted across every field of
the self-schema together — is checked on the way in, and a self-schema too
long is handed back to be cut like any other unusable answer.

[`backends.ask()`](../src/elsewhere/adapters/backends/__init__.py) puts a `Call` to a
backend: it tries once, and if the answer does not pass the check the harness
handed it, hands the model its own complaint and tries once more before giving
up and returning `None`. Every attempt — prompt, raw answer, whether it
validated, how long it took — is appended to a `Transcript`.

## From an answer to a tool call

An answer names a tool in its `action` field — `move`, `talk`, `leave` for a
being, `occur`, `admit` for the world — or leaves it empty. The harness turns
it into the call: names become ids (`"Beth El"` becomes `{"to": "bethel"}`), an
empty action becomes `stay` with what they said they were `doing`, and
`duration` becomes a `wait`. What the grammar did not offer is not
called. The call goes over an in-process MCP session (`mcp.Client` on
`server.build(world)`, a fresh one each step) to the server, which checks
again what can be reached and refuses what cannot be — so a lenient backend,
a bug in the harness, and the world are all held to the same engine.

The server is the official MCP Python SDK's `MCPServer`, so the same server
could be put on stdio for any MCP client; nothing in Elsewhere does that yet.

Memory never goes through the server. An episode, an engram, a self-schema and
what somebody has perceived are what a mind holds rather than what the world
does, and the harness
writes them itself ([`harness/memory.py`](../src/elsewhere/harness/memory.py)).

## The world throws events; beings decide

The world never calls a being's tools. When the water comes into the garden,
`stir` comes to `occur`: the event is recorded, reaches whoever it reaches,
and interrupts them (`schedule.interrupt`), so they are due in the same step — after
the world, before anyone moves. Each of them is then asked `act` with the
event in front of them, and what they do about it — go up to Beth El, stay
and watch the water, go and find somebody — is their answer, turned into
their own call. That is the first rule kept in the shape of the code: the
world decides what happened and what it reached, and never what anybody does
about it.

The harness names every method itself. No model is given the server's tool
list or descriptions to choose from; a mind answers in its own schema, the
grammar offers only what can be reached, and the harness maps the answer to
the method (`action: "move"` → `tools/call move`). Nothing outside the world
decides a turn: there is no command that calls a tool for anybody.

## The memory model

There is no memory model in the engine, and what memory management there is
belongs to the harness ([`harness/memory.py`](../src/elsewhere/harness/memory.py)).
There are three kinds of writing, two spans, a filter, a search somebody else
wrote, and a published forgetting curve. It is laid out the way the
multi-store model lays out a mind (Atkinson & Shiffrin 1968), with sleep doing
the moving from one store to the next, the way complementary learning systems
theory has it (McClelland, McNaughton & O'Reilly 1995): episodes written down
fast as they happen, and folded overnight into what lasts.

```
sensory      memory.percepts      what reached them since they last looked up, shown once, at most SENSORY_SPAN
short-term   memory.short_term    their own episodes since they last consolidated, at most SHORT_TERM_SPAN
long-term    Engram               gists laid down by consolidate, each weighted by the mind
self         Identity.self_schema      who they take themselves to be, rewritten each night, at most SELF_SCHEMA_CHARACTERS
retrieved    memory.retrieve      one engram the moment points at, with only the gists time has left
```

**The chronicle is shown once.** `percepts` is every event after
`Clock.perceived_through` whose `informed` includes this person, each with where
they stood, newest `SENSORY_SPAN` (12). It goes in front of the next `act` or
`speak` they are asked, and whatever the answer, `perceived_through` moves past
it: nobody is shown the same event twice. `perceived_through` is a position in
the chronicle rather than an hour, because a step can take no time and events
at the same hour can fall on either side of somebody looking up.

**What they encode of it is theirs.** The same answer carries `encoded`: the
fragment they keep, in their own voice, or nothing — most of what happens
sticks to nobody, and what nobody encoded is gone from them the moment they
looked away. An `Episode` is appended with the events it was of, which is how
`elsewhere event` can put every version of one event side by side. Encoding
costs no call of its own, because it rides on an answer that was being given
anyway; the price is that what happened is only encoded when they are next asked.

**The short-term store is their day.** `act` and `speak` are shown
`short_term` — the episodes they have encoded since they last consolidated —
and so is `consolidate`, which is shown nothing else of the day but what they
were doing (`Activity.doings`). The chronicle is never shown at night: sleep goes
over what they encoded, not over what happened, so what they got wrong in the
moment stays wrong.

**Sleep is not a question put to them.** `consolidate` is asked of their mind,
not of them: its prompt speaks about the person in the third person, as what
their sleep does with the day, and nothing it answers is shown to them as an
answer. Two things come of it, in one call:

- **Engrams.** For each thing from the day that will last, the broken-off
  pieces it will be remembered as — one to four gists, each a short
  proposition of who did what or what was where — each with a weight from 0
  to 1 for how much of the memory hangs on it, weighed by what matters to this
  person rather than by what was remarkable. An ordinary day lays down
  nothing. Gists rather than single words because people keep the gist of an
  experience long after its wording is gone (Brainerd & Reyna 1990,
  fuzzy-trace theory), and the gist is propositional — who, what, to what —
  not a bag of words (Kintsch & van Dijk 1978); a bare word drops the
  relations that made it a memory. Picking the pieces and weighing them is
  meaning, so it is the mind's; a summariser would only say what is central
  to the text, not what matters to the person who wrote it. The episodes are
  never searched again: from here on the day is only its gists.
- **The self-schema** (Markus 1977), rewritten whole: `idiolect` (Bloch 1948),
  how they talk; `traits` (Allport 1937), what they are like — the
  dispositions they act from, the slowest-changing line of the four; `concerns`
  (Klinger 1975), what they are after and have not got; `assumptions` (Janoff-Bulman 1992), what they take to be true;
  `impressions` (Asch 1946), how they see each person they know. This is
  MemGPT's core memory (Packer et al. 2023, "MemGPT: Towards LLMs as Operating
  Systems"): a fixed-size block of context the agent itself edits, where the
  size is the constraint and what survives it is the agent's decision; done
  once a night over the old one and the new episodes, it is the recursive
  summarisation of Wang et al. (2023). `SELF_SCHEMA_CHARACTERS` (4000), every
  field counted together, is the one number the world has about who somebody
  can be: a safety valve for a prompt that carries the whole self-schema on
  every call, and the pressure that makes the mind choose what to let go. `Identity.biography` — where they came from — is written once, by the
  seed or by `admit`, and never revised: it is what the self-schema drifts
  from, not part of it.

`consolidated_through` then moves past the day, the engrams are appended with
an embedding of their gists, and the self-schema is appended to its history.

**Something long gone comes back, in pieces.** Every `act`, `speak` and
`consolidate` asks `memory.retrieve` for one engram, cued by the moment: what
just reached them and where they are standing, for `act`; whom they are talking
to and what was just said, for `speak`; the day's own episodes and what they
were doing, for `consolidate`. Finding it is
[`adapters.retrieval.search`](../src/elsewhere/adapters/retrieval.py): two
rankings over the engrams' gists, each published and each run by a
library — Okapi BM25 (Robertson & Zaragoza 2009) in SQLite's FTS5 over
Porter-stemmed words (Porter 1980), which is good at names; and cosine
distance between sentence embeddings in sqlite-vec, which is good at a thing
said in other words — fused by Reciprocal Rank Fusion (Cormack, Clarke &
Buettcher 2009) at the paper's k = 60. It is a request answered with the best
there is, not a gate: there is no threshold, so on a day that points at nothing
much, what comes back is only loosely related, the way a mind wanders. Without
an embedder or without sqlite-vec, BM25 alone decides; an engram placed by one
embedder is never compared with another's vectors (`Engram.embedded_by`).

What comes back of it is `retrieval.fragment`: the power law of forgetting
(Wixted & Ebbesen 1991), at ACT-R's decay d = 0.5 (Anderson & Lebiere 1998).
After `t` days, `(1 + t)^-0.5` of its gists are left — all of them the first
night, half after three days, a quarter after a fortnight, a tenth after
three months, and never none — and the ones left are those the mind weighted
heaviest. They are shown as broken-off pieces with a rough age ("weeks ago"), never
the words the episode was in, which were never laid down. Making sense of
them again is the mind's (Bartlett 1932): what it makes up is what
misremembering is. The engram itself is never revised, and being recalled does
not strengthen it; rehearsal is a known omission, not an accident.

What follows:

- **A want, a belief, how one person sees another** are all lines on the
  self-schema. Whether today changed any of them is the night's call.
- **Telling changes what is told** without a call of its own: whoever speaks
  has their self-schema in front of them, what they said is an event, the
  listener encodes what they kept of it, and that night each of them sleeps on
  it.
- **A newcomer carries nothing.** `admit` sets `perceived_through` to the
  chronicle's length, so nothing from before they came reaches them, and their
  self-schema holds only how they talk.
- **Somebody who left is frozen.** Nothing informs someone who is not present,
  and nobody gone is asked anything.
- **A consolidate that gives nothing usable changes nothing** — the
  self-schema stays, nothing is laid down, and the day stays in the short-term
  store, to be slept on next time.

Long-term memory in the weights — a LoRA adapter per person, trained on their
own self-schemas and engrams — is the next layer down, and is in the roadmap.

## Scarcity, and who supplies it

A model has no sense of scarcity: asked "does something marking happen to this
person," or "would she leave," or "does anyone come up the road," it will
eventually say yes to all of them, because nothing in its context tells it
these things ought to be rare. What supplies the scarcity is that **the thing
being asked sets its own interval, in the same answer**:

- `ACT` and `STIR` both carry `duration`. `ACT` adds `sleep`. A
  person says how long they will be at what they are doing and whether this is
  them stopping for the day. If something reaches them sooner, they are asked
  sooner, and whether it is any business of theirs is their answer: a short
  `duration` and the same `doing` is going back to it.
- In `STIR`, the world says how long a quiet stretch it is giving the town,
  and is asked for it whether or not anything happened or anybody came, so a
  town that has just had a fire, or has just taken somebody in, can take its
  fortnight.

The engine puts no limit on the town's size: anybody may leave, even the last
of them, and the world is asked however many are already here.

Three more are budgets: `schemas.SELF_SCHEMA_CHARACTERS` (4000) is how much
of a self one person can carry, `memory.SENSORY_SPAN` and
`memory.SHORT_TERM_SPAN` (12 each) how much of a day is in front of them before
they sleep on it, and `tick.TURNS` (4) the most that may be said in one
exchange.

## One step

There is no step size. [`schedule.py`](../src/elsewhere/application/schedule.py) is a small
version of Concordia's interrupt-driven scheduler
(`concordia/components/game_master/interrupt_scheduling.py`): every entity in
the world carries exactly one timer and sets it itself, and the world advances
to whichever comes first. Two rules, and they are the whole module:

```
the world advances to the earliest timer, and never past it
anything that reaches somebody pulls their timer to now
```

The second is Concordia's interrupt, without its mask. Concordia's
`InterruptMask` lets an entity ignore events by tag prefix; here the engine
masks nothing, because whether something matters is a question of meaning and
so belongs to the mind. Being woken costs a call, and the mind can spend it
saying "not mine" by waiting again.

[`tick.py`](../src/elsewhere/harness/tick.py) lives one step, in a fixed order.
Each turn is made as calls on the server.

1. **`schedule.advance_to_next_due`** moves the clock to the next thing due. Anyone with no
   timer of their own is woken at that same moment: a mind that gave no usable
   duration said nothing, so the engine supplies nothing on its behalf beyond
   letting it round again. If *nothing* anywhere has a timer, the step returns
   `idle` and the clock does not move.
2. **The world**, if its timer has come round: `stir`, then `wait`, then
   `occur` or `admit` if that is what it came to. It runs before anyone
   decides what to do, so a happening can be reacted to in the same step and a
   newcomer lives the day they arrive.
3. **Whoever is due decides at once**, from wherever they are standing, before
   anyone moves, and each one's `wait` is called as they do. Not everybody — a person who said they would be asleep for
   eight hours is asleep for eight hours unless something woke them.
4. **The server settles what is physically so** — every call but `talk`:
   `move`, `stay`, and `leave`, after which they are no longer present for
   anything that follows.
5. **Conversation** — `talk`, among people still in the same place, at most
   one exchange per person per step. An exchange is turns, alternating, until
   one of them has nothing to say: `speak`, then `say`. Each turn is its own
   event, informing everyone there, so the next turn is a reply to it. Only the
   one spoken to is interrupted (by `talk`); whoever overheard it finds it in front
   of them the next time they look up.
6. **Whoever said they were stopping** sleeps on the day they are stopping at
   the end of, with `consolidate`. Their day is what they encoded of it in
   their own episodes since they last did this, and what they were doing
   (`Activity.doings`).

Setting a timer is always a `wait`, so the world's and every being's timer is
set by the server, from the number their own answer gave.

`elsewhere tick -n` calls this directly. `elsewhere continue` is the scheduled
entry point, and the promise it keeps is that a day here is a day there:
`tick.backlog` works out how much world time the wall clock says has gone
unlived, and the loop pays it off in whatever steps the people in the world
asked for. `--max` bounds model calls, not time. `tick.reconcile` decides
whether the rest of a longer backlog is carried forward or slept through; past
`--max` it is not, because carrying it forward would mean a laptop asleep for a
week wakes up and spends an hour catching up.

## Consequence

The engine does not resolve an action into an outcome. What somebody is doing
goes into `Activity.doings` in their own words (`stay`), and `stir` is shown it —
so the world can see that somebody has been on a roof for a fortnight and say
what came of it. That is the whole of how anything anybody does changes the world.

Full action resolution, which is Concordia's Game Master
(`components/game_master/event_resolution.py`), is not in this engine.

## The road

Leaving and arriving go through the same engine-decides/mind-decides split as
everything else, but the facts checked are about the map, not about wants:

- `reachability.may_leave(world, person)` — does the road go out from where they are
  standing (`world.map.road`). Only if it does does `leave` enter the
  grammar `act` is asked under, and the `leave` tool refuses anywhere else.
  Whether to take it, and at what hour, is theirs.
- `reachability.may_admit(world)` — is there a road at all. Only if there is does
  `admit` enter the grammar `stir` is asked under. Who has gone is a fact
  shown *to* the world rather than the engine's reason for asking it.

Whoever leaves is recorded as a `departure` event that informs everyone still
present, then marked by `Clock.left_at` and never asked anything again. Their
self-schema, and every impression anyone holds of them, stays exactly as it
was the day they went. Whoever arrives is built from the world's own `stir`
answer — a biography and an idiolect — dropped at the place the road comes in
with no home of their own and nothing else in their self-schema, and lives the
day they arrived.

## What a being is

```
Being
  id, name, mind                 the handle, and whose answers these are
  identity: Identity             biography, self_schema
  location: Location             place, home
  activity: Activity             doings, at most DOINGS_SPAN   (doing = doings[-1])
  clock:    Clock                arrived_at, left_at, perceived_through,
                                 consolidated_through, due_at
  present                        a property: clock.left_at is None
```

That is the opening split made into types instead of into comments. `identity` holds
everything a mind wrote, and the engine never reads any of it to decide
anything — it hands it to a mind and takes back what comes. `location`, `activity`
and `clock` are the engine's entirely and mean nothing on their own. Crossing the
line means typing `.identity.`. `doings` keeps `DOINGS_SPAN` entries, the span of
immediate memory (Miller 1956; Cowan 2001 puts it nearer four).

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
`positions` too: where each place lies, worked out once when the world is made
([`domain/geography.py`](../src/elsewhere/domain/geography.py), Kamada-Kawai
as networkx implements it — Kamada & Kawai 1989) so that the distance between two
places follows how many ways apart they are. The seed says only which places
touch; where they lie follows from that, and is kept so it never moves.

Every field on every one of these is read by something. A field nobody reads is
storage pretending to be design.

## Minds

[`backends/__init__.py`](../src/elsewhere/adapters/backends/__init__.py) defines the
`Backend` protocol (one method, `complete(call, settings) -> str`) and a small
registry. Nothing outside it imports a specific backend; the harness always
goes through `get_backend(settings.backend)`. Backends know nothing about call
sites: a `Call` carries its own grammar and `ask` is handed its own check.

- [`backends/mlx.py`](../src/elsewhere/adapters/backends/mlx.py) — `MLXBackend`: the
  model runs in this process on Apple silicon through `mlx-lm`, with the schema
  compiled by `llguidance` into a per-token mask; embeddings through
  `mlx-embeddings`. Weights come from the Hugging Face hub and are cached. An
  optional extra, `pip install -e ".[mlx]"`, imported only when first called.
- [`backends/openai_compatible.py`](../src/elsewhere/adapters/backends/openai_compatible.py) —
  `OpenAICompatibleBackend` (any `/v1` server — LM Studio, llama-server, vLLM —
  through the official `openai` client pointed at the configured endpoint; tries
  `response_format: json_schema` and falls back to plain `json_object`).
- [`backends/stub.py`](../src/elsewhere/adapters/backends/stub.py) — answers every call
  with a fixed or scripted answer. This is what `make test` runs against; no
  model, no key, no latency.

An embedder is the one thing a backend is asked for that is not an answer
(`backends.embed`), and nothing requires it: an embedder that is missing or
down gives back no vector, and retrieval falls back on BM25.

[`configuration.py`](../src/elsewhere/harness/configuration.py) decides which backend
and model answer which of the four call sites, read from the world's
`configuration.json` over the defaults (`elsewhere configure` writes it)
so it is editable rather than buried in code. The intent: the cheap, frequent
decisions (`act`) can run on something small and local, while the ones that
need judgement (`speak`, `consolidate`) can be pointed at something larger. The
embedder is configured beside them as `embed`. The file is the only source:
nothing in the environment overrides it. The key `ELSEWHERE_OPENAI_KEY` is the exception,
since it decides whether a mind can be reached rather than which one it is.
Tests write a stub configuration into their own temporary world.

## Storage

```
<world>/
  world.json             clock, places, the map, the world's timer
  configuration.json     (once configured) which mind answers which call site; the only place that says
  beings/<id>.json       one being, as who / where / when, self-schema included
  bookmark.json          how much of the chronicle you have read (the interface's, not the world's)
  chronicle.jsonl        append-only history
  episodes/<id>.jsonl    every episode one person has encoded, append-only
  engrams/<id>.jsonl     every engram one person's sleep has laid down, append-only
  self_schemas/<id>.jsonl every self-schema one person has held, append-only
  transcript/<day>.jsonl every question put to a mind that day, and its answer
  tick.lock              locked while a tick is running
```

[`adapters/storage.py`](../src/elsewhere/adapters/storage.py) is the only module that
touches disk. It is also what `domain.world.Records` is: `Archive` keeps the
chronicle, episodes, engrams and self-schemas as JSON lines (`Annals`) under the world's root. `save`/`load` round-trip a `World`; `Lock` is a
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
comes from [`backends/stub.py`](../src/elsewhere/adapters/backends/stub.py) instead.

## What is not here yet

Tracked in [`ROADMAP.md`](ROADMAP.md), in the order it would be built: letting
you be one of the beings, admitting a memory from outside the world, making
things, long-term memory in the weights, somebody coming back, structure above
the individual, and taking leave of a world that has ended. Action resolution,
above, is the other known gap.
