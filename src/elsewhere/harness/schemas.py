"""JSON schemas for every model call, used both as a decoding grammar and to
validate the answer on the way back in.

An answer is not a tool call yet: its `action` names one of the server's
tools (or none), and the harness turns it, with the rest of the answer, into
the call itself (`harness.being`, `harness.world`).
"""

from __future__ import annotations

import copy
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ..application.actions import Reach
from ..server import Tool


class CallName(str, Enum):
    # A being's.
    ACT = "act"
    SPEAK = "speak"
    CONSOLIDATE = "consolidate"
    # The world's.
    STIR = "stir"

    def __str__(self) -> str:
        return self.value


# Nothing to do is the empty string, as it is for `target`; the harness turns
# it into `Tool.STAY`.
NO_ACTION = ""
#: Offered every time; `Tool.LEAVE` only where the road goes out.
ALWAYS_OFFERED = [Tool.MOVE, Tool.TALK]

# Under a grammar keys are generated in declaration order, so every schema puts
# reasoning first and the decision last.
ACT = {
    "type": "object",
    "properties": {
        # What they encode of what just reached them, in their own words; ""
        # for nothing. The only thing that writes an `Episode`, with SPEAK's.
        "encoded": {"type": "string"},
        "reason": {"type": "string"},
        "doing": {"type": "string"},
        "action": {"type": "string", "enum": [NO_ACTION] + ALWAYS_OFFERED + [Tool.LEAVE]},
        "target": {"type": "string"},
        # The only thing that schedules a person's next turn; see `Tool.WAIT`.
        "duration": {"type": "integer"},
        # Ending the day; the only trigger for `consolidate`.
        "sleep": {"type": "boolean"},
    },
    "required": ["action"],
}

SPEAK = {
    "type": "object",
    "properties": {
        "encoded": {"type": "string"},
        "utterance": {"type": "string"},
    },
    "required": ["utterance"],
}

#: The one number the world has about who somebody is: how much of a self one
#: person can carry from one day to the next. What goes when it is full is theirs.
SELF_SCHEMA_CHARACTERS = 4000

LINES = {"type": "array", "items": {"type": "string"}}

SELF_SCHEMA = {
    "type": "object",
    "properties": {
        "idiolect": {"type": "string"},
        "traits": LINES,
        "concerns": LINES,
        "assumptions": LINES,
        "impressions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"being": {"type": "string"}, "impression": {"type": "string"}},
                "required": ["being", "impression"],
            },
        },
    },
    "required": ["idiolect", "traits", "concerns", "assumptions", "impressions"],
}

ENGRAM = {
    "type": "object",
    "properties": {
        "gists": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "proposition": {"type": "string"},
                    "weight": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["proposition", "weight"],
            },
        },
    },
    "required": ["gists"],
}

CONSOLIDATE = {
    "type": "object",
    "properties": {
        # What the day is laid down as; the only thing that writes an `Engram`.
        "engrams": {"type": "array", "items": ENGRAM},
        # The whole self-schema, rewritten; the only thing that writes
        # `Identity.self_schema`. At most SELF_SCHEMA_CHARACTERS, all fields counted.
        "self_schema": SELF_SCHEMA,
    },
    "required": ["engrams", "self_schema"],
}

REACH = [str(extent) for extent in Reach]

STIR = {
    "type": "object",
    "properties": {
        "why_now": {"type": "string"},
        # For `occur`.
        "what": {"type": "string"},
        "where": {"type": "string"},
        "who": {"type": "string"},
        "reach": {"type": "string", "enum": REACH},
        # For `admit`.
        "name": {"type": "string"},
        "from_where": {"type": "string"},
        "biography": {"type": "string"},
        "idiolect": {"type": "string"},
        "action": {"type": "string", "enum": [NO_ACTION, Tool.OCCUR, Tool.ADMIT]},
        # The only thing that paces how often the world is asked.
        "duration": {"type": "integer"},
    },
    "required": ["action"],
}

SCHEMA_BY_CALL_NAME: Dict[CallName, dict] = {
    CallName.ACT: ACT,
    CallName.SPEAK: SPEAK,
    CallName.CONSOLIDATE: CONSOLIDATE,
    CallName.STIR: STIR,
}


