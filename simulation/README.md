# 模拟测试

模拟算法输入与真实 tactical ATD 共用格式和唯一入口，决策见 [ADR-001](../docs/decisions/ADR-001-ATD-OBSERVATIONS.md)。
默认观测不加缺陷；可选加入球坐标缺失，不加球员漏检、噪声或槽位交换。模拟成绩不代表真实比赛成绩。

| 文档 | 内容 |
|---|---|
| 本文 | 流程、运行命令、文件布局、代码索引 |
| [scenarios/SCENARIOS.md](scenarios/SCENARIOS.md) | 全部场景族的规格和实现状态（当前 17 个子型已实现） |
| [MOTION.md](MOTION.md) | 运动积木的用法和物理参数依据 |

## 流程：三层分开

```text
剧本事件 ──► 完整世界 + 答案 ──► ATD 观测层 ──► 算法 ──► 评分
                    │
                    └──► debug/ 干净轨迹 ──► 人工查看器
```

观测层去掉球高、固定球员身份和裁判信号，转换坐标并生成槽位速度。
`game_state` 仅留在生成器内部，不写文件，不供算法读取。
干净轨迹只用于排查；后续观测缺陷也应在观测层实现，不能修改事件答案来迎合算法。

## 运行方式

从仓库根目录执行，使用已有 `.venv`（需要 numpy、pandas、PyYAML）：

```bash
# 1. 新编号生成数据集并自检；不覆盖已有编号。--stories 每子型故事数，--seed 起始种子
.venv/bin/python -m simulation.generate \
  --dataset-id <dataset_id> --subtypes TI01,HD01,BP01 --stories 5 --seed 0

# 2. 运行实验配置里的算法并逐片段评分（例如占位算法 20261107_placeholder_atd_interface）
bash scripts/run_simulation.sh <experiment_id> <dataset_id>

# 3. 导出现有轨迹、答案与预测，不重新生成或运行算法
.venv/bin/python -m simulation.view --dataset <dataset_id> --experiment <experiment_id>
```

编号已存在时生成会拒绝写入；换新编号，不覆盖原目录。
旧长表数据集不供新入口运行，需要按新编号重新生成；查看器也不兼容旧数据。
占位算法全部输出 X，准确性检查失败是预期的，只用来检查运行链路。

导出的 `viewer.html` 在对应结果目录，双击即可打开。页面包含全部数据，无需服务器或网络。
可选择片段、播放／暂停、拖动时间轴、输入帧号或逐帧查看；空格播放，左右键步进。
页面展示的是 **debug 中的完整剧本轨迹**，不是算法实际可见输入。
球高度曲线标注“仅模拟剧本有，算法看不到”；同时显示答案、预测及可点击事件。
缺少预测时显示灰色“无预测”；紫色色带标注缺球帧，并用紫色虚线球显示干净轨迹。
数据格式或帧对齐错误抛异常。

## 可选球坐标缺失

