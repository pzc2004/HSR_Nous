## 21. 语法参考 (Syntax Reference)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

### 21.1 总览

`sim_schema` DSL 是基于 YAML/JSON 语法的声明式配置语言，用于描述角色/光锥/遗器/敌人/关卡的战斗机制。

它由三部分组成：

1. **数据声明语法**：YAML/JSON 本身（字段、列表、字典、字符串）
2. **变量绑定语法**：`variable_bindings` 字段中的 `lookup_table()` 和 `if` 语句
3. **表达式 DSL**：`amount`、`condition`、`target`、`in_zone_filter` 等字段中的受限表达式

### 21.2 文件格式

模板文件使用 `.yaml` 或 `.json`：

```yaml
# data/sim_templates/characters/1001_march_7th.yaml
id: "1001"
name: "march_7th"
path: "preservation"
element: "ice"

lookup_tables:
  base_hp_by_level: [1200, 1300, 1400]

variable_bindings:
  - self.base_hp = lookup_table("base_hp_by_level", index=$build.level - 1)

actions:
  - action_id: "100101"
    action_type: "basic"
    effects:
      - effect_type: "deal_damage"
        amount: "$self.atk * $self.basic_scaling"
```

### 21.3 `variable_bindings` 语法

每个模板通过 `variable_bindings` 字段把 build 配置转换成具体数值。

#### 查表绑定

```yaml
self.<var_name> = lookup_table("<table_name>", index=<expression>)
```

`lookup_table` 查找本模板内嵌的 `lookup_tables[<table_name>][<index>]`。

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

### 21.4 表达式 DSL

表达式用于 `amount`、`condition`、`target`、`in_zone_filter` 等字段。

#### 白名单变量

| 变量 | 含义 | 可用位置 |
|------|------|---------|
| `$self.xxx` | 当前 actor 字段/变量 | 任意表达式 |
| `$resource.xxx` | 自定义资源当前值 | 任意表达式 |
| `$event.xxx` | 事件上下文 | hook condition / effect |
| `$target.xxx` | 主目标字段 | 伤害/治疗/效果表达式 |
| `$build.xxx` | build 配置 | `variable_bindings` condition |

#### 白名单函数

| 函数 | 说明 |
|------|------|
| `chance(N)` | N% 概率判定 |
| `in_zone(zone_id)` | 目标是否在指定 zone 内 |
| `min(a, b)` / `max(a, b)` | 最值 |
| `clamp(x, lo, hi)` | 裁剪到 [lo, hi] |
| `lookup_table(name, index)` | 查本模板内嵌表（仅 variable_bindings） |

#### 运算符

支持标准算术、比较、逻辑运算符：

```yaml
amount: "$self.max_hp * 0.3 + 200"
condition: "$resource.punchline > 100 && !target.broken"
condition: "$self.hp / $self.max_hp < 0.5"
```

#### 禁止项

表达式 DSL 禁止以下行为（安全红线）：

- `import` / `exec` / `eval`
- 循环语句
- 文件 I/O
- 网络访问
- 反射 / 任意 Python 语法

### 21.5 `amount` 字段写法

`amount` / `pct` 等数值字段支持多种形式：

| 形式 | 示例 | 说明 |
|------|------|------|
| 常量 | `amount: 5` | 固定数值 |
| 关键字 | `amount: "all"` | 全部当前值 |
| 比例 | `amount: "ratio:0.5"` | 当前值的 50% |
| 表达式 | `amount: "$self.max_hp * 0.3"` | 运行时求值 |
| 资源引用 | `amount: "$resource.punchline * 0.1"` | 读资源当前值 |
| 前序结果 | `amount: "$prev.amount * 0.8"` | 同一 action 前一个 effect 结果 |

### 21.6 `condition` 表达式

`condition` 是返回布尔值的字符串表达式：

```yaml
condition: "$self.hp / $self.max_hp < 0.5"
condition: "$build.eidolon >= 6"
condition: "$resource.punchline > 100 && !target.broken"
condition: "in_zone('yao_zone')"
```

### 21.7 `target` 选择器

target 字段支持字符串或参数字典：

```yaml
# 字符串预注册选择器
target: "primary_target"
target: "all_enemies"
target: "lowest_hp_ally"

# 参数化选择器
target:
  type: "min"
  key: "stats.hp"

target:
  type: "filter"
  condition: "in_zone('yao_zone')"
```

### 21.8 命名空间约定

| 上下文 | 前缀 | 例子 |
|--------|------|------|
| variable_bindings 赋值 | `self.xxx` | `self.base_hp = ...` |
| effect 表达式取值 | `$self.xxx` | `amount: "$self.max_hp * 0.3"` |
| 资源取值 | `$resource.xxx` | `amount: "$resource.punchline"` |
| 事件上下文 | `$event.xxx` | `condition: "$event.target != $self.memosprite"` |
| 目标取值 | `$target.xxx` | `condition: "$target.hp < $target.max_hp * 0.5"` |
| build 配置 | `$build.xxx` | `if $build.eidolon >= 6:` |

### 21.9 完整示例

```yaml
# data/sim_templates/characters/1409_hyacine.yaml
id: "1409"
name: "hyacine"

lookup_tables:
  base_hp_by_level:        [1200, 1300, 1400]
  skill_1140901_clear_ratio:  [0.50, 0.50, 0.50]

variable_bindings:
  - self.base_hp     = lookup_table("base_hp_by_level",      index=$build.level - 1)
  - self.clear_ratio = lookup_table("skill_1140901_clear_ratio", index=$build.skill_levels.skill - 1)
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
    effects:
      - effect_type: "heal"
        target: "$event.targets"
        amount: "$self.max_hp * $self.memps_heal_pct + $self.memps_heal_base"
```

### 21.10 常见错误

| 错误 | 原因 | 修正 |
|------|------|------|
| `amount: $self.max_hp` | 表达式缺少引号 | `amount: "$self.max_hp"` |
| `self.base_hp = 100` | variable_bindings 中写常量绕过查表 | 用 `lookup_table` 或显式说明 |
| `if eidolon >= 6:` | condition 缺少 `$build` 前缀 | `if $build.eidolon >= 6:` |
| `in_zone(yao_zone)` | 字符串未加引号 | `in_zone('yao_zone')` |
| 引用未定义变量 | `$self.xxx` 未在 variable_bindings 中声明 | 先在 variable_bindings 中定义 |

### 21.11 TBD

- 完整 BNF 语法定义（§5 #18）
- `variable_bindings` 是否支持 `let` 局部变量
- condition 是否支持引用其他已绑定变量

---
