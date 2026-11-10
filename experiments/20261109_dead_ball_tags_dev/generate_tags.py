"""Generate interval-valued tags from script restart events, never from truth.csv."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from simulation.core import io
from simulation.run_algorithm import load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--profile', choices=['nominal', 'complete', 'none'], default='nominal')
    args = parser.parse_args()
    config = load_config(args.experiment)['synthetic_tags']
    source = Path(io.dataset_dir(args.dataset))
    events = pd.read_csv(source / 'events.csv', keep_default_na=False)
    samples = pd.read_csv(source / 'samples.csv')
    metadata = json.loads((source / 'metadata.json').read_text())
    result, counts = {}, {'available': 0, 'retained': 0}
    for sample in samples.itertuples(index=False):
        rng = np.random.default_rng(np.random.SeedSequence([int(sample.seed), config['seed']]))
        fps = metadata[sample.clip]['fps']
        tags = []
        restarts = events[(events['clip'] == sample.clip) & (events['event'] == 'legal_restart')]
        for ordinal, event in enumerate(restarts.itertuples(index=False)):
            counts['available'] += 1
            keep = rng.random()
            jitter = rng.uniform(-config['jitter_s'], config['jitter_s'])
            retention = {'nominal': config['retention'], 'complete': 1.0, 'none': 0.0}[args.profile]
            if keep >= retention:
                continue
            kind = ('Throw-in' if sample.subtype == 'TI01' or
                    (sample.subtype == 'ST02' and ordinal > 0) else
                    'Kick Off (Start)' if ordinal == 0 else
                    'Goal Kick' if sample.subtype == 'ST03' else
                    'Kick Off (After Goal)' if sample.subtype == 'ST04' else 'Free Kick')
            duration = config['opening_duration_s'] if ordinal == 0 else config['restart_duration_s']
            first = round((float(event.t) - config['pre_s'] + jitter) * fps)
            # Preserve uncertain annotation windows; do not expose the exact event frame.
            tags.append({'start_frame': first, 'end_frame': first + round(duration * fps),
                         'code': 'SET PIECES', 'type': kind,
                         'team': None if kind in ('Throw-in', 'Kick Off (Start)',
                                                  'Kick Off (After Goal)') else event.team})
            counts['retained'] += 1
        result[sample.clip] = tags
    target = Path(io.REPO_ROOT) / 'outputs' / args.experiment / 'tags' / args.dataset
    target.mkdir(parents=True, exist_ok=True)
    (target / (args.profile + '.json')).write_text(json.dumps(result, indent=2))
    (target / (args.profile + '_manifest.json')).write_text(json.dumps(
        {'profile': args.profile, 'config': config, 'counts': counts,
         'source': 'script legal_restart events and sample metadata; no truth.csv',
         'assumption': 'synthetic retention and timing, not measured provider accuracy'}, indent=2))
    print(args.dataset, args.profile, counts)


if __name__ == '__main__':
    main()
