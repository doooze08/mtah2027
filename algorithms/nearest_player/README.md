# nearest_player

状态：**停用，保留历史记录**。旧实验 `20261028_nearest_player_sim_skeleton` 不修改。
旧实现把最近球员等同于实际控制，并直接使用理想裁判信号 `play_live` 决定 D。
真实 tactical ATD 不提供该信号；旧长表和 `predict_clip()` 也不符合统一接口。

当前仅保留统一签名的报错入口，阻止旧实验静默运行。历史实现可由 Git 历史检索。
本次没有把它迁移成新的控球算法；端到端格式冒烟测试改用 `placeholder`。
依据见 [ADR-001](../../docs/ADR-001-ATD-OBSERVATIONS.md)。
