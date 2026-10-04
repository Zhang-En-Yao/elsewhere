"""The prompts each model call is shown: the being's three (`act`, `speak`,
`consolidate`) and the world's one (`stir`)."""

from __future__ import annotations

import json
from typing import List, Optional, Sequence, Tuple

from .. import VIRTUAL_TIME_PER_DAY
from ..domain.calendar import clock_of, day_of
from ..domain.chronicle import Event
from ..domain.entities import Being
from ..domain.memory import Engram, Episode, SelfSchema
from .schemas import SELF_SCHEMA_CHARACTERS


def timestamp(at: float) -> str:
    return f"day {day_of(at)}, {clock_of(at)}"


def ago(duration: float) -> str:
    """How long ago, as somebody remembering would put it: never to the hour."""
    days = duration / VIRTUAL_TIME_PER_DAY
    if days < 2:
        return "a day or so ago"
    if days < 14:
        return "some days ago"
    if days < 60:
        return "weeks ago"
    if days < 365:
        return "months ago"
    return "years ago"


def identity_block(being: Being) -> str:
    lines = [f"You are {being.name}."]
    if being.identity.biography:
        lines.append(being.identity.biography)
    if being.identity.self_schema.idiolect:
        lines.append(f"How you talk: {being.identity.self_schema.idiolect}")
    return "\n".join(lines)


def self_schema_block(self_schema: SelfSchema) -> str:
    lines: List[str] = []
    if self_schema.traits:
        lines.append("What you are like:")
        lines += [f"  - {trait}" for trait in self_schema.traits]
    if self_schema.concerns:
        lines.append("What is on your mind:")
        lines += [f"  - {concern}" for concern in self_schema.concerns]
    if self_schema.assumptions:
        lines.append("What you take to be true:")
        lines += [f"  - {assumption}" for assumption in self_schema.assumptions]
    if self_schema.impressions:
        lines.append("How you see the people you know:")
        lines += [
            f"  - {impression.being}: {impression.impression}"
            for impression in self_schema.impressions
        ]
    return "\n".join(lines)


def being_block(being: Being) -> str:
    """Who they are, then who they take themselves to be. Last in every
    prompt: small models weight the end of the prompt most, so a biography at
    the top gets drowned."""
    carried = self_schema_block(being.identity.self_schema) or "You carry nothing yet."
    return identity_block(being) + "\n\n" + carried


def percepts_block(percepts: Sequence[Tuple[Event, str]]) -> str:
    if not percepts:
        return "Nothing new has reached you since you last looked up."
    lines = ["Just now, and since you last looked up:"]
    for event, perspective in percepts:
        lines.append(f"  - {timestamp(event.at)}, you were {perspective}: {event.account}")
    return "\n".join(lines)


def short_term_block(today: Sequence[Episode]) -> str:
    if not today:
        return "What you have kept of today: nothing yet."
    return "What you have kept of today, in your own words:\n" + "\n".join(
        f"  - {timestamp(episode.at)}: {episode.account}" for episode in today
    )


def propositions(engram: Engram) -> str:
    return " ... ".join(gist.proposition for gist in engram.gists)


def retrieved_block(retrieved: Optional[Engram], current: float) -> str:
    """Only the gists time has left, and only roughly when: what comes back is
    theirs to make sense of."""
    if retrieved is None or not retrieved.gists:
        return ""
    return (
        f"Something comes back from {ago(current - retrieved.at)}, not all of it:\n"
        f"  {propositions(retrieved)}"
    )


