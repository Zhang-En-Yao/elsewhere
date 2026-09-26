"""The places where a mind is asked something, and the shape of the answer.

These schemas are the contract between the engine and whatever is thinking.
They are handed to the model as a grammar (Ollama's ``format``, vLLM guided
decoding) so the output is structurally valid by construction, and they are
checked again on the way in, because "structurally valid" and "usable" are not
the same thing.

Nothing here decides what a person feels. It only decides what a feeling looks
like once it has been written down.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Two things a mind is never given a vocabulary for, on purpose.
#
# A feeling is stored, printed, and handed back to a mind as text; not one
# line anywhere compares two of them or sorts by one. A list to pick from
# would be a constraint on a person for nobody's benefit.
#
# How much a memory weighs is not asked at all. What a memory is worth is how
# often anybody has had cause to think of it, which `retrieval` counts from
# `Trace.told` rather than taking anyone's word for on the day. The one thing
# a mind can actually answer about a moment it has just lived is whether any
# of it stayed - see PERCEIVE.

# Three verbs, because there are exactly three things the engine can do about
# an answer: move somebody, put two people in a conversation, or take somebody
# out of the world. What they are *doing* is not enumerated anywhere - it goes
# in `doing`, in their own words, and can be anything.
ACTIONS = ["stay", "go", "talk"]

# Not a fourth everyday verb. Leaving is added to the grammar only where the
# road actually goes out and only when the town can spare somebody, so a model
# that picks it has been standing somewhere that means it. See agents.may_leave.
LEAVE = "leave"      # a fourth, offered only where the road goes out

# Order matters under a grammar: keys are generated in the order they appear
# here, so a model asked for a verdict first commits to it in one token, before
# it has written a word about what happened. Every schema below therefore puts
# the reasoning and the description first and the decision last, so the
# decision is about something the model has already said.
#
# One field per decision, too. Two fields for one decision is how a model gets
# to contradict itself.
PERCEIVE = {
    "type": "object",
    "properties": {
        "trace": {"type": "string"},      # the fragment they are left holding
        "means": {"type": "string"},      # what they make of it, if anything
        "feeling": {"type": "string"},    # in their words, from no vocabulary
        "stuck": {"type": "boolean"},     # did any of it stay at all
    },
    "required": [],
}

# Reason, then what it looks like, then the verb: by the time a verb is picked
# they have already said what they are doing, and the verb is only which of
# three things the world must do about it. The last three fields are how this
# person schedules themselves - see `schedule`.
ACT = {
    "type": "object",
    "properties": {
        "because": {"type": "string"},
        "doing": {"type": "string"},
        # Leaving is in the vocabulary here and taken out again by act_grammar
        # wherever the road does not go. The inbound check stays lenient, the
        # way it is for every other field; the engine's own gate is what
        # actually stops somebody walking out of their kitchen.
        "action": {"type": "string", "enum": ACTIONS + [LEAVE]},
        "target": {"type": "string"},
        # How long they expect to be at it. This is the only thing anywhere
        # that says when they are asked anything again - the engine has no
        # step size. A person mending a net says four; a person who cannot
        # settle says one; a person going to bed says eight.
        #
        # A number of hours rather than "a few hours", so there is nothing to
        # parse. Non-positive or missing is not usable, and somebody who gives
        # nothing usable is woken when the world next stirs.
        "for_hours": {"type": "number"},
        # Whether this is them stopping for the day, which is the only thing
        # that sends anybody to `reflect`. Not an hour on a clock.
        "settling": {"type": "boolean"},
        # Whether anything short of the roof coming off gets their attention
        # before `for_hours` is up. Concordia's interrupt mask
        # (`interrupt_scheduling.InterruptMask`) with one bit instead of a
        # list of tag prefixes, because a town has four kinds of event and a
        # person does not think in prefixes. A thing that happens *to* them
        # reaches them regardless, which is what non-maskable means there.
        "absorbed": {"type": "boolean"},
    },
    "required": ["action"],
}

# What they draw on is chosen before the words are, so the words are about it.
SPEAK = {
    "type": "object",
    "properties": {
        "about": {"type": "string"},
        "line": {"type": "string"},
    },
    "required": ["line"],
}

# Remembering again: the words come back first, and may come back changed.
RECALL = {
    "type": "object",
    "properties": {
        "trace": {"type": "string"},
        "means": {"type": "string"},
        "feeling": {"type": "string"},
    },
    "required": ["trace"],
}

# Flat on purpose. A nested list of belief objects is more than a 3.8B model
# can reliably fill under a grammar; one thought, at most one belief, one want.
REFLECT = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "belief": {"type": "string"},
        "belief_from": {"type": "string"},
        # Whether this is a thing they already hold, said again. Asked of the
        # mind, because it is a question about meaning: "the river is not to
        # be trusted" and "I do not go down there after rain" are the same
        # belief or two, and no amount of word overlap settles which.
        "belief_again": {"type": "string"},
        "want": {"type": "string"},
        # Somebody who has been on their mind, and what they would now say
        # about them. This is the only thing in the world that rewrites a
        # `Regard`, and it rewrites one side of it.
        "about_someone": {"type": "string"},
        "now_say": {"type": "string"},
    },
    "required": [],
}

# What the town does to its people. The verdict comes last, after the director
# has said why now and what - and 'nothing' is always allowed.
REACH = ["the people there", "the whole town"]

DIRECT = {
    "type": "object",
    "properties": {
        "why_now": {"type": "string"},
        "what": {"type": "string"},
        "where": {"type": "string"},
        "who": {"type": "string"},
        "reach": {"type": "string", "enum": REACH},
        "happens": {"type": "boolean"},
        # When this town is worth asking again, in hours. Nothing else paces
        # the town: one that has just had a fire says a fortnight, one in a
        # dry summer with the river falling says a day.
        "ask_again_in_hours": {"type": "number"},
    },
    "required": ["happens"],
}

# Who comes up the road. Reason first and the verdict last, like DIRECT: the
# road says who this person would be before it says whether they are coming, so
# "nobody" is a decision about somebody rather than the cheapest token.
ARRIVE = {
    "type": "object",
    "properties": {
        "why_now": {"type": "string"},
        "name": {"type": "string"},
        "from_where": {"type": "string"},
        "card": {"type": "string"},
        "manner": {"type": "string"},
        "comes": {"type": "boolean"},
        # And when the road is worth asking again. Nothing else paces it: a
        # town short of nobody says a year, one that has just lost the only
        # person who could do a thing it needs doing says a month.
        "ask_again_in_hours": {"type": "number"},
    },
    "required": ["comes"],
}

BY_NAME: Dict[str, dict] = {
    "perceive": PERCEIVE, "act": ACT, "speak": SPEAK,
    "recall": RECALL, "reflect": REFLECT, "direct": DIRECT,
    "arrive": ARRIVE,
}

class Invalid(ValueError):
    """The answer came back in a shape the world cannot use."""


def validate(name: str, data: Any) -> Tuple[Optional[dict], Optional[str]]:
    """Check an answer against its schema.

    Returns ``(clean, None)`` or ``(None, complaint)``. The complaint is
    written to be handed straight back to the model as a repair instruction,
    so it says what was wrong rather than what a validator thinks.
    """
    schema = BY_NAME.get(name)
    if schema is None:
        return None, f"there is no call named {name!r}"
    if not isinstance(data, dict):
        return None, "the answer must be a single JSON object"

    clean: Dict[str, Any] = {}
    props = schema.get("properties", {})
    for key, rule in props.items():
        if key not in data:
            continue
        value = data[key]
        kind = rule.get("type")
        if kind == "boolean":
            if not isinstance(value, bool):
                return None, f"{key!r} must be true or false, not {value!r}"
        elif kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None, f"{key!r} must be a number, not {value!r}"
            value = float(value)
        elif kind == "string":
            if not isinstance(value, str):
                return None, f"{key!r} must be a string, not {value!r}"
            allowed = rule.get("enum")
            if allowed and value not in allowed:
                return None, (f"{key!r} must be one of {', '.join(allowed)}; "
                              f"{value!r} is not")
        elif kind == "array":
            if not isinstance(value, list):
                return None, f"{key!r} must be a list, not {value!r}"
        elif kind == "object" and not isinstance(value, dict):
            return None, f"{key!r} must be an object, not {value!r}"
        clean[key] = value

    for key in schema.get("required", []):
        if key not in clean:
            return None, f"{key!r} is required and was missing"

    return clean, None


def grammar(name: str) -> dict:
    """The schema as handed to a decoder: every field required.

    Under grammar-constrained decoding an optional field is an invitation to
    stop early: the shortest valid answer to PERCEIVE would be {"stuck": true},
    which says something stayed and nothing about what. The validator stays
    lenient, because a backend without grammar support may omit fields; the
    grammar does not.
    """
    import copy

    schema = copy.deepcopy(BY_NAME[name])
    schema["required"] = list(schema.get("properties", {}).keys())
    return schema


def act_grammar(places: List[str], beings: List[str],
                may_leave: bool = False) -> dict:
    """ACT with its target narrowed to what is actually there.

    A target chosen from what exists cannot be a place that is not adjacent or
    a person who is not in the room: the grammar makes the wrong answer
    unwritable rather than leaving the engine to repair it afterwards.

    The same applies to the verb. Leaving for good enters the vocabulary only
    where `agents.may_leave` has already said it is possible, so a model cannot
    walk somebody out of the world from their own kitchen.
    """
    schema = grammar("act")
    options = [""] + sorted(set(places) | set(beings))
    schema["properties"]["target"] = {"type": "string", "enum": options}
    schema["properties"]["action"] = {
        "type": "string", "enum": ACTIONS + ([LEAVE] if may_leave else [])}
    return schema


def speak_grammar(topics: int) -> dict:
    """SPEAK with 'about' narrowed to the numbered things they can bring to mind."""
    schema = grammar("speak")
    choices = ["nothing in particular"] + [str(i) for i in range(1, topics + 1)]
    schema["properties"]["about"] = {"type": "string", "enum": choices}
    return schema


def direct_grammar(places: List[str], beings: List[str]) -> dict:
    """DIRECT with where/who narrowed to what exists in this town."""
    schema = grammar("direct")
    schema["properties"]["where"] = {"type": "string", "enum": sorted(places)}
    schema["properties"]["who"] = {"type": "string", "enum": [""] + sorted(beings)}
    return schema


def reflect_grammar(sources: int, held: int = 0,
                    known: Optional[List[str]] = None) -> dict:
    """REFLECT with every pointer narrowed to something that exists.

    `belief_from` is one of today's numbered memories; `belief_again` is one of
    the beliefs this person already holds, which is how the engine learns that
    a belief is being restated rather than found; `about_someone` is a person
    they could actually have been thinking about. All three are enums, so none
    of them can name something that is not there.
    """
    schema = grammar("reflect")
    schema["properties"]["belief_from"] = {
        "type": "string", "enum": [""] + [str(i) for i in range(1, sources + 1)]}
    schema["properties"]["belief_again"] = {
        "type": "string", "enum": [""] + [str(i) for i in range(1, held + 1)]}
    schema["properties"]["about_someone"] = {
        "type": "string", "enum": [""] + sorted(known or [])}
    return schema
