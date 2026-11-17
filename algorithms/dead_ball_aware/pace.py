"""Collective player pace used only to veto or confirm an existing dead-ball decision.

F1 is the median speed of the slots with a finite speed, averaged backwards over one
second.  Speeds are always recomputed from adjacent positions; the ``_s`` columns are
deliberately ignored so that the fixed threshold is applied to the same quantity on
simulation, external tracking and the tactical ATD.  A frame with fewer than five
finite player speeds is ``NaN``: there is not enough evidence to veto or confirm.
"""

import math

import numpy as np
import pandas as pd

PLAYER_PACE_THRESHOLD_M_S = 1.39
MIN_PLAYERS = 5
WINDOW = 25


def player_pace(observations, metadata):
    """Return the 1 s trailing F1 for every frame, with insufficient frames as NaN."""
    slots = list(metadata["slot_teams"])
    n = len(observations)
    if not n:
        return np.full(0, np.nan, dtype=float)
    scale = np.array([float(metadata["pitch_length"]), float(metadata["pitch_width"])])
    fps = float(metadata["fps"])
    players = np.stack([
        observations[[slot + "_x", slot + "_y"]].to_numpy(dtype=float)
        for slot in slots
    ], axis=1)

    speeds = np.full((n, len(slots)), np.nan, dtype=float)
    if n > 1:
        delta = np.diff(players, axis=0) * scale
        speeds[1:] = np.hypot(delta[:, :, 0], delta[:, :, 1]) * fps
        # Match the simulator and the external converter: frame 0 uses the first
        # forward difference, not a zero or a backward edge.
        speeds[0] = speeds[1]
    finite = np.isfinite(speeds)
    count = finite.sum(axis=1)
    raw = np.full(n, np.nan, dtype=float)
    has_speed = count > 0
    if has_speed.any():
        raw[has_speed] = np.nanmedian(speeds[has_speed], axis=1)
    smooth = pd.Series(raw).rolling(WINDOW, min_periods=1).mean().to_numpy().copy()
    smooth[count < MIN_PLAYERS] = np.nan
    return smooth


def restart_player_rise(pace, launch, fps, window_s, delta_m_s):
    """Whether a restart action is followed by enough player movement.

    ``True`` also means "not enough pace data", so the caller keeps the original
    restart.  A finite value above the fixed threshold, or a finite value at least
    ``delta_m_s`` above the frame before the action, confirms the restart.
    """
    n = len(pace)
    if not n:
        return True
    first = max(0, int(launch))
    stop = min(n, first + int(math.ceil(window_s * fps)) + 1)
    window = pace[first:stop]
    finite = window[np.isfinite(window)]
    if not len(finite):
        return True
    if (finite > PLAYER_PACE_THRESHOLD_M_S).any():
        return True
    before = pace[first - 1] if first > 0 else np.nan
    if not np.isfinite(before):
        # The pre-action frame is data-insufficient: we cannot evaluate the rise.
        # Keep the original restart instead of rejecting it.
        return True
    return bool((finite >= before + delta_m_s).any())
