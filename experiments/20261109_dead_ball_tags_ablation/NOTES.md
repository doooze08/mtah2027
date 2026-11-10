# 标签保留／遗漏对照

一个实验目录保存 complete 和 none 两个运行分支；不再保留 v3/v5 等独立目录。
当前参数与开发定稿相同，仅改变传入的模拟标签。历史检查点留在 Git 历史。

复用开发集 12000–12004 的五种缺球条件、每组 170 段，禁止另生成故事比较。
complete 全保留模拟标签，none 全遗漏；两者均经同一个 simulation.run_algorithm 运行。

```bash
.venv/bin/python -B -m experiments.20261109_dead_ball_tags_dev.run_checks --split ablation
```

共享运行器 --variant complete/none 将预测、诊断和参数记录分别写入
outputs/20261109_dead_ball_tags_ablation/complete/ 和 none/；不会覆盖主实验或另一分支。
合成标签位于同一实验的 tags/<dataset>/ 下，JSON 只作为独立输入传给算法。
诊断报告位于各分支 simulation/<dataset>/diagnostics.json；不读取真实比赛或公开答案。

标签覆盖差异只在开发集上比较；不在新独立集补跑标签方案或据其选择参数。
