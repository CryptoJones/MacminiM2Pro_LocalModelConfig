#!/usr/bin/env bash
# Set up the Gemma 4 12B local server on Apple Silicon.
# Creates a Python 3.12 venv (MLX has no 3.14 wheels), installs deps,
# and downloads the 4-bit MLX weights (~10 GB).
set -euo pipefail
cd "$(dirname "$0")"

MODEL="mlx-community/gemma-4-12B-4bit"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' is required (https://github.com/astral-sh/uv). Install it and re-run." >&2
  exit 1
fi

echo ">> creating venv (.venv) with Python 3.12"
uv venv --python 3.12 .venv

echo ">> installing dependencies"
uv pip install --python .venv -r requirements.txt

echo ">> downloading weights: $MODEL (~10 GB)"
./.venv/bin/hf download "$MODEL"

cat <<'NEXT'

Done. Next steps:

  1) Raise the Metal GPU memory ceiling (required; resets on reboot):
       sudo sysctl iogpu.wired_limit_mb=13500

  2) Start the server (binds 0.0.0.0:8080):
       ./.venv/bin/python server.py

  3) From a LAN client:
       curl http://<THIS_MAC_LAN_IP>:8080/v1/chat/completions \
         -H 'Content-Type: application/json' \
         -d '{"messages":[{"role":"user","content":"hello"}]}'

NEXT
