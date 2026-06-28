# 崩坏：星穹铁道 战斗规则

本文档记录崩铁核心战斗机制，作为战斗模拟器的**唯一事实来源**。

> 当本文档与代码实现冲突时，以本文档为准，代码需要修正。

---

## 目录

| 章节 | 说明 | 详细文档 |
|------|------|---------|
| **1. 基础属性** | 角色/敌人属性计算、技能分类、记忆命途与忆灵 | [mechanics/01_base_stats.md](mechanics/01_base_stats.md) |
| **2. 伤害公式** | 完整伤害乘区体系（增伤、易伤、防御、抗性、暴击、真实伤害等） | [mechanics/02_damage_formula.md](mechanics/02_damage_formula.md) |
| **3. 行动序** | 回合/轮次/波次概念、行动值计算、拉条/推条、速度变化、额外回合、冻结 | [mechanics/03_action_sequence.md](mechanics/03_action_sequence.md) |
| **4. 击破机制** | 韧性削减、弱点击破、击破伤害、超击破 | [mechanics/04_break_system.md](mechanics/04_break_system.md) |
| **5. 能量机制** | 能量获取、终结技释放、能量恢复效率 | [mechanics/05_energy_system.md](mechanics/05_energy_system.md) |
| **6. 战技点机制** | 战技点上限、获取与消耗规则 | [mechanics/06_skill_points.md](mechanics/06_skill_points.md) |
| **7. Buff / Debuff** | 持续时间、结算机制、层数叠加、驱散规则 | [mechanics/07_buff_system.md](mechanics/07_buff_system.md) |
| **8. 欢愉命途** | 欢愉伤害、阿哈时刻、笑点、好活当赏 | [mechanics/08_elation_system.md](mechanics/08_elation_system.md) |
| **9. 追加攻击** | 追加攻击的触发条件与优先级 | [mechanics/09_follow_up_attacks.md](mechanics/09_follow_up_attacks.md) |
| **10. 嘲讽机制** | 基础嘲讽值、受击概率计算 | [mechanics/10_taunt_system.md](mechanics/10_taunt_system.md) |
| **11. 特殊机制** | 专属效果、控制效果、HP 事件 vs 伤害事件区分 | [mechanics/11_special_mechanics.md](mechanics/11_special_mechanics.md) |
| **12. 秘技系统** | 秘技点（TP）、秘技分类、战前策略 | [mechanics/12_technique_system.md](mechanics/12_technique_system.md) |

---

## 核心公式速查

### 基础伤害

```
伤害 = 技能倍率(abilityMulti) × 增伤(dmgBoostMulti) × 独立增伤(indDmgBoostMulti) × 防御(defMulti) × 抗性(resMulti)
      × 韧性减伤(baseUniversalMulti) × 易伤(vulnMulti) × 独立易伤(indVulnMulti) × 最终伤害(finalDmgMulti)
      × 暴击(critMulti) × 虚弱(weakenMulti) × 减伤(dmgRedMulti)
```

各乘区详见 [mechanics/02_damage_formula.md](mechanics/02_damage_formula.md)。

### 行动值

```
AV = 10000 / speed
```

详见 [mechanics/03_action_sequence.md](mechanics/03_action_sequence.md)。

### 削韧值

```
最终削韧 = toughnessDmg × (1 + 削韧值提高(breakEfficiencyBoost)) × (1 + 弱点击破效率提高(weaknessBreakEfficiencyBoost)) + 固定削韧值(fixedToughnessDmg)
```

详见 [mechanics/04_break_system.md](mechanics/04_break_system.md)。

---

## 待确认事项

- [x] 真实伤害是否受减伤/虚弱影响 — **已确认**：真实伤害完全不受任何常规乘区影响（包括减伤、虚弱、易伤、防御、抗性、增伤、暴伤等）
- [ ] 追加攻击的触发条件分类是否需要进一步细化
- [ ] 强烈震荡的触发来源与抵抗机制

## 修改记录

