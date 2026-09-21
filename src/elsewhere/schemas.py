"""The six places where a mind is asked something, and the shape of the answer.

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

FEELINGS = [
    "fear", "grief", "relief", "warmth", "unease", "awe", "anger",
    "resolve", "shame", "tenderness", "boredom", "hope", "none",
]

# A small ladder instead of a float: a 4B model has no idea what 0.73 means,
# and neither does a person. The engine maps these onto numbers itself.
WEIGHTS = ["nothing", "faint", "ordinary", "stays", "marks"]

ACTIONS = ["stay", "go", "talk", "work", "rest", "make", "tend", "walk"]

# Order matters under a grammar: keys are generated in this order, so a model
# that is asked "stuck?" first commits to an answer in one token, before it has
# written a word about what happened. Asking for the fragment first and the
# verdict last lets the decision be about something it has already said.
PERCEIVE = {
    "type": "object",
    "properties": {
        "trace": {"type": "string"},
        "means": {"type": "string"},
        "feeling": {"type": "string", "enum": FEELINGS},
        "tags": {"type": "array", "items": {"type": "string"}},
        "weight": {"type": "string", "enum": WEIGHTS},
    },
    # One decision in one field. An earlier version also asked for a boolean
    # 'stuck', and a small model happily answered weight "stays", stuck false.
    "required": [],
}

ACT = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ACTIONS},
        "target": {"type": "string"},
        "because": {"type": "string"},
    },
    "required": ["action"],
}

SPEAK = {
    "type": "object",
    "properties": {
        "line": {"type": "string"},
        "holding_back": {"type": "boolean"},
    },
    "required": ["line"],
}

RECALL = {
    "type": "object",
    "properties": {
        "trace": {"type": "string"},
        "means": {"type": "string"},
        "feeling": {"type": "string", "enum": FEELINGS},
        "changed": {"type": "boolean"},
        "what_changed": {"type": "string"},
    },
    "required": ["trace"],
}

REFLECT = {
    "type": "object",
    "properties": {
        "beliefs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "confidence": {"type": "number"},
                    "from": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text"],
            },
        },
        "card": {"type": "string"},
        "wants": {"type": "array", "items": {"type": "string"}},
    },
    "required": [],
}

DIRECT = {
    "type": "object",
    "properties": {
        "happens": {"type": "boolean"},
        "what": {"type": "string"},
        "where": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "why_now": {"type": "string"},
    },
    "required": ["happens"],
}

BY_NAME: Dict[str, dict] = {
    "perceive": PERCEIVE, "act": ACT, "speak": SPEAK,
    "recall": RECALL, "reflect": REFLECT, "direct": DIRECT,
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


def required_for(name: str) -> List[str]:
    return list(BY_NAME[name].get("required", []))


def grammar(name: str) -> dict:
    """The schema as handed to a decoder: every field required.

    Under grammar-constrained decoding an optional field is an invitation to
    stop early - the shortest valid answer to PERCEIVE is {"stuck": true},
    which says something stayed and nothing about what. The inbound validator
    stays lenient (other backends and recorded tapes may omit fields); the
    grammar does not.
    """
    import copy

    schema = copy.deepcopy(BY_NAME[name])
    schema["required"] = list(schema.get("properties", {}).keys())
    return schema
