## 13. 输入验证 (Validator)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

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
| `modifier_type` | `Literal["buff", "debuff", "dot", "shield", "heal", "control"]` |
| `level` | `Field(ge=1, le=90)` |
| `spd` | `Field(gt=0)` |
| `energy` | `Field(le=max_energy)` |
| `toughness` | `Field(le=max_toughness)` |
| `actor_state` | `Literal[...]`（见 `17_actor_state.md`） |
| `resource_id` | 字符串，非空 |

复杂跨字段规则用 `@model_validator` 实现。

### 13.3 DSL 静态检查

| 检查项 | 说明 | 严重程度 |
|--------|------|---------|
| 变量引用 | `$self.xxx` 必须在模板 `variable_bindings` 中定义 | error |
| 资源 ID | 引用的 `resource_id` 必须存在 | error |
| 表达式语法 | 受限表达式 DSL 的 parser 检查 | error |
| 非法函数 | 表达式中只允许白名单函数 | error |
| 模板引用 | `build.yaml` 中的 `character_template` 必须存在于模板索引 | error |
| 重复 ID | `actor_id`、`modifier_id`、`zone_id` 等不能重复 | error |

### 13.4 传统校验规则

| 类别 | 规则 | 严重程度 |
|------|------|---------|
| 角色数量 | 上限 4 个 | error |
| 敌人数量 | 每波次上限 10 个 | error |
| 波次数 | 上限 10 个 | error |
| 轮次 AV | 首轮/后续 AV >= 1 | error |
| 最大轮次数 | 上限 99 | error |
| 等级 | 1-90 | error |
| 速度 | 必须 > 0 | error |
| 能量 | 当前 <= 上限 | error |
| 韧性 | 当前 <= 上限 | error |
| 暴击率 | 建议 0-1 | warning |
| 战技点 | current <= max | error |

### 13.5 表达式白名单

| 变量 | 说明 |
|------|------|
| `$self.xxx` | 当前 actor 字段 |
| `$resource.xxx` | 资源当前值 |
| `$event.xxx` | 事件上下文 |
| `$target.xxx` | 目标 actor 字段 |
| `$build.xxx` | build 配置 |

| 函数 | 说明 |
|------|------|
| `chance(N)` | 概率判定 |
| `in_zone(id)` | 是否在指定 zone 内 |
| `min(a, b)` / `max(a, b)` | 最值 |
| `clamp(x, lo, hi)` | 裁剪 |
| `lookup_table(name, index)` | 查本模板内嵌表（仅 variable_bindings） |

---
