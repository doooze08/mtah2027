"""Generate interval tags for the trusted-tag experiment.

The accurate profile has no retention loss and no timing jitter. Stress profiles are hand-written
scenarios: no tags, half retained, live-play fake tags, and flipped team names. The old_nominal
profile reproduces the 2026-11-09 assumption for a same-data comparison. No profile reads truth.csv.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from simulation.core import io
from simulation.run_algorithm import load_config

PROFILES = ('accurate', 'none', 'half', 'fake', 'flipped', 'old_nominal')


def _tag(sample, event, ordinal, config, fps, rng, retention, jitter_s):
    keep = rng.random()
    jitter = rng.uniform(-jitter_s, jitter_s)
    if keep >= retention:
        return None
    kind = ('Throw-in' if sample.subtype == 'TI01'
            or (sample.subtype == 'ST02' and ordinal > 0)
            else 'Kick Off (Start)' if ordinal == 0
            else 'Goal Kick' if sample.subtype == 'ST03'
            else 'Kick Off (After Goal)' if sample.subtype == 'ST04'
            else 'Free Kick')
    duration = config['opening_duration_s'] if ordinal == 0 else config['restart_duration_s']
    start = max(0, round((float(event.t) - config['pre_s'] + jitter) * fps))
    return {'start_frame': start,
            'end_frame': start + round(duration * fps),
            'code': 'SET PIECES',
            'type': kind,
            'team': None if kind in ('Throw-in', 'Kick Off (Start)',
                                     'Kick Off (After Goal)') else event.team}


def _event_tags(sample, events, config, fps, rng, retention, jitter_s):
    tags = []
    restarts = events[(events['clip'] == sample.clip) & (events['event'] == 'legal_restart')]
    for ordinal, event in enumerate(restarts.itertuples(index=False)):
        tag = _tag(sample, event, ordinal, config, fps, rng, retention, jitter_s)
        if tag is not None:
            tags.append(tag)
    return tags


def _live_mask(events, n_frames):
    live = np.zeros(n_frames, dtype=bool)
    state, cursor = False, 0
    for event in events.sort_values('frame').itertuples(index=False):
        frame = min(max(int(event.frame), 0), n_frames)
        live[cursor:frame] = state
        if event.event in ('ball_out', 'stoppage'):
            state = False
        elif event.event == 'legal_restart':
            state = True
        cursor = frame
    live[cursor:] = state
    return live


def _fake_tags(sample, observations, events, config, fps, rng, pitch):
    """Add labels on visible, fast live-ball frames; they are deliberately false positives."""
    clip_obs = observations[observations['clip'] == sample.clip].sort_values('frame')
    n = len(clip_obs)
    if n < 2:
        return []
    live = _live_mask(events[events['clip'] == sample.clip], n)
    scale = np.asarray(pitch)
    ball = clip_obs[['ball_x', 'ball_y']].to_numpy(dtype=float) * scale
    speed = np.full(n, np.nan)
    speed[:-1] = np.linalg.norm(np.diff(ball, axis=0), axis=1) * fps
    pre_frames = round(config['pre_s'] * fps)
    candidates = np.flatnonzero(live & np.isfinite(speed) & (speed >= 8.0)
                                & (np.arange(n) >= pre_frames))
    rng.shuffle(candidates)
    chosen = []
    for frame in candidates:
        if all(abs(int(frame) - other) >= 5 * fps for other in chosen):
            chosen.append(int(frame))
        if len(chosen) >= 2:
            break
    tags = []
    for frame in chosen:
        start = max(0, frame - pre_frames)
        tags.append({'start_frame': start,
                     'end_frame': start + round(config['restart_duration_s'] * fps),
                     'code': 'SET PIECES', 'type': 'Free Kick', 'team': None})
    return tags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    args = parser.parse_args()
    config = load_config(args.experiment)['synthetic_tags']
    source = Path(io.dataset_dir(args.dataset))
    events = pd.read_csv(source / 'events.csv', keep_default_na=False)
    samples = pd.read_csv(source / 'samples.csv')
    metadata = json.loads((source / 'metadata.json').read_text())
    observations = pd.read_csv(source / 'observations.csv', dtype={'clip': str})
    result = {}
    counts = {'available': 0, 'retained': 0, 'fake': 0}
    for sample in samples.itertuples(index=False):
        fps = metadata[sample.clip]['fps']
        pitch = (metadata[sample.clip]['pitch_length'],
                 metadata[sample.clip]['pitch_width'])
        rng = np.random.default_rng(np.random.SeedSequence(
            [int(sample.seed), int(config['seed']), PROFILES.index(args.profile)]))
        if args.profile == 'none':
            result[sample.clip] = []
            continue
        if args.profile == 'half':
            retention, jitter = config['half_retention'], 0.0
        elif args.profile == 'old_nominal':
            retention, jitter = config['legacy_retention'], config['legacy_jitter_s']
        else:
            retention, jitter = 1.0, 0.0
        tags = _event_tags(sample, events, config, fps, rng, retention, jitter)
        available = len(events[(events['clip'] == sample.clip)
                               & (events['event'] == 'legal_restart')])
        counts['available'] += available
        counts['retained'] += len(tags)
        if args.profile == 'flipped':
            for tag in tags:
                if tag['team'] in ('H', 'A'):
                    tag['team'] = 'A' if tag['team'] == 'H' else 'H'
        if args.profile == 'fake':
            fake = _fake_tags(sample, observations, events, config, fps, rng, pitch)
            tags.extend(fake)
            counts['fake'] += len(fake)
        result[sample.clip] = tags
    target = Path(io.REPO_ROOT) / 'outputs' / args.experiment / 'tags' / args.dataset
    target.mkdir(parents=True, exist_ok=True)
    (target / (args.profile + '.json')).write_text(json.dumps(result, indent=2))
    (target / (args.profile + '_manifest.json')).write_text(json.dumps(
        {'profile': args.profile, 'config': config, 'counts': counts,
         'source': 'script legal_restart events and algorithm-visible observations; no truth.csv',
         'assumption': 'hand-written retention and timing stress; not measured provider accuracy'},
        indent=2))
    print(args.dataset, args.profile, counts)


if __name__ == '__main__':
    main()
