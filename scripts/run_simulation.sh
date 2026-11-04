#!/usr/bin/env bash
# Run one experiment's algorithm on a simulation dataset, then score it clip by clip.
# The dataset must already exist (python -m simulation.generate ...); this script never makes one.
#
#   scripts/run_simulation.sh <experiment_id> <dataset_id>
#   -> outputs/<experiment_id>/simulation/<dataset_id>/{predictions.csv,per_clip.csv,report.md}
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <experiment_id> <dataset_id>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || PY="${PYTHON:-python3}"

cd "$ROOT"
"$PY" -m simulation.run_algorithm --experiment "$1" --dataset "$2"
"$PY" -m simulation.evaluate --experiment "$1" --dataset "$2"
