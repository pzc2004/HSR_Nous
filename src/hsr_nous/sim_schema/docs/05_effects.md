## 5. 效果类型 (Effect Type)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

Effect 是技能/行动/事件触发的最小执行单元。所有 effect 共享若干通用字段：

```yaml
effect:
  effect_type: "deal_damage"   # 必填：effect 类型
  target: "primary_target"     # 选填：目标选择器
  condition: "$self.energy >= 120"   # 选填：触发条件（受限 DSL）
  trigger: "on_cast"           # 选填：触发时机（ Modifier / Action 内）
```

### 5.1 数值字段 `amount` 统一说明

多个 effect 的数值字段统一为 `amount`（或 `pct`），支持以下形式：

| 形式 | 示例 | 说明 |
|------|------|------|
| 常量 | `amount: 5` | 固定数值 |
| 关键字 | `amount: "all"` | 全部当前值 |
| 比例 | `amount: "ratio:0.5"` | 当前值的 50% |
| 表达式 | `amount: "$self.max_hp * 0.3"` | 受限 DSL 求值 |
| 引用资源 | `amount: "$resource.punchline * 0.1"` | 读资源当前值 |
| 引用前序 | `amount: "$prev.amount * 0.8"` | 同一 action 内前一个 effect 结果 |

### 5.2 标准 effect_type 列表

#### 造成伤害

```yaml
# 假设 self.basic_scaling 已通过 variable_bindings 绑定
effect_type: "deal_damage"
formula: "damage"           # 引用 formulas.yaml 中定义的公式
target: "primary_target"    # 主目标 | all_enemies | all_allies | self | random_enemy | lowest_hp_enemy
amount: "$self.atk * $self.basic_scaling"   # 技能倍率/基础伤害（支持表达式）
damage_type: "ice"          # 伤害属性
split: "even"               # 可选：总量按结算时存活目标均分（缺省 = 每目标全额）
```

> 旧字段 `scaling` 已被 `amount` 取代。`formula` 字段缺省为 `"damage"`（直伤公式）；仅使用其他公式（如 `dot_damage`、`elation_damage`）时需显式写明。

**类别与段数（决策卡 #19）**：`category: "additional"` 声明附加伤害（写入事件 payload `tags: [additional]`——不吃类型限定增伤、不再触发命中类监听，见 `03_actor.md` §3.8 tags 登记）；`instances: <expr>` 声明多段/动态段数——DSL 禁循环，循环只存在于编译期：按表达式展开为 N 段独立结算（`target: "random_each"` 时逐段独立随机），并注入 `$seg.index` 段序号（"第 N 段起生效"类条件可读）。

**分配轴 `split`（可选）**：与范围轴（`target` / `target_type`：单体/扩散/群攻/弹射）**正交**——范围轴定"打谁"，分配轴定"每目标全额还是总量均分"（均分与打击范围是两个维度，不并入范围轴字段）。`split: even` 时 `amount` 为**总量**，按结算时**存活目标数**均分（目标中途退场，存活者份额随之变大）；弹射类按段均分到随机目标。实例：开拓者·欢愉欢愉技（均分欢愉伤害）、赛飞儿终结技终结一击、白厄最后一击。公式层零改动——effect 层均分后逐目标喂入 `ability_multiplier`（见 `01_formula.md` §1.1）。

> 落地自决策卡 #16（2026-08-15）

#### 连携攻击（joint_attack）

单行动、多伤害包：一次行动产生多个**独立伤害结算**，每包带 `caster` 引用、按**各自面板/属性**求值（机制事实见 `../../../../docs/mechanics/11_special_mechanics.md` §11.6：单次行动、多次结算、固定顺序）。

```yaml
# 忆师 + 忆灵连携（迷迷 / 阿格莱雅类）：忆师先攻、忆灵后攻
effect_type: "joint_attack"
packets:
  - caster: "self"
    target: "all_enemies"
    damage_type: "ice"
    amount: "$self.atk * 1.0"
  - caster: "$self.memosprite"
    target: "all_enemies"
    damage_type: "ice"
    amount: "$self.atk * 0.6"
```

```yaml
# 联动角色连携（凛×Archer / 金闪闪×Saber）：caster 用具名绑定，与忆灵连携同构
effect_type: "joint_attack"
packets:
  - caster: "self"
    target: "enemy_single"
    damage_type: "wind"
    amount: "$self.atk * 1.2"
  - caster: "character_ref('archer')"
    target: "enemy_single"
    damage_type: "imaginary"
    amount: "$self.atk * 0.8"
```

