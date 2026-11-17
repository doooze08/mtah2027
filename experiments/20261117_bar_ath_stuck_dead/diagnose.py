#!/usr/bin/env python3
"""Read-only classification of BAR-ATH predicted-D segments with a fast visible ball.

No ground truth, evaluator, annotation, or algorithm changes.  Per-segment times
stay under outputs/20261117_bar_ath_stuck_dead/; NOTES has aggregates and tag
types only.  See NOTES.md for the pre-registered groups and decision rule.
"""

import argparse
import json
import math
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="Mean of empty slice",
                        category=RuntimeWarning)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
GAP_DIR = os.path.join(REPO_ROOT, "experiments", "20261116_gap_characterization")
PREV_DIR = os.path.join(REPO_ROOT, "experiments", "20261117_bar_ath_gap_diagnostic")
for path in (HERE, GAP_DIR, PREV_DIR, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import features  # noqa: E402
import diagnose as gap_diagnostic  # noqa: E402
from algorithms.dead_ball_aware.predict import infer, runs  # noqa: E402
from observations.atd import load_tactical  # noqa: E402
from simulation.run_algorithm import load_config, load_tags  # noqa: E402

OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "20261117_bar_ath_stuck_dead")
FPS = 25
TRUSTED_EXPERIMENT = "20261111_dead_ball_trusted_tags"
FAST_PLAYER_LINE_M_S = 1.575
BALL_STILL_SPEED_M_S = 0.5
MIN_FAST_FRAMES = FPS
MIN_STILL_FRAMES = FPS
SET_PIECE_CATEGORIES = gap_diagnostic.SET_PIECE_CATEGORIES

START_CAUSES = ("out", "long_gap", "tag_visible_stoppage", "other")
FAST_LOCATIONS = ("A2_after_long_gap", "A3_after_out", "tag_window", "other")
D_ENDS = ("restart", "pass", "half_end", "other")
GROUPS = ("real_dead", "stuck_live", "uncertain")


def _clip_tags(tags, offset, n):
    out = []
    for tag in tags:
        start = int(tag["start_frame"]) - offset
        stop = int(tag["end_frame"]) - offset
        if stop <= 0 or start >= n:
            continue
        shifted = dict(tag)
        shifted["start_frame"] = max(0, start)
        shifted["end_frame"] = min(n, stop)
        out.append(shifted)
    return out


def _ball_state(observations, pitch_length, pitch_width, radius):
    ball = observations[["ball_x", "ball_y"]].to_numpy(dtype=float)
    scale = np.array([pitch_length, pitch_width])
    ball_m = ball * scale
    known = np.isfinite(ball_m).all(axis=1)
    outside = known & ((ball_m < -radius) | (ball_m > scale + radius)).any(axis=1)
    speed = np.full(len(ball_m), np.nan, dtype=float)
    if len(ball_m) > 1:
        speed[1:] = np.hypot(np.diff(ball_m[:, 0]), np.diff(ball_m[:, 1])) * FPS
        speed[1:][~known[1:] | ~known[:-1]] = np.nan
    return ball, known, outside, speed


def _fast_ball(known, outside, speed, release_speed):
    return known & ~outside & np.isfinite(speed) & (speed >= release_speed)


def _start_cause(start, outside, long_gaps, visible_stoppages):
    if outside[start]:
        return "out"
    for gap_start, gap_stop in long_gaps:
        if gap_start <= start < gap_stop:
            return "long_gap"
    for stoppage in visible_stoppages:
        if int(stoppage["start"]) <= start < int(stoppage["stop"]):
            return "tag_visible_stoppage"
    return "other"


def _first_fast_location(start, first, outside, long_gaps, tags, offset):
    for gap_start, gap_stop in long_gaps:
        if gap_start <= first and gap_stop <= first:
            return "A2_after_long_gap"
    if outside[start:first + 1].any():
        return "A3_after_out"
    absolute = offset + first
    if any(tag["start_frame"] <= absolute < tag["end_frame"] for tag in tags):
        return "tag_window"
    return "other"


def _end_cause(stop, n, restarts, passes):
    if stop >= n:
        return "half_end"
    if any(int(record["frame"]) == stop for record in restarts):
        return "restart"
    if any(int(record["frame"]) == stop for record in passes):
        return "pass"
    return "other"


def _still_ball(stuck_start, stuck_stop, ball, known, speed,
                pitch_length, pitch_width):
    still = known & np.isfinite(speed) & (speed <= BALL_STILL_SPEED_M_S)
    best_s, best_category = 0.0, ""
    for run_start, run_stop in runs(still):
        overlap_start = max(int(run_start), stuck_start)
        overlap_stop = min(int(run_stop), stuck_stop)
        if overlap_stop - overlap_start < MIN_STILL_FRAMES:
            continue
        length_s = (overlap_stop - overlap_start) / FPS
        if length_s > best_s:
            best_s = length_s
            x, y = ball[overlap_start]
            best_category = features.position_category(
                x, y, pitch_length, pitch_width)
    return best_s, best_category


