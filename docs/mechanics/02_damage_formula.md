# 伤害公式


### 2.1 基础伤害（Ability Multiplier）

```
伤害 = 基础乘区(abilityMulti) × 增伤(dmgBoostMulti) × 独立增伤(indDmgBoostMulti) × 防御(defMulti) × 抗性(resMulti)
      × 韧性减伤(baseUniversalMulti) × 易伤(vulnMulti) × 独立易伤(indVulnMulti) × 最终伤害(finalDmgMulti)
      × 暴击(critMulti) × 虚弱(weakenMulti) × 减伤(dmgRedMulti)
```

| 乘区 | 公式 |
|------|------|
| abilityMulti | 技能倍率 × 基础属性 |
| dmgBoostMulti | 1 + 增伤 + 属性增伤 |
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
技能倍率(abilityMulti) = 攻击倍率(atkScaling) × 攻击力(ATK) + 生命倍率(hpScaling) × 生命值(HP) + 防御倍率(defScaling) × 防御力(DEF)
```

基础属性取值：
- `ATK`：攻击力
- `HP`：生命值
- `DEF`：防御力

特殊 scaling：
- **BE scaling**：`atkScaling + beScaling × min(beCap, BE)`（击破特攻转攻击力，如流萤）

#### 伤害类型与乘区生效关系

| 伤害类型 | 生效乘区 | 不生效乘区 |
|---------|---------|-----------|
| 直伤（普攻/战技/终结技/追加攻击/附加伤害）| 全部 | 无 |
| 常规持续伤害（DOT）| 除双暴区外全部 | 双暴区 |
| 击破伤害 | 基础击破伤害、击破特攻、韧性系数、防御、易伤、减伤、抗性 | 双暴、增伤 |
| 超击破伤害 | 超击破基数、击破特攻、削韧、防御、易伤、减伤、抗性 | 双暴、增伤 |
| 真实伤害 | 仅真实伤害(trueDmgMulti) | 防御、抗性、增伤、暴伤、易伤、减伤、虚弱等全部常规乘区 |
| 欢愉伤害 | 等级系数、技能倍率、欢愉度、笑点/好活当赏、增笑、双暴、防御、抗性、易伤、真伤、特殊乘区 | 增伤、虚弱 |

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
增伤(dmgBoostMulti) = 1 + 通用增伤(DMG_BOOST) + 属性增伤(elementalDmgBoost)
独立增伤(indDmgBoostMulti) = 1 + 独立增伤(INDEPENDENT_DMG_BOOST)
```

- `DMG_BOOST`：通用增伤（如停云战技、某些光锥特效等）
- `elementalDmgBoost`：对应属性增伤（如属性球、`PHYSICAL_DMG_BOOST`、`FIRE_DMG_BOOST` 等）
- `INDEPENDENT_DMG_BOOST`：独立增伤（如部分命途机制、特殊 buff 等）

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
         × 击破基数(breakBaseMulti) × 击破特攻区(beMulti) × 虚弱(weakenMulti) × 减伤(dmgRedMulti)

击破基数(breakBaseMulti) = 3767.5533 × 属性击破倍率(elementalBreakScaling) × (0.5 + 最大韧性(maxToughness) / 40) × 特殊倍率(specialScaling)
击破特攻区(beMulti) = 1 + 击破特攻(BE)
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

> 击破伤害**不吃增伤**（包括通用增伤和属性增伤）。

#### 各属性击破效果

击破效果伤害公式通用框架：

```
击破效果伤害(breakEffectDmg) = 等级基数(levelBase) × 效果倍率(effectMultiplier) × (1 + 击破特攻(BE)) × 易伤(vulnMulti) × 防御(defMulti) × 抗性(resMulti)
               × 减伤(dmgRedMulti) × 虚弱(weakenMulti)
```

