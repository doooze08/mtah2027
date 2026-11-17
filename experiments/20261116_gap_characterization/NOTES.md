# 缺球段是活球还是死球：可区分特征调研

状态：测量完成。只新增实验脚本、配置和本记录；没有修改 `algorithms/`、模拟器或已完成的实验。
本记录只回答“哪些特征分得最干净”，不写阈值规则，也不把任何特征直接接进算法。

## 1. 问题、数据和证据顺序

最严重的整段错误有两类：活球中长时间缺球被判成 D，以及球可见的停表被判成活球。本调研测量两类特征能否区分“死球缺球”和“活球缺球”：球重现的位置/状态，以及球员整体运动。

- 设计：Metrica Game 1、2（`ext_metrica_game_1/2`）。
- 检查：Metrica Game 3，在特征和样本定义冻结后只运行一次；结果见第 6 节。
- 不使用 BAR-ATH 的公开答案；本场诊断本次未做。所有外部样本只用数据商事件/弱标签，不用跟踪坐标反推答案。

## 2. 样本定义

固定种子 `20261116`。每场两半场合为一个 match；所有 `start_s`/`stop_s` 是 clip 内秒数。

| 类型 | 定义 |
|---|---|
| `dead_gap` | 球坐标连续缺失至少 5 s，段内弱标签 D 占多数 |
| `live_gap` | 同样缺球，但弱标签 H/A 占多数；若缺球结束后第一个原始事件是 `SET PIECE`，标为 `suspicious_gap`，不并入普通活球 |
| `artificial_live` | 球可见且弱标签全程 H/A 的连续时段；固定种子随机遮住 5–15 s，每场 200 段；遮罩内标签必须全为活球 |
| `dead_visible` | 弱标签 D 且球全程可见的连续子段，至少 2 s；只测球员特征 |

`dead_gap`/`live_gap` 的段级标签采用多数票，和 PR #19 的逐段统计一致；平票丢弃。`suspicious_gap` 是 `live_gap` 的子集，单独统计，不并入普通活球。`dead_visible` 按“球一缺失就把 D 段切开”的方式取子段，否则 Game 3 没有任何全程可见的 D 段。

样本数：

| split | dead_gap | live_gap | 其中 suspicious | artificial_live | dead_visible |
|---|---:|---:|---:|---:|---:|
| design（G1/G2） | 145 | 20 | 8 | 400 | 53 |
| test（G3） | 74 | 14 | 11 | 200 | 20 |

外部数据来自 `external.convert` 生成的四套 `ext_metrica_*`；事件顺序来自原始 Metrica 事件文件。原始文件和转换结果都不进 Git。

## 3. 特征定义

### A. 球重现

- **重现/消失位置类别**：`out_or_touchline`、`corner`、`goal_area`、`center_circle`、`other`。先判场外，再判角旗 1 m、球门区、中圈、边线 1 m 带，最后 `other`。
- **重现后 0.5 s 球速**：重现后 12 个相邻位置差速度的平均，单位 m/s。
- **消失前 1 s 球速**：缺失开始前最多 25 个相邻位置差速度的平均。
- **重现–消失距离**：两个已知球位置之间的米制距离。
- **扣除两队整体位移后的距离**：用缺失前后所有有位置球员的平均位置差作为整体位移，再看重现点与“消失点 + 位移”的距离。

类别边界写在 `features.py` 常量中，来源是 IFAB Law 1 的场地标记：球门区深 5.5 m、宽 18.32 m，中圈半径 9.15 m，角旗弧半径 1 m。边线 1 m 带是分析前固定的操作定义，不是 Law 1 的标记。

### B. 球员整体运动

每段取中位数（`_med`）和 90 分位（`_p90`）：

1. `f1_speed_*`：有位置球员速度的中位数，1 s 后向平均；定义同 `experiments/20261116_collective_speed`。少于 5 个有效速度的帧为 NaN。
2. `speed_gt4_count_*`：速度严格大于 4 m/s 的人数。
3. `team_speed_*`：每队 10 名场上球员（不含门将）平均位置的移动速度，两队取平均；1 s 平滑。
4. `team_cos_*`：两队整体移动方向的余弦；只有两队整体速度都大于 0.3 m/s 时计算，否则 NaN。
5. `dispersion_*`：每队球员到本队中心的平均距离，两队取平均。

