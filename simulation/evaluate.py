"""Score an experiment's predictions on a simulation dataset, clip by clip.

    .venv/bin/python -m simulation.evaluate --experiment <experiment_id> --dataset <dataset_id>

Each clip is scored on its own with the official evaluation/possession_metrics.py; clips are never
joined end to end (that would invent a transition at every seam). On top of the official numbers
it answers the V1 question for each clip: is the core window right frame by frame, and if not,
which switch came early, late, or should not exist?

Writes, next to predictions.csv in outputs/<experiment_id>/simulation/<dataset_id>/:
    per_clip.csv    one row per clip, all numbers
    report.md       the same in plain language
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

from simulation.core import io
from simulation.core.checks import collapse
from simulation.core.constants import FPS
from simulation.run_algorithm import prediction_dir

sys.path.insert(0, os.path.join(io.REPO_ROOT, "evaluation"))
import possession_metrics as pm  # noqa: E402  (official scorer, not a package)

SWITCH_TOLERANCE = pm.TAUS[-1]          # frames; a predicted switch further away is "extra"


def describe_switches(gt_codes, pred_codes):
    """Compare label switches. Returns (list of plain-language lines, counts dict).

    Temporal diagnostics use the official gap-aware runs: a ground-truth X run is not
    scored, and a predicted X run is filled inside a valid run so that abstaining does
    not invent two transitions.
    """
    runs = pm.valid_runs(gt_codes)
    gt_switches = pm.transitions(gt_codes, runs)
    pred_switches = pm.transitions(pm.fill_abstentions(pred_codes, runs), runs)
    pairs, missed, extra = pm.match_transitions(gt_switches, pred_switches, SWITCH_TOLERANCE)

    lines = []                                   # (frame, text), sorted by frame at the end
    for gt, pred in pairs:
        offset = pred[0] - gt[0]
        timing = "on time" if offset == 0 else "{} frames {}".format(
            abs(offset), "late" if offset > 0 else "early")
        lines.append((gt[0], "true switch {} at frame {}: predicted at {} ({})".format(
            _arrow(gt), gt[0], pred[0], timing)))
    for gt in missed:
        lines.append((gt[0], "true switch {} at frame {}: missing".format(_arrow(gt), gt[0])))
    for pred in extra:
        lines.append((pred[0], "extra switch {} at frame {}".format(_arrow(pred), pred[0])))
    counts = {"n_true_switches": len(gt_switches), "n_pred_switches": len(pred_switches),
              "n_missing_switches": len(missed), "n_extra_switches": len(extra),
              "max_switch_offset": max([abs(p[0] - g[0]) for g, p in pairs], default=0)}
    return lines, counts


def describe_events(clip_events):
    """Script events as (frame, text), so the report can show what happened where."""
    return [(int(e.frame), "script: {}{} at frame {}".format(
        e.event, " ({})".format(e.team) if e.team else "", int(e.frame)))
        for e in clip_events.itertuples(index=False)]


def score_clip(sample, gt_labels, pred_labels):
    gt_codes = pm.label_codes(np.array(gt_labels, dtype=object))
    pred_codes = pm.label_codes(np.array(pred_labels, dtype=object))
    official = pm.evaluate(gt_codes, pred_codes)

    core = slice(int(sample.core_start), int(sample.core_stop))
    # The official scorer never scores a frame whose truth is X. Keep the simulation
    # diagnostics on the same graded set instead of charging a prediction mismatch on
    # frames the ground truth deliberately leaves open.
    graded = gt_codes != pm.X
    core_wrong = int(np.sum(graded[core] & (gt_codes[core] != pred_codes[core])))
    switch_lines, switch_counts = describe_switches(gt_codes, pred_codes)
    row = {
        "clip": sample.clip, "subtype": sample.subtype, "story_id": sample.story_id,
        "initiating_team": sample.initiating_team, "n_frames": int(sample.n_frames),
        "core_frames": core.stop - core.start, "core_wrong_frames": core_wrong,
        "core_all_correct": core_wrong == 0,
        "clip_wrong_frames": int(np.sum(graded & (gt_codes != pred_codes))),
        "spell_f1_mean": official["spell_f1_mean"], "macro_f1": official["macro_f1"],
        "true_sequence": " ".join(collapse(gt_labels)),
        "pred_sequence": " ".join(collapse(pred_labels)),
    }
    row.update(switch_counts)
    return row, switch_lines


def write_report(path, experiment, dataset, rows, details):
    passed = sum(row["core_all_correct"] for row in rows)
    lines = [
        "# Simulation report",
        "",
        "- experiment: `{}`".format(experiment),
        "- dataset: `{}`".format(dataset),
        "- core window correct frame by frame: **{} of {} clips**".format(passed, len(rows)),
        "",
        "| clip | subtype | starts | core | core wrong | clip wrong | true | predicted "
        "| spellF1 | macroF1 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| {clip} | {subtype} | {initiating_team} | {verdict} | {core_wrong_frames}/"
                     "{core_frames} | {clip_wrong_frames}/{n_frames} | {true_sequence} | "
                     "{pred_sequence} | {spell_f1_mean:.3f} | {macro_f1:.3f} |".format(
                         verdict="pass" if row["core_all_correct"] else "FAIL", **row))
    lines += ["", "## Timeline, clip by clip (script events and switches)", ""]
    for row, switch_lines in zip(rows, details):
        lines.append("**{clip} ({subtype}, {initiating_team} starts)**".format(**row))
        lines += ["- " + line for line in switch_lines] or ["- no switches"]
        lines.append("")
    lines += [
        "## How to read this",
        "",
        "- `core` is the V1 pass mark: every frame of the tested event must be right.",
        "- Frames whose truth is X are not scored, matching the official metric. The wrong-"
        "frame counts and switch comparison above cover only graded (non-X) frames.",
        "- Switch timing is in frames at {} fps; a predicted switch more than {} frames from any "
        "true one of the same destination is listed as extra.".format(FPS, SWITCH_TOLERANCE),
        "- macroF1 averages F1 over H, A and D, and a class absent from a clip scores 0. A clip "
        "without A (e.g. TI01) therefore tops out at 0.667 even when every frame is right. Use it "
        "to compare algorithms on the same clip, not as a pass mark.",
        "- These are simulation results under the stated scenario assumptions; they say nothing "
        "about the real match score.",
        "",
    ]
    with open(path, "w") as handle:
        handle.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()

    out_dir = prediction_dir(args.experiment, args.dataset)
    predictions = pd.read_csv(os.path.join(out_dir, "predictions.csv"), dtype={"clip": str})
    truth, samples, _ = io.load_answers(io.dataset_dir(args.dataset))

    events = io.load_answers(io.dataset_dir(args.dataset))[2]
    rows, details = [], []
    for sample in samples.sort_values("clip").itertuples(index=False):
        gt = truth[truth["clip"] == sample.clip].sort_values("frame")["label"].tolist()
        pred = predictions[predictions["clip"] == sample.clip].sort_values("frame")
        if pred["frame"].tolist() != list(range(len(gt))):
            raise SystemExit("{}: predictions do not cover frames 0..{}".format(
                sample.clip, len(gt) - 1))
        row, switch_lines = score_clip(sample, gt, pred["label"].tolist())
        rows.append(row)
        timeline = describe_events(events[events["clip"] == sample.clip]) + switch_lines
        details.append([text for _, text in sorted(timeline, key=lambda item: item[0])])

    pd.DataFrame(rows).to_csv(os.path.join(out_dir, "per_clip.csv"), index=False,
                              float_format="%.4f")
    write_report(os.path.join(out_dir, "report.md"), args.experiment, args.dataset, rows,
                 details)
    for row in rows:
        print("{clip}  {subtype}  {initiating_team} starts  core {verdict}  "
              "({core_wrong_frames}/{core_frames} wrong)".format(
                  verdict="pass" if row["core_all_correct"] else "FAIL", **row))
    print("wrote {}".format(os.path.relpath(os.path.join(out_dir, "report.md"), io.REPO_ROOT)))


def _arrow(transition):
    return "{}->{}".format(pm.LABELS[transition[1]], pm.LABELS[transition[2]])


if __name__ == "__main__":
    main()
