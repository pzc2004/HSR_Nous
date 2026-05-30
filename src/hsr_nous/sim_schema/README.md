# Sim Schema 仿真器输入格式

本文档定义战斗模拟器的完整输入数据结构。核心设计原则：**一切机制都抽象为"事件-响应"模型**。

## 文档结构

| 文件 | 内容 |
|------|------|
| [00_overview.md](docs/00_overview.md) | 设计哲学、数据流概览、波次/轮次机制 |
| [01_formula.md](docs/01_formula.md) | 伤害公式（12 乘区、特殊伤害、击破效果、削韧值） |
| [02_globals.md](docs/02_globals.md) | 全局状态（行动值、战技点、能量系统） |
| [03_actor.md](docs/03_actor.md) | 参战单位（角色/敌人属性、技能、行迹、星魂、光锥、遗器） |
| [04_modifier.md](docs/04_modifier.md) | Buff/Modifier（结构、A/B 类判定、叠加、驱散、触发时机） |
| [05_effects.md](docs/05_effects.md) | 效果类型（伤害、治疗、buff、拉条等） |
| [06_relics.md](docs/06_relics.md) | 遗器数值设计（主词条、副词条） |
| [07_examples.md](docs/07_examples.md) | 完整输入示例 |
| [08_adapter.md](docs/08_adapter.md) | 与 Adapter 的交互边界（角色/敌人数据映射） |
| [09_faq.md](docs/09_faq.md) | FAQ（表达式执行、嘲讽、欢愉命途、召唤物等） |
| [10_termination.md](docs/10_termination.md) | 战斗结束条件、行动值系统 |
| [11_combat_log.md](docs/11_combat_log.md) | 战斗日志结构、事件类型清单 |
| [12_summon.md](docs/12_summon.md) | 召唤物/忆灵系统 |
| [13_validator.md](docs/13_validator.md) | 输入验证规则 |
| [14_policy.md](docs/14_policy.md) | 策略 DSL（规则匹配、参数优化） |
| [15_data_separation.md](docs/15_data_separation.md) | 数据分离：游戏机制 vs 玩家配装 |

## 与模块边界的关系

```
pipeline/ → raw_schema/ → adapters/ → sim_schema (本文档) → sim/
```

- `adapters/` 把 `raw_schema`（StarRailRes 数据）转换成本文定义的格式
- `sim/` 只认识 `sim_schema`，不直接读 `raw_schema` 或 `pipeline/`
- 公式定义与 `docs/mechanics/damage_formula.md` 对齐
