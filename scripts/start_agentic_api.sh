#!/usr/bin/env bash
# Start lightweight Boardman Agentic API on :8000 (no full .env needed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv-agentic ]]; then
  echo "Creating .venv-agentic …"
  python3 -m venv .venv-agentic
  .venv-agentic/bin/pip install -q -U pip
  .venv-agentic/bin/pip install -q 'fastapi>=0.115' 'uvicorn[standard]>=0.32' 'chess>=1.10' 'eth-account>=0.10' 'pyyaml>=6'
fi

mkdir -p gaming
[[ -e gaming/src ]] || ln -sfn ../src gaming/src
[[ -e gaming/__init__.py ]] || touch gaming/__init__.py
[[ -e gaming/config ]] || ln -sfn ../config gaming/config
[[ -e gaming/data ]] || ln -sfn ../data gaming/data

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export BOARDMAN_USE_STOCKFISH="${BOARDMAN_USE_STOCKFISH:-1}"
export GEO_FENCE_DISABLED=1

exec .venv-agentic/bin/python scripts/run_agentic_api.py
