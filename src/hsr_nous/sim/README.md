# Sim 战斗模拟器

纯战斗仿真核心，只依赖 `sim_schema`，不认识 `raw_schema` 和 `pipeline`。

## 文件说明

| 文件 | 职责 | 状态 |
|------|------|------|
| `engine.py` | `CombatEngine`：行动值驱动主循环 + `PolicyInterpreter` 策略解释器 | ✅ Phase 1（直伤循环） |
| `timeline.py` | `Timeline`：行动序管理（AV=10000/速度、拉条/推条/变速） | ✅ Phase 1 |
| `resolver.py` | `DamageResolver`：标准直伤公式（12 乘区期望形式） | ✅ Phase 1 |
| `selectors.py` | 目标选择器注册表 + 参数化选择器解析 | ✅ 完善 |

> 实现进度见 [docs/sim_engine_roadmap.md](../../../docs/sim_engine_roadmap.md)。
> Phase 1（行动值 + 直伤）已完成；Phase 2（Modifier/buff）、Phase 3（能量/击破/轮次）待实现。

## 设计决策

- **事件-响应模型**：游戏运行时触发事件，所有机制（技能/buff/光锥）注册为监听器
- **策略模型**：`PolicyInterpreter` 解释 Rule-based 策略，支持字符串选择器（注册表）和字典选择器（参数化）
- **目标选择器可扩展**：通过 `@register_selector` 装饰器或参数化字典内联定义

## 使用方式

```python
from hsr_nous.sim import CombatEngine
from hsr_nous.sim_schema import Encounter, Policy

engine = CombatEngine(encounter=enc, policy=policy)
result = engine.run()
print(result.total_damage)
```

## 修改记录

- 初始创建：`CombatEngine` 骨架 + `PolicyInterpreter`
- 添加 `selectors.py`：目标选择器注册表 + 参数化选择器解析
- `PolicyInterpreter.select_target` 支持字符串（注册表）和字典（参数化）两种 selector
