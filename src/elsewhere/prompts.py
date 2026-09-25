"""What a mind is shown before it is asked anything.

A person is never handed the world. They are handed themselves, the room they
are standing in, and the few things they can currently bring to mind - which
is the retrieval layer's decision, not theirs.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from . import HOURS_PER_DAY
from .world.entities import Being
from .world.memories import Trace
from .world.store import clock_at, day_of


def _when(at: float) -> str:
    """A moment as the record says it: 'day 68, 02:00'. No name for the hour."""
    return f"day {day_of(at)}, {clock_at(at)}"


def being_block(being: Being) -> str:
    lines = [f"You are {being.name}."]
    if being.card:
        lines.append(being.card)
    if being.voice:
        lines.append(f"How you talk: {being.voice}")
    if being.thought:
        lines.append(f"What you keep coming back to: {being.thought}")
    if being.wants:
        lines.append("What you want at the moment: " + "; ".join(being.wants) + ".")
    if being.beliefs:
        held = sorted(being.beliefs, key=lambda b: -b.confidence)[:3]
        lines.append("What you hold to be true: " +
                     " ".join(f"{b.belief}." for b in held))
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


def _since(regard, at: float) -> str:
    """How long since they last spoke, as a fact and not as a verdict.

    The engine does not decide what a season of silence means - some people
    pick up where they left off and some never do. It says how long it has
    been and leaves the reading of it to them.
    """
    if regard.last_seen_at <= 0.0:
        return ""
    days = int((at - regard.last_seen_at) // HOURS_PER_DAY)
    if days <= 0:
        return " You spoke earlier today."
    if days == 1:
        return " You last spoke yesterday."
    return f" You last spoke {days} days ago."


def regards_block(being: Being, others: Sequence[Being], at: float) -> str:
    """Who is here, as this person would account for them.

    Knowing somebody is having something to say about them - not a number
    above a threshold. A mind that has never formed an account of this face
    does not know it, however many times they have passed in the road.
    """
    if not others:
        return "You are alone."
    lines = ["Who is here:"]
    for other in others:
        regard = being.regards.get(other.id)
        if regard is None or not regard.account:
            lines.append(f"  - {other.name}, who you do not know.")
        else:
            lines.append(f"  - {other.name}. {regard.account}{_since(regard, at)}")
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

feeling: what it feels like to them, in their own words. Usually one word,
and not necessarily a common one - a feeling nobody has a tidy name for is
still the feeling they had, and "relief that came out wrong" is a better
answer than the nearest word off a list. Empty, or "none", when there is
nothing.

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
     "means": "", "feeling": "grief", "weight": "stays"}

  Oskar, a trader who counts everything. Behind the cart, holding his own horse.
    {"trace": "two sacks of flour split open in the mud",
     "means": "someone is paying for that, and it is not me",
     "feeling": "unease", "weight": "faint"}

  Pell, an old ferryman who has seen it before. On the far bank.
    {"trace": "a cart on its side", "means": "", "feeling": "none",
     "weight": "nothing"}"""


#: The example traces above, so the eval can tell a copied example from a memory.
PERCEIVE_EXAMPLE_TRACES = (
    "its eye was open the whole time they were deciding",
    "two sacks of flour split open in the mud",
    "a cart on its side",
)


def perceive_user(being: Being, what_happened: str, where: str, when: str,
                  at: float, others: Sequence[Being],
                  part_of_it: bool, vantage: str = "") -> str:
    """Scene first, person last, and nothing they already remember.

    A small model weights the end of a prompt far more than the start. With the
    character card at the top, by the time it reaches the question the card
    has been drowned by the scene - and everyone answers as the same narrator.

    What is deliberately absent is their own memories. Laying four of them in
    front of somebody and then asking what this new thing leaves in them is
    asking to be handed one of the four back, and it was: with them in the
    prompt, two in five answers were word-for-word copies of a memory the
    person already had, every one of them weighed "stays", and three people
    between them used five words for how anything felt. Without them: four in
    five answers new, and nine words for a feeling. Who they are is still
    here - the card, what they want, where they were standing. What has gone
    is the nearest thing to copy.
    """
    parts = [
        f"It was {when}, at {where}.",
        ("What happened to you: " if part_of_it else "What happened: ")
        + what_happened,
        (f"You were {vantage}. That is where you stood, not what you noticed - "
         f"do not reuse its words.") if vantage else "",
        regards_block(being, others, at).replace("Who is here:", "Who else was there:"),
        being_block(being),
        f"Now answer as {being.name}, and only as {being.name}: how much of this "
        f"do you carry? For some people it is everything; for others, nothing at all.",
    ]
    return "\n\n".join(part for part in parts if part)


