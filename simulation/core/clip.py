"""ClipBuilder: the toolkit a scenario script uses to stage one clip.

A scenario is written as a story from the point of view of the team that starts it:

    "atk"  the team that has the ball at the start and attacks towards +x
    "dfn"  the opponent

The builder keeps a script clock `b.now`. Calls like hold(), dribble() and kick_to() move the
ball and advance the clock; run_to() and event() only schedule things. When the story is done,
finish() renders it into frames. generate.py runs the same script twice with the same seed,
once with atk = H and once with atk = A; for the second, finish() rotates the pitch 180 degrees.

What the builder records, and who may later read it:

    positions of players and ball     -> observation layer -> algorithm
    events (control_start, ...)        -> truth labels and the play_live signal
    contacts (every kick / header)     -> self-checks only
    core window, expected sequence     -> self-checks and scoring only
"""

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from simulation.core import events as ev
from simulation.core.constants import (AWAY, BALL_ID, BALL_RADIUS, FPS, HOME, PITCH_LENGTH,
                                       PITCH_WIDTH)
from simulation.core.motion import BallFlight, BallWithPlayer, GroundRoll, PlayerTrack

# Starting positions in the attacker frame (atk attacks +x, so its goal is at x = 0).
# A 4-4-2 against a 4-4-2, roughly a settled phase of play around midfield.
# "Left" and "right" are from each team's own point of view.
FORMATION = {
    "atk": {
        "gk": (6, 34), "lb": (30, 58), "lcb": (24, 42), "rcb": (24, 26), "rb": (30, 10),
        "lm": (50, 58), "lcm": (44, 40), "rcm": (44, 28), "rm": (50, 10),
        "ls": (64, 40), "rs": (64, 28),
    },
    "dfn": {
        "gk": (99, 34), "lb": (78, 10), "lcb": (82, 26), "rcb": (82, 42), "rb": (78, 58),
        "lm": (66, 12), "lcm": (68, 28), "rcm": (68, 40), "rm": (66, 56),
        "ls": (54, 28), "rs": (54, 40),
    },
}
ROLES = list(FORMATION["atk"])          # fixed order -> stable object ids p01..p22

# Movement comfort limits used to pick a run duration when the script does not give one.
RUN_AVERAGE_SPEED = 5.0                 # m/s
RUN_PEAK_ACCELERATION = 8.0             # m/s^2

# Default ball offsets from the player who has it.
BALL_AT_FEET = 0.4                      # metres in front of the player, standing or holding
BALL_DRIBBLE_LEAD = 0.6                 # metres in front of the player while dribbling
MAX_GRAB_DISTANCE = 1.0                 # a player can only start holding a ball this close


@dataclass
class Clip:
    """One rendered clip, already in H/A terms and in the final pitch orientation."""
    initiating_team: str                        # "H" or "A": who plays "atk" in the story
    n_frames: int
    events: List[ev.Event]                      # team is "H" / "A"
    contact_times: List[float]
    core_window: Tuple[int, int]                # [start, stop) frames of the tested event
    expected_sequence: List[str]                # e.g. ["D", "H", "A"]
    frames: pd.DataFrame                        # clean positions: frame, object, team, x, y, z
    truth: List[str]                            # per frame H / A / D
    play_live: List[int]                        # per frame 0 / 1
    restart_team: List[str]                     # per frame "H" / "A" on a restart frame, else ""
    ball_at: Callable[[float], Tuple[float, float, float]]
    players_at: Callable[[float], List[Tuple[str, str, float, float]]]   # (object, team, x, y)


