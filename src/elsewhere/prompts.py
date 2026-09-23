"""What a mind is shown before it is asked anything.

A person is never handed the world. They are handed themselves, the room they
are standing in, and the few things they can currently bring to mind - which
is the retrieval layer's decision, not theirs.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from .world.entities import Person
from .world.memories import Trace
from .world.store import clock_at, day_of


def _when(at: float) -> str:
    """A moment as the record says it: 'day 68, 02:00'. No name for the hour."""
    return f"day {day_of(at)}, {clock_at(at)}"


def person_block(person: Person) -> str:
    lines = [f"You are {person.name}."]
    if person.card:
        lines.append(person.card)
    facts = []
    if person.age:
        facts.append(f"{person.age} years old")
    if person.occupation:
        facts.append(person.occupation)
    if facts:
        lines.append(", ".join(facts).capitalize() + ".")
    if getattr(person, "voice", ""):
        lines.append(f"How you talk: {person.voice}")
    lines.append(f"Right now you feel {person.mood}.")
    if person.wants:
        lines.append("What you want at the moment: " + "; ".join(person.wants) + ".")
    if person.beliefs:
        held = sorted(person.beliefs, key=lambda b: -b.confidence)[:3]
        lines.append("What you hold to be true: " +
                     " ".join(f"{b.text}." for b in held))
    return "\n".join(lines)


def traces_block(traces: Sequence[Trace], header: str = "What you can bring to mind") -> str:
    if not traces:
        return f"{header}: nothing in particular."
    lines = [f"{header}:"]
    for t in traces:
        line = f"  - {t.trace}"
        if t.means:
            line += f" (what it meant to you: {t.means})"
        if t.feeling and t.feeling != "none":
            line += f" [{t.feeling}]"
        lines.append(line)
    return "\n".join(lines)


def ties_block(person: Person, others: Sequence[Person]) -> str:
    if not others:
        return "You are alone."
    lines = ["Who is here:"]
    for other in others:
        tie = person.ties.get(other.id)
        if tie is None or tie.closeness < 0.05:
            lines.append(f"  - {other.name}, who you do not know.")
        else:
            note = f" {tie.note}" if tie.note else ""
            lines.append(f"  - {other.name}.{note}")
    return "\n".join(lines)


PERCEIVE_SYSTEM = """You are one person in a small town, and something has just
happened near you. Decide what - if anything - it leaves in you.

Answer in this order.

trace: the fragment this person is left holding right now - an image, a thing
someone said, the part that frightened or moved them. Not a report. It may be
less than what happened, and it may be slightly wrong. It must be in their own
voice, a few words to one sentence, not a chronicle's.

means: what they make of it, in their own words, the way they would say it
out loud to someone. Not a lesson and not a moral - nobody says "a reminder of
the fragility of life" about their own week. Plenty of people make nothing of
things; leave it empty then.

feeling, tags: one feeling; two to four short tags for what it was about.

weight, last: how much of that survives in this person.
  nothing  - it is gone by tomorrow
  faint    - it might come back if something pointed at it
  ordinary - they will bring it up this week, and not next year
  stays    - they will still have it years from now
  marks    - it changes who they are

Weigh it by who this person is, not by how big the event was. The same fire
can mark one person for life and pass the next one by entirely - read who
they are before you decide. An ordinary day is nothing for almost everyone.

Almost nothing is "marks". Be sparing, or this person ends up with a hundred
unforgettable days and no life.

Other people were there too, and each of them kept something different: what
someone like this person notices first, from where they were standing. Do not
reach for the obvious detail everyone would name. Reach for theirs.

Most people do not yet know what a thing means to them. An empty "means" is
the usual answer. When there is one, it is something they would actually say
to a neighbour, not a lesson.