- 2026-06-15：大量补充
  - 新建 `00_game_basics.md`：命途/属性/光锥/遗器/养成/基础属性总览
  - 新建 `12_technique_system.md`：秘技系统（TP 秘技点、分类、战前策略），基于 [Fandom - Technique](https://honkai-star-rail.fandom.com/wiki/Technique)
  - `06_skill_points.md`：新增 §6.5 战技点（SP）vs 秘技点（TP）对比
  - `07_buff_system.md`：新增 §7.7 属性二次转化（基本部分/额外部分模型 + 4 维度 + 全角色盘点表 + 知更鸟/玲可固定值特殊处理），基于 [B 站 · 夜殇黑羽《论属性的二次转化》](https://www.bilibili.com/opus/1176311260863528979)
  - `10_taunt_system.md`：全面重写（公式 `嘲讽值 = 基础 × (1 + Σ 百分比加成)` + 全角色技能/光锥加成清单 + 彦卿特殊修改 Base），基于 [Fandom - Taunt](https://honkai-star-rail.fandom.com/wiki/Aggro)
  - `11_special_mechanics.md`：新增 §11.3 HP 变化事件 vs 伤害事件区分；§11.4 结界 (Zone)；§11.5 境界 (Territory)；§11.6 连携攻击 (Joint ATK)
  - 更新 `docs/README.md` 和 `game_rules.md` 索引
- 2026-05-16：新增 elation_system.md 欢愉命途机制；damage_formula.md 新增 2.14 欢愉伤害；术语统一（笑点乘区 `humorMulti` → `punchlineMulti`，与官方英文对齐：Elation/Punchline/Certified Banger/Aha Instant）；伤害类型表格补充真实伤害与欢愉伤害
- 2026-05-16：修复章节编号与 game_rules.md 索引对齐（elation 8.x、follow_up_attacks 9.x、taunt 10.x、special 11.x）
- 2026-05-16：补充 skill_points.md 战技点特殊机制（上限可提升、战技不耗点/多耗点、普攻不回复、终结技回复等）
- 2026-05-16：确认真实伤害完全不受任何常规乘区影响（包括减伤、虚弱、易伤、防御、抗性、增伤、暴伤等）
- 2026-05-16：批量修复文档矛盾（game_rules.md 速查公式删除残留 `trueDmgMulti`；待确认事项更新；修改记录修正抗性上下限描述和 `superBreakModMulti` 描述；break_system.md 补充量子/虚数击破独立推条比例；damage_formula.md 暴击表格改用 effectiveCR/effectiveCD、DOT 公式区分角色/击破 DOT、效果命中公式统一加入 EFFECT_RES_PEN、防御等价形式条件修正；energy_system.md 明确能量恢复效率面板为总倍率；buff_system.md 效果命中公式加入 EFFECT_RES_PEN）
- 2026-05-16：damage_formula.md 修复（删除击破伤害公式中多余的 `增伤(dmgBoostMulti)`；精简 `击破特攻(击破特攻(BE))`、`等级基数(等级基数(levelBase))`、`效果倍率(效果倍率(effectMultiplier))` 等重复嵌套命名）
- 2026-05-16：修正 base_stats.md 中打击方式示例角色（单体/扩散/弹射）
- 2026-05-16：公式变量名统一为中文+英文格式（如 `防御(defMulti)`）；补充参考来源（紫喵Azunya 入坑指南系列）
- 2026-05-16：超击破公式修正（删除 `dmgBoostMulti`；削韧效率拆为两个乘算乘区；`superBreakModMulti` 修正为 `1 + SUPER_BREAK_MODIFIER + extraSuperBreakModifier`）；添加双击破机制；击破/超击破/DOT 删除 `trueDmgMulti`；主公式删除 `trueDmgMulti`；添加 `weakenMulti` 和 `dmgRedMulti`；普攻削韧值修正为 10；速度公式修正为百分比加成；能量恢复效率基础值修正为 100%；效果命中公式加 `min(1, ...)` 上限
- 2026-05-15：拆分为 `mechanics/` 目录下的独立文档，`game_rules.md` 改为总纲
- 2026-05-15：新增 1.4 记忆命途与忆灵、2.8 真实伤害、2.2 防御乘区收益特性
- 2026-05-15：新增独立增伤区、独立易伤区；修正抗性上限为 90%、下限为 -100%
