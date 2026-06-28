## 5. 效果类型 (Effect Type)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

Effect 是技能/行动/事件触发的最小执行单元。所有 effect 共享若干通用字段：

```yaml
effect:
  effect_type: "deal_damage"   # 必填：effect 类型
  target: "primary_target"     # 选填：目标选择器
  condition: "energy >= 120"   # 选填：触发条件（受限 DSL）
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

---

effect_type: "remove_modifier"
modifier_id: "MOD_XXX"
target: "enemy_single"
```

#### 修改属性

```yaml
effect_type: "add_stat"
stat: "spd"
amount: "$self.base_spd * 0.25"
```

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
amount: 100                  # 行动值推进 100（立即行动）
```

#### 回复战技点

```yaml
effect_type: "gain_skill_point"
amount: 1
```

#### 召唤/召唤物行动

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

见 `22_event_hook_system.md` 详细说明。

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
| `consume_resource_substitute` | 事件 hook 系统（见 `22_event_hook_system.md`） |
| `script`（任意 Python 表达式） | 受限 DSL 表达式；复杂逻辑拆分为多个声明式 effect 或 hook |

### 5.7 参数覆盖 vs 追加

- `override_action_param`：直接替换参数值（如万敌 E1 把战技主目标倍率从 0.55 改为 0.65）。
- `append_action_param`：在原值基础上加（如爻光 E1 使终结技触发的额外阿哈时刻多 10 笑点）。

两者都支持 `condition` 字段，可用于星魂等级、行迹解锁等条件判断。

---
