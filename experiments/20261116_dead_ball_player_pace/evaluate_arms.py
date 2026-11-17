"""Score the four player-pace arms on the external weak-label sets.

Development sets are used only for the parameter grid in select_development.py.  This script evaluates
the already-run predictions; it does not choose or change any parameter.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
import yaml

from algorithms.dead_ball_aware.predict import infer
from simulation.core import io

sys.path.insert(0, os.path.join(io.REPO_ROOT, "evaluation"))
import possession_metrics as pm  # noqa: E402

EXPERIMENT = "20261116_dead_ball_player_pace"
ARMS = ("off", "gap", "restart", "both")
DATASETS = (
    ("ext_metrica_game_1", "dev"),
    ("ext_metrica_game_2", "dev"),
    ("ext_metrica_game_3", "test"),
    ("ext_skillcorner_1925299", "test"),
)
OUT = os.path.join(io.REPO_ROOT, "outputs", EXPERIMENT, "eval")


def variant_params(config, arm):
    variant = config["variants"][arm]
    return {**config["params"], **variant.get("params", {})}


def long_gap_mask(observations):
    missing = ~np.isfinite(observations["ball_x"].to_numpy(dtype=float))
    mask = np.zeros(len(observations), dtype=bool)
    start = None
    for index, value in enumerate(missing):
        if value and start is None:
            start = index
        if start is not None and (not value or index == len(missing) - 1):
            stop = index if not value else index + 1
            if stop - start > 125:          # more than five seconds at 25 fps
                mask[start:stop] = True
            start = None
    return mask


def score_clip(dataset, clip, labels, truth, observations, config, arm):
    gt = pm.label_codes(np.array(truth))
    pred = pm.label_codes(np.array(labels))
    official = pm.evaluate(gt, pred)
    gap = long_gap_mask(observations)
    gap_live = ((gt == pm.H) | (gt == pm.A)) & gap
    pred_labels, audit = infer(observations, metadata_for(observations), variant_params(config, arm))
    if pred_labels != labels:
        raise AssertionError("{}: stored predictions differ from infer()".format(clip))
    return {
        "group": "dev" if dataset in ("ext_metrica_game_1", "ext_metrica_game_2") else "test",
        "dataset": dataset, "clip": clip, "arm": arm,
        "n_frames": len(gt), "n_graded": int(official["n_graded"]),
        "d_f1": official["per_class"]["D"]["f1"],
        "h_f1": official["per_class"]["H"]["f1"],
        "a_f1": official["per_class"]["A"]["f1"],
        "macro_f1": official["macro_f1"],
        "spell_f1": official["spell_f1_mean"],
        "alive_dead_f1": official["alive_dead_f1"],
        "gap_live_frames": int(gap_live.sum()),
        "gap_live_as_d": int((gap_live & (pred == pm.D)).sum()),
        "dead_as_live": int(((gt == pm.D) & ((pred == pm.H) | (pred == pm.A))).sum()),
        "live_as_d": int((((gt == pm.H) | (gt == pm.A)) & (pred == pm.D)).sum()),
        "long_gaps": len(audit["long_gap_checks"]),
        "b1_vetoed_gaps": sum(1 for check in audit["long_gap_checks"] if check["vetoed"]),
        "restart_actions": len(audit["restarts"]),
        "b2_rejected_restarts": len(audit["restart_rejections"]),
    }


_METADATA = {}


def metadata_for(observations):
    """The stored clips all carry the 46-slot metadata in the surrounding loader."""
    return _METADATA[id(observations)]


def summarize(per_clip):
    numeric = per_clip.select_dtypes(include=[np.number]).columns.difference(
        ["n_frames", "n_graded"])
    grouped = per_clip.groupby(["group", "dataset", "arm"], sort=False)
    rows = []
    for (group, dataset, arm), part in grouped:
        row = {"group": group, "dataset": dataset, "arm": arm, "clips": len(part)}
        for column in numeric:
            row[column] = part[column].mean()
        for column in ("gap_live_frames", "gap_live_as_d", "dead_as_live", "live_as_d",
                       "long_gaps", "b1_vetoed_gaps", "restart_actions",
                       "b2_rejected_restarts"):
            row[column] = int(part[column].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def write_report(summary, per_clip):
    lines = ["# Player-pace arms on external weak labels", ""]
    lines += ["The values are weak-label diagnostics, not official accuracy. The test sets "
              "were read once after the development parameters were frozen.", ""]
    columns = ["arm", "d_f1", "h_f1", "a_f1", "macro_f1", "spell_f1", "alive_dead_f1",
               "gap_live_as_d", "gap_live_frames", "dead_as_live", "live_as_d",
               "b1_vetoed_gaps", "b2_rejected_restarts"]
    for group, title in (("dev", "Development (Metrica Game 1/2)"),
                         ("test", "Test (Metrica Game 3 + SkillCorner)")):
        part = summary[summary["group"] == group]
        lines += ["## " + title, ""]
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("|" + "---|" * len(columns))
        for row in part.itertuples(index=False):
            cells = []
            for column in columns:
                value = getattr(row, column)
                cells.append("{:.4f}".format(value) if isinstance(value, float) else str(value))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Per clip", "",
              "| group | dataset | clip | arm | D F1 | macro | spell | gap live D "
              "| dead as live | B1 vetoes | B2 rejects |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in per_clip.itertuples(index=False):
        lines.append("| {group} | {dataset} | {clip} | {arm} | {d_f1:.4f} | {macro_f1:.4f} "
                     "| {spell_f1:.4f} | {gap_live_as_d}/{gap_live_frames} | {dead_as_live} "
                     "| {b1_vetoed_gaps} | {b2_rejected_restarts} |".format(**row._asdict()))
    lines += ["", "## Reading", "",
              "- `gap_live_as_d` counts truth H/A frames inside >5 s ball gaps predicted D.",
              "- `dead_as_live` counts truth D frames predicted H or A; it includes the known "
              "cost of vetoing a fast dead-ball gap and of delaying a restart.",
              "- `live_as_d` is the total H/A-to-D error, not only inside long gaps.",
              "- SkillCorner has almost no live long gaps with player tracking; B1 therefore "
              "cannot change it there.", ""]
    path = os.path.join(OUT, "report.md")
    with open(path, "w") as handle:
        handle.write("\n".join(lines))


def main():
    config = yaml.safe_load(open(os.path.join(
        io.REPO_ROOT, "experiments", EXPERIMENT, "config.yaml")))
    rows = []
    for dataset, group in DATASETS:
        truth, _, _ = io.load_answers(io.dataset_dir(dataset))
        for clip, observations, metadata in io.load_clips(io.dataset_dir(dataset)):
            _METADATA[id(observations)] = metadata
            for arm in ARMS:
                path = os.path.join(io.REPO_ROOT, "outputs", EXPERIMENT, arm,
                                    "simulation", dataset, "predictions.csv")
                predictions = pd.read_csv(path)
                part = predictions[predictions["clip"] == clip].sort_values("frame")
                labels = part["label"].tolist()
                labels_truth = truth[truth["clip"] == clip].sort_values("frame")["label"].tolist()
                rows.append(score_clip(dataset, clip, labels, labels_truth, observations,
                                       config, arm))
    per_clip = pd.DataFrame(rows)
    summary = summarize(per_clip)
    os.makedirs(OUT, exist_ok=True)
    per_clip.to_csv(os.path.join(OUT, "per_clip.csv"), index=False)
    summary.to_csv(os.path.join(OUT, "metrics.csv"), index=False)
    write_report(summary, per_clip)
    print(summary.to_string(index=False))
    print("wrote", os.path.join(OUT, "report.md"))


if __name__ == "__main__":
    main()