ST01–ST04 的故事、正确答案和事件边界见 [场景规格 §12](scenarios/SCENARIOS.md#12-场景族八长停顿与重启)。
“数据商会在部分死球期间移除球坐标”是模拟假设，不是官方说明。
缺球默认关闭。开启后，仅将观测表的 `ball_x`、`ball_y` 一起置为 NaN；
球员坐标和速度、干净轨迹、事件与正确答案均不变。算法元数据不含遮罩、策略或场景名。

| 参数 | 默认值 | 含义 |
|---|---|---|
| `--dead-ball-gaps` | 关闭 | 开启死球策略与可选活球短缺 |
| `--dead-ball-gap-weights WHOLE DELAYED VISIBLE` | 1 1 1 | 每段独立抽取整段缺球、延迟后缺球、全程可见的相对权重 |
| `--dead-ball-delay-range MIN MAX` | 2 5 | 延迟策略额外等待的秒数，均匀抽样 |
| `--live-ball-gap-rate RATE` | 13/5400 ≈ 0.002407 | 每活球秒的短缺发生率；0 关闭 |

三种策略默认各约 1/3 **是假设**，不是从官方答案估计的比例。出界也允许全程可见。
每段死球包括片段开头的等待，独立抽一次策略；整段策略允许 0–5 帧（0–0.2 s）起点抖动，
延迟策略在此基础上加 2–5 s。第一帧恢复坐标为合法重启帧或其前一帧，等概率抽取；
这是观测模拟抖动，不改变实际踢出／掷入的事件或答案边界。
末尾未重启的死球不会提前恢复。延迟超过死球长度时，该段不产生缺球。

```text
真实状态  D 等待 │ H 活球 │ stoppage / ball_out ───── D ─────│ legal_restart → H/A
整段缺球  NaN…   │ 有球   │ 0–0.2 s 后 NaN………………恢复 │ 有球
延迟缺球  可见*  │ 有球   │ 先可见数秒，再 NaN………恢复 │ 有球
全程可见  有球   │ 有球   │             始终有球           │ 有球
```

`*` 短于延迟的开头等待全程可见。死球时仍可能看见快球、捡球或摆球，
因此不能把“缺球”和 D 当作完全相同的状态。

活球短缺长度为 1–4 帧（0.04–0.16 s），按活球时间的指数等待抽样；
前后各保留可见帧，不与死球缺球或另一短缺合并，不产生活球长缺球。
发生率按活球时长计，不是每个片段强制插入一次。
观测使用独立随机流，同故事镜像共享遮罩，不消耗剧本或槽位随机数。
manifest 记录全部参数、随机流和各片段每段死球所选策略及遮罩边界，不供算法读取。

生成并检查长停顿数据集，不运行算法：

```bash
.venv/bin/python -m simulation.generate \
  --dataset-id <st_dataset_id> --subtypes ST01,ST02,ST03,ST04 \
  --stories 50 --seed 0 --dead-ball-gaps
.venv/bin/python -m experiments.20261108_ball_gaps.ball_gaps --dataset <st_dataset_id>
.venv/bin/python -m simulation.view --dataset <st_dataset_id> --experiment <preview_id>
```

已有编号不覆盖。统计脚本只使用 `--dataset`，不使用 tactical 数据入口。
每个子型 50 个种子、双镜像，共 400 片段，任一自检失败都会阻止整套写出。
验收数字和查看器抽查记录保存在 [PR #14](https://github.com/doooze08/mtah2027/pull/14) 描述中。

停顿密集片段的缺球率取决于场景比例、死球长度和策略权重，不代表整场比赛的缺球率。
等量 ST04 会提高 >30 s 的段数占比；延迟策略可以产生短尾段。
模拟始终有 22 名球员，没有球员漏检。重启前一帧恢复可使统计脚本的前向差分速度偏低；
消失前球速取决于停顿原因，重现距离和位移取决于摆球位置和捡球路线。
这些模型参数不是对本场比赛的拟合；不根据真实摘要选择种子或调整参数。

## 文件放置

```text
simulation/scenarios/           场景规格和脚本，进 Git
outputs/simulation_sets/<id>/   生成的数据，不进 Git
    observations.csv            算法可读：每帧一行的 ATD 宽表，外加 clip 分组键
    metadata.json               算法可读：每片段的槽位球队表、球场尺寸、帧率
    debug/clean_positions.csv   仅排查：米制完整轨迹，含 z、p01–p22
    truth.csv                   仅评分／查看：逐帧答案
    events.csv                  仅评分／查看：剧本事件
    samples.csv                 仅评分／查看：片段说明
    manifest.json               生成命令、代码版本、依赖和观测版本；不供算法读取
outputs/<experiment_id>/simulation/<id>/
    predictions.csv             算法输出
    per_clip.csv                逐片段指标
    report.md                   逐片段报告
    viewer.html                 仅人工排查，含干净档、答案和预测
```

| 文件 | 列或字段 | 说明 |
|---|---|---|
| `observations.csv` | `clip, frame, ball_x, ball_y, 1_x, 1_y, 1_s, …, 46_x, 46_y, 46_s` | 共 142 列；读取器移除 clip 后为算法的 141 列。坐标按球场边界 0–1 归一化，场外值不裁切；缺失为 NaN，速度 s 为 m/s；帧号从 0，25 fps |
| `metadata.json` | `clip → {slot_teams, pitch_length, pitch_width, fps}` | 算法只收到当前片段的值，不收到 clip id。全部 46 个字符串槽位键映射到 H/A；尺寸单位 m，帧率单位 fps；无身份映射、事件或场景名 |
| `debug/clean_positions.csv` | `clip, frame, object, team, x, y, z` | 每帧 23 行（球 + 22 名球员）；object 为 ball 或 p01–p22，球的 team 为空。位置单位 m，z 为球心高度，球员 z 为空；不供算法读取 |
| `truth.csv` | `clip, frame, label` | H/A/D，只由事件推导 |
| `events.csv` | `clip, event, t, frame, team` | t 为秒，边界帧 `ceil(25·t)` |
| `samples.csv` | `clip, family, subtype, story_id, seed, initiating_team, n_frames, core_start, core_stop, expected_sequence` | 核心窗口为左闭右开，initiating_team 为发起方 |
| `predictions.csv` | `clip, frame, label` | H/A/D/X，每个片段每帧一行 |

模拟 p01–p22 每片段随机映射到 1–46 中 22 个不同槽位，片段内固定、不互换。
全部槽位都有球队：24 个 H、22 个 A，每队各 11 个活动槽位；其余 24 槽位的 x/y/s 为 NaN。
映射直接使用故事种子，同种子同映射。模拟速度由相邻位置按 25 fps 差分计算，首帧用前向差分；
完整公式和真实 ATD 本地验证命令见 [统一观测接口](../docs/OBSERVATIONS.md)。
默认每帧都有球和 22 名球员；开启缺球时仍保留全部球员。这不是真实数据质量假设。

clip 是按种子打乱的不透明编号 c001…；故事、种子、主客互换配对只记入评分侧文件。
同一故事的主客互换版本使用相同故事种子，球场旋转 180°；同种子的片段共享槽位映射。

## 代码索引

| 位置 | 作用 |
|---|---|
| `scenarios/<族>.py` | 场景剧本，导出 FAMILY 和 SUBTYPES；`scenarios/_motion.py` 为按故事抽样的运动参数 |
| `core/clip.py` | 完整世界和事件生成工具 |
| `core/motion.py` | 球员和球的连续轨迹 |
| `core/events.py` | 事件与唯一答案推导 |
| `core/checks.py` | 场景自检 |
| `core/observe.py`、`core/gaps.py` | 完整世界投影为 ATD 宽表；可选球坐标缺失 |
| `core/io.py` | 算法与评分分开读取 |
| `examples/` | 运动积木的对照示例入口，不进场景自动发现 |
| `generate.py` | 生成数据集、自检和记录版本 |
| `run_algorithm.py` | 模拟和真实 tactical 均调用 predict(observations, metadata, config) |
| `evaluate.py` | 仅对模拟答案逐片段评分 |
| `view.py`、`viewer.html` | 完整干净轨迹、答案与预测的独立 HTML 查看器 |
| `../observations/` | 共同结构校验与真实 tactical ATD 加载器 |

算法接入模板：[algorithms/_template/predict.py](../algorithms/_template/predict.py)。

## 两条红线

1. 算法只读 `observations.csv` 和 `metadata.json` 中的观测元信息，不读干净档、答案、剧本、事件、场景名或生成清单；不传入 game_state。接口分离不是操作系统权限隔离。
2. 不用比赛的公开答案或人工标注构造场景（见 [AGENTS.md](../AGENTS.md)）。
