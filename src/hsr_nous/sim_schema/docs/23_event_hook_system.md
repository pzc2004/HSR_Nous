## 23. 事件 Hook 系统 (Event Hook System)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。
>
> **地位说明**：本文档是**统一事件总线的正文档**——modifier 的生命周期触发（`04_modifier.md` §4.4/§4.8）与本章的通用 hook 事件已裁决合并为一套总线：事件 = 发射点 + payload；响应（modifier / hook / zone 等）= `condition` 过滤 + effects。新增事件一律先考虑"现有发射点 + 过滤"，不逐机制膨胀枚举。

### 23.1 背景与动机

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

### 23.2 设计目标

- 一个机制覆盖所有事件类型（资源 / 伤害 / HP / 状态）
- 支持同步触发 + 异步累积
- `$event` 可变上下文（hook 可修改原事件参数）
- target 动态过滤
- Hook 是 `sim_schema` 的声明字段，由 DSL 模板的 `hooks` 字段声明
- 不引入运行时 Python

### 23.3 Hook 定义

Hook 是角色/光锥/遗器模板上的声明：当某事件发生时，触发一组 effect。

```yaml
# 火花 climax 抵扣 sp
hooks:
  - event: "before_consume"
    target_resource: "sp"
    scope: "self"
    condition: "$resource.climax > 0"
    effects:
      - effect_type: "consume_resource"
        resource_id: "climax"
        amount: "$event.amount"
        on_insufficient: "clamp"
      - effect_type: "modify_event"
        event_updates:
          amount: "$event.amount - $last.actual_amount"
```

### 23.4 事件类型枚举

> **设计原则（发射点生成式）**：事件 = 引擎状态变更操作的**强制自动发射**——每个变更操作（削韧、modifier 施加/移除、资源增减、单位入场/离场、敌方行动……）都必须有对应发射点，事实自动在列；**本表是引擎变更操作的对账表**（永备，随引擎变更操作同步登记），不是封闭申请清单。对账闸：引擎变更操作必须有对应发射（见 `13_validator.md` §13.3）。hook 侧**不逐机制膨胀**：用 payload + `condition` 过滤表达具体机制（见本节末示例）。

