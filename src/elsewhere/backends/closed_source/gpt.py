"""OpenAI's own models, through the same /v1 dialect the open-source servers speak."""

from __future__ import annotations

import os

from ..open_source.openai_compatible import OpenAICompatibleBackend


class GPTBackend(OpenAICompatibleBackend):
    """The /v1 backend with OpenAI's address and OpenAI's key filled in."""

    name = "gpt"
    base = "https://api.openai.com/v1"

    def _key(self) -> str:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        return key
