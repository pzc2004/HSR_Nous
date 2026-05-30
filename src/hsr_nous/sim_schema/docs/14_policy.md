## 14. 策略 DSL (Policy)

策略是可独立输入、可搜索优化的战斗决策逻辑。采用 **Rule-based DSL + 参数化混合** 设计。

### 设计原则

- **可执行**：模拟器直接 interpret，不需要 LLM 实时参与
- **可参数化**：关键数值（如大招阈值）抽离为可调参数，方便网格搜索/贝叶斯优化
- **LLM 友好**：结构清晰，LLM 容易生成和修改
- **维度拆分**：技能选择、目标选择、时机策略分离

### 策略结构

```yaml
policy:
  name: "三月七_default"
  version: "1.0"

  # ========== 技能选择规则（按 priority 降序匹配）==========
  action_rules:
    - condition: "energy >= ULT_THRESHOLD"
      action: "ultimate"
      priority: 100
      description: "能量满时开大"

    - condition: "skill_points > 0 && ally_without_shield"
      action: "skill"
      priority: 50
      description: "有战技点且队友没护盾时给盾"

    - condition: "true"
      action: "basic"
      priority: 0
      description: "默认普攻"

  # ========== 目标选择规则 ==========
  target_rules:
    - condition: "action_type == 'skill'"
      selector: "lowest_hp_ally"
      priority: 100

    - condition: "action_type == 'ultimate'"
      selector: "all_enemies"
      priority: 100

    - condition: "true"
      selector: "primary_target"
      priority: 0

  # ========== 时机策略（可选）==========
  timing_rules:
    - condition: "buff.stack >= 3 && !enemy.broken"
      timing: "delay"
      delay_condition: "enemy.broken == true"
      description: "buff叠满但敌人未击破，延迟到击破后再出手"

  # ========== 可调参数 ==========
  parameters:
    ULT_THRESHOLD: 120        # 大招能量阈值
    SHIELD_PRIORITY: 0.8     # 护盾优先级权重
    HP_THRESHOLD: 0.5        # 低血量阈值
```

### 规则匹配逻辑

1. **技能选择**：按 `priority` 降序遍历 `action_rules`，第一条 `condition` 为真的规则被执行
2. **目标选择**：同样按优先级匹配，决定技能打谁
3. **时机选择**：决定是否立即出手或延迟等待条件

### 表达式上下文

策略表达式中可以访问的变量：

| 变量 | 说明 |
|------|------|
| `energy` | 当前能量 |
| `skill_points` | 当前战技点 |
| `hp` / `max_hp` | 生命值 |
| `buff.<modifier_id>` | 特定 buff 的引用（如 `buff.MOD_1001_SHIELD.stack`） |
| `enemy.<attr>` | 主目标属性 |
| `allies[]` | 队友列表 |
| `enemies[]` | 敌人列表 |
| `parameters.<name>` | 策略参数 |

### 为什么不用自然语言策略

| 自然语言 | Rule-based DSL |
|---------|---------------|
| "优先使用战技" | `condition: "skill_points > 0", action: "skill"` |
| 不可精确执行 | 100% deterministic |
| 不可搜索优化 | 参数可独立调整，适合贝叶斯优化 |
| LLM 生成后需人工翻译 | LLM 直接生成可执行结构 |

### 参数优化示例

```python
# 用贝叶斯优化搜索最佳大招阈值
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim_schema.policy import Policy

def evaluate(threshold: float) -> float:
    policy = Policy(
        action_rules=[...],
        parameters={"ULT_THRESHOLD": threshold}
    )
    engine = CombatEngine(encounter, policy=policy)
    result = engine.run()
    return result.dps

# 在 [100, 140] 区间搜索最优阈值
best_threshold = bayesian_optimize(evaluate, bounds=(100, 140))
```

### 策略与 Encounter 的关系

```yaml
encounter:
  encounter_id: "E_001"
  formula: {...}
  globals: {...}
  actors: [...]
  policy: {...}        # <-- 每个 encounter 可绑定不同策略
  initial_modifiers: []
```

同一个队伍配不同策略，可以对比不同操作手法的差异。
