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
```

> 旧字段 `scaling` 已被 `amount` 取代。`formula` 字段缺省为 `"damage"`（直伤公式）；仅使用其他公式（如 `dot_damage`、`elation_damage`）时需显式写明。

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

```yaml
effect_type: "remove_modifier"
modifier_id: "MOD_XXX"
target: "enemy_single"
```

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

#### 行动延后（推条）

```yaml
effect_type: "delay_action"
target: "primary_target"
amount: 30                  # 延后 30% 行动条
```

行动延后增加目标当前 AV：`new_av = current_av + 10000/speed * amount%`；999 仅为显示层封顶，内部值不钳（社区实测 B站 BV1rp4y1T7wG，旁证 BV1dqZyYBEya；单一来源，未独立复现）。

#### 生命汲取 / 生命流失

```yaml
effect_type: "drain_hp"
target: "primary_target"          # 流失 HP 的目标
amount: "$self.atk * 0.5"         # 流失量
drain_ratio: 1.0                   # 流失量中转化为治疗的比例（0~1，默认 1.0）
heal_target: "self"                # 治疗目标，默认自身；可指定为其他 actor
into_resource: "lc23042_hp_consumed"   # 可选：流失总额灌进资源（见下）
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
