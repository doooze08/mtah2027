"""Reading and writing a simulation dataset: outputs/simulation_sets/<dataset_id>/.

Two sides, kept apart on purpose:

    algorithm side   load_clips()          observations.csv + game_state.csv only
    grading side     load_answers()        truth.csv + samples.csv (+ events.csv)

An algorithm runner imports only load_clips(). Nothing stops a determined reader from opening
truth.csv (see docs/EXPERIMENTS.md); the split makes the honest path the easy one.
"""

import os

import pandas as pd

from simulation.core.constants import (EVENT_COLUMNS, GAME_STATE_COLUMNS, OBSERVATION_COLUMNS,
                                       SAMPLE_COLUMNS, TRUTH_COLUMNS)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIMULATION_SETS = os.path.join(REPO_ROOT, "outputs", "simulation_sets")

OBSERVATIONS_FILE = "observations.csv"
GAME_STATE_FILE = "game_state.csv"
TRUTH_FILE = "truth.csv"
EVENTS_FILE = "events.csv"
SAMPLES_FILE = "samples.csv"
MANIFEST_FILE = "manifest.json"


def dataset_dir(dataset_id):
    return os.path.join(SIMULATION_SETS, dataset_id)


def write_dataset(directory, observations, game_state, truth, events, samples):
    """Write the five tables. Each argument is a DataFrame already holding every clip."""
    os.makedirs(directory, exist_ok=True)
    tables = [(OBSERVATIONS_FILE, observations, OBSERVATION_COLUMNS),
              (GAME_STATE_FILE, game_state, GAME_STATE_COLUMNS),
              (TRUTH_FILE, truth, TRUTH_COLUMNS),
              (EVENTS_FILE, events, EVENT_COLUMNS),
              (SAMPLES_FILE, samples, SAMPLE_COLUMNS)]
    for name, table, columns in tables:
        table[columns].to_csv(os.path.join(directory, name), index=False, float_format="%.4f")


def load_clips(directory):
    """Algorithm input: yields (clip_id, observations, game_state), one clip at a time.

    observations: frame, object, team, x, y, z   (z only for the ball)
    game_state:   frame, play_live, restart_team (restart_team is "" except on a restart frame)
    """
    observations = pd.read_csv(os.path.join(directory, OBSERVATIONS_FILE),
                               dtype={"clip": str, "object": str, "team": str})
    game_state = pd.read_csv(os.path.join(directory, GAME_STATE_FILE),
                             dtype={"clip": str, "restart_team": str}, keep_default_na=False)
    for clip_id, clip_obs in observations.groupby("clip", sort=True):
        clip_state = game_state[game_state["clip"] == clip_id]
        yield (clip_id,
               clip_obs.drop(columns="clip").reset_index(drop=True),
               clip_state.drop(columns="clip").sort_values("frame").reset_index(drop=True))


def load_answers(directory):
    """Grading input: (truth, samples, events) DataFrames for the whole dataset."""
    truth = pd.read_csv(os.path.join(directory, TRUTH_FILE), dtype={"clip": str})
    samples = pd.read_csv(os.path.join(directory, SAMPLES_FILE), dtype={"clip": str})
    events = pd.read_csv(os.path.join(directory, EVENTS_FILE), dtype={"clip": str},
                         keep_default_na=False)
    return truth, samples, events
