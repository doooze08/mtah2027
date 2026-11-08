"""Continuous-time motion pieces: how a player or the ball moves between script moments.

Nothing here is a physics engine. The script decides who is where and when; these pieces only
draw a believable path between those moments, so that the result has no teleports and no
impossible speeds. Every position is a function of continuous time t (seconds), which lets the
builder find exact event times (for example, the instant a thrown ball enters the pitch).

Coordinates inside this module are in the "attacker frame": the team that starts the story
attacks towards +x. The builder rotates the whole clip afterwards for the swapped version.
"""

import math
from dataclasses import dataclass, field
from typing import Callable, List, Tuple

import numpy as np

from simulation.core.constants import BALL_RADIUS, GRAVITY

Point2 = Tuple[float, float]
Point3 = Tuple[float, float, float]


def ease(u):
    """Smooth 0 -> 1 progress with zero speed at both ends (cosine profile)."""
    u = min(max(u, 0.0), 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * u)


def lerp(a, b, u):
    return tuple(ai + (bi - ai) * u for ai, bi in zip(a, b))


# -- players ------------------------------------------------------------------------------------

@dataclass
class Move:
    """A player runs from p0 to p1 between t0 and t1, starting and stopping smoothly."""
    t0: float
    t1: float
    p0: Point2
    p1: Point2


@dataclass
class StillPeriod:
    """A fixed sway offset while the player's scripted anchor is stationary."""
    t0: float
    t1: float
    sway: Point2


@dataclass
class PlayerTrack:
    """Where one player is at any time: scripted moves plus a small idle sway.

    The sway (a few tens of centimetres, periods of several seconds) keeps players from standing
    perfectly still. It is part of the true position, so anything that follows a player (the ball
    at the player's feet, a pass aimed at the player) follows the swaying position too.
    """
    team: str                  # "atk" or "dfn"
    role: str                  # e.g. "lcb"; see clip.FORMATION
    start: Point2
    sway_amplitude: Point2
    sway_period: Point2
    sway_phase: Point2
    moves: List[Move] = field(default_factory=list)
    still_periods: List[StillPeriod] = field(default_factory=list)

    def anchor(self, t):
        """Scripted position, without the sway."""
        position = self.start
        for move in self.moves:
            if t <= move.t0:
                break
            if t < move.t1:
                return lerp(move.p0, move.p1, ease((t - move.t0) / (move.t1 - move.t0)))
            position = move.p1
        return position

    def position(self, t) -> Point2:
        x, y = self.anchor(t)
        x += self.sway_amplitude[0] * math.sin(2 * math.pi * t / self.sway_period[0]
                                               + self.sway_phase[0])
        y += self.sway_amplitude[1] * math.sin(2 * math.pi * t / self.sway_period[1]
                                               + self.sway_phase[1])
        if self.still_periods:
            anchor = self.anchor(t)
            for period in self.still_periods:
                if period.t0 <= t <= period.t1:
                    return (anchor[0] + period.sway[0], anchor[1] + period.sway[1])
            # Blend only outside held intervals. Short gaps split the available blend time
            # evenly, so nearby holds never modify one another's stationary interval.
            for index, period in enumerate(self.still_periods):
                before = 0.6
                if index > 0:
                    before = min(before, (period.t0 - self.still_periods[index - 1].t1) / 2)
                after = 0.6
                if index + 1 < len(self.still_periods):
                    after = min(after, (self.still_periods[index + 1].t0 - period.t1) / 2)
                weight = 0.0
                if before > 0 and period.t0 - before < t < period.t0:
                    weight = ease((t - period.t0 + before) / before)
                elif after > 0 and period.t1 < t < period.t1 + after:
                    weight = 1.0 - ease((t - period.t1) / after)
                if weight:
                    return lerp((x, y), (anchor[0] + period.sway[0],
                                         anchor[1] + period.sway[1]), weight)
        return (x, y)

    def add_still(self, t0, t1):
        """Freeze this player locally; reject contradictory scripted movement."""
        if t1 <= t0:
            raise ValueError("still interval must have positive duration")
        if self.still_periods and t0 < self.still_periods[-1].t1 - 1e-9:
            raise ValueError("still intervals must be ordered and must not overlap")
        if any(max(t0, m.t0) < min(t1, m.t1) for m in self.moves):
            raise ValueError("still interval overlaps a scripted run")
        position, anchor = self.position(t0), self.anchor(t0)
        self.still_periods.append(StillPeriod(t0, t1, (position[0] - anchor[0],
                                                      position[1] - anchor[1])))

    def add_move(self, t0, t1, target):
        if any(max(t0, s.t0) < min(t1, s.t1) for s in self.still_periods):
            raise ValueError("scripted run overlaps a still interval")
        if self.moves and t0 < self.moves[-1].t1 - 1e-9:
            raise ValueError("{} {}: new move at {:.2f}s overlaps the previous one".format(
                self.team, self.role, t0))
        self.moves.append(Move(t0, t1, self.anchor(t0), tuple(target)))


