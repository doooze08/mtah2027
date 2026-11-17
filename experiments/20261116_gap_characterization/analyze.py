#!/usr/bin/env python3
"""Distribution and single-feature AUC tables for gap characterization."""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
for path in (HERE, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from features import POSITION_CATEGORIES  # noqa: E402

OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "20261116_gap_characterization")

CONTINUOUS_FEATURES = (
    "reappear_speed_0p5s_m_s",
    "disappear_speed_1s_m_s",
    "reappear_to_disappear_m",
    "reappear_to_disappear_after_team_shift_m",
    "f1_speed_med",
    "f1_speed_p90",
    "speed_gt4_count_med",
    "speed_gt4_count_p90",
    "team_speed_med",
    "team_speed_p90",
    "team_cos_med",
    "team_cos_p90",
    "dispersion_med",
    "dispersion_p90",
)

GROUPS = (
    "dead_gap",
    "real_live_gap",
    "artificial_live",
    "dead_visible",
    "suspicious_gap",
)


def add_groups(frame):
    frame = frame.copy()
    frame["sample_type"] = frame["sample_type"].astype(str)
    live = frame["sample_type"].eq("live_gap")
    frame["sample_type"] = np.where(
        live & frame["suspicious"].astype(bool), "suspicious_gap",
        np.where(live, "real_live_gap", frame["sample_type"]))
    return frame


def distribution(frame, split):
    rows = []
    data = frame if split == "all" else frame[frame["split"] == split]
    for group in GROUPS:
        group_data = data[data["sample_type"] == group]
        if group_data.empty:
            continue
        for feature in CONTINUOUS_FEATURES:
            values = group_data[feature].to_numpy(dtype=float)
            values = values[np.isfinite(values)]
            if len(values) == 0:
                continue
            rows.append({
                "split": split,
                "sample_type": group,
                "feature": feature,
                "n": len(values),
                "median": float(np.median(values)),
                "q1": float(np.percentile(values, 25)),
                "q3": float(np.percentile(values, 75)),
                "mean": float(np.mean(values)),
            })
        for feature in ("reappear_category", "disappear_category"):
            counts = group_data[feature].fillna("").value_counts()
            total = int(counts.sum())
            for category, count in counts.items():
                rows.append({
                    "split": split,
                    "sample_type": group,
                    "feature": feature,
                    "n": int(count),
                    "median": np.nan,
                    "q1": np.nan,
                    "q3": np.nan,
                    "mean": count / total if total else np.nan,
                    "category": category,
                })
    return rows


def auc_positive_vs_negative(positive, negative):
    positive = np.asarray(positive, dtype=float)
    negative = np.asarray(negative, dtype=float)
    positive = positive[np.isfinite(positive)]
    negative = negative[np.isfinite(negative)]
    if len(positive) == 0 or len(negative) == 0:
        return np.nan, len(positive), len(negative)
    values = np.r_[positive, negative]
    ranks = pd.Series(values).rank(method="average").to_numpy()
    rank_sum = ranks[:len(positive)].sum()
    auc = (rank_sum - len(positive) * (len(positive) + 1) / 2.0) / (
        len(positive) * len(negative))
    return float(auc), len(positive), len(negative)


