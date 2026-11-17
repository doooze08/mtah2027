"""Feature extraction for the gap-characterization study.

Read-only measurement code.  It reads the generated external simulation sets and the raw
Metrica event files; it does not import or modify an algorithm, the simulator, or the
converter.

Sample definitions (fixed before looking at Game 3 distributions)
------------------------------------------------------------------
* ``dead_gap``: a contiguous run of missing ball coordinates of at least 5 s whose
  frame-level weak labels are majority ``D``.
* ``live_gap``: the same run with a majority of ``H``/``A``.  If the first raw Metrica
  event at or after the gap's first visible frame is a ``SET PIECE``, the sample is
  additionally marked ``suspicious`` and is *not* pooled with ordinary live gaps.
* ``artificial_live``: a ball-visible, all-live run of at least 5 s; a 5--15 s interval is
  sampled with a fixed seed and treated as if the ball coordinates were absent.  The
  original coordinates are only used to measure what happens at the two ends.
* ``dead_visible``: a maximal contiguous run of weak ``D`` and visible ball coordinates,
  at least 2 s, used only for the player-motion features.

Features
--------
A. Reappearance (for gaps and artificial masks)
   reappear/disappear position category, ball speed in the 0.5 s after reappearance,
   speed in the 1 s before disappearance, reappearance-to-disappearance distance, and
   that distance after subtracting the mean player displacement between the two ends.

B. Player motion (median and 90th percentile over the segment)
   all-player median speed (collective-speed ``F1``), number of players above 4 m/s,
   mean of the two teams' 10-outfield-player centroid speeds (1 s smoothed), cosine of
   the two teams' centroid directions (only when both speeds exceed 0.3 m/s), and mean
   within-team dispersion.

C. Pre-disappearance
   disappearance category and ball speed in the preceding 1 s.

All player speeds come from adjacent positions, never the ``_s`` columns.  The ball speed
is the distance between adjacent finite positions times 25 fps.
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
OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "20261116_gap_characterization")
FPS = 25
WINDOW = FPS
MIN_PLAYERS = 5
MIN_GAP_FRAMES = 5 * FPS
MIN_VISIBLE_DEAD_FRAMES = 2 * FPS
ARTIFICIAL_MIN_FRAMES = 5 * FPS
ARTIFICIAL_MAX_FRAMES = 15 * FPS
ARTIFICIAL_PER_MATCH = 200

# Law 1 field markings, in metres.  The 1 m touchline band is an analysis choice, not a
# Law 1 marking; it is fixed here before looking at distributions.
GOAL_AREA_DEPTH_M = 5.5
GOAL_AREA_WIDTH_M = 18.32
CENTER_CIRCLE_RADIUS_M = 9.15
CORNER_ARC_RADIUS_M = 1.0
TOUCHLINE_BAND_M = 1.0

POSITION_CATEGORIES = (
    "out_or_touchline",
    "corner",
    "goal_area",
    "center_circle",
    "other",
)

MATCHES = {
    1: "ext_metrica_game_1",
    2: "ext_metrica_game_2",
    3: "ext_metrica_game_3",
}

SLOT_IDS = [str(i) for i in range(1, 47)]
POSITION_COLUMNS = [f"{slot}_{axis}" for slot in SLOT_IDS for axis in ("x", "y")]

_CONTINUOUS_FEATURES = (
    "reappear_speed_0p5s_m_s",
    "disappear_speed_1s_m_s",
    "reappear_to_disappear_m",
    "reappear_to_disappear_after_team_shift_m",
    "f1_speed_med",
    "f1_speed_p90",
    "speed_gt4_count_med",
    "speed_gt4_count_p90",
    "team_speed_med",
    "team_speed_p90",
    "team_cos_med",
    "team_cos_p90",
    "dispersion_med",
    "dispersion_p90",
)


def dataset_dir(match):
    return os.path.join(SIMULATION_SETS, MATCHES[match])


def load_clips(match):
    """Load both half clips, sorted first_half then second_half."""
    directory = dataset_dir(match)
    observations = pd.read_csv(os.path.join(directory, "observations.csv"),
                               dtype={"clip": str})
    truth = pd.read_csv(os.path.join(directory, "truth.csv"), dtype={"clip": str})
    with open(os.path.join(directory, "metadata.json")) as handle:
        metadata = json.load(handle)
    clips = []
    for clip_id in ("first_half", "second_half"):
        frames = observations[observations["clip"] == clip_id].sort_values("frame")
        frames = frames.reset_index(drop=True)
        labels = truth[truth["clip"] == clip_id].sort_values("frame")["label"].to_numpy()
        if len(labels) != len(frames):
            raise ValueError(f"{MATCHES[match]} {clip_id}: truth/frame mismatch")
        meta = metadata[clip_id]
        clips.append({
            "dataset": MATCHES[match],
            "match": match,
            "clip": clip_id,
            "observations": frames,
            "labels": labels,
            "pitch_length": float(meta["pitch_length"]),
            "pitch_width": float(meta["pitch_width"]),
            "slot_teams": {str(k): str(v) for k, v in meta["slot_teams"].items()},
        })
    return clips


def metrica_game_dir(match):
    return os.path.join(REPO_ROOT, "data", "external", "metrica",
                        f"Sample_Game_{match}")


def read_metrica_events(match):
    """Read raw Metrica events (period, frame, type, subtype)."""
    base = metrica_game_dir(match)
    events = []
    csv_path = os.path.join(base, f"Sample_Game_{match}_RawEventsData.csv")
    json_path = os.path.join(base, f"Sample_Game_{match}_events.json")
    if os.path.exists(csv_path):
        table = pd.read_csv(csv_path)
        for _, row in table.iterrows():
            start = int(row["Start Frame"])
            end = int(row["End Frame"])
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
        raise SystemExit(f"no raw Metrica event file under {base}")
    return events


def clip_events(clips, raw_events):
    """Attach events to clips as clip-relative frames."""
    offsets = {1: 1, 2: 1 + len(clips[0]["observations"])}
    by_clip = {clip["clip"]: [] for clip in clips}
    for clip in clips:
        period = 1 if clip["clip"] == "first_half" else 2
        offset = offsets[period]
        for event in raw_events:
            if event["period"] != period:
                continue
            relative = event["start"] - offset
            by_clip[clip["clip"]].append({
                "frame": int(relative),
                "type": event["type"],
                "subtype": event["subtype"],
            })
        by_clip[clip["clip"]].sort(key=lambda item: item["frame"])
    return by_clip


def first_post_gap_event(events, stop):
    for event in events:
        if event["frame"] >= stop:
            label = event["type"]
            if event["subtype"]:
                label = f"{label} {event['subtype']}"
            return label, event["type"] == "SET PIECE"
    return "", False


def position_category(x, y, pitch_length, pitch_width):
    """Classify a normalized position using fixed Law 1 markings."""
    if not (np.isfinite(x) and np.isfinite(y)):
        return ""
    if x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
        return "out_or_touchline"
    xm = x * pitch_length
    ym = y * pitch_width
    corners = ((0.0, 0.0), (0.0, pitch_width),
               (pitch_length, 0.0), (pitch_length, pitch_width))
    corner_distance = min(np.hypot(xm - cx, ym - cy) for cx, cy in corners)
    if corner_distance <= CORNER_ARC_RADIUS_M:
        return "corner"
    in_goal_area_depth = xm <= GOAL_AREA_DEPTH_M or xm >= pitch_length - GOAL_AREA_DEPTH_M
    if in_goal_area_depth and abs(ym - pitch_width / 2.0) <= GOAL_AREA_WIDTH_M / 2.0:
        return "goal_area"
    if np.hypot(xm - pitch_length / 2.0, ym - pitch_width / 2.0) <= CENTER_CIRCLE_RADIUS_M:
        return "center_circle"
    if ym <= TOUCHLINE_BAND_M or ym >= pitch_width - TOUCHLINE_BAND_M:
        return "out_or_touchline"
    return "other"


def _rolling_mean(values, window=WINDOW):
    # pandas 3's to_numpy() is read-only; copy before masking below.
    return pd.Series(values).rolling(window, min_periods=1).mean().to_numpy().copy()


def _slot_positions(observations):
    return observations[POSITION_COLUMNS].to_numpy(dtype=float).reshape(
        len(observations), len(SLOT_IDS), 2)


def _slot_speeds(positions, pitch_length, pitch_width):
    speeds = np.full(positions.shape[:2], np.nan, dtype=float)
    if len(positions) > 1:
        dx = np.diff(positions[:, :, 0], axis=0) * pitch_length
        dy = np.diff(positions[:, :, 1], axis=0) * pitch_width
        speeds[1:] = np.hypot(dx, dy) * FPS
        speeds[0] = speeds[1]
    finite = np.isfinite(positions).all(axis=2)
    speeds[~finite] = np.nan
    return speeds


def _team_slots(positions, slot_teams, team, pitch_length, pitch_width):
    """Pick 11 slots by finite count, infer goalkeeper, return 10 outfield slots."""
    team_ids = [slot for slot in SLOT_IDS if slot_teams.get(slot) == team]
    if not team_ids:
        return [], "", 0
    finite = np.isfinite(positions[:, [SLOT_IDS.index(slot) for slot in team_ids], :]).all(axis=2)
    counts = finite.sum(axis=0)
    order = np.argsort(-counts)
    candidates = [team_ids[i] for i in order if counts[i] > 0][:11]
    if not candidates:
        return [], "", 0
    best_slot = None
    best_goal = None
    best_distance = np.inf
    for slot in candidates:
        col = SLOT_IDS.index(slot)
        rows = positions[:, col, :]
        keep = np.isfinite(rows).all(axis=1)
        if keep.sum() == 0:
            continue
        xm = rows[keep, 0] * pitch_length
        ym = rows[keep, 1] * pitch_width
        left = float(np.median(np.hypot(xm, ym - pitch_width / 2.0)))
        right = float(np.median(np.hypot(xm - pitch_length, ym - pitch_width / 2.0)))
        distance = min(left, right)
        if distance < best_distance:
            best_distance = distance
            best_slot = slot
            best_goal = "left" if left <= right else "right"
    outfield = [slot for slot in candidates if slot != best_slot][:10]
    return outfield, best_goal or "", len(candidates)


def _team_motion(positions, slots, pitch_length, pitch_width):
    """Centroid position, raw/smoothed velocity, speed and dispersion for one team."""
    n = len(positions)
    if not slots:
        nan = np.full(n, np.nan, dtype=float)
        return {"centroid": np.full((n, 2), np.nan), "vx": nan, "vy": nan,
                "speed": nan, "dispersion": nan, "count": np.zeros(n, dtype=int)}
    cols = [SLOT_IDS.index(slot) for slot in slots]
    team_pos = positions[:, cols, :]
    finite = np.isfinite(team_pos).all(axis=2)
    count = finite.sum(axis=1)
    summed = np.nansum(np.where(finite[:, :, None], team_pos, 0.0), axis=1)
    centroid = np.divide(summed, count[:, None],
                         out=np.full((n, 2), np.nan, dtype=float),
                         where=count[:, None] >= MIN_PLAYERS)
    centroid_m = centroid * np.array([pitch_length, pitch_width])
    vx = np.full(n, np.nan, dtype=float)
    vy = np.full(n, np.nan, dtype=float)
    if n > 1:
        vx[1:] = np.diff(centroid_m[:, 0]) * FPS
        vy[1:] = np.diff(centroid_m[:, 1]) * FPS
        vx[0] = vx[1]
        vy[0] = vy[1]
    raw_speed = np.hypot(vx, vy)
    raw_speed[count < MIN_PLAYERS] = np.nan
    vx_s = _rolling_mean(vx)
    vy_s = _rolling_mean(vy)
    speed = np.hypot(vx_s, vy_s)
    speed[~np.isfinite(raw_speed)] = np.nan
    vx_s[~np.isfinite(raw_speed)] = np.nan
    vy_s[~np.isfinite(raw_speed)] = np.nan
    diff = (team_pos - centroid[:, None, :]) * np.array([pitch_length, pitch_width])
    distance = np.hypot(diff[:, :, 0], diff[:, :, 1])
    distance = np.where(finite, distance, np.nan)
    dispersion = np.divide(np.nansum(distance, axis=1), count,
                           out=np.full(n, np.nan, dtype=float),
                           where=count >= MIN_PLAYERS)
    return {"centroid": centroid_m, "vx": vx_s, "vy": vy_s,
            "speed": speed, "dispersion": dispersion, "count": count}


def build_context(clip):
    """Precompute all frame-level quantities needed by the segment features."""
    observations = clip["observations"]
    pitch_length = clip["pitch_length"]
    pitch_width = clip["pitch_width"]
    positions = _slot_positions(observations)
    speeds = _slot_speeds(positions, pitch_length, pitch_width)
    finite_speed = np.isfinite(speeds)
    speed_count = finite_speed.sum(axis=1)
    with np.errstate(all="ignore"):
        f1_raw = np.nanmedian(speeds, axis=1)
    count_gt4 = (speeds > 4.0).sum(axis=1).astype(float)
    count_gt4[speed_count < MIN_PLAYERS] = np.nan
    f1 = _rolling_mean(f1_raw)
    f1[speed_count < MIN_PLAYERS] = np.nan

    team_motion = {}
    for team in ("H", "A"):
        slots, goal, n_candidates = _team_slots(
            positions, clip["slot_teams"], team, pitch_length, pitch_width)
        motion = _team_motion(positions, slots, pitch_length, pitch_width)
        motion["slots"] = slots
        motion["goal"] = goal
        motion["n_candidates"] = n_candidates
        team_motion[team] = motion

    team_speed = np.nanmean(
        np.vstack([team_motion["H"]["speed"], team_motion["A"]["speed"]]), axis=0)
    dispersion = np.nanmean(
        np.vstack([team_motion["H"]["dispersion"], team_motion["A"]["dispersion"]]), axis=0)
    cos = np.full(len(observations), np.nan, dtype=float)
    h = team_motion["H"]
    a = team_motion["A"]
    both = (h["speed"] > 0.3) & (a["speed"] > 0.3) & np.isfinite(h["vx"]) & np.isfinite(a["vx"])
    dot = h["vx"] * a["vx"] + h["vy"] * a["vy"]
    cos[both] = dot[both] / (h["speed"][both] * a["speed"][both])
    cos[~np.isfinite(cos)] = np.nan

    ball = observations[["ball_x", "ball_y"]].to_numpy(dtype=float)
    ball_known = np.isfinite(ball).all(axis=1)
    ball_speed = np.full(len(observations), np.nan, dtype=float)
    if len(ball) > 1:
        ball_speed[1:] = np.hypot(np.diff(ball[:, 0]) * pitch_length,
                                  np.diff(ball[:, 1]) * pitch_width) * FPS
        ball_speed[1:][~ball_known[1:]] = np.nan
        ball_speed[1:][~ball_known[:-1]] = np.nan
    ball_speed[0] = np.nan
    return {
        "clip": clip,
        "positions": positions,
        "ball": ball,
        "ball_known": ball_known,
        "ball_speed": ball_speed,
        "f1": f1,
        "count_gt4": count_gt4,
        "team_speed": team_speed,
        "dispersion": dispersion,
        "cos": cos,
        "team_motion": team_motion,
    }


def _segment_stats(values, start, stop):
    segment = values[start:stop]
    finite = segment[np.isfinite(segment)]
    if len(finite) == 0:
        return np.nan, np.nan
    return float(np.median(finite)), float(np.percentile(finite, 90))


def _mean_finite(values):
    finite = values[np.isfinite(values)]
    return float(np.mean(finite)) if len(finite) else np.nan


def _sample_row(context, start, stop, sample_type, *, match, split, clip_name,
                dead_votes=0, live_votes=0, first_event="", suspicious=False,
                synthetic=False):
    clip = context["clip"]
    pitch_length = clip["pitch_length"]
    pitch_width = clip["pitch_width"]
    f1_med, f1_p90 = _segment_stats(context["f1"], start, stop)
    gt4_med, gt4_p90 = _segment_stats(context["count_gt4"], start, stop)
    team_med, team_p90 = _segment_stats(context["team_speed"], start, stop)
    cos_med, cos_p90 = _segment_stats(context["cos"], start, stop)
    disp_med, disp_p90 = _segment_stats(context["dispersion"], start, stop)
    row = {
        "sample_id": "",
        "split": split,
        "match": match,
        "dataset": clip["dataset"],
        "clip": clip_name,
        "sample_type": sample_type,
        "start_s": start / FPS,
        "stop_s": stop / FPS,
        "length_s": (stop - start) / FPS,
        "n_frames": stop - start,
        "dead_votes": dead_votes,
        "live_votes": live_votes,
        "first_post_gap_event": first_event,
        "suspicious": bool(suspicious),
        "synthetic": bool(synthetic),
        "f1_speed_med": f1_med,
        "f1_speed_p90": f1_p90,
        "speed_gt4_count_med": gt4_med,
        "speed_gt4_count_p90": gt4_p90,
        "team_speed_med": team_med,
        "team_speed_p90": team_p90,
        "team_cos_med": cos_med,
        "team_cos_p90": cos_p90,
        "dispersion_med": disp_med,
        "dispersion_p90": disp_p90,
        "reappear_category": "",
        "disappear_category": "",
        "reappear_speed_0p5s_m_s": np.nan,
        "disappear_speed_1s_m_s": np.nan,
        "reappear_to_disappear_m": np.nan,
        "reappear_to_disappear_after_team_shift_m": np.nan,
    }
    # Ball features do not exist for a visible-dead segment.
    if sample_type == "dead_visible":
        return row
    if start <= 0 or stop >= len(context["ball"]):
        return row
    before = context["ball"][start - 1]
    after = context["ball"][stop]
    if not (np.isfinite(before).all() and np.isfinite(after).all()):
        return row
    row["disappear_category"] = position_category(
        before[0], before[1], pitch_length, pitch_width)
    row["reappear_category"] = position_category(
        after[0], after[1], pitch_length, pitch_width)
    row["reappear_speed_0p5s_m_s"] = _mean_finite(
        context["ball_speed"][stop + 1:stop + 1 + 12])
    row["disappear_speed_1s_m_s"] = _mean_finite(
        context["ball_speed"][max(1, start - 25):start])
    distance = np.hypot((after[0] - before[0]) * pitch_length,
                        (after[1] - before[1]) * pitch_width)
    row["reappear_to_disappear_m"] = float(distance)
    # Mean player displacement across all finite slots, both teams.
    p_before = context["positions"][start - 1]
    p_after = context["positions"][stop]
    keep_before = np.isfinite(p_before).all(axis=1)
    keep_after = np.isfinite(p_after).all(axis=1)
    if keep_before.sum() >= MIN_PLAYERS and keep_after.sum() >= MIN_PLAYERS:
        mean_before = p_before[keep_before].mean(axis=0) * np.array([pitch_length, pitch_width])
        mean_after = p_after[keep_after].mean(axis=0) * np.array([pitch_length, pitch_width])
        shift = mean_after - mean_before
        expected = before * np.array([pitch_length, pitch_width]) + shift
        actual = after * np.array([pitch_length, pitch_width])
        row["reappear_to_disappear_after_team_shift_m"] = float(
            np.hypot(*(actual - expected)))
    return row


def ball_missing_runs(observations, min_frames=MIN_GAP_FRAMES):
    missing = observations[["ball_x", "ball_y"]].isna().any(axis=1).to_numpy()
    edges = np.diff(np.r_[False, missing, False].astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    return [(int(a), int(b)) for a, b in zip(starts, stops) if b - a >= min_frames]


def _visible_dead_runs(labels, ball_known):
    mask = (labels == "D") & ball_known
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    return [(int(a), int(b)) for a, b in zip(starts, stops)
            if b - a >= MIN_VISIBLE_DEAD_FRAMES]


def _visible_live_runs(labels, ball_known):
    mask = ball_known & np.isin(labels, ["H", "A"])
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    return [(int(a), int(b)) for a, b in zip(starts, stops)
            if b - a >= ARTIFICIAL_MIN_FRAMES]


def _artificial_samples(clips, contexts, labels_by_clip, rng):
    candidates = []
    for clip, context in zip(clips, contexts):
        labels = labels_by_clip[clip["clip"]]
        for run_start, run_stop in _visible_live_runs(labels, context["ball_known"]):
            candidates.append((clip["clip"], run_start, run_stop))
    if not candidates:
        return []
    chosen = []
    attempts = 0
    while len(chosen) < ARTIFICIAL_PER_MATCH and attempts < ARTIFICIAL_PER_MATCH * 200:
        attempts += 1
        clip_name, run_start, run_stop = candidates[int(rng.integers(len(candidates)))]
        length = int(rng.integers(ARTIFICIAL_MIN_FRAMES, ARTIFICIAL_MAX_FRAMES + 1))
        if run_stop - run_start < length:
            continue
        start = int(rng.integers(run_start, run_stop - length + 1))
        stop = start + length
        if any(item["clip"] == clip_name and not (stop <= item["start"] or start >= item["stop"])
               for item in chosen):
            continue
        chosen.append({"clip": clip_name, "start": start, "stop": stop})
    if len(chosen) < ARTIFICIAL_PER_MATCH:
        raise RuntimeError(
            f"only {len(chosen)} non-overlapping artificial samples, need {ARTIFICIAL_PER_MATCH}")
    return chosen


def build_match_samples(match, seed):
    clips = load_clips(match)
    raw_events = read_metrica_events(match)
    events_by_clip = clip_events(clips, raw_events)
    contexts = [build_context(clip) for clip in clips]
    labels_by_clip = {clip["clip"]: clip["labels"] for clip in clips}
    split = "design" if match in (1, 2) else "test"
    rows = []
    for clip, context in zip(clips, contexts):
        labels = clip["labels"]
        clip_name = clip["clip"]
        events = events_by_clip[clip_name]
        for start, stop in ball_missing_runs(clip["observations"]):
            dead = int((labels[start:stop] == "D").sum())
            live = int(np.isin(labels[start:stop], ["H", "A"]).sum())
            if dead == live:
                continue
            if dead > live:
                sample_type = "dead_gap"
                suspicious = False
                first_event = ""
            else:
                sample_type = "live_gap"
                first_event, suspicious = first_post_gap_event(events, stop)
            row = _sample_row(context, start, stop, sample_type,
                              match=match, split=split, clip_name=clip_name,
                              dead_votes=dead, live_votes=live,
                              first_event=first_event, suspicious=suspicious)
            rows.append(row)
        for start, stop in _visible_dead_runs(labels, context["ball_known"]):
            rows.append(_sample_row(context, start, stop, "dead_visible",
                                    match=match, split=split, clip_name=clip_name,
                                    dead_votes=stop - start, live_votes=0))
    rng = np.random.default_rng(seed + match)
    for item in _artificial_samples(clips, contexts, labels_by_clip, rng):
        index = next(i for i, clip in enumerate(clips) if clip["clip"] == item["clip"])
        rows.append(_sample_row(contexts[index], item["start"], item["stop"],
                                "artificial_live", match=match, split=split,
                                clip_name=item["clip"], live_votes=item["stop"] - item["start"],
                                synthetic=True))
    for i, row in enumerate(rows):
        row["sample_id"] = f"m{match}_{i:05d}"
    return rows


def build_samples(matches, seed=20261116):
    rows = []
    for match in matches:
        rows.extend(build_match_samples(match, seed))
    return rows
