# v2: what is left

Where the rewrite stands, and what I would build next, in the order I would
build it. Written against the tree at the time of writing; the line references
are a starting point, not a promise.

## Where v2 stands

Landed:

- **P0** — the ledger, the retrieval policy, six call sites with schemas used
  both as a decoding grammar and as an inbound check; backends for Ollama,
  OpenAI-compatible servers, Claude, a stub, and replay-from-transcript; the
  world on disk as `chronicle.jsonl` + `people/*.json` + `memories/*.jsonl`
  under a directory lock.
- **P1** — the town moves on its own: simultaneous decisions, movement,
  one conversation per person per phase, `tick` / `continue` / `news`, and a
  launchd agent that keeps a day here to a day there.
- **P3** — things happen to the town (`direct`, once each morning), and
  telling changes what is told (`recall`, when a memory is brought up).
- **P4** — nights change what is held (`reflect`): a thought, at most one
  belief pointing at the memory it came from, and a want.
- **One clock** — `day` and `phase` are gone. The world keeps hours elapsed as
  a single float; days, seasons and a clock reading are worked out from it and
  never stored. A mind is told the time and whether the sun is up, and decides
  for itself what that is worth - naming a quarter of the day was the engine
  suggesting what everyone ought to be doing at it.
- **Nothing anybody here made up** — what is left on the engine's side is a
  published algorithm used as published, or it is not an algorithm. Retrieval
  is ACT-R's declarative memory at its own parameters, with no threshold and
  so no number that had to be picked; the five-word weight ladder, the floats
  under it, the belief confidence, the word-overlap belief matcher and its
  stop-word list, the bare cosine threshold for a cued return, and all seven
  scarcity constants are gone. Scheduling went with them: there is no step
  size, every entity keeps one timer and sets it itself, and a day ends when
  the person says it does. See [ARCHITECTURE.md](ARCHITECTURE.md).
- **The road** — people leave and are not got back, and a town is asked who
  comes up the road: about monthly while it is down somebody, about yearly
  when it is not. A seventh call site, `arrive`, and a sixth verb for `act`
  that only exists where the road does. The population moves both ways
  between a floor of two and a ceiling of eight.
- **A window** — `elsewhere watch`, which is the printed views with room to
  put two of them side by side: what is in reach above the line where reach
  ended, and what is not below it, dimmed. It reads the world off disk and
  picks up whatever moves it, its own `c` or the schedule behind it, and the
  only thing it writes is where you stopped reading.
  [`tui/views.py`](../src/elsewhere/tui/views.py) is a pure function of a
  loaded world and is tested as one; `screen.py` is the half a test cannot
  check.

There is no P2 in the history. It went P1 → P3/P4.

What the world therefore does today: it lives, it perceives, it talks, it
misremembers, it decides for itself whether anything happens, it changes what
people believe, and it survives losing somebody. What it does not do: admit
you, make anything, or grow anything larger than one person.

---

## P2 — You

**The gap.** `Being.mind` is typed `model | player`
([`entities.py`](../src/elsewhere/world/entities.py)), and nothing in the tree
reads `"player"`. [`tick.py`](../src/elsewhere/tick.py) selects
`p.present and p.mind == "model"`, so a person marked `player` is skipped
entirely: they do not act, are not spoken to, and leave no trace.

This is first because it is the thing the README is about. A world that is
worth returning to is not a world you read the logs of.

**What it means to build.** A player is a person who is asked the six questions
by a prompt on a terminal instead of by a model, and whose answers go through
exactly the same schemas. That constraint is the design: if `act` for a player
returns anything the engine would not have accepted from a model, the player
has become an administrator.

- A `play` command that lives one phase with you in it: you are shown only what
  your person could see, you pick from the same target enum the engine builds
  per person per phase, and when someone speaks to you, you answer in your own
  words.
- `perceive` for the player is the interesting question. Either you write your
  own memory, or — more in keeping with the rest — a model writes it *for* you,
  from what you did, and you find out later what you turned out to have kept.
  Worth trying both; the second is the one that makes forgetting apply to you.
- A player who is not present must be handled: `elsewhere tick` while you are
  away should let the world run without stalling on an answer that is not
  coming. `present=False` is already on `Being` and already respected.
- Regards: other beings forming an account of you is free once you are a
  `Being` like any other. Nothing to add.

**Acceptance.** Play three phases, leave for a week of wall clock, come back and
run `elsewhere person Eve` — she should have a note about you, and it should
be wrong in some specific way.

## P5 — Making things

**The gap.** `ACTIONS` is three verbs
([`schemas.py`](../src/elsewhere/schemas.py)) and the comment there already
names the plan: `make` and `tend` arrive with art. `Memory.source = "made"`
is reserved and unwritten.

