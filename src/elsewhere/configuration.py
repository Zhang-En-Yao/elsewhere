"""Which mind answers which question.

Per call site, so the cheap decisions can run on something small at home while
the ones that need judgement go somewhere larger. Written into the world as
``configuration.json`` at creation time, so it is visible and editable rather
than buried in code.

That file is the only thing that decides. Nothing in the environment can
override it, so what you read there is what the world runs on - whether it is
you at a terminal or launchd at three in the morning. The one exception is a
key: a secret does not belong in a file that gets copied around, and a key only
decides whether a mind can be reached, never which one it is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

from .backends import Settings
from .schemas import CallName

# Model names are Hugging Face repositories, fetched on first use and cached
# in ~/.cache/huggingface; a local directory of MLX weights works too.
#
# The defaults below assume the model runs on the same machine as the tick and
# that machine has about 4GB to spare once the OS has taken its share. That
# buys a 3-4B model at Q4 and nothing larger - which is a real constraint on
# quality, not a detail. Gemma 4 E2B in its quantisation-aware build is the
# newest thing that fits: on an 8GB M1 it takes 3.4GB once loaded and peaks
# near 4.1GB while answering. See `notes` in the written configuration for the
# two ways out: a bigger model on a GPU somewhere (backend "openai" with its
# base set), or sending the calls that need judgement to a hosted model
# (backend "claude", "gpt" or "gemini").
# One model for every call site. On 8GB two models cannot both stay resident,
# and loading a second one every tick costs more than it saves.
LOCAL = {"backend": "mlx", "model": "mlx-community/gemma-4-E2B-it-qat-4bit"}  # ~4GB

# Not a mind: the thing that says where a memory reads from, so that what
# comes back to somebody is what this moment is about rather than what they
# happened to type the same word for. Google's EmbeddingGemma, which MLX runs
# natively. Nothing breaks if it is missing: retrieval falls back on how
# reachable a memory is, which is what it used before. Vectors from two
# embedders cannot be compared, so after changing this run
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

# The minds, as opposed to the embedder: what `configure` changes unless told
# otherwise, since one model rarely does both.
MINDS = tuple(name for name in DEFAULTS if name != "embed")


def path_of(root) -> Path:
    return Path(root) / FILENAME


def default_configuration() -> dict:
    return {"notes": list(NOTES),
            "agents": {k: dict(v) for k, v in DEFAULTS.items()}}


def read_configuration(root) -> dict:
    """The file as written, with anything it leaves out taken from the defaults."""
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
    """Read a world's configuration: one Settings per call site."""
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
    """Write the defaults, unless this world already has a configuration.

    Kept rather than replaced, so that `configure` can run before a world is
    made, and starting a world over does not undo which minds it runs on.
    """
    path = path_of(root)
    if path.exists():
        return path
    return _write(root, default_configuration())


def configure(root, backend: str, model: str, base: Optional[str] = None,
              calls: Iterable[str] = MINDS) -> Path:
    """Point these call sites at one backend and model, and write it down."""
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
