"""Optional ball-only observation gaps; these assumptions never change story events."""

from dataclasses import asdict, dataclass

import numpy as np

from simulation.core.constants import FPS
from simulation.core.events import play_live_from_events


@dataclass(frozen=True)
class BallGapConfig:
    # Relative weights, not estimates of a tracking provider's policy.
    policy_weights: tuple = (1.0, 1.0, 1.0)
    delayed_start_seconds: tuple = (2.0, 5.0)
    live_gaps_per_second: float = 13 / 5400
    live_long_gaps_per_second: float = 0.0

    def __post_init__(self):
        if min(self.policy_weights) < 0 or sum(self.policy_weights) <= 0:
            raise ValueError("gap policy weights must be nonnegative with a positive sum")
        low, high = self.delayed_start_seconds
        if (not 0 <= low <= high or self.live_gaps_per_second < 0
                or self.live_long_gaps_per_second < 0):
            raise ValueError("gap delays and live gap rates must be nonnegative")

    def manifest(self):
        return dict(asdict(self), assumption="synthetic policy; not an official provider rule",
                    policy_order=["whole", "delayed", "visible"],
                    start_jitter_frames=[0, 5], restore_early_frames=[0, 1],
                    live_gap_frames=[1, 4], live_long_gap_frames=[125, 375],
                    live_long_gap_rate_per_live_second=self.live_long_gaps_per_second,
                    rng_stream="SeedSequence([story_seed, 4279])")


def intervals(mask):
    """Half-open intervals of true frames, without joining clip boundaries."""
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False]))
    return zip(edges[::2], edges[1::2])


def ball_gap_mask(clip, seed, config):
    """Return the observation mask and a manifest-only audit of dead-ball policies."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 4279]))
    live = np.asarray(play_live_from_events(clip.events, clip.n_frames), dtype=bool)
    missing = np.zeros(clip.n_frames, dtype=bool)
    probabilities = np.asarray(config.policy_weights) / sum(config.policy_weights)
    audit = []
    for start, stop in intervals(~live):
        policy = str(rng.choice(["whole", "delayed", "visible"], p=probabilities))
        first, restore = int(start), int(stop)
        if policy != "visible":
            first += int(rng.integers(0, 6))
            if policy == "delayed":
                first += int(np.ceil(rng.uniform(*config.delayed_start_seconds) * FPS))
            # A clip ending dead has no restart to restore before.
            if stop < clip.n_frames:
                restore -= int(rng.integers(0, 2))
            first = min(first, restore)
            missing[first:restore] = True
        audit.append(dict(dead_start=int(start), dead_stop=int(stop), policy=policy,
                          missing_start=first if policy != "visible" else None,
                          missing_stop=restore if policy != "visible" else None))

    if config.live_gaps_per_second:
        for start, stop in intervals(live):
            cursor = float(start)
            while True:
                cursor += rng.exponential(FPS / config.live_gaps_per_second)
                first = max(int(cursor), int(start) + 1)
                length = int(rng.integers(1, 5))
                # Keep a visible frame on both ends; short gaps cannot merge with dead gaps.
                if first + length >= stop:
                    break
                missing[first:first + length] = True
                cursor = first + length + 1

    if config.live_long_gaps_per_second:
        for start, stop in intervals(live):
            cursor = float(start)
            while True:
                cursor += rng.exponential(FPS / config.live_long_gaps_per_second)
                first = max(int(cursor), int(start) + 1)
                length = int(rng.integers(5 * FPS, 15 * FPS + 1))
                # Keep the requested 5-15 s length and a visible frame after it. Shift
                # past any existing short gap rather than shortening or merging the run.
                while first + length < stop and (
                        missing[first:first + length].any() or missing[first + length]):
                    first += 1
                if first + length >= stop:
                    break
                missing[first:first + length] = True
                cursor = first + length + 1
    return missing, audit
