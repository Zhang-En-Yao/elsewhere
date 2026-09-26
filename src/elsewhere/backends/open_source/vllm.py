"""vLLM, on this machine or on a GPU box somewhere else."""

from __future__ import annotations

from .. import Call
from .openai_compatible import OpenAICompatibleBackend


class VLLMBackend(OpenAICompatibleBackend):
    """vLLM, with its own name for the same idea.

    vLLM constrains decoding through ``guided_json`` (xgrammar or outlines
    underneath) rather than OpenAI's ``response_format``. Recent builds accept
    both; this sends the one that has worked the longest, and inherits the
    fallback for servers that accept neither.

    It is the right backend when the model lives somewhere with a GPU - a
    workstation, a cluster, a rented box - and only the tick runs on the
    laptop. Point ``base`` at it in the configuration:

        "base": "http://gpu-box:8000/v1"
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
