"""Generate the five gap conditions once, then score the new rules against dead_ball_aware.

    python -B -m experiments.20261116_dead_ball_recovery_dev.run_checks --split dev
    python -B -m experiments.20261116_dead_ball_recovery_dev.run_checks --split final

Simulation only: reads no match file, public answer or public score. The dev split also runs
one variant per rule so a change in error can be attributed; the final split does not.
Tags are the accurate profile of the trusted-tag experiment; the baseline is the current
dead_ball_aware with the same parameters and the same tags.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
NAME = '20261116_dead_ball_recovery_{}'
TAGS = 'experiments.20261111_dead_ball_trusted_tags.generate_tags'
TOOLS = 'experiments.20261109_dead_ball_tags_dev'
SUBTYPES = 'TI01,HD01,BP01,BP02,BP03,LC01,LC02,LC03,LC04,LC05,DC01,DC02,DC03,ST01,ST02,ST03,ST04'
GROUPS = {'clean': [], 'mixed': ['--dead-ball-gaps'],
          'delayed': ['--dead-ball-gaps', '--dead-ball-delay-range', '2', '20'],
          'whole': ['--dead-ball-gaps', '--dead-ball-gap-weights', '1', '0', '0'],
          'visible': ['--dead-ball-gaps', '--dead-ball-gap-weights', '0', '0', '1']}
ABLATIONS = ['out_only', 'revive_only', 'absorb_only']


def run(module, *args):
    subprocess.run([sys.executable, '-B', '-m', module, *map(str, args)], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--split', choices=['dev', 'final'], required=True)
    args = parser.parse_args()
    experiment = NAME.format(args.split)
    config = yaml.safe_load((ROOT / 'experiments' / experiment / 'config.yaml').read_text())
    settings = config['validation']
    datasets = []
    for group, options in GROUPS.items():
        dataset = '{}_{}_s{}'.format(settings['dataset_prefix'], group, settings['seed'])
        datasets.append(dataset)
        # An existing dev set is reused; the generator refuses to overwrite a final set.
        if args.split == 'final' or not (ROOT / 'outputs/simulation_sets' / dataset).exists():
            run('simulation.generate', '--dataset-id', dataset, '--subtypes', SUBTYPES,
                '--stories', settings['stories'], '--seed', settings['seed'], *options)
        run(TAGS, '--experiment', experiment, '--dataset', dataset, '--profile', 'accurate')
        tags = ROOT / 'outputs' / experiment / 'tags' / dataset / 'accurate.json'
        variants = [None, 'baseline'] + (ABLATIONS if args.split == 'dev' else [])
        for variant in variants:
            extra = ['--variant', variant] if variant else []
            run('simulation.run_algorithm', '--experiment', experiment, '--dataset', dataset,
                '--tags', tags, *extra)
            scored = experiment + '/' + variant if variant else experiment
            run('simulation.evaluate', '--experiment', scored, '--dataset', dataset)
            run(TOOLS + '.diagnostics', '--experiment', experiment, '--dataset', dataset, *extra)
    run(TOOLS + '.report', '--experiment', experiment, '--datasets', ','.join(datasets))


if __name__ == '__main__':
    main()
