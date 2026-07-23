## 13. 输入验证 (Validator)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

验证器在加载 DSL 后执行静态检查，防止非法输入导致模拟器异常。

### 13.1 使用方式

```python
from hsr_nous.sim_schema import validate_encounter, Encounter

encounter = Encounter.model_validate(yaml.safe_load(path.read_text()))
result = validate_encounter(encounter)

if result.valid:
    print("验证通过")
else:
    for error in result.errors:
        print(f"ERROR: {error.path} - {error.message}")
    for warning in result.warnings:
        print(f"WARNING: {warning.path} - {warning.message}")
```

`validate_encounter()` 保留为 facade 函数，内部调用 `Encounter.model_validate()` 并附加 DSL 静态检查。

### 13.2 Pydantic 字段约束

迁移到 Pydantic v2 后，以下校验由字段约束自动完成：

| 字段 | 约束 |
|------|------|
| `actor_type` | `Literal["character", "monster", "summon"]` |
| `modifier_type` | `Literal["buff", "debuff", "shield", "heal"]`（dot/control 并入 `debuff_kind`，见 04_modifier.md §4.1） |
| `level` | 按 `actor_type` 区分：character `Field(ge=1, le=80)`；monster/summon `Field(ge=1)`（敌人可达 95/120 级） |
| `spd` | `Field(gt=0)` |
| `energy` | `Field(le=max_energy)` |
| `toughness` | `Field(le=max_toughness)` |
| `actor_state` | `Literal[...]`（见 `17_actor_state.md`） |
| `resource_id` | 字符串，非空 |

复杂跨字段规则用 `@model_validator` 实现。

### 13.3 DSL 静态检查

| 检查项 | 说明 | 严重程度 |
|--------|------|---------|
| 变量引用 | `$self.xxx` 必须对应 Actor 已声明字段（如 `base_stats.max_hp`）或本模板 `variable_bindings` 中绑定的变量 | error |
| 资源 ID | 引用的 `resource_id` 必须存在 | error |
| 表达式语法 | 受限表达式 DSL 的 parser 检查 | error |
| 非法函数 | 表达式中只允许白名单函数 | error |
| 模板引用 | `build.yaml` 中的 `character_template` 必须存在于模板索引 | error |
| 重复 ID | `actor_id`、`modifier_id`、`zone_id` 等不能重复 | error |
| override 冲突 | 同一属性多个 `override` modifier 可能同时生效（静态可判的叠加场景） | error |
| override 互斥 | 同一 modifier 同时携带 `override` 与 `flat_bonus`/`scaling_from_source` | error |

### 13.4 传统校验规则

| 类别 | 规则 | 严重程度 |
|------|------|---------|
| 角色数量 | 上限 4 个 | error |
| 敌人数量 | 每波次上限 10 个 | error |
| 波次数 | 上限 10 个 | error |
| 轮次 AV | 首轮/后续 AV >= 1 | error |
| 最大轮次数 | 上限 99 | error |
| 等级 | 角色 1-80；敌人/召唤物 ≥1（可达 95/120 级） | error |
| 速度 | 必须 > 0 | error |
| 能量 | 当前 <= 上限 | error |
| 韧性 | 当前 <= 上限 | error |
| 暴击率 | 建议 0-1 | warning |
| 战技点 | current <= max | error |
| policy 结构 | `mode: rule_based\|scripted\|hybrid`；`state_resources` 的 resource_id 与 `state_hooks` 内引用存在；`script` 的 actor/action 可解析到该 actor 的 actions 内 | error |

### 13.5 表达式白名单

#### 13.5.1 通用变量

| 变量 | 说明 | 可用位置 |
|------|------|---------|
| `$self.xxx` | 当前 actor 字段 | 任意表达式 |
| `$resource.xxx` | 资源当前值 | 任意表达式 |
| `$event.xxx` | 事件上下文 | 事件响应全域（hook / modifier trigger / summon trigger / hit_condition） |
| `$target.xxx` | 目标 actor 字段 | 伤害/治疗/效果表达式 |
| `$build.xxx` | build 配置 | `variable_bindings` condition / effect `condition` |
| `$prev.xxx` | 同一 action 内前一个 effect 的结果 | effect 表达式 |
| `$last.xxx` | hook effects 链中上一个 effect 执行后的 `$event` 状态 | 仅 hook effect |
| `$team.xxx` | 队伍级聚合字段 | 部分表达式 |

#### 13.5.2 effect 表达式白名单（`amount` / `condition` / `target_filter` 等）

| 函数 | 说明 |
|------|------|
| `chance(N)` | 概率判定（仅 condition 上下文） |
| `in_zone(id)` | 是否在指定 zone 内（仅 condition 上下文） |
| `min(a, b)` / `max(a, b)` | 最值 |
| `clamp(x, lo, hi)` | 裁剪 |
| `abs(x)` / `round(x)` | 绝对值 / 四舍五入 |
| `sum(iterable)` | 聚合求和（如 `sum($team.taunt)`） |
| `lookup_table(name, index)` | 查本模板内嵌表（允许但不推荐，优先读已绑定变量） |
| `zone_owner()` | 返回 zone 的拥有者（见 19_zone_system.md） |

#### 13.5.3 全局公式白名单（`data/sim_templates/global/formulas.yaml`）

在 effect 表达式白名单基础上，额外允许：

| 函数 | 说明 |
|------|------|
| `random()` | 均匀随机数 `[0, 1)`，仅用于公式层随机判定 |

> 与 `22_syntax_reference.md` §22.10 互为镜像，唯一事实来源为 §22.10。

---
