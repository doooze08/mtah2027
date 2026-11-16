"""Metrica sample games -> simulation dataset (observations plus vendor weak labels).

Three games are supported with one label rule set:

* Game 1/2: raw tracking CSV (14/14 and 14/12 roster columns, 25 fps, native 0-1
  coordinates) plus raw event CSV.
* Game 3: EPTS metadata/tracking read through kloppy, exactly the loader path used by
  ``observations/atd.py``, plus the raw JSON events.

Weak labels (from vendor events only; tracking coordinates are never used to decide
dead/alive):

* ``D`` by event order. A stoppage starts at ``BALL OUT``, at a ``SHOT`` whose subtype
  contains ``OUT``, at ``FAULT RECEIVED``, at ``CARD``, or at a ``CHALLENGE`` whose
  subtype contains ``FAULT``. From that start to the next restart, the frames are D
  only when no live event (``PASS``, ``CARRY``, ``RECOVERY``, or a ``SHOT`` that is not
  out) starts after the stoppage event and before the restart; a live event in between
  is treated as advantage and the stoppage does not produce D. A restart is a
  ``SET PIECE``, or a ``PASS`` whose subtype is exactly ``GOAL KICK`` (the vendor
  encodes goal kicks as passes; ``GOAL KICK-INTERCEPTION`` remains a live event). A
  goal (``SHOT`` subtype contains ``GOAL``) keeps the original rule: from the frame
  after the shot ends until the next ``KICK OFF``.
* ``X`` only from the start of a half to the first kickoff and after the last event.
  There is no fixed foul window: a foul 30 s before the free kick is still D when no
  live event separates them.
* ``H``/``A``: the team of the most recent ``PASS``, ``CARRY``, ``RECOVERY``,
  ``SHOT`` or ``SET PIECE``; the side persists between events. ``BALL LOST`` and
  ``CHALLENGE`` do not switch the side.

Ball gaps and tracking coordinates never decide D; they are only observations.

Coordinates are never flipped by attacking direction. Games 1/2 keep the vendor's raw
top-left 0-1 y (the sample-data README's convention, and the same convention as the
EPTS raw coordinates used by the real ATD); Game 3 keeps kloppy's EPTS output.

Run from the repository root::

    .venv/bin/python -m external.convert --source metrica --data-dir "$PWD/data"
"""

import os

import numpy as np
import pandas as pd

from external.common import (
    Clip,
    Event,
    FPS,
    assign_slots,
    dataset_diagnostics,
    observations_frame,
    print_diagnostics,
    slot_teams,
    write_dataset,
)

SWITCH_TYPES = frozenset({"PASS", "CARRY", "RECOVERY", "SHOT", "SET PIECE"})
LIVE_TYPES = frozenset({"PASS", "CARRY", "RECOVERY"})
DIRECT_STOPPAGE_TYPES = frozenset({"BALL OUT", "FAULT RECEIVED", "CARD"})
OUTPUT_TYPES = frozenset(SWITCH_TYPES | {"BALL OUT", "FAULT RECEIVED", "CARD"})
PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0


# -- raw tracking -------------------------------------------------------------------------------

def _read_tracking_csv(path):
    """Read one Metrica raw tracking CSV; coordinates stay in the vendor 0-1 frame."""
    with open(path) as handle:
        team_row = handle.readline().rstrip("\n").split(",")
        number_row = handle.readline().rstrip("\n").split(",")
        name_row = handle.readline().rstrip("\n").split(",")
        data = pd.read_csv(handle, header=None)
    if name_row[:3] != ["Period", "Frame", "Time [s]"]:
        raise ValueError("{}: unexpected Metrica CSV header".format(path))
    player_starts = list(range(3, len(name_row) - 2, 2))
    jerseys = [number_row[i] for i in player_starts]
    if len(set(jerseys)) != len(jerseys):
        raise ValueError("{}: duplicate shirt numbers".format(path))
    frames = data.iloc[:, 1].to_numpy(dtype=int)
    periods = data.iloc[:, 0].to_numpy(dtype=int)
    players = data.iloc[:, 3:3 + 2 * len(jerseys)].to_numpy(dtype=float)
    players = players.reshape(len(data), len(jerseys), 2)
    # A half-missing coordinate pair is not a usable position.
    players[~np.isfinite(players).all(axis=2)] = np.nan
    ball = data.iloc[:, -2:].to_numpy(dtype=float)
    ball[~np.isfinite(ball).all(axis=1)] = np.nan
    team_name = team_row[3].strip()
    return {
        "team": team_name,
        "jerseys": [str(j).strip() for j in jerseys],
        "frames": frames,
        "periods": periods,
        "players": players,
        "ball": ball,
    }