# -- ball -------------------------------------------------------------------------------------

@dataclass
class BallWithPlayer:
    """Ball at a player's feet (or in the player's hands), offset from that position.

    The offset glides from where the ball was at t0 to `target_offset` over `settle` seconds, so
    the ball never jumps when it changes from one segment to the next.
    """
    t0: float
    t1: float
    player: PlayerTrack
    start_offset: Point3
    target_offset: Point3
    settle: float = 0.4

    def position(self, t) -> Point3:
        px, py = self.player.position(t)
        u = ease((t - self.t0) / self.settle) if self.settle > 0 else 1.0
        dx, dy, z = lerp(self.start_offset, self.target_offset, u)
        return (px + dx, py + dy, z)


@dataclass
class BallFlight:
    """Ball in the air (or skimming the ground) from p0 at t0 to p1 at t1.

    Horizontal speed is constant (no air drag) and height follows a parabola under gravity. The
    launch speed is whatever makes the ball arrive at p1 exactly at t1.
    """
    t0: float
    t1: float
    p0: Point3
    p1: Point3

    def position(self, t) -> Point3:
        s = t - self.t0
        duration = self.t1 - self.t0
        u = s / duration
        x = self.p0[0] + (self.p1[0] - self.p0[0]) * u
        y = self.p0[1] + (self.p1[1] - self.p0[1]) * u
        vz0 = (self.p1[2] - self.p0[2] + 0.5 * GRAVITY * duration ** 2) / duration
        z = self.p0[2] + vz0 * s - 0.5 * GRAVITY * s ** 2
        return (x, y, max(z, BALL_RADIUS))

    def horizontal_speed(self):
        dx = self.p1[0] - self.p0[0]
        dy = self.p1[1] - self.p0[1]
        return math.hypot(dx, dy) / (self.t1 - self.t0)

    def velocity(self, t):
        """Unclipped flight velocity, used at the exact ground impact by new motions."""
        duration = self.t1 - self.t0
        vz0 = (self.p1[2] - self.p0[2] + 0.5 * GRAVITY * duration ** 2) / duration
        return ((self.p1[0] - self.p0[0]) / duration,
                (self.p1[1] - self.p0[1]) / duration, vz0 - GRAVITY * (t - self.t0))


@dataclass
class GroundRoll:
    """A straight ground pass with fixed deceleration and nonzero arrival speed.

    t1 is the reception time, not necessarily the stop time. With no receiver,
    continuing the same segment rolls the ball onward until friction stops it.
    """
    t0: float
    t1: float
    p0: Point2
    p1: Point2
    deceleration: float = 2.0
    arrival_time: float = field(init=False)
    initial_speed: float = field(init=False)
    direction: Point2 = field(init=False)

    def __post_init__(self):
        duration = self.t1 - self.t0
        distance = math.hypot(self.p1[0] - self.p0[0], self.p1[1] - self.p0[1])
        if duration <= 0 or distance <= 0 or self.deceleration <= 0:
            raise ValueError("ground roll needs positive duration, distance and deceleration")
        self.initial_speed = distance / duration + 0.5 * self.deceleration * duration
        if self.initial_speed - self.deceleration * duration < -1e-9:
            raise ValueError("arrival time is too late: the ball would stop before the target")
        self.arrival_time = self.t1
        self.direction = ((self.p1[0] - self.p0[0]) / distance,
                          (self.p1[1] - self.p0[1]) / distance)

    def position(self, t) -> Point3:
        elapsed = min(max(t - self.t0, 0.0), self.initial_speed / self.deceleration)
        distance = self.initial_speed * elapsed - 0.5 * self.deceleration * elapsed ** 2
        return (self.p0[0] + self.direction[0] * distance,
                self.p0[1] + self.direction[1] * distance, BALL_RADIUS)

    def speed(self, t):
        return max(0.0, self.initial_speed - self.deceleration * max(t - self.t0, 0.0))

    def velocity(self, t):
        return tuple(component * self.speed(t) for component in self.direction)


@dataclass
class GroundTrap:
    """A foot cushions the incoming ball: continuous cosine speed decay to rest."""
    t0: float
    t1: float
    p0: Point2
    incoming_velocity: Point2
    duration: float = field(init=False)

    def __post_init__(self):
        self.duration = self.t1 - self.t0

    def position(self, t) -> Point3:
        u = min(max((t - self.t0) / self.duration, 0.0), 1.0)
        travel_time = self.duration * (0.5 * u + math.sin(math.pi * u) / (2 * math.pi))
        return (self.p0[0] + self.incoming_velocity[0] * travel_time,
                self.p0[1] + self.incoming_velocity[1] * travel_time, BALL_RADIUS)

    def velocity(self, t):
        u = min(max((t - self.t0) / self.duration, 0.0), 1.0)
        fraction = 0.5 * (1 + math.cos(math.pi * u))
        return tuple(component * fraction for component in self.incoming_velocity)


