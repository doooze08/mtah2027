# <algo_name>

- **负责人**：@github-handle
- **状态**：draft / active / archived

## 思路

一两段话说明方法。

## 输入 / 输出

- 输入：`predict(observations, metadata, config)`；仅 tactical ATD 格式观测，见 [统一观测接口](../../docs/OBSERVATIONS.md)
- 输出：与输入帧数相同的标签序列（真实全场 199,319 帧），由运行器写 CSV；标签 `H` / `A` / `D` / `X`（见 [SUBMISSION.md](../../SUBMISSION.md)）

## 额外依赖

除 `requirements.txt` 外需要的包（如有）。

## 相关实验

- `experiments/<experiment_id>/`
