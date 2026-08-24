# 伤害公式


### 2.1 基础伤害（Ability Multiplier）

```
伤害 = 技能倍率(abilityMultiplier) × 增伤(dmgBoostMulti) × 独立增伤(indDmgBoostMulti) × 防御(defMulti) × 抗性(resMulti)
      × 韧性减伤(baseUniversalMulti) × 易伤(vulnMulti) × 独立易伤(indVulnMulti) × 最终伤害(finalDmgMulti)
      × 暴击(critMulti) × 虚弱(weakenMulti) × 减伤(dmgRedMulti)
```

| 乘区 | 公式 |
|------|------|
| abilityMultiplier | 技能倍率 × 基础属性 |
| dmgBoostMulti | 1 + 增伤 + 属性增伤 + 技能类型增伤（见 2.5） |
| indDmgBoostMulti | 1 + 独立增伤 |
| defMulti | (攻击者等级 + 20) / ((敌人等级 + 20) × max(0, 1 - DEF_PEN) + (攻击者等级 + 20)) |
| resMulti | 1 - effectiveResistance（见 2.3） |
| baseUniversalMulti | 1.0（已击破）/ 0.9（未击破） |
| vulnMulti | 1 + 易伤 |
| indVulnMulti | 1 + 独立易伤 |
| finalDmgMulti | 1 + 最终伤害加成 |
| critMulti | 有效暴击率 × (1 + 有效暴击伤害) + (1 - 有效暴击率) |
| weakenMulti | 1 - WEAKEN（见 2.7） |
| dmgRedMulti | ∏(1 - DMG_RED)（见 2.7） |

#### 基础属性

```
技能倍率(abilityMultiplier) = 攻击倍率(atkScaling) × 攻击力(ATK) + 生命倍率(hpScaling) × 生命值(HP) + 防御倍率(defScaling) × 防御力(DEF) + 附加基础伤害(baseDmgAdd)
```

基础属性取值：
- `ATK`：攻击力
- `HP`：生命值
- `DEF`：防御力
- `baseDmgAdd`：附加基础伤害（加法注入基数区，可带行动类别限定；如光锥「这就是我啦！」：终结技伤害值提高 = 防御力 60%）（决策卡 #17）

特殊 scaling：
- **BE scaling**：`atkScaling + beScaling × min(beCap, BE)`（击破特攻转攻击力，如流萤）

#### 伤害类型与乘区生效关系

| 伤害类型 | 生效乘区 | 不生效乘区 |
|---------|---------|-----------|
| 直伤（普攻/战技/终结技/追加攻击/角色附加伤害）| 2.1 全部常规乘区（角色附加伤害另注：不吃类型限定增伤——如 `follow_up_dmg_boost` 等，除非效果特别注明；fandom Additional DMG 页明载） | 无 |
| 常规持续伤害（DOT）| 2.1 常规乘区（除双暴区）+ 效果命中区(ehrMulti)（期望值建模层，fandom 无此概念——EHR 在 fandom 只影响施加概率不进伤害式） | 双暴区、击破特攻区、击破增伤区、超击破增伤区 |
| 击破伤害 | 基础击破伤害、击破特攻、韧性系数、击破增伤、最终伤害、防御、易伤、减伤、抗性、韧性减伤 | 双暴、增伤、独立增伤、独立易伤、虚弱 |
| 超击破伤害 | 超击破基数、击破特攻、削韧、超击破转换倍率、击破增伤、超击破增伤、最终伤害、防御、易伤、减伤、抗性、韧性减伤 | 双暴、增伤、独立增伤、独立易伤、虚弱 |
| 真实伤害 | 仅真实伤害(trueDmgMulti) | 防御、抗性、增伤、暴伤、易伤、减伤、虚弱等全部常规乘区 |
| 欢愉伤害 | 等级系数、技能倍率、欢愉度、原始欢愉伤害倍率、欢愉增伤区(elationDmgBoostMulti)、笑点/好活当赏、增笑、双暴、防御、抗性、易伤、减伤、韧性减伤、最终伤害 | 通用增伤(dmgBoostMulti)、独立增伤、独立易伤、虚弱 |

