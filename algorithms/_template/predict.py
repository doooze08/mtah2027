"""Entry point of an algorithm. Copy this folder, rename it, then implement predict().

Contract shared by every algorithm so scripts can run any of them the same way:

    labels = predict(config)   # sequence of 'H' / 'A' / 'D' / 'X', one per tactical video frame

Writing the CSV, validating and scoring are handled by scripts/, not here.

Optional second entry, for the simulation test bench (simulation/run_algorithm.py):

    labels = predict_clip(observations, game_state, config)   # one label per clip frame

It sees one simulated clip at a time, in metres, and nothing else (no truth, no scenario name).
"""


def predict(config):
    """Return one label per tactical video frame.

    Args:
        config: dict loaded from experiments/<experiment_id>/config.yaml (the `params` section).
    """
    raise NotImplementedError("Template only -- copy algorithms/_template to a new folder first.")


def predict_clip(observations, game_state, config):
    """Return one label per frame of a simulated clip.

    Args:
        observations: DataFrame with columns frame, object, team, x, y, z. One row per object
            per frame: object "ball" (team empty, z = height) or "p01".."p22" (team "H"/"A",
            z empty). Positions in metres on a 105 x 68 pitch, frames from 0.
        game_state: DataFrame with columns frame, play_live (1/0), restart_team ("H"/"A" on the
            frame a restart takes effect, else "").
        config: the `params` section of experiments/<experiment_id>/config.yaml.
    """
    raise NotImplementedError("Template only -- implement if the algorithm runs on simulations.")
