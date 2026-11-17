import importlib.util
import os
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCHMARK = os.path.join(ROOT, "experiments", "20261117_bar_ath_gap_diagnostic",
                         "metrica_live_d.py")
SPEC = importlib.util.spec_from_file_location("metrica_live_d", BENCHMARK)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DRunEndTest(unittest.TestCase):
    def test_only_d_runs_have_an_end(self):
        np.testing.assert_array_equal(
            MODULE.d_run_end(np.array(["H", "D", "D", "H", "D"])),
            np.array([0, 3, 3, 3, 5]))


class LiveDClassTest(unittest.TestCase):
    def test_a1_is_missing_and_has_priority(self):
        pred = np.array(["D"] * 10)
        live = np.ones(10, dtype=bool)
        known = np.ones(10, dtype=bool)
        known[:4] = False
        a1, a2, a3, other = MODULE.classify_live_d(
            pred, live, known, [(0, 4)], [], fps=1, min_gap_s=1, window_s=10)
        self.assertEqual(int(a1.sum()), 4)
        self.assertEqual(int(a2.sum()), 6)
        self.assertEqual(int(a3.sum()), 0)
        self.assertEqual(int(other.sum()), 0)

    def test_a2_starts_at_first_visible_frame_after_long_gap(self):
        pred = np.array(["D"] * 20)
        live = np.ones(20, dtype=bool)
        known = np.ones(20, dtype=bool)
        known[:5] = False
        a1, a2, a3, other = MODULE.classify_live_d(
            pred, live, known, [(0, 5)], [], fps=1, min_gap_s=5, window_s=10)
        self.assertEqual(int(a1.sum()), 5)
        self.assertEqual(int(a2.sum()), 10)
        self.assertEqual(int(a3.sum()), 0)
        self.assertEqual(int(other.sum()), 5)

    def test_a2_stops_at_window_and_does_not_cross_non_d(self):
        pred = np.array(["D"] * 20)
        live = np.ones(20, dtype=bool)
        known = np.ones(20, dtype=bool)
        known[:5] = False
        pred[8] = "H"
        a1, a2, _, other = MODULE.classify_live_d(
            pred, live, known, [(0, 5)], [], fps=1, min_gap_s=5, window_s=10)
        self.assertEqual(int(a1.sum()), 5)
        self.assertEqual(int(a2.sum()), 3)
        self.assertEqual(int(other.sum()), 11)

    def test_short_gap_is_not_a2(self):
        pred = np.array(["D"] * 20)
        live = np.ones(20, dtype=bool)
        known = np.ones(20, dtype=bool)
        known[:4] = False
        _, a2, _, _ = MODULE.classify_live_d(
            pred, live, known, [(0, 4)], [], fps=1, min_gap_s=5, window_s=10)
        self.assertEqual(int(a2.sum()), 0)

    def test_a3_starts_at_first_d_after_out(self):
        pred = np.array(["H", "H", "D", "D", "D"])
        live = np.ones(5, dtype=bool)
        known = np.ones(5, dtype=bool)
        _, _, a3, other = MODULE.classify_live_d(
            pred, live, known, [], [0], fps=1, min_gap_s=5, window_s=10,
            out_onset_grace_s=3)
        self.assertEqual(int(a3.sum()), 3)
        self.assertEqual(int(other.sum()), 0)

    def test_later_onset_wins_between_a2_and_a3(self):
        pred = np.array(["D"] * 20)
        live = np.ones(20, dtype=bool)
        known = np.ones(20, dtype=bool)
        known[:5] = False
        a1, a2, a3, _ = MODULE.classify_live_d(
            pred, live, known, [(0, 5)], [8], fps=1, min_gap_s=5, window_s=10)
        self.assertEqual(int(a1.sum()), 5)
        self.assertEqual(int(a2.sum()), 3)   # frames 5, 6, 7
        self.assertEqual(int(a3.sum()), 10)  # frames 8..17, capped by the 10 s window


if __name__ == "__main__":
    unittest.main()
