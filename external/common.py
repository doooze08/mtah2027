"""Shared conversion helpers: slots, coordinates, speed, upsampling and the dataset writer.

The output contract is the one in ``simulation/README.md`` and ``docs/OBSERVATIONS.md``:
one clip per half, 25 fps, contiguous zero-based frames, 142 observation columns
(``clip`` plus the 141-column ATD contract), pitch-normalised coordinates, NaN for
missing values and speeds from position differences.

Coordinate convention: the real tactical ATD is a Metrica EPTS export loaded through
kloppy (``observations/atd.py``). It uses kloppy's normalised system with origin at the
top-left and y increasing towards the bottom. Metrica files are kept in their native
0-1 coordinates; SkillCorner centre-origin metres are mapped to the same top-left
system. No conversion flips ends by attacking direction: the pitch frame is fixed for
the whole match, so the two teams swap halves at half time exactly as they do in ATD.
"""

import json
import math
import os
import shutil
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from observations.schema import COLUMNS, validate as validate_observations
from simulation.core import io as simulation_io
from simulation.core.constants import EVENT_COLUMNS, SAMPLE_COLUMNS, TRUTH_COLUMNS

FPS = 25
FACTOR_10_TO_25 = 2.5

SLOTS = tuple(str(i) for i in range(1, 47))
HOME_SLOTS = SLOTS[:24]
AWAY_SLOTS = SLOTS[24:]
LABELS = ("H", "A", "D", "X")

REPO_ROOT = simulation_io.REPO_ROOT
SIMULATION_SETS = simulation_io.SIMULATION_SETS


@dataclass
class Event:
    """One vendor event in clip-relative 25 fps frames.

    ``end`` is inclusive. ``team`` is ``H``, ``A`` or an empty string when the vendor
    does not name a side. Only the fields used to derive labels are kept.
    """

    index: int
    event_type: str
    subtype: str
    start: int
    end: int
    team: str = ""
    period: int = 0

    @property
    def name(self):
        return " ".join(part for part in (self.event_type, self.subtype) if part).strip()


@dataclass
class Clip:
    """One half, already in the shared observation contract plus its weak labels."""

    clip_id: str
    observations: pd.DataFrame
    truth: np.ndarray
    events: list
    sample: dict
    metadata: dict
    diagnostics: dict = field(default_factory=dict)


def slot_teams():
    """All 46 slots have a team, 24 H and 22 A, matching the real ATD XML shape."""
    return {slot: ("H" if int(slot) <= 24 else "A") for slot in SLOTS}


def assign_slots(players):
    """Map stable vendor player keys to one fixed slot per team.

    ``players`` is an iterable of ``{"key": str, "team": "H"|"A", "number": int|None}``.
    Players are ordered by shirt number and then key, which keeps the mapping stable
    across both halves of a match. Home uses slots 1-24 and away 25-46; unused slots
    stay without a player and therefore stay NaN in observations.
    """
    grouped = {"H": [], "A": []}
    seen = set()
    for player in players:
        key = str(player["key"])
        team = player["team"]
        if team not in grouped:
            raise ValueError("unknown team {!r} for player {}".format(team, key))
        if key in seen:
            raise ValueError("duplicate player key {!r}".format(key))
        seen.add(key)
        grouped[team].append(player)

    mapping = {}
    for team, slots in (("H", HOME_SLOTS), ("A", AWAY_SLOTS)):
        ordered = sorted(
            grouped[team],
            key=lambda p: (
                p["number"] is None,
                p["number"] if p["number"] is not None else 0,
                p["key"],
            ),
        )
        if len(ordered) > len(slots):
            raise ValueError("{} players on team {} but only {} slots".format(
                len(ordered), team, len(slots)))
        for slot, player in zip(slots, ordered):
            mapping[player["key"]] = slot
    return mapping


