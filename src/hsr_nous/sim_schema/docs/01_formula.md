## 1. 伤害公式 (Formula)

公式单独定义，参数从运行时状态读取。完整公式参见 `../../../../docs/mechanics/02_damage_formula.md`。

> **可执行唯一来源**：本章全部公式/乘区表达式的 rulebook 数据文件为 `../rulebook.yaml`（引擎结算实际消费它）；本章是同内容的文档镜像，两边逐字一致由 `tests/test_doc_lint.py` 镜像闸保证——改公式必须两边同步。

> **两层属性模型**：公式中使用的属性默认是 **effective（Layer 1 + Layer 2）**。但 scaling modifier 在计算 Layer 2 时，读的是 source actor 的 **Layer 1（base）**，避免二次转化循环。详见 `04_modifier.md` §4.10。

### 1.1 标准伤害公式

```yaml
formula:
  # 标准伤害（12 个乘区）
  damage:
    expression: "ability_multiplier * dmg_boost_multi * ind_dmg_boost_multi * def_multi * res_multi * base_universal_multi * vuln_multi * ind_vuln_multi * final_dmg_multi * crit_multi * weaken_multi * dmg_red_multi"

    parameters:
      # 1. 技能倍率乘区（基数区 = 倍率×基础属性 + Σbase_dmg_add）
      - name: ability_multiplier
        source: skill_scaling  # 技能倍率×基础属性（由 effect 的 amount 表达式喂入，见 05_effects.md deal_damage）；非纯倍率
        # base_dmg_add：附加基础伤害（加法注入基数区，可带 hit_condition 限定行动类别；如「这就是我啦！」终结技伤害值+防御力 60%）——决策卡 #17

      # 2. 增伤乘区（DMG_BOOST = 通用增伤 + 属性增伤 + 技能类型增伤）
      - name: dmg_boost_multi
        expression: "1 + (all_dmg_bonus + elemental_dmg_bonus + type_dmg_bonus)"
        # 括号分组钉死浮点结合序，与引擎结算实现逐比特一致（数学口径与 12 乘区表相同）
        # elemental_dmg_bonus 由当前伤害属性从 actor.dmg_bonus[element] 解析得到
        # type_dmg_bonus 按当前伤害的类别标签集合（主类别 action_type + 附加标签如 joint）从 actor.dmg_bonus_by_type 命中各档求和

      # 3. 独立增伤乘区（独立于增伤）
      - name: ind_dmg_boost_multi
        expression: "1 + ind_dmg_bonus"

      # 4. 防御乘区（def_pen = 无视防御% + 防御降低%，def_multi 始终 <= 1）
      - name: def_multi
        expression: "(attacker_level * 10 + 200) / (target_def * max(0, 1 - def_pen) + attacker_level * 10 + 200)"

      # 5. 抗性乘区（先 clamp 有效抗性 [-1.0, 0.9]，再算乘区，范围 [0.1, 2.0]）
      - name: res_multi
        expression: "1 - clamp(target_res - res_pen, -1.0, 0.9)"

      # 6. 基础通用乘区（韧性状态：未击破 0.9 减伤，已击破 1.0 无减伤）
      # 按 broken 旗标判定而非韧性读数——虚韧性条期间 toughness>0 但仍是击破态
      # （忘归人 122504 原文：主条破=击破，虚条破=再吃一次击破伤害，期间可超击破）
      - name: base_universal_multi
        expression: "target_broken > 0 ? 1.0 : 0.9"

      # 7. 易伤乘区
      - name: vuln_multi
        expression: "1 + vulnerability"

      # 8. 独立易伤乘区
      - name: ind_vuln_multi
        expression: "1 + ind_vulnerability"

      # 9. 最终伤害乘区
      - name: final_dmg_multi
        expression: "1 + final_dmg_bonus"

      # 10. 暴击乘区（单次判定形式）
      # 公式层写法：random() 判定；战斗日志/Hook 中已解析为 is_critical
      - name: crit_multi
        expression: "(random() < crit_rate) ? (1 + crit_dmg) : 1.0"

      # 11. 虚弱乘区
      - name: weaken_multi
        expression: "1 - weaken"

      # 12. 减伤乘区（多个减伤源乘算：∏(1 - DMG_RED_i)）
      - name: dmg_red_multi
        expression: "1 - dmg_reduction"  # dmg_reduction 已预计算为乘积结果
```

