## 22. 事件 Hook 系统 (Event Hook System)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

### 22.1 背景与动机

HSR 大量“事件触发”机制原本散落在各种 `effect_type` 里（如 `consume_resource_substitute`），语义割裂。本系统提出**通用事件 hook**，统一覆盖资源 / 伤害 / HP / 状态等事件。

| 原 effect | 问题 | 真实用例 |
|----------|------|---------|
| `convert_resource` | “消耗 A 产出 B” | 无真实用例（已删除） |
| `consume_resource_substitute` | 只能表达“消耗 A 时优先扣 B” | 火花 climax 抵扣 sp |

但 HSR 还有大量“非资源消耗”的事件触发：

| 角色 | 触发事件 | hook 行为 |
|------|---------|----------|
| 火花 (1501) | `before_consume(sp)` | 优先扣 climax |
| 银狼 LV.999 (1506) | `after_consume(sp, scope=team)` | 概率触发盲盒三选一 |
| 绯英 (1505) | `after_gain(energy)` / `after_gain(certified_banger)` | 双向同步 |
| 符玄 (1208) | `before_take_damage(team)` | 分摊伤害（修改 `$event.amount`） |
| 符玄星魂 4 | `after_being_hit(team)` | 恢复 5 能量 |
| 风堇 (1409) M2 | `on_hp_decrease(team)` | 速度 +30% |
| 风堇小伊卡天赋 | `on_hp_decrease(team, accumulated=true)` | 累积后统一治疗 |

### 22.2 设计目标

- 一个机制覆盖所有事件类型（资源 / 伤害 / HP / 状态）
- 支持同步触发 + 异步累积
- `$event` 可变上下文（hook 可修改原事件参数）
- target 动态过滤
- Hook 是 `sim_schema` 的声明字段，由 DSL 模板的 `hooks` 字段声明
- 不引入运行时 Python

### 22.3 Hook 定义

Hook 是角色/光锥/遗器模板上的声明：当某事件发生时，触发一组 effect。

```yaml
# 火花 climax 抵扣 sp
hooks:
  - event: "before_consume"
    target_resource: "sp"
    scope: "self"
    condition: "$resource.climax.current > 0"
    effects:
      - effect_type: "consume_resource"
        resource_id: "climax"
        amount: "$event.amount"
        on_insufficient: "clamp"
      - effect_type: "modify_event"
        event_updates:
          amount: "$event.amount - $last.actual_amount"
```

### 22.4 事件类型枚举

| event | 触发时机 | scope | `$event` 字段 |
|-------|---------|-------|--------------|
| `before_consume` | 任何 effect 试图消耗某资源前 | `self` / `team` | `amount`、`resource_id`、`source` |
| `after_consume` | 资源消耗完成后 | `self` / `team` | `amount`、`resource_id`、`actual_amount` |
| `before_gain` | 任何 effect 试图获得某资源前 | `self` / `team` | `amount`、`resource_id`、`source` |
| `after_gain` | 资源获得完成后 | `self` / `team` | `amount`、`resource_id`、`actual_amount` |
| `before_take_damage` | actor 受到伤害前 | `self` / `team` | `amount`、`element`、`source`、`is_breaking` |
| `after_being_hit` | actor 被命中后 | `self` / `team` | `amount`、`element`、`source`、`is_critical`、`is_break` |
| `on_hp_decrease` | actor HP 降低时 | `self` / `team` | `amount`、`source`、`reason` |
| `on_hp_increase` | actor HP 回升时 | `self` / `team` | `amount`、`source`、`reason` |
| `on_state_change` | actor_state 切换时 | `self` / `team` | `from_state`、`to_state`、`source` |
| `on_resource_threshold` | 某资源达到阈值时 | `self` / `team` | `resource_id`、`threshold`、`direction` |

`reason` 取值示例：`"damage"` / `"consume"` / `"dot"` / `"drain"` / `"heal"` / `"drain_back"`。

### 22.5 Hook 字段

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `event` | enum | 必填 | 见 §22.4 |
| `target_resource` | string | 视 event | 资源类事件必填（如 `"sp"`） |
| `scope` | enum | `"self"` | `"self"` / `"team"` |
| `condition` | expression | `"true"` | 触发条件 |
| `effects` | `List[Effect]` | `[]` | 触发时执行的 effect 列表 |
| `accumulated` | bool | `false` | 是否累积模式 |
| `flush_triggers` | `List[event]` | `[]` | 累积模式下消费队列的时机 |
| `target_filter` | expression | `"true"` | 累积模式下过滤 `$event.targets` |

### 22.6 `$event` 上下文

Hook effects 执行时，引擎注入 `$event` 对象。

**可变字段**（可被 `modify_event` 修改）：
- `$event.amount`
- `$event.target`
- `$event.cancel`