> 击破伤害与超击破伤害**均不吃增伤**（包括通用增伤和属性增伤）。

### 2.2 防御乘区

```
防御(defMulti) = (攻击者等级(attackerLevel) + 20) / ((敌人等级(enemyLevel) + 20) × max(0, 1 - 防御穿透(DEF_PEN)) + (攻击者等级(attackerLevel) + 20))
```

等价形式（基于 `敌人防御(enemyDEF) = 200 + 10 × 敌人等级(enemyLevel)`）：

```
防御(defMulti) = 1 - (敌人防御(enemyDEF) × max(0, 1 - 防御穿透(DEF_PEN)) / (敌人防御(enemyDEF) × max(0, 1 - 防御穿透(DEF_PEN)) + 200 + 10 × 攻击者等级(attackerLevel)))
敌人防御(enemyDEF) = 200 + 10 × 敌人等级(enemyLevel)
```

其中 `DEF_PEN` 为防御穿透，由以下部分构成：

```
防御穿透(DEF_PEN) = ∑攻击方无视防御% + ∑受击方防御降低%
```

- **无视防御**：攻击方属性（如光锥、行迹、星魂等提供的无视防御）
- **防御降低**：施加给敌方的 debuff（如银狼终结技、佩拉战技等）

> 防御力最低为 **0**，无法变成负数，防御乘区收益存在上限。

#### 防御乘区收益特性

防御区本质上是敌人的**减伤区**，`defMulti` 始终 ≤ 1（即无法超过 100% 基础伤害）。减防与无视防御的作用是将 `defMulti` 向 1 靠近，因此这是一个**有上限的增益乘区**。

以下数据基于**攻击方 80 级 + 受击方 95 级**（当前混沌回忆常用等级）：

| 特性 | 说明 |
|------|------|
| 每 1% 减防/无视防御收益范围 | 约 **0.538% ~ 1.150%** |
| 边际收益趋势 | 减防/无视防御数额越高，每 1% 的收益越高 |
| 87% 阈值 | 当总减防/无视防御达到 **87%** 时，实际提升率与 BUFF 总数值一致；低于 87% 时实际提升率**低于** BUFF 数值，高于 87% 时**高于** BUFF 数值 |

> 若游戏后续提高等级上限或敌人等级，上述具体数值会变化，需重新计算。核心结论（有上限、边际递增）不变。

### 2.3 抗性乘区

```
抗性(resMulti) = 1 - 有效抗性(effectiveResistance)
```

其中：
- `enemyResistance` 为目标当前抗性
- `RES_PEN` 为抗性穿透（含抗性降低）
- `effectiveResistance = clamp(enemyResistance - RES_PEN, -1.0, 0.9)`

#### 怪物基础抗性

| 属性关系 | 基础抗性 |
|---------|---------|
| 弱点属性 | 0% |
| 非弱点属性 | 20% |

> 怪物对非弱点属性的 20% 基础抗性不会显示在怪物面板中。

#### 抗性上下限

- 抗性上限 **90%**：超过 90% 后仍按 90% 计算
- 抗性下限 **-100%**：超额穿透后 `resMulti` 最高为 **2.0**

抗性乘区取值范围为 **[0.1, 2.0]**。

### 2.4 韧性减伤乘区（Base Universal Multiplier）

```
韧性减伤(baseUniversalMulti) = 1.0  （目标已击破）
韧性减伤(baseUniversalMulti) = 0.9  （目标未击破）
```

> 注：崩铁中未击破敌人统一受到 10% 伤害减免，击破后无减免。

### 2.5 增伤乘区

```
增伤(dmgBoostMulti) = 1 + 通用增伤(DMG_BOOST) + 属性增伤(elementalDmgBoost) + 技能类型增伤(typeDmgBoost)
独立增伤(indDmgBoostMulti) = 1 + 独立增伤(INDEPENDENT_DMG_BOOST)
```

