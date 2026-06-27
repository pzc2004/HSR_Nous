## 16. 自定义资源容器 (Custom Resources)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

### 16.1 设计目标

用统一的 `Dict[str, ResourceBlock]` 容纳所有战斗内可累积/消耗的资源（Coreflame / Punchline / 累计治疗等），避免为每种资源加硬编码字段。

**不属于 `custom_resources` 的两种关键数值**：
- `elation`（欢愉度）是 **StatBlock 面板属性**（见 `03_actor.md`），参与欢愉伤害公式，不是可消耗资源。
- `technique_point`（秘技点）是 **纯战前预算**，没有 current/max/regen/overflow 等战斗内语义，见 `18_technique_system.md`。

### 16.2 ResourceBlock 字段

```python
class ResourceBlock(BaseModel):
    resource_id: str
    max: float | Literal["inf"]
    current: float = 0.0
    owner: Literal["actor", "light_cone", "relic"] = "actor"
    scope: Literal["actor", "team"] = "actor"
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `resource_id` | string | 必填 | 资源唯一 ID，命名见 §16.4 |
| `max` | float / `"inf"` | 必填 | 上限；无上限用 `"inf"` |
| `current` | float | `0.0` | 当前值 |
| `owner` | enum | `"actor"` | 资源来源：`actor` / `light_cone` / `relic` |
| `scope` | enum | `"actor"` | 资源池归属：`actor`（私有） / `team`（全队共享） |

### 16.3 `owner` 与 `scope` 语义

两个字段正交：

| `owner` | 资源由谁提供 | 典型例子 |
|---------|--------------|----------|
| `actor` | 角色机制自带 | `coreflame`（白厄）、`punchline`（欢愉通用）、`hyacine_cumulative_heal`（风堇忆灵技） |
| `light_cone` | 装备的光锥赋予 | `lc23042_hp_consumed`（23042 "愿虹光永驻天空"） |
| `relic` | 装备的遗器套装赋予 | 未来 4 件套触发的层数资源（当前无实例） |

| `scope` | 资源池归属 | 典型例子 |
|---------|------------|----------|
| `actor` | 该角色私有 | 上述全部角色/光锥/遗器资源 |
| `team` | 整支队伍共享 | `technique_point` 之外可能的队伍资源（欢愉笑点当前仍按 actor 计，全队共享通过同步机制实现） |

### 16.4 资源 ID 命名约定

小写 + 下划线：

| ID | 出处 | Owner | 角色 / 光锥 |
|----|------|-------|-------------|
| `coreflame` | 形态值 | actor | Phainon |
| `scourge` | 终技累加 | actor | Phainon |
| `recollection` | 忆灵 | actor | Cyrene |
| `story` | 终技 | actor | Cyrene |
| `hyacine_cumulative_heal` | 本场累计治疗 | actor | 风堇 1140901 忆灵技 |
| `punchline` | 笑点 | actor | 欢愉通用 |
| `certified_banger` | 好活当赏 | actor | 欢愉通用 |
| `hidden_mmr` | 隐藏 MMR | actor | Silver Wolf LV.999 |
| `climax` | 爆点 | actor | 火花 |
| `merrymake` | 欢庆值 | actor | Evanescia |
| `lc23042_hp_consumed` | HP 消耗累加 | light_cone | 23042 "愿虹光永驻天空" |

### 16.5 新增 effect_type

以下 effect 的 `amount` / `pct` 字段统一支持表达式（见 §16.6）。

#### `gain_resource`

```yaml
effect_type: "gain_resource"
resource_id: "punchline"
amount: 5
overflow_policy: "cap"   # "cap" | "allow" | "convert_to_extra"（系统默认值 TBD）
```

#### `consume_resource`

```yaml
effect_type: "consume_resource"
resource_id: "hyacine_cumulative_heal"
amount: "ratio:0.5"      # 消耗 current 的 50%
on_insufficient: "fail"  # "fail" | "clamp" | "consume_all"
```

#### `consume_team_hp_pct`

```yaml
# 光锥 23042 "愿虹光永驻天空" 用例
effect_type: "consume_team_hp_pct"
target: "team_allies"
pct: "$self.consume_pct"
into_resource: "lc23042_hp_consumed"
```

### 16.6 `amount` 字段表达式

`gain_resource` / `consume_resource` / `deal_damage` / `heal` 等 effect 的数值字段支持：

- 常量：`amount: 5`
- 关键字：`amount: "all"`（全部）、`amount: "ratio:0.5"`（比例的 50%）
- 表达式：`amount: "heal_value * 0.02"`、`amount: "current * 0.28"`
- 引用资源：`amount: "$resource.hyacine_cumulative_heal * 0.5"`
- 引用前序 effect 结果：`amount: "$prev.amount * 0.8"`

> **安全红线**：表达式走受限 DSL，禁止 `eval` Python 代码。白名单变量见 `09_faq.md` / `13_validator.md`。

### 16.7 光锥资源

装备特定光锥时角色才拥有某种资源。光锥模板需要：
- 声明 `custom_resources`（`owner: "light_cone"`）
- 用 `variable_bindings` 按叠影查表
- effects 中引用 `$resource.xxx` 或 `$self.xxx`

```yaml
# data/sim_templates/light_cones/23042.yaml
id: "23042"
name: "愿虹光永驻天空"

