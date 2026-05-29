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
```

### 4.2 A/B 类 Buff 判定与结算

崩铁 buff 分为 A 类和 B 类，判定和结算时机不同：

| 类型 | 判定时机 | 结算时机 | 示例 |
|------|---------|---------|------|
| A 类 | 回合开始 或 行动进行 | 回合开始 或 回合结束 | 多数增伤 buff |
| B 类 | 行动进行 | 回合结束 | 部分 debuff |

**回合四阶段**：
1. 回合开始：A 类 buff 判定 + 结算
2. 行动准备：推拉条、冻结补偿
3. 行动进行：A/B 类 buff 判定
4. 回合结束：A/B 类 buff 结算、DOT 伤害

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