| 字段 | 说明 |
|------|------|
| `packets` | 伤害包列表，按序结算；每包字段同 `deal_damage`（`target` / `damage_type` / `amount` / `formula`），另加 `caster` |
| `caster` | 该包的伤害来源：`self` / `$self.memosprite` / `character_ref(id)`（具名队友绑定，见 `22_syntax_reference.md` §22.7）；**包内表达式的 `$self` 绑定到该包 caster**（各自面板/属性） |

**"连携攻击"是一等可被选中的标签（伤害类别）**：joint_attack 打出的伤害包除主类别（`action_type`）外附加 `joint` 标签——`dmg_bonus_by_type` 增伤按标签集合命中各档求和（见 `03_actor.md` §3.2），`hit_condition` 可写 `'joint' in $event.tags` 选中（见 `04_modifier.md` §4.2）。忆灵连携（迷迷/阿格莱雅）与联动角色连携（凛×Archer、金闪闪×Saber）同构，差别只在 `caster` 的写法。

> 落地自决策卡 #10（2026-08-14）

#### 立即结算持续伤害（trigger_dot）

强制让目标身上的 DOT modifier **立即结算一次**——卡芙卡终结技、昔涟类"引爆"机制。

```yaml
effect_type: "trigger_dot"
target: "primary_target"     # 结算对象身上的 DOT
scope: "all"                 # "all"（卡芙卡 A2：全部来源）| "self"（仅自己施加的）| modifier_id（指定单一 DOT，如只引爆 Shock）
consume: false               # true = 消耗原跳数（本跳并入）；false = 额外结算一次（原计时不受影响的 Jump）
```

**语义**：

- 被结算的 DOT 按其**施加者面板**计算（不是施放 `trigger_dot` 的角色——后手归属：dot 伤害属施加者）
- `trigger_dot` 是**动作**不是事件；它产生的事件是统一的 **`on_dot_retrigger`**（见 `23_event_hook_system.md` §23.4：自然回合结算与本效果强制结算共用同一事件，`retriggered: true` 标记强制来源）
- 自然跳伤（回合开始 判定A/结算1）不需要此效果——那是 modifier 生命周期结算

#### 回复生命

```yaml
effect_type: "heal"
formula: "heal"
target: "ally_single"
amount: "$self.max_hp * 0.3 + 200"
```

#### 施加/移除 modifier

```yaml
effect_type: "apply_modifier"
modifier_id: "MOD_XXX"
modifier: { ... }            # 可内联完整 modifier 定义
target: "self"
duration: 3
chance: 1.0                  # 基础概率，受效果命中/抵抗影响
```

> **弱点植入不新增 effect_type**：用 `apply_modifier` + 弱点操作类 modifier（`weakness_add` 字段，见 `04_modifier.md` §4.11）表达；已挂 modifier 的时长增减用 `adjust_duration` 结算原子（同节）。

```yaml
effect_type: "remove_modifier"
modifier_id: "MOD_XXX"       # 可选；缺省 = 不限定 ID（配合 filter / max_count 使用）
target: "enemy_single"
filter: "$mod.debuff_kind == 'control'"   # 可选：表达式过滤，$mod 绑定待审 modifier（复用 ast 求值器，见 22_syntax_reference.md §22.4）
max_count: 1                 # 可选：最多移除个数（缺省 = 全部匹配）
order: "newest"              # 可选：移除顺序 newest（默认，LIFO）| oldest
```

三个可选字段的组合对应常见净化/驱散族：流萤类"驱散全部" = 无 `filter`；知更鸟类"净化控制" = `filter: "$mod.debuff_kind == 'control'"`；灵砂类按个数 = `max_count`。命中的仍仅限 `dispellable: true` 实例（见 `04_modifier.md` §4.6）。

#### 转移 modifier（transfer_modifier）

把 modifier 实例从 source 转移到 target，**保留剩余时长/层数**（区别于"重挂"——重新施加是全新实例）：

