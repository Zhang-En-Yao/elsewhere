"""Backends: whatever is doing the thinking, and the tape that records it.

The engine never talks to a model directly. It composes a ``Call`` - a system
prompt, a user prompt and the schema the answer must fit - and hands it to a
backend. Which backend answers which call is configuration, so ``act`` can run
on a 4B model at home while ``reflect`` goes to something larger.

Every exchange is appended to a transcript - a durable record of what was
asked, what came back, and whether it was usable. It is this world's
replacement for a random seed, in the sense that it is the thing that
explains a run after the fact; the tests themselves run offline against a
stub backend instead, with no model and no tape to replay.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from ..schemas import validate

REPAIR = ("That was not usable: {complaint}. "
          "Answer again with the same JSON object, corrected. Nothing else.")


@dataclass
class Call:
    name: str        # perceive | act | speak | recall | reflect | direct | arrive
    system: str
    user: str
    schema: dict
    about: str = ""                 # person id or similar, for the transcript


class Backend(Protocol):
    name: str

    def complete(self, call: Call, settings: "Settings") -> str:
        """Return the raw text of one answer. Must not raise on model nonsense."""
        ...


class Embedder(Protocol):
    """A backend that can also place text somewhere, rather than answer about it.

    This is the only thing in Elsewhere a model is asked for that is not an
    answer. It exists because the alternative was a tag vocabulary that every
    mind had to keep spelling the same way for the engine to match on, and a
    person does not file their own memories.
    """
    name: str

    def embed(self, texts: List[str], settings: "Settings") -> List[List[float]]:
        """One vector per text, in order. Must not raise on nonsense input."""
        ...


@dataclass
class Settings:
    backend: str = "stub"
    model: str = "stub"
    temperature: float = 0.8
    extra: Dict = field(default_factory=dict)
    base: str = ""                  # where the server is; "" for the backend's own default
    timeout: float = 180.0          # seconds to wait for one answer

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        return cls(backend=d.get("backend", "stub"), model=d.get("model", "stub"),
                   temperature=float(d.get("temperature", 0.8)),
                   extra=dict(d.get("extra", {})),
                   base=str(d.get("base", "")),
                   timeout=float(d.get("timeout", 180.0)))


class Transcript:
    """Append-only record of every question put to a mind, and its answer."""

    def __init__(self, path: Optional[Path]):
        self.path = Path(path) if path else None

    def write(self, row: dict) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of whatever came back.

    Grammar-constrained models return clean JSON. Unconstrained ones wrap it in
    prose, fences, or an apology. All three are handled here rather than in the
    call sites.
    """
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:i + 1])
                        if isinstance(value, dict):
                            return value
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def ask(backend: Backend, call: Call, settings: Settings,
        transcript: Optional[Transcript] = None, attempts: int = 2) -> Optional[dict]:
    """Put one question to a mind and insist on a usable answer, twice.

    Returns ``None`` if it could not give one. A caller that gets ``None``
    treats it as the person having nothing to offer - which is a normal thing
    for a person to have - rather than as an error to retry forever.
    """
    user = call.user
    complaint = None
    for attempt in range(attempts):
        started = time.time()
        try:
            raw = backend.complete(Call(call.name, call.system, user, call.schema,
                                        call.about), settings)
            error = None
        except Exception as exc:                      # a backend that is simply down
            raw, error = "", f"{type(exc).__name__}: {exc}"
        took = time.time() - started

        parsed = extract_json(raw) if raw else None
        clean, complaint = (None, "nothing came back") if parsed is None \
            else validate(call.name, parsed)

        if transcript is not None:
            transcript.write({
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "call": call.name,
                "about": call.about, "backend": settings.backend,
                "model": settings.model, "attempt": attempt + 1,
                "seconds": round(took, 2), "system": call.system, "user": user,
                "raw": raw, "ok": clean is not None,
                "complaint": complaint, "error": error,
            })

        if clean is not None:
            return clean
        user = f"{call.user}\n\n{REPAIR.format(complaint=complaint or error)}"
    return None


def embed(texts: List[str], settings: Settings) -> List[List[float]]:
    """Where these read from, as vectors. An empty list back means: no idea.

    A backend that cannot embed, or one that is down, is not an error here.
    Retrieval falls back on how reachable something is and nothing else,
    which is what it did before any of this existed.
    """
    if not texts:
        return []
    backend = get(settings.backend)
    backend_embed = getattr(backend, "embed", None)
    if backend_embed is None:
        return []
    try:
        out = backend_embed(list(texts), settings)
    except Exception:
        return []
    return out if len(out) == len(texts) else []


def probe(settings: Settings) -> tuple:
    """Can this mind be reached at all? (ok, message). Never raises."""
    call = Call(name="probe", system="Answer only with JSON.",
                user='Reply exactly {"ok": true}.',
                schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                        "required": ["ok"]}, about="probe")
    started = time.time()
    try:
        raw = get(settings.backend).complete(
            call, replace(settings, temperature=0.0))
    except Exception as exc:
        return False, f"unreachable: {type(exc).__name__}: {exc}"
    if extract_json(raw) is None:
        return False, f"answered, but not with JSON: {raw[:60]!r}"
    return True, f"ok ({time.time() - started:.1f}s)"


_REGISTRY: Dict[str, Backend] = {}


def register(backend: Backend) -> None:
    _REGISTRY[backend.name] = backend


def get(name: str) -> Backend:
    if name not in _REGISTRY:
        _bootstrap()
    if name not in _REGISTRY:
        raise KeyError(f"no backend named {name!r}; have {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def _bootstrap() -> None:
    from .openai_compat import (OllamaBackend, OpenAICompatBackend,
                                VLLMBackend)
    from .stub import StubBackend
    for backend in (StubBackend(script_from_env=True), OllamaBackend(), OpenAICompatBackend(),
                    VLLMBackend()):
        register(backend)
    try:
        from .anthropic_backend import AnthropicBackend
        register(AnthropicBackend())
    except Exception:
        pass


_bootstrap()