| event | 触发时机 | scope | `$event` 字段 | 可改性 |
|-------|---------|-------|--------------|--------|
| `before_consume` | 任何 effect 试图消耗某资源前 | `self` / `team` | `amount`、`resource_id`、`source`、`target` | waterfall |
| `after_consume` | 资源消耗完成后 | `self` / `team` | `amount`、`resource_id`、`actual_amount`、`target` | emit |
| `before_gain` | 任何 effect 试图获得某资源前 | `self` / `team` | `amount`、`resource_id`、`source`、`target` | waterfall |
| `after_gain` | 资源获得完成后 | `self` / `team` | `amount`、`resource_id`、`actual_amount`、`target` | emit |
| `before_take_damage` | actor 受到伤害前 | `self` / `team` | `amount`、`damage_type`、`source`、`target`、`is_breaking`、`action_type`、`tags` | waterfall |
| `after_being_hit` | actor 被命中后 | `self` / `team` | `amount`、`damage_type`、`source`、`target`、`is_critical`、`is_breaking`、`action_type`、`tags` | emit |
| `on_hp_decrease` | actor HP 降低时 | `self` / `team` | `amount`、`source`、`reason`、`target` | emit |
| `on_hp_increase` | actor HP 回升时 | `self` / `team` | `amount`、`source`、`reason`、`target` | emit |
| `on_state_change` | actor_state 切换时（现态：引擎原生发射；**B24 数据宏落地后降格为宏**——展开为 `after_apply_modifier` / `after_remove_modifier` + `singleton_group: actor_state` 过滤，模板写法不变，决策卡 #20） | `self` / `team` | `from_state`、`to_state`、`source`、`target` | emit |
| `on_resource_threshold` | 某资源达到阈值时 | `self` / `team` | `resource_id`、`threshold`、`direction`、`target` | emit |
| `on_stat_threshold` | 面板属性穿越阈值时（资源阈值的面板版；如欢愉度首达 40%/80%） | `self` / `team` | `stat`、`threshold`、`direction`、`target` | emit |
| `after_apply_modifier` | modifier 施加完成后 | `self` / `team` | `modifier_id`、`modifier_type`、`stat`、`target`、`source` | emit |
| `after_remove_modifier` | modifier 移除完成后 | `self` / `team` | `modifier_id`、`reason`（`expire` / `dispel` / `purify` / `replace`）、`target`、`source` | emit |
| `actor_enter` | actor 入场（波次敌人登场 / `summon`）时 | — | `actor`、`actor_type`、`wave_index`、`position` | emit |
| `actor_exit` | actor 离场（死亡 / 放逐 / `dismiss_summon`）时 | — | `actor`、`actor_type`、`reason`（`death` / `exile` / `dismiss_summon`） | emit |
| `aha_instant_start` | 阿哈时刻开始时 | `team` | `elation_number_order`、`source` | emit |
| `aha_instant_end` | 阿哈时刻结束时 | `team` | `source` | emit |
| `on_dot_retrigger` | DOT 结算时（自然结算：回合开始判定A 结算1；强制结算：`trigger_dot` 效果，见 `05_effects.md`） | `self` / `team` | `modifier_id`、`element`、`source`（施加者）、`target`、`retriggered`（是否强制结算） | emit |
| `on_toughness_damage` | 削韧结算时（每次削韧按实际量发射；击破本身另有 `on_break`，见 `04_modifier.md` §4.8） | `self` / `team` | `amount`（实际削韧量）、`source`、`target`、`damage_type`、`action_type`、`bar_index` | emit |
| `on_enemy_action` | 敌方主动行动时（无论行动指向谁——云璃"敌方主动使用技能即触发反击"类） | — | `actor`（行动者）、`action`、`action_type`、`targets` | emit |
| `shield_absorbed` | 护盾吸收结算时（受击链护盾层，逐实例按实际吸收量发射；mechanics 01 §1.3 并行吸收） | `self` / `team` | `shield_id`、`amount`（本实例吸收量）、`remaining`（吸收后剩余）、`source`、`target` | emit |
| `shield_broken` | 护盾实例后台破裂时（级联摘除关联 modifier——`after_remove_modifier` 带 `reason: "shield_broken"`，附带效果一并移除） | `self` / `team` | `shield_id`、`source`、`target` | emit |
| `on_revive` | 死亡检查触发复活时（消费复活件，按生命上限百分比回拉；复活件为 modifier `revive_percent` 字段，见 `04_modifier.md` §4.15） | `self` / `team` | `target`、`percent`、`hp`（回拉后 HP）、`source` | emit |
| `on_gain_energy` | 能量获得结算前（`before_gain` 的能量专门化——**一切能量获得路径的统一改写点**：行动回能（普攻/战技/终结技/追加，整动作一次，见 mechanics 05 §5.1）、受击回能（同 §5.1）、effect 原语 `gain_energy`（秘技装填预置/光锥/行迹/星魂通道）；初始能量布场非事件，不发射） | `self` / `team` | `actor`（获得者）、`amount`（ERR 乘算前基础量，waterfall 改写发生在 ERR 之前）、`source`、`action_id`（effect 原语无 action，为 `None`）、`reason`（`"being_hit"` / 行动类别名 `"basic"`·`"skill"`·`"ultimate"`·`"follow_up"` 等 / `"effect"`）、`err_exempt`（mechanics 05 §5.3 具名豁免：不乘 ERR，事件照发） | waterfall |

**可改性列**：`waterfall` = 可修改（hook 可用 `modify_event` 改写白名单 payload）；`emit` = 只读事实通知（禁止 `modify_event`，validator 校验）。契约与白名单全文见 §23.6；`04_modifier.md` §4.8 生命周期发射点的可改性在该表同列声明。`action_type` / `tags` 为伤害事件的行动类别与类别标签集合（改写语义见 §23.6）。

`reason` 取值示例：`"damage"` / `"consume"` / `"dot"` / `"drain"` / `"heal"` / `"drain_back"`。

> 注：`on_extra_turn`（额外回合开始）属 `04_modifier.md` §4.8 的 modifier 生命周期触发器（与 `on_turn_start` 同族），不在本表——hook 侧如需响应额外回合，经 modifier trigger 表达。

**发射点 + 过滤的组合示例**（替代新增事件类型）：

