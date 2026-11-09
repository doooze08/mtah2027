"""LC01-LC05: arrival, proximity and bouncing are distinct from controlled possession."""

import math

from simulation.scenarios._motion import StoryMotion, arrive, carry_tail, open_play

FAMILY = "long_ball_landing_contest"


def _landing(b, rng, motion, subtype):
    """Jointly choose flight and roll durations, keeping reception at 3-10 m/s."""
    launch = b.now
    bx, by, _ = b.ball_position(launch)
    flight = rng.uniform(2.4 if subtype == "LC02" else 1.8, 2.5)
    retention = motion.first_retention * motion.later_retention
    distance = rng.uniform(max(25, 6 * flight / retention),
                           min(40, 10 * flight / retention))
    speed = distance / flight * retention
    # LC04's 0.5-2 s chase includes the entire first rebound, not just the roll.
    low, high = 0.1, 0.5
    if subtype == "LC04":
        high = min(0.8, 2.0 - motion.restitution * flight)
    roll_seconds = rng.uniform(low, min(high, (speed - 3) / motion.deceleration))
    b.bounce_to(flight, point=(bx + distance, by), bounces=1,
                restitution=motion.restitution, deceleration=motion.deceleration,
                first_horizontal_retention=motion.first_retention,
                horizontal_retention=motion.later_retention, roll_seconds=roll_seconds)
    return launch, flight, speed - motion.deceleration * roll_seconds


def _receive(b, rng, motion, receiver, speed):
    point = b.ball_position(b.now)[:2]
    arrive(b, receiver, point, b.now)
    b.event("control_start", team=receiver.team)
    b.trap(receiver, motion.trap_seconds(speed))
    carry_tail(b, rng, receiver)


def build_lc01(b, rng):
    """An aerial pass crosses directly above an opponent, then reaches an atk teammate."""
    motion = StoryMotion.sample(rng)
    open_play(b, rng, motion)
    launch, flight, speed = _landing(b, rng, motion, "LC01")
    overhead = launch + flight / 2
    point = b.ball_position(overhead)
    opponent = b.player("dfn", "ls")
    arrive(b, opponent, point[:2], overhead, offset=(0, 3))
    _receive(b, rng, motion, b.player("atk", "ls"), speed)
    b.expect("D", "atk")


def build_lc02(b, rng):
    """The defender reaches the landing area first but the rebound passes overhead."""
    motion = StoryMotion.sample(rng)
    open_play(b, rng, motion)
    launch, flight, speed = _landing(b, rng, motion, "LC02")
    # Reach the rebound's path before the attacker; no header or foot contact occurs.
    overhead = launch + flight + motion.restitution * flight / 2
    point = b.ball_position(overhead)
    opponent = b.player("dfn", "ls")
    arrive(b, opponent, point[:2], launch + flight - rng.uniform(0.1, 0.4), offset=(0, 3))
    _receive(b, rng, motion, b.player("atk", "ls"), speed)
    b.expect("D", "atk")


def build_lc03(b, rng):
    """A defender cushions the landed ball, changes direction and carries it away."""
    motion = StoryMotion.sample(rng)
    open_play(b, rng, motion)
    _, _, speed = _landing(b, rng, motion, "LC03")
    _receive(b, rng, motion, b.player("dfn", "ls"), speed)
    b.expect("D", "atk", "dfn")


def build_lc04(b, rng):
    """Neither chaser controls the rolling loose ball until the defender collects it."""
    motion = StoryMotion.sample(rng)
    open_play(b, rng, motion)
    _, _, speed = _landing(b, rng, motion, "LC04")
    point = b.ball_position(b.now)
    chaser = b.player("atk", "ls")
    arrive(b, chaser, (point[0] - 1.5, point[1] + 1.5),
           b.now - rng.uniform(0, 0.6), seconds=2.0, offset=(-5, 2))
    _receive(b, rng, motion, b.player("dfn", "ls"), speed)
    b.expect("D", "atk", "dfn")


def build_lc05(b, rng):
    """An untouched overhit long pass crosses the touchline before anyone controls it."""
    motion = StoryMotion.sample(rng)
    open_play(b, rng, motion)
    launch = b.now
    bx, by, _ = b.ball_position(launch)
    point = (bx + rng.uniform(4, 8), 69.0)
    distance = math.hypot(point[0] - bx, point[1] - by)
    flight = distance / rng.uniform(20, 23)
    b.bounce_to(flight, point=point, bounces=1, restitution=motion.restitution,
                deceleration=motion.deceleration,
                first_horizontal_retention=motion.first_retention,
                horizontal_retention=motion.later_retention, roll_seconds=0)
    out = b.time_ball_leaves_pitch(launch, launch + flight)
    b.event("ball_out", at=out)
    b.end_core(at=out)
    b.wait(max(0, rng.uniform(2, 3) - (b.now - out)))
    b.expect("D", "atk", "D")


SUBTYPES = {"LC01": build_lc01, "LC02": build_lc02, "LC03": build_lc03,
            "LC04": build_lc04, "LC05": build_lc05}
