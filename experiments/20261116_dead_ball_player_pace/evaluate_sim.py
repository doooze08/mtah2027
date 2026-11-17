"""Score the four player-pace arms on a generated simulation dataset.

This is a regression check, not evidence that the rule generalizes: the simulator's
collective-pace behaviour is built from the same assumption as the rule.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import argparse
import json

import numpy as np
import pandas as pd
import yaml

from simulation.core import io
from simulation.core.checks import collapse
from simulation.evaluate import score_clip
from simulation.generate import assign_clip_ids, build_clips

EXPERIMENT = "20261116_dead_ball_player_pace"
ARMS = ("off", "gap", "restart", "both")
OUT = os.path.join(io.REPO_ROOT, "outputs", EXPERIMENT, "eval")


def predictions_path(dataset, arm):
    return os.path.join(io.REPO_ROOT, "outputs", EXPERIMENT, arm, "simulation",
                        dataset, "predictions.csv")


def load_pace_audit(dataset):
    """Rebuild the same clips and return clip_id -> collective-pace audit."""
    manifest = json.load(open(os.path.join(io.dataset_dir(dataset), io.MANIFEST_FILE)))
    built = assign_clip_ids(
        build_clips(manifest["subtypes"], manifest["stories_per_subtype"],
                    manifest["base_seed"], collective_pace=True),
        manifest["base_seed"])
    return {item["clip_id"]: item["clip"].collective_pace for item in built}


def per_clip_rows(dataset):
    truth, samples, events = io.load_answers(io.dataset_dir(dataset))
    audit = load_pace_audit(dataset)
    observations = pd.read_csv(os.path.join(io.dataset_dir(dataset), io.OBSERVATIONS_FILE),
                               dtype={"clip": str})
    rows = []
    for sample in samples.sort_values("clip").itertuples(index=False):
        gt = truth[truth["clip"] == sample.clip].sort_values("frame")["label"].tolist()
        obs = observations[observations["clip"] == sample.clip]
        missing = ~np.isfinite(obs["ball_x"].to_numpy(float))
        edges = np.flatnonzero(np.diff(np.r_[False, missing, False].astype(int)))
        runs = [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2]) if b - a > 125]
        for arm in ARMS:
            part = pd.read_csv(predictions_path(dataset, arm))
            part = part[part["clip"] == sample.clip].sort_values("frame")
            if part["frame"].tolist() != list(range(len(gt))):
                raise SystemExit("{} {}: bad frames".format(arm, sample.clip))
            row, _ = score_clip(sample, gt, part["label"].tolist())
            row["arm"] = arm
            pace = audit.get(sample.clip) or {}
            row["pace_live_target"] = pace.get("live_target")
            row["pace_dead_target"] = pace.get("dead_target")
            row["pace_dead_fast"] = bool(pace.get("dead_fast"))
            row["pace_live_slow"] = bool(pace.get("live_slow"))
            row["n_live_long_gaps"] = sum(
                1 for a, b in runs if ((np.array(gt[a:b]) == "H") | (np.array(gt[a:b]) == "A")).any())
            gt_codes = np.array(gt)
            pred_codes = np.array(part["label"].tolist())
            d = gt_codes == "D"
            row["d_frames"] = int(d.sum())
            row["d_pred_live"] = int((d & ((pred_codes == "H") | (pred_codes == "A"))).sum())
            row["live_pred_d"] = int(((~d) & (pred_codes == "D")).sum())
            rows.append(row)
    return pd.DataFrame(rows)


def summarize(per_clip):
    grouped = per_clip.groupby(["subtype", "arm"], sort=True)
    rows = []
    for (subtype, arm), part in grouped:
        rows.append({
            "subtype": subtype, "arm": arm, "clips": len(part),
            "core_pass": int(part["core_all_correct"].sum()),
            "core_wrong": int(part["core_wrong_frames"].sum()),
            "clip_wrong": int(part["clip_wrong_frames"].sum()),
            "macro_f1": float(part["macro_f1"].mean()),
            "spell_f1": float(part["spell_f1_mean"].mean()),
            "n_live_long_gaps": int(part["n_live_long_gaps"].sum()),
            "d_pred_live": int(part["d_pred_live"].sum()),
            "live_pred_d": int(part["live_pred_d"].sum()),
        })
    return pd.DataFrame(rows)


def counterexample_rows(per_clip):
    part = per_clip[per_clip["pace_dead_fast"] | per_clip["pace_live_slow"]].copy()
    if part.empty:
        return part
    part["counterexample"] = np.where(part["pace_dead_fast"], "dead_fast",
                                      np.where(part["pace_live_slow"], "live_slow", "both"))
    return part.sort_values(["counterexample", "clip", "arm"])


def write_report(per_clip, summary, counterexamples):
    lines = ["# Simulation regression: player-pace arms", "",
             "The simulator's collective pace is generated from the same assumption as the "
             "rule; these numbers only check that the implementation runs and that other "
             "subtypes are not broken.", ""]
    lines += ["## All subtypes", "",
              "| subtype | arm | clips | core pass | core wrong | clip wrong | macro | spell |",
              "|---|---|---|---|---|---|---|---|"]
    for row in summary.itertuples(index=False):
        lines.append("| {subtype} | {arm} | {clips} | {core_pass}/{clips} | {core_wrong} "
                     "| {clip_wrong} | {macro_f1:.3f} | {spell_f1:.3f} |".format(**row._asdict()))
    st05 = per_clip[per_clip["subtype"] == "ST05"]
    lines += ["", "## ST05", "",
              "| arm | core wrong | clip wrong | D predicted live | live predicted D |",
              "|---|---|---|---|---|"]
    for arm in ARMS:
        part = st05[st05["arm"] == arm]
        if part.empty:
            continue
        lines.append("| {} | {} | {} | {} | {} |".format(
            arm, int(part["core_wrong_frames"].sum()), int(part["clip_wrong_frames"].sum()),
            int(part["d_pred_live"].sum()), int(part["live_pred_d"].sum())))
    lines += ["", "## Counterexample clips", "",
              "| clip | subtype | arm | pace flag | core wrong | clip wrong | macro |",
              "|---|---|---|---|---|---|---|"]
    for row in counterexamples.itertuples(index=False):
        lines.append("| {clip} | {subtype} | {arm} | {counterexample} | {core_wrong_frames} "
                     "| {clip_wrong_frames} | {macro_f1:.3f} |".format(**row._asdict()))
    lines += ["", "`dead_fast` and `live_slow` are sampled by the simulator, not by the "
              "algorithm; a clip can have both flags. The core window is the scenario's tested "
              "segment, not the whole clip.", ""]
    path = os.path.join(OUT, "simulation_report_{}.md".format(DATASET))
    with open(path, "w") as handle:
        handle.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()
    global DATASET
    DATASET = args.dataset
    per_clip = per_clip_rows(DATASET)
    summary = summarize(per_clip)
    counterexamples = counterexample_rows(per_clip)
    out = os.path.join(OUT, "sim_" + DATASET)
    os.makedirs(out, exist_ok=True)
    per_clip.to_csv(os.path.join(out, "per_clip.csv"), index=False)
    summary.to_csv(os.path.join(out, "by_subtype.csv"), index=False)
    counterexamples.to_csv(os.path.join(out, "counterexamples.csv"), index=False)
    write_report(per_clip, summary, counterexamples)
    print(summary.to_string(index=False))
    print("wrote", os.path.join(out, "per_clip.csv"))


if __name__ == "__main__":
    main()
