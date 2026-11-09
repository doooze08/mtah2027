"""Dataset I/O with separate algorithm, grading and debugging paths.

load_clips opens only observations.csv and metadata.json. This is an interface boundary,
not an operating-system sandbox (see experiments/README.md).
"""

import json
import os

import pandas as pd

from observations.schema import COLUMNS, validate
from simulation.core.constants import EVENT_COLUMNS, SAMPLE_COLUMNS, TRUTH_COLUMNS

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIMULATION_SETS = os.path.join(REPO_ROOT, "outputs", "simulation_sets")
OBSERVATIONS_FILE = "observations.csv"
METADATA_FILE = "metadata.json"
CLEAN_FILE = os.path.join("debug", "clean_positions.csv")
TRUTH_FILE = "truth.csv"
EVENTS_FILE = "events.csv"
SAMPLES_FILE = "samples.csv"
MANIFEST_FILE = "manifest.json"


def dataset_dir(dataset_id):
    return os.path.join(SIMULATION_SETS, dataset_id)


def write_dataset(directory, observations, metadata, truth, events, samples, clean):
    """Write a new dataset; old layouts must be regenerated under a new dataset id."""
    os.makedirs(directory, exist_ok=False)
    tables = [(OBSERVATIONS_FILE, observations, ["clip"] + COLUMNS),
              (TRUTH_FILE, truth, TRUTH_COLUMNS),
              (EVENTS_FILE, events, EVENT_COLUMNS),
              (SAMPLES_FILE, samples, SAMPLE_COLUMNS),
              (CLEAN_FILE, clean, ["clip", "frame", "object", "team", "x", "y", "z"])]
    for name, table, columns in tables:
        path = os.path.join(directory, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        table[columns].to_csv(path, index=False, float_format="%.10g")
    with open(os.path.join(directory, METADATA_FILE), "w") as handle:
        json.dump(metadata, handle, indent=2, allow_nan=False)


def load_clips(directory):
    """Yield (clip_id, observations, metadata), reading only algorithm-visible files."""
    metadata_path = os.path.join(directory, METADATA_FILE)
    observations = pd.read_csv(os.path.join(directory, OBSERVATIONS_FILE), dtype={"clip": str})
    with open(metadata_path) as handle:
        metadata = json.load(handle)
    for clip_id, clip_obs in observations.groupby("clip", sort=True):
        frames = clip_obs.drop(columns="clip").reset_index(drop=True)
        validate(frames)
        yield clip_id, frames, metadata[clip_id]


def load_answers(directory):
    """Grading input: (truth, samples, events) DataFrames for the whole dataset."""
    truth = pd.read_csv(os.path.join(directory, TRUTH_FILE), dtype={"clip": str})
    samples = pd.read_csv(os.path.join(directory, SAMPLES_FILE), dtype={"clip": str})
    events = pd.read_csv(os.path.join(directory, EVENTS_FILE), dtype={"clip": str},
                         keep_default_na=False)
    return truth, samples, events
