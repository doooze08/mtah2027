# 运动积木：带速地滚传球、停球与局部静止（PR 1）

本版新增地滚传球和显式停球。原抛物线 `kick_to()`、默认晃动、事件到标签的映射不变。
不修改观测层或算法接口，不使用比赛答案。弹跳与阵型跟随留待 PR 2。

## 带速地滚传球

下面是互斥的调用方式示例，不是一个连续剧本。

```python
# 方式一：指定到脚速度。剧本应先安排接球人的跑动。
b.roll_to(player=receiver, arrival_speed=6.0, deceleration=2.0)
b.event("control_start", team=receiver.team)  # 到脚这一刻，不能推迟到停球结束
b.trap(receiver, 0.2)                       # 0.2 s 内减速，向前滚动 0.6 m
b.hold(receiver, 1.0, still=True)

# 方式二：指定到脚时间，仍使用固定减速度，不强迫球到脚时速度为 0。
b.roll_to(1.5, player=receiver, deceleration=2.0)

# 无人接的球才直接滚到停止点，终点不虚构触球。
b.roll_to(point=(30.0, 69.0), arrival_speed=0.0, arrival_contact=False)
b.wait(2.0)
```

`seconds` 与 `arrival_speed` 二选一。默认减速度 a=2 m/s²，可逐次调用配置，球心恒为 0.11 m。
给定距离 d 与到脚速度 vf：`v0 = sqrt(vf² + 2ad)`，`T = 2d/(v0+vf)`。
给定 d 与 T：`v0 = d/T + aT/2`，`vf = d/T - aT/2`；vf<0 表示时长不可行，直接报错。
对运动中的接球人，以其到达时的位置求解传球时间，不把当前球员位置当作固定终点。

`GroundRoll` 在接球点仍保留速度；若没有后续触球动作，轨迹会继续按同一减速度滚到自然停止。
延长 `wait()` 只延长覆盖范围，不重算初速度或摩擦。2 m/s² 是本版的简化参数，不是本场草地的实测值。

## `trap(player, seconds)`：脚下停球

剧本在 `roll_to()` 返回时声明 `control_start`，随后调用 `trap()`，不等停球结束才换权。
停球期间球沿来球方向继续向前，接球人站定。朝向不作为算法输入，脚前偏移按来球方向表达，
不硬编码为球队进攻的 +x/-x 方向。

停球速度为 `v(t)=v_in*(1+cos(pi*u))/2`，其中 `u=(t-t_contact)/T`。
触球瞬间速度等于到脚速度，之后连续、单调减至 0，端点加速度为 0；位移为 `v_in*T/2`。
BP 故事到脚速度各自抽样 3–10 m/s；在 0.1–0.3 s 内选择与速度匹配的停球时长，使位移为 0.3–0.95 m。
不分别独立抽取不兼容的速度、时长和距离。

停球由脚施力，可超过自由运动自检的 20 m/s² 上限。自检仅排除显式停球区间及相邻差分采样的
自由加速度判据；全程速度限制、触球可达性和其他自由区间的检查保留。
独立测试验证停球曲线、到脚前后速度一致、不能单帧停止，以及事件边界不随停球动作后移。
停球不会新增控球事件，也不伪造若干离散触球来绕过自检。

## `hold(still=True)`

默认 `still=False` 保留旧行为。开启时保存当前球脚相对位置和高度，仅冻结该持球时段。
`height`、`in_front` 只用于普通 hold；still 不把球挪回默认偏移。到脚时仍在滚动的球必须先 trap。

不永久关闭球员晃动。区间外最多用 0.6 s 平滑接入/退出；短间隔各用半个间隔过渡。
其他球员不受影响；与显式跑动重叠时直接报错。

## 验收与查看

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m simulation.generate --dataset-id basic_possession_moving_v1 --subtypes BP01,BP02,BP03 --stories 20
.venv/bin/python -m simulation.view --dataset basic_possession_moving_v1 --experiment ground_roll_preview
```

新积木测试覆盖固定摩擦、带速到达、无人接的自然停止、停球的连续位置/速度、接球时刻换权、
局部静止与恢复晃动。BP01–BP03 的 20 个种子及主客版本共 120 个实例接受全部现有场景自检。
逐帧查看到脚时刻、停球中的后续 3–8 帧，以及之后的静止持球；高度曲线全程贴地。
生成 CSV、HTML、日志和截图不加入 Git。模拟效果不代表真实比赛成绩。