- `DMG_BOOST`：通用增伤（如停云战技、某些光锥特效等）
- `elementalDmgBoost`：对应属性增伤（如属性球、`PHYSICAL_DMG_BOOST`、`FIRE_DMG_BOOST` 等）
- `typeDmgBoost`：按技能类型增伤，根据当前施放的技能类型取值：
  - `basic_dmg_boost`：普攻增伤
  - `skill_dmg_boost`：战技增伤
  - `ult_dmg_boost`：终结技增伤
  - `follow_up_dmg_boost`：追加攻击增伤
  - `dot_dmg_boost`：DOT 增伤
- `INDEPENDENT_DMG_BOOST`：独立增伤（如部分命途机制、特殊 buff 等）

**类型专属增伤区（独立成池，不进 dmgBoostMulti）**：

- `breakDmgBoostMulti`：击破增伤区（见 2.10，"击破伤害提高"类专属增益，击破与超击破均生效）
- `elationDmgBoostMulti`：欢愉增伤区（`1 + Σ 欢愉伤害提高`，池内加算；欢愉伤害不吃通用增伤，此类增伤独立成池。当前游戏内尚无实例，预留槽默认 1）

> 示例：遗器"使装备者追加攻击伤害提高 20%"→ `follow_up_dmg_boost += 0.20`，加算进 `dmgBoostMulti`。
> 示例：刻律德菈战技"使指定目标战技暴伤+X%、战技全属性抗性穿透+Y%"→ 对目标施加 modifier，`skill_crit_dmg` 和 `skill_all_res_pen` 仅作用于战技伤害。
> 示例：万敌 E1"战技弑神登神主目标倍率+30%"→ `append_action_param` 在 params[0] 原值上加算。
> 示例：爻光 E1"终结技触发的额外阿哈时刻笑点变为 40"→ `override_action_param` 覆盖 params[3] 为 40。

独立增伤区与普通增伤区**乘算**：

```
总增伤(totalDmgBoost) = 增伤(dmgBoostMulti) × 独立增伤(indDmgBoostMulti)
```

> 独立增伤不受常规增伤稀释影响，为独立乘区。

### 2.6 易伤乘区

```
易伤(vulnMulti) = 1 + 易伤(VULNERABILITY)
独立易伤(indVulnMulti) = 1 + 独立易伤(INDEPENDENT_VULNERABILITY)
```

- `VULNERABILITY`：常规易伤加成（如姬子秘技、桑博终结技等）
- `INDEPENDENT_VULNERABILITY`：独立易伤（如部分特殊机制提供的易伤）

独立易伤区与普通易伤区**乘算**：

```
总易伤(totalVuln) = 易伤(vulnMulti) × 独立易伤(indVulnMulti)
```

> 独立易伤不受常规易伤稀释影响，为独立乘区。

### 2.7 最终伤害乘区

```
最终伤害(finalDmgMulti) = 1 + 最终伤害加成(FINAL_DMG_BOOST)
```

`FINAL_DMG_BOOST` 为最终伤害加成，在所有其他乘区之后独立计算。

> **定槽规则（文本家族，owner 裁决 2026-07-21）**：技能文本"（造成的）伤害**为原伤害的 X%**"（修饰已有伤害的倍数）一律归本槽（如黄泉行迹「奈落」115%/160%、爻光 E4 欢愉技 150%）；"倍率提高/倍率+X%/×X"归对应倍率区；"额外造成/立即产生"（新 hit 实例——姬子 E6 类额外伤害、卡芙卡类引爆、昔涟/迷迷真实伤害）**不进乘区**。fandom 公式把这类效果称 **Original DMG Multiplier**（欢愉类称 Original Elation DMG Multiplier，命名不同、与本槽同物）；字面"最终伤害提高"仅见于 2.6+ 的游戏模式 buff（模拟宇宙/差分宇宙/异相仲裁）。角色侧"原伤害%"与模式 buff"最终伤害提高"**同池加算属推断，待实测**（fandom 各伤害公式页均未列 Final DMG 乘区；保留本槽的依据 = 模式 buff 作为全局 stat 应对全部伤害类型生效的外推，optimizer 同构）。

#### 虚弱区与减伤区（补充乘区）

```
虚弱(weakenMulti) = 1 - 虚弱(WEAKEN)
减伤(dmgRedMulti) = ∏(1 - 伤害减免(DMG_RED))
```