```yaml
# 符玄六壬式"被施加 debuff 时反击"——不是 on_debuff_applied 事件，是 apply_modifier 发射点
- event: "after_apply_modifier"
  condition: "$event.modifier_type == 'debuff' && $event.target != $self"
  effects: [...]

# 原目标死亡、改在新登场敌人身上触发——actor_enter 发射点
- event: "actor_enter"
  condition: "$event.actor_type == 'monster'"
  effects: [...]

# CB 到期转化（Evanescia）——remove_modifier 发射点 + reason 过滤
- event: "after_remove_modifier"
  condition: "$event.reason == 'expire' && $event.modifier_id == 'certified_banger'"
  effects: [...]

# 雪衣天赋：削韧按量叠【恶报】——削韧发射点（削韧量在 payload），追加攻击不叠层用 action_type 过滤
- event: "on_toughness_damage"
  scope: "team"
  condition: "$event.action_type != 'follow_up'"
  effects:
    - effect_type: "gain_resource"
      resource_id: "xueyi_karma"
      amount: "$event.amount * $self.karma_per_toughness"   # 换算系数经 variable_bindings 绑定
```

> 落地自决策卡 #16（2026-08-15）

### 23.5 Hook 字段

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `event` | enum | 必填 | 见 §23.4 |
| `target_resource` | string | 视 event | 资源类事件必填（如 `"sp"`） |
| `scope` | enum | `"self"` | `"self"` / `"team"` |
| `condition` | expression | `"true"` | 触发条件 |
| `effects` | `List[Effect]` | `[]` | 触发时执行的 effect 列表 |
| `accumulated` | bool | `false` | 是否累积模式 |
| `flush_triggers` | `List[event]` | `[]` | 累积模式下消费队列的时机；可填 hook 事件（§23.4）或 modifier 生命周期触发器（如 `on_turn_start`、`on_after_action`） |
| `target_filter` | expression | `"true"` | 累积模式下过滤 `$event.targets` |

### 23.6 `$event` 上下文

Hook effects 执行时，引擎注入 `$event` 对象。

**事件可改性契约（waterfall / emit）**：每个事件声明可改性（§23.4 表"可改性"列；`04_modifier.md` §4.8 生命周期发射点同）——

- `waterfall`（可修改）：hook 可用 `modify_event` 改写白名单 payload；引擎在 hook 链后按 `$event` 当前值继续原事件处理
- `emit`（只读）：事实通知，**禁止 `modify_event`**——validator 校验 error（见 `13_validator.md` §13.3）

**可改字段白名单**（仅 waterfall 事件，`event_updates` 只允许这些键）：

| 字段 | 语义 |
|------|------|
| `amount` | 数值改写（抵扣/分摊等） |
| `target` / `targets` | 目标改写（非累积模式为单数 `target`，累积模式聚合后为列表 `targets`） |
| `cancel` | 取消原事件 |
| `source` | **来源重归因**——改写事件的来源归属（姬子·启行"助战技视为姬子·启行施放战技"） |
| `action_type` | **行动类别改写**——改写事件的行动类别（飞霄行迹"终结技伤害视为发动追加攻击"；千冶·刃/貊泽/黄泉同类重标记）；改写为 `"none"` = **归因抹除**——无类别，不触发类别监听、不吃类别增伤（饮月"不视为使用战技"，决策卡 #18） |

**不可改字段**：`resource_id`、`damage_type`、`reason`、`bar_index` 等事实字段。

> **注意区分**：`source` / `action_type` 改写改的是**事件归因与行动类别**——影响触发器监听（"施放战技时"类按改写后的 `source` / `action_type` 判定）与加成命中（`hit_condition` / `dmg_bonus_by_type` 按改写后值匹配）；**不是**伤害类型标签——`damage_type` 全程只读。改写 `action_type` 时引擎同步更新 `tags` 中的主类别位。

```yaml
# 姬子·启行天赋（151004）：助战技视为姬子·启行施放战技——来源重归因 + 类别改写（on_cast 为 waterfall，见 04_modifier.md §4.8）
hooks:
  - event: "on_cast"
    condition: "$event.action_type == 'assist' && $event.source != $self"
    effects:
      - effect_type: "modify_event"
        event_updates:
          source: "$self"            # 来源重归因：视为姬子·启行施放
          action_type: "skill"       # 类别改写：视为施放战技 → "施放战技时"类触发器正确命中
```