| 属性 | 击破效果 | 效果倍率 | 特殊机制 |
|------|---------|---------|---------|
| 物理 | 裂伤 | Min(敌人类型系数×HP, levelBase×韧性单位×2) | 持续伤害，敌人类型系数：精英/首领 7%，普通 16% |
| 火 | 灼烧 | 100% | 持续伤害 |
| 冰 | 冻结 | 100% | 附加伤害；冻结恢复后下一轮行动值为原行动值的 50% |
| 雷 | 触电 | 200% | 持续伤害 |
| 风 | 风化 | 每层 100% | 持续伤害，可叠加多层；精英怪被击破时直接叠加 3 层；风化状态下被击破可叠加并重置回合 |
| 量子 | 纠缠 | 60% × 层数 × (最大韧性/10+2)/4 | 附加伤害，额外行动延后 20%×(1+BE) |
| 虚数 | 禁锢 | 无伤害 | 额外行动延后 30%×(1+BE)，减速 10%（可与其他减速叠加） |

> 量子/虚数的行动延后是在击破通用 25% 基础上的额外延后。

#### 量子纠缠详细规则

纠缠伤害公式：
```
纠缠伤害 = 等级基数 × 60% × 层数 × (1+BE) × (最大韧性/10+2) / 4 × 易伤 × 防御 × 抗性 × 减伤
```

- 击破时获得 **1 层**纠缠
- 纠缠触发前，敌人每受**一次攻击**叠加 **1 层**（最高 **5 层**）
- 单次弹射攻击无论命中几段都只算**一次攻击**
- 纠缠伤害触发时结算层数

### 2.11 超击破伤害（Super Break）

```
超击破伤害(superBreakDmg) = 韧性减伤(baseUniversalMulti) × 防御(defMulti) × 抗性(resMulti) × 易伤(vulnMulti) × 最终伤害(finalDmgMulti)
              × 超击破基数(superBreakBaseMulti) × 击破特攻区(beMulti) × 超击破倍率(superBreakModMulti)
              × 虚弱(weakenMulti) × 减伤(dmgRedMulti)

超击破基数(superBreakBaseMulti) = (3767.5533 / 10) × 有效削韧值(effectiveToughness)
有效削韧值(effectiveToughness) = 削韧值(toughnessDmg) × (1 + 削韧值提高(breakEfficiencyBoost)) × (1 + 弱点击破效率提高(weaknessBreakEfficiencyBoost)) + 固定削韧值(fixedToughnessDmg)
超击破倍率(superBreakModMulti) = 1 + 超击破伤害提高(SUPER_BREAK_MODIFIER) + 额外超击破伤害提高(extraSuperBreakModifier)
```

其中：
- `toughnessDmg` 为本次攻击造成的削韧值
- `fixedToughnessDmg` 为固定削韧值（不受削韧效率影响）
- `breakEfficiencyBoost` 为削韧值提高（如角色行迹、光锥提供的削韧加成）
- `weaknessBreakEfficiencyBoost` 为弱点击破效率提高（如某些遗器套装效果）
- `SUPER_BREAK_MODIFIER` 为超击破伤害提高（如忘归人、流萤等角色提供）
- `extraSuperBreakModifier` 为本次攻击附带的额外超击破伤害提高

#### 技能最终削韧值

```
有效削韧值(effectiveToughness) = 削韧值(toughnessDmg) × (1 + 削韧值提高(breakEfficiencyBoost)) × (1 + 弱点击破效率提高(weaknessBreakEfficiencyBoost)) + 固定削韧值(fixedToughnessDmg)
```

- `breakEfficiencyBoost` 与 `weaknessBreakEfficiencyBoost` 为两个独立的乘区，**乘算**而非加算。
- 弱点击破效率上限为 **300%**。

> 超击破仅对处于击破状态的敌人生效。超击破伤害的属性取决于触发角色的属性（如火属性角色造成的超击破为火属性伤害）。
>
> 超击破**不吃攻击、不吃增伤、不吃双暴**，只吃等级、削韧值、击破特攻、超击破独立增伤、易伤、防御、抗性、减伤。

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
| 易伤 | 生效 | 生效 |
| 防御 | 生效 | 生效 |
| 抗性 | 生效 | 生效 |
| 减伤 | 生效 | 生效 |

#### 伤害公式