```yaml
# 椒丘【烬煨】死亡转移：携带者死亡 → 转移到当前层数最高的其他敌人
hooks:
  - event: "actor_exit"
    condition: "$event.actor_type == 'monster' && $event.reason == 'death'"
    effects:
      - effect_type: "transfer_modifier"
        modifier_id: "MOD_JQ_ASHEN_ROAST"
        source: "$event.actor"          # 从谁身上取下（缺省 = 事件/行动当前目标）
        target: "min_by(enemies, 'ashen_roast_stacks')"   # min_by 目标表达式（见 22_syntax_reference.md §22.4）
```

hook 驱动（`actor_exit` 死亡发射点 + `condition` + 目标表达式）即可覆盖椒丘/大黑塔同族；银狼植入的"重挂式"转移见 `04_modifier.md` §4.11。

**重排目标表达式（优先精英）**：大黑塔【解读】重排——携带者死亡/离场时层数转移，**优先精英及以上**目标；多键优先级用参数化选择器 `type: "priority"`（`22_syntax_reference.md` §22.7 参数化选择器族扩展：按 `keys` 列顺序逐键降序比较，取首个）：

```yaml
# 大黑塔【解读】重排：携带者死亡/离场 → 优先转移到精英及以上敌人，其次按层数高者
hooks:
  - event: "actor_exit"
    condition: "$event.actor_type == 'monster' && ($event.reason == 'death' || $event.reason == 'exile')"
    effects:
      - effect_type: "transfer_modifier"
        modifier_id: "MOD_THERTA_INTERPRETATION"
        source: "$event.actor"
        target:
          type: "priority"
          keys: ["is_elite", "interpretation_stacks"]   # 先精英层级、再按层数，逐键降序取首个
```

> 落地自决策卡 #9（2026-08-14）、#14（2026-08-14）、#16（2026-08-15）

#### 调整时长（adjust_duration）

modifier 剩余时长的**增量**加减（±N）——回合结束 tick（全体 -1）、延长植入（+1）、界外单位手动衰减（-1）共用同一**结算原子**：

```yaml
effect_type: "adjust_duration"
target: "primary_target"
amount: 1                    # +N 延长 / -N 衰减（增量：剩 1 回合 +1 = 2 回合；不是 refresh 重置满值）
filter: "$mod.modifier_id == 'MOD_SW_IMPLANT'"   # 可选：$mod 绑定待审 modifier（复用 remove_modifier.filter 语义，见 22_syntax_reference.md §22.4）；缺省 = 目标全部持续效果
```

- **职责分离**：原子 = 系统结算（改系统账本）；hook 要改时长必须调本原子，不直接改时长账本；时长变化事实照常经总线发射
- 与 `stack_mode: "refresh"` 的区别：refresh 把剩余时长**重置为满值**；本原子在剩余时长上**加减 N**（示例与界外单位用法见 `04_modifier.md` §4.11）
- 目标上无匹配 modifier 时无效果（区别于 apply_modifier 的施加语义）

> 落地自决策卡 #15（2026-08-15）、#16（2026-08-15）

#### 修改属性

```yaml
effect_type: "add_stat"
stat: "spd"
amount: "$self.spd * 0.25"
```

> `add_stat` 通常用于一次性/瞬时属性调整；持续属性加成应使用 `apply_modifier`。

#### 无效果 / 占位

```yaml
effect_type: "none"
```

用于 modifier / action trigger 中必须声明 effect 列表但无实际行为的占位场景。

#### 移除属性

```yaml
effect_type: "remove_stat"
stat: "shield"
```

用于 modifier 过期/移除时清理临时属性（如护盾清零）。`remove_stat` 只清指定 stat 的加成源，不处理完整的 modifier 生命周期；完整移除 modifier 应使用 `remove_modifier`。

#### 回复能量

```yaml
effect_type: "gain_energy"
target: "self"
amount: 30
```

#### 激活终结技（activate_ultimate）

把目标的充能资源补到**激活阈值**（`ult_threshold`，见 `16_custom_resources.md` §16.2）即停——不是充满到 `max`。覆盖昔涟"点亮"全队、紊流 buff 系统级激活。

```yaml
# 昔涟：激活全队终结技（每人补到自己的 ult_threshold，而非满贯）
effect_type: "activate_ultimate"
target: "all_allies"
resource_id: "energy"        # 缺省 = energy；可指定其他充能资源（如 recollection）
```

