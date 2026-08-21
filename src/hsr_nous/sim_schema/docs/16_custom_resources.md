## 16. 自定义资源容器 (Custom Resources)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

### 16.1 设计目标

用统一的 `Dict[str, ResourceBlock]` 容纳所有战斗内可累积/消耗的资源（Coreflame / Punchline / 累计治疗等），避免为每种资源加硬编码字段。

**不属于 `custom_resources` 的两种关键数值**：
- `elation`（欢愉度）是 **StatBlock 面板属性**（见 `03_actor.md`），参与欢愉伤害公式，不是可消耗资源。
- `technique_point`（秘技点）是 **纯战前预算**，没有 current/max/regen/overflow 等战斗内语义，见 `18_technique_system.md`。

### 16.2 ResourceBlock 字段

```python
class ResourceBlock(BaseModel):
    resource_id: str | None = None   # 在 YAML 中可省略，由 custom_resources 的 dict key 提供
    max: float | Literal["inf"]
    current: float = 0.0
    owner: Literal["actor", "light_cone", "relic"] = "actor"
    scope: Literal["actor", "team"] = "actor"
    # ---- 充能资源三段式与溢出（§16.12）----
    ult_threshold: float | list[float] | None = None
    activation_grant: float | None = None
    overflow_mode: Literal["none", "bank"] = "none"
    bank_max: float | None = None
    bank_refund: str | None = None
    # ---- 机制注入与持久化（§16.13 / §16.14）----
    host: str = "self"               # self | allies | enemies | named(id)
    provenance: bool = False
    persist_across_battles: bool = False
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `resource_id` | string? | `None` | 资源唯一 ID。在 `custom_resources: {id: ResourceBlock}` 写法中可省略，由 dict key 提供 |
| `max` | float / `"inf"` | 必填 | 上限；无上限用 `"inf"`。可 ≠ 开大所需，且可被 modifier `max_override` 覆写（见 §16.12） |
| `current` | float | `0.0` | 当前值 |
| `owner` | enum | `"actor"` | 资源来源：`actor` / `light_cone` / `relic` |
| `scope` | enum | `"actor"` | 资源池归属：`actor`（私有） / `team`（全队共享） |
| `ult_threshold` | float / list? | `None` | 激活阈值（开大所需）；多档写 `[90, 180]`（银枝双档，各档对应不同终结技版本）。缺省 = `max` |
| `activation_grant` | float? | `None` | 激活提供值——`activate_ultimate` 类效果实际补到的量（昔涟给到阈值 24 而非充满）；**独立字段，不可默认 = 上限**；缺省 = 补到 `ult_threshold` |
| `overflow_mode` | enum | `"none"` | 溢出形态：`none` 作废（默认）/ `bank` 银行（**糖**，desugar 见 §16.12，引擎零新概念） |
| `bank_max` | float? | `None` | `bank` 糖的银行存储上限（展开为独立银行资源的 max） |
| `bank_refund` | string? | `None` | `bank` 糖的返还时机（如 `"after_ultimate"` 开大后返还；展开为返还 hook） |
| `host` | enum | `"self"` | 资源长在谁身上：`self` / `allies` / `enemies` / `named(id)`；初始化时**物化到对方面板**（调试界面可见真实变量，非 modifier 标记），见 §16.13 |
| `provenance` | bool | `false` | `true` = 记录来源集合，配 `unique_sources(resource)` 按来源去重计数（昔涟"不同队友数"，见 §16.13）；**计数口径（决策卡 #20 钉死）= 当前持有**（来源集合随资源耗尽清空重计，非历史累计） |
| `persist_across_battles` | bool | `false` | 跨战斗保留（波提欧类；实测深渊不生效、连战场景用，低优先级，见 §16.14） |

> **YAML 简写**：`custom_resources` 是 `Dict[str, ResourceBlock]`，key 即资源 ID，因此 value 中通常不写 `resource_id`：
>
> ```yaml
> custom_resources:
>   punchline:
>     max: 999999
>     owner: "actor"
>     scope: "team"
> ```

### 16.3 `owner` 与 `scope` 语义

两个字段正交：

| `owner` | 资源由谁提供 | 典型例子 |
|---------|--------------|----------|
| `actor` | 角色机制自带 | `coreflame`（白厄）、`hyacine_cumulative_heal`（风堇忆灵技） |
| `light_cone` | 装备的光锥赋予 | `lc23042_hp_consumed`（23042 "愿虹光永驻天空"） |
| `relic` | 装备的遗器套装赋予 | 未来 4 件套触发的层数资源（当前无实例） |

| `scope` | 资源池归属 | 典型例子 |
|---------|------------|----------|
| `actor` | 该角色私有 | `coreflame`、`scourge`、`hyacine_cumulative_heal`、`lc23042_hp_consumed` 等 |
| `team` | 整支队伍共享 | `punchline`（欢愉笑点） |

### 16.4 资源 ID 命名约定

小写 + 下划线：

| ID | 出处 | Owner | 角色 / 光锥 |
|----|------|-------|-------------|
| `coreflame` | 形态值 | actor | Phainon |
| `scourge` | 终技累加 | actor | Phainon |
| `recollection` | 忆灵 | actor | Cyrene |
| `story` | 终技 | actor | Cyrene |
| `hyacine_cumulative_heal` | 本场累计治疗 | actor | 风堇 1140901 忆灵技 |
| `punchline` | 笑点 | actor（scope: team，全队共享） | 欢愉通用 |
| `certified_banger` | 好活当赏 | actor | 欢愉通用 |
| `hidden_mmr` | 隐藏 MMR | actor | Silver Wolf LV.999 |
| `climax` | 爆点 | actor | 火花 |
| `merrymake` | 增笑 | actor | Evanescia |
| `lc23042_hp_consumed` | HP 消耗累加 | light_cone | 23042 "愿虹光永驻天空" |

### 16.5 新增 effect_type

以下 effect 的 `amount` / `pct` 字段统一支持表达式（见 §16.6）。

#### `gain_resource`

```yaml
effect_type: "gain_resource"
resource_id: "punchline"
amount: 5
# 溢出由资源自身声明的 overflow_mode 处理（§16.12），effect 不再带溢出字段
```

#### `consume_resource`

```yaml
effect_type: "consume_resource"
resource_id: "hyacine_cumulative_heal"
amount: "ratio:0.5"      # 消耗 current 的 50%
on_insufficient: "fail"  # "fail" | "clamp" | "consume_all"
```

#### ~~`consume_team_hp_pct`~~（已废弃）

> **废弃**：改用 `drain_hp` + 可选字段 `into_resource`（见 `05_effects.md` §5.2）。等价写法：

```yaml
# 光锥 23042 "愿虹光永驻天空" 用例
effect_type: "drain_hp"
target: "team_allies"
amount: "ratio:$self.consume_pct"
drain_ratio: 0
into_resource: "lc23042_hp_consumed"
```

### 16.6 `amount` 字段表达式

`gain_resource` / `consume_resource` / `deal_damage` / `heal` 等 effect 的数值字段支持：

- 常量：`amount: 5`
- 关键字：`amount: "all"`（全部）、`amount: "ratio:0.5"`（比例的 50%）
- 表达式：`amount: "$prev.amount * 0.02"`、`amount: "$resource.current * 0.28"`（变量须带 `$` 前缀，见 13.5/22.4 白名单）
- 引用资源：`amount: "$resource.hyacine_cumulative_heal * 0.5"`
- 引用前序 effect 结果：`amount: "$prev.amount * 0.8"`

> **安全红线**：表达式走受限 DSL，禁止 `eval` Python 代码。白名单变量见 `13_validator.md` §13.5 / `22_syntax_reference.md` §22.4。

### 16.7 光锥资源

装备特定光锥时角色才拥有某种资源。光锥模板需要：
- 声明 `custom_resources`（`owner: "light_cone"`）
- 用 `variable_bindings` 按叠影查表
- effects 中引用 `$resource.xxx` 或 `$self.xxx`

```yaml
# data/sim_templates/light_cones/23042.yaml
light_cone_id: "23042"
name: "愿虹光永驻天空"

