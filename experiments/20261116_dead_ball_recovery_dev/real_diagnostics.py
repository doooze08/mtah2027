"""Describe what each rule changes on the real tactical tracking, without any answer.

    python -B -m experiments.20261116_dead_ball_recovery_dev.real_diagnostics [--data-dir DIR]
    python -B -m experiments.20261116_dead_ball_recovery_dev.real_diagnostics --no-tags

Runs dead_ball_recovery with the new rules off (identical to dead_ball_aware), with each rule
alone, and with all three, on the same input. It reports aggregate properties of the outputs
only: label shares, possession counts and durations, how often each rule fired, and how much of
the predicted dead ball has a visible, fast, in-pitch ball. It reads no public or private
answer and exports no frame numbers. These numbers say whether an output is plausible, not
whether it is correct.
"""

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import yaml

from algorithms.dead_ball_recovery.predict import infer, runs

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = '20261116_dead_ball_recovery_dev'
OFF = {'out_confirm_s': 0.0, 'revive_after_gap': False, 'min_possession_s': 0.0}


def variants(params):
    return {'rules_off': {**params, **OFF},
            'out_only': {**params, **OFF, 'out_confirm_s': params['out_confirm_s']},
            'revive_only': {**params, **OFF, 'revive_after_gap': True},
            'absorb_only': {**params, **OFF, 'min_possession_s': params['min_possession_s']},
            'all_rules': dict(params)}


def describe(labels, audit, observations, metadata, params, blocks):
    """Aggregate one output over the graded blocks [(first_frame, last_frame), ...]."""
    fps = metadata['fps']
    scale = np.array([metadata['pitch_length'], metadata['pitch_width']])
    ball = observations[['ball_x', 'ball_y']].to_numpy(dtype=float) * scale
    known = np.isfinite(ball).all(axis=1)
    radius = params['ball_radius_m']
    inside = known & ~((ball < -radius) | (ball > scale + radius)).any(axis=1)
    speed = np.r_[np.linalg.norm(np.diff(ball, axis=0), axis=1) * fps, np.nan]
    labels = np.asarray(labels, dtype=object)
    graded = np.zeros(len(labels), dtype=bool)
    for first, last in blocks:
        graded[first:last + 1] = True
    counts = {label: int(((labels == label) & graded).sum()) for label in 'HAD'}
    durations = []
    for first, last in blocks:
        for label, group in itertools.groupby(labels[first:last + 1]):
            if label in ('H', 'A'):
                durations.append(len(list(group)) / fps)
    durations = np.asarray(durations)
    dead = (labels == 'D') & graded
    # A fast, visible, in-pitch ball during a predicted stoppage: the "stuck in D" symptom.
    fast_dead = dead & inside & (speed >= params['release_speed_m_s'])
    stuck_runs = sum(1 for start, stop in runs(dead) if fast_dead[start:stop].sum() >= fps)
    in_blocks = lambda frames: int(sum(bool(graded[f]) for f in frames))
    return {
        'graded_frames': int(graded.sum()),
        'frames': counts,
        'dead_share': counts['D'] / max(1, int(graded.sum())),
        'possessions': int(len(durations)),
        'possession_s_median': float(np.median(durations)) if len(durations) else None,
        'possession_s_mean': float(durations.mean()) if len(durations) else None,
        'possessions_under_1s': int((durations < 1).sum()),
        'possessions_under_2s': int((durations < 2).sum()),
        'long_gaps': in_blocks(g[0] for g in audit['long_gaps']),
        'restarts': in_blocks(r['frame'] for r in audit['restarts']),
        'revived_gaps': in_blocks(g['frame'] for g in audit['revived_gaps']),
        'absorbed_possessions': int(audit['absorbed_possessions']),
        'dead_frames_with_fast_visible_ball': int(fast_dead.sum()),
        'dead_runs_with_1s_of_fast_visible_ball': int(stuck_runs),
        'live_frames_with_ball_missing': int(((labels != 'D') & graded & ~known).sum()),
    }


def compare(observations, metadata, params, tags, blocks):
    report = {}
    for name, config in variants(params).items():
        labels, audit = infer(observations, metadata, config, tags)
        report[name] = describe(labels, audit, observations, metadata, params, blocks)
    return report


def render(report):
    names = list(report)
    rows = [('graded frames', lambda r: r['graded_frames']),
            ('H frames', lambda r: r['frames']['H']), ('A frames', lambda r: r['frames']['A']),
            ('D frames', lambda r: r['frames']['D']),
            ('D share', lambda r: '{:.1%}'.format(r['dead_share'])),
            ('possessions', lambda r: r['possessions']),
            ('median possession (s)', lambda r: '{:.1f}'.format(r['possession_s_median'] or 0)),
            ('mean possession (s)', lambda r: '{:.1f}'.format(r['possession_s_mean'] or 0)),
            ('possessions < 1 s', lambda r: r['possessions_under_1s']),
            ('possessions < 2 s', lambda r: r['possessions_under_2s']),
            ('long ball gaps', lambda r: r['long_gaps']),
            ('restarts found', lambda r: r['restarts']),
            ('  of which revived after gap', lambda r: r['revived_gaps']),
            ('short possessions absorbed', lambda r: r['absorbed_possessions']),
            ('D frames, ball visible and fast', lambda r: r['dead_frames_with_fast_visible_ball']),
            ('D runs with >=1 s of that', lambda r: r['dead_runs_with_1s_of_fast_visible_ball']),
            ('live frames, ball missing', lambda r: r['live_frames_with_ball_missing'])]
    width = max(len(label) for label, _ in rows)
    lines = [' ' * width + ''.join('{:>14}'.format(n) for n in names)]
    for label, value in rows:
        lines.append(label.ljust(width) + ''.join('{:>14}'.format(value(report[n])) for n in names))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--data-dir')
    parser.add_argument('--no-tags', action='store_true', help='coordinate branch only')
    args = parser.parse_args()
    from games import GAME, half_video_blocks
    from observations.atd import load_tactical
    from simulation.run_algorithm import load_tags

    params = yaml.safe_load((ROOT / 'experiments' / EXPERIMENT / 'config.yaml').read_text())['params']
    observations, metadata = load_tactical(args.data_dir)
    tags = None if args.no_tags else load_tags('smart-tagging', args.data_dir)
    blocks = [(first, last) for _, first, last in half_video_blocks(GAME)]
    report = compare(observations, metadata, params, tags, blocks)
    print(render(report))
    target = ROOT / 'outputs' / EXPERIMENT / 'real_diagnostics.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2))
    print('wrote {}'.format(target.relative_to(ROOT)))


if __name__ == '__main__':
    main()
