"""Collective player-speed analysis for dead-ball / live-ball separation.

Run from the repository root::

    .venv/bin/python experiments/20261116_collective_speed/analyze.py

Figures and tables go to ``outputs/20261116_collective_speed/`` (ignored by Git).
No algorithm, simulator, converter, or completed experiment is modified.
"""

import argparse
import json
import os
import warnings

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from features import (
    FPS, OUTPUT_DIR, ball_missing_runs, ball_speed, load_atd, load_atd_cache,
    load_external, period_offsets, read_metrica_events, save_atd_cache,
)

METRICA_GAMES = ["game_1", "game_2", "game_3"]
METRICA_NAMES = {"game_1": "Game 1", "game_2": "Game 2", "game_3": "Game 3"}
SKILLCORNER = "1925299"
RNG_SEED = 20261116
Q2_PRE, Q2_POST = 250, 500
Q3_PRE, Q3_POST = 250, 250

os.makedirs(OUTPUT_DIR, exist_ok=True)


# -- common statistics -------------------------------------------------------------------------

def clean(values):
    values = np.asarray(values, dtype=float)
    return values[np.isfinite(values)]


def describe(values):
    values = clean(values)
    if not len(values):
        return {"n": 0, "median": None, "q1": None, "q3": None}
    return {
        "n": int(len(values)),
        "median": float(np.median(values)),
        "q1": float(np.percentile(values, 25)),
        "q3": float(np.percentile(values, 75)),
    }


