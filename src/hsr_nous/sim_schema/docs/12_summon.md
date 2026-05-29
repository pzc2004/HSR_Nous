## 11. 召唤物系统 (Summon/Memosprite)

召唤物（忆灵）是类似角色的战斗单位，但有特殊行为模式。

### 11.1 召唤物 Actor 结构

```yaml
actor:
  actor_id: "SUMMON_001"
  name: "小伊卡"
  actor_type: "summon"           # character | monster | summon
  level: 80
  owner_id: "1001"               # 召唤者 ID

  # 召唤物属性（可选，不一定全部拥有）
  base_stats:
    hp: 5000                     # 可选：有些召唤物没有生命值
    atk: 800
    def: 300
    spd: 100
    # ... 其他属性可选

  # 召唤物行为模式
  behavior:
    # 行动模式
    action_mode: "independent"   # "independent" | "triggered"

    # independent：出现在行动条上，独立计算行动值
    # triggered：不出现在行动条上，仅在触发条件满足时行动

    # 触发条件（triggered 模式下）
    triggers:
      - event: "on_owner_action_end"  # 召唤者行动后
        description: "风堇的小伊卡"
      - event: "on_ally_hit"          # 队友受击时
        description: "反击型召唤物"
      - event: "on_owner_hp_low"      # 召唤者血量低时
        description: "保护型召唤物"

    # 离场条件
    leave_conditions:
      - type: "hp_zero"          # 生命值归零
      - type: "duration_expire"  # 持续时间到期
      - type: "owner_leave"      # 召唤者离场
      - type: "manual"           # 手动召回（技能效果）
      - type: "mechanic"         # 自身机制（如特定条件触发）

    # 继承规则
    inheritance:
      stats: "partial"           # "full" | "partial" | "none"
      # full：继承召唤者全部属性
      # partial：部分继承（如只继承攻击力）
      # none：使用召唤物自身属性

  # 召唤物技能
  actions:
    - action_id: "SUMMON_001_basic"
      name: "伊卡攻击"
      action_type: "basic"
      target_type: "enemy_single"
      toughness_dmg: 10

  # 召唤物特有机制
  special_mechanics:
    - mechanic: "heal_on_action"
      description: "每次行动后恢复召唤者生命值"
      trigger: "on_after_action"
      effect_type: "heal"
      target: "owner"
      scaling: 0.1
```

### 11.2 召唤物行为模式

| 模式 | 说明 | 示例 |
|------|------|------|
| `independent` | 出现在行动条上，独立计算行动值 | 景元的神君 |
| `triggered` | 不出现在行动条上，仅在触发条件满足时行动 | 风堇的小伊卡、反击型召唤物 |

**触发条件示例**：
- `on_owner_action_end`：召唤者行动后（小伊卡）
- `on_ally_hit`：队友受击时（反击型）
- `on_owner_hp_low`：召唤者血量低时（保护型）
- `on_kill`：击杀敌人时（追击型）

### 11.3 召唤物生命周期

```yaml
# 召唤流程
summon_flow:
  trigger: "on_skill_cast"       # 触发时机
  condition: "skill_id == XXX"   # 触发条件
  effect_type: "summon"
  summon_id: "SUMMON_001"
  position: "after_owner"        # 召唤位置

# 离场流程
leave_flow:
  trigger: "on_hp_zero"          # 生命值归零
  effect_type: "dismiss_summon"
  summon_id: "SUMMON_001"

# 续命机制（某些召唤物可以被治疗/续命）
sustain_mechanic:
  can_be_healed: true            # 是否可被治疗
  can_be_shielded: true          # 是否可被套盾
  persistence: "temporary"       # "permanent" | "temporary"
```

### 11.4 召唤物与忆灵的区别

| 特性 | 普通召唤物 | 忆灵（记忆命途） |
|------|-----------|----------------|
| 行动模式 | 多为 `independent` | 多为 `triggered`（on_owner_action_end） |
| 属性继承 | 部分继承 | 通常独立属性 |
| 离场条件 | 多样 | 通常与召唤者绑定 |
| 技能组 | 固定 | 可能随召唤者成长 |

---