- 目标能量已 ≥ 阈值时无效果；未声明 `ult_threshold` 的资源阈值视为 `max`
- 多档资源补到"高于当前值的最低档"（银枝 45 能 → 90 档）
- 提供量 = 阈值 − 当前值；资源声明了 `activation_grant` 时以该字段为准（独立字段，不可默认 = 上限，见 `16_custom_resources.md` §16.12）

> 落地自决策卡 #13（2026-08-14）

#### 推进/拉条

```yaml
effect_type: "advance_action"
target: "self"
amount: 100                  # 行动值推进百分比：100 = 拉条 100%（通常可立即行动，但 ≠ "立即行动"原语——后者无视推条直接归零，见下节）
```

#### 立即行动

```yaml
effect_type: "immediate_action"
target: "self"
```

与 `advance_action: 100` 的区别：`immediate_action` 直接将该 actor 的 AV 设为 0，不受当前推条影响；`advance_action: 100` 是按当前速度减去 100% 行动条，若之前被推条可能无法到 0。

#### 授予额外回合

```yaml
effect_type: "grant_extra_turn"
target: "self"
queue_mode: "insert"      # insert = 插入第 2 层额外回合队列（再现/终结技类）；after_action = 战技类"本回合不结束"
```

语义（详见 `../../../../docs/mechanics/03_action_sequence.md` §3.4 分层 FIFO）：

| `queue_mode` | 机制 | 语义 |
|---|---|---|
| `"insert"`（默认） | 希儿再现、终结技后额外回合类 | 进入第 2 层额外回合队列（与终结技同级 FIFO，不能插其他额外回合的队）；**不消耗 buff 回合数**；不受推条/减速影响；触发 `on_extra_turn` 事件 |
| `"after_action"` | 刃/青雀/波提欧战技、乱破终结技（游戏文本"本回合不会结束"） | 排在第 2 层队列**之后**，视同普通回合（消耗 buff 回合数） |

与 `advance_action` / `immediate_action` 的区别：后两者产出的是行动轴上的**普通回合**（消耗 buff 回合数；advance 可被推条抵消）；`grant_extra_turn` 产出**插入式**额外回合，不动行动轴。再现（希儿）标准写法见 `09_faq.md` 多段伤害示例。

#### 放逐 / 离场（banish_actor）

强制目标离场（白厄变身放逐队友类）：

```yaml
effect_type: "banish_actor"
target: "team_allies"        # 放逐对象
until: "transformation_end"  # 回场时机：变身终局结算后（关键字；也可写条件表达式）
```

三条语义（缺一不是放逐）：

- **不可选中**：离场者不进任何 `target` 选择器（见 `22_syntax_reference.md` §22.7）
- **状态冻结**：AV / buff / 生命保持离场前值，离场期间不 tick（时长不衰减、DOT 不结算、不在行动条上跑字）
- **回场恢复**：`until` 时机到、终局结算后按冻结值恢复（AV 与状态从冻结点续跑）

- 离场事实经总线发射 `actor_exit`（`reason: "exile"`，见 `23_event_hook_system.md` §23.4）；回场 = 再入场，发 `actor_enter`
- **例外注**：分摊类持续效果（符玄穷观阵）对离场者不生效——离场排除粒度为实测口径：不止"不被选中"，持续效果的作用域同样排除离场者
- 放逐**不是**控制类 debuff——不可驱散/净化（技能原文"不属于晕眩，无法被解除"）
- 离场是正交的**在场性**维度，不是 ActorState 形态（见 `17_actor_state.md` §17.2 注）

> 落地自决策卡 #16（2026-08-15）

#### 结束当前回合（end_current_turn）

立即结束目标当前回合（白厄天赋：变身时结束当前回合锁增益类）：

```yaml
effect_type: "end_current_turn"
target: "self"               # 被结束者
```

语义 = **保留已发生、丢弃未行动**：

- 已发生的行动/效果全部保留；被结束者本回合**未行动**的部分丢弃（不再行动）
- 被结束者 AV 重置满条（`10000 / speed`）；其他队友与倒计时 AV **冻结**（变身结束后按冻结值续跑）

**时序**（"锁 buff"数学原理）：引擎先对被结束者执行 `adjust_duration(+1)`（时长原子，见本节 adjust_duration）→ 再按**正常回合末结算**（B 类结算，时长 tick -1）→ 净效果：已有增益时长不变（+1 −1），本回合新挂增益**白赚 +1**。机制事实见 `../../../../docs/mechanics/03_action_sequence.md` §3.6。

