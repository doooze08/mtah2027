"""Unit tests for the external-data converter and the X-scoring boundary.

All inputs here are hand-written; no real match files are read, so the tests are fast
and do not depend on the locally downloaded external data.
"""

import types
import unittest

import numpy as np

from external import metrica, skillcorner
from external.common import (
    Event,
    assign_slots,
    observations_frame,
    slot_teams,
    speed_from_positions,
    upsample_factor,
    upsample_positions,
)
from simulation.evaluate import score_clip


class SlotMappingTest(unittest.TestCase):
    def test_fixed_team_slots_and_unused_slots(self):
        players = [{"key": "h{}".format(n), "team": "H", "number": n}
                   for n in (11, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14)]
        players += [{"key": "a{}".format(n), "team": "A", "number": n}
                    for n in (25, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 26)]
        mapping = assign_slots(players)
        self.assertEqual(mapping["h1"], "1")
        self.assertEqual(mapping["h14"], "14")          # 14 home players -> slots 1..14
        self.assertEqual(mapping["a15"], "25")
        self.assertEqual(mapping["a26"], "36")          # 12 away players -> slots 25..36
        self.assertEqual(len(mapping), 26)
        self.assertEqual(len(set(mapping.values())), 26)
        self.assertTrue(all(int(slot) <= 24 for key, slot in mapping.items() if key[0] == "h"))
        self.assertTrue(all(int(slot) >= 25 for key, slot in mapping.items() if key[0] == "a"))

    def test_all_46_slots_have_a_team(self):
        teams = slot_teams()
        self.assertEqual(len(teams), 46)
        self.assertEqual(sum(1 for value in teams.values() if value == "H"), 24)
        self.assertEqual(sum(1 for value in teams.values() if value == "A"), 22)
        self.assertEqual(set(teams), {str(i) for i in range(1, 47)})

    def test_too_many_players_is_rejected(self):
        players = [{"key": str(n), "team": "H", "number": n} for n in range(1, 26)]
        with self.assertRaises(ValueError):
            assign_slots(players)


class ResamplingTest(unittest.TestCase):
    def test_missing_values_are_not_bridged(self):
        values = np.array([0.0, 1.0, np.nan, 3.0, 4.0])
        result, nearest = upsample_factor(values)
        self.assertEqual(len(result), 11)
        np.testing.assert_array_equal(nearest, [0, 0, 1, 1, 2, 2, 2, 3, 3, 4, 4])
        np.testing.assert_allclose(result[[0, 1, 2]], [0.0, 0.4, 0.8])
        self.assertTrue(np.isnan(result[3:8]).all())
        np.testing.assert_allclose(result[[8, 9, 10]], [3.2, 3.6, 4.0])

    def test_whole_frame_gap_stays_nan(self):
        positions = np.array([
            [0.0, 0.0],
            [0.1, 0.1],
            [np.nan, np.nan],
            [0.3, 0.3],
            [0.4, 0.4],
        ])
        result, nearest = upsample_positions(positions)
        self.assertEqual(len(result), 11)
        self.assertTrue(np.isnan(result[3:8]).all())
        np.testing.assert_allclose(result[8], [0.32, 0.32])
        np.testing.assert_array_equal(nearest, [0, 0, 1, 1, 2, 2, 2, 3, 3, 4, 4])

    def test_speed_uses_adjacent_frames_and_nan(self):
        x = np.array([0.0, 0.001, np.nan, 0.003])
        y = np.zeros(4)
        speed = speed_from_positions(x, y, 105.0, 68.0, 25.0)
        self.assertAlmostEqual(speed[1], 0.105 * 25.0)
        self.assertAlmostEqual(speed[0], speed[1])       # forward difference
        self.assertTrue(np.isnan(speed[2]))
        self.assertTrue(np.isnan(speed[3]))

    def test_observation_contract(self):
        players = {"1": np.array([[0.1, 0.2], [0.2, 0.2]]),
                   "25": np.array([[np.nan, np.nan], [0.3, 0.3]])}
        ball = np.array([[0.5, 0.5], [np.nan, np.nan]])
        table = observations_frame(ball, players, 105.0, 68.0)
        self.assertEqual(table.shape, (2, 141))
        self.assertEqual(table.columns[0], "frame")
        self.assertAlmostEqual(table.loc[0, "1_x"], 0.1)
        self.assertAlmostEqual(table.loc[0, "1_s"], np.hypot(0.1 * 105.0, 0.0) * 25.0)
        self.assertTrue(np.isnan(table.loc[0, "25_x"]))
        self.assertAlmostEqual(table.loc[1, "25_x"], 0.3)
        self.assertTrue(np.isnan(table.loc[1, "ball_x"]))


