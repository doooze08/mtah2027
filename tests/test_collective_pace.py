"""Opt-in collective background pace, long live-ball gaps and ST05.

These tests use synthetic scenarios only. They check that the default renderer is
unchanged and that the new switches do what their names say; they do not validate a
collective-speed possession algorithm.
"""

import unittest

import numpy as np
import pandas as pd

from simulation.core import checks
from simulation.core.constants import FPS
from simulation.core.gaps import BallGapConfig, ball_gap_mask, intervals
from simulation.core.observe import observe
from simulation.core.pace import DEAD_MEDIAN_RANGE, LIVE_MEDIAN_RANGE
from simulation.generate import build_clips


def _median_speed(clip, frame):
    """Median of the 22 player speeds at one frame, in m/s."""
    before = clip.players_at((frame - 1) / FPS)
    after = clip.players_at(frame / FPS)
    speeds = [np.hypot(b[2] - a[2], b[3] - a[3]) * FPS for a, b in zip(before, after)]
    return float(np.median(speeds))


class CollectivePaceTests(unittest.TestCase):
    def test_default_is_unchanged_and_ball_stays_clean(self):
        for subtype in ("ST01", "TI01"):
            default = build_clips([subtype], 1, 0)
            explicit_off = build_clips([subtype], 1, 0, collective_pace=False)
            paced = build_clips([subtype], 1, 0, collective_pace=True)
            for off, explicit, on in zip(default, explicit_off, paced):
                pd.testing.assert_frame_equal(off["clip"].frames, explicit["clip"].frames)
                self.assertIsNone(off["clip"].collective_pace)
                self.assertEqual(off["clip"].truth, on["clip"].truth)
                self.assertEqual(off["clip"].events, on["clip"].events)
                ball = off["clip"].frames["object"] == "ball"
                pd.testing.assert_frame_equal(off["clip"].frames[ball], on["clip"].frames[ball])
                self.assertIsNotNone(on["clip"].collective_pace)

    def test_targets_and_counterexample_ranges(self):
        pair = build_clips(["ST01"], 1, 0, collective_pace=True)
        first, second = (item["clip"].collective_pace for item in pair)
        for field in ("live_target", "dead_target", "dead_transition", "live_transition",
                      "dead_fast", "live_slow"):
            self.assertEqual(first[field], second[field])
        for item in pair:
            clip = item["clip"]
            audit = clip.collective_pace
            self.assertGreaterEqual(audit["n_background"], 12)
            self.assertTrue(1.4 <= audit["live_target"] <= 2.4)
            self.assertTrue(0.5 <= audit["dead_target"] <= 1.4)
            self.assertTrue(1.0 <= audit["dead_transition"] <= 3.0)
            self.assertTrue(1.0 <= audit["live_transition"] <= 3.0)
            self.assertEqual(checks.run_all(clip), [])
            for interval in audit["intervals"]:
                if interval["counterexample"]:
                    if interval["counterexample"] == "dead_fast":
                        self.assertTrue(1.8 <= interval["target"] <= 2.6)
                    else:
                        self.assertTrue(0.25 <= interval["target"] <= 0.85)
                    continue
                frame = int(0.5 * (interval["start"] + interval["stop"]) * FPS)
                if frame < 1 or frame >= clip.n_frames:
                    continue
                target = interval["target"]
                self.assertAlmostEqual(_median_speed(clip, frame), target, delta=0.12)

    def test_generated_f1_medians_stay_in_ranges(self):
        built = build_clips(["ST01"], 5, 0, collective_pace=True)
        live, dead = [], []
        for item in built:
            clip = item["clip"]
            for frame in range(1, clip.n_frames):
                speed = _median_speed(clip, frame)
                (live if clip.truth[frame] in ("H", "A") else dead).append(speed)
        self.assertGreaterEqual(np.median(live), LIVE_MEDIAN_RANGE[0])
        self.assertLessEqual(np.median(live), LIVE_MEDIAN_RANGE[1])
        self.assertGreaterEqual(np.median(dead), DEAD_MEDIAN_RANGE[0])
        self.assertLessEqual(np.median(dead), DEAD_MEDIAN_RANGE[1])

    def test_counterexamples_appear_but_do_not_dominate(self):
        built = build_clips(["ST01"], 40, 0, collective_pace=True)
        dead_fast = sum(item["clip"].collective_pace["dead_fast"] for item in built)
        live_slow = sum(item["clip"].collective_pace["live_slow"] for item in built)
        self.assertGreater(dead_fast, 0)
        self.assertGreater(live_slow, 0)
        self.assertLess(dead_fast, len(built) * 0.5)
        self.assertLess(live_slow, len(built) * 0.5)
        for item in built:
            audit = item["clip"].collective_pace
            for interval in audit["intervals"]:
                if interval["counterexample"] == "dead_fast":
                    self.assertGreater(interval["target"], audit["dead_target"])
                if interval["counterexample"] == "live_slow":
                    self.assertLess(interval["target"], audit["live_target"])


