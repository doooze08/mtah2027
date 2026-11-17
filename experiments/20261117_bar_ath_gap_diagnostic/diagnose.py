#!/usr/bin/env python3
"""Count BAR-ATH long ball gaps that look live according to two fixed descriptions.

Read-only diagnostic.  It does not read ground truth, run the evaluator, annotate
frames, or modify an algorithm.  Per-segment times are written only below
``outputs/20261117_bar_ath_gap_diagnostic/``; NOTES contains aggregate counts and
type names, never match frame numbers or times.

The two description lines are the ones frozen in
``experiments/20261116_gap_characterization/NOTES.md``:

* fast players: ``f1_speed_med > 1.575 m/s`` (Metrica artificial-live 25th
  percentile);
* open and far: reappearance category ``other`` and reappearance-to-disappearance
  distance > 10 m.

They are descriptive group lines, not rules or thresholds.
"""

import argparse
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
GAP_DIR = os.path.join(REPO_ROOT, "experiments", "20261116_gap_characterization")
for path in (HERE, GAP_DIR, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import features  # noqa: E402
from algorithms.dead_ball_aware.predict import predict  # noqa: E402
from games import GAME, half_video_blocks  # noqa: E402
from observations.atd import load_tactical  # noqa: E402
from simulation.run_algorithm import load_config, load_tags  # noqa: E402
from starter.load_smart_tagging import KICKOFF_VIDEO_FRAMES  # noqa: E402

OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "20261117_bar_ath_gap_diagnostic")
FPS = 25
FAST_LINE_M_S = 1.575
OPEN_FAR_M = 10.0
GAP_MIN_FRAMES = 5 * FPS
TRUSTED_EXPERIMENT = "20261111_dead_ball_trusted_tags"

# Official graded halves: first graded frame through last graded frame.  The
# tracking block for the second half starts earlier, but those frames are not scored.
# Boundaries come from the official loader constants; this file stores no match
# frame numbers of its own.
_HALF_BLOCKS = {half: (first, last)
                for half, first, last in half_video_blocks(GAME)}
SCORED_HALVES = (
    ("first_half", 1, _HALF_BLOCKS[1][0], _HALF_BLOCKS[1][1]),
    ("second_half", 2, KICKOFF_VIDEO_FRAMES["2nd Half"], _HALF_BLOCKS[2][1]),
)

SET_PIECE_CATEGORIES = ("corner", "goal_area", "center_circle")


def _clip_observations(observations, start, stop):
    """Return a reset-index slice, never a view that retains the full frame."""
    return observations.iloc[start:stop + 1].reset_index(drop=True).copy()


def build_clips(observations, metadata):
    clips = []
    for clip_name, half, start, stop in SCORED_HALVES:
        frame = _clip_observations(observations, start, stop)
        clips.append({
            "dataset": "BAR-ATH",
            "match": "BAR-ATH",
            "half": half,
            "clip": clip_name,
            "video_start_frame": start,
            "video_stop_frame": stop,
            "observations": frame,
            "pitch_length": float(metadata["pitch_length"]),
            "pitch_width": float(metadata["pitch_width"]),
            "slot_teams": {str(k): str(v) for k, v in metadata["slot_teams"].items()},
        })
    return clips


def f1_distribution(contexts):
    values = np.concatenate([context["f1"] for context in contexts])
    values = values[np.isfinite(values)]
    if not len(values):
        return {"n_frames": 0, "median": None, "q1": None, "q3": None}
    return {
        "n_frames": int(len(values)),
        "median": float(np.median(values)),
        "q1": float(np.percentile(values, 25)),
        "q3": float(np.percentile(values, 75)),
    }


