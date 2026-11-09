"""Basic possession with rolling passes, explicit control events and foot cushioning."""

import math

from simulation.scenarios._motion import StoryMotion

FAMILY = "basic_possession"


def _receive(b, rng, receiver, motion):
    """Arrive at 3-10 m/s; control starts at contact, before cushioning ends."""
    speed = motion.arrival_speed
    b.roll_to(player=receiver, arrival_speed=speed, deceleration=motion.deceleration)
    b.event("control_start", team=receiver.team)
    b.trap(receiver, motion.trap_seconds())


def _opening(b, rng, motion, near_touchline=False):
    """One second dead, a legal ground pass, then 2-3 seconds of stable control."""
    kicker = b.player("atk", "rcb")
    receiver = b.player("atk", "lcb")
    y = 56.0 if near_touchline else 22.0
    x = rng.uniform(23.0, 27.0)
    b.start_at(kicker, (x - 8.0, y))
    b.start_at(receiver, (x, y))
    b.place_ball(kicker, in_front=0.0)
    b.hold(kicker, 1.0, still=True)
    b.event("legal_restart", team="atk")
    _receive(b, rng, receiver, motion)
    b.hold(receiver, rng.uniform(2.0, 3.0), still=True)
    return receiver


def _tail(b, player):
    """Carry the result for 2-4 seconds; pad short stories with controlled movement."""
    if b.now < 6.0:
        x, y = player.anchor(b.now)
        b.dribble(player, (x + 2.0, y), max(1.5, 6.0 - b.now), settle=1.0)
    b.end_core()
    seconds = max(2.0, 10.0 - b.now)
    x, y = player.anchor(b.now)
    direction = 1.0 if player.team == "atk" else -1.0
    b.dribble(player, (x + direction * 3.0, y), seconds, settle=1.0)


def build_bp01(b, rng):
    """BP01: 2-4 stationary holds, rolling passes and cushioned receptions."""
    motion = StoryMotion.sample(rng)
    holder = _opening(b, rng, motion)
    partner = b.player("atk", "rcm")
    x, y = holder.anchor(b.now)
    b.start_at(partner, (x + 6.0, y + 4.0))
    b.begin_core()
    for cycle in range(int(rng.integers(2, 5))):
        # Reserve a full 3 s hold and 2 s tail; account for this story's pass speed.
        # The extra 0.6 m bounds the stationary target's remaining idle sway.
        distance = b.distance_to_ball(partner, b.now) + 0.6
        pass_time = (math.sqrt(motion.arrival_speed ** 2 + 2 * motion.deceleration * distance)
                     - motion.arrival_speed) / motion.deceleration
        if cycle >= 2 and b.now + pass_time + motion.trap_seconds() + 3.0 + 2.0 > 20.0:
            break
        _receive(b, rng, partner, motion)
        holder, partner = partner, holder
        b.hold(holder, rng.uniform(0.5, 3.0), still=True)
    _tail(b, holder)
    b.expect("D", "atk")


def build_bp02(b, rng):
    """BP02: the opponent runs onto a still-moving pass, cushions it and carries away."""
    motion = StoryMotion.sample(rng)
    holder = _opening(b, rng, motion)
    opponent = b.player("dfn", "ls")
    b.begin_core()
    b.hold(holder, rng.uniform(0.5, 3.0), still=True)
    speed = motion.arrival_speed
    # Choose distance for about 2 s of flight at the story's sampled friction. The run
    # ends 0.2 s early; the actual arrival solver accounts for the residual sway.
    bx, by, _ = b.ball_position(b.now)
    travel_time, deceleration = 2.0, motion.deceleration
    distance = speed * travel_time + 0.5 * deceleration * travel_time ** 2
    intercept = (bx + distance, by)
    b.start_at(opponent, (intercept[0], intercept[1] + 5.0))
    b.run_to(opponent, intercept, arrive_at=b.now + 1.8, seconds=1.8)
    b.roll_to(player=opponent, arrival_speed=speed, deceleration=deceleration)
    b.event("control_start", team="dfn")
    b.trap(opponent, motion.trap_seconds())
    b.hold(opponent, rng.uniform(0.5, 3.0), still=True)
    # Separate idle-sway restoration from the 5 m carry's 6.17 m/s^2 acceleration.
    b.wait(0.6)
    b.dribble(opponent, (intercept[0] - 4.0, intercept[1] - 3.0), 2.0, settle=1.0)
    _tail(b, opponent)
    b.expect("D", "atk", "dfn")


def build_bp03(b, rng):
    """BP03: an unreceived ground pass crosses the line and friction stops it outside."""
    motion = StoryMotion.sample(rng)
    holder = _opening(b, rng, motion, near_touchline=True)
    b.begin_core()
    b.hold(holder, rng.uniform(0.5, 3.0), still=True)
    x, y = holder.anchor(b.now)
    b.dribble(holder, (x + 3.0, y), 2.0, settle=1.0)
    launch = b.now
    bx, _, _ = b.ball_position(launch)
    b.roll_to(point=(bx + 2.0, 69.0), arrival_speed=0.0,
              deceleration=motion.deceleration, arrival_contact=False)
    out = b.time_ball_leaves_pitch(launch, b.now)
    b.event("ball_out", at=out)
    b.end_core(at=out)
    b.wait(2.0)
    b.expect("D", "atk", "D")


SUBTYPES = {"BP01": build_bp01, "BP02": build_bp02, "BP03": build_bp03}
