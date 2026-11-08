"""Ground motion, scoped stillness, and byte-level legacy compatibility."""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from simulation.core import ClipBuilder, checks, io
from simulation.core.constants import BALL_RADIUS, FPS
from simulation.core.motion import GroundRoll
from simulation.generate import assign_clip_ids, build_clips, tables


class GroundRollTests(unittest.TestCase):
    def test_uniform_deceleration_stop_and_ground_height(self):
        for start, end in (((0, 0), (3, 4)), ((12, 70), (-2, 68)), ((1, 1), (1, 1))):
            roll = GroundRoll(2.0, 6.0, start, end)
            times = np.linspace(2, 6, 101)
            positions = np.array([roll.position(t) for t in times])
            np.testing.assert_allclose(positions[:, 2], BALL_RADIUS, atol=1e-9, rtol=0)
            speeds = np.linalg.norm(np.diff(positions[:, :2], axis=0), axis=1) / 0.04
            self.assertTrue(np.all(np.diff(speeds) <= 1e-9))
            np.testing.assert_allclose(np.diff(speeds), np.diff(speeds)[0], atol=1e-9)
            for t in (6, 7, 100):
                np.testing.assert_allclose(roll.position(t), (*end, BALL_RADIUS), atol=1e-9)
                self.assertEqual(roll.speed(t), 0.0)
            before = roll.position(4)
            roll.t1 = 100  # Extending coverage must never stretch the completed roll.
            self.assertEqual(roll.position(4), before)
        with self.assertRaises(ValueError):
            GroundRoll(1, 1, (0, 0), (1, 0))

    def test_builder_roll_and_wait_do_not_create_truth_or_arrival_contact(self):
        b = ClipBuilder(np.random.default_rng(3), "H")
        player = b.player("atk", "lcb")
        b.place_ball(player)
        start = b.ball_position(0)
        b.roll_to(2, point=(start[0] + 5, start[1]), arrival_contact=False)
        midway = b.ball_position(1)
        b.wait(3)
        self.assertEqual(b.ball_position(1), midway)
        self.assertEqual(b.ball_position(2), b.ball_position(5))
        self.assertEqual(b._events, [])
        self.assertEqual(b._contacts, [0])
        with self.assertRaises(ValueError):
            b.roll_to(0, point=(0, 0))
        with self.assertRaises(ValueError):
            b.roll_to(1, point=(0, 0), player=player)
        high = ClipBuilder(np.random.default_rng(3), "H")
        high.place_ball(high.player("atk", "lcb"), height=1)
        with self.assertRaises(ValueError):
            high.roll_to(2, point=(1, 1))


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
        with self.assertRaises(ValueError):
            b.hold(player, 1, height=2, in_front=0, still=True)


class LegacyCompatibilityTests(unittest.TestCase):
    def test_ti01_hd01_bytes_match_main_39ebb28(self):
        # Golden hashes captured before changing motion code, using the existing venv.
        expected = {
            "observations.csv": "1b575342a2cb742217081555f2e70c5839db9e7a86837a163939cd485b9c6e94",
            "truth.csv": "28dbb21b589328e128a28b29ae1310e264371eaa0ee1dccd787a930511b0866b",
        }
        built = assign_clip_ids(build_clips(["TI01", "HD01"], 20, 0), 0)
        self.assertEqual(len(built), 80)
        for item in built:
            self.assertEqual(checks.run_all(item["clip"]), [])
        with TemporaryDirectory() as temp:
            output = Path(temp) / "dataset"
            io.write_dataset(str(output), *tables(built))
            for name, digest in expected.items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