def speed_from_positions(x, y, pitch_length, pitch_width, fps=FPS):
    """Speed in m/s from adjacent observed positions, or NaN when either is missing.

    This is the simulator formula from ``docs/OBSERVATIONS.md``:
    ``s[f] = fps * hypot(dx * length, dy * width)``. Frame 0 uses the forward
    difference (frames 0-1); a single-frame clip has no speed and stays NaN.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) != len(y):
        raise ValueError("x and y lengths differ")
    n = len(x)
    result = np.full(n, np.nan, dtype=float)
    if n > 1:
        distance = np.hypot(np.diff(x) * pitch_length, np.diff(y) * pitch_width) * fps
        result[1:] = distance
        result[0] = result[1]
    return result


def observations_frame(ball, players, pitch_length, pitch_width, fps=FPS):
    """Build the 141 contract columns from normalised positions.

    ``ball`` is an ``(n, 2)`` array of normalised x/y. ``players`` maps a slot string to
    an ``(n, 2)`` array. Missing positions are NaN and are never filled; out-of-pitch
    values are kept. Each player slot gets its own speed column.
    """
    ball = np.asarray(ball, dtype=float)
    n = len(ball)
    table = pd.DataFrame(np.nan, index=range(n), columns=COLUMNS[1:])
    table.insert(0, "frame", np.arange(n, dtype=np.int64))
    table["ball_x"] = ball[:, 0]
    table["ball_y"] = ball[:, 1]
    for slot, xy in players.items():
        xy = np.asarray(xy, dtype=float)
        if len(xy) != n:
            raise ValueError("slot {} has {} frames, expected {}".format(slot, len(xy), n))
        table[slot + "_x"] = xy[:, 0]
        table[slot + "_y"] = xy[:, 1]
        table[slot + "_s"] = speed_from_positions(
            xy[:, 0], xy[:, 1], pitch_length, pitch_width, fps)
    validate_observations(table)
    return table


def resample_indices(n, factor=FACTOR_10_TO_25):
    """Indices and fractions for 10 -> 25 fps resampling of ``n`` original frames."""
    if n <= 0:
        empty = np.array([], dtype=int)
        return empty, empty, np.array([], dtype=float), empty
    if n == 1:
        return np.zeros(1, dtype=int), np.zeros(1, dtype=int), np.zeros(1), np.zeros(1, dtype=int)
    n_out = int(math.floor(factor * (n - 1) + 1e-9)) + 1
    u = np.arange(n_out, dtype=float) / factor
    low = np.floor(u).astype(int)
    high = np.minimum(low + 1, n - 1)
    frac = u - low
    nearest = np.floor(u + 0.5).astype(int)
    return low, high, frac, nearest


def upsample_factor(values, factor=FACTOR_10_TO_25):
    """Linear 10 -> 25 fps resampling that never bridges a missing endpoint.

    Returns ``(resampled, nearest)``. ``resampled[f]`` is the linear interpolation
    between the two surrounding original frames when both are finite; otherwise it is
    NaN. ``nearest[f]`` is the nearest original frame index, used for label mapping.
    The output covers ``u = f / factor`` from 0 up to the largest value not past the
    last original frame. Whole-frame tracking gaps therefore stay NaN.
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return np.array([], dtype=float), np.array([], dtype=int)
    low, high, frac, nearest = resample_indices(n, factor)
    result = values[low] * (1.0 - frac) + values[high] * frac
    missing = ~(np.isfinite(values[low]) & np.isfinite(values[high]))
    result[missing] = np.nan
    return result, nearest


def upsample_positions(positions, factor=FACTOR_10_TO_25):
    """Upsample ``(n, 2)`` positions, treating a half-missing pair as missing."""
    positions = np.asarray(positions, dtype=float)
    valid = np.isfinite(positions).all(axis=1)
    cleaned = positions.copy()
    cleaned[~valid] = np.nan
    x, nearest = upsample_factor(cleaned[:, 0], factor)
    y, _ = upsample_factor(cleaned[:, 1], factor)
    return np.column_stack([x, y]), nearest