class MetricaLabelTest(unittest.TestCase):
    def _labels(self, n_frames, events):
        return list(metrica.derive_labels(n_frames, events))

    def test_ball_out_to_set_piece_is_dead(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "BALL OUT", "", 10, 12, "H"),
            Event(3, "SET PIECE", "THROW IN", 20, 20, "A"),
            Event(4, "PASS", "", 20, 20, "A"),
        ]
        labels = self._labels(25, events)
        self.assertEqual(labels[0], "H")
        self.assertEqual(labels[9], "H")
        self.assertEqual(labels[10], "D")
        self.assertEqual(labels[19], "D")
        self.assertEqual(labels[20], "A")
        self.assertEqual(labels[21], "X")               # after the last event

    def test_goal_to_kickoff_is_dead(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "A"),
            Event(2, "SHOT", "ON TARGET|GOAL", 5, 8, "A"),
            Event(3, "SET PIECE", "KICK OFF", 15, 15, "H"),
            Event(4, "PASS", "", 15, 15, "H"),
        ]
        labels = self._labels(25, events)
        self.assertEqual(labels[8], "A")
        self.assertEqual(labels[9], "D")
        self.assertEqual(labels[14], "D")
        self.assertEqual(labels[15], "H")
        self.assertEqual(labels[16], "X")

    def test_fault_to_set_piece_is_dead(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "FAULT RECEIVED", "", 10, 10, "H"),
            Event(3, "SET PIECE", "FREE KICK", 20, 20, "A"),
        ]
        labels = self._labels(25, events)
        self.assertEqual(labels[9], "H")
        self.assertEqual(labels[10], "D")               # stoppage start is included
        self.assertEqual(labels[19], "D")
        self.assertEqual(labels[20], "A")
        self.assertEqual(labels[21], "X")

    def test_fault_30s_before_set_piece_is_still_dead(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "FAULT RECEIVED", "", 10, 10, "H"),
            Event(3, "SET PIECE", "FREE KICK", 300, 300, "A"),
        ]
        labels = self._labels(310, events)
        self.assertEqual(labels[9], "H")
        self.assertEqual(labels[10], "D")
        self.assertEqual(labels[299], "D")
        self.assertEqual(labels[300], "A")
        self.assertEqual(labels[301], "X")

    def test_fault_then_pass_is_advantage_not_dead(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "FAULT RECEIVED", "", 10, 10, "H"),
            Event(3, "PASS", "", 20, 20, "A"),
            Event(4, "SET PIECE", "FREE KICK", 30, 30, "A"),
        ]
        labels = self._labels(40, events)
        self.assertEqual(labels[10], "H")               # no D: a live event follows
        self.assertEqual(labels[19], "H")
        self.assertEqual(labels[20], "A")
        self.assertEqual(labels[29], "A")
        self.assertEqual(labels[30], "A")
        self.assertEqual(labels[31], "X")

    def test_shot_out_to_set_piece_is_dead(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "SHOT", "OFF TARGET|OUT", 10, 12, "H"),
            Event(3, "SET PIECE", "THROW IN", 20, 20, "A"),
            Event(4, "PASS", "", 20, 20, "A"),
        ]
        labels = self._labels(30, events)
        self.assertEqual(labels[9], "H")
        self.assertEqual(labels[10], "D")
        self.assertEqual(labels[19], "D")
        self.assertEqual(labels[20], "A")

    def test_shot_on_target_does_not_start_stoppage(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "SHOT", "ON TARGET|SAVED", 10, 12, "H"),
            Event(3, "SET PIECE", "GOAL KICK", 20, 20, "A"),
            Event(4, "PASS", "", 20, 20, "A"),
        ]
        labels = self._labels(30, events)
        self.assertEqual(labels[10], "H")               # a non-out shot is live
        self.assertEqual(labels[19], "H")
        self.assertEqual(labels[20], "A")

    def test_pass_goal_kick_is_a_restart_not_live(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "BALL OUT", "", 10, 12, "H"),
            Event(3, "PASS", "GOAL KICK", 20, 20, "A"),
            Event(4, "PASS", "", 21, 21, "A"),
        ]
        labels = self._labels(30, events)
        self.assertEqual(labels[9], "H")
        self.assertEqual(labels[10], "D")
        self.assertEqual(labels[19], "D")
        self.assertEqual(labels[20], "A")               # goal kick is the restart
        self.assertEqual(labels[21], "A")

    def test_goal_kick_interception_is_a_restart(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "BALL OUT", "", 10, 12, "H"),
            Event(3, "PASS", "GOAL KICK-INTERCEPTION", 20, 20, "A"),
            Event(4, "SET PIECE", "THROW IN", 30, 30, "A"),
        ]
        labels = self._labels(40, events)
        self.assertEqual(labels[10], "D")               # intercepted goal kick ends D
        self.assertEqual(labels[19], "D")
        self.assertEqual(labels[20], "A")               # goal kick is the restart
        self.assertEqual(labels[30], "A")

    def test_ball_lost_goal_kick_is_a_restart_not_live(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "BALL OUT", "", 10, 12, "H"),
            Event(3, "RECOVERY", "", 15, 15, "A"),
            Event(4, "BALL LOST", "GOAL KICK-INTERCEPTION", 20, 20, "A"),
            Event(5, "PASS", "", 20, 20, "A"),
        ]
        labels = self._labels(30, events)
        self.assertEqual(labels[10:20], ["D"] * 10)     # BALL OUT to goal kick
        self.assertEqual(labels[20], "A")               # goal kick is the restart

    def test_ball_out_then_recovery_is_still_dead(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "BALL OUT", "", 10, 12, "H"),
            Event(3, "RECOVERY", "", 15, 15, "A"),
            Event(4, "SET PIECE", "THROW IN", 20, 20, "A"),
        ]
        labels = self._labels(30, events)
        self.assertEqual(labels[9], "H")
        self.assertEqual(labels[10], "D")               # RECOVERY must not cancel D
        self.assertEqual(labels[19], "D")
        self.assertEqual(labels[20], "A")

    def test_challenge_fault_to_set_piece_is_dead(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "CHALLENGE", "GROUND|FAULT|WON", 10, 10, "H"),
            Event(3, "SET PIECE", "FREE KICK", 20, 20, "A"),
            Event(4, "PASS", "", 20, 20, "A"),
        ]
        labels = self._labels(30, events)
        self.assertEqual(labels[9], "H")
        self.assertEqual(labels[10], "D")
        self.assertEqual(labels[19], "D")
        self.assertEqual(labels[20], "A")

    def test_ball_lost_and_challenge_do_not_switch(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 0, 0, "H"),
            Event(1, "PASS", "", 1, 1, "H"),
            Event(2, "BALL LOST", "", 5, 5, "A"),
            Event(3, "CHALLENGE", "GROUND|WON", 6, 6, "A"),
            Event(4, "RECOVERY", "", 7, 7, "A"),
            Event(5, "PASS", "", 9, 9, "A"),
        ]
        labels = self._labels(10, events)
        self.assertEqual(labels[4], "H")
        self.assertEqual(labels[6], "H")
        self.assertEqual(labels[7], "A")
        self.assertEqual(labels[8], "A")
        self.assertEqual(labels[9], "A")

    def test_half_start_and_end_are_x(self):
        events = [
            Event(0, "SET PIECE", "KICK OFF", 5, 5, "H"),
            Event(1, "PASS", "", 5, 5, "H"),
        ]
        labels = self._labels(20, events)
        self.assertEqual(labels[:5], ["X"] * 5)
        self.assertEqual(labels[5], "H")
        self.assertEqual(labels[6:], ["X"] * 14)


