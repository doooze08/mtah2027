# 本场长缺球诊断：有多少段同时像活球

只做计数和描述。没有读取答案、没有运行评分、没有修改算法，也没有把逐段时间写进 Git。
逐段时间在 `outputs/20261117_bar_ath_gap_diagnostic/gaps.csv`，仅供团队看录像理解，
不是验证标签，也不能当作人工标注或调参依据。

## 1. 固定定义与预注册判据

两条描述线来自 PR #24，原样沿用，不重新选择：

- **球员快**：段内 `f1_speed_med` 高于 1.575 m/s。这个数值是 Metrica artificial_live
  的 25 分位，是描述线，不是阈值。
- **开阔且远**：球重现类别为 `other`，且重现点与消失点距离超过 10 m。
  这也是描述线，不是阈值或规则。

球员速度只由相邻帧位置差分计算，不使用 ATD 的 `_s` 列；所有特征直接 import
`experiments/20261116_gap_characterization/features.py`，没有复制实现。

**运行前写定的判据**：

- 候选段不超过 5 段且总时长不超过 2 分钟：不值得写规则，记录后结束。
- 候选段至少 10 段或总时长至少 3 分钟：值得设计规则，下一步另开任务。
- 介于两者之间：看录像理解候选段是什么场景，再由团队决定；不据此调整描述线。

候选段的定义是“球员快 + 开阔且远 + 不与 SET PIECES/GOALS 重叠”。
两个“快/远”描述线在整个分析中没有改过；结果也没有反过来改动它们。

## 2. 数据边界和尺度检查

只统计两个计分半场：从第一半场第一个计分帧到最后一个计分帧，以及第二半场开球后的
计分帧到最后一个计分帧。两半场之间的中场休息、开球前热身和未计分帧不进入统计。
ATD 通过 `observations.atd.load_tactical` 读取；Smart Tagging 通过
`simulation.run_algorithm.load_tags('smart-tagging')` 读取；当前预测使用
`20261111_dead_ball_trusted_tags` 的 `trusted_tags: true` 参数，只用来统计
“这些段现在被判成什么”，不作为准确率。Metrica 尺度检查只读取
`observations.csv` 和 `metadata.json`，不打开 `truth.csv` 或任何答案文件。

### 逐帧 F1 尺度

| 数据 | 中位数 m/s | Q1 | Q3 | 有限帧数 |
|---|---:|---:|---:|---:|
| 本场 BAR-ATH（两个计分半场） | 1.360 | 0.965 | 2.025 | 154,337 |
| Metrica Game 1（全场） | 1.359 | 0.969 | 2.097 | 145,006 |
| Metrica Game 2（全场） | 1.372 | 0.991 | 2.057 | 141,156 |
| Metrica Game 3（全场） | 1.583 | 1.111 | 2.336 | 143,761 |

本场与 Game 1/2 基本同速（差 +0.001 / −0.012 m/s），比 Game 3 慢 0.223 m/s。
后一个差值超过 0.2 m/s，已记录；描述线照原样使用，没有重新标定。
本场没有“整体明显偏慢于所有 Metrica”的情况。

PR #22 曾报告本场全场 F1 中位数约 1.218 m/s。那是包含中场休息的整文件统计；
本任务按任务要求只取两个计分半场，得到 1.360 m/s。两者不是同一统计口径，
不构成需要重新标定的新证据。

## 3. 样本与标签覆盖

两个计分半场合计 **130 段** 至少 5 s 的缺球，总时长 **2556.24 s**。
其中 129 段有可用的 `f1_speed_med`；1 段少于 5 名有位置球员，按“慢”处理并保留在表里。

Smart Tagging 覆盖（一段可与多个 code 重叠，所以下面不是互斥计数）：

- 与 `SET PIECES` 重叠：65 段；
- 与 `GOALS` 重叠：11 段（其中 9 段同时与 `SET PIECES` 重叠）；
- 与其他 phase code 重叠：102 段；
- 不与任何 code 重叠：16 段。

互斥覆盖表使用优先级 `SET PIECES` 优先，其次 `GOALS`，再次 `other phase`，最后 `none`：
`SET PIECES` 65 段、`GOALS` 2 段、`other phase` 47 段、`none` 16 段。
候选段的排除条件是“不与 SET PIECES 且不与 GOALS 重叠”，所以 `other phase` 和
`none` 都可能成为候选。

## 4. 2×2：球员快慢 × 重现位置

| | 开阔且远 | 定位球位置或近 |
|---|---:|---:|
| 球员快 | 15 段 / 119.48 s | 4 段 / 24.56 s |
| 球员慢 | 24 段 / 427.56 s | 87 段 / 1984.64 s |

“球员快”合计 19 段（14.6%），低于任务预期的 20–30 段；没有移动 1.575 m/s
的描述线来凑数。多数段仍然是“球员慢 + 定位球位置或近”。

## 5. 按标签覆盖拆开

每格为“段数 / 总秒数”。

| 覆盖 | 总段数 / 秒 | 快 + 开阔远 | 快 + 定位球或近 | 慢 + 开阔远 | 慢 + 定位球或近 |
|---|---:|---:|---:|---:|---:|
| SET PIECES | 65 / 1542.92 | 6 / 52.80 | 2 / 12.72 | 13 / 288.48 | 44 / 1188.92 |
| GOALS | 2 / 50.60 | 0 / 0 | 0 / 0 | 0 / 0 | 2 / 50.60 |
| other phase | 47 / 740.08 | 7 / 52.48 | 1 / 6.08 | 9 / 102.16 | 30 / 579.36 |
| none | 16 / 222.64 | 2 / 14.20 | 1 / 5.76 | 2 / 36.92 | 11 / 165.76 |

