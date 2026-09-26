#!/usr/bin/env bash
#
# Install an MLX model on this Mac (macOS only), write it into the world's
# configuration, and check every call site can reach it.
#
#   scripts/live.sh                       # Gemma 4 E2B, the default
#   MODEL=mlx-community/Llama-3.2-3B-Instruct-4bit scripts/live.sh
#   WORLD=elsewhere scripts/live.sh       # a world other than ./world
#
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${MODEL:-mlx-community/gemma-4-E2B-it-qat-4bit}"
EMBEDDER="${EMBEDDER:-mlx-community/embeddinggemma-300m-8bit}"
VENV="${VENV:-.venv}"
WORLD="${WORLD:-world}"

say() { printf "\n\033[1m%s\033[0m\n" "$*"; }

say "1/3  python environment, with MLX"
if [ ! -d "$VENV" ]; then python3 -m venv "$VENV"; fi
# shellcheck disable=SC1091
. "$VENV/bin/activate"
pip install -qe ".[mlx]" >/dev/null

say "2/3  fetching $MODEL and $EMBEDDER (this is the slow part; cached afterwards)"
MODEL="$MODEL" EMBEDDER="$EMBEDDER" python - <<'PY'
import os
from huggingface_hub import snapshot_download

for name in (os.environ["MODEL"], os.environ["EMBEDDER"]):
    print(f"     {name} at {snapshot_download(name)}")
PY

say "3/3  pointing $WORLD at it; can every call site reach a mind?"
elsewhere --world "$WORLD" configure --backend mlx --model "$MODEL"
elsewhere --world "$WORLD" configure --backend mlx --model "$EMBEDDER" --call embed
elsewhere --world "$WORLD" doctor

say "done"
echo "If the embedder changed, place every memory again: elsewhere --world $WORLD reembed"
