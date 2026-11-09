# 项目指导

## 硬性规则（IMPORTANT）

以下规则可能影响参赛资格，优先于便利性和分数提升。完整依据见
[RULES.md](RULES.md)、[EVALUATION.md](EVALUATION.md)、[OVERVIEW.md](OVERVIEW.md)；
数据使用范围以报名时接受的条款为准。

- **不得使用公开五分钟答案训练、调参或选择算法。**
  答案是 `evaluation/gt/BAR-ATH_possession_gt_public.csv`，配套统计是
  `evaluation/gt/BAR-ATH_possession_gt_public_meta.json`。
  只允许用于检查帧对齐、标签含义、文件和评测流程。不得把这些答案、统计或
  公开窗口评分反馈接入自动搜索、参数扫描、候选排序或提前停止逻辑。
  该限制也适用于复制件和派生报告，包括 `evaluation/scoreboard.csv`、
  `evaluation/reports/`、`outputs/<experiment_id>/eval/` 中的公开窗口结果。
- **不得对本场参赛比赛人工标注、人工修正标签或追踪，或将此类数据用于训练、验证。**
  不得引入任何来源的人工制作的本场事件数据、校正追踪或隐藏答案。
  可以观看比赛、理解数据、设计通用特征；不得写入针对本场特定帧的修正规则或常数。
  官方公布的比赛边界和帧对齐常数可按现有代码使用。
- 不得使用私有全场答案或其派生信息；若意外发现这类文件，不读取或用于实验。
  `evaluation/gt/` 不是可任意用于训练的数据目录。
- 模拟正确答案 `outputs/simulation_sets/<dataset_id>/truth.csv` 仅供评分读取，
  不得作为算法输入或特征。模拟器不得调用候选控球算法生成正确答案。
  模拟成绩只代表明确的模拟假设下的表现，不代表真实比赛成绩。
- 预测必须由程序生成，并能从相同输入、代码和配置复现。遇到规则不明的情况，
  明确指出具体疑点，不擅自把高分解释为合规。

## 项目是什么

More than a Hack 2027 第一阶段：为 Barcelona 对 Athletic Club 的战术录像逐帧判断控球状态。
提交文件为 `frame,label`，共 199,319 行，帧编号 `0..199318`，帧率 25 fps。
`H` 是主队活球控球，`A` 是客队活球控球，`D` 是死球，`X` 是放弃判断。
活球时的争抢和松散球保留上一支实际控制球队，不能把最近球员直接等同于控制权。

排名主要依据 `spellF1`（球队正确的控球时间段匹配），`macroF1` 是逐帧指标及第一并列判据。
完整指标定义以 `evaluation/possession_metrics.py` 为准。公开答案只有开赛后五分钟，
不能用其分数推断全场排名。

## 输入、目录与修改边界

| 路径 | 用途和约定 |
|---|---|
| `data/tactical/` | 参考时间轴。`BAR-ATH_tactical_atd.txt` 是逐帧球员／球位置和速度；`BAR-ATH_tactical_atd.xml` 是球队及追踪元信息 |
| `data/broadcast/` | 可选转播输入，与 tactical 不同步，不能直接混用帧编号 |
| `algorithms/` | 自有算法，每个一个子目录。真实比赛和模拟片段统一入口为 `predict(observations, metadata, config)`；输入是 ATD 宽表、槽位球队表、球场尺寸和帧率，不含 z、裁判信号或球员身份。约定见 `algorithms/_template/predict.py`、`docs/OBSERVATIONS.md` |
| `simulation/` | 模拟器和场景。已实现 TI01、HD01、BP01–BP03、LC01–LC05、DC01–DC03、ST01–ST04，共 17 个子型；可选死球三策略缺球和活球短缺。用法和文件格式见 `simulation/README.md` |
| `outputs/simulation_sets/<dataset_id>/` | 固定模拟测试集；观测、正确答案和生成清单分别保存，不进 Git |
| `experiments/<experiment_id>/` | 可追踪的配置和结论，进 Git；已完成实验不覆盖配置，参数变化新建实验 |
| `outputs/<experiment_id>/` | 预测、评分和日志，不进 Git；模拟结果放 `simulation/<dataset_id>/` 子目录 |
| `scripts/`、`docs/` | 团队通用运行入口、说明和决策记录 |
| `starter/`、`evaluation/`、`games.py` | 官方加载器、baseline 和评分工具；复用但不修改，只随官方更新同步 |
| 根目录官方文档 | `README.md`、`CHALLENGE.md`、`DATA.md`、`EVALUATION.md`、`SUBMISSION.md`、`RULES.md`、`FAQ.md`、`OVERVIEW.md` 不改写；团队指导写在本文件或 `docs/` |

ATD 坐标归一化为 0–1，距离计算需要按球场长宽换算；缺失位置为 NaN。
ATD 的 `frame_id` 从 1 开始，提交帧从 0 开始。追踪编号不是稳定球员身份。
细节见 [DATA.md](DATA.md)，路径通过 `games.py` 获取，不到处硬编码。

## 运行方式

以下命令从仓库根目录执行。优先使用现有 `.venv`，不无故重建环境。

```bash
# 仅在缺少环境时安装 baseline／评分所需依赖
bash scripts/setup_env.sh

# 读取 tactical 原始追踪，生成四个官方 baseline；不读取答案
.venv/bin/python starter/baseline.py --out outputs/baseline_reproduction/submission

# 校验行数、帧编号、标签；不做答案评分
.venv/bin/python evaluation/validate_submission.py outputs/baseline_reproduction/submission/baseline_raw.csv

# 校验并对公开五分钟评分：仅用于流程检查，禁止用于优化和选型
bash scripts/evaluate.sh baseline_reproduction
```

其他实验使用 `bash scripts/evaluate.sh <experiment_id>`，读取
`outputs/<experiment_id>/submission/*.csv`，写到对应的 `eval/`。

模拟测试：

```bash
# 生成数据集并自检；已有编号不会被覆盖
.venv/bin/python -m simulation.generate --dataset-id <dataset_id> --subtypes TI01,HD01

# 运行实验配置里的算法，并逐片段评分
bash scripts/run_simulation.sh <experiment_id> <dataset_id>
```

`scripts/evaluate.sh` 不会运行算法。不为尚未实现的功能提供假装可执行的命令。

## 技术判断与记录

- 严格区分实测、推断和未知。运行通过不等于准确；输出平滑不等于控球正确。
  不在缺少独立验证时宣称算法最优，不把同一模拟集反复运行当作新增验证样本。
- 重要决定记录理由、假设、验证方式及触发重新评估的条件；报告产物位置、运行方式、验证结果和限制。
- 代码、代码注释和提交信息用英文；团队文档用中文。

## 实验与版本管理

- 公平比较使用相同固定测试集；实验配置、数据校验和复现记录见 [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)。
- Git 只保存代码、配置、说明和实验结论。原始数据、生成预测／报告、模型权重、环境和密钥不加入 Git。
  官方原本跟踪的公开答案及四个 baseline 文件保留，不因全局排除规则删除。
- 保留其他队员或其他任务未提交的修改，不自动清理、暂存或提交不相关文件。
  分支、PR 和团队协作按 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) 执行；推送前检查实际提交清单。
