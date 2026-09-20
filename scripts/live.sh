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
#
set -euo pipefail
cd "$(dirname "$0")/.."

RUNTIME="${RUNTIME:-vllm-mlx}"
PORT="${PORT:-8000}"
MODEL="${MODEL:-mlx-community/Llama-3.2-3B-Instruct-4bit}"
VENV="${VENV:-.venv}"
SERVER_PID=""

say() { printf "\n\033[1m%s\033[0m\n" "$*"; }

cleanup() {
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
    sleep 2; waited=$((waited + 2))
    printf "."
  done
  return 1
}

say "1/5  python environment"
if [ ! -d "$VENV" ]; then python3 -m venv "$VENV"; fi
# shellcheck disable=SC1091
. "$VENV/bin/activate"
pip install -qe . >/dev/null

case "$RUNTIME" in
  vllm-mlx)
    say "2/5  vllm-mlx"
    python -c "import vllm_mlx" 2>/dev/null || pip install -q vllm-mlx
    say "3/5  serving $MODEL on :$PORT"
    vllm-mlx serve "$MODEL" --port "$PORT" >/tmp/elsewhere-server.log 2>&1 &
    SERVER_PID=$!
    BASE="http://localhost:$PORT/v1"
    HEALTH="$BASE/models"
    export ELSEWHERE_BACKEND=openai ELSEWHERE_OPENAI_BASE="$BASE"
    ;;
  ollama)
    say "2/5  ollama"
    command -v ollama >/dev/null || { echo "install it first: brew install ollama"; exit 1; }
    pgrep -qx ollama || { ollama serve >/tmp/elsewhere-server.log 2>&1 & SERVER_PID=$!; }
    ollama pull "$MODEL"
    say "3/5  serving $MODEL on :11434"
    HEALTH="http://localhost:11434/api/tags"
    export ELSEWHERE_BACKEND=ollama
    ;;
  *) echo "RUNTIME must be vllm-mlx or ollama"; exit 1 ;;
esac

export ELSEWHERE_MODEL="$MODEL"
printf "     waiting for the model to load"
if ! wait_for "$HEALTH" 300; then
  echo; echo "the server never came up. last lines:"; tail -20 /tmp/elsewhere-server.log; exit 1
fi
echo " up"

say "4/5  can every call site reach a mind?"
elsewhere doctor

say "5/5  the fire: four people, one street"
ELSEWHERE_LIVE=1 python -m unittest tests.test_fire -v 2>&1 | tail -40

say "done"
echo "Server log: /tmp/elsewhere-server.log"
echo "If the four accounts above read like four people, the model is good enough."
echo "If they read like one narrator, try a different MODEL= and run this again."