def _load_tracking_csv(game_dir, game):
    home = _read_tracking_csv(os.path.join(
        game_dir, "{}_RawTrackingData_Home_Team.csv".format(game)))
    away = _read_tracking_csv(os.path.join(
        game_dir, "{}_RawTrackingData_Away_Team.csv".format(game)))
    if home["team"].lower() != "home" or away["team"].lower() != "away":
        raise ValueError("home/away CSV files are swapped")
    if not np.array_equal(home["frames"], away["frames"]):
        raise ValueError("home/away frame ids differ")
    if not np.array_equal(home["periods"], away["periods"]):
        raise ValueError("home/away periods differ")
    if not np.allclose(home["ball"], away["ball"], equal_nan=True):
        raise ValueError("home/away ball positions differ; files belong to different games")

    roster = []
    for ground, table in (("H", home), ("A", away)):
        for jersey in table["jerseys"]:
            roster.append({
                "key": "csv_{}_{}".format(ground, jersey),
                "team": ground,
                "number": int(jersey),
            })
    periods = {}
    for period in sorted(set(home["periods"].tolist())):
        mask = home["periods"] == period
        frames = home["frames"][mask]
        if not np.array_equal(frames, np.arange(frames[0], frames[0] + len(frames))):
            raise ValueError("period {} frames are not contiguous".format(period))
        players = {}
        for team, table in (("H", home), ("A", away)):
            for index, jersey in enumerate(table["jerseys"]):
                players["csv_{}_{}".format(team, jersey)] = table["players"][mask, index, :]
        periods[period] = {
            "frames": frames,
            "ball": home["ball"][mask],
            "players": players,
        }
    return roster, periods, PITCH_LENGTH, PITCH_WIDTH


def _load_tracking_epts(game_dir, game):
    from kloppy import metrica

    meta = os.path.join(game_dir, "{}_metadata.xml".format(game))
    raw = os.path.join(game_dir, "{}_tracking.txt".format(game))
    dataset = metrica.load_tracking_epts(meta_data=meta, raw_data=raw)
    frame = dataset.to_df(engine="pandas")
    pitch = dataset.metadata.pitch_dimensions
    roster = []
    for team in dataset.metadata.teams:
        ground = "H" if str(team.ground.value).lower() == "home" else "A"
        for player in team.players:
            roster.append({
                "key": player.player_id,
                "team": ground,
                "number": player.jersey_no,
            })
    periods = {}
    for period in sorted(frame["period_id"].dropna().unique().tolist()):
        part = frame[frame["period_id"] == period].sort_values("frame_id")
        frames = part["frame_id"].to_numpy(dtype=int)
        if not np.array_equal(frames, np.arange(frames[0], frames[0] + len(frames))):
            raise ValueError("period {} frames are not contiguous".format(period))
        players = {}
        for player in roster:
            x = part[player["key"] + "_x"].to_numpy(dtype=float)
            y = part[player["key"] + "_y"].to_numpy(dtype=float)
            players[player["key"]] = np.column_stack([x, y])
        ball = part[["ball_x", "ball_y"]].to_numpy(dtype=float)
        periods[int(period)] = {"frames": frames, "ball": ball, "players": players}
    return roster, periods, float(pitch.pitch_length), float(pitch.pitch_width)


# -- raw events ---------------------------------------------------------------------------------

def _team_code(name):
    if str(name).strip().lower() in ("home", "team a", "fifatma"):
        return "H"
    if str(name).strip().lower() in ("away", "team b", "fifatmb"):
        return "A"
    return ""


def _read_csv_events(path):
    table = pd.read_csv(path)
    required = {"Team", "Type", "Subtype", "Period", "Start Frame", "End Frame"}
    if not required <= set(table.columns):
        raise ValueError("{}: unexpected event columns".format(path))
    events = []
    for index, row in table.iterrows():
        start = int(row["Start Frame"])
        end = int(row["End Frame"])
        if end < start:
            # Metrica writes 0 for instantaneous set pieces; the start is the real frame.
            end = start
        events.append(Event(
            index=int(index),
            event_type=str(row["Type"]).strip().upper(),
            subtype="" if pd.isna(row["Subtype"]) else str(row["Subtype"]).strip().upper(),
            start=start,
            end=end,
            team=_team_code(row["Team"]),
            period=int(row["Period"]),
        ))
    return events