@dataclass
class BouncingBall:
    """Damped vertical hops after impact, followed by the existing ground-roll model.

    Airborne horizontal velocity is retained. Each vertical rebound is restitution
    times the previous impact speed. Ground collisions are not player contacts.
    """
    t0: float
    p0: Point2
    incoming_velocity: Point3
    restitution: float = 0.55
    bounces: int = 3
    deceleration: float = 2.0
    hops: list = field(init=False, default_factory=list)
    ground_impacts: list = field(init=False, default_factory=list)
    roll: object = field(init=False, default=None)
    roll_start: float = field(init=False)
    stop_time: float = field(init=False)
    t1: float = field(init=False)

    def __post_init__(self):
        if not 0 < self.restitution < 1 or self.bounces < 1:
            raise ValueError("bouncing needs 0 < restitution < 1 and at least one rebound")
        time = self.t0
        vz = abs(self.incoming_velocity[2]) * self.restitution
        self.ground_impacts.append(time)
        for _ in range(self.bounces):
            duration = 2 * vz / GRAVITY
            self.hops.append((time, time + duration, vz))
            time += duration
            self.ground_impacts.append(time)
            vz *= self.restitution
        self.roll_start = time
        vx, vy = self.incoming_velocity[:2]
        x = self.p0[0] + vx * (time - self.t0)
        y = self.p0[1] + vy * (time - self.t0)
        speed = math.hypot(vx, vy)
        self.stop_time = time + speed / self.deceleration
        if speed > 0:
            end = (x + vx * speed / (2 * self.deceleration),
                   y + vy * speed / (2 * self.deceleration))
            self.roll = GroundRoll(time, self.stop_time, (x, y), end, self.deceleration)
        self.t1 = self.stop_time

    def position(self, t):
        if t >= self.roll_start:
            if self.roll is not None:
                return self.roll.position(t)
            return (*self.p0, BALL_RADIUS)
        time = max(t, self.t0)
        vx, vy = self.incoming_velocity[:2]
        for start, stop, vz in self.hops:
            if time < stop:
                elapsed = time - start
                return (self.p0[0] + vx * (time - self.t0),
                        self.p0[1] + vy * (time - self.t0),
                        BALL_RADIUS + vz * elapsed - 0.5 * GRAVITY * elapsed ** 2)

    def velocity(self, t):
        if t >= self.roll_start:
            return (*self.roll.velocity(t), 0.0) if self.roll is not None else (0.0, 0.0, 0.0)
        for start, stop, vz in self.hops:
            if t < stop:
                return (*self.incoming_velocity[:2], vz - GRAVITY * (max(t, start) - start))


class FormationFollow:
    """A common, critically damped translation for non-scripted background players.

    Solve x'' + 2*w*x' + w*w*x = w*w*target exactly per 25-fps target interval,
    then use cubic Hermite interpolation for continuous position and velocity.
    No randomness or tactical decisions, and no feedback into the ball trajectory.
    """
    def __init__(self, ball_at: Callable, end: float, lower, upper, fps: float,
                 gain: float = 0.25, response_seconds: float = 1.5):
        self.dt = 1.0 / fps
        count = int(math.ceil(end * fps)) + 1
        self.positions = np.zeros((count, 2))
        self.velocities = np.zeros((count, 2))
        origin = np.asarray(ball_at(0)[:2])
        omega = 1.0 / response_seconds
        decay = math.exp(-omega * self.dt)
        for index in range(1, count):
            target = np.clip(gain * (np.asarray(ball_at((index - 1) * self.dt)[:2]) - origin),
                             lower, upper)
            previous, velocity = self.positions[index - 1], self.velocities[index - 1]
            error = previous - target
            coefficient = velocity + omega * error
            self.positions[index] = target + (error + coefficient * self.dt) * decay
            self.velocities[index] = (velocity - omega * coefficient * self.dt) * decay

    def position(self, t):
        index = min(max(int(t / self.dt), 0), len(self.positions) - 2)
        u = min(max((t - index * self.dt) / self.dt, 0.0), 1.0)
        p0, p1 = self.positions[index:index + 2]
        v0, v1 = self.velocities[index:index + 2]
        return ((2 * u ** 3 - 3 * u ** 2 + 1) * p0
                + (u ** 3 - 2 * u ** 2 + u) * self.dt * v0
                + (-2 * u ** 3 + 3 * u ** 2) * p1
                + (u ** 3 - u ** 2) * self.dt * v1)


def sample(function, times):
    """Evaluate a position function at many times; returns an array of shape (len(times), k)."""
    return np.array([function(t) for t in times], dtype=float)
