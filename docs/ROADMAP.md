# Roadmap

What Elsewhere does not do yet, and what I would build next, in the order I
would build it. [ARCHITECTURE.md](ARCHITECTURE.md) is how what exists is put
together; the README's *What It Does* is the list of it.

In one line: the town lives on its own, remembers, forgets, misremembers,
decides for itself whether anything happens, and survives losing somebody. It
does not admit you, make anything, or grow anything larger than one being.

---

## You

**The gap.** `Being.mind` is typed `model | player`
([`entities.py`](../src/elsewhere/domain/entities.py)), and nothing reads
`"player"`: [`schedule.being_due`](../src/elsewhere/application/schedule.py) admits only
`mind == "model"`, so a player is skipped entirely — not asked, not spoken to,
leaving no trace.

This is first because it is the thing the README is about. A world that is
worth returning to is not a world you read the logs of.

**What it means to build.** A player is a being asked the same questions by a
prompt on a terminal instead of by a model, whose answers go through exactly
the same schemas. That constraint is the design: if `act` for a player returns
anything the engine would not have accepted from a model, the player has
become an administrator.

- A `play` command that lives one step with you in it: you are shown only what
  your being could see, you pick from the same target enum the engine builds,
  and when someone speaks to you, you answer in your own words.
- `encoded` and `consolidate` for the player are the interesting question.
  Either you write your own episodes and self-schema, or — more in keeping with
  the rest — a model writes them *for* you, from what you did, and you find out
  later what you turned out to have kept. Worth trying both; the second is the one that makes
  forgetting apply to you.
- A player who is away must not stall the world: `elsewhere continue` while
  you are gone lets it run without waiting on an answer that is not coming.
- Other beings forming an impression of you is free once you are a `Being`
  like any other.

**Acceptance.** Play three steps, leave for a week of wall clock, come back and
run `elsewhere person Havvah` — she should have an impression of you, and it
should be wrong in some specific way.

## Real life, back in

**The gap.** Everything that reaches a being happened inside the world. The
README's first promise is a sentence from your life admitted into it.

- `elsewhere remember "the night bus back from Hualien, and the rain"` records
  an event nobody witnessed and lets it reach beings as something carried in —
  it becomes an episode in whoever keeps it, like anything else.
- `elsewhere invite "Momo" --premise "..."` — a presence is a being with a
  thinner biography, who comes up the road with a biography you wrote. `admit` already
  does everything else.
- Photographs and places are the same shape of problem and can wait.

## Making things

**The gap.** `act` has two verbs everywhere (`schemas.ALWAYS_OFFERED`) and a
third only where the road goes out. Nothing a being does leaves anything
behind but a line in `Activity.doings`.

**What it means to build.** An artifact is not a new kind of object so much as
an event with a maker and a durable presence in a place.

- A `make` verb, and a call site asked only of whoever chose it: what they are
  making, out of what in their self-schema, and what it is for. What it came from is
  the whole point; a painting of nothing is decoration.
- Artifacts live in the chronicle as events and in a place. Seeing one is an
  event that reaches whoever is there, so somebody else's painting can end up
  in your episodes — that is the ripple the README describes, and it needs no new
  machinery.
- `tend`, the cheap half: maintaining a thing keeps it in the world. Without
  it, everything made survives forever, which is the wrong failure.
- `elsewhere art` to see what has been made, and out of what.

**Watch out for.** A small model asked to write a poem will write a bad poem
every step. Making should be rare. A cooldown is the obvious gate and the wrong
kind of rule: it would have the engine decide whether somebody makes something
today, on the same clock for everyone. Rarity has to come from the self-schema —
and a concern worth making a thing out of is rare at a different moment for
each being.

## Long-term memory in the weights

**The gap.** What a being carries is one self-schema in the prompt, plus a
search over their engrams. Nothing of them is in the model itself: every being
is the same weights with a different self-schema.