class SkillCornerLabelTest(unittest.TestCase):
    def test_phase_team_and_phase_outside_dead(self):
        n = 40
        players = np.full(n, 22)
        phases = [(0, 9, "H"), (10, 19, "A")]
        labels = list(skillcorner.derive_labels(n, players, phases))
        self.assertEqual(labels[:10], ["H"] * 10)
        self.assertEqual(labels[10:20], ["A"] * 10)
        self.assertEqual(labels[20:30], ["D"] * 10)
        self.assertEqual(labels[30:], ["D"] * 10)

    def test_overlapping_phases_are_x(self):
        n = 40
        players = np.full(n, 22)
        phases = [(0, 19, "H"), (10, 29, "A")]
        labels = list(skillcorner.derive_labels(n, players, phases))
        self.assertEqual(labels[0], "H")
        self.assertEqual(labels[9], "H")
        self.assertEqual(labels[10], "X")
        self.assertEqual(labels[19], "X")
        self.assertEqual(labels[20], "A")
        self.assertEqual(labels[29], "A")
        self.assertEqual(labels[30], "D")

    def test_phase_without_tracking_is_x(self):
        n = 20
        players = np.full(n, 22)
        players[5] = 0
        phases = [(0, 19, "H")]
        labels = list(skillcorner.derive_labels(n, players, phases))
        self.assertEqual(labels[4], "H")
        self.assertEqual(labels[5], "X")
        self.assertEqual(labels[6], "H")

    def test_no_phase_and_no_tracking_is_still_dead(self):
        n = 20
        players = np.full(n, 22)
        players[5] = 0
        labels = list(skillcorner.derive_labels(n, players, []))
        self.assertEqual(labels, ["D"] * n)

    def test_unique_phase_without_team_is_x(self):
        n = 10
        players = np.full(n, 22)
        labels = list(skillcorner.derive_labels(n, players, [(0, 9, "")]))
        self.assertEqual(labels, ["X"] * n)


