"""Event boundaries, ball-only masking, and feasible long-stoppage stories."""

from types import SimpleNamespace
import unittest

import numpy as np
import pandas as pd

from simulation.core import checks
from simulation.core.clip import ball_fully_out
from simulation.core.constants import FPS
from simulation.core.events import Event
from simulation.core.gaps import BallGapConfig, ball_gap_mask, intervals
from simulation.core.observe import observe
from simulation.generate import build_clips


class BallGapTests(unittest.TestCase):
    def test_three_policies_initial_wait_and_boundaries(self):
        clip = SimpleNamespace(n_frames=700, events=[Event("legal_restart", 1, "H"),
                               Event("stoppage", 4, None), Event("legal_restart", 24, "H")])
        for weights, policy in (((1, 0, 0), "whole"), ((0, 1, 0), "delayed"),
                                ((0, 0, 1), "visible")):
            for seed in range(10):
                config = BallGapConfig(weights, (2, 5), 0)
                mask, audit = ball_gap_mask(clip, seed, config)
                np.testing.assert_array_equal(mask, ball_gap_mask(clip, seed, config)[0])
                self.assertEqual(len(audit), 2)
                self.assertFalse(mask[25:100].any())
                self.assertFalse(mask[600:].any())
                for record in audit:
                    self.assertEqual(record["policy"], policy)
                    if policy == "visible":
                        self.assertFalse(mask.any())
                    else:
                        self.assertIn(record["dead_stop"] - record["missing_stop"], (0, 1))
                        delay = record["missing_start"] - record["dead_start"]
                        if record["missing_start"] < record["missing_stop"]:
                            self.assertTrue((0 <= delay <= 5) if policy == "whole"
                                            else (50 <= delay <= 130))
                            self.assertTrue(mask[record["missing_start"]:record["missing_stop"]].all())

    def test_live_short_gaps_cannot_merge_with_dead_gaps(self):
        clip = SimpleNamespace(n_frames=3000, events=[Event("legal_restart", 1, "H"),
                               Event("stoppage", 80, None)])
        mask, _ = ball_gap_mask(clip, 3, BallGapConfig((0, 0, 1), (2, 5), 1))
        runs = list(intervals(mask))
        self.assertGreater(len(runs), 20)
        for start, stop in runs:
            self.assertGreater(start, 25)
            self.assertLess(stop, 2000)
            self.assertIn(stop - start, (1, 2, 3, 4))

    def test_only_ball_coordinates_change_and_mirrors_share_mask(self):
        masks = []
        for item in build_clips(["ST01"], 1, 0):
            clip = item["clip"]
            truth = list(clip.truth)
            clean, meta = observe(clip, seed=0)
            masked, gap_meta = observe(clip, seed=0, gaps=BallGapConfig((1, 0, 0), (2, 5), 0))
            missing = masked.ball_x.isna().to_numpy()
            masks.append(missing)
            self.assertTrue(missing.any())
            self.assertEqual(meta, gap_meta)
            pd.testing.assert_frame_equal(clean.drop(columns=["ball_x", "ball_y"]),
                                          masked.drop(columns=["ball_x", "ball_y"]))
            pd.testing.assert_frame_equal(clean.loc[~missing], masked.loc[~missing])
            self.assertTrue(masked.loc[missing, ["ball_x", "ball_y"]].isna().all().all())
            self.assertEqual(clip.truth, truth)
        np.testing.assert_array_equal(*masks)


class StoppageStoryTests(unittest.TestCase):
    def test_fifty_seeds_both_mirrors(self):
        fast_whistles = 0
        for subtype in ("ST01", "ST02", "ST03", "ST04"):
            for seed in range(50):
                pair = build_clips([subtype], 1, seed)
                for item in pair:
                    with self.subTest(subtype=subtype, seed=seed, team=item["initiating_team"]):
                        clip = item["clip"]
                        self.assertEqual(checks.run_all(clip), [])
                        team = item["initiating_team"]
                        opponent = "A" if team == "H" else "H"
                        self.assertEqual(checks.collapse(clip.truth),
                                         ["D", team, "D", team if subtype == "ST01" else opponent])
                        dead = next(e for e in clip.events if e.kind in ("stoppage", "ball_out"))
                        restart = next(e for e in clip.events if e.kind == "legal_restart" and e.t > dead.t)
                        self.assertEqual(clip.truth[dead.frame - 1], team)
                        self.assertEqual(clip.truth[dead.frame], "D")
                        self.assertEqual(clip.truth[restart.frame - 1], "D")
                        duration = restart.t - dead.t
                        self.assertGreaterEqual(duration, 30 if subtype == "ST04" else 5)
                        self.assertLessEqual(duration, 90 if subtype == "ST04" else 30)
                        dt = 0.001
                        for kick in (e for e in clip.events if e.kind == "legal_restart"):
                            speed = np.linalg.norm(np.subtract(clip.ball_at(kick.t + dt)[:2],
                                                              clip.ball_at(kick.t)[:2])) / dt
                            self.assertGreaterEqual(speed, 10 - 0.01)
                            self.assertLessEqual(speed, 25 + 0.01)
                        if subtype in ("ST03", "ST04"):
                            speed = np.linalg.norm(np.subtract(clip.ball_at(dead.t + dt)[:2],
                                                              clip.ball_at(dead.t)[:2])) / dt
                            self.assertGreaterEqual(speed, 12)
                            self.assertLessEqual(speed, 18.1)
                            self.assertFalse(ball_fully_out(clip.ball_at(dead.t - dt)))
                            self.assertTrue(ball_fully_out(clip.ball_at(dead.t + dt)))
                            reception = next(t for t in clip.contact_times if t > dead.t)
                            self.assertLess(reception, restart.t)
                            self.assertEqual(clip.truth[int(np.ceil(reception * FPS))], "D")
                            self.assertFalse(any(e.kind == "control_start"
                                                 and dead.t < e.t < restart.t for e in clip.events))
                            # The full final live-frame interval must also contain a fast shot.
                            last_live = dead.frame - 1
                            frame_speed = np.linalg.norm(np.subtract(
                                clip.ball_at(last_live / FPS)[:2],
                                clip.ball_at((last_live - 1) / FPS)[:2])) * FPS
                            self.assertGreater(frame_speed, 12)
                        if subtype == "ST01":
                            speed = np.linalg.norm(np.subtract(clip.ball_at(dead.t + dt)[:2],
                                                              clip.ball_at(dead.t)[:2])) / dt
                            fast_whistles += int(speed > 5)
                self.assertEqual([{"D": "D", "H": "A", "A": "H"}[x]
                                  for x in pair[0]["clip"].truth], pair[1]["clip"].truth)
        self.assertGreater(fast_whistles, 20)


if __name__ == "__main__":
    unittest.main()