球员速度一律由相邻帧位置差计算，不用 observations 的 `_s` 列。门将无法从匿名槽位直接识别：每队按有限位置数取 11 个槽位，再取“到某一球门中点的中位距离最小”的槽位为门将，另一侧球门视为本方球门；其余 10 个槽位为场上球员。换人、重复槽位和追踪缺失会让这个近似不完美，逐段统计中保留有限样本数。每队少于 5 个有效位置时该帧球队特征为 NaN。

### C. 消失前

消失位置类别和消失前 1 s 球速，定义同上。

## 4. 设计集分布

下表是 G1/G2 的 `median (Q1, Q3)`；`dead_visible` 的 A 类特征不适用，记为 `-`。完整表在 `outputs/20261116_gap_characterization/distributions.csv`。

| feature | dead_gap | real_live_gap | artificial_live | dead_visible |
|---|---|---|---|---|
| `reappear_speed_0p5s_m_s` | 11.179 (8.327, 15.194) | 15.734 (13.834, 17.241) | 7.024 (3.360, 11.346) | - |
| `disappear_speed_1s_m_s` | 8.794 (5.160, 13.234) | 11.968 (9.985, 15.814) | 6.407 (3.805, 10.436) | - |
| `reappear_to_disappear_m` | 6.557 (3.341, 13.207) | 12.638 (8.053, 17.952) | 30.521 (19.229, 44.394) | - |
| `reappear_to_disappear_after_team_shift_m` | 14.475 (8.311, 20.487) | 23.223 (18.167, 26.748) | 22.179 (14.051, 31.356) | - |
| `f1_speed_med` | 1.039 (0.854, 1.229) | 1.374 (1.211, 1.446) | 1.936 (1.556, 2.445) | 1.820 (1.290, 2.588) |
| `f1_speed_p90` | 1.378 (1.171, 1.592) | 1.660 (1.484, 1.820) | 2.813 (2.231, 3.426) | 2.270 (1.561, 3.063) |
| `speed_gt4_count_med` | 0.000 (0.000, 0.000) | 0.000 (0.000, 0.000) | 1.250 (1.000, 3.000) | 1.000 (0.000, 2.000) |
| `speed_gt4_count_p90` | 1.000 (0.000, 1.000) | 1.000 (0.000, 2.250) | 4.000 (2.000, 8.000) | 3.000 (1.000, 6.000) |
| `team_speed_med` | 0.795 (0.514, 1.081) | 1.312 (1.090, 1.476) | 1.846 (1.417, 2.339) | 1.639 (1.209, 2.540) |
| `team_speed_p90` | 1.212 (0.928, 1.646) | 1.805 (1.385, 2.057) | 2.714 (2.122, 3.418) | 2.145 (1.555, 3.097) |
| `team_cos_med` | 0.960 (0.904, 0.982) | 0.988 (0.984, 0.990) | 0.981 (0.960, 0.992) | 0.985 (0.962, 0.995) |
| `team_cos_p90` | 0.998 (0.993, 0.999) | 1.000 (0.999, 1.000) | 0.999 (0.997, 1.000) | 0.999 (0.996, 1.000) |
| `dispersion_med` | 14.824 (12.774, 16.492) | 16.493 (15.038, 18.029) | 16.201 (14.954, 17.236) | 15.805 (14.483, 18.157) |
| `dispersion_p90` | 16.182 (15.055, 17.635) | 18.806 (17.285, 20.831) | 17.113 (15.924, 18.193) | 16.467 (15.178, 18.701) |

位置类别（百分比；只列四种主要类别，NaN 未列入）：

