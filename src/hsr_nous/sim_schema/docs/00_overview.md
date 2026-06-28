# Sim Schema 仿真器输入格式

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

本文档定义战斗模拟器的完整输入数据结构。核心设计原则：

- **DSL-first 运行时格式**：所有进入 `sim` 引擎的输入都是声明式 YAML/JSON，不写硬编码逻辑。
- **事件-响应模型**：技能、行迹、星魂、光锥、遗器本质都是事件监听器，在特定时机触发效果。
- **buff/debuff 也是事件监听器**：在持续期间内响应特定事件。
- **模板自包含**：每个实体模板自带 `lookup_tables` + `variable_bindings`，sim 加载即跑。

## 设计哲学

| 语言概念 | 对应物 |
|---------|--------|
| 类型系统 | Pydantic 模型（Actor / Effect / Modifier / Zone / ...） |
| 模板/输入格式 | **DSL（YAML/JSON）** |
| 变量声明/赋值 | DSL `variable_bindings` 字段 |
| 表达式求值 | `amount: "$self.max_hp * $self.heal_pct"`（受限表达式 DSL） |
| 内建函数 | `lookup_table(name, index)` / `chance(N)` / `in_zone(id)` |
| 条件/分支 | hook `condition` / `if $build.eidolon >= 6:` |
| 事件系统 | `on_battle_start` / `on_turn_start` / `on_before_hit` 等 hook |
| 作用域 | `$self.xxx` / `$event.xxx` / `$build.xxx` / `$resource.xxx` |
| 解释器 | `sim` 引擎（resolver 解析 DSL，engine 运行） |

## 语法速览

```yaml
# variable_bindings：build 决定后、进入 sim 前求值
variable_bindings:
  - self.base_hp = lookup_table("base_hp_by_level", index=$build.level - 1)
  - if $build.eidolon >= 6:
      self.clear_ratio = 0.12

# 表达式 DSL：战斗中动态求值
effects:
  - effect_type: "deal_damage"
    amount: "$self.atk * $self.basic_scaling"
  - effect_type: "gain_resource"
    resource_id: "punchline"
    amount: 5
  - effect_type: "apply_modifier"
    condition: "$self.hp / $self.max_hp < 0.5"
    modifier:
      stat: "dmg_bonus"
      flat_bonus: 0.3
```

完整语法参考见 [21_syntax_reference.md](21_syntax_reference.md)。

## 数据流概览

输入拆为两类运行时文件 + 一组 per-entity 模板：

```
data/sim_templates/          build.yaml              stage.yaml
├── characters/              ├── team[]              ├── stage_template
├── light_cones/             │   ├── character_template
├── relics/                  │   ├── light_cone_template
├── enemies/                 │   └── relics[]
├── stages/                  └── policy              ├── enemy_level_overrides
└── global/                                             ├── environment_overrides
    ├── formulas.yaml                                   └── termination
    └── timing_rules.yaml

         loader ──→ resolver ──→ bind_template ──→ Encounter ──→ sim.engine
```

详细分离设计见 [15_data_separation.md](15_data_separation.md)。

## 模块流向

```
StarRailRes (JSON)
    ↓
[pipeline.loader]
    ↓
raw_schema/
    ↓
[adapters.generate_templates]   ← adapters 允许 import pipeline
    ↓
data/sim_templates/**/*.yaml
    ↓
[sim.loader.build_template_index]
    ↓
[sim.resolver.resolve_variables]  (按 build.yaml)
    ↓
[sim.resolver.bind_template]
    ↓
Encounter
    ↓
[sim.engine.run] ──→ 仿真结果
```

## 文档索引

| 章节 | 主题 |
|------|------|
| [01_formula](01_formula.md) | 伤害公式 |
| [02_globals](02_globals.md) | 全局状态（SP/能量/AV） |
| [03_actor](03_actor.md) | Actor 结构 |
| [04_modifier](04_modifier.md) | Modifier / Buff / 两层属性模型 |
| [05_effects](05_effects.md) | Effect 类型 |
| [06_relics](06_relics.md) | 遗器规则 |
| [07_examples](07_examples.md) | 完整示例 |
| [08_adapter](08_adapter.md) | Adapter / Preprocessing |
| [09_faq](09_faq.md) | 常见问题 |
| [10_termination](10_termination.md) | 结束条件 / AV 系统 |
| [11_combat_log](11_combat_log.md) | 战斗日志 |
| [12_summon](12_summon.md) | 召唤物 / 忆灵 |
| [13_validator](13_validator.md) | 校验规则 |
| [14_policy](14_policy.md) | 策略模型 |
| [15_data_separation](15_data_separation.md) | 数据分离架构 |
| [16_custom_resources](16_custom_resources.md) | 自定义资源容器 |
| [17_actor_state](17_actor_state.md) | Actor 形态状态机 |
| [18_technique_system](18_technique_system.md) | 秘技系统 |
| [19_zone_system](19_zone_system.md) | 场地系统 |
| [20_pre_battle_strategy](20_pre_battle_strategy.md) | 战前策略 |
| [20_elation](20_elation.md) | 欢愉机制 |
| [21_syntax_reference](21_syntax_reference.md) | DSL 语法参考 |

## 波次机制

波次定义战斗中的敌人分组。当一个波次的所有敌人被击败后，下一个波次的敌人登场。

```yaml
waves:
  - wave_index: 1
    enemy_ids: ["1002011", "1002012", "1002013"]
    enemy_levels: [80, 80, 80]
    on_wave_start:
      - effect_type: "apply_modifier"
        modifier_id: "MOD_ENV_BUFF_1"
        target: "all_allies"
        description: "忘却之庭环境 buff"

  - wave_index: 2
    enemy_ids: ["1002020", "1002021"]
    enemy_levels: [80, 80]
    on_wave_start:
      - effect_type: "apply_modifier"
        modifier_id: "MOD_ENV_BUFF_2"
        target: "all_allies"
```

**波次触发时机**：
- `on_wave_start`：新波次敌人登场时触发
- 忘却之庭特殊机制：转波次会清空当前轮次 AV（重置为 150），所有角色和敌人重新计算行动值

## 轮次机制

轮次是 AV（行动值）循环机制，与角色的回合（Turn）是不同概念。详见 `docs/mechanics/action_sequence.md`。

```yaml
cycle:
  first_cycle_av: 150
  subsequent_cycle_av: 100
  on_cycle_start:
    - effect_type: "apply_modifier"
      modifier_id: "MOD_ENV_BUFF"
      target: "all_allies"
  on_cycle_end:
    - effect_type: "remove_modifier"
      modifier_id: "MOD_ENV_BUFF"
      target: "all_allies"
```

**轮次与回合的区别**：
- **回合 (Turn)**：角色/敌人的单次行动，由速度决定行动顺序
- **轮次 (Cycle)**：AV 循环周期，独立于速度，不能被推拉条影响

## 安全模型：DSL-first

`sim` 的运行时输入全部是声明式 DSL，不存在执行任意代码的风险。安全不依赖沙箱，而依赖 DSL 的语法限制和静态验证：

- 模板层没有 `import` / `exec`
- 表达式 DSL 天然无循环
- 解释器不暴露 random/time
- 校验器可静态检查字段类型、变量引用、资源 ID、表达式语法

内部 preprocessing / LLM 辅助生成时可以使用受限 Python 草稿，但必须 transpile 成 DSL 后再进入 sim。

---