# --------------------------------------------------------------------------
# act: what someone does with the next few hours

ACT_SYSTEM = """You are one person in a small town, deciding what to do with
the next few hours. You are not narrating and not explaining yourself to anyone.

because: first, in a few words and in your own voice, what is pulling at you
right now - a want, a worry, tiredness, someone you have been meaning to see.

doing: then what you are actually doing, in your own words and in the
present - mending the nets, sitting with the door open, not sleeping, walking
because lying there is worse. This is not chosen from anything. Most of a life
is here, and most of it is ordinary.

action: then which of three things the world has to do about it. There are
only three because there are only three things it can do.
  stay  - nothing moves; whatever you said in "doing" is what it looks like
  go    - walk to one of the places you can reach from here (target: the place)
  talk  - speak with someone who is here right now (target: their name)

target: the place or the person, exactly as written in the options; empty for
stay.

Some days one more verb is there: leave. It only ever appears when this person
is standing where the road goes out of the town, and it is not a walk to the
next place - it is the end of their life here. Almost nobody takes it. Take it
only when their own wants, and what they hold to be true, have been pointing
down that road for a while, and say so plainly in "because".

The hour is a fact about the clock, not an instruction about what to do with
it. It does not mean the same thing to everyone: the same night is nothing for
one person and everything for another. Read that from who they are, below -
their card, what they keep coming back to, what they want - not from what
hour it is. Most people
are home and settled by night, because most people are; that is a fact about
most people, not a rule this one has to follow.

This town is small. When someone is right there with you, you usually say
something, even if it is only about the weather - unless you have your own
reason not to, and then that reason is your "because".

Four people, another town, another day - the form, not the content:

  Morning. Mira is at her door. Here: nobody. Can go to: the ford, the well.
    {"because": "the children arrive soon and the step needs scrubbing",
     "doing": "scrubbing the step, badly, because there is no time",
     "action": "stay", "target": ""}

  Afternoon. Oskar is at the ford. Here: Mira. Can go to: the market.
    {"because": "she saw the cart go over; I want to know what she told the reeve",
     "doing": "working round to asking her about it",
     "action": "talk", "target": "Mira"}

  Night. Pell is at the ferry house. Here: nobody. Can go to: the far bank.
    {"because": "tired",
     "doing": "asleep in the chair before he gets as far as the bed",
     "action": "stay", "target": ""}

  Night. Sula, who has not slept right since the flood, is at her door.
  Here: nobody. Can go to: the waterline.
    {"because": "lying there is worse than walking",
     "doing": "going down to look at the water, which she knows does not help",
     "action": "go", "target": "the waterline"}

  Afternoon. Carin is on the ridge, where the road goes out. Here: nobody.
  Can go to: the well. Leaving is possible today.
    {"because": "I said I would go before winter and I have not",
     "action": "go", "target": "the well"}"""


def act_user(being: Being, when: str, at: float, place, others: Sequence[Being],
             reachable: Sequence[str], traces: Sequence[Trace],
             home_name: str = "", may_leave: bool = False) -> str:
    here = ", ".join(o.name for o in others) if others else "nobody"
    if place and being.home == place.id:
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
        regards_block(being, others, at) if others else "",
        traces_block(traces),
        being_block(being),
        f"Now decide as {being.name}: what do you do for the next few hours?",
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