class LiveLongGapTests(unittest.TestCase):
    def test_long_gaps_change_only_the_ball(self):
        # Seed 3 is one of the BP02 stories whose ~14 s live interval can hold a 5-15 s gap.
        clip = build_clips(["BP02"], 1, 3)[0]["clip"]
        config = BallGapConfig((0, 0, 1), (2, 5), 0.0, live_long_gaps_per_second=0.2)
        mask, _ = ball_gap_mask(clip, 3, config)
        long_runs = [(start, stop) for start, stop in intervals(mask) if stop - start >= 125]
        self.assertTrue(long_runs)
        for start, stop in long_runs:
            self.assertLessEqual(stop - start, 375)
            self.assertFalse(mask[start - 1])
            self.assertFalse(mask[stop])
        clean, meta = observe(clip, seed=3)
        masked, gap_meta = observe(clip, seed=3, gaps=config)
        self.assertEqual(meta, gap_meta)
        missing = masked["ball_x"].isna().to_numpy()
        np.testing.assert_array_equal(missing, mask)
        pd.testing.assert_frame_equal(clean.drop(columns=["ball_x", "ball_y"]),
                                      masked.drop(columns=["ball_x", "ball_y"]))
        pd.testing.assert_frame_equal(clean.loc[~missing], masked.loc[~missing])
        self.assertTrue(masked.loc[missing, ["ball_x", "ball_y"]].isna().all().all())


class StoppageDeliveryTests(unittest.TestCase):
    def test_st05_truth_stays_dead_until_the_actual_kick(self):
        pair = build_clips(["ST05"], 1, 0)
        self.assertEqual(len(pair), 2)
        for item in pair:
            clip = item["clip"]
            team = item["initiating_team"]
            self.assertEqual(clip.expected_sequence, ["D", team, "D", team])
            self.assertEqual(checks.run_all(clip), [])
            dead = next(e for e in clip.events if e.kind == "stoppage")
            restart = next(e for e in clip.events
                           if e.kind == "legal_restart" and e.t > dead.t)
            self.assertEqual(clip.truth[dead.frame], "D")
            self.assertEqual(clip.truth[restart.frame - 1], "D")
            self.assertEqual(clip.truth[restart.frame], team)
            self.assertFalse(any(e.kind == "control_start" and dead.t < e.t < restart.t
                                 for e in clip.events))
            # The dead-ball pass and the setting touch do move the ball, but not the answer.
            moved = np.linalg.norm(np.subtract(clip.ball_at(dead.t + 2.0)[:2],
                                               clip.ball_at(dead.t)[:2]))
            self.assertGreater(moved, 0.5)
            self.assertEqual(clip.truth[dead.frame:restart.frame], ["D"] * (restart.frame - dead.frame))


if __name__ == "__main__":
    unittest.main()
