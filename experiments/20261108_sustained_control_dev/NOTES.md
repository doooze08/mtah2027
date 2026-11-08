# 基础状态机开发记录

开发集 50/50 段全片逐帧正确：13,752 帧，0 错误。仅用于本轮开发，不作为最终独立检查。
基线 main 为 `39ebb28`（包含 PR #4 和 #5）。不修改模拟器、观测层或官方工具。

使用 `control_dev_20261108_s120`，TI01、HD01、BP01–BP03，每子型 5 个故事，
故事种子 120–124，每故事包含主客镜像。镜像与同一故事不拆分到最终集。
生成器自检 50 段通过，生成清单中的 simulation dirty=false。

采用用户指定的离线状态机，拒绝直接最近球员规则：距离只能提供候选，连续共同移动／静止才提供控制证据。
另一可行方式是只在接球帧建立控球；代价是现有合法重启后的传球飞行段均会错。
经用户确认，采用后续同队接球确认后回溯开场出脚／重新入场的规则。
收益是匹配本轮已有事件语义；失效方式是无法识别未获许可的重启。
此接口不变，后续可关闭 `infer_restarts` 或在新的实验替换规则；不必迁移数据。

开发中先检查距离和相对速度连续证据，再修正混合飞行／接球采样间隔造成的 1 帧提前，
并加入初始等待抑制、位置重启回溯和双方控制迹象冲突时保持原队。
只查看开发集模拟评分与逐帧差异；无真实比赛反馈、公开答案或其评分参与开发。
冻结数值见 config.yaml；局部速度变化阈值 0.1 m/s、接触起点容差 0.02 m 为代码内常数。
这些小阈值依赖无噪声轨迹，不是实际追踪精度声明。

| 子型 | 片段数 | 全片帧数 | 错误帧数 |
|---|---:|---:|---:|
| TI01 | 10 | 1704 | 0 |
| HD01 | 10 | 2732 | 0 |
| BP01 | 10 | 3008 | 0 |
| BP02 | 10 | 3352 | 0 |
| BP03 | 10 | 2956 | 0 |

算法输入从不包含答案；评分使用现有 `simulation.evaluate`。
详细逐片段评分在 `outputs/20261108_sustained_control_dev/simulation/control_dev_20261108_s120/`：
`report.md`、`per_clip.csv`。最终检查结果记录在相邻 final 实验。

复现（从仓库根目录，已有目录不覆盖；复建应换新编号）：

```bash
.venv/bin/python -m simulation.generate --dataset-id control_dev_20261108_s120 --subtypes TI01,HD01,BP01,BP02,BP03 --stories 5 --seed 120
.venv/bin/python -m simulation.run_algorithm --experiment 20261108_sustained_control_dev --dataset control_dev_20261108_s120
.venv/bin/python -m simulation.evaluate --experiment 20261108_sustained_control_dev --dataset control_dev_20261108_s120
```

本机实际复用 `/Users/yyluo/Projects/mtah2027/.venv/bin/python`。
球缺失专项处理：**未处理**，仅沿用上一状态；中途裁判停表：**未处理**。
重新评估条件：加入观测噪声、槽位跳变、曲线或慢速争抢、非法重启、独立新模拟族时。
模拟通过只证明既定干净运动假设，不推断真实比赛准确率。
