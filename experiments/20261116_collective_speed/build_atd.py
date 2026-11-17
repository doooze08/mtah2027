"""Build the cached ATD collective-speed features for this experiment.

The cache stays under ``outputs/20261116_collective_speed/`` and is not committed. The
loader is the project's tactical ATD reader; no labels or answers are read.
"""

import os
import time

from features import load_atd, save_atd_cache


def main():
    started = time.time()
    observations, features, metadata = load_atd()
    save_atd_cache(observations, features)
    print("rows={} columns={} fps={} elapsed={:.1f}s".format(
        len(observations), len(observations.columns), metadata["fps"],
        time.time() - started))
    print("cache={}".format(os.path.relpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "outputs",
                     "20261116_collective_speed", "atd_features.npz"))))


if __name__ == "__main__":
    main()
