"""Reproduce consolidated development, tag ablation, or one frozen independent check."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEV = '20261109_dead_ball_tags_dev'
FINAL = '20261109_dead_ball_tags_final'
ABLATION = '20261109_dead_ball_tags_ablation'
TOOLS = 'experiments.' + DEV
SUBTYPES = 'TI01,HD01,BP01,BP02,BP03,LC01,LC02,LC03,LC04,LC05,DC01,DC02,DC03,ST01,ST02,ST03,ST04'
GROUPS = {'clean': [], 'mixed': ['--dead-ball-gaps'],
          'delayed': ['--dead-ball-gaps', '--dead-ball-delay-range', '2', '20'],
          'whole': ['--dead-ball-gaps', '--dead-ball-gap-weights', '1', '0', '0'],
          'visible': ['--dead-ball-gaps', '--dead-ball-gap-weights', '0', '0', '1']}


def run(module, *args):
    subprocess.run([sys.executable, '-B', '-m', module, *map(str, args)], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['dev', 'ablation', 'final'], required=True)
    args = parser.parse_args()
    experiment = {'dev': DEV, 'final': FINAL, 'ablation': ABLATION}[args.split]
    config = yaml.safe_load((ROOT / 'experiments' / experiment / 'config.yaml').read_text())
    settings = config['validation']
    output = ROOT / 'outputs' / experiment
    output.mkdir(parents=True, exist_ok=True)
    if args.split == 'final':
        freeze = json.loads((ROOT / 'experiments' / FINAL / 'freeze.json').read_text())
        for path, expected in freeze.items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
        with (output / 'review_final_once.json').open('x') as handle:
            json.dump({'freeze': freeze, 'seed': settings['seed']}, handle, indent=2)
    datasets = []
    for group, options in GROUPS.items():
        dataset = '{}_{}_s{}'.format(settings['dataset_prefix'], group, settings['seed'])
        datasets.append(dataset)
        dataset_exists = (ROOT / 'outputs/simulation_sets' / dataset).exists()
        if args.split == 'final' or (args.split == 'dev' and not dataset_exists):
            run('simulation.generate', '--dataset-id', dataset, '--subtypes', SUBTYPES,
                '--stories', settings['stories'], '--seed', settings['seed'], *options)
        profiles = ['complete', 'none'] if args.split == 'ablation' else ['nominal']
        for profile in profiles:
            run(TOOLS + '.generate_tags', '--experiment', experiment, '--dataset', dataset,
                '--profile', profile)
            variant = ['--variant', profile] if args.split == 'ablation' else []
            tags = output / 'tags' / dataset / (profile + '.json')
            run('simulation.run_algorithm', '--experiment', experiment, '--dataset', dataset,
                '--tags', tags, *variant)
            scored_id = experiment + '/' + profile if variant else experiment
            run('simulation.evaluate', '--experiment', scored_id, '--dataset', dataset)
            run(TOOLS + '.diagnostics', '--experiment', experiment, '--dataset', dataset, *variant)
        if args.split != 'ablation':
            run('simulation.run_algorithm', '--experiment', experiment, '--dataset', dataset,
                '--variant', 'baseline')
            run('simulation.evaluate', '--experiment', experiment + '/baseline', '--dataset', dataset)
            run(TOOLS + '.diagnostics', '--experiment', experiment, '--dataset', dataset,
                '--variant', 'baseline')
    if args.split != 'ablation':
        run(TOOLS + '.report', '--experiment', experiment, '--datasets', ','.join(datasets))


if __name__ == '__main__':
    main()