def load_scale_clips(match):
    """Read Metrica observations and metadata only; no truth file is opened."""
    directory = features.dataset_dir(match)
    observations = pd.read_csv(os.path.join(directory, "observations.csv"),
                               dtype={"clip": str})
    with open(os.path.join(directory, "metadata.json")) as handle:
        metadata = json.load(handle)
    clips = []
    for clip_name in ("first_half", "second_half"):
        frames = (observations[observations["clip"] == clip_name]
                  .sort_values("frame").reset_index(drop=True))
        meta = metadata[clip_name]
        clips.append({
            "dataset": features.MATCHES[match],
            "match": match,
            "clip": clip_name,
            "observations": frames,
            "pitch_length": float(meta["pitch_length"]),
            "pitch_width": float(meta["pitch_width"]),
            "slot_teams": {str(k): str(v) for k, v in meta["slot_teams"].items()},
        })
    return clips


def metrica_scale_rows():
    rows = []
    for match in (1, 2, 3):
        clips = load_scale_clips(match)
        contexts = [features.build_context(clip) for clip in clips]
        dist = f1_distribution(contexts)
        rows.append({"source": "Metrica", "match": f"Game {match}", **dist})
    return rows


def tag_type(tag):
    return str(tag.get("type") or tag.get("code") or "")


def tag_coverage(tags, start, stop):
    """Classify a half-open [start, stop) interval against Smart Tagging."""
    overlaps = [tag for tag in tags
                if tag["start_frame"] < stop and tag["end_frame"] > start]
    has_set = any(tag.get("code") == "SET PIECES" for tag in overlaps)
    has_goals = any(tag.get("code") == "GOALS" for tag in overlaps)
    has_other = any(tag.get("code") not in ("SET PIECES", "GOALS")
                    for tag in overlaps)
    if has_set:
        coverage = "SET PIECES"
    elif has_goals:
        coverage = "GOALS"
    elif has_other:
        coverage = "other phase"
    else:
        coverage = "none"
    return {
        "has_set_pieces": bool(has_set),
        "has_goals": bool(has_goals),
        "has_other_phase": bool(has_other),
        "tag_coverage": coverage,
        "overlapping_tags": len(overlaps),
    }


def nearest_tags(tags, start, stop):
    before = [tag for tag in tags if tag["end_frame"] <= start]
    after = [tag for tag in tags if tag["start_frame"] >= stop]
    before.sort(key=lambda tag: (tag["end_frame"], tag["start_frame"]))
    after.sort(key=lambda tag: (tag["start_frame"], tag["end_frame"]))
    return (tag_type(before[-1]) if before else "",
            tag_type(after[0]) if after else "")


def _is_fast(value):
    return bool(np.isfinite(value) and value > FAST_LINE_M_S)


def _is_open_far(row):
    distance = row.get("reappear_to_disappear_m", np.nan)
    return bool(row.get("reappear_category") == "other"
                and np.isfinite(distance) and distance > OPEN_FAR_M)


def _seconds(rows):
    return float(sum(row["length_s"] for row in rows))


def _bucket(rows, fast, open_far):
    selected = [row for row in rows
                if row["fast"] is fast and row["open_far"] is open_far]
    return {"segments": len(selected), "seconds": round(_seconds(selected), 3)}


def table_a(rows):
    out = []
    for fast, open_far in ((True, True), (True, False), (False, True), (False, False)):
        out.append({"fast": fast, "open_far": open_far,
                    **_bucket(rows, fast, open_far)})
    return out


def table_b(rows):
    out = []
    for coverage in ("SET PIECES", "GOALS", "other phase", "none"):
        selected = [row for row in rows if row["tag_coverage"] == coverage]
        out.append({
            "coverage": coverage,
            "segments": len(selected),
            "seconds": round(_seconds(selected), 3),
            "fast_open_far": _bucket(selected, True, True),
            "fast_setpiece_or_near": _bucket(selected, True, False),
            "slow_open_far": _bucket(selected, False, True),
            "slow_setpiece_or_near": _bucket(selected, False, False),
        })
    return out


