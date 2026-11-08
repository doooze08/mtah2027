# placeholder

状态：接口冒烟测试专用。唯一入口为 `predict(observations, metadata, config)`。
每个输入帧输出 X，无参数，不尝试判断控球。真实与模拟使用同一代码。
全 X 的低评分属于预期，不用它选择算法或衡量模拟器的准确程度。

运行方式见 [统一观测接口](../../docs/OBSERVATIONS.md)。
