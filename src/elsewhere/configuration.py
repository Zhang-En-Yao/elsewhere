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

# Model names are deliberately left as plain strings: check the exact tag you
# have with `ollama list` before trusting these.
#
# The defaults below assume the model runs on the same machine as the tick and
# that machine has about 4GB to spare once the OS has taken its share. That
# buys a 3-4B model at Q4 and nothing larger - which is a real constraint on
# quality, not a detail. See `notes` in the written configuration for the two ways
# out: a bigger model on a GPU somewhere (backend "vllm"), or sending the
# calls that need judgement to a hosted model (backend "claude").
# One model for every call site. On 8GB two models cannot both stay resident,
# and swapping between them every tick costs more than it saves.
LOCAL = {"backend": "ollama", "model": "phi4-mini"}        # ~2.5GB at Q4_K_M

# Not a mind: the thing that says where a memory reads from, so that what
# comes back to somebody is what this moment is about rather than what they
# happened to type the same word for. Tested against the memories of a real
# world - nomic ranked all four probes right with a spread of 0.32, while
# multilingual-e5-large put everything between 0.79 and 0.84 and could barely
# tell two memories apart. Nothing breaks if it is missing: retrieval falls
# back on how reachable a memory is, which is what it used before.
EMBED = {"backend": "ollama", "model": "nomic-embed-text"}  # ~274MB, 768 dims

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
    "backend: ollama | openai | vllm | claude | stub",
    "base: where the server is; leave it out for the default "
    "(ollama http://localhost:11434, openai and vllm http://localhost:8000/v1). "
    "timeout: seconds to wait for one answer, 180 if left out",
    "anything with an OpenAI-compatible /v1 works through backend \"openai\" "
    "with its base set. vllm-mlx: http://localhost:8000/v1 (MLX native, "
    "JSON schema via response_format). llama-server: http://localhost:8080/v1 "
    "(GBNF grammars, most control over context and KV quantisation). "
    "LM Studio: http://localhost:1234/v1. A hosted endpoint takes its key "
    "from ELSEWHERE_OPENAI_KEY, the only thing read from the environment",
    "backend \"ollama\" uses its native /api/chat, where the schema is passed "
    "as format and constrains decoding directly",
    "vllm: set base to http://your-gpu-host:8000/v1 - the tick itself needs "
    "almost no memory, so the model does not have to be here",
    "claude: pip install -e '.[llm]' and set ANTHROPIC_API_KEY; worth it for "
    "perceive/speak/reflect if the local model makes everyone sound alike",
    "a thinking-capable local model needs its thinking turned off or the JSON "
    "arrives inside the reasoning field: ollama -> extra {\"think\": false}, "
    "vllm -> extra {\"chat_template_kwargs\": {\"enable_thinking\": false}}",
    "change a whole backend at once with `elsewhere configure`; "
    "run `elsewhere doctor` after any change here",
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
            data["agents"].setdefault(name, {}).update(settings)
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
        settings.update(backend=backend, model=model)
        if base:
            settings["base"] = base
        else:
            settings.pop("base", None)
    return _write(root, data)