```
角色持续伤害(dotDmg) = 韧性减伤(baseUniversalMulti) × 防御(defMulti) × 抗性(resMulti) × 易伤(vulnMulti) × 独立易伤(indVulnMulti) × 最终伤害(finalDmgMulti)
       × 增伤(dmgBoostMulti) × 独立增伤(indDmgBoostMulti) × 技能倍率(abilityMulti) × 效果命中区(ehrMulti) × DOT跳数系数(dotTickCoefficientMulti)
       × 虚弱(weakenMulti) × 减伤(dmgRedMulti)
```

> 角色 DOT 的 `abilityMulti` 按角色面板计算（攻击力/生命值/防御力 × 倍率）；击破 DOT 的 `abilityMulti` 按击破基数计算（见击破效果表格），不依赖角色攻击力。

#### DOT 效果命中乘区

```
有效DOT概率(effectiveDotChance) = min(1, DOT基础概率(dotBaseChance) × (1 + 效果命中(EHR)) × (1 - 敌人效果抵抗(enemyEffectRes) + 效果抵抗穿透(EFFECT_RES_PEN)))
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
- `INCOMING_HEAL`：被治疗者的受治疗量加成（如部分角色技能、光锥提供的受治疗提高）

> 治疗量加成与受治疗量加成属于**同一乘区**，加法叠加后作为总倍率。

#### 护盾

```
护盾值(shield) = 基础护盾(baseShield) × 护盾加成区(shieldBoostMulti)

基础护盾(baseShield) = 防御倍率(defScaling) × 防御力(DEF) + 生命倍率(hpScaling) × 生命值(HP) + 攻击倍率(atkScaling) × 攻击力(ATK) + 固定护盾(flatShield)
护盾加成区(shieldBoostMulti) = 1 + 护盾加成(shieldBoost)
```

### 2.14 欢愉伤害

欢愉命途（Path of Elation）角色的专属伤害类型。与常规伤害不同，欢愉伤害的基础伤害基于**等级系数**而非角色属性：

```
欢愉伤害 = 基础伤害(baseDMG) × 原始欢愉伤害倍率(origElationDmgMulti)
           × 暴击(critMulti) × 欢愉度(elationMulti) × 笑点/好活当赏(punchlineMulti)
           × 增笑(merrymakeMulti) × 防御(defMulti) × 抗性(resMulti)
           × 易伤(vulnMulti) × 减伤(dmgMitigationMulti) × 韧性(baseUniversalMulti)
```

**基础伤害**：
```
baseDMG = 等级系数(levelMultiplier) × 技能倍率(abilityMultiplier)
```

等级系数与击破伤害类似，但数值约为击破的 2 倍（Lv.80 = 7535.1070）。

| 乘区 | 公式 |
|------|------|
| levelMultiplier | 等级系数（Lv.80 = 7535.1070），见下方表格 |
| abilityMultiplier | 技能倍率 |
| elationMulti | `1 + 欢愉度(Elation)` |
| punchlineMulti | `1 + 5 × X / (X + 240)`，收敛上限 6（+500%）。施放欢愉技时 X=笑点，其余欢愉伤害 X=好活当赏 |
| merrymakeMulti | `1 + 增笑(Merrymake)`，稀有乘区，仅爻光 E6 / 绯英 E6 / 银狼LV.999 E6 可提供 |
| critMulti | 同 2.9 暴击乘区 |
| defMulti | 同 2.2 防御乘区 |
| resMulti | 同 2.3 抗性乘区 |
| vulnMulti | `1 + 欢愉伤害易伤 + 全类型易伤`（欢愉伤害易伤是独立类型） |
| origElationDmgMulti | 原始欢愉伤害倍率 |
| specialMulti | 角色专属特殊乘区 |

> 欢愉伤害**不享受增伤乘区**（即不吃我方角色提供的增伤 buff），也**不受虚弱(Weaken)影响**。
>
> 英文术语：欢愉度 = Elation，笑点 = Punchline，好活当赏 = Certified Banger，阿哈时刻 = Aha Instant。
>
> Certified Banger 产生的笑点使用独立公式：`1 + 5 × Certified_Banger / (Certified_Banger + 240)`。
>
> 详见 [08_elation_system.md](08_elation_system.md)。

- `shieldBoost`：护盾 boost（来自 DMG_BOOST slot，过滤为护盾类型）

---