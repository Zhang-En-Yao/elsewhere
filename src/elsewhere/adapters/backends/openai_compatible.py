"""Anything that serves the OpenAI chat completions API, from your own machine."""

from __future__ import annotations

import os
from typing import List

import openai

from . import Call, Settings


class OpenAICompatibleBackend:
    """Tries a json_schema response format, falling back to json_object."""

    name = "openai"
    endpoint = "http://localhost:8000/v1"

    def _endpoint(self, settings: Settings) -> str:
        return (settings.endpoint or self.endpoint).rstrip("/")

    def _key(self) -> str:
        # The only setting read from the environment, since it is a secret.
        return os.environ.get("ELSEWHERE_OPENAI_KEY", "none")

    def payload(self, call: Call, model: str, temperature: float, strict: bool) -> dict:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": call.system},
                {"role": "user", "content": call.user},
            ],
            "temperature": temperature,
        }
        if strict:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": str(call.name), "schema": call.schema, "strict": False},
            }
        else:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def complete(self, call: Call, settings: Settings) -> str:
        client = openai.OpenAI(
            base_url=self._endpoint(settings), api_key=self._key(), timeout=settings.timeout
        )
        for strict in (True, False):
            payload = self.payload(call, settings.model, settings.temperature, strict)
            try:
                response = client.chat.completions.create(**payload, extra_body=settings.options)
            except (openai.BadRequestError, openai.UnprocessableEntityError):
                if strict:
                    continue  # server has no schema support
                raise
            return response.choices[0].message.content or ""
        return ""

    def embed(self, texts: List[str], settings: Settings) -> List[List[float]]:
        client = openai.OpenAI(
            base_url=self._endpoint(settings), api_key=self._key(), timeout=settings.timeout
        )
        response = client.embeddings.create(model=settings.model, input=list(texts))
        return [
            list(embedding.embedding)
            for embedding in sorted(response.data, key=lambda embedding: embedding.index)
        ]
