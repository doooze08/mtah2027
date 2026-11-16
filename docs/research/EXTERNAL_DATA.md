# 外部数据作为 H/A/D 测试集的调研

调研日期：2026-11-08。本文只回答“其他比赛的公开跟踪数据能否作为控球算法的真实测试集”，不包含转换代码、算法改动或模拟器改动。所有外部数据放在本机 `data/external/`，该目录被 `.gitignore` 的 `data/*` 规则排除，不进 Git。调研期间没有打开 `data/tactical/`、`data/broadcast/` 下的 BAR-ATH 文件，也没有读取公开答案、评分板或 `evaluation/gt/`。

## 结论摘要

1. **没有任何候选数据源提供与官方定义一致的逐帧 H/A/D 真值。** 外部数据最多提供“弱标签”：由供应商的 possession/ball-state、比赛阶段或事件推导。它可以做格式、缺失、帧率和坐标转换的鲁棒性检查，不能直接当作“真实测试集”替代官方评分。
2. **SkillCorner open data 是当前最可用的公开弱标签源。** 仓库根目录为 MIT 许可，公开可下载；10 fps、105×68 m、归一化坐标、球有 z、有球队/球员 ID、有 `possession` 与 `phases_of_play`。但它是转播计算机视觉追踪，约 42% 的球员观测是外推的；10 fps 与本场 25 fps 不同；phase 球队与 tracking possession 在 14.8% 的重叠帧上不一致；D 的起止仍有秒级不确定性。
3. **Metrica sample-data 最适合做 ATD 格式/缺失鲁棒性检查，不适合做 H/A/D 标签测试。** Game 3 是 EPTS，和本场 ATD 同格式、25 fps、0–1 坐标、105×68 m；但 `ball_z` 全为空、没有速度、没有 possession/ball-state，球缺失 32.2%（Game 1/2 为 39.1%/41.0%）。事件数据可推部分 D，但犯规/牌/换人/越位等不完备，按“下一次 set piece”推 D 会明显高估。
4. **PFF FC（现 Gradient Sports）2022 世界杯 64 场在技术上是最强的候选，但当前不能作为公开数据使用。** 官方博客说 64 场、广播追踪 + 事件 + 评分，免费申请；但当前 Gradient 页面只找到 Klaviyo newsletter 表单，`fc.pff.com/docs` 返回 HTTP 530，未找到数据集专属许可。kloppy 3.18.0 的 PFF loader 和其公开测试夹具显示数据有 29.97 fps、球 z、`ball_state`、`ball_owning_team_id`、`game_event`（含 OUT/SUB/END 等），技术上可直接推 H/A/D；但在拿到书面许可前不应使用。
5. **推荐顺序：** SkillCorner 一场做弱标签外部 sanity；Metrica Game 3 做 ATD 格式/缺失测试；PFF 暂排除，除非组织方拿到明确许可；StatsBomb 等只有事件的公开集不适合作为 ATD 测试集。
6. **补充检验（第 11 节）：** Metrica 三场分别有 155/169/160 段缺球，中位 5.1–7.8 s，58/58/72 段落在 5–30 s；98.6–99.3% 的缺球帧至少一端锚定在停顿/重启事件，起止多在 1 帧（0.04 s）内。没有确认的活球长段缺失。SkillCorner 的 54 段缺球全部是无球员的整段跟踪缺口（3 段活球 >5 s），不能支持“只移除球”；PFF 64 场无法验证换人。

## 1. 判定口径

### 1.1 官方 H/A/D 的含义

根目录 [CHALLENGE.md](../../CHALLENGE.md) 和 [EVALUATION.md](../../EVALUATION.md) 的定义：

- `H`：主队活球控球；`A`：客队活球控球；`D`：死球；`X`：放弃判断。
- 活球时，争抢和松散球保留上一支实际控制球队；不能把“最近球员”直接等同于控制权。
- 一个 possession 是同一球队 `H/A` 的最大连续段；`D` 是停表，不是 possession。
- 官方标签由 corrected tracking 机械导出：corrected tracking 标为 ball dead 的帧是 `D`，否则取 tracking 指定的控球球队（[CHALLENGE.md](../../CHALLENGE.md) 的 “The ground truth is derived from corrected tracking data” 一段）。
- `X` 是“不回答”，不是第四种比赛状态；外部数据没有 abstention 标签，因此**无法从任何外部数据推导 `X`**。

这决定了外部数据的上限：即使供应商有 `possession` 或 `ball_state`，它也不是官方 corrected tracking 的 dead/owning 字段。两者可能接近，但不能假定等价。

### 1.2 “公开可得”和“许可允许”

本文把两件事分开：

- **公开可得**：无需私人关系即可下载，或至少可通过公开、免费的注册/申请表获取。
- **许可允许**：有明确条款允许比赛用途、研究/评估用途，并允许组织方检查和复现。

“组织方可获取”按 [RULES.md](../../RULES.md) 的“organisers can access and inspect”理解；仅有公开博客介绍、但没有可下载数据或可核实的许可，不算满足。

### 1.3 什么是“真实测试集”

本文只把“有逐帧标签、且标签定义与官方 H/A/D 足够接近”的数据称为真实测试集。外部数据若只有供应商 possession/phase，应称为**弱标签外部集**。用弱标签算出的 macroF1/spellF1 只能作为诊断，不能与本场官方分数比较，也不能用来调本场参数。

## 2. 总表

| 数据源 | 公开可得 | 许可 | 场次/时长 | fps | 球 z | 球缺失 | 追踪方式 | 事件 | H/A/D 结论 |
|---|---|---|---|---|---|---|---|---|---|
| Metrica sample-data | 是，GitHub 直接下载 | **无明确 LICENSE**；README 只要求署名和“responsible use” | 3 场，约 94–97 min/场 | 25 | Game 3 有列但全 NaN；Game 1/2 无 | Game 3 32.2%；Game 1 39.1%；Game 2 41.0% | Game 3 元数据写 Optical；CSV 场未注明 | 1,745–3,620 条/场，25 fps 对齐 | 可做格式/缺失测试；H/A/D 标签不可靠 |
| SkillCorner open data | 是，GitHub 直接下载 | **MIT**（仓库根 LICENSE）；README 要求 credit；无独立数据许可 | README 说 10 场；仓库现有 20 个 match 目录，跟踪 LFS 合计 1.82 GB | 10 | 有；全场 78.2% 有值，活球 97.9% 有值 | 全场 21.8%；活球 1.5% | 转播计算机视觉，42.1% 球员观测为外推 | 483 个 phase + 5,222 条 dynamic events，10 fps 对齐 | **当前最佳弱标签源**；不是官方真值 |
| PFF FC / Gradient 2022 WC | **有条件**：博客说免费填表；当前页面未找到数据集表单，docs 530 | **未找到数据集许可**；存档条款是 API Sandbox 协议，限制严格 | 64 场 | 29.97（kloppy 测试夹具实测；官方博客未写） | 有（夹具与 loader 均支持） | 未知（夹具仅 200 帧，不能代表全场） | 广播追踪 | 事件 + play-by-play 评分；格式由 kloppy loader 确认 | 技术最强，但当前不可合法/可复核地作为公开测试集 |
| StatsBomb open data | 是 | 未核实（事件数据） | 多场 | 无跟踪 | 无 | n/a | 事件 only | 丰富 | 只有事件，无法生成 46 槽位逐帧表，排除 |

表中 Metrica/SkillCorner 的数字是本次实测；PFF 的 29.97 fps、球 z、`ball_state` 来自 kloppy 3.18.0 的公开测试夹具与 loader，不是 64 场数据实测，不能代表 64 场的 fps/缺失率/事件精度。

## 3. Metrica Sports sample-data

### 3.1 许可与可得性

