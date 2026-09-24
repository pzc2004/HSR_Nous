# API 编排层

协调多 Agent 完成完整 ReAct 决策闭环的编排器。

## 文件说明

| 文件 | 职责 |
|------|------|
| `orchestrator.py` | `Orchestrator`：管理 Agent 执行顺序和中间状态传递 |

## 设计决策

- `Orchestrator` 持有所有 Agent 实例，按固定流程调度
- 中间状态（如候选列表、评估结果）由编排器管理，不暴露给单个 Agent
- 支持在任意步骤注入人类反馈（Human-in-the-loop）
- 跨模块 import 边界以根 `AGENTS.md` 模块边界表为准

## 使用方式

```python
from hsr_nous.api import Orchestrator

orch = Orchestrator()
result = orch.run(goal="最大化黄泉伤害", constraints={"team_size": 4})
print(result["report"])
```

## 修改记录

- 初始创建：占位实现，ReAct 循环待实现
