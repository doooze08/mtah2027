"""Behavioral checks for ending D at a moving long-gap reappearance."""

import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from algorithms.dead_ball_aware.predict import infer, predict
from observations.schema import COLUMNS


class MovingReappearanceTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load((Path(__file__).parents[1] / 'experiments' /
            '20261109_dead_ball_tags_dev' / 'config.yaml').read_text())['params']
        self.on = {**self.config, 'end_gap_on_moving_ball': True}
        self.trusted_on = {**self.on, 'trusted_tags': True,
                           'trusted_tag_min_slow_s': 0.5}
        self.meta = {'fps': 25, 'pitch_length': 105, 'pitch_width': 68,
                     'slot_teams': {str(i): 'H' if i <= 24 else 'A'
                                    for i in range(1, 47)}}

    def _base(self):
        obs = pd.DataFrame(np.nan, index=range(450), columns=COLUMNS)
        obs['frame'] = range(450)
        obs[['ball_x', 'ball_y']] = [20 / 105, 30 / 68]
        obs[['1_x', '1_y']] = [20 / 105, 30 / 68]
        obs.loc[100:225, ['ball_x', 'ball_y']] = np.nan
        return obs

    def _moving(self):
        obs = self._base()
        for frame in range(226, 251):
            x = 20 + (frame - 225) * 0.14
            obs.loc[frame, ['ball_x', 'ball_y']] = [x / 105, 30 / 68]
            obs.loc[frame, ['1_x', '1_y']] = [x / 105, 30 / 68]
        obs.loc[251:, ['ball_x', 'ball_y']] = [23.5 / 105, 30 / 68]
        obs.loc[251:, ['1_x', '1_y']] = [23.5 / 105, 30 / 68]
        return obs

    def test_moving_reappearance_ends_d_with_first_control_team(self):
        labels, audit = infer(self._moving(), self.meta, self.on)
        self.assertEqual(labels[226], 'H')
        self.assertEqual(audit['moving_reappearances'][0]['frame'], 226)
        self.assertEqual(audit['moving_reappearances'][0]['team'], 'H')
        self.assertEqual(predict(self._moving(), self.meta, self.config)[226], 'D')

    def test_moving_reappearance_uses_trusted_tag_team(self):
        tag = {'start_frame': 220, 'end_frame': 240, 'code': 'SET PIECES',
               'type': 'Throw In', 'team': 'A'}
        labels, audit = infer(self._moving(), self.meta, self.trusted_on, [tag])
        self.assertEqual(labels[226], 'A')
        record = audit['moving_reappearances'][0]
        self.assertEqual(record['team'], 'A')
        self.assertEqual(record['team_source'], 'tag')

    def test_slow_reappearance_keeps_original_d(self):
        slow = self._base()
        off = predict(slow, self.meta, self.config)
        on, audit = infer(slow, self.meta, self.on)
        self.assertEqual(on, off)
        self.assertFalse(audit['moving_reappearances'])

    def test_second_gap_or_exit_before_first_control_keeps_original_d(self):
        obs = self._base()
        for frame in range(226, 231):
            x = 20 + (frame - 225) * 0.14
            obs.loc[frame, ['ball_x', 'ball_y']] = [x / 105, 30 / 68]
            obs.loc[frame, ['1_x', '1_y']] = [x / 105, 30 / 68]
        obs.loc[231:300, ['ball_x', 'ball_y']] = np.nan
        for frame in range(301, 350):
            x = 20 + (frame - 225) * 0.14
            obs.loc[frame, ['ball_x', 'ball_y']] = [x / 105, 30 / 68]
            obs.loc[frame, ['1_x', '1_y']] = [x / 105, 30 / 68]
        off = predict(obs, self.meta, self.config)
        on, audit = infer(obs, self.meta, self.on)
        self.assertEqual(on, off)
        self.assertFalse(audit['moving_reappearances'])

    def test_exit_before_first_control_keeps_original_d(self):
        obs = self._moving()
        for frame in range(231, 236):
            obs.loc[frame, ['ball_x', 'ball_y']] = [106 / 105, 30 / 68]
        obs.loc[226:249, ['1_x', '1_y']] = [20 / 105, 30 / 68]
        off = predict(obs, self.meta, self.config)
        on, audit = infer(obs, self.meta, self.on)
        self.assertEqual(on, off)
        self.assertFalse(audit['moving_reappearances'])

    def test_outside_reappearance_ends_at_entry_frame(self):
        obs = self._base()
        for frame in range(226, 260):
            x = 106 - (frame - 226) * 0.14
            obs.loc[frame, ['ball_x', 'ball_y']] = [x / 105, 30 / 68]
            obs.loc[frame, ['1_x', '1_y']] = [x / 105, 30 / 68]
        labels, audit = infer(obs, self.meta, self.on)
        entry = audit['moving_reappearances'][0]['frame']
        self.assertEqual(entry, 233)
        self.assertEqual(labels[entry], 'H')
        self.assertEqual(labels[entry - 1], 'D')

    def test_switch_off_matches_current_output(self):
        obs = self._moving()
        off = {**self.config, 'end_gap_on_moving_ball': False}
        self.assertEqual(predict(obs, self.meta, off), predict(obs, self.meta, self.config))
        labels, audit = infer(obs, self.meta, off)
        self.assertFalse(audit['moving_reappearances'])


if __name__ == '__main__':
    unittest.main()
