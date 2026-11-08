"""Contract tests using synthetic worlds and synthetic EPTS, never match assets or labels."""

import copy
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from algorithms.placeholder import predict as placeholder
from observations import COLUMNS, SLOTS, validate
from observations.atd import from_kloppy, load_tactical
from simulation.core import io
from simulation.core.observe import observe
from simulation.generate import assign_clip_ids, build_clips, tables, verify_written
from simulation.run_algorithm import main as run_algorithm, predict_frames
from simulation.view import build_payload


def moving_world():
    """Distinct linear tracks: 3 m/s along x, 4 m/s along y, hence 5 m/s speed."""
    rows = []
    for f in range(4):
        rows.append((f, "ball", "", 106 + f, -1, 2 + f))
        for i in range(1, 23):
            rows.append((f, "p{:02d}".format(i), "H" if i <= 11 else "A",
                         i + 3 * f / 25, 10 + 4 * f / 25, np.nan))
    return SimpleNamespace(n_frames=4, frames=pd.DataFrame(
        rows, columns=["frame", "object", "team", "x", "y", "z"]))


def synthetic_epts(directory):
    """Write a minimal three-frame FIFA/EPTS export accepted by kloppy 3.18.0."""
    root = ET.Element("EPTS")
    meta = ET.SubElement(root, "Metadata")
    ET.SubElement(meta, "GlobalConfig").extend([
        ET.fromstring('<ProviderName>Metrica Sports</ProviderName>'),
        ET.fromstring('<FrameRate>25</FrameRate>')])
    params = ET.SubElement(meta.find("GlobalConfig"), "ProviderGlobalParameters")
    for name, value in (("first_half_start", "1"), ("first_half_end", "3")):
        parameter = ET.SubElement(params, "ProviderParameter")
        ET.SubElement(parameter, "Name").text = name
        ET.SubElement(parameter, "Value").text = value
    teams = ET.SubElement(meta, "Teams")
    # Away is deliberately first; Score metadata determines the H/A mapping.
    for team_id in ("away", "home"):
        team = ET.SubElement(teams, "Team", id=team_id)
        ET.SubElement(team, "Name").text = team_id
        params = ET.SubElement(team, "ProviderTeamsParameters")
        parameter = ET.SubElement(params, "ProviderParameter")
        ET.SubElement(parameter, "Name").text = "attack_direction_first_half"
        ET.SubElement(parameter, "Value").text = "left_to_right"
    session = ET.SubElement(ET.SubElement(meta, "Sessions"), "Session")
    size = ET.SubElement(session, "FieldSize")
    ET.SubElement(size, "Width").text = "105"
    ET.SubElement(size, "Height").text = "68"
    score = ET.SubElement(ET.SubElement(session, "MatchParameters"), "Score",
                          idLocalTeam="home", idVisitingTeam="away")
    ET.SubElement(score, "LocalTeamScore").text = "0"
    ET.SubElement(score, "VisitingTeamScore").text = "0"
    players = ET.SubElement(meta, "Players")
    channels = ET.SubElement(meta, "PlayerChannels")
    sensors = ET.SubElement(ET.SubElement(ET.SubElement(meta, "Devices"), "Device"), "Sensors")
    for sensor_id, fields, unit in (("position", ("x", "y", "z"), "normalized"),
                                    ("speed", ("s",), "m/s")):
        sensor = ET.SubElement(sensors, "Sensor", id=sensor_id)
        ET.SubElement(sensor, "Name").text = sensor_id
        sensor_channels = ET.SubElement(sensor, "Channels")
        for field in fields:
            channel = ET.SubElement(sensor_channels, "Channel", id=field)
            ET.SubElement(channel, "Name").text = field
            ET.SubElement(channel, "Unit").text = unit
    spec = ET.SubElement(ET.SubElement(root, "DataFormatSpecifications"),
                         "DataFormatSpecification", startFrame="1", endFrame="3", separator=":")
    ET.SubElement(spec, "StringRegister", name="frameCount")
    refs = ET.SubElement(spec, "SplitRegister", separator=";")
    for i in range(1, 47):
        player_id = "Track_{}".format(i)
        player = ET.SubElement(players, "Player", id=player_id,
                               teamId="home" if i <= 23 else "away")
        ET.SubElement(player, "ShirtNumber").text = str(i)
        ET.SubElement(player, "Name").text = "Track {}".format(i)
        fields = ET.SubElement(refs, "SplitRegister", separator=",")
        for field in ("x", "y", "s"):
            channel_id = "{}_{}".format(i, field)
            ET.SubElement(channels, "PlayerChannel", id=channel_id,
                          playerId=player_id, channelId=field)
            ET.SubElement(fields, "PlayerChannelRef", playerChannelId=channel_id)
    ball = ET.SubElement(spec, "SplitRegister", separator=",")
    for field in ("x", "y", "z"):
        ET.SubElement(ball, "BallChannelRef", channelId=field)
    xml_path, raw_path = Path(directory) / "metadata.xml", Path(directory) / "tracking.txt"
    ET.ElementTree(root).write(xml_path, encoding="utf-8")
    lines = []
    for f in range(1, 4):
        values = ["0.2,0.3,7.5"] * 45 + ["NaN,NaN,NaN"]
        ball_values = "NaN,NaN,NaN" if f == 1 else "1.05,-0.02,8"
        lines.append("{}:{}:{}".format(f, ";".join(values), ball_values))
    raw_path.write_text("\n".join(lines) + "\n")
    return xml_path, raw_path