def clean_json(value):
    """Recursively replace NaN/inf with None so output JSON is standards-compliant."""
    if isinstance(value, dict):
        return {key: clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def auc_live_gt_dead(live, dead):
    """P(live value > dead value), ties counted as 0.5; rank-based, no scipy."""
    live = clean(live)
    dead = clean(dead)
    if not len(live) or not len(dead):
        return None
    combined = np.concatenate([live, dead])
    ranks = pd.Series(combined).rank(method="average").to_numpy()
    n_live, n_dead = len(live), len(dead)
    return float((ranks[:n_live].sum() - n_live * (n_live + 1) / 2.0)
                 / (n_live * n_dead))


def game_clips(game):
    return load_external("ext_metrica_" + game)


def skillcorner_clips():
    return load_external("ext_skillcorner_" + SKILLCORNER)


def labels_as_bool(labels):
    live = np.isin(labels, ["H", "A"])
    dead = labels == "D"
    return live, dead


# -- Q1: frame and segment separation ---------------------------------------------------------

def frame_q1(clips):
    rows = []
    for clip in clips:
        features = clip["features"]
        live, dead = labels_as_bool(clip["labels"])
        for feature in ("F1", "F2"):
            values = features[feature].to_numpy(dtype=float)
            row = {
                "dataset": clip["dataset"],
                "clip": clip["clip"],
                "feature": feature,
            }
            for name, mask in (("dead", dead), ("live", live)):
                stats = describe(values[mask])
                row["n_" + name] = stats["n"]
                row[name + "_median"] = stats["median"]
                row[name + "_q1"] = stats["q1"]
                row[name + "_q3"] = stats["q3"]
            row["auc_live_gt_dead"] = auc_live_gt_dead(values[live], values[dead])
            rows.append(row)
    return pd.DataFrame(rows)


def frame_q1_game(clips):
    """Pooled D vs H/A frame statistics for one dataset (both halves together)."""
    f1 = np.concatenate([clip["features"]["F1"].to_numpy(float) for clip in clips])
    f2 = np.concatenate([clip["features"]["F2"].to_numpy(float) for clip in clips])
    labels = np.concatenate([clip["labels"] for clip in clips])
    live, dead = labels_as_bool(labels)
    rows = []
    for feature, values in (("F1", f1), ("F2", f2)):
        row = {"dataset": clips[0]["dataset"], "feature": feature}
        for name, mask in (("dead", dead), ("live", live)):
            stats = describe(values[mask])
            row["n_" + name] = stats["n"]
            row[name + "_median"] = stats["median"]
            row[name + "_q1"] = stats["q1"]
            row[name + "_q3"] = stats["q3"]
        row["auc_live_gt_dead"] = auc_live_gt_dead(values[live], values[dead])
        rows.append(row)
    return pd.DataFrame(rows)


def segment_q1(clips):
    rows = []
    for clip in clips:
        labels = clip["labels"]
        features = clip["features"]
        n = len(clip["observations"])
        for index, (start, stop) in enumerate(ball_missing_runs(clip["observations"])):
            window_labels = labels[start:stop]
            values = pd.Series(window_labels).value_counts()
            dead_votes = int(values.get("D", 0))
            live_votes = int(values.get("H", 0) + values.get("A", 0))
            if dead_votes == live_votes:
                continue
            majority = "dead" if dead_votes > live_votes else "live"
            window = features.iloc[start:stop]
            rows.append({
                "dataset": clip["dataset"],
                "clip": clip["clip"],
                "segment_index": index,
                "length": stop - start,
                "dead_votes": dead_votes,
                "live_votes": live_votes,
                "majority": majority,
                "mean_F1": float(np.nanmean(window["F1"])) if window["F1"].notna().any() else None,
                "mean_F2": float(np.nanmean(window["F2"])) if window["F2"].notna().any() else None,
                "n_feature_frames": int(window["F1"].notna().sum()),
            })
    return pd.DataFrame(rows)


def segment_restart_info(game, clips):
    """First raw event at/after each >5 s ball gap.

    A live-majority gap whose first post-gap event is SET PIECE is suspicious: the
    actual stoppage may be a vendor event outside the stoppage list (for example
    BALL LOST OFFSIDE or HAND BALL), so the weak label missed it.  This flag is used
    only for a sensitivity check, never to relabel the dataset.
    """
    events = metrica_events(game, clips)
    by_clip = {}
    for event in events:
        by_clip.setdefault(event["clip"]["clip"], []).append(event)
    for values in by_clip.values():
        values.sort(key=lambda item: item["relative"])
    rows = []
    for clip in clips:
        clip_events = by_clip.get(clip["clip"], [])
        for index, (start, stop) in enumerate(ball_missing_runs(clip["observations"])):
            after = [event for event in clip_events if event["relative"] >= stop]
            first = after[0] if after else None
            label = ""
            if first is not None:
                label = "{} {}".format(first["type"], first["subtype"]).strip()
            rows.append({
                "dataset": clip["dataset"],
                "clip": clip["clip"],
                "segment_index": index,
                "first_post_gap_event": label,
                "first_post_gap_is_set_piece": bool(
                    first is not None and first["type"] == "SET PIECE"),
            })
    return pd.DataFrame(rows)


def segment_summary(segments):
    rows = []
    if segments.empty:
        return pd.DataFrame(rows)
    for dataset, group in segments.groupby("dataset"):
        for feature in ("mean_F1", "mean_F2"):
            dead = group.loc[group["majority"] == "dead", feature].to_numpy()
            live = group.loc[group["majority"] == "live", feature].to_numpy()
            row = {"dataset": dataset, "feature": feature}
            for name, values in (("dead", dead), ("live", live)):
                stats = describe(values)
                row["n_" + name] = stats["n"]
                row[name + "_median"] = stats["median"]
                row[name + "_q1"] = stats["q1"]
                row[name + "_q3"] = stats["q3"]
            row["auc_live_gt_dead"] = auc_live_gt_dead(live, dead)
            if "first_post_gap_is_set_piece" in group.columns:
                restart = group["first_post_gap_is_set_piece"].eq(True).to_numpy()
                live_mask = group["majority"].eq("live").to_numpy()
                live_keep = group.loc[live_mask & ~restart, feature].to_numpy()
                row["n_live_set_piece_restart"] = int((live_mask & restart).sum())
                row["n_live_excluding_set_piece_restart"] = int(len(live_keep))
                row["auc_live_gt_dead_excluding_set_piece_restart"] = (
                    auc_live_gt_dead(live_keep, dead))
            rows.append(row)
    return pd.DataFrame(rows)


def q1_plots(metrica, skillcorner, segments):
    datasets = [(METRICA_NAMES[game], metrica[game]) for game in METRICA_GAMES]
    datasets.append(("SkillCorner", skillcorner))
    fig, axes = plt.subplots(2, 4, figsize=(12, 6))
    for column, (name, clips) in enumerate(datasets):
        f1 = np.concatenate([clip["features"]["F1"].to_numpy(float) for clip in clips])
        f2 = np.concatenate([clip["features"]["F2"].to_numpy(float) for clip in clips])
        labels = np.concatenate([clip["labels"] for clip in clips])
        live, dead = labels_as_bool(labels)
        for row, (feature, values) in enumerate((("F1", f1), ("F2", f2))):
            axis = axes[row, column]
            groups = [clean(values[dead]), clean(values[live])]
            axis.boxplot(groups, tick_labels=["D", "H/A"], showfliers=False,
                         medianprops={"color": "black"})
            axis.set_title(name if row == 0 else "")
            axis.set_ylabel(feature)
            axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "q1_frame_dist.png"), dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    for axis, feature in zip(axes, ("mean_F1", "mean_F2")):
        for offset, game in enumerate(METRICA_GAMES):
            group = segments[segments["dataset"] == "ext_metrica_" + game]
            for shift, majority, color in ((-0.12, "dead", "#b2182b"),
                                           (0.12, "live", "#2166ac")):
                values = clean(group.loc[group["majority"] == majority, feature])
                axis.scatter(np.full(len(values), offset + shift + np.random.default_rng(0).uniform(
                    -0.03, 0.03, len(values))), values, s=12, alpha=0.6, color=color,
                    label=majority if offset == 0 else None)
        axis.set_xticks(range(len(METRICA_GAMES)))
        axis.set_xticklabels([METRICA_NAMES[game] for game in METRICA_GAMES])
        axis.set_ylabel(feature)
        axis.grid(alpha=0.25)
    axes[0].legend(title="majority")
    fig.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "q1_segments.png"), dpi=160)
    plt.close(fig)


