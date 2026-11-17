#!/usr/bin/env python3
"""External weak-label benchmark for live-ball frames predicted as dead ball.

This is a follow-up to the BAR-ATH long-gap diagnostic.  It runs the current
``dead_ball_aware`` algorithm without Smart Tagging on the three Metrica games
and splits every live->D frame into the three diagnostic buckets requested for
the later A2/A3 repair work:

* A1: the ball coordinates are missing;
* A2: the ball is present after a long ball gap, but the algorithm stays in D;
* A3: the ball is present after a ball-out event, but the algorithm stays in D;
* other: live->D frames not explained by A1/A2/A3 (reported so the buckets add up).

Metrica truth is a weak label derived by the external converter, not official
truth.  The BAR-ATH answer files and evaluator are never opened.
"""

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

from algorithms.dead_ball_aware.predict import predict  # noqa: E402
from simulation.core import io  # noqa: E402
from simulation.run_algorithm import load_config  # noqa: E402

OUTPUTS_DIR = os.path.join(REPO_ROOT, "outputs")
OUTPUT_DIR = os.path.join(OUTPUTS_DIR, "20261117_bar_ath_gap_diagnostic")
TRUSTED_EXPERIMENT = "20261111_dead_ball_trusted_tags"
DATASET_PREFIX = "ext_metrica_game_"
GAMES = (1, 2, 3)
FPS = 25
WINDOW_S = 10.0
OUT_ONSET_GRACE_S = 2.0
MIN_GAP_S = 5.0
OUT_EVENT_PATTERN = r"(?:^| )BALL OUT|SHOT.*OUT"


def d_run_end(pred):
    """Exclusive end of the contiguous D run starting at each frame."""
    pred = np.asarray(pred)
    ends = np.empty(len(pred), dtype=int)
    end = len(pred)
    for frame in range(len(pred) - 1, -1, -1):
        if pred[frame] != "D":
            end = frame
        ends[frame] = end if pred[frame] == "D" else frame
    return ends


def classify_live_d(pred, live, known, gaps, out_frames,
                    window_s=WINDOW_S, out_onset_grace_s=OUT_ONSET_GRACE_S,
                    min_gap_s=MIN_GAP_S, fps=FPS):
    """Return masks for A1, A2, A3, and other live->D frames.

    ``gaps`` are half-open ``(start, stop)`` ball-missing runs.  A2 only uses
    gaps of at least ``min_gap_s`` because shorter gaps are not what the
    long-gap diagnostic is about.  A2 starts at the first visible frame after
    the gap; A3 starts at the first predicted-D frame within
    ``out_onset_grace_s`` after an out event.  Both post-event classes require
    continuous D and stop after ``window_s``.  If A2 and A3 overlap, the later
    onset wins; A1 has priority over both.
    """
    pred = np.asarray(pred)
    live = np.asarray(live, dtype=bool)
    known = np.asarray(known, dtype=bool)
    n = len(pred)
    if not (len(live) == len(known) == n):
        raise ValueError("pred, live and known must have the same length")

    dead = pred == "D"
    a1 = live & dead & ~known

    window = max(0, int(round(window_s * fps)))
    grace = max(0, int(round(out_onset_grace_s * fps)))
    min_gap = int(round(min_gap_s * fps))
    ends = d_run_end(pred)

    a2_onset = np.full(n, -1, dtype=int)
    for start, stop in gaps:
        start, stop = int(start), int(stop)
        if stop - start < min_gap or stop >= n or not dead[stop]:
            continue
        run_stop = min(n, stop + window, ends[stop])
        if run_stop > stop:
            a2_onset[stop:run_stop] = stop

    a3_onset = np.full(n, -1, dtype=int)
    for frame in np.asarray(out_frames, dtype=int):
        if frame < 0 or frame >= n:
            continue
        onset = -1
        for candidate in range(frame, min(n, frame + grace + 1)):
            if dead[candidate]:
                onset = candidate
                break
        if onset < 0:
            continue
        run_stop = min(n, onset + window, ends[onset])
        if run_stop > onset:
            a3_onset[onset:run_stop] = onset

    has_a2 = a2_onset >= 0
    has_a3 = a3_onset >= 0
    a2 = live & dead & ~a1 & has_a2 & (~has_a3 | (a2_onset >= a3_onset))
    a3 = live & dead & ~a1 & has_a3 & (~has_a2 | (a3_onset > a2_onset))
    other = live & dead & ~a1 & ~a2 & ~a3
    return a1, a2, a3, other