- `WEAKEN`：我方受到的伤害降低效果（如敌方施加的虚弱 debuff）
- `DMG_RED`：敌方伤害减免效果（乘算）

> 注：部分简化计算场景可能将虚弱与减伤合并处理。

### 2.8 真实伤害与真伤乘区

#### 真实伤害的定义

真实伤害是一种**无属性固定伤害**，具有以下特性：

| 特性 | 说明 |
|------|------|
| 无属性 | 不享受任何属性克制关系，不受敌人抗性乘区影响 |
| 无攻击判定 | 不会触发需要攻击判定才能激活的效果 |
| 不受常规乘区影响 | **不享受**增伤、暴伤、易伤、防御穿透、减伤、虚弱等**任何**常规乘区加成 |

#### 真实伤害计算公式

```
真实伤害 = 固定数值来源 × 真实伤害倍率 × 真实伤害加成(trueDmgMulti)
```

- **固定数值来源**：根据机制描述替换，如"原伤害"、"目标生命值上限"等
- **真实伤害倍率**：技能/效果中明确标注的百分比
- `trueDmgMulti`：真实伤害加成乘区

```
真实伤害加成乘区(trueDmgMulti) = 1 + 角色真实伤害加成(TRUE_DMG_MODIFIER) + 攻击真实伤害加成(hitTrueDmgModifier)
```

- `TRUE_DMG_MODIFIER`：角色身上的真实伤害加成值
- `hitTrueDmgModifier`：本次攻击附带的额外真实伤害加成值

#### 常见场景

1. **基于原伤害的比例真实伤害**：额外造成等同于原伤害 N% 的真实伤害
2. **基于固定数值的真实伤害**：额外造成等同于某数值（如目标生命值上限）N% 的真实伤害

#### 补充规则

- **来源间关系**：多个真实伤害**加成**来源同属一个乘区，互相**加算**（会互相稀释），不会互相增幅
- **护盾抵挡**：真实伤害会被护盾抵挡（紫喵 11 置顶原话；机理展开：护盾先吸收伤害，不破盾不伤本体——护盾非乘区，属伤害结算后的吸收层，与"不受减伤乘区影响"不冲突）

> 真实伤害的基础值跳过所有常规伤害乘区，仅受专属的真实伤害加成乘区影响。

### 2.9 暴击乘区

```
有效暴击率(effectiveCR) = min(1, 暴击率(CR) + 暴击率加成(CR_BOOST))
有效暴击伤害(effectiveCD) = 暴击伤害(CD) + 暴击伤害加成(CD_BOOST)
暴击(critMulti) = 有效暴击率(effectiveCR) × (1 + 有效暴击伤害(effectiveCD)) + (1 - 有效暴击率(effectiveCR))
```

- `CR`：面板暴击率
- `CR_BOOST`：临时暴击率加成（如符玄战技、某些光锥效果）
- `CD`：面板暴击伤害
- `CD_BOOST`：临时暴击伤害加成

> 暴击率上限为 100%（`min(1, ...)`），超过部分无收益。

### 2.10 击破伤害

```
击破伤害(breakDmg) = 韧性减伤(baseUniversalMulti) × 防御(defMulti) × 抗性(resMulti) × 易伤(vulnMulti) × 最终伤害(finalDmgMulti)
         × 击破基数(breakBaseMulti) × 击破特攻区(beMulti) × 击破增伤区(breakDmgBoostMulti) × 减伤(dmgRedMulti)

击破基数(breakBaseMulti) = 3767.5533 × 属性击破倍率(elementalBreakScaling) × (0.5 + 最大韧性(maxToughness) / 40) × 特殊倍率(specialScaling)
击破特攻区(beMulti) = 1 + 击破特攻(BE)
击破增伤区(breakDmgBoostMulti) = 1 + Σ 击破伤害提高（"击破伤害提高"类专属增益，如忘归人 E4、部分光锥；击破与超击破均生效，池内加算）
```