def skillcorner_coverage(clips):
    rows = []
    for clip in clips:
        live, dead = labels_as_bool(clip["labels"])
        values = clip["features"]["F1"].to_numpy(dtype=float)
        eligible = np.isfinite(values)
        for name, mask in (("D", dead), ("H/A", live), ("all", np.ones_like(dead))):
            total = int(mask.sum())
            usable = int((mask & eligible).sum())
            rows.append({
                "clip": clip["clip"],
                "label": name,
                "total_frames": total,
                "frames_with_features": usable,
                "coverage": usable / total if total else None,
            })
    return pd.DataFrame(rows)


def threshold_from_games(clips):
    """Pick F1 threshold on Game 1/2 by maximum balanced accuracy, fixed grid."""
    f1, live, dead = [], [], []
    for clip in clips:
        values = clip["features"]["F1"].to_numpy(dtype=float)
        is_live, is_dead = labels_as_bool(clip["labels"])
        f1.append(values)
        live.append(is_live)
        dead.append(is_dead)
    f1 = np.concatenate(f1)
    live = np.concatenate(live)
    dead = np.concatenate(dead)
    keep = np.isfinite(f1)
    f1, live, dead = f1[keep], live[keep], dead[keep]
    best = (None, -1.0)
    for threshold in np.arange(0.0, 5.0001, 0.01):
        predicted_live = f1 >= threshold
        tpr = np.mean(predicted_live[live]) if live.any() else 0.0
        tnr = np.mean(~predicted_live[dead]) if dead.any() else 0.0
        score = 0.5 * (tpr + tnr)
        if score > best[1]:
            best = (float(threshold), float(score))
    threshold = best[0]
    predicted_live = f1 >= threshold
    accuracy = float(np.mean(predicted_live == live))
    return threshold, best[1], accuracy, len(f1)


def apply_threshold(clips, threshold):
    frame_rows = []
    for clip in clips:
        values = clip["features"]["F1"].to_numpy(dtype=float)
        live, dead = labels_as_bool(clip["labels"])
        predicted_live = values >= threshold
        paired = np.isfinite(values)
        rows = {
            "dataset": clip["dataset"],
            "clip": clip["clip"],
            "n": int(paired.sum()),
            "accuracy": float(np.mean(predicted_live[paired] == live[paired])),
        }
        tpr = np.mean(predicted_live[paired & live]) if (paired & live).any() else 0.0
        tnr = np.mean(~predicted_live[paired & dead]) if (paired & dead).any() else 0.0
        rows["balanced_accuracy"] = float(0.5 * (tpr + tnr))
        rows["dead_correct"] = int((~predicted_live & dead & paired).sum())
        rows["dead_wrong"] = int((predicted_live & dead & paired).sum())
        rows["live_correct"] = int((predicted_live & live & paired).sum())
        rows["live_wrong"] = int((~predicted_live & live & paired).sum())
        frame_rows.append(rows)
    return pd.DataFrame(frame_rows)


def apply_threshold_segments(segments, threshold):
    rows = []
    for dataset, group in segments.groupby("dataset"):
        usable = group[group["mean_F1"].notna()].copy()
        predicted_live = usable["mean_F1"].to_numpy() >= threshold
        actual_live = usable["majority"].to_numpy() == "live"
        rows.append({
            "dataset": dataset,
            "n_segments": int(len(usable)),
            "accuracy": float(np.mean(predicted_live == actual_live)),
            "predicted_live": int(predicted_live.sum()),
            "predicted_dead": int((~predicted_live).sum()),
        })
    return pd.DataFrame(rows)


# -- event windows ----------------------------------------------------------------------------

def metrica_events(game, clips=None):
    """All raw Metrica events with clip-relative frames and weak label at that frame."""
    clips = clips if clips is not None else game_clips(game)
    offsets, ordered = period_offsets(clips)
    events = read_metrica_events(game)
    rows = []
    for event in events:
        period = event["period"]
        if period not in offsets:
            continue
        clip = ordered[0] if period == 1 else ordered[1]
        relative = event["start"] - offsets[period]
        if not 0 <= relative < len(clip["observations"]):
            continue
        rows.append({
            "clip": clip,
            "relative": relative,
            "label": clip["labels"][relative],
            "type": event["type"],
            "subtype": event["subtype"],
        })
    return rows


def is_stoppage_start(event):
    if event["type"] in ("BALL OUT", "FAULT RECEIVED", "CARD"):
        return True
    if event["type"] == "SHOT" and "OUT" in event["subtype"]:
        return True
    if event["type"] == "CHALLENGE" and "FAULT" in event["subtype"]:
        return True
    return False


