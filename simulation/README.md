# 模拟测试

在已知答案的虚拟比赛片段上检查控球算法：先在信息完整时验证逻辑，再逐步加入观测缺陷。
模拟成绩不代表真实比赛成绩。场景定义见 [CLEAN_CORNER_CASES_V1.md](scenarios/CLEAN_CORNER_CASES_V1.md)。

当前状态：只有场景规格，生成器、评分脚本和算法入口都还没有实现。

## 流程：三层分开

```text
剧本（事件）  ──►  干净轨迹 + 答案  ──►  观测层  ──►  算法  ──►  评分
                                        │
                                        └ V1 原样通过；之后在这里加噪声、丢球、ID 互换
```

观测层从第一版起就单独存在，即使暂时什么都不做。这样以后加缺陷时，剧本、答案和评分都不用改，
同一个干净片段也能和"加缺陷"版本直接对比。

## 文件放置

```text
simulation/scenarios/           场景规格，进 Git
outputs/simulation_sets/<id>/   生成的数据，不进 Git
    observations.csv            算法能看到的逐帧位置
    truth.csv                   逐帧答案 H/A/D，只给评分脚本
    samples.csv                 每个片段的场景、故事编号、种子
outputs/<experiment_id>/simulation/<id>/   预测和评分结果
```

每个样本记下故事编号和随机种子，以后要分开发集／保留集时按故事编号划分。

## 两条红线

1. 算法只读 `observations.csv`，不读答案、剧本或场景名。
2. 不用比赛的公开答案或人工标注构造场景（见 [AGENTS.md](../AGENTS.md)）。