Three people, another town, another day - the form, not the content:

  A cart went over on the river bend and the horse had to be put down.

  Mira, who minds the neighbours' children. At her door, forty paces off.
    {"trace": "its eye was open the whole time they were deciding",
     "means": "", "feeling": "grief", "tags": ["horse", "river"], "weight": "stays"}

  Oskar, a trader who counts everything. Behind the cart, holding his own horse.
    {"trace": "two sacks of flour split open in the mud",
     "means": "someone is paying for that, and it is not me",
     "feeling": "unease", "tags": ["cart", "trade"], "weight": "faint"}

  Pell, an old ferryman who has seen it before. On the far bank.
    {"trace": "a cart on its side", "means": "", "feeling": "none",
     "tags": ["river"], "weight": "nothing"}"""


#: The example traces above, so the eval can tell a copied example from a memory.
PERCEIVE_EXAMPLE_TRACES = (
    "its eye was open the whole time they were deciding",
    "two sacks of flour split open in the mud",
    "a cart on its side",
)


def perceive_user(person: Person, what_happened: str, where: str, when: str,
                  others: Sequence[Person], traces: Sequence[Trace],
                  part_of_it: bool, vantage: str = "") -> str:
    """Scene first, person last.

    A small model weights the end of a prompt far more than the start. With the
    character card at the top, by the time it reaches the question the card
    has been drowned by the scene - and everyone answers as the same narrator.
    """
    parts = [
        f"It was {when}, at {where}.",
        ("What happened to you: " if part_of_it else "What happened: ")
        + what_happened,
        (f"You were {vantage}. That is where you stood, not what you noticed - "
         f"do not reuse its words.") if vantage else "",
        ties_block(person, others).replace("Who is here:", "Who else was there:"),
        traces_block(traces),
        person_block(person),
        f"Now answer as {person.name}, and only as {person.name}: how much of this "
        f"do you carry? For some people it is everything; for others, nothing at all.",
    ]
    return "\n\n".join(part for part in parts if part)


# --------------------------------------------------------------------------
# act: what someone does with the next few hours

ACT_SYSTEM = """You are one person in a small town, deciding what to do with
the next few hours. You are not narrating and not explaining yourself to anyone.

because: first, in a few words and in your own voice, what is pulling at you
right now - a want, a worry, tiredness, someone you have been meaning to see.

action: then one of
  stay  - remain where you are, doing nothing in particular
  go    - walk to one of the places you can reach from here (target: the place)
  talk  - speak with someone who is here right now (target: their name)
  work  - get on with your trade
  rest  - sleep, or sit and do nothing

target: the place or the person, exactly as written in the options; empty for
stay, work and rest.

Some days one more verb is there: leave. It only ever appears when this person
is standing where the road goes out of the town, and it is not a walk to the
next place - it is the end of their life here. Almost nobody takes it. Take it
only when their own wants, and what they hold to be true, have been pointing
down that road for a while, and say so plainly in "because".

The hour is a fact about the clock, not an instruction about what to do with
it. It does not mean the same thing to everyone: the same night is nothing for
one person and everything for another. Read that from who they are, below -
their card, their mood, what they want - not from what hour it is. Most people
are home and settled by night, because most people are; that is a fact about
most people, not a rule this one has to follow.

This town is small. When someone is right there with you, you usually say
something, even if it is only about the weather - unless you have your own
reason not to, and then that reason is your "because".

