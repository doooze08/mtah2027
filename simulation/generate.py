"""Generate a simulation dataset: run scenario scripts, self-check them, write the files.

    .venv/bin/python -m simulation.generate --dataset-id clean_v1_skeleton --subtypes TI01,HD01

For every subtype and story it builds two clips from the same seed: one where H starts the story
and one where A does (pitch rotated 180 degrees). If any clip fails a self-check, nothing is
written. Output goes to outputs/simulation_sets/<dataset_id>/ (see simulation/README.md).
"""

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from simulation.core import ClipBuilder, checks, io
from simulation.core import events as ev
from simulation.core.constants import AWAY, HOME
from simulation.core.observe import observe
from simulation.scenarios import all_subtypes


def build_clips(subtype_ids, n_stories, base_seed):
    """Run each script for each story and both initiating teams.

    Returns a list of dicts with the rendered clip and its sample description.
    """
    registry = all_subtypes()
    unknown = [s for s in subtype_ids if s not in registry]
    if unknown:
        raise SystemExit("unknown subtypes {}; known: {}".format(unknown, sorted(registry)))

    built = []
    for subtype in subtype_ids:
        family, build = registry[subtype]
        for story in range(n_stories):
            seed = base_seed + story
            for initiating_team in (HOME, AWAY):
                rng = np.random.default_rng(seed)       # same seed -> same story, both versions
                builder = ClipBuilder(rng, initiating_team)
                build(builder, rng)
                clip = builder.finish()
                built.append({
                    "clip": clip,
                    "family": family,
                    "subtype": subtype,
                    "story_id": "{}-{:03d}".format(subtype, story + 1),
                    "seed": seed,
                    "initiating_team": initiating_team,
                })
    return built


def assign_clip_ids(built, base_seed):
    """Opaque ids c001, c002, ... in shuffled order, so an id says nothing about the scenario."""
    order = np.random.default_rng(base_seed).permutation(len(built))
    for clip_number, index in enumerate(order, start=1):
        built[index]["clip_id"] = "c{:03d}".format(clip_number)
    return sorted(built, key=lambda item: item["clip_id"])


def tables(built):
    """Build algorithm observations separately from answers and debug-only clean positions."""
    observations, metadata, truth, events, samples, clean = [], {}, [], [], [], []
    for item in built:
        clip, clip_id = item["clip"], item["clip_id"]
        obs, meta = observe(clip, seed=item["seed"])
        observations.append(obs.assign(clip=clip_id))
        metadata[clip_id] = meta
        clean.append(clip.frames.assign(clip=clip_id))
        truth.append(pd.DataFrame({"clip": clip_id, "frame": range(clip.n_frames),
                                   "label": clip.truth}))
        events.append(pd.DataFrame([{"clip": clip_id, "event": e.kind, "t": e.t,
                                     "frame": e.frame, "team": e.team or ""}
                                    for e in clip.events]))
        samples.append({
            "clip": clip_id, "family": item["family"], "subtype": item["subtype"],
            "story_id": item["story_id"], "seed": item["seed"],
            "initiating_team": item["initiating_team"], "n_frames": clip.n_frames,
            "core_start": clip.core_window[0], "core_stop": clip.core_window[1],
            "expected_sequence": " ".join(clip.expected_sequence),
        })
    return (pd.concat(observations), metadata, pd.concat(truth),
            pd.concat(events), pd.DataFrame(samples), pd.concat(clean))


def verify_written(directory):
    """Re-read the files and confirm truth.csv still follows from events.csv, clip by clip."""
    truth, samples, events = io.load_answers(directory)
    problems = []
    for sample in samples.itertuples(index=False):
        clip_events = [ev.Event(row.event, float(row.t), row.team or None)
                       for row in events[events["clip"] == sample.clip].itertuples(index=False)]
        derived = ev.truth_from_events(clip_events, int(sample.n_frames))
        stored = truth[truth["clip"] == sample.clip].sort_values("frame")["label"].tolist()
        if derived != stored:
            problems.append("{}: truth.csv does not follow from events.csv".format(sample.clip))
    return problems


def write_manifest(directory, args):
    def git(*command):
        try:
            return subprocess.check_output(["git"] + list(command), cwd=io.REPO_ROOT,
                                           text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    manifest = {
        "dataset_id": args.dataset_id,
        "command": "python -m simulation.generate " + " ".join(sys.argv[1:]),
        "subtypes": args.subtypes,
        "stories_per_subtype": args.stories,
        "base_seed": args.seed,
        "observation_layer": "atd_format_v2_all_slot_teams_no_defects",
        "slot_mapping": "story seed; 24 H / 22 A slots; 11 active players per team",
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain", "--", "simulation")),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(os.path.join(directory, io.MANIFEST_FILE), "w") as handle:
        json.dump(manifest, handle, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--subtypes", required=True, help="comma-separated, e.g. TI01,HD01")
    parser.add_argument("--stories", type=int, default=1, help="stories per subtype")
    parser.add_argument("--seed", type=int, default=0, help="base seed; story k uses seed + k")
    args = parser.parse_args()
    args.subtypes = [s.strip() for s in args.subtypes.split(",") if s.strip()]

    directory = io.dataset_dir(args.dataset_id)
    if os.path.exists(directory):
        raise SystemExit("{} exists; pick a new dataset id".format(directory))

    built = assign_clip_ids(build_clips(args.subtypes, args.stories, args.seed), args.seed)

    failed = False
    for item in built:
        problems = checks.run_all(item["clip"])
        status = "ok" if not problems else "FAILED"
        print("{}  {}  starts={}  {:>4} frames  {}  self-check {}".format(
            item["clip_id"], item["story_id"], item["initiating_team"], item["clip"].n_frames,
            " -> ".join(item["clip"].expected_sequence), status))
        for problem in problems:
            print("      - " + problem)
        failed = failed or bool(problems)
    if failed:
        raise SystemExit("self-check failed; nothing written")

    io.write_dataset(directory, *tables(built))
    problems = verify_written(directory)
    if problems:
        raise SystemExit("\n".join(problems))
    write_manifest(directory, args)
    print("wrote {} clips to {}".format(len(built), os.path.relpath(directory, io.REPO_ROOT)))


if __name__ == "__main__":
    main()
