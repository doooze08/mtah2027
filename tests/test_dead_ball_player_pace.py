"""Behavioral checks for the player-pace veto/confirmation switches."""

import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from algorithms.dead_ball_aware.pace import player_pace, restart_player_rise
from algorithms.dead_ball_aware.predict import infer
from observations.schema import COLUMNS


class PlayerPaceTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load((Path(__file__).parents[1] / 'experiments' /
            '20261109_dead_ball_tags_dev' / 'config.yaml').read_text())['params']
        self.meta = {'fps': 25, 'pitch_length': 105, 'pitch_width': 68,
                     'slot_teams': {str(i): 'H' if i <= 24 else 'A'
                                    for i in range(1, 47)}}

    def observations(self, n_players=6):
        obs = pd.DataFrame(np.nan, index=range(450), columns=COLUMNS)
        obs['frame'] = range(450)
        obs[['ball_x', 'ball_y']] = [20 / 105, 30 / 68]
        obs[['1_x', '1_y']] = [20 / 105, 30 / 68]
        obs[['2_x', '2_y']] = [28 / 105, 30 / 68]
        obs[['25_x', '25_y']] = [36 / 105, 30 / 68]
        for slot in range(3, 3 + max(0, n_players - 3)):
            obs[[str(slot) + '_x', str(slot) + '_y']] = [(10 + 2 * slot) / 105, 30 / 68]
        obs.loc[25:35, 'ball_x'] = np.linspace(20, 28, 11) / 105
        obs.loc[36:349, 'ball_x'] = 28 / 105
        obs.loc[350:370, 'ball_x'] = np.linspace(28, 36, 21) / 105
        obs.loc[371:, 'ball_x'] = 36 / 105
        obs.loc[100:225, ['ball_x', 'ball_y']] = np.nan
        return obs

    def move_players(self, obs, start, rate):
        for slot in range(1, 7):
            xy = obs[[str(slot) + '_x', str(slot) + '_y']].to_numpy().copy()
            frames = np.arange(len(obs))
            xy[:, 0] += np.clip((frames - start) / 25.0 * rate, 0, 10) / 105
            obs[[str(slot) + '_x', str(slot) + '_y']] = xy
        return obs

    def test_f1_is_computed_from_positions_not_the_speed_columns(self):
        obs = self.observations()
        for slot in range(1, 47):
            obs[str(slot) + '_s'] = 100.0
        static = player_pace(obs, self.meta)
        self.assertTrue(np.allclose(static, 0.0))
        moved = self.move_players(obs, 0, 2.0)
        f1 = player_pace(moved, self.meta)
        self.assertGreater(np.nanmedian(f1[:100]), 1.9)

    def test_fewer_than_five_visible_players_is_nan(self):
        obs = self.observations(n_players=3)
        f1 = player_pace(obs, self.meta)
        self.assertTrue(np.isnan(f1).all())

    def test_b1_vetoes_a_long_gap_when_players_keep_running(self):
        obs = self.move_players(self.observations(), 100, 2.0)
        config = {**self.config, 'gap_requires_slow_players': True,
                  'gap_slow_fraction': 0.6}
        labels, audit = infer(obs, self.meta, config)
        self.assertEqual(labels[99], 'H')
        self.assertEqual(labels[150], 'H')
        self.assertTrue(audit['long_gap_checks'][0]['vetoed'])

    def test_b1_keeps_original_d_when_the_gap_is_slow_or_unobserved(self):
        config = {**self.config, 'gap_requires_slow_players': True,
                  'gap_slow_fraction': 0.6}
        slow = infer(self.observations(), self.meta, config)[0]
        self.assertEqual(slow[150], 'D')
        sparse = infer(self.observations(n_players=3), self.meta, config)[0]
        self.assertEqual(sparse[150], 'D')

    def test_b2_rejects_a_restart_with_static_players(self):
        config = {**self.config, 'restart_requires_player_rise': True,
                  'player_rise_window_s': 2.0, 'player_rise_delta_m_s': 0.4}
        labels, audit = infer(self.observations(), self.meta, config)
        rejected = [record['launch'] for record in audit['restart_rejections']]
        self.assertIn(350, rejected)
        self.assertEqual(labels[349], 'D')
        self.assertEqual(labels[350], 'D')

    def test_b2_accepts_a_rise_at_the_original_restart_frame(self):
        config = {**self.config, 'restart_requires_player_rise': True,
                  'player_rise_window_s': 2.0, 'player_rise_delta_m_s': 0.4}
        labels, audit = infer(self.move_players(self.observations(), 350, 3.0),
                              self.meta, config)
        self.assertNotIn(350, [record['launch']
                               for record in audit['restart_rejections']])
        self.assertEqual(labels[349], 'D')
        self.assertEqual(labels[350], 'H')

    def test_b2_missing_pre_action_baseline_keeps_the_original_restart(self):
        pace = np.array([np.nan, 0.1, 0.1, 0.1])
        self.assertTrue(restart_player_rise(pace, 1, 25, 2.0, 0.4))

    def test_b2_data_insufficiency_keeps_the_original_restart(self):
        config = {**self.config, 'restart_requires_player_rise': True,
                  'player_rise_window_s': 2.0, 'player_rise_delta_m_s': 0.4}
        labels, audit = infer(self.observations(n_players=3), self.meta, config)
        self.assertEqual(audit['restart_rejections'], [])
        self.assertEqual(labels[350], 'H')


if __name__ == '__main__':
    unittest.main()
