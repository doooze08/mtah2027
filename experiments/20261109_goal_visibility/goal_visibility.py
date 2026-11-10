"""Find planar whole-ball goal-line crossings and the next missing-ball onset."""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from games import GAME, GAMES, half_video_blocks, require


def crossings(ball, length, width, radius, goal_width):
    """Yield adjacent-sample outward crossings; never bridge missing coordinates."""
    lower, upper = (width - goal_width) / 2 + radius, (width + goal_width) / 2 - radius
    for f in range(1, len(ball)):
        before, after = ball[f - 1], ball[f]
        if not np.isfinite([before, after]).all():
            continue
        for side, line in (('left', -radius), ('right', length + radius)):
            crossed = before[0] >= line > after[0] if side == 'left' else before[0] <= line < after[0]
            if crossed:
                fraction = (line - before[0]) / (after[0] - before[0])
                y = before[1] + fraction * (after[1] - before[1])
                if lower <= y <= upper:
                    yield f, side, float(y)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir')
    args = parser.parse_args()
    config = yaml.safe_load(Path(__file__).with_name('config.yaml').read_text())
    meta_path, raw_path = require(['atd_meta', 'atd_raw'], data_dir=args.data_dir)
    field = ET.parse(meta_path).find('.//FieldSize')
    length, width = float(field.findtext('Width')), float(field.findtext('Height'))
    with open(raw_path) as handle:
        ball = np.array([[float(v) for v in line.rstrip().rsplit(':', 1)[1].split(',')[:2]]
                         for line in handle]) * [length, width]
    fps = GAMES[GAME]['fps']
    rows = []
    for half, first, last in half_video_blocks(GAME):
        section = ball[first:last + 1]
        missing = ~np.isfinite(section).all(axis=1)
        starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
        for frame, side, y in crossings(section, length, width,
                                         config['ball_radius_m'], config['goal_width_m']):
            following = starts[starts > frame]
            next_gap = int(following[0]) if len(following) else None
            rows.append({'half': half, 'frame': first + frame, 'goal_side': side,
                         'crossing_y_m': y,
                         'next_gap_frame': first + next_gap if next_gap is not None else None,
                         'visible_delay_s': (next_gap - frame) / fps if next_gap is not None else None,
                         'censored_visible_s': (len(section) - frame) / fps if next_gap is None else None})
    out = Path(__file__).resolve().parents[2] / 'outputs' / Path(__file__).parent.name
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / 'crossings.csv', index=False)
    delays = [r['visible_delay_s'] for r in rows if r['visible_delay_s'] is not None]
    summary = {'planar_crossing_candidates': len(rows), 'delays_s': delays,
               'config': config, 'pitch_m': [length, width],
               'limitation': 'No ball height: these are planar goal-mouth crossings, not '
               'confirmed goals. Next gap need not be caused by the crossing. Missing crossings '
               'cannot be detected. No answer, tagging or video is read.'}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
