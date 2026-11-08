# 统一 ATD 观测接口冒烟测试

日期：2026-11-07。目的：只验证格式、输入边界与端到端运行，不验证控球准确率。
决策提交：`8b70829`。实现版本：本记录所在提交；完整代码以 Git 提交记录为准。
配置固定：`placeholder`，无参数；未修改任何历史实验。

## 输入与产物

- dataset：`atd_interface_smoke_20261107`，TI01、HD01 各 1 个故事、主客互换，共 4 片段；base seed=0。
- 观测版本：`atd_format_v1_no_defects`。球场 105 × 68 m，25 fps；片段内槽位不互换。
- 原始生成数据：`outputs/simulation_sets/atd_interface_smoke_20261107/`。
- 预测、报告和查看器：`outputs/20261107_placeholder_atd_interface/simulation/atd_interface_smoke_20261107/`。
- 环境：复用 `/Users/yyluo/Projects/mtah2027/.venv/bin/python`；Python 3.9.6，kloppy 3.18.0。
  numpy、pandas 版本由生成清单记录。未安装新依赖。

## 运行与实测

仓库根目录，令 `PY` 为已有虚拟环境的 Python 解释器：

```bash
"$PY" -m simulation.generate --dataset-id atd_interface_smoke_20261107 --subtypes TI01,HD01
"$PY" -m simulation.run_algorithm --experiment 20261107_placeholder_atd_interface --dataset atd_interface_smoke_20261107
"$PY" -m simulation.evaluate --experiment 20261107_placeholder_atd_interface --dataset atd_interface_smoke_20261107
"$PY" -m simulation.view --dataset atd_interface_smoke_20261107 --experiment 20261107_placeholder_atd_interface
"$PY" -m unittest discover -s tests -v
```

上述 dataset 已生成，不重用编号重新生成。复现新生成过程时换新 dataset id，并更换后续命令参数。

| 检查 | 实测结果 |
|---|---|
| 场景原自检、写盘后答案从事件重推 | 4/4 通过 |
| 片段长度 | 303、207、207、303 帧；合计 1,020 帧 |
| 算法输入列数 | 每片段 141 列；CSV 含 clip 分组键时 142 列 |
| 可见球员 | 每帧 22 个活动槽位；24 个未用槽位为 NaN |
| 球缺失 | 0 帧；符合本次无缺陷范围 |
| 输出 | 1,020 行，全部 X；帧号与片段逐一对齐 |
| 模拟评分链路 | 正常生成 per_clip.csv、report.md；全 X 的 4 个核心窗口全部失败，属于预期 |
| 映射复现、球队归属、速度单位 | 契约测试通过；合成 3/4 m/s 分量得到 5 m/s，含首帧 |
| 实际 kloppy 加载路径 | 自制 3 帧 EPTS XML/TXT 经 kloppy 读取，再适配并从真实模式运行器写出 3 行 X |
| 真实路径的 NaN 和场外值 | 合成夹具中的 NaN、x=1.05、y=-0.02、原始速度 7.5 m/s 保留 |
| 算法文件读取边界 | 移走答案、事件、样本和 debug 干净档后仍能加载；只打开观测 CSV 和 metadata.json |
| 测试集 | 4 项 unittest 通过，包含上述契约、磁盘、查看器数据和实际 kloppy 测试 |
| 查看器 | 导出 4 片段，JSON 无非法 NaN；高度提示存在；JavaScript 通过 node --check |
| 页面视觉检查 | 未完成：浏览器安全策略禁止 file://；未绕过限制 |
| 差异检查 | git diff --check 通过 |

## 限制

没有读取真实比赛文件或公开答案。合成 EPTS 证明适配路径可运行，不证明实际比赛导出已通过全量检查。
真实文件的本地命令与预期见 [OBSERVATIONS.md](../../docs/OBSERVATIONS.md)。
当前成绩不能评估观测缺陷，也不能推断真实比赛准确率。
生成时清单记录 dirty=true，表示实现尚未提交；源代码以本实验记录所在提交为复现依据。
