"""JSON schemas for every model call, used both as a decoding grammar and to
validate the answer on the way back in."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CallName(str, Enum):
    PERCEIVE = "perceive"
    ACT = "act"
    SPEAK = "speak"
    RECALL = "recall"
    REFLECT = "reflect"
    DIRECT = "direct"
    ARRIVE = "arrive"
    PROBE = "probe"    # health check, not a person's call

    def __str__(self) -> str:
        return self.value


ACTIONS = ["stay", "go", "talk"]
# Offered only where agents.may_leave allows it; see act_grammar.
LEAVE = "leave"

# Under a grammar keys are generated in declaration order, so every schema puts
# reasoning first and the decision last.
PERCEIVE = {
    "type": "object",
    "properties": {
        "account": {"type": "string"},
        "means": {"type": "string"},
        "feeling": {"type": "string"},
        "stuck": {"type": "boolean"},
    },
    "required": [],
}

ACT = {
    "type": "object",
    "properties": {
        "because": {"type": "string"},
        "doing": {"type": "string"},
        "action": {"type": "string", "enum": ACTIONS + [LEAVE]},
        "target": {"type": "string"},
        # The only thing that schedules a person's next turn; see `schedule`.
        "for_hours": {"type": "number"},
        # Ending the day; the only trigger for `reflect`.
        "settling": {"type": "boolean"},
        # Ignore ambient events until `for_hours` is up; events aimed at them
        # still get through.
        "absorbed": {"type": "boolean"},
    },
    "required": ["action"],
}

SPEAK = {
    "type": "object",
    "properties": {
        "about": {"type": "string"},
        "line": {"type": "string"},
    },
    "required": ["line"],
}

RECALL = {
    "type": "object",
    "properties": {
        "account": {"type": "string"},
        "means": {"type": "string"},
        "feeling": {"type": "string"},
    },
    "required": ["account"],
}

# Flat on purpose: small models cannot reliably fill nested lists under a grammar.
REFLECT = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "belief": {"type": "string"},
        "belief_from": {"type": "string"},
        # Index of an existing belief this restates; asked of the model because
        # sameness of meaning cannot be decided by word overlap.
        "belief_again": {"type": "string"},
        "want": {"type": "string"},
        # The only thing that rewrites a `Regard` (one side of it).
        "about_someone": {"type": "string"},
        "now_say": {"type": "string"},
    },
    "required": [],
}

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
        # The only thing that paces the director.
        "ask_again_in_hours": {"type": "number"},
    },
    "required": ["happens"],
}

ARRIVE = {
    "type": "object",
    "properties": {
        "why_now": {"type": "string"},
        "name": {"type": "string"},
        "from_where": {"type": "string"},
        "card": {"type": "string"},
        "manner": {"type": "string"},
        "comes": {"type": "boolean"},
        # The only thing that paces arrivals.
        "ask_again_in_hours": {"type": "number"},
    },
    "required": ["comes"],
}

PROBE = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}

SCHEMA_BY_CALL_NAME: Dict[CallName, dict] = {
    CallName.PERCEIVE: PERCEIVE, CallName.ACT: ACT, CallName.SPEAK: SPEAK,
    CallName.RECALL: RECALL, CallName.REFLECT: REFLECT, CallName.DIRECT: DIRECT,
    CallName.ARRIVE: ARRIVE, CallName.PROBE: PROBE,
}


class Invalid(ValueError):
    pass


def validate(name: CallName, data: Any) -> Tuple[Optional[dict], Optional[str]]:
    """Returns ``(clean, None)`` or ``(None, complaint)``; the complaint is
    worded to be sent back to the model as a repair instruction."""
    schema = SCHEMA_BY_CALL_NAME.get(name)
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


def grammar(name: CallName) -> dict:
    """The schema with every field required, since under constrained decoding
    optional fields let the model stop early. `validate` stays lenient for
    backends without grammar support."""
    import copy

    schema = copy.deepcopy(SCHEMA_BY_CALL_NAME[name])
    schema["required"] = list(schema.get("properties", {}).keys())
    return schema


def act_grammar(places: List[str], beings: List[str],
                may_leave: bool = False) -> dict:
    schema = grammar(CallName.ACT)
    options = [""] + sorted(set(places) | set(beings))
    schema["properties"]["target"] = {"type": "string", "enum": options}
    schema["properties"]["action"] = {
        "type": "string", "enum": ACTIONS + ([LEAVE] if may_leave else [])}
    return schema


def speak_grammar(topics: int) -> dict:
    schema = grammar(CallName.SPEAK)
    choices = ["nothing in particular"] + [str(i) for i in range(1, topics + 1)]
    schema["properties"]["about"] = {"type": "string", "enum": choices}
    return schema


def direct_grammar(places: List[str], beings: List[str]) -> dict:
    schema = grammar(CallName.DIRECT)
    schema["properties"]["where"] = {"type": "string", "enum": sorted(places)}
    schema["properties"]["who"] = {"type": "string", "enum": [""] + sorted(beings)}
    return schema


def reflect_grammar(sources: int, held: int = 0,
                    known: Optional[List[str]] = None) -> dict:
    schema = grammar(CallName.REFLECT)
    schema["properties"]["belief_from"] = {
        "type": "string", "enum": [""] + [str(i) for i in range(1, sources + 1)]}
    schema["properties"]["belief_again"] = {
        "type": "string", "enum": [""] + [str(i) for i in range(1, held + 1)]}
    schema["properties"]["about_someone"] = {
        "type": "string", "enum": [""] + sorted(known or [])}
    return schema