> **`split: even` 与公式层兼容**：`deal_damage` 声明 `split: even` 时，effect 层把 `amount` 总量按结算时存活目标数均分，再逐目标喂入 `ability_multiplier`——公式层**零改动**，各乘区仍逐目标独立求值（分配轴见 `05_effects.md` deal_damage）。
>
> 落地自决策卡 #16（2026-08-15）

### 1.2 期望伤害公式

用于理论计算（不模拟随机）：

```yaml
  damage_expected:
    expression: "ability_multiplier * dmg_boost_multi * ind_dmg_boost_multi * def_multi * res_multi * base_universal_multi * vuln_multi * ind_vuln_multi * final_dmg_multi * crit_expected_multi * weaken_multi * dmg_red_multi"

    parameters:
      # 暴击使用期望值形式
      - name: crit_expected_multi
        expression: "min(1, crit_rate) * (1 + crit_dmg) + (1 - min(1, crit_rate))"
      # ... 其他乘区同上
```

### 1.3 特殊伤害类型

```yaml
  # 真实伤害（无属性固定伤害，不受任何常规乘区影响）
  true_damage:
    expression: "fixed_value * true_dmg_rate * true_dmg_multi"
    description: "仅受真实伤害加成乘区影响，无视防御/抗性/增伤/暴击/易伤/减伤/虚弱等全部常规乘区；会被护盾抵挡（先扣护盾值，见 mechanics 02 §2.8）"
    parameters:
      - name: true_dmg_multi
        expression: "1 + true_dmg_modifier + hit_true_dmg_modifier"
      - name: fixed_value
        source: fixed_value_source  # 固定数值来源
      - name: true_dmg_rate
        source: true_dmg_rate  # 技能中明确标注的真实伤害倍率

  # 击破伤害
  break_damage:
    expression: "break_base_multi * be_multi * break_dmg_boost_multi * base_universal_multi * def_multi * res_multi * vuln_multi * final_dmg_multi * dmg_red_multi"
    parameters:
      - name: break_base_multi
        expression: "3767.5533 * elemental_break_scaling * (0.5 + max_toughness / 40) * special_scaling"
      - name: be_multi
        expression: "1 + break_effect"
      - name: break_dmg_boost_multi
        expression: "1 + break_dmg_boost"  # 击破伤害提高池（击破/超击破均生效，池内加算）

  # 超击破伤害（不吃攻击、不吃增伤、不吃双暴、不吃虚弱）
  super_break_damage:
    expression: "base_universal_multi * def_multi * res_multi * vuln_multi * final_dmg_multi * super_break_base_multi * be_multi * super_break_conversion_multi * break_dmg_boost_multi * super_break_dmg_boost_multi * dmg_red_multi"
    parameters:
      - name: super_break_base_multi
        expression: "(3767.5533 / 10) * effective_toughness"
      - name: effective_toughness
        expression: "toughness_dmg * (1 + break_efficiency_boost) * (1 + weakness_break_efficiency_boost) + fixed_toughness_dmg"
        # weakness_break_efficiency_boost 上限 300%（mechanics 02:360）
      - name: super_break_conversion_multi
        expression: "sum(super_break_modifier)"  # 转换倍率池（同谐主终结技/忘归人天赋/流萤行迹等），无转换源则为 0
      - name: break_dmg_boost_multi
        expression: "1 + break_dmg_boost"  # 击破伤害提高池（击破/超击破均生效）
      - name: super_break_dmg_boost_multi
        expression: "1 + super_break_dmg_boost"  # 超击破伤害提高池（仅超击破）；三个池两两乘算
      - name: be_multi
        expression: "1 + break_effect"

  # DOT 持续伤害（不吃双暴）
  dot_damage:
    expression: "ability_multiplier * dmg_boost_multi * ind_dmg_boost_multi * def_multi * res_multi * base_universal_multi * vuln_multi * ind_vuln_multi * final_dmg_multi * weaken_multi * dmg_red_multi * ehr_multi"
    parameters:
      - name: ehr_multi
        expression: "min(1, base_chance * (1 + effect_hit) * (1 - target_effect_res + effect_res_pen) * (1 - type_res))"
        # 命中公式全体 debuff 统一（与 04_modifier hit_chance 同式）；type_res 按 debuff_kind 取——
        # 当前内容仅控制类有实例（如莲华主控制抵抗），dot 类默认为 0；详见 03_actor.md type_res 字段
      # 注：卡芙卡类"手动引爆 DOT"按引爆技能给定的固定百分比单独结算（专属参数），不进入通用 dot_damage 公式

  # 欢愉伤害（不享受增伤，不受虚弱影响）
  # 基础伤害 = 等级系数 × 技能倍率（与击破类似，不基于角色属性）
  elation_damage:
    expression: "elation_level_multiplier * ability_multiplier * orig_elation_dmg_multi * elation_dmg_boost_multi * crit_multi * elation_multi * punchline_multi * merrymake_multi * def_multi * res_multi * vuln_multi * dmg_red_multi * base_universal_multi * final_dmg_multi"
    parameters:
      - name: elation_level_multiplier
        source: elation_level_multiplier  # Lv.80 = 7535.1070
      - name: ability_multiplier
        source: elation_ability_multiplier
      - name: elation_multi
        expression: "1 + elation"
      - name: punchline_multi
        # 施放欢愉技时用 punchline，其他欢愉伤害用 certified_banger
        # 公式相同，数据来源不同
        expression: "1 + 5 * punchline_source / (punchline_source + 240)"
        # 收敛上限 6（+500%），等价形式：6 - 1200 / (punchline_source + 240)
      - name: merrymake_multi
        # 增笑：类似最终伤害的独立乘区，与好活当赏/笑点无关
        # 公式层参数可直接引用运行时字段/资源（如 merrymake = $resource.merrymake）
        expression: "1 + merrymake"
      - name: orig_elation_dmg_multi
        source: orig_elation_dmg_multi
        # 欢愉技自身基础倍率（数据侧绑定）；⚠️ 勿填 fandom "Original Elation DMG Multiplier"（如爻光 E4 150%）——
        # 按 mechanics 02 §2.7 定槽规则该类效果归 final_dmg_multi 槽，填这里会双重计算
      - name: elation_dmg_boost_multi
        expression: "1 + elation_dmg_boost"  # 欢愉专属增伤区（池内加算；当前无实例，预留槽默认 1）
      - name: dmg_red_multi
        expression: "1 - dmg_reduction"

  # 治疗（heal_bonus = 施放者治疗加成，incoming_heal = 受治疗者受治疗量变化——加成为正、降低为负，如敌方萨姆领域）
  heal:
    expression: "(atk_scaling * atk + hp_scaling * hp + flat_heal) * (1 + heal_bonus + incoming_heal)"

  # 护盾（可从 DEF/HP/ATK 缩放，shield_boost = 护盾 boost）
  shield:
    expression: "(def_scaling * def + hp_scaling * hp + atk_scaling * atk + flat_shield) * (1 + shield_bonus)"
```

