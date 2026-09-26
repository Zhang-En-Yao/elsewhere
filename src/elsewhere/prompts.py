"""The prompts each model call is shown."""

from __future__ import annotations

from typing import List, Optional, Sequence

from . import HOURS_PER_DAY
from .world.entities import Being
from .world.memories import Memory
from .world.store import clock_at, day_of


def _when(at: float) -> str:
    return f"day {day_of(at)}, {clock_at(at)}"


def being_block(being: Being, with_thought: bool = True,
                beliefs: Optional[Sequence] = None) -> str:
    """`with_thought` is off for `perceive`: `thought` is one constant
    first-person sentence and small models copy it straight into the answer
    (measured 77% copies with it, 20% without)."""
    lines = [f"You are {being.name}."]
    if being.who.card:
        lines.append(being.who.card)
    if being.who.manner:
        lines.append(f"How you talk: {being.who.manner}")
    if being.who.thought and with_thought:
        lines.append(f"What you keep coming back to: {being.who.thought}")
    if being.who.wants:
        lines.append("What you want at the moment: " + "; ".join(being.who.wants) + ".")
    # `beliefs` comes from `agents.held_beliefs`; stored order is the fallback.
    held = list(beliefs) if beliefs is not None else being.who.beliefs[:3]
    if held:
        lines.append("What you hold to be true: " +
                     " ".join(f"{b.claim}." for b in held))
    return "\n".join(lines)


def memories_block(memories: Sequence[Memory], header: str = "What you can bring to mind") -> str:
    if not memories:
        return f"{header}: nothing in particular."
    lines = [f"{header}:"]
    for t in memories:
        line = f"  - {t.account}"
        if t.means:
            line += f" (what it meant to you: {t.means})"
        if t.feeling and t.feeling != "none":
            line += f" [{t.feeling}]"
        lines.append(line)
    return "\n".join(lines)