| 类别 | dead_gap | real_live_gap | artificial_live | dead_visible |
|---|---|---|---|---|
| 重现 `other` | 40.7% | 8.3% | 91.2% | - |
| 重现 `out_or_touchline` | 38.6% | 8.3% | 1.8% | - |
| 重现 `goal_area` | 12.4% | 91.7% | 0.8% | - |
| 重现 `center_circle` | 8.3% | 0.0% | 5.0% | - |
| 消失 `out_or_touchline` | 63.4% | 100.0% | 3.0% | - |
| 消失 `other` | 33.8% | 0.0% | 88.8% | - |

`suspicious_gap` 的设计集分布（不进主表）：F1 中位数 0.745、球队速度 0.591、重现球速 14.659、重现–消失距离 9.603 m；8 段中 7 段重现于 `other`、1 段中圈。它们更像死球，不应与普通活球合并。

## 5. 单特征 AUC（设计集，死球缺球 vs 人工遮球）

AUC 定义为“人工活球的特征值大于死球缺球”的概率；小于 0.5 表示方向相反。`separation = |AUC - 0.5| * 2`。类别特征用 one-vs-rest 指示变量，不能当作连续阈值。

| feature | AUC | separation | 方向 | n live/dead |
|---|---:|---:|---|---:|
| `f1_speed_med` | 0.929 | 0.858 | 活球更高 | 400/145 |
| `f1_speed_p90` | 0.918 | 0.835 | 活球更高 | 400/145 |
| `speed_gt4_count_p90` | 0.908 | 0.816 | 活球更高 | 400/145 |
| `team_speed_p90` | 0.908 | 0.816 | 活球更高 | 400/145 |
| `team_speed_med` | 0.907 | 0.813 | 活球更高 | 400/145 |
| `speed_gt4_count_med` | 0.876 | 0.752 | 活球更高 | 400/145 |
| `reappear_to_disappear_m` | 0.859 | 0.717 | 活球更高 | 395/145 |
| `disappear_category=out_or_touchline` | 0.198 | 0.604 | 死球更高 | 400/145 |
| `disappear_category=other` | 0.775 | 0.550 | 活球更高 | 400/145 |
| `reappear_category=other` | 0.753 | 0.506 | 活球更高 | 400/145 |
| `reappear_speed_0p5s_m_s` | 0.270 | 0.459 | 死球更高 | 394/144 |
| `reappear_to_disappear_after_team_shift_m` | 0.690 | 0.379 | 活球更高 | 395/145 |
| `team_cos_med` | 0.675 | 0.350 | 活球更高 | 400/145 |
| `dispersion_med` | 0.663 | 0.326 | 活球更高 | 400/145 |
| `disappear_speed_1s_m_s` | 0.395 | 0.211 | 死球更高 | 393/145 |
| `dispersion_p90` | 0.611 | 0.223 | 活球更高 | 400/145 |
| `team_cos_p90` | 0.610 | 0.221 | 活球更高 | 400/145 |

完整 AUC（含所有位置类别指示变量、design/test/all 三个 split）在 `outputs/20261116_gap_characterization/feature_auc.csv`。

## 6. Game 3 检查（只运行一次）

特征和样本定义在运行 G3 前冻结；`features.py` 和 `config.yaml` 的哈希保存在 `outputs/20261116_gap_characterization/design/frozen_hashes.txt`。G3 样本数：dead_gap 74、live_gap 14（其中 suspicious 11）、artificial_live 200、dead_visible 20。

关键分布：

| feature | dead_gap（G3） | artificial_live（G3） | AUC |
|---|---:|---:|---:|
| `f1_speed_med` | 1.050 | 2.047 | 0.925 |
| `f1_speed_p90` | 1.429 | 2.848 | 0.903 |
| `team_speed_med` | 0.674 | 1.871 | 0.911 |
| `reappear_to_disappear_m` | 4.676 | 31.977 | 0.903 |
| `reappear_speed_0p5s_m_s` | 10.337 | 5.718 | 0.288 |
| `team_cos_med` | 0.933 | 0.979 | 0.744 |
| `reappear_category=other` | 25.7% | 93.5% | 0.839 |
| `disappear_category=out_or_touchline` | 78.4% | 4.5% | 0.131 |

