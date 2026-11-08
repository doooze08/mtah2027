# PR #4 复核：全部槽位球队、精简防护、真实文件验证

日期：2026-11-07。目标：关闭评审提出的 3 项问题，不改变观测缺陷范围或准确率验收依据。
实现版本以本记录所在提交为准；保留旧实验及其产物，不修改原记录。

## 改动

全部 46 个模拟槽位均有 H/A 球队。真实 tactical XML 实测为 24 个 H、22 个 A 槽位；
模拟采用相同数量并用故事种子随机排列槽位，各队放入 11 名球员，其余 24 个槽位的 x/y/s 全为 NaN。
不再有 None 球队，也不再混入 clip id 的哈希；同种子共享映射。
删除评审列出的元信息、数值、旧格式和重复防护；保留列名与顺序、连续帧号、真实帧数和预测长度检查。

## Mac 真实文件集成验证

从当前 worktree 根目录执行，使用已有虚拟环境；没有安装依赖：

```bash
/Users/yyluo/Projects/mtah2027/.venv/bin/python -m observations.atd \
  --data-dir /Users/yyluo/Projects/mtah2027/data
```

输入仅为 `games.require()` 定位的 tactical ATD XML/TXT。没有读取比赛答案、视频或 broadcast。
外层监控设定 600 s／8 GiB RSS 上限，正常退出，未触发停止条件。

| 项目 | 实测 |
|---|---|
| Python／kloppy | 3.9.6／3.18.0 |
| 行数／列数 | 199,319／141 |
| frame | 0..199318，连续 |
| 槽位元信息 | 46 项全部为 H/A；H=24，A=22 |
| 球场／帧率 | 105 × 68 m／25 fps |
| 坐标有限值范围 | −0.10713..1.48854，原样保留 |
| 场外坐标分量数 | 49,272（按 x/y 分量计数，不是帧数） |
| 速度有限值范围 | 0.00015743177209515125..11.29382610321045 m/s |
| 球缺失帧 | 85,831／199,319 = 43.06% |
| 耗时 | 72.3 s |
| 采样峰值 RSS | 4,908,417,024 bytes，约 4.57 GiB；每 2 s 采样 |
| 退出码 | 0 |

完整本地输出位于 `outputs/20261107_placeholder_atd_review/validation/`：
`atd_report.json`、`atd_load.log`、`run_stats.json`、`input_sha256.json`；均不进 Git。
该验证覆盖加载与格式，不代表真实比赛控球准确率。

## 模拟与测试

新建 `atd_interface_review_20261107`，TI01／HD01 各 1 个故事，主客互换，共 4 片段、1,020 帧。
base seed=0，观测版本为 `atd_format_v2_all_slot_teams_no_defects`。
每个片段的全部 46 槽位均有球队，活动槽位 22 个、无观测槽位 24 个；不加入噪声、缺球或槽位交换。

```bash
PY=/Users/yyluo/Projects/mtah2027/.venv/bin/python
"$PY" -m unittest discover -s tests -v
"$PY" -m simulation.generate --dataset-id atd_interface_review_20261107 --subtypes TI01,HD01
"$PY" -m simulation.run_algorithm --experiment 20261107_placeholder_atd_review --dataset atd_interface_review_20261107
"$PY" -m simulation.evaluate --experiment 20261107_placeholder_atd_review --dataset atd_interface_review_20261107
"$PY" -m simulation.view --dataset atd_interface_review_20261107 --experiment 20261107_placeholder_atd_review
```

已有数据集编号不能重复生成；需要重建时换新编号。
2 项单元测试通过，覆盖槽位映射、24/22 球队归属、各队 11 名活动球员、种子复现、5 m/s 速度、
NaN／场外坐标／球高剔除，以及实际 kloppy 对象的适配和加载器调用路径。
测试由 241 行减少至 110 行；删除的防护不再有专门测试。
模拟生成自检、全 X 预测、模拟评分、查看器导出均通过；全 X 的 4 个核心窗口失败属于预期。
结果位于 `outputs/20261107_placeholder_atd_review/simulation/atd_interface_review_20261107/`。
页面视觉检查不在本次复核中重试；此前 file:// 浏览器限制仍未解除。
