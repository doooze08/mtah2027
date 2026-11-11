"""Run the algorithm and print its tag audit without writing a submission.

Simulation:
    python -m experiments.20261111_dead_ball_trusted_tags.audit_tags --experiment <id> \
        --dataset <dataset_id> --tags <tags.json>

Tactical:
    python -m experiments.20261111_dead_ball_trusted_tags.audit_tags --experiment <id> \
        --tactical --data-dir "$PWD/data" --tags smart-tagging

The audit is diagnostic only. It reads observations and interval tags, never truth.csv or answers.
"""

import argparse
import json

from algorithms.dead_ball_aware.predict import infer
from observations.atd import load_tactical
from simulation.core import io
from simulation.run_algorithm import load_config, load_tags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--dataset')
    parser.add_argument('--tactical', action='store_true')
    parser.add_argument('--data-dir')
    parser.add_argument('--tags', required=True)
    parser.add_argument('--out')
    args = parser.parse_args()
    config = load_config(args.experiment)['params']
    tags = load_tags(args.tags, args.data_dir)
    totals = {'clips': 0, 'frames': 0, 'tags_seen': 0, 'tags_used': 0,
              'tags_overridden': 0, 'tag_team_conflicts': 0, 'tags_unmatched': 0,
              'restarts': 0, 'visible_stoppages': 0, 'long_gaps': 0}
    if args.tactical:
        observations, metadata = load_tactical(args.data_dir)
        labels, audit = infer(observations, metadata, config, tags)
        totals['clips'] = 1
        totals['frames'] = len(labels)
        for key in ('tags_seen', 'tags_used', 'tags_overridden', 'tag_team_conflicts',
                    'tags_unmatched'):
            totals[key] = audit[key]
        totals['restarts'] = len(audit['restarts'])
        totals['visible_stoppages'] = len(audit['visible_stoppages'])
        totals['long_gaps'] = len(audit['long_gaps'])
    else:
        for clip_id, observations, metadata in io.load_clips(io.dataset_dir(args.dataset)):
            labels, audit = infer(observations, metadata, config, tags[clip_id])
            totals['clips'] += 1
            totals['frames'] += len(labels)
            for key in ('tags_seen', 'tags_used', 'tags_overridden', 'tag_team_conflicts',
                        'tags_unmatched'):
                totals[key] += audit[key]
            totals['restarts'] += len(audit['restarts'])
            totals['visible_stoppages'] += len(audit['visible_stoppages'])
            totals['long_gaps'] += len(audit['long_gaps'])
    text = json.dumps(totals, indent=2)
    print(text)
    if args.out:
        with open(args.out, 'w') as handle:
            handle.write(text + '\n')


if __name__ == '__main__':
    main()