G3 的排序与设计集一致：F1 中位数仍最强（0.925），球队重心速度次之（0.911），位置类别 `other` 的方向也一致。G3 没有明显变差，位置类别甚至略强；没有据此改动特征。完整 G3 分布和 AUC 在 `distributions.csv`、`feature_auc.csv` 的 `test` 行。

### 长度混杂检查

死球缺球的时长通常比人工遮球长（设计集中位数 20.5 s vs 8.4 s），所以“重现–消失距离”可能部分反映时长。把死球缺球限制到 5–15 s 后重算（只作为敏感性检查，不作为主结果）：所有比赛上该距离 AUC 0.956、F1 中位数 0.873、球队速度 0.857；设计集 0.956/0.873/0.847，G3 0.957/0.884/0.870。距离在等时长子集上仍然很强，但死球样本只剩 96 段；该检查说明它不是单纯由时长造成，不能说明真实部署时没有长度偏差。完整表在 `feature_auc_length_matched.csv`。

## 7. 真实活球缺球与可疑段

下表是全部 `live_gap`/`suspicious_gap` 的逐段摘要（`real_live_segments.csv` 含全部特征；不含 BAR-ATH 帧号）。`start_s`/`stop_s` 是 clip 内秒数。

| match | clip | start–stop (s) | 缺球后首事件 | suspicious | 重现类别 | 消失类别 | F1 中位 | 球队速度中位 | 重现球速 |
|---:|---|---:|---|---:|---|---|---:|---:|---:|
| 1 | first_half | 311.6–339.2 | RECOVERY | no | goal_area | out_or_touchline | 1.300 | 1.269 | 16.898 |
| 1 | first_half | 879.3–903.1 | RECOVERY | no | goal_area | out_or_touchline | 1.226 | 1.139 | 18.267 |
| 1 | first_half | 1065.4–1089.8 | RECOVERY | no | goal_area | out_or_touchline | 1.407 | 1.181 | 16.716 |
| 1 | first_half | 1180.7–1214.7 | SET PIECE FREE KICK | yes | other | other | 1.177 | 1.010 | 16.954 |
| 1 | first_half | 1317.9–1345.8 | RECOVERY | no | goal_area | out_or_touchline | 1.165 | 0.945 | 20.303 |
| 1 | first_half | 1739.4–1770.8 | SET PIECE FREE KICK | yes | other | other | 0.757 | 0.519 | 14.757 |
| 1 | first_half | 2309.6–2362.1 | RECOVERY | no | goal_area | out_or_touchline | 0.851 | 0.664 | 16.032 |
| 1 | second_half | 232.1–249.6 | RECOVERY | no | goal_area | out_or_touchline | 1.929 | 1.590 | 1.740 |
| 1 | second_half | 1042.0–1072.0 | RECOVERY | no | goal_area | out_or_touchline | 1.437 | 1.454 | 22.548 |
| 2 | first_half | 177.7–198.2 | RECOVERY | no | goal_area | out_or_touchline | 1.475 | 1.540 | 15.435 |
| 2 | first_half | 1094.4–1119.7 | RECOVERY | no | out_or_touchline | out_or_touchline | 1.381 | 1.356 | 9.802 |
| 2 | first_half | 1193.8–1215.6 | SET PIECE FREE KICK | yes | other | other | 1.324 | 1.177 | 9.396 |
| 2 | first_half | 1741.0–1787.2 | RECOVERY | no | goal_area | out_or_touchline | 0.909 | 0.766 | 13.746 |
| 2 | second_half | 3.6–19.0 | SET PIECE KICK OFF | yes | center_circle | other | 0.182 | 0.103 | 14.561 |
| 2 | second_half | 161.2–174.2 | RECOVERY | no | goal_area | out_or_touchline | 1.579 | 1.733 | 13.863 |
| 2 | second_half | 1161.5–1179.5 | RECOVERY | no | goal_area | out_or_touchline | 1.367 | 1.426 | 14.552 |
| 2 | second_half | 1485.9–1543.5 | SET PIECE FREE KICK | yes | other | other | 0.662 | 0.473 | 17.330 |
| 2 | second_half | 2018.8–2026.0 | SET PIECE FREE KICK-RETAKEN | yes | other | other | 1.975 | 2.308 | 9.166 |
| 2 | second_half | 2026.8–2049.0 | SET PIECE FREE KICK | yes | other | other | 0.697 | 0.663 | 6.972 |
| 2 | second_half | 2057.4–2095.6 | SET PIECE FREE KICK | yes | other | other | 0.733 | 0.467 | 20.137 |
| 3 | first_half | 305.2–324.3 | SET PIECE THROW IN | yes | out_or_touchline | other | 0.664 | 0.392 | 16.718 |
| 3 | first_half | 343.9–350.6 | SET PIECE FREE KICK\|INDIRECT | yes | other | other | 1.550 | 1.230 | 9.350 |
| 3 | first_half | 451.5–466.3 | SET PIECE FREE KICK\|INDIRECT | yes | other | other | 1.258 | 1.026 | 9.989 |
| 3 | first_half | 749.6–763.5 | SET PIECE FREE KICK\|INDIRECT | yes | center_circle | other | 1.085 | 0.496 | 13.926 |
| 3 | first_half | 1253.1–1258.6 | SET PIECE FREE KICK\|INDIRECT | yes | other | other | 1.568 | 1.267 | 7.651 |
| 3 | first_half | 1821.3–1887.8 | RECOVERY | no | goal_area | out_or_touchline | 0.521 | 0.286 | 8.205 |
| 3 | first_half | 2206.5–2213.4 | SET PIECE FREE KICK\|INDIRECT | yes | other | other | 1.432 | 0.913 | 3.634 |
| 3 | first_half | 2387.5–2403.2 | SET PIECE FREE KICK\|INDIRECT | yes | goal_area | other | 1.296 | 0.925 | 17.209 |
| 3 | first_half | 2424.6–2438.0 | SET PIECE FREE KICK\|INDIRECT | yes | other | other | 0.941 | 0.724 | 7.824 |
| 3 | second_half | 98.8–114.4 | RECOVERY | no | goal_area | out_or_touchline | 1.304 | 0.952 | 15.776 |
| 3 | second_half | 227.4–235.8 | SET PIECE FREE KICK\|INDIRECT | yes | out_or_touchline | other | 1.222 | 1.143 | 7.955 |
| 3 | second_half | 346.2–382.7 | SET PIECE FREE KICK\|INDIRECT | yes | other | other | 0.462 | 0.369 | 18.292 |
| 3 | second_half | 2480.1–2507.4 | RECOVERY | no | goal_area | out_or_touchline | 1.399 | 1.349 | 14.465 |
| 3 | second_half | 2705.2–2745.5 | SET PIECE FREE KICK\|INDIRECT | yes | other | other | 1.124 | 1.008 | 15.983 |