def window_matrix(events, value_getter, pre, post):
    matrix = np.full((len(events), pre + post + 1), np.nan, dtype=float)
    for row, event in enumerate(events):
        clip = event["clip"]
        values = value_getter(clip)
        centre = event["relative"]
        for index, offset in enumerate(range(-pre, post + 1)):
            frame = centre + offset
            if 0 <= frame < len(values):
                matrix[row, index] = values[frame]
    return matrix


def half_drop_time(values, pre=Q2_PRE, post=Q2_POST, min_drop=0.2):
    """First sustained 50 % drop after the event, in seconds; NaN if no clear drop."""
    if len(values) != pre + post + 1:
        raise ValueError("window length mismatch")
    baseline = np.nanmedian(values[:pre - 50])      # -10 s .. -2 s
    post_values = values[pre:]
    minimum = np.nanmin(post_values) if np.isfinite(post_values).any() else np.nan
    if not np.isfinite(baseline) or not np.isfinite(minimum):
        return np.nan
    drop = baseline - minimum
    if drop < min_drop:
        return np.nan
    target = baseline - 0.5 * drop
    below = values <= target
    for index in range(pre, len(values) - 12):
        if below[index] and below[index:index + 12].sum() >= 10:
            return (index - pre) / FPS
    return np.nan


def half_rise_time(values, pre=Q3_PRE, post=Q3_POST, min_rise=0.2):
    """First sustained 50 % rise after the event, in seconds; NaN if no clear rise."""
    if len(values) != pre + post + 1:
        raise ValueError("window length mismatch")
    baseline = np.nanmedian(values[:pre - 50])      # -10 s .. -2 s
    post_values = values[pre:]
    peak = np.nanmax(post_values) if np.isfinite(post_values).any() else np.nan
    if not np.isfinite(baseline) or not np.isfinite(peak):
        return np.nan
    rise = peak - baseline
    if rise < min_rise:
        return np.nan
    target = baseline + 0.5 * rise
    above = values >= target
    for index in range(pre, len(values) - 12):
        if above[index] and above[index:index + 12].sum() >= 10:
            return (index - pre) / FPS
    return np.nan


def curve_drop_time(x, y, baseline_window=(-10.0, -2.0), post_start=0.0,
                    min_drop=0.3, sustain_s=1.0):
    """First time the median curve is at least ``min_drop`` below baseline for 1 s."""
    base_mask = (x >= baseline_window[0]) & (x <= baseline_window[1])
    baseline = np.nanmedian(y[base_mask])
    if not np.isfinite(baseline):
        return None
    target = baseline - min_drop
    for index in range(len(x)):
        if x[index] < post_start:
            continue
        window = (x >= x[index]) & (x < x[index] + sustain_s)
        if window.any() and np.all(y[window] <= target):
            return float(x[index])
    return None


def onset_time(values, pre=Q3_PRE, post=Q3_POST, min_rise=0.2, sustain=12):
    """First sustained absolute rise above the pre-event baseline, in seconds."""
    if len(values) != pre + post + 1:
        raise ValueError("window length mismatch")
    baseline = np.nanmedian(values[:pre - 50])
    if not np.isfinite(baseline):
        return np.nan
    target = baseline + min_rise
    above = values >= target
    for index in range(pre, len(values) - sustain):
        if above[index] and above[index:index + sustain].sum() >= sustain - 2:
            return (index - pre) / FPS
    return np.nan


