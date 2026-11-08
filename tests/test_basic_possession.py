"""Regression checks for unambiguous possession stories, without competition data."""

import unittest

import numpy as np

from simulation.core import ClipBuilder, checks
from simulation.core.clip import ball_fully_out
from simulation.core.constants import BALL_RADIUS, FPS, PITCH_LENGTH, PITCH_WIDTH
from simulation.core.motion import BallWithPlayer
from simulation.scenarios import all_subtypes


class BasicPossessionTests(unittest.TestCase):
    def test_stories_and_mirrors(self):
        registry = all_subtypes()
        pass_counts = set()
        hold_durations = set()
        for subtype in ("BP01", "BP02", "BP03"):
            self.assertEqual(registry[subtype][0], "basic_possession")
            for seed in range(20):
                clips = []
                for team in ("H", "A"):
                    with self.subTest(subtype=subtype, seed=seed, team=team):
                        rng = np.random.default_rng(seed)
                        builder = ClipBuilder(rng, team)
                        registry[subtype][1](builder, rng)
                        clip = builder.finish()
                        clips.append(clip)
                        frozen = {("atk", "rcb"), ("atk", "lcb")}
                        if subtype == "BP01":
                            frozen.add(("atk", "rcm"))
                        elif subtype == "BP02":
                            frozen.add(("dfn", "ls"))
                        for player in builder.all_players():
                            if (player.team, player.role) in frozen:
                                self.assertEqual(player.sway_amplitude, (0.0, 0.0))
                            else:
                                self.assertTrue(all(a > 0 for a in player.sway_amplitude))
                                positions = np.array([player.position(t) for t in (0, 0.5, 1)])
                                self.assertGreater(np.ptp(positions, axis=0).max(), 0.0)
                        self.assertEqual(checks.run_all(clip), [])
                        self.assertGreaterEqual((clip.n_frames - 1) / FPS, 10.0)
                        self.assertLessEqual((clip.n_frames - 1) / FPS, 20.0)
                        self.assertEqual(clip.truth[:FPS], ["D"] * FPS)
                        self.assertEqual(clip.truth[FPS], team)
                        tail = (clip.n_frames - clip.core_window[1]) / FPS
                        self.assertGreaterEqual(tail, 2.0 - 1 / FPS)
                        self.assertLessEqual(tail, 4.0 + 1 / FPS)

                        if subtype == "BP01":
                            self.assertEqual(set(clip.truth[FPS:]), {team})
                            # Exclude the shared dead-ball and live opening holds.
                            holds = [s for s in builder._ball_segments
                                     if isinstance(s, BallWithPlayer)
                                     and s.t0 >= clip.core_window[0] / FPS - 1 / FPS
                                     and s.start_offset == s.target_offset
                                     and s.target_offset == (0.0, 0.0, BALL_RADIUS)
                                     and s.t1 > s.t0]
                            pass_counts.add(len(holds))
                            self.assertIn(len(holds), (2, 3, 4))
                            for hold in holds:
                                self.assertGreaterEqual(hold.t1 - hold.t0, 0.5 - 1e-9)
                                self.assertLessEqual(hold.t1 - hold.t0, 3.0 + 1e-9)
                                hold_durations.add(round(hold.t1 - hold.t0, 8))
                                times = np.linspace(hold.t0, hold.t1, 5, endpoint=False)
                                positions = np.array([clip.ball_at(t) for t in times])
                                np.testing.assert_allclose(positions, np.tile(positions[0], (5, 1)))

                        if subtype == "BP02":
                            opponent = "A" if team == "H" else "H"
                            event = next(e for e in clip.events
                                         if e.kind == "control_start" and e.team == opponent)
                            self.assertEqual(clip.truth[event.frame - 1], team)
                            self.assertEqual(set(clip.truth[event.frame:]), {opponent})
                            self.assertGreater(np.linalg.norm(
                                np.array(clip.ball_at((clip.n_frames - 1) / FPS)[:2])
                                - np.array(clip.ball_at(event.t)[:2])), 1.0)

                        if subtype == "BP03":
                            event = next(e for e in clip.events if e.kind == "ball_out")
                            self.assertEqual(clip.truth[event.frame - 1], team)
                            self.assertEqual(set(clip.truth[event.frame:]), {"D"})
                            self.assertFalse(ball_fully_out(clip.ball_at(event.t - 1e-6)))
                            self.assertTrue(ball_fully_out(clip.ball_at(event.t + 1e-6)))
                            self.assertFalse(any(t > event.t for t in clip.contact_times))
                            self.assertFalse(any(e.kind == "incidental_touch" for e in clip.events))

                home, away = clips
                self.assertEqual(home.n_frames, away.n_frames)
                self.assertEqual([{"H": "A", "A": "H", "D": "D"}[x]
                                  for x in home.truth], away.truth)
                # Match roles across swapped teams, rather than comparing opaque object ids.
                for frame in (0, home.core_window[0], home.n_frames - 1):
                    t = frame / FPS
                    hx, hy, hz = home.ball_at(t)
                    np.testing.assert_allclose(away.ball_at(t),
                                               (PITCH_LENGTH - hx, PITCH_WIDTH - hy, hz))
                    for hp, ap in zip(home.players_at(t), away.players_at(t)):
                        self.assertNotEqual(hp[1], ap[1])
                        np.testing.assert_allclose(ap[2:], (PITCH_LENGTH - hp[2], PITCH_WIDTH - hp[3]))
        self.assertEqual(pass_counts, {2, 3, 4})
        self.assertGreater(len(hold_durations), 20)


if __name__ == "__main__":
    unittest.main()