```yaml
# 飞霄行迹：终结技伤害视为发动追加攻击——行动类别改写
hooks:
  - event: "before_take_damage"
    condition: "$event.source == $self && $event.action_type == 'ultimate'"
    effects:
      - effect_type: "modify_event"
        event_updates:
          action_type: "follow_up"   # 追加攻击加成（hit_condition / dmg_bonus_by_type.follow_up）命中
```

```yaml
- effect_type: "modify_event"
  event_updates:
    amount: 0        # 取消原消耗/伤害量
    cancel: true     # 取消原事件
```

> 落地自决策卡 #12（2026-08-14）

### 23.7 `$last` 上下文

在 hook 的 `effects` 链中，后执行的 effect 可通过 `$last` 读取上一个 effect 执行后的 `$event` 状态。典型用途是 `modify_event` 后计算剩余量：

```yaml
hooks:
  - event: "before_consume"
    target_resource: "sp"
    scope: "self"
    condition: "$resource.climax > 0"
    effects:
      - effect_type: "consume_resource"
        resource_id: "climax"
        amount: "$event.amount"
        on_insufficient: "clamp"
      - effect_type: "modify_event"
        event_updates:
          amount: "$event.amount - $last.actual_amount"
```

**`$last` 可读字段**：上一个 effect 执行后 `$event` 的当前值，常见包括 `amount`、`actual_amount`、`cancel`、`target`、`targets` 等。具体可用字段与当前 hook 事件类型相关。

**注意**：`$last` 只在同一个 hook 的 `effects` 链内有效；跨 hook 或跨 action 的 effect 之间没有 `$last`。

### 23.8 `modify_event` effect_type

`modify_event` 用于在 hook 中修改原事件参数：

```yaml
effect_type: "modify_event"
event_updates:
  amount: "$event.amount - $last.actual_amount"
  target: "$self"
```

引擎在 hook effects 执行后读取 `$event` 当前值，继续原事件处理。

**约束**：`modify_event` 仅可用于 `waterfall`（可修改）事件；对 `emit`（只读）事件使用，或 `event_updates` 键超出白名单（`amount` / `target` / `cancel` / `source` / `action_type`），validator 报错（契约全文见 §23.6）。

### 23.9 累积窗口模式

某些机制不是“事件 → 立即反应”，而是“事件 → 记录 → 下个时机统一处理”。

```yaml
- event: "on_hp_decrease"
  scope: "team"
  accumulated: true
  flush_triggers: ["on_turn_start", "on_after_action"]
  condition: "$event.target != $self.memosprite"  # 排除小伊卡自身（drain 会再发 on_hp_decrease，防自循环；与 07/22.11 统一）
  effects:
    - effect_type: "drain_hp"
      target: "$self.memosprite"
      amount: "$self.memosprite.max_hp * $self.memps_drain_pct"
      drain_ratio: 1.0
      heal_target: "$event.targets"
```

**累积队列机制**：
1. 事件触发时：把 `$event` 推入队列（不执行 effects）
2. `flush_triggers` 触发时：取出队列所有事件，聚合 `$event.targets`
3. `target_filter` 对每个 target 求值，过滤后执行一次 effects
4. 队列清空

### 23.10 真实用例

| 角色 | skill ID | hook 配置摘要 |
|------|---------|------------|
| 火花 (1501) | 150120 | `before_consume(sp)` → 优先消耗 climax，修改 `$event.amount` |
| 银狼 LV.999 (1506) | 150603 | `after_consume(sp, scope=team, condition: "in_zone('godmode') && chance(1.0)")` → 盲盒三选一 |
| 绯英 (1505) | 150504 | `after_gain(energy)` → gain certified_banger；`after_gain(certified_banger)` → gain energy |
| 符玄 (1208) | 120802 | `before_take_damage(team)` → 分摊 65% 伤害 |
| 符玄星魂 4 | 120804 | `after_being_hit(team)` → 符玄 gain 5 能量 |
| 风堇 M2 | 140902（星魂 rank id，与战技 skill id 同号不同物） | `on_hp_decrease(team)` → 速度 +30% |
| 风堇小伊卡天赋 | 1140903 | `on_hp_decrease(team, accumulated=true)` → 小伊卡 drain + heal |

