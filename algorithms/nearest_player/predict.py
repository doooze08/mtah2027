"""Archived legacy smoke algorithm; see README.md for the incompatible old inputs."""


def predict(observations, metadata, config):
    """Fail explicitly rather than silently reusing an ideal referee signal."""
    raise RuntimeError(
        "nearest_player is retired: it relied on game_state and the old long table. "
        "Use placeholder for interface smoke tests.")
