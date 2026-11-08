# LC／DC 场景与运动随机化验证记录

日期：2026-11-08。范围：参数随机化、LC01–LC05、DC01–DC03、文档与关键行为测试。
未修改观测层、算法或实验目录；未读取比赛追踪、公开答案或比赛评分。

## 验证结果

| 验证 | 数量与结果 |
|---|---|
| 新子型 | 8 × 10 种子（0–9）× 2 主客镜像 = 160 个片段，全部自检通过 |
| BP 回归 | 3 × 20 种子（0–19）× 2 主客镜像 = 120 个片段，全部自检通过；仍覆盖 2、3、4 次传球，片段时长 10–20 s |
| 原有子型 | TI01／HD01 各 10 种子 × 2 主客镜像 = 40 个片段，全部自检通过 |
| 单元测试 | `unittest discover -s tests -v`，26 项通过；含 160 个新片段的故事、几何、镜像与边界检查 |
| 查看器 | 种子 0、H 发起，每个新增子型 1 段，共 8 段；抽查关键帧，浏览器控制台无警告或错误 |

答案始终由剧本事件生成；所有落地、弹跳和被动触球本身均不触发换权。
新事件边界为 `ceil(25t)`；真实接球起点立即换权，不等停球结束。

| 定量项目 | 10 个故事的实测范围 | 要求 |
|---|---|---|
| LC01 过顶采样帧水平距离 | 0.026–0.311 m | <1.3 m |
| LC01 同一帧球心高度 | 4.092–7.616 m | 规格 3–8 m，同时满足 >2 m |
| LC04 首次落地至控制 | 1.504–1.966 s | 0.5–2.0 s，包含弹跳 |
| DC01 擦碰点至下一次 H 触球位移 | 0.699–1.911 m | 0.5–2 m |
| DC02 擦碰后位移 | 2.398–4.823 m | 2–5 m |
| DC02 擦碰至收回球的追逐 | 0.499–0.953 s | 0.4–1.2 s |
| 新子型地滚减速度 | 1.427–2.943 m/s² | 1–3 m/s² |
| 竖直恢复系数 | 0.557–0.671 | 0.55–0.70 |
| 首次／后续水平保留 | 0.557–0.693／0.855–0.966 | 0.55–0.70／0.85–1.00 |
| 脚下接球速度 | 3.118–9.863 m/s | 3–10 m/s |
| 停球时间 | 0.112–0.298 s | 0.1–0.3 s |

范围按 H 故事统计；A 版本由同种子旋转 180°，不算额外独立故事。
自检包括球员速度 ≤10 m/s、加速度 ≤12 m/s²、球速 ≤35 m/s、非接触自由加速度 ≤20 m/s²、
触球可达、事件顺序、连续越界和事件答案一致性。脚下停球及真实碰撞只按现有规则排除相应加速度差分窗口。

## TI01／HD01 新旧逐字节比较

基准为任务起点 `origin/main`：`0f9dee2`（PR #9 合并点）。本地 `main` 当时落后 19 个提交，
仍使用旧观测格式，因此不把该陈旧分支当作本轮兼容性基准。

只把基准中的 `simulation/`、`observations/` 导出到临时目录，用同一 Python 环境分别运行：

```bash
.venv/bin/python -m simulation.generate --dataset-id <new_id> \
  --subtypes TI01,HD01 --stories 10 --seed 0
```

比较 40 个片段对应的数据集文件：`observations.csv`、`metadata.json`、
`debug/clean_positions.csv`、`truth.csv`、`events.csv`、`samples.csv`，6 个文件全部逐字节相同。
运行清单的 dataset ID、命令、Git 状态和生成时间应不同，不作为轨迹一致性证据。
此次比较是一次性验收，没有把旧输出哈希写死进测试。

准备 PR 时远端 main 已前进到 `105ad7b`（PR #10）。相对 `0f9dee2` 只新增／修改球缺失统计实验和其测试，
`simulation/`、`observations/` 均无差异，因此上述模拟输出比较仍覆盖该 main 的生成逻辑。

BP01–BP03 显式接入故事抽样器，到脚速度与停球时间在故事内复用，减速度从固定 2 改为 1–3 m/s²。
新增抽样改变后续 RNG 序列；新轨迹、片段长度和部分事件边界帧会变化，答案序列不变。
旧数据不覆盖；算法比较需要使用同一新数据集。

## 查看器抽查记录

查看数据集：`lc_dc_preview_20261108`，种子 0，各子型 H/A 各 1 段；以下抽查 H 版本。
使用既有离线查看器，不运行算法。截图位于 `outputs/lc_dc_visual_review/screenshots/`，不进 Git。
这是关键帧和轨迹曲线检查，不是完整比赛视觉验证，也不表示算法准确率。

| 子型／片段 | 检查帧 | 观察结果 |
|---|---|---|
| LC01／c005 | f142 | 球与 A 平面重叠附近，z=6.13 m，标签 H；高度曲线随后落地、回弹并地滚 |
| LC02／c001 | f195 | 首次反弹峰附近，球越过已到位的 A，z=3.09 m，仍为 H；f219 才由 H 接球 |
| LC03／c006 | f209 | 地滚到脚，z=0.11 m，A 在停球起点取得控制；停球区间未把换权后移 |
| LC04／c011 | f195 | 两人接近并追球，弹跳尚未结束，仍为 H；换权标记在 f210 |
| LC05／c014 | f164 | 球完全越出边线，z=0.32 m，转 D；飞向边线期间保留 H |
| DC01／c004 | f173 | f172 被动触球后球偏转，z=0.11 m，仍为 H；f174 由 H 再次触球 |
| DC02／c010 | f184 | f178 擦碰后球在双方附近滚动、双方追逐，保持 H；f191 H 收回 |
| DC03／c009 | f178、f205 | f174 第一次擦碰后仍 H；f183 第二名 A 停球才换 A，f205 可见 A 已带走 |

球员以点表示，查看器不能验证脚／腿姿态或身体接触；物理一致性同时依赖连续轨迹和速度自检。
球高仅在 debug／查看器中出现，算法仍只能看到二维 ATD 观测。

## 本地产物与复现

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m simulation.generate --dataset-id lc_dc_acceptance_20261108 \
  --subtypes LC01,LC02,LC03,LC04,LC05,DC01,DC02,DC03 --stories 10 --seed 0
.venv/bin/python -m simulation.generate --dataset-id bp_motion_acceptance_20261108 \
  --subtypes BP01,BP02,BP03 --stories 20 --seed 0
.venv/bin/python -m simulation.generate --dataset-id lc_dc_preview_20261108 \
  --subtypes LC01,LC02,LC03,LC04,LC05,DC01,DC02,DC03 --stories 1 --seed 0
.venv/bin/python -m simulation.view --dataset lc_dc_preview_20261108 --experiment lc_dc_visual_review
```

已有编号不能重用。当前工作区 `.venv` 不存在时，本轮复用了主项目已有环境的解释器；未安装依赖。
完整数值审计保存在 `outputs/lc_dc_visual_review/audit.json`；查看器在
`outputs/lc_dc_visual_review/simulation/lc_dc_preview_20261108/viewer.html`，可直接离线打开。
