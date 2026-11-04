"""Family 1, long ball + header duel (spec section 3).

What it tests: winning a header duel does not by itself give a team possession.

Story positions are in the attacker frame: "atk" plays the long ball and attacks towards +x.
"""

import math

from simulation.core.constants import BALL_RADIUS

FAMILY = "long_ball_header_duel"


def open_with_home_restart(b, rng):
    """Shared opening (spec 2.5): 1 s dead ball, atk restarts with a short pass, then keeps the
    ball for 2-3 s. Returns the atk player who has the ball at the end."""
    kicker = b.player("atk", "rcb")
    partner = b.player("atk", "lcb")
    b.place_ball(kicker)
    b.hold(kicker, 1.0)

    b.event("legal_restart", team="atk")                 # free kick taken: play is live
    b.kick_to(1.0, player=partner)
    b.event("control_start", team="atk")
    b.hold(partner, 0.4)                                 # first touch before moving off

    settled = rng.uniform(1.6, 2.6)                      # 2-3 s of control with the first touch
    start = partner.anchor(b.now)
    b.dribble(partner, (start[0] + rng.uniform(3, 5), start[1]), settled)
    return partner


def build_hd01(b, rng):
    """HD01: dfn defender wins the header but does not control it; the ball drops to a dfn
    midfielder, who controls it and carries it away.

    Expected: atk until the midfielder's control_start, dfn after it. Exactly one switch.
    The tested mistake: switching to dfn at the header.
    """
    passer = open_with_home_restart(b, rng)
    striker = b.player("atk", "ls")
    defender = b.player("dfn", "rcb")
    midfielder = b.player("dfn", "rcm")

    # Plan the long ball: it drops near the defender's spot, 35-55 m from the passer.
    b.begin_core()
    ball_x, ball_y, _ = b.ball_position(b.now)
    home_spot = defender.anchor(b.now)
    duel_point = (home_spot[0] + rng.uniform(-6, 0), home_spot[1] + rng.uniform(-3, 3))
    distance = math.hypot(duel_point[0] - ball_x, duel_point[1] - ball_y)
    assert 35 <= distance <= 55, "long ball is {:.1f} m, outside the spec's 35-55 m".format(distance)
    # Flight time follows from distance and a realistic long-ball speed, not drawn on its own.
    flight = distance / rng.uniform(22.0, 28.0)
    assert 1.5 <= flight <= 2.5, "long ball flies {:.2f} s, outside the spec's 1.5-2.5 s".format(
        flight)
    duel_time = b.now + flight

    # Both players arrive under the ball together; the striker is just behind the defender.
    b.run_to(defender, duel_point, arrive_at=duel_time)
    b.run_to(striker, (duel_point[0] - rng.uniform(1.0, 1.4), duel_point[1]), arrive_at=duel_time)

    # The header sends the ball back towards dfn's own midfield, 10-20 m away.
    knock_down = rng.uniform(0.8, 1.4)
    catch_point = (duel_point[0] - rng.uniform(10, 20), duel_point[1] + rng.uniform(-4, 4))
    b.run_to(midfielder, catch_point, arrive_at=duel_time + knock_down)

    # The long ball, then the header duel: a touch, but nobody controls it.
    b.kick_to(flight, player=defender, height=rng.uniform(2.2, 2.5))
    check_trap_is_set(b, defender)
    b.event("incidental_touch", team="dfn")

    # The header lands at the midfielder's feet: this is the moment dfn takes possession.
    b.kick_to(knock_down, player=midfielder, height=BALL_RADIUS)
    b.event("control_start", team="dfn")
    b.hold(midfielder, 0.4)
    b.end_core()

    # Afterwards: the midfielder carries the ball away towards dfn's attacking direction (-x).
    tail = rng.uniform(2.0, 4.0)
    b.dribble(midfielder, (catch_point[0] - rng.uniform(6, 10), catch_point[1]), tail)

    b.expect("D", "atk", "dfn")


def check_trap_is_set(b, header_player):
    """HD01 is only a fair test if, at the header, the clip really looks like a dfn win:
    the dfn player who heads the ball should be the closest player to it. That is the trap a
    "closest player has the ball" rule must fall into; without it, an algorithm could pass
    HD01 without understanding anything. Raise ValueError if the trap is not set.

    Available: b.now (header time), b.all_players(), b.distance_to_ball(player, t),
    player.team ("atk"/"dfn"), player.role.
    """
    closest = min(b.all_players(), key=lambda player: b.distance_to_ball(player, b.now))
    if closest is not header_player:
        raise ValueError(
            "trap not set at the header ({:.2f}s): closest is {} {} at {:.2f} m, "
            "not {} {} at {:.2f} m".format(
                b.now, closest.team, closest.role, b.distance_to_ball(closest, b.now),
                header_player.team, header_player.role,
                b.distance_to_ball(header_player, b.now)))


SUBTYPES = {"HD01": build_hd01}