> 落地自决策卡 #16（2026-08-15）

#### 示例：白厄变身全链

```yaml
# 白厄终结技全链：火种 → 变身 → 锁 buff → 结束当前回合 → 倒计时回合 → 最后一击均分 → 队友回场
custom_resources:
  coreflame:                       # 火种：12 点激活终结技
    max: 12
    ult_threshold: 12              # 充能三段式，见 16_custom_resources.md §16.12
  khaslana_turns:                  # 卡厄斯兰那倒计时回合额度（8 回）
    max: 8

actions:
  - action_id: "140803"
    name: "He Who Bears the World Must Burn"
    action_type: "ultimate"
    target_type: "self"
    effects:
      # ① 变身：队友放逐离场（不可选中/状态冻结/终局回场），自身进入 Khaslana 形态
      - effect_type: "banish_actor"
        target: "team_allies"
        until: "transformation_end"
      - effect_type: "enter_state"
        to_state: "khaslana"
        exit_conditions:
          - {trigger: "on_resource_depleted", value: "khaslana_turns"}   # StateConfig 私有枚举，见 17_actor_state.md §17.3
        on_exit_effects:
          # ⑥ 最后一击：总量按存活敌人均分（split 与 target 正交，见本节 deal_damage）
          - effect_type: "deal_damage"
            target: "all_enemies"
            split: "even"
            damage_type: "physical"
            amount: "$self.atk * $self.final_hit_scaling"
      # ②③ 锁 buff + 结束当前回合：end_current_turn 时序内置 adjust_duration(+1) → 正常回合末结算，
      #    本回合新挂增益白赚 +1（见本节 end_current_turn 时序注）
      - effect_type: "end_current_turn"
        target: "self"

# ④ 倒计时回合：卡厄斯兰那 8 个倒计时类额外回合——不消耗回合数、无回合开始/结束事件、
#    波次开始不重置行动值（额外回合两类型，见 03_actor.md §3.11）；
#    形态内行动（140808/140809/140811）各自带 consume_resource(khaslana_turns, 1)，
#    耗尽退出形态 → on_exit_effects 最后一击 → 终局结算后队友按冻结值回场（⑦）
```

#### 代放 / 复制行动（trigger_action）

以指定 caster 发起一次行动——覆盖"代放"（开拓者·欢愉代放欢愉技）与"复制"（刻律德菈复制战技）两族：

```yaml
# 静态引用：开拓者·欢愉代放欢愉技
effect_type: "trigger_action"
caster: "self"                  # 代放执行者
action: "tb_elation_skill"      # 静态引用 action_id
cost: "none"                    # none（不支付正常消耗）| pay（照付）
attribution: "original_caster"  # 归因：trigger_caster（算代放者发动）| original_caster（算原行动者发动）
timing: "immediate"             # immediate（立即插入执行）| queue（排入插入队列）
```

```yaml
# 动态引用 = 复制：刻律德菈复制队友战技（hook 驱动）
hooks:
  - event: "on_cast"
    condition: "$event.action_type == 'skill' && $event.source != $self"
    effects:
      - effect_type: "trigger_action"
        caster: "self"
        action: "$event.action"       # 动态引用事件中的行动 = 复制
        cost: "none"
        attribution: "trigger_caster"
        timing: "immediate"
```

- `action: "$event.action"` 动态引用 = 复制该次行动（含其 effects 与数值上下文）
- 复制的行动会再经总线发射——模板需用 `condition` 排除自身（如上例 `$event.source != $self`）防自循环
- 代放不消耗被代放者的回合；是否支付消耗由 `cost` 控制

> 落地自决策卡 #13（2026-08-14）

#### 行动延后（推条）

```yaml
effect_type: "delay_action"
target: "primary_target"
amount: 30                  # 延后 30% 行动条
```

行动延后增加目标当前 AV：`new_av = current_av + 10000/speed * amount%`；999 仅为显示层封顶，内部值不钳（社区实测 B站 BV1rp4y1T7wG，旁证 BV1dqZyYBEya；单一来源，未独立复现）。

#### 追加韧性条（add_toughness_bar）

给目标追加一条韧性条（韧性条列表模型见 `03_actor.md` §3.10）——忘归人虚韧性条 = 挂 modifier 加条：

