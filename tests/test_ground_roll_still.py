"""Rolling friction, moving receptions, cushioning and scoped stillness."""

import math
import unittest

import numpy as np

from simulation.core import ClipBuilder, checks
from simulation.core.constants import BALL_RADIUS, FPS
from simulation.core.motion import GroundRoll, GroundTrap


class GroundRollTests(unittest.TestCase):
    def test_fixed_deceleration_and_moving_arrival(self):
        for deceleration in (1.0, 2.0, 3.0):
            for arrival_speed in (0.0, 3.0, 10.0):
                distance = 15.0
                initial = math.sqrt(arrival_speed ** 2 + 2 * deceleration * distance)
                duration = 2 * distance / (initial + arrival_speed)
                roll = GroundRoll(2, 2 + duration, (0, 0), (9, 12), deceleration)
                times = np.linspace(roll.t0, roll.arrival_time, 101)
                positions = np.array([roll.position(t) for t in times])
                np.testing.assert_allclose(positions[:, 2], BALL_RADIUS, atol=1e-9, rtol=0)
                speeds = np.array([roll.speed(t) for t in times])
                np.testing.assert_allclose(np.diff(speeds) / (duration / 100), -deceleration)
                self.assertAlmostEqual(speeds[-1], arrival_speed)
                np.testing.assert_allclose(positions[-1], (9, 12, BALL_RADIUS), atol=1e-9)
                stopped = roll.position(roll.t0 + initial / deceleration)
                self.assertEqual(roll.speed(100), 0)
                np.testing.assert_allclose(roll.position(100), stopped, atol=1e-9)
                midway = roll.position(roll.t0 + duration / 2)
                roll.t1 = 100  # Coverage extensions do not change friction or past positions.
                self.assertEqual(roll.position(roll.t0 + duration / 2), midway)
        with self.assertRaises(ValueError):
            GroundRoll(0, 10, (0, 0), (1, 0))

    def test_builder_speed_or_time_and_unreceived_stop(self):
        for kwargs in ({"arrival_speed": 6}, {"seconds": 2}):
            b = ClipBuilder(np.random.default_rng(3), "H")
            b.place_ball(b.player("atk", "lcb"))
            start = b.ball_position(0)
            b.roll_to(point=(start[0] + 15, start[1]), **kwargs)
            roll = b._ball_segments[-1]
            self.assertAlmostEqual(roll.deceleration, 2)
            self.assertAlmostEqual(roll.speed(b.now), 6 if "arrival_speed" in kwargs else 5.5)
        b = ClipBuilder(np.random.default_rng(3), "H")
        b.place_ball(b.player("atk", "lcb"))
        start = b.ball_position(0)
        b.roll_to(point=(start[0] + 5, start[1]), arrival_speed=0,
                  deceleration=3, arrival_contact=False)
        stop = b.now
        midway = b.ball_position(stop / 2)
        b.wait(3)
        self.assertEqual(b.ball_position(stop / 2), midway)
        self.assertEqual(b.ball_position(stop), b.ball_position(stop + 3))
        self.assertEqual(b._events, [])
        self.assertEqual(b._contacts, [0])