def _read_json_events(path):
    import json

    with open(path) as handle:
        payload = json.load(handle)
    events = []
    for index, row in enumerate(payload.get("data", [])):
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
        events.append(Event(
            index=index,
            event_type=str(row["type"]["name"]).strip().upper(),
            subtype=subtype.strip().upper(),
            start=start,
            end=end,
            team=(_team_code(row["team"].get("id"))
                  or _team_code(row["team"].get("name"))),
            period=int(row["period"]),
        ))
    return events


# -- weak labels --------------------------------------------------------------------------------

def _next_event(events, after, predicate):
    """Earliest event satisfying ``predicate`` with start strictly after ``after``."""
    candidates = [event for event in events if predicate(event) and event.start > after]
    return min(candidates, key=lambda event: (event.start, event.index)) if candidates else None


def _is_goal(event):
    return event.event_type == "SHOT" and "GOAL" in event.subtype


def _is_shot_out(event):
    return event.event_type == "SHOT" and "OUT" in event.subtype


def _is_challenge_fault(event):
    return event.event_type == "CHALLENGE" and "FAULT" in event.subtype


def _is_goal_kick_pass(event):
    # The vendor encodes a goal kick as PASS/GOAL KICK rather than SET PIECE.
    return event.event_type == "PASS" and event.subtype.strip() == "GOAL KICK"


def _is_restart(event):
    return event.event_type == "SET PIECE" or _is_goal_kick_pass(event)


def _is_stoppage_start(event):
    """Vendor events that can start a stoppage under the event-order rule."""
    return (event.event_type in DIRECT_STOPPAGE_TYPES
            or _is_shot_out(event)
            or _is_challenge_fault(event))


def _is_live_event(event):
    """Events that mean play continued and therefore cancel the preceding stoppage."""
    return ((event.event_type in LIVE_TYPES and not _is_goal_kick_pass(event))
            or (event.event_type == "SHOT" and not _is_shot_out(event)))


def _has_live_event_between(events, start_event, stop):
    """True when a live event starts after the stoppage event ends and before ``stop``."""
    for event in events:
        if not _is_live_event(event):
            continue
        if event.start <= start_event.end:
            continue
        if event.start < stop:
            return True
    return False


def derive_labels(n_frames, events):
    """H/A/D/X per frame from Metrica events and the event-order rules in the docstring.

    ``events`` use clip-relative frames and inclusive ends. This function is pure so the
    rule tests can use tiny hand-written event lists.
    """
    if n_frames <= 0:
        return np.array([], dtype=object)
    events = [event for event in events if 0 <= event.start < n_frames]
    for event in events:
        event.end = min(max(event.end, event.start), n_frames - 1)

    labels = np.full(n_frames, "X", dtype=object)
    switching = sorted(
        (event for event in events if event.event_type in SWITCH_TYPES and event.team in ("H", "A")),
        key=lambda event: (event.start, event.index),
    )
    current = None
    cursor = 0
    for frame in range(n_frames):
        while cursor < len(switching) and switching[cursor].start <= frame:
            current = switching[cursor].team
            cursor += 1
        if current is not None:
            labels[frame] = current

    dead = np.zeros(n_frames, dtype=bool)
    restarts = sorted(
        (event for event in events if _is_restart(event)),
        key=lambda event: (event.start, event.index),
    )
    for event in events:
        if _is_goal(event):
            next_kickoff = _next_event(
                restarts, event.end,
                lambda item: "KICK OFF" in item.subtype)
            stop = next_kickoff.start if next_kickoff is not None else n_frames
            dead[event.end + 1:stop] = True
    for event in events:
        if not _is_stoppage_start(event):
            continue
        next_piece = _next_event(restarts, event.start, lambda item: True)
        stop = next_piece.start if next_piece is not None else n_frames
        if stop <= event.start:
            continue
        # A live event in between means the referee played advantage (or the stoppage
        # was not real); leave the H/A stream untouched.
        if not _has_live_event_between(events, event, stop):
            dead[event.start:stop] = True
    labels[dead] = "D"

    # Half boundaries are not inferable from the events; before the first kickoff and
    # after the last event the label is deliberately X rather than a guess.
    kickoffs = [event for event in events if event.event_type == "SET PIECE"
                and "KICK OFF" in event.subtype]
    if kickoffs:
        first_kickoff = min(kickoffs, key=lambda event: (event.start, event.index)).start
        labels[:first_kickoff] = "X"
    else:
        labels[:] = "X"
    if events:
        last_end = max(event.end for event in events)
        labels[last_end + 1:] = "X"
    else:
        labels[:] = "X"
    return labels


# -- conversion ---------------------------------------------------------------------------------

