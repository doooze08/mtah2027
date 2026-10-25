# experiments/

一次实验 = 一个目录，只放**配置和记录**（小文本，提交到 Git）。结果文件放 `outputs/`（不提交）。

```
experiments/
├─ _template/
│  ├─ config.yaml        实验配置模板
│  └─ NOTES.md           实验记录模板
└─ <experiment_id>/
   ├─ config.yaml        算法名 + 参数 + 数据源（完整可复现）
   └─ NOTES.md           目的、结果（spellF1 / macroF1）、结论
```

## 命名：`<YYYYMMDD>_<algo_name>_<short_desc>`

例如 `20261025_ball_owner_hmm_window50`。同一个名字在 `outputs/` 中对应同名结果目录：

```
experiments/20261025_ball_owner_hmm_window50/   ← 配置 + 记录（提交）
outputs/20261025_ball_owner_hmm_window50/       ← 提交文件、评测报告、日志（不提交）
```

## 规则

- 用 `scripts/new_experiment.sh <algo_name> <short_desc>` 创建，自动生成两个对应目录。
- 实验跑完后**不要修改** `config.yaml`；改参数就新建一个实验，保证每条结果都能追溯。
- 结果数字写进 `NOTES.md`，这是团队对比结果的唯一记录（`outputs/` 不在 Git 里）。
- 每人只修改自己创建的实验目录，避免冲突。
