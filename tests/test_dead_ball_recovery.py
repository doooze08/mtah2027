"""Behavioral checks for the three optional rules added on top of dead_ball_aware."""

import itertools
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from algorithms.dead_ball_aware.predict import predict as reference
from algorithms.dead_ball_recovery.predict import (absorb_short_possessions, confirm_outside,
                                                   infer, predict)
from observations.schema import COLUMNS

LENGTH, WIDTH, FPS = 105.0, 68.0, 25
NEW_KEYS = ('out_confirm_s', 'revive_after_gap', 'revive_window_s', 'min_possession_s')


def collapse(labels):
    return [(label, len(list(group))) for label, group in itertools.groupby(labels)]


class Scene:
    """Slots 1 and 2 are home, slot 25 is away; positions are given in metres."""

    def __init__(self, n):
        self.obs = pd.DataFrame(np.nan, index=range(n), columns=COLUMNS)
        self.obs['frame'] = range(n)
        self.meta = {'fps': FPS, 'pitch_length': LENGTH, 'pitch_width': WIDTH,
                     'slot_teams': {str(i): 'H' if i <= 24 else 'A' for i in range(1, 47)}}

    def put(self, name, start, stop, xy):
        xy = np.broadcast_to(np.asarray(xy, dtype=float), (stop - start, 2))
        self.obs.loc[start:stop - 1, name + '_x'] = xy[:, 0] / LENGTH
        self.obs.loc[start:stop - 1, name + '_y'] = xy[:, 1] / WIDTH

    def line(self, start, stop, origin, velocity):
        steps = np.arange(1, stop - start + 1)[:, None]
        return np.asarray(origin, dtype=float) + steps * np.asarray(velocity, dtype=float) / FPS


def kickoff_pass(n):
    """Still ball at slot 1, passed at 10 m/s to slot 2 who then stands on it from frame 75."""
    scene = Scene(n)
    scene.put('1', 0, n, [50, 34.3])
    scene.put('2', 0, n, [60.3, 34.3])
    scene.put('25', 0, n, [20, 10])
    scene.put('ball', 0, 50, [50, 34])
    scene.put('ball', 50, 75, scene.line(50, 75, [50, 34], [10, 0]))
    scene.put('ball', 75, n, [60, 34])
    return scene


