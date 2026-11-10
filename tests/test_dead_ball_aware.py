"""Independent behavioral checks for strict dead-ball and tag fusion rules."""

import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from algorithms.dead_ball_aware.predict import infer, predict
from observations.schema import COLUMNS


class DeadBallAwareTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load((Path(__file__).parents[1] / 'experiments' /
            '20261109_dead_ball_tags_dev_v3' / 'config.yaml').read_text())['params']
        self.obs = pd.DataFrame(np.nan, index=range(450), columns=COLUMNS)
        self.obs['frame'] = range(450)
        self.obs[['ball_x', 'ball_y']] = [20 / 105, 30 / 68]
        self.obs[['1_x', '1_y']] = [20 / 105, 30 / 68]
        self.obs[['2_x', '2_y']] = [28 / 105, 30 / 68]
        self.obs[['25_x', '25_y']] = [36 / 105, 30 / 68]
        self.obs.loc[25:35, 'ball_x'] = np.linspace(20, 28, 11) / 105
        self.obs.loc[36:349, 'ball_x'] = 28 / 105
        self.obs.loc[350:370, 'ball_x'] = np.linspace(28, 36, 21) / 105
        self.obs.loc[371:, 'ball_x'] = 36 / 105
        self.meta = {'fps': 25, 'pitch_length': 105, 'pitch_width': 68,
                     'slot_teams': {str(i): 'H' if i <= 24 else 'A' for i in range(1, 47)}}
        self.tag = {'start_frame': 300, 'end_frame': 800, 'code': 'SET PIECES',
                    'type': 'Free Kick', 'team': 'H'}

    def test_stationary_live_ball_and_short_gap_do_not_create_dead_ball(self):
        self.obs.loc[100:103, ['ball_x', 'ball_y']] = np.nan
        result = predict(self.obs, self.meta, self.config)
        self.assertEqual(result[:25], ['D'] * 25)
        self.assertEqual(result[25:370], ['H'] * 345)
        self.assertEqual(result[370:], ['A'] * 80)

    def test_long_gap_is_backdated_but_reception_does_not_restart(self):
        self.obs.loc[100:225, ['ball_x', 'ball_y']] = np.nan
        result = predict(self.obs, self.meta, self.config)
        self.assertEqual(result[100:350], ['D'] * 250)
        self.assertEqual(result[350:370], ['H'] * 20)

    def test_tag_requires_release_and_team_agreement(self):
        result, audit = infer(self.obs, self.meta, self.config, [self.tag])
        self.assertTrue(audit['visible_stoppages'])
        self.assertEqual(result[349], 'D')
        self.assertEqual(result[350], 'H')
        wrong = {**self.tag, 'team': 'A'}
        self.assertFalse(infer(self.obs, self.meta, self.config, [wrong])[1]['visible_stoppages'])
        self.obs.loc[350:, 'ball_x'] = 28 / 105
        self.assertEqual(predict(self.obs, self.meta, self.config, [self.tag])[349], 'H')

    def test_slow_retrieval_does_not_end_dead_ball(self):
        self.obs.loc[100:, 'ball_x'] = 106 / 105
        self.obs.loc[125:200, 'ball_x'] = np.linspace(106, 104.5, 76) / 105
        self.obs.loc[201:, 'ball_x'] = 104.5 / 105
        self.obs.loc[100:, '25_x'] = self.obs.loc[100:, 'ball_x']
        result = predict(self.obs, self.meta, self.config)
        self.assertEqual(result[100:], ['D'] * 350)

    def test_near_receiver_does_not_own_the_release(self):
        result, audit = infer(self.obs, self.meta, self.config)
        self.assertEqual(audit['restarts'][0]['team'], 'H')
        self.assertEqual(result[350], 'H')
        swapped = {**self.meta, 'slot_teams': {s: {'H': 'A', 'A': 'H'}[t]
                                              for s, t in self.meta['slot_teams'].items()}}
        self.assertEqual(predict(self.obs, swapped, self.config),
                         [{'H': 'A', 'A': 'H', 'D': 'D'}[t] for t in result])

    def test_visible_pause_does_not_precede_an_observed_touchline_exit(self):
        self.obs[['2_x', '2_y']] = [104 / 105, 30 / 68]
        self.obs[['25_x', '25_y']] = [96 / 105, 30 / 68]
        self.obs.loc[25:35, 'ball_x'] = np.linspace(20, 104, 11) / 105
        self.obs.loc[36:349, 'ball_x'] = 104 / 105
        self.obs.loc[100:150, 'ball_x'] = np.linspace(104, 105.3, 51) / 105
        self.obs.loc[150:200, 'ball_x'] = np.linspace(105.3, 104, 51) / 105
        self.obs.loc[350:370, 'ball_x'] = np.linspace(104, 96, 21) / 105
        self.obs.loc[371:, 'ball_x'] = 96 / 105
        result = predict(self.obs, self.meta, self.config, [self.tag])
        self.assertEqual(result[130], 'H')
        self.assertEqual(result[145], 'D')
        self.assertEqual(result[349], 'D')
        self.assertEqual(result[350], 'H')

    def test_tag_can_support_an_observed_wait_before_a_long_gap(self):
        self.obs.loc[220:349, ['ball_x', 'ball_y']] = np.nan
        plain = predict(self.obs, self.meta, self.config)
        result, audit = infer(self.obs, self.meta, self.config, [self.tag])
        self.assertEqual(plain[150], 'H')
        self.assertEqual(result[150], 'D')
        self.assertTrue(audit['visible_stoppages'][0]['evidence_before_gap'])
        self.assertEqual(result[350], 'H')


if __name__ == '__main__':
    unittest.main()
