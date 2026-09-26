"""Ollama, through its own API rather than the OpenAI-shaped one."""

from __future__ import annotations

from typing import List

from .. import Call, Settings
from .http import post


class OllamaBackend:
    """Ollama's own API, with the schema used as a decoding grammar.

    Note for Gemma 4 and other thinking-capable models: pass
    ``"extra": {"think": false}`` in the call's settings, or the JSON comes
    back inside the reasoning field instead of the content.
    """

    name = "ollama"
    base = "http://localhost:11434"

    def _base(self, settings: Settings) -> str:
        return (settings.base or self.base).rstrip("/")

    def complete(self, call: Call, settings: Settings) -> str:
        payload = {
            "model": settings.model,
            "messages": [{"role": "system", "content": call.system},
                         {"role": "user", "content": call.user}],
            "format": call.schema,          # token-level constraint, not a hint
            "stream": False,
            "options": {"temperature": settings.temperature},
        }
        payload.update(settings.extra)
        data = post(f"{self._base(settings)}/api/chat", payload, settings.timeout)
        return (data.get("message") or {}).get("content", "")

    def embed(self, texts: List[str], settings: Settings) -> List[List[float]]:
        data = post(f"{self._base(settings)}/api/embed",
                     {"model": settings.model, "input": list(texts)}, settings.timeout)
        return [[float(x) for x in v] for v in data.get("embeddings", [])]
