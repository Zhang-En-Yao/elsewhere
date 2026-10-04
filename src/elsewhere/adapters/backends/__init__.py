"""Model backends, the call/answer plumbing, and the transcript of every call.

Nothing here knows which call sites exist or what their answers mean: a
`Call` carries its own grammar, and `ask` is handed the check its answer must
pass (`harness.schemas.validate`).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Tuple



@dataclass
class Call:
    name: str                       # the call site, `harness.schemas.CallName`
    system: str
    user: str
    schema: dict                    # the decoding grammar
    mind: str = ""                  # the being or world the call is put to, for the transcript


@dataclass
class Settings:
    backend: str = "stub"
    model: str = "stub"
    temperature: float = 0.8
    options: Dict = field(default_factory=dict)
    endpoint: str = ""                  # "" for the backend's own default
    timeout: float = 180.0          # seconds

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        return cls(backend=data.get("backend", "stub"), model=data.get("model", "stub"),
                   temperature=float(data.get("temperature", 0.8)),
                   options=dict(data.get("options", {})),
                   endpoint=str(data.get("endpoint", "")),
                   timeout=float(data.get("timeout", 180.0)))


class Backend(Protocol):
    name: str

    def complete(self, call: Call, settings: "Settings") -> str:
        """Must not raise on model nonsense."""
        ...



REGISTRY: Dict[str, Backend] = {}


def register(backend: Backend) -> None:
    REGISTRY[backend.name] = backend


def get(name: str) -> Backend:
    if name not in REGISTRY:
        bootstrap()
    if name not in REGISTRY:
        raise KeyError(f"no backend named {name!r}; have {sorted(REGISTRY)}")
    return REGISTRY[name]


def bootstrap() -> None:
    from .mlx import MLXBackend
    from .openai_compatible import OpenAICompatibleBackend
    from .stub import StubBackend
    for backend in (StubBackend(script_from_env=True), MLXBackend(), OpenAICompatibleBackend()):
        register(backend)



class Transcript:

    def __init__(self, path: Optional[Path]):
        self.path = Path(path) if path else None

    def write(self, row: dict) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


REPAIR = ("That was not usable: {complaint}. "
          "Answer again with the same JSON object, corrected. Nothing else.")


#: `(clean, None)` or `(None, complaint)`; the complaint is sent back to the
#: model as a repair instruction.
Check = Callable[[dict], Tuple[Optional[dict], Optional[str]]]


def anything(data: dict) -> Tuple[Optional[dict], Optional[str]]:
    return data, None


def extract_json(text: str) -> Optional[dict]:
    """The first JSON object anywhere in the text, skipping prose and fences."""
    decoder = json.JSONDecoder()
    for brace in re.finditer(r"\{", text or ""):
        try:
            value, _ = decoder.raw_decode(text, brace.start())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def ask(backend: Backend, call: Call, settings: Settings,
        transcript: Optional[Transcript] = None, check: Check = anything,
        attempts: int = 2) -> Optional[dict]:
    """Retries once with a repair instruction. ``None`` means no usable answer,
    which callers treat as the person having nothing, not as an error."""
    user = call.user
    complaint = None
    for attempt in range(attempts):
        started = time.time()
        try:
            raw = backend.complete(Call(call.name, call.system, user, call.schema,
                                        call.mind), settings)
            error = None
        except Exception as exception:
            raw, error = "", f"{type(exception).__name__}: {exception}"
        elapsed = time.time() - started

        parsed = extract_json(raw) if raw else None
        clean, complaint = (None, "nothing came back") if parsed is None \
            else check(parsed)

        if transcript is not None:
            transcript.write({
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "call": str(call.name),
                "mind": call.mind, "backend": settings.backend,
                "model": settings.model, "attempt": attempt + 1,
                "seconds": round(elapsed, 2), "system": call.system, "user": user,
                "raw": raw, "ok": clean is not None,
                "complaint": complaint, "error": error,
            })

        if clean is not None:
            return clean
        user = f"{call.user}\n\n{REPAIR.format(complaint=complaint or error)}"
    return None



def embed(texts: List[str], settings: Settings) -> List[List[float]]:
    """One vector per text; an empty list on any failure, or if the backend
    cannot embed."""
    if not texts:
        return []
    embedder = getattr(get(settings.backend), "embed", None)
    if embedder is None:
        return []
    try:
        vectors = embedder(list(texts), settings)
    except Exception:
        return []
    return vectors if len(vectors) == len(texts) else []



PROBE = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}


def probe(settings: Settings) -> tuple:
    """Returns (ok, message). Never raises."""
    call = Call(name="probe", system="Answer only with JSON.",
                user='Reply exactly {"ok": true}.', schema=PROBE, mind="probe")
    started = time.time()
    try:
        raw = get(settings.backend).complete(
            call, replace(settings, temperature=0.0))
    except Exception as exception:
        return False, f"unreachable: {type(exception).__name__}: {exception}"
    if extract_json(raw) is None:
        return False, f"answered, but not with JSON: {raw[:60]!r}"
    return True, f"ok ({time.time() - started:.1f}s)"


bootstrap()
