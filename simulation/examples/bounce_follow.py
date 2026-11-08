"""Export paired follow-off/on bounce examples through the existing dataset pipeline."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

from simulation.core import ClipBuilder, checks, io
from simulation.generate import assign_clip_ids, tables, verify_written, write_manifest


def build_example(seed=0, team="H", follow_ball=False, horizontal_retention=0.75):
    """A generic unreceived high pass: three rebounds, rolling, then a stopped ball."""
    rng = np.random.default_rng(seed)
    b = ClipBuilder(rng, team, follow_ball=follow_ball)
    passer = b.player("atk", "lcb")
    runner = b.player("dfn", "rs")
    b.place_ball(passer)
    b.hold(passer, 1.0)
    b.event("legal_restart", team="atk")
    b.begin_core()
    b.run_to(runner, (48, 38), arrive_at=b.now + 3.0, seconds=2.0)
    b.bounce_to(1.2, point=(38 + rng.uniform(-0.5, 0.5), 42.0),
                horizontal_retention=horizontal_retention)
    b.end_core()
    b.wait(2.0)
    b.expect("D", "atk")
    return b.finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    built = []
    for enabled in (False, True):
        for team in ("H", "A"):
            clip = build_example(args.seed, team, enabled)
            problems = checks.run_all(clip)
            assert not problems, problems
            subtype = "FOLLOW_ON" if enabled else "FOLLOW_OFF"
            built.append(dict(clip=clip, family="motion_example", subtype=subtype,
                              story_id="bounce-{:03d}".format(args.seed), seed=args.seed,
                              initiating_team=team))
    directory = io.dataset_dir(args.dataset_id)
    assert not Path(directory).exists(), "use a new dataset id"
    io.write_dataset(directory, *tables(assign_clip_ids(built, args.seed)))
    assert not verify_written(directory)
    args.subtypes = ["FOLLOW_OFF", "FOLLOW_ON"]
    args.stories = 1
    write_manifest(directory, args)
    # The shared manifest helper names the regular generator; record the real entry point.
    manifest_path = Path(directory) / io.MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text())
    manifest["command"] = "python -m simulation.examples.bounce_follow " + " ".join(sys.argv[1:])
    manifest["follow_ball"] = {item["clip_id"]: item["subtype"] == "FOLLOW_ON" for item in built}
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print("Wrote 4 paired motion examples to " + directory)


if __name__ == "__main__":
    main()
