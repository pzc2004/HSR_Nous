## 1. 伤害公式 (Formula)

公式单独定义，参数从运行时状态读取。完整公式参见 `docs/mechanics/02_damage_formula.md`。

### 1.1 标准伤害公式

```yaml
formula:
  # 标准伤害（12 个乘区）
  damage:
    expression: "abilityMulti * dmgBoostMulti * indDmgBoostMulti * defMulti * resMulti * baseUniversalMulti * vulnMulti * indVulnMulti * finalDmgMulti * critMulti * weakenMulti * dmgRedMulti"

    parameters:
      # 1. 技能倍率乘区
      - name: abilityMulti
        source: skill_scaling  # 从技能倍率表读取

      # 2. 增伤乘区（DMG_BOOST）
      - name: dmgBoostMulti
        expression: "1 + dmg_bonus + all_dmg_bonus"

      # 3. 独立增伤乘区（独立于增伤）
      - name: indDmgBoostMulti
        expression: "1 + ind_dmg_bonus"

      # 4. 防御乘区（def_pen = 无视防御% + 防御降低%，defMulti 始终 <= 1）
      - name: defMulti
        expression: "(attacker_level * 10 + 200) / (target_def * max(0, 1 - def_pen) + attacker_level * 10 + 200)"

      # 5. 抗性乘区（先 clamp 有效抗性 [-1.0, 0.9]，再算乘区，范围 [0.1, 2.0]）
      - name: resMulti
        expression: "1 - clamp(target_res - res_pen, -1.0, 0.9)"

      # 6. 基础通用乘区（韧性状态：未击破 0.9 减伤，已击破 1.0 无减伤）
      - name: baseUniversalMulti
        expression: "target_toughness > 0 ? 0.9 : 1.0"

      # 7. 易伤乘区
      - name: vulnMulti
        expression: "1 + vulnerability"

      # 8. 独立易伤乘区
      - name: indVulnMulti
        expression: "1 + ind_vulnerability"

      # 9. 最终伤害乘区
      - name: finalDmgMulti
        expression: "1 + final_dmg_bonus"

      # 10. 暴击乘区（单次判定形式）
      # 期望形式：effective_crit_rate * (1 + crit_dmg) + (1 - effective_crit_rate)
      # effective_crit_rate = min(1, crit_rate + crit_rate_boost)
      # effective_crit_dmg = crit_dmg + crit_dmg_boost
      # crit_rate_boost/crit_dmg_boost 来自 modifier 的临时加成（如符玄技能、光锥特效）
      - name: critMulti
        expression: "is_crit ? (1 + crit_dmg) : 1.0"

      # 11. 虚弱乘区
      - name: weakenMulti
        expression: "1 - weaken"

      # 12. 减伤乘区（多个减伤源乘算：∏(1 - DMG_RED_i)）
      - name: dmgRedMulti
        expression: "1 - dmg_reduction"  # dmg_reduction 已预计算为乘积结果
```

### 1.2 期望伤害公式

用于理论计算（不模拟随机）：

```yaml
  damage_expected:
    expression: "abilityMulti * dmgBoostMulti * indDmgBoostMulti * defMulti * resMulti * baseUniversalMulti * vulnMulti * indVulnMulti * finalDmgMulti * critExpectedMulti * weakenMulti * dmgRedMulti"

    parameters:
      # 暴击使用期望值形式
      - name: critExpectedMulti
        expression: "effective_crit_rate * (1 + crit_dmg) + (1 - effective_crit_rate)"
      # ... 其他乘区同上
```

### 1.3 特殊伤害类型

