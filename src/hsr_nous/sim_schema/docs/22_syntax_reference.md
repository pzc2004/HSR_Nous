## 22. DSL 语法参考 (Syntax Reference)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

### 22.1 总览

`sim_schema` DSL 是基于 YAML/JSON 语法的声明式配置语言，用于描述角色/光锥/遗器/敌人/关卡的战斗机制。

它由三部分组成：

1. **数据声明语法**：YAML/JSON 本身（字段、列表、字典、字符串）
2. **变量绑定语法**：`variable_bindings` 字段中的 `lookup_table()` 和 `if` 语句
3. **表达式 DSL**：`amount`、`condition`、`target`、`in_zone_filter` 等字段中的受限表达式

### 22.2 文件格式

模板文件使用 `.yaml` 或 `.json`：

```yaml
# data/sim_templates/characters/1001_march_7th.yaml
actor_id: "1001"
name: "march_7th"
path: "preservation"
damage_type: "ice"

lookup_tables:
  base_hp_by_level: [1200, 1300, 1400]
  basic_scaling: [0.50, 0.55, 0.60]

variable_bindings:
  - self.base_hp      = lookup_table("base_hp_by_level", index=$build.level - 1)
  - self.basic_scaling = lookup_table("basic_scaling",  index=$build.skill_levels.basic - 1)

actions:
  - action_id: "100101"
    action_type: "basic"
    effects:
      - effect_type: "deal_damage"
        amount: "$self.atk * $self.basic_scaling"
```

### 22.3 `variable_bindings` 语法

每个模板通过 `variable_bindings` 字段把 build 配置转换成具体数值。

#### 查表绑定

```yaml
self.<var_name> = lookup_table("<table_name>", index=<expression>)
```

`lookup_table` 查找本模板内嵌的 `lookup_tables[<table_name>][<index>]`。

> `lookup_table` 主要用于 `variable_bindings`，也可在全局公式或 effect 表达式中调用。effect 表达式中推荐先通过 `variable_bindings` 绑定到 `$self.xxx`，再读取该变量，以保持 effect 简洁。

#### 条件覆盖

```yaml
if <condition>:
    self.<var_name> = <value>
```

常用于星魂/行迹 patch：

```yaml
variable_bindings:
  - self.clear_ratio = lookup_table("skill_clear_ratio", index=$build.skill_levels.skill - 1)
  - if $build.eidolon >= 6:
      self.clear_ratio = 0.12
```

#### 命名空间

- `self.xxx`：本模板变量（角色/光锥/遗器/敌人实例）
- `$self.xxx`：运行时表达式中对当前实例的引用
- `$self.memosprite.xxx`：忆灵属性（仅角色模板）

### 22.4 表达式 DSL

表达式用于 `amount`、`condition`、`target`、`in_zone_filter` 等字段。

#### 白名单变量

| 变量 | 含义 | 可用位置 |
|------|------|---------|
| `$self.xxx` | 当前 actor 字段/变量 | 任意表达式 |
| `$resource.xxx` | 自定义资源当前值 | 任意表达式 |
| `$event.xxx` | 事件上下文 | 事件响应全域（hook / modifier trigger / summon trigger / hit_condition；完整字段见 `23_event_hook_system.md`） |
| `$target.xxx` | 主目标字段 | 伤害/治疗/效果表达式 |
| `$build.xxx` | build 配置 | `variable_bindings` condition / effect `condition` |
| `$prev.xxx` | 同一 action 内前一个 effect 的结果 | effect 表达式 |
| `$last.xxx` | hook effects 链中上一个 effect 执行后的 `$event` 状态 | 仅 hook effect（字段：`amount` / `actual_amount` / `cancel` / `target` 等） |
| `$team.xxx` | 队伍级聚合字段（如全队总 taunt、队伍平均速度等） | 部分表达式（具体见各字段定义） |

#### 白名单函数

| 函数 | 说明 |
|------|------|
| `chance(N)` | N% 概率判定（仅 condition 上下文） |
| `in_zone(zone_id)` | 目标是否在指定 zone 内（仅 condition 上下文） |
| `zone_owner()` | 返回 zone 的拥有者（见 19_zone_system.md） |
| `min(a, b)` / `max(a, b)` | 最值 |
| `sum(iterable)` | 求和（如 `sum($team.taunt)`） |
| `clamp(x, lo, hi)` | 裁剪到 [lo, hi] |
| `abs(x)` / `round(x)` | 绝对值 / 四舍五入 |
| `lookup_table(name, index)` | 查本模板内嵌表；主要用于 `variable_bindings`，effect 中不推荐 |

#### 运算符

支持标准算术、比较、逻辑运算符：

```yaml
amount: "$self.max_hp * 0.3 + 200"
```