lookup_tables:
  speed_pct:          [0.180, 0.225, 0.270, 0.315, 0.360]
  consume_pct:        [0.010, 0.0125, 0.015, 0.0175, 0.020]
  vulnerability_pct:  [0.180, 0.225, 0.270, 0.315, 0.360]
  vulnerability_duration: [2, 2, 2, 2, 2]
  multiplier:         [2.500, 3.125, 3.750, 4.375, 5.000]

variable_bindings:
  - self.speed_pct          = lookup_table("speed_pct",          index=$build.light_cone.superimposition - 1)
  - self.consume_pct        = lookup_table("consume_pct",        index=$build.light_cone.superimposition - 1)
  - self.vulnerability_pct      = lookup_table("vulnerability_pct",      index=$build.light_cone.superimposition - 1)
  - self.vulnerability_duration = lookup_table("vulnerability_duration", index=$build.light_cone.superimposition - 1)
  - self.multiplier         = lookup_table("multiplier",         index=$build.light_cone.superimposition - 1)

custom_resources:
  lc23042_hp_consumed:
    max: 999999
    owner: "light_cone"
    scope: "actor"

effects:
  - trigger: "on_battle_start"
    effect_type: "apply_modifier"
    target: "self"
    modifier:
      modifier_id: "MOD_LC_23042_SPD"
      modifier_type: "buff"
      stat: "spd"
      flat_bonus: "$self.speed_pct"
      duration: 0
  - trigger: "on_after_action"
    effect_type: "drain_hp"
    target: "team_allies"
    amount: "ratio:$self.consume_pct"
    drain_ratio: 0
    into_resource: "lc23042_hp_consumed"
  - trigger: "on_memosprite_attack"
    effect_type: "deal_damage"
    target: "primary_target"
    amount: "$resource.lc23042_hp_consumed * $self.multiplier"
  - trigger: "on_memosprite_skill"
    effect_type: "apply_modifier"
    target: "all_enemies"
    modifier:
      modifier_id: "MOD_LC_23042_VULNERABILITY"
      modifier_type: "debuff"
      stat: "vulnerability"
      flat_bonus: "$self.vulnerability_pct"
      duration: "$self.vulnerability_duration"
