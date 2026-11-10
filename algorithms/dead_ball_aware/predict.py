"""Offline inference from coordinates and optional interval-valued event tags."""

import math

import numpy as np


def runs(mask):
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False]))
    return zip(edges[::2], edges[1::2])


def infer(observations, metadata, config, tags=None):
    """Return labels and observation-only diagnostics; never read files or answers."""
    fps = metadata['fps']
    scale = np.array([metadata['pitch_length'], metadata['pitch_width']])
    ball = observations[['ball_x', 'ball_y']].to_numpy(dtype=float) * scale
    n = len(ball)
    if not n:
        return [], {'restarts': [], 'visible_stoppages': [], 'long_gaps': []}
    slots = list(metadata['slot_teams'])
    teams = np.array([metadata['slot_teams'][s] for s in slots])
    players = np.stack([observations[[s + '_x', s + '_y']].to_numpy(dtype=float)
                        for s in slots], axis=1) * scale
    known = np.isfinite(ball).all(axis=1)
    radius = config['ball_radius_m']
    outside = known & ((ball < -radius) | (ball > scale + radius)).any(axis=1)
    offset = ball[:, None] - players
    distance = np.linalg.norm(offset, axis=2)
    relative = np.linalg.norm(np.diff(offset, axis=0), axis=2) * fps
    speed = np.r_[np.linalg.norm(np.diff(ball, axis=0), axis=1) * fps, np.nan]

    # Confirm actual control only while live; no reception-frame micro-adjustment.
    stable = (distance <= config['control_radius_m']) & ~outside[:, None]
    stable[:-1] &= relative <= config['relative_speed_m_s']
    stable[-1] = False
    confirm = math.ceil(config['confirm_s'] * fps)
    confirmed = np.zeros_like(stable)
    for player in range(len(slots)):
        for start, stop in runs(stable[:, player]):
            if stop - start >= confirm:
                confirmed[start:stop - confirm + 1, player] = True
    evidence = {}
    for player in range(len(slots)):
        for start, stop in runs(stable[:, player]):
            if (start and stop - start >= confirm
                    and not confirmed[start, teams != teams[player]].any()):
                evidence.setdefault(int(start), set()).add(str(teams[player]))

    forced_dead = outside.copy()
    gaps = []
    for start, stop in runs(~known):
        if (stop - start) / fps > config['gap_s']:
            forced_dead[start:stop] = True
            gaps.append([int(start), int(stop)])

    slow = speed <= config['slow_speed_m_s']
    slow_start = np.full(n, -1, dtype=int)
    for start, stop in runs(slow):
        slow_start[start:stop] = start

    relevant_tags = [t for t in (tags or []) if t['code'] == 'SET PIECES']
    margin = math.ceil(config['tag_margin_s'] * fps)
    rise = math.ceil(config['release_rise_s'] * fps)
    separate = math.ceil(config['separation_s'] * fps)
    travel = math.ceil(config['restart_flight_s'] * fps)
    refractory = math.ceil(config['release_merge_s'] * fps)
    restarts, visible_stoppages = {}, []
    last_launch = -refractory - 1
    for launch in np.flatnonzero(speed >= config['release_speed_m_s']):
        launch = int(launch)
        if launch - last_launch <= refractory or launch + separate >= n:
            continue
        previous = speed[max(0, launch - rise):launch]
        finite = previous[np.isfinite(previous)]
        after_gap = launch > 0 and not known[launch - 1]
        from_slow = (len(finite) and finite.min() <= config['slow_speed_m_s']
                     and speed[launch] - finite.min() >= config['release_gain_m_s'])
        if not (after_gap or from_slow):
            continue
        if not known[launch:launch + separate + 1].all():
            continue
        # A restored observation can already be several samples into the release.
        reach = config['control_radius_m']
        if after_gap:
            reach += speed[launch] * config['gap_release_grace_s']
        candidates = np.flatnonzero(
            (distance[launch] <= reach)
            & (distance[launch + separate] - distance[launch]
               >= config['separation_m']))
        if not len(candidates):
            continue
        order = candidates[np.argsort(distance[launch, candidates])]
        actor = order[0]
        opponents = order[teams[order] != teams[actor]]
        if (len(opponents) and distance[launch, opponents[0]] - distance[launch, actor]
                < config['actor_margin_m']):
            continue
        team = str(teams[actor])
        restart = launch
        if outside[launch]:
            # Throw-ins become live on entry, not on the release outside the pitch.
            entry = launch
            while entry < min(n, launch + travel) and known[entry] and outside[entry]:
                entry += 1
            if entry >= min(n, launch + travel) or not known[entry]:
                continue
            restart = entry
        support = [t for t in relevant_tags
                   if t['start_frame'] - margin <= restart < t['end_frame'] + margin]
        matching = [t for t in support if t['team'] in (None, team)]
        # A tag cannot supply a release or override an observed release actor.
        record = {'frame': int(restart), 'launch': launch, 'team': team,
                  'slot': slots[actor], 'tag_supported': bool(matching),
                  'tag_conflict': bool(support and not matching),
                  'after_gap': bool(after_gap)}
        restarts[restart] = record
        last_launch = launch
        if matching and launch > 0 and slow_start[launch - 1] >= 0:
            start = int(slow_start[launch - 1])
            if ((launch - start) / fps >= config['tagged_slow_s']
                    and not outside[start:launch].any()):
                # Preserve an ordinary-hold allowance before assigning a visible pause.
                onset = start + math.ceil(config['visible_grace_s'] * fps)
                forced_dead[onset:restart] = True
                visible_stoppages.append({'start': onset, 'slow_start': start, 'stop': int(restart),
                                          'team': team})

    state, labels = 'D', []
    for frame in range(n):
        if forced_dead[frame]:
            state = 'D'
        elif state == 'D' and frame in restarts:
            state = restarts[frame]['team']
        elif state != 'D' and known[frame] and len(evidence.get(frame, ())) == 1:
            state = next(iter(evidence[frame]))
        labels.append(state)
    return labels, {'restarts': list(restarts.values()),
                    'visible_stoppages': visible_stoppages, 'long_gaps': gaps}


def predict(observations, metadata, config, tags=None):
    """Return one H/A/D per frame; absent tags select the strict coordinate branch."""
    return infer(observations, metadata, config, tags)[0]
