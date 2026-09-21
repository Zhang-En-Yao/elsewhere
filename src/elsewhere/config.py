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
# One model for every call site. On 8GB two models cannot both stay resident,
# and swapping between them every tick costs more than it saves.
LOCAL = {"backend": "ollama", "model": "phi4-mini"}        # ~2.5GB at Q4_K_M

DEFAULTS: Dict[str, dict] = {
    "act":      {**LOCAL, "temperature": 0.9},
    "perceive": {**LOCAL, "temperature": 0.7},
    "speak":    {**LOCAL, "temperature": 1.0},
    "recall":   {**LOCAL, "temperature": 1.0},
    "reflect":  {**LOCAL, "temperature": 0.8},
    "direct":   {**LOCAL, "temperature": 1.0},
}

NOTES = [
    "backend: ollama | openai | vllm | claude | stub",
    "anything with an OpenAI-compatible /v1 works through backend \"openai\"; "
    "set ELSEWHERE_OPENAI_BASE. vllm-mlx: http://localhost:8000/v1 (MLX native, "
    "JSON schema via response_format). llama-server: http://localhost:8080/v1 "
    "(GBNF grammars, most control over context and KV quantisation). "
    "LM Studio: http://localhost:1234/v1. Hosted endpoints work the same way "
    "with ELSEWHERE_OPENAI_KEY.",
    "backend \"ollama\" uses its native /api/chat, where the schema is passed "
    "as format and constrains decoding directly",
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
