# 运动积木：传球、停球、弹跳与背景跟随

`ClipBuilder` 运动积木的用法和物理依据。积木只生成连续轨迹，不推断答案；答案只由剧本声明的事件推导。
所有新选项默认关闭或保持原默认值，不改变未使用它们的剧本。

## 按故事随机化与物理依据

BP01–BP03、LC01–LC05、DC01–DC03 使用 `scenarios/_motion.py` 的 `StoryMotion.sample(rng)`。
同一故事的减速度、恢复系数和水平保留系数抽取一次；主客镜像复用同种子，参数完全相同。
BP 同一故事复用到脚速度；LC/DC 的核心接球速度由距离、飞行、弹跳或追逐时间联合确定。
停球仅抽取一次故事参数 `trap_fraction`（0–1）。每次接球以实际速度 v 计算
`T_low=max(0.1, 0.6/v)`、`T_high=min(0.3, 1.9/v)`，由 `trap_seconds(v)` 返回
`T_low + trap_fraction*(T_high-T_low)`；不在接球时重新消耗随机数。
DC01 先扣除收球时的球脚偏移，再用 `max_distance` 收紧停球位移上限，保证偏移加停球位移 ≤0.95 m；
该可行性约束仍使用同一 `trap_seconds()`，不另抽时长、不改变 1 m 可达性自检。
除联合约束外使用均匀抽样；这些是测试覆盖范围，不是比赛参数分布。

| 参数 | 抽样范围 | 依据与限制 |
|---|---|---|
| 地滚减速度 a | 1–3 m/s² | 参考 FIFA 滚动测试数量级，并向快球的等效阻力扩展；模型中 a 恒定，不单独模拟空气阻力 |
| 竖直恢复系数 e | 0.55–0.70 | 2 m 落下回弹 0.6–1.0 m，`e=sqrt(h_rebound/h_drop)=0.548–0.707` |
| 首次落地水平保留 q₀ | 0.55–0.70 | 无初始旋转的理想空心球由滑动进入纯滚动时约为 0.6；真实旋转、草地接触会改变它 |
| 后续落地水平保留 q | 0.85–1.00 | 已有旋转的低跳保留更多水平速度；这是模拟假设，不是 FIFA 规定或本场实测值 |
| 到脚速度 | 3–10 m/s | 清晰接球样例的设计范围；无人接球的滚停不受此范围约束 |
| 停球时间 | 0.1–0.3 s | 与速度联合抽样，使停球位移 `v_in*T/2` 为 0.3–0.95 m |

来源采用固定版本，避免把标准更新误当作草地参数变化：