所有 15 段非可疑“真实活球”缺球的第一个事件都是 `RECOVERY`，消失类别都是边线/场外，重现几乎都在球门区；这更像漏标的死球/重启，而不是干净的活球。可疑段大多以定位球开始，F1 和球队速度也更接近死球。因此：

- “真实活球”样本不适合作为干净的活球基准，只能定性对照；
- 人工遮球和真实活球的特征不同（人工 F1 中位 1.94，真实 1.31–1.37），不能把人工遮球的 AUC 直接当成真实缺球的 AUC；
- 反过来说，弱标签里的“活球长缺球”本身混有大量可疑段，这也解释了为什么靠弱标签评估的球员速度规则会不稳定。

## 8. 结论

1. **分得最干净的是球员整体运动，而不是预期的“重现位置/状态”。** `f1_speed_med` 的 AUC 0.929（G3 0.925），`team_speed_med` 0.907（G3 0.911）；两者高度相关，实际是同一类信号。`speed_gt4_count_p90` 也接近（0.908）。
2. **重现位置类别有稳定但较弱的方向**：活球缺球重现更常在 `other`（设计 91.2%，G3 93.5%），死球缺球更多在边线/场外或定位球区；`reappear_category=other` 的 AUC 0.753（G3 0.839）。它不能单独达到运动特征的区分度。
3. **“重现球速”方向与预期相反**：死球缺球的 0.5 s 球速中位数 11.2 m/s，人工活球 7.0 m/s（AUC 0.270，死球更高）。死球缺球常以开球/解围结束，球一出现就很快；人工遮球结束时球可能只是慢慢滚动或在脚下。这个特征不能按“活球一出现就在动”解释。
4. **方向余弦几乎不可用**：两类样本的中位余弦都接近 1（0.96 vs 0.98），AUC 只有 0.675；离散程度也弱（0.663）。在本数据上，两队整体方向不是有效的死球/活球分离量。
5. **球可见的 D 段球员并不慢**：`dead_visible` 的 F1 中位 1.82（G1/G2）、1.84（G3），甚至高于死球缺球；球员运动特征不能识别“球可见但停表”的情况。这正好对应另一类整段错误，需另找信号。
6. **G3 没有明显变差**：主要排序和方向保持，F1 AUC 0.925、球队速度 0.911、位置类别 0.839；没有根据 G3 改特征。

