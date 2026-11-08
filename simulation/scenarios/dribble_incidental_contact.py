"""DC01-DC03: passive leg deflections followed by recovery or a later interception."""

import math

from simulation.scenarios._motion import StoryMotion, arrive, carry_tail, open_play

FAMILY = "dribble_incidental_contact"


def _approach(b, rng, holder):
    """A 2-6 m/s dribble, followed by the last forward touch towards a defender's leg."""
    x, y = holder.anchor(b.now)
    seconds = rng.uniform(2.0, 2.4)
    peak = rng.uniform(2.5, 5.5)
    b.dribble(holder, (x + 2 * peak * seconds / math.pi, y), seconds, settle=1)


def build_dc01(b, rng):
    """A passive leg deflection travels 0.5-2 m back across atk's path; atk recovers it."""
    motion = StoryMotion.sample(rng)
    holder = open_play(b, rng, motion)
    _approach(b, rng, holder)
    hx, hy = holder.position(b.now)
    distance = rng.uniform(0.5, 2.0)
    angle = rng.uniform(0.5, 0.9)
    point = (hx + distance * math.cos(angle), hy + distance * math.sin(angle))
    target = (hx, hy)
    speed = motion.arrival_speed
    outgoing = math.sqrt(speed ** 2 + 2 * motion.deceleration * distance)
    seconds = 2 * distance / (outgoing + speed)
    defender = b.player("dfn", "ls")
    b.roll_to(point=point, arrival_speed=outgoing / 0.85,
              deceleration=motion.deceleration)
    arrive(b, defender, point, b.now, offset=(0, 3))
    b.event("incidental_touch", team="dfn")
    b.deflect_to(defender, seconds, target, deceleration=motion.deceleration)
    b.event("control_start", team="atk")
    motion.cushion(b, rng, holder, speed)
    carry_tail(b, rng, holder)
    b.expect("D", "atk")


def build_dc02(b, rng):
    """The ball deflects 2-5 m; both players chase for 0.4-1.2 s and atk recovers."""
    motion = StoryMotion.sample(rng)
    holder = open_play(b, rng, motion)
    _approach(b, rng, holder)
    run_start = b.now
    distance = rng.uniform(2.0, 5.0)
    # Choose a joint distance/time pair with 3-10 m/s remaining at reception.
    max_chase = 2 * distance / (math.sqrt(9 + 2 * motion.deceleration * distance) + 3)
    chase = rng.uniform(max(0.4, distance / 6), min(1.2, max_chase))
    outgoing = distance / chase + 0.5 * motion.deceleration * chase
    incoming = outgoing / 0.85
    approach = 0.3
    approach_distance = incoming * approach + 0.5 * motion.deceleration * approach ** 2
    bx, by, _ = b.ball_position(b.now)
    point = (bx + approach_distance, by)
    dy = rng.uniform(0.5, 0.8)
    target = (point[0] - math.sqrt(distance ** 2 - dy ** 2), point[1] + dy)
    defender = b.player("dfn", "ls")
    arrive(b, defender, point, b.now + approach, offset=(0, 3))
    b.roll_to(approach, point=point, deceleration=motion.deceleration)
    reception = b.now + chase
    anchor, position = holder.anchor(reception), holder.position(reception)
    destination = tuple(target[i] - position[i] + anchor[i] for i in (0, 1))
    b.run_to(holder, destination, arrive_at=reception, seconds=reception - run_start)
    b.event("incidental_touch", team="dfn")
    b.deflect_to(defender, chase, target, deceleration=motion.deceleration)
    # Both pursue; the first defender stays behind and never establishes control.
    b.run_to(defender, (target[0] + 1.5, target[1] + 1.5),
             arrive_at=b.now + 0.8, seconds=chase + 0.8)
    b.event("control_start", team="atk")
    speed = distance / chase - 0.5 * motion.deceleration * chase
    motion.cushion(b, rng, holder, speed)
    carry_tail(b, rng, holder)
    b.expect("D", "atk")


def build_dc03(b, rng):
    """A passive deflection reaches a second defender, who traps and carries it away."""
    motion = StoryMotion.sample(rng)
    holder = open_play(b, rng, motion)
    _approach(b, rng, holder)
    bx, by, _ = b.ball_position(b.now)
    first = b.player("dfn", "ls")
    second = b.player("dfn", "lcm")
    distance = rng.uniform(3, 5)
    speed = motion.arrival_speed
    outgoing = math.sqrt(speed ** 2 + 2 * motion.deceleration * distance)
    seconds = 2 * distance / (outgoing + speed)
    point = (bx + rng.uniform(1.5, 2), by)
    b.roll_to(point=point, arrival_speed=outgoing / 0.85,
              deceleration=motion.deceleration)
    arrive(b, first, point, b.now, offset=(0, 3))
    target = (point[0] + 0.3 * distance, point[1] + math.sqrt(0.91) * distance)
    arrive(b, second, target, b.now + seconds, offset=(0, 4))
    b.event("incidental_touch", team="dfn")
    b.deflect_to(first, seconds, target, deceleration=motion.deceleration)
    b.event("control_start", team="dfn")
    motion.cushion(b, rng, second, speed)
    carry_tail(b, rng, second)
    b.expect("D", "atk", "dfn")


SUBTYPES = {"DC01": build_dc01, "DC02": build_dc02, "DC03": build_dc03}
