"""Summarize already-scored trusted-tag runs; never runs or selects an algorithm."""

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = '20261111_dead_ball_trusted_tags'
PROFILES = ['accurate', 'none', 'half', 'fake', 'flipped', 'no_tags', 'legacy']
GROUPS = ['clean', 'mixed', 'delayed', 'whole', 'visible']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['dev', 'final'], default='dev')
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / 'experiments' / EXPERIMENT / 'config.yaml').read_text())
    settings = config['development' if args.split == 'dev' else 'validation']
    rows = []
    for group in GROUPS:
        dataset = '{}_{}_s{}'.format(settings['dataset_prefix'], group, settings['seed'])
        for profile in PROFILES:
            path = (ROOT / 'outputs' / EXPERIMENT / profile / 'simulation' / dataset /
                    'diagnostics.json')
            if not path.exists():
                continue
            report = json.loads(path.read_text())
            total = report['total']
            st01 = next((item for item in report['groups']['subtype']
                         if item['subtype'] == 'ST01'), None)
            rows.append({
                'dataset': dataset, 'group': group, 'profile': profile,
                'n_frames': total['n_frames'], 'wrong': total['wrong'],
                'error_pct': total['error_pct'],
                'dead_as_live': total['dead_as_live'],
                'live_as_dead': total['live_as_dead'],
                'wrong_team': total['wrong_team'],
                'st01_frames': st01['n_frames'] if st01 else 0,
                'st01_wrong': st01['wrong'] if st01 else 0,
                'st01_error_pct': st01['error_pct'] if st01 else 0.0,
            })
    if not rows:
        raise SystemExit('no diagnostics found; run run_checks first')
    target = ROOT / 'outputs' / EXPERIMENT / ('summary_' + args.split + '.csv')
    header = list(rows[0])
    lines = [','.join(header)]
    for row in rows:
        lines.append(','.join('{:.4f}'.format(row[key]) if isinstance(row[key], float)
                              else str(row[key]) for key in header))
    target.write_text('\n'.join(lines) + '\n')

    markdown = ['# Trusted tags summary', '',
                'Error is wrong frames / all frames. ST01 is the visible-whistle subtype.', '',
                '| group | profile | error % | D→live | live→D | wrong team | ST01 error % |',
                '|---|---|---:|---:|---:|---:|---:|']
    for row in rows:
        markdown.append('| {group} | {profile} | {error_pct:.3f} | {dead_as_live} | '
                        '{live_as_dead} | {wrong_team} | {st01_error_pct:.3f} |'.format(**row))
    (ROOT / 'outputs' / EXPERIMENT / ('summary_' + args.split + '.md')).write_text(
        '\n'.join(markdown) + '\n')
    print(target)


if __name__ == '__main__':
    main()