def length_summary(rows):
    lengths = np.array([row["length_s"] for row in rows], dtype=float)
    if not len(lengths):
        return {"n": 0, "min_s": None, "q1_s": None, "median_s": None,
                "q3_s": None, "max_s": None, "seconds": 0.0}
    return {
        "n": int(len(lengths)),
        "min_s": float(np.min(lengths)),
        "q1_s": float(np.percentile(lengths, 25)),
        "median_s": float(np.median(lengths)),
        "q3_s": float(np.percentile(lengths, 75)),
        "max_s": float(np.max(lengths)),
        "seconds": float(np.sum(lengths)),
    }


def decision_rule(n_candidates, total_seconds):
    if n_candidates <= 5 and total_seconds <= 120.0:
        return "not_worth"
    if n_candidates >= 10 or total_seconds >= 180.0:
        return "worth_designing"
    return "review_footage_and_team_decision"


def _safe(value):
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _row_detail(row, prefix):
    return {
        "gap_id": f"{prefix}{row['row_index']:03d}",
        "before_type": row["before_tag_type"],
        "after_type": row["after_tag_type"],
        "tag_coverage": row["tag_coverage"],
        "f1_speed_med": _safe(row["f1_speed_med"]),
        "reappear_category": row["reappear_category"],
        "reappear_to_disappear_m": _safe(row["reappear_to_disappear_m"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out-dir", default=OUTPUT_DIR)
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    observations, metadata = load_tactical(args.data_dir)
    clips = build_clips(observations, metadata)
    contexts = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for clip in clips:
            contexts.append(features.build_context(clip))

    config = load_config(TRUSTED_EXPERIMENT)
    params = config.get("params") or {}
    if not params.get("trusted_tags"):
        raise SystemExit("trusted-tags config no longer has trusted_tags: true")
    tags = load_tags("smart-tagging", args.data_dir)
    predictions = predict(observations, metadata, params, tags=tags)
    predictions = np.asarray(predictions, dtype=object)

    bar_dist = f1_distribution(contexts)
    metrica_rows = metrica_scale_rows()
    scale_rows = [{"source": "BAR-ATH", "match": "BAR-ATH", **bar_dist}] + metrica_rows
    scale_delta = {
        row["match"]: (bar_dist["median"] - row["median"]
                       if bar_dist["median"] is not None and row["median"] is not None
                       else None)
        for row in metrica_rows
    }
    scale_csv = pd.DataFrame(scale_rows)
    scale_csv.to_csv(os.path.join(args.out_dir, "f1_scale.csv"), index=False)

    gaps = []
    gap_number = 0
    for clip, context in zip(clips, contexts):
        local_observations = clip["observations"]
        for start, stop in features.ball_missing_runs(local_observations,
                                                      min_frames=GAP_MIN_FRAMES):
            abs_start = clip["video_start_frame"] + start
            abs_stop = clip["video_start_frame"] + stop
            row = features._sample_row(
                context, start, stop, "bar_ath_long_gap",
                match="BAR-ATH", split="diagnostic", clip_name=clip["clip"])
            coverage = tag_coverage(tags, abs_start, abs_stop)
            before_type, after_type = nearest_tags(tags, abs_start, abs_stop)
            pred = predictions[abs_start:abs_stop]
            d_frames = int((pred == "D").sum())
            row.update({
                "gap_id": f"gap_{gap_number:03d}",
                "half": clip["half"],
                "clip": clip["clip"],
                "start_s": abs_start / FPS,
                "stop_s": abs_stop / FPS,
                "length_s": (abs_stop - abs_start) / FPS,
                "n_frames": abs_stop - abs_start,
                "fast": _is_fast(row.get("f1_speed_med", np.nan)),
                "open_far": _is_open_far(row),
                "fast_setpiece": bool(
                    _is_fast(row.get("f1_speed_med", np.nan))
                    and row.get("reappear_category") in SET_PIECE_CATEGORIES),
                "before_tag_type": before_type,
                "after_tag_type": after_type,
                "pred_d_frames": d_frames,
                "pred_d_fraction": d_frames / len(pred) if len(pred) else np.nan,
                **coverage,
            })
            row["candidate"] = bool(row["fast"] and row["open_far"]
                                    and not row["has_set_pieces"]
                                    and not row["has_goals"])
            gaps.append(row)
            gap_number += 1

    # Row index is assigned after collection so NOTES can refer to anonymous gaps.
    for index, row in enumerate(gaps, start=1):
        row["row_index"] = index
    gaps_frame = pd.DataFrame(gaps)
    gaps_frame.to_csv(os.path.join(args.out_dir, "gaps.csv"), index=False)

    candidates = [row for row in gaps if row["candidate"]]
    fast_setpiece = [row for row in gaps if row["fast_setpiece"]]
    candidates_frame = pd.DataFrame(candidates)
    candidates_frame.to_csv(os.path.join(args.out_dir, "candidates.csv"), index=False)

    candidate_seconds = _seconds(candidates)
    candidate_frames = sum(row["n_frames"] for row in candidates)
    candidate_d_frames = sum(row["pred_d_frames"] for row in candidates)
    summary = {
        "protocol": {
            "source": "BAR-ATH tactical ATD",
            "scored_halves": [{"clip": c[0], "half": c[1],
                               "first_video_frame": c[2], "last_video_frame": c[3]}
                              for c in SCORED_HALVES],
            "min_gap_seconds": GAP_MIN_FRAMES / FPS,
            "fast_line_m_s": FAST_LINE_M_S,
            "open_far_m": OPEN_FAR_M,
            "trusted_experiment": TRUSTED_EXPERIMENT,
        },
        "scale_check": {
            "bar_ath": bar_dist,
            "metrica": metrica_rows,
            "delta_vs_metrica_m_s": scale_delta,
            "note": ("BAR-ATH median differs by more than 0.2 m/s from at least one "
                     "Metrica match; description lines were not recalibrated."
                     if any(value is not None and abs(value) > 0.2
                            for value in scale_delta.values()) else
                     "BAR-ATH median is within 0.2 m/s of every Metrica match."),
        },
        "n_gaps": len(gaps),
        "total_gap_seconds": round(_seconds(gaps), 3),
        "n_gaps_with_finite_f1": sum(bool(np.isfinite(row["f1_speed_med"]))
                                      for row in gaps),
        "tag_code_counts": {
            "set_pieces": sum(row["has_set_pieces"] for row in gaps),
            "goals": sum(row["has_goals"] for row in gaps),
            "other_phase": sum(row["has_other_phase"] for row in gaps),
            "none": sum(row["tag_coverage"] == "none" for row in gaps),
        },
        "table_a": table_a(gaps),
        "table_b": table_b(gaps),
        "candidates": {
            "definition": ("fast and open_far and no SET PIECES/GOALS overlap"),
            "n": len(candidates),
            "seconds": round(candidate_seconds, 3),
            "n_frames": candidate_frames,
            "pred_d_frames": candidate_d_frames,
            "pred_d_fraction": (candidate_d_frames / candidate_frames
                                if candidate_frames else None),
            "length_s": length_summary(candidates),
            "details": [_row_detail(row, "G") for row in candidates],
            "decision": decision_rule(len(candidates), candidate_seconds),
        },
        "fast_setpiece": {
            "definition": ("fast and reappearance category corner/goal_area/center_circle"),
            "n": len(fast_setpiece),
            "seconds": round(_seconds(fast_setpiece), 3),
            "details": [_row_detail(row, "S") for row in fast_setpiece],
        },
    }
    with open(os.path.join(args.out_dir, "summary.json"), "w") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False, default=_safe)

    print(json.dumps({
        "n_gaps": summary["n_gaps"],
        "total_gap_seconds": summary["total_gap_seconds"],
        "bar_ath_f1_median": bar_dist["median"],
        "scale_delta": scale_delta,
        "table_a": summary["table_a"],
        "candidates": {k: summary["candidates"][k]
                       for k in ("n", "seconds", "pred_d_frames",
                                 "pred_d_fraction", "decision")},
        "fast_setpiece_n": summary["fast_setpiece"]["n"],
    }, indent=2, ensure_ascii=False, default=_safe))


if __name__ == "__main__":
    main()
