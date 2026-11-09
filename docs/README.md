# docs/

团队自己的项目文档。官方文档保留在根目录（`README.md`、`CHALLENGE.md`、`DATA.md`、`EVALUATION.md`、
`SUBMISSION.md`、`RULES.md`、`FAQ.md`、`OVERVIEW.md`），这里不复制、不改写。

每类信息只放一处：

| 信息 | 放在哪里 |
|---|---|
| 硬性规则、目录地图、常用命令 | 根目录 [AGENTS.md](../AGENTS.md) |
| 重要决策：背景、决定、取舍、重新评估条件 | [decisions/](decisions/) |
| 数据与算法认知：实测 / 推断 / 未知，指向证据 | [FINDINGS.md](FINDINGS.md) |
| 算法输入的数据契约 | [OBSERVATIONS.md](OBSERVATIONS.md) |
| 较长的调研记录 | [research/](research/) |
| 实验规范 | [experiments/README.md](../experiments/README.md) |
| 每个实验的数字和结论 | `experiments/<id>/NOTES.md` |
| 模拟器用法、积木、场景规格 | [simulation/README.md](../simulation/README.md)、[MOTION.md](../simulation/MOTION.md)、[SCENARIOS.md](../simulation/scenarios/SCENARIOS.md) |
| 分支、PR、协作 | [CONTRIBUTING.md](CONTRIBUTING.md) |

PR 的验收过程只写在 PR 描述中，不进仓库文档。

| 文档 | 内容 |
|---|---|
| [decisions/ADR-001-ATD-OBSERVATIONS.md](decisions/ADR-001-ATD-OBSERVATIONS.md) | 模拟与真实比赛共用 ATD 输入和算法入口 |
| [decisions/ADR-002-INPUT-SOURCES.md](decisions/ADR-002-INPUT-SOURCES.md) | 先做跟踪坐标核心，后续引入 Smart Tagging 和录像证据 |
| [FINDINGS.md](FINDINGS.md) | 跟踪质量、缺球、官方 D 含义、外部数据和算法现状 |
| [OBSERVATIONS.md](OBSERVATIONS.md) | 141 列契约和真实 ATD 本地加载 |
| [research/EXTERNAL_DATA.md](research/EXTERNAL_DATA.md) | 外部公开跟踪数据能否用作测试集 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 环境、分支、PR 与目录归属 |
