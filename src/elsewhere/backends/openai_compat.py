"""Local and self-hosted models: Ollama, vLLM, LM Studio.

Two shapes of the same thing. Ollama's native ``/api/chat`` takes a JSON schema
in ``format`` and constrains decoding to it, which is the most reliable way to
get usable structure out of a small model. Everything else speaks the
OpenAI chat completions API, where the equivalent is ``response_format``.

Written against ``urllib`` so the world keeps its promise of no dependencies.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import List, Optional

from . import Call

TIMEOUT = float(os.environ.get("ELSEWHERE_HTTP_TIMEOUT", "180"))


def _post(url: str, payload: dict, headers: Optional[dict] = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"content-type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


class OllamaBackend:
    """Ollama's own API, with the schema used as a decoding grammar.

    Note for Gemma 4 and other thinking-capable models: pass
    ``"extra": {"think": false}`` in the call's settings, or the JSON comes
    back inside the reasoning field instead of the content.
    """

    name = "ollama"

    def __init__(self, base: Optional[str] = None):
        self.base = (base or os.environ.get("OLLAMA_HOST")
                     or "http://localhost:11434").rstrip("/")

    def complete(self, call: Call, model: str, temperature: float,
                 extra: Optional[dict] = None) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": call.system},
                         {"role": "user", "content": call.user}],
            "format": call.schema,          # token-level constraint, not a hint
            "stream": False,
            "options": {"temperature": temperature},
        }
        payload.update(extra or {})
        data = _post(f"{self.base}/api/chat", payload)
        return (data.get("message") or {}).get("content", "")

    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        data = _post(f"{self.base}/api/embed", {"model": model, "input": list(texts)})
        return [[float(x) for x in v] for v in data.get("embeddings", [])]


class OpenAICompatBackend:
    """vLLM, LM Studio, llama.cpp server, or anything else with /v1.

    Tries a json_schema response format first (vLLM supports it through guided
    decoding) and falls back to plain json_object for servers that do not.
    """

    name = "openai"

    def __init__(self, base: Optional[str] = None, api_key: Optional[str] = None):
        self.base = (base or os.environ.get("ELSEWHERE_OPENAI_BASE")
                     or "http://localhost:8000/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("ELSEWHERE_OPENAI_KEY", "none")

    def _body(self, call: Call, model: str, temperature: float,
              strict: bool) -> dict:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": call.system},
                         {"role": "user", "content": call.user}],
            "temperature": temperature,
        }
        if strict:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": call.name, "schema": call.schema,
                                "strict": False},
            }
        else:
            body["response_format"] = {"type": "json_object"}
        return body

    def complete(self, call: Call, model: str, temperature: float,
                 extra: Optional[dict] = None) -> str:
        headers = {"authorization": f"Bearer {self.api_key}"}
        for strict in (True, False):
            payload = self._body(call, model, temperature, strict)
            payload.update(extra or {})
            try:
                data = _post(f"{self.base}/chat/completions", payload, headers)
            except urllib.error.HTTPError as exc:
                if strict and exc.code in (400, 422):
                    continue                      # server has no schema support
                raise
            choices = data.get("choices") or [{}]
            return (choices[0].get("message") or {}).get("content", "")
        return ""


class VLLMBackend(OpenAICompatBackend):
    """vLLM, with its own name for the same idea.

    vLLM constrains decoding through ``guided_json`` (xgrammar or outlines
    underneath) rather than OpenAI's ``response_format``. Recent builds accept
    both; this sends the one that has worked the longest, and inherits the
    fallback for servers that accept neither.

    It is the right backend when the model lives somewhere with a GPU - a
    workstation, a cluster, a rented box - and only the tick runs on the
    laptop. Point ``base`` at it:

        ELSEWHERE_OPENAI_BASE=http://gpu-box:8000/v1
    """

    name = "vllm"

    def _body(self, call: Call, model: str, temperature: float,
              strict: bool) -> dict:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": call.system},
                         {"role": "user", "content": call.user}],
            "temperature": temperature,
        }
        if strict:
            body["guided_json"] = call.schema
            body["guided_decoding_backend"] = "xgrammar"
        else:
            body["response_format"] = {"type": "json_object"}
        return body
