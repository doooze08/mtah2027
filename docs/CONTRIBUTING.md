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

## 3. 分支与 PR

- `main` 只通过 PR 合并；合并前由负责人或评审者在临时副本中复现关键验证。
- 工作分支按执行者和主题命名，例如 `codex/<topic>`、`claude/<topic>`；一个 PR 只做一件事。
- PR 描述写清改动、验证方式和限制；验收过程只写在 PR 描述里，不另建仓库文档。
- 已合并的 PR 不再追加提交；后续修改从最新 `main` 开新分支。

## 4. 目录归属（减少冲突）

| 路径 | 谁改 |
|---|---|
| `algorithms/<algo_name>/` | 该算法负责人 |
| `experiments/<experiment_id>/` | 实验创建者 |
| `scripts/`、`docs/`、`.gitignore` | 任何人，走 PR |
| `starter/`、`evaluation/`、`games.py`、根目录官方 `*.md` | **不修改**（只随 upstream 同步） |

## 5. 不要提交

比赛数据、完整比赛标签、生成结果、模型权重和密钥不进 Git，完整规则见 [AGENTS.md](../AGENTS.md)。
`.gitignore` 已覆盖这些内容；提交前用 `git status` 确认。

## 6. 提交前检查

```bash
python3 -m unittest discover -s tests   # 单元测试
git status                              # 确认没有数据/结果文件
```