如果只能选一两个：`f1_speed_med`（或等价的球队重心速度中位数）是唯一接近“干净”的单特征；重现位置类别可作为方向一致的补充，但明显更弱。这里不给出阈值、组合规则或算法接入方式。

## 9. 限制

- 弱标签有噪声：15 段“真实活球”全部以 `RECOVERY` 开始、消失于边线/场外，可能是漏标死球；可疑段只覆盖“首个事件是 SET PIECE”的情况，其他漏标形式没有单独标出。
- 真实活球只有 15 段（G3 仅 3 段非可疑），不能算稳定 AUC；所有 AUC 都是死球 vs 人工遮球。
- 人工遮球不是真实追踪丢失：它只遮球，球员轨迹完整；真实缺球常伴随转播/追踪问题。人工与真实活球的 F1 分布明显不同，结论不能直接外推到真实缺球。
- 死球缺球时长分布比人工遮球长；距离特征受时长影响。5–15 s 等时长检查仍显示距离很强，但死球样本只剩 96 段，且这不是主分析。
- 球队特征基于“每队有限位置最多的 11 个槽位 + 最近球门近似门将”，换人、重复槽位和缺失会让 10 名场上球员的近似不完美；没有球员身份。
- 位置类别是离散的，AUC 用 one-vs-rest 指示变量；多类别联合分布可能比单个指示变量更有信息，但本任务不训练分类器。
- 未做 BAR-ATH 的特征分布诊断，也没有使用公开五分钟答案。

## 10. 产物和复现

脚本：

- `experiments/20261116_gap_characterization/features.py`：样本/特征定义和读取。
- `experiments/20261116_gap_characterization/build_samples.py`：生成逐段样本。
- `experiments/20261116_gap_characterization/analyze.py`：分布、AUC、逐段表。
- `experiments/20261116_gap_characterization/config.yaml`：固定参数、窗口、场地常量。实验脚本为独立运行，`features.py` 中的常量与 config 一致，但不解析 YAML；config 是冻结参数的记录。

运行（从仓库根目录）：

```bash
# 设计集（G1/G2）
.venv/bin/python experiments/20261116_gap_characterization/build_samples.py --matches 1,2

# 特征冻结后，检查集（G3）只跑一次
.venv/bin/python experiments/20261116_gap_characterization/build_samples.py --matches 3

# 汇总
.venv/bin/python experiments/20261116_gap_characterization/analyze.py \
  --inputs outputs/20261116_gap_characterization/design/samples_design.csv \
           outputs/20261116_gap_characterization/samples_test.csv
```

输出（`outputs/` 已被 Git 忽略）：

- `samples_all.csv`：926 段全部特征。
- `real_live_segments.csv`：真实活球/可疑段逐段表。
- `distributions.csv`：按 split/type 的分布。
- `feature_auc.csv`：单特征 AUC。
- `feature_auc_length_matched.csv`：5–15 s 等时长敏感性。
- `summary.json`：样本数和段长。
- `design/`：G1/G2 设计阶段结果和冻结哈希。

仓库测试：88 个测试通过（expected failures=1）。没有原始数据、转换结果或输出进入 Git。
