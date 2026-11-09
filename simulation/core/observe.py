"""Project the complete simulated world onto the shared tactical ATD contract.

It removes height, identities and referee signals. Ball-only gaps are opt-in.
"""

import numpy as np
import pandas as pd

from observations.schema import COLUMNS, SLOTS
from simulation.core.constants import FPS, PITCH_LENGTH, PITCH_WIDTH
from simulation.core.gaps import ball_gap_mask


def observe(clip, seed=0, gaps=None):
    """Return (frame table, metadata); the story seed fixes all track-slot assignments."""
    slots = np.random.default_rng(seed).permutation(SLOTS)
    # Tactical XML has 24 home slots and 22 away slots; each team fields 11 players.
    slot_teams = {slot: "H" if i < 24 else "A" for i, slot in enumerate(slots)}
    team_slots = {"H": iter(slots[:24]), "A": iter(slots[24:])}
    frames = clip.frames
    observations = pd.DataFrame(np.nan, index=range(clip.n_frames), columns=COLUMNS[1:])
    observations.insert(0, "frame", np.arange(clip.n_frames, dtype=np.int64))
    ball = frames[frames["object"] == "ball"].set_index("frame").reindex(range(clip.n_frames))
    observations["ball_x"] = ball["x"] / PITCH_LENGTH
    observations["ball_y"] = ball["y"] / PITCH_WIDTH
    if gaps is not None:
        missing, _ = ball_gap_mask(clip, seed, gaps)
        observations.loc[missing, ["ball_x", "ball_y"]] = np.nan
    for obj in ["p{:02d}".format(i) for i in range(1, 23)]:
        track = frames[frames["object"] == obj].set_index("frame").reindex(range(clip.n_frames))
        slot = next(team_slots[track["team"].iloc[0]])
        observations[slot + "_x"] = track["x"] / PITCH_LENGTH
        observations[slot + "_y"] = track["y"] / PITCH_WIDTH
        # Backward difference in metres at 25 Hz; first frame uses the forward difference.
        distance = np.hypot(track["x"].diff(), track["y"].diff()) * FPS
        distance.iloc[0] = distance.iloc[1] if clip.n_frames > 1 else 0.0
        observations[slot + "_s"] = distance
    metadata = {"slot_teams": slot_teams, "pitch_length": PITCH_LENGTH,
                "pitch_width": PITCH_WIDTH, "fps": FPS}
    return observations, metadata
