"""SkillCorner open data -> simulation dataset.

One clip per period. The tracking file is 10 fps; observations are resampled to 25 fps
by linear interpolation between the two surrounding original frames, but only when both
endpoints have a value for that object. A missing endpoint makes the whole interval NaN,
so no gap is bridged and the original broadcast/tracking gaps stay visible. Whole frames
without player tracking therefore remain all-NaN. Weak labels are mapped from the
nearest original frame.

Weak labels use ``phases_of_play.csv`` exactly as drafted in
``docs/research/EXTERNAL_DATA.md`` section 7.1:

* exactly one phase at the original frame -> that phase's team, unless the frame has no
  player tracking at all (then ``X``, because the live side cannot be confirmed);
* no phase -> ``D``; the vendor defines phases only while the ball is in play, so a
  frame outside every phase is a stoppage whether or not that frame also lacks
  tracking (the 21.8% of frames without players are mostly these dead-ball frames);
* more than one overlapping phase -> ``X``.

Extrapolated player positions (``is_detected`` false) are kept unchanged; their share is
reported in the experiment notes and in the per-dataset diagnostics. Ball height, player
identity and events never enter observations.

Run from the repository root::

    .venv/bin/python -m external.convert --source skillcorner --data-dir "$PWD/data"
"""

import json
import os

import numpy as np
import pandas as pd

from external.common import (
    Clip,
    FACTOR_10_TO_25,
    FPS,
    assign_slots,
    dataset_diagnostics,
    normalise_to_top_left,
    observations_frame,
    print_diagnostics,
    resample_indices,
    slot_teams,
    upsample_positions,
    write_dataset,
)

TRACKING_SUFFIX = "_tracking_extrapolated.jsonl"
PHASES_SUFFIX = "_phases_of_play.csv"
MATCH_SUFFIX = "_match.json"


# -- raw tracking -------------------------------------------------------------------------------

def _read_tracking(path, roster_keys):
    """Read one JSONL tracking file, keeping only period 1/2 frames.

    Returns per-period lists of global frames, ball positions, player positions and
    detection flags. Positions stay in the vendor centre-origin metres here.
    """
    periods = {}
    unknown = set()
    with open(path) as handle:
        for line in handle:
            row = json.loads(line)
            period = row.get("period")
            if period not in (1, 2):
                continue
            table = periods.setdefault(period, {
                "frames": [],
                "ball": [],
                "players": {key: [] for key in roster_keys},
                "detected": {key: [] for key in roster_keys},
                "n_players": [],
            })
            table["frames"].append(int(row["frame"]))
            ball = row.get("ball_data") or {}
            bx, by = ball.get("x"), ball.get("y")
            if bx is None or by is None:
                table["ball"].append([np.nan, np.nan])
            else:
                table["ball"].append([float(bx), float(by)])
            present = {}
            for entry in row.get("player_data") or []:
                key = str(entry.get("player_id"))
                if key not in present:
                    present[key] = None
                x, y = entry.get("x"), entry.get("y")
                if x is None or y is None:
                    continue
                if key not in table["players"]:
                    unknown.add(key)
                    continue
                present[key] = (float(x), float(y), bool(entry.get("is_detected", True)))
            table["n_players"].append(sum(1 for value in present.values() if value is not None))
            for key in roster_keys:
                value = present.get(key)
                if value is None:
                    table["players"][key].append([np.nan, np.nan])
                    table["detected"][key].append(False)
                else:
                    table["players"][key].append([value[0], value[1]])
                    table["detected"][key].append(value[2])
    if unknown:
        raise ValueError("tracking contains player ids absent from match.json: {}".format(
            sorted(unknown)[:5]))
    return periods


def _read_phases(path):
    table = pd.read_csv(path)
    required = {"frame_start", "frame_end", "team_in_possession_id",
                "team_in_possession_phase_type"}
    if not required <= set(table.columns):
        raise ValueError("{}: unexpected phase columns".format(path))
    phases = []
    for row in table.itertuples(index=False):
        phases.append({
            "start": int(row.frame_start),
            "end": int(row.frame_end),
            "team_id": None if pd.isna(row.team_in_possession_id)
            else int(row.team_in_possession_id),
            "type": "" if pd.isna(row.team_in_possession_phase_type)
            else str(row.team_in_possession_phase_type),
        })
    return phases


