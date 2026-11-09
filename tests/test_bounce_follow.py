"""Damped impacts, continuous formation motion, actor priority and opt-in behavior."""

import unittest

import numpy as np
import pandas as pd

from simulation.core import ClipBuilder, checks
from simulation.core.constants import BALL_RADIUS, FPS, GRAVITY, PITCH_LENGTH, PITCH_WIDTH
from simulation.core.motion import BouncingBall, FormationFollow
from simulation.examples.bounce_follow import build_example
from simulation.scenarios import all_subtypes


class BounceTests(unittest.TestCase):
    def test_separate_first_impact_retention_and_rolling_reception(self):
        b = ClipBuilder(np.random.default_rng(3), "H")
        receiver = b.player("atk", "ls")
        b.place_ball(b.player("atk", "lcb"))
        b.bounce_to(2, point=(52, 42), bounces=2,
                    first_horizontal_retention=0.6, horizontal_retention=0.9,
                    roll_seconds=0.2)
        flight, bounce = b._ball_segments[-2:]
        vx = flight.velocity(bounce.t0)[0]
        np.testing.assert_allclose([v[0] for v in bounce.hop_velocities],
                                   [vx * 0.6, vx * 0.6 * 0.9])
        self.assertAlmostEqual(bounce.velocity(bounce.roll_start)[0], vx * 0.6 * 0.9 ** 2)
        self.assertAlmostEqual(b.now, bounce.roll_start + 0.2)
        before = bounce.position(b.now)
        b.start_at(receiver, before[:2])
        velocity = bounce.velocity(b.now)[:2]
        b.trap(receiver, 0.2)
        trap = b._ball_segments[-1]
        np.testing.assert_allclose(trap.position(trap.t0), before)
        np.testing.assert_allclose(trap.velocity(trap.t0), velocity)
        self.assertIn(trap.t0, b._contacts)

    def test_initial_flight_is_unchanged_and_joins_the_first_rebound(self):
        b = ClipBuilder(np.random.default_rng(3), "H")
        b.place_ball(b.player("atk", "lcb"))
        b.bounce_to(1.2, point=(38, 42))
        flight, bounce = b._ball_segments[-2:]
        np.testing.assert_allclose(flight.position(bounce.t0), bounce.position(bounce.t0))
        np.testing.assert_allclose(np.array(flight.velocity(bounce.t0)[:2]) * bounce.horizontal_retention,
                                   bounce.velocity(bounce.t0)[:2])
        self.assertLess(flight.velocity(bounce.t0)[2], 0)
        self.assertGreater(bounce.velocity(bounce.t0)[2], 0)
        for t in np.linspace(0, bounce.t0, 21, endpoint=False):
            self.assertEqual(b.ball_position(t), flight.position(t))

    def test_peaks_decay_and_transition_to_ground_roll(self):
        for restitution in (0.4, 0.55, 0.7):
            motion = BouncingBall(1, (10, 20), (6, 2, -6), restitution=restitution)
            peaks = [motion.position((start + stop) / 2)[2] - BALL_RADIUS
                     for start, stop, _ in motion.hops]
            self.assertEqual(len(peaks), 3)
            self.assertTrue(np.all(np.diff(peaks) < 0))
            np.testing.assert_allclose(np.array(peaks[1:]) / peaks[:-1], restitution ** 2)
            self.assertAlmostEqual(peaks[0], (6 * restitution) ** 2 / (2 * GRAVITY))
            for t in np.linspace(motion.t0, motion.stop_time + 1, 501):
                self.assertGreaterEqual(motion.position(t)[2], BALL_RADIUS - 1e-9)
            for impact in motion.ground_impacts[1:]:
                self.assertAlmostEqual(motion.position(impact)[2], BALL_RADIUS)
                np.testing.assert_allclose(motion.position(impact - 1e-8),
                                           motion.position(impact + 1e-8), atol=2e-7, rtol=0)
                np.testing.assert_allclose(np.array(motion.velocity(impact - 1e-8)[:2])
                                           * motion.horizontal_retention,
                                           motion.velocity(impact + 1e-8)[:2], atol=1e-7, rtol=0)
            np.testing.assert_allclose(motion.velocity(motion.stop_time), (0, 0, 0), atol=1e-9)
            stopped = motion.position(motion.stop_time)
            np.testing.assert_allclose(motion.position(motion.stop_time + 10), stopped)
            earlier = motion.position(1.25)
            motion.t1 += 10
            self.assertEqual(motion.position(1.25), earlier)

    def test_vertical_bounces_can_end_stationary(self):
        motion = BouncingBall(0, (20, 30), (0, 0, -5))
        self.assertIsNone(motion.roll)
        self.assertEqual(motion.position(motion.stop_time + 1), (20, 30, BALL_RADIUS))
        self.assertEqual(motion.velocity(motion.stop_time + 1), (0, 0, 0))

    def test_horizontal_losses_include_first_and_final_ground_impacts(self):
        for retention in (0.0, 0.75, 1.0):
            motion = BouncingBall(0, (0, 0), (11.6, 0, -5.886), horizontal_retention=retention)
            expected_hops = [11.6 * retention ** (i + 1) for i in range(3)]
            np.testing.assert_allclose([v[0] for v in motion.hop_velocities], expected_hops)
            expected_roll_speed = 11.6 * retention ** 4
            self.assertAlmostEqual(motion.velocity(motion.roll_start)[0], expected_roll_speed)
            bounce_distance = sum(v * (stop - start) for v, (start, stop, _) in
                                  zip(expected_hops, motion.hops))
            roll_distance = expected_roll_speed ** 2 / (2 * motion.deceleration)
            self.assertAlmostEqual(motion.position(motion.stop_time)[0], bounce_distance + roll_distance)
            if retention == 0:
                self.assertIsNone(motion.roll)
            elif retention == 1:
                self.assertAlmostEqual(bounce_distance, 11.6 * (motion.roll_start - motion.t0))

    def test_builder_impacts_are_not_player_contacts_or_truth_events(self):
        clip = build_example()
        self.assertEqual(checks.run_all(clip), [])
        self.assertEqual(clip.contact_times, [1.0])
        self.assertEqual(len(clip.ground_impacts), 4)
        self.assertEqual([e.kind for e in clip.events], ["legal_restart"])
        self.assertEqual(checks.collapse(clip.truth), ["D", "H"])
        clip.ground_impacts = [1.6]  # An airborne point must never justify a ground impulse.
        self.assertTrue(checks.check_ground_impacts(clip))
        clip.ground_impacts = []
        self.assertTrue(checks.check_ball_motion(clip))