### 1.4 属性击破效果

击破效果伤害通用框架：
```
break_effect_dmg = level_base * effect_multiplier * (1 + BE) * vuln_multi * def_multi * res_multi * final_dmg_multi * base_universal_multi * dmg_red_multi
```

```yaml
# 注：本表三种伤害字段并存——dot 类用 `effect_multiplier`（倍率，走通用框架；ice 虽 type:control 也用此字段）；裂伤用 `scaling`（含 cap 的完整表达式）；
# 量子/虚数用 `damage`（完整表达式或 null）。`scaling` 是击破效果表专用字段（该击破效果的 DoT 伤害表达式），
# 与 effect 的数值字段 amount 不同义（旧 effect 字段 scaling 已废弃，见 05_effects.md）。
# 裂伤特例：`scaling` 的 min 结果**整体替代**通用框架的 `level_base * effect_multiplier`（cap 项自带 level_base，不再重复乘），
# 其后照常乘 vuln/def/res/final/base_universal/dmg_red（与 mechanics 02:300 注一致）。
break_effects:
  physical:  # 裂伤
    type: "dot"
    scaling: "min(enemy_type_coeff * target_hp, 2 * level_base * (0.5 + max_toughness / 40))"
    # 裂伤 cap 在基数层比较（fandom "max cap for Bleed Base DMG"；有实测支持：米游社 58632087 封顶区裂伤仍随击破特攻/减防/易伤变化）；紫喵把乘区放进 min 的写法与此矛盾，疑为行文不严谨
    duration: 2
    description: "敌人类型系数：精英/首领 7%，普通 16%"

  fire:  # 灼烧
    type: "dot"
    effect_multiplier: 1.0  # 100%
    duration: 2

  ice:  # 冻结
    type: "control"
    effect_multiplier: 1.0  # 100% 击破附加伤害
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
    stacking: true  # 可叠加（最高 5 层）；精英/首领被击破时直接叠加 3 层

  quantum:  # 纠缠（击破附加伤害）
    type: "control"
    damage: "level_base * 0.6 * stack_count * (1 + break_effect) * (max_toughness / 10 + 2) / 4 * vuln_multi * def_multi * res_multi * final_dmg_multi * base_universal_multi * dmg_red_multi"
    # 纠缠倍率 60%，含韧性条上限乘区 (max_toughness/10+2)/4
    # 纠缠属击破效果伤害，不吃虚弱（fandom Weaken/Toughness、hsr-optimizer、紫喵入坑指南07 一致）
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

裂伤基数区的可执行锚（引擎 `bleed_tick` 实际消费；`level_base` 按 break_base_multi 同例内联为等级 80 常数 3767.5533；敌类型系数 elite 7% / normal 16% 数据在 `rulebook.yaml` `break_effects.physical.bleed_coeff`）：

```yaml
# 裂伤 DoT（物理击破效果，非顶层公式——无独立 route，基数区经 bleed_tick 消费）
bleed_dot:
  parameters:
    - name: bleed_base_multi
      expression: "min(enemy_type_coeff * target_hp, 2 * 3767.5533 * (0.5 + max_toughness / 40))"