def load_match(match_dir):
    """Load a SkillCorner match: roster, per-period tracking, phases and pitch size."""
    match_id = os.path.basename(os.path.abspath(match_dir))
    meta_path = os.path.join(match_dir, match_id + MATCH_SUFFIX)
    tracking_path = os.path.join(match_dir, match_id + TRACKING_SUFFIX)
    phases_path = os.path.join(match_dir, match_id + PHASES_SUFFIX)
    with open(meta_path) as handle:
        meta = json.load(handle)
    home_id = int(meta["home_team"]["id"])
    away_id = int(meta["away_team"]["id"])
    team_code = {home_id: "H", away_id: "A"}
    roster = []
    roster_keys = []
    for player in meta["players"]:
        # The tracking stream uses the match.json player "id"; trackable_object is a
        # different identifier and is not what appears in player_data.player_id.
        key = str(player["id"])
        roster_keys.append(key)
        roster.append({
            "key": key,
            "team": team_code[int(player["team_id"])],
            "number": player.get("number"),
        })
    if len(set(roster_keys)) != len(roster_keys):
        raise ValueError("{}: duplicate player id".format(match_id))

    raw = _read_tracking(tracking_path, roster_keys)
    periods = {}
    for period, table in raw.items():
        frames = np.asarray(table["frames"], dtype=int)
        if not np.array_equal(frames, np.arange(frames[0], frames[0] + len(frames))):
            raise ValueError("{} period {}: frames are not contiguous".format(match_id, period))
        players = {key: np.asarray(table["players"][key], dtype=float)
                   for key in roster_keys}
        detected = {key: np.asarray(table["detected"][key], dtype=bool)
                    for key in roster_keys}
        periods[period] = {
            "frames": frames,
            "ball": np.asarray(table["ball"], dtype=float),
            "players": players,
            "detected": detected,
            "n_players": np.asarray(table["n_players"], dtype=int),
        }
    phases = _read_phases(phases_path)
    return {
        "match_id": match_id,
        "roster": roster,
        "periods": periods,
        "phases": phases,
        "team_code": team_code,
        "pitch_length": float(meta["pitch_length"]),
        "pitch_width": float(meta["pitch_width"]),
    }


# -- weak labels --------------------------------------------------------------------------------

def derive_labels(n_frames, n_players, phases):
    """H/A/D/X from phase spans and whole-frame tracking presence.

    ``phases`` is a list of ``(start, end, team)`` with clip-relative inclusive frames.
    Phases are the vendor's in-play definition: no phase means D. Overlapping phases are
    X. A unique phase gives its team only when the frame has player tracking; a phase
    frame with no tracking is X because the live side cannot be confirmed.
    """
    n_players = np.asarray(n_players, dtype=int)
    if len(n_players) != n_frames:
        raise ValueError("n_players length differs from n_frames")
    count = np.zeros(n_frames, dtype=int)
    team_at = np.full(n_frames, "", dtype=object)
    for start, end, team in phases:
        start = max(0, int(start))
        end = min(n_frames - 1, int(end))
        if end < start:
            continue
        count[start:end + 1] += 1
        team_at[start:end + 1] = team if team in ("H", "A") else ""
    labels = np.full(n_frames, "D", dtype=object)
    labels[count > 1] = "X"
    unique = count == 1
    known_team = np.isin(team_at, ("H", "A"))
    labels[unique & ((n_players == 0) | ~known_team)] = "X"
    known = unique & (n_players > 0) & known_team
    labels[known & (team_at == "H")] = "H"
    labels[known & (team_at == "A")] = "A"
    return labels


def _half_name(period):
    return "first_half" if period == 1 else "second_half"


def _first_team(labels):
    for label in labels:
        if label in ("H", "A"):
            return label
    return "H"


def _collapse(labels):
    out = []
    for label in labels:
        if not out or out[-1] != label:
            out.append(label)
    return out


