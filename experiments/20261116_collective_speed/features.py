"""Feature definitions and data loaders for the collective-speed study.

The analysis is deliberately read-only: this module reads generated external
observation/truth files, the raw Metrica event files needed for alignment, and the
tactical ATD through ``observations.atd``. It never imports or edits an algorithm, the
simulator, the converter, or a completed experiment.

Fixed feature definitions (chosen before looking at the distributions):

* ``F1``: median speed (m/s) over slots with a finite speed at the current frame.
* ``F2``: fraction of those slots whose speed is strictly greater than 2 m/s.
* ``F3``: ``F1(t) - F1(t - 25)``, i.e. the change over the past 1 s.

``F1`` and ``F2`` use a trailing 1 s moving average (25 frames, at least one sample).
A frame with fewer than ``MIN_PLAYERS`` finite speeds is ineligible and stays NaN after
smoothing, so a tracking gap is not filled from earlier frames. ``F3`` is the difference
of the already-smoothed ``F1`` and is not smoothed again. Goalkeepers cannot be
identified from the anonymised slots and are included. External speeds come from
position differences in the generated observations; the tactical ATD uses its original
speed columns, so its short-term noise/smoothing differs from the external sets.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
SIMULATION_SETS = os.path.join(REPO_ROOT, "outputs", "simulation_sets")
OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "20261116_collective_speed")
FPS = 25
WINDOW = FPS
MIN_PLAYERS = 5
SPEED_COLUMNS = [str(slot) + "_s" for slot in range(1, 47)]


def dataset_dir(dataset_id):
    return os.path.join(SIMULATION_SETS, dataset_id)


def frame_features(observations, min_players=MIN_PLAYERS):
    """Return a DataFrame with frame, n_speed, F1, F2, F3 for one clip."""
    speeds = observations[SPEED_COLUMNS].to_numpy(dtype=float)
    finite = np.isfinite(speeds)
    count = finite.sum(axis=1)
    with np.errstate(all="ignore"):
        f1_raw = np.nanmedian(speeds, axis=1)
    numerator = (speeds > 2.0).sum(axis=1)
    f2_raw = np.divide(
        numerator, count,
        out=np.full(len(observations), np.nan, dtype=float),
        where=count > 0,
    )
    eligible = count >= min_players
    # pandas 3's to_numpy() is read-only; copy before writing NaNs below.
    f1 = pd.Series(f1_raw).rolling(WINDOW, min_periods=1).mean().to_numpy().copy()
    f2 = pd.Series(f2_raw).rolling(WINDOW, min_periods=1).mean().to_numpy().copy()
    f1[~eligible] = np.nan
    f2[~eligible] = np.nan
    f3 = pd.Series(f1).diff(WINDOW).to_numpy()
    return pd.DataFrame({
        "frame": observations["frame"].to_numpy(dtype=int),
        "n_speed": count,
        "F1": f1,
        "F2": f2,
        "F3": f3,
    })


def ball_missing_runs(observations, min_frames=126):
    """Half-open runs of missing ball coordinates longer than 5 s (125 frames)."""
    missing = observations[["ball_x", "ball_y"]].isna().any(axis=1).to_numpy()
    edges = np.diff(np.r_[False, missing, False].astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    return [(int(a), int(b)) for a, b in zip(starts, stops) if b - a > min_frames]


def load_external(dataset_id):
    """Load one external dataset, returning clip records with frames and truth labels."""
    directory = dataset_dir(dataset_id)
    observations = pd.read_csv(os.path.join(directory, "observations.csv"),
                               dtype={"clip": str})
    truth = pd.read_csv(os.path.join(directory, "truth.csv"), dtype={"clip": str})
    with open(os.path.join(directory, "metadata.json")) as handle:
        metadata = json.load(handle)
    clips = []
    for clip_id in sorted(observations["clip"].unique()):
        frame_table = observations[observations["clip"] == clip_id].sort_values("frame")
        frame_table = frame_table.reset_index(drop=True)
        labels = truth[truth["clip"] == clip_id].sort_values("frame")["label"].to_numpy()
        if len(labels) != len(frame_table):
            raise ValueError("{} {}: truth/frame length mismatch".format(dataset_id, clip_id))
        clips.append({
            "dataset": dataset_id,
            "clip": clip_id,
            "observations": frame_table,
            "labels": labels,
            "features": frame_features(frame_table),
            "pitch_length": float(metadata[clip_id]["pitch_length"]),
            "pitch_width": float(metadata[clip_id]["pitch_width"]),
        })
    return clips


def metrica_game_dir(game_key):
    number = game_key.rsplit("_", 1)[-1]
    return os.path.join(REPO_ROOT, "data", "external", "metrica", "Sample_Game_" + number)


def read_metrica_events(game_key):
    """Read raw Metrica events with period, frame, type and subtype."""
    base = metrica_game_dir(game_key)
    events = []
    csv_path = os.path.join(base, "Sample_Game_{}_RawEventsData.csv".format(
        game_key.rsplit("_", 1)[-1]))
    json_path = os.path.join(base, "Sample_Game_{}_events.json".format(
        game_key.rsplit("_", 1)[-1]))
    if os.path.exists(csv_path):
        table = pd.read_csv(csv_path)
        for _, row in table.iterrows():
            end = int(row["End Frame"])
            start = int(row["Start Frame"])
            if end < start:
                end = start
            events.append({
                "period": int(row["Period"]),
                "start": start,
                "end": end,
                "type": str(row["Type"]).strip().upper(),
                "subtype": "" if pd.isna(row["Subtype"])
                else str(row["Subtype"]).strip().upper(),
            })
    elif os.path.exists(json_path):
        with open(json_path) as handle:
            payload = json.load(handle)
        for row in payload.get("data", []):
            subtypes = row.get("subtypes")
            if isinstance(subtypes, list):
                subtype = "|".join(str(item.get("name", "")) for item in subtypes)
            elif isinstance(subtypes, dict):
                subtype = str(subtypes.get("name", ""))
            else:
                subtype = ""
            start = int(row["start"]["frame"])
            end = int(row["end"]["frame"])
            if end < start:
                end = start
            events.append({
                "period": int(row["period"]),
                "start": start,
                "end": end,
                "type": str(row["type"]["name"]).strip().upper(),
                "subtype": subtype.strip().upper(),
            })
    else:
        raise SystemExit("no Metrica event file under {}".format(base))
    return events


def period_offsets(clips):
    """Map period 1/2 to clip-relative event offsets for the Metrica half clips."""
    ordered = sorted(clips, key=lambda item: (item["clip"] != "first_half", item["clip"]))
    # Metrica raw frame ids start at 1; clip frame 0 is raw frame 1.
    offsets = {1: 1}
    if len(ordered) > 1:
        offsets[2] = 1 + len(ordered[0]["observations"])
    return offsets, ordered


def ball_speed(observations, pitch_length, pitch_width):
    """Trailing 1 s mean of ball speed; NaN on frames without both ball coordinates."""
    ball = observations[["ball_x", "ball_y"]].to_numpy(dtype=float)
    known = np.isfinite(ball).all(axis=1)
    speed = np.full(len(observations), np.nan, dtype=float)
    distance = np.hypot(np.diff(ball[:, 0]) * pitch_length,
                        np.diff(ball[:, 1]) * pitch_width) * FPS
    speed[1:] = distance
    raw = speed.copy()
    # Same read-only issue as frame_features: copy before masking.
    speed = pd.Series(speed).rolling(WINDOW, min_periods=1).mean().to_numpy().copy()
    speed[~known | ~np.isfinite(raw)] = np.nan
    return speed


def load_atd():
    """Load tactical ATD through the project loader; no labels or answers are read."""
    from observations.atd import load_tactical
    observations, metadata = load_tactical()
    features = frame_features(observations)
    return observations, features, metadata


def atd_cache_path():
    return os.path.join(OUTPUT_DIR, "atd_features.npz")


def save_atd_cache(observations, features):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    missing = observations[["ball_x", "ball_y"]].isna().any(axis=1).to_numpy()
    np.savez_compressed(
        atd_cache_path(),
        F1=features["F1"].to_numpy(),
        F2=features["F2"].to_numpy(),
        F3=features["F3"].to_numpy(),
        n_speed=features["n_speed"].to_numpy(),
        ball_missing=missing,
    )


def load_atd_cache():
    data = np.load(atd_cache_path())
    return {key: data[key] for key in data.files}
