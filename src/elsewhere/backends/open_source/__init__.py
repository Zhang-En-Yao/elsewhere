"""Open-source models, which you run yourself: Ollama, vLLM, LM Studio, llama.cpp.

Two shapes of the same thing. Ollama's native ``/api/chat`` takes a JSON schema
in ``format`` and constrains decoding to it, which is the most reliable way to
get usable structure out of a small model. Everything else speaks the
OpenAI chat completions API, where the equivalent is ``response_format``.

Written against ``urllib`` so the world keeps its promise of no dependencies.
"""
