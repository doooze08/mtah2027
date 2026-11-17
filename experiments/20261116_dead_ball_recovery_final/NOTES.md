# 20261116_dead_ball_recovery_final

- **日期**：2026-11-16
- **算法**：`algorithms/dead_ball_recovery/`，参数见本目录 `config.yaml`，与开发实验相同
- **代码版本**：基于 `main` 提交 `76042bc`；本 PR 合并后在此补提交号

## 目的

对 [开发实验](../20261116_dead_ball_recovery_dev/NOTES.md)的规则和参数做一次性独立检查。

## 模拟结果

```bash
python -B -m experiments.20261116_dead_ball_recovery_dev.run_checks --split final
```

预先指定独立种子 64000–64004（此前未用过），17 子型，每型 5 故事及主客镜像，五种缺球条件，每组 170 段、74,070 帧。
只运行一次，新算法和对照各预测一次；之后没有修改代码、参数或标签方案。输出在 `outputs/20261116_dead_ball_recovery_final/`。

| 条件 | 错误帧：`dead_ball_aware` → 新 | 活球判 D：原 → 新 | spellF1：原 → 新 | 重启 匹配/漏检/多检：原 → 新 |
|---|---:|---:|---:|---|
| clean | 1830 → 1830 | 934 → 934 | 0.9706 → 0.9706 | 210/0/0 → 210/0/0 |
| mixed | 1486 → 1226 | 644 → 384 | 0.9769 → 0.9847 | 206/4/0 → 210/0/0 |
| delayed | 2138 → 1878 | 644 → 384 | 0.9698 → 0.9776 | 206/4/0 → 210/0/0 |
| whole | 674 → 280 | 546 → 152 | 0.9824 → 0.9941 | 204/6/0 → 210/0/0 |
| visible | 1830 → 1830 | 934 → 934 | 0.9706 → 0.9706 | 210/0/0 → 210/0/0 |

850 段中 14 段错误帧减少，0 段增加；D 判活球和球队错误帧数在五组中均不变。

## 真实比赛

输出诊断已在本地运行，汇总数字见 [开发记录](../20261116_dead_ball_recovery_dev/NOTES.md)的“真实比赛”一节。
**提交文件的生成和官方格式校验结果待补**；命令如下：

```bash
python -m simulation.run_algorithm --experiment 20261116_dead_ball_recovery_final --tactical --tags smart-tagging
python evaluation/validate_submission.py outputs/20261116_dead_ball_recovery_final/submission/dead_ball_recovery.csv
```

提交前把输出复制为 `<队名>.csv`，并对复制后的文件再运行一次官方校验。

## 有效范围

- 五个条件复用同一批故事，850 段不是 850 个独立样本。
- 模拟成绩不代表真实比赛精度。该检查集已使用，不能再作为后续修改的独立验收集。
- 同日早些时候曾在旧基线（`cc4eda4`）上用种子 48000 和 60000 做过同样的检查，结论一致；
  那批结果对应旧代码，不计入本记录。
