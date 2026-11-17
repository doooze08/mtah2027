#!/usr/bin/env python3
"""Fixed acceptance checks for ending D at a moving long-gap reappearance.

Reads only observations, metadata, weak external labels, and the pre-existing PR #27
diagnostic table. It never reads BAR-ATH ground truth and never runs the evaluator.
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
GAP_DIR = os.path.join(REPO_ROOT, "experiments", "20261116_gap_characterization")
GAP_DIAG_DIR = os.path.join(REPO_ROOT, "experiments", "20261117_bar_ath_gap_diagnostic")
for path in (HERE, GAP_DIR, GAP_DIAG_DIR, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import diagnose as gap_diagnostic  # noqa: E402
from algorithms.dead_ball_aware.predict import infer, predict, runs  # noqa: E402
from observations.atd import load_tactical  # noqa: E402
from simulation.core import io as sim_io  # noqa: E402
from simulation.evaluate import score_clip  # noqa: E402
from simulation.run_algorithm import load_tags  # noqa: E402

FPS = 25
OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "20261117_a2_moving_reappearance")
PR27_SEGMENTS = os.path.join(REPO_ROOT, "outputs", "20261117_bar_ath_stuck_dead",
                             "segments.csv")
SIM_DATASET = "sim_pace_accept3"
METRICA_DATASETS = ("ext_metrica_game_1", "ext_metrica_game_2", "ext_metrica_game_3")
SET_PIECE_CATEGORIES = ("corner", "goal_area", "center_circle")


def _params(variant):
    with open(os.path.join(HERE, "config.yaml")) as handle:
        config = yaml.safe_load(handle)["params"]
    return {**config, "end_gap_on_moving_ball": variant == "on"}


def _write_json(name, payload):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, name), "w") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)


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


def _changed_runs(off, on):
    changed = (np.asarray(off, dtype=object) == "D") & (
        np.asarray(on, dtype=object) != "D")
    for start, stop in runs(changed):
        yield int(start), int(stop)


def _overlap(start_s, stop_s, other_start, other_stop):
    return max(0.0, min(stop_s, other_stop) - max(start_s, other_start))


def bar_ath(data_dir):
    observations, metadata = load_tactical(data_dir)
    tags = load_tags("smart-tagging", data_dir)
    clips = gap_diagnostic.build_clips(observations, metadata)
    seg = pd.read_csv(PR27_SEGMENTS) if os.path.exists(PR27_SEGMENTS) else pd.DataFrame()
    off_params, on_params = _params("off"), _params("on")
    changed = []
    per_clip = []
    for clip in clips:
        local_tags = _clip_tags(tags, clip["video_start_frame"],
                                len(clip["observations"]))
        off, off_audit = infer(clip["observations"], {**clip, "fps": FPS},
                               off_params, tags=local_tags)
        on, on_audit = infer(clip["observations"], {**clip, "fps": FPS},
                             on_params, tags=local_tags)
        offset = clip["video_start_frame"]
        frames = 0
        for start, stop in _changed_runs(off, on):
            start_s = (offset + start) / FPS
            stop_s = (offset + stop) / FPS
            team = sorted(set(on[start:stop]) - {"D"})
            changed.append({
                "clip": clip["clip"], "start_s": start_s, "stop_s": stop_s,
                "seconds": (stop - start) / FPS, "team": "+".join(team),
                "moving_reappearances": len(on_audit.get("moving_reappearances", []))})
            frames += stop - start
        per_clip.append({"clip": clip["clip"], "changed_frames": frames,
                         "changed_s": frames / FPS,
                         "moving_reappearances": len(on_audit.get("moving_reappearances", []))})
    changed_table = pd.DataFrame(changed)
    if len(changed_table):
        changed_table["in_pr27_45"] = changed_table.apply(
            lambda row: bool(
                len(seg) and (((seg["clip"] == row["clip"])
                              & (seg["start_s"] < row["stop_s"])
                              & (seg["stop_s"] > row["start_s"])).any())),
            axis=1)
        stationary = seg[(seg["ball_still_s"] >= 1.0)
                         & (seg["still_category"].isin(SET_PIECE_CATEGORIES))] \
            if len(seg) else seg
        changed_table["in_stationary"] = changed_table.apply(
            lambda row: bool(
                len(stationary) and (((stationary["clip"] == row["clip"])
                                      & (stationary["start_s"] < row["stop_s"])
                                      & (stationary["stop_s"] > row["start_s"])).any())),
            axis=1)
        changed_table["seconds_in_pr27_45"] = changed_table.apply(
            lambda row: sum(_overlap(row["start_s"], row["stop_s"], other["start_s"],
                                     other["stop_s"]) for _, other in
                            seg[seg["clip"] == row["clip"]].iterrows()), axis=1)
    else:
        changed_table = changed_table.assign(in_pr27_45=[], in_stationary=[],
                                             seconds_in_pr27_45=[])
    changed_table.to_csv(os.path.join(OUTPUT_DIR, "bar_ath_changed_segments.csv"), index=False)
    total_s = float(changed_table["seconds"].sum()) if len(changed_table) else 0.0
    in45_s = float(changed_table["seconds_in_pr27_45"].sum()) if len(changed_table) else 0.0
    changed_in_45 = int(changed_table["in_pr27_45"].sum()) if len(changed_table) else 0
    stationary_count = int(changed_table["in_stationary"].sum()) if len(changed_table) else 0
    payload = {
        "clip_rows": per_clip,
        "changed_segments": len(changed_table),
        "changed_seconds": round(total_s, 3),
        "changed_segments_in_pr27_45": changed_in_45,
        "changed_seconds_in_pr27_45": round(in45_s, 3),
        "fraction_changed_seconds_in_pr27_45": (round(in45_s / total_s, 4) if total_s else None),
        "changed_segments_in_stationary_set_piece": stationary_count,
        "pr27_segments": int(len(seg)),
        "stationary_set_piece_segments": int(len(seg[
            (seg["ball_still_s"] >= 1.0)
            & (seg["still_category"].isin(SET_PIECE_CATEGORIES))]))
        if len(seg) else 0,
    }
    _write_json("bar_ath_summary.json", payload)
    return payload


def metrica():
    off_params, on_params = _params("off"), _params("on")
    rows = []
    for dataset in METRICA_DATASETS:
        directory = sim_io.dataset_dir(dataset)
        observations = pd.read_csv(os.path.join(directory, "observations.csv"),
                                   dtype={"clip": str})
        with open(os.path.join(directory, "metadata.json")) as handle:
            metadata = json.load(handle)
        truth = pd.read_csv(os.path.join(directory, "truth.csv"), dtype={"clip": str})
        for clip, clip_obs in observations.groupby("clip", sort=True):
            frames = clip_obs.drop(columns="clip").reset_index(drop=True)
            gt = truth[truth["clip"] == clip].sort_values("frame")["label"].to_numpy()
            off = np.asarray(predict(frames, metadata[clip], off_params), dtype=object)
            on = np.asarray(predict(frames, metadata[clip], on_params), dtype=object)
            live = np.isin(gt, ["H", "A"])
            live_pred_d_off = int((live & (off == "D")).sum())
            live_pred_d_on = int((live & (on == "D")).sum())
            new_flips = 0
            for start, stop in runs(gt == "D"):
                if stop - start < 3 * FPS:
                    continue
                off_live = float((off[start:stop] != "D").mean())
                on_live = float((on[start:stop] != "D").mean())
                if on_live > 0.5 and off_live <= 0.5:
                    new_flips += 1
            rows.append({
                "game": dataset, "clip": clip, "weak_live_frames": int(live.sum()),
                "live_pred_d_off": live_pred_d_off, "live_pred_d_on": live_pred_d_on,
                "new_whole_dead_run_flips": new_flips,
            })
    frame = pd.DataFrame(rows)
    frame.to_csv(os.path.join(OUTPUT_DIR, "metrica_segments.csv"), index=False)
    summary = {
        "games": frame.groupby("game").agg(
            weak_live_frames=("weak_live_frames", "sum"),
            live_pred_d_off=("live_pred_d_off", "sum"),
            live_pred_d_on=("live_pred_d_on", "sum"),
            new_whole_dead_run_flips=("new_whole_dead_run_flips", "sum"),
        ).reset_index().to_dict(orient="records"),
    }
    _write_json("metrica_summary.json", summary)
    return summary


def simulation():
    directory = sim_io.dataset_dir(SIM_DATASET)
    truth, samples, _ = sim_io.load_answers(directory)
    off_params, on_params = _params("off"), _params("on")
    rows = []
    for clip, observations, metadata in sim_io.load_clips(directory):
        sample = samples[samples["clip"] == clip].iloc[0]
        gt = truth[truth["clip"] == clip].sort_values("frame")["label"].to_numpy()
        for variant, params in (("off", off_params), ("on", on_params)):
            labels = list(predict(observations, metadata, params))
            scored, _ = score_clip(sample, gt, labels)
            rows.append({"clip": clip, "subtype": scored["subtype"],
                         "variant": variant,
                         "core_wrong_frames": scored["core_wrong_frames"],
                         "clip_wrong_frames": scored["clip_wrong_frames"],
                         "core_all_correct": scored["core_all_correct"]})
    frame = pd.DataFrame(rows)
    frame.to_csv(os.path.join(OUTPUT_DIR, "simulation_per_clip.csv"), index=False)
    grouped = frame.groupby(["subtype", "variant"]).agg(
        clips=("clip", "nunique"),
        core_pass=("core_all_correct", "sum"),
        core_wrong=("core_wrong_frames", "sum"),
        clip_wrong=("clip_wrong_frames", "sum")).reset_index()
    wide = grouped.pivot(index="subtype", columns="variant")
    summary = []
    for subtype in sorted(grouped["subtype"].unique()):
        off = grouped[(grouped["subtype"] == subtype) & (grouped["variant"] == "off")].iloc[0]
        on = grouped[(grouped["subtype"] == subtype) & (grouped["variant"] == "on")].iloc[0]
        summary.append({
            "subtype": subtype,
            "clips": int(off["clips"]),
            "core_pass_off": int(off["core_pass"]), "core_pass_on": int(on["core_pass"]),
            "core_wrong_off": int(off["core_wrong"]), "core_wrong_on": int(on["core_wrong"]),
            "clip_wrong_off": int(off["clip_wrong"]), "clip_wrong_on": int(on["clip_wrong"]),
            "core_wrong_delta": int(on["core_wrong"] - off["core_wrong"]),
            "clip_wrong_delta": int(on["clip_wrong"] - off["clip_wrong"]),
        })
    table = pd.DataFrame(summary)
    table.to_csv(os.path.join(OUTPUT_DIR, "simulation_per_subtype.csv"), index=False)
    payload = {"dataset": SIM_DATASET, "subtypes": summary,
               "total": {
                   "core_pass_off": int(table["core_pass_off"].sum()),
                   "core_pass_on": int(table["core_pass_on"].sum()),
                   "core_wrong_off": int(table["core_wrong_off"].sum()),
                   "core_wrong_on": int(table["core_wrong_on"].sum()),
                   "clip_wrong_off": int(table["clip_wrong_off"].sum()),
                   "clip_wrong_on": int(table["clip_wrong_on"].sum()),
               }}
    _write_json("simulation_summary.json", payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=os.path.join(REPO_ROOT, "data"))
    parser.add_argument("--skip-bar-ath", action="store_true")
    args = parser.parse_args()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = {}
    if not args.skip_bar_ath:
        out["bar_ath"] = bar_ath(args.data_dir)
        print("BAR-ATH", json.dumps(out["bar_ath"], ensure_ascii=False))
    out["metrica"] = metrica()
    print("Metrica", json.dumps(out["metrica"], ensure_ascii=False))
    out["simulation"] = simulation()
    print("Simulation", json.dumps(out["simulation"]["total"], ensure_ascii=False))
    _write_json("summary.json", out)


if __name__ == "__main__":
    main()
