## 10. 战斗结束条件 (Termination)

结束条件决定模拟何时停止，支持多种模式组合。

```yaml
# 模式一：固定行动值，统计总伤害
termination:
  mode: "fixed_av"
  max_action_value: 1500
  max_turns: 50
```

```yaml
# 模式二：击杀目标，统计所需行动值
termination:
  mode: "kill_target"
  target_ids: ["M_8001", "M_8002"]  # 指定敌人 ID，空列表表示全部
  max_turns: 50
```

```yaml
# 模式三：生存测试，统计存活回合数
termination:
  mode: "survival"
  max_turns: 20
```

```yaml
# 模式四：全灭测试
termination:
  mode: "wipe"
  max_turns: 50
```

### 10.1 行动值系统

**行动值公式**：
```yaml
action_value: "10000 / speed"
```

**拉条/推条**：
```yaml
# 立即行动：直接设 AV = 0
effect_type: "immediate_action"
```

```yaml
# 100% 拉条：current_AV - 10000/speed（若之前被推条可能不到 0）
effect_type: "advance_action"
amount: 100  # 百分比
```

```yaml
# N% 拉条（0 < N < 100）：current_AV - 10000/speed × N%，最小为 0
effect_type: "advance_action"
amount: 50   # 50% 拉条
```

```yaml
# 推条（行动延后）：current_AV + 10000/speed × 延后比例，上限 999
effect_type: "delay_action"
amount: 30   # 行动延后 30%
# 注意：推条后 AV 最大为 999
```

**遇袭**：战斗开始时若被遇袭，所有我方角色行动值 +20。

**速度变化时行动值调整**：
```yaml
# 当速度发生变化时，行动值需要实时调整
new_action_value: "current_action_value * old_speed / new_speed"
# 若当前 AV = 0，速度变化从下一次行动值计算开始生效
```

**冻结/强烈震荡补偿**：
```yaml
# 冻结解除后，行动值为初始值的 50%
action_value_penalty: 0.5
```

```yaml
# 强烈震荡解除后，行动值为初始值的 70%
action_value_penalty: 0.7
```

```yaml
# 若未跳过行动就被解除冻结/震荡，则不会触发补偿
no_compensation_if_not_skipped: true
```

**插入行动优先级**：
1. 追加攻击
2. 终结技
3. 命途回响
4. 额外回合
5. 战技触发

**后拉先动原则**：行动值相同时，后拉条的单位先行动。

> Zone 的 `duration_decrement_trigger` 也基于回合/轮次边界，详见 `19_zone_system.md`。

**输出指标（根据模式不同）**：

| 模式 | 主要输出 | 次要输出 |
|------|---------|---------|
| `fixed_av` | 总伤害、DPS | 伤害分布、击杀数 |
| `kill_target` | 所需行动值、回合数 | 伤害效率 |
| `survival` | 存活回合数、存活率 | 承伤总量、治疗量 |
| `wipe` | 是否全灭、全灭回合 | 剩余敌人血量 |

---
