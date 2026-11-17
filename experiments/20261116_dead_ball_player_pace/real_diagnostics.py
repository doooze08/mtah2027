"""Diagnostics only on the real tactical file, with official Smart Tagging intervals.

No answer is read, no five-minute score is produced, and nothing here is used to choose a
parameter.  The output counts what the two switches would reject.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import json

import numpy as np
import pandas as pd
import yaml

from algorithms.dead_ball_aware.pace import player_pace
from algorithms.dead_ball_aware.predict import infer
from observations.atd import load_tactical
from simulation.run_algorithm import load_tags

EXPERIMENT = "20261116_dead_ball_player_pace"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "outputs", EXPERIMENT, "real_diagnostics.json")


def f1_from_speed(observations):
    slots = [c[:-2] for c in observations.columns if c.endswith("_s")]
    speeds = observations[[slot + "_s" for slot in slots]].to_numpy(dtype=float)
    finite = np.isfinite(speeds)
    f1 = np.full(len(observations), np.nan)
    enough = finite.sum(axis=1) >= 5
    values = np.where(finite, speeds, np.nan)
    f1[enough] = np.nanmedian(values[enough], axis=1)
    return f1


def compare_f1(f1_position, f1_speed):
    both = np.isfinite(f1_position) & np.isfinite(f1_speed)
    difference = f1_position[both] - f1_speed[both]
    return {
        "frames_both": int(both.sum()),
        "frames_position_only": int(np.isfinite(f1_position).sum() - both.sum()),
        "frames_speed_only": int(np.isfinite(f1_speed).sum() - both.sum()),
        "median_position": float(np.nanmedian(f1_position)),
        "median_speed": float(np.nanmedian(f1_speed)),
        "median_difference": float(np.median(difference)),
        "mean_absolute_difference": float(np.mean(np.abs(difference))),
        "p95_absolute_difference": float(np.quantile(np.abs(difference), 0.95)),
        "correlation": float(np.corrcoef(f1_position[both], f1_speed[both])[0, 1]),
    }


def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config = yaml.safe_load(open(os.path.join(
        root, "experiments", EXPERIMENT, "config.yaml")))
    observations, metadata = load_tactical(os.path.join(root, "data"))
    tags = load_tags("smart-tagging", os.path.join(root, "data"))
    f1_position = player_pace(observations, metadata)
    f1_speed = f1_from_speed(observations)
    # A clip is the whole real file here; the tag adapter returns the event list.
    clip_tags = tags
    result = {"frames": int(len(observations)),
              "f1_position_vs_speed": compare_f1(f1_position, f1_speed),
              "arms": {}}
    for arm in ("off", "gap", "restart", "both"):
        variant = config["variants"][arm]
        params = {**config["params"], **variant.get("params", {})}
        labels, audit = infer(observations, metadata, params, clip_tags)
        labels = np.array(labels)
        result["arms"][arm] = {
            "d_frames": int((labels == "D").sum()),
            "long_gaps": len(audit["long_gaps"]),
            "b1_vetoed_gaps": sum(1 for check in audit["long_gap_checks"] if check["vetoed"]),
            "restart_actions": len(audit["restarts"]),
            "b2_rejected_restarts": len(audit["restart_rejections"]),
            "tags_used": int(audit.get("tags_used", 0)),
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
