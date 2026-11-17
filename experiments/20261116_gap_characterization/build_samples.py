#!/usr/bin/env python3
"""Build per-segment gap-characterization samples.

Design matches (1, 2) and the held-out match (3) are written separately so that the
feature definitions can be frozen before Game 3 is read.
"""

import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
for path in (HERE, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from features import build_samples  # noqa: E402

OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "20261116_gap_characterization")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", default="1,2",
                        help="comma-separated Metrica game numbers")
    parser.add_argument("--seed", type=int, default=20261116)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    matches = [int(item) for item in args.matches.split(",") if item.strip()]
    rows = build_samples(matches, seed=args.seed)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = args.out or os.path.join(
        OUTPUT_DIR, "samples_design.csv" if 3 not in matches else "samples_test.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"wrote {len(rows)} samples to {path}")
    print(pd.DataFrame(rows)["sample_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
