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
#
# The defaults below assume the model runs on the same machine as the tick and
# that machine has about 4GB to spare once the OS has taken its share. That
# buys a 3-4B model at Q4 and nothing larger - which is a real constraint on
# quality, not a detail. See `notes` in the written config for the two ways
# out: a bigger model on a GPU somewhere (backend "vllm"), or sending the
# calls that need judgement to a hosted model (backend "claude").
SMALL = {"backend": "ollama", "model": "qwen3.5:4b"}       # ~3.4GB at Q4
TINY = {"backend": "ollama", "model": "phi-4-mini"}        # ~2.2GB at Q4

DEFAULTS: Dict[str, dict] = {
    # closed-set decisions: the smallest thing that can follow a schema
    "act":      {**TINY, "temperature": 0.9},
    # judgement and voice: still local by default, and this is where a 4B
    # model will disappoint first
    "perceive": {**SMALL, "temperature": 0.7},
    "speak":    {**SMALL, "temperature": 1.0},
    "recall":   {**SMALL, "temperature": 1.0},
    "reflect":  {**SMALL, "temperature": 0.8},
    "direct":   {**SMALL, "temperature": 1.0},
}

NOTES = [
    "backend: ollama | vllm | openai | claude | stub",
    "vllm: set ELSEWHERE_OPENAI_BASE=http://your-gpu-host:8000/v1 - the tick "
    "itself needs almost no memory, so the model does not have to be here",
    "claude: pip install -e '.[llm]' and set ANTHROPIC_API_KEY; worth it for "
    "perceive/speak/reflect if the local model makes everyone sound alike",
    "a thinking-capable local model needs its thinking turned off or the JSON "
    "arrives inside the reasoning field: ollama -> extra {\"think\": false}, "
    "vllm -> extra {\"chat_template_kwargs\": {\"enable_thinking\": false}}",
    "run `elsewhere doctor` after any change here",
]


def default_config() -> dict:
    return {"notes": list(NOTES),
            "agents": {k: dict(v) for k, v in DEFAULTS.items()}}


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