```yaml
condition: "$resource.punchline > 100 && !$target.broken"
```

```yaml
condition: "$self.hp / $self.max_hp < 0.5"
```

#### 禁止项

表达式 DSL 禁止以下行为（安全红线）：

- `import` / `exec` / `eval`
- 循环语句
- 文件 I/O
- 网络访问
- 反射 / 任意 Python 语法

### 22.5 `amount` 字段写法

`amount` / `pct` 等数值字段支持多种形式：

| 形式 | 示例 | 说明 |
|------|------|------|
| 常量 | `amount: 5` | 固定数值 |
| 关键字 | `amount: "all"` | 全部当前值 |
| 比例 | `amount: "ratio:0.5"` | 当前值的 50% |
| 表达式 | `amount: "$self.max_hp * 0.3"` | 运行时求值 |
| 资源引用 | `amount: "$resource.punchline * 0.1"` | 读资源当前值 |
| 前序结果 | `amount: "$prev.amount * 0.8"` | 同一 action 前一个 effect 结果 |

### 22.6 `condition` 表达式

`condition` 是返回布尔值的字符串表达式：

```yaml
condition: "$self.hp / $self.max_hp < 0.5"
```

```yaml
condition: "$build.eidolon >= 6"
```

```yaml
condition: "$resource.punchline > 100 && !$target.broken"
```

```yaml
condition: "in_zone('yao_zone')"
```

### 22.7 `target` 选择器

target 字段支持字符串预注册选择器或参数字典。

#### 字符串预注册选择器

| 选择器 | 说明 |
|--------|------|
| `self` | 自身 |
| `primary_target` | action 的主目标（由 `target_type` 决定） |
| `random_enemy` | 随机敌人 |
| `random_ally` | 随机友方 |
| `lowest_hp_enemy` | 当前 HP 最低的敌人 |
| `lowest_hp_ally` | 当前 HP 最低的友方（含自身） |
| `highest_hp_enemy` | 当前 HP 最高的敌人 |
| `highest_hp_ally` | 当前 HP 最高的友方 |
| `all_enemies` | 全体敌人 |
| `all_allies` | 全体友方（含自身） |
| `ally_single` | 单个友方（通常配合 `target_type` 或默认主目标） |
| `enemy_single` | 单个敌人（通常配合 `target_type` 或默认主目标） |
| `ally_aoe` | 友方群体 |
| `enemy_aoe` | 敌方群体 |
| `team_allies` | 队伍内所有友方（不含召唤物/忆灵等独立行动单位） |
| `owner` | 召唤物/忆灵的召唤者 |
| `$self.memosprite` | 自身的忆灵（表达式形式，用于 hook/effect 中动态取值） |
| `$event.target` | 事件触发目标（事件响应全域：hook / modifier trigger / summon trigger / hit_condition） |
| `$event.targets` | 累积模式下的事件目标列表（hook 累积模式） |

#### 参数化选择器

```yaml
target:
  type: "min"
  key: "stats.hp"
```

```yaml
target:
  type: "filter"
  condition: "in_zone('yao_zone')"
```

参数化选择器用于预注册选择器无法表达的复杂目标逻辑。

> **扩散（Blast）攻击的目标声明**：当前版本**没有** `enemy_blast` / `adjacent` 选择器——不要虚构。扩散攻击暂用 `enemy_single` 声明主目标；相邻目标的副目标伤害与削韧由公式层的打击方式默认值处理（`01_formula.md` §1.5 / §1.11：扩散主 20 / 副 10 削韧）。为扩散声明主/副目标倍率的 `attack_pattern: "blast"` 字段是 schema 候选扩展，落地前一律按上述近似写法。

### 22.8 命名空间约定

| 上下文 | 前缀 | 例子 |
|--------|------|------|
| variable_bindings 赋值 | `self.xxx` | `self.base_hp = ...` |
| effect 表达式取值 | `$self.xxx` | `amount: "$self.max_hp * 0.3"` |
| 资源取值 | `$resource.xxx` | `amount: "$resource.punchline"` |
| 事件上下文 | `$event.xxx` | `condition: "$event.target != $self.memosprite"` |
| 目标取值 | `$target.xxx` | `condition: "$target.hp < $target.max_hp * 0.5"` |
| build 配置 | `$build.xxx` | `if $build.eidolon >= 6:` / `condition: "$build.eidolon >= 1"` |

### 22.9 条件表达式

DSL 支持类 C 三元运算符：

```yaml
condition: "$target.hp / $target.max_hp < 0.5"
base_universal_multi: "target_toughness > 0 ? 0.9 : 1.0"
```

- 只支持 `condition ? true_value : false_value` 形式
- 不支持 Python 风格 `true_value if condition else false_value`
- `?` 和 `:` 两侧建议加空格，提高可读性