```yaml
  # 真实伤害（无属性固定伤害，不受任何常规乘区影响）
  true_damage:
    expression: "fixed_value * true_dmg_rate * trueDmgMulti"
    description: "仅受真实伤害加成乘区影响，无视防御/抗性/增伤/暴击/易伤/减伤/虚弱等全部常规乘区"
    parameters:
      - name: trueDmgMulti
        expression: "1 + true_dmg_modifier + hit_true_dmg_modifier"
      - name: fixed_value
        source: fixed_value_source  # 固定数值来源
      - name: true_dmg_rate
        source: true_dmg_rate  # 技能中明确标注的真实伤害倍率

  # 击破伤害
  break_damage:
    expression: "breakBaseMulti * beMulti * baseUniversalMulti * defMulti * resMulti * vulnMulti * finalDmgMulti * weakenMulti * dmgRedMulti"
    parameters:
      - name: breakBaseMulti
        expression: "3767.5533 * elemental_break_scaling * (0.5 + max_toughness / 40) * special_scaling"
      - name: beMulti
        expression: "1 + break_effect"

  # 超击破伤害（不吃攻击、不吃增伤、不吃双暴）
  super_break_damage:
    expression: "baseUniversalMulti * defMulti * resMulti * vulnMulti * finalDmgMulti * superBreakBaseMulti * beMulti * superBreakModMulti * weakenMulti * dmgRedMulti"
    parameters:
      - name: superBreakBaseMulti
        expression: "(3767.5533 / 10) * effective_toughness"
      - name: effective_toughness
        expression: "toughness_dmg * (1 + break_efficiency_boost) * (1 + weakness_break_efficiency_boost) + fixed_toughness_dmg"
      - name: superBreakModMulti
        expression: "1 + super_break_modifier + extra_super_break_modifier"
      - name: beMulti
        expression: "1 + break_effect"

  # DOT 持续伤害（不吃双暴）
  dot_damage:
    expression: "abilityMulti * dmgBoostMulti * indDmgBoostMulti * defMulti * resMulti * baseUniversalMulti * vulnMulti * indVulnMulti * finalDmgMulti * weakenMulti * dmgRedMulti * ehrMulti * dot_tick_coefficient"
    parameters:
      - name: ehrMulti
        expression: "min(1, base_chance * (1 + effect_hit) * (1 - target_effect_res + effect_res_pen))"
      - name: dot_tick_coefficient
        source: dot_tick_coefficient  # 不同 DOT 类型不同

  # 欢愉伤害（不享受增伤，不受虚弱影响）
  # 基础伤害 = 等级系数 × 技能倍率（与击破类似，不基于角色属性）
  elation_damage:
    expression: "levelMultiplier * abilityMultiplier * origElationDmgMulti * critMulti * elation_multi * punchline_multi * merrymake_multi * defMulti * resMulti * vulnMulti * dmgMitigationMulti * baseUniversalMulti"
    parameters:
      - name: levelMultiplier
        source: elation_level_multiplier  # Lv.80 = 7535.1070
      - name: abilityMultiplier
        source: elation_ability_multiplier
      - name: elation_multi
        expression: "1 + elation_damage_bonus"
      - name: punchline_multi
        # 施放欢愉技时用 punchline，其他欢愉伤害用 certified_banger
        # 公式相同，数据来源不同
        expression: "1 + 5 * punchline_source / (punchline_source + 240)"
        # 收敛上限 6（+500%），等价形式：6 - 1200 / (punchline_source + 240)
      - name: merrymake_multi
        # 增笑：类似最终伤害的独立乘区，与好活当赏/笑点无关
        expression: "1 + merrymake"
      - name: origElationDmgMulti
        source: orig_elation_dmg_multi
      - name: dmgMitigationMulti
        expression: "1 - dmg_mitigation"

  # 治疗（heal_bonus = 施放者治疗加成，incoming_heal = 受治疗者受到治疗加成）
  heal:
    expression: "(atk_scaling * atk + hp_scaling * hp + flat_heal) * (1 + heal_bonus + incoming_heal)"

  # 护盾（可从 DEF/HP/ATK 缩放，shield_boost = 护盾 boost）
  shield:
    expression: "(def_scaling * def + hp_scaling * hp + atk_scaling * atk + flat_shield) * (1 + shield_bonus)"
```

### 1.4 属性击破效果

击破效果伤害通用框架：
```
breakEffectDmg = levelBase * effectMultiplier * (1 + BE) * vulnMulti * defMulti * resMulti * dmgRedMulti * weakenMulti
```

```yaml
break_effects:
  physical:  # 裂伤
    type: "dot"
    scaling: "min(enemy_type_coeff * target_hp, levelBase * toughness_unit * 2)"
    duration: 2
    description: "敌人类型系数：精英/首领 7%，普通 16%"

  fire:  # 灼烧
    type: "dot"
    effect_multiplier: 1.0  # 100%
    duration: 2

  ice:  # 冻结
    type: "control"
    effect_multiplier: 1.0  # 100% 附加伤害
    duration: 1
    action_value_penalty: 0.5  # 解冻后行动值为原行动值的 50%

  thunder:  # 触电
    type: "dot"
    effect_multiplier: 2.0  # 200%
    duration: 2

  wind:  # 风化
    type: "dot"
    effect_multiplier: 1.0  # 每层 100%
    duration: 2
    stacking: true  # 可叠加多层；精英怪被击破时直接叠加 3 层

  quantum:  # 纠缠（附加伤害）
    type: "control"
    damage: "level_multiplier * 0.6 * stack_count * (1 + break_effect) * (max_toughness / 10 + 2) / 4 * vuln * def * res * dmg_mitigation"
    # 纠缠倍率 60%，含韧性条上限乘区 (max_toughness/10+2)/4
    duration: 1
    action_value_delay: "0.2 * (1 + break_effect)"
    # 纠缠专属延后 20%×(1+BE)，另有击破通用延后 25%
    max_stacks: 5  # 击破时 1 层，每次受击 +1 层，最高 5 层
    # 单次弹射攻击无论命中几段都只算一次攻击

  imaginary:  # 禁锢（无伤害）
    type: "control"
    damage: null  # 禁锢不造成伤害
    duration: 1
    action_value_delay: "0.3 * (1 + break_effect)"
    # 禁锢专属延后 30%×(1+BE)，另有击破通用延后 25%
    speed_reduction: 0.1  # 减速 10%（可与其他减速叠加）
```

