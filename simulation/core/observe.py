"""Observation layer: turns a clean clip into what an algorithm is allowed to see.

V1 passes positions through unchanged. It still exists as its own step so that later versions can
add tracking defects here (position noise, missing ball, swapped player ids, ...) without touching
the scripts, the truth or the scoring, and so a clean and a degraded version of the same clip can
be compared directly.

Only positions and the referee signal leave this function. The truth, the events, the contacts
and the scenario name never do.
"""

import pandas as pd

from simulation.core.clip import Clip
from simulation.core.constants import GAME_STATE_COLUMNS, OBSERVATION_COLUMNS


def observe(clip_id: str, clip: Clip, config=None):
    """Return (observations, game_state) DataFrames for one clip.

    config is reserved for future defect settings; V1 ignores it.
    """
    observations = clip.frames.copy()
    observations.insert(0, "clip", clip_id)
    observations = observations[OBSERVATION_COLUMNS]

    game_state = pd.DataFrame({
        "clip": clip_id,
        "frame": range(clip.n_frames),
        "play_live": clip.play_live,
        "restart_team": clip.restart_team,
    })[GAME_STATE_COLUMNS]
    return observations, game_state
