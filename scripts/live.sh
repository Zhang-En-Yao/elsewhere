#!/usr/bin/env bash
#
# Serve a model on this machine, check it can be reached, and put the fire to
# it. Everything here has to run on macOS itself: MLX does not exist anywhere
# else, and a server bound to this machine's localhost is not reachable from
# anywhere but this machine.
#
#   scripts/live.sh                       # vllm-mlx, Llama 3.2 3B, 4-bit
#   MODEL=mlx-community/Phi-4-mini-instruct-4bit scripts/live.sh
#   RUNTIME=ollama MODEL=phi-4-mini scripts/live.sh
#   KEEP=1 scripts/live.sh                # leave the server up between runs
#
# The first run downloads the weights, which on a slow line takes longer than
# anything else here. They are cached, so every run after that is quick.
#
set -euo pipefail
cd "$(dirname "$0")/.."

RUNTIME="${RUNTIME:-vllm-mlx}"
PORT="${PORT:-8000}"
MODEL="${MODEL:-mlx-community/Llama-3.2-3B-Instruct-4bit}"
VENV="${VENV:-.venv}"
SERVER_PID=""
LOG="${LOG:-/tmp/elsewhere-server.log}"

say() { printf "\n\033[1m%s\033[0m\n" "$*"; }

cleanup() {
  if [ -n "${KEEP:-}" ] && [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    say "leaving the server up (pid $SERVER_PID) - KEEP was set"
    echo "  stop it with: kill $SERVER_PID"
    return 0
  fi
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    say "stopping the server (pid $SERVER_PID)"
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

wait_for() {                      # wait_for <url> <seconds>
  local url="$1" limit="$2" waited=0
  while [ "$waited" -lt "$limit" ]; do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then return 0; fi
    if [ -n "$SERVER_PID" ] && ! kill -0 "$SERVER_PID" 2>/dev/null; then
      return 2                    # it died; no point waiting out the clock
    fi
    sleep 2; waited=$((waited + 2))
    if [ $((waited % 20)) -eq 0 ]; then printf " %ss" "$waited"; fi
  done
  return 1
}

fetch_model() {                   # pull the weights before anything is timed
  say "3/6  fetching $MODEL (this is the slow part; cached afterwards)"
  MODEL="$MODEL" python - <<'PY'
import os
from huggingface_hub import snapshot_download

print(f"     weights at {snapshot_download(os.environ['MODEL'])}")
PY
}

say "1/6  python environment"
if [ ! -d "$VENV" ]; then python3 -m venv "$VENV"; fi
# shellcheck disable=SC1091
. "$VENV/bin/activate"
pip install -qe . >/dev/null

case "$RUNTIME" in
  vllm-mlx)
    say "2/6  vllm-mlx"
    python -c "import vllm_mlx, mlx_lm" 2>/dev/null || pip install -q vllm-mlx mlx-lm
    python -c "import huggingface_hub" 2>/dev/null || pip install -q huggingface_hub
    fetch_model
    say "4/6  serving $MODEL on :$PORT"
    vllm-mlx serve "$MODEL" --port "$PORT" >"$LOG" 2>&1 &
    SERVER_PID=$!
    BASE="http://localhost:$PORT/v1"
    HEALTH="$BASE/models"
    export ELSEWHERE_BACKEND=openai ELSEWHERE_OPENAI_BASE="$BASE"
    ;;
  ollama)
    say "2/6  ollama"
    command -v ollama >/dev/null || { echo "install it first: brew install ollama"; exit 1; }
    pgrep -qx ollama || { ollama serve >"$LOG" 2>&1 & SERVER_PID=$!; }
    say "3/6  fetching $MODEL (cached afterwards)"
    ollama pull "$MODEL"
    say "4/6  serving $MODEL on :11434"
    HEALTH="http://localhost:11434/api/tags"
    export ELSEWHERE_BACKEND=ollama
    ;;
  *) echo "RUNTIME must be vllm-mlx or ollama"; exit 1 ;;
esac

export ELSEWHERE_MODEL="$MODEL"
printf "     waiting for it to load:"
wait_for "$HEALTH" 600 && ready=0 || ready=$?
if [ "${ready:-1}" -eq 2 ]; then
  echo; echo "The server exited while starting up. The last lines of its log:"
  tail -25 "$LOG"
  exit 1
elif [ "${ready:-1}" -ne 0 ]; then
  echo; echo "The server did not answer in ten minutes. The last lines of its log:"
  tail -20 "$LOG"
  exit 1
fi
echo " up"

say "5/6  can every call site reach a mind?"
elsewhere doctor

say "6/6  the fire: four people, one street"
ELSEWHERE_LIVE=1 python -m unittest tests.test_fire -v 2>&1 | tail -40

say "done"
echo "Server log: $LOG"
echo "If the four accounts above read like four people, the model is good enough."
echo "If they read like one narrator, try a different MODEL= and run this again."