```yaml
# 忘归人：虚韧性条（modifier 驱动；条随 modifier 移除/过期一并移除）
modifier:
  modifier_id: "MOD_FUGUE_EXO_BAR"
  modifier_type: "debuff"
  duration: 2
  on_apply:
    - effect_type: "add_toughness_bar"
      target: "self"            # modifier 携带者
      bar_id: "fugue_exo"       # 条标识；同 ID 重复施加 = 刷新该条
      amount: 40                # 条的韧性值
      exo: true                 # 超韧性条：任意属性可削、击破再次触发弱点击破
```

- 追加条按加入顺序排在主条之后，**按序扣除**（前条未归零不扣后条）
- 每条归零经总线发射 `on_break`（payload 带 `bar_index`，主条 = 0）——二次击破用普通触发器 + `condition` 过滤，不加事件人头税
- modifier 施加的条登记来源：modifier 移除/过期时其挂载的条一并移除（无需 remove 原语）

#### 随机抽取（random_pick）

受控随机原语——效果层的随机性只走显式原语（同 `chance(N)` 哲学，见 `22_syntax_reference.md` §22.10）：

```yaml
# 银狼随机 debuff 池：加权抽 1 个挂上
effect_type: "random_pick"
pool: ["MOD_SW_DEF_DOWN", "MOD_SW_ATK_DOWN", "MOD_SW_SPD_DOWN"]
weights: [1, 1, 1]            # 可选：加权（缺省等权）
count: 1                      # 抽取个数（默认 1，不放回）
into: "picked_debuff"         # 结果写入模板变量，后续 effect 用 $self.picked_debuff 引用
```

| 字段 | 说明 |
|------|------|
| `pool` | 候选列表（modifier_id / 值） |
| `weights` | 可选权重列表（缺省等权） |
| `count` | 抽取个数（默认 1，不放回） |
| `rolls` / `keep` | 可选：重 roll 次数与保留策略——`rolls: 2` + `keep: "highest"` = 保留最高重 roll（砂金类） |
| `into` | 结果写入的变量名（后续 effect 以 `$self.xxx` 引用） |

- 青雀摸牌 = `pool` 牌型抽取；银狼随机 debuff 池 = `pool` + `weights`；砂金 = `rolls` + `keep: "highest"`
- **衰减概率变量**不是新原语：概率存 `custom_resources` 计数，`condition: "chance($resource.xxx * 5)"` 引用，触发后 gain/consume 该资源调整概率（黑天鹅衰减链）

> 落地自决策卡 #14（2026-08-14）

#### 生命汲取 / 生命流失

```yaml
effect_type: "drain_hp"
target: "primary_target"          # 流失 HP 的目标
amount: "$self.atk * 0.5"         # 流失量
drain_ratio: 1.0                   # 流失量中转化为治疗的比例（0~1，默认 1.0）
heal_target: "self"                # 治疗目标，默认自身；可指定为其他 actor
into_resource: "lc23042_hp_consumed"   # 可选：流失总额灌进资源（见下）
floor: 1                           # 可选：流失保底——耗不致死（决策卡 #19 小件族）
```

**语义**：使 `target` 失去 HP，并按 `drain_ratio` 治疗 `heal_target`。

**`into_resource`（可选）**：声明时，本次流失的**实际总额**（多目标时求和）灌入指定自定义资源，**替代** `consume_team_hp_pct`（已废弃）。用于表达"消耗全队生命累计计数"类机制（如光锥 23042）：

```yaml
# 光锥 23042：消耗全队当前生命 X% 并累计到资源
effect_type: "drain_hp"
target: "team_allies"
amount: "ratio:$self.consume_pct"
drain_ratio: 0                     # 不治疗
into_resource: "lc23042_hp_consumed"
```

**与 `deal_damage` + `heal` 的区别**：
- `drain_hp` **不触发** `before_take_damage` / `after_being_hit` 等**伤害类** hook（drain 不是伤害，避免"受击后"类效果被自伤误触发）。
- 但 `drain_hp` **触发** `on_hp_decrease`（reason='drain'）——HP 消耗与受击、DOT、流血一样都是 HP 降低来源（见 `docs/mechanics/11_special_mechanics.md` §11.3），刃天赋叠层、小伊卡天赋治疗等都挂在这个事件上。
- 适合表达"自残回血""小伊卡流失生命治疗队友"等机制。

