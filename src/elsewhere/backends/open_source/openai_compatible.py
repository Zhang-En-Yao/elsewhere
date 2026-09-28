"""Anything that serves the OpenAI chat completions API, from your own machine."""

from __future__ import annotations

import os
import urllib.error

from .. import Call, Settings
from .http import post


class OpenAICompatibleBackend:
    """Tries a json_schema response format, falling back to json_object."""

    name = "openai"
    endpoint = "http://localhost:8000/v1"

    def _endpoint(self, settings: Settings) -> str:
        return (settings.endpoint or self.endpoint).rstrip("/")

    def _key(self) -> str:
        # The only setting read from the environment, since it is a secret.
        return os.environ.get("ELSEWHERE_OPENAI_KEY", "none")

    def payload(self, call: Call, model: str, temperature: float,
                strict: bool) -> dict:
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": call.system},
                         {"role": "user", "content": call.user}],
            "temperature": temperature,
        }
        if strict:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": call.name.value, "schema": call.schema,
                                "strict": False},
            }
        else:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def complete(self, call: Call, settings: Settings) -> str:
        headers = {"authorization": f"Bearer {self._key()}"}
        for strict in (True, False):
            payload = self.payload(call, settings.model, settings.temperature, strict)
            payload.update(settings.options)
            try:
                data = post(f"{self._endpoint(settings)}/chat/completions", payload,
                             settings.timeout, headers)
            except urllib.error.HTTPError as exception:
                if strict and exception.code in (400, 422):
                    continue                      # server has no schema support
                raise
            choices = data.get("choices") or [{}]
            return (choices[0].get("message") or {}).get("content", "")
        return ""