def normalise_to_top_left(x, y, pitch_length, pitch_width):
    """Map SkillCorner centre-origin metres to kloppy's top-left 0-1 coordinates.

    SkillCorner stores x to the right and y from bottom to top with the origin at the
    pitch centre. Kloppy's normalised system (also used by the real ATD loader) has
    the origin at the top-left and y increasing downwards.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    return (x + pitch_length / 2.0) / pitch_length, (pitch_width / 2.0 - y) / pitch_width


def dataset_dir(dataset_id):
    return simulation_io.dataset_dir(dataset_id)


def _safe_remove(directory):
    resolved = os.path.realpath(directory)
    root = os.path.realpath(SIMULATION_SETS)
    if os.path.islink(directory):
        raise SystemExit("refusing to replace symlink {}".format(directory))
    if not resolved.startswith(root + os.sep):
        raise SystemExit("refusing to remove {} outside {}".format(resolved, root))
    if not os.path.basename(resolved).startswith("ext_"):
        raise SystemExit("refusing to remove non-external dataset {}".format(resolved))
    shutil.rmtree(resolved)


def write_dataset(dataset_id, clips, force=False):
    """Write the five format-compatible files; returns the dataset directory.

    No ``debug/clean_positions.csv`` is written because external data has no clean
    ground-truth trajectories, and no manifest because the task contract is the five
    files read by the existing runner and scorer.
    """
    if not clips:
        raise ValueError("no clips to write")
    directory = dataset_dir(dataset_id)
    if os.path.exists(directory):
        if not force:
            raise SystemExit("{} exists; pass --force to replace it".format(directory))
        _safe_remove(directory)
    os.makedirs(directory)

    observation_tables, truth_rows, event_rows, sample_rows = [], [], [], []
    metadata = {}
    for clip in clips:
        if list(clip.observations.columns) != COLUMNS:
            raise ValueError("{}: observations do not have the 141 contract columns".format(
                clip.clip_id))
        validate_observations(clip.observations)
        if len(clip.truth) != len(clip.observations):
            raise ValueError("{}: truth length differs from observations".format(clip.clip_id))
        if not set(clip.truth) <= set(LABELS):
            raise ValueError("{}: unknown labels".format(clip.clip_id))
        observation_tables.append(clip.observations.assign(clip=clip.clip_id)[["clip"] + COLUMNS])
        truth_rows.append(pd.DataFrame({
            "clip": clip.clip_id,
            "frame": np.arange(len(clip.truth), dtype=np.int64),
            "label": clip.truth,
        }))
        event_rows.extend(clip.events)
        sample_rows.append(clip.sample)
        metadata[clip.clip_id] = clip.metadata

    observations = pd.concat(observation_tables, ignore_index=True)
    truth = pd.concat(truth_rows, ignore_index=True)
    events = pd.DataFrame(event_rows, columns=EVENT_COLUMNS)
    samples = pd.DataFrame(sample_rows, columns=SAMPLE_COLUMNS)
    observations.to_csv(os.path.join(directory, "observations.csv"), index=False,
                        float_format="%.10g")
    truth.to_csv(os.path.join(directory, "truth.csv"), index=False)
    events.to_csv(os.path.join(directory, "events.csv"), index=False)
    samples.to_csv(os.path.join(directory, "samples.csv"), index=False)
    with open(os.path.join(directory, "metadata.json"), "w") as handle:
        json.dump(metadata, handle, indent=2, allow_nan=False)
    return directory


def _finite_player_counts(observations, slot_teams_map):
    counts = {}
    for team in ("H", "A"):
        columns = []
        for slot, slot_team in slot_teams_map.items():
            if slot_team != team:
                continue
            columns.extend([slot + "_x", slot + "_y"])
        if not columns:
            counts[team] = np.zeros(len(observations), dtype=int)
            continue
        present = observations[columns].notna().to_numpy()
        counts[team] = present.reshape(len(observations), -1, 2).all(axis=2).sum(axis=1)
    return counts


def dataset_diagnostics(clips):
    """Per-dataset summaries used in the experiment notes and the converter output."""
    total_frames = 0
    ball_missing = 0
    label_counts = {label: 0 for label in LABELS}
    speed_values = []
    max_players = {"H": 0, "A": 0}
    frames_over_11 = {"H": 0, "A": 0}
    out_of_pitch = 0
    no_player_frames = 0
    per_clip = []
    for clip in clips:
        obs = clip.observations
        teams = clip.metadata["slot_teams"]
        counts = _finite_player_counts(obs, teams)
        n = len(obs)
        total_frames += n
        ball_null = obs[["ball_x", "ball_y"]].isna().any(axis=1).to_numpy()
        ball_missing += int(ball_null.sum())
        for label in LABELS:
            label_counts[label] += int((clip.truth == label).sum())
        speed_columns = [slot + "_s" for slot in SLOTS]
        speed_values.append(obs[speed_columns].to_numpy(dtype=float).ravel())
        player_columns = [slot + field for slot in SLOTS for field in ("_x", "_y")]
        no_player_frames += int(obs[player_columns].isna().all(axis=1).sum())
        for team in ("H", "A"):
            max_players[team] = max(max_players[team], int(counts[team].max()))
            frames_over_11[team] += int((counts[team] > 11).sum())
        coord_columns = [slot + field for slot in SLOTS for field in ("_x", "_y")]
        out_of_pitch += int(((obs[coord_columns] < 0) | (obs[coord_columns] > 1)).to_numpy().sum())
        mean_x = {}
        for team in ("H", "A"):
            columns = [slot + "_x" for slot in SLOTS if teams[slot] == team]
            values = obs[columns].to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            mean_x[team] = float(finite.mean()) if finite.size else float("nan")
        per_clip.append({
            "clip": clip.clip_id,
            "n_frames": n,
            "ball_missing": int(ball_null.sum()),
            "mean_x_H": mean_x["H"],
            "mean_x_A": mean_x["A"],
            "max_players_H": int(counts["H"].max()),
            "max_players_A": int(counts["A"].max()),
            "extrapolated_share": clip.diagnostics.get("extrapolated_share"),
            "labels": {label: int((clip.truth == label).sum()) for label in LABELS},
        })
    speeds = np.concatenate(speed_values) if speed_values else np.array([])
    finite_speeds = speeds[np.isfinite(speeds)]
    label_share = {label: (count / total_frames if total_frames else 0.0)
                   for label, count in label_counts.items()}
    return {
        "n_clips": len(clips),
        "n_frames": total_frames,
        "ball_missing": ball_missing,
        "ball_missing_share": ball_missing / total_frames if total_frames else 0.0,
        "labels": label_counts,
        "label_share": label_share,
        "speed_p99": float(np.percentile(finite_speeds, 99)) if finite_speeds.size else None,
        "speed_max": float(finite_speeds.max()) if finite_speeds.size else None,
        "speed_over_10": int((finite_speeds > 10.0).sum()),
        "max_players": max_players,
        "frames_over_11": frames_over_11,
        "out_of_pitch_x": out_of_pitch,
        "no_player_frames": no_player_frames,
        "clips": per_clip,
    }


def print_diagnostics(dataset_id, diagnostics):
    """One compact line per dataset, plus per-clip direction checks."""
    print("{}".format(dataset_id))
    print("  frames={n_frames}  ball_missing={ball_missing} ({ball_missing_share:.2%})  "
          "speed_p99={speed_p99}  speed_max={speed_max}  over10={speed_over_10}".format(
              **diagnostics))
    print("  labels={}  shares={}".format(
        diagnostics["labels"],
        {"H": round(diagnostics["label_share"]["H"], 4),
         "A": round(diagnostics["label_share"]["A"], 4),
         "D": round(diagnostics["label_share"]["D"], 4),
         "X": round(diagnostics["label_share"]["X"], 4)}))
    print("  max players H/A={}  frames>11 H/A={}  no-player frames={}  "
          "x out of 0-1={}".format(diagnostics["max_players"],
                                   diagnostics["frames_over_11"],
                                   diagnostics["no_player_frames"],
                                   diagnostics["out_of_pitch_x"]))
    for clip in diagnostics["clips"]:
        print("  {}  n={}  ball_missing={}  mean_x H/A={:.4f}/{:.4f}  "
              "max players H/A={}/{}  extrapolated={}".format(
                  clip["clip"], clip["n_frames"], clip["ball_missing"],
                  clip["mean_x_H"], clip["mean_x_A"],
                  clip["max_players_H"], clip["max_players_A"],
                  clip["extrapolated_share"]))
