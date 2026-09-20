"""Claude, for the calls where judgement is the whole job.

Schema is given as a tool definition, which is how this API constrains shape.
Imported lazily: a world that never uses it never needs the package.
"""

from __future__ import annotations

import os
from typing import Optional

from . import Call


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

    def complete(self, call: Call, model: str, temperature: float,
                 extra: Optional[dict] = None) -> str:
        import json

        client = self._client_or_raise()
        tool = {"name": call.name, "description": f"Answer for {call.name}",
                "input_schema": {**call.schema, "type": "object"}}
        response = client.messages.create(
            model=model, max_tokens=self.max_tokens, temperature=temperature,
            system=call.system, tools=[tool],
            tool_choice={"type": "tool", "name": call.name},
            messages=[{"role": "user", "content": call.user}],
            **(extra or {}),
        )
        for block in response.content:
            if getattr(block, "type", "") == "tool_use":
                return json.dumps(block.input, ensure_ascii=False)
        return "".join(getattr(b, "text", "") for b in response.content)
