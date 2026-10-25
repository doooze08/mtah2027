#!/usr/bin/env bash
# Validate, then score, every submission of one experiment with the OFFICIAL evaluation code.
# Reads outputs/<id>/submission/*.csv, writes outputs/<id>/eval/. Extra args go to run_evaluation.py.
#
#   scripts/evaluate.sh <experiment_id>
#   scripts/evaluate.sh <experiment_id> --bootstrap 1000
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <experiment_id> [run_evaluation.py args...]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ID="$1"; shift
SUB_DIR="$ROOT/outputs/$ID/submission"
EVAL_DIR="$ROOT/outputs/$ID/eval"
PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || PY="${PYTHON:-python3}"

shopt -s nullglob
files=("$SUB_DIR"/*.csv)
if [[ ${#files[@]} -eq 0 ]]; then
  echo "error: no CSV in $SUB_DIR" >&2
  exit 1
fi

for f in "${files[@]}"; do
  "$PY" "$ROOT/evaluation/validate_submission.py" "$f"
done

mkdir -p "$EVAL_DIR"
"$PY" "$ROOT/evaluation/run_evaluation.py" --results "$SUB_DIR" --out "$EVAL_DIR" "$@"
