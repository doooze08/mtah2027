"""Script events, and the only place where the answer (truth labels) is made.

The truth is derived from the event list alone: no positions, no possession algorithm.
This is the rule table of spec section 2.3:

    event                   meaning                                          label
    incidental_touch        touch without control (deflection, lost duel)    unchanged
    control_start(team)     a player of `team` takes controlled possession   -> team, if ball live
    ball_out                ball wholly over the pitch boundary              -> D
    stoppage                referee stops play                               -> D
    legal_restart(team)     a legal restart takes effect                     -> team

Every clip starts dead (spec 2.5), so the label before the first event is D.
"""

import math
from dataclasses import dataclass
from typing import List, Optional

from simulation.core.constants import DEAD, FPS

INCIDENTAL_TOUCH = "incidental_touch"
CONTROL_START = "control_start"
BALL_OUT = "ball_out"
STOPPAGE = "stoppage"
LEGAL_RESTART = "legal_restart"

EVENT_KINDS = (INCIDENTAL_TOUCH, CONTROL_START, BALL_OUT, STOPPAGE, LEGAL_RESTART)
EVENTS_WITH_TEAM = (INCIDENTAL_TOUCH, CONTROL_START, LEGAL_RESTART)


@dataclass
class Event:
    kind: str                 # one of EVENT_KINDS
    t: float                  # continuous time in seconds
    team: Optional[str]       # "H" / "A" (or "atk" / "dfn" inside the builder); None if no team

    @property
    def frame(self):
        return boundary_frame(self.t)


def boundary_frame(t):
    """First frame that already carries the new label: ceil(25 * t) (spec 2.4).

    The tiny tolerance keeps an event at exactly t = 4.00 s on frame 100 instead of letting
    floating-point noise (4.0000000001 * 25) push it to frame 101.
    """
    return int(math.ceil(t * FPS - 1e-9))


def truth_from_events(events: List[Event], n_frames: int) -> List[str]:
    """Per-frame labels H / A / D for one clip, from its event list only."""
    labels = []
    state = DEAD
    pending = sorted(events, key=lambda e: e.t)
    next_event = 0
    for frame in range(n_frames):
        # Apply, in time order, every event whose boundary frame is this frame.
        while next_event < len(pending) and pending[next_event].frame <= frame:
            state = apply_event(state, pending[next_event])
            next_event += 1
        labels.append(state)
    return labels


def apply_event(state: str, event: Event) -> str:
    """The label after `event`, given the label before it."""
    if event.kind in (BALL_OUT, STOPPAGE):
        return DEAD
    if event.kind == LEGAL_RESTART:
        return event.team
    if event.kind == CONTROL_START:
        # Control while the ball is dead does not restart play. Applied in time order, this also
        # gives "dead wins" when a stoppage and a control fall on the same frame (spec 2.4).
        return state if state == DEAD else event.team
    return state              # incidental_touch: possession carries on


def play_live_from_events(events: List[Event], n_frames: int) -> List[int]:
    """The referee signal handed to algorithms: 1 while the ball is in play, else 0.

    It says nothing about which team has the ball; that is the algorithm's job.
    """
    live = []
    state = 0
    pending = sorted(events, key=lambda e: e.t)
    next_event = 0
    for frame in range(n_frames):
        while next_event < len(pending) and pending[next_event].frame <= frame:
            kind = pending[next_event].kind
            if kind in (BALL_OUT, STOPPAGE):
                state = 0
            elif kind == LEGAL_RESTART:
                state = 1
            next_event += 1
        live.append(state)
    return live