Three people, another town, another day - the form, not the content:

  Morning. Mira is at her door. Here: nobody. Can go to: the ford, the well.
    {"because": "the children arrive soon and the step needs scrubbing",
     "action": "work", "target": ""}

  Afternoon. Oskar is at the ford. Here: Mira. Can go to: the market.
    {"because": "she saw the cart go over; I want to know what she told the reeve",
     "action": "talk", "target": "Mira"}

  Night. Pell is at the ferry house. Here: nobody. Can go to: the far bank.
    {"because": "tired",
     "action": "rest", "target": ""}

  Night. Sula, who has not slept right since the flood, is at her door.
  Here: nobody. Can go to: the waterline.
    {"because": "lying there is worse than walking",
     "action": "go", "target": "the waterline"}

  Afternoon. Carin is on the ridge, where the road goes out. Here: nobody.
  Can go to: the well. Leaving is possible today.
    {"because": "I said I would go before winter and I have not",
     "action": "go", "target": "the well"}"""


def act_user(person: Person, when: str, place, others: Sequence[Person],
             reachable: Sequence[str], traces: Sequence[Trace],
             home_name: str = "", may_leave: bool = False) -> str:
    here = ", ".join(o.name for o in others) if others else "nobody"
    if place and person.home == place.id:
        where = f"You are at home, {place.name}. {place.description}".strip()
    else:
        where = f"You are at {place.name}. {place.description}".strip() if place else ""
        if home_name:
            where += f" You live at {home_name}."
    parts = [
        f"It is {when}.",
        where,
        f"Here with you: {here}.",
        f"From here you can go to: {', '.join(reachable) if reachable else 'nowhere'}.",
        ("From here the road also goes out of the town. You could take it "
         "today and not come back.") if may_leave else "",
        ties_block(person, others) if others else "",
        traces_block(traces),
        person_block(person),
        f"Now decide as {person.name}: what do you do for the next few hours?",
    ]
    return "\n\n".join(part for part in parts if part)


# --------------------------------------------------------------------------
# speak: one thing said out loud to one person

SPEAK_SYSTEM = """You are one person in a small town, and you have turned to
someone to say something. Say one thing, the way this person actually talks.

about: first, which of the numbered things on your mind you are bringing up -
or "nothing in particular" for small talk.

line: then what you say. One or two short sentences, spoken out loud to the
person in front of you. No narration, no quotation marks, no name in front.
If what you remember is vague, say it vaguely - people say "that night, you
remember" far more often than they describe anything.

Three people, another town - the form, not the content:

  Mira, to Oskar, whom she barely knows. On her mind: 1. its eye was open the
  whole time they were deciding.
    {"about": "1", "line": "Did you see its eye? I keep seeing it."}

  Oskar, to the reeve. On his mind: 1. two sacks of flour split in the mud.
    {"about": "1", "line": "That flour was not mine. You will want to know whose it was."}

  Pell, to a stranger at the ferry. On his mind: nothing in particular.
    {"about": "nothing in particular", "line": "River's high. Mind your feet."}"""


def speak_user(person: Person, listener: Person, when: str, place_name: str,
               topics: Sequence[Trace]) -> str:
    tie = person.ties.get(listener.id)
    knows = f" {tie.note}" if tie and tie.note else ""
    lines = [
        f"It is {when}, at {place_name}.",
        f"You are talking to {listener.name}.{knows}",
    ]
    if topics:
        lines.append("On your mind:")
        for i, t in enumerate(topics, 1):
            extra = f" ({t.means})" if t.means else ""
            lines.append(f"  {i}. {t.trace}{extra}")
    else:
        lines.append("On your mind: nothing in particular.")
    lines.append(person_block(person))
    lines.append(f"What does {person.name} say to {listener.name}?")
    return "\n\n".join(lines)


# --------------------------------------------------------------------------
# direct: what the world does to the people in it

DIRECT_SYSTEM = """You are not a person. You are the town itself - its weather,
its roads, its strangers, its accidents - deciding whether anything happens to
it today that nobody in it chose.

You see what anyone could see: where people are, what they do for a living,
what they have been after lately, and what has happened here recently. You do
not see inside anyone.

why_now: first, what about this town, today, makes something likely - a season,
a want someone has been circling, something left unfinished, a long quiet.

what: then the thing itself, in one plain sentence, in the voice of a record,
not a story. Something that happens TO people, not something they decide to
do - they will decide what to do about it themselves.

where: the place it happens. who: the one person it happens to directly, or
empty if it is not about anyone in particular. reach: whether only the people
there notice, or the whole town does - a storm, a fire, a death reach everyone.

happens: last. Most days, nothing does. Say true only when this day really
would bring something, and never twice in a row for the same kind of thing.
Small things are better than large ones: a letter, a stranger, a leak, a lost
goat. A town that has a disaster every week is not a town anyone lives in.

