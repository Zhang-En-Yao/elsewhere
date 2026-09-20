"""Which mind answers which question.

Per call site, so the cheap decisions can run on something small at home while
the ones that need judgement go somewhere larger. Written into the world as
``config.json`` at creation time, so it is visible and editable rather than
buried in code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

from .backends import Settings

# Model names are deliberately left as plain strings: check the exact tag you
# have with `ollama list` before trusting these.
LOCAL = {"backend": "ollama", "model": "gemma4:26b-a4b",
         "extra": {"think": False}}          # Gemma 4 hides JSON in reasoning otherwise
SMALL = {"backend": "ollama", "model": "gemma4:e2b", "extra": {"think": False}}

DEFAULTS: Dict[str, dict] = {
    # closed-set decisions: a small model is enough
    "act":      {**SMALL, "temperature": 0.9},
    "perceive": {**LOCAL, "temperature": 0.7},
    # voice and judgement: the calls worth spending on
    "speak":    {**LOCAL, "temperature": 1.0},
    "recall":   {**LOCAL, "temperature": 1.0},
    "reflect":  {**LOCAL, "temperature": 0.8},
    "direct":   {**LOCAL, "temperature": 1.0},
}


def default_config() -> dict:
    return {"agents": {k: dict(v) for k, v in DEFAULTS.items()}}


def load(root) -> Dict[str, Settings]:
    """Read a world's config, with an environment override for quick runs.

    ``ELSEWHERE_BACKEND=stub`` forces every call site onto one backend, which
    is how the tests and ``--dry-run`` work without touching a model.
    """
    path = Path(root) / "config.json"
    data = default_config()
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        for name, settings in loaded.get("agents", {}).items():
            data["agents"].setdefault(name, {}).update(settings)

    forced = os.environ.get("ELSEWHERE_BACKEND")
    forced_model = os.environ.get("ELSEWHERE_MODEL")
    out: Dict[str, Settings] = {}
    for name, settings in data["agents"].items():
        if forced:
            settings = {**settings, "backend": forced,
                        "model": forced_model or ("stub" if forced == "stub"
                                                  else settings.get("model", "")),
                        "extra": {} if forced == "stub" else settings.get("extra", {})}
        out[name] = Settings.from_dict(settings)
    return out


def write_default(root) -> Path:
    path = Path(root) / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(default_config(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path
