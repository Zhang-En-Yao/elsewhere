"""MLX, Apple's own framework: the model runs inside this process, on the GPU."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .. import Call, Settings

# Enough for the longest answer any call site asks for, several times over.
# Under a grammar the answer ends when the JSON closes, not when this runs out.
MAX_TOKENS = 1024


def closed(schema: Any) -> Any:
    """The schema with every object shut to fields it does not name.

    JSON Schema leaves an object open unless told otherwise, and a grammar
    compiled from it faithfully lets the model add fields of its own. Ollama
    closed them by default; this does the same, so a small model spends its
    tokens on the fields that were asked for.
    """
    if isinstance(schema, list):
        return [closed(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: closed(v) for k, v in schema.items()}
    if "properties" in out:
        out.setdefault("additionalProperties", False)
    return out


class MLXBackend:
    """A model from the Hugging Face hub, run with ``mlx-lm`` in this process.

    There is no server. The first call loads the weights and every call after
    that in the same process reuses them, so a tick pays for loading once. The
    schema is compiled by ``llguidance`` into a mask over the vocabulary at
    every step - a token-level constraint, not a hint, as with Ollama's
    ``format``.

    ``extra`` goes to the chat template. Thinking is off unless it says
    otherwise, because a thinking model puts its JSON after the reasoning, and
    the grammar would have it skip the reasoning anyway.

    The embedder is the same arrangement through ``mlx-embeddings``.

    Needs ``pip install -e '.[mlx]'``, and Apple silicon.
    """

    name = "mlx"

    def __init__(self) -> None:
        self._minds: Dict[str, Tuple[Any, Any, Any, dict]] = {}
        self._embedders: Dict[str, Tuple[Any, Any]] = {}
        # One GPU, one model at a time: MLX is not safe to drive from two
        # threads, and nothing here would be faster for trying.
        self._lock = threading.Lock()

    def _mind(self, model: str) -> Tuple[Any, Any, Any, dict]:
        if model not in self._minds:
            import llguidance.hf
            from huggingface_hub import snapshot_download
            from mlx_lm import load

            loaded, tokenizer, *_ = load(model)
            where = Path(model) if Path(model).exists() \
                else Path(snapshot_download(model, local_files_only=True))
            # How the model was meant to be sampled, apart from temperature,
            # which is the call site's to choose.
            sampling: dict = {}
            generation = where / "generation_config.json"
            if generation.exists():
                config = json.loads(generation.read_text(encoding="utf-8"))
                sampling = {k: config[k] for k in ("top_p", "top_k") if k in config}
            self._minds[model] = (loaded, tokenizer,
                                  llguidance.hf.from_tokenizer(tokenizer._tokenizer),
                                  sampling)
        return self._minds[model]

    def complete(self, call: Call, settings: Settings) -> str:
        import llguidance
        import llguidance.mlx as guidance
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        with self._lock:
            model, tokenizer, vocabulary, sampling = self._mind(settings.model)
            prompt = tokenizer.apply_chat_template(
                [{"role": "system", "content": call.system},
                 {"role": "user", "content": call.user}],
                add_generation_prompt=True,
                **{"enable_thinking": False, **settings.extra})
            matcher = llguidance.LLMatcher(
                vocabulary,
                llguidance.LLMatcher.grammar_from_json_schema(closed(call.schema)))
            if matcher.is_error():
                raise ValueError(f"schema did not compile: {matcher.get_error()}")
            mask = guidance.allocate_token_bitmask(1, vocabulary.vocab_size)
            started = [False]

            def constrain(tokens, logits):
                # The first call sees the prompt; every one after it sees
                # the prompt and one more token, which the grammar has to
                # hear about before it can say what may come next.
                if started[0]:
                    matcher.consume_token(int(tokens[-1]))
                started[0] = True
                guidance.fill_next_token_bitmask(matcher, mask, 0)
                return guidance.apply_token_bitmask(logits, mask)

            sampler = make_sampler(temp=settings.temperature, **sampling)
            deadline = time.time() + settings.timeout
            pieces: List[str] = []
            for step in stream_generate(model, tokenizer, prompt,
                                        max_tokens=MAX_TOKENS, sampler=sampler,
                                        logits_processors=[constrain]):
                pieces.append(step.text)
                if matcher.is_error():
                    break
                if time.time() > deadline:
                    raise TimeoutError(f"no answer within {settings.timeout:.0f}s")
            return "".join(pieces)

    def embed(self, texts: List[str], settings: Settings) -> List[List[float]]:
        import mlx.core as mx
        from mlx_embeddings.utils import load

        with self._lock:
            if settings.model not in self._embedders:
                self._embedders[settings.model] = load(settings.model)
            model, tokenizer = self._embedders[settings.model]
            batch = tokenizer(list(texts), padding=True, truncation=True,
                              return_tensors="np")
            out = model(mx.array(batch["input_ids"]),
                        attention_mask=mx.array(batch["attention_mask"]))
            return [[float(x) for x in v] for v in out.text_embeds.tolist()]
