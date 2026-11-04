"""Fixed conventions shared by every scenario (spec section 2.1 and 2.4)."""

# Time
FPS = 25                      # frames per second; frame f is sampled at t = f / FPS seconds

# Pitch, in metres. Origin at one corner, x along the length, y across the width.
# The pitch edge is the outer edge of the touchline.
PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0

# Ball
BALL_RADIUS = 0.11            # ball centre height when resting on the grass
GRAVITY = 9.81                # m/s^2, used for ball flights

# Labels
HOME, AWAY, DEAD = "H", "A", "D"

# Object id of the ball in the observation table; players are p01..p22.
BALL_ID = "ball"

# Column names of the files written to outputs/simulation_sets/<dataset_id>/.
# simulation/README.md documents the same lists; keep the two in sync.
OBSERVATION_COLUMNS = ["clip", "frame", "object", "team", "x", "y", "z"]
GAME_STATE_COLUMNS = ["clip", "frame", "play_live", "restart_team"]
TRUTH_COLUMNS = ["clip", "frame", "label"]
EVENT_COLUMNS = ["clip", "event", "t", "frame", "team"]
SAMPLE_COLUMNS = ["clip", "family", "subtype", "story_id", "seed", "initiating_team",
                  "n_frames", "core_start", "core_stop", "expected_sequence"]