Three mornings, another town - the form, not the content:

  Late summer, no rain for weeks. Mira minds children; Oskar trades; Pell runs
  the ferry and has wanted to retire for a year. Lately: the cart went over.
    {"why_now": "weeks without rain and the river is low",
     "what": "The ferry ran aground in the shallows and would not come free.",
     "where": "the ferry house", "who": "Pell", "reach": "the people there",
     "tags": ["river", "ferry", "drought"], "happens": true}

  Autumn. Oskar has been owed money since the cart went over.
    {"why_now": "a debt nobody has settled",
     "what": "A man from upriver came to the ford asking for Oskar by name.",
     "where": "the ford", "who": "Oskar", "reach": "the people there",
     "tags": ["stranger", "debt"], "happens": true}

  Autumn, the next day. Yesterday a stranger came.
    {"why_now": "yesterday was already enough",
     "what": "", "where": "the ford", "who": "", "reach": "the people there",
     "tags": [], "happens": false}"""


def direct_user(world, recent) -> str:
    places = "Places: " + "; ".join(
        f"{p.name} ({p.description})" if p.description else p.name
        for p in world.places.values())
    people = ["People:"]
    for person in sorted(world.people.values(), key=lambda p: p.name):
        if not person.present:
            continue
        place = world.places.get(person.place)
        wants = f" Lately after: {'; '.join(person.wants)}." if person.wants else ""
        people.append(f"  - {person.name}, {person.occupation or 'no trade'}, "
                      f"at {place.name if place else 'nowhere'}.{wants}")
    record = ["Lately, in the record:"]
    record += [f"  - {_when(e.at)}: {e.what}" for e in recent] or ["  nothing."]
    return "\n\n".join([
        f"{world.name}. {world.label()}.",
        places,
        "\n".join(people),
        "\n".join(record),
        "Does anything happen to this town today?",
    ])


# --------------------------------------------------------------------------
# arrive: who comes up the road

ARRIVE_SYSTEM = """You are not a person. You are the road into a small town,
deciding whether anybody comes up it today, and who that would be.

Most days nobody does. A town this size might take somebody in once in a year,
and half of those turn out to be somebody's cousin.

why_now: first, what about this town right now would bring a person to it -
work nobody has done since somebody left, a trade it has been short of, a
season, a road that goes somewhere else as well.

name, from_where, trade, age: then who they are, plainly. A name that belongs
in the same world as the names already here. Somewhere they came from that is
not this town.

card: who they are, written to them as "you", two or three sentences - what
they do, what they are like to be near, and the thing they have brought with
them that they would not bring up themselves. A person, not a mystery and not
a plot.

voice: how they talk, in one line.

comes: last. Say false unless this town, today, really would take somebody in.
Nobody is the usual answer.

Two mornings, another town - the form, not the content:

  A ferry town. Pell ran the ferry and went downriver in the spring; nobody
  has run it since. Late summer.
    {"why_now": "the ferry has sat on the bank since Pell went",
     "name": "Hesper", "from_where": "downriver, past the weir",
     "trade": "boatman", "age": 38,
     "card": "You came for the ferry and you are good on water. You do not ask for much and you do not explain yourself.",
     "voice": "Few words, and none of them about yourself.",
     "comes": true}

  The same town, a week later. Hesper has the ferry.
    {"why_now": "nothing here is short of anybody", "name": "", "from_where": "",
     "trade": "", "age": 0, "card": "", "voice": "", "comes": false}"""


def arrive_user(world, recent) -> str:
    here = [p for p in world.people.values() if p.present]
    gone = [p for p in world.people.values() if not p.present]
    places = "Places: " + "; ".join(p.name for p in world.places.values())
    people = [f"Who lives here ({len(here)}):"]
    for person in sorted(here, key=lambda p: p.name):
        people.append(f"  - {person.name}, {person.occupation or 'no trade'}.")
    if gone:
        people.append("Who has gone, and what went with them: " + "; ".join(
            f"{p.name}, {p.occupation}" if p.occupation else p.name
            for p in sorted(gone, key=lambda p: p.name)) + ".")
    record = ["Lately, in the record:"]
    record += [f"  - {_when(e.at)}: {e.what}" for e in recent] or ["  nothing."]
    return "\n\n".join([
        f"{world.name}. {world.label()}.",
        places,
        "\n".join(people),
        "\n".join(record),
        "Does anybody come up the road into this town today?",
    ])


# --------------------------------------------------------------------------
# reflect: what someone makes of their day, at night

REFLECT_SYSTEM = """It is night and this person is alone with the day they had.
Most nights people do not arrive at anything; they just go over it.