class XScoringTest(unittest.TestCase):
    def test_x_frames_are_not_counted_as_wrong(self):
        sample = types.SimpleNamespace(
            clip="c001", subtype="external", story_id="s", initiating_team="H",
            n_frames=6, core_start=0, core_stop=6)
        gt = ["H", "H", "X", "X", "D", "D"]
        pred = ["H", "A", "H", "A", "D", "H"]
        row, switch_lines = score_clip(sample, gt, pred)
        self.assertEqual(row["core_wrong_frames"], 2)    # frames 1 and 5 only
        self.assertEqual(row["clip_wrong_frames"], 2)
        self.assertEqual(row["n_true_switches"], 0)
        self.assertTrue(switch_lines)

    def test_mismatch_only_on_x_is_a_pass(self):
        sample = types.SimpleNamespace(
            clip="c002", subtype="external", story_id="s", initiating_team="H",
            n_frames=6, core_start=0, core_stop=6)
        gt = ["H", "H", "X", "X", "D", "D"]
        pred = ["H", "H", "D", "D", "D", "D"]
        row, _ = score_clip(sample, gt, pred)
        self.assertEqual(row["core_wrong_frames"], 0)
        self.assertTrue(row["core_all_correct"])


if __name__ == "__main__":
    unittest.main()