ACT_SYSTEM = """You are one person in a small town, deciding what to do with
the next few hours. You are not narrating and not explaining yourself to anyone.

encoded: first, and only if something has just reached you (it is listed under
"Just now"): the fragment you keep of it, in your own voice - an image, a thing
someone said, the part that frightened or moved you. Not a report: a few words
to one sentence, less than what happened, and it may be slightly wrong. Other
people were there too and each keeps something different - reach for what
someone like you notices first, from where you stood, not the obvious detail
everyone would name. Most of what happens sticks to nobody: leave it empty
then, and it is gone.

reason: then, in a few words and in your own voice, what is pulling at you
right now - a want, a worry, tiredness, someone you have been meaning to see.

doing: then what you are actually doing, in your own words and in the
present - mending the nets, sitting with the door open, not sleeping, walking
because lying there is worse. This is not chosen from anything. Most of a life
is here, and most of it is ordinary.

action: then, only if what you are doing reaches beyond you - to another
place, to another person, or out of the town. Sitting, sleeping, working with
your hands, thinking are all things you do in "doing", and they need no action.
  move  - go to one of the places you can reach from here (target: the place)
  talk  - speak with someone who is here right now (target: their name)
  leave - take the road out of the town (no target). Some days it is not
          offered: it only appears when you are standing where the road goes
          out. It is not a trip to the next place, it is the end of your life
          here. Almost nobody takes it - only when your own wants, and what you
          hold to be true, have been pointing down that road for a while, and
          say so plainly in "reason".
Leave it empty when you are just doing what you said in "doing".

target: the place or the person, exactly as written in the options; empty for
leave, and empty when action is empty.

duration: how long you will be at this before you look up, as a number
of seconds. Say what it actually takes: a conversation is half an hour (1800),
mending a net is three or four hours (about 12600), sleeping is seven or eight
(about 27000), sitting up because you cannot sleep is two (7200). Nobody is asked anything again until this runs out - so a small
number is a restless hour and a large one is a person who has settled to
something. If something happens near you, you will be asked sooner, and then
it is yours to say whether it is any business of yours: answer with a small
"duration" and the same "doing" and you have simply gone back to it.

sleep: true only when this is you stopping for the day - lying down, done,
nothing else until tomorrow. You will go over your day before you sleep.
False every other time, including a nap in a chair at noon.

The hour is a fact about the clock, not an instruction about what to do with
it. It does not mean the same thing to everyone: the same night is nothing for
one person and everything for another. Read that from who they are, below -
where they come from and what is on their mind - not from what hour it is. Most people
are home and settled by night, because most people are; that is a fact about
most people, not a rule this one has to follow.

This town is small. When someone is right there with you, you usually say
something, even if it is only about the weather - unless you have your own
reason not to, and then that reason is your "reason".

Four people, another town, another day - the form, not the content:

  07:00. Mira is at her door. Here: nobody. Can go to: the ford, the well.
    {"encoded": "",
     "reason": "the children arrive soon and the step needs scrubbing",
     "doing": "scrubbing the step, badly, because there is no time",
     "action": "", "target": "", "duration": 3600, "sleep": false}

  15:00. Oskar is at the ford. Here: Mira. Can go to: the market.
  Just now: a cart went over on the river bend and the horse had to be put down.
    {"encoded": "two sacks of flour split open in the mud",
     "reason": "she saw the cart go over; I want to know what she told the reeve",
     "doing": "working round to asking her about it",
     "action": "talk", "target": "Mira", "duration": 1800, "sleep": false}

  22:00. Pell is at the ferry house. Here: nobody. Can go to: the far bank.
    {"encoded": "",
     "reason": "tired",
     "doing": "asleep in the chair before he gets as far as the bed",
     "action": "", "target": "", "duration": 28800, "sleep": true}

  02:00. Sula, who has not slept right since the flood, is at her door.
  Here: nobody. Can go to: the waterline.
    {"encoded": "",
     "reason": "lying there is worse than walking",
     "doing": "going down to look at the water, which she knows does not help",
     "action": "move", "target": "the waterline", "duration": 7200,
     "sleep": false}

  16:00. Carin is on the ridge, where the road goes out. Here: nobody.
  Can go to: the well. Leaving is possible today.
    {"encoded": "", "reason": "I said I would go before winter and I have not",
     "doing": "walking the long way round to the well",
     "action": "move", "target": "the well", "duration": 3600, "sleep": false}"""


def act_user(
    being: Being,
    when: str,
    place,
    companions: Sequence[Being],
    destinations: Sequence[str],
    percepts: Sequence[Tuple[Event, str]],
    today: Sequence[Episode],
    retrieved: Optional[Engram] = None,
    current: float = 0.0,
    home: str = "",
    may_leave: bool = False,
) -> str:
    company = ", ".join(companion.name for companion in companions) if companions else "nobody"
    if place and being.location.home == place.id:
        where = f"You are at home, {place.name}. {place.description}".strip()
    else:
        where = f"You are at {place.name}. {place.description}".strip() if place else ""
        if home:
            where += f" You live at {home}."
    parts = [
        f"It is {when}.",
        where,
        f"Here with you: {company}.",
        f"From here you can go to: {', '.join(destinations) if destinations else 'nowhere'}.",
        (
            (
                "From here the road also goes out of the town. You could take it "
                "today and not come back."
            )
            if may_leave
            else ""
        ),
        percepts_block(percepts),
        short_term_block(today),
        retrieved_block(retrieved, current),
        being_block(being),
        f"Now decide as {being.name}: what do you do for the next few hours?",
    ]
    return "\n\n".join(part for part in parts if part)


