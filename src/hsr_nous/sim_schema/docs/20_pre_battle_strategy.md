## 20. 战前策略 (Pre-Battle Strategy)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

### 20.1 设计目标

让 agent/LLM 显式声明“谁先放秘技、谁最后攻击进战”，并把强制进战的副作用明确化。

### 20.2 PreBattleStrategy 字段

```python
class PreBattleStrategy(BaseModel):
    name: str = "default"
    technique_order: list[str] = []
    entry_attacker: str = ""
    point_policy: Literal["auto", "strict", "force"] = "auto"
    battle_start_effects: list[Effect] = []   # 秘技 effects 累积队列，进战时按序 fire（见 18.3）
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `name` | string | `"default"` | 策略名 |
| `technique_order` | `List[technique_id]` | `[]` | 秘技施放顺序 |
| `entry_attacker` | `actor_id` | `""` | 若未触发强制进战，由该角色攻击进战；进战触发者记录供战斗内表达式读取（`$battle.entry_attacker`——大丽花"开战的队友"族，决策卡 #18） |
| `maze_attack` | `{toughness_dmg, element?}` | — | 大世界普攻进战削韧的 adapter 层声明块（非秘技、不耗点；element 缺省 = 进战角色自身属性）——决策卡 #19 族 12 |
| `point_policy` | enum | `"auto"` | 秘技点不足时的策略 |
| `battle_start_effects` | `List[Effect]` | `[]` | 战前遍历中各秘技 effects 的累积队列（释放瞬间不执行，进战时按顺序 fire） |

### 20.3 `point_policy` 枚举

| 值 | 行为 |
|----|------|
| `"auto"` | 按 `technique_order` 顺序施放，秘技点不够就跳过 |
| `"strict"` | 秘技点不够立即终止整个战前策略 |
| `"force"` | 忽略秘技点限制全部施放（用于策略对比实验） |

### 20.4 执行流程

```
1. 初始化：
   technique_point_initial = team_defaults.technique_point_initial
                           + Σ team.member.team_modifiers.technique_point_initial_bonus
   technique_point_max     = team_defaults.technique_point_max
                           + Σ team.member.team_modifiers.technique_point_max_bonus

2. 遍历 technique_order：
   a. 取当前 technique
   b. 若 forces_battle_entry == true：
      - 检查秘技点是否 ≥ point_cost（强制进战技同样消耗 TP，见 18.7）
      - 若不足：按 point_policy 处理（skip / strict fail / force）
      - 若足够：扣点 + 该 technique 的 effects 追加到 `battle_start_effects` 队列
      - 触发战斗（直接进入 step 4）
      - 若后面还有未处理的 technique → 输出 WARNING
   c. 否则（预置秘技）：
      - 检查秘技点是否 ≥ point_cost
      - 若不足：按 point_policy 处理（skip / strict fail / force）
      - 若足够：扣点 + effects 追加到 `battle_start_effects` 队列，继续下一个

3. 若遍历完毕都未触发强制进战：
   - 由 entry_attacker 发动攻击，触发战斗

4. 战斗开始：按序 fire `battle_start_effects`（释放瞬间不执行、进战才生效，见 18.3）；之后所有 preload 视为 actor 已有状态，应用 on_battle_start
```

### 20.5 WARNING 协议

```yaml
warnings:
  - code: TECHNIQUE_ORDER_TRUNCATED
    severity: warn
    message: "秘技 '刃_无间地狱' 是强制进战技，其后的 2 个秘技不会生效"
    location:
      strategy: pre_battle_default
      technique_index: 1
      truncated: [2, 3]
    recommendation: "将强制进战技放在 technique_order 末尾，或改用其他角色 entry_attacker"
```

**输出位置**：
- 引擎返回 `BattleStartResult` 时附带 `warnings: List[Warning]`
- 编排器把 warnings 暴露给 agent，供下一轮策略迭代修正

### 20.6 示例

```yaml
pre_battle_strategy:
  name: "phainon_first"
  technique_order:
    - "kafka_technique"
    - "blade_technique"        # 强制进战技
    - "hyacine_technique"      # 不会执行
  entry_attacker: "kafka"
  point_policy: "auto"
```

### 20.7 明确不建模

- **拉黑**（apply_blacklist）：大世界隐身机制
- **红包 / 击碎可破坏物奖励**：大世界奖励，与战斗仿真无关

### 20.8 TBD

- `technique_order` 元素类型：`technique_id` vs `actor_id`（TBD）。
- WARNING 是否阻断执行，以及 `warn` / `error` 分级（TBD）。
- 秘技预置能否覆盖角色基线属性（TBD）。

---
