"""Check aggregate statistics with synthetic coordinates; never load match assets."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from observations.ball_gaps import main, markdown, summarize
from observations.schema import COLUMNS, SLOTS


def fixture(n=100):
    observations = pd.DataFrame(np.nan, index=range(n), columns=COLUMNS)
    observations["frame"] = np.arange(n)
    x = 10 + 2 * np.arange(n) / 25
    observations["ball_x"] = x / 105
    observations["ball_y"] = 10 / 68
    observations["1_x"] = (x + 3) / 105
    observations["1_y"] = 10 / 68
    observations["2_x"] = (x + 20) / 105
    observations["2_y"] = 10 / 68
    metadata = {"fps": 25, "pitch_length": 105, "pitch_width": 68,
                "slot_teams": {s: "H" if int(s) <= 24 else "A" for s in SLOTS}}
    return observations, metadata


def masked_fixture():
    observations, metadata = fixture()
    observations.loc[10:11, "ball_x"] = np.nan
    observations.loc[30:39, "ball_y"] = np.nan
    observations.loc[60:84, ["ball_x", "ball_y", "2_y"]] = np.nan
    return observations, metadata


class BallGapTests(unittest.TestCase):
    def test_known_lengths_context_jumps_and_player_counts(self):
        observations, metadata = masked_fixture()
        report = summarize([(observations, metadata)])
        self.assertEqual(report["missing_frames"], 37)
        self.assertEqual(report["missing_fraction"], 0.37)
        self.assertEqual(report["gap_count"], 3)
        self.assertEqual(report["complete_gap_count"], 3)
        for key, expected in (("p10", 3.6), ("p50", 10), ("p90", 22),
                              ("p99", 24.7), ("max", 25)):
            self.assertAlmostEqual(report["gap_length_frames"][key], expected)
        self.assertEqual(report["gap_length_s"]["p50"], 0.4)
        for name, frames in (("<0.2", 2), ("[0.2, 1)", 10), ("[1, 5)", 25)):
            stats = report["duration_bins_s"][name]
            self.assertEqual(stats["missing_frames"], frames)
            self.assertAlmostEqual(stats["fraction_of_missing_frames"], frames / 37)
        for side in ("before", "after"):
            context = report["context"][side]
            self.assertAlmostEqual(context["speed_m_s"]["p50"], 2)
            self.assertAlmostEqual(context["nearest_player_m"]["p50"], 3)
            self.assertAlmostEqual(context["touchline_m"]["p50"], 10)
            self.assertEqual(context["speed_m_s"]["bins"]["[1, 3)"]["count"], 3)
        self.assertAlmostEqual(report["context"]["before"]["goal_line_m"]["p50"], 12.32)
        self.assertAlmostEqual(report["context"]["after"]["goal_line_m"]["p50"], 13.2)
        self.assertAlmostEqual(report["reappearance_jump_m"]["p50"], 0.88)
        self.assertAlmostEqual(report["reappearance_jump_m"]["max"], 2.08)
        counts = report["visible_players_during_gaps"]["counts"]
        self.assertEqual(counts["1"], 25)
        self.assertEqual(counts["2"], 12)
        self.assertEqual(sum(counts.values()), 37)
        self.assertNotIn("NaN", json.dumps(report, allow_nan=False))

    def test_clip_edges_all_missing_empty_and_no_gaps(self):
        a, meta = fixture(5)
        b, _ = fixture(5)
        a.loc[3:, ["ball_x", "ball_y"]] = np.nan
        b.loc[:1, ["ball_x", "ball_y"]] = np.nan
        report = summarize([(a, meta), (b, meta)])
        self.assertEqual(report["gap_count"], 2)
        self.assertEqual(report["complete_gap_count"], 0)
        self.assertEqual(report["left_censored_gap_count"], 1)
        self.assertEqual(report["right_censored_gap_count"], 1)
        self.assertEqual(report["reappearance_jump_m"]["count"], 0)
        self.assertEqual(report["context"]["before"]["speed_m_s"]["unavailable_count"], 1)
        a[["ball_x", "ball_y"]] = np.nan
        report = summarize([(a, meta)])
        self.assertEqual(report["censored_gap_count"], 1)
        self.assertEqual(report["left_censored_gap_count"], 1)
        self.assertEqual(report["right_censored_gap_count"], 1)
        self.assertIsNone(report["reappearance_jump_m"]["p50"])
        for obs in (fixture()[0], a.iloc[:0]):
            report = summarize([(obs, meta)])
            self.assertEqual(report["gap_count"], 0)
            self.assertEqual(report["missing_frames"], 0)
            json.dumps(report, allow_nan=False)
            self.assertIn("球位置缺失统计", markdown(report))

    def test_duration_endpoints_and_unavailable_speed(self):
        clips = []
        for length in (4, 5, 25, 125, 750, 751):
            obs, meta = fixture(length + 2)
            obs.loc[1:length, ["ball_x", "ball_y"]] = np.nan
            clips.append((obs, meta))
        report = summarize(clips)
        self.assertEqual([b["gap_count"] for b in report["duration_bins_s"].values()],
                         [1, 1, 1, 2, 1])
        for side in ("before", "after"):
            self.assertEqual(report["context"][side]["speed_m_s"]["unavailable_count"], 6)
        self.assertEqual(report["reappearance_jump_m"]["count"], 6)

    def test_signed_boundary_distances_and_no_players(self):
        obs, meta = fixture(5)
        obs[[s + "_" + axis for s in SLOTS for axis in ("x", "y")]] = np.nan
        obs["ball_x"] = -2 / 105
        obs["ball_y"] = 69 / 68
        obs.loc[2, "ball_x"] = np.nan
        report = summarize([(obs, meta)])
        for side in ("before", "after"):
            context = report["context"][side]
            self.assertEqual(context["goal_line_m"]["p50"], -2)
            self.assertAlmostEqual(context["touchline_m"]["p50"], -1)
            self.assertEqual(context["nearest_player_m"]["unavailable_count"], 1)
        self.assertEqual(report["visible_players_during_gaps"]["counts"]["0"], 1)

    def test_simulation_cli_only_reads_observations_and_metadata(self):
        obs, meta = masked_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "synthetic"
            directory.mkdir()
            obs.assign(clip="synthetic_only").to_csv(directory / "observations.csv", index=False)
            (directory / "metadata.json").write_text(json.dumps({"synthetic_only": meta}))
            output = Path(temporary) / "report"
            with patch("simulation.core.io.SIMULATION_SETS", temporary), patch(
                    "observations.atd.load_tactical", side_effect=AssertionError("Forbidden")):
                main(["--dataset", "synthetic", "--out", str(output)])
            report = json.loads((output / "statistics.json").read_text())
            reloaded = pd.read_csv(directory / "observations.csv").drop(columns="clip")
            self.assertEqual(report, summarize([(reloaded, meta)]))
            text = (output / "summary.md").read_text()
            self.assertNotIn("synthetic_only", text)
            self.assertLessEqual(len(text.splitlines()), 40)


if __name__ == "__main__":
    unittest.main()
