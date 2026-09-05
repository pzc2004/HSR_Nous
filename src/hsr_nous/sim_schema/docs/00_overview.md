# Sim Schema 仿真器输入格式

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

本文档定义战斗模拟器的完整输入数据结构。核心设计原则：

- **DSL-first 运行时格式**：所有进入 `sim` 引擎的输入都是声明式 YAML/JSON，不写硬编码逻辑。
- **事件-响应模型**：技能、行迹、星魂、光锥、遗器本质都是事件监听器，在特定时机触发效果。
- **buff/debuff 也是事件监听器**：在持续期间内响应特定事件。
- **模板自包含**（目标形态）：每个实体模板自带 `lookup_tables` + `variable_bindings`，sim 加载即跑——`variable_bindings` 求值器尚未接线（光锥归并也只读白值三围），现状是生成器直接产出求值后数值。

## 设计哲学

| 语言概念 | 对应物 |
|---------|--------|
| 类型系统 | Pydantic 模型（Actor / Effect / Modifier / Zone / ...） |
| 模板/输入格式 | **DSL（YAML/JSON）** |
| 变量声明/赋值 | DSL `variable_bindings` 字段 |
| 表达式求值 | `amount: "$self.max_hp * $self.heal_pct"`（受限表达式 DSL） |
| 内建函数 | `lookup_table(name, index)` / `chance(N)` / `in_zone(id)` |
| 条件/分支 | hook `condition` / `if $build.eidolon >= 6:` |
| 事件系统 | `on_battle_start` / `on_turn_start` / `before_take_damage` 等 hook |
| 作用域 | `$self.xxx` / `$event.xxx` / `$build.xxx` / `$resource.xxx` |
| 解释器 | `sim` 引擎（compile 层绑定编译 DSL，engine 运行） |

### 数据三分：配置 / 状态 / 规则

一切实体（角色/光锥/遗器/敌人/关卡/策略）的输入数据都分三类：

| 类 | 身份 | 例子 |
|----|------|------|
| 常量数值 | 静态配置 | 面板、倍率、消耗定值、资源定义（上限/初始值）、等级与系数 |
| 自定义变量 | 动态状态 | 资源当前值、计数器、标记、激活中的 modifier 与召唤物实例 |
| 技能机制 | 规则 | effects / triggers / modifiers / 状态机定义 |

战前组装时，光锥/遗器等实体**编译归并**进所属 actor 的三桶：数值→面板、机制→挂身 modifier、叠层→`custom_resources`。引擎只消费组装完的 actor，不认识"光锥""遗器"这类实体类别。

战斗中：**规则不变、配置静止、状态演化**。effect 是动作不是数据——激活的 modifier 实例归状态桶，战斗日志是输出不是输入。不存在第四类数据。

## 语法速览

```yaml
# variable_bindings：build 决定后、进入 sim 前求值
# （目标语法——求值器未落地：编译器不消费本字段，生成器直接产出求值后数值）
variable_bindings:
  - self.base_hp      = lookup_table("base_hp_by_level", index=$build.level - 1)
  - self.basic_scaling = lookup_table("basic_scaling",   index=$build.skill_levels.basic - 1)
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
      stat: "all_dmg_bonus"
      flat_bonus: 0.3
```

完整语法参考见 [22_syntax_reference.md](22_syntax_reference.md)。

## 数据流概览

输入拆为两类运行时文件 + 一组 per-entity 模板：

```
data/sim_templates/        build.yaml                 stage.yaml
├── characters/            ├── team[]                 ├── stage_id
├── light_cones/           │   ├── character_template ├── mode（玩法模式 → rulebook modes 派生轮次）
├── relics/                │   ├── light_cone_template├── enemies[]（inline / enemy_template 引用）
└── enemies/               │   └── relics[]           ├── waves[]（wave 键仅 {wave_index, enemies}）
                           ├── policy                    └── termination
                           └── pre_battle
（stages/、global/ 磁盘未生成：stage 模板通道待 adapters，全局公式唯一来源已迁 rulebook.yaml——见 15 章）

              [sim.compile.compile_encounter]（BuildCompiler + StageCompiler）
                                ↓
                  CompiledEncounter（不可变编译产物）
                                ↓
              [sim.engine.CombatEngine.from_compiled] ──→ 仿真结果
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
[adapters.template_generator]   ← adapters 允许 import pipeline
    ↓
data/sim_templates/**/*.yaml
    ↓
[sim.compile.build_compiler]  (build.yaml → 队伍 + policy；模板按引用编译期 glob 加载)
    ↓
[sim.compile.stage_compiler]  (stage.yaml → 阵容 + 波次 + 轮次)
    ↓
CompiledEncounter（不可变编译产物）
    ↓
[sim.engine.CombatEngine.from_compiled] ──→ 仿真结果
```

## 文档索引

章节清单唯一来源：[../README.md](../README.md)（索引闸 `tests/test_doc_lint.py` 双向校验 README ↔ 磁盘），本文件不另维护副本。

## 波次机制

波次定义战斗中的敌人分组。当一个波次的所有敌人被击败后，下一个波次的敌人登场。

```yaml
# stage.yaml inline 形——wave 合法键仅 {wave_index, enemies}（stage_compiler _WAVE_KEYS）
waves:
  - wave_index: 1
    enemies:
      - enemy_template: "1002011"   # 引用 data/sim_templates/enemies/1002011_Ice_Edge.yaml
        level: 80
      - enemy_template: "1002012"
        level: 80
      - enemy_template: "1002013"
        level: 80

  - wave_index: 2
    enemies:
      - enemy_template: "1002020"
        level: 80
      - enemy_template: "1002021"
        level: 80
```

> 环境 buff 不进 wave 配置——`on_wave_start` 是总线事件（契约表已登记），由模板 hooks 订阅触发。`stage.yaml` 顶层的 `enemy_level_overrides` / `environment_overrides` 属 `stage_template` 引用通道的覆盖槽——该通道**未接入**（引用 `stage_template` 编译期抛 `NotImplementedError`），inline stage 写这两个键会被顶层键闸拒绝。

**`enemy_template` 引用侧的覆盖槽**：`actor_id` / `name` 可按引用覆盖（`level` / `taunt` 同理）——同一份敌人模板多放（一波同型怪、多个沙包假人）靠它去重；不覆盖则取模板 `enemy_id`/原名，多份引用会产出同 id 单位互相覆盖。

**波次触发时机**：
- `on_wave_start`：新波次敌人登场时发射（总线事件）
- 忘却之庭特殊机制：转波次会清空当前轮次 AV（重置为首轮 AV），所有角色和敌人重新计算行动值（**倒计时实体除外**——跨波按原行动值续跑，见 `03_actor.md` §3.11）

## 轮次机制

轮次是 AV（行动值）循环机制，与角色的回合（Turn）是不同概念。详见 `../../../../docs/mechanics/03_action_sequence.md`。

```yaml
# stage.yaml 不直写轮次 AV——由 mode 查 rulebook.yaml modes 节派生（stage 编译器填 Cycle）
mode: forgotten_hall
```

> `Cycle`（first_cycle_av / subsequent_cycle_av / reset_on_wave）的唯一来源是 `rulebook.yaml` modes 节，stage.yaml 无 cycle 键；轮次起止是总线事件（`on_cycle_start` / `on_cycle_end`，契约表已登记、发射已接线于 engine._tick_cycle），`Cycle` 无 on_cycle_start/end 配置字段——轮次 buff 类机制经模板 hooks 订阅。

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