其中：
- `3767.5533` 为等级 80 基础击破伤害常数（已包含等级系数）
- `elementalBreakScaling` 为属性击破倍率，见下表
- `maxToughness` 为敌人最大韧性值
- `specialScaling` 为特殊倍率修正（如特定角色/命途）
- `BE` 为击破特攻

#### 属性击破倍率

| 属性 | 击破倍率 |
|------|---------|
| 物理 | 200% |
| 火 | 200% |
| 风 | 150% |
| 冰 | 100% |
| 雷 | 100% |
| 量子 | 50% |
| 虚数 | 50% |

> 击破伤害**不吃增伤**（包括通用增伤和属性增伤），但吃"击破伤害提高"类专属增益（见 `breakDmgBoostMulti`）。

#### 各属性击破效果

击破效果伤害公式通用框架：

```
击破效果伤害(breakEffectDmg) = 等级基数(levelBase) × 效果倍率(effectMultiplier) × (1 + 击破特攻(BE)) × 易伤(vulnMulti) × 防御(defMulti) × 抗性(resMulti)
               × 最终伤害(finalDmgMulti) × 韧性减伤(baseUniversalMulti) × 减伤(dmgRedMulti)
```

> 注：裂伤的"等级基数 × 效果倍率"由 min 结果整体担任（cap 项自带 levelBase，不再重复乘，见下表裂伤行）；其余效果 `effectMultiplier` 为常数倍率。

| 属性 | 击破效果 | 效果倍率 | 特殊机制 |
|------|---------|---------|---------|
| 物理 | 裂伤 | Min(敌人类型系数×HP, 2 × levelBase × 韧性系数(0.5+最大韧性/40)) | 持续伤害，敌人类型系数：精英/首领 7%，普通 16% |
| 火 | 灼烧 | 100% | 持续伤害 |
| 冰 | 冻结 | 100% | 击破附加伤害；冻结恢复后下一轮行动值为原行动值的 50% |
| 雷 | 触电 | 200% | 持续伤害 |
| 风 | 风化 | 每层 100% | 持续伤害，可叠加（最高 5 层）；精英/首领被击破时直接叠加 3 层；风化状态下被击破可叠加并重置回合 |
| 量子 | 纠缠 | 60% × 层数 × (最大韧性/10+2)/4 | 击破附加伤害，额外行动延后 20%×(1+BE) |
| 虚数 | 禁锢 | 无伤害 | 额外行动延后 30%×(1+BE)，减速 10%（可与其他减速叠加） |

> 量子/虚数的行动延后是在击破通用 25% 基础上的额外延后。
>
> 裂伤 cap 在**基数层**比较（fandom 原文 "max cap for Bleed Base DMG"）——min 取完再乘 (1+击破特攻)/防御/抗性/易伤/最终伤害/韧性减伤/减伤。**有实测支持**（米游社 58632087：差分宇宙高血量环境必处封顶区，裂伤仍随击破特攻/减防/易伤/抗性穿透变化，排除"终值固定 cap"）；紫喵把乘区放进 min 第二参数的写法与此矛盾，疑为行文不严谨。

#### 量子纠缠详细规则

纠缠伤害公式：
```
纠缠伤害 = 等级基数 × 60% × 层数 × (1+BE) × (最大韧性/10+2) / 4 × 易伤 × 防御 × 抗性 × 最终伤害(finalDmgMulti) × 韧性减伤(baseUniversalMulti) × 减伤(dmgRedMulti)
```

> 注：纠缠属击破效果伤害，不吃虚弱（fandom Weaken/Toughness、hsr-optimizer、紫喵入坑指南 07 一致）。

- 击破时获得 **1 层**纠缠
- 纠缠触发前，敌人每受**一次攻击**叠加 **1 层**（最高 **5 层**）
- 单次弹射攻击无论命中几段都只算**一次攻击**
- 纠缠伤害触发时结算层数

### 2.11 超击破伤害（Super Break）