### 1.5 削韧值表

基础削韧值（按打击方式）：

| 打击方式 | 削韧值 | 示例 |
|---------|--------|------|
| 单体 (SingleAttack) | 10 | 普攻、单体战技 |
| 扩散 (Blast) | 10(主) + 5(扩散) | 普攻扩散、战技扩散 |
| 群体 (AoEAttack) | 10 | 群体战技、群体终结技 |
| 弹射 (Bounce) | 5×N | 弹射技能 |

**削韧效率公式**：
```
实际削韧 = 基础削韧 × (1 + breakEfficiencyBoost) × (1 + weaknessBreakEfficiencyBoost)
```

### 1.6 双击破机制

当削韧值 >= 剩余韧性时，触发双击破：
1. 先结算当前攻击的伤害
2. 再结算击破伤害
3. 如果是弱点击破，额外触发弱点击破效果

### 1.7 击破伤害属性倍率

击破伤害的 `elemental_break_scaling` 按属性不同：

| 属性 | 倍率 |
|------|------|
| 物理 | 200% |
| 火 | 200% |
| 风 | 150% |
| 冰 | 100% |
| 雷 | 100% |
| 量子 | 50% |
| 虚数 | 50% |

### 1.8 击破效果基础概率

所有击破效果的基础概率为 **150%**，受效果命中/抗性影响。

### 1.9 伤害类型 vs 乘区适用矩阵

| 乘区 | 直伤 | DOT | 击破 | 超击破 | 真实伤害 | 欢愉 |
|------|------|-----|------|--------|---------|------|
| abilityMulti | ✓ | ✓ | — | — | — | ✓ |
| dmgBoostMulti | ✓ | ✓ | — | — | — | — |
| indDmgBoostMulti | ✓ | ✓ | — | — | — | — |
| defMulti | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| resMulti | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| baseUniversalMulti | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| vulnMulti | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| indVulnMulti | ✓ | ✓ | — | — | — | — |
| finalDmgMulti | ✓ | ✓ | ✓ | ✓ | — | — |
| critMulti | ✓ | — | — | — | — | ✓ |
| weakenMulti | ✓ | ✓ | ✓ | ✓ | — | — |
| dmgRedMulti | ✓ | ✓ | ✓ | ✓ | — | — |
| trueDmgMulti | — | — | — | — | ✓ | ✓ |
| elationMulti | — | — | — | — | — | ✓ |
| punchlineMulti | — | — | — | — | — | ✓ |

### 1.10 DOT 分裂机制（dotSplit）

部分角色（如黑天鹅）的 DOT 具有分裂特性。当 `dotSplit > 0` 时，效果命中公式特殊处理：

```yaml
# 标准 ehrMulti（dotSplit = 0 时）
ehrMulti: "effective_dot_chance"
# effective_dot_chance = min(1, base_chance * (1 + effect_hit) * (1 - target_effect_res + effect_res_pen))

# dotSplit 模式（当 dotSplit > 0 时）
ehrMulti_split: "(1 + dotSplit * effective_dot_chance * (dot_stacks - 1)) / (1 + dotSplit * (dot_stacks - 1))"
```

其中 `effective_dot_chance` 为标准效果命中概率。

### 1.11 削韧值细分表

基础削韧值按技能类型和打击方式不同：

| 技能类型 | 单体 | 扩散（主/副） | 群体 | 弹射 |
|---------|------|-------------|------|------|
| 普攻 | 10 | 10/5 | — | 5×N |
| 战技 | 20 | 20/10 | 10 | 5×N |
| 终结技 | 30 | 30/20 | 20 | 5×N |

> 部分角色有特殊削韧值（如流萤强化普攻 15、战技 30；波提欧强化普攻 20）。
> 每次攻击的削韧值由 `Action.toughness_dmg` 字段定义，上表为通用默认值。

**设计意图**：
- 公式与机制解耦，想改公式只需改这里
- `expression` 用简单数学表达式，运行时求值
- `source` 指向运行时状态中的某个值
- 支持自定义新公式（如追加伤害、持续伤害等）
- 乘区定义与 `docs/mechanics/02_damage_formula.md` 完全对齐

---