class ObservationTests(unittest.TestCase):
    def test_projection_mapping_speed_and_reproducibility(self):
        world = moving_world()
        obs, metadata = observe("c001", world, seed=12)
        again, same_meta = observe("c001", world, seed=12)
        pd.testing.assert_frame_equal(obs, again)
        self.assertEqual(metadata, same_meta)
        different, _ = observe("c002", world, seed=12)
        self.assertFalse(obs.equals(different))
        different_seed, _ = observe("c001", world, seed=13)
        self.assertFalse(obs.equals(different_seed))
        self.assertEqual(list(obs.columns), COLUMNS)
        active = [s for s in SLOTS if metadata["slot_teams"][s]]
        self.assertEqual(len(active), 22)
        self.assertEqual(list(metadata["slot_teams"].values()).count("H"), 11)
        self.assertEqual(list(metadata["slot_teams"].values()).count("A"), 11)
        for slot in active:
            np.testing.assert_allclose(obs[slot + "_s"], 5.0, atol=1e-10)
            start = int(round(obs[slot + "_x"].iloc[0] * 105))
            self.assertEqual(metadata["slot_teams"][slot], "H" if start <= 11 else "A")
            np.testing.assert_allclose(obs[slot + "_x"] * 105, start + 3 * np.arange(4) / 25)
        for slot in set(SLOTS) - set(active):
            self.assertTrue(obs[[slot + "_" + f for f in ("x", "y", "s")]].isna().all().all())
        self.assertTrue((obs.ball_x > 1).all())
        self.assertTrue((obs.ball_y < 0).all())
        changed = copy.deepcopy(world)
        changed.frames["z"] = 999
        pd.testing.assert_frame_equal(observe("c001", changed, 12)[0], obs)
        # No access to truth, events, play_live, restart_team or scenario fields is possible here.
        result = predict_frames(placeholder, obs, metadata, {})
        self.assertEqual(result.label.tolist(), ["X"] * 4)

    def test_single_frame_and_schema_failures(self):
        world = moving_world()
        world.frames = world.frames[world.frames.frame == 0]
        world.n_frames = 1
        obs, metadata = observe("c001", world)
        active = next(s for s in SLOTS if metadata["slot_teams"][s])
        self.assertEqual(obs[active + "_s"].iloc[0], 0)
        with self.assertRaises(ValueError):
            validate(obs.assign(z=0), metadata)
        with self.assertRaises(ValueError):
            validate(obs.assign(frame=1), metadata)
        with self.assertRaises(ValueError):
            validate(obs, dict(metadata, play_live=1))
        bad = SimpleNamespace(predict=lambda *args: [])
        with self.assertRaises(ValueError):
            predict_frames(bad, obs, metadata, {})
        bad.predict = lambda *args: ["invalid"]
        with self.assertRaises(ValueError):
            predict_frames(bad, obs, metadata, {})

    def test_disk_boundary_truth_and_viewer(self):
        built = assign_clip_ids(build_clips(["TI01", "HD01"], 1, 0), 0)
        with TemporaryDirectory() as temp:
            directory = Path(temp) / "new"
            io.write_dataset(directory, *tables(built))
            self.assertEqual(verify_written(directory), [])
            self.assertFalse((directory / "game_state.csv").exists())
            self.assertTrue((directory / io.CLEAN_FILE).exists())
            with self.assertRaises(FileExistsError):
                io.write_dataset(directory, *tables(built))
            original_read = pd.read_csv
            opened = []

            def visible_only(path, *args, **kwargs):
                self.assertEqual(Path(path).name, "observations.csv")
                opened.append(Path(path).name)
                return original_read(path, *args, **kwargs)

            with patch.object(pd, "read_csv", side_effect=visible_only):
                loaded = list(io.load_clips(directory))
            self.assertEqual(opened, ["observations.csv"])
            self.assertEqual(sum(len(obs) for _, obs, _ in loaded), 1020)
            # Removing every grading/debug file must not affect the algorithm loader.
            for name in (io.TRUTH_FILE, io.EVENTS_FILE, io.SAMPLES_FILE, io.CLEAN_FILE):
                (directory / name).rename(directory / (Path(name).name + ".hidden"))
            self.assertEqual(len(list(io.load_clips(directory))), 4)
            for name in (io.TRUTH_FILE, io.EVENTS_FILE, io.SAMPLES_FILE, io.CLEAN_FILE):
                (directory / (Path(name).name + ".hidden")).rename(directory / name)
            with patch("simulation.view.dataset_dir", return_value=str(directory)):
                payload, _ = build_payload("synthetic", "no_predictions")
            self.assertEqual(len(payload["clips"]), 4)
            self.assertEqual(len(payload["clips"][0]["positions"][0]), 23)
            json.dumps(payload, allow_nan=False)
            # Reject old files instead of passing the old long table to an algorithm.
            (directory / io.METADATA_FILE).unlink()
            with self.assertRaisesRegex(ValueError, "Legacy"):
                list(io.load_clips(directory))

    def test_synthetic_epts_through_actual_kloppy_and_loader(self):
        from kloppy import metrica

        with TemporaryDirectory() as temp:
            xml_path, raw_path = synthetic_epts(temp)
            dataset = metrica.load_tracking_epts(meta_data=xml_path, raw_data=raw_path)
            obs, metadata = from_kloppy(dataset, expected_frames=3)
            self.assertEqual(list(obs.columns), COLUMNS)
            self.assertEqual(obs.frame.tolist(), [0, 1, 2])
            self.assertTrue(obs.loc[0, ["ball_x", "ball_y"]].isna().all())
            self.assertEqual(obs.ball_x.iloc[1], 1.05)
            self.assertEqual(obs.ball_y.iloc[1], -0.02)
            np.testing.assert_allclose(obs["1_s"], 7.5)
            self.assertTrue(obs[["46_x", "46_y", "46_s"]].isna().all().all())
            self.assertEqual(metadata["slot_teams"]["1"], "H")
            self.assertEqual(metadata["slot_teams"]["46"], "A")
            self.assertEqual(metadata["pitch_length"], 105)
            self.assertEqual(metadata["pitch_width"], 68)
            self.assertEqual(predict_frames(placeholder, obs, metadata, {}).label.tolist(), ["X"] * 3)
            with patch("observations.atd.require", return_value=[xml_path, raw_path]) as paths, \
                    patch("observations.atd.source_frames", return_value=3):
                loaded, _ = load_tactical(data_dir=temp)
                pd.testing.assert_frame_equal(loaded, obs)
                paths.assert_called_once_with(["atd_meta", "atd_raw"], data_dir=temp, source="tactical")
            with patch("observations.atd.require", return_value=[xml_path, raw_path]), \
                    patch("observations.atd.source_frames", return_value=3), \
                    patch("simulation.run_algorithm.load_config", return_value={"algorithm": "placeholder"}), \
                    patch.object(io, "REPO_ROOT", temp), \
                    patch("sys.argv", ["run_algorithm", "--experiment", "synthetic", "--tactical"]), \
                    redirect_stdout(StringIO()):
                run_algorithm()
            written = pd.read_csv(Path(temp) / "outputs/synthetic/submission/placeholder.csv")
            self.assertEqual(written.to_dict("list"), {"frame": [0, 1, 2], "label": ["X"] * 3})
            with self.assertRaisesRegex(ValueError, "frame_id"):
                from_kloppy(dataset, expected_frames=4)
            dataset.records[1].frame_id = 1
            with self.assertRaisesRegex(ValueError, "frame_id"):
                from_kloppy(dataset, expected_frames=3)


if __name__ == "__main__":
    unittest.main()