“快 + 开阔远”在 SET PIECES 中仍有 6 段，但候选定义要求排除 SET PIECES/GOALS，
所以它们不进入候选。SET PIECES 中的“快 + 开阔远”多数可能是定位球开出后的
快速运动，而不是真正的活球缺球；这里只按覆盖拆开，不下结论。

## 6. 候选段

候选段 = 球员快 + 开阔且远 + 不与 SET PIECES/GOALS 重叠。

- **9 段，66.68 s**；段长分布：最短 5.28 s，Q1 6.08 s，中位 6.76 s，
  Q3 8.92 s，最长 11.20 s。
- 当前可信标签模式预测：D 帧 **1667 / 1667 = 100%**。
  这只是“当前算法怎么判”，不是这些段真的是死球还是活球。
- 9 段落在预注册判据的“介于两者之间”：不足 10 段、也不足 3 分钟，
  但超过“不超过 5 段且不超过 2 分钟”的结束线。因此本任务**不宣布值得写规则**，
  也不宣布不值得；需要团队看 `outputs/` 里的逐段时间和录像后再决定。

候选段的前后 Smart Tagging 类型（类型名即可；`gap_id` 是匿名编号，不含时间）：

| 候选 | 前一个标签类型 | 后一个标签类型 | 覆盖 |
|---|---|---|---|
| G002 | PLAYERS IN THE BOX | PROGRESSION | none |
| G003 | PLAYERS IN THE BOX | Free Kick | other phase |
| G007 | BALL IN FINAL THIRD | BUILD UP | other phase |
| G050 | PLAYERS IN THE BOX | Corner Kick | other phase |
| G053 | BALL IN FINAL THIRD | CREATING CHANCES | other phase |
| G065 | BALL IN FINAL THIRD | LONG BALL | none |
| G077 | LONG BALL | Corner Kick | other phase |
| G086 | LONG BALL | Goal Kick | other phase |
| G093 | BALL IN FINAL THIRD | LONG BALL | other phase |

注意：后一个标签类型里出现 Free Kick、Corner Kick 或 Goal Kick，并不说明缺球段本身
与 SET PIECES 重叠。Smart Tagging 的 set-piece 区间是重启前后的一个窗口，可能从缺球
结束后才开始；候选的“不与 SET PIECES 重叠”只表示两个区间没有交集，不能证明缺球段
是活球。这正是需要看录像的地方。

## 7. 球员快、但在定位球位置重现的段

定义：球员快，且重现类别为 `corner`、`goal_area` 或 `center_circle`。

| 匿名编号 | 前一个标签类型 | 后一个标签类型 | 覆盖 | 重现类别 | F1 m/s | 重现–消失距离 m |
|---|---|---|---|---|---|---:|---:|
| S033 | DEFENDING IN MIDDLE THIRD | PROGRESSION | none | center_circle | 1.616 | 11.08 |
| S089 | BALL IN THE BOX | BALL IN FINAL THIRD | SET PIECES | goal_area | 1.609 | 2.37 |

另有两段“球员快但不开阔远、也不是上述三个定位球类别”（重现类别 `other` 但距离
不超过 10 m，或类别为其他近点），不列入本表；它们在 `outputs/` 的 `gaps.csv` 中。

## 8. 解释与限制

- 两线索都像活球的候选只有 9 段、66.68 s；当前规则把它们全部判成 D。
  这只是“像活球”的计数，不是“它们真是活球”的证据，也不是“推翻 D 会提高分数”的证据。
- 9 段落在预注册的“看录像再决定”区间；本任务没有替团队做决定，也没有写规则。
- 本场与 Game 1/2 的 F1 尺度几乎相同，比 Game 3 慢 0.22 m/s；描述线未改。
  这也说明不能把 Game 3 的分布直接当作本场标定。
- 两条描述线来自 Metrica 的人工遮球和 PR #24 的 weak-label 研究；人工遮球可能
  高估“活球”的可分性，本场标签覆盖也只是 Smart Tagging，不是答案。
- 候选段的“不与 SET PIECES/GOALS 重叠”是区间不交，不等于没有定位球。候选段前后
  仍可能出现 Free Kick、Corner Kick 或 Goal Kick 类型（见上表）。
- 一段缺球可能少于 5 名有位置球员，F1 为空；本表把它按“慢”归类，只有 1 段。
- 没有读取 `evaluation/gt/`，没有运行 `evaluate.sh`，没有单独报告公开五分钟窗口。
- 未修改 `algorithms/`、`simulation/` 或转换器；本目录只有诊断脚本和记录。

## 9. 复现

```bash
.venv/bin/python experiments/20261117_bar_ath_gap_diagnostic/diagnose.py --data-dir data
```

输出（不进 Git）：

- `outputs/20261117_bar_ath_gap_diagnostic/gaps.csv`：130 段的逐段特征、标签覆盖、
  当前 D 帧数和时间；时间只在这里。
- `outputs/20261117_bar_ath_gap_diagnostic/candidates.csv`：9 个候选段。
- `outputs/20261117_bar_ath_gap_diagnostic/f1_scale.csv`：本场和 Metrica 的 F1 尺度。
- `outputs/20261117_bar_ath_gap_diagnostic/summary.json`：汇总数字和判据结果。
