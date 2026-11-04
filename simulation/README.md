# 模拟测试

在已知答案的虚拟比赛片段上检查控球算法：先在信息完整时验证逻辑，再逐步加入观测缺陷。
模拟成绩不代表真实比赛成绩。场景定义见 [CLEAN_CORNER_CASES_V1.md](scenarios/CLEAN_CORNER_CASES_V1.md)。

当前状态：骨架已跑通，只实现了 TI01、HD01 两个子型（各含主客互换版本）；观测层为 V1 原样输出。

## 流程：三层分开

```text
剧本（事件）  ──►  干净轨迹 + 答案  ──►  观测层  ──►  算法  ──►  评分
                                        │
                                        └ V1 原样通过；之后在这里加噪声、丢球、ID 互换
```

观测层从第一版起就单独存在，即使暂时什么都不做。这样以后加缺陷时，剧本、答案和评分都不用改，
同一个干净片段也能和"加缺陷"版本直接对比。

## 运行方式

从仓库根目录执行：

```bash
# 1. 生成数据集并自检（任一片段自检失败则不写文件）
.venv/bin/python -m simulation.generate --dataset-id clean_v1_skeleton_02 --subtypes TI01,HD01

# 2. 运行实验配置里的算法，并逐片段评分
bash scripts/run_simulation.sh 20261028_nearest_player_sim_skeleton clean_v1_skeleton_02
```

`generate` 默认不覆盖已有数据集；改了场景或生成逻辑就换一个 dataset id。

## 文件放置

```text
simulation/scenarios/           场景规格和场景脚本，进 Git
outputs/simulation_sets/<id>/   生成的数据，不进 Git
    observations.csv            算法可读：逐帧位置
    game_state.csv              算法可读：裁判信号
    truth.csv                   仅评分：逐帧答案
    events.csv                  仅评分：剧本事件表
    samples.csv                 仅评分：片段说明
    manifest.json               生成命令、代码版本、依赖版本
outputs/<experiment_id>/simulation/<id>/
    predictions.csv             算法输出
    per_clip.csv                逐片段指标
    report.md                   逐片段报告
```

| 文件 | 列 | 说明 |
|---|---|---|
| `observations.csv` | `clip, frame, object, team, x, y, z` | 每帧每个对象一行（1 个球 + 22 名球员）。`object` 为 `ball` 或 `p01`–`p22`（`p01`–`p11` 主队，`p12`–`p22` 客队）；`team` 为 `H`/`A`，球为空；`z` 只有球有（球心高度，贴地为 0.11）。米制，105 × 68 m，原点在一角；帧号从 0 开始，25 fps |
| `game_state.csv` | `clip, frame, play_live, restart_team` | `play_live` 为 1/0；`restart_team` 只在重启生效那一帧填 `H`/`A`，其余为空。不含活球期间的控球队 |
| `truth.csv` | `clip, frame, label` | `H`/`A`/`D`，只由事件表推出 |
| `events.csv` | `clip, event, t, frame, team` | `t` 为连续时间（秒），`frame = ceil(25·t)` 为边界帧 |
| `samples.csv` | `clip, family, subtype, story_id, seed, initiating_team, n_frames, core_start, core_stop, expected_sequence` | `core_start`–`core_stop` 是核心事件窗口（左闭右开）；`initiating_team` 是剧本中发起事件的一方 |
| `predictions.csv` | `clip, frame, label` | 算法输出，`H`/`A`/`D`/`X` |

`clip` 是不透明编号（`c001`…，按种子打乱），场景名只在 `samples.csv` 里。每个样本记下故事编号和随机种子，
以后要分开发集／保留集时按故事编号划分。同一故事的主客互换版本使用同一种子，球场旋转 180°。

## 代码索引

| 位置 | 作用 |
|---|---|
| `scenarios/<族>.py` | 场景剧本；每族一个文件，导出 `FAMILY` 和 `SUBTYPES`，只调用 `core`，按文件名自动发现 |
| `core/clip.py` | `ClipBuilder`：剧本用的工具（摆位、持球、带球、传球、跑位、记事件），以及渲染成逐帧数据 |
| `core/motion.py` | 球员和球的连续时间轨迹（平滑跑动、抛物线飞行） |
| `core/events.py` | 事件类型；`truth_from_events()` 是唯一产生答案的地方 |
| `core/checks.py` | 场景自检：运动合理、触球有人、事件顺序、答案与预期序列一致 |
| `core/observe.py` | 观测层（V1 原样输出） |
| `core/io.py` | 数据集读写；`load_clips()` 只读算法可见文件 |
| `generate.py` | 生成数据集 + 自检 |
| `run_algorithm.py` | 读实验配置，对每个片段调用算法的 `predict_clip()` |
| `evaluate.py` | 逐片段调用官方 `possession_metrics.evaluate()`，加核心窗口和换权时点诊断 |

算法接入：在 `algorithms/<算法>/predict.py` 实现 `predict_clip(observations, game_state, config)`，
约定见 [algorithms/_template/predict.py](../algorithms/_template/predict.py)。原有 `predict(config)` 不变。

## 两条红线

1. 算法只读 `observations.csv` 和 `game_state.csv`，不读答案、剧本、事件表或场景名。
2. 不用比赛的公开答案或人工标注构造场景（见 [AGENTS.md](../AGENTS.md)）。
