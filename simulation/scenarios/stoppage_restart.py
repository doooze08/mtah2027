"""Long stoppages with physical retrieval and event-defined restarts."""

import math

from simulation.core.clip import comfortable_run_time
from simulation.core.constants import BALL_RADIUS, PITCH_LENGTH, PITCH_WIDTH
from simulation.scenarios._motion import StoryMotion

FAMILY = "stoppage_restart"


def _start(b, rng, point, motion):
    b.follow_ball = True
    holder = b.player("atk", "rs")
    passer = b.player("atk", "rcb")
    b.start_at(holder, point)
    b.start_at(passer, (point[0] - 14, point[1]))
    b.place_ball(passer, in_front=0)
    b.begin_core()
    b.hold(passer, rng.uniform(0.8, 1.5), still=True)
    b.event("legal_restart", team="atk")
    arrival_speed = rng.uniform(9, 10)
    b.roll_to(player=holder, arrival_speed=arrival_speed, deceleration=motion.deceleration)
    b.event("control_start", team="atk")
    b.trap(holder, motion.trap_seconds(arrival_speed))
    b.hold(holder, 1.0, still=True)
    # Let the local still-to-sway blend finish before any scripted run.
    b.wait(0.6)
    return holder


def _collect(b, player):
    """Retrieve a ball already rolling to rest, without a teleport or a dead-ball control event."""
    point = b.ball_position(b.now)[:2]
    distance = math.dist(player.anchor(b.now), point)
    seconds = max(1.5, comfortable_run_time(distance) + 0.8)
    at = b.now + seconds
    sway = tuple(p - a for p, a in zip(player.position(at), player.anchor(at)))
    b.run_to(player, tuple(p - s for p, s in zip(point, sway)), at, seconds=seconds)
    b.wait(seconds)
    b.hold(player, 0.8, in_front=0)


def _carry(b, player, point):
    distance = math.dist(player.anchor(b.now), point)
    b.dribble(player, point, max(2.0, distance / 1.8,
                                 comfortable_run_time(distance) + 0.8), settle=1.0)
    b.hold(player, 0.8, in_front=0)


def _wait_for_restart(b, rng, taker, dead_at, long=False, entry_seconds=0.0):
    low = max(30.0 if long else 5.24, b.now - dead_at + entry_seconds + 1.0)
    duration = rng.uniform(low, 90.0 if long else 30.0)
    b.hold(taker, dead_at + duration - b.now - entry_seconds, still=True)


def _ground_restart(b, rng, taker, receiver, motion):
    """Release at 10-25 m/s, with a 6-9 m/s reception and at most 35 m of travel."""
    direction = 1 if taker.team == "atk" else -1
    arrival_speed = rng.uniform(6.0, 9.0)
    launch_limit = min(25.0, math.sqrt(arrival_speed ** 2 + 2 * motion.deceleration * 35))
    launch_speed = rng.uniform(10.0, launch_limit)
    duration = (launch_speed - arrival_speed) / motion.deceleration
    distance = (launch_speed ** 2 - arrival_speed ** 2) / (2 * motion.deceleration)
    x, y, _ = b.ball_position(b.now)
    point = (x + direction * distance, y)
    at = b.now + duration
    sway = tuple(p - a for p, a in zip(receiver.position(at), receiver.anchor(at)))
    b.start_at(receiver, tuple(p - s for p, s in zip(point, sway)))
    b.event("legal_restart", team=taker.team)
    b.roll_to(duration, player=receiver, deceleration=motion.deceleration)
    b.event("control_start", team=taker.team)
    b.trap(receiver, motion.trap_seconds(arrival_speed))
    b.hold(receiver, 2.0, still=True)
    b.end_core()


def build_st01(b, rng):
    """Foul: the whistle can interrupt a fast in-field pass; atk retrieves and restarts."""
    motion = StoryMotion.sample(rng)
    holder = _start(b, rng, (43, rng.uniform(28, 40)), motion)
    marker = b.player("dfn", "lcm")
    b.start_at(marker, (44, holder.start[1] + 0.7))
    if rng.random() < 0.5:
        # The foul stops play, not the ball. A released pass keeps rolling for seconds.
        release = b.now
        x, y, _ = b.ball_position(release)
        b.roll_to(point=(x + rng.uniform(18, 24), y), arrival_speed=0,
                  deceleration=motion.deceleration, arrival_contact=False)
        dead_at = release + rng.uniform(0.1, 0.2)
        b.event("stoppage", at=dead_at)
    else:
        x, y = holder.anchor(b.now)
        b.dribble(holder, (x + 3, y), 3.0, settle=1.0)
        b.run_to(marker, (x + 3.3, y + 0.5), arrive_at=b.now, seconds=2.5)
        b.event("stoppage")
        dead_at = b.now
        b.hold(holder, 1.0, in_front=0)
    _collect(b, holder)
    _carry(b, holder, (43, holder.start[1]))
    _wait_for_restart(b, rng, holder, dead_at)
    _ground_restart(b, rng, holder, b.player("atk", "ls"), motion)
    b.expect("D", "atk", "D", "atk")


