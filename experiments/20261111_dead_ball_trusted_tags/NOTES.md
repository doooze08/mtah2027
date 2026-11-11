# 20261111_dead_ball_trusted_tags

- **作者**：@doooze08
- **日期**：2026-11-11
- **算法**：`algorithms/dead_ball_aware/`
- **Git commit**：TBD

## 目的

把 `dead_ball_aware` 的标签策略从“弱线索、先证明有 6 s 慢球”改为“标签默认可信、坐标定边界”，
并在模拟和真实 tactical 上检查它是否达到预期。标签只负责说明这里有一次停顿／重启；重启时刻、
发球人和 D 的起止仍由出球、出界、长缺球和慢球坐标给出。没有标签时仍走原来的纯坐标分支。

本轮不从真实标签统计任何参数，不修改模拟器或共享运行器，不读取公开答案或评分。

## 第 0 步：数据前置检查

本机 `data/tactical/BAR-ATH_tactical_smart_tagging.xml` 存在，`starter/load_smart_tagging.py`
读出 638 个实例，其中 59 个 `SET PIECES`：

| Type | 数量 |
|---|---:|
| Throw-in | 26 |
| Corner Kick | 12 |
| Goal Kick | 10 |
| Free Kick | 5 |
| Kick Off (After Goal) | 4 |
| Kick Off (Start) | 2 |

`Team=N/A` 的定位球标签为 32 个（全部实例中为 36 个）。两个半场的官方开球帧都落在对应
`Kick Off (Start)` 标签区间内，加载器时间基检查通过。没有统计标签与缺球、重启位置的分布。

## 模拟设计

- 数据：17 个子型，5 个故事，主客镜像；五种缺球条件（clean、mixed、delayed、whole、visible）。
- 开发种子 35000；验收种子 37000（故事使用 37000–37004），验收只跑一次。
- 主条件 `accurate`：保留率 1.0、时间扰动 0；窗口仍按文件格式前置 3.5 s、开头 5 s、后续 35 s。
- 压力测试：`none` 全部漏标；`half` 随机保留一半；`fake` 在活球高速段加假标签；
  `flipped` 翻转有队名的标签球队。
- 对照：`no_tags` 同一数据不传标签；`legacy` 用 `20261109_dead_ball_tags_final` 的旧参数和
  旧名义标签（保留率 0.75、±2 s 扰动）。

运行：

```bash
.venv/bin/python -B -m experiments.20261111_dead_ball_trusted_tags.run_checks --split dev
.venv/bin/python -B -m experiments.20261111_dead_ball_trusted_tags.run_checks --split final
```

输出在 `outputs/20261111_dead_ball_trusted_tags/<profile>/simulation/<dataset_id>/`；
汇总表由 `summary.py` 生成，逐片段表和报告只在 `outputs/`，不进 Git。

## 模拟结果

TBD

## 真实比赛

TBD

## 结论、限制与下一步

TBD
