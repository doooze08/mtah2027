"""Run interval-tag fusion without changing the shared simulation runner."""

import argparse
import importlib
import hashlib
import json
from pathlib import Path

import pandas as pd

from simulation.core import io
from simulation.run_algorithm import load_config, prediction_dir


def load_real_tags(data_dir=None):
    from starter.load_smart_tagging import load
    teams = {'Barcelona': 'H', 'Atletic Club': 'A', 'N/A': None}
    return [{'start_frame': event['start_frame'], 'end_frame': event['end_frame'],
             'code': event['code'], 'type': event['tags'].get('Type'),
             'team': teams[event['tags']['Team']]}
            for event in load(data_dir=data_dir)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--dataset')
    source.add_argument('--tactical', action='store_true')
    parser.add_argument('--data-dir')
    parser.add_argument('--compare-experiment', help='coordinate baseline, using the same loaded match')
    parser.add_argument('--profile', choices=['nominal', 'complete', 'none'], default='nominal')
    args = parser.parse_args()
    config = load_config(args.experiment)
    algorithm = importlib.import_module('algorithms.' + config['algorithm'] + '.predict')
    if args.tactical:
        from observations.atd import load_tactical
        observations, metadata = load_tactical(args.data_dir)
        tags = [] if args.profile == 'none' else load_real_tags(args.data_dir)
        labels, audit = algorithm.infer(observations, metadata, config['params'], tags)
        result = pd.DataFrame({'frame': observations['frame'], 'label': labels})
        target = Path(io.REPO_ROOT) / 'outputs' / args.experiment / 'submission'
        target.mkdir(parents=True, exist_ok=True)
        result.to_csv(target / (config['algorithm'] + '.csv'), index=False)
        (target / 'audit.json').write_text(json.dumps(audit, indent=2))
        print('rows', len(result), 'labels', result['label'].value_counts().to_dict())
        if args.compare_experiment:
            baseline = load_config(args.compare_experiment)
            module = importlib.import_module('algorithms.' + baseline['algorithm'] + '.predict')
            labels = module.predict(observations, metadata, baseline['params'])
            paired = pd.DataFrame({'frame': observations['frame'], 'label': labels})
            paired_dir = Path(io.REPO_ROOT) / 'outputs' / args.compare_experiment / 'submission'
            paired_dir.mkdir(parents=True, exist_ok=True)
            paired.to_csv(paired_dir / (baseline['algorithm'] + '.csv'), index=False)
            print('baseline', paired['label'].value_counts().to_dict())
    else:
        tag_path = Path(io.REPO_ROOT) / 'outputs' / args.experiment / 'tags' / args.dataset
        tags = json.loads((tag_path / (args.profile + '.json')).read_text())
        results, audits = [], {}
        for clip, observations, metadata in io.load_clips(io.dataset_dir(args.dataset)):
            labels, audit = algorithm.infer(observations, metadata, config['params'], tags[clip])
            results.append(pd.DataFrame({'clip': clip, 'frame': observations['frame'], 'label': labels}))
            audits[clip] = audit
        target = Path(prediction_dir(args.experiment, args.dataset))
        target.mkdir(parents=True, exist_ok=True)
        pd.concat(results, ignore_index=True).to_csv(target / 'predictions.csv', index=False)
        (target / 'audit.json').write_text(json.dumps(audits, indent=2))
        print(args.dataset, len(results), 'clips', sum(map(len, results)), 'frames')
    source_file = Path(algorithm.__file__)
    (target / 'run_metadata.json').write_text(json.dumps(
        {'experiment': args.experiment, 'config': config, 'profile': args.profile,
         'source_sha256': hashlib.sha256(source_file.read_bytes()).hexdigest(),
         'source': str(source_file.relative_to(io.REPO_ROOT)),
         'input': args.dataset or 'tactical', 'reads_public_answers': False}, indent=2))


if __name__ == '__main__':
    main()
