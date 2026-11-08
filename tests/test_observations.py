"""Mapping, speed and real-loader tests; match assets and labels are never opened here."""

from datetime import timedelta
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from algorithms.placeholder import predict as placeholder
from observations import COLUMNS, SLOTS
from observations.atd import from_kloppy, load_tactical
from simulation.core.observe import observe
from simulation.run_algorithm import predict_frames


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


def tracking_dataset():
    """Build actual kloppy objects, including an unobserved slot and a missing ball."""
    from kloppy.domain import (DatasetFlag, Frame, Ground, Metadata, NormalizedPitchDimensions,
                               Orientation, Period, Player, PlayerData, Point, Point3D,
                               Provider, Team, TrackingDataset, build_coordinate_system)

    home, away = Team("h", "home", Ground.HOME), Team("a", "away", Ground.AWAY)
    for i in range(1, 47):
        team = home if i <= 24 else away
        team.players.append(Player("Track_{}".format(i), team, i))
    players = {player: PlayerData(Point(0.2, 0.3), speed=7.5)
               for team in (home, away) for player in team.players}
    players[away.players[-1]] = PlayerData(None)
    period = Period(1, timedelta(0), timedelta(seconds=1))
    metadata = Metadata(periods=[period], teams=[away, home],
                        coordinate_system=build_coordinate_system(Provider.METRICA, 105, 68),
                        pitch_dimensions=NormalizedPitchDimensions(pitch_length=105, pitch_width=68),
                        orientation=Orientation.NOT_SET, flags=DatasetFlag(0),
                        provider=Provider.METRICA, frame_rate=25)
    records = [Frame(period, timedelta(seconds=i/25), [], None, None, i+1, players, {},
                     Point3D(np.nan, np.nan, np.nan) if i == 0 else Point3D(1.05, -0.02, 8))
               for i in range(3)]
    return TrackingDataset(records, metadata)


class ObservationTests(unittest.TestCase):
    def test_mapping_speed_and_reproducibility(self):
        world = moving_world()
        obs, metadata = observe(world, seed=12)
        again, same_meta = observe(world, seed=12)
        pd.testing.assert_frame_equal(obs, again)
        self.assertEqual(metadata, same_meta)
        self.assertFalse(obs.equals(observe(world, seed=13)[0]))
        self.assertEqual(list(obs.columns), COLUMNS)
        self.assertEqual(set(metadata["slot_teams"]), set(SLOTS))
        self.assertEqual(list(metadata["slot_teams"].values()).count("H"), 24)
        self.assertEqual(list(metadata["slot_teams"].values()).count("A"), 22)
        active = [s for s in SLOTS if obs[s + "_x"].notna().any()]
        self.assertEqual(len(active), 22)
        self.assertEqual([metadata["slot_teams"][s] for s in active].count("H"), 11)
        for slot in active:
            np.testing.assert_allclose(obs[slot + "_s"], 5.0, atol=1e-10)
            start = int(round(obs[slot + "_x"].iloc[0] * 105))
            self.assertEqual(metadata["slot_teams"][slot], "H" if start <= 11 else "A")
            np.testing.assert_allclose(obs[slot + "_x"] * 105, start + 3 * np.arange(4) / 25)
        for slot in set(SLOTS) - set(active):
            self.assertTrue(obs[[slot + "_" + f for f in ("x", "y", "s")]].isna().all().all())
        self.assertTrue((obs.ball_x > 1).all())
        self.assertTrue((obs.ball_y < 0).all())
        world.frames["z"] = 999
        pd.testing.assert_frame_equal(observe(world, seed=12)[0], obs)
        self.assertEqual(predict_frames(placeholder, obs, metadata, {}).label.tolist(), ["X"] * 4)

    def test_real_loader(self):
        dataset = tracking_dataset()
        obs, metadata = from_kloppy(dataset, expected_frames=3)
        self.assertEqual(list(obs.columns), COLUMNS)
        self.assertEqual(obs.frame.tolist(), [0, 1, 2])
        self.assertTrue(obs.loc[0, ["ball_x", "ball_y"]].isna().all())
        self.assertEqual(obs.ball_x.iloc[1], 1.05)
        self.assertEqual(obs.ball_y.iloc[1], -0.02)
        np.testing.assert_allclose(obs["1_s"], 7.5)
        self.assertTrue(obs[["46_x", "46_y", "46_s"]].isna().all().all())
        self.assertEqual(metadata["slot_teams"]["24"], "H")
        self.assertEqual(metadata["slot_teams"]["25"], "A")
        self.assertEqual(metadata["pitch_length"], 105)
        self.assertEqual(metadata["pitch_width"], 68)
        with TemporaryDirectory() as temp, \
                patch("observations.atd.require", return_value=["meta.xml", "raw.txt"]) as paths, \
                patch("observations.atd.source_frames", return_value=3), \
                patch("kloppy.metrica.load_tracking_epts", return_value=dataset) as load:
            loaded, loaded_metadata = load_tactical(data_dir=temp)
            pd.testing.assert_frame_equal(loaded, obs)
            self.assertEqual(loaded_metadata, metadata)
            paths.assert_called_once_with(["atd_meta", "atd_raw"], data_dir=temp, source="tactical")
            load.assert_called_once_with(meta_data="meta.xml", raw_data="raw.txt")


if __name__ == "__main__":
    unittest.main()
