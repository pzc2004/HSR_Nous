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

> 旧字段 `scaling` 已被 `amount` 取代。

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
amount: 100                  # 行动值推进百分比：100 表示立即行动
```

#### 立即行动

```yaml
effect_type: "immediate_action"
target: "self"
```

与 `advance_action: 100` 的区别：`immediate_action` 直接将该 actor 的 AV 设为 0，不受当前推条影响；`advance_action: 100` 是按当前速度减去 100% 行动条，若之前被推条可能无法到 0。

#### 行动延后（推条）

```yaml
effect_type: "delay_action"
target: "primary_target"
amount: 30                  # 延后 30% 行动条
```

行动延后增加目标当前 AV：`new_av = current_av + 10000/speed * amount%`，上限 999。

#### 生命汲取 / 生命流失

```yaml
effect_type: "drain_hp"
target: "primary_target"          # 流失 HP 的目标
amount: "$self.atk * 0.5"         # 流失量
drain_ratio: 1.0                   # 流失量中转化为治疗的比例（0~1，默认 1.0）
heal_target: "self"                # 治疗目标，默认自身；可指定为其他 actor
```

**语义**：使 `target` 失去 HP，并按 `drain_ratio` 治疗 `heal_target`。

**与 `deal_damage` + `heal` 的区别**：
- `drain_hp` **不触发** `before_take_damage` / `after_being_hit` / `on_hp_decrease` 等伤害相关 hook，避免循环触发。
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

#### `consume_team_hp_pct`

```yaml
# 假设 self.consume_pct 已通过 variable_bindings 绑定
effect_type: "consume_team_hp_pct"
target: "team_allies"
pct: "$self.consume_pct"
into_resource: "lc23042_hp_consumed"
```

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
