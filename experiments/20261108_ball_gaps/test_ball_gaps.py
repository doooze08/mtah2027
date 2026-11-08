"""Verify known artificial ball gaps without loading any match data."""

import unittest

import numpy as np
import pandas as pd

from ball_gaps import summarize
from observations.schema import COLUMNS


class BallGapTests(unittest.TestCase):
    def test_injected_gaps_are_counted(self):
        observations = pd.DataFrame(np.nan, index=range(100), columns=COLUMNS)
        observations["frame"] = np.arange(100)
        observations[["ball_x", "ball_y"]] = 0.5
        observations.loc[10:11, "ball_x"] = np.nan
        observations.loc[30:39, "ball_y"] = np.nan
        observations.loc[60:84, ["ball_x", "ball_y"]] = np.nan
        metadata = {"fps": 25, "pitch_length": 105, "pitch_width": 68}

        report = summarize([(observations, metadata)])

        self.assertEqual(report["missing_frames"], 37)
        self.assertEqual(report["missing_fraction"], 0.37)
        self.assertEqual(report["gap_count"], 3)
        self.assertEqual(report["gap_length_frames"]["p50"], 10)
        self.assertEqual(report["gap_length_frames"]["max"], 25)
        self.assertEqual(report["gap_length_s"]["p50"], 0.4)
        self.assertEqual([b["missing_frames"] for b in report["duration_bins_s"].values()],
                         [2, 10, 25, 0, 0])


if __name__ == "__main__":
    unittest.main()