def auc_table(frame, split):
    rows = []
    data = frame if split == "all" else frame[frame["split"] == split]
    dead = data[data["sample_type"] == "dead_gap"]
    live = data[data["sample_type"] == "artificial_live"]
    if dead.empty or live.empty:
        return rows
    for feature in CONTINUOUS_FEATURES:
        auc, n_live, n_dead = auc_positive_vs_negative(live[feature], dead[feature])
        if not np.isfinite(auc):
            continue
        rows.append({
            "split": split,
            "feature": feature,
            "kind": "continuous",
            "n_live": n_live,
            "n_dead": n_dead,
            "auc_live_gt_dead": auc,
            "separation": abs(auc - 0.5) * 2.0,
            "direction": "live_higher" if auc >= 0.5 else "dead_higher",
        })
    for feature in ("reappear_category", "disappear_category"):
        for category in POSITION_CATEGORIES:
            pos = live[feature].eq(category).astype(float)
            neg = dead[feature].eq(category).astype(float)
            if pos.nunique() == 1 and neg.nunique() == 1:
                continue
            auc, n_live, n_dead = auc_positive_vs_negative(pos, neg)
            if not np.isfinite(auc):
                continue
            rows.append({
                "split": split,
                "feature": f"{feature}={category}",
                "kind": "category_indicator",
                "n_live": n_live,
                "n_dead": n_dead,
                "auc_live_gt_dead": auc,
                "separation": abs(auc - 0.5) * 2.0,
                "direction": "live_higher" if auc >= 0.5 else "dead_higher",
            })
    return rows



def length_matched_auc(frame, split, low=5.0, high=15.0):
    """Post-hoc sensitivity: compare only samples with the same 5--15 s duration."""
    rows = []
    data = frame if split == "all" else frame[frame["split"] == split]
    data = data[data["length_s"].between(low, high)]
    dead = data[data["sample_type"] == "dead_gap"]
    live = data[data["sample_type"] == "artificial_live"]
    for feature in CONTINUOUS_FEATURES:
        auc, n_live, n_dead = auc_positive_vs_negative(live[feature], dead[feature])
        if np.isfinite(auc):
            rows.append({
                "split": split,
                "feature": feature,
                "n_live": n_live,
                "n_dead": n_dead,
                "auc_live_gt_dead": auc,
                "separation": abs(auc - 0.5) * 2.0,
            })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", default=[])
    parser.add_argument("--out-dir", default=OUTPUT_DIR)
    args = parser.parse_args()
    inputs = args.inputs or [os.path.join(OUTPUT_DIR, "samples_design.csv")]
    frame = pd.concat([pd.read_csv(path, dtype={"clip": str}) for path in inputs],
                      ignore_index=True)
    frame = add_groups(frame)
    os.makedirs(args.out_dir, exist_ok=True)

    dist_rows = []
    auc_rows = []
    for split in ("design", "test", "all"):
        dist_rows.extend(distribution(frame, split))
        auc_rows.extend(auc_table(frame, split))
    pd.DataFrame(dist_rows).to_csv(os.path.join(args.out_dir, "distributions.csv"), index=False)
    pd.DataFrame(auc_rows).to_csv(os.path.join(args.out_dir, "feature_auc.csv"), index=False)
    length_rows = []
    for split in ("design", "test", "all"):
        length_rows.extend(length_matched_auc(frame, split))
    pd.DataFrame(length_rows).to_csv(
        os.path.join(args.out_dir, "feature_auc_length_matched.csv"), index=False)
    frame[frame["sample_type"].isin(["real_live_gap", "suspicious_gap"])].to_csv(
        os.path.join(args.out_dir, "real_live_segments.csv"), index=False)
    frame.to_csv(os.path.join(args.out_dir, "samples_all.csv"), index=False)

    summary = {
        "inputs": inputs,
        "n_samples": int(len(frame)),
        "counts": frame.groupby(["split", "sample_type"]).size().unstack(fill_value=0)
        .to_dict(orient="index"),
        "length_seconds": {
            f"{key[0]}|{key[1]}": value
            for key, value in frame.groupby(["split", "sample_type"])["length_s"]
            .agg(["count", "median", "min", "max"]).to_dict(orient="index").items()
        },
    }
    with open(os.path.join(args.out_dir, "summary.json"), "w") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)

    ranked = pd.DataFrame(auc_rows)
    if not ranked.empty:
        ranked = ranked[ranked["split"] == "all"].sort_values("separation", ascending=False)
        print("Top features (all matches, artificial live vs dead gap):")
        print(ranked.head(20).to_string(index=False))
    print("counts by split/type:")
    print(frame.groupby(["split", "sample_type"]).size().to_string())


if __name__ == "__main__":
    main()
