"""Verify known artificial ball gaps without loading any match data."""

import json
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from observations.schema import COLUMNS

ball_gaps = import_module("experiments.20261108_ball_gaps.ball_gaps")


class BallGapTests(unittest.TestCase):
    def test_injected_gaps_are_counted(self):
        observations = pd.DataFrame(np.nan, index=range(100), columns=COLUMNS)
        observations["frame"] = np.arange(100)
        observations[["ball_x", "ball_y"]] = 0.5
        observations.loc[10:11, "ball_x"] = np.nan
        observations.loc[30:39, "ball_y"] = np.nan
        observations.loc[60:84, ["ball_x", "ball_y"]] = np.nan
        metadata = {"fps": 25, "pitch_length": 105, "pitch_width": 68}

        report = ball_gaps.summarize([(observations, metadata)])

        self.assertEqual(report["missing_frames"], 37)
        self.assertEqual(report["missing_fraction"], 0.37)
        self.assertEqual(report["gap_count"], 3)
        self.assertEqual(report["gap_length_frames"]["p50"], 10)
        self.assertEqual(report["gap_length_frames"]["max"], 25)
        self.assertEqual(report["gap_length_s"]["p50"], 0.4)
        self.assertEqual([b["missing_frames"] for b in report["duration_bins_s"].values()],
                         [2, 10, 25, 0, 0])

        # A masked gap spanning a synthetic halftime must become two censored gaps.
        observations.loc[48:59, ["ball_x", "ball_y"]] = np.nan
        with tempfile.TemporaryDirectory() as tmp, \
                patch("observations.atd.load_tactical", return_value=(observations, metadata)), \
                patch("games.half_video_blocks", return_value=[(1, 0, 49), (2, 60, 99)]):
            output = Path(tmp) / "report"
            ball_gaps.main(["--data-dir", "synthetic-only", "--out", str(output)])
            report = json.loads((output / "statistics.json").read_text())
        self.assertEqual(report["clip_count"], 2)
        self.assertEqual(report["total_frames"], 90)
        self.assertEqual(report["missing_frames"], 39)
        self.assertEqual(report["gap_count"], 4)
        self.assertEqual(report["gap_length_frames"]["max"], 25)
        self.assertEqual(report["censored_gap_count"], 2)
        self.assertEqual(report["reappearance_jump_m"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
