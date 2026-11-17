"""Render-only background motion for the optional collective-pace experiment.

The behaviour is intentionally synthetic. It makes the median speed of background
players follow a story-level live/dead target so that collective-speed algorithms can be
exercised in simulation. It is not a model of real player intent and cannot validate a
collective-speed algorithm; validity is measured on external matches only.

Every background player follows a small closed loop around its formation position. All
loops share one speed profile, so each player's instantaneous speed equals the profile;
the loop radius only changes how quickly the player turns. This keeps the median speed
predictable without changing any scripted role or the ball.

The speed profile is derived only from the script event list (via play/dead intervals),
never from observations or a possession algorithm. It is switched on by
``ClipBuilder(..., collective_pace=True)``; the default is off and renders exactly as
before.
"""

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from simulation.core import events as ev
from simulation.core.constants import FPS

# Story-level targets and counterexample coverage. These are deliberately wider than the
# external measurements and are test-range assumptions, not fitted match statistics.
LIVE_MEDIAN_RANGE = (1.4, 2.4)
DEAD_MEDIAN_RANGE = (0.5, 1.4)
TRANSITION_RANGE = (1.0, 3.0)
DEAD_FAST_PROBABILITY = 0.20
LIVE_SLOW_PROBABILITY = 0.20
DEAD_FAST_RANGE = (1.8, 2.6)
LIVE_SLOW_RANGE = (0.25, 0.85)
LOOP_RADIUS_RANGE = (1.5, 3.0)
MIN_COUNTEREXAMPLE_SECONDS = 5.0


@dataclass(frozen=True)
class StateInterval:
    start: float
    stop: float
    live: bool
    target: float
    counterexample: str = ""


