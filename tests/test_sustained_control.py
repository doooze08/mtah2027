"""Behavior checks independent of scripted scenario answers and real-match labels."""

import unittest

import numpy as np
import pandas as pd

from algorithms.sustained_control.predict import predict
from observations.schema import COLUMNS


class SustainedControlTests(unittest.TestCase):
    def observations(self):
        n = 120
        table = pd.DataFrame(np.nan, index=range(n), columns=COLUMNS)
        table['frame'] = range(n)
        table[['ball_x', 'ball_y']] = [20 / 105, 30 / 68]
        table[['1_x', '1_y']] = [20 / 105, 30 / 68]
        table[['2_x', '2_y']] = [28 / 105, 30 / 68]
        # A stationary ball is kicked after waiting; the teammate controls it.
        table.loc[25:35, 'ball_x'] = np.linspace(20, 28, 11) / 105
        table.loc[36:, 'ball_x'] = 28 / 105
        teams = {str(i): 'H' if i <= 24 else 'A' for i in range(1, 47)}
        meta = dict(slot_teams=teams, pitch_length=105, pitch_width=68, fps=25)
        return table, meta

    def test_restart_static_control_nan_and_radius(self):
        obs, meta = self.observations()
        obs.loc[50:59, ['ball_x', 'ball_y']] = np.nan
        # An opponent is momentarily closest; this is insufficient control evidence.
        obs[['25_x', '25_y']] = [60 / 105, 30 / 68]
        obs.loc[65:66, '25_x'] = 28 / 105
        obs.loc[90:, 'ball_x'] = (105 + 0.10) / 105
        obs.loc[100:, 'ball_x'] = (105 + 0.12) / 105
        labels = predict(obs, meta, {})
        self.assertEqual(labels, ['D'] * 25 + ['H'] * 75 + ['D'] * 20)

    def test_contest_preserves_established_team(self):
        obs, meta = self.observations()
        obs[['25_x', '25_y']] = [60 / 105, 30 / 68]
        obs.loc[60:, '25_x'] = 28 / 105
        labels = predict(obs, meta, {})
        self.assertEqual(labels, ['D'] * 25 + ['H'] * 95)

    def test_no_control_no_live_state(self):
        obs, meta = self.observations()
        obs[['ball_x', 'ball_y']] = [20 / 105, 30 / 68]
        self.assertEqual(predict(obs, meta, {}), ['D'] * len(obs))
        obs[['ball_x', 'ball_y']] = np.nan
        self.assertEqual(predict(obs, meta, {}), ['D'] * len(obs))
        self.assertEqual(predict(obs.iloc[:0], meta, {}), [])

    def test_opponent_control_is_backdated_and_slot_numbers_do_not_matter(self):
        obs, meta = self.observations()
        obs[['25_x', '25_y']] = [36 / 105, 30 / 68]
        obs.loc[60:70, 'ball_x'] = np.linspace(28, 36, 11) / 105
        obs.loc[71:, 'ball_x'] = 36 / 105
        labels = predict(obs, meta, {})
        self.assertEqual(labels, ['D'] * 25 + ['H'] * 45 + ['A'] * 50)
        swapped = {**meta, 'slot_teams': {s: {'H': 'A', 'A': 'H'}[t]
                                        for s, t in meta['slot_teams'].items()}}
        self.assertEqual(predict(obs, swapped, {}),
                         [{'H': 'A', 'A': 'H', 'D': 'D'}[v] for v in labels])


if __name__ == '__main__':
    unittest.main()