class ClipBuilder:
    """Stage one story. See the module docstring for the vocabulary."""

    def __init__(self, rng: np.random.Generator, initiating_team: str):
        if initiating_team not in (HOME, AWAY):
            raise ValueError("initiating_team must be 'H' or 'A'")
        self.rng = rng
        self.initiating_team = initiating_team
        self.now = 0.0
        self._players: Dict[Tuple[str, str], PlayerTrack] = {}
        self._ball_segments: list = []
        self._events: List[ev.Event] = []
        self._contacts: List[float] = []
        self._core = [None, None]
        self._expected: Optional[List[str]] = None
        for team in ("atk", "dfn"):
            for role in ROLES:
                self._players[(team, role)] = PlayerTrack(
                    team=team, role=role, start=FORMATION[team][role],
                    sway_amplitude=tuple(rng.uniform(0.1, 0.3, size=2)),
                    sway_period=tuple(rng.uniform(4.0, 8.0, size=2)),
                    sway_phase=tuple(rng.uniform(0, 2 * math.pi, size=2)))

    # -- looking things up ---------------------------------------------------------------------

    def player(self, team: str, role: str) -> PlayerTrack:
        return self._players[(team, role)]

    def all_players(self) -> List[PlayerTrack]:
        return list(self._players.values())

    def ball_position(self, t: float):
        segment = self._segment_at(t)
        return segment.position(t)

    def distance_to_ball(self, player: PlayerTrack, t: float) -> float:
        """Horizontal distance from a player to the ball, in metres."""
        bx, by, _ = self.ball_position(t)
        px, py = player.position(t)
        return math.hypot(bx - px, by - py)

    # -- staging the ball ----------------------------------------------------------------------

    def place_ball(self, player: PlayerTrack, height: float = BALL_RADIUS,
                   in_front: float = BALL_AT_FEET):
        """Put the ball with a player at t = 0 (before anything else happens)."""
        offset = self._forward(player.team, in_front) + (height,)
        self._ball_segments = [BallWithPlayer(0.0, 0.0, player, offset, offset, settle=0.0)]

    def hold(self, player: PlayerTrack, seconds: float, height: float = BALL_RADIUS,
             in_front: float = BALL_AT_FEET, still: bool = False):
        """The player keeps the ball close: at the feet, or in the hands (height ~1-2 m,
        in_front=0). A change of height or offset is spread over the whole hold.

        still=True freezes both at their current pose for this interval only. The ball
        must already match height/in_front; conflicting runs or offset changes raise.
        """
        if still:
            # A still hold preserves the current pose; moving the ball to a different
            # requested offset would contradict "still". Settle it before this call.
            bx, by, bz = self.ball_position(self.now)
            px, py = player.position(self.now)
            target = self._forward(player.team, in_front) + (height,)
            offset = (bx - px, by - py, bz)
            if any(abs(a - b) > 1e-9 for a, b in zip(offset, target)):
                raise ValueError("still hold requires the ball at the requested offset already")
            if math.hypot(bx - px, by - py) > MAX_GRAB_DISTANCE:
                raise ValueError("still holder is too far from the ball")
            player.add_still(self.now, self.now + seconds)
            self._with_player(player, seconds, offset, settle=0.0)
            return
        target = self._forward(player.team, in_front) + (height,)
        self._with_player(player, seconds, target, settle=seconds)

    def dribble(self, player: PlayerTrack, to, seconds: float, settle: float = 0.4):
        """The player runs to `to` with the ball just in front."""
        start = player.anchor(self.now)
        dx, dy = to[0] - start[0], to[1] - start[1]
        length = math.hypot(dx, dy) or 1.0
        lead = (BALL_DRIBBLE_LEAD * dx / length, BALL_DRIBBLE_LEAD * dy / length, BALL_RADIUS)
        player.add_move(self.now, self.now + seconds, to)
        self._with_player(player, seconds, lead, settle=settle)

    def kick_to(self, seconds: float, player: Optional[PlayerTrack] = None, point=None,
                height: float = BALL_RADIUS, arrival_contact: bool = True) -> float:
        """Send the ball through the air to a player (or a point), arriving after `seconds`.

        Aimed at a player, the ball arrives exactly where that player will be at that moment,
        so schedule the player's run (run_to) before the kick. Returns the arrival time.
        Kicks, headers and throws all use this; the script says which by the events it adds.
        Set arrival_contact=False for an unreceived flight, such as a pass out of play.
        """
        if (player is None) == (point is None):
            raise ValueError("kick_to needs exactly one of player= or point=")
        arrival = self.now + seconds
        if player is not None:
            point = player.position(arrival)
        start = self.ball_position(self.now)
        self._contacts.append(self.now)
        self._end_current_segment()
        self._ball_segments.append(BallFlight(self.now, arrival, start,
                                              (point[0], point[1], height)))
        if arrival_contact:
            self._contacts.append(arrival)
        self.now = arrival
        return arrival

    def roll_to(self, seconds: float, player: Optional[PlayerTrack] = None, point=None,
                arrival_contact: bool = True) -> float:
        """Roll to a player or point, decelerating uniformly to rest after seconds.

        The ball must already be on the ground. No truth event is inferred. For an
        unreceived pass out, use point= and arrival_contact=False, then wait().
        """
        if (player is None) == (point is None):
            raise ValueError("roll_to needs exactly one of player= or point=")
        arrival = self.now + seconds
        start = self.ball_position(self.now)
        if abs(start[2] - BALL_RADIUS) > 1e-9:
            raise ValueError("roll_to requires a ball on the ground")
        if player is not None:
            point = player.position(arrival)
        roll = GroundRoll(self.now, arrival, start[:2], tuple(point[:2]))
        self._end_current_segment()
        self._contacts.append(self.now)
        if arrival_contact:
            self._contacts.append(arrival)
        self._ball_segments.append(roll)
        self.now = arrival
        return arrival

    # -- staging players -----------------------------------------------------------------------

    def start_at(self, player: PlayerTrack, point):
        """Move a player's starting position away from the default formation spot."""
        if player.moves:
            raise ValueError("start_at() must come before any run of {} {}".format(
                player.team, player.role))
        player.start = tuple(point)

    def run_to(self, player: PlayerTrack, point, arrive_at: float,
               seconds: Optional[float] = None):
        """Schedule a run (without the ball) so the player reaches `point` at `arrive_at`."""
        if seconds is None:
            seconds = comfortable_run_time(_distance(player.anchor(arrive_at), point))
        start = arrive_at - seconds
        if start < 0:
            raise ValueError("{} {} would have to start running before the clip starts".format(
                player.team, player.role))
        player.add_move(start, arrive_at, point)

    # -- story bookkeeping ---------------------------------------------------------------------

    def event(self, kind: str, team: Optional[str] = None, at: Optional[float] = None):
        """Record a script event (see events.py). `at` defaults to the script clock."""
        if kind not in ev.EVENT_KINDS:
            raise ValueError("unknown event kind {!r}".format(kind))
        if (kind in ev.EVENTS_WITH_TEAM) != (team is not None):
            raise ValueError("{} {} a team".format(
                kind, "needs" if kind in ev.EVENTS_WITH_TEAM else "takes no"))
        self._events.append(ev.Event(kind, self.now if at is None else at, team))

    def wait(self, seconds: float):
        """Continue a held ball, or wait after an unreceived ground roll has stopped."""
        self._end_current_segment()
        last = self._ball_segments[-1]
        if isinstance(last, GroundRoll):
            if seconds < 0:
                raise ValueError("wait duration cannot be negative")
            self.now += seconds
            self._end_current_segment()
            return
        if not isinstance(last, BallWithPlayer):
            raise ValueError("wait() needs the ball to be with a player")
        self._with_player(last.player, seconds, last.target_offset)

    def begin_core(self):
        """Mark the start of the event the scenario is really testing."""
        self._core[0] = self.now

    def end_core(self, at: Optional[float] = None):
        """End the core window now, or at an exact event time within a staged flight."""
        self._core[1] = self.now if at is None else at

    def expect(self, *labels):
        """Declare the label sequence the story must produce, e.g. expect("D", "atk", "dfn")."""
        self._expected = list(labels)

    def time_ball_enters_pitch(self, after: float, before: float) -> float:
        """Exact moment (continuous time) the ball stops being wholly outside the pitch."""
        return self._first_time(lambda t: not ball_fully_out(self.ball_position(t)),
                                after, before)

    def time_ball_leaves_pitch(self, after: float, before: float) -> float:
        """Exact moment the ball is first wholly outside the pitch (spec 2.4)."""
        return self._first_time(lambda t: ball_fully_out(self.ball_position(t)), after, before)

    # -- rendering -----------------------------------------------------------------------------

    def finish(self) -> Clip:
        """Render the story into frames, truth and referee signal, in H/A terms."""
        if self._expected is None or None in self._core:
            raise ValueError("scenario must call expect(), begin_core() and end_core()")
        self._end_current_segment()
        end = self.now
        n_frames = int(math.floor(end * FPS + 1e-9)) + 1

        team_of = {"atk": self.initiating_team,
                   "dfn": AWAY if self.initiating_team == HOME else HOME}
        events = [ev.Event(e.kind, e.t, team_of.get(e.team)) for e in self._events]
        expected = [team_of.get(label, label) for label in self._expected]
        object_id = self._object_ids(team_of)
        swap = self.initiating_team == AWAY

        def place(x, y):
            """Attacker frame -> final frame (rotate the pitch for the swapped version)."""
            return (PITCH_LENGTH - x, PITCH_WIDTH - y) if swap else (x, y)

        def ball_at(t):
            x, y, z = self.ball_position(t)
            return place(x, y) + (z,)

        def players_at(t):
            out = []
            for key, track in self._players.items():
                x, y = place(*track.position(t))
                out.append((object_id[key], team_of[track.team], x, y))
            return out

        rows = []
        for frame in range(n_frames):
            t = frame / FPS
            bx, by, bz = ball_at(t)
            rows.append((frame, BALL_ID, "", bx, by, bz))
            for obj, team, x, y in players_at(t):
                rows.append((frame, obj, team, x, y, np.nan))
        frames = pd.DataFrame(rows, columns=["frame", "object", "team", "x", "y", "z"])

        restart_team = [""] * n_frames
        for e in events:
            if e.kind == ev.LEGAL_RESTART and e.frame < n_frames:
                restart_team[e.frame] = e.team

        return Clip(
            initiating_team=self.initiating_team,
            n_frames=n_frames,
            events=events,
            contact_times=list(self._contacts),
            core_window=(ev.boundary_frame(self._core[0]),
                         min(ev.boundary_frame(self._core[1]), n_frames)),
            expected_sequence=expected,
            frames=frames,
            truth=ev.truth_from_events(events, n_frames),
            play_live=ev.play_live_from_events(events, n_frames),
            restart_team=restart_team,
            ball_at=ball_at,
            players_at=players_at,
        )

    # -- internals -----------------------------------------------------------------------------

    def _segment_at(self, t):
        for segment in reversed(self._ball_segments):
            if segment.t0 <= t + 1e-12:
                return segment
        return self._ball_segments[0]

    def _end_current_segment(self):
        """Cut the last ball segment at the script clock, so the next one starts there."""
        last = self._ball_segments[-1]
        if last.t1 < self.now:
            last.t1 = self.now
        elif last.t1 > self.now + 1e-9:
            raise ValueError("ball segment runs past the script clock")

    def _with_player(self, player, seconds, target_offset, settle=0.4):
        self._end_current_segment()
        bx, by, bz = self.ball_position(self.now)
        px, py = player.position(self.now)
        if math.hypot(bx - px, by - py) > MAX_GRAB_DISTANCE:
            raise ValueError("{} {} is {:.1f} m from the ball at {:.2f}s and cannot have it".format(
                player.team, player.role, math.hypot(bx - px, by - py), self.now))
        start_offset = (bx - px, by - py, bz)
        self._ball_segments.append(BallWithPlayer(self.now, self.now + seconds, player,
                                                  start_offset, target_offset, settle))
        self.now += seconds

    def _first_time(self, condition, after, before, step=0.001):
        """First t in [after, before] where condition(t) holds, to about a microsecond."""
        t = after
        while t <= before:
            if condition(t):
                low, high = max(after, t - step), t
                if condition(low):
                    return low
                for _ in range(40):                 # bisection between low (false) and high (true)
                    middle = 0.5 * (low + high)
                    if condition(middle):
                        high = middle
                    else:
                        low = middle
                return high
            t += step
        raise ValueError("condition never became true between {:.2f}s and {:.2f}s".format(
            after, before))

    def _object_ids(self, team_of):
        """p01..p11 for the home team, p12..p22 for the away team, in FORMATION role order."""
        ids = {}
        for team in ("atk", "dfn"):
            base = 0 if team_of[team] == HOME else len(ROLES)
            for index, role in enumerate(ROLES):
                ids[(team, role)] = "p{:02d}".format(base + index + 1)
        return ids

    @staticmethod
    def _forward(team, distance):
        """A horizontal offset of `distance` metres in the direction `team` attacks."""
        return (distance, 0.0) if team == "atk" else (-distance, 0.0)


def ball_fully_out(position) -> bool:
    """True when the ball's footprint is entirely beyond a pitch boundary line (spec 2.4).

    Touching or sitting on the line is still in. Works in either pitch orientation because the
    pitch is symmetric under the 180-degree rotation used for the swapped version.
    """
    x, y = position[0], position[1]
    return (x < -BALL_RADIUS or x > PITCH_LENGTH + BALL_RADIUS
            or y < -BALL_RADIUS or y > PITCH_WIDTH + BALL_RADIUS)


def comfortable_run_time(distance: float) -> float:
    """A run duration that keeps average speed and peak acceleration within normal limits."""
    by_speed = distance / RUN_AVERAGE_SPEED
    by_acceleration = math.sqrt(math.pi ** 2 / 2 * distance / RUN_PEAK_ACCELERATION)
    return max(1.0, by_speed, by_acceleration)


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])