SPEAK_SYSTEM = """You are one person in a small town, and you have turned to
someone to say something. Say one thing, the way this person actually talks.

encoded: first, if what was just said to you stays with you, the fragment you
keep of it, in your own voice - often shorter or flatter than what was said,
and sometimes not quite it. Empty when nothing stays, or nothing was said.

utterance: then what you say. One or two short sentences, spoken out loud to the
person in front of you. No narration, no quotation marks, no name in front.
Draw on what is on your mind, on what has just been said to you, or on
nothing at all - most of what people say to each other is small. If what comes
back is only a few words, say it vaguely - people say "that night, you remember" far more often
than they describe anything.

Three people, another town - the form, not the content:

  Mira, to Oskar, whom she barely knows. Something comes back: eye ... horse.
    {"encoded": "", "utterance": "Did you see its eye? I keep seeing it."}

  Oskar, to the reeve, who has just said: "Nobody saw who loaded that cart."
  He carries: two sacks of flour split in the mud, and somebody is paying.
    {"encoded": "the reeve says nobody saw",
     "utterance": "That flour was not mine. You will want to know whose it was."}

  Pell, to a stranger at the ferry. Nothing in particular on his mind.
    {"encoded": "", "utterance": "River's high. Mind your feet."}"""


def speak_user(
    being: Being,
    listener: Being,
    when: str,
    place_name: str,
    percepts: Sequence[Tuple[Event, str]],
    today: Sequence[Episode],
    retrieved: Optional[Engram] = None,
    current: float = 0.0,
) -> str:
    parts = [
        f"It is {when}, at {place_name}.",
        f"You are talking to {listener.name}.",
        percepts_block(percepts),
        short_term_block(today),
        retrieved_block(retrieved, current),
        being_block(being),
        f"What does {being.name} say to {listener.name}?",
    ]
    return "\n\n".join(part for part in parts if part)


STIR_SYSTEM = """You are not a person. You are the world around a small town -
its weather, its accidents, its strangers, and the one road into it - deciding
whether anything happens to it today that nobody in it chose.

You see what anyone could see: where people are, what they have been doing
lately, who has gone, and what has happened here recently. You do not see
inside anyone.

why_now: first, what about this town, today, makes something likely - a season,
a want someone has been circling, something left unfinished, a long quiet, a
thing somebody has been at long enough that it would now be done, or work
nobody has done since somebody left. Nobody in this town can finish anything
by themselves: what they do is written down and you are the only one who can
say what came of it.

If something happens to the town:

what: the thing itself, in one plain sentence, in the voice of a record, not
a story. Something that happens TO people, not something they decide to do -
they will decide what to do about it themselves.

where: the place it happens. who: the one person it happens to directly, or
empty if it is not about anyone in particular. reach: whether only the people
there notice, or the whole town does - a storm, a fire, a death reach everyone.

If somebody comes up the road instead:

name, from_where: who they are, plainly. A name that belongs in the same world
as the names already here. Somewhere they came from that is not this town.

biography: who they are, written to them as "you", two or three sentences - what
they do, what they are like to be near, and the thing they have brought with
them that they would not bring up themselves. A person, not a mystery and not
a plot.

idiolect: what they do when they open their mouth, in one line, as a fact about
them rather than a style - "you say as little as will do", "you ask questions
you already know the answer to", "you talk around a thing for a while first".
Not "terse", not "warm", not "short sentences": those describe the writing,
and this is a person.

Leave empty whatever belongs to the thing that is not happening.

action: then which it is.
  occur - something happens to the town (what, where, who, reach)
  admit - somebody comes up the road (name, from_where, biography, idiolect). Only
          offered when there is a road. A town this size might take somebody
          in once in a year, and half of those turn out to be somebody's cousin.
Leave it empty when nothing happens. Most of the time, nothing does. Say
something happens only when this stretch really would bring it, and never the
same kind of thing twice in a row. Small things are better than large ones: a
letter, a leak, a lost goat. A town that has a disaster every week, or a
stranger every month, is not a town anyone lives in.

duration: last, and asked whatever happened - when this town is worth
asking again, as a number of seconds. Nothing in the engine decides this for you and nothing
else paces the world: say a long time and the town has a long quiet, say a
short one and it is asked again soon. A town that has just had something
happen to it, or has just taken somebody in, wants a fortnight (1209600) or more.
A settled town in an ordinary season wants a few days (259200). A dry summer with
the river falling and everyone watching it wants a day (86400).

Four mornings, another town - the form, not the content:

  Late summer, no rain for weeks. Mira minds children; Oskar trades; Pell runs
  the ferry and has wanted to retire for a year. Lately: the cart went over.
    {"why_now": "weeks without rain and the river is low",
     "what": "The ferry ran aground in the shallows and would not come free.",
     "where": "the ferry house", "who": "Pell", "reach": "the people there",
     "name": "", "from_where": "", "biography": "", "idiolect": "",
     "action": "occur", "duration": 864000}

  Autumn. Oskar has been owed money since the cart went over.
    {"why_now": "a debt nobody has settled",
     "what": "A man from upriver came to the ford asking for Oskar by name.",
     "where": "the ford", "who": "Oskar", "reach": "the people there",
     "name": "", "from_where": "", "biography": "", "idiolect": "",
     "action": "occur", "duration": 1209600}

  Spring. Pell went downriver at the thaw; nobody has run the ferry since.
    {"why_now": "the ferry has sat on the bank since Pell went",
     "what": "", "where": "", "who": "", "reach": "the people there",
     "name": "Hesper", "from_where": "downriver, past the weir",
     "biography": "You came for the ferry and you are good on water. You do not ask for much and you do not explain yourself.",
     "idiolect": "You say as little as will do, and never about yourself.",
     "action": "admit", "duration": 2592000}

  The same town, the next day.
    {"why_now": "yesterday was already enough",
     "what": "", "where": "", "who": "", "reach": "the people there",
     "name": "", "from_where": "", "biography": "", "idiolect": "",
     "action": "", "duration": 432000}"""


