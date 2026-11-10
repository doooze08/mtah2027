"""Run the same algorithm entry on a simulation dataset or real tactical ATD.

    python -m simulation.run_algorithm --experiment <id> --dataset <dataset_id>
    python -m simulation.run_algorithm --experiment <id> --tactical [--data-dir /path/to/data]

Simulation reads observations.csv, metadata.json and optional interval tags; neither mode reads answers.
"""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path

import pandas as pd
import yaml

from simulation.core import io


def load_config(experiment_id):
    path = os.path.join(io.REPO_ROOT, "experiments", experiment_id, "config.yaml")
    with open(path) as handle:
        return yaml.safe_load(handle)


def prediction_dir(experiment_id, dataset_id):
    return os.path.join(io.REPO_ROOT, "outputs", experiment_id, "simulation", dataset_id)


def predict_frames(algorithm, observations, metadata, params, tags=None):
    """Call the single entry and check its output length before writing."""
    optional = {} if tags is None else {'tags': tags}
    labels = list(algorithm.predict(observations, metadata, params, **optional))
    if len(labels) != len(observations):
        raise ValueError("{} labels for {} frames".format(len(labels), len(observations)))
    return pd.DataFrame({"frame": observations["frame"].to_numpy(), "label": labels})


def load_tags(source, data_dir=None):
    """Read interval JSON, or adapt official Smart Tagging for a local tactical run."""
    if source == 'smart-tagging':
        from starter.load_smart_tagging import load

        teams = {'Barcelona': 'H', 'Atletic Club': 'A', 'N/A': None}
        return [{'start_frame': event['start_frame'], 'end_frame': event['end_frame'],
                 'code': event['code'], 'type': event['tags'].get('Type'),
                 'team': teams[event['tags']['Team']]}
                for event in load(data_dir=data_dir)]
    with open(source) as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset")
    source.add_argument("--tactical", action="store_true")
    parser.add_argument("--data-dir", help="match asset root; only with --tactical")
    parser.add_argument('--tags', help='Optional interval JSON: clip -> list for simulation, '
                        'list for tactical; smart-tagging loads official tactical intervals')
    parser.add_argument('--variant', help='Named config variant; outputs use an experiment subdirectory')
    args = parser.parse_args()
    config = load_config(args.experiment)
    variant = config['variants'][args.variant] if args.variant else {}
    config = {**config, **variant,
              'params': {**(config.get('params') or {}), **variant.get('params', {})}}
    output_id = os.path.join(args.experiment, args.variant) if args.variant else args.experiment
    algorithm = importlib.import_module("algorithms.{}.predict".format(config["algorithm"]))
    params = config.get("params") or {}
    tags = load_tags(args.tags, args.data_dir) if args.tags else None

    if args.tactical:
        from observations.atd import load_tactical

        observations, metadata = load_tactical(args.data_dir)
        result = predict_frames(algorithm, observations, metadata, params, tags)
        target = os.path.join(io.REPO_ROOT, "outputs", output_id, "submission",
                              config["algorithm"] + ".csv")
    else:
        rows = []
        for clip_id, observations, metadata in io.load_clips(io.dataset_dir(args.dataset)):
            result = predict_frames(algorithm, observations, metadata, params,
                                    tags[clip_id] if tags is not None else None)
            result.insert(0, "clip", clip_id)
            rows.append(result)
            print("{}  {} frames predicted".format(clip_id, len(result)))
        result = pd.concat(rows, ignore_index=True)
        target = os.path.join(prediction_dir(output_id, args.dataset), "predictions.csv")

    os.makedirs(os.path.dirname(target), exist_ok=True)
    result.to_csv(target, index=False)
    source = Path(algorithm.__file__)
    Path(target).with_name('run_metadata.json').write_text(json.dumps({
        'experiment': args.experiment, 'variant': args.variant, 'config': config,
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'tags_sha256': (hashlib.sha256(json.dumps(tags, sort_keys=True).encode()).hexdigest()
                        if tags is not None else None),
        'input': args.dataset or 'tactical', 'reads_public_answers': False}, indent=2))
    print("wrote {}".format(os.path.relpath(target, io.REPO_ROOT)))


if __name__ == "__main__":
    main()
