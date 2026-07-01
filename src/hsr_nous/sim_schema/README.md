# Sim Schema 仿真器输入格式

本文档定义战斗模拟器的完整输入数据结构。核心设计原则：**DSL-first 运行时格式 + 事件-响应模型**。

> **Schema 实现状态**：本目录下的文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

## 文档结构

| 文件 | 内容 |
|------|------|
| [00_overview.md](docs/00_overview.md) | 设计哲学、数据流概览、波次/轮次机制 |
| [01_formula.md](docs/01_formula.md) | 伤害公式（12 乘区、特殊伤害、击破效果、削韧值） |
| [02_globals.md](docs/02_globals.md) | 全局状态（行动值、战技点、能量系统） |
| [03_actor.md](docs/03_actor.md) | 参战单位（角色/敌人属性、技能、行迹、星魂、光锥、遗器） |
| [04_modifier.md](docs/04_modifier.md) | Buff/Modifier（结构、A/B 类判定、叠加、驱散、触发时机、两层属性模型） |
| [05_effects.md](docs/05_effects.md) | 效果类型（伤害、治疗、buff、资源、形态、场地等） |
| [06_relics.md](docs/06_relics.md) | 遗器数值设计（主词条、副词条） |
| [07_examples.md](docs/07_examples.md) | 完整输入示例 |
| [08_adapter.md](docs/08_adapter.md) | 与 Adapter / Preprocessing 的交互边界 |
| [09_faq.md](docs/09_faq.md) | FAQ（表达式执行、嘲讽、欢愉命途、召唤物等） |
| [10_termination.md](docs/10_termination.md) | 战斗结束条件、行动值系统 |
| [11_combat_log.md](docs/11_combat_log.md) | 战斗日志结构、事件类型清单 |
| [12_summon.md](docs/12_summon.md) | 召唤物/忆灵系统 |
| [13_validator.md](docs/13_validator.md) | 输入验证规则（Pydantic + DSL 静态检查） |
| [14_policy.md](docs/14_policy.md) | 策略模型（规则匹配、参数优化） |
| [15_data_separation.md](docs/15_data_separation.md) | 数据分离：per-entity 模板 / build.yaml / stage.yaml |
| [16_custom_resources.md](docs/16_custom_resources.md) | 自定义资源容器 |
| [17_actor_state.md](docs/17_actor_state.md) | Actor 形态状态机 |
| [18_technique_system.md](docs/18_technique_system.md) | 秘技系统 |
| [19_zone_system.md](docs/19_zone_system.md) | 场地系统 |
| [20_pre_battle_strategy.md](docs/20_pre_battle_strategy.md) | 战前策略 |
| [21_elation.md](docs/21_elation.md) | 欢愉机制 |
| [22_syntax_reference.md](docs/22_syntax_reference.md) | DSL 语法参考 |
| [23_event_hook_system.md](docs/23_event_hook_system.md) | 事件 Hook 系统 |

## 数据流

```
StarRailRes (JSON)
    ↓
[pipeline.loader]
    ↓
raw_schema/
    ↓
[adapters.generate_templates]
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

## 与模块边界的关系

| 模块 | 允许 import | 禁止 import |
|------|------------|------------|
| `pipeline/` | 无 | `raw_schema`, `sim_schema`, `sim`, `agents`, `api` |
| `raw_schema/` | 无 | `sim_schema`, `sim`, `agents`, `api` |
| `adapters/` | `pipeline`, `raw_schema`, `sim_schema` | `sim` |
| `sim/` | `sim_schema` | `raw_schema`, `pipeline`, `adapters`, `agents`, `api` |
| `agents/` | `adapters`, `sim`, `pipeline`（仅数据查询） | `raw_schema` |
| `api/` | `agents`, `adapters`, `sim` | `pipeline`, `raw_schema` |

- `adapters/` 把 `raw_schema` 转换成 `data/sim_templates/**/*.yaml`
- `sim/` 只消费绑定后的 `Encounter`，不直接读 `raw_schema` 或 `pipeline/`
- 公式定义与 `../../../docs/mechanics/02_damage_formula.md` 对齐
