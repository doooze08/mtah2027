#!/usr/bin/env bash
# Scaffold a new experiment: experiments/<id>/ (committed) and outputs/<id>/ (gitignored).
#
#   scripts/new_experiment.sh <algo_name> <short_desc>
#   -> experiments/20261025_<algo_name>_<short_desc>/{config.yaml,NOTES.md}
#   -> outputs/20261025_<algo_name>_<short_desc>/{submission,eval,logs}/
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <algo_name> <short_desc>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALGO="$1"
DESC="$2"
ID="$(date +%Y%m%d)_${ALGO}_${DESC}"
EXP_DIR="$ROOT/experiments/$ID"
OUT_DIR="$ROOT/outputs/$ID"

if [[ ! -d "$ROOT/algorithms/$ALGO" ]]; then
  echo "warning: algorithms/$ALGO does not exist yet" >&2
fi
if [[ -e "$EXP_DIR" ]]; then
  echo "error: $EXP_DIR already exists" >&2
  exit 1
fi

mkdir -p "$EXP_DIR" "$OUT_DIR/submission" "$OUT_DIR/eval" "$OUT_DIR/logs"
sed -e "s/^experiment_id: .*/experiment_id: $ID/" \
    -e "s/^algorithm: algo_name /algorithm: $ALGO /" \
    "$ROOT/experiments/_template/config.yaml" > "$EXP_DIR/config.yaml"
sed -e "s/<experiment_id>/$ID/" -e "s/<algo_name>/$ALGO/" \
    "$ROOT/experiments/_template/NOTES.md" > "$EXP_DIR/NOTES.md"

echo "experiments/$ID/"
echo "outputs/$ID/"
