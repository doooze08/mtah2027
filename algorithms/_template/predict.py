"""Entry point of an algorithm. Copy this folder, rename it, then implement predict().

Contract shared by every algorithm so scripts can run any of them the same way:

    labels = predict(config)   # sequence of 'H' / 'A' / 'D' / 'X', one per tactical video frame

Writing the CSV, validating and scoring are handled by scripts/, not here.
"""


def predict(config):
    """Return one label per tactical video frame.

    Args:
        config: dict loaded from experiments/<experiment_id>/config.yaml (the `params` section).
    """
    raise NotImplementedError("Template only -- copy algorithms/_template to a new folder first.")