当 `heal_target` 与 `target` 相同时，就是典型的吸血；当 `heal_target` 为其他 actor 时，就是生命转移/反哺。

#### 回复战技点

```yaml
effect_type: "gain_skill_point"
amount: 1
```

#### 召唤/解散召唤物

```yaml
# 召唤单位
effect_type: "summon"
summon_id: "SUMMON_001"      # 引用 data/sim_templates/characters/SUMMON_001.yaml
position: "after_owner"      # 召唤位置：after_owner | before_owner | fixed_position
```

```yaml
# 解散召唤物
effect_type: "dismiss_summon"
summon_id: "SUMMON_001"
```

#### 召唤物行动

```yaml
effect_type: "summon_action"
action_id: "SUMMON_XXX"
```

#### 覆盖/追加技能参数

```yaml
# 直接替换参数值
effect_type: "override_action_param"
action_id: "120502"
param_index: 0
amount: 0.65
condition: "$build.eidolon >= 1"
```

```yaml
# 在原值基础上加
effect_type: "append_action_param"
action_id: "100103"
param_index: 1
amount: 10
condition: "$build.eidolon >= 1"
```

### 5.3 资源相关 effect_type

见 `16_custom_resources.md` 详细说明。

#### `gain_resource`

```yaml
effect_type: "gain_resource"
resource_id: "punchline"
amount: 5
overflow_policy: "cap"       # "cap" | "allow" | "convert_to_extra"
```

#### `consume_resource`

```yaml
effect_type: "consume_resource"
resource_id: "hyacine_cumulative_heal"
amount: "ratio:0.5"
on_insufficient: "fail"      # "fail" | "clamp" | "consume_all"
```

#### ~~`consume_team_hp_pct`~~（已废弃）

> **废弃**：案例焊进关键字，违反"闭合关键字集"原则。改用 `drain_hp` + 可选字段 `into_resource`（见 §5.2 生命汲取）——聚合语义、原子性、变量绑定全部保留，类型零增长。原模板中的 `effect_type: "consume_team_hp_pct"` 等价改写为 `effect_type: "drain_hp" + target: "team_allies" + amount: "ratio:…" + drain_ratio: 0 + into_resource: …`。

### 5.4 形态相关 effect_type

见 `17_actor_state.md` 详细说明。

#### `enter_state`

```yaml
effect_type: "enter_state"
to_state: "hellscape"
duration: 3
replaces_actions:
  shard_sword: forest_of_swords
locked_actions: ["blade_skill"]
on_enter_effects: []
on_exit_effects: []
```

#### `exit_state`

```yaml
effect_type: "exit_state"
target_state: "normal"
```

#### `transform_action`

```yaml
effect_type: "transform_action"
target_action: "basic"
new_action_id: "enhanced_basic"
```

### 5.5 场地相关 effect_type

见 `19_zone_system.md` 详细说明。

#### `deploy_zone`

```yaml
effect_type: "deploy_zone"
zone_id: "ruinous_irontomb"
area_shape: "battlefield"
duration: 3
on_turn_start: []
on_enter: []
on_damage_deal: []
scoped_modifiers: []
```

#### `dismiss_zone`

```yaml
effect_type: "dismiss_zone"
zone_id: "ruinous_irontomb"
```

### 5.6 Hook 相关 effect_type

见 `23_event_hook_system.md` 详细说明。

#### `modify_event`

在 hook effects 中修改原事件参数：

```yaml
effect_type: "modify_event"
event_updates:
  amount: "$event.amount - $last.actual_amount"
  target: "$self"
  cancel: false
```

### 5.7 已移除的 effect_type

| 旧 effect | 替代方案 |
|----------|---------|
| `convert_resource` | 并列 `consume_resource` + `gain_resource` |
| `consume_resource_substitute` | 事件 hook 系统（见 `23_event_hook_system.md`） |
| `script`（任意 Python 表达式） | 受限 DSL 表达式；复杂逻辑拆分为多个声明式 effect 或 hook |

### 5.8 参数覆盖 vs 追加

- `override_action_param`：直接替换参数值（如万敌 E1 把战技主目标倍率从 0.55 改为 0.65）。
- `append_action_param`：在原值基础上加（如爻光 E1 使终结技触发的额外阿哈时刻多 10 笑点）。

两者都支持 `condition` 字段，可用于星魂等级、行迹解锁等条件判断。

---