def _clip_events(events, period, first_frame, n_frames):
    rows = []
    for event in events:
        if event.period != period:
            continue
        start = event.start - first_frame
        if start < 0 or start >= n_frames:
            continue
        end = min(max(event.end - first_frame, start), n_frames - 1)
        rows.append(Event(
            index=event.index,
            event_type=event.event_type,
            subtype=event.subtype,
            start=start,
            end=end,
            team=event.team,
            period=period,
        ))
    return rows


def _event_rows(clip_id, events):
    rows = []
    for event in events:
        if event.event_type not in OUTPUT_TYPES and not _is_challenge_fault(event):
            continue
        rows.append({
            "clip": clip_id,
            "event": event.name,
            "t": event.start / FPS,
            "frame": event.start,
            "team": event.team,
        })
    return rows


def _game_key(directory):
    name = os.path.basename(os.path.abspath(directory))
    if name.lower().startswith("sample_game_"):
        return "game_" + name.rsplit("_", 1)[-1]
    return name.lower()


def _half_name(period):
    return "first_half" if period == 1 else "second_half"


def load_game(game_dir):
    """Load one Metrica game into (roster, periods, pitch_length, pitch_width, events)."""
    game = os.path.basename(os.path.abspath(game_dir))
    epts_meta = os.path.join(game_dir, "{}_metadata.xml".format(game))
    epts_raw = os.path.join(game_dir, "{}_tracking.txt".format(game))
    csv_home = os.path.join(game_dir, "{}_RawTrackingData_Home_Team.csv".format(game))
    if os.path.exists(epts_meta) and os.path.exists(epts_raw):
        roster, periods, length, width = _load_tracking_epts(game_dir, game)
        events = _read_json_events(os.path.join(game_dir, "{}_events.json".format(game)))
    elif os.path.exists(csv_home):
        roster, periods, length, width = _load_tracking_csv(game_dir, game)
        events = _read_csv_events(os.path.join(game_dir, "{}_RawEventsData.csv".format(game)))
    else:
        raise SystemExit("{}: no supported Metrica tracking files".format(game_dir))
    return roster, periods, length, width, events


def convert_game(game_dir, force=False):
    """Convert one Metrica game to ``outputs/simulation_sets/ext_metrica_<game>/``."""
    match = _game_key(game_dir)
    dataset_id = "ext_metrica_{}".format(match)
    roster, periods, length, width, events = load_game(game_dir)
    slots = assign_slots(roster)
    teams = slot_teams()
    clips = []
    for period in sorted(periods):
        table = periods[period]
        frames = table["frames"]
        n_frames = len(frames)
        first_frame = int(frames[0])
        clip_id = _half_name(period)
        players = {}
        for player in roster:
            slot = slots[player["key"]]
            players[slot] = table["players"][player["key"]]
        observations = observations_frame(table["ball"], players, length, width)
        relative_events = _clip_events(events, period, first_frame, n_frames)
        truth = derive_labels(n_frames, relative_events)
        sample = {
            "clip": clip_id,
            "family": "external",
            "subtype": "metrica",
            "story_id": "{}_{}".format(match, clip_id),
            "seed": 0,
            "initiating_team": _first_team(truth),
            "n_frames": n_frames,
            "core_start": 0,
            "core_stop": n_frames,
            "expected_sequence": " ".join(_collapse(truth)),
        }
        metadata = {
            "slot_teams": teams,
            "pitch_length": length,
            "pitch_width": width,
            "fps": FPS,
        }
        clips.append(Clip(
            clip_id=clip_id,
            observations=observations,
            truth=truth,
            events=_event_rows(clip_id, relative_events),
            sample=sample,
            metadata=metadata,
            diagnostics={"period": period, "first_source_frame": first_frame},
        ))
    directory = write_dataset(dataset_id, clips, force=force)
    diagnostics = dataset_diagnostics(clips)
    print_diagnostics(dataset_id, diagnostics)
    return directory, diagnostics


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


def discover_games(metrica_dir):
    """All local Metrica sample games, sorted by game number."""
    if not os.path.isdir(metrica_dir):
        raise SystemExit("Metrica directory not found: {}".format(metrica_dir))
    games = []
    for name in sorted(os.listdir(metrica_dir)):
        path = os.path.join(metrica_dir, name)
        if not os.path.isdir(path):
            continue
        if name.startswith("Sample_Game_"):
            games.append(path)
    if not games:
        raise SystemExit("no Sample_Game_* directories under {}".format(metrica_dir))

    def number(path):
        try:
            return int(os.path.basename(path).rsplit("_", 1)[-1])
        except ValueError:
            return 10 ** 6

    return sorted(games, key=number)
