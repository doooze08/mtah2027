# 基础状态机最终检查

算法和配置在 `freeze.json` 中以 SHA-256 冻结，冻结后不再根据最终集或真实比赛修改。
开发集种子 120–124；最终集预先指定种子 901–905，TI01、HD01、BP01–BP03 各 5 个故事及镜像，
共 50 段。两个集合的故事种子不重叠，但使用同一场景生成模型，不代表独立现实分布。

执行一次检查：

```bash
.venv/bin/python experiments/20261108_sustained_control_final/check_once.py
```

脚本先验证冻结校验和，在 outputs 中排他创建运行标记，再生成最终集、运行一次预测并评分。
已有标记会终止，不重跑最终集，不根据结果继续修改；若失败，保留失败结论。
评分程序可以重读既有预测，不重复运行算法。详细结果待此次运行后填入。

## 真实比赛本地命令

使用本地已有 `.venv`，参数与最终检查相同。`--data-dir` 指向含 tactical/ 的数据根目录。

```bash
.venv/bin/python -m simulation.run_algorithm --experiment 20261108_sustained_control_final --tactical --data-dir /absolute/path/to/data
.venv/bin/python evaluation/validate_submission.py outputs/20261108_sustained_control_final/submission/sustained_control.csv
# 可选：公开五分钟仅检查评分流程，禁止据此调整算法或参数
bash scripts/evaluate.sh 20261108_sustained_control_final
```

预期输出 CSV：199,319 行数据（另加表头），列为 frame,label，帧 0..199318，标签 H/A/D；
官方校验打印 OK 和 199319 rows。格式通过不代表标签正确。
本轮真实跟踪仅用于全量运行与格式验收；公开评分不用于选择或调整。

球 NaN 专项策略：**未处理**，保留上一状态；不插值。中途裁判停表：**未处理**。
初始等待／合法重启依赖位置假设，真实位置无法证明裁判许可；无球高时不能保证区分空中投影与脚下控制。
参数、机制及重新评估条件见开发记录与算法 README。
