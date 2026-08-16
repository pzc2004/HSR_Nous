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
    # 复合触发名是"发射点 × 过滤"的语法糖（不逐机制膨胀枚举）
    triggers:
      - event: "on_after_action"       # 发射点：任意行动后
        condition: "$event.actor == $self.owner"   # 过滤：行动者是召唤者（原 on_owner_action_end）
        description: "风堇的小伊卡"
      - event: "after_being_hit"       # 发射点：任意友方被命中
        condition: "$event.target != $self"        # 过滤：非自身（队友受击，原 on_ally_hit）
        description: "反击型召唤物"
      - event: "on_hp_decrease"        # 发射点：HP 降低
        condition: "$event.target == $self.owner"  # 过滤：目标是召唤者（原 on_owner_hp_low；低血量阈值在 effects 的 condition 中给出）
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

  # 召唤物特有机制（可选，用于描述非标准 action 的被动机制）
  special_mechanics:
    - mechanic: "heal_on_action"
      description: "每次行动后恢复召唤者生命值"
      trigger: "on_after_action"
      effect_type: "heal"
      target: "owner"
      amount: "$self.max_hp * 0.1"

    # 忆灵行动时为召唤者恢复能量
    - mechanic: "energy_restore_to_owner"
      description: "忆灵施放技能时为召唤者恢复能量"
      trigger: "on_after_action"
      effect_type: "gain_energy"
      target: "owner"
      amount: 10
```

`special_mechanics` 是召唤物/忆灵的可选描述字段，每个条目包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `mechanic` | string | 机制标识名 |
| `description` | string | 人类可读描述 |
| `trigger` | enum | 触发时机（Modifier trigger 命名空间） |
| `effect_type` | enum | 触发效果类型 |
| `target` | selector | 效果目标 |
| `amount` / `pct` / 其他 | 视 `effect_type` | 效果参数 |

> `special_mechanics` 中的 effect 语义上等价于在 `actions` / `traces` / `hooks` 中显式声明的 effect；它只是一种更紧凑的召唤物专用描述方式。

### 12.2 召唤物行为模式

| 模式 | 说明 | 示例 |
|------|------|------|
| `independent` | 出现在行动条上，独立计算行动值 | 景元的神君 |
| `triggered` | 不出现在行动条上，仅在触发条件满足时行动 | 风堇的小伊卡、反击型召唤物 |

**触发条件示例**（写法均为"发射点 + `condition` 过滤"）：
- `on_after_action` + `condition: "$event.actor == $self.owner"`：召唤者行动后（小伊卡）
- `after_being_hit` + `condition: "$event.target != $self"`：队友受击时（反击型）
- `on_hp_decrease` + `condition: "$event.target == $self.owner"`：召唤者血量降低时（保护型；阈值另行给定）
- `on_kill`：击杀敌人时（追击型）

### 12.3 召唤物生命周期

#### 召唤入场

召唤通过角色 action 的 `summon` effect 触发：

```yaml
actions:
  - action_id: "140902"
    action_type: "skill"
    effects:
      - trigger: "on_cast"
        effect_type: "summon"
        summon_id: "hyacine_memosprite"
        position: "after_owner"        # 召唤位置：after_owner | before_owner | fixed_position
```

#### 离场/解散

召唤物生命值归零或满足特定条件时，通过 `dismiss_summon` effect 离场：

```yaml
# 在召唤物自身模板中
actions:
  - action_id: "hyacine_memosprite_passive"
    action_type: "basic"
    effects:
      - trigger: "on_hp_zero"
        effect_type: "dismiss_summon"
        summon_id: "hyacine_memosprite"
```

#### 续命机制

某些召唤物可以被治疗/续命：

```yaml
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
| 嘲讽 | — | 有独立嘲讽值 |

**忆灵/召唤物能力通用约定**：能力集合**默认全开**——可被敌方选中、可被我方选中、有 AV（上行动条）、参与嘲讽；仅技能文本明确否认的能力才剔除（逐实例显式标注为 `false`）。已确认示例：

- **Demiurge**（Cyrene 忆灵）：`av: false` + `enemy_targetable: false`——忆灵天赋 1141503 原文：SPD 恒为 0、不上行动条（Action Order）、在场视为界外（Out-of-Bounds）
- **Netherwing**（Pollux）：`enemy_targetable: false`，但有 AV（能否被我方治疗/护盾单点选中**待实测**）
- **小伊卡**（Hyacine 忆灵）：`av: false`——SPD=0，不出现在行动条上，只能通过额外回合行动

**忆灵离场条件**：
- 生命值归零
- 特定条件（如 Garmentmaker 倒计时、Pollux 回合限制）
- 离场后忆师需重新召唤

### 12.5 与自定义资源、形态状态机的关系

- 忆灵/召唤物可以有自己的 `custom_resources`（如风堇模板上的 `hyacine_cumulative_heal`——owner=actor，由小伊卡技能记账），见 `16_custom_resources.md`。
- 忆灵/召唤物也可以有 `actor_state` 和 `state_config`，用于表达形态切换，见 `17_actor_state.md`。
- 召唤物继承召唤者的 Layer 1 属性（不是 effective），避免 scaling 循环。详见 `04_modifier.md` §4.10。

---

