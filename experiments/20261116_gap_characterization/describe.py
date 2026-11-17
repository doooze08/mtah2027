#!/usr/bin/env python3
"""Post-hoc descriptions requested in review.

These tables are descriptive only.  They do not change samples, features, or
classifiers, and they do not select a threshold for an algorithm.
"""

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

import features  # noqa: E402

OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "20261116_gap_characterization")


def _label(event):
    return event["type"] + (f" {event['subtype']}" if event["subtype"] else "")


def _event_context(events, start_frame, stop_frame, n_before=3, n_after=2):
    before = [event for event in events if event["frame"] < start_frame][-n_before:]
    after = [event for event in events if event["frame"] >= stop_frame][:n_after]
    return (
        " | ".join(_label(event) for event in before),
        " | ".join(_label(event) for event in after),
    )


def _d_start(labels, start):
    index = start
    while index > 0 and labels[index - 1] == "D":
        index -= 1
    return index


def dead_visible_groups(frame):
    rows = []
    for match in (1, 2, 3):
        clips = {clip["clip"]: clip for clip in features.load_clips(match)}
        subset = frame[(frame["match"] == match) &
                       (frame["sample_type"] == "dead_visible")]
        for _, sample in subset.iterrows():
            clip = clips[sample["clip"]]
            start = int(round(sample["start_s"] * features.FPS))
            stop = int(round(sample["stop_s"] * features.FPS))
            start_of_d = _d_start(clip["labels"], start)
            rows.append({
                "split": sample["split"],
                "match": match,
                "clip": sample["clip"],
                "start_s": sample["start_s"],
                "stop_s": sample["stop_s"],
                "length_s": sample["length_s"],
                "since_d_start_s": (start - start_of_d) / features.FPS,
                "f1_speed_med": sample["f1_speed_med"],
                "team_speed_med": sample["team_speed_med"],
            })
    table = pd.DataFrame(rows)
    table["group"] = np.where(table["since_d_start_s"] < 1.0,
                              "at_d_start_lt_1s", "mid_d_ge_1s")
    summary = table.groupby("group").agg(
        n=("f1_speed_med", "size"),
        length_median=("length_s", "median"),
        length_mean=("length_s", "mean"),
        f1_median=("f1_speed_med", "median"),
        f1_q1=("f1_speed_med", lambda values: np.percentile(values, 25)),
        f1_q3=("f1_speed_med", lambda values: np.percentile(values, 75)),
    ).reset_index()
    return table, summary


def fast_dead_gaps(frame):
    artificial = frame[frame["sample_type"] == "artificial_live"]
    q25 = float(artificial["f1_speed_med"].quantile(0.25))
    fast = frame[(frame["sample_type"] == "dead_gap") &
                 (frame["f1_speed_med"] > q25)].copy()
    fast["reappear_to_disappear_le_10m"] = fast["reappear_to_disappear_m"] <= 10.0
    fast["length_le_10s"] = fast["length_s"] <= 10.0

    rows = []
    for match in (1, 2, 3):
        clips = features.load_clips(match)
        raw = features.read_metrica_events(match)
        events = features.clip_events(clips, raw)
        subset = fast[fast["match"] == match]
        for _, sample in subset.iterrows():
            before, after = _event_context(
                events[sample["clip"]],
                int(round(sample["start_s"] * features.FPS)),
                int(round(sample["stop_s"] * features.FPS)),
            )
            rows.append({
                "split": sample["split"],
                "match": match,
                "clip": sample["clip"],
                "start_s": sample["start_s"],
                "stop_s": sample["stop_s"],
                "length_s": sample["length_s"],
                "f1_speed_med": sample["f1_speed_med"],
                "reappear_category": sample["reappear_category"],
                "disappear_category": sample["disappear_category"],
                "reappear_to_disappear_m": sample["reappear_to_disappear_m"],
                "reappear_to_disappear_le_10m": bool(
                    sample["reappear_to_disappear_m"] <= 10.0),
                "length_le_10s": bool(sample["length_s"] <= 10.0),
                "events_before": before,
                "events_after": after,
            })
    table = pd.DataFrame(rows).sort_values(
        ["split", "match", "clip", "start_s"]).reset_index(drop=True)

    other_far = artificial[
        artificial["reappear_category"].eq("other") &
        artificial["reappear_to_disappear_m"].gt(10.0)]
    summary = {
        "artificial_q25_f1_speed_med": q25,
        "n_fast_dead_gaps": int(len(table)),
        "n_fast_dead_by_split": table.groupby("split").size().to_dict(),
        "reappear_categories": table["reappear_category"].value_counts().to_dict(),
        "n_distance_le_10m": int(table["reappear_to_disappear_le_10m"].sum()),
        "n_length_le_10s": int(table["length_le_10s"].sum()),
        "n_other_and_distance_gt_10m": int(
            ((table["reappear_category"] == "other") &
             (table["reappear_to_disappear_m"] > 10.0)).sum()),
        "n_artificial_other_and_distance_gt_10m": int(len(other_far)),
        "n_artificial": int(len(artificial)),
        "fraction_artificial_other_and_distance_gt_10m": (
            float(len(other_far) / len(artificial)) if len(artificial) else None),
    }
    return table, summary


def real_live_event_context(frame):
    rows = []
    for match in (1, 2, 3):
        clips = features.load_clips(match)
        raw = features.read_metrica_events(match)
        events = features.clip_events(clips, raw)
        subset = frame[(frame["match"] == match) &
                       (frame["sample_type"] == "real_live_gap")]
        for _, sample in subset.iterrows():
            before, after = _event_context(
                events[sample["clip"]],
                int(round(sample["start_s"] * features.FPS)),
                int(round(sample["stop_s"] * features.FPS)),
            )
            rows.append({
                "match": match,
                "clip": sample["clip"],
                "start_s": sample["start_s"],
                "stop_s": sample["stop_s"],
                "events_before": before,
                "events_after": after,
            })
    return pd.DataFrame(rows)


def main():
    frame = pd.read_csv(os.path.join(OUTPUT_DIR, "samples_all.csv"))
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    visible, visible_summary = dead_visible_groups(frame)
    visible.to_csv(os.path.join(OUTPUT_DIR, "dead_visible_groups.csv"), index=False)
    visible_summary.to_csv(
        os.path.join(OUTPUT_DIR, "dead_visible_group_summary.csv"), index=False)

    fast, fast_summary = fast_dead_gaps(frame)
    fast.to_csv(os.path.join(OUTPUT_DIR, "fast_dead_gaps.csv"), index=False)

    live_events = real_live_event_context(frame)
    live_events.to_csv(
        os.path.join(OUTPUT_DIR, "real_live_event_context.csv"), index=False)

    summary = {
        "dead_visible_groups": visible_summary.to_dict(orient="records"),
        "fast_dead_gaps": fast_summary,
        "n_real_live_gap": int(len(live_events)),
    }
    with open(os.path.join(OUTPUT_DIR, "description_summary.json"), "w") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