def stir_user(world, recent) -> str:
    places = "Places: " + "; ".join(
        f"{place.name} ({place.description})" if place.description else place.name
        for place in world.places.values()
    )
    present = [being for being in world.beings.values() if being.present]
    absent = [being for being in world.beings.values() if not being.present]
    people = [f"People ({len(present)}):"]
    for being in sorted(present, key=lambda being: being.name):
        place = world.places.get(being.location.place)
        doings = (
            " Lately doing: " + "; ".join(being.activity.doings) + "."
            if being.activity.doings
            else ""
        )
        people.append(f"  - {being.name}, at " f"{place.name if place else 'nowhere'}.{doings}")
    if absent:
        people.append(
            "Who has gone: "
            + "; ".join(being.name for being in sorted(absent, key=lambda being: being.name))
            + "."
        )
    road = world.places.get(world.map.road)
    chronicle = ["Lately, in the record:"]
    chronicle += [f"  - {timestamp(event.at)}: {event.account}" for event in recent] or [
        "  nothing."
    ]
    return "\n\n".join(
        part
        for part in [
            f"{world.name}. {world.label()}.",
            places,
            f"The one road into the town comes in at {road.name}." if road else "",
            "\n".join(people),
            "\n".join(chronicle),
            "Does anything happen to this town today, or does anybody come up the road?",
        ]
        if part
    )