def speak_user(being: Being, listener: Being, when: str, place_name: str,
               topics: Sequence[Trace]) -> str:
    regard = being.regards.get(listener.id)
    knows = f" {regard.account}" if regard and regard.account else ""
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
    lines.append(being_block(being))
    lines.append(f"What does {being.name} say to {listener.name}?")
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
     "happens": true}

  Autumn. Oskar has been owed money since the cart went over.
    {"why_now": "a debt nobody has settled",
     "what": "A man from upriver came to the ford asking for Oskar by name.",
     "where": "the ford", "who": "Oskar", "reach": "the people there",
     "happens": true}

  Autumn, the next day. Yesterday a stranger came.
    {"why_now": "yesterday was already enough",
     "what": "", "where": "the ford", "who": "", "reach": "the people there",
     "happens": false}"""


def direct_user(world, recent) -> str:
    places = "Places: " + "; ".join(
        f"{p.name} ({p.description})" if p.description else p.name
        for p in world.places.values())
    beings = ["People:"]
    for being in sorted(world.beings.values(), key=lambda p: p.name):
        if not being.present:
            continue
        place = world.places.get(being.place)
        wants = f" Lately after: {'; '.join(being.wants)}." if being.wants else ""
        beings.append(f"  - {being.name}, at "
                      f"{place.name if place else 'nowhere'}.{wants}")
    record = ["Lately, in the record:"]
    record += [f"  - {_when(e.at)}: {e.account}" for e in recent] or ["  nothing."]
    return "\n\n".join([
        f"{world.name}. {world.label()}.",
        places,
        "\n".join(beings),
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
work nobody has done since somebody left, a season, a road that goes
somewhere else as well.

name, from_where: then who they are, plainly. A name that belongs in the same
world as the names already here. Somewhere they came from that is not this
town.

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
     "card": "You came for the ferry and you are good on water. You do not ask for much and you do not explain yourself.",
     "voice": "Few words, and none of them about yourself.",
     "comes": true}

  The same town, a week later. Hesper has the ferry.
    {"why_now": "nothing here is short of anybody", "name": "", "from_where": "",
     "card": "", "voice": "", "comes": false}"""


def arrive_user(world, recent) -> str:
    here = [p for p in world.beings.values() if p.present]
    gone = [p for p in world.beings.values() if not p.present]
    places = "Places: " + "; ".join(p.name for p in world.places.values())
    beings = [f"Who lives here ({len(here)}):"]
    for being in sorted(here, key=lambda p: p.name):
        beings.append(f"  - {being.name}.")
    if gone:
        beings.append("Who has gone: " + "; ".join(
            p.name for p in sorted(gone, key=lambda p: p.name)) + ".")
    record = ["Lately, in the record:"]
    record += [f"  - {_when(e.at)}: {e.account}" for e in recent] or ["  nothing."]
    return "\n\n".join([
        f"{world.name}. {world.label()}.",
        places,
        "\n".join(beings),
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

Two people, another town - the form, not the content:

  Mira. Today: 1. its eye was open the whole time they were deciding.
    {"thought": "Why did nobody close its eye", "belief": "",
     "belief_from": "", "want": "keep the children away from the river bend"}

  Oskar. Today: 1. a man from upriver asked for me by name.
    {"thought": "He knew my name before he knew my face",
     "belief": "Somebody upriver has been talking about me",
     "belief_from": "1", "want": "find out who sent him"}"""


def reflect_user(being: Being, today: Sequence[Trace],
                 older: Sequence[Trace]) -> str:
    lines = []
    if today:
        lines.append("Today, what stayed with you:")
        for i, t in enumerate(today, 1):
            extra = f" ({t.means})" if t.means else ""
            lines.append(f"  {i}. {t.trace}{extra}")
    lines.append(traces_block(older, "Older things you can still bring to mind"))
    lines.append(being_block(being))
    lines.append(f"It is night. What is {being.name} left with?")
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
feeling: what comes with it now, in their own words. It does not have to be
what it was, and it does not have to be a word anyone else would use.

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


def recall_user(being: Being, trace: Trace, age_days: int, reach_value: float) -> str:
    was = f'"{trace.trace}"' + (f" (what it meant: {trace.means})" if trace.means else "")
    told = {0: "never told", 1: "told once"}.get(trace.recalls, f"told {trace.recalls} times")
    return "\n\n".join([
        f"The memory, {age_days} days old, {clarity(reach_value)}, {told}. It was: {was}",
        being_block(being),
        f"How does it come back to {being.name} now?",
    ])
