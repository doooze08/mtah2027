# 外部弱标签测试集（2026-11-16）

本实验只做转换：把本地 `data/external/` 的 Metrica Sample Game 1/2/3 和 SkillCorner
`1925299` 转成与 `outputs/simulation_sets/<id>/` 相同的五个文件，使现有
`simulation.run_algorithm` 和 `simulation.evaluate` 不改逻辑即可运行。弱标签由数据商的
事件／阶段／possession 推出，不是官方 H/A/D 真值；本文件不评价算法、不调参、不做结论。

没有读取 BAR-ATH 的答案、Smart Tagging 或公开窗口评分；只使用了 `data/external/` 下的
其他比赛数据和 `data/tactical/` 的 XML 元信息（仅核对坐标方向，见第 4 节）。

**PR 范围**：只含 `external/` 转换代码、`tests/test_external_convert.py`、本说明和
`simulation/evaluate.py` 的 GT X 计分修正；不提交 `data/`、`outputs/` 下的任何原始数据、
转换结果、预测或报告。外部弱标签只用于诊断，不能替代官方 H/A/D 真值。

## 1. 产物与代码

| 内容 | 位置 |
|---|---|
| 转换命令 | `python -m external.convert --source metrica`（或 `skillcorner` / `all`） |
| 共用写出与槽位/速度/上采样 | [`external/common.py`](../../external/common.py) |
| Metrica 读取、事件与弱标签 | [`external/metrica.py`](../../external/metrica.py) |
| SkillCorner 读取、phase 与弱标签 | [`external/skillcorner.py`](../../external/skillcorner.py) |
| 命令行入口 | [`external/convert.py`](../../external/convert.py) |
| 单元测试 | [`tests/test_external_convert.py`](../../tests/test_external_convert.py) |
| 生成的数据集 | `outputs/simulation_sets/ext_metrica_game_1/`、`..._game_2`、`..._game_3`、`ext_skillcorner_1925299/` |

每个数据集两个 clip：`first_half` 和 `second_half`。本地 `data/external/skillcorner/` 只有
`1925299` 一场完整数据，因此只生成一个 SkillCorner 数据集；扫描目录时发现更多比赛会自动一并转换。目录名固定，重复转换同一目录需要
`--force`；原始数据和转换结果都在 `.gitignore` 的 `data/*`、`outputs/*` 规则下，不进 Git。

## 2. 各数据集规模、缺球率与标签占比

