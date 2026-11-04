"""Run one experiment's algorithm on a simulation dataset and save its predictions.

    .venv/bin/python -m simulation.run_algorithm --experiment <experiment_id> --dataset <dataset_id>

Reads experiments/<experiment_id>/config.yaml for `algorithm` and `params`, feeds each clip's
observations and game state to algorithms/<algorithm>/predict.py::predict_clip(), and writes
outputs/<experiment_id>/simulation/<dataset_id>/predictions.csv (clip, frame, label).

This script only ever opens the algorithm-side files (via io.load_clips); it never reads truth.
"""

import argparse
import importlib
import os

import pandas as pd
import yaml

from simulation.core import io

LABELS = {"H", "A", "D", "X"}


def load_config(experiment_id):
    path = os.path.join(io.REPO_ROOT, "experiments", experiment_id, "config.yaml")
    with open(path) as handle:
        return yaml.safe_load(handle)


def prediction_dir(experiment_id, dataset_id):
    return os.path.join(io.REPO_ROOT, "outputs", experiment_id, "simulation", dataset_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()

    config = load_config(args.experiment)
    algorithm = importlib.import_module("algorithms.{}.predict".format(config["algorithm"]))
    params = config.get("params") or {}

    rows = []
    for clip_id, observations, game_state in io.load_clips(io.dataset_dir(args.dataset)):
        labels = list(algorithm.predict_clip(observations, game_state, params))
        if len(labels) != len(game_state):
            raise SystemExit("{}: {} labels for {} frames".format(
                clip_id, len(labels), len(game_state)))
        bad = set(labels) - LABELS
        if bad:
            raise SystemExit("{}: labels outside H/A/D/X: {}".format(clip_id, sorted(bad)))
        rows.append(pd.DataFrame({"clip": clip_id, "frame": game_state["frame"],
                                  "label": labels}))
        print("{}  {} frames predicted".format(clip_id, len(labels)))

    out_dir = prediction_dir(args.experiment, args.dataset)
    os.makedirs(out_dir, exist_ok=True)
    pd.concat(rows).to_csv(os.path.join(out_dir, "predictions.csv"), index=False)
    print("wrote {}".format(os.path.relpath(os.path.join(out_dir, "predictions.csv"),
                                            io.REPO_ROOT)))


if __name__ == "__main__":
    main()
