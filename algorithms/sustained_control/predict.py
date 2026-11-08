"""Offline possession state machine; reads only the shared observation arguments."""

import math

import numpy as np


def _runs(mask):
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False]))
    return zip(edges[::2], edges[1::2])


def predict(observations, metadata, config):
    """Confirm control over time, then backdate switches to the first control sample."""
    fps = metadata["fps"]
    scale = np.array([metadata["pitch_length"], metadata["pitch_width"]])
    ball = observations[["ball_x", "ball_y"]].to_numpy(dtype=float) * scale
    n = len(ball)
    if not n:
        return []
    slots = list(metadata["slot_teams"])
    players = np.stack([observations[[s + "_x", s + "_y"]].to_numpy(dtype=float)
                        for s in slots], axis=1) * scale
    teams = np.array([metadata["slot_teams"][s] for s in slots])
    radius = config.get("ball_radius_m", 0.11)
    near = config.get("control_radius_m", 1.3)
    relative_limit = config.get("relative_speed_m_s", 3.0)
    confirm = max(2, math.ceil(config.get("confirm_s", 0.32) * fps))
    known = np.isfinite(ball).all(axis=1)
    outside = known & ((ball < -radius) | (ball > scale + radius)).any(axis=1)
    offset = ball[:, None, :] - players
    distance = np.linalg.norm(offset, axis=2)
    relative_speed = np.linalg.norm(np.diff(offset, axis=0), axis=2) * fps
    # Each interval must match, rather than just the net start/end displacement.
    stable = (distance <= near) & ~outside[:, None]
    stable[:-1] &= relative_speed <= relative_limit
    stable[-1] = False
    velocity = np.diff(ball, axis=0) * fps
    confirmed = np.zeros_like(stable)
    for player in range(len(slots)):
        for start, stop in _runs(stable[:, player]):
            if stop - start >= confirm:
                confirmed[start:stop - confirm + 1, player] = True
    evidence = {}
    for player in range(len(slots)):
        for start, stop in _runs(stable[:, player]):
            if stop - start < confirm:
                continue
            if np.any(confirmed[start, teams != teams[player]]):
                continue  # Simultaneous control-like proximity from both teams is a contest.
            if start == 0:
                continue  # The initial waiting ball does not establish live possession.
            onset = start
            # A mixed flight/control interval can pass the velocity gate one sample early.
            # Locate the first departure from the preceding straight incoming trajectory.
            if 1 <= start < n - 2:
                before = velocity[max(0, start - 3)]
                if np.linalg.norm(before) > relative_limit:
                    for k in range(max(1, start - 2), min(n - 1, start + 3)):
                        if (np.linalg.norm(velocity[k] - before) > 0.1
                                and distance[k + 1, player] <= near):
                            onset = k if distance[k, player] < 0.02 else k + 1
                            break
            evidence.setdefault(onset, set()).add(teams[player])
    restarts = {}
    if config.get("infer_restarts", True):
        # Offline confirmation permits a restart to precede the eventual reception.
        speed = np.linalg.norm(velocity, axis=1)
        lookback = math.ceil(config.get("restart_lookback_s", 5.0) * fps)
        for onset, candidates in sorted(evidence.items()):
            if len(candidates) != 1:
                continue
            team = next(iter(candidates))
            k = onset - 1
            if k >= 1 and speed[k] <= relative_limit:
                k -= 1
            if k < 0 or not speed[k] > relative_limit:
                continue
            while k > max(0, onset - lookback) and speed[k - 1] > relative_limit:
                k -= 1
            launch = k
            # Require an observed same-team player at the launch; never label by nearest alone.
            if not np.any((teams == team) & (distance[launch] <= near)):
                continue
            segment = np.arange(launch, onset + 1)
            if not known[segment].all():
                continue
            exits = segment[outside[segment]]
            restart = int(exits[-1] + 1) if len(exits) else launch
            restarts.setdefault(restart, set()).add(team)
    state = "D"
    labels = []
    for frame in range(n):
        if outside[frame]:
            state = "D"
        elif state == "D" and known[frame] and len(restarts.get(frame, ())) == 1:
            state = next(iter(restarts[frame]))
        elif known[frame] and frame in evidence and len(evidence[frame]) == 1:
            state = next(iter(evidence[frame]))
        labels.append(state)
    return labels
