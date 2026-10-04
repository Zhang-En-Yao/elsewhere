"""Which backend and model answers each of the harness's call sites, from the world's
``configuration.json``. The environment never overrides it, except for API keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

from ..adapters.backends import Settings
from .schemas import CallName

# Hugging Face repo or a local MLX directory. Sized for ~4GB free on an 8GB
# Apple-silicon Mac (3.4GB resident, ~4.1GB peak); one model for every call,
# since two cannot stay resident at once.
LOCAL = {"backend": "mlx", "model": "mlx-community/gemma-4-E2B-it-qat-4bit"}  # ~4GB

# Optional: without it, retrieval is BM25 alone. Engrams placed by one
# embedder are not compared with another's.
EMBED = {"backend": "mlx", "model": "mlx-community/embeddinggemma-300m-8bit"}  # ~330MB, 768 dims

DEFAULTS: Dict[str, dict] = {
    CallName.ACT:      {**LOCAL, "temperature": 0.9},
    CallName.SPEAK:    {**LOCAL, "temperature": 1.0},
    CallName.CONSOLIDATE: {**LOCAL, "temperature": 0.8},
    CallName.STIR:     {**LOCAL, "temperature": 1.0},
    "embed":           dict(EMBED),
}

GUIDANCE = [
    "backend: mlx | openai | stub",
    "mlx runs the model in this process on Apple silicon: model is a Hugging "
    "Face repository (fetched once, then cached) or a local directory of MLX "
    "weights. The schema constrains decoding directly. Needs "
    "pip install -e '.[mlx]'",
    "endpoint: where the server is, for openai; http://localhost:8000/v1 if left "
    "out. timeout: seconds to wait for one answer, 180 if left out",
    "anything with an OpenAI-compatible /v1 works through backend \"openai\" "
    "with its endpoint set: llama-server, LM Studio, vLLM on a GPU box. A hosted "
    "endpoint takes its key from ELSEWHERE_OPENAI_KEY, the only thing read "
    "from the environment",
    "embed on backend \"openai\" asks the endpoint's /v1/embeddings, which not "
    "every server has (mlx_lm.server does not); without it retrieval is BM25 alone",
    "mlx: options go to the chat template, with enable_thinking false unless "
    "it says otherwise",
    "change a whole backend at once with `elsewhere configure`; "
    "run `elsewhere doctor` after any change here",
]

FILENAME = "configuration.json"

MINDS = tuple(name for name in DEFAULTS if name != "embed")


def locate(root) -> Path:
    return Path(root) / FILENAME


def default() -> dict:
    return {"notes": list(GUIDANCE),
            "agents": {name: dict(settings) for name, settings in DEFAULTS.items()}}


def read(root) -> dict:
    """The file merged over the defaults."""
    data = default()
    path = locate(root)
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        for name, settings in loaded.get("agents", {}).items():
            if name not in data["agents"]:
                continue                      # a call site there is no longer
            merged = data["agents"][name]
            if settings.get("backend", merged.get("backend")) != merged.get("backend"):
                merged.pop("options", None)   # the default's options are for its backend
            merged.update(settings)
    return data


def load(root) -> Dict[str, Settings]:
    return {name: Settings.from_dict(settings)
            for name, settings in read(root)["agents"].items()}


def write(root, data: dict) -> Path:
    path = locate(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {**data, "notes": list(GUIDANCE)}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def configure(root, backend: str, model: str, endpoint: Optional[str] = None,
              calls: Iterable[str] = MINDS) -> Path:
    data = read(root)
    for name in calls:
        if name not in data["agents"]:
            raise KeyError(f"no call site named {name!r}; have {sorted(data['agents'])}")
        settings = data["agents"][name]
        if settings.get("backend") != backend:
            settings.pop("options", None)     # what one backend takes, another refuses
        settings.update(backend=backend, model=model)
        if endpoint:
            settings["endpoint"] = endpoint
        else:
            settings.pop("endpoint", None)
    return write(root, data)