def build_st02(b, rng):
    """A slow touchline exit, retrieval, and a long wait for the opponent's throw-in."""
    motion = StoryMotion.sample(rng)
    x = rng.uniform(40, 60)
    holder = _start(b, rng, (x, PITCH_WIDTH - 4), motion)
    release = b.now
    b.dribble(holder, (x, PITCH_WIDTH + 0.3), 3.5, settle=1.0)
    dead_at = b.time_ball_leaves_pitch(release, b.now)
    b.event("ball_out", at=dead_at)
    taker = b.player("dfn", "rm")
    b.start_at(taker, (x + 2, PITCH_WIDTH - 1))
    _collect(b, taker)
    _carry(b, taker, (x, PITCH_WIDTH + 0.4))
    b.hold(taker, 0.8, height=2.0, in_front=0)
    receiver = b.player("dfn", "rcm")
    point = (x - 3, PITCH_WIDTH - 12)
    start = b.ball_position(b.now)
    flight = math.dist(start[:2], point) / rng.uniform(10, 25)
    # Count the throw's transit to the line inside the 30 s dead-ball limit.
    entry_seconds = (start[1] - PITCH_WIDTH - BALL_RADIUS) / (start[1] - point[1]) * flight
    _wait_for_restart(b, rng, taker, dead_at, entry_seconds=entry_seconds)
    at = b.now + flight
    sway = tuple(p - a for p, a in zip(receiver.position(at), receiver.anchor(at)))
    b.start_at(receiver, tuple(p - s for p, s in zip(point, sway)))
    release = b.now
    arrival = b.kick_to(flight, player=receiver, height=BALL_RADIUS)
    b.event("legal_restart", team="dfn", at=b.time_ball_enters_pitch(release, arrival))
    b.event("control_start", team="dfn")
    b.hold(receiver, 2.0)
    b.end_core()
    b.expect("D", "atk", "D", "dfn")


def _shot_out(b, rng, goal):
    motion = StoryMotion.sample(rng)
    y = PITCH_WIDTH / 2 if goal else rng.uniform(45, 49)
    holder = _start(b, rng, (rng.uniform(93, 97), y), motion)
    taker = b.player("dfn", "gk" if not goal else "rs")
    release = b.now
    catch_point = (PITCH_LENGTH + 0.4, y)
    catch_speed = rng.uniform(12.0, 18.0)
    b.roll_to(point=catch_point, arrival_speed=catch_speed, deceleration=motion.deceleration)
    # Receive only after the whole ball is out; collecting a dead ball is not control_start.
    sway = tuple(p - a for p, a in zip(taker.position(b.now), taker.anchor(b.now)))
    b.start_at(taker, tuple(p - s for p, s in zip(catch_point, sway)))
    dead_at = b.time_ball_leaves_pitch(release, b.now)
    b.event("ball_out", at=dead_at)
    b.trap(taker, motion.trap_seconds(catch_speed))
    b.hold(taker, 0.8, in_front=0)
    _carry(b, taker, (PITCH_LENGTH / 2, PITCH_WIDTH / 2) if goal else (100, 40))
    _wait_for_restart(b, rng, taker, dead_at, long=goal)
    _ground_restart(b, rng, taker, b.player("dfn", "lcb"), motion)
    b.expect("D", "atk", "D", "dfn")


def build_st03(b, rng):
    """A shot wide, followed by a 5-30 s stoppage and the opponent's goal kick."""
    _shot_out(b, rng, goal=False)


def build_st04(b, rng):
    """A goal, retrieval to the centre spot, and the opponent's kick-off after 30-90 s."""
    _shot_out(b, rng, goal=True)


SUBTYPES = {"ST01": build_st01, "ST02": build_st02, "ST03": build_st03, "ST04": build_st04}
