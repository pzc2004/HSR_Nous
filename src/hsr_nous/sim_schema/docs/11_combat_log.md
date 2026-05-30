## 11. 战斗日志 (Combat Log)

战斗模拟器的输出是一个结构化的事件序列，描述从开始到结束的全过程。

### 日志结构

```yaml
combat_log:
  encounter_id: "E_001"
  policy_name: "三月七_default"
  termination_reason: "max_action_value_reached"  # 或 "target_killed" | "all_allies_dead" | "max_turns"

  # 汇总统计
  summary:
    total_damage: 125000
    total_action_value: 1500
    total_turns: 12
    dps: 83.3
    kills: 3
    deaths: 0

  # 事件序列（核心输出）
  events:
    - timestamp: 0
      event_type: "battle_start"
      data: {}

    - timestamp: 0
      event_type: "turn_start"
      actor_id: "1001"
      actor_name: "三月七"
      action_value: 100

    - timestamp: 0
      event_type: "action"
      actor_id: "1001"
      action_id: "1001_skill"
      action_name: "可爱即是正义"
      target_ids: ["1001"]
      skill_points_before: 3
      skill_points_after: 2

    - timestamp: 0
      event_type: "effect"
      effect_type: "apply_modifier"
      source_id: "1001"
      target_id: "1001"
      modifier_id: "MOD_1001_SHIELD"
      duration: 3

    - timestamp: 0
      event_type: "turn_end"
      actor_id: "1001"

    - timestamp: 100
      event_type: "turn_start"
      actor_id: "M_8001"
      actor_name: "银鬃近卫"

    - timestamp: 100
      event_type: "action"
      actor_id: "M_8001"
      action_id: "M_8001_basic"
      action_name: "爪击"
      target_ids: ["1001"]

    - timestamp: 100
      event_type: "damage"
      source_id: "M_8001"
      target_id: "1001"
      damage: 500
      damage_type: "physical"
      is_crit: false
      target_hp_before: 2000
      target_hp_after: 1500

    - timestamp: 100
      event_type: "turn_end"
      actor_id: "M_8001"

    - timestamp: 1500
      event_type: "battle_end"
      reason: "max_action_value_reached"
```

### 事件类型清单

| event_type | 说明 | 关键字段 |
|------------|------|---------|
| `battle_start` | 战斗开始 | - |
| `battle_end` | 战斗结束 | `reason` |
| `turn_start` | 回合开始 | `actor_id`, `action_value` |
| `turn_end` | 回合结束 | `actor_id` |
| `action` | 执行动作 | `action_id`, `target_ids`, `skill_points_before/after` |
| `damage` | 造成伤害 | `source_id`, `target_id`, `damage`, `damage_type`, `is_crit` |
| `heal` | 回复生命 | `source_id`, `target_id`, `heal`, `target_hp_before/after` |
| `effect` | 效果触发 | `effect_type`, `source_id`, `target_id` |
| `modifier_apply` | 施加 buff | `modifier_id`, `duration` |
| `modifier_expire` | buff 过期 | `modifier_id` |
| `break` | 击破韧性 | `source_id`, `target_id`, `toughness_before/after` |
| `kill` | 击杀 | `killer_id`, `target_id` |
| `death` | 死亡 | `actor_id` |
| `energy_change` | 能量变化 | `actor_id`, `before`, `after` |
| `skill_point_change` | 战技点变化 | `before`, `after` |
| `wave_start` | 波次开始 | `wave_index` |
| `wave_end` | 波次结束 | `wave_index` |
| `cycle_start` | 轮次开始 | `cycle_number`, `cycle_av` |
| `cycle_end` | 轮次结束 | `cycle_number`, `av_consumed` |

### Agent 分析友好

日志设计考虑了 Agent 分析需求：

1. **可追溯**：每个事件有 `timestamp`（行动值），可重建时间线
2. **可聚合**：通过 `event_type` 过滤，快速统计伤害/治疗/buff 覆盖率
3. **可归因**：`source_id` → `target_id` 链路清晰，可追踪伤害来源
4. **可比较**：相同 encounter 不同 policy 的日志可直接对比

```python
# Agent 分析示例
def analyze_log(log: dict) -> dict:
    events = log["events"]

    # 统计伤害分布
    damage_events = [e for e in events if e["event_type"] == "damage"]
    total_damage = sum(e["damage"] for e in damage_events)

    # 统计 buff 覆盖率
    buff_events = [e for e in events if e["event_type"] == "modifier_apply"]

    # 统计死亡
    deaths = [e for e in events if e["event_type"] == "death"]

    return {
        "total_damage": total_damage,
        "buff_count": len(buff_events),
        "deaths": len(deaths),
    }
```

---

