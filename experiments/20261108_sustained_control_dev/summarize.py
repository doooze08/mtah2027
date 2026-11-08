"""Grading-only exact error intervals and provenance; never imported by the algorithm."""

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    experiment, dataset = sys.argv[1:]
    root = Path(__file__).resolve().parents[2]
    source = root / 'outputs/simulation_sets' / dataset
    out = root / 'outputs' / experiment / 'simulation' / dataset
    truth = pd.read_csv(source / 'truth.csv')
    pred = pd.read_csv(out / 'predictions.csv')
    merged = truth.merge(pred, on=['clip', 'frame'], suffixes=('_true', '_pred'),
                         validate='one_to_one', how='outer')
    assert merged.notna().all().all() and len(merged) == len(truth)
    errors = []
    for clip, group in merged.groupby('clip'):
        wrong = group[group.label_true != group.label_pred].sort_values('frame')
        for row in wrong.itertuples(index=False):
            if (errors and errors[-1]['clip'] == clip
                    and errors[-1]['stop'] + 1 == row.frame
                    and errors[-1]['true'] == row.label_true
                    and errors[-1]['pred'] == row.label_pred):
                errors[-1]['stop'] = int(row.frame)
            else:
                errors.append(dict(clip=clip, start=int(row.frame), stop=int(row.frame),
                                   true=row.label_true, pred=row.label_pred))
    files = [source / f for f in ('observations.csv', 'metadata.json', 'truth.csv',
                                  'samples.csv', 'events.csv', 'manifest.json')]
    files += [root / 'algorithms/sustained_control/predict.py',
              root / 'experiments' / experiment / 'config.yaml', out / 'predictions.csv']
    report = dict(experiment=experiment, dataset=dataset, rows=len(merged),
                  wrong_frames=int((merged.label_true != merged.label_pred).sum()),
                  error_intervals_inclusive=errors,
                  sha256={str(p.relative_to(root)): sha(p) for p in files},
                  git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                     cwd=root, text=True).strip(),
                  versions=dict(python=platform.python_version(), numpy=np.__version__,
                                pandas=pd.__version__, pyyaml=yaml.__version__))
    (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    pd.DataFrame(errors, columns=['clip', 'start', 'stop', 'true', 'pred']).to_csv(
        out / 'error_intervals.csv', index=False)
    print(json.dumps({k: report[k] for k in ('rows', 'wrong_frames',
                                           'error_intervals_inclusive')}))


if __name__ == '__main__':
    main()
