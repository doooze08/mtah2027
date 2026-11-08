"""Shared algorithm entry point for tactical ATD and simulated clips.

    labels = predict(observations, metadata, config)

The runner loads inputs and writes CSVs. Algorithms never load files or answers themselves.
"""


def predict(observations, metadata, config):
    """Return one H/A/D/X label per input row, in the same order.

    Args:
        observations: DataFrame with exactly 141 columns: frame, ball_x, ball_y,
            then <slot>_x, <slot>_y, <slot>_s for slots 1..46 (numeric order).
            One row per frame at 25 fps, frame numbered 0..n-1. Coordinates use
            pitch boundaries 0..1; out-of-pitch values are preserved, missing values
            are NaN. Player speed s is in m/s. No ball height or player identities.
        metadata: dict with slot_teams (string slot -> H/A or None for unknown/unused),
            pitch_length and pitch_width in metres, fps. No events or referee signals.
        config: params from experiments/<experiment_id>/config.yaml.

    Do not assume slots are persistent player identities, or positions always exist.
    """
    raise NotImplementedError("Copy algorithms/_template and implement predict().")
