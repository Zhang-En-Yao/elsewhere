"""Which backend and model answers each call, from the world's
``configuration.json``. The environment never overrides it, except for API keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

from .backends import Settings
from .schemas import CallName

# Hugging Face repo or a local MLX directory. Sized for ~4GB free on an 8GB
# Apple-silicon Mac (3.4GB resident, ~4.1GB peak); one model for every call,
# since two cannot stay resident at once.
LOCAL = {"backend": "mlx", "model": "mlx-community/gemma-4-E2B-it-qat-4bit"}  # ~4GB

# Optional; without it retrieval ranks by base level only. Changing it requires
# `elsewhere reembed`.
EMBED = {"backend": "mlx", "model": "mlx-community/embeddinggemma-300m-8bit"}  # ~330MB, 768 dims

DEFAULTS: Dict[str, dict] = {
    CallName.ACT:      {**LOCAL, "temperature": 0.9},
    CallName.PERCEIVE: {**LOCAL, "temperature": 0.7},
    CallName.SPEAK:    {**LOCAL, "temperature": 1.0},
    CallName.RECALL:   {**LOCAL, "temperature": 1.0},
    CallName.REFLECT:  {**LOCAL, "temperature": 0.8},
    CallName.DIRECT:   {**LOCAL, "temperature": 1.0},
    CallName.ARRIVE:   {**LOCAL, "temperature": 1.0},
    "embed":    dict(EMBED),
}

NOTES = [
    "backend: mlx | openai | claude | gpt | gemini | stub",
    "mlx runs the model in this process on Apple silicon: model is a Hugging "
    "Face repository (fetched once, then cached) or a local directory of MLX "
    "weights. The schema constrains decoding directly. Needs "
    "pip install -e '.[mlx]'",
    "base: where the server is, for openai; http://localhost:8000/v1 if left "
    "out. timeout: seconds to wait for one answer, 180 if left out",
    "anything with an OpenAI-compatible /v1 works through backend \"openai\" "
    "with its base set: llama-server, LM Studio, vLLM on a GPU box. A hosted "
    "endpoint takes its key from ELSEWHERE_OPENAI_KEY, the only thing read "
    "from the environment",
    "claude: pip install -e '.[llm]' and set ANTHROPIC_API_KEY; worth it for "
    "perceive/speak/reflect if the local model makes everyone sound alike",
    "gpt: set OPENAI_API_KEY. gemini: set GEMINI_API_KEY. Both need no extra "
    "package; anything they cannot do with the model you name is the model's "
    "limit, not this file's",
    "mlx: extra goes to the chat template, with enable_thinking false unless "
    "it says otherwise",
    "change a whole backend at once with `elsewhere configure`; "
    "run `elsewhere doctor` after any change here. After changing the "
    "embedder, run `elsewhere reembed`",
]

FILENAME = "configuration.json"

MINDS = tuple(name for name in DEFAULTS if name != "embed")


def path_of(root) -> Path:
    return Path(root) / FILENAME


def default_configuration() -> dict:
    return {"notes": list(NOTES),
            "agents": {k: dict(v) for k, v in DEFAULTS.items()}}


def read_configuration(root) -> dict:
    """The file merged over the defaults."""
    data = default_configuration()
    path = path_of(root)
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        for name, settings in loaded.get("agents", {}).items():
            merged = data["agents"].setdefault(name, {})
            if settings.get("backend", merged.get("backend")) != merged.get("backend"):
                merged.pop("extra", None)   # the default's extra is for its backend
            merged.update(settings)
    return data


def load_configuration(root) -> Dict[str, Settings]:
    return {name: Settings.from_dict(settings)
            for name, settings in read_configuration(root)["agents"].items()}


def _write(root, data: dict) -> Path:
    path = path_of(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {**data, "notes": list(NOTES)}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def write_default_configuration(root) -> Path:
    """Kept if one exists, so `configure` can run before `initialize`."""
    path = path_of(root)
    if path.exists():
        return path
    return _write(root, default_configuration())


def configure(root, backend: str, model: str, base: Optional[str] = None,
              calls: Iterable[str] = MINDS) -> Path:
    data = read_configuration(root)
    for name in calls:
        if name not in data["agents"]:
            raise KeyError(f"no call site named {name!r}; have {sorted(data['agents'])}")
        settings = data["agents"][name]
        if settings.get("backend") != backend:
            settings.pop("extra", None)     # what one backend takes, another refuses
        settings.update(backend=backend, model=model)
        if base:
            settings["base"] = base
        else:
            settings.pop("base", None)
    return _write(root, data)