```

S5 求值后绑定结果：`speed_pct=0.360`、`consume_pct=0.020`、`vulnerability_pct=0.360`、`vulnerability_duration=2`、`multiplier=5.0`。

### 16.8 累加器 = 资源 + 表达式

**核心原则**：累加器不是一种独立原语，它是 `custom_resources`（纯存储） + 通用 effect（读/写/转换） + 表达式引擎的组合。不要在 schema 里枚举“累加器类型”。

**案例 1：风堇 1140901 忆灵技**

> 以下用 `modifier_id + trigger + effects` 的伪代码形式拆解逻辑；真实模板结构（action 形式）见 §16.7 与 `07_examples.md`。

```yaml
# 假设 self.damage_ratio / self.clear_ratio 已通过 variable_bindings 绑定（详见 §16.10）
- modifier_id: "hyacine_1140901"
  trigger: "on_memosprite_skill"
  effects:
    - effect_type: "deal_damage"
      target: "all_enemies"
      damage_type: "wind"
      amount: "$resource.hyacine_cumulative_heal * $self.damage_ratio"
    - effect_type: "consume_resource"
      resource_id: "hyacine_cumulative_heal"
      amount: "ratio:$self.clear_ratio"
```

**案例 2：23042 光锥**

> 以下用 `modifier_id + trigger + effects` 的伪代码形式拆解逻辑；真实模板结构见 §16.7 与 `07_examples.md`。

```yaml
# 战前启动：给装备者加速
- modifier_id: "lc23042_battle_start"
  trigger: "on_battle_start"
  effects:
    - effect_type: "apply_modifier"
      target: "self"
      modifier:
        modifier_id: "MOD_LC_23042_SPD"
        modifier_type: "buff"
        stat: "spd"
        flat_bonus: "$self.speed_pct"
        duration: 0

