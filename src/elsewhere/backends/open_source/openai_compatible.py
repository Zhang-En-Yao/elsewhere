"""Anything that serves the OpenAI chat completions API, from your own machine."""

from __future__ import annotations

import os
import urllib.error

from .. import Call, Settings
from .http import post


class OpenAICompatibleBackend:
    """vLLM, LM Studio, llama.cpp server, or anything else with /v1.

    Tries a json_schema response format first (vLLM supports it through guided
    decoding) and falls back to plain json_object for servers that do not.
    """

    name = "openai"
    base = "http://localhost:8000/v1"

    def _base(self, settings: Settings) -> str:
        return (settings.base or self.base).rstrip("/")

    def _key(self) -> str:
        # A secret, so the one thing that stays in the environment: it says
        # whether a server will answer, never which mind it is.
        return os.environ.get("ELSEWHERE_OPENAI_KEY", "none")

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
                "json_schema": {"name": call.name.value, "schema": call.schema,
                                "strict": False},
            }
        else:
            body["response_format"] = {"type": "json_object"}
        return body

    def complete(self, call: Call, settings: Settings) -> str:
        headers = {"authorization": f"Bearer {self._key()}"}
        for strict in (True, False):
            payload = self._body(call, settings.model, settings.temperature, strict)
            payload.update(settings.extra)
            try:
                data = post(f"{self._base(settings)}/chat/completions", payload,
                             settings.timeout, headers)
            except urllib.error.HTTPError as exc:
                if strict and exc.code in (400, 422):
                    continue                      # server has no schema support
                raise
            choices = data.get("choices") or [{}]
            return (choices[0].get("message") or {}).get("content", "")
        return ""