**What it means to build.** An artifact is not a new kind of object so much as
an event with a maker and a durable presence in a place.

- Two new verbs in `ACTIONS`, and a seventh call site — `make` — asked only of
  someone who chose that action: what they are making, out of which memory, and
  what it is for. The memory it came from is the whole point; a painting of
  nothing is decoration.
- Artifacts live in the chronicle as events and in a place. Seeing one is a
  `perceive` call with a different `source`, which means somebody else's
  painting can lay down a memory in you — that is the ripple the README
  describes, and it needs no new machinery.
- `tend` is the cheap half: maintaining a thing keeps it in the world. Without
  it, everything made survives forever, which is the wrong failure.
- `elsewhere art` to see what has been made, and out of what.

**Watch out for.** A small model asked to write a poem will write a bad poem
every step. Making should be rare and expensive — gated on a memory that is
still in reach, and on nothing else. A cooldown was the obvious second gate
and it is the wrong kind of rule: it would have the engine decide whether
somebody makes something today, on the same clock for everyone. The engine
decides what can be reached; a mind decides what to do about it. Rarity has to
come from the fact that a memory still active enough to make something out of
is itself rare - and rare at a different moment for each being, because
activation is a fact about their own history of thinking about it and not a
weight the engine keeps.

## P6 — Above the individual

**The gap.** [`store.py`](../src/elsewhere/world/store.py) has `World`, a lock,
and an event stream. There is no structure between a person and the town.

This is last of the three because it should be *found*, not declared. The
README is explicit that culture must be allowed to develop in ways nobody
designed, which means the engine's job is to notice a pattern in the ledger,
not to offer a `Tradition` class for a model to fill in.

**What it means to build.**

- A detector, not a schema: the same thing done by the same people at the same
  time of year, or the same belief held by three people with origins pointing
  at one event. The engine finds the repetition; a model is asked once whether
  it has a name.
- Once named, it becomes visible in the world the way a place is: something
  `act` can see and choose, which is how a tradition becomes self-sustaining.
- `elsewhere culture` to read what has hardened.
- Generational memory is no longer blocked: people arrive and leave now. What
  it still needs is for somebody to have been here long enough that what they
  hold came from a town that no longer exists in anyone else's memory.

## Real life, back in

**The gap.** v2's `remember` takes an event id and puts an existing event past
everyone again ([`cli.py`](../src/elsewhere/cli.py)). v0.1's took a sentence
from your life and admitted it as a new event. The second is the one the README
is about, and it is missing.

- `elsewhere remember "the night bus back from Hualien, and the rain"` should
  record an event nobody witnessed and let it reach people as something carried
  in — `Memory.source = "carried_in"` is already reserved for it.
- `elsewhere invite "Momo" --premise "..."` — `Being.kind` is already typed
  `person | companion | presence`. A presence is a person with a thinner card
  and no occupation; everything else already works on it.
- Photographs and places are the same shape of problem and can wait.

## Ending a world

Nothing can close a world. The README describes `elsewhere end` as the only way
out and as a thing you do from outside. It needs: a last pass over what each
person turned out to be, what they lost, which beliefs outlived their origins,
a final chronicle line, and an archive to `worlds/`. Small, and worth doing
once the world is long enough for the summary to say something.

## Documentation

[`ARCHITECTURE.md`](ARCHITECTURE.md) now exists and explains the
division the rewrite is for: the engine keeps the ledger and decides
reachability, a mind decides meaning, and the two never cross. Keep it
current as each item below lands, rather than letting it drift the way the
old link to a nonexistent `docs/ARCHITECTURE.md` did.

---

## What the road left undone

Two things it deliberately does not do, and one to watch:

- **Nobody comes back.** A name the town has used is refused, which is the
  right guard against the road inventing a second Lilith, and also means the
  one thing the README asks for by name — meeting again years later, both
  changed — cannot happen. Returning is a different call site: the person
  already exists, with everything they left holding.
- **A newcomer has no home.** `home` is empty and nothing gives them one, so
  at night they do whatever a mind does with nowhere to go. Watch what that
  turns into before deciding whether it is a bug.

## Order

1. **P2, you** — the project's stated point, and nothing else is blocked on it.
2. **Real life back in** (`remember`, `invite`) — small, and it finishes the
   entrance the README promises. `invite` is close to `arrive` now: a presence
   is somebody who comes up the road with a card you wrote.
3. **P5, making** — needs nothing new from the engine, and produces the first
   things worth returning for.
4. **Coming back** — the return case above, once there is a town old enough
   for it to mean anything.
5. **P6, culture** — only once there is enough ledger for a detector to find
   something real in it.
6. **Ending a world** — whenever; it is a read-only pass and an archive.

Documentation happens alongside, not at the end.