# 装备者行动后：消耗全队 HP 累加到资源
- modifier_id: "lc23042_consume"
  trigger: "on_after_action"
  effects:
    - effect_type: "drain_hp"
      target: "team_allies"
      amount: "ratio:$self.consume_pct"
      drain_ratio: 0
      into_resource: "lc23042_hp_consumed"

# 忆灵攻击时：用资源造成额外伤害
- modifier_id: "lc23042_memosprite_attack"
  trigger: "on_memosprite_attack"
  effects:
    - effect_type: "deal_damage"
      target: "primary_target"
      amount: "$resource.lc23042_hp_consumed * $self.multiplier"
```

### 16.9 复杂资源逻辑用 Hook

当资源消费涉及"抵扣"、"替代"、"双向同步"等复杂逻辑时，优先使用事件 hook 系统而不是特殊 effect_type。

例如：
- 火花 `climax` 抵扣 `sp`：`before_consume(sp)` hook
- 银狼 LV.999 盲盒：`after_consume(sp)` hook
- 绯英能量 ↔ 好活当赏双向同步：`after_gain(energy)` + `after_gain(certified_banger)` hooks

详见 `23_event_hook_system.md`。

### 16.10 用 `variable_bindings` 处理星魂/行迹 patch

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

### 16.11 与 modifier 叠层的区别

`modifiers[].max_stack` 仍是独立概念（叠层 buff），不在 `custom_resources` 体系内。原因：
- 叠层 buff 的消费方是**属性计算**（`add_stat_per_stack`）。
- 累加器的消费方是**读当前值并产出 X**（伤害、清空、转换）。

两者语义不同，不能混用。

### 16.12 充能资源三段式与溢出形态

充能类资源（能量及追忆等新式充能）按**三段式**建模（机制事实见 `../../../../docs/mechanics/05_energy_system.md` §5.2）：

1. **开大所需** = `ult_threshold`——可多档（银枝 `[90, 180]`，各档对应不同终结技版本；policy 合法性按当前值开放对应档位）
2. **能量上限** = `max`——可 ≠ 所需，且可被 modifier `max_override` 覆写（遐蝶诗篇：新蕊上限 100 → 200；绯英上限 = 2× 所需，可存两段连放）
3. **激活提供值** = `activation_grant`——独立字段，不可默认 = 上限（昔涟激活给到阈值 24 而非充满）

**内建能量资源**：`energy` 是内建充能资源（面板映射 `base_stats.max_energy` / `energy`）；有三段式需求的角色在 `custom_resources` 声明 `energy` 块挂扩展字段（`ult_threshold` / `overflow_mode` 等），不重复计值。

**溢出形态 `overflow_mode`**（超出 `max` 的部分如何处理）：

| 取值 | 语义 | 实例 |
|------|------|------|
| `none`（默认） | 作废 | 普通能量 |
| `bank`（**糖**） | 银行：溢出存入银行（上限 `bank_max`），按 `bank_refund` 声明的时机返还 | 千冶刃·Saber 型（开大后返还） |

```yaml
# 银枝双档终结技
custom_resources:
  energy:
    max: 180
    ult_threshold: [90, 180]     # 90 → 小版终结技；180 → 完整版
```

```yaml
# 遐蝶诗篇：modifier 覆写资源上限（新蕊 100 → 200）
modifier:
  modifier_id: "MOD_CASTORICE_POEM_MAX"
  modifier_type: "buff"
  target_resource: "newbud"      # 覆写哪个资源的 max
  max_override: 200
  duration: 0
