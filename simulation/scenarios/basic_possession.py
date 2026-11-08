"""Basic possession with rolling passes, explicit control events and foot cushioning."""

FAMILY = "basic_possession"


def _receive(b, rng, receiver):
    """Arrive at 3-10 m/s; control starts at contact, before cushioning ends."""
    speed = rng.uniform(3.0, 10.0)
    b.roll_to(player=receiver, arrival_speed=speed)
    b.event("control_start", team=receiver.team)
    _cushion(b, rng, receiver, speed)


def _cushion(b, rng, receiver, speed):
    # Couple duration to speed so stopping distance is 0.3-0.95 m, not an overshoot.
    seconds = rng.uniform(max(0.1, 0.6 / speed), min(0.3, 1.9 / speed))
    b.trap(receiver, seconds)


def _opening(b, rng, near_touchline=False):
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
    _receive(b, rng, receiver)
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
    holder = _opening(b, rng)
    partner = b.player("atk", "rcm")
    x, y = holder.anchor(b.now)
    b.start_at(partner, (x + 6.0, y + 4.0))
    b.begin_core()
    for cycle in range(int(rng.integers(2, 5))):
        # Bound optional extra cycles, never redraw or shorten an independent hold.
        # 5.5 s covers a 3 s hold, this short pass at >=3 m/s, and a <=0.3 s trap.
        if cycle >= 2 and b.now + 5.5 + 2.0 > 20.0:
            break
        _receive(b, rng, partner)
        holder, partner = partner, holder
        b.hold(holder, rng.uniform(0.5, 3.0), still=True)
    _tail(b, holder)
    b.expect("D", "atk")


def build_bp02(b, rng):
    """BP02: the opponent runs onto a still-moving pass, cushions it and carries away."""
    holder = _opening(b, rng)
    opponent = b.player("dfn", "ls")
    b.begin_core()
    b.hold(holder, rng.uniform(0.5, 3.0), still=True)
    speed = rng.uniform(3.0, 10.0)
    # Choose distance for about 2 s of flight at fixed 2 m/s^2 friction. The run
    # ends 0.2 s early; the actual arrival solver accounts for the residual sway.
    bx, by, _ = b.ball_position(b.now)
    travel_time, deceleration = 2.0, 2.0
    distance = speed * travel_time + 0.5 * deceleration * travel_time ** 2
    intercept = (bx + distance, by)
    b.start_at(opponent, (intercept[0], intercept[1] + 5.0))
    b.run_to(opponent, intercept, arrive_at=b.now + 1.8, seconds=1.8)
    b.roll_to(player=opponent, arrival_speed=speed, deceleration=deceleration)
    b.event("control_start", team="dfn")
    _cushion(b, rng, opponent, speed)
    b.hold(opponent, rng.uniform(0.5, 3.0), still=True)
    b.dribble(opponent, (intercept[0] - 4.0, intercept[1] - 3.0), 2.0, settle=1.0)
    _tail(b, opponent)
    b.expect("D", "atk", "dfn")


def build_bp03(b, rng):
    """BP03: an unreceived ground pass crosses the line and friction stops it outside."""
    holder = _opening(b, rng, near_touchline=True)
    b.begin_core()
    b.hold(holder, rng.uniform(0.5, 3.0), still=True)
    x, y = holder.anchor(b.now)
    b.dribble(holder, (x + 3.0, y), 2.0, settle=1.0)
    launch = b.now
    bx, _, _ = b.ball_position(launch)
    b.roll_to(point=(bx + 2.0, 69.0), arrival_speed=0.0, arrival_contact=False)
    out = b.time_ball_leaves_pitch(launch, b.now)
    b.event("ball_out", at=out)
    b.end_core(at=out)
    b.wait(2.0)
    b.expect("D", "atk", "D")


SUBTYPES = {"BP01": build_bp01, "BP02": build_bp02, "BP03": build_bp03}
