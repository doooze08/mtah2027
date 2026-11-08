"""One frame per row; pitch-normalized coordinates and player speed in m/s."""

import numpy as np
import pandas as pd

SLOTS = tuple(str(i) for i in range(1, 47))
COLUMNS = ["frame", "ball_x", "ball_y"] + [
    "{}_{}".format(slot, field) for slot in SLOTS for field in ("x", "y", "s")]
METADATA_KEYS = {"slot_teams", "pitch_length", "pitch_width", "fps"}


def validate(observations, metadata):
    """Reject schema drift without filling, clipping or reordering observations."""
    if list(observations.columns) != COLUMNS:
        raise ValueError("Expected exactly the 141 shared observation columns in order")
    if len(observations) == 0:
        raise ValueError("Observations must contain at least one frame")
    if not pd.api.types.is_integer_dtype(observations["frame"]):
        raise ValueError("frame must have integer dtype")
    if not np.array_equal(observations["frame"].to_numpy(), np.arange(len(observations))):
        raise ValueError("Frames must be ordered, unique and contiguous from 0")
    if set(metadata) != METADATA_KEYS or set(metadata["slot_teams"]) != set(SLOTS):
        raise ValueError("Metadata must contain only slot_teams, pitch_length, pitch_width, fps")
    if any(team not in ("H", "A", None) for team in metadata["slot_teams"].values()):
        raise ValueError("Slot teams must be H, A or null (unknown/unused)")
    if metadata["fps"] != 25:
        raise ValueError("Only 25 fps tactical observations are supported")
    for key in ("pitch_length", "pitch_width"):
        if not np.isfinite(metadata[key]) or metadata[key] <= 0:
            raise ValueError("{} must be a positive length in metres".format(key))
    numeric = observations[COLUMNS[1:]]
    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in numeric.dtypes):
        raise ValueError("Coordinates and speed must be numeric, with NaN for missing values")
    if np.isinf(numeric.to_numpy()).any():
        raise ValueError("Infinite observations are not supported; use NaN for missing values")
    speeds = observations[[slot + "_s" for slot in SLOTS]]
    if (speeds < 0).any().any():
        raise ValueError("Speed must be nonnegative in m/s or NaN")
    for slot, team in metadata["slot_teams"].items():
        fields = [slot + "_" + f for f in ("x", "y", "s")]
        if team is None and observations[fields].notna().any().any():
            raise ValueError("Observed slot {} has no team membership".format(slot))
