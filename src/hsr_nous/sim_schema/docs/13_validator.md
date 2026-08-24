## 13. 输入验证 (Validator)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

验证器在加载 DSL 后执行静态检查，防止非法输入导致模拟器异常。

### 13.1 校验层现状（三层）

> **退役公告**：原 `sim_schema/validator.py`（`validate_encounter` 全家）已删除（2026-08-24）——
> 零调用方且校验形状与编译产物脱节。校验职责由以下三层现役闸门承担：

| 层 | 闸门 | 位置 |
|----|------|------|
| 编译期 | 未知键拒绝 / 枚举校验 / effect_type 白名单 / 表达式预编译 / 事件契约对账（§13.2） | `sim/compile/build_compiler.py`、`sim/compile/stage_compiler.py` |
| 表达式 | 白名单 AST 解析（变量/函数/节点三层，§13.5） | `sim_schema/expression.py` |
| 文档↔代码 | lint 闸族（模块边界闸、镜像公式闸、effect_type 闸、§引用闸等十余项） | `tests/test_doc_lint.py`（清单见 `tests/README.md`） |

设计哲学：**"LLM 写模板靠报错自愈"——错拼/未知键/非法枚举必须编译期炸，静默吞 = 幻觉温床**。

### 13.2 编译期校验闸（现役）

| 检查项 | 说明 | 报错形态 |
|--------|------|---------|
| 未知键拒绝 | `base_stats` / `actions` / `apply_modifiers`（modifier dict）/ `hooks` / `policy` / `termination` / stage 各级 dict 做已知键集合 diff——错拼（如 `atkk` / `toughness_dmgg`）编译期炸 | `含未知键 'x'（合法集合：[...]）` |
| effect_type 白名单 | hook effects 的 `effect_type` 必须命中引擎已实现集合（单一事实源 `sim_schema/effect_types.py`，实现状态对账见 `05_effects.md` §5.2） | `未知 effect_type 'x'（已实现集合：[...]）` |
| target 选择器 | hook effect `target` 必须命中选择器词表（`sim_schema/effect_types.py`）或 `$event.<字段>` 寻址；引擎侧 `_hook_target_states` 同口径炸（不静默退化 enemy_first） | `未知 target 选择器 'x'` |
| 枚举字段 | `ult_timing` / `stage.mode` / `termination.mode` / `action_type` / `target_type` / `stack_mode` / `tick_anchor` / `effect_scope` 拼错编译期炸（历史案例：`ult_timing: "after_actoin"` 曾致终结技永远不开零提示；`mode` 拼错曾静默关闭轮次系统） | `非法值 'x'（合法集合：[...]）` |
| 表达式预编译 | hook `condition` 与 effects 数值槽（`amount`/`ratio`/`scaling_atk`/`scaling_hp`/`delta`/`percent`）的字符串值统一过白名单预编译（B8：非法表达式编译期炸，不进运行时） | `表达式非法：...` |
| 事件契约 | hook `event` 必须命中总线契约表（`sim/bus.py` DEFAULT_CONTRACT；发射点对账表见 `23_event_hook_system.md` §23.4） | `引用了未登记事件 'x'` |
| 糖键拒绝 | `trigger_limit` 等糖键（`04_modifier.md` §4.12-4.14 设计预览，desugar 未接线）按"已知但未落地"拒绝——写了会炸并指路，不是静默吞 | `使用了糖键 'x'——设计预览，desugar 未接线` |
| inline hooks 拒绝 | build.yaml inline 角色不支持 `hooks:` 块——机制 DSL 只走模板文件通道（`data/sim_templates/characters/`） | `inline 角色不支持 hooks: 块` |

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
| 事件可改性 | `modify_event` 用于 `emit`（只读）事件，或 `event_updates` 键超出可改白名单（`amount` / `target` / `targets` / `cancel` / `source` / `action_type`） | error |
| 发射点对账（引擎侧） | 引擎每个状态变更操作必须在 `23_event_hook_system.md` §23.4 对账表有对应发射点登记（生成式发射原则） | error |

> 末行"发射点对账"是**引擎侧对账闸**（实现层），不是 DSL 静态检查——它校验引擎代码的变更操作清单与 §23.4 对账表双向一致（新增变更操作未登记发射点 = 实现缺陷）；DSL 模板本身无需申报。
>
> 落地自决策卡 #16（2026-08-15）

### 13.4 传统校验规则

| 类别 | 规则 | 严重程度 |
|------|------|---------|
| 角色数量 | 上限 4 个 | error |
| 敌人数量 | 每波次上限 10 个 | error |
| 波次数 | 上限 10 个 | error |
| 轮次 AV | 首轮/后续 AV >= 1 | error |
| 最大轮次数 | 上限 99 | error |
| 等级 | 角色 1-80；敌人/召唤物 1-120（深渊 95、异相仲裁 120）；光锥 1-80；遗器强化 ≤ 稀有度上限（5★15 / 4★12 / 3★9 / 2★6） | error |
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
| `$last.xxx` | hook effects 链中上一个 effect 执行后的 `$event` 状态（与 `$prev` 同为"前序快照"——决策卡 #20 合并命名，统一 action/hook 两链语境；`$last` 为兼容保留） | 仅 hook effect |
| `$team.xxx` | 队伍级聚合字段 | 部分表达式 |
| `$modifier.source` | modifier 的施加者（挂在他人身上的 modifier 引用施加者） | modifier 内表达式 / effects |
| `$mod` | `filter` 中绑定的待审 modifier 实例 | 带 `filter` 的 effect 通用（`remove_modifier` / `adjust_duration` 等） |

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
| `min_by(collection, key)` | 返回集合中 `key` 最小的元素（用于 target 表达式等） |
| `unique_sources(resource_id)` | 资源的来源去重计数（需 `provenance: true`，见 `16_custom_resources.md` §16.13） |
| `has_modifier(target, modifier_id)` | 目标是否持有指定 modifier 实例 |
| `weakness_count(target)` | 目标当前弱点列表的属性种类数（含 modifier `weakness_add` 植入，见 `04_modifier.md` §4.11） |
| `enemies_alive()` | 当前存活敌人数（"敌方全体行动完毕"类阈值条件的计数源——反击/叠层族） |

#### 13.5.3 全局公式白名单（`data/sim_templates/global/formulas.yaml`）

在 effect 表达式白名单基础上，额外允许：

| 函数 | 说明 |
|------|------|
| `random()` | 均匀随机数 `[0, 1)`，仅用于公式层随机判定 |

> 与 `22_syntax_reference.md` §22.10 互为镜像，唯一事实来源为 §22.10。

### 13.6 目标态：Pydantic 字段约束

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

---