```

### 1.5 削韧值表

基础削韧值（按打击方式）：

| 打击方式 | 削韧值 | 示例 |
|---------|--------|------|
| 单体 (SingleAttack) | 10 | 普攻 |
| 扩散 (Blast) | 20(主) + 10(邻) | 强化普攻扩散（刃基线；饮月特例 30/10、40/20） |
| 群体 (AoEAttack) | 10 | 群体战技 |
| 群体终结技 (AoEAttack) | 20 | 群体终结技 |
| 终结技扩散 (Blast) | 20(主) + 20(邻) | 饮月/Mydei 终结技 |
| 弹射 (Bounce) | 5×N | 弹射技能 |

**削韧效率公式**：

**削韧闸门**（前置）：攻击属性不满足 `toughness_scope`（`03_actor.md` §3.4）时 `toughness_dmg` 记 0（`fixed_toughness_dmg` 一并记 0）；满足后按下式结算。

```yaml
toughness_damage:
  expression: "base_toughness * (1 + break_efficiency_boost) * (1 + weakness_break_efficiency_boost) + fixed_toughness_dmg"
  # 实际削韧 = 基础削韧 × (1 + break_efficiency_boost) × (1 + weakness_break_efficiency_boost) + fixed_toughness_dmg
```
（`fixed_toughness_dmg` 为固定削韧值，不受效率加成影响；与 §1.3 超击破 `effective_toughness` 同出处）

### 1.6 击破结算顺序

当削韧值 >= 剩余韧性时触发击破，任意击破均按以下顺序结算（本节与 `../../../../docs/mechanics/04_break_system.md` 的"双击破"——同次攻击多段伤害先后触发击破+超击破——**非同概念**）：
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
| ability_multiplier | ✓ | ✓ | — | — | — | ✓ |
| be_multi | — | — | ✓ | ✓ | — | — |
| ehr_multi | — | ✓ | — | — | — | — |
| dmg_boost_multi | ✓ | ✓ | — | — | — | — |
| ind_dmg_boost_multi | ✓ | ✓ | — | — | — | — |
| def_multi | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| res_multi | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| base_universal_multi | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| vuln_multi | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| ind_vuln_multi | ✓ | ✓ | — | — | — | — |
| final_dmg_multi | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| break_dmg_boost_multi | — | — | ✓ | ✓ | — | — |
| super_break_dmg_boost_multi | — | — | — | ✓ | — | — |
| crit_multi | ✓ | — | — | — | — | ✓ |
| weaken_multi | ✓ | ✓ | — | — | — | — |
| dmg_red_multi | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| true_dmg_multi | — | — | — | — | ✓ | — |
| orig_elation_dmg_multi | — | — | — | — | — | ✓ |
| elation_dmg_boost_multi | — | — | — | — | — | ✓ |
| merrymake_multi | — | — | — | — | — | ✓ |
| elation_multi | — | — | — | — | — | ✓ |
| punchline_multi | — | — | — | — | — | ✓ |

> 注：本矩阵"击破"列指一击击破（`break_damage`）；击破效果中的持续伤害类（裂伤/灼烧/触电/风化）走 §1.4 框架与 `02_damage_formula.md` 2.12 表，纠缠/冻结等击破附加伤害走 §2.10 框架——口径均不同（无击破增伤区、无增伤区、有韧性减伤区）。

### 1.10 DOT 分裂机制（dot_split）

部分角色（如黑天鹅）的 DOT 具有分裂特性。当 `dot_split > 0` 时，效果命中公式特殊处理：

```yaml
# 标准 ehr_multi（dot_split = 0 时）
ehr_multi: "effective_dot_chance"
# effective_dot_chance = min(1, base_chance * (1 + effect_hit) * (1 - target_effect_res + effect_res_pen) * (1 - type_res))
# 与 04_modifier hit_chance 同式；type_res 按 debuff_kind 取，dot 类当前默认为 0

