"""Generate and evaluate the frozen final split once; an exclusive marker forbids retries."""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = '20261108_sustained_control_final'
DATASET = 'control_final_20261108_s901'


def main():
    freeze = json.loads((Path(__file__).parent / 'freeze.json').read_text())
    for path, expected in freeze['sha256'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    directory = ROOT / 'outputs' / EXPERIMENT
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / 'final_check_once.json'
    with marker.open('x') as handle:
        json.dump(dict(started_utc=datetime.now(timezone.utc).isoformat(),
                       dataset=DATASET, freeze=freeze), handle, indent=2)
    commands = [
        ['-m', 'simulation.generate', '--dataset-id', DATASET, '--subtypes',
         'TI01,HD01,BP01,BP02,BP03', '--stories', '5', '--seed', '901'],
        ['-m', 'simulation.run_algorithm', '--experiment', EXPERIMENT, '--dataset', DATASET],
        ['-m', 'simulation.evaluate', '--experiment', EXPERIMENT, '--dataset', DATASET],
        ['experiments/20261108_sustained_control_dev/summarize.py', EXPERIMENT, DATASET],
    ]
    for command in commands:
        subprocess.run([sys.executable] + command, cwd=ROOT, check=True)
    with marker.open('a') as handle:
        handle.write('\nCompleted; results must not drive further tuning.\n')


if __name__ == '__main__':
    main()
