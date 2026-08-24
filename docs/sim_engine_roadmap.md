# CombatEngine 分阶段实现路线

> **历史文档**——Phase 1-3 已全部完成于 2026-08，留作演进考古；当前引擎架构见 [engine_design.md](engine_design.md)。
>
> 目标：将 `sim/` 从骨架完善为可用的回合制战斗模拟器，逐步提高对游戏机制的还原度。
> 设计哲学（来自 [sim_schema/docs/00_overview.md](../src/hsr_nous/sim_schema/docs/00_overview.md)）：**一切机制都抽象为「事件-响应」模型**。

## 现状盘点

| 组件 | 文件 | 状态 |
|------|------|------|
| PolicyInterpreter | `sim/engine.py` | ✅ 可用（策略选行动/目标） |
| Selectors | `sim/selectors.py` | ✅ 完善（目标选择器注册表） |
| CombatEngine.run | `sim/engine.py` | 🔴 骨架（空循环） |
| Timeline | `sim/timeline.py` | 🔴 骨架（返回 actors[0]） |
| DamageResolver | `sim/resolver.py` | 🔴 骨架（返回 0） |
| Modifier (schema) | `sim_schema/modifiers.py` | 🟡 过简，缺事件钩子 |
| Action (schema) | `sim_schema/action.py` | 🟡 缺事件钩子 |
| 表达式求值 | `engine.py` / `selectors.py` | 🔴 不安全 `eval()` 占位 |

## 设计原则

1. **事件驱动核心**：引擎主循环只负责派发事件，具体效果由监听器（技能/buff/光锥/遗器）响应。
2. **公式与机制解耦**：伤害公式参数化（见 [01_formula.md](../src/hsr_nous/sim_schema/docs/01_formula.md)），改公式不改引擎。
3. **每个 Phase 都可运行**：每阶段结束都有可跑通的测试和可观测的输出，不留半成品。
4. **schema 随引擎演进**：引擎需要的字段在对应 Phase 补充到 sim_schema。
5. **遵守模块边界**：`sim/` 只依赖 `sim_schema/`，不碰 `raw_schema`/`pipeline`/`adapters`。

---

## Phase 1 — 行动值系统 + 标准伤害公式

**目标**：能算出"角色 X 用技能 Y 打 Lv.80 敌人造成多少伤害"，并让多个单位按速度正确轮流行动。

### 1.1 行动值系统（Timeline）
- 行动值公式与拉条/延后语义见 [mechanics/03_action_sequence.md](mechanics/03_action_sequence.md)（唯一来源，本路线图不复述常数）
- 每个单位维护当前 `action_value`，每"tick"全体减去最小 AV，归零者行动
- 行动后重置该单位 AV
- 支持拉条/延后

### 1.2 标准伤害公式（DamageResolver）
实现 12 乘区直伤公式（期望形式，不模拟随机暴击）。公式与乘区表达式的唯一来源是
`src/hsr_nous/sim_schema/rulebook.yaml`（可执行数据），文档镜像见
[01_formula.md](../src/hsr_nous/sim_schema/docs/01_formula.md) 与
[mechanics/02_damage_formula.md](mechanics/02_damage_formula.md)——本路线图不复述表达式与常数。

### 1.3 主循环骨架
```
while not terminated:
    actor = timeline.next_actor()
    action = policy.select_action(actor, context)
    target = policy.select_target(actor, action, enemies, context)
    result = resolver.resolve(action, actor, target)
    state.total_damage += result.damage
    timeline.advance(actor)
```

**交付物**：`test_phase1_sim.py`（现有）— 验证已知配装下黄泉普攻伤害数值合理。
**schema 改动**：Actor 增加 `max_hp`、当前 `action_value` 运行时字段。

---

## Phase 2 — Modifier 系统 + 技能事件钩子

**目标**：能模拟 buff/debuff 对伤害的影响（如花火加暴伤、银狼减防）。

### 2.1 扩展 Modifier schema
按 [04_modifier.md](../src/hsr_nous/sim_schema/docs/04_modifier.md) 补充：
- 事件钩子：`on_apply` / `on_turn_start` / `on_turn_end` / `on_expire` 等
- `stack_mode`（independent / refresh / replace）、`max_stack`、`dispellable`
- `stat_changes` 支持表达式（如 `def × 0.48 + 640`）

