"""Unambiguous possession controls: passing, a clean interception, and a pass out.

All coordinates describe generic synthetic play, never a recorded match. Truth comes
only from scripted events. Each story is mirrored by the existing dataset generator.
"""

FAMILY = "basic_possession"


def _opening(b, rng, near_touchline=False, ground=False):
    """One second dead, a short legal restart, then 2-3 seconds of control."""
    kicker = b.player("atk", "rcb")
    receiver = b.player("atk", "lcb")
    y = 56.0 if near_touchline else 22.0
    x = rng.uniform(23.0, 27.0)
    b.start_at(kicker, (x - 8.0, y))
    b.start_at(receiver, (x, y))
    b.place_ball(kicker, in_front=0.0)
    b.hold(kicker, 1.0, in_front=0.0, still=True)
    b.event("legal_restart", team="atk")
    if ground:
        b.roll_to(1.0, player=receiver)
    else:
        b.kick_to(0.4, player=receiver)
    b.event("control_start", team="atk")
    b.hold(receiver, rng.uniform(2.0, 3.0), in_front=0.0, still=True)
    return receiver


def _tail(b, player):
    """Carry the result for 2-4 seconds; pad short stories with controlled movement."""
    if b.now < 6.0:
        x, y = player.anchor(b.now)
        b.dribble(player, (x + 2.0, y), max(1.5, 6.0 - b.now), settle=0.6)
    b.end_core()
    seconds = max(2.0, 10.0 - b.now)
    x, y = player.anchor(b.now)
    direction = 1.0 if player.team == "atk" else -1.0
    b.dribble(player, (x + direction * 3.0, y), seconds, settle=0.6)


def build_bp01(b, rng):
    """BP01: 2-4 receive/hold/pass cycles, never changing the possessing team."""
    holder = _opening(b, rng)
    partner = b.player("atk", "rcm")
    x, y = holder.anchor(b.now)
    b.start_at(partner, (x + 6.0, y + 4.0))
    b.begin_core()
    # Every hold has its own independent draw; do not rescale or reject durations.
    for _ in range(int(rng.integers(2, 5))):
        b.hold(holder, rng.uniform(0.5, 3.0), in_front=0.0, still=True)
        b.kick_to(0.4, player=partner)
        b.event("control_start", team="atk")
        holder, partner = partner, holder
    _tail(b, holder)
    b.expect("D", "atk")


def build_bp02(b, rng):
    """BP02: an opponent actively intercepts a pass, then carries it away."""
    holder = _opening(b, rng, ground=True)
    opponent = b.player("dfn", "ls")
    x, y = holder.anchor(b.now)
    intercept = (x + 7.0, y)
    b.start_at(opponent, (intercept[0], intercept[1] + 5.0))
    b.begin_core()
    b.hold(holder, rng.uniform(0.5, 3.0), in_front=0.0, still=True)
    # The opponent runs onto the ball, rather than passively receiving a deflection.
    flight = 1.8
    b.run_to(opponent, intercept, arrive_at=b.now + flight, seconds=flight)
    b.roll_to(flight, player=opponent)
    b.event("control_start", team="dfn")
    b.hold(opponent, rng.uniform(0.5, 3.0), in_front=0.0, still=True)
    b.dribble(opponent, (intercept[0] - 4.0, intercept[1] - 3.0), 2.0, settle=0.6)
    _tail(b, opponent)
    b.expect("D", "atk", "dfn")


def build_bp03(b, rng):
    """BP03: an untouched pass crosses the touchline; only full exit makes it dead."""
    holder = _opening(b, rng, near_touchline=True, ground=True)
    b.begin_core()
    b.hold(holder, rng.uniform(0.5, 3.0), in_front=0.0, still=True)
    x, y = holder.anchor(b.now)
    b.dribble(holder, (x + 3.0, y), 2.0, settle=0.6)
    launch = b.now
    bx, _, _ = b.ball_position(launch)
    # Roll fully across the line, then stop 1 m outside without a fictional touch.
    b.roll_to(4.0, point=(bx + 2.0, 69.0), arrival_contact=False)
    out = b.time_ball_leaves_pitch(launch, b.now)
    b.event("ball_out", at=out)
    b.end_core(at=out)
    b.wait(2.0)
    b.expect("D", "atk", "D")


SUBTYPES = {"BP01": build_bp01, "BP02": build_bp02, "BP03": build_bp03}
