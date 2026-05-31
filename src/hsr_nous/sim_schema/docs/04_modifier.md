## 4. Buff / Modifier 定义

Buff 是核心机制，所有持续效果都用它表达。

### 4.1 Modifier 结构

```yaml
modifier:
  modifier_id: "MOD_1001_SHIELD"
  name: "护盾"
  modifier_type: "shield"       # buff | debuff | dot | shield | heal | control
  max_stack: 1
  duration: 3                    # 持续回合数，0 为永久
  stack_mode: "refresh"          # 独立计时 | refresh | replace
  dispellable: true              # 是否可驱散

  # 触发时机和效果
  on_apply:
    - effect_type: "add_stat"
      stat: "shield"
      value: "base_stats.def * 0.48 + 640"

  on_turn_start:                 # 回合开始时
    - effect_type: "none"        # 护盾回合开始时无效果

  on_expire:
    - effect_type: "remove_stat"
      stat: "shield"

  # 如果是 dot：
  on_turn_start:
    - effect_type: "deal_damage"
      formula: "damage"
      damage_type: "fire"
      scaling: 0.5

  # 如果是 debuff（减防）：
  on_apply:
    - effect_type: "add_stat"
      stat: "def_reduction"
      value: 0.3                  # 减防 30%

  # 指向性增伤（如刻律德菈战技：使指定目标战技暴伤+X%、战技全属性抗性穿透+Y%）
  # 通过 apply_modifier 施加到目标身上，modifier 内部 add_stat 即可
  # 注意：暴伤和抗性穿透仅作用于战技伤害，不是全局加成
  # MOD_KAFKA_TARGET_BUFF:
  #   on_apply:
  #     - effect_type: "add_stat"
  #       stat: "skill_crit_dmg"       # 仅战技暴伤
  #       value: 0.30
  #     - effect_type: "add_stat"
  #       stat: "skill_all_res_pen"    # 仅战技全属性抗性穿透
  #       value: 0.20
```

### 4.2 星魂/行迹修改技能参数

星魂和行迹可以通过 `override_action_param` 或 `append_action_param` 修改技能的倍率参数：

```yaml
# 万敌 E1：战技弑神登神主目标倍率 +30%
- trigger: "on_battle_start"
  effect_type: "override_action_param"
  action_id: "120502"            # 战技 ID
  param_index: 0                 # params[level][0] = 主目标倍率
  value_offset: 0.30             # 在原值基础上 +0.30
  condition: "eidolon >= 1"

# 爻光 E1：终结技触发的额外阿哈时刻笑点变为 40
- trigger: "on_aha_instant_start"
  effect_type: "override_action_param"
  action_id: "100103"            # 终结技 ID
  param_index: 2                 # params[level][2] = 笑点参数
  value: 40                      # 直接覆盖为 40
  condition: "eidolon >= 1"
```

详见 [05_effects.md](05_effects.md) 中的 `override_action_param` 和 `append_action_param`。

### 4.3 A/B 类 Buff 判定与结算

崩铁 buff 分为 A 类和 B 类，判定和结算时机不同：

| 类型 | 判定时机 | 结算时机 | 来源 |
|------|---------|---------|------|
| A 类 | 判定A(回合开始) 或 判定B(行动进行) | 结算1(回合开始) 或 结算2(回合结束) | DOT、冻结/纠缠/禁锢、遗器/光锥/技能产生的 buff |
| B 类 | 判定B(行动进行) | 结算2(回合结束) | 部分终结技产生的 buff |

**回合四阶段**：
1. **回合开始**：判定A + 结算1（DOT 和控制效果在此结算）
2. **行动准备**：推拉条、冻结补偿
3. **行动进行**：判定B（A/B 类 buff 均可在此判定）
4. **回合结束**：结算2（除 DOT 外的计时状态在此结算）

> 部分永久状态（如火主"灼烧意志"）**不受回合结算影响**，持续到特定移除条件。

**击破状态 + 控制效果交互**：
- 冻结/纠缠/禁锢在敌人回合开始时结算
- 结算后敌人仍处于击破状态（韧性 = 0），直到真正行动
- 此期间无法再次削韧

### 4.3 叠加模式

```yaml
stack_mode: "refresh"  # 默认

# 独立计时：每层独立计算持续时间
# 示例：风化 DOT，每层独立倒计时

# refresh：刷新持续时间
# 示例：多数 buff，重复施加时刷新持续时间

# replace：替换
# 示例：护盾，新护盾替换旧护盾
```

### 4.4 驱散规则

```yaml
dispellable: true       # 可驱散（默认）
dispellable: false      # 不可驱散（如控制效果）

# 驱散顺序：LIFO（后进先出）
# 净化顺序：LIFO（后进先出）
```

> 净化**不会优先解除控制效果**——控制类 debuff 和其他 debuff 同等对待。

### 4.5 效果命中公式

```yaml
# 实际命中概率
hit_chance: "min(1, base_chance * (1 + effect_hit) * (1 - target_effect_res + effect_res_pen) * (1 - type_res))"
```

### 4.6 Buff 触发时机清单

| 触发时机 | 说明 |
|---------|------|
| `on_battle_start` | 战斗开始时 |
| `on_wave_start` | 波次开始时 |
| `on_cycle_start` | 轮次开始时 |
| `on_cycle_end` | 轮次结束时 |
| `on_turn_start` | 携带者回合开始时 |
| `on_turn_end` | 携带者回合结束时 |
| `on_before_action` | 行动前（用于增伤 buff） |
| `on_after_action` | 行动后 |
| `on_before_hit` | 造成伤害前 |
| `on_after_hit` | 造成伤害后 |
| `on_being_hit` | 受击时 |
| `on_being_targeted` | 被选为目标时（嘲讽用） |
| `on_kill` | 击杀敌人时 |
| `on_ally_kill` | 队友击杀时 |
| `on_hp_change` | 生命值变化时 |
| `on_break` | 击破韧性时 |
| `on_weakness_break` | 造成弱点击破时 |
| `on_energy_full` | 能量满时（用于自动开大） |
| `on_death` | 死亡时 |

---