def _truth_for_clip(truth, clip, observations):
    rows = truth[truth["clip"] == clip].sort_values("frame")
    if len(rows) != len(observations):
        raise ValueError("{} truth rows for {} observations".format(len(rows), len(observations)))
    if not np.array_equal(rows["frame"].to_numpy(), observations["frame"].to_numpy()):
        raise ValueError("truth frames do not match observations for {}".format(clip))
    return rows["label"].to_numpy()


def benchmark_game(game, data_dir, params):
    dataset = "{}{}".format(DATASET_PREFIX, game)
    directory = os.path.join(data_dir, "simulation_sets", dataset)
    truth = pd.read_csv(os.path.join(directory, "truth.csv"), dtype={"clip": str})
    events = pd.read_csv(os.path.join(directory, "events.csv"), dtype={"clip": str},
                         keep_default_na=False)

    rows = []
    for clip, observations, metadata in io.load_clips(directory):
        labels = predict(observations, metadata, params, tags=None)
        labels = np.asarray(labels)
        live = np.isin(_truth_for_clip(truth, clip, observations), ("H", "A"))
        known = np.isfinite(observations[["ball_x", "ball_y"]].to_numpy(dtype=float)).all(axis=1)
        gaps = []
        edges = np.flatnonzero(np.diff(np.r_[False, ~known, False]))
        for start, stop in zip(edges[::2], edges[1::2]):
            gaps.append((int(start), int(stop)))
        clip_events = events[events["clip"] == clip]
        out_events = clip_events[clip_events["event"].str.contains(
            OUT_EVENT_PATTERN, case=False, regex=True, na=False)]["frame"].to_numpy()
        a1, a2, a3, other = classify_live_d(labels, live, known, gaps, out_events)
        rows.append({
            "dataset": dataset,
            "game": game,
            "clip": clip,
            "frames": int(len(labels)),
            "live_d_frames": int((live & (labels == "D")).sum()),
            "a1_missing": int(a1.sum()),
            "a2_after_gap": int(a2.sum()),
            "a3_after_out": int(a3.sum()),
            "other_live_d": int(other.sum()),
        })
    return rows


def _total_row(rows, game):
    keys = ("frames", "live_d_frames", "a1_missing", "a2_after_gap",
            "a3_after_out", "other_live_d")
    return {"dataset": "{}{}".format(DATASET_PREFIX, game), "game": game,
            "clip": "all", **{key: int(sum(row[key] for row in rows)) for key in keys}}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=OUTPUTS_DIR,
                        help="directory containing simulation_sets/")
    parser.add_argument("--out-dir", default=OUTPUT_DIR)
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    config = load_config(TRUSTED_EXPERIMENT)
    params = config.get("params") or {}
    if params.get("trusted_tags"):
        # Keep the no-tag branch explicit even though the trusted experiment is
        # the current production config: this benchmark must not use tags.
        params = dict(params)
        params["trusted_tags"] = False

    all_rows = []
    for game in GAMES:
        rows = benchmark_game(game, args.data_dir, params)
        all_rows.extend(rows)
        all_rows.append(_total_row(rows, game))
    total = _total_row([row for row in all_rows if row["clip"] == "all"], "all")
    total["dataset"] = "all"
    all_rows.append(total)

    result = pd.DataFrame(all_rows)
    target = os.path.join(args.out_dir, "metrica_live_d.csv")
    result.to_csv(target, index=False)

    summary = {
        "protocol": {
            "source": "Metrica external weak labels",
            "datasets": ["{}{}".format(DATASET_PREFIX, game) for game in GAMES],
            "algorithm": "dead_ball_aware",
            "tags": None,
            "window_s": WINDOW_S,
            "out_onset_grace_s": OUT_ONSET_GRACE_S,
            "min_gap_s": MIN_GAP_S,
            "a1": "ball coordinates missing",
            "a2": "first visible frame after a >=5 s gap, continuous D",
            "a3": "first D within 2 s after BALL OUT or SHOT OUT, continuous D",
            "other": "live->D frames outside A1/A2/A3",
        },
        "rows": all_rows,
    }
    with open(os.path.join(args.out_dir, "metrica_live_d.json"), "w") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    print(result.to_string(index=False))
    print("wrote {}".format(os.path.relpath(target, REPO_ROOT)))


if __name__ == "__main__":
    main()
