"""Story semantics and adversarial geometry, independent of any possession algorithm."""

import unittest

import numpy as np

from simulation.core import ClipBuilder, checks
from simulation.core.constants import FPS, PITCH_LENGTH, PITCH_WIDTH
from simulation.core.motion import BallFlight, BouncingBall, GroundTrap
from simulation.scenarios import all_subtypes


class LandingTests(unittest.TestCase):
    def test_landing_stories_ten_seeds_and_both_mirrors(self):
        registry = all_subtypes()
        for subtype in ("LC01", "LC02", "LC03", "LC04", "LC05"):
            for seed in range(10):
                pair = []
                for team in ("H", "A"):
                    with self.subTest(subtype=subtype, seed=seed, team=team):
                        rng = np.random.default_rng(seed)
                        b = ClipBuilder(rng, team)
                        registry[subtype][1](b, rng)
                        clip = b.finish()
                        pair.append(clip)
                        self.assertEqual(checks.run_all(clip), [])
                        expected = ["D", team]
                        opponent = "A" if team == "H" else "H"
                        if subtype in ("LC03", "LC04"):
                            expected.append(opponent)
                        if subtype == "LC05":
                            expected.append("D")
                        self.assertEqual(checks.collapse(clip.truth), expected)
                        flight = next(s for s in b._ball_segments if isinstance(s, BallFlight))
                        bounce = next(s for s in b._ball_segments if isinstance(s, BouncingBall))
                        distance = np.linalg.norm(np.array(flight.p1[:2]) - flight.p0[:2])
                        self.assertTrue(25 <= distance <= 50)
                        self.assertTrue(1.2 <= flight.t1 - flight.t0 <= 2.5)
                        for s in b._ball_segments:
                            if isinstance(s, GroundTrap):
                                self.assertTrue(3 - 1e-8 <= np.linalg.norm(s.incoming_velocity) <= 10 + 1e-8)
                        if subtype in ("LC01", "LC02"):
                            t = ((flight.t0 + flight.t1) / 2 if subtype == "LC01"
                                 else sum(bounce.hops[0][:2]) / 2)
                            # Check sampled geometry as well as the exact continuous apex.
                            t = round(t * FPS) / FPS
                            x, y, z = clip.ball_at(t)
                            reach = min(np.hypot(x - px, y - py)
                                        for _, side, px, py in clip.players_at(t) if side == opponent)
                            self.assertLess(reach, 1.3)
                            self.assertGreater(z, 3 if subtype == "LC01" else 2)
                            self.assertLessEqual(z, 8)
                            self.assertEqual(clip.truth[round(t * FPS)], team)
                        if subtype in ("LC03", "LC04"):
                            control = next(e for e in clip.events
                                           if e.kind == "control_start" and e.team == opponent)
                            self.assertEqual(clip.truth[control.frame - 1], team)
                            self.assertEqual(clip.truth[control.frame], opponent)
                            self.assertLess(control.t, b._ball_segments[-2].t1)
                            if subtype == "LC04":
                                self.assertTrue(0.5 <= control.t - bounce.t0 <= 2.0)
                        if subtype == "LC05":
                            self.assertFalse(any(t > flight.t0 for t in clip.contact_times))
                            out = next(e for e in clip.events if e.kind == "ball_out")
                            self.assertEqual(clip.truth[out.frame - 1], team)
                            self.assertEqual(clip.truth[out.frame], "D")
                home, away = pair
                np.testing.assert_allclose(away.frames[away.frames.object == "ball"][["x", "y"]],
                                           np.array([PITCH_LENGTH, PITCH_WIDTH])
                                           - home.frames[home.frames.object == "ball"][["x", "y"]])


class DeflectionTests(unittest.TestCase):
    def test_deflection_stories_ten_seeds_and_both_mirrors(self):
        registry = all_subtypes()
        for subtype in ("DC01", "DC02", "DC03"):
            for seed in range(10):
                pair = []
                for team in ("H", "A"):
                    with self.subTest(subtype=subtype, seed=seed, team=team):
                        rng = np.random.default_rng(seed)
                        b = ClipBuilder(rng, team)
                        registry[subtype][1](b, rng)
                        clip = b.finish()
                        pair.append(clip)
                        self.assertEqual(checks.run_all(clip), [])
                        touch = next(e for e in clip.events if e.kind == "incidental_touch")
                        receive = next(e for e in clip.events
                                       if e.kind == "control_start" and e.t > touch.t)
                        self.assertEqual(clip.truth[touch.frame:receive.frame],
                                         [team] * (receive.frame - touch.frame))
                        distance = np.linalg.norm(np.array(clip.ball_at(receive.t)[:2])
                                                  - clip.ball_at(touch.t)[:2])
                        if subtype == "DC01":
                            self.assertTrue(0.5 - 1e-8 <= distance <= 2 + 1e-8)
                        if subtype == "DC02":
                            self.assertTrue(2 - 1e-8 <= distance <= 5 + 1e-8)
                            self.assertTrue(0.4 <= receive.t - touch.t <= 1.2)
                        expected = ["D", team]
                        if subtype == "DC03":
                            opponent = "A" if team == "H" else "H"
                            expected.append(opponent)
                            self.assertEqual(clip.truth[receive.frame - 1], team)
                            self.assertEqual(clip.truth[receive.frame], opponent)
                        self.assertEqual(checks.collapse(clip.truth), expected)
                        incoming = next(s for s in b._ball_segments
                                        if abs(s.t1 - touch.t) < 1e-9)
                        outgoing = next(s for s in b._ball_segments
                                        if abs(s.t0 - touch.t) < 1e-9)
                        v0, v1 = np.array(incoming.velocity(touch.t)), np.array(outgoing.velocity(touch.t))
                        self.assertLess(np.linalg.norm(v1), np.linalg.norm(v0))
                        cosine = np.dot(v0, v1) / (np.linalg.norm(v0) * np.linalg.norm(v1))
                        self.assertLess(cosine, 0.99)
                home, away = pair
                self.assertEqual([{"H": "A", "A": "H", "D": "D"}[x]
                                  for x in home.truth], away.truth)
                np.testing.assert_allclose(away.frames[away.frames.object == "ball"][["x", "y"]],
                                           np.array([PITCH_LENGTH, PITCH_WIDTH])
                                           - home.frames[home.frames.object == "ball"][["x", "y"]])


if __name__ == "__main__":
    unittest.main()
