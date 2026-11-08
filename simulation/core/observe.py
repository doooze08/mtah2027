"""Project the complete simulated world onto the shared tactical ATD contract.

This version adds no observation defects. It removes height, identities and referee signals.
"""

import hashlib

import numpy as np
import pandas as pd

from observations.schema import COLUMNS, SLOTS, validate
from simulation.core.constants import FPS, PITCH_LENGTH, PITCH_WIDTH


def observe(clip_id, clip, seed=0):
    """Return (frame table, metadata); random track slots remain fixed inside this clip."""
    entropy = int.from_bytes(hashlib.sha256(clip_id.encode("utf-8")).digest()[:8], "big")
    rng = np.random.default_rng(np.random.SeedSequence([seed, entropy]))
    assigned = rng.choice(SLOTS, size=22, replace=False)
    mapping = dict(zip(["p{:02d}".format(i) for i in range(1, 23)], assigned))
    frames = clip.frames
    observations = pd.DataFrame(np.nan, index=range(clip.n_frames), columns=COLUMNS[1:])
    observations.insert(0, "frame", np.arange(clip.n_frames, dtype=np.int64))
    ball = frames[frames["object"] == "ball"].set_index("frame").reindex(range(clip.n_frames))
    observations["ball_x"] = ball["x"] / PITCH_LENGTH
    observations["ball_y"] = ball["y"] / PITCH_WIDTH
    slot_teams = {slot: None for slot in SLOTS}
    for obj, slot in mapping.items():
        track = frames[frames["object"] == obj].set_index("frame").reindex(range(clip.n_frames))
        teams = track["team"].unique()
        if len(teams) != 1 or teams[0] not in ("H", "A"):
            raise ValueError("Clean simulated player must have one fixed H/A team")
        slot_teams[slot] = teams[0]
        observations[slot + "_x"] = track["x"] / PITCH_LENGTH
        observations[slot + "_y"] = track["y"] / PITCH_WIDTH
        # Backward difference in metres at 25 Hz; first frame uses the forward difference.
        distance = np.hypot(track["x"].diff(), track["y"].diff()) * FPS
        distance.iloc[0] = distance.iloc[1] if clip.n_frames > 1 else 0.0
        observations[slot + "_s"] = distance
    metadata = {"slot_teams": slot_teams, "pitch_length": PITCH_LENGTH,
                "pitch_width": PITCH_WIDTH, "fps": FPS}
    validate(observations, metadata)
    return observations, metadata
