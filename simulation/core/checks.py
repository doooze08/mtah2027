"""Scenario self-checks: is the generated clip a fair exam question?

A failure here is a data problem, not an algorithm failure (spec section 10, step 1): fix the
script, do not score it. Each check returns a list of plain-language problems; empty means pass.

    motion      no teleports, no impossible speeds, the ball only changes course when touched
    contacts    every kick, header or reception has a player close enough to do it
    events      events are in a sensible order and agree with what the ball actually does
    truth       the answer follows from the events and matches the story's expected sequence
"""

import math

import numpy as np

from simulation.core import events as ev
from simulation.core.clip import Clip, ball_fully_out
from simulation.core.constants import BALL_ID, DEAD, FPS, PITCH_LENGTH, PITCH_WIDTH

PLAYER_MAX_SPEED = 10.0           # m/s; top sprint speed
PLAYER_MAX_ACCELERATION = 12.0    # m/s^2
PLAYER_MAX_OFF_PITCH = 1.5        # metres a player may stand beyond a line (e.g. a throw-in taker)
BALL_MAX_SPEED = 35.0             # m/s
BALL_MAX_FREE_ACCELERATION = 20.0  # m/s^2 between touches (gravity, a player dribbling)
CONTACT_REACH = 1.0               # m; horizontal distance from the ball to the touching player
CONTACT_MAX_HEIGHT = 2.8          # m; highest a header can reach
CONTROL_REACH = 1.0               # m; a team gaining control has a player this close


def run_all(clip: Clip):
    """Every check for one clip; returns the combined list of problems."""
    return (check_player_motion(clip) + check_ball_motion(clip) + check_contacts(clip)
            + check_control_events(clip) + check_event_order(clip) + check_ball_out(clip)
            + check_truth(clip))


# -- motion -------------------------------------------------------------------------------------

def check_player_motion(clip: Clip):
    problems = []
    players = clip.frames[clip.frames["object"] != BALL_ID]
    for obj, rows in players.groupby("object"):
        xy = rows.sort_values("frame")[["x", "y"]].to_numpy()
        speed, acceleration = _speed_and_acceleration(xy)
        if speed.max() > PLAYER_MAX_SPEED:
            problems.append("{} runs at {:.1f} m/s (limit {})".format(
                obj, speed.max(), PLAYER_MAX_SPEED))
        if acceleration.max() > PLAYER_MAX_ACCELERATION:
            problems.append("{} accelerates at {:.1f} m/s^2 (limit {})".format(
                obj, acceleration.max(), PLAYER_MAX_ACCELERATION))
        off = np.maximum.reduce([-xy[:, 0], xy[:, 0] - PITCH_LENGTH,
                                 -xy[:, 1], xy[:, 1] - PITCH_WIDTH])
        if off.max() > PLAYER_MAX_OFF_PITCH:
            problems.append("{} stands {:.1f} m off the pitch".format(obj, off.max()))
    return problems


def check_ball_motion(clip: Clip):
    """The ball may change course sharply only at a contact (kick, header, reception)."""
    problems = []
    ball = clip.frames[clip.frames["object"] == BALL_ID].sort_values("frame")
    xyz = ball[["x", "y", "z"]].to_numpy()
    speed, acceleration = _speed_and_acceleration(xyz)
    if speed.max() > BALL_MAX_SPEED:
        problems.append("ball travels at {:.1f} m/s (limit {})".format(
            speed.max(), BALL_MAX_SPEED))

    # acceleration[i] is centred on frame i + 1; a contact disturbs the two frames around it.
    near_contact = np.zeros(len(acceleration), dtype=bool)
    for t in clip.contact_times:
        centre = t * FPS - 1
        near_contact[max(0, int(math.floor(centre)) - 1):int(math.ceil(centre)) + 2] = True
    controlled = np.zeros(len(acceleration), dtype=bool)
    centres = (np.arange(len(acceleration)) + 1) / FPS
    for start, stop in clip.controlled_windows:
        # A foot can brake much harder than grass friction. Exclude only stencils
        # touching an explicit cushioning action, not arbitrary slow/fast ball motion.
        controlled |= (centres >= start - 1 / FPS) & (centres <= stop + 1 / FPS)
    free_mask = ~(near_contact | controlled)
    free = acceleration[free_mask]
    if len(free) and free.max() > BALL_MAX_FREE_ACCELERATION:
        frame = int(np.flatnonzero(free_mask)[np.argmax(free)]) + 1
        problems.append("ball changes course at frame {} without a touch ({:.1f} m/s^2)".format(
            frame, free.max()))
    if (xyz[:, 2] < 0).any():
        problems.append("ball goes below the ground")
    return problems


