# nearest_player

- **负责人**：@github-handle
- **状态**：active（仅模拟测试）

## 思路

活球时，离球最近（水平距离）的球员所在球队即为控球队；`play_live=0` 时输出 D。
这是模拟测试流程的冒烟用参照算法，故意把“最近”当成“控制”。HD01 这类场景就是为抓这个错误设计的：
它在 HD01 上判对，说明场景有漏洞。

## 输入 / 输出

- 输入：`predict_clip(observations, game_state, config)`，见 `algorithms/_template/predict.py`
- 输出：每个模拟片段每帧一个标签 `H` / `A` / `D`
- `predict(config)`（真实比赛）未实现

## 相关实验

- `experiments/20261028_nearest_player_sim_skeleton/`