# dot_split 模式（当 dot_split > 0 时）
ehr_multi_split: "(1 + dot_split * effective_dot_chance * (dot_stacks - 1)) / (1 + dot_split * (dot_stacks - 1))"
```

其中 `effective_dot_chance` 为标准效果命中概率。

### 1.11 削韧值细分表

基础削韧值按技能类型和打击方式不同：

| 技能类型 | 单体 | 扩散（主/副） | 群体 | 弹射 |
|---------|------|-------------|------|------|
| 普攻 | 10 | 20/10（强化普攻，如刃；饮月特例 30/10、40/20） | — | 5×N |
| 战技 | 20 | 20/10 | 10 | 5×N |
| 终结技 | 30 | 20/20 | 20 | 5×N |

> 部分角色有特殊削韧值（如流萤强化普攻 15、战技 30；波提欧强化普攻 20）。
> 每次攻击的削韧值由 `Action.toughness_dmg` 字段定义，上表为通用默认值。
> 此表（含 §1.5）为**通用缺省值 + 分类基准**；逐技能削韧数值以 fandom Toughness/Data（社区逐技能实测表）为准，冲突时实测覆盖。

**设计意图**：
- 公式与机制解耦，想改公式只需改这里
- `expression` 用简单数学表达式，运行时求值
- `source` 指向运行时状态中的某个值
- 支持自定义新公式（如追加伤害、持续伤害等）
- 乘区定义与 `../../../../docs/mechanics/02_damage_formula.md` 完全对齐

---