def check_contacts(clip: Clip):
    problems = []
    for t in clip.contact_times:
        bx, by, bz = clip.ball_at(t)
        nearest = min(math.hypot(bx - x, by - y) for _, _, x, y in clip.players_at(t))
        if nearest > CONTACT_REACH:
            problems.append("ball is touched at {:.2f}s but the nearest player is {:.1f} m away"
                            .format(t, nearest))
        if bz > CONTACT_MAX_HEIGHT:
            problems.append("ball is touched at {:.2f}s at {:.1f} m height".format(t, bz))
    return problems


# -- events -------------------------------------------------------------------------------------

def check_control_events(clip: Clip):
    """A team can only gain control if one of its players is right at the ball."""
    problems = []
    for e in clip.events:
        if e.kind != ev.CONTROL_START:
            continue
        bx, by, _ = clip.ball_at(e.t)
        reach = min(math.hypot(bx - x, by - y)
                    for _, team, x, y in clip.players_at(e.t) if team == e.team)
        if reach > CONTROL_REACH:
            problems.append("{} gains control at {:.2f}s but its nearest player is {:.1f} m away"
                            .format(e.team, e.t, reach))
    return problems


def check_event_order(clip: Clip):
    """Restarts happen only while dead; control only while live."""
    problems = []
    live = False
    for e in sorted(clip.events, key=lambda e: e.t):
        if e.kind == ev.LEGAL_RESTART:
            if live:
                problems.append("restart at {:.2f}s while the ball is already live".format(e.t))
            live = True
        elif e.kind in (ev.BALL_OUT, ev.STOPPAGE):
            if not live:
                problems.append("{} at {:.2f}s while the ball is already dead".format(e.kind, e.t))
            live = False
        elif not live:
            problems.append("{} at {:.2f}s while the ball is dead".format(e.kind, e.t))
    return problems


def check_ball_out(clip: Clip):
    """ball_out events sit exactly where the ball first leaves, and live play stays on the pitch."""
    problems = []
    for e in clip.events:
        if e.kind != ev.BALL_OUT:
            continue
        if not ball_fully_out(clip.ball_at(e.t + 1e-6)):
            problems.append("ball_out at {:.2f}s but the ball is not wholly out".format(e.t))
        if ball_fully_out(clip.ball_at(e.t - 1e-3)):
            problems.append("ball_out at {:.2f}s but the ball was already out".format(e.t))

    ball = clip.frames[clip.frames["object"] == BALL_ID].sort_values("frame")
    for frame, x, y in ball[["frame", "x", "y"]].itertuples(index=False):
        if clip.play_live[frame] and ball_fully_out((x, y)):
            problems.append("ball is wholly out at frame {} while play is live".format(frame))
            break
    return problems


# -- truth --------------------------------------------------------------------------------------

def check_truth(clip: Clip):
    problems = []
    if clip.truth != ev.truth_from_events(clip.events, clip.n_frames):
        problems.append("truth does not follow from the event list")
    if collapse(clip.truth) != clip.expected_sequence:
        problems.append("truth reads {} but the story expects {}".format(
            " -> ".join(collapse(clip.truth)), " -> ".join(clip.expected_sequence)))
    if clip.truth[0] != DEAD:
        problems.append("clip does not start dead")
    start, stop = clip.core_window
    if not 0 <= start < stop <= clip.n_frames:
        problems.append("core window [{}, {}) is empty or outside the clip".format(start, stop))
    live_from_truth = [int(label != DEAD) for label in clip.truth]
    if live_from_truth != clip.play_live:
        problems.append("play_live signal disagrees with the dead-ball periods of the truth")
    return problems


def collapse(labels):
    """['D', 'D', 'H', 'H', 'A'] -> ['D', 'H', 'A']"""
    out = []
    for label in labels:
        if not out or out[-1] != label:
            out.append(label)
    return out


def _speed_and_acceleration(positions):
    velocity = np.diff(positions, axis=0) * FPS
    speed = np.linalg.norm(velocity, axis=1)
    acceleration = np.linalg.norm(np.diff(velocity, axis=0) * FPS, axis=1)
    return speed, acceleration