```

```yaml
# 千冶刃·Saber 型银行：溢出存储、开大后返还（表面声明）
custom_resources:
  energy:
    max: 160
    overflow_mode: "bank"
    bank_max: 160
    bank_refund: "after_ultimate"
```

**bank 的 desugar（决策卡 #19 降级，糖非一等字段）**：`overflow_mode: "bank"` 在绑定/编译期展开为**两个普通资源 + 转移 hook + 返还 hook**——引擎只见普通资源件，不认识 bank 概念：

```yaml
# 展开产物（等价手写形）
custom_resources:
  energy: {max: 160, overflow_mode: "none"}     # 主资源：超顶作废
  energy_bank: {max: 160}                        # 银行本体（bank_max 即其 max）
hooks:
  # before_gain(energy, waterfall)：获得量改写为"填满主资源 + 溢出部分灌银行"
  # on_<bank_refund 时机>：从银行回填（clamp 至主资源余量）
```

**边缘语义（钉死）**：① 溢出量 = attempted gain − 填满主资源所需量（截断时点在 before_gain 改写处，唯一口径）；② 银行满时的二层溢出 = 作废（`overflow_mode: "none"` 语义，不再回流）；③ 返还时主资源若又顶到上限，**不再回流银行**（防递归——返还只做一次 clamp，多出作废）。

> 落地自决策卡 #13（2026-08-14，字段形态）、#19（2026-08-20，**降级为糖**——owner 裁决：通用资源件可组合，但溢出量/二层溢出/返还递归三个翻车点须在糖定义里钉死）。注：`extend` 超顶形态已退役（R10-O4 裁决 2026-08-15）——昔涟型的正确模型是 `max`=真实上限 27 + `ult_threshold`=激活阈值 24，上限本来就是 27，不存在超顶；`overflow_cap` 字段同步移除。

### 16.13 机制注入三件套

"我的机制长在别人身上"的通用通道：

1. **`host` 声明**——资源可长在队友/敌人身上（`host: allies | enemies | named(id)`，默认 `self`），初始化时**真实物化**在对方面板（调试界面可见真实变量，非 modifier 标记）
2. **`$modifier.source`**——挂在他人身上的 modifier 可引用施加者（见 `04_modifier.md` §4.2；昔涟未来标记消耗后给昔涟回追忆）
3. **`provenance: true` + `unique_sources(resource)`**——资源记录来源集合，按来源去重计数（昔涟"不同队友数"）

```yaml
# 昔涟：点亮 + 未来标记 + 去重计数
custom_resources:
  recollection:
    max: 27                      # 真实上限 27（技能参数 [1,0.1,27,24,12]）——上限本来就是 27，不存在超顶
    ult_threshold: 24            # 激活阈值：攒到 24 即可开大
    activation_grant: 24         # 激活给到阈值 24，而非充满
  xilian_future_mark:
    max: 1
    host: "allies"               # 标记长在每个队友面板上
    provenance: true             # 记录来源（按队友去重）

hooks:
  # 队友消耗未来标记 → 昔涟回追忆
  - event: "after_consume"
    target_resource: "xilian_future_mark"
    scope: "team"
    effects:
      # 去重计数：unique_sources("xilian_future_mark") 返回不同来源队友数（白名单见 22_syntax_reference.md §22.4）
      - effect_type: "gain_resource"
        resource_id: "recollection"
        amount: 1
```

> 落地自决策卡 #13（2026-08-14）

### 16.14 跨战斗持久化

`persist_across_battles: true` 的资源在战斗结束（波次/关卡切换）后保留当前值——波提欧类跨战斗叠层。**注意**：实测深渊（多波次连续作战）中该保留不生效，主要用于连战场景；低优先级实现。

> 落地自决策卡 #14（2026-08-14）

### 16.15 TBD

- `team` scope 资源的同步/合并规则。

---