**不可变字段**：
- `$event.resource_id`
- `$event.element`
- `$event.source`
- `$event.reason`

```yaml
- effect_type: "modify_event"
  event_updates:
    amount: 0        # 取消原消耗/伤害量
    cancel: true     # 取消原事件
```

### 22.7 `modify_event` effect_type

`modify_event` 用于在 hook 中修改原事件参数：

```yaml
effect_type: "modify_event"
event_updates:
  amount: "$event.amount - $last.actual_amount"
  target: "$self"
```

引擎在 hook effects 执行后读取 `$event` 当前值，继续原事件处理。

### 22.8 累积窗口模式

某些机制不是“事件 → 立即反应”，而是“事件 → 记录 → 下个时机统一处理”。

```yaml
- event: "on_hp_decrease"
  scope: "team"
  accumulated: true
  flush_triggers: ["on_turn_start", "after_action"]
  target_filter: "$target != $self or $event.reason == 'damage'"
  effects:
    - effect_type: "drain_hp"
      target: "$self.memosprite"
      amount: "$self.memosprite.max_hp * $self.memps_drain_pct"
    - effect_type: "heal"
      target: "$event.targets"
      amount: "$self.max_hp * $self.memps_heal_pct + $self.memps_heal_base"
```

**累积队列机制**：
1. 事件触发时：把 `$event` 推入队列（不执行 effects）
2. `flush_triggers` 触发时：取出队列所有事件，聚合 `$event.targets`
3. `target_filter` 对每个 target 求值，过滤后执行一次 effects
4. 队列清空

### 22.9 真实用例

| 角色 | skill ID | hook 配置摘要 |
|------|---------|------------|
| 火花 (1501) | 150120 | `before_consume(sp)` → 优先消耗 climax，修改 `$event.amount` |
| 银狼 LV.999 (1506) | 150603 | `after_consume(sp, scope=team, condition: in_zone(godmode) and chance(1.0))` → 盲盒三选一 |
| 绯英 (1505) | 150504 | `after_gain(energy)` → gain certified_banger；`after_gain(certified_banger)` → gain energy |
| 符玄 (1208) | 120802 | `before_take_damage(team)` → 分摊 65% 伤害 |
| 符玄星魂 4 | 120804 | `after_being_hit(team)` → 符玄 gain 5 能量 |
| 风堇 M2 | 140902 | `on_hp_decrease(team)` → 速度 +30% |
| 风堇小伊卡天赋 | 1140903 | `on_hp_decrease(team, accumulated=true)` → 小伊卡 drain + heal |

### 22.10 触发顺序

```
event 触发
    ↓
[before_* hooks] 同步执行
    ↓
hook effects 修改 $event
    ↓
原事件按 $event 当前值执行
    ↓
[after_* hooks] 同步执行
    ↓
[on_* hooks] 异步累积（accumulated=true）
```

同一事件多个 hook 按注册顺序执行（一般按 actor.speed 或入战顺序）。

### 22.11 与 Modifier 体系的关系

Modifier 的 `on_turn_start` / `on_before_hit` 等 trigger 是 **buff/debuff 生命周期事件**，由 modifier 自身状态驱动。

Hook 是 **actor-level 事件反应机制**，监听游戏内各种事件并触发 effects。

两者有语义重叠（如 `on_hp_decrease` 既可以是 hook 也可以是 modifier trigger），但当前保持分离：
- modifier 聚焦于**状态加成/减成**的持续效果
- hook 聚焦于**事件响应**的瞬时逻辑

是否合并是 TBD（§22.13 #6）。

### 22.12 引擎实现要点（概述）

**Hook 注册表**：

sim 引擎启动时扫描所有模板的 `hooks` 字段，构建事件分发表：

```
{
    ("before_consume", "sp"): [hook1, hook2],
    ("after_gain", "energy"): [hook3],
    ("on_hp_decrease", None): [hook4, hook5],
    ...
}
```

**事件分发**：引擎每次执行 effect 前/后，检查对应事件类型的 hook 列表，依次调用。

**累积队列**：每个累积 hook 有独立队列，`flush_triggers` 触发时消费。

### 22.13 TBD

1. `condition` 表达式完整 BNF（是否支持 `chance(N)` / `in_zone(id)` 等内建函数）
2. `$event.cancel` 语义：取消后原 effect 是否完全不执行？
3. 累积队列生命周期：跨回合 / 跨波次是否清空？
4. Hook 死锁防护：hook 触发新事件又触发 hook，是否限制嵌套深度？
5. `target_filter` vs `condition` 边界是否冗余？
6. Hook 与 modifier trigger 体系是否合并？
7. `random_select` effect 是否独立 effect_type？

---