class DeadBallRecoveryTests(unittest.TestCase):
    def setUp(self):
        path = (Path(__file__).parents[1] / 'experiments' /
                '20261116_dead_ball_recovery_dev' / 'config.yaml')
        self.config = yaml.safe_load(path.read_text())['params']
        self.plain = {k: v for k, v in self.config.items() if k not in NEW_KEYS}

    def touchline_blip(self, frames):
        scene = kickoff_pass(325)
        scene.put('ball', 200, 200 + frames, [60, WIDTH + 0.45])
        return scene

    def late_reappearance(self, receiver='2', exit_before_control=False):
        """An 8 s gap ends with the ball already in flight, 6 m from the stationary taker."""
        scene = kickoff_pass(550)
        scene.put('ball', 125, 325, [np.nan, np.nan])
        scene.put('1', 125, 550, [30, 20.3])
        flight = scene.line(339, 364, [35.6, 20], [10, 0])
        scene.put('ball', 325, 350, flight)
        scene.put('ball', 350, 550, flight[-1])
        if exit_before_control:
            scene.put('ball', 340, 550, [50, -1.0])
        scene.put(receiver, 325, 550, flight[-1] + [0.3, 0.3])
        return scene

    def brief_touch(self, frames):
        """The away slot stands on the ball for a moment while the home holder steps away."""
        scene = kickoff_pass(375)
        scene.put('2', 200, 200 + frames + 4, [63, 34])
        scene.put('25', 202, 202 + frames, [60.2, 33.8])
        return scene

    def test_without_new_keys_matches_dead_ball_aware(self):
        scenes = [self.touchline_blip(3), self.late_reappearance(), self.brief_touch(10),
                  self.late_reappearance(receiver='25'), self.touchline_blip(40)]
        for scene in scenes:
            self.assertEqual(predict(scene.obs, scene.meta, self.plain),
                             reference(scene.obs, scene.meta, self.plain))

    def test_short_exit_that_returns_is_ignored(self):
        scene = self.touchline_blip(3)
        self.assertEqual(collapse(reference(scene.obs, scene.meta, self.plain))[-1], ('D', 125))
        self.assertEqual(collapse(predict(scene.obs, scene.meta, self.config)),
                         [('D', 49), ('H', 276)])

    def test_lasting_exit_is_still_dead(self):
        scene = self.touchline_blip(40)
        labels = predict(scene.obs, scene.meta, self.config)
        self.assertEqual(labels[200:240], ['D'] * 40)

    def test_exit_next_to_missing_ball_is_kept(self):
        known = np.array([True, True, True, False, False, True, True, True])
        outside = np.array([False, False, True, False, False, True, False, False])
        kept = confirm_outside(outside, known, 10)
        self.assertTrue(kept[2])        # followed by a gap: the ball left and was removed
        self.assertTrue(kept[5])        # preceded by a gap: a release from outside the pitch
        edge = confirm_outside(np.array([True, False, False, True]), np.ones(4, dtype=bool), 10)
        self.assertEqual(edge.tolist(), [True, False, False, True])

    def test_fast_reappearance_revives_play_for_first_controller(self):
        scene = self.late_reappearance()
        self.assertEqual(collapse(reference(scene.obs, scene.meta, self.plain))[-1], ('D', 425))
        labels, audit = infer(scene.obs, scene.meta, self.config)
        self.assertEqual(collapse(labels), [('D', 49), ('H', 76), ('D', 200), ('H', 225)])
        self.assertEqual([g['frame'] for g in audit['revived_gaps']], [325])

    def test_revival_takes_the_team_that_controls_first(self):
        scene = self.late_reappearance(receiver='25')
        labels = predict(scene.obs, scene.meta, self.config)
        self.assertEqual(collapse(labels)[-2:], [('D', 200), ('A', 225)])

    def test_no_revival_when_ball_leaves_before_any_control(self):
        scene = self.late_reappearance(exit_before_control=True)
        labels, audit = infer(scene.obs, scene.meta, self.config)
        self.assertEqual(audit['revived_gaps'], [])
        self.assertEqual(labels[125:], ['D'] * 425)

    def test_slow_reappearance_still_waits_for_a_release(self):
        scene = kickoff_pass(450)
        scene.put('ball', 125, 275, [np.nan, np.nan])    # 6 s: longer than gap_s
        labels, audit = infer(scene.obs, scene.meta, self.config)
        self.assertEqual(len(audit['long_gaps']), 1)
        self.assertEqual(audit['revived_gaps'], [])
        self.assertEqual(labels[125:], ['D'] * 325)

    def test_brief_opposing_control_is_absorbed(self):
        scene = self.brief_touch(10)
        self.assertIn('A', reference(scene.obs, scene.meta, self.plain))
        labels, audit = infer(scene.obs, scene.meta, self.config)
        self.assertEqual(collapse(labels), [('D', 49), ('H', 326)])
        self.assertEqual(audit['absorbed_possessions'], 1)

    def test_longer_opposing_control_is_kept(self):
        scene = self.brief_touch(60)
        labels = predict(scene.obs, scene.meta, self.config)
        self.assertGreaterEqual(labels.count('A'), 25)

    def test_absorption_rules_on_label_runs(self):
        def squash(text, min_frames=3):
            return ''.join(absorb_short_possessions(list(text), min_frames)[0])

        self.assertEqual(squash('HHHHAAHHHH'), 'HHHHHHHHHH')
        self.assertEqual(squash('HHHHAAAHHH'), 'HHHHAAAHHH')    # at the threshold: kept
        self.assertEqual(squash('HHHHAADDDD'), 'HHHHHHDDDD')    # touch, then dead ball
        self.assertEqual(squash('DDDDAAHHHH'), 'DDDDAAHHHH')    # first run after a restart
        self.assertEqual(squash('HHHHHHHHAA'), 'HHHHHHHHAA')    # cut off by the end of the data
        self.assertEqual(squash('HHHHAAHAAHHHH'), 'HHHHHHHHHHHHH')
        self.assertEqual(squash('HHHHDDHHHH'), 'HHHHDDHHHH')    # a dead ball is never absorbed
        self.assertEqual(squash('HHHHAAHHHH', 0), 'HHHHAAHHHH')


if __name__ == '__main__':
    unittest.main()
