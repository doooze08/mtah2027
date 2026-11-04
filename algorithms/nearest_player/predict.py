"""Nearest player: the team of whichever player is closest to the ball has possession.

A deliberately naive reference used to prove the simulation pipeline end to end. It treats
"closest" as "in control", which is exactly the mistake several scenarios are built to expose
(a lost header duel, a deflection, a ball flying over a defender). If it ever scores perfectly on
such a scenario, the scenario has a hole, not the algorithm a strength.

Rule per frame:
    play_live == 0  -> D
    otherwise       -> team of the player with the smallest horizontal distance to the ball
"""

import numpy as np


def predict(config):
    raise NotImplementedError("nearest_player only runs on simulated clips; use predict_clip().")


def predict_clip(observations, game_state, config):
    """One label per clip frame. See algorithms/_template/predict.py for the input columns."""
    ball = observations[observations["object"] == "ball"].set_index("frame")[["x", "y"]]
    players = observations[observations["object"] != "ball"]

    labels = []
    for frame, live in game_state[["frame", "play_live"]].itertuples(index=False):
        if not live:
            labels.append("D")
            continue
        here = players[players["frame"] == frame]
        bx, by = ball.loc[frame]
        distance = np.hypot(here["x"].to_numpy() - bx, here["y"].to_numpy() - by)
        labels.append(here["team"].to_numpy()[np.argmin(distance)])
    return labels