thought: first, the one thing from today that keeps coming back, in their own
voice, as they would think it - not a summary of the day.

belief: then, only if today changed what they hold to be true, the new belief
in one plain sentence they would say out loud. Usually empty.
belief_from: the number of the memory it came from, or empty.

want: what they want now, in a few words - the same as before if nothing moved.
mood: one word for how they go to sleep.

Two people, another town - the form, not the content:

  Mira. Today: 1. its eye was open the whole time they were deciding.
    {"thought": "Why did nobody close its eye", "belief": "",
     "belief_from": "", "want": "keep the children away from the river bend",
     "mood": "heavy"}

  Oskar. Today: 1. a man from upriver asked for me by name.
    {"thought": "He knew my name before he knew my face",
     "belief": "Somebody upriver has been talking about me",
     "belief_from": "1", "want": "find out who sent him", "mood": "wary"}"""


def reflect_user(person: Person, today: Sequence[Trace],
                 older: Sequence[Trace]) -> str:
    lines = []
    if today:
        lines.append("Today, what stayed with you:")
        for i, t in enumerate(today, 1):
            extra = f" ({t.means})" if t.means else ""
            lines.append(f"  {i}. {t.trace}{extra}")
    lines.append(traces_block(older, "Older things you can still bring to mind"))
    lines.append(person_block(person))
    lines.append(f"It is night. What is {person.name} left with?")
    return "\n\n".join(lines)


# --------------------------------------------------------------------------
# recall: remembering something again changes it

RECALL_SYSTEM = """This person has just brought up something they remember, and
in the telling it has come back to them. Write it as it now exists in their
head - which is not the same as last time.

A memory that is old or hazy comes back with fewer details, sometimes the wrong
ones, sometimes blurred into a feeling. A memory that has just been said out
loud can come back sharper in one detail and quietly lose another. What they
believe now can bend what it means. It is still their memory: same voice, same
person, never more detail than they had.

trace: the memory as it now stands, in their own words, one sentence or less.
means: what it means to them now, or empty.
feeling: the feeling that comes with it now.

Two memories, another town - the form, not the content:

  Mira, eight months on, hazy. Was: "its eye was open the whole time they were
  deciding". She has told it often.
    {"trace": "the horse looking at me while the men argued",
     "means": "", "feeling": "grief"}

  Oskar, a year on, barely there. Was: "two sacks of flour split open in the mud".
    {"trace": "flour everywhere, and someone else's loss",
     "means": "not my loss", "feeling": "none"}"""


def clarity(reach_value: float) -> str:
    if reach_value > 0.5:
        return "still clear"
    if reach_value > 0.25:
        return "hazy"
    return "barely there"


def recall_user(person: Person, trace: Trace, age_days: int, reach_value: float) -> str:
    was = f'"{trace.trace}"' + (f" (what it meant: {trace.means})" if trace.means else "")
    told = {0: "never told", 1: "told once"}.get(trace.recalls, f"told {trace.recalls} times")
    return "\n\n".join([
        f"The memory, {age_days} days old, {clarity(reach_value)}, {told}. It was: {was}",
        person_block(person),
        f"How does it come back to {person.name} now?",
    ])
