"""MLX, Apple's own framework: the model runs inside this process, on the GPU."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .. import Call, Settings

# Generous; under a grammar generation stops when the JSON closes.
MAX_TOKENS = 1024


def closed(schema: Any) -> Any:
    """Set ``additionalProperties: false`` on every object, so the grammar
    doesn't let the model invent fields."""
    if isinstance(schema, list):
        return [closed(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: closed(v) for k, v in schema.items()}
    if "properties" in out:
        out.setdefault("additionalProperties", False)
    return out


class MLXBackend:
    """Runs ``mlx-lm`` in-process with an ``llguidance`` token mask. Weights
    load once per process. Thinking is off unless ``extra`` says otherwise.
    Needs Apple silicon and ``pip install -e '.[mlx]'``."""

    name = "mlx"

    def __init__(self) -> None:
        self._minds: Dict[str, Tuple[Any, Any, Any, dict]] = {}
        self._embedders: Dict[str, Tuple[Any, Any]] = {}
        # MLX is not thread-safe.
        self._lock = threading.Lock()

    def _mind(self, model: str) -> Tuple[Any, Any, Any, dict]:
        if model not in self._minds:
            import llguidance.hf
            from huggingface_hub import snapshot_download
            from mlx_lm import load

            loaded, tokenizer, *_ = load(model)
            where = Path(model) if Path(model).exists() \
                else Path(snapshot_download(model, local_files_only=True))
            # The model's own sampling defaults, except temperature.
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
                # After the first call, feed the grammar the token just sampled.
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
