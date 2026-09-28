"""JSON schemas for every model call, used both as a decoding grammar and to
validate the answer on the way back in."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CallName(str, Enum):
    ACT = "act"
    SPEAK = "speak"
    SETTLE = "settle"
    STIR = "stir"
    ARRIVE = "arrive"
    PROBE = "probe"    # health check, not a person's call

    def __str__(self) -> str:
        return self.value


class Action(str, Enum):
    MOVE = "move"
    TALK = "talk"
    # Offered only where agents.may_leave allows it; see act_grammar.
    LEAVE = "leave"

    def __str__(self) -> str:
        return self.value


# Nothing to resolve is the empty string, as it is for `target`.
NO_ACTION = ""
#: Offered every time; `Action.LEAVE` only where the road goes out.
ALWAYS_OFFERED = [Action.MOVE, Action.TALK]

# Under a grammar keys are generated in declaration order, so every schema puts
# reasoning first and the decision last.
ACT = {
    "type": "object",
    "properties": {
        # What they keep of what just reached them, in their own words; "" for
        # nothing. The only thing that writes a `Note`, with SPEAK's.
        "noted": {"type": "string"},
        "because": {"type": "string"},
        "doing": {"type": "string"},
        "action": {"type": "string", "enum": [NO_ACTION] + ALWAYS_OFFERED + [Action.LEAVE]},
        "target": {"type": "string"},
        # The only thing that schedules a person's next turn; see `schedule`.
        "again_in_hours": {"type": "number"},
        # Ending the day; the only trigger for `settle`.
        "settling": {"type": "boolean"},
        # Ignore ambient events until `again_in_hours` is up; events aimed at them
        # still get through.
        "absorbed": {"type": "boolean"},
    },
    "required": ["action"],
}

SPEAK = {
    "type": "object",
    "properties": {
        "noted": {"type": "string"},
        "utterance": {"type": "string"},
    },
    "required": ["utterance"],
}

#: The one number the world has about memory: how much of a life one person
#: can carry from one day to the next. What goes when it is full is theirs.
NOTEBOOK_CHARACTERS = 1500

SETTLE = {
    "type": "object",
    "properties": {
        # The whole page, rewritten; the only thing that writes `Who.notebook`.
        "notebook": {"type": "string", "maxLength": NOTEBOOK_CHARACTERS},
    },
    "required": ["notebook"],
}

REACH = ["the people there", "the whole town"]

STIR = {
    "type": "object",
    "properties": {
        "why_now": {"type": "string"},
        "what": {"type": "string"},
        "where": {"type": "string"},
        "who": {"type": "string"},
        "reach": {"type": "string", "enum": REACH},
        "happens": {"type": "boolean"},
        # The only thing that paces how often the town is asked.
        "again_in_hours": {"type": "number"},
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
        "happens": {"type": "boolean"},
        # The only thing that paces arrivals.
        "again_in_hours": {"type": "number"},
    },
    "required": ["happens"],
}

PROBE = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}

SCHEMA_BY_CALL_NAME: Dict[CallName, dict] = {
    CallName.ACT: ACT, CallName.SPEAK: SPEAK, CallName.SETTLE: SETTLE,
    CallName.STIR: STIR, CallName.ARRIVE: ARRIVE, CallName.PROBE: PROBE,
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
    properties = schema.get("properties", {})
    for key, rule in properties.items():
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
            maximum = rule.get("maxLength")
            if maximum is not None and len(value) > maximum:
                return None, (f"{key!r} is {len(value)} characters and can hold "
                              f"at most {maximum}; let go of what matters least")
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
        "type": "string",
        "enum": [NO_ACTION] + ALWAYS_OFFERED + ([Action.LEAVE] if may_leave else [])}
    return schema


def stir_grammar(places: List[str], beings: List[str]) -> dict:
    schema = grammar(CallName.STIR)
    schema["properties"]["where"] = {"type": "string", "enum": sorted(places)}
    schema["properties"]["who"] = {"type": "string", "enum": [""] + sorted(beings)}
    return schema

