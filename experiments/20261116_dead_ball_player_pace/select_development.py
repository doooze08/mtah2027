"""Reproduce the small development grid for the two player-pace switches.

Only Metrica Game 1 and Game 2 (the development sets) are read.  The chosen values are
copied into config.yaml; this script does not change them and never reads the test sets.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
import yaml

from algorithms.dead_ball_aware.predict import infer
from simulation.core import io

sys.path.insert(0, os.path.join(io.REPO_ROOT, "evaluation"))
import possession_metrics as pm  # noqa: E402

EXPERIMENT = "20261116_dead_ball_player_pace"
DATASETS = ["ext_metrica_game_1", "ext_metrica_game_2"]
OUT = os.path.join(io.REPO_ROOT, "outputs", EXPERIMENT, "dev_grid.csv")


def clips():
    for dataset in DATASETS:
        truth, _, _ = io.load_answers(io.dataset_dir(dataset))
        for clip, observations, metadata in io.load_clips(io.dataset_dir(dataset)):
            labels = truth[truth["clip"] == clip].sort_values("frame")["label"].tolist()
            yield dataset, clip, observations, metadata, labels


def metrics(labels, truth):
    gt = pm.label_codes(np.array(truth))
    pred = pm.label_codes(np.array(labels))
    official = pm.evaluate(gt, pred)
    return {
        "d_f1": official["per_class"]["D"]["f1"],
        "macro_f1": official["macro_f1"],
        "spell_f1": official["spell_f1_mean"],
        "alive_dead_f1": official["alive_dead_f1"],
    }


def main():
    config = yaml.safe_load(open(os.path.join(
        io.REPO_ROOT, "experiments", EXPERIMENT, "config.yaml")))
    base = config["params"]
    rows = []
    for p in (0.4, 0.6, 0.8):
        params = {**base, "gap_requires_slow_players": True,
                  "gap_slow_fraction": p}
        for dataset, clip, observations, metadata, truth in clips():
            result = metrics(infer(observations, metadata, params)[0], truth)
            rows.append({"arm": "gap", "p": p, "w": None, "delta": None,
                         "dataset": dataset, "clip": clip, **result})
    for window in (1.0, 2.0, 3.0):
        for delta in (0.3, 0.5, 0.8):
            params = {**base, "restart_requires_player_rise": True,
                      "player_rise_window_s": window,
                      "player_rise_delta_m_s": delta}
            for dataset, clip, observations, metadata, truth in clips():
                result = metrics(infer(observations, metadata, params)[0], truth)
                rows.append({"arm": "restart", "p": None, "w": window,
                             "delta": delta, "dataset": dataset, "clip": clip,
                             **result})
    frame = pd.DataFrame(rows)
    grouped = frame.groupby(["arm", "p", "w", "delta"], dropna=False).agg(
        d_f1=("d_f1", "mean"), macro_f1=("macro_f1", "mean"),
        spell_f1=("spell_f1", "mean"), alive_dead_f1=("alive_dead_f1", "mean"),
        n_clips=("dataset", "count")).reset_index()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    frame.to_csv(OUT, index=False)
    print(grouped.sort_values(["arm", "d_f1"], ascending=[True, False]).to_string(
        index=False))


if __name__ == "__main__":
    main()