```
超击破伤害(superBreakDmg) = 韧性减伤(baseUniversalMulti) × 防御(defMulti) × 抗性(resMulti) × 易伤(vulnMulti) × 最终伤害(finalDmgMulti)
              × 超击破基数(superBreakBaseMulti) × 击破特攻区(beMulti) × 超击破转换倍率(superBreakConversionMulti)
              × 击破增伤区(breakDmgBoostMulti) × 超击破增伤区(superBreakDmgBoostMulti) × 减伤(dmgRedMulti)

超击破基数(superBreakBaseMulti) = (3767.5533 / 10) × 有效削韧值(effectiveToughness)
有效削韧值(effectiveToughness) = 削韧值(toughnessDmg) × (1 + 削韧值提高(breakEfficiencyBoost)) × (1 + 弱点击破效率提高(weaknessBreakEfficiencyBoost)) + 固定削韧值(fixedToughnessDmg)
超击破转换倍率(superBreakConversionMulti) = Σ 超击破转换倍率(SUPER_BREAK_MODIFIER)（池内加算；无转换源则为 0，不造成超击破）
超击破增伤区(superBreakDmgBoostMulti) = 1 + Σ 超击破伤害提高（"超击破伤害提高"类专属增益，仅超击破生效，池内加算）
```

其中：
- `toughnessDmg` 为本次攻击造成的削韧值
- `fixedToughnessDmg` 为固定削韧值（不受削韧效率影响）
- `breakEfficiencyBoost` 为削韧值提高（如角色行迹、光锥提供的削韧加成）
- `weaknessBreakEfficiencyBoost` 为弱点击破效率提高（如某些遗器套装效果）
- `SUPER_BREAK_MODIFIER` 为超击破**转换倍率**（同谐主终结技 1.6/1.4/1.2、忘归人天赋、流萤/乱破行迹、大丽花天赋等提供——决定削韧值按多大比例转为超击破伤害），池内加算
- 击破伤害提高（`breakDmgBoostMulti` 池）：忘归人 E4、光锥 In Pursuit of the Wind / Never Forget Her Flame 等
- 超击破伤害提高（`superBreakDmgBoostMulti` 池）：同谐主行迹「卫我起舞」等
- 三个池两两**乘算**（社区实测：+20% 超击破伤害常驻、再加 +16% 击破伤害后，超击破比值 = 1.16 = 乘算预期 (1.20×1.16)/1.20；若为同一加算池应为 (1+0.20+0.16)/(1+0.20) ≈ 1.1333，被排除——米游社 67198368，详见 game_rules.md 修改记录 2026-07-21）

#### 技能最终削韧值

```
有效削韧值(effectiveToughness) = 削韧值(toughnessDmg) × (1 + 削韧值提高(breakEfficiencyBoost)) × (1 + 弱点击破效率提高(weaknessBreakEfficiencyBoost)) + 固定削韧值(fixedToughnessDmg)
```

- `breakEfficiencyBoost` 与 `weaknessBreakEfficiencyBoost` 为两个独立的乘区，**乘算**而非加算。
- 弱点击破效率上限为 **300%**。

> 超击破仅对处于击破状态的敌人生效（例外：大丽花战技结界期间，全队可对未击破/韧性保护状态的敌人造成超击破——fandom Toughness 页已记载）。超击破伤害的属性取决于触发角色的属性（如火属性角色造成的超击破为火属性伤害）。
>
> 超击破**不吃攻击、不吃增伤、不吃双暴、不吃虚弱**，只吃等级、削韧值、击破特攻、超击破转换倍率、击破增伤、超击破增伤、最终伤害、易伤、防御、抗性、韧性减伤、减伤。

### 2.12 持续伤害（DOT）

#### 持续伤害特性

| 特性 | 说明 |
|------|------|
| 结算时机 | 回合开始时（结算 1）|
| 暴击 | **不会暴击** |
| 负面状态 | 可被净化解除，参与负面状态计数 |
| 同源同名 | 同源效果互相**覆盖**；非同源同名效果可**并存** |
| 属性类型 | 触电（雷）、风化（风）、灼烧（火）、裂伤（物理）|

#### 增益乘区生效情况

