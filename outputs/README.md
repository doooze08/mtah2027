# outputs/

生成的模拟测试集和实验输出，**整个目录不进 Git**（只提交本 README 和 `.gitkeep`）。

提交文件就是整场比赛的完整标签，属于不能公开的内容，见 [evaluation/results/README.md](../evaluation/results/README.md)。

```
outputs/
├─ simulation_sets/<dataset_id>/    固定的模拟输入、正确答案及生成清单
└─ <experiment_id>/                 与 experiments/<experiment_id>/ 同名
   ├─ submission/<experiment_id>.csv  frame,label，199,319 行
   ├─ eval/                          scripts/evaluate.sh 写入：scoreboard.csv、reports/
   ├─ simulation/<dataset_id>/        该算法在固定模拟测试集上的预测和报告
   └─ logs/                          运行日志、中间文件
```

- 只把 `submission/` 下的 CSV 交给评测（评测会给目录里的每个 `*.csv` 打分）。
- 需要分享结果时，把数字写进 `experiments/<experiment_id>/NOTES.md`，不要提交 CSV。
- `simulation_sets` 是保留目录名。模拟测试的结构与公平比较约定见 [simulation/README.md](../simulation/README.md)；模拟生成器和运行入口尚未实现。
