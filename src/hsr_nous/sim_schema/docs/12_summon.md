## 12. 召唤物系统 (Summon/Memosprite)

召唤物是角色在战斗中召唤的独立单位，拥有自己的速度和行动序列。造成伤害时使用召唤者的当前属性。一般情况下召唤物不能被敌方或我方选中为目标。

**忆灵**是记忆命途角色的专属召唤物，与普通召唤物不同，忆灵**可以被选中为目标**（接受我方 buff/治疗，也会被敌方攻击）。

### 12.1 召唤物 Actor 结构

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

    # 继承规则（继承的是召唤者的战斗外面板，非战斗内状态）
    inheritance:
      stats: "partial"           # "full" | "partial" | "none"
      # full：继承召唤者战斗外面板全部属性
      # partial：部分继承（如只继承攻击力）
      # none：使用召唤物自身属性

    # 战斗内属性独立性
    combat_independence: true
    # 召唤者和召唤物的战斗内属性变化互不干扰
    # 单体 buff 不会共享（给召唤者加攻不影响召唤物）


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

    # 忆灵行动时为召唤者恢复能量
    - mechanic: "energy_restore_to_owner"
      description: "忆灵施放技能时为召唤者恢复能量"
      trigger: "on_after_action"
      effect_type: "gain_energy"
      target: "owner"
      value: 10
```

### 12.2 召唤物行为模式

| 模式 | 说明 | 示例 |
|------|------|------|
| `independent` | 出现在行动条上，独立计算行动值 | 景元的神君 |
| `triggered` | 不出现在行动条上，仅在触发条件满足时行动 | 风堇的小伊卡、反击型召唤物 |

**触发条件示例**：
- `on_owner_action_end`：召唤者行动后（小伊卡）
- `on_ally_hit`：队友受击时（反击型）
- `on_owner_hp_low`：召唤者血量低时（保护型）
- `on_kill`：击杀敌人时（追击型）

### 12.3 召唤物生命周期

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

### 12.4 忆灵特性

忆灵与普通召唤物的关键区别：

| 特性 | 普通召唤物 | 忆灵（记忆命途） |
|------|-----------|----------------|
| 可被选中 | 否 | 是（可接受 buff/治疗/被敌方攻击） |
| 属性继承 | 视角色而定 | 默认继承忆师战斗外面板，有特殊说明的优先 |
| 状态效果 | 独立 | 独立于忆师（单体 buff 不共享） |
| 遗器套装效果 | — | 大部分条件性加成不生效（除非特殊说明） |
| 影响范围 | — | 影响忆师的效果不影响忆灵，反之亦然（全体效果除外） |
| 召唤位置 | — | 忆师右侧（不可能是队伍第一个目标） |
| 技能升级 | — | 忆灵技能和忆灵天赋独立于忆师行迹升级 |
| 行动模式 | 多为 `independent` | 有固定速度，出现在行动条上 |
| SPD 例外 | — | 小伊卡(Hyacine)和 Demiurge(Cyrene) SPD=0，不出现在行动条上，只能通过额外回合行动 |
| 嘲讽 | — | 有独立嘲讽值（Pollux 除外，为后备单位不可选中） |

**忆灵离场条件**：
- 生命值归零
- 特定条件（如 Garmentmaker 倒计时、Pollux 回合限制）
- 离场后忆师需重新召唤

### 12.5 与自定义资源、形态状态机的关系

- 忆灵/召唤物可以有自己的 `custom_resources`（如风堇小伊卡的 `hyacine_cumulative_heal`），见 `16_custom_resources.md`。
- 忆灵/召唤物也可以有 `actor_state` 和 `state_config`，用于表达形态切换，见 `17_actor_state.md`。
- 召唤物继承召唤者的 Layer 1 属性（不是 effective），避免 scaling 循环。详见 `04_modifier.md` §4.9。

---