仓库：[metrica-sports/sample-data](https://github.com/metrica-sports/sample-data)。数据可直接 `curl`/`git clone`，属于公开可得。

但仓库**没有 LICENSE 文件**，GitHub API 的 `license` 字段也是 `null`（实测）。[README](https://raw.githubusercontent.com/metrica-sports/sample-data/master/README.md) 的 “Legal stuff” 原文只有：

> Please be responsible with the use of this data. If you use it for anything public, please aknowledge the source.

这不是一个完整的开源许可，只表达了“负责使用、公开使用时署名”的请求。[Metrica 网站的通用条款](https://www.metrica-sports.com/terms-conditions)第 6 节又写：

> All content, trademarks, logos, and software provided by Metrica Sports BV remain our exclusive property. You may not copy, distribute, or modify our content without explicit permission.

该条款是否覆盖 GitHub sample-data 并不明确；它更像是网站/服务条款。**结论：公开可得，但许可是否允许本项目的使用与再分发不明确。** 如果要把 Metrica 数据写进技术文档并让组织方复核，建议先向 Metrica 或组织方确认；不要自行把它标成 CC BY 或其他开放许可。

### 3.2 规模与格式

三场都是 105×68 m，坐标为 0–1（README 明确说 (0,0) 左上、(1,1) 右下、(0.5,0.5) 开球点）。Game 3 元数据写 `TrackingType=Optical`、`ProviderName=Metrica Sports`、`FrameRate=25`。

| 场次 | 帧数 | 时长（25 fps） | 球员列 | 球缺失 | 球 z | 事件数 |
|---|---:|---:|---|---:|---|---:|
| Game 1 CSV | 145,006 | 96.7 min | 14/队，11 人在场 | 39.14% | 无 | 1,745 |
| Game 2 CSV | 141,156 | 94.1 min | 14/队，11 人在场 | 41.01% | 无 | 1,935 |
| Game 3 EPTS | 143,761 | 95.8 min | 35 人名单，22 人在场 | 32.22% | 列存在，0 个非空 | 3,620 |

Game 1/2 的 CSV 每队有 14 个 player 列，但每帧只有 11 个有限位置（偶尔 12 个，可能是重复检测）；这说明列里包含替补/未上场球员。Game 3 的 35 个 player 列中，每帧恰好 22 个有限位置。

### 3.3 内容与质量

**实测（kloppy 3.18.0，Game 3 全量）**：

- 143,761 行，149 列；25 fps；105×68 m；0–1 坐标。
- 35 个球员列，22 人在场；球队 `Team A`/`Team B`，球员 ID `P3578` 等，球衣号存在。
- `ball_x`/`ball_y` 缺失 46,325 帧，32.22%；`ball_z` 列存在但 0 个非空；`ball_speed` 0 个非空。
- `ball_state` 全部为 `None`；`ball_owning_team_id` 全部为 `None`。
- 35 个球员的 `_s`（速度）和 `_d`（距离）全部为空。也就是说，Metrica EPTS 只有位置，没有本场 ATD 那样的速度列；速度必须由位置差分。

Game 1/2 的 CSV 同样没有 z、没有速度；球缺失约四成。三场的球缺失为 32–41%，与本场 ATD 的 43.06% 总量、41% graded 同一量级；Game 1/2 接近本场，Game 3 略低（[DATA.md](../../DATA.md)）。所以**在“球经常缺失”这一点上比 SkillCorner 更接近本场难度**。

### 3.4 事件数据

Game 3 原始 JSON 有 3,620 条事件，类型如下（**实测**）：

| 类型 | 数量 | 说明 |
|---|---:|---|
| CARRY | 1,395 | 带球 |
| PASS | 1,121 | 传球 |
| CHALLENGE | 335 | 对抗，含 GROUND/AERIAL、WON/LOST、FAULT |
| RECOVERY | 294 | 夺回球权 |
| BALL LOST | 288 | 失去球权 |
| SET PIECE | 90 | KICK OFF、THROW IN、FREE KICK、CORNER KICK 等 |
| BALL OUT | 64 | 球出界 |
| SHOT | 20 | 射门，含 ON TARGET/GOAL |
| FAULT RECEIVED | 12 | 被犯规 |
| CARD | 1 | 黄牌 |

事件与跟踪帧对齐：Game 3 的 `start.frame`/`end.frame` 直接是 25 fps 帧号，`start.time` 精确到 0.01 s；例如第一个 `SET PIECE KICK OFF` 在 frame 361、time 14.44 s。Game 1/2 的事件也有 `Start Frame`/`End Frame`，25 fps 对齐。

**事件覆盖明显不完整**：Game 3 只有 12 次 `FAULT RECEIVED`、1 张牌，且没有 `SUBSTITUTION`、`OFFSIDE`、`VAR`、`INJURY` 等类型。不能假定所有死球原因都记录在事件里。Game 1/2 的 `FAULT RECEIVED` 为 22/20，`CARD` 为 4/6，数量也不高；不能把事件表当作完整比赛事件流。

### 3.5 能否推出 H/A/D

**D 的草案**：

1. `BALL OUT` 的 `start.frame` 作为 D 起点；下一条 `SET PIECE` 的 `start.frame - 1` 作为 D 终点。
2. `FAULT RECEIVED` 后，仅当在短窗口（例如 10 s）内出现 `SET PIECE`，才把这段当 D；否则视为 advantage/活球。
3. `CARD` 同理，只有紧接 `SET PIECE` 才当 D。
4. `SHOT` 的 `ON TARGET|GOAL` 后，到下一次 `KICK OFF` 前当 D。
5. 合并重叠区间。

**实测的问题**：

- 只按 `BALL OUT` 推，D 覆盖 34,671 帧，占 143,761 的 24.1%；这个量级看似合理，但 64 次出界中有 60 个合并区间，边界仍依赖“下一次 set piece”。
- 按“犯规→下一次 set piece”推，会严重高估：例如 frame 4481 的 `FAULT RECEIVED`，下一次 `SET PIECE` 在 5829，相隔 1,348 帧（53.9 s）；中间有大量 pass/carry，实际不可能是同一次死球。原因是事件没有 advantage/哨声信息。
- 黄牌同理：frame 105378 的 `CARD`，下一次 `SET PIECE` 在 106000，相隔 622 帧（24.9 s），不能直接当 D。
- `BALL OUT` 的 `start` 更像“最后触球/球开始出界”，不一定是球完全出界的瞬间；D 起点可能偏早。
- 没有换人、伤停、VAR、越位事件，无法覆盖这些死球原因。

**H/A 的草案**：

- 事件区间（PASS/CARRY/RECOVERY/BALL LOST/CHALLENGE/SHOT）覆盖 66.0% 的帧；可以用事件 `team` 做基础标签，但 `BALL LOST` 的 `team` 是丢球方而不是之后的控球方，`CHALLENGE` 的 WON/LOST 也不能直接等同于控球。
- 事件之间约 34% 的帧没有覆盖，需要靠 tracking 的最近球员/滞后规则补，或保留上一标签；这正是官方定义里最模糊的“controlled possession/争抢/松散球”部分。
- 没有 `ball_state`、没有 `possession`，无法直接得到“活球/死球”或“控球球队”。

**结论：Metrica 不适合作为 H/A/D 标签测试集。** 它适合回答“转换后能不能跑、缺失怎么处理、25 fps/0–1 坐标/46 槽位是否兼容”；D 只能做粗粒度事件窗口，H/A 只能做弱代理。

### 3.6 转成 ATD 宽表的难点

- **槽位**：ATD 是 46 个槽位（24 H/22 A），Metrica Game 3 是 35 个带稳定 ID 的球员（22 人在场），Game 1/2 是 14/队。需要把球员映射到槽位，未使用槽位填 NaN；ATD 的槽位不是稳定身份，外部数据的稳定 ID 反而不能复现“同槽换人/身份切换”的噪声。
- **坐标**：Metrica 已是 0–1、左上原点，和 ATD 接近；但仍要确认主队方向、半场是否翻转、以及 105×68 与 ATD 元信息的 0.3 m 差异。
- **帧率**：25 fps 与 ATD 相同，是最省事的一点；但 Game 3 的 `timestamp` 在 kloppy 里按 period 重置，不能直接拿 timestamp 当全局时间。
- **缺失**：球缺失 32–41%，球员位置也有缺失；ATD 允许 NaN，转换时应保留 NaN，不要插值后再当“真实观测”。
- **速度**：外部没有 `_s`；必须位置差分并决定平滑方式。ATD 的速度来自原始导出，二者误差分布不同。
- **z**：Game 3 的 `ball_z` 全空；ATD 也不含 z。转换时直接丢弃即可，但不能声称外部数据测试了 z。
- **事件**：ATD 141 列不含事件；事件只能用于生成弱标签或元数据，不能塞进 `predict` 的观测。

### 3.7 kloppy 实测

命令（在仓库根目录，使用现有 `.venv`，kloppy 3.18.0）：

```bash
.venv/bin/python - <<'PY'
from kloppy import metrica
base = "data/external/metrica/Sample_Game_3"
ds = metrica.load_tracking_epts(
    meta_data=f"{base}/Sample_Game_3_metadata.xml",
    raw_data=f"{base}/Sample_Game_3_tracking.txt",
)
df = ds.to_df(engine="pandas")
print(len(df), df.shape, ds.metadata.frame_rate, ds.metadata.pitch_dimensions)
print(df.ball_x.isna().mean(), df.ball_z.notna().sum())
PY
```

结果（**实测**）：加载 14.65 s；143,761 行、149 列；25 fps；105×68 m；35 个球员列、每帧 22 人在场；`ball_x` 缺失 46,325（32.22%）；`ball_z` 非空 0；`ball_state`/`ball_owning_team_id` 全为 `None`；35 个 `_s` 与 35 个 `_d` 全为空。

事件侧：`metrica.load_event` 能加载 3,594 条，但会把 `SET PIECE`/`BALL LOST`/`CARD` 等折叠成 `generic`（336 条）；做事件类型统计应直接读原始 JSON 的 3,620 条，而不是只用 kloppy 的 `event_type`。

## 4. SkillCorner open data

### 4.1 许可与可得性

仓库：[SkillCorner/opendata](https://github.com/SkillCorner/opendata)。根目录 [LICENSE](https://raw.githubusercontent.com/SkillCorner/opendata/master/LICENSE) 是 MIT：

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies …

[README](https://raw.githubusercontent.com/SkillCorner/opendata/master/README.md) 说明数据是 SkillCorner 与 PySport 联合开源的，并写：

> if you use the data, we kindly ask that you credit SkillCorner

**结论：公开可得；仓库级 MIT 是三个候选里最明确的许可。** 需要保留版权/许可声明并署名 SkillCorner。严格说 MIT 文本写的是 “Software”，仓库没有单独的数据许可；数据覆盖是否 100% 由 MIT 授权并非毫无歧义，但这是目前最可用的公开许可。若用于公开提交，建议在技术文档中写明来源、MIT 许可和署名。

### 4.2 规模与格式

README 写“10 matches”；但仓库当前 `data/matches.json` 和 `data/matches/` 有 **20 个 match 目录**（19 个 `closed`、1 个 `not_started`），跟踪 LFS 合计 1.82 GB。数量以仓库现状为准，README 的 10 场已过时/不完整。本次只下载并检查了 `1925299`（Brisbane Roar vs Perth Glory，2024-12-21）。

| 项目 | 实测/原文 |
|---|---|
| 单场帧数 | 61,301 原始帧（kloppy 61,282 行，19 帧 period 为空被丢弃） |
| 时长 | 102.17 min；period 1 50.38 min，period 2 51.75 min |
| fps | 10 |
| 坐标 | 原始为米、球场中心为原点；kloppy 默认转成 0–1 |
| 球场 | 105×68 m（`match.json` 的 `pitch_length`/`pitch_width`） |
| 球员 | 36 人名单，18/队；每帧 22 人在场 |
| 追踪方式 | 转播视频计算机视觉；文件名为 `tracking_extrapolated` |
| 身份 | 有稳定 `player_id`、球衣号、球队 |

### 4.3 内容与质量

**实测（单场 `1925299`，kloppy `only_alive=False, include_empty_frames=True`）**：

- 61,282 行、137 列；10 fps；105×68 m；0–1 坐标。
- 球有 x/y/z：全场 `ball_z` 缺失 13,576（22.15%），活球帧缺失 734（2.06%）；活球 z 范围 −0.12..13.33 m。z 有负值和异常高值，不能当作精确高度。
- 球缺失：全场 13,349（21.78%）；**活球帧只有 531（1.49%）**。这与本场 ATD 的 41% graded 球缺失差别很大；SkillCorner 的活球球跟踪明显更容易。
- 球员观测 1,054,724 个，其中 444,267 个是外推（42.12%）；5,335 帧所有球员都是外推。`is_detected` 标志可区分，但外推位置不是真实检测。
- 没有速度/距离列（`_s`/`_d` 全空）；需要位置差分。
- `possession` 是 dict：`group` 为 `home team`/`away team`/null，`player_id` 多数为空；`ball_state` 和 `ball_owning_team_id` 由 kloppy 根据 possession 生成。
- 球队/球员 ID 稳定：主队 1802、客队 871；球员如 `51050`、`333110`；比 ATD 的 46 个匿名槽位信息更多。

### 4.4 事件与 phase

SkillCorner 不是传统的 Opta/StatsBomb 事件流。它提供：

- `phases_of_play.csv`：483 个 phase；只在球在场上时定义；字段包括 `frame_start`、`frame_end`、`period`、`team_in_possession_id`、`team_in_possession_shortname`、`team_in_possession_phase_type`（`build_up`/`create`/`finish`/`chaotic`/`direct`/`set_play` 等）。README 明确说：“Phases of play are only defined when the ball is in play. When the ball is out of play there is no phase of play.”
- `dynamic_events.csv`：5,222 行、322 列；四类 `event_type`：`passing_option` 2,734、`player_possession` 1,054、`on_ball_engagement` 936、`off_ball_run` 498。`event_subtype` 有 pressure、pressing、recovery_press、run_ahead_of_the_ball 等；还有 `game_interruption_before/after`（throw_in、free_kick、goal_kick、corner、goal）等字段。
- 没有 `foul`、`card`、`substitution`、`offside` 这类传统事件类型；`match.json` 有球员黄/红牌、上下场时间，但不是逐帧事件。
- 时间是 0.1 s 精度，`frame_start`/`frame_end` 与 10 fps 跟踪帧对齐；`phases` 的 start/end 也是帧号。
- `dynamic_events` 的 x/y 是米制、未按标准球场缩放（README 明确提醒需要调整）；不要直接当 0–1 坐标。

### 4.5 能否推出 H/A/D

**规则草案（推荐）**：

1. 以 `phases_of_play` 为主：若帧落在唯一 phase 内，`H/A` 取该 phase 的 `team_in_possession_shortname`（1802→H，871→A）。
2. 若帧不在任何 phase 内，标 `D`。
3. 若多个 phase 重叠（实测 384 帧重叠），取 `frame_start` 更晚的 phase，或标为“边界不确定”；不要静默取任意一个。
4. `possession.group` 只作为交叉检查/补充：若帧在 phase 外、但球和 22 名球员都在、且 possession 连续存在，说明可能是 phase 未覆盖的活球段；应单独标记，不要直接当 D。若帧在 phase 内但 possession 为 null，保留 phase 球队但降低置信度。
5. 争抢/松散球没有官方“上一支实际控制球队”的标签；phase 球队在 `chaotic`/`transition` 段可能快速切换，不能只靠最近球员或 phase 边界。

**实测的差异与量级**：

| 指标 | 数值 | 含义 |
|---|---:|---|
| phase 总帧数（含重叠） | 36,210 | 483 个 phase 的 `frame_end-frame_start+1` 之和 |
| phase 并集帧数 | 35,826 | 实际被至少一个 phase 覆盖 |
| phase 外帧数 | 25,465 | 若按“phase 外=D”，占 61,282 的 41.5% |
| possession 非空帧 | 35,589 | `home` 22,367 + `away` 13,222 |
| phase 内但 possession 为空 | 1,461 | 4.1% 的 phase 帧；不能直接给 H/A |
| phase 内但无球员/无球 | 649 | 1.8% 的 phase 帧；可能是转播切换/遮挡 |
| phase 外但 possession 非空 | 1,224 | 其中 1,013 帧球和球员都在，可能是 phase 未覆盖的活球段 |
| phase 与 possession 球队不一致 | 5,093 / 34,365 | 14.8% 的重叠帧；41.2% 在边界 1 s 内，65.8% 在 2 s 内，89.9% 在 5 s 内 |
| possession H/A spell 数 | 335 | 平均 10.62 s |
| phase H/A spell 数 | 257 | 平均 13.94 s |

注：phase 并集 35,826 中有 9 帧属于跨半场 phase（`period` 为空），所以按 period 1/2 的补集是 25,465，而 61,282−35,826=25,456；差 9 帧是 period 空值。这个跨半场 phase 本身也说明 phase 边界不能直接当官方半场边界。

官方公开样例是 5 分钟 17 个 possession、平均 14.2 s（[DATA.md](../../DATA.md)）。SkillCorner 的 phase 平均 13.94 s 更接近这个尺度，possession 平均 10.62 s 更碎；但这只是量级对照，不能证明哪一种更接近官方标签。**结论：SkillCorner 可以生成“弱 H/A/D”，phase 版本比 possession 版本更适合做 possession 段；但 14.8% 的球队不一致、1,461 个 phase 内无 possession、1,013 帧 phase 外有球+球员，说明它不是官方真值。**

### 4.6 转成 ATD 宽表的难点

- **帧率**：10 fps → 25 fps，需要 2.5 倍上采样；保持/线性插值/最近邻会改变球和球员速度，影响控球判断。事件/phase 标签也要从 10 fps 映射到 25 fps，边界会放大到 2–3 帧。
- **槽位**：36 人名单、22 人在场，需要映射到 46 槽位；外部有稳定 player_id，ATD 槽位没有身份，二者语义不同。未使用槽位填 NaN。
- **坐标**：原始米制、中心原点；要转成 0–1、左上原点，并确认主队方向/半场翻转。`dynamic_events` 的 x/y 还要按球场尺寸单独缩放。
- **缺失**：活球球缺失只有 1.5%，远低于 ATD 的 41%；如果直接用，会低估本场最核心的缺失困难。全场 21.8% 的缺失主要来自无球员的 13,359 帧（转播切换/死球），不能简单当“球被遮挡”。
- **速度**：无 `_s`，必须差分；外推位置会产生不真实的速度/加速度。
- **z**：球有 z，但 ATD 没有 z；转换时丢弃，不能用来测试 z 相关逻辑。
- **标签**：phase/possession 只应作为外部弱标签，不能写入 ATD 的 141 列观测；观测与标签必须分离。

### 4.7 kloppy 实测

```bash
.venv/bin/python - <<'PY'
from kloppy import skillcorner
base = "data/external/skillcorner/1925299"
ds = skillcorner.load(
    meta_data=f"{base}/1925299_match.json",
    raw_data=f"{base}/1925299_tracking_extrapolated.jsonl",
    only_alive=False,
    include_empty_frames=True,
)
df = ds.to_df(engine="pandas")
print(len(df), ds.metadata.frame_rate, df.ball_state.value_counts().to_dict())
print(df.ball_x.isna().mean(), df.ball_z.isna().mean())
PY
```

结果（**实测**）：61,282 行、137 列；10 fps；105×68 m；36 个球员列、22 人在场；`alive` 35,589、`dead` 25,693；球缺失 13,349（21.78%）；活球球缺失 531（1.49%）；活球 z 缺失 734（2.06%）；没有速度列；加载 23.03 s。

`only_alive=True`（kloppy 默认）会丢掉 25,693 个 dead 帧，只剩 35,589 行，球缺失 1.49%。**要保留 D 必须显式设 `only_alive=False`，并建议 `include_empty_frames=True`。**

## 5. PFF FC / Gradient Sports 2022 世界杯

### 5.1 许可与可得性

官方发布页：

- 2024-09-12：[PFF FC 2022 World Cup Dataset Now Available](https://www.blog.fc.pff.com/blog/pff-fc-release-2022-world-cup-data)
- 2025-02-13：[Enhanced 2022 World Cup Dataset](https://www.blog.fc.pff.com/blog/enhanced-2022-world-cup-dataset)
- 现品牌页：[Gradient 2024](https://www.gradientsports.com/blog/pff-fc-release-2022-world-cup-data)、[Gradient 2025](https://www.gradientsports.com/blog/enhanced-2022-world-cup-dataset)
- 品牌历史：[PFF FC → Gradient](https://www.gradientsports.com/our-history)

博客原文说 64 场、广播追踪 + 事件 + play-by-play 评分，跟踪文件为 `{game_id}.jsonl.bz2`，事件为 `events.json`，元数据包括 `metadata.csv`、`players.csv`、`rosters.csv`、`competitions.csv`；获取方式是：

> Simply fill out the form below to gain instant access to this invaluable dataset.

**但当前可核实性很差（实测，2026-11-08）**：

- `https://fc.pff.com/docs` 和 `https://fc.pff.com/` 都返回 HTTP 530。
- 当前 Gradient 页面正文仍写“fill out the form below”，但抓取到的 HTML 里只有一个 Klaviyo newsletter 表单（`klaviyo-form-TNUsYL`），没有数据集申请表；也没有数据下载链接。
- 没有找到 2022 World Cup 数据集专属的许可/条款页。能存档到的 PFF 条款是 2022 年的 **PFF API Sandbox Environment User Agreement**（[Wayback 存档](https://web.archive.org/web/20250713012512/https://fc.pff.com/terms)），其中写：
  > The Sandbox and the data contained in the Sandbox may only be used for testing purposes …
  >
  > No rights are granted to you hereunder other than as expressly set forth herein.
  这不是世界杯数据集的明确许可，但它是目前能找到的唯一 PFF 数据条款，且限制很强（仅测试、无再分发、保密）。不能据此推断世界杯数据可用，也不能据此推断它不可用；需要 PFF/Gradient 的书面说明。

**结论：PFF 在“公开可得”上是有条件的，在“许可允许”上未解决。** 没有填表（避免提交个人信息，也避免在条款不明时获取数据），没有下载 64 场数据。当前不能把它作为公开测试集。

### 5.2 技术格式：kloppy loader 与公开测试夹具

虽然没有 64 场数据，kloppy 3.18.0 的 [PFF loader](https://github.com/PySport/kloppy/blob/v3.18.0/kloppy/infra/serializers/tracking/pff.py) 和其公开测试夹具可以确认格式（**实测/代码证据**）：

- `kloppy.pff.load_tracking(meta_data, roster_meta_data, raw_data, only_alive=...)`。
- 原始 JSONL 字段：`frameNum`、`period`、`periodElapsedTime`、`ballsSmoothed`（x/y/z）、`homePlayersSmoothed`/`awayPlayersSmoothed`（jerseyNum、x、y）、`game_event`。
- `game_event.game_event_type` 含 `FIRSTKICKOFF`、`SECONDKICKOFF`、`END`、`OUT`、`SUB`、`OTB`、`VID`、`OFF`、`ON`、`G`（stays in play）等；`game_event.home_ball` 给出球权方。
- 元数据含 `fps`、`stadium.pitches[0].width/length`、`homeTeam`/`awayTeam`；roster 元数据含球员 ID、昵称、球衣号、位置。
- kloppy 根据 `game_event` 维护 `ball_state`（OUT/END→dead；KICKOFF/OTB→alive）和 `ball_owning_team`；`only_alive=True` 会丢掉 dead 帧。**这意味着 PFF 数据在技术上可以直接给出 H/A/D，而不需要像 Metrica 那样从事件反推。**

kloppy 自带的公开测试夹具（game 10517，2022-12-18，阿根廷 vs 法国）实测：

- 200 帧（每半场/加时首尾各 25 帧的抽样，不是完整比赛）。
- 29.97 fps；4 个 period（含加时）；105×68 m；0–1 坐标。
- 50 人 roster；35 个球员列；球 z 存在，范围 0.00–2.88 m；200 帧中 52 帧球缺失（26%，这是稀疏抽样，不能代表全场缺失率）。
- `ball_state`：199 alive、1 dead；`ball_owning_team_id`：主/客各 100 帧。
- 没有速度/距离列。
- 加载命令与结果见 §10.3。

**这个夹具只能证明格式和 loader 可用，不是 2022 世界杯 64 场数据，也不能用于估计全场规模/缺失率。**

### 5.3 规模与内容（官方博客 + 格式推断）

| 项目 | 结论 |
|---|---|
| 场次 | 64 场（2022 世界杯） |
| fps | 官方博客未写；kloppy 夹具 29.97 fps，loader 从 metadata 读取 `fps`；可推断约 30 Hz，待 64 场数据确认 |
| 坐标 | loader 按 stadium pitch 尺寸转换；具体原始坐标未实测 |
| 球场 | 从 `stadium.pitches[0]` 读取，可能因球场而异 |
| 球 z | 有（`ballsSmoothed.z`；夹具 0–2.88 m） |
| 球员身份/球队 | 有（roster：player id、nickname、shirt number、position） |
| 追踪方式 | 广播追踪（官方称 broadcast tracking） |
| 事件 | 有事件 + play-by-play 评分；事件类型/时间精度未公开规格，未实测 |
| 球缺失 | 未知；夹具 26% 但为稀疏抽样，不能代表全场 |

### 5.4 能否推出 H/A/D

**技术上最直接**：

- `H/A`：当 `ball_state == alive` 且 `ball_owning_team_id` 非空时，取该球队；`ball_owning_team_id` 在 dead 帧也可能保留，必须用 `ball_state` 门控。
- `D`：`ball_state == dead`。`game_event` 的 `OUT`/`END` 进入 dead，`FIRSTKICKOFF`/`SECONDKICKOFF`/`OTB` 进入 alive；`SUB`/`OFF`/`ON` 发生在死球期，`VID`（视频缺失）需要单独处理。
- 争抢/松散球：`home_ball` 是供应商的球权判断，不等于官方“controlled possession”；需要看 `OTB`/`game_event` 的语义。
- 犯规/停表：`OUT` 和 `END` 只给死球状态，不给“哪次犯规、何时哨响”；`SUB`/`VID` 也不等于官方 D 的起止。
- 加时：夹具是 4 个 period；ATD 只有两个半场；需要把 3/4 period 映射或排除。

**与官方定义的不一致**：

- 官方 D 是 corrected tracking 的 ball dead；PFF `ball_state` 是供应商的 game_event 状态，边界可能不同。
- 官方在死球时丢弃球权；PFF `ball_owning_team_id` 在 dead 帧仍可能有值，不能直接当 H/A。
- `VID`（视频缺失）可能是活球但无画面，官方可能标 D 或 X；外部没有 `X`。
- `SUB`/`OFF`/`ON` 是死球事件，但官方 D 的起止仍以 corrected tracking 为准；不能用事件时间直接替代。

**结论：如果拿到有明确许可的 PFF 数据，它比 SkillCorner 更接近“可直接推 H/A/D”的理想源；但当前没有数据、没有许可，不能使用。**

### 5.5 转成 ATD 宽表的难点

- 30 Hz → 25 Hz 下采样；PFF 的 29.97 不是整数，帧号/时间映射需要小心。
- 50 人 roster → 46 槽位；PFF 有稳定 player id，ATD 槽位无身份；映射语义不同。
- 原始坐标经 loader 转 0–1；仍需确认方向/半场翻转。
- 4 个 period（含加时）→ ATD 两个半场；需要排除或映射加时。
- 球 z 有值但 ATD 无 z；转换时丢弃。
- 速度/距离没有；需要差分。
- 事件/评分不在 ATD 141 列内；只能用于弱标签。
- 64 场的数据量、许可和缺失率都未知；不能先写转换。

## 6. 其他候选

- **StatsBomb open data**（[GitHub](https://github.com/statsbomb/open-data)）：公开事件数据丰富，但没有逐帧球/球员跟踪，无法生成 ATD 的 141 列；不适合作为本任务的测试集。
- **Signality/Hammarby 3 场、Last Row 19 球**：Metrica README 的 “Other tracking data sources” 提到它们；样本小、无事件或不同步，不能覆盖 D/H/A 的完整比赛，排除。
- 其他公开集（DFL、SoccerNet 等）本次未展开核实；在未确认有完整 22 人 + 球逐帧跟踪和明确许可前，不作为候选。

## 7. H/A/D 推导规则草案（跨源）

### 7.1 分源草案

| 源 | H/A 草案 | D 草案 | 主要问题 |
|---|---|---|---|
| Metrica | 事件 `team` 基础 + tracking 最近球员/滞后；`BALL LOST`/`RECOVERY` 用于切换；争抢保留上一队 | `BALL OUT`→下一次 `SET PIECE`；`FAULT`/`CARD` 仅在短窗口内有 set piece 时算 D；进球→下一次 kickoff | 事件不完整；advantage；下一次 set piece 可能隔 50 s；无 possession/ball_state |
| SkillCorner | phase 的 `team_in_possession_shortname`；重叠取更晚 phase；phase 内无 possession 时保留但降置信度 | phase 外=D；phase 外但有球+球员+possession 时单独标记，不直接当 D | phase 与 possession 14.8% 不一致；649 个 phase 内无球员；1,013 帧 phase 外有球+球员；无犯规/换人事件 |
| PFF | `ball_state=alive` 且 `ball_owning_team_id` 非空；`home_ball` 仅作交叉检查 | `ball_state=dead`；`OUT`/`END` 进入 dead，`KICKOFF`/`OTB` 进入 alive；`VID`/`SUB` 单独处理 | 无数据/许可；`VID` 语义；dead 帧仍有 ball owning；加时 4 period |

### 7.2 与官方定义不一致或无法确定的地方

1. **“controlled possession”**：官方要求“控制”，外部只有 phase/possession/ball owning 的供应商判断；争抢、松散球、折射、空中对抗没有统一代理。SkillCorner 的 phase 球队在 `chaotic`/`transition` 段可能快速切换；Metrica 的 `CHALLENGE` WON/LOST 也不等于控制。
2. **争抢归属**：官方规则是“保留上一支实际控制球队”；外部数据没有“上一支实际控制球队”的显式字段，只能靠相位/滞后；不同实现会给出不同 H/A。
3. **D 的起点**：球出界是“最后触球”“球完全过线”还是“裁判哨响”？Metrica `BALL OUT.start` 更像最后触球；SkillCorner phase 结束是供应商的 in-play 边界；PFF `OUT` 是 game_event。三者都可能与官方 corrected tracking 的 dead 起点差几帧到几秒。
4. **D 的终点**：下一次 set piece 的 `start` 不一定是裁判允许重启的瞬间；快发、延迟重启、换人/伤停/VAR 都会改变边界。
5. **犯规停表**：Metrica 没有 advantage/哨声；`FAULT RECEIVED` 后下一次 set piece 可能隔 54 s（实测 frame 4481→5829），直接当 D 会错。SkillCorner 没有 foul 事件；PFF 的 `game_event` 只确认 `OUT`/`SUB`/`END` 等，犯规细节未公开规格。
6. **换人/伤停/VAR**：Metrica 没有 substitution/VAR/injury 事件；SkillCorner 只有 match.json 的上下场时间与牌，没有逐帧事件；PFF 有 `SUB`/`VID`，但 `VID` 可能是活球无画面，官方可能标 D 或 X。
7. **球出界/进球/越位/角球/任意球**：Metrica 有 `BALL OUT`/`SET PIECE`/`SHOT`，但无 offside；SkillCorner 只有 `game_interruption_before/after` 的 throw-in/free-kick/goal-kick/corner/goal，不是逐帧事件；PFF 的 `game_event` 有 OUT/SUB/END，但事件类型未公开完整规格。
8. **半场/加时**：Metrica 的 timestamp 按 period 重置；SkillCorner 的 period 1/2 连续，10 fps；PFF 夹具 4 个 period。ATD 是两个半场，映射规则不同。
9. **视频缺失/转播切换**：SkillCorner 有 13,359 帧无球员/无球（21.8% 全场），其中 649 帧落在 phase 内；这些帧不能当 D，也不能当 H/A，应标“未知/边界”。ATD 的缺失是 NaN，允许算法处理；外部数据的“无球员”不等于“死球”。
10. **X**：所有外部数据都没有“放弃判断”标签，无法构造 X；外部评测不能覆盖官方 macroF1 对 X 的惩罚和 spellF1 的填充规则。

## 8. 推荐

### 8.1 用哪一个

| 用途 | 推荐 | 理由 |
|---|---|---|
| ATD 格式/加载/缺失/槽位鲁棒性 | **Metrica Game 3 EPTS** | 同 EPTS、25 fps、0–1、105×68；球缺失 32.2%；能直接测 loader、NaN、坐标、槽位 |
| 弱标签 H/A/D 外部 sanity | **SkillCorner `1925299`** | MIT、公开、10 fps、球 z、phase+possession、球队/球员 ID；phase 可给出 in-play 段，补集可给 D |
| 高保真 H/A/D（若许可解决） | **PFF 2022 WC** | 29.97 fps、球 z、`ball_state`/`ball_owning_team_id`、game_event；技术最直接 |
| 仅事件 | StatsBomb 等 | 无跟踪，不能生成 46 槽位逐帧表；排除 |

**总体推荐：SkillCorner 一场做主弱标签 sanity，Metrica Game 3 做格式/缺失对照；PFF 暂不作为公开测试集。** 不要把任何一个外部集称为“真实测试集”或“官方替代”；在技术文档中应写“弱标签外部 sanity set”，并说明标签来源与不确定点。

### 8.2 对外部集的定位

- **可以回答**：转换后能否加载、球缺失/球员缺失怎么表现、10 fps/30 fps 到 25 fps 的插值是否稳定、46 槽位映射是否可行、算法在外部弱标签上是否出现明显崩溃。
- **不能回答**：本场官方 spellF1/macroF1 的绝对水平；官方 D 的精确边界；争抢/松散球的官方归属；换人/伤停/VAR 的官方停表；`X` 的收益。
- **不能用于**：用外部弱标签调本场参数、用外部分数选择本场算法、用外部数据训练本场标签、把外部分数写进排行榜比较。

## 9. 下一步转换任务的建议范围

本节保留当时的范围建议；第 1–3 项已实现，见本节末尾。建议顺序如下：

1. **SkillCorner 单场观测转换（优先）**：`1925299` → 25 fps、141 列、46 槽位、0–1 坐标、NaN 缺失；metadata 保持 105×68、25 fps；先不生成标签。
2. **SkillCorner 弱标签（与观测分离）**：用 `phases_of_play` 的球队作为 H/A，phase 外作为 D；对重叠 phase、phase 内无 possession、phase 外有球+球员的帧单独打“不确定”标记；不要把手动规则写成针对本场的常数。
3. **Metrica Game 3 观测转换（格式对照）**：EPTS → 141 列；25 fps 直接映射；速度由位置差分；球 z 丢弃；事件不进入观测。用它检查 ATD loader/槽位/缺失，不用它算 H/A/D 准确率。
4. **外部标签边界审计**：在**其他比赛**上抽 5–10 分钟，人工核对 D 起止、争抢归属、换人/伤停；这是规则允许的（其他比赛可手标），但不要把本场 BAR-ATH 的任何片段放进去。审计结果只用于给弱标签加置信度/剔除边界帧。
5. **PFF 先谈许可**：向 Gradient/PFF 或组织方确认 64 场数据是否可获取、许可是否允许比赛用途/技术文档/复核；在没有书面确认前不写 PFF 转换、不下载、不使用。
6. **停止条件**：Metrica 许可仍不明确；SkillCorner 弱标签在边界审计中误差过大；PFF 许可/数据拿不到；任一情况下，不把外部数据升级为“真实测试集”。

**已实现（2026-11-16）**：新增 [`external/`](../../external/) 转换包，把 Metrica Sample Game 1/2/3 和 SkillCorner `1925299` 转成 `outputs/simulation_sets/ext_<source>_<match>/`，命令为
`.venv/bin/python -m external.convert --source metrica --data-dir "$PWD/data"`（把 `metrica` 换成 `skillcorner` 或 `all` 可转换另一源或全部；目录已存在时加 `--force`）。
观测、弱标签和写出口径分别在 [`external/common.py`](../../external/common.py)、[`external/metrica.py`](../../external/metrica.py)、[`external/skillcorner.py`](../../external/skillcorner.py)；
各数据集的帧数、缺球率、H/A/D/X 占比、外推占比和已知限制见 [`experiments/20261116_external_sets/NOTES.md`](../../experiments/20261116_external_sets/NOTES.md)。
第 4 项（人工边界审计）和第 5 项（PFF 许可）没有做；本节不重复格式细节。

## 10. 下载、校验与复现

### 10.1 本地目录

```text
data/external/
├─ SHA256SUMS
├─ metrica/
│  ├─ Sample_Game_1/  (tracking home/away + events)
│  ├─ Sample_Game_2/  (tracking home/away + events)
│  ├─ Sample_Game_3/  (EPTS metadata + tracking + events)
│  └─ documentation/events-definitions.pdf
├─ skillcorner/
│  ├─ matches.json
│  └─ 1925299/  (match.json, tracking, dynamic_events, phases_of_play)
└─ kloppy_pff_fixture/  (kloppy 测试夹具，仅格式检查，不是 64 场数据)
```

`data/external/` 被 `.gitignore` 的 `data/*` 排除（实测 `git check-ignore` 命中 `.gitignore:32`），不会进 Git。`data/external/SHA256SUMS` 是本地校验清单。

### 10.2 下载命令

Metrica（公开 raw）：

```bash
BASE=https://raw.githubusercontent.com/metrica-sports/sample-data/master
mkdir -p data/external/metrica/Sample_Game_3
for f in \
  data/Sample_Game_3/Sample_Game_3_metadata.xml \
  data/Sample_Game_3/Sample_Game_3_tracking.txt \
  data/Sample_Game_3/Sample_Game_3_events.json; do
  curl -L --fail --retry 3 -o "data/external/metrica/${f#data/}" "$BASE/$f"
done
```

Game 1/2 的 CSV 和 `documentation/events-definitions.pdf` 同理；完整文件清单和校验值见 `data/external/SHA256SUMS`。仓库 commit：`e706dd506b360d69d9d123d5b8026e7294b13996`（2021-04-15）。

SkillCorner（metadata/events/phases 用 raw，tracking 是 Git LFS，用 media）：

```bash
R=https://raw.githubusercontent.com/SkillCorner/opendata/master/data
M=https://media.githubusercontent.com/media/SkillCorner/opendata/master/data
mkdir -p data/external/skillcorner/1925299
curl -L --fail -o data/external/skillcorner/matches.json "$R/matches.json"
curl -L --fail -o data/external/skillcorner/1925299/1925299_match.json "$R/matches/1925299/1925299_match.json"
curl -L --fail -o data/external/skillcorner/1925299/1925299_dynamic_events.csv "$R/matches/1925299/1925299_dynamic_events.csv"
curl -L --fail -o data/external/skillcorner/1925299/1925299_phases_of_play.csv "$R/matches/1925299/1925299_phases_of_play.csv"
curl -L --fail -o data/external/skillcorner/1925299/1925299_tracking_extrapolated.jsonl "$M/matches/1925299/1925299_tracking_extrapolated.jsonl"
```

仓库 commit：`4340d274572876239c154c90bc507a9b3250a656`（2026-09-14）。

PFF：**未下载 64 场数据**。仅下载 kloppy 3.18.0 的公开测试夹具（200 帧，格式检查）：

```bash
B=https://raw.githubusercontent.com/PySport/kloppy/v3.18.0/kloppy/tests/files
mkdir -p data/external/kloppy_pff_fixture
for f in pff_metadata_10517.json pff_rosters_10517.json pff_10517.jsonl; do
  curl -L --fail -o "data/external/kloppy_pff_fixture/$f" "$B/$f"
done
```

### 10.3 kloppy 复现命令与结果

环境：`.venv`，Python 3.9，kloppy 3.18.0，macOS。

Metrica Game 3：

```bash
.venv/bin/python - <<'PY'
from kloppy import metrica
base = "data/external/metrica/Sample_Game_3"
ds = metrica.load_tracking_epts(
    meta_data=f"{base}/Sample_Game_3_metadata.xml",
    raw_data=f"{base}/Sample_Game_3_tracking.txt",
)
df = ds.to_df(engine="pandas")
print(len(df), df.shape, ds.metadata.frame_rate, ds.metadata.pitch_dimensions)
print("ball_missing", int(df.ball_x.isna().sum()), float(df.ball_x.isna().mean()))
print("ball_z_nonnull", int(df.ball_z.notna().sum()))
print("ball_state", df.ball_state.value_counts(dropna=False).to_dict())
print("speed_nonnull", int(df[[c for c in df.columns if c.endswith("_s")]].notna().sum().sum()))
PY
```

结果：143,761 行、149 列、25 fps、105×68；球缺失 46,325（32.22%）；`ball_z` 非空 0；`ball_state` 全 None；速度非空 0；加载 14.65 s。

SkillCorner `1925299`：

```bash
.venv/bin/python - <<'PY'
from kloppy import skillcorner
base = "data/external/skillcorner/1925299"
ds = skillcorner.load(
    meta_data=f"{base}/1925299_match.json",
    raw_data=f"{base}/1925299_tracking_extrapolated.jsonl",
    only_alive=False,
    include_empty_frames=True,
)
df = ds.to_df(engine="pandas")
print(len(df), ds.metadata.frame_rate, df.ball_state.value_counts(dropna=False).to_dict())
alive = df[df.ball_state == "alive"]
print("ball_missing_full", int(df.ball_x.isna().sum()), float(df.ball_x.isna().mean()))
print("ball_missing_alive", int(alive.ball_x.isna().sum()), float(alive.ball_x.isna().mean()))
print("ball_z_missing_alive", int(alive.ball_z.isna().sum()), float(alive.ball_z.isna().mean()))
PY
```

结果：61,282 行、137 列、10 fps、105×68；`alive` 35,589、`dead` 25,693；全场球缺失 13,349（21.78%）；活球球缺失 531（1.49%）；活球 z 缺失 734（2.06%）；加载 23.03 s。默认 `only_alive=True` 只剩 35,589 行。

PFF 测试夹具：

```bash
.venv/bin/python - <<'PY'
from kloppy import pff
base = "data/external/kloppy_pff_fixture"
ds = pff.load_tracking(
    meta_data=f"{base}/pff_metadata_10517.json",
    roster_meta_data=f"{base}/pff_rosters_10517.json",
    raw_data=f"{base}/pff_10517.jsonl",
    only_alive=False,
)
df = ds.to_df(engine="pandas")
print(len(df), ds.metadata.frame_rate, [p.id for p in ds.metadata.periods])
print(df.ball_state.value_counts(dropna=False).to_dict())
print("ball_z_range", float(df.ball_z.min()), float(df.ball_z.max()), "missing", int(df.ball_z.isna().sum()))
PY
```

结果：200 行、29.97 fps、4 个 period；`ball_state` 199 alive/1 dead；球 z 0.00–2.88 m；52/200 帧球缺失。**这是 200 帧测试夹具，不是 64 场数据；不能据此估计全场缺失率。**

### 10.4 关键文件校验

完整清单见本地 `data/external/SHA256SUMS`（18 个数据文件，不含清单本身）。关键文件：

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `metrica/Sample_Game_3/Sample_Game_3_tracking.txt` | 53,443,115 | `570e6ce82c2d93bc92723af331d93c31110bec1d6dc0be07c6d44ca3f981d658` |
| `metrica/Sample_Game_3/Sample_Game_3_metadata.xml` | 81,806 | `009c7dcfcb66192014917ca1559c158f612353e390eafb85f8214b06a1c7dec1` |
| `metrica/Sample_Game_3/Sample_Game_3_events.json` | 1,709,486 | `28a53bfe9eaf32535362335553d517cdce0eabb588af6166009081753751f4e0` |
| `skillcorner/1925299/1925299_tracking_extrapolated.jsonl` | 97,091,519 | `48528be40ad82fa3e2b232e1af8d311705f7d6d119925ef199d2b59ea36fd3c9` |
| `skillcorner/1925299/1925299_match.json` | 28,396 | `f4345b32c0fdd7c9990df70050b3a74f57b1992cf762e20f2a4d309bd2fba7d2` |
| `skillcorner/1925299/1925299_dynamic_events.csv` | 5,043,601 | `2557acbdcba6547d764b9f7c277c3d7e81a4d58692d6c20c2bfa28625ae0cce3` |
| `skillcorner/1925299/1925299_phases_of_play.csv` | 131,104 | `a1682a736a9cf1c311cb799f0a949f7e023dca4ebaa9dd294b138e8929271274` |
| `kloppy_pff_fixture/pff_10517.jsonl` | 1,003,941 | `8bf1ce4963da1d6c9a1644fff4b4b2cf421a8779ce3f6004861713902bfc63c4` |

## 11. 补充：球缺失段与停顿事件的对应性（仅外部数据）

你给出的本场统计——缺球集中为 5–30 s 长段、两个半场共 150 段、消失前球慢、重现时球快（中位 11.6 m/s）且紧贴球员——只作为对照假设，不作为输入。本节只读 `data/external/`，没有打开 `data/tactical/`、`data/broadcast/` 或任何本场文件。

### 11.1 方法

**Metrica（Game 1/2/3）**

- 缺球段：连续的 `ball_x`/`ball_y` 为 NaN 的帧。Metrica 缺球时球员仍在：Game 3 每帧 22 人，Game 1/2 每帧 11 人；所以这是球单独缺失，不是整段跟踪缺失。
- 起点锚（start anchor）：缺球段开始前 5 s 内结束的停顿类事件，取事件 `end` 到缺球段开始的间隔。停顿类事件包括：
  - `BALL OUT`、`FAULT RECEIVED`、`CARD`；
  - `SHOT` 的 `OUT`/`GOAL`；
  - `BALL LOST` 的 `OFFSIDE`/`HAND BALL`/`END HALF`；
  - `CHALLENGE` 的 `FAULT`（WON/LOST 都算）。
- 终点锚（end anchor）：缺球段结束后 2 s 内开始的 `SET PIECE`，取缺球段结束到 `SET PIECE` 的间隔。
- 分类：
  - `both`：有起点锚和终点锚；
  - `start_only`：只有起点锚（重启延迟/漏记）；
  - `end_only`：只有终点锚（停顿原因漏记，如 offside/foul）；
  - `neither`：两端都没有。
- 速度：用相邻有效球位置差分，位置乘 105×68 m，25 fps；`pre_speed` 是缺球前最后一个有效速度，`post_speed` 是重现后第一个有效速度；`post_near` 是重现第一帧球到最近球员的距离。
- 这套锚定不是官方 D 定义，只是用外部事件检验“缺球是否发生在停表附近”。

**SkillCorner（`1925299`）**

- 缺球段：`ball_data.x/y` 为 null 的连续帧。
- 该数据没有犯规/换人逐帧事件，只有 `phases_of_play`；用 phase 外作为停表近似。
- 重要区别：SkillCorner 的 13,359 个缺球帧**全部** `player_data` 为空（`n_players=0`）。也就是说它不是“球员还在、只把球拿掉”，而是整段跟踪/视频缺失。

**PFF**

- 200 帧 kloppy 夹具每段只有首尾 25 帧，不能做连续缺球段分析；64 场数据未获得。PFF 的 `SUB`/`VID` 事件存在，但本次无法验证。

### 11.2 Metrica 结果

#### 段长与锚定

| 场次 | 缺球帧 | 段数 | 中位段长 | 5–30 s | >30 s | <5 s | both | start_only | end_only | neither（帧 / 最长） |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Game 1 | 56,755 | 155 | 7.84 s | 58 | 26 | 71 | 63 | 34 | 1 | 561 / 7.16 s |
| Game 2 | 57,884 | 169 | 5.08 s | 58 | 27 | 84 | 64 | 31 | 5 | 825 / 4.24 s |
| Game 3 | 46,325 | 160 | 6.68 s | 72 | 19 | 69 | 84 | 13 | 6 | 319 / 1.96 s |

- 三场分别有 155/169/160 段，接近本场“两个半场共 150 段”的总段数；其中 5–30 s 为 58/58/72 段，另有 26/27/19 段 >30 s、71/84/69 段 <5 s。如果本场的 150 段指“总段数”，量级一致；如果指“5–30 s 段数”，Metrica 每场只有 58–72 段，少一些。
- 98.6–99.3% 的缺球帧位于至少有一个锚的段中（Game 1 99.0%、Game 2 98.6%、Game 3 99.3%）。按帧数（both/start_only/end_only/neither）：Game 1 36,254/19,843/97/561；Game 2 38,293/15,994/2,772/825；Game 3 33,304/9,412/3,290/319。
- 所有 >=5 s 的段中，**只有一个没有自动锚**：Game 1 的 134913–135091（7.16 s）。手动检查发现 134915 有 `CHALLENGE TACKLE-FAULT-WON`，135085 有 `SET PIECE FREE KICK`，所以它仍是死球段，不是活球长缺失。

#### 起点/终点偏移

Game 3 的精确分布：

- 起点锚 97 段：`start_gap` 中位数 1 帧（0.04 s），**92/97 段就是 1 帧**；其余为 0、7、26、64、94 帧。
- 终点锚 90 段：`end_gap` 中位数 1 帧（0.04 s），**88/90 段就是 1 帧**，2 段为 2 帧。
- 两端都有的 84 段：起点/终点中位都是 1 帧。

Game 1/2 的起点锚、终点锚中位也都是 0.04 s（1 帧）。也就是说，Metrica 的缺球段基本是：**停顿事件结束后的下一帧开始，重启 set piece 的前一帧结束**。

Game 3 的起点锚类型：

| 起点锚 | 段数 |
|---|---:|
| `BALL OUT`（含 HEAD/CLEARANCE/CROSS 等） | 64 |
| `CHALLENGE` 的 FAULT | 12 |
| `FAULT RECEIVED` | 7 |
| `SHOT OFF TARGET / OUT` | 6 |
| `SHOT ON TARGET / GOAL` | 2 |
| `BALL LOST HAND BALL` | 2 |
| `BALL LOST OFFSIDE` | 2 |
| `BALL LOST END HALF` | 2 |

终点锚类型：throw-in 49、free kick 26、corner 8、kick off 4、direct free kick 1、retaken throw-in 1、retaken free kick 1。

两个进球段非常干净：

- 27525–27544 进球 → 缺球 27545–28880 → 28881 kick off；
- 80761–80779 进球 → 缺球 80780–82124 → 82125 kick off。

即进球结束后 1 帧开始缺球，重启前 1 帧恢复。

**换人和牌**：Metrica 事件没有 `SUBSTITUTION`；Game 3 只有 1 张黄牌（105378），它落在一个 `end_only` 缺球段 105030–105999 内部，不是起点锚。因此 Metrica 不能检验换人，也不能把牌作为主要锚。

#### 速度和球员距离

| 场次 | 全部段 pre / post / post_near | >=5 s 段 pre / post / post_near |
|---|---|---|
| Game 1 | 9.89 m/s / 3.25 m/s / 0.00 m | 9.03 / 5.68 / 0.00 |
| Game 2 | 9.58 / 2.90 / 0.04 | 10.05 / 4.53 / 3.79 |
| Game 3 | 9.96 / 3.48 / 0.00 | 10.14 / 4.39 / 0.00 |

- **“重现时紧贴球员”在 Game 1/3 很强**：中位距离 0.00 m（最大 0.012 m），球几乎精确落在某个球员位置上；Game 2 全段中位 0.04 m，但 >=5 s 段中位 3.79 m，弱一些。
- **“消失前球慢、重现时球快”没有复现**：Metrica 的 pre_speed 中位约 9.6–10.0 m/s，不是慢球；post_speed 中位约 2.9–3.5 m/s，也不是 11.6 m/s。少数段（Game 3 `end_only`）post 中位可到 10.6 m/s，但不是整体规律。
- 因此外部 Metrica 支持“死球时把球拿掉、重启时把球放回球员附近”，但**不支持**本场那个具体的“pre 慢 / post 11.6 m/s”速度签名。

#### 活球长缺失

- Game 3：`neither` 57 段，合计 319 帧（0.69% 缺球帧），中位 0.04 s，最长 1.96 s。
- Game 2：`neither` 69 段，合计 825 帧（1.4%），最长 4.24 s。
- Game 1：`neither` 57 段，合计 561 帧（1.0%），最长 7.16 s；该段手动检查是犯规→任意球，仍属死球。
- **结论：Metrica 三场没有确认的活球长段缺失。** 长段都能被至少一个停顿/重启事件解释；未被自动锚定的段都很短，或手动检查后仍是死球。

### 11.3 SkillCorner 结果

| 指标 | 数值 |
|---|---:|
| 缺球段 | 54 |
| 中位 / p90 / 最长 | 15.95 s / 39.21 s / 137.8 s |
| >=5 s / >=10 s / >=30 s | 51 / 42 / 18 |
| 基本在 phase 外（`live_ratio<=0.1`） | 48 段 |
| >=90% 在 phase 内（`live_ratio>=0.9`） | 4 段 |
| 混合 | 2 段 |
| 缺球帧 | 13,359 |
| 其中在 phase 内 | 649（4.9%） |
| 其中在 phase 外 | 12,710（95.1%） |
| 缺球帧中 `n_players=0` | 13,359（100%） |

- phase 外共 25,465 帧，其中缺球 12,710（49.9%），**另有 12,755 帧球仍在**。这说明 SkillCorner 在死球期间通常仍保留球，不是“死球就移除球”。
- 对 26 个两端都有 phase 边界的完全死球段：起点中位在 phase 结束后 80.5 帧（8.05 s），终点中位在下一 phase 开始前 69 帧（6.9 s）；不是“哨响即消失、重启即恢复”的 1 帧对齐。
- 速度：完全死球段 pre/post 中位 1.14 / 1.61 m/s，球员距离中位 2.65 m；有活球帧的段 pre/post 中位 1.08 / 10.43 m/s，距离 3.75 m。这个 post 速度看起来像本场的 11.6 m/s，但它是**整段无球员**的广播缺口，不是球单独被拿掉。
- 3 个完全活球且 >=5 s 的段：17.0 s（49969–50138）、15.3 s（8328–8480）、10.2 s（56849–56950）。三段在缺球期间都是 0 名球员；更可能是转播切换/跟踪中断，而不是“活球时把球坐标去掉”。

**结论：SkillCorner 不能支持“死球时数据商去掉球坐标”的假设。** 它的缺球是整段跟踪缺失；它反而显示死球期间球通常还在。

### 11.4 PFF

- 公开夹具 200 帧中有 52 帧缺球，但夹具是每个 period 首尾 25 帧的抽样，不能构成连续段，不能回答 ①–③。
- PFF 的 `game_event` 有 `SUB`、`VID`、`OUT`、`END` 等，理论上可以检验换人和视频缺失；但 64 场数据当前不可获取，不能下结论。

### 11.5 回答三个问题

**① 缺球段与出界、犯规、进球、换人等停顿是否对应？**

- Metrica：**大部分对应**。Game 3 的 160 段中，97 段有起点锚、90 段有终点锚、84 段两端都有；起点锚里 BALL OUT 64、犯规类 19（12 CHALLENGE FAULT + 7 FAULT RECEIVED）、SHOT OUT 6、GOAL 2、HANDBALL 2、OFFSIDE 2、END HALF 2。两个进球段精确对齐。98.6–99.3% 的缺球帧在至少一端有锚的段中。
- SkillCorner：**不对应**。缺球是全对象缺失，不是球单独移除；54 段中 48 段基本在 phase 外，但死球期间 12,755 帧球仍在。
- PFF：**无法验证**（数据不可得）。
- 换人：Metrica 没有 SUB 事件；SkillCorner 只有 match.json 的上下场时间，没有逐帧换人事件；PFF 有 SUB 但不可得。**本次外部数据不能验证换人。**

**② 缺失从停顿事件前后多少秒开始，到重启事件前后多少秒结束？**

- Metrica Game 3：起点中位 1 帧（0.04 s）**在停顿事件结束之后**，92/97 段就是 1 帧；终点中位 1 帧（0.04 s）**在重启 set piece 之前**，88/90 段就是 1 帧。Game 1/2 的起点/终点中位也都是 0.04 s。
- Metrica 的缺球不是从“停顿事件开始”算，而是从事件 `end` 后 1 帧；例如 BALL OUT 的 `end` 是球出界，GOAL 的 `end` 是射门结束。
- SkillCorner：起点中位在 phase 结束后 8.05 s，终点中位在下一 phase 前 6.9 s；不是 1 帧对齐。

**③ 是否存在活球期间的长段缺失？**

- Metrica：**没有确认的活球长段缺失**。Game 3 未锚定段最长 1.96 s；Game 2 最长 4.24 s；Game 1 最长 7.16 s，但手动检查是犯规→任意球。除这一段外，所有 >=5 s 段都有至少一个自动锚；这一段手动检查后仍属死球。
- SkillCorner：有 3 个完全活球且 >=5 s 的缺球段（17.0/15.3/10.2 s），但缺球期间 0 名球员；这是整段跟踪/转播缺口，不能当作“活球时只移除球”。
- PFF：未验证。

### 11.6 与本场假设的关系

- **支持的部分**：Metrica 的段长（中位 5–8 s、58–72 段落在 5–30 s）、1 帧对齐、进球/出界/犯规/越位/手球后的缺球、重启前恢复、Game 1/3 球精确回到球员位置，都支持“死球时数据商去掉球坐标”的机制。三场共 484 段，量级和本场 150 段接近。
- **不支持/不能确认的部分**：外部 Metrica 没有复现“消失前慢、重现时 11.6 m/s”的速度签名；pre 约 10 m/s、post 约 3–5 m/s。Game 2 的 post_near 也明显弱于 Game 1/3。不同数据商/不同导出可能采用不同的缺球策略，不能把 Metrica 的机制直接当成所有数据商的机制。
- **SkillCorner 是反例**：它保留死球期间的球，缺球时整段无球员；不能用它验证本场假设。
- **仍无法回答**：换人（Metrica 无事件、SkillCorner 无逐帧事件、PFF 不可得）、VAR/伤停、以及“官方 corrected tracking 的 dead 起点”与供应商事件的精确差异。

## 12. 未决问题

1. **Metrica 的许可**：没有 LICENSE；README 的署名请求能否覆盖本项目/公开提交，需要 Metrica 或组织方确认。
2. **PFF 的许可与访问**：没有数据集专属条款；当前页面无可用数据集表单；`fc.pff.com/docs` 530；需要 Gradient/PFF 书面确认。
3. **官方“controlled possession”的精确边界**：外部数据没有官方标签可对照；争抢/松散球只能近似。
4. **D 的精确起止**：犯规停表、advantage、快发、换人、伤停、VAR、进球庆祝、半场/加时都没有统一外部字段。
5. **SkillCorner 的 20 场 vs README 10 场**：数量差异原因未知；本文只实测了 1 场，不能代表全部 20 场。
6. **PFF 全场的球缺失率/事件精度**：没有数据，未知；夹具不能代表全场。
7. **外推/追踪误差对 H/A 的影响**：SkillCorner 42.1% 球员观测是外推；本场 ATD 也有缺失/错误，但两者分布不同，不能互相替代。
8. **46 槽位映射的语义**：外部稳定 player id 映射到 ATD 匿名槽位，无法复现 slot 换人/身份切换；这是格式转换的固有差异。

## 13. 本调研未做

- 没有写转换代码、算法代码、模拟器代码，也没有修改 `algorithms/`、`simulation/`；第 11 节的补充分析只用内联 Python，未提交脚本。
- 没有打开或读取 BAR-ATH 的 tactical/broadcast 文件，没有读取 `evaluation/gt/`、`evaluation/scoreboard.csv`、`evaluation/reports/` 或公开窗口评分。
- 没有把任何比赛数据片段提供给托管大模型；本文只使用公开文档、公开仓库、公开页面和本机 kloppy 输出。
- 没有把外部弱标签用于本场训练/调参/选型；本文只做可行性调研。