def q2_analysis():
    all_rows = []
    curve_rows = []
    plot_data = {}
    for game in METRICA_GAMES:
        events = metrica_events(game)
        dead_starts = [event for event in events
                       if is_stoppage_start(event) and event["label"] == "D"]
        passes = [event for event in events
                  if event["type"] == "PASS" and event["label"] in ("H", "A")]
        rng = np.random.default_rng(RNG_SEED + int(game.rsplit("_", 1)[-1]))
        if len(passes) > len(dead_starts):
            indices = rng.choice(len(passes), size=len(dead_starts), replace=False)
            control = [passes[index] for index in sorted(indices)]
        else:
            control = passes
        for name, group in (("dead_start", dead_starts), ("control_pass", control)):
            matrix = window_matrix(group, lambda clip: clip["features"]["F1"].to_numpy(float),
                                   Q2_PRE, Q2_POST)
            f3_matrix = window_matrix(group, lambda clip: clip["features"]["F3"].to_numpy(float),
                                      Q2_PRE, Q2_POST)
            medians = np.nanmedian(matrix, axis=0) if len(group) else np.full(
                Q2_PRE + Q2_POST + 1, np.nan)
            f3_medians = np.nanmedian(f3_matrix, axis=0) if len(group) else np.full(
                Q2_PRE + Q2_POST + 1, np.nan)
            f3_post = f3_medians[Q2_PRE:]
            f3_min_index = int(np.nanargmin(f3_post)) if np.isfinite(f3_post).any() else None
            valid = np.isfinite(matrix).sum(axis=0) if len(group) else np.zeros(
                Q2_PRE + Q2_POST + 1, dtype=int)
            times = np.array([half_drop_time(row) for row in matrix]) if len(group) else np.array([])
            times = times[np.isfinite(times)]
            baseline = np.nanmedian(matrix[:, :Q2_PRE - 50], axis=1) if len(group) else np.array([])
            minimum = np.nanmin(matrix[:, Q2_PRE:], axis=1) if len(group) else np.array([])
            x_curve = np.arange(-Q2_PRE, Q2_POST + 1) / FPS
            all_rows.append({
                "game": METRICA_NAMES[game],
                "kind": name,
                "n_events": len(group),
                "n_with_event_drop": int(len(times)),
                "median_event_half_drop_s": float(np.median(times)) if len(times) else None,
                "q1_event_half_drop_s": float(np.percentile(times, 25)) if len(times) else None,
                "q3_event_half_drop_s": float(np.percentile(times, 75)) if len(times) else None,
                "curve_drop_s": curve_drop_time(x_curve, medians),
                "median_baseline": float(np.nanmedian(baseline)) if len(baseline) else None,
                "median_min": float(np.nanmedian(minimum)) if len(minimum) else None,
            })
            for offset, label in ((25, "at_1s"), (50, "at_2s"), (75, "at_3s")):
                index = Q2_PRE + offset
                all_rows[-1]["median_" + label] = float(medians[index]) if np.isfinite(
                    medians[index]) else None
            all_rows[-1]["median_F3_min_s"] = (f3_min_index / FPS
                                               if f3_min_index is not None else None)
            all_rows[-1]["median_F3_min"] = (
                float(f3_post[f3_min_index]) if f3_min_index is not None else None)
            all_rows[-1]["_f3_curves"] = f3_medians
            if name == "dead_start":
                plot_data[game] = (medians, valid)
            else:
                plot_data[game + "_control"] = (medians, valid)
        # Curve CSV for the first game only is not enough; save all games.
        for game_name in (game, game + "_control"):
            medians, valid = plot_data[game_name]
            for index, offset in enumerate(range(-Q2_PRE, Q2_POST + 1)):
                curve_rows.append({
                    "game": METRICA_NAMES[game],
                    "kind": "dead_start" if game_name == game else "control_pass",
                    "relative_s": offset / FPS,
                    "median_F1": float(medians[index]) if np.isfinite(medians[index]) else None,
                    "n_events": int(valid[index]),
                })
    pd.DataFrame(curve_rows).to_csv(os.path.join(OUTPUT_DIR, "q2_curves.csv"), index=False)

    fig, axes = plt.subplots(len(METRICA_GAMES), 1, figsize=(8, 9), sharex=True)
    for axis, game in zip(axes, METRICA_GAMES):
        dead_median, _ = plot_data[game]
        control_median, _ = plot_data[game + "_control"]
        x = np.arange(-Q2_PRE, Q2_POST + 1) / FPS
        axis.plot(x, dead_median, label="D-start events", color="#b2182b")
        axis.plot(x, control_median, label="random live PASS", color="#2166ac")
        axis.axvline(0, color="black", linewidth=0.8, linestyle="--")
        axis.set_title(METRICA_NAMES[game])
        axis.set_ylabel("F1 median (m/s)")
        axis.grid(alpha=0.25)
    axes[0].legend(loc="upper right")
    axes[-1].set_xlabel("relative to event (s)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "q2_curves.png"), dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(len(METRICA_GAMES), 1, figsize=(8, 9), sharex=True)
    for axis, game in zip(axes, METRICA_GAMES):
        # Reconstruct the F3 curve from the saved row to avoid another pass.
        dead_row = next(row for row in all_rows if row["game"] == METRICA_NAMES[game]
                        and row["kind"] == "dead_start")
        control_row = next(row for row in all_rows if row["game"] == METRICA_NAMES[game]
                           and row["kind"] == "control_pass")
        x = np.arange(-Q2_PRE, Q2_POST + 1) / FPS
        axis.plot(x, dead_row["_f3_curves"], color="#b2182b", label="D-start")
        axis.plot(x, control_row["_f3_curves"], color="#2166ac", label="random live PASS")
        axis.axvline(0, color="black", linewidth=0.8, linestyle="--")
        axis.axhline(0, color="black", linewidth=0.5)
        axis.set_title(METRICA_NAMES[game])
        axis.set_ylabel("F3 median (m/s per 1 s)")
        axis.grid(alpha=0.25)
    axes[0].legend(loc="upper right")
    axes[-1].set_xlabel("relative to event (s)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "q2_f3_curves.png"), dpi=160)
    plt.close(fig)
    for row in all_rows:
        row.pop("_f3_curves", None)
    response = pd.DataFrame(all_rows)
    response.to_csv(os.path.join(OUTPUT_DIR, "q2_response.csv"), index=False)
    return response


def q3_analysis():
    rows = []
    curve_rows = []
    plot_data = {}
    for game in METRICA_GAMES:
        clips = game_clips(game)
        clips_by_name = {clip["clip"]: clip for clip in clips}
        events = [event for event in metrica_events(game, clips)
                  if event["type"] == "SET PIECE" and event["label"] in ("H", "A")]
        # Attach the ball-speed series to each clip for the getter.
        for clip in clips:
            clip["ball_speed"] = ball_speed(
                clip["observations"], clip["pitch_length"], clip["pitch_width"])
        f1_matrix = window_matrix(events, lambda clip: clip["features"]["F1"].to_numpy(float),
                                  Q3_PRE, Q3_POST)
        f3_matrix = window_matrix(events, lambda clip: clip["features"]["F3"].to_numpy(float),
                                  Q3_PRE, Q3_POST)
        ball_matrix = window_matrix(events, lambda clip: clip["ball_speed"],
                                    Q3_PRE, Q3_POST)
        f1_times = np.array([half_rise_time(row, min_rise=0.2) for row in f1_matrix])
        ball_times = np.array([half_rise_time(row, min_rise=0.5) for row in ball_matrix])
        paired = np.isfinite(f1_times) & np.isfinite(ball_times)
        differences = f1_times[paired] - ball_times[paired]
        f1_onset = np.array([onset_time(row, min_rise=0.2) for row in f1_matrix])
        ball_onset = np.array([onset_time(row, min_rise=0.5) for row in ball_matrix])
        onset_paired = np.isfinite(f1_onset) & np.isfinite(ball_onset)
        onset_diff = f1_onset[onset_paired] - ball_onset[onset_paired]
        f3_median = np.nanmedian(f3_matrix, axis=0)
        f3_post = f3_median[Q3_PRE:]
        f3_peak_index = int(np.nanargmax(f3_post)) if np.isfinite(f3_post).any() else None
        rows.append({
            "game": METRICA_NAMES[game],
            "n_set_pieces": len(events),
            "median_F3_peak_s": (f3_peak_index / FPS if f3_peak_index is not None else None),
            "median_F3_peak": (float(f3_post[f3_peak_index])
                               if f3_peak_index is not None else None),
            "n_player_onset": int(np.isfinite(f1_onset).sum()),
            "median_player_onset_s": float(np.nanmedian(f1_onset)) if np.isfinite(f1_onset).any() else None,
            "n_ball_onset": int(np.isfinite(ball_onset).sum()),
            "median_ball_onset_s": float(np.nanmedian(ball_onset)) if np.isfinite(ball_onset).any() else None,
            "n_onset_pairs": int(onset_paired.sum()),
            "median_player_minus_ball_onset_s": float(np.median(onset_diff)) if len(onset_diff) else None,
            "q1_player_minus_ball_onset_s": float(np.percentile(onset_diff, 25)) if len(onset_diff) else None,
            "q3_player_minus_ball_onset_s": float(np.percentile(onset_diff, 75)) if len(onset_diff) else None,
            "n_player_rise": int(np.isfinite(f1_times).sum()),
            "median_player_half_rise_s": float(np.nanmedian(f1_times)) if np.isfinite(f1_times).any() else None,
            "n_ball_rise": int(np.isfinite(ball_times).sum()),
            "median_ball_half_rise_s": float(np.nanmedian(ball_times)) if np.isfinite(ball_times).any() else None,
            "n_rise_pairs": int(paired.sum()),
            "median_player_minus_ball_half_rise_s": float(np.median(differences)) if len(differences) else None,
            "q1_player_minus_ball_half_rise_s": float(np.percentile(differences, 25)) if len(differences) else None,
            "q3_player_minus_ball_half_rise_s": float(np.percentile(differences, 75)) if len(differences) else None,
        })
        f1_median = np.nanmedian(f1_matrix, axis=0)
        ball_median = np.nanmedian(ball_matrix, axis=0)
        plot_data[game] = (f1_median, ball_median)
        for index, offset in enumerate(range(-Q3_PRE, Q3_POST + 1)):
            curve_rows.append({
                "game": METRICA_NAMES[game],
                "relative_s": offset / FPS,
                "median_F1": float(f1_median[index]) if np.isfinite(f1_median[index]) else None,
                "median_F3": float(f3_median[index]) if np.isfinite(f3_median[index]) else None,
                "median_ball_speed": float(ball_median[index]) if np.isfinite(ball_median[index]) else None,
            })
    response = pd.DataFrame(rows)
    response.to_csv(os.path.join(OUTPUT_DIR, "q3_response.csv"), index=False)
    pd.DataFrame(curve_rows).to_csv(os.path.join(OUTPUT_DIR, "q3_curves.csv"), index=False)

    fig, axes = plt.subplots(len(METRICA_GAMES), 1, figsize=(8, 9), sharex=True)
    for axis, game in zip(axes, METRICA_GAMES):
        f1_median, ball_median = plot_data[game]
        x = np.arange(-Q3_PRE, Q3_POST + 1) / FPS
        axis.plot(x, f1_median, color="#b2182b", label="F1 median")
        axis.set_ylabel("F1 median (m/s)", color="#b2182b")
        axis.tick_params(axis="y", labelcolor="#b2182b")
        axis2 = axis.twinx()
        axis2.plot(x, ball_median, color="#2166ac", label="ball speed median")
        axis2.set_ylabel("ball speed (m/s)", color="#2166ac")
        axis2.tick_params(axis="y", labelcolor="#2166ac")
        axis.axvline(0, color="black", linewidth=0.8, linestyle="--")
        axis.set_title(METRICA_NAMES[game])
        axis.grid(alpha=0.25)
    axes[-1].set_xlabel("relative to SET PIECE (s)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "q3_curves.png"), dpi=160)
    plt.close(fig)
    return response


# -- Q4: tactical ATD without labels -----------------------------------------------------------

def two_means(values):
    """Deterministic 1-D two-means split; returns centres, counts and gap."""
    values = np.sort(clean(values))
    if len(values) < 2:
        return {"low_center": float(values[0]) if len(values) else None,
                "high_center": None, "low_count": int(len(values)), "high_count": 0,
                "gap": None, "overall_sd": 0.0, "within_sd": 0.0}
    best = None
    for split in range(1, len(values)):
        left, right = values[:split], values[split:]
        sse = ((left - left.mean()) ** 2).sum() + ((right - right.mean()) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, split, left.mean(), right.mean())
    _, split, low_center, high_center = best
    within = np.sqrt(best[0] / len(values))
    return {
        "low_center": float(low_center),
        "high_center": float(high_center),
        "low_count": int(split),
        "high_count": int(len(values) - split),
        "gap": float(values[split] - values[split - 1]),
        "overall_sd": float(values.std()),
        "within_sd": float(within),
        "split_value": float((values[split - 1] + values[split]) / 2.0),
    }


def q4_analysis(threshold):
    if os.path.exists(os.path.join(OUTPUT_DIR, "atd_features.npz")):
        cache = load_atd_cache()
    else:
        observations, features, _ = load_atd()
        save_atd_cache(observations, features)
        cache = load_atd_cache()
    features = pd.DataFrame({
        "F1": cache["F1"],
        "F2": cache["F2"],
        "F3": cache["F3"],
    })
    missing = cache["ball_missing"].astype(bool)
    runs = []
    edges = np.diff(np.r_[False, missing, False].astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    for start, stop in zip(starts, stops):
        if stop - start > 125:
            runs.append((int(start), int(stop)))
    rows = []
    for index, (start, stop) in enumerate(runs):
        window = features.iloc[start:stop]
        valid = window["F1"].notna()
        if not valid.any():
            continue
        rows.append({
            "segment_index": index,
            "length": stop - start,
            "n_feature_frames": int(valid.sum()),
            "mean_F1": float(np.nanmean(window["F1"])),
            "mean_F2": float(np.nanmean(window["F2"])),
            "median_F1": float(np.nanmedian(window["F1"])),
            "median_F2": float(np.nanmedian(window["F2"])),
        })
    segments = pd.DataFrame(rows)
    segments.to_csv(os.path.join(OUTPUT_DIR, "q4_segments.csv"), index=False)

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    for axis, column in zip(axes, ("mean_F1", "mean_F2")):
        values = clean(segments[column])
        axis.hist(values, bins=20, color="#4c72b0", edgecolor="white")
        axis.set_title(column)
        axis.set_ylabel("segments")
        axis.grid(alpha=0.25)
    axes[0].set_xlabel("segment mean F1 (m/s)")
    axes[1].set_xlabel("segment mean F2")
    fig.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "q4_hist.png"), dpi=160)
    plt.close(fig)

    f1_clusters = two_means(segments["mean_F1"])
    f2_clusters = two_means(segments["mean_F2"])
    predicted_live = int((segments["mean_F1"] >= threshold).sum())
    summary = {
        "n_long_segments": int(len(runs)),
        "n_segments_with_features": int(len(segments)),
        "n_segments_without_features": int(len(runs) - len(segments)),
        "mean_F1": describe(segments["mean_F1"]),
        "mean_F2": describe(segments["mean_F2"]),
        "clusters_F1": f1_clusters,
        "clusters_F2": f2_clusters,
        "holdout_threshold": threshold,
        "segments_predicted_live_by_threshold": predicted_live,
        "segments_predicted_dead_by_threshold": int(len(segments) - predicted_live),
    }
    with open(os.path.join(OUTPUT_DIR, "q4_summary.json"), "w") as handle:
        json.dump(clean_json(summary), handle, indent=2, allow_nan=False)
    return summary


# -- entry point -------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-atd", action="store_true",
                        help="run Q1-Q3 only; Q4 needs the tactical ATD cache/load")
    args = parser.parse_args()
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    metrica = {game: game_clips(game) for game in METRICA_GAMES}
    skillcorner = skillcorner_clips()

    frame_rows = []
    for game, clips in metrica.items():
        table = frame_q1(clips)
        table["source"] = "Metrica"
        frame_rows.append(table)
    skill_table = frame_q1(skillcorner)
    skill_table["source"] = "SkillCorner"
    frame_rows.append(skill_table)
    frame_stats = pd.concat(frame_rows, ignore_index=True)
    frame_stats.to_csv(os.path.join(OUTPUT_DIR, "q1_frame_stats.csv"), index=False)
    game_rows = []
    for game, clips in metrica.items():
        table = frame_q1_game(clips)
        table["source"] = "Metrica"
        game_rows.append(table)
    skill_game = frame_q1_game(skillcorner)
    skill_game["source"] = "SkillCorner"
    game_rows.append(skill_game)
    pd.concat(game_rows, ignore_index=True).to_csv(
        os.path.join(OUTPUT_DIR, "q1_frame_game_stats.csv"), index=False)

    segments = []
    restart_tables = []
    for game, clips in metrica.items():
        table = segment_q1(clips)
        restart = segment_restart_info(game, clips)
        restart_tables.append(restart)
        if not table.empty:
            table = table.merge(
                restart[["dataset", "clip", "segment_index",
                         "first_post_gap_event", "first_post_gap_is_set_piece"]],
                on=["dataset", "clip", "segment_index"], how="left", validate="one_to_one")
            table["source"] = "Metrica"
            segments.append(table)
    metric_segments = pd.concat(segments, ignore_index=True) if segments else pd.DataFrame()
    segment_restart = (
        pd.concat(restart_tables, ignore_index=True) if restart_tables else pd.DataFrame())
    metric_segments.to_csv(os.path.join(OUTPUT_DIR, "q1_segments.csv"), index=False)
    segment_restart.to_csv(os.path.join(OUTPUT_DIR, "q1_segment_restart.csv"), index=False)
    segment_stats = segment_summary(metric_segments)
    segment_stats.to_csv(os.path.join(OUTPUT_DIR, "q1_segment_stats.csv"), index=False)

    q1_plots(metrica, skillcorner, metric_segments)

    coverage = skillcorner_coverage(skillcorner)
    coverage.to_csv(os.path.join(OUTPUT_DIR, "q1_skillcorner_coverage.csv"), index=False)
    sc_segments = segment_q1(skillcorner)
    sc_segment_summary = {
        "n_long_segments": int(len(sc_segments)),
        "n_segments_with_features": int(sc_segments["mean_F1"].notna().sum())
        if not sc_segments.empty else 0,
    }

    selection = threshold_from_games(metrica["game_1"] + metrica["game_2"])
    threshold, balanced, accuracy, n_selection = selection
    game3_frames = apply_threshold(metrica["game_3"], threshold)
    game3_segments = apply_threshold_segments(
        metric_segments[metric_segments["dataset"] == "ext_metrica_game_3"], threshold)
    game3_total = game3_frames[["dead_correct", "dead_wrong", "live_correct", "live_wrong"]].sum()
    game3_n = int(game3_total.sum())
    game3_dead = int(game3_total["dead_correct"] + game3_total["dead_wrong"])
    game3_live = int(game3_total["live_correct"] + game3_total["live_wrong"])
    holdout = {
        "feature": "F1",
        "threshold": threshold,
        "selection_balanced_accuracy": balanced,
        "selection_accuracy": accuracy,
        "selection_frames": n_selection,
        "game_3_overall": {
            "n": game3_n,
            "accuracy": float((game3_total["dead_correct"] + game3_total["live_correct"]) / game3_n),
            "balanced_accuracy": float(0.5 * (
                game3_total["dead_correct"] / game3_dead
                + game3_total["live_correct"] / game3_live)),
            "dead_correct": int(game3_total["dead_correct"]),
            "dead_wrong": int(game3_total["dead_wrong"]),
            "live_correct": int(game3_total["live_correct"]),
            "live_wrong": int(game3_total["live_wrong"]),
        },
        "game_3_frames": game3_frames.to_dict(orient="records"),
        "game_3_segments": game3_segments.to_dict(orient="records"),
    }
    with open(os.path.join(OUTPUT_DIR, "q1_holdout.json"), "w") as handle:
        json.dump(clean_json(holdout), handle, indent=2, allow_nan=False)

    q2 = q2_analysis()
    q3 = q3_analysis()
    q4 = None if args.skip_atd else q4_analysis(threshold)

    summary = {
        "frame_stats_rows": len(frame_stats),
        "segment_stats_rows": len(segment_stats),
        "segment_restart_rows": len(segment_restart),
        "segment_restart_set_piece": (
            segment_restart.groupby("dataset")["first_post_gap_is_set_piece"]
            .sum().astype(int).to_dict() if not segment_restart.empty else {}),
        "skillcorner_coverage": coverage.to_dict(orient="records"),
        "skillcorner_segments": sc_segment_summary,
        "holdout": holdout,
        "q2": q2.to_dict(orient="records"),
        "q3": q3.to_dict(orient="records"),
        "q4": q4,
    }
    with open(os.path.join(OUTPUT_DIR, "summary.json"), "w") as handle:
        json.dump(clean_json(summary), handle, indent=2, allow_nan=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
