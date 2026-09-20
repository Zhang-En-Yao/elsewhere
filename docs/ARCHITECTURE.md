# How Elsewhere is put together

This is the first working version of the world described in the README. It is
small on purpose: four people, one town, no server, no model required.

## The two records

Everything rests on one separation.

```
World.history        one objective chronicle   "The old market burned down."
Person.memories      one store per person      "I was frightened that day."
```

`world.history` is append-only and never edited. A `Memory` is created from an
`Event` at the moment it happens and then goes its own way: it fades, distorts,
merges with other memories, is reinterpreted years later, and may be dropped
entirely while the belief it produced stays behind.

Nothing in the simulation ever reads another person's memories. To learn
something, a person has to be told, and what arrives is a new memory of being
told, not a copy.

## Modules

| file | what it owns |
| --- | --- |
| `worldtime.py` | day / phase / season / year. Four phases per day, 30-day seasons, 120-day years. |
| `events.py` | `Event`, and the table of unexpected things that happen to a town. |
| `memory.py` | `Memory` and `MemoryStore`: decay, recall, distortion, conflation, resurfacing, pruning. |
| `person.py` | traits, needs, relationships, beliefs, expressive style. |
| `perception.py` | event → memory. Salience, lens, interpretation; second-hand and art-borne memories. |
| `world.py` | places, people, chronicle, artifacts, traditions, deterministic RNG, ids. |
| `mind/` | `Mind` protocol, `RuleMind` (default), `PlayerMind`, `LLMMind` (optional). |
| `actions.py` | what actions do to the world and to the people in it. |
| `art.py` | memory → artifact. |
| `culture.py` | themes that enough people carry become traditions, and traditions produce events. |
| `simulation.py` | the tick loop, daily maintenance, world events. |
| `storage.py` | one JSON file per world. |
| `seed.py` | the small beginning, including the fire from the README. |
| `cli.py` | everything a resident can do from a terminal. |

## The memory model

Three quantities decay at different rates:

```
detail     what was said, in what order      fast    (x2.4)
strength   whether it can be reached         normal
intensity  what it felt like                 slow    (x0.08)
```

Resistance to decay is `0.25 + 3.6 * intensity^1.5 + 0.35 * ln(1 + recalls)`,
which produces roughly:

| emotional intensity | forgotten after (never recalled) |
| --- | --- |
| 0.95 | ~460 days |
| 0.70 | ~280 days |
| 0.50 | ~175 days |
| 0.15 | ~47 days |

Below `FORGET_THRESHOLD` a memory goes **dormant**, not deleted: detail is
zeroed, but a matching cue (a place, a theme, a dream) can still bring it back
with `MemoryStore.resurface`, which is where "a memory that unexpectedly
returns years later" lives. Dormant memories are eventually pruned for real;
by then their effect on beliefs, relationships and disposition is already
permanent.

Recalling is not reading. `Memory.recall` strengthens the memory *and* can
distort it: the feeling grows, the colour changes, the details go. Two faded
memories that share a theme can merge into one nobody actually lived.

## From event to person

`perception.encode_event` decides two things: whether this lands at all
(`salience`, which depends on participation, relationships, disposition and
existing beliefs) and through which **lens** it is understood — one of
`fear, resilience, change, loss, wonder, duty, belonging`. The lens sets the
feeling, the interpretation, the belief it can produce, the adjectives that
end up in any art made from it, and the ritual a tradition built on it will
use. This is the machinery behind the README's four versions of one fire.

## Minds

```python
class Mind(Protocol):
    def decide(self, person, view: View, rng) -> Action
```

A `View` is deliberately partial: where you are, who is here, what you can
walk to, what you have made or seen, what is currently on your mind. No mind
receives the `World` object.

`RuleMind` scores about a dozen candidate actions from needs, traits and the
time of day, then samples with a softmax — people are not optimisers.
`LLMMind` builds the same view into a prompt and falls back to `RuleMind`
whenever the model is unavailable or answers with something the world does not
understand, so a language model can be given to one person, a few, or everyone
without changing anything else.

## Speech

A conversation is a memory transfer, and the sentence is the surface of it.
`Mind.speak(scene, rng)` is a second, optional method on the mind protocol: it
receives a `Scene` (who is speaking, to whom, how well they know each other,
where, and the topic memory *in its current state of decay*) and returns one
line. `get_speech()` falls back to `RuleMind` for any mind that does not
implement it, and swallows failures — a tick never dies because nobody could
think of anything to say.

`RuleMind.compose_line` does not invent language; it arranges fixed fragments
around whatever survives of the memory, so the same person telling the same
story sounds different three years later:

```
detail > 0.30   "You will think I never got over it. The old market burned down."
detail > 0.08   "I do not much like bringing this up. I have the fire and not much else."
otherwise       "I do not much like bringing this up. All I have left of it is the fear."
```

The opener and closer come from the memory's lens, so Bram's fire ("It was not
as bad as people say now… It got put back together") and Carol's ("Things were
different after that… Nothing stayed the same after") are recognisably
different accounts of one event. Names of people in the room are turned back
into pronouns, because nobody narrates themselves in the third person.

`LLMMind.speak` sends the same scene to a model, asking for one line of at most
25 words, and explicitly tells it how much of the memory is left so that a
vague memory produces a vague sentence. It falls back to `compose_line` when
the model is unavailable.

What crosses to the listener is **not** the sentence. `perception.distort_line`
strips the framing and keeps the middle, and when the listener misheard — the
existing `misunderstood` roll — wraps it in a wrong takeaway:

```
Alice said:   "It was not as bad as people say now. A storm came down over
               The Old Market; roofs and nerves were tested. It got put back together."
Carol kept:   "What I took from it was a storm came down over The Old Market;
               roofs and nerves were tested - though it may have been the opposite."
```

The result is stored on the listener's memory as `heard`. The division is
deliberate: a model may supply words, but decay, transmission and mishearing
stay in the engine, so a world remains reproducible and an LLM cannot talk its
way past the memory model.

## Culture

Every 30 days the world checks whether a theme has soaked in far enough:
carried by at least 60% of the people, with a combined memory-and-belief
score over 8, and at least two artifacts made about it. If so it hardens into
a `Tradition`, whose day of year comes from the origin event and whose
practice comes from the dominant lens. From then on the tradition produces its
own annual event, which produces new memories — which is how a practice can
outlive everyone who remembers why it started. At most one new tradition can
appear per check, and not within 150 days of the last.

## Determinism

There is no stored RNG state. Every random draw comes from
`World.rng_for(...)`, which hashes the world seed together with the day, the
phase and the person id. The same seed replays the same world, and a world
saved and reloaded mid-run continues identically — both are covered by tests.

## Cost of a world

About 2 seconds per simulated year, and roughly 1-3 MB of JSON per few
hundred days, mostly memories. Memory dicts are written without their default
fields to keep saving and loading cheap.

## What is not here yet

Communities and organizations, religion, artistic movements, generational
memory (nobody is born and nobody dies), photographs and real-world places as
memory sources, and any interface that is not a terminal. The seams for all of
these are the same two: a new `Event` kind, and a new rule in `culture.py`.
