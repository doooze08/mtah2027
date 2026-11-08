"""Run the same algorithm entry on a simulation dataset or real tactical ATD.

    python -m simulation.run_algorithm --experiment <id> --dataset <dataset_id>
    python -m simulation.run_algorithm --experiment <id> --tactical [--data-dir /path/to/data]

Simulation input reads only observations.csv and metadata.json; neither mode reads answers.
"""

import argparse
import importlib
import os

import pandas as pd
import yaml

from simulation.core import io


def load_config(experiment_id):
    path = os.path.join(io.REPO_ROOT, "experiments", experiment_id, "config.yaml")
    with open(path) as handle:
        return yaml.safe_load(handle)


def prediction_dir(experiment_id, dataset_id):
    return os.path.join(io.REPO_ROOT, "outputs", experiment_id, "simulation", dataset_id)


def predict_frames(algorithm, observations, metadata, params):
    """Call the single entry and check its output length before writing."""
    labels = list(algorithm.predict(observations, metadata, params))
    if len(labels) != len(observations):
        raise ValueError("{} labels for {} frames".format(len(labels), len(observations)))
    return pd.DataFrame({"frame": observations["frame"].to_numpy(), "label": labels})


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset")
    source.add_argument("--tactical", action="store_true")
    parser.add_argument("--data-dir", help="match asset root; only with --tactical")
    args = parser.parse_args()
    config = load_config(args.experiment)
    algorithm = importlib.import_module("algorithms.{}.predict".format(config["algorithm"]))
    params = config.get("params") or {}

    if args.tactical:
        from observations.atd import load_tactical

        observations, metadata = load_tactical(args.data_dir)
        result = predict_frames(algorithm, observations, metadata, params)
        target = os.path.join(io.REPO_ROOT, "outputs", args.experiment, "submission",
                              config["algorithm"] + ".csv")
    else:
        rows = []
        for clip_id, observations, metadata in io.load_clips(io.dataset_dir(args.dataset)):
            result = predict_frames(algorithm, observations, metadata, params)
            result.insert(0, "clip", clip_id)
            rows.append(result)
            print("{}  {} frames predicted".format(clip_id, len(result)))
        result = pd.concat(rows, ignore_index=True)
        target = os.path.join(prediction_dir(args.experiment, args.dataset), "predictions.csv")

    os.makedirs(os.path.dirname(target), exist_ok=True)
    result.to_csv(target, index=False)
    print("wrote {}".format(os.path.relpath(target, io.REPO_ROOT)))


if __name__ == "__main__":
    main()
