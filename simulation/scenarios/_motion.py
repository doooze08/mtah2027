"""Per-story motion parameters shared by the new scenarios and basic possession."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StoryMotion:
    deceleration: float
    restitution: float
    first_retention: float
    later_retention: float
    arrival_speed: float
    trap_seconds: float

    @classmethod
    def sample(cls, rng):
        deceleration = rng.uniform(1.0, 3.0)
        restitution = rng.uniform(0.55, 0.7)
        first = rng.uniform(0.55, 0.7)
        later = rng.uniform(0.85, 1.0)
        speed = rng.uniform(3.0, 10.0)
        seconds = rng.uniform(max(0.1, 0.6 / speed), min(0.3, 1.9 / speed))
        return cls(deceleration, restitution, first, later, speed, seconds)

    def cushion(self, b, rng, player, speed):
        """Match a rolling reception to the 0.3-0.95 m foot cushioning distance."""
        seconds = rng.uniform(max(0.1, 0.6 / speed), min(0.3, 1.9 / speed))
        b.trap(player, seconds)


def open_play(b, rng, motion):
    """One second dead, a legal ground restart, then 2-3 seconds in control."""
    b.follow_ball = True
    passer, holder = b.player("atk", "rcb"), b.player("atk", "lcb")
    x, y = rng.uniform(23, 27), rng.uniform(22, 28)
    b.start_at(passer, (x - 8, y))
    b.start_at(holder, (x, y))
    b.place_ball(passer, in_front=0)
    b.hold(passer, 1, still=True)
    b.event("legal_restart", team="atk")
    b.roll_to(player=holder, arrival_speed=motion.arrival_speed,
              deceleration=motion.deceleration)
    b.event("control_start", team="atk")
    b.trap(holder, motion.trap_seconds)
    b.hold(holder, rng.uniform(2, 3), still=True)
    b.begin_core()
    return holder


def arrive(b, player, point, at, seconds=2.0, offset=(0, 5)):
    """Run to an exact physical point, accounting for the player's idle sway."""
    b.start_at(player, (point[0] + offset[0], point[1] + offset[1]))
    anchor, position = player.anchor(at), player.position(at)
    target = tuple(point[i] - position[i] + anchor[i] for i in (0, 1))
    b.run_to(player, target, arrive_at=at, seconds=seconds)


def carry_tail(b, rng, player):
    """Show deliberate control and a direction change for 2-4 seconds."""
    b.end_core()
    x, y = player.anchor(b.now)
    direction = 1 if player.team == "atk" else -1
    b.dribble(player, (x + direction * rng.uniform(4, 6), y + 2),
              rng.uniform(2.5, 3.5), settle=1.0)
