"""Run the trusted-tag experiment on simulation data, one profile at a time."""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = '20261111_dead_ball_trusted_tags'
TOOLS = 'experiments.20261111_dead_ball_trusted_tags'
DIAGNOSTICS = 'experiments.20261109_dead_ball_tags_dev.diagnostics'
SUBTYPES = 'TI01,HD01,BP01,BP02,BP03,LC01,LC02,LC03,LC04,LC05,DC01,DC02,DC03,ST01,ST02,ST03,ST04'
GROUPS = {'clean': [], 'mixed': ['--dead-ball-gaps'],
          'delayed': ['--dead-ball-gaps', '--dead-ball-delay-range', '2', '20'],
          'whole': ['--dead-ball-gaps', '--dead-ball-gap-weights', '1', '0', '0'],
          'visible': ['--dead-ball-gaps', '--dead-ball-gap-weights', '0', '0', '1']}
RUNS = [
    ('accurate', 'accurate', 'accurate', True),
    ('none', 'none', 'none', True),
    ('half', 'half', 'half', True),
    ('fake', 'fake', 'fake', True),
    ('flipped', 'flipped', 'flipped', True),
    ('no_tags', None, 'no_tags', False),
    ('legacy', 'old_nominal', 'legacy', True),
]


def run(module, *args):
    subprocess.run([sys.executable, '-B', '-m', module, *map(str, args)], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['dev', 'final'], required=True)
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / 'experiments' / EXPERIMENT / 'config.yaml').read_text())
    settings = config['development' if args.split == 'dev' else 'validation']
    output = ROOT / 'outputs' / EXPERIMENT
    output.mkdir(parents=True, exist_ok=True)
    datasets = []
    for group, options in GROUPS.items():
        dataset = '{}_{}_s{}'.format(settings['dataset_prefix'], group, settings['seed'])
        datasets.append(dataset)
        dataset_exists = (ROOT / 'outputs/simulation_sets' / dataset).exists()
        if not dataset_exists:
            run('simulation.generate', '--dataset-id', dataset, '--subtypes', SUBTYPES,
                '--stories', settings['stories'], '--seed', settings['seed'], *options)
        for name, tag_profile, variant, with_tags in RUNS:
            command = ['simulation.run_algorithm', '--experiment', EXPERIMENT,
                       '--dataset', dataset, '--variant', variant]
            if with_tags:
                tags = output / 'tags' / dataset / (tag_profile + '.json')
                run(TOOLS + '.generate_tags', '--experiment', EXPERIMENT, '--dataset', dataset,
                    '--profile', tag_profile)
                command += ['--tags', tags]
            run(*command)
            run('simulation.evaluate', '--experiment', EXPERIMENT + '/' + variant,
                '--dataset', dataset)
            run(DIAGNOSTICS, '--experiment', EXPERIMENT, '--dataset', dataset,
                '--variant', variant)
    print('datasets: ' + ','.join(datasets))


if __name__ == '__main__':
    main()
