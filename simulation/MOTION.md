# 运动积木：传球、停球、弹跳与背景跟随

本版新增地滚传球和显式停球。原抛物线 `kick_to()`、默认晃动、事件到标签的映射不变。
不修改观测层或算法接口，不使用比赛答案。PR 2 新增可显式调用的弹跳与默认关闭的阵型跟随。

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

## `bounce_to()`：高球落地、衰减弹跳、地滚停止

```python
b.event("legal_restart", team="atk")  # The script declares the restart.
b.bounce_to(1.2, point=(38.0, 42.0), restitution=0.55, bounces=3, deceleration=2.0)
b.wait(2.0)
```

`seconds=1.2` 只指定第一段高球到落地点的时间。函数沿用原 `kick_to()` 的空中轨迹，
随后产生 3 次回弹，再按 PR 1 地滚球减速度滚至停止。调用完成时脚本时钟已到自然停止时刻，
返回该停止时间。原 `kick_to()` 的位置函数、触球记录与默认行为均未更改。

每次起跳竖直速度为前一次落地速度绝对值的 e 倍，默认 `e=0.55`；
离地峰值满足 `h_next/h_previous=e²=0.3025`。空中水平速度保持不变，最后一次落地后水平速度
连续接入匀减速滚动。按给定回弹次数截断竖直运动，不模拟球旋转、空气阻力或地面切向能量损失；
e 和摩擦参数不是本场草地实测值。

碰地时间单独保存在内部 `ground_impacts`，不是球员触球，也不是控球事件。
自检只在这些地面冲量邻近的差分窗口排除自由加速度上限，并检查冲量位置确实在 0.11 m。
全程速度、其他自由区间、球员触球可达性和事件顺序检查保留。落地、弹跳、滚停均不自动换权或判 D；
若故事里球出界或有人建立控制，仍由剧本声明对应事件。

## `ClipBuilder(..., follow_ball=True)`：背景阵型平移

默认 `False`。开启后，在最终渲染时为背景球员加入同一连续平移；原晃动保留，球轨迹不参与反馈修改。
整段有显式跑动、静止时段或持球安排的角色均不加入跟随，连同这些角色没有动作的时段也保留原轨迹。
这是一条保守的剧情优先规则，不是逐帧识别“现在谁有球”。剧本阶段的 `player.position()` 仍表示基础轨迹；
启用后的最终位置通过 `Clip.players_at()` 和生成文件查看。

目标平移取球相对开场位移的 25%，每轴最多 6 m，并按背景球员原位置及晃动幅度收紧范围，保留 1 m 边距。
采用临界阻尼二阶响应，`offset'' + 2ω offset' + ω² offset = ω² target`，`ω=1/1.5 s⁻¹`。
按 25 fps 精确更新每段常值目标的状态，再用三次 Hermite 插值保持位置和速度连续；
不通过逐帧直接搬动阵型或裁切输出位置来制造跳变，也不额外消耗随机数。
所有启用片段仍必须通过原有球员速度 ≤10 m/s、加速度 ≤12 m/s² 自检。

该功能只让背景动起来，不模拟盯人、攻防决策、主动抢球或逐名球员战术。不会自动为现有场景开启跟随。

## PR 2 开关对照示例

```bash
# Four clips: follow off/on and H/A mirrors of the same synthetic story.
.venv/bin/python -m simulation.examples.bounce_follow --dataset-id bounce_follow_demo --seed 0
.venv/bin/python -m simulation.view --dataset bounce_follow_demo --experiment bounce_follow_preview
```

在查看器中选择 `FOLLOW_OFF` 与 `FOLLOW_ON`。两者球、事件、答案完全相同，区别仅为 20 名背景球员的平移。
默认示例的 3 次离地峰值约 0.534、0.162、0.049 m；之后高度保持 0.11 m 并地滚停止。
检查弹跳段逐帧连续、背景随球移动，且持球人和显式跑动角色不被整体平移覆盖。

示例入口不加入 `simulation/scenarios/` 自动发现表，不把运动展示样本当作独立准确率证据。
单元测试覆盖峰值衰减、地滚衔接、地面冲量与球员触球分离、跟随开关、镜像、显式动作优先以及连续速度。