def validate(name: CallName, data: Any) -> Tuple[Optional[dict], Optional[str]]:
    """Returns ``(clean, None)`` or ``(None, complaint)``; the complaint is
    worded to be sent back to the model as a repair instruction."""
    schema = SCHEMA_BY_CALL_NAME.get(name)
    if schema is None:
        return None, f"there is no call named {name!r}"
    if not isinstance(data, dict):
        return None, "the answer must be a single JSON object"
    clean, complaint = conform("the answer", data, schema)
    if complaint is not None:
        return None, complaint
    if name == CallName.CONSOLIDATE:
        complaint = oversize(clean.get("self_schema", {}))
        if complaint is not None:
            return None, complaint
    return clean, None


def conform(key: str, value: Any, rule: dict) -> Tuple[Any, Optional[str]]:
    """One value checked against its rule, objects and arrays all the way down;
    keys the rule does not name are dropped."""
    kind = rule.get("type")
    if kind == "boolean":
        if not isinstance(value, bool):
            return None, f"{key!r} must be true or false, not {value!r}"
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return None, f"{key!r} must be a whole number, not {value!r}"
    elif kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"{key!r} must be a number, not {value!r}"
        value = float(value)
    elif kind == "string":
        if not isinstance(value, str):
            return None, f"{key!r} must be a string, not {value!r}"
        allowed = rule.get("enum")
        if allowed and value not in allowed:
            return None, (f"{key!r} must be one of {', '.join(allowed)}; " f"{value!r} is not")
        maximum = rule.get("maxLength")
        if maximum is not None and len(value) > maximum:
            return None, (
                f"{key!r} is {len(value)} characters and can hold "
                f"at most {maximum}; let go of what matters least"
            )
    elif kind == "array":
        if not isinstance(value, list):
            return None, f"{key!r} must be a list, not {value!r}"
        items = rule.get("items")
        if items is not None:
            conformed = []
            for item in value:
                item, complaint = conform(f"each of {key}", item, items)
                if complaint is not None:
                    return None, complaint
                conformed.append(item)
            value = conformed
    elif kind == "object":
        if not isinstance(value, dict):
            return None, f"{key!r} must be an object, not {value!r}"
        clean: Dict[str, Any] = {}
        for property, subrule in rule.get("properties", {}).items():
            if property not in value:
                continue
            clean[property], complaint = conform(property, value[property], subrule)
            if complaint is not None:
                return None, complaint
        for property in rule.get("required", []):
            if property not in clean:
                return None, f"{property!r} is required and was missing"
        value = clean
    return value, None


def oversize(self_schema: dict) -> Optional[str]:
    """The one rule a self-schema has that JSON Schema cannot say: its size,
    every field counted together."""
    written = (
        len(self_schema.get("idiolect", ""))
        + sum(len(line) for line in self_schema.get("traits", []))
        + sum(len(line) for line in self_schema.get("concerns", []))
        + sum(len(line) for line in self_schema.get("assumptions", []))
        + sum(
            len(impression.get("being", "")) + len(impression.get("impression", ""))
            for impression in self_schema.get("impressions", [])
        )
    )
    if written <= SELF_SCHEMA_CHARACTERS:
        return None
    return (
        f"'self_schema' is {written} characters and can hold at most "
        f"{SELF_SCHEMA_CHARACTERS}; let go of what matters least"
    )


def grammar(name: CallName) -> dict:
    """The schema with every field required, since under constrained decoding
    optional fields let the model stop early. `validate` stays lenient for
    backends without grammar support."""
    schema = copy.deepcopy(SCHEMA_BY_CALL_NAME[name])
    schema["required"] = list(schema.get("properties", {}).keys())
    return schema


def act_grammar(places: List[str], beings: List[str], may_leave: bool = False) -> dict:
    schema = grammar(CallName.ACT)
    options = [""] + sorted(set(places) | set(beings))
    schema["properties"]["target"] = {"type": "string", "enum": options}
    schema["properties"]["action"] = {
        "type": "string",
        "enum": [NO_ACTION] + ALWAYS_OFFERED + ([Tool.LEAVE] if may_leave else []),
    }
    return schema


def stir_grammar(places: List[str], beings: List[str], may_admit: bool = True) -> dict:
    schema = grammar(CallName.STIR)
    schema["properties"]["where"] = {"type": "string", "enum": [""] + sorted(places)}
    schema["properties"]["who"] = {"type": "string", "enum": [""] + sorted(beings)}
    schema["properties"]["action"] = {
        "type": "string",
        "enum": [NO_ACTION, Tool.OCCUR] + ([Tool.ADMIT] if may_admit else []),
    }
    return schema