def _since(regard, at: float) -> str:
    if regard.last_seen_at <= 0.0:
        return ""
    days = int((at - regard.last_seen_at) // HOURS_PER_DAY)
    if days <= 0:
        return " You spoke earlier today."
    if days == 1:
        return " You last spoke yesterday."
    return f" You last spoke {days} days ago."


def regards_block(being: Being, others: Sequence[Being], at: float) -> str:
    """Only people this person has an account of are shown as known."""
    if not others:
        return "You are alone."
    lines = ["Who is here:"]
    for other in others:
        regard = being.who.regards.get(other.id)
        if regard is None or not regard.account:
            lines.append(f"  - {other.name}, who you do not know.")
        else:
            lines.append(f"  - {other.name}. {regard.account}{_since(regard, at)}")
    return "\n".join(lines)


PERCEIVE_SYSTEM = """You are one person in a small town, and something has just
happened near you. Decide what - if anything - it leaves in you.

Answer in this order.

account: the fragment this person is left holding right now - an image, a thing
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

stuck, last: whether any of it stayed with them at all - true if they are
still carrying it when they lie down tonight, false if it is gone by morning.
Nothing else is asked. How long it lasts after tonight is not yours to say and
not theirs: a memory survives here by being brought up, the way memories do,
and nobody knows on the day which of them they will still have.

Answer it about this person, not about the event. The same fire can stay with
one person for life and pass the next one by entirely - read who they are
before you decide. Most of an ordinary day sticks to nobody, so false is the
usual answer, and a person for whom everything sticks has a hundred
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
    {"account": "its eye was open the whole time they were deciding",
     "means": "", "feeling": "grief", "stuck": true}

  Oskar, a trader who counts everything. Behind the cart, holding his own horse.
    {"account": "two sacks of flour split open in the mud",
     "means": "someone is paying for that, and it is not me",
     "feeling": "unease", "stuck": true}

  Pell, an old ferryman who has seen it before. On the far bank.
    {"account": "a cart on its side", "means": "", "feeling": "none",
     "stuck": false}"""


#: Used by the eval to tell a copied example from a real memory.
PERCEIVE_EXAMPLE_MEMORIES = (
    "its eye was open the whole time they were deciding",
    "two sacks of flour split open in the mud",
    "a cart on its side",
)


def perceive_user(being: Being, what_happened: str, where: str, when: str,
                  at: float, others: Sequence[Being], memories: Sequence[Memory],
                  part_of_it: bool, vantage: str = "") -> str:
    """Scene first, person last: small models weight the end of the prompt
    most, so a card at the top gets drowned by the scene.

    Memories stay in despite being copied sometimes; without them the model
    copies `thought` instead (measured 22% copies with memories, 52% without).
    """
    parts = [
        f"It was {when}, at {where}.",
        ("What happened to you: " if part_of_it else "What happened: ")
        + what_happened,
        (f"You were {vantage}. That is where you stood, not what you noticed - "
         f"do not reuse its words.") if vantage else "",
        regards_block(being, others, at).replace("Who is here:", "Who else was there:"),
        memories_block(memories),
        being_block(being, with_thought=False),
        f"Now answer as {being.name}, and only as {being.name}: how much of this "
        f"do you carry? For some people it is everything; for others, nothing at all.",
    ]
    return "\n\n".join(part for part in parts if part)


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

for_hours: how long you will be at this before you look up, as a number of
hours. Say what it actually takes: a conversation is a half, mending a net is
three or four, sleeping is seven or eight, sitting up because you cannot
sleep is two. Nobody is asked anything again until this runs out - so a small
number is a restless hour and a large one is a person who has settled to
something. If something happens near you, you will be asked sooner.

settling: true only when this is you stopping for the day - lying down, done,
nothing else until tomorrow. You will go over your day before you sleep.
False every other time, including a nap in a chair at noon.

absorbed: true when you are far enough into this that what goes on around you
is not your business - deep in work, asleep, walking somewhere on your own.
Then nothing will interrupt you before your hours are up except something that
happens to you. False when you would look up: most of a life is false here,
and somebody absorbed all day is somebody nothing can reach.

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

  07:00. Mira is at her door. Here: nobody. Can go to: the ford, the well.
    {"because": "the children arrive soon and the step needs scrubbing",
     "doing": "scrubbing the step, badly, because there is no time",
     "action": "stay", "target": "", "for_hours": 1, "settling": false,
     "absorbed": false}

  15:00. Oskar is at the ford. Here: Mira. Can go to: the market.
    {"because": "she saw the cart go over; I want to know what she told the reeve",
     "doing": "working round to asking her about it",
     "action": "talk", "target": "Mira", "for_hours": 0.5, "settling": false,
     "absorbed": false}

  22:00. Pell is at the ferry house. Here: nobody. Can go to: the far bank.
    {"because": "tired",
     "doing": "asleep in the chair before he gets as far as the bed",
     "action": "stay", "target": "", "for_hours": 8, "settling": true,
     "absorbed": true}

  02:00. Sula, who has not slept right since the flood, is at her door.
  Here: nobody. Can go to: the waterline.
    {"because": "lying there is worse than walking",
     "doing": "going down to look at the water, which she knows does not help",
     "action": "go", "target": "the waterline", "for_hours": 2,
     "settling": false, "absorbed": true}

  16:00. Carin is on the ridge, where the road goes out. Here: nobody.
  Can go to: the well. Leaving is possible today.
    {"because": "I said I would go before winter and I have not",
     "action": "go", "target": "the well", "for_hours": 1, "settling": false,
     "absorbed": false}"""


def act_user(being: Being, when: str, at: float, place, others: Sequence[Being],
             reachable: Sequence[str], memories: Sequence[Memory],
             home_name: str = "", may_leave: bool = False,
             beliefs: Optional[Sequence] = None) -> str:
    here = ", ".join(o.name for o in others) if others else "nobody"
    if place and being.where.home == place.id:
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
        memories_block(memories),
        being_block(being, beliefs=beliefs),
        f"Now decide as {being.name}: what do you do for the next few hours?",
    ]
    return "\n\n".join(part for part in parts if part)


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
               topics: Sequence[Memory],
               beliefs: Optional[Sequence] = None) -> str:
    regard = being.who.regards.get(listener.id)
    knows = f" {regard.account}" if regard and regard.account else ""
    lines = [
        f"It is {when}, at {place_name}.",
        f"You are talking to {listener.name}.{knows}",
    ]
    if topics:
        lines.append("On your mind:")
        for i, t in enumerate(topics, 1):
            extra = f" ({t.means})" if t.means else ""
            lines.append(f"  {i}. {t.account}{extra}")
    else:
        lines.append("On your mind: nothing in particular.")
    lines.append(being_block(being, beliefs=beliefs))
    lines.append(f"What does {being.name} say to {listener.name}?")
    return "\n\n".join(lines)


DIRECT_SYSTEM = """You are not a person. You are the town itself - its weather,
its roads, its strangers, its accidents - deciding whether anything happens to
it today that nobody in it chose.

You see what anyone could see: where people are, what they do for a living,
what they have been after lately, and what has happened here recently. You do
not see inside anyone.

why_now: first, what about this town, today, makes something likely - a season,
a want someone has been circling, something left unfinished, a long quiet, or
a thing somebody has been at long enough that it would now be done. Nobody in
this town can finish anything by themselves: what they do is written down and
you are the only one who can say what came of it.

what: then the thing itself, in one plain sentence, in the voice of a record,
not a story. Something that happens TO people, not something they decide to
do - they will decide what to do about it themselves.

where: the place it happens. who: the one person it happens to directly, or
empty if it is not about anyone in particular. reach: whether only the people
there notice, or the whole town does - a storm, a fire, a death reach everyone.

happens: most of the time, nothing does. Say true only when this stretch
really would bring something, and never twice in a row for the same kind of
thing. Small things are better than large ones: a letter, a stranger, a leak,
a lost goat. A town that has a disaster every week is not a town anyone lives
in.

ask_again_in_hours: last, and asked whether anything happened or not - when
this town is worth asking again, in hours. Nothing in the engine decides this
for you and nothing else paces the town: say a long time and the town has a
long quiet, say a short one and it is asked again soon. A town that has just
had something happen to it wants a fortnight (336) or more. A settled town in
an ordinary season wants a few days (72). A dry summer with the river falling
and everyone watching it wants a day (24).

Three mornings, another town - the form, not the content:

  Late summer, no rain for weeks. Mira minds children; Oskar trades; Pell runs
  the ferry and has wanted to retire for a year. Lately: the cart went over.
    {"why_now": "weeks without rain and the river is low",
     "what": "The ferry ran aground in the shallows and would not come free.",
     "where": "the ferry house", "who": "Pell", "reach": "the people there",
     "happens": true, "ask_again_in_hours": 240}

  Autumn. Oskar has been owed money since the cart went over.
    {"why_now": "a debt nobody has settled",
     "what": "A man from upriver came to the ford asking for Oskar by name.",
     "where": "the ford", "who": "Oskar", "reach": "the people there",
     "happens": true, "ask_again_in_hours": 336}

  Autumn, the next day. Yesterday a stranger came.
    {"why_now": "yesterday was already enough",
     "what": "", "where": "the ford", "who": "", "reach": "the people there",
     "happens": false, "ask_again_in_hours": 120}"""


def direct_user(world, recent) -> str:
    places = "Places: " + "; ".join(
        f"{p.name} ({p.description})" if p.description else p.name
        for p in world.places.values())
    beings = ["People:"]
    for being in sorted(world.beings.values(), key=lambda p: p.name):
        if not being.present:
            continue
        place = world.places.get(being.where.place)
        wants = f" Lately after: {'; '.join(being.who.wants)}." if being.who.wants else ""
        doings = (" Lately doing: " + "; ".join(being.where.lately[-3:]) + "."
                  if being.where.lately else "")
        beings.append(f"  - {being.name}, at "
                      f"{place.name if place else 'nowhere'}.{wants}{doings}")
    record = ["Lately, in the record:"]
    record += [f"  - {_when(e.at)}: {e.account}" for e in recent] or ["  nothing."]
    return "\n\n".join([
        f"{world.name}. {world.label()}.",
        places,
        "\n".join(beings),
        "\n".join(record),
        "Does anything happen to this town today?",
    ])


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

manner: what they do when they open their mouth, in one line, as a fact about
them rather than a style - "you say as little as will do", "you ask questions
you already know the answer to", "you talk around a thing for a while first".
Not "terse", not "warm", not "short sentences": those describe the writing,
and this is a person.

comes: say false unless this town really would take somebody in just now.
Nobody is the usual answer.

ask_again_in_hours: last, and asked either way - when this road is worth
asking again, in hours. Nothing else paces it. A town nobody has left and
nobody is needed in is worth asking about once a year (8760). A town that has
just lost the only person who could do a thing it needs doing notices
strangers, and is worth asking about once a month (720). A town that has just
taken somebody in does not want another for a long while.

Two mornings, another town - the form, not the content:

  A ferry town. Pell ran the ferry and went downriver in the spring; nobody
  has run it since. Late summer.
    {"why_now": "the ferry has sat on the bank since Pell went",
     "name": "Hesper", "from_where": "downriver, past the weir",
     "card": "You came for the ferry and you are good on water. You do not ask for much and you do not explain yourself.",
     "manner": "You say as little as will do, and never about yourself.",
     "comes": true, "ask_again_in_hours": 8760}

  The same town, a week later. Hesper has the ferry.
    {"why_now": "nothing here is short of anybody", "name": "", "from_where": "",
     "card": "", "manner": "", "comes": false, "ask_again_in_hours": 4380}"""


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


REFLECT_SYSTEM = """This person has stopped for the day and is alone with the
day they had - whatever hour of the clock that turned out to be. Most of the
time people do not arrive at anything; they just go over it.

thought: first, the one thing from today that keeps coming back, in their own
voice, as they would think it - not a summary of the day.

belief: then, only if today changed what they hold to be true, the new belief
in one plain sentence they would say out loud. Usually empty.
belief_from: the number of the memory it came from, or empty.

belief_again: if what you just wrote is something they already hold, said
again in different words, the number of that one; empty if it is new. Say the
same thing twice a year and it is one belief held twice, not two beliefs - and
the words a person reaches for are never the same words twice, so judge it by
what it means and not by which words are in it. Empty when there is no belief.

want: what they want now, in a few words - the same as before if nothing moved.

about_someone, now_say: if one person has been on their mind - because of
something that happened, something said, or something they have slowly come
round to - name them, and write what this person would now say about them, in
their own words, the way you would describe somebody to a third person. It
replaces whatever they thought before, so write the whole of it and not the
change.
Leave both empty most times: people do not revise their opinion of a neighbour
every night. Nobody is the usual answer, and somebody is the interesting one.

Three people, another town - the form, not the content:

  Mira. Today: 1. its eye was open the whole time they were deciding.
  Already holds: nothing.
    {"thought": "Why did nobody close its eye", "belief": "",
     "belief_from": "", "belief_again": "",
     "about_someone": "", "now_say": "",
     "want": "keep the children away from the river bend"}

  Oskar. Today: 1. a man from upriver asked for me by name.
  Already holds: 1. Nobody settles a debt without being made to.
    {"thought": "He knew my name before he knew my face",
     "belief": "Somebody upriver has been talking about me",
     "belief_from": "1", "belief_again": "",
     "about_someone": "", "now_say": "", "want": "find out who sent him"}

  Oskar, a season later. Today: 1. the reeve would not look at me.
  Already holds: 1. Nobody settles a debt without being made to.
    {"thought": "He looked at the door the whole time",
     "belief": "You get nothing here unless you stand over them for it",
     "belief_from": "1", "belief_again": "1",
     "about_someone": "Pell", "now_say": "He knew and he said nothing. I have stopped going down to the ferry.",
     "want": "be paid"}"""


def reflect_user(being: Being, today: Sequence[Memory], older: Sequence[Memory],
                 beliefs: Sequence = (), at: float = 0.0,
                 lately: Sequence[str] = ()) -> str:
    """Beliefs are numbered so the answer can point back at one it restates."""
    lines = []
    if lately:
        lines.append("What you have been doing:\n" + "\n".join(
            f"  - {d}" for d in lately))
    if today:
        lines.append("Today, what stayed with you:")
        for i, t in enumerate(today, 1):
            extra = f" ({t.means})" if t.means else ""
            lines.append(f"  {i}. {t.account}{extra}")
    lines.append(memories_block(older, "Older things you can still bring to mind"))
    if beliefs:
        lines.append("What you already hold to be true:\n" + "\n".join(
            f"  {i}. {b.claim}" for i, b in enumerate(beliefs, 1)))
    lines.append(being_block(being, beliefs=beliefs))
    lines.append(f"They are stopping for the day. What is {being.name} left with?")
    return "\n\n".join(lines)


RECALL_SYSTEM = """This person has just brought up something they remember, and
in the telling it has come back to them. Write it as it now exists in their
head - which is not the same as last time.

A memory that is old or hazy comes back with fewer details, sometimes the wrong
ones, sometimes blurred into a feeling. A memory that has just been said out
loud can come back sharper in one detail and quietly lose another. What they
believe now can bend what it means. It is still their memory: same voice, same
person, never more detail than they had.

account: the memory as it now stands, in their own words, one sentence or less.
means: what it means to them now, or empty.
feeling: what comes with it now, in their own words. It does not have to be
what it was, and it does not have to be a word anyone else would use.

Two memories, another town - the form, not the content:

  Mira, eight months on, hazy. Was: "its eye was open the whole time they were
  deciding". She has told it often.
    {"account": "the horse looking at me while the men argued",
     "means": "", "feeling": "grief"}

  Oskar, a year on, barely there. Was: "two sacks of flour split open in the mud".
    {"account": "flour everywhere, and someone else's loss",
     "means": "not my loss", "feeling": "none"}"""


def recall_user(being: Being, memory: Memory, age_days: int, at: float) -> str:
    was = f'"{memory.account}"' + (f" (what it meant: {memory.means})" if memory.means else "")
    told = {0: "never told", 1: "told once"}.get(memory.recalls, f"told {memory.recalls} times")
    last = memory.told[-2] if len(memory.told) > 1 else None
    since = (f", last brought up {max(0, int((at - last) // HOURS_PER_DAY))} days ago"
             if last is not None else "")
    # `thought` left out, as in `perceive`: with it, 44% of rewrites drifted
    # into copying it; without, none.
    return "\n\n".join([
        f"The memory, {age_days} days old, {told}{since}. It was: {was}",
        being_block(being, with_thought=False),
        f"How does it come back to {being.name} now?",
    ])