def _control_teams(ball, positions, teams, outside, config,
                   stuck_start, stuck_stop):
    offset = ball[:, None, :] - positions
    distance = np.linalg.norm(offset, axis=2)
    relative = np.full_like(distance, np.nan, dtype=float)
    if len(distance) > 1:
        relative[:-1] = np.linalg.norm(np.diff(offset, axis=0), axis=2) * FPS
    stable = (distance <= config["control_radius_m"]) & ~outside[:, None]
    stable[:-1] &= relative[:-1] <= config["relative_speed_m_s"]
    stable[-1] = False
    confirm = math.ceil(config["confirm_s"] * FPS)
    found = set()
    for slot in range(stable.shape[1]):
        for run_start, run_stop in runs(stable[:, slot]):
            if run_stop - run_start < confirm:
                continue
            if run_stop <= stuck_start or run_start >= stuck_stop:
                continue
            found.add(str(teams[slot]))
    if len(found) == 2:
        return "both"
    if len(found) == 1:
        return next(iter(found))
    return "none"


def _group(row):
    still_setpiece = bool(
        row["ball_still_s"] >= 1.0
        and row["still_category"] in SET_PIECE_CATEGORIES
        and row["d_end"] in ("restart", "pass"))
    slow_players = bool(
        np.isfinite(row["f1_stuck_med"])
        and row["f1_stuck_med"] <= FAST_PLAYER_LINE_M_S)
    reasons = []
    if still_setpiece:
        reasons.append("still_setpiece_then_released")
    if row["fast_frame_has_set_pieces"]:
        reasons.append("fast_frame_in_set_pieces")
    if slow_players:
        reasons.append("slow_players")
    row["real_dead_reasons"] = reasons
    if reasons:
        return "real_dead"
    live = bool(
        not row["fast_frame_has_set_pieces"]
        and not row["fast_frame_has_goals"]
        and np.isfinite(row["f1_stuck_med"])
        and row["f1_stuck_med"] > FAST_PLAYER_LINE_M_S
        and row["control_team"] != "none")
    return "stuck_live" if live else "uncertain"


def _decision(seconds):
    if seconds <= 60.0:
        return "not_worth"
    if seconds >= 120.0:
        return "worth_designing"
    return "review_footage_and_team_decision"


def _summary(rows, config, clips):
    def count(key, value):
        return sum(row[key] == value for row in rows)

    groups = {}
    for group in GROUPS:
        selected = [row for row in rows if row["group"] == group]
        groups[group] = {
            "segments": len(selected),
            "stuck_s": round(sum(row["stuck_s"] for row in selected), 3),
            "d_s": round(sum(row["d_length_s"] for row in selected), 3),
            "by_location": {
                loc: {
                    "segments": sum(row["fast_location"] == loc for row in selected),
                    "stuck_s": round(sum(row["stuck_s"] for row in selected
                                         if row["fast_location"] == loc), 3),
                }
                for loc in FAST_LOCATIONS
            },
        }
    live_seconds = groups["stuck_live"]["stuck_s"]
    return {
        "protocol": {
            "source": "BAR-ATH tactical ATD",
            "scored_halves": [{"clip": c["clip"], "half": c["half"]} for c in clips],
            "trusted_experiment": TRUSTED_EXPERIMENT,
            "release_speed_m_s": config["release_speed_m_s"],
            "fast_player_line_m_s": FAST_PLAYER_LINE_M_S,
            "ball_still_speed_m_s": BALL_STILL_SPEED_M_S,
        },
        "n_segments": len(rows),
        "total_stuck_s": round(sum(row["stuck_s"] for row in rows), 3),
        "total_d_s": round(sum(row["d_length_s"] for row in rows), 3),
        "start_causes": {c: count("start_cause", c) for c in START_CAUSES},
        "fast_locations": {c: count("fast_location", c) for c in FAST_LOCATIONS},
        "d_ends": {c: count("d_end", c) for c in D_ENDS},
        "control_teams": {c: count("control_team", c)
                          for c in ("H", "A", "both", "none")},
        "tag_coverage": {
            "set_pieces": sum(row["has_set_pieces"] for row in rows),
            "goals": sum(row["has_goals"] for row in rows),
            "other_phase": sum(row["has_other_phase"] for row in rows),
            "none": sum(row["tag_coverage"] == "none" for row in rows),
        },
        "groups": groups,
        "decision": {
            "rule": "stuck_live total <=60 s not worth; >=120 s worth; else review",
            "stuck_live_seconds": live_seconds,
            "result": _decision(live_seconds),
        },
    }


