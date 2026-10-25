# 协作指南

## 1. 环境

```bash
scripts/setup_env.sh              # numpy + pandas，足够跑评测和 baseline
scripts/setup_env.sh --starter    # 需要 notebook 时
source .venv/bin/activate
python evaluation/run_evaluation.py   # 冒烟测试：应输出四个 baseline 的 scoreboard
```

比赛数据解压到 `data/`，或设置 `MTAH_DATA_DIR`（见 [data/README.md](../data/README.md)）。

## 2. Git remotes

```bash
git remote -v
# upstream  https://github.com/metrica-sports/more-than-a-hack-2027.git   官方仓库，只拉取
# origin    <团队仓库>                                                    日常推送
git fetch upstream && git merge upstream/main     # 同步官方更新
```

> 官方仓库是公开的。团队仓库建议设为 **Private**。

## 3. 分支

| 分支 | 用途 |
|---|---|
| `main` | 稳定版本，只通过 PR 合并 |
| `algo/<algo_name>` | 某个算法的开发 |
| `exp/<experiment_id>` | 只改实验配置/记录时可用 |
| `docs/<topic>`、`chore/<topic>` | 文档、脚本、工具 |

## 4. 目录归属（减少冲突）

| 路径 | 谁改 |
|---|---|
| `algorithms/<algo_name>/` | 该算法负责人 |
| `experiments/<experiment_id>/` | 实验创建者 |
| `scripts/`、`docs/`、`.gitignore` | 任何人，走 PR |
| `starter/`、`evaluation/`、`games.py`、根目录官方 `*.md` | **不修改**（只随 upstream 同步） |

## 5. 绝对不要提交

- `data/` 下的任何比赛数据（`.mp4`、ATD、homography、Smart Tagging）
- 任何完整比赛的标签 CSV（提交文件、`outputs/`）
- 模型权重、缓存、`.env` / 密钥

`.gitignore` 已覆盖以上内容。提交前用 `git status` 看一眼；如果某个数据文件出现在列表里，先补 `.gitignore`。

## 6. 提交前检查

```bash
scripts/evaluate.sh <experiment_id>     # 官方校验 + 评测
git status                              # 确认没有数据/结果文件
```