def convert_match(match_dir, force=False):
    """Convert one SkillCorner match to ``outputs/simulation_sets/ext_skillcorner_<id>/``."""
    data = load_match(match_dir)
    match = data["match_id"]
    dataset_id = "ext_skillcorner_{}".format(match)
    slots = assign_slots(data["roster"])
    teams = slot_teams()
    length, width = data["pitch_length"], data["pitch_width"]
    clips = []
    for period in sorted(data["periods"]):
        table = data["periods"][period]
        frames = table["frames"]
        n_original = len(frames)
        first_frame = int(frames[0])
        clip_id = _half_name(period)
        ball_norm = np.column_stack(normalise_to_top_left(
            table["ball"][:, 0], table["ball"][:, 1], length, width))
        ball_up, nearest = upsample_positions(ball_norm)
        n_out = len(ball_up)
        low, high, frac, _ = resample_indices(n_original)
        players = {}
        raw_detected = 0
        raw_present = 0
        output_extrapolated = 0
        output_present = 0
        for key in table["players"]:
            x, y = normalise_to_top_left(
                table["players"][key][:, 0], table["players"][key][:, 1], length, width)
            up, _ = upsample_positions(np.column_stack([x, y]))
            players[slots[key]] = up
            present = np.isfinite(up).all(axis=1)
            detected = table["detected"][key]
            raw_present += int(np.isfinite(table["players"][key]).all(axis=1).sum())
            raw_detected += int(detected.sum())
            # A resampled position is backed by detection only when every endpoint it
            # uses was detected. Exact original frames use one endpoint.
            backed = detected[low].copy()
            interpolated = frac > 0
            backed[interpolated] = (detected[low][interpolated]
                                    & detected[high][interpolated])
            output_present += int(present.sum())
            output_extrapolated += int((present & ~backed).sum())

        phases = []
        for phase in data["phases"]:
            start = max(phase["start"], first_frame) - first_frame
            end = min(phase["end"], first_frame + n_original - 1) - first_frame
            if end < start:
                continue
            phases.append((start, end, data["team_code"].get(phase["team_id"], "")))
        labels_original = derive_labels(n_original, table["n_players"], phases)
        truth = labels_original[nearest]
        observations = observations_frame(ball_up, players, length, width)

        event_rows = []
        for phase in data["phases"]:
            start = max(phase["start"], first_frame)
            end = min(phase["end"], first_frame + n_original - 1)
            if end < start:
                continue
            frame = int(round((start - first_frame) * FACTOR_10_TO_25))
            frame = max(0, min(n_out - 1, frame))
            event_rows.append({
                "clip": clip_id,
                "event": "PHASE {}".format(phase["type"].upper()).strip(),
                "t": frame / FPS,
                "frame": frame,
                "team": data["team_code"].get(phase["team_id"], ""),
            })
        sample = {
            "clip": clip_id,
            "family": "external",
            "subtype": "skillcorner",
            "story_id": "{}_{}".format(match, clip_id),
            "seed": 0,
            "initiating_team": _first_team(truth),
            "n_frames": n_out,
            "core_start": 0,
            "core_stop": n_out,
            "expected_sequence": " ".join(_collapse(truth)),
        }
        metadata = {
            "slot_teams": teams,
            "pitch_length": length,
            "pitch_width": width,
            "fps": FPS,
        }
        raw_share = (1.0 - raw_detected / raw_present) if raw_present else None
        output_share = (output_extrapolated / output_present) if output_present else None
        clips.append(Clip(
            clip_id=clip_id,
            observations=observations,
            truth=truth,
            events=event_rows,
            sample=sample,
            metadata=metadata,
            diagnostics={
                "period": period,
                "first_source_frame": first_frame,
                "n_source_frames": n_original,
                "extrapolated_share": output_share,
                "extrapolated_share_raw": raw_share,
            },
        ))
    directory = write_dataset(dataset_id, clips, force=force)
    diagnostics = dataset_diagnostics(clips)
    print_diagnostics(dataset_id, diagnostics)
    raw_shares = [clip.diagnostics["extrapolated_share_raw"] for clip in clips]
    output_shares = [clip.diagnostics["extrapolated_share"] for clip in clips]
    print("  extrapolated raw 10 fps={}  after 25 fps resampling={}".format(
        [None if value is None else round(value, 4) for value in raw_shares],
        [None if value is None else round(value, 4) for value in output_shares]))
    return directory, diagnostics


def discover_matches(skillcorner_dir):
    """All local SkillCorner match directories with the three required files."""
    if not os.path.isdir(skillcorner_dir):
        raise SystemExit("SkillCorner directory not found: {}".format(skillcorner_dir))
    matches = []
    for name in sorted(os.listdir(skillcorner_dir)):
        path = os.path.join(skillcorner_dir, name)
        if not os.path.isdir(path):
            continue
        if (os.path.exists(os.path.join(path, name + MATCH_SUFFIX))
                and os.path.exists(os.path.join(path, name + TRACKING_SUFFIX))
                and os.path.exists(os.path.join(path, name + PHASES_SUFFIX))):
            matches.append(path)
    if not matches:
        raise SystemExit("no SkillCorner match directories under {}".format(skillcorner_dir))
    return matches
