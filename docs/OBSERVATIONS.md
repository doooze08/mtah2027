# 统一观测接口

依据：[ADR-001](decisions/ADR-001-ATD-OBSERVATIONS.md)。本版本只统一格式和调用方式，不加入观测缺陷。
真实与模拟均使用 `predict(observations, metadata, config)`，返回与输入等长的 `H/A/D/X` 序列。
运行器负责读取、校验和写 CSV。算法不自行读取文件。

## 数据契约

`observations` 为 pandas DataFrame。pandas 是本项目已有的表格处理库。
每帧一行，严格按以下顺序排列 **141 列**：

```text
frame,ball_x,ball_y,1_x,1_y,1_s,2_x,2_y,2_s,…,46_x,46_y,46_s
```

- `frame`：整数，连续 `0..n-1`，25 fps。真实 ATD 的 `frame_id` 减 1，不使用半场偏移。
- `*_x, *_y`：无量纲，球场边界分别是 0 和 1。场外值可超出此区间，原样保留；缺失为 NaN，不插值、不裁切。
- `<slot>_s`：球员平面速度，m/s，非负或 NaN。真实使用 kloppy 的原始 ATD 速度；模拟由位置计算。
- 无球高、裁判信号、稳定身份、事件或场景字段；球也不附加速度列。

`metadata` 是仅含以下 4 项的 Python 字典：

```python
{
    "slot_teams": {"1": "H", "2": "A", ... , "46": "A"},
    "pitch_length": 105.0,  # m
    "pitch_width": 68.0,    # m
    "fps": 25
}
```

`slot_teams` 包含全部 46 个字符串槽位键，每个值均为 `H` 或 `A`，未使用槽位也有球队归属。
真实球队从 XML 元信息读取，不从槽位号码猜测。模拟随机分配 24 个 H 槽位和 22 个 A 槽位，
与本地真实 XML 的球队槽位数一致，各队只有 11 个槽位有位置。
槽位不是稳定球员身份，真实追踪可能在同一槽位换人。
米制距离为 `sqrt((Δx·pitch_length)² + (Δy·pitch_width)²)`。
真实球场尺寸取 kloppy XML 元信息，预期为 105 × 68 m；不混用 `games.py` 的 105.3 m。

模拟 `p01–p22` 每片段随机映射至 22 个不同槽位；其余 24 槽位全为 NaN。
映射直接由故事种子确定，同种子使用相同映射；片段内不交换，不向算法暴露对象与槽位的对应关系。
模拟速度为 `s[f] = 25·hypot(x_m[f]-x_m[f-1], y_m[f]-y_m[f-1])`。
首帧使用第 0–1 帧的前向差分；若只有 1 帧则为 0。两种来源的速度估计误差不保证相同。

## 真实 ATD：本地验证

使用已有 `.venv`。若该环境没有 kloppy，安装仓库已固定的 `kloppy==3.18.0`；无需新建环境。
以下命令只读取 tactical TXT/XML，不读取比赛答案、Smart Tagging 或视频：

```bash
# 仅在缺包时执行；PyYAML 是现有运行器所需依赖
.venv/bin/python -m pip install 'kloppy==3.18.0' PyYAML

# 数据在本仓库默认 data/ 时
.venv/bin/python -m observations.atd

# 或显式提供包含 tactical/ 的数据根目录
.venv/bin/python -m observations.atd --data-dir /absolute/path/to/data

# 使用同一算法入口生成真实全场 X；不做公开答案评分
.venv/bin/python -m simulation.run_algorithm \
  --experiment 20261107_placeholder_atd_interface --tactical \
  --data-dir /absolute/path/to/data
.venv/bin/python evaluation/validate_submission.py \
  outputs/20261107_placeholder_atd_interface/submission/placeholder.csv
```

加载器通过 `games.require()` 定位文件，使用 kloppy 读取原生坐标；显式检查仅保留帧数、连续帧号、
输出列名和顺序。元信息直接传递，不重复检查速度、坐标范围或球队；缺列由 pandas 抛错。
全量 kloppy 加载可能耗时数分钟、使用数 GB 内存。

预期诊断输出为 JSON：`rows=199319`、`column_count=141`、`frame_range=[0,199318]`，
`columns` 与上面的完整列序一致。`slot_teams` 有 46 项且来自 XML 主客队元信息，
`pitch_length=105`、`pitch_width=68`、`fps=25`。
`coordinate_range` 用归一化单位报告实际有限值范围；场内在 0–1，场外允许越界，
`coordinate_values_outside_pitch` 单独计数。`speed_range_m_s` 的下限应 ≥0，上限由实际数据决定，
不设未经验证的速度上限。缺失值保持 NaN，`ball_missing_frames` 预期约占 43%（依据 DATA.md，
实际数量以本地输出为准）。输出 CSV 应为 199,319 行（另加 1 行表头），标签全部为 X。

Mac 本地全量验证结果（行数、槽位、缺球、耗时和内存）见
[复核实验记录](../experiments/20261107_placeholder_atd_review/NOTES.md)。

## 模拟验证与迁移

命令见 [simulation/README.md](../simulation/README.md)。算法读取器只打开 `observations.csv` 与
`metadata.json`；运输文件中的 `clip` 分组键会先移除，算法只看到 141 列。
旧长表和 `game_state.csv` 数据集不自动迁移；用新编号重新生成，不覆盖已有数据。
查看器不兼容旧数据集，只读取新格式的 debug 干净档。`nearest_player` 已停用，旧实验不改写。

```bash
.venv/bin/python -m unittest discover -s tests -v
```

单元测试使用合成轨迹和 kloppy 对象：验证全部槽位球队、随机映射、位置不变、5 m/s 差分速度、
NaN、界外坐标和真实加载器调用路径；不为删除的防护保留测试。`debug/`、答案目录的分离是接口约定，
不是文件权限隔离；当前实现不声称能阻止恶意算法自行打开其他文件。