### 23.11 触发顺序

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

同一事件多个 hook 按**注册顺序**执行——注册顺序是**确定的一等规则**，不是"一般"：

1. **同 actor 内**：按模板 `hooks:` 块的**声明顺序**（模板作者可控、可读）；
2. **星魂追加**：eidolons 的 hooks 按 E1→E6 序号追加在模板 hooks 之后；
3. **跨 actor**：按编队位（position 小者先）——**实现约定，非实测结论**（社区对"多被动挂同一事件的相对顺序"无公开测试；哪天实测出真规则，以实测为准改写本条）。

**顺序敏感（良定义）**：两个 hook 交换执行顺序会导致结算结果不同 → 这两个 hook**都**属于顺序敏感（可机器判定：交换跑两遍，结算 diff 非零）。纯加算型效果（攻击+8%/攻击+12%）交换无差异，天然不敏感；改写链（分摊/护盾/减伤）与取消链天然敏感。

**全局顺序表**：顺序敏感的 hook 集中登记在全局文件（`data/sim_templates/global/trigger_order.yaml`，按事件名列出 hook id 顺序，小者先）——机制定义留在各角色模板，**顺序编排集中一处**（接线图：电器归各家，通电顺序归配电箱）；插入=表里加一行，不改他人；lint 校验表中 hook id 必须存在。不敏感的 hook 不进表，按上述注册序执行——表永远只装那一小撮改写链/取消链。

**有据锚点**（官方/社区已钉死的顺序，与本规则不冲突时以锚点为准）：符玄分摊先于护盾（官方技能文本 "before this DMG is mitigated by any Shields"）；DoT 按施加顺序 FIFO（Arcana 队尾、Hysilens 结界最后）；FUA > 终结技 > 额外回合 > 普通回合，同级 FIFO；AV 并列按编队位（角色先于敌人）。

理由：waterfall hook 是对 payload 的**连续改写**（分摊 ×65% 与护盾 −1000 交换结果不同），且 `$last` 让后序 hook 能读前序改写——组合链是顺序敏感的，所以顺序必须是显式规则而非实现细节。（对比：纯加算型 stat buff（攻击+8%/攻击+12%）与顺序无关，本规则只约束改写链与触发链。）

### 23.12 与 Modifier 体系的关系

Modifier 的 `on_turn_start` / `on_before_hit` 等 trigger 与本章 hook **同属一套统一事件总线**：事件 = 发射点 + payload；响应（modifier / hook / zone 等）= `condition` 过滤 + effects。分工只是响应者的语义侧重：

- modifier 聚焦于**状态加成/减成**的持续效果（其 trigger 即总线上的带过滤响应；`on_memosprite_attack` 等复合名是语法糖，见 `04_modifier.md` §4.8）
- hook 聚焦于**事件响应**的瞬时逻辑（抵扣、分摊、双向同步、累积治疗等）

事件枚举唯一事实来源是本章 §23.4；新增事件一律先考虑"现有发射点 + 过滤"，不逐机制膨胀枚举。

### 23.13 引擎实现要点（概述）

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

**生成式发射**：引擎每个状态变更操作在变更点**强制自动发射**对应事件（发射是变更操作的固有步骤，不可遗漏）；新增引擎变更操作必须同步在 §23.4 对账表登记发射点（对账闸见 `13_validator.md` §13.3）。

**累积队列**：每个累积 hook 有独立队列，`flush_triggers` 触发时消费。

### 23.14 TBD

1. `condition` 表达式完整 BNF（是否支持 `chance(N)` / `in_zone(id)` 等内建函数）
2. `$event.cancel` 语义：取消后原 effect 是否完全不执行？
3. 累积队列生命周期：跨回合 / 跨波次是否清空？
4. Hook 死锁防护：hook 触发新事件又触发 hook，是否限制嵌套深度？
5. `target_filter` vs `condition` 边界是否冗余？
6. ~~Hook 与 modifier trigger 体系是否合并？~~ **已裁决：合并**——本章为统一事件总线正文档，见 §23.12
7. `random_select` effect 是否独立 effect_type？

---
