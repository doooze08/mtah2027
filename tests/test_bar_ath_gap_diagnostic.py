import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAGNOSE = os.path.join(ROOT, "experiments", "20261117_bar_ath_gap_diagnostic",
                        "diagnose.py")
SPEC = importlib.util.spec_from_file_location("bar_ath_gap_diagnostic", DIAGNOSE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TagCoverageTest(unittest.TestCase):
    def test_set_piece_wins_when_it_also_overlaps_goals(self):
        tags = [
            {"start_frame": 0, "end_frame": 100, "code": "SET PIECES",
             "type": "Corner Kick"},
            {"start_frame": 0, "end_frame": 100, "code": "GOALS", "type": "Goal"},
        ]
        coverage = MODULE.tag_coverage(tags, 10, 20)
        self.assertTrue(coverage["has_set_pieces"])
        self.assertTrue(coverage["has_goals"])
        self.assertEqual(coverage["tag_coverage"], "SET PIECES")
        self.assertEqual(coverage["overlapping_tags"], 2)

    def test_goals_only(self):
        tags = [{"start_frame": 10, "end_frame": 20, "code": "GOALS", "type": "Goal"}]
        coverage = MODULE.tag_coverage(tags, 0, 30)
        self.assertFalse(coverage["has_set_pieces"])
        self.assertTrue(coverage["has_goals"])
        self.assertFalse(coverage["has_other_phase"])
        self.assertEqual(coverage["tag_coverage"], "GOALS")

    def test_other_phase_and_none(self):
        tags = [{"start_frame": 0, "end_frame": 10, "code": "PROGRESSION",
                 "type": "Progression"}]
        coverage = MODULE.tag_coverage(tags, 20, 30)
        self.assertEqual(coverage["tag_coverage"], "none")
        coverage = MODULE.tag_coverage(tags, 5, 15)
        self.assertEqual(coverage["tag_coverage"], "other phase")

    def test_interval_overlap_is_half_open(self):
        tags = [{"start_frame": 100, "end_frame": 200, "code": "GOALS",
                 "type": "Goal"}]
        self.assertFalse(MODULE.tag_coverage(tags, 0, 100)["has_goals"])
        self.assertTrue(MODULE.tag_coverage(tags, 100, 150)["has_goals"])


class DescriptionLineTest(unittest.TestCase):
    def test_fast_is_strictly_above_the_line(self):
        self.assertFalse(MODULE._is_fast(1.575))
        self.assertTrue(MODULE._is_fast(1.5751))
        self.assertFalse(MODULE._is_fast(float("nan")))

    def test_open_far_needs_other_and_more_than_ten_metres(self):
        self.assertFalse(MODULE._is_open_far({
            "reappear_category": "other", "reappear_to_disappear_m": 10.0}))
        self.assertTrue(MODULE._is_open_far({
            "reappear_category": "other", "reappear_to_disappear_m": 10.01}))
        self.assertFalse(MODULE._is_open_far({
            "reappear_category": "goal_area", "reappear_to_disappear_m": 30.0}))
        self.assertFalse(MODULE._is_open_far({
            "reappear_category": "other", "reappear_to_disappear_m": float("nan")}))


class DecisionRuleTest(unittest.TestCase):
    def test_pre_registered_boundaries(self):
        self.assertEqual(MODULE.decision_rule(5, 120.0), "not_worth")
        self.assertEqual(MODULE.decision_rule(5, 120.1),
                         "review_footage_and_team_decision")
        self.assertEqual(MODULE.decision_rule(9, 66.68),
                         "review_footage_and_team_decision")
        self.assertEqual(MODULE.decision_rule(10, 0.0), "worth_designing")
        self.assertEqual(MODULE.decision_rule(0, 180.0), "worth_designing")


class LengthSummaryTest(unittest.TestCase):
    def test_length_summary(self):
        rows = [{"length_s": 5.0}, {"length_s": 10.0}, {"length_s": 15.0}]
        summary = MODULE.length_summary(rows)
        self.assertEqual(summary["n"], 3)
        self.assertEqual(summary["seconds"], 30.0)
        self.assertEqual(summary["median_s"], 10.0)
        self.assertAlmostEqual(summary["q1_s"], 7.5)
        self.assertAlmostEqual(summary["q3_s"], 12.5)


if __name__ == "__main__":
    unittest.main()