class GroundTrapTests(unittest.TestCase):
    def test_continuous_velocity_and_smooth_stop(self):
        for speed in (3.0, 6.0, 10.0):
            duration = max(0.1, min(0.3, 1.2 / speed))
            trap = GroundTrap(1, 1 + duration, (5, 8), (0.6 * speed, 0.8 * speed))
            times = np.linspace(1, 1 + duration, 101)
            velocities = np.array([trap.velocity(t) for t in times])
            np.testing.assert_allclose(velocities[0], (0.6 * speed, 0.8 * speed))
            np.testing.assert_allclose(velocities[-1], (0, 0), atol=1e-12)
            self.assertTrue(np.all(np.diff(np.linalg.norm(velocities, axis=1)) <= 1e-9))
            self.assertGreater(np.linalg.norm(trap.velocity(1 + 1 / FPS)), 0)
            distance = np.linalg.norm(np.array(trap.position(1 + duration)[:2]) - (5, 8))
            self.assertTrue(0.3 <= distance <= 1.0)
            for t in times[1:-1]:
                numerical = (np.array(trap.position(t + 1e-6)[:2])
                             - np.array(trap.position(t - 1e-6)[:2])) / 2e-6
                np.testing.assert_allclose(numerical, trap.velocity(t), atol=1e-8)
            np.testing.assert_allclose([trap.position(t)[2] for t in times], BALL_RADIUS)

    def test_contact_boundary_precedes_trap_and_hold(self):
        b = ClipBuilder(np.random.default_rng(6), "H")
        passer, receiver = b.player("atk", "lcb"), b.player("dfn", "ls")
        b.place_ball(passer)
        b.hold(passer, 1)
        b.begin_core()
        b.event("legal_restart", team="atk")
        b.roll_to(player=receiver, arrival_speed=6)
        contact = b.now
        incoming = b._ball_segments[-1]
        with self.assertRaises(ValueError):
            b.hold(receiver, 1, still=True)
        b.event("control_start", team="dfn")
        events_before = list(b._events)
        b.trap(receiver, 0.2)
        trap = b._ball_segments[-1]
        self.assertEqual(events_before, b._events)
        np.testing.assert_allclose(trap.velocity(contact), incoming.velocity(contact), atol=1e-9)
        b.hold(receiver, 1, still=True)
        b.end_core()
        b.expect("D", "atk", "dfn")
        clip = b.finish()
        event = next(e for e in clip.events if e.kind == "control_start")
        self.assertEqual(clip.truth[event.frame - 1], "H")
        self.assertEqual(set(clip.truth[event.frame:]), {"A"})
        self.assertEqual(checks.run_all(clip), [])
        for t in np.linspace(contact + 0.2, contact + 1.2, 11):
            np.testing.assert_allclose(clip.ball_at(t), clip.ball_at(contact + 0.2), atol=1e-9)
        # Free-motion validation is still strict; only the explicit foot action is exempt.
        clip.controlled_windows = []
        self.assertTrue(checks.check_ball_motion(clip))


class StillHoldTests(unittest.TestCase):
    def test_still_is_local_continuous_and_restores_sway(self):
        b = ClipBuilder(np.random.default_rng(8), "H")
        original = ClipBuilder(np.random.default_rng(8), "H")
        holder = b.player("atk", "lcb")
        b.place_ball(holder)
        b.hold(holder, 1)
        b.hold(holder, 2, still=True)
        for t in np.linspace(1, 3, 101):
            np.testing.assert_allclose(holder.position(t), holder.position(1), atol=1e-9, rtol=0)
            np.testing.assert_allclose(b.ball_position(t), b.ball_position(1), atol=1e-9, rtol=0)
        for player in b.all_players():
            if player is holder:
                continue
            reference = original.player(player.team, player.role)
            for t in np.linspace(0, 4, 101):
                self.assertEqual(player.position(t), reference.position(t))
        reference = original.player(holder.team, holder.role)
        for t in (4, 5, 6):
            self.assertEqual(holder.position(t), reference.position(t))
        for edge in (1, 3):
            np.testing.assert_allclose(holder.position(edge - 1e-8),
                                       holder.position(edge + 1e-8), atol=1e-7, rtol=0)
        positions = np.array([holder.position(t) for t in np.arange(0, 4, 1 / FPS)])
        speed, acceleration = checks._speed_and_acceleration(positions)
        self.assertLess(speed.max(), checks.PLAYER_MAX_SPEED)
        self.assertLess(acceleration.max(), checks.PLAYER_MAX_ACCELERATION)

    def test_adjacent_holds_and_run_conflicts(self):
        b = ClipBuilder(np.random.default_rng(4), "H")
        player = b.player("atk", "lcb")
        b.place_ball(player, in_front=0)
        b.hold(player, 1, in_front=0, still=True)
        b.hold(player, 1, in_front=0, still=True)
        for t in np.linspace(0, 2, 51):
            np.testing.assert_allclose(b.ball_position(t), b.ball_position(0), atol=1e-9)
        with self.assertRaises(ValueError):
            player.add_move(0.5, 1.5, (40, 40))
        player.add_move(3, 4, (40, 40))
        with self.assertRaises(ValueError):
            player.add_still(3, 4)
        with self.assertRaises(ValueError):
            b.hold(player, 0, in_front=0, still=True)


if __name__ == "__main__":
    unittest.main()