lookup_tables:
  speed_pct:          [0.180, 0.225, 0.270, 0.315, 0.360]
  consume_pct:        [0.010, 0.0125, 0.015, 0.0175, 0.020]
  dmg_taken_pct:      [0.180, 0.225, 0.270, 0.315, 0.360]
  dmg_taken_duration: [2, 2, 2, 2, 2]
  multiplier:         [2.500, 3.125, 3.750, 4.375, 5.000]

variable_bindings:
  - self.speed_pct          = lookup_table("speed_pct",          index=$build.light_cone.superimposition - 1)
  - self.consume_pct        = lookup_table("consume_pct",        index=$build.light_cone.superimposition - 1)
  - self.dmg_taken_pct      = lookup_table("dmg_taken_pct",      index=$build.light_cone.superimposition - 1)
  - self.dmg_taken_duration = lookup_table("dmg_taken_duration", index=$build.light_cone.superimposition - 1)
  - self.multiplier         = lookup_table("multiplier",         index=$build.light_cone.superimposition - 1)

custom_resources:
  lc23042_hp_consumed:
    max: 999999
    owner: "light_cone"
    scope: "actor"

effects:
  - effect_type: "stat_bonus"
    stat: "spd"
    value: "$self.speed_pct"
  - trigger: "on_after_action"
    effect_type: "consume_team_hp_pct"
    target: "team_allies"
    pct: "$self.consume_pct"
    into_resource: "lc23042_hp_consumed"
  - trigger: "on_memosprite_attack"
    effect_type: "deal_damage"
    target: "primary"
    amount: "$resource.lc23042_hp_consumed * $self.multiplier"
  - trigger: "on_memosprite_skill"
    effect_type: "apply_debuff"
    target: "all_enemies"
    stat: "dmg_taken"
    value: "$self.dmg_taken_pct"
    duration: "$self.dmg_taken_duration"
```

S5 求值后绑定结果：`speed_pct=0.30`、`consume_pct=0.020`、`dmg_taken_pct=0.360`、`dmg_taken_duration=2`、`multiplier=5.0`。

### 16.8 累加器 = 资源 + 表达式

**核心原则**：累加器不是一种独立原语，它是 `custom_resources`（纯存储） + 通用 effect（读/写/转换） + 表达式引擎的组合。不要在 schema 里枚举“累加器类型”。

**案例 1：风堇 1140901 忆灵技**

```yaml
# 对敌方全体造成 累计治疗 × #1% 伤害，清空 累计治疗 × #2%
- id: "hyacine_1140901"
  trigger: "on_memosprite_skill"
  effects:
    - effect_type: "deal_damage"
      target: "all_enemies"
      element: "wind"
      amount: "$resource.hyacine_cumulative_heal * $self.damage_ratio"
    - effect_type: "consume_resource"
      resource_id: "hyacine_cumulative_heal"
      amount: "ratio:$self.clear_ratio"
```

**案例 2：23042 光锥**

```yaml
- id: "lc23042_consume"
  trigger: "on_after_action"
  effects:
    - effect_type: "consume_team_hp_pct"
      target: "team_allies"
      pct: "$self.consume_pct"
      into_resource: "lc23042_hp_consumed"

- id: "lc23042_memosprite_attack"
  trigger: "on_memosprite_attack"
  effects:
    - effect_type: "deal_damage"
      target: "primary"
      amount: "$resource.lc23042_hp_consumed * $self.multiplier"
    - effect_type: "consume_resource"
      resource_id: "lc23042_hp_consumed"
      amount: "all"
```

### 16.9 用 `variable_bindings` 处理星魂/行迹 patch

风堇 M6 把 1140901 的清空比例从 0.5 改为 0.12。在 DSL 设计下，这是 `variable_bindings` 里的条件覆盖：

```yaml
# data/sim_templates/characters/1409_hyacine.yaml 片段
variable_bindings:
  - self.damage_ratio = lookup_table("skill_1140901_damage_ratio", index=$build.skill_levels.skill - 1)
  - self.clear_ratio  = lookup_table("skill_1140901_clear_ratio",  index=$build.skill_levels.skill - 1)
  - if $build.eidolon >= 6:
      self.clear_ratio = 0.12
```

> 为什么不用双 condition effect：同一个语义写两份互斥 effect 可读性差；若 M6 改的值被多处引用，双 condition 要复制 N 份。

### 16.10 与 modifier 叠层的区别

`modifiers[].max_stack` 仍是独立概念（叠层 buff），不在 `custom_resources` 体系内。原因：
- 叠层 buff 的消费方是**属性计算**（`add_stat_per_stack`）。
- 累加器的消费方是**读当前值并产出 X**（伤害、清空、转换）。

两者语义不同，不能混用。

### 16.11 TBD

- 资源 overflow 的系统默认策略（§5 #2）。
- 跨战斗持久化资源（cross-encounter state）。
- `team` scope 资源的同步/合并规则。

---
