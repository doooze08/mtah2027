"""Summarize already-scored paired experiments; never run or select algorithms."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--baseline', help='Baseline output ID; defaults to experiment/baseline')
    parser.add_argument('--datasets', required=True, help='comma-separated dataset ids')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2] / 'outputs'
    pairs = []
    for dataset in args.datasets.split(','):
        reports = [json.loads((root / exp / 'simulation' / dataset / 'diagnostics.json').read_text())
                   for exp in (args.experiment, args.baseline or args.experiment + '/baseline')]
        pairs.append((dataset, *reports))
    lines = ['# 同数据比较', '', '误差分母为各组全部帧；D→活球、活球→D 均表示真值→预测。', '',
             '| 数据集 | 帧数 | 新算法错误帧（%） | 原算法错误帧（%） |',
             '|---|---:|---:|---:|']
    for dataset, new, old in pairs:
        a, b = new['total'], old['total']
        lines.append(f"| {dataset} | {a['n_frames']} | {a['wrong']}（{a['error_pct']:.4f}%） | "
                     f"{b['wrong']}（{b['error_pct']:.4f}%） |")
    lines += ['', '| 数据集 | 算法 | D→活球 | 活球→D | H/A 队伍错误 |', '|---|---|---:|---:|---:|']
    for dataset, new, old in pairs:
        for name, report in [('新', new), ('原', old)]:
            t = report['total']
            lines.append(f"| {dataset} | {name} | {t['dead_as_live']} | {t['live_as_dead']} | {t['wrong_team']} |")
    lines += ['', '| 数据集 | 场景族 | 新算法错误帧（%） | 原算法错误帧（%） | 新 D→活球 | 新活球→D |',
              '|---|---|---:|---:|---:|---:|']
    for dataset, new, old in pairs:
        previous = {r['family']: r for r in old['groups']['family']}
        for a in new['groups']['family']:
            b = previous[a['family']]
            lines.append(f"| {dataset} | {a['family']} | {a['wrong']}（{a['error_pct']:.4f}%） | "
                         f"{b['wrong']}（{b['error_pct']:.4f}%） | {a['dead_as_live']} | {a['live_as_dead']} |")
    lines += ['', '| 数据集 | 停顿子型 | 新错误帧（%） | 原错误帧（%） |', '|---|---|---:|---:|']
    for dataset, new, old in pairs:
        previous = {r['subtype']: r for r in old['groups']['subtype']}
        for a in new['groups']['subtype']:
            if a['subtype'].startswith('ST'):
                b = previous[a['subtype']]
                lines.append(f"| {dataset} | {a['subtype']} | {a['wrong']}（{a['error_pct']:.4f}%） | "
                             f"{b['wrong']}（{b['error_pct']:.4f}%） |")
    lines += ['', '时刻偏差 = 预测帧 − 真值帧，25 fps；匹配容差 5 s，同起止状态、一对一最近匹配。',
              '未匹配事件计入漏检／多检，不从偏差分布中隐藏。完整分布及各族分布见 diagnostics.json。', '',
              '| 数据集 | 算法 | 事件 | 匹配 | 漏检 | 多检 | 最小 / P05 / 中位 / P95 / 最大（帧） | ±2 帧内 |',
              '|---|---|---|---:|---:|---:|---|---:|']
    for dataset, new, old in pairs:
        for name, report in [('新', new), ('原', old)]:
            for kind in ('turnover', 'restart', 'dead_start'):
                t = report['timing']['ALL'][kind]
                q = ' / '.join(str(t.get(k, '—')) for k in ('min', 'p05', 'median', 'p95', 'max'))
                lines.append(f"| {dataset} | {name} | {kind} | {t['matched']} | {t['missed']} | "
                             f"{t['extra']} | {q} | {t.get('within_2_frames', 0)} |")
    target = root / args.experiment / 'comparison.md'
    target.write_text('\n'.join(lines) + '\n')
    print(target)


if __name__ == '__main__':
    main()
