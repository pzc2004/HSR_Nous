## 10. 战斗结束条件 (Termination)

结束条件决定模拟何时停止，支持多种模式组合。

```yaml
# 模式一：固定行动值，统计总伤害（已实现）
termination:
  mode: "fixed_av"
  max_action_value: 1500
```

```yaml
# 模式二：击杀目标，统计所需行动值（未实现——写了编译期炸）
termination:
  mode: "kill_target"
```

```yaml
# 模式三：生存测试，统计存活回合数（未实现——写了编译期炸）
termination:
  mode: "survival"
```

```yaml
# 模式四：全灭测试（未实现——写了编译期炸）
termination:
  mode: "wipe"
```

> **实现状态对账**：termination 现役键仅 `mode` / `max_action_value`（`sim/compile/stage_compiler.py` `_TERMINATION_KEYS`，其余键——如旧示例的 `max_turns` / `target_ids`——写了编译期炸，已删）。
>
> | mode | 状态 |
> |------|------|
> | `fixed_av` | **已实现**（AV 上限截断） |
> | `kill_target` | **已实现**（对面全灭判停；我方全灭与对面全灭同为模式无关通则分支，见 `sim/engine.py` `_should_terminate`） |
> | `survival` / `wipe` | 词表已登记但**未实现**（引擎不判停——经 stage.yaml 进入时 stage_compiler 编译期炸指路，不静默吞） |
>
> 行动数兜底与 termination 解耦：引擎硬编码 `MAX_TURNS_SAFETY = 200`（`sim/engine.py`），非 termination 声明键。

### 10.1 行动值系统

行动值公式与拉条/推条数值的唯一事实源是 `../../../../docs/mechanics/03_action_sequence.md`（防腐，本节不抄录）；此处只登记 effect 形态与实现状态：

> **距离制口径**：行动轴主状态是守恒的**剩余距离**（拉条/推条 = 基础行动距离的 X% 绝对增减；AV 只是派生读数——剩余距离按速度换算的剩余时间），与 `sim/scheduler.py` 同口径（`_remaining`：实体句柄 → 剩余距离，守恒主状态）。

```yaml
# 立即行动：直接设 AV = 0
effect_type: "immediate_action"   # 待收编（写了编译期炸——05_effects.md §5.2）
```

```yaml
# 100% / N% 拉条（N% = 基础行动距离的 N%，最小为 0）
effect_type: "advance_action"     # 待收编（写了编译期炸——05_effects.md §5.2）
amount: 100  # 百分比
```

```yaml
# 推条（行动延后）：数值层不钳（内部值可超显示封顶 999——社区实测见 mechanics 03）
effect_type: "delay_action"       # 已实现（hook 通道；amount 为百分数，见 05_effects §delay_action）
amount: 30   # 行动延后 30%
```

**战斗行动次数兜底**：spec 目标值为整场战斗我方行动次数上限 999（termination 层兜底，防永动机无限循环）。只计**完整回合**——角色走完一个完整回合计数 +1；追加攻击、施放终结技、插入行动**不计入**。**引擎现状**：兜底为硬编码 `MAX_TURNS_SAFETY = 200` 弹出数（`sim/engine.py`，不分回合类型），撞线即截断并置 `BattleState.truncated = True`（毒数据防线——截断局没打完，优化器不得当合法样本）；999 上限未落地。

**遇袭**：战斗开始时若被遇袭，所有我方角色行动值 +20（机制事实见 mechanics 03）。**未实现**——引擎无遇袭入口。

**速度变化时行动值调整**：速度变化按守恒剩余距离口径自然生效（剩余距离 ÷ 新速度 = 新剩余时间；当前剩余时间归零后从下一次跑条起按新速度计）。公式与实测见 mechanics 03——本节不抄录（防腐）。

**冻结/强烈震荡补偿**（数值 0.5 / 0.7 见 mechanics 03，不抄录）：

- 冻结解除后行动值按初始值 50% 补偿——**已实现**（rulebook `constants.freeze_advance` + `sim/engine.py` 解冻提前，`scheduler.advance_action` 内部通道）
- 强烈震荡解除后按 70% 补偿——**未实现**（引擎无强烈震荡结算路径）
- 若未跳过行动就被解除冻结/震荡，则不触发补偿

**插入行动优先级**（分层 FIFO，详见 `../../../../docs/mechanics/03_action_sequence.md` §3.4）：
1. 追加行动（追加攻击及非攻击追加行动）——已触发的恒先结算
2. 额外回合（**含终结技**、再现、命途回响）——同层按触发顺序 FIFO，终结技不能插其他额外回合的队
3. 普通回合（忆灵/召唤物回合属此层）；标注"不结束当前回合"的战技类额外回合排在第 2 层队列之后，视同普通回合

**后拉先动原则**：自然同值按编队顺序；因拉条导致行动值相同时，后拉的先动（机制事实见 mechanics 03）。**未实现**——调度器同值 tie_break 为注册序（我方先于敌方、编队位小者先，见 `sim/scheduler.py`），不区分"自然同值"与"拉条同值"。

> Zone 的 `duration_decrement_trigger` 也基于回合/轮次边界，详见 `19_zone_system.md`。

**输出指标（根据模式不同）**：

| 模式 | 主要输出 | 次要输出 |
|------|---------|---------|
| `fixed_av` | 总伤害、DPS | 伤害分布、击杀数 |
| `kill_target` | 所需行动值、回合数 | 伤害效率 |
| `survival` | 存活回合数、存活率 | 承伤总量、治疗量 |
| `wipe` | 是否全灭、全灭回合 | 剩余敌人血量 |

> **实现状态**：`fixed_av` 行外三模式未实现（见章首对账表）；指标侧 `BattleState` 现役字段仅 `total_damage` / `damage_by_actor` / `turn_count` / `clock`（`cycle_index`）/ `truncated`——**DPS、击杀数、存活率等均未实现**（DPS 需自算 `total_damage / clock`）。

---
