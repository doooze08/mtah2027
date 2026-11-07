"""Export an offline viewer of existing simulated observations, answers and predictions.

    python -m simulation.view --dataset <dataset_id> --experiment <experiment_id>

This is a human inspection tool, not an input to possession algorithms.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from simulation.core.constants import FPS, PITCH_LENGTH, PITCH_WIDTH
from simulation.core.io import REPO_ROOT, dataset_dir


def build_payload(dataset_id, experiment_id):
    """Join labels by clip/frame and pack positions in a fixed object order."""
    directory = Path(dataset_dir(dataset_id))
    output = Path(REPO_ROOT) / "outputs" / experiment_id / "simulation" / dataset_id
    observations = pd.read_csv(directory / "observations.csv")
    state = pd.read_csv(directory / "game_state.csv", keep_default_na=False)
    truth = pd.read_csv(directory / "truth.csv").rename(columns={"label": "truth"})
    samples = pd.read_csv(directory / "samples.csv")
    events = pd.read_csv(directory / "events.csv", keep_default_na=False)
    keys = ["clip", "frame"]
    assert not observations.duplicated(keys + ["object"]).any()
    assert observations.groupby(keys).size().eq(23).all()
    labels = state.merge(truth, on=keys, how="outer", validate="one_to_one", indicator=True)
    assert labels.pop("_merge").eq("both").all()
    assert labels["truth"].isin(["H", "A", "D"]).all()
    if (output / "predictions.csv").exists():
        predictions = pd.read_csv(output / "predictions.csv").rename(columns={"label": "prediction"})
        assert predictions["prediction"].isin(["H", "A", "D", "X"]).all()
        labels = labels.merge(predictions, on=keys, how="outer", validate="one_to_one", indicator=True)
        assert not labels.pop("_merge").eq("right_only").any()
    else:
        labels["prediction"] = None

    objects = ["ball"] + ["p{:02d}".format(i) for i in range(1, 23)]
    clips = []
    assert not samples["clip"].duplicated().any()
    assert set(samples["clip"]) == set(observations["clip"]) == set(labels["clip"])
    for sample in samples.sort_values("clip").to_dict("records"):
        clip_id, n_frames = sample["clip"], int(sample["n_frames"])
        obs = observations[observations["clip"] == clip_id]
        frame_labels = labels[labels["clip"] == clip_id].sort_values("frame")
        assert frame_labels["frame"].tolist() == list(range(n_frames))
        assert sorted(obs["frame"].unique()) == list(range(n_frames))
        assert set(obs["object"]) == set(objects)
        index = pd.MultiIndex.from_product([range(n_frames), objects], names=["frame", "object"])
        ordered = obs.set_index(["frame", "object"]).reindex(index)
        positions = json.loads(ordered[["x", "y", "z"]].to_json(orient="values", double_precision=10))
        clips.append({
            "id": clip_id,
            "subtype": sample["subtype"],
            "initiatingTeam": sample["initiating_team"],
            "core": [int(sample["core_start"]), int(sample["core_stop"])],
            "positions": [positions[f * 23:(f + 1) * 23] for f in range(n_frames)],
            "objects": [{"id": obj, "team": None if obj == "ball" else
                         obs.loc[obs["object"] == obj, "team"].iloc[0]} for obj in objects],
            "truth": frame_labels["truth"].tolist(),
            "prediction": frame_labels["prediction"].where(frame_labels["prediction"].notna(), None).tolist(),
            "events": events[events["clip"] == clip_id].to_dict("records"),
        })
    return {"dataset": dataset_id, "experiment": experiment_id, "fps": FPS,
            "pitch": [PITCH_LENGTH, PITCH_WIDTH], "clips": clips}, output


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--experiment", required=True)
    args = parser.parse_args()
    for identifier in (args.dataset, args.experiment):
        assert identifier not in (".", "..") and Path(identifier).name == identifier
    payload, output = build_payload(args.dataset, args.experiment)
    template = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
    embedded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    output.mkdir(parents=True, exist_ok=True)
    target = output / "viewer.html"
    target.write_text(template.replace("__SIMULATION_PAYLOAD__", embedded), encoding="utf-8")
    print("Exported {} clips to {}".format(len(payload["clips"]), target))


if __name__ == "__main__":
    main()
