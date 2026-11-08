# algorithms/

每个算法一个独立子目录（Python 包），互不依赖，可并行开发。

```
algorithms/
├─ __init__.py
├─ _template/            新算法模板，复制后改名使用（不要直接修改）
└─ <algo_name>/          例如 nearest_player_hmm/、spell_segmentation/
   ├─ __init__.py
   ├─ README.md          思路、依赖、负责人
   └─ predict.py         入口：predict(...) -> 每帧标签（H/A/D/X）
```

## 约定

- **命名**：`snake_case`，描述方法本身（如 `ball_owner_hmm`），不要用人名或日期。
- **独立性**：算法之间不要互相 import；共用工具如确有需要，再统一抽到 `algorithms/common/`。
- **官方代码只读**：可以 `from games import asset_paths`、`from starter.load_atd import ...` 复用官方加载器，
  但不要修改 `starter/`、`evaluation/`、`games.py`。
- **数据读写交给运行器**：算法只接收 `predict(observations, metadata, config)` 的内存输入，返回每帧标签；格式见 [统一观测接口](../docs/OBSERVATIONS.md)。不读取文件或写结果。
- **超参数不写死**：放在 `experiments/<experiment_id>/config.yaml`，由脚本传入。

新建算法：

```bash
cp -r algorithms/_template algorithms/<algo_name>
```