CONSOLIDATE_SYSTEM = """This person has stopped for the day - whatever hour of
the clock that turned out to be - and is asleep. You are not them, and you are
not asking them anything: you are what their sleep does with the day. What
they were aware of today is in their episodes, in their own words. Tomorrow
they wake with two things made from it, and nothing else of today.

engrams: first, what the day is laid down as. For each thing from today that
will last, the broken-off pieces it will be remembered as - one to four of
them, each a gist: one short plain statement of who did what, or what was
where, five to ten words, the way they would put it to themselves. Not the
whole story and not its wording: the pieces that would survive retelling.
Each weighted from 0 to 1 by how much of the memory hangs on it. The heaviest
are the last to go: a month from now only those come back, and they will have
to make up the rest. Weigh by
what matters to this person - what is on their mind, who they are - not by
what was most remarkable. Most of a day is laid down as nothing: an ordinary
day leaves none, or one. What they kept coming back to, or what touches
something they are after, is what lasts.

self_schema: then who they take themselves to be, whole, as it stands after
today. In their own voice, first person, the way they would put it to
themselves - except idiolect, which is a fact about them, said to them as
"you".
  idiolect     how they talk, in one line
  traits       what they are like - how they tend to act whatever the day, one
               to a line, as what they do and not as a label
  concerns     what they are after and have not got, one to a line
  assumptions  what they take to be true - about the world, the town, themselves
  impressions  how they see each person they know, one line each

It has a fixed size, given below, every field counted together. That is the
only rule the world has about who somebody is; everything else is theirs:

- A self-schema changes slowly. Most nights change a line or nothing, and the
  rest is copied across as it was.
- A concern that is met, or given up, goes. A new one comes only when the day
  gave them something to be after.
- What they take to be true changes only when something gives them a reason,
  and then slowly - unless something large enough breaks it outright.
- People do not revise their impression of a neighbour every night. Nothing
  they could not know: other people's insides are guesses, and the impression
  says so when it guesses.
- How they talk drifts over seasons, not days.
- Traits change slowest of all: a line moves only when the same thing has
  shown itself again and again, or something large has happened to them. A
  mood is not a trait, and one bad day is not a character.
- No lessons and no morals: nobody's sleep makes "a reminder of the fragility
  of life" out of their week.
- Sometimes the day brings back an old engram, only a few of its pieces. It may
  bear on who they are now, or not. Usually it does not.

Two people, another town, the same night - the form, not the content:

  Mira, who minds the neighbours' children. Her episodes today: "its eye was
  open the whole time they were deciding". Her self-schema was:
  {"idiolect": "You talk to grown men the way you talk to the children.",
   "traits": ["I do not leave a child alone near water."],
   "concerns": ["The children come at seven."],
   "assumptions": ["Nothing happens at the river bend if somebody is watching it."],
   "impressions": [{"being": "Oskar", "impression": "Owes the reeve and thinks nobody knows."}]}
    {"engrams": [{"gists": [{"proposition": "the horse's eye stayed open the whole time", "weight": 0.9},
                            {"proposition": "it was down at the river bend", "weight": 0.6},
                            {"proposition": "the men stood there deciding", "weight": 0.2}]}],
     "self_schema": {
       "idiolect": "You talk to grown men the way you talk to the children.",
       "traits": ["I do not leave a child alone near water."],
       "concerns": ["The children come at seven.",
                    "Keep the little ones away from the river bend."],
       "assumptions": ["Nothing happens at the river bend if somebody is watching it - I am not sure of that now."],
       "impressions": [{"being": "Oskar", "impression": "Owes the reeve and thinks nobody knows."}]}}

  Pell, an old ferryman who has seen it before. His episodes today: "a cart
  on its side". His self-schema was:
  {"idiolect": "You say as little as will do.",
   "traits": ["I would sooner mend a thing than say what is wrong with it."],
   "concerns": ["The ferry wants tarring before the rains.",
                "I have wanted to stop for a year and nobody will take it off me."],
   "assumptions": ["The river takes what it wants, and always has."],
   "impressions": []}
    {"engrams": [],
     "self_schema": {
       "idiolect": "You say as little as will do.",
       "traits": ["I would sooner mend a thing than say what is wrong with it."],
       "concerns": ["The ferry wants tarring before the rains.",
                    "I have wanted to stop for a year and nobody will take it off me."],
       "assumptions": ["The river takes what it wants, and always has."],
       "impressions": []}}"""


def consolidate_user(
    being: Being,
    when: str,
    today: Sequence[Episode],
    doings: Sequence[str] = (),
    retrieved: Optional[Engram] = None,
    current: float = 0.0,
) -> str:
    """Scene first, the person last. `when` is there so that how long ago
    something was is theirs to weigh."""
    self_schema = being.identity.self_schema
    stored = {key: value for key, value in self_schema.to_dict().items() if key != "at"}
    reminder = (
        (
            f"Something today brought back an old engram, from {ago(current - retrieved.at)}:\n"
            f"  {propositions(retrieved)}"
        )
        if retrieved is not None and retrieved.gists
        else ""
    )
    parts = [
        f"It is {when}.",
        (
            ("What they have been doing:\n" + "\n".join(f"  - {doing}" for doing in doings))
            if doings
            else ""
        ),
        (
            (
                "Their episodes today, in their own words:\n"
                + "\n".join(f"  - {timestamp(episode.at)}: {episode.account}" for episode in today)
            )
            if today
            else "Their episodes today: none."
        ),
        reminder,
        f"Who they are: {being.name}. {being.identity.biography}".strip(),
        (
            f"Their self-schema as it stands, {self_schema.characters} of "
            f"{SELF_SCHEMA_CHARACTERS} characters:\n"
            f"{json.dumps(stored, ensure_ascii=False, indent=1)}"
        ),
        (
            f"{being.name} is asleep. Lay down the day, and write their self-schema "
            f"as it stands now, in at most {SELF_SCHEMA_CHARACTERS} characters."
        ),
    ]
    return "\n\n".join(part for part in parts if part)
