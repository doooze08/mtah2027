#!/usr/bin/env bash
# Create a local virtual environment and install the official requirements.
#
#   scripts/setup_env.sh            # evaluation only: numpy + pandas
#   scripts/setup_env.sh --starter  # also kloppy, matplotlib, notebook (for starter/*.ipynb)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
REQ="requirements.txt"
[[ "${1:-}" == "--starter" ]] && REQ="requirements-starter.txt"

cd "$ROOT"
[[ -d .venv ]] || "$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r "$REQ"

echo
echo "Done. Activate with:  source .venv/bin/activate"