| 数据集 | 两半 frame 数 | 总 frame | 缺球 frame | H | A | D | X |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ext_metrica_game_1` | 71,268 / 73,738 | 145,006 | 56,755（39.14%） | 54,733（37.75%） | 47,215（32.56%） | 39,436（27.20%） | 3,622（2.50%） |
| `ext_metrica_game_2` | 67,941 / 73,215 | 141,156 | 57,884（41.01%） | 57,602（40.81%） | 47,666（33.77%） | 34,291（24.29%） | 1,597（1.13%） |
| `ext_metrica_game_3` | 69,661 / 74,100 | 143,761 | 46,325（32.22%） | 55,170（38.38%） | 50,192（34.91%） | 36,857（25.64%） | 1,542（1.07%） |
| `ext_skillcorner_1925299` | 75,576 / 77,626 | 153,202 | 33,480（21.85%） | 53,378（34.84%） | 33,600（21.93%） | 63,661（41.55%） | 2,563（1.67%） |

X 的来源也只有两类：Metrica 的半场首尾（Game 1/2/3 分别为 2,932 / 1,042 / 1,063
frame）和 10 s 犯规窗口（690 / 555 / 479 frame），没有其他 X；SkillCorner 的 2,563 个 X
中 969 frame 来自重叠 phase，1,594 frame 来自 phase 内没有球员追踪。

缺球率与调研一致（Metrica 32–41%，SkillCorner 约 22%）；SkillCorner 上采样后为
153,202 frame，约等于 61,282 × 2.5。每 clip 的缺球率：

- Game 1：上半 42.67%，下半 35.73%
- Game 2：上半 28.57%，下半 52.54%
- Game 3：上半 31.74%，下半 32.67%
- SkillCorner：上半 20.98%，下半 22.71%

SkillCorner 的上采样只在两个原始帧都有值时线性插值；任一端缺失保持 NaN。整帧无球员的
转播缺口保持全 NaN。上采样后全表只有两种状态：119,722 frame 有 22 名球员，33,480 frame
有 0 名球员且球也缺失；没有半帧。标签按最近原始帧映射，因此边界量化到 0.1 s。

## 3. 观测格式与速度

四个数据集都是每半场一个 clip、clip 内 `frame=0..n-1`、25 fps、142 列、46 槽位
（24 H / 22 A，slot 1–24 为 H、25–46 为 A），metadata 全部 46 键都有球队，球场
105 × 68 m。每名球员固定映射到本队一个槽位，未使用槽位全 NaN。坐标保持 0–1 归一化，
场外值不裁切，缺失保持 NaN，不插值补缺。球 z、球员身份和事件都不进观测。

| 数据集 | 每帧最多 H/A 槽位 | 某队 12 个位置的 frame 数 | 速度 P99 / 最大 / >10 m/s | 坐标有限值范围（x 与 y 合计） |
|---|---:|---:|---:|---:|
| Game 1 | 12 / 12 | H 3，A 3 | 6.22 / 557.03 / 745 | −0.0500 .. 1.0600 |
| Game 2 | 12 / 12 | H 3，A 1 | 6.05 / 182.05 / 1,447 | −0.0497 .. 1.0500 |
| Game 3 | 11 / 11 | 0 / 0 | 6.02 / 53.42 / 1,271 | −0.0779 .. 1.0414 |
| SkillCorner | 11 / 11 | 0 / 0 | 6.00 / 12.08 / 61 | −0.1025 .. 1.0869 |

- P99 均低于 10 m/s，符合预期。最大速度异常全部保留、没有裁切：Game 1 的 557 m/s 来自
  下半场开头几帧同一槽位的连续位置跳变（frame 10–14，slot 3）；Game 2 的 182 m/s 来自
  下半场开头 slot 25 的跳变；Game 3 与 SkillCorner 的最大值也是单帧/短段跳变。这些是原始
  追踪或外推造成的，不是转换公式造成的；速度只在相邻帧都有位置时计算。
- Metrica 1/2 的 14/12 名 roster 球员中，每帧通常 11 人有位置。少数帧出现 12 个有限位置，
  检查后第 12 个位置与另一槽位坐标完全相同，是重复检测/重复列，不是额外上场球员；按原始
  数据保留，所以这些 frame 的“有位置槽位数”为 12。Game 3 和 SkillCorner 每队最多 11。
- 场外坐标值计数（x 或 y 超出 [0,1]，按所有球员坐标合计）：Game 1 31,012、Game 2
  21,364、Game 3 23,423、SkillCorner 15,785；没有裁切。

## 4. 坐标方向核对

真实 ATD 是 Metrica EPTS，`observations/atd.py` 通过 kloppy EPTS 读取，坐标系统为
kloppy 的归一化系统：原点在左上、y 向下。用与 `observations/atd.py` 相同的 kloppy
EPTS 元信息路径检查 ATD：provider=`metrica`、fps=25、pitch=105×68；对应的
`MetricaCoordinateSystem` 为 `origin=top-left`、`vertical=TOP_TO_BOTTOM`。本转换遵守
同一方向：

- **Metrica Game 3**：直接用 kloppy EPTS（和 `observations/atd.py` 同一加载路径），
  不做翻转。用 Game 3 自己的 XML 元信息核对：Team A 上半场 `attack_direction_first_half`
  为 `right_to_left`，其 Right Back（formation `position_y=0.9`）在开球帧的原始 y≈0.19；
  Team B 为 `left_to_right`，其 Right Back（同样 `position_y=0.9`）在原始 y≈0.79。这只有
  在“原点左上、y 向下”时才能同时成立。由此确认 EPTS 原始 y 与 ATD 的 y 方向一致。
- **Metrica Game 1/2**：数据商 README 明确写 `(0,0)` 左上、`(1,1)` 右下。这里保留 CSV 的
  原始 y，不采用 kloppy Metrica CSV loader 的 `y=1-y` 翻转；这样 CSV 两场与 EPTS/ATD 的
  左上、y 向下约定一致。原始 CSV 的 ball/player 坐标与同一场的事件坐标也一致（事件坐标
  使用原始 CSV 坐标）。
- **SkillCorner**：原始数据是米制、球场中心原点、y 从下到上；转换为
  `x=(x+L/2)/L`、`y=(W/2−y)/W`，即左上、y 向下。用 kloppy 的 SkillCorner loader 在
  原始 frame 10 对照，球坐标完全一致（归一化后 `(0.493714, 0.491471)`），确认转换公式与
  kloppy/ATD 的目标坐标系统一致。

半场换边核对（每队所有有限球员 x 的均值）：

| 数据集 | 上半场 H / A 平均 x | 下半场 H / A 平均 x | 是否换边 |
|---|---:|---:|---|
| Game 1 | 0.4735 / 0.6017 | 0.5828 / 0.4583 | 是 |
| Game 2 | 0.5558 / 0.4256 | 0.4204 / 0.5456 | 是 |
| Game 3 | 0.5592 / 0.4237 | 0.4787 / 0.6058 | 是 |
| SkillCorner | 0.5356 / 0.4106 | 0.5077 / 0.6341 | 是 |

四组数据的 H/A 平均 x 差都在上下半场变号；没有按进攻方向翻转坐标，换边来自原始数据本身。

## 5. 弱标签规则

### 5.1 Metrica（三场统一规则）

- **D**：`BALL OUT` 的 `start` 到下一个 `SET PIECE` 的 `start`（左闭右开）。进球
  （`SHOT` subtype 含 `GOAL`）从射门事件 `end+1` 到下一次 `KICK OFF` 的 `start`。
  两个来源的 D 区间合并；事件之间沿用上一支球队。
- **X（犯规/牌窗口）**：`FAULT RECEIVED` 或 `CARD` 之后，若下一个 `SET PIECE` 在固定
  10 s（250 frame）内开始，则事件 `end+1` 到该 `SET PIECE` 的 `start` 之间标 X；否则按
  活球处理（有利原则）。10 s 取调研草案 §3.5 的短窗口，能覆盖几场里约 4–9 s 的清晰
  犯规→重启对，同时把已知的 53.9 s 反例排除在 X 之外。窗口对所有场次、所有半场相同，
  没有按单场调整。
- **X（半场首尾）**：半场开始到第一次 `KICK OFF` 之前；该半场最后一个事件的 `end` 之后。
  没有可用的终场哨事件，因此“终场之后”用最后一个事件结束来近似。
- **H/A**：最近一次 `PASS`、`CARRY`、`RECOVERY`、`SHOT` 或 `SET PIECE` 的球队；事件
  之间沿用该队。`BALL LOST`、`CHALLENGE` 不直接切换球队。
- 优先级：半场首尾的 X 最高；犯规窗口 X 覆盖 D；其余 D 覆盖 H/A。
- `events.csv` 只写出推导用到的类型：上述五类切换事件、`BALL OUT`、`SHOT`、
  `FAULT RECEIVED`、`CARD`。`event` 写成“类型 + subtype”，`t=frame/25`。

### 5.2 SkillCorner

- 一帧落在唯一 phase 内且有球员追踪 → 该 phase 的 `team_in_possession_id`（主队 1802
  → H，客队 871 → A）。
- 一帧不在任何 phase 内 → D。phase 只在球在场上时定义；这类帧即使同时没有球员/球追踪
  也仍是 D，因为数据商已经用 phase 的补集说明它不在活球内。SkillCorner 的 33,480 个
  无球员 frame 绝大多数属于这一类。
- 一帧在唯一 phase 内但没有球员追踪 → X（phase 说活球，坐标无法确认球队）。
- 多个 phase 覆盖同一帧 → X。phase 区间按 `frame_start..frame_end` 闭区间计，连续 phase
  共享端点也算重叠；这是 2,563 个 X frame 的主要来源，并造成 phase 边界处的 X 闪烁。
- `events.csv` 写出所有与半场相交的 phase（start 映射到最近的 25 fps frame），不写
  `dynamic_events`——标签推导没有用后者。

### 5.3 X 的计分

`simulation.evaluate` 原有官方指标 `possession_metrics.evaluate` 本来就不对 GT 为 X 的
帧计分；但 `score_clip` 自己的 `core_wrong_frames` / `clip_wrong_frames` 和
`describe_switches` 原先把 GT X 也算进差异。已做最小修改：错误帧只统计 GT 非 X 的帧，
switch 只在官方 `valid_runs` 内比较，predict 的 X 在 run 内按官方 `fill_abstentions`
处理。`tests/test_external_convert.py` 覆盖“只错在 X 上仍算通过”和“X 帧不增加错误数”。
没有 X 的模拟数据集行为不变。

## 6. SkillCorner 外推位置占比

`is_detected=false` 的球员位置照常保留。按原始 10 fps 的球员-帧计数：

- 上半场 44.91%，下半场 39.35%，合计 **42.09%**（与调研的 42.12% 同量级）。
- 上采样到 25 fps 后，按输出球员-帧计，凡插值任一端为外推即计入：上半场 45.25%，
  下半场 39.66%，合计 **42.42%**。
- 外推位置会产生 12.08 m/s 的最大速度和 61 个 >10 m/s 的样本；P99 仍为 6.00 m/s。

## 7. 算法可运行性（只记录，不解释）

两个现有算法都在四个数据集上跑完并生成 `per_clip.csv` / `report.md`，没有报错。使用已有
实验配置，没有修改算法、配置或已完成实验：

- `20261108_sustained_control_final`（`sustained_control`）
- `20261111_dead_ball_trusted_tags`（`dead_ball_aware`，不传 tags，走无标签坐标分支；
  2026-11-16 同步到 main `38c3fdb` 后重跑）

| 实验 | 数据集 | spellF1 上半/下半 | macroF1 上半/下半 |
|---|---|---:|---:|
| sustained_control | Game 1 | 0.5665 / 0.5529 | 0.7646 / 0.8121 |
| sustained_control | Game 2 | 0.6033 / 0.5503 | 0.8224 / 0.7659 |
| sustained_control | Game 3 | 0.5698 / 0.5021 | 0.7863 / 0.8387 |
| sustained_control | SkillCorner | 0.6108 / 0.6326 | 0.7203 / 0.7519 |
| dead_ball_aware（无标签） | Game 1 | 0.5000 / 0.4883 | 0.6865 / 0.7023 |
| dead_ball_aware（无标签） | Game 2 | 0.5787 / 0.5041 | 0.7587 / 0.6352 |
| dead_ball_aware（无标签） | Game 3 | 0.5358 / 0.5013 | 0.7303 / 0.7788 |
| dead_ball_aware（无标签） | SkillCorner | 0.6194 / 0.6379 | 0.8161 / 0.8212 |

8 个 clip 等权平均的补充诊断（per-class F1 也是先按 clip 算再平均，不是把两半合成一个混淆矩阵）：

| 算法 | spellF1 | macroF1 | alive/dead F1 | H F1 | A F1 | D F1 |
|---|---:|---:|---:|---:|---:|---:|
| sustained_control | 0.574 | 0.783 | 0.897 | 0.819 | 0.780 | 0.749 |
| dead_ball_aware（无标签） | 0.546 | 0.741 | 0.840 | 0.760 | 0.768 | 0.695 |

按数据源平均：

| 算法 | 源 | spellF1 | macroF1 | alive/dead F1 | D F1 |
|---|---|---:|---:|---:|---:|
| sustained_control | Metrica | 0.558 | 0.798 | 0.915 | 0.760 |
| sustained_control | SkillCorner | 0.622 | 0.736 | 0.844 | 0.716 |
| dead_ball_aware（无标签） | Metrica | 0.518 | 0.715 | 0.820 | 0.639 |
| dead_ball_aware（无标签） | SkillCorner | 0.629 | 0.819 | 0.899 | 0.863 |

这些分数只说明链路能跑通。弱标签由不同数据商的事件/phase 推出，和官方 H/A/D 定义不同，
不能与模拟集或官方分数比较，也不能据此选算法或调参。

2026-11-16 同步到 main `38c3fdb`（PR #16 的 merge commit；`git diff d4d7e91..38c3fdb`
为空，代码树与 `d4d7e91` 相同）后，用 `20261111_dead_ball_trusted_tags` 配置重跑了
`dead_ball_aware`；最新提交的 tag ownership 改动只影响传入 tags 的分支，外部数据没有
Smart Tagging 标签，因此上表与同步前 `f5b5d45` 的结果逐项相同。`sustained_control` 代码
没有变化，分数也相同。评分使用同一批 `ext_*` 数据集，未重新生成观测或答案。

## 8. 已知限制

1. **弱标签不是官方真值**。Metrica 没有 `ball_state`/`possession`，SkillCorner phase 与
   possession 在约 14.8% 的重叠帧上不一致；本转换没有解决这个分歧，只按 phase 取球队。
2. **Metrica 事件不完整**：没有换人、伤停、VAR、越位事件，只有少量犯规/牌；`BALL OUT`
   的 `start` 可能偏早，下一次 `SET PIECE` 可能隔很久。10 s 犯规窗口是固定折中，长暂停
   会被当作活球（有利），短于 10 s 但实际不是同一次死球的 set piece 会被标 X。
3. **Metrica H/A 是事件滞后代理**：只取最近一次切换事件，不区分控制、争抢、松散球；
   `BALL LOST`/`CHALLENGE` 被有意忽略。事件覆盖不到的帧沿用上一队，可能把活球/死球
   边界附近标错。
4. **Metrica 1/2 的重复位置**：14/12 列 roster 偶尔给出 12 个有限位置，第 12 个是另一
   槽位的重复坐标；按原始数据保留，不是真实 12 人。槽位映射按球衣号固定到本队槽位，
   不能复现真实 ATD 的同槽换人/身份切换。
5. **缺球不插值**：Metrica 保留原始 NaN；SkillCorner 只在线性插值的两端都有值时补中间，
   任一端缺失保持 NaN。速度用相邻 25 fps 帧差分，SkillCorner 的插值会让速度更平滑；
   外推位置和原始追踪跳变会产生 >10 m/s 的异常，全部保留、没有裁切。
6. **SkillCorner 的边界**：10→25 fps 上采样把标签边界量化到 0.1 s；phase 闭区间共享
   端点被算作重叠，导致每个 phase 边界有 2–3 个 X frame；无球员 frame 全部 NaN；死球
   期间球通常还在，缺球和 D 不能互相替代。
7. **坐标方向是转换约定**：Metrica 1/2 采用 CSV 原始 y（左上、向下），没有采用 kloppy
   Metrica CSV loader 的翻转；这是为了与 EPTS/ATD 一致，不是数据商 CSV 的唯一可能解释。
8. **没有做人工边界审计**（调研任务第 4 项）；没有获取或使用 PFF 数据（第 5 项）。
   Metrica 的许可仍不明确；这些数据集只在本地作为诊断用，不应公开再分发。
9. `core_start=0`、`core_stop=n_frames`：外部数据没有模拟故事的核心窗口，所以“core”就是
   整个 clip；`initiating_team` 填第一个 H/A 标签，仅用于兼容报告；“expected_sequence”
   是弱标签的压缩序列。它们都不是官方窗口或官方先验。

## 9. 复现

```bash
# 转换（固定目录；已存在时加 --force）
.venv/bin/python -m external.convert --source metrica --data-dir "$PWD/data"
.venv/bin/python -m external.convert --source skillcorner --data-dir "$PWD/data"
# 或一次转换全部
.venv/bin/python -m external.convert --source all --data-dir "$PWD/data" --force

# 运行并评分（两个算法 × 四个数据集；示例）
bash scripts/run_simulation.sh 20261108_sustained_control_final ext_metrica_game_3
bash scripts/run_simulation.sh 20261109_dead_ball_tags_final ext_metrica_game_3

# 全部单元测试
.venv/bin/python -m unittest discover -s tests
```

本地 `data/external/SHA256SUMS` 记录原始文件校验值。原始数据和 `outputs/` 下的转换结果、
预测和报告都不进 Git。