| 乘区 | 常规持续伤害 | 击破持续伤害 |
|------|-------------|-------------|
| 攻击力 | 生效 | 不生效 |
| 击破特攻 | 不生效 | 生效 |
| 增伤（含属性增伤）| 生效 | 不生效 |
| 独立增伤 | 生效 | 不生效 |
| 击破增伤 | 不生效 | 不生效 |
| 超击破增伤 | 不生效 | 不生效 |
| 易伤 | 生效 | 生效 |
| 独立易伤 | 生效 | 不生效 |
| 防御 | 生效 | 生效 |
| 抗性 | 生效 | 生效 |
| 减伤 | 生效 | 生效 |
| 虚弱 | 生效 | 不生效 |
| 最终伤害 | 生效 | 生效 |
| 韧性减伤 | 生效 | 生效 |

> 注：击破 DOT 的"独立易伤=不生效"为我方建模决策（fandom 无独立易伤概念、易伤单一池——按 fandom 结构任何易伤对击破 DOT 均生效），待实测；"最终伤害=生效"为模式 buff 外推推断（同 §2.7 定槽注，optimizer 无击破 DOT 实现可佐证）。

#### 伤害公式

```
角色持续伤害(dotDmg) = 韧性减伤(baseUniversalMulti) × 防御(defMulti) × 抗性(resMulti) × 易伤(vulnMulti) × 独立易伤(indVulnMulti) × 最终伤害(finalDmgMulti)
       × 增伤(dmgBoostMulti) × 独立增伤(indDmgBoostMulti) × 技能倍率(abilityMultiplier) × 效果命中区(ehrMulti)
       × 虚弱(weakenMulti) × 减伤(dmgRedMulti)
```

> 角色 DOT 的 `abilityMultiplier` 按角色面板计算（攻击力/生命值/防御力 × 倍率）；击破 DOT 的 `abilityMultiplier` 按击破基数计算（见击破效果表格），不依赖角色攻击力。
>
> 注：卡芙卡类"手动引爆 DOT"不是通用乘区——引爆按**引爆技能给定的固定百分比**单独结算（如卡芙卡战技"立即产生相当于原伤害 X% 的伤害"，专属参数；不减少持续回合数），不进入本公式。

#### DOT 效果命中乘区

```
有效DOT概率(effectiveDotChance) = min(1, DOT基础概率(dotBaseChance) × (1 + 效果命中(EHR)) × (1 - 敌人效果抵抗(enemyEffectRes) + 效果抵抗穿透(EFFECT_RES_PEN)) × (1 - 类型抵抗(typeRes)))
```

- `dotBaseChance`：DOT 基础概率（由技能/光锥决定）
- `EHR`：效果命中
- `enemyEffectRes`：敌人效果抵抗
- `EFFECT_RES_PEN`：效果抵抗穿透

#### DOT 分裂机制（如黑天鹅）

当 `dotSplit > 0` 时：

```
效果命中区(ehrMulti) = (1 + DOT分裂系数(dotSplit) × 有效DOT概率(effectiveDotChance) × (DOT层数(dotStacks) - 1)) / (1 + DOT分裂系数(dotSplit) × (DOT层数(dotStacks) - 1))
```

当 `dotSplit = 0` 时：

```
效果命中区(ehrMulti) = 有效DOT概率(effectiveDotChance)
```

- `dotSplit`：DOT 分裂系数
- `dotStacks`：DOT 层数

### 2.13 治疗与护盾

#### 治疗

```
治疗量(heal) = 基础治疗(baseHeal) × 治疗加成区(healMulti)

基础治疗(baseHeal) = 攻击倍率(atkScaling) × 攻击力(ATK) + 生命倍率(hpScaling) × 生命值(HP) + 固定治疗(flatHeal)
治疗加成区(healMulti) = 1 + 治疗量加成(OHB) + 受治疗量加成(INCOMING_HEAL)
```

- `OHB`（Outgoing Healing Boost）：治疗者自身的治疗量加成（如治疗衣、遗器套装、光锥等）
- `INCOMING_HEAL`：被治疗者的受治疗量变化（加成为正；也存在受治疗量**降低**——如敌方萨姆领域，按负值计入同一乘区）

> 治疗量加成与受治疗量加成属于**同一乘区**，加法叠加后作为总倍率。

#### 护盾

