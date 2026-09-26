"""Google's Gemini, through the OpenAI-compatible endpoint it offers."""

from __future__ import annotations

import os

from ..open_source.openai_compatible import OpenAICompatibleBackend


class GeminiBackend(OpenAICompatibleBackend):
    """The /v1 backend with Gemini's address and Gemini's key filled in."""

    name = "gemini"
    base = "https://generativelanguage.googleapis.com/v1beta/openai"

    def _key(self) -> str:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        return key
