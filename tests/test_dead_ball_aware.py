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
            '20261109_dead_ball_tags_dev' / 'config.yaml').read_text())['params']
        self.trusted = {**self.config, 'trusted_tags': True,
                        'trusted_tag_min_slow_s': 0.5}
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

    def test_two_confirmed_teammates_restart_at_the_pass_without_a_fast_release(self):
        config = {**self.config, 'release_speed_m_s': 100.0}
        result, audit = infer(self.obs, self.meta, config)
        self.assertEqual(result[:25], ['D'] * 25)
        self.assertEqual(result[25:35], ['H'] * 10)
        self.assertFalse(audit['restarts'])
        self.assertEqual(audit['confirmed_passes'][0]['source_slot'], '1')
        self.assertEqual(audit['confirmed_passes'][0]['receiver_slot'], '2')
        opponent = {**self.meta, 'slot_teams': {**self.meta['slot_teams'], '2': 'A'}}
        self.assertEqual(predict(self.obs, opponent, config)[:100], ['D'] * 100)

    def test_one_player_or_a_gap_cannot_supply_two_control_confirmations(self):
        config = {**self.config, 'release_speed_m_s': 100.0}
        self.obs.loc[100:225, ['ball_x', 'ball_y']] = np.nan
        self.assertEqual(predict(self.obs, self.meta, config)[100:350], ['D'] * 250)
        self.obs[['ball_x', 'ball_y']] = [20 / 105, 30 / 68]
        self.assertEqual(predict(self.obs, self.meta, config), ['D'] * len(self.obs))

    def test_two_release_transition_intervals_do_not_erase_a_long_slow_wait(self):
        self.obs.loc[348:350, 'ball_x'] = np.array([28, 28.15, 28.30]) / 105
        self.obs.loc[350:370, 'ball_x'] = np.linspace(28.30, 36, 21) / 105
        result, audit = infer(self.obs, self.meta, self.config, [self.tag])
        self.assertEqual(result[349], 'D')
        self.assertEqual(result[350], 'H')
        self.assertEqual(audit['visible_stoppages'][0]['transition_frames'], 2)

    def test_release_actor_is_selected_before_acceleration_not_near_the_fast_ball(self):
        self.obs.loc[200:325, ['ball_x', 'ball_y']] = np.nan
        self.obs.loc[350:352, 'ball_x'] = np.array([28, 28.399, 29.329]) / 105
        self.obs.loc[352:355, 'ball_x'] = np.linspace(29.329, 36, 4) / 105
        self.obs.loc[356:, 'ball_x'] = 36 / 105
        self.obs.loc[330:, '25_x'] = 28.16 / 105
        result, audit = infer(self.obs, self.meta, self.config)
        release = next(record for record in audit['restarts'] if record['launch'] == 350)
        self.assertEqual(release['slot'], '2')
        self.assertLess(release['actor_frame'], 350)
        self.assertEqual(result[350], 'H')

    def test_trusted_tag_accepts_a_pause_shorter_than_the_legacy_six_seconds(self):
        frames = np.arange(36, 325)
        self.obs.loc[36:324, 'ball_x'] = (20 + 2 * np.cos(frames * 0.7)) / 105
        self.obs.loc[36:324, 'ball_y'] = (30 + 2 * np.sin(frames * 0.7)) / 68
        self.obs.loc[325:349, ['ball_x', 'ball_y']] = [20 / 105, 30 / 68]
        legacy, legacy_audit = infer(self.obs, self.meta, self.config, [self.tag])
        trusted, trusted_audit = infer(self.obs, self.meta, self.trusted, [self.tag])
        self.assertFalse(legacy_audit['visible_stoppages'])
        self.assertTrue(trusted_audit['visible_stoppages'])
        self.assertEqual(trusted[330], 'D')
        self.assertEqual(trusted[348], 'D')
        self.assertEqual(trusted[349], 'H')
        self.assertEqual(legacy[330], 'H')

    def test_trusted_tag_team_is_used_only_when_the_actors_are_ambiguous(self):
        self.obs.loc[300:349, ['ball_x', 'ball_y']] = [20 / 105, 30 / 68]
        self.obs[['25_x', '25_y']] = [20.1 / 105, 30 / 68]
        self.meta['slot_teams']['25'] = 'A'
        tag = {**self.tag, 'start_frame': 340, 'team': 'A'}
        trusted = {**self.trusted, 'tag_margin_s': 0.4}
        result, audit = infer(self.obs, self.meta, trusted, [tag])
        tagged = next(record for record in audit['restarts'] if record['frame'] == 349)
        self.assertEqual(result[350], 'A')
        self.assertEqual(tagged['team_source'], 'tag')
        self.obs[['25_x', '25_y']] = np.nan
        result, audit = infer(self.obs, self.meta, trusted, [tag])
        tagged = next(record for record in audit['restarts'] if record['frame'] == 349)
        self.assertEqual(result[350], 'H')
        self.assertEqual(tagged['team_source'], 'coordinates')
        self.assertEqual(audit['tag_team_conflicts'], 1)

    def test_trusted_mode_without_tags_matches_the_untagged_branch(self):
        plain = predict(self.obs, self.meta, self.trusted)
        self.assertEqual(plain, predict(self.obs, self.meta, self.trusted, []))

    def test_extreme_fast_contested_play_overrides_a_tag_without_creating_dead_ball(self):
        obs = self.obs.copy()
        obs[['ball_x', 'ball_y']] = [20.5 / 105, 30 / 68]
        obs['ball_x'] = (20.5 + (np.arange(len(obs)) % 2)) / 105
        obs[['1_x', '1_y']] = [20.5 / 105, 30 / 68]
        obs[['25_x', '25_y']] = [21.5 / 105, 30 / 68]
        meta = {**self.meta, 'slot_teams': {**self.meta['slot_teams'], '25': 'A'}}
        tag = {**self.tag, 'start_frame': 0, 'end_frame': 449}
        _, audit = infer(obs, meta, self.trusted, [tag])
        self.assertEqual(audit['tags_overridden'], 1)
        self.assertEqual(audit['tags_used'], 0)

    def test_opening_kickoff_tag_does_not_need_slow_evidence(self):
        tag = {**self.tag, 'start_frame': 0, 'end_frame': 125,
               'type': 'Kick Off (Start)', 'team': None}
        _, audit = infer(self.obs, self.meta, self.trusted, [tag])
        opening = min(audit['restarts'], key=lambda record: abs(record['frame'] - 25))
        self.assertTrue(opening['tag_used'])

    def test_tag_is_not_stolen_by_an_earlier_live_pass(self):
        self.obs[['26_x', '26_y']] = [44 / 105, 30 / 68]
        self.obs.loc[36:249, 'ball_x'] = 28 / 105
        self.obs.loc[250:260, 'ball_x'] = np.linspace(28, 36, 11) / 105
        self.obs.loc[261:369, 'ball_x'] = 36 / 105
        self.obs.loc[370:390, 'ball_x'] = np.linspace(36, 44, 21) / 105
        self.obs.loc[391:, 'ball_x'] = 44 / 105
        tag = {**self.tag, 'start_frame': 250, 'end_frame': 440, 'team': 'A'}
        result, audit = infer(self.obs, self.meta, self.trusted, [tag])
        early = min(audit['restarts'], key=lambda record: abs(record['frame'] - 250))
        late = min(audit['restarts'], key=lambda record: abs(record['frame'] - 370))
        self.assertFalse(early['tag_used'])
        self.assertTrue(late['tag_used'])
        self.assertEqual(result[330], 'D')

    def test_tag_waits_for_a_dead_ball_pass_to_the_taker(self):
        self.obs[['26_x', '26_y']] = [44 / 105, 30 / 68]
        self.obs.loc[36:149, 'ball_x'] = 28 / 105
        self.obs.loc[150:160, 'ball_x'] = np.linspace(28, 36, 11) / 105
        self.obs.loc[161:249, 'ball_x'] = 36 / 105
        self.obs.loc[250:270, 'ball_x'] = np.linspace(36, 44, 21) / 105
        self.obs.loc[271:, 'ball_x'] = 44 / 105
        tag = {**self.tag, 'start_frame': 100, 'end_frame': 400, 'team': 'A'}
        result, audit = infer(self.obs, self.meta, self.trusted, [tag])
        early = min(audit['restarts'], key=lambda record: abs(record['frame'] - 150))
        late = min(audit['restarts'], key=lambda record: abs(record['frame'] - 250))
        self.assertFalse(early['tag_used'])
        self.assertTrue(late['tag_used'])
        self.assertEqual(result[220], 'D')

    def test_tag_waits_for_a_dead_ball_pass_after_an_out(self):
        self.obs[['26_x', '26_y']] = [44 / 105, 30 / 68]
        self.obs.loc[36:99, 'ball_x'] = 28 / 105
        self.obs.loc[100:149, 'ball_x'] = 106 / 105
        self.obs.loc[150:160, 'ball_x'] = np.linspace(106, 36, 11) / 105
        self.obs.loc[161:249, 'ball_x'] = 36 / 105
        self.obs.loc[250:270, 'ball_x'] = np.linspace(36, 44, 21) / 105
        self.obs.loc[271:, 'ball_x'] = 44 / 105
        tag = {**self.tag, 'start_frame': 100, 'end_frame': 400, 'team': 'A'}
        result, audit = infer(self.obs, self.meta, self.trusted, [tag])
        early = min(audit['restarts'], key=lambda record: abs(record['frame'] - 150))
        late = min(audit['restarts'], key=lambda record: abs(record['frame'] - 250))
        self.assertFalse(early['tag_used'])
        self.assertTrue(late['tag_used'])
        self.assertEqual(result[220], 'D')


if __name__ == '__main__':
    unittest.main()
