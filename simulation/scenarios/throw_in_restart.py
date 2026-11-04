"""Family 3, throw-in restart (spec section 5).

What it tests: the end of a dead ball, who restarts, and any later change of possession are three
separate questions.

Story positions are in the attacker frame: "atk" takes the throw and attacks towards +x. The
throw is taken from the touchline at y = 68 (the attacker's left).
"""

import math

from simulation.core.constants import BALL_RADIUS, PITCH_WIDTH

FAMILY = "throw_in_restart"

TAKER_BEYOND_LINE = 0.8            # metres the taker stands outside the touchline


def build_ti01(b, rng):
    """TI01: atk waits, raises the ball, fakes, then throws legally to a team-mate.

    Expected: D until the ball enters the pitch, atk from that instant on.
    The tested mistake: ending the dead ball early because an atk player is close to the ball
    or because the ball has already left the taker's hands.
    """
    taker = b.player("atk", "lm")
    receiver = b.player("atk", "lcm")
    marker = b.player("dfn", "rm")

    # Who stands where.
    throw_x = rng.uniform(40, 60)
    b.start_at(taker, (throw_x, PITCH_WIDTH + TAKER_BEYOND_LINE))
    throw_distance = rng.uniform(5, 20)
    angle = math.radians(rng.uniform(40, 80))           # from the touchline into the pitch
    catch_point = (throw_x + throw_distance * math.cos(angle),
                   PITCH_WIDTH + TAKER_BEYOND_LINE - throw_distance * math.sin(angle))
    b.start_at(receiver, catch_point)
    b.start_at(marker, (catch_point[0], catch_point[1] - rng.uniform(2.5, 3.5)))  # a step infield

    # Dead ball, 2-3 s: the taker waits, raises the ball, fakes a throw and raises it again.
    b.place_ball(taker, height=1.0, in_front=0.0)
    b.begin_core()
    b.hold(taker, rng.uniform(0.2, 1.2), height=1.0, in_front=0.0)  # waiting
    b.hold(taker, 0.8, height=2.2, in_front=0.0)                    # ball up over the head
    b.hold(taker, 0.5, height=1.7, in_front=0.0)                    # the fake
    b.hold(taker, 0.5, height=2.2, in_front=0.0)

    # The throw. Play restarts at the exact instant the ball enters the pitch, not at release.
    release = b.now
    flight = throw_distance / rng.uniform(10.0, 13.0)
    arrival = b.kick_to(flight, player=receiver, height=BALL_RADIUS)
    b.event("legal_restart", team="atk", at=b.time_ball_enters_pitch(release, arrival))

    # The team-mate takes it: control stays with atk, so the label does not change here.
    b.event("control_start", team="atk")
    b.hold(receiver, 0.4)
    b.end_core()

    # Afterwards: carry on for a few seconds so a late, wrong switch would show up.
    tail = rng.uniform(2.0, 4.0)
    b.dribble(receiver, (catch_point[0] + rng.uniform(6, 10), catch_point[1]), tail)

    b.expect("D", "atk")


SUBTYPES = {"TI01": build_ti01}