涉及 `random()` 的三元表达式只能在**全局公式层**使用（如 `crit_multi`），effect 表达式层禁止 `random()`。详见 §22.10。

### 22.10 函数白名单

DSL 表达式按使用位置分为两层白名单：

| 位置 | 允许函数 | 说明 |
|------|---------|------|
| **全局公式** (`data/sim_templates/global/formulas.yaml`) | effect 层全部 + `random()` | `random()` 均匀随机数 `[0,1)`，仅公式层可用，避免单个 effect 内引入不可控随机性 |
| **effect 表达式** (`amount` / `condition` / `target_filter` 等) | `clamp()`, `min()`, `max()`, `abs()`, `round()`, `sum()`, `lookup_table()`, `zone_owner()`；condition 上下文另允许 `chance()`, `in_zone()` | `sum()` 用于聚合（如 `sum($team.taunt)`）；`lookup_table()` 允许但不推荐（优先读已绑定变量）；随机判定通过 `chance()` 显式表达，禁 `random()` |

> 本表与 `13_validator.md` §13.5.2/§13.5.3 互为镜像，改动必须同步（唯一事实来源为本节，13 为校验视角复述）。

所有位置都禁止：文件 I/O、网络、反射、任意 Python 内置函数。

### 22.11 完整示例

> 以下示例展示语法形态；`hooks` 的完整语义（事件类型、累积模式、`$event` 可变性等）见 `23_event_hook_system.md`。

```yaml
# data/sim_templates/characters/1409_hyacine.yaml
actor_id: "1409"
name: "hyacine"

lookup_tables:
  base_hp_by_level:        [1200, 1300, 1400]
  skill_1140901_clear_ratio:  [0.50, 0.50, 0.50, 0.50, 0.50]
  skill_1140901_damage_ratio: [0.50, 0.55, 0.60, 0.65, 0.70]
  memps_drain_pct:         [0.05, 0.05, 0.05, 0.05, 0.05]

variable_bindings:
  - self.base_hp          = lookup_table("base_hp_by_level",      index=$build.level - 1)
  - self.clear_ratio      = lookup_table("skill_1140901_clear_ratio", index=$build.skill_levels.skill - 1)
  - self.damage_ratio     = lookup_table("skill_1140901_damage_ratio", index=$build.skill_levels.skill - 1)
  - self.memps_drain_pct  = lookup_table("memps_drain_pct", index=$build.skill_levels.talent - 1)
  - if $build.eidolon >= 6:
      self.clear_ratio = 0.12

custom_resources:
  hyacine_cumulative_heal:
    max: 999999

actions:
  - action_id: "1140901"
    action_type: "memosprite_skill"
    effects:
      - effect_type: "deal_damage"
        target: "all_enemies"
        amount: "$resource.hyacine_cumulative_heal * $self.damage_ratio"
      - effect_type: "consume_resource"
        resource_id: "hyacine_cumulative_heal"
        amount: "ratio:$self.clear_ratio"

hooks:
  - event: "on_hp_decrease"
    scope: "team"
    condition: "$event.target != $self.memosprite"
    accumulated: true
    flush_triggers: ["on_turn_start", "on_after_action"]
    effects:
      # A 模型（X2 裁决）：小伊卡消耗自身 HP → 治疗掉血目标；drain 自身会再发 on_hp_decrease(reason='drain')，上方 condition 排除 memosprite 防自循环
      - effect_type: "drain_hp"
        target: "$self.memosprite"
        amount: "$self.memosprite.max_hp * $self.memps_drain_pct"
        drain_ratio: 1.0
        heal_target: "$event.targets"
```

### 22.12 常见错误

| 错误 | 原因 | 修正 |
|------|------|------|
| `amount: $self.max_hp` | 表达式缺少引号 | `amount: "$self.max_hp"` |
| `self.base_hp = 100` | variable_bindings 中写常量绕过查表 | 用 `lookup_table` 或显式说明 |
| `if eidolon >= 6:` | condition 缺少 `$build` 前缀 | `if $build.eidolon >= 6:` |
| `in_zone(yao_zone)` | 字符串未加引号 | `in_zone('yao_zone')` |
| 引用未定义变量 | `$self.xxx` 既不是 Actor 字段也未在 variable_bindings 中绑定 | 检查字段名或先在 variable_bindings 中定义 |
| `1 + crit_dmg if random() < crit_rate else 1` | 不支持 Python 风格三元 | `(random() < crit_rate) ? (1 + crit_dmg) : 1.0` |

### 22.13 TBD

- 完整 BNF 语法定义（TBD）
- `variable_bindings` 是否支持 `let` 局部变量
- condition 是否支持引用其他已绑定变量

---