class CollectivePace:
    """One story's background speed profile and the per-player loop offsets."""

    def __init__(self, rng: np.random.Generator, event_list: Sequence[ev.Event],
                 end: float, followers: Sequence[Tuple[str, str]]):
        self.rng = rng
        self.followers = list(followers)
        self.end = float(end)
        self.n_frames = int(np.floor(self.end * FPS + 1e-9)) + 1

        self.live_target = float(rng.uniform(*LIVE_MEDIAN_RANGE))
        self.dead_target = float(rng.uniform(*DEAD_MEDIAN_RANGE))
        self.dead_transition = float(rng.uniform(*TRANSITION_RANGE))
        self.live_transition = float(rng.uniform(*TRANSITION_RANGE))

        base = self._state_intervals(event_list, self.end)
        self.intervals = self._with_counterexamples(base)
        self.speed = self._speed_profile()
        self._offsets: Dict[Tuple[str, str], Tuple[np.ndarray, np.ndarray]] = {}
        for key in self.followers:
            radius = float(rng.uniform(*LOOP_RADIUS_RANGE))
            phase = float(rng.uniform(0.0, 2.0 * np.pi))
            direction = 1.0 if rng.random() < 0.5 else -1.0
            # angle[0] = phase, and angle[i+1] - angle[i] = speed[i] / radius / FPS.
            steps = direction * self.speed / radius / FPS
            angles = phase + np.concatenate(([0.0], np.cumsum(steps[:-1])))
            self._offsets[key] = (
                radius * (np.cos(angles) - np.cos(phase)),
                radius * (np.sin(angles) - np.sin(phase)),
            )

    # -- public render API ---------------------------------------------------------------------

    def offset(self, key: Tuple[str, str], t: float) -> Tuple[float, float]:
        """Loop displacement at time ``t``; zero at t=0 and continuous in between."""
        if not self._offsets:
            return (0.0, 0.0)
        x, y = self._offsets[key]
        if self.n_frames == 1:
            return (0.0, 0.0)
        frame = min(max(t * FPS, 0.0), self.n_frames - 1.0)
        return (float(np.interp(frame, np.arange(self.n_frames), x)),
                float(np.interp(frame, np.arange(self.n_frames), y)))

    def audit(self) -> dict:
        """Test-facing summary; never written to algorithm-visible files."""
        return {
            "live_target": round(self.live_target, 4),
            "dead_target": round(self.dead_target, 4),
            "dead_transition": round(self.dead_transition, 4),
            "live_transition": round(self.live_transition, 4),
            "dead_fast": any(iv.counterexample == "dead_fast" for iv in self.intervals),
            "live_slow": any(iv.counterexample == "live_slow" for iv in self.intervals),
            "intervals": [
                {"start": round(iv.start, 4), "stop": round(iv.stop, 4),
                 "live": iv.live, "target": round(iv.target, 4),
                 "counterexample": iv.counterexample}
                for iv in self.intervals
            ],
            "loop_radius_range": list(LOOP_RADIUS_RANGE),
            "n_background": len(self.followers),
        }

    # -- internals -----------------------------------------------------------------------------

    @staticmethod
    def _state_intervals(event_list: Sequence[ev.Event], end: float) -> List[StateInterval]:
        """Play/dead intervals in continuous time, from the script events alone."""
        ordered = sorted(event_list, key=lambda e: e.t)
        intervals: List[StateInterval] = []
        start = 0.0
        live = False
        for event in ordered:
            if event.kind not in (ev.BALL_OUT, ev.STOPPAGE, ev.LEGAL_RESTART):
                continue
            if event.t <= start + 1e-9:
                # Apply boundary events without creating zero-length intervals.
                if event.kind in (ev.BALL_OUT, ev.STOPPAGE):
                    live = False
                else:
                    live = True
                continue
            intervals.append(StateInterval(start, event.t, live, 0.0))
            start = event.t
            if event.kind in (ev.BALL_OUT, ev.STOPPAGE):
                live = False
            else:
                live = True
        if not intervals:
            intervals.append(StateInterval(0.0, end, False, 0.0))
        elif start < end - 1e-9:
            intervals.append(StateInterval(start, end, live, 0.0))
        return intervals

    def _with_counterexamples(self, base: List[StateInterval]) -> List[StateInterval]:
        """Assign baseline targets, then optionally override one dead/live interval."""
        intervals = [
            StateInterval(iv.start, iv.stop, iv.live,
                           self.live_target if iv.live else self.dead_target)
            for iv in base
        ]
        dead = [i for i, iv in enumerate(intervals)
                if not iv.live and iv.start > 1e-9
                and iv.stop - iv.start >= MIN_COUNTEREXAMPLE_SECONDS]
        if dead and self.rng.random() < DEAD_FAST_PROBABILITY:
            index = int(self.rng.integers(0, len(dead)))
            iv = intervals[dead[index]]
            intervals[dead[index]] = StateInterval(
                iv.start, iv.stop, iv.live,
                float(self.rng.uniform(*DEAD_FAST_RANGE)), "dead_fast")

        live = [i for i, iv in enumerate(intervals)
                if iv.live and iv.stop - iv.start >= MIN_COUNTEREXAMPLE_SECONDS]
        if live and self.rng.random() < LIVE_SLOW_PROBABILITY:
            index = int(self.rng.integers(0, len(live)))
            iv = intervals[live[index]]
            intervals[live[index]] = StateInterval(
                iv.start, iv.stop, iv.live,
                float(self.rng.uniform(*LIVE_SLOW_RANGE)), "live_slow")
        return intervals

    def _target_at(self, t: float) -> float:
        starts = np.asarray([iv.start for iv in self.intervals])
        index = int(np.searchsorted(starts, t, side="right") - 1)
        index = min(max(index, 0), len(self.intervals) - 1)
        interval = self.intervals[index]
        if index == 0:
            return interval.target
        previous = self.intervals[index - 1].target
        ramp = self.dead_transition if not interval.live else self.live_transition
        if ramp <= 1e-9:
            return interval.target
        u = (t - interval.start) / ramp
        if u >= 1.0:
            return interval.target
        u = max(0.0, u)
        smooth = u * u * (3.0 - 2.0 * u)
        return previous + (interval.target - previous) * smooth

    def _speed_profile(self) -> np.ndarray:
        if self.n_frames == 1:
            return np.asarray([self._target_at(0.0)])
        times = np.arange(self.n_frames, dtype=float) / FPS
        return np.asarray([self._target_at(float(t)) for t in times])
