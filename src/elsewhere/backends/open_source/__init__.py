"""Open-source models, which you run yourself.

Two shapes of the same thing. MLX runs the model inside this process on
Apple silicon, and compiles the JSON schema into a mask over the vocabulary
at every step, which is the most reliable way to get usable structure out of
a small model. Anything else - llama-server, LM Studio, vLLM on a GPU box -
speaks the OpenAI chat completions API, where the equivalent is
``response_format``.

The /v1 client is written against ``urllib``, so reaching a server needs no
dependency. MLX is an optional extra: ``pip install -e '.[mlx]'``.
"""