class FormationFollowTests(unittest.TestCase):
    def test_pairs_follow_without_changing_actors_ball_or_truth(self):
        for seed in range(10):
            for team in ("H", "A"):
                with self.subTest(seed=seed, team=team):
                    off = build_example(seed, team, False)
                    on = build_example(seed, team, True)
                    self.assertEqual(checks.run_all(on), [])
                    self.assertEqual(on.events, off.events)
                    self.assertEqual(on.truth, off.truth)
                    self.assertEqual(on.ground_impacts, off.ground_impacts)
                    self.assertEqual(on.contact_times, off.contact_times)
                    pd.testing.assert_frame_equal(on.frames[on.frames.object == "ball"],
                                                  off.frames[off.frames.object == "ball"])
                    actors = {"p03", "p22"} if team == "H" else {"p14", "p11"}
                    reference_offset = None
                    for obj in sorted(set(on.frames.object) - {"ball"}):
                        original = off.frames[off.frames.object == obj][["x", "y"]].to_numpy()
                        followed = on.frames[on.frames.object == obj][["x", "y"]].to_numpy()
                        if obj in actors:
                            np.testing.assert_array_equal(original, followed)
                        else:
                            offset = followed - original
                            self.assertGreater(np.linalg.norm(offset[-1]), 0.5)
                            if reference_offset is None:
                                reference_offset = offset
                            else:
                                np.testing.assert_allclose(offset, reference_offset, atol=1e-12)
                            self.assertTrue((followed[:, 0] >= 0).all())
                            self.assertTrue((followed[:, 0] <= PITCH_LENGTH).all())
                            self.assertTrue((followed[:, 1] >= 0).all())
                            self.assertTrue((followed[:, 1] <= PITCH_WIDTH).all())
                    for t in np.arange(2, 3, 1 / FPS):
                        before = np.array([p[2:] for p in on.players_at(t - 1e-8)])
                        after = np.array([p[2:] for p in on.players_at(t + 1e-8)])
                        np.testing.assert_allclose(before, after, atol=1e-6, rtol=0)

    def test_filter_has_continuous_velocity_even_at_target_steps(self):
        curve = FormationFollow(lambda t: (30 if t >= 1 else 0, 0, 0),
                                8, (-6, -6), (6, 6), FPS)
        self.assertGreater(curve.position(8)[0], 5)
        for t in np.arange(0.5, 7.5, 1 / FPS):
            epsilon = 1e-5
            left = (curve.position(t) - curve.position(t - epsilon)) / epsilon
            right = (curve.position(t + epsilon) - curve.position(t)) / epsilon
            np.testing.assert_allclose(left, right, atol=1e-3, rtol=0)
        positions = np.array([curve.position(t) for t in np.arange(0, 8, 1 / FPS)])
        speed, acceleration = checks._speed_and_acceleration(positions)
        self.assertLess(speed.max(), checks.PLAYER_MAX_SPEED)
        self.assertLess(acceleration.max(), checks.PLAYER_MAX_ACCELERATION)

    def test_explicit_stillness_and_random_stream_take_priority(self):
        clips, next_random = [], []
        for enabled in (False, True):
            rng = np.random.default_rng(4)
            b = ClipBuilder(rng, "H", follow_ball=enabled)
            passer = b.player("atk", "lcb")
            guard = b.player("atk", "gk")
            guard.add_still(0, 20)
            b.place_ball(passer)
            b.hold(passer, 1)
            b.event("legal_restart", team="atk")
            b.begin_core()
            b.bounce_to(1.2, point=(38, 42))
            b.end_core()
            b.expect("D", "atk")
            clips.append(b.finish())
            next_random.append(rng.integers(0, 2 ** 31))
        self.assertEqual(next_random[0], next_random[1])
        for clip in clips:
            self.assertEqual(checks.run_all(clip), [])
        for obj in ("p01", "p03"):
            pd.testing.assert_frame_equal(clips[0].frames[clips[0].frames.object == obj],
                                          clips[1].frames[clips[1].frames.object == obj])

    def test_default_and_explicitly_disabled_follow_are_identical(self):
        for subtype in ("TI01", "HD01"):
            clips = []
            for options in ({}, {"follow_ball": False}):
                rng = np.random.default_rng(0)
                b = ClipBuilder(rng, "H", **options)
                all_subtypes()[subtype][1](b, rng)
                clips.append(b.finish())
            pd.testing.assert_frame_equal(clips[0].frames, clips[1].frames)
            self.assertEqual(clips[0].truth, clips[1].truth)

    def test_following_preserves_home_away_rotation(self):
        home = build_example(2, "H", True)
        away = build_example(2, "A", True)
        self.assertEqual(home.n_frames, away.n_frames)
        self.assertEqual([{"H": "A", "A": "H", "D": "D"}[s] for s in home.truth], away.truth)
        for t in (0, 2.5, 5, (home.n_frames - 1) / FPS):
            x, y, z = home.ball_at(t)
            np.testing.assert_allclose(away.ball_at(t), (PITCH_LENGTH - x, PITCH_WIDTH - y, z))
            for hp, ap in zip(home.players_at(t), away.players_at(t)):
                np.testing.assert_allclose(ap[2:], (PITCH_LENGTH - hp[2], PITCH_WIDTH - hp[3]))


if __name__ == "__main__":
    unittest.main()