def analyze_clip(clip, tags, config):
    observations = clip["observations"]
    n = len(observations)
    pitch_length = clip["pitch_length"]
    pitch_width = clip["pitch_width"]
    f1 = features.build_context(clip)["f1"]
    ball, known, outside, speed = _ball_state(
        observations, pitch_length, pitch_width, config["ball_radius_m"])
    local_tags = _clip_tags(tags, clip["video_start_frame"], n)
    labels, diagnostics = infer(observations, {**clip, "fps": FPS},
                                config, tags=local_tags)
    labels = np.asarray(labels)
    fast = _fast_ball(known, outside, speed, config["release_speed_m_s"])
    pitch_scale = np.array([pitch_length, pitch_width])
    positions = observations[features.POSITION_COLUMNS].to_numpy(dtype=float).reshape(
        n, len(features.SLOT_IDS), 2) * pitch_scale
    ball_m = ball * pitch_scale
    slots = list(clip["slot_teams"])
    teams = np.array([clip["slot_teams"][slot] for slot in slots])
    offset = clip["video_start_frame"]
    rows = []

    for start, stop in runs(labels == "D"):
        start, stop = int(start), int(stop)
        fast_count = int(fast[start:stop].sum())
        if fast_count < MIN_FAST_FRAMES:
            continue
        first = start + int(np.flatnonzero(fast[start:stop])[0])
        abs_start, abs_stop, abs_first = offset + start, offset + stop, offset + first
        coverage = gap_diagnostic.tag_coverage(tags, abs_start, abs_stop)
        fast_coverage = gap_diagnostic.tag_coverage(tags, abs_first, abs_first + 1)
        before_type, after_type = gap_diagnostic.nearest_tags(
            tags, abs_start, abs_stop)
        still_s, still_category = _still_ball(
            first, stop, ball, known, speed, pitch_length, pitch_width)
        f1_stuck = f1[first:stop]
        f1_med = float(np.nanmedian(f1_stuck)) if np.isfinite(f1_stuck).any() else np.nan
        control_team = _control_teams(
            ball_m, positions, teams, outside, config, first, stop)
        row = {
            "clip": clip["clip"],
            "half": clip["half"],
            "start_s": abs_start / FPS,
            "stop_s": abs_stop / FPS,
            "first_fast_s": abs_first / FPS,
            "d_length_s": (stop - start) / FPS,
            "d_start_to_fast_s": (first - start) / FPS,
            "stuck_s": (stop - first) / FPS,
            "n_d_frames": stop - start,
            "n_fast_frames": fast_count,
            "start_cause": _start_cause(
                start, outside, diagnostics["long_gaps"],
                diagnostics["visible_stoppages"]),
            "fast_location": _first_fast_location(
                start, first, outside, diagnostics["long_gaps"], tags, offset),
            "d_end": _end_cause(stop, n, diagnostics["restarts"],
                                diagnostics["confirmed_passes"]),
            "ball_still_s": round(still_s, 3),
            "still_category": still_category,
            "f1_stuck_med": f1_med,
            "control_team": control_team,
            "has_set_pieces": coverage["has_set_pieces"],
            "has_goals": coverage["has_goals"],
            "has_other_phase": coverage["has_other_phase"],
            "tag_coverage": coverage["tag_coverage"],
            "fast_frame_has_set_pieces": fast_coverage["has_set_pieces"],
            "fast_frame_has_goals": fast_coverage["has_goals"],
            "before_tag_type": before_type,
            "after_tag_type": after_type,
        }
        row["group"] = _group(row)
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=os.path.join(REPO_ROOT, "data"))
    parser.add_argument("--out-dir", default=OUTPUT_DIR)
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    observations, metadata = load_tactical(args.data_dir)
    tags = load_tags("smart-tagging", args.data_dir)
    config = load_config(TRUSTED_EXPERIMENT)["params"]
    if not config.get("trusted_tags"):
        raise SystemExit("trusted-tags config no longer has trusted_tags: true")
    clips = gap_diagnostic.build_clips(observations, metadata)
    rows = []
    for clip in clips:
        rows.extend(analyze_clip(clip, tags, config))
    rows.sort(key=lambda row: (row["start_s"], row["clip"]))

    pd.DataFrame(rows).to_csv(os.path.join(args.out_dir, "segments.csv"), index=False)
    summary = _summary(rows, config, clips)
    with open(os.path.join(args.out_dir, "summary.json"), "w") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