**What it means to build.** The second half of complementary learning systems
(McClelland, McNaughton & O'Reilly 1995): what is written down fast, day by
day, folded slowly into the network itself.

- A LoRA adapter per being (Hu et al. 2021), trained with `mlx_lm.lora` on
  their own episodes and every self-schema they have held. The subjective
  record is kept whole from the first night, so the training data already
  exists.
- `consolidate` is the natural call to run on the being's own adapter first:
  it is already the mind beneath the person, not the person answering.
- Trained rarely, on the world's clock — a season, say — and only on what the
  being wrote, never on the chronicle.
- `MLXBackend` loads the adapter of whoever `Call.mind` names. Only one base
  model fits on an 8GB Mac, so adapters swap rather than stack.

**Watch out for.** A model trained on its own summaries of its own summaries
drifts toward a caricature. That may be what memory is, but it should be looked
at before it is left running.

## Coming back

A being who leaves is never asked anything again, and `admit` always makes a
new one — so the one thing the README asks for by name, meeting again years
later with both of you changed, cannot happen. Returning is its own call site:
the being already exists, with the self-schema they left holding, and the
town has been forming its own impressions of them since.

## Above the individual

**The gap.** There is no structure between a being and the town. This should
be *found*, not declared: the README says culture must be allowed to develop in
ways nobody designed, so the engine's job is to notice a pattern, not to offer
a `Tradition` class for a model to fill in.

- A detector, not a schema: the same thing done by the same beings at the same
  time of year, found in the chronicle. Whether three beings hold the same
  assumption is a question about meaning, so it is a model's, asked once.
- Once named, it is visible in the world the way a place is — something `act`
  can see and choose, which is how a tradition sustains itself.
- `elsewhere culture` to read what has hardened.
- Generational memory needs only time: somebody here long enough that what
  they hold came from a town that exists in nobody else's engrams.

## Ending a world, properly

`elsewhere end` closes a world and leaves it readable. What it does not do yet
is take leave of it: a last pass over what each being turned out to be and what
is still in their self-schema, a final line in the chronicle, and an archive to
`worlds/`. Small, and worth doing once a world is long enough for that pass to
say something.

## Smaller things to watch

- **A newcomer has no home.** `home` is empty and nothing gives them one, so at
  night they do whatever a mind does with nowhere to go. Watch what that turns
  into before deciding whether it is a bug.
- **Retrieval has no threshold.** One engram always comes back when anything
  is shared, however slightly. Watch whether small models treat a loosely
  related couple of gists as important before deciding to gate it.
- **Recall does not rehearse.** An engram fades on the same curve whether it
  comes back every day or never; in people, retrieval strengthens a memory.
  If the town's oldest memories turn out too thin, count the age from the last
  time it came back (ACT-R's base-level learning, Anderson & Lebiere 1998)
  rather than from the night it was laid down.
- **How heavily a night weighs its gists** is a small model's call. Watch
  whether it weights everything near 1, which would make forgetting keep
  arbitrary pieces.
- **Consequence is thin.** The engine does not resolve an action into an
  outcome; `stir` reading `Activity.doings` is the whole of it. Full action
  resolution is Concordia's Game Master
  (`components/game_master/event_resolution.py`).

## Order

1. **You** — the project's stated point, and nothing else is blocked on it.
2. **Real life, back in** — small, and it finishes the entrance the README
   promises. `invite` is close to `admit` already.
3. **Making things** — needs nothing new from the engine, and produces the
   first things worth returning for.
4. **Long-term memory in the weights** — once there are seasons of episodes
   and self-schemas to train on.
5. **Coming back** — once there is a town old enough for it to mean anything.
6. **Above the individual** — once there is enough chronicle for a detector to
   find something real in it.
7. **Ending a world, properly** — whenever; it is a read-only pass and an
   archive.

Keep [ARCHITECTURE.md](ARCHITECTURE.md) current as each of these lands.