```
护盾值(shield) = 基础护盾(baseShield) × 护盾加成区(shieldBoostMulti)

基础护盾(baseShield) = 防御倍率(defScaling) × 防御力(DEF) + 生命倍率(hpScaling) × 生命值(HP) + 攻击倍率(atkScaling) × 攻击力(ATK) + 固定护盾(flatShield)
护盾加成区(shieldBoostMulti) = 1 + 护盾加成(shieldBoost)
```

- `shieldBoost`：护盾 boost（来自 DMG_BOOST slot，过滤为护盾类型）

### 2.14 欢愉伤害

欢愉命途（Path of Elation）角色的专属伤害类型。与常规伤害不同，欢愉伤害的基础伤害基于**等级系数**而非角色属性：

```
欢愉伤害 = 基础伤害(baseDMG) × 原始欢愉伤害倍率(origElationDmgMulti) × 欢愉增伤区(elationDmgBoostMulti)
           × 暴击(critMulti) × 欢愉度(elationMulti) × 笑点/好活当赏(punchlineMulti)
           × 增笑(merrymakeMulti) × 防御(defMulti) × 抗性(resMulti)
           × 易伤(vulnMulti) × 减伤(dmgRedMulti) × 韧性(baseUniversalMulti) × 最终伤害(finalDmgMulti)
```

**基础伤害**：
```
baseDMG = 等级系数(levelMultiplier) × 技能倍率(abilityMultiplier)
```

等级系数与击破伤害类似，但数值约为击破的 2 倍（Lv.80 = 7535.1070）。

| 乘区 | 公式 |
|------|------|
| levelMultiplier | 等级系数（Lv.80 = 7535.1070，约为击破等级系数 3767.5533 的 2 倍） |
| abilityMultiplier | 技能倍率（欢愉技自身的**纯倍率**——比例量纲，数据侧绑定；与 §2.1 的 abilityMultiplier（倍率×基础属性，伤害量纲）同名不同义） |
| elationMulti | `1 + 欢愉度(Elation)` |
| punchlineMulti | `1 + 5 × X / (X + 240)`，收敛上限 6（+500%）。施放欢愉技时 X=笑点，其余欢愉伤害 X=好活当赏 |
| merrymakeMulti | `1 + 增笑(Merrymake)`，稀有乘区，仅爻光 E6 / 绯英 E6 / 银狼LV.999 E6 可提供 |
| critMulti | 同 2.9 暴击乘区 |
| defMulti | 同 2.2 防御乘区 |
| resMulti | 同 2.3 抗性乘区 |
| vulnMulti | `1 + 欢愉伤害易伤 + 全类型易伤`（欢愉伤害易伤是独立类型） |
| origElationDmgMulti | 原始欢愉伤害倍率（额外的独立倍率修正，默认 1——与 abilityMultiplier 分工：abilityMultiplier 是技能自身倍率、进 baseDMG，origElationDmgMulti 是独立的修正乘区，数据侧 source 绑定；⚠️ 与 fandom 的 "Original Elation DMG Multiplier" 命名撞车但**不同物**——后者按 §2.7 定槽规则归 finalDmgMulti 槽） |
| elationDmgBoostMulti | 欢愉专属增伤区（`1 + Σ 欢愉伤害提高`，池内加算；当前无实例，预留槽默认 1） |
| finalDmgMulti | 同 2.7 最终伤害乘区（"为原伤害的 X%"类，如爻光 E4 欢愉技 150%——护栏：此类效果**只进本槽、不进 origElationDmgMulti**，防双重计算；fandom 将其归为 Original Elation DMG Multiplier，命名不同、与本槽同物） |

> 欢愉伤害**不享受增伤乘区**（即不吃我方角色提供的增伤 buff），也**不受虚弱(Weaken)影响**。
>
> 英文术语：欢愉度 = Elation，笑点 = Punchline，好活当赏 = Certified Banger，阿哈时刻 = Aha Instant。
>
> Certified Banger 与笑点**公式相同**（`1 + 5 × X / (X + 240)`），只是数据来源不同（施放欢愉技时 X=笑点，其余欢愉伤害 X=好活当赏）。
>
> 详见 [08_elation_system.md](08_elation_system.md)。

---
