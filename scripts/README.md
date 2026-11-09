# scripts/

运行和测试脚本。都从任意目录可调用（内部按仓库根目录定位），优先使用 `.venv/bin/python`。

| 脚本 | 作用 |
|---|---|
| `setup_env.sh [--starter]` | 创建 `.venv` 并安装官方 `requirements.txt`（或 `requirements-starter.txt`） |
| `new_experiment.sh <algo> <desc>` | 生成 `experiments/<id>/` 和 `outputs/<id>/` |
| `run_simulation.sh <id> <dataset_id>` | 用实验配置里的算法跑模拟数据集并逐片段评分（模拟答案，不涉及比赛答案） |
| `evaluate.sh <id> [args]` | 用**官方** `validate_submission.py` + `run_evaluation.py` 评测 `outputs/<id>/submission/*.csv` |

约定：

- 脚本只调用官方代码，不复制、不修改 `evaluation/` 和 `starter/`。
- 新脚本用 `动词_对象.sh` / `.py` 命名，开头注释写清用法。
- 和单个算法强相关的运行逻辑放在 `algorithms/<algo>/`，这里只放通用脚本。