- FIFA《[Handbook of Test Methods, October 2015, V3.0 (2019)](https://www.actglobal.com/research/fqp-handbook-of-test-methods-2015-v30-w-cover.pdf)》第 9、11 节（PDF 第 10–14 页）规定竖直落球和 1 m 斜坡滚动测试。
- FIFA《[Handbook of Requirements, October 2015, V2.3](https://www.footballvictoria.com.au/sites/ffv/files/2023-04/FIFA_Quality_Manual_Handbook-of-requirements-2015.pdf)》表 1、表 3：FIFA QUALITY 竖直回弹 0.6–1.0 m；滚动距离 4–10 m。链接是 FIFA 原文的镜像，不表示当前认证要求。

滚动换算是推导，不是标准给出的减速度。假设薄壳球 `I/(mR²)=2/3`、斜坡无能量损失，
1 m 落差给出 `v²=2gh/(1+2/3)`；等效恒减速度 `a=v²/(2L)=0.6gh/L`。
L=4–10 m 对应约 0.59–1.47 m/s²；其中 L=4–6 m 对应约 1–1.5 m/s²。
这里选 1–3 m/s² 作更宽的覆盖，不宣称全部由 FIFA 测试直接推出。

首次水平保留约 0.6 来自理想冲量模型：初始角速度为 0，摩擦使其达到纯滚动，
`v_after/v_before=1/(1+I/(mR²))=3/5`。球已有旋转或碰撞期间不达到纯滚动时，此推导不成立。
因此 q₀、q 与 e 分开配置，不把竖直回弹测试当成水平耗散测量。

TI01/HD01 不调用故事抽样器。

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
延长 `wait()` 只延长覆盖范围，不重算初速度或摩擦。默认 2 m/s² 是简化参数，不是本场草地的实测值。

## `trap(player, seconds)`：脚下停球

剧本在 `roll_to()` 返回时声明 `control_start`，随后调用 `trap()`，不等停球结束才换权。
停球期间球沿来球方向继续向前，接球人站定。朝向不作为算法输入，脚前偏移按来球方向表达，
不硬编码为球队进攻的 +x/-x 方向。

停球速度为 `v(t)=v_in*(1+cos(pi*u))/2`，其中 `u=(t-t_contact)/T`。
触球瞬间速度等于到脚速度，之后连续、单调减至 0，端点加速度为 0；位移为 `v_in*T/2`。
停球时长在 0.1–0.3 s 内按到脚速度选取，使位移为 0.3–0.95 m（见上文 `trap_seconds`）。

停球由脚施力，可超过自由运动自检的 20 m/s² 上限。自检仅排除显式停球区间及相邻差分采样的
自由加速度判据；全程速度限制、触球可达性和其他自由区间的检查保留。
停球不会新增控球事件，也不伪造若干离散触球来绕过自检。

## `hold(still=True)`

默认 `still=False`。开启时保存当前球脚相对位置和高度，仅冻结该持球时段。
`height`、`in_front` 只用于普通 hold；still 不把球挪回默认偏移。到脚时仍在滚动的球必须先 trap。

不永久关闭球员晃动。区间外最多用 0.6 s 平滑接入/退出；短间隔各用半个间隔过渡。
其他球员不受影响；与显式跑动重叠时直接报错。

DC01–DC03 的接近带球、BP02 的停球后带走，都在静止持球结束后先用 `wait(0.6)` 让晃动恢复，
再开始跑动。球仍由原持球人带在脚边，活球标签不变。这避免恢复加速度与余弦跑动的
`a_peak=π²d/(2T²)` 直接叠加；不改变 12 m/s² 自检上限，也不跳过失败种子。

## `bounce_to()`：高球落地、衰减弹跳、地滚停止

```python
b.event("legal_restart", team="atk")  # The script declares the restart.
b.bounce_to(1.2, point=(38.0, 42.0), restitution=0.55, bounces=3,
            deceleration=2.0, horizontal_retention=0.75)
b.wait(2.0)
```

`seconds=1.2` 只指定第一段高球到落地点的时间。函数沿用原 `kick_to()` 的空中轨迹，
随后产生指定次数的回弹，再按地滚减速度滚至停止。调用完成时脚本时钟已到自然停止时刻，
返回该停止时间。

每次起跳竖直速度为前一次落地速度绝对值的 e 倍，默认 `e=0.55`；
离地峰值满足 `h_next/h_previous=e²=0.3025`。每次落地按 `horizontal_retention=q` 缩放水平速度，
默认 q=0.75，包含第一次落地及弹完转地滚的最后一次落地；各次空中段内水平速度不变。
3 次回弹共经过 4 次地面碰撞，因此地滚初速度为首次落地前水平速度的 `q⁴` 倍，
地滚距离为 `v_in²*q⁸/(2a)`。水平速度只在地面冲量处降低，位置保持连续，之后按摩擦减速至停。
q=1 表示落地不损失水平速度，q=0 表示第一次落地就消除水平速度。
按给定回弹次数截断竖直运动，不模拟球旋转或空气阻力；q、e 和摩擦参数不是本场草地实测值。

可选参数：

```python
# First impact loses more speed; later impacts retain more. End before natural stop.
b.bounce_to(2.0, point=(52.0, 28.0), restitution=0.62, bounces=1,
            deceleration=2.0, first_horizontal_retention=0.60,
            horizontal_retention=0.93, roll_seconds=0.2)
# Schedule the receiver at this endpoint, then declare control at contact.
b.event("control_start", team=receiver.team)
b.trap(receiver, 0.2)
```

`first_horizontal_retention=None` 时首次碰地仍使用 `horizontal_retention`；
显式设置 q₀ 后，第 n 次回弹后的地滚初速度为 `v_in*q₀*qⁿ`，包括最后一次落地的损失。
`roll_seconds=None` 时仍前进到自然停止；显式设置时前进到最后一次落地后指定的地滚时刻，
球继续运动，允许 `trap()` 从弹跳后的地滚段保持位置和速度连续地接管。不会新增落地控球事件。

## `deflect_to()`：被动脚／腿擦碰

```python
# The incoming ball is a ground roll; the named defender must be within 1 m.
b.event("incidental_touch", team="dfn")
b.deflect_to(defender, 0.6, point=(34.0, 30.0), deceleration=2.0)
b.event("control_start", team=receiver.team)
b.trap(receiver, 0.2)
```

这是瞬时接触冲量后的地滚变向，位置连续，速度方向允许在真实接触时刻跳变。
出射初速不得高于入射速度；不模拟腿部几何或身体姿态。动作本身只记录触球，不生成事件或答案。
默认终点是接球触点；无人接的终点可用 `arrival_contact=False`。剧本负责显式声明擦碰与后续控制事件。
DC01/02 擦碰后答案保持发起队；DC03 直到第二名对手受控接球才换队。

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

该功能只让背景动起来，不模拟盯人、攻防决策、主动抢球或逐名球员战术。LC、DC 剧本开启了跟随；TI、HD、BP 未开启。

## `ClipBuilder(..., collective_pace=True)`：背景球员集体速度

默认 `False`。开启后只改变“背景球员”的最终渲染位置：背景指全段没有
`BallWithPlayer` 持球、没有显式 `moves` 跑动、也没有 `still_periods` 的角色；
剧本显式安排的角色保持原轨迹。球、事件、答案、`core_window` 和帧数不变。
与 `follow_ball=True` 同时开启时本功能优先，关闭背景跟随平移，避免两个位移叠加。

每个故事（主客镜像共享同一组抽样）只从剧本事件构造活球／死球区间，边界仅用
`BALL_OUT`、`STOPPAGE`、`LEGAL_RESTART` 三类事件，不调用控球算法、不读取观测或答案。
每个故事随机抽取：

- 活球目标中位数 1.4–2.4 m/s，死球 0.5–1.4 m/s；
- 死球开始后 1–3 s 减速，合法重启后 1–3 s 加速；
- 每个背景球员围绕阵型位置做半径 1.5–3 m、方向随机的闭环。所有闭环共享同一
  速度剖面，因此背景球员的瞬时速度相同，片段 F1 中位数可直接对照目标。

范围故意比外部测量宽，只参考 Metrica Game 1/2 的数量级，不使用 Game 3 或
SkillCorner 的具体数字。它是行为假设，不是从真实球员拟合出的模型。

在存在持续至少 5 s 的相应区间时，每个故事还按以下概率加入反例，每类至多一个：

| 反例 | 概率 | 目标中位数 | 要防止的误判 |
|---|---|---|---|
| 死球中仍在跑：进球后庆祝、角球前跑位 | 20% | 1.8–2.6 m/s | 慢就等于死球 |
| 活球中很慢：门将持球、后场慢速倒脚 | 20% | 0.25–0.85 m/s | 快就等于活球 |

反例只改该区间的整体速度，不改事件、答案或显式角色。抽样仍须通过原有自检：
球员速度 ≤10 m/s、加速度 ≤12 m/s²；超限时生成失败，不裁切轨迹来掩盖。
背景闭环的位移只用于渲染，不会写回剧本位置，也不影响 `player.position()`。

这个开关是为了让“用整体速度判断死球”的算法能在模拟中运行和做回归检查。
行为本身来自同一假设，因此模拟结果不能作为该算法有效的证据；有效性只看外部
比赛检验集（Metrica Game 3、SkillCorner）。默认关闭时输出与改动前逐字节一致
（同一子型列表和参数）。

## 开关对照示例

```bash
# Four clips: follow off/on and H/A mirrors of the same synthetic story.
.venv/bin/python -m simulation.examples.bounce_follow --dataset-id <new_id> --seed 0
.venv/bin/python -m simulation.view --dataset <new_id> --experiment <preview_id>
```

在查看器中选择 `FOLLOW_OFF` 与 `FOLLOW_ON`：两者球、事件、答案完全相同，区别仅为背景球员的平移。
示例入口不加入场景自动发现表，不作为准确率证据。
