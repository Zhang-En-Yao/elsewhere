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

# There is no list of feelings. There was one - thirteen words and "none" -
# and the engine never did anything with it: a feeling is stored, printed,
# and handed back to a mind as text, and not one line anywhere compares two
# of them or sorts by one. It was a vocabulary a person had to squeeze into
# for the engine's convenience, and the engine had no convenience in it.
#
# Compare `thought` in REFLECT, which has never been constrained and is
# whatever the day left somebody holding. Both are the same kind of thing.
# The unconstrained one was right.

# A small ladder instead of a float: a 4B model has no idea what 0.73 means,
# and neither does a person. The engine maps these onto numbers itself.
WEIGHTS = ["nothing", "faint", "ordinary", "stays", "marks"]

# Three, because the engine can only do three things about an answer: move
# somebody, put two people in a conversation, or take somebody out of the
# world. There used to be five - 'work' and 'rest' were in here too - and
# the engine did nothing with either of them except print a different canned
# sentence. They were a vocabulary a life had to be squeezed into so that the
# display could say "worked" instead of "rested".
#
# What somebody is doing is not the engine's to enumerate. It goes in `doing`,
# in their words, and 'work' and 'rest' are two of the infinite things it can
# say. 'make' and 'tend' come back with art (P5), because those two do change
# the world and so the engine does have to know them apart.
ACTIONS = ["stay", "go", "talk"]

# Not a fourth everyday verb. Leaving is added to the grammar only where the
# road actually goes out and only when the town can spare somebody, so a model
# that picks it has been standing somewhere that means it. See agents.may_leave.
LEAVE = "leave"      # a fourth, offered only where the road goes out

# Order matters under a grammar: keys are generated in this order, so a model
# that is asked "stuck?" first commits to an answer in one token, before it has
# written a word about what happened. Asking for the fragment first and the
# verdict last lets the decision be about something it has already said.
PERCEIVE = {
    "type": "object",
    "properties": {
        "trace": {"type": "string"},
        "means": {"type": "string"},
        "feeling": {"type": "string"},
        "weight": {"type": "string", "enum": WEIGHTS},
    },
    # One decision in one field. An earlier version also asked for a boolean
    # 'stuck', and a small model happily answered weight "stays", stuck false.
    "required": [],
}

# Reason, then what it looks like, then the verb - the same lesson as
# PERCEIVE: under a grammar the first key is committed before anything else
# is written, so the description comes before the classification rather than
# after it. By the time a verb is picked they have already said what they are
# doing, and the verb is only which of three things the world must do about it.
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
        "want": {"type": "string"},
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
    },
    "required": ["comes"],
}

BY_NAME: Dict[str, dict] = {
    "perceive": PERCEIVE, "act": ACT, "speak": SPEAK,
    "recall": RECALL, "reflect": REFLECT, "direct": DIRECT,
    "arrive": ARRIVE,
}

# What the ladder is worth, once the engine has to sort things by it.
WEIGHT_VALUE = {"nothing": 0.0, "faint": 0.15, "ordinary": 0.4,
                "stays": 0.7, "marks": 0.95}


def weight_to_salience(weight: Optional[str]) -> float:
    return WEIGHT_VALUE.get(weight or "ordinary", 0.4)


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
    stop early - the shortest valid answer to PERCEIVE would be {"weight":
    "stays"}, which says something stayed and nothing about what. The validator
    stays lenient (other backends and recorded tapes may omit fields); the
    grammar does not.
    """
    import copy

    schema = copy.deepcopy(BY_NAME[name])
    schema["required"] = list(schema.get("properties", {}).keys())
    return schema


def act_grammar(places: List[str], beings: List[str],
                may_leave: bool = False) -> dict:
    """ACT with its target narrowed to what is actually there.

    A target the model can only choose from what exists cannot be a place that
    is not adjacent or a person who is not in the room - the grammar makes the
    wrong answer unwritable instead of the engine repairing it afterwards.

    The same applies to the verb. Leaving for good is in the vocabulary only
    when the engine has already decided it is possible from here today, so a
    model cannot walk somebody out of the world from their own kitchen.
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


def reflect_grammar(sources: int) -> dict:
    """REFLECT with belief_from narrowed to today's numbered memories."""
    schema = grammar("reflect")
    schema["properties"]["belief_from"] = {
        "type": "string", "enum": [""] + [str(i) for i in range(1, sources + 1)]}
    return schema
