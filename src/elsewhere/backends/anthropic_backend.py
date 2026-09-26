"""Claude, for the calls where judgement is the whole job.

Schema is given as a tool definition, which is how this API constrains shape.
Imported lazily: a world that never uses it never needs the package.
"""

from __future__ import annotations

import os
from . import Call, Settings


class AnthropicBackend:
    name = "claude"

    def __init__(self, max_tokens: int = 600):
        self.max_tokens = max_tokens
        self._client = None

    def _client_or_raise(self):
        if self._client is None:
            import anthropic                       # noqa: F401  (optional extra)
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("ANTHROPIC_API_KEY is not set")
            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, call: Call, settings: Settings) -> str:
        import json

        client = self._client_or_raise()
        tool = {"name": call.name.value, "description": f"Answer for {call.name}",
                "input_schema": {**call.schema, "type": "object"}}
        response = client.messages.create(
            model=settings.model, max_tokens=self.max_tokens,
            temperature=settings.temperature, timeout=settings.timeout,
            system=call.system, tools=[tool],
            tool_choice={"type": "tool", "name": call.name.value},
            messages=[{"role": "user", "content": call.user}],
            **settings.extra,
        )
        for block in response.content:
            if getattr(block, "type", "") == "tool_use":
                return json.dumps(block.input, ensure_ascii=False)
        return "".join(getattr(b, "text", "") for b in response.content)
