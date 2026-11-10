"""Score frame errors and one-to-one transition timing on synthetic answers only."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from simulation.core import io
from simulation.run_algorithm import load_config, prediction_dir


def transitions(labels, kind):
    frames = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    pairs = [(int(f), str(labels[f - 1]), str(labels[f])) for f in frames]
    if kind == 'restart':
        return [p for p in pairs if p[1] == 'D' and p[2] in ('H', 'A')]
    if kind == 'turnover':
        return [p for p in pairs if p[1] in ('H', 'A') and p[2] in ('H', 'A')]
    return [p for p in pairs if p[1] in ('H', 'A') and p[2] == 'D']


def match(true, predicted, tolerance):
    candidates = sorted((abs(p[0] - t[0]), ti, pi)
                        for ti, t in enumerate(true) for pi, p in enumerate(predicted)
                        if t[1:] == p[1:] and abs(p[0] - t[0]) <= tolerance)
    used_t, used_p, offsets = set(), set(), []
    for _, ti, pi in candidates:
        if ti not in used_t and pi not in used_p:
            used_t.add(ti)
            used_p.add(pi)
            offsets.append(predicted[pi][0] - true[ti][0])
    return offsets, len(true) - len(used_t), len(predicted) - len(used_p)


def distribution(values):
    if not values:
        return {'matched': 0, 'offsets_frames': []}
    a = np.asarray(values)
    return {'matched': len(values), 'offsets_frames': sorted(map(int, values)),
            'min': int(a.min()), 'p05': float(np.quantile(a, .05)),
            'median': float(np.median(a)), 'p95': float(np.quantile(a, .95)),
            'max': int(a.max()), 'within_2_frames': int((abs(a) <= 2).sum())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--tolerance-s', type=float, default=None)
    args = parser.parse_args()
    config = load_config(args.experiment)
    tolerance_s = (args.tolerance_s if args.tolerance_s is not None else
                   config.get('diagnostics', {}).get('event_match_s', 5.0))
    source = Path(io.dataset_dir(args.dataset))
    truth, samples, _ = io.load_answers(str(source))
    metadata = json.loads((source / 'metadata.json').read_text())
    out = Path(prediction_dir(args.experiment, args.dataset))
    pred = pd.read_csv(out / 'predictions.csv')
    rows, timings = [], []
    for sample in samples.itertuples(index=False):
        g = truth[truth['clip'] == sample.clip].sort_values('frame')['label'].to_numpy()
        p = pred[pred['clip'] == sample.clip].sort_values('frame')['label'].to_numpy()
        row = {'clip': sample.clip, 'family': sample.family, 'subtype': sample.subtype,
               'n_frames': len(g), 'wrong': int((g != p).sum()),
               'dead_as_live': int(((g == 'D') & np.isin(p, ['H', 'A'])).sum()),
               'live_as_dead': int((np.isin(g, ['H', 'A']) & (p == 'D')).sum()),
               'wrong_team': int((np.isin(g, ['H', 'A']) & np.isin(p, ['H', 'A'])
                                  & (g != p)).sum())}
        rows.append(row)
        tolerance = round(tolerance_s * metadata[sample.clip]['fps'])
        for kind in ('restart', 'turnover', 'dead_start'):
            offsets, missed, extra = match(transitions(g, kind), transitions(p, kind), tolerance)
            timings.append({'clip': sample.clip, 'family': sample.family,
                            'subtype': sample.subtype, 'kind': kind,
                            'offsets': offsets, 'missed': missed, 'extra': extra})
    per_clip = pd.DataFrame(rows)
    per_clip.to_csv(out / 'frame_errors.csv', index=False)
    summaries = {}
    for level in ('family', 'subtype'):
        summary = per_clip.groupby(level)[['n_frames', 'wrong', 'dead_as_live',
                                           'live_as_dead', 'wrong_team']].sum()
        summary['error_pct'] = 100 * summary['wrong'] / summary['n_frames']
        summary.to_csv(out / (level + '_errors.csv'))
        summaries[level] = summary.reset_index().to_dict(orient='records')
    timing_summary = {}
    for family in ['ALL'] + sorted(per_clip.family.unique()):
        timing_summary[family] = {}
        for kind in ('restart', 'turnover', 'dead_start'):
            selected = [t for t in timings if t['kind'] == kind
                        and (family == 'ALL' or t['family'] == family)]
            stats = distribution([v for t in selected for v in t['offsets']])
            stats.update(missed=sum(t['missed'] for t in selected),
                         extra=sum(t['extra'] for t in selected))
            timing_summary[family][kind] = stats
    total = per_clip[['n_frames', 'wrong', 'dead_as_live', 'live_as_dead', 'wrong_team']].sum()
    total = {k: int(v) for k, v in total.items()}
    total['error_pct'] = 100 * total['wrong'] / total['n_frames']
    report = {'experiment': args.experiment, 'dataset': args.dataset, 'total': total,
              'groups': summaries, 'timing': timing_summary, 'per_clip_timing': timings,
              'timing_definition': 'prediction minus truth; same source/destination; '
              'one-to-one nearest matching within configured tolerance; misses and extras retained',
              'tolerance_s': tolerance_s}
    (out / 'diagnostics.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'dataset': args.dataset, 'total': total,
                      'timing': timing_summary['ALL']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
