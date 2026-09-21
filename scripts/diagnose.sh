#!/usr/bin/env bash
#
# Why will the MLX server not start? Ask each layer directly, without vllm-mlx
# in the way - it rewrites every ImportError as "mlx-lm is required", which
# hides the one line that matters.
#
# Everything goes to .elsewhere/diagnose.log inside the repo, so it can be read
# back without anyone having to copy and paste a traceback.
#
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p .elsewhere
OUT=.elsewhere/diagnose.log
PY="${PY:-.venv/bin/python}"
MODEL="${MODEL:-mlx-community/Llama-3.2-3B-Instruct-4bit}"

{
  echo "== machine =="
  sw_vers 2>/dev/null; uname -m
  "$PY" -c "import platform,sys; print('python', sys.version.split()[0], platform.machine())"

  echo; echo "== the real cause from the last server run =="
  if [ -f .elsewhere/server.log ]; then
    grep -n -B1 -A12 "direct cause" .elsewhere/server.log | head -40 || echo "(no chained exception in the log)"
  elif [ -f /tmp/elsewhere-server.log ]; then
    grep -n -B1 -A12 "direct cause" /tmp/elsewhere-server.log | head -40 || echo "(no chained exception in the log)"
  else
    echo "(no server log yet)"
  fi

  echo; echo "== layer 1: can MLX load its Metal library at all? =="
  "$PY" -c "import mlx.core as mx; print('mlx', mx.__version__, 'device', mx.default_device())" 2>&1 | tail -15

  echo; echo "== layer 2: can transformers build a tokenizer? =="
  "$PY" -c "from transformers import AutoTokenizer; print('transformers ok')" 2>&1 | tail -15

  echo; echo "== layer 2b: the import transformers' lazy loader hides =="
  # Going through AutoConfig turns any failure in here into "Could not import
  # module 'LlamaConfig'". Importing the file directly shows what really broke.
  "$PY" -X importtime -c "import transformers.models.llama.configuration_llama as m; print('llama config ok')" 2>.elsewhere/importtime.log | tail -1
  "$PY" -c "import transformers.models.llama.configuration_llama" 2>&1 | tail -25

  echo; echo "== layer 3: can mlx-lm load the model by itself? =="
  "$PY" -c "from mlx_lm import load; load('$MODEL'); print('mlx-lm loaded $MODEL')" 2>&1 | tail -20

  echo; echo "== versions =="
  "$PY" -m pip list 2>/dev/null | grep -iE "^(mlx|vllm|transformers|torch|huggingface|tokenizers) "
} 2>&1 | tee "$OUT"

echo
echo "written to $OUT"