### 2.2 事件总线（EventBus）
- 注册时机清单（见 04_modifier.md §4.6）：`on_battle_start`、`on_before_action`、`on_after_hit`、`on_break` 等
- modifier 作为监听器挂到携带者，事件触发时执行其 effects

### 2.3 Modifier 生命周期管理
- 施加 → 叠层/刷新 → 回合结算（A/B 类判定）→ 到期移除
- 驱散/净化 LIFO 顺序

**交付物**：`test_phase2_buff.py`（计划中，未创建）— 验证"裸装黄泉 vs 花火增益后黄泉"伤害差异符合预期。
**schema 改动**：Modifier 重写；Action 增加 `on_hit` 等触发效果字段。

---

## Phase 3 — 能量 / 韧性击破 / 轮次波次

**目标**：完整战斗循环，支持终结技自动释放、击破机制、多波次关卡。

### 3.1 能量系统
- 行动获取能量（`energy_gain`）、受击获取能量
- 满能触发 `on_resource_threshold(resource_id: energy, threshold: max)` → 策略决定是否插入终结技

### 3.2 韧性 / 击破系统
- 削韧公式（`toughness_damage` 乘区）与击破/超击破伤害公式唯一来源同 §1.2（rulebook.yaml；见 01_formula.md §1.1）
- 击破触发 `on_weakness_break` → 属性击破效果（裂伤/灼烧/冻结/触电/风化/纠缠/禁锢）

### 3.3 轮次 / 波次
- Cycle AV 预算管理（各模式 AV 表唯一来源：rulebook.yaml `modes:` 节；语义见 mechanics 03）
- Wave 切换（清场进下一波）+ `on_wave_start` / `on_cycle_start` 环境效果

### 3.4 终止条件
- `fixed_av` / `kill_target` / `survival` / `wipe`（见 encounter.py TerminationConfig）

**交付物**：`test_phase3_full.py`（计划中，未创建）— 完整忘却之庭单边模拟，输出每轮伤害。

---

## Phase 4 — 安全表达式引擎（横切）

**目标**：替换所有 `eval()` 占位，支持公式/条件/选择器的安全表达式求值。

- 支持：算术运算、比较、布尔、三元 `? :`、`min/max/clamp` 函数、变量/嵌套属性访问
- 实现方式：基于 `ast` 模块的白名单求值器（禁止函数调用、属性访问之外的操作）
- 替换位置：`engine.py:_eval_condition`、`selectors.py:filter/first`、伤害公式 expression

**交付物**：`test_expression.py`（现有）— 覆盖各类表达式 + 注入攻击防护测试。
**说明**：可在 Phase 1-3 中先用受限占位，Phase 4 统一替换；或提前到 Phase 1.5 实现以支撑公式求值。

---

## 实施顺序与里程碑

```
Phase 1 (行动值+伤害) ──► 能算单次伤害、多单位轮流行动   【最小可用】
   │
Phase 4-lite (表达式) ──► 支撑公式/条件求值（按需提前）
   │
Phase 2 (Modifier)    ──► 能模拟 buff/debuff 增益       【有参考价值】
   │
Phase 3 (能量/击破/轮次)─► 完整战斗循环                  【实战可用】
   │
Phase 4 (表达式收尾)  ──► 安全、可扩展                    【生产就绪】
```

每个 Phase 完成后：
1. 跑通对应 `test_phaseN_*.py`
2. 更新 `sim/README.md` 标注组件状态
3. 必要时回填 `sim_tools.py`，让 agent 用上真实模拟

---

## 与 adapters 的关系

`sim/` 只认识 `sim_schema`。真实游戏数据（角色属性、技能倍率）通过 `adapters/` 从 `raw_schema` 转换为 `sim_schema`（Actor / Action / Modifier）。

- adapters 层独立设计（见单独任务），可与 Phase 1-2 **并行推进**
- 引擎用手写的 sim_schema 测试数据即可验证，不阻塞 adapters
