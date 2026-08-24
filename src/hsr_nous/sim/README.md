# Sim 战斗模拟器（翁法罗斯 / Amphoreus）

纯战斗仿真核心，只依赖 `sim_schema`，不认识 `raw_schema` 和 `pipeline`。
形状是"编译器 + 虚拟机"：`compile/` 把 DSL YAML 编译为不可变 `CompiledEncounter`，
运行时 VM（调度 / 事件总线 / 结算管线）从它完整重建每一局。

## 模块地图

| 文件 | 职责 |
|------|------|
| `engine.py` | `CombatEngine` 战斗主干：回合四段主循环 + 击破 + 敌人行动 + 波次切换 + 护盾/生存/光环/轮次（hooks/modifier/策略运行时已拆出，本类薄委托） |
| `scheduler.py` | `Scheduler`：距离制调度器——守恒剩余距离为主状态，红黑树排序键 = 派生预计时刻 |
| `avtree.py` | `AVTree`：数组化红黑树（CFS 同构有序平衡树，整树一根 int 数组，snapshot 免费） |
| `bus.py` | `EventBus`：事件总线——发射点 / waterfall-emit 分派 / modify_event |
| `hooks.py` | `HookRuntime`：模板 hooks 运行时（订阅 + 条件求值 + 效果执行） |
| `modifiers.py` | `ModifierBook`：modifier 生命周期（施加/tick 走字/驱散净化/物化）+ 护盾吸收 |
| `pipeline.py` | `SettlementPipeline`：结算管线（两层求值 → effect 原语 → 伤害公式），公式全部来自 `sim_schema/rulebook.yaml` 表达式，节点值树输出 |
| `state.py` | 战斗全状态 dataclass：可序列化快照（纯净不变量的载体） |
| `resources.py` | 能量资源三段式（ult_threshold / 终结技可用性判定） |
| `policy_api.py` | 策略接口：`legal_action_set` 生成 + 决策点注入 + `ScriptedPolicy` / `CompiledPolicyRuntime` |
| `montecarlo.py` | 多局统计聚合：roll 模式 N 局 → 伤害分布 |
| `compile/` | 绑定编译层：build/stage YAML → 不可变 `CompiledEncounter`（符号解析 + AST 预编译 + 糖 desugar） |

## 设计文档

- 机制规格（唯一事实来源）：`src/hsr_nous/sim_schema/docs/`（含公式镜像 `01_formula.md` ↔ 可执行来源 `rulebook.yaml`）
- 架构文档（入库）：`docs/engine_design.md`——编译器+VM 分层、三条全局不变量（纯净 / 白名单求值 / waterfall-emit 契约）、当前未实现清单
- 设计草稿（本地不入库）：`designs/ENGINE_DESIGN.md`

## 使用方式

```python
from hsr_nous.sim import CombatEngine, MODE_EXPECTED
from hsr_nous.sim.compile import compile_encounter_yaml

compiled = compile_encounter_yaml(build_yaml_text, stage_yaml_text)
state = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, seed=42).run()
print(state.total_damage)
```

低层入口（手写 sim_schema 对象，golden case 用）：直接构造 `CombatEngine(Encounter, ...)`，
见 `tests/test_engine_v01.py`。

## 测试

- golden case / 两局全等（纯净不变量）：`tests/test_engine_v01.py` 起的一批 `test_engine_*.py`
- 调度树 property test、表达式注入防护、rulebook↔文档镜像闸等：`pytest tests/`
