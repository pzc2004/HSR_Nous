# 崩坏：星穹铁道 战斗规则

本文档记录崩铁核心战斗机制，作为战斗模拟器的**唯一事实来源**。

> 当本文档与代码实现冲突时，以本文档为准，代码需要修正。

---

## 目录

> 分册文件清单的唯一来源是 [README.md](README.md) 目录树（索引闸 `tests/test_doc_lint.py` 双向校验磁盘）；本表为章节导航，说明列如有出入以分册正文为准。

| 章节 | 说明 | 详细文档 |
|------|------|---------|
| **0. 游戏基础** | 命途/属性/光锥/遗器/养成/基础属性总览 | [mechanics/00_game_basics.md](mechanics/00_game_basics.md) |
| **1. 基础属性** | 角色/敌人属性计算、治疗与护盾、技能分类、记忆命途与忆灵 | [mechanics/01_base_stats.md](mechanics/01_base_stats.md) |
| **2. 伤害公式** | 完整伤害乘区体系（增伤、易伤、防御、抗性、暴击、真实伤害等） | [mechanics/02_damage_formula.md](mechanics/02_damage_formula.md) |
| **3. 行动序** | 回合/轮次/波次概念、行动值计算、拉条/推条、速度变化、额外回合、冻结 | [mechanics/03_action_sequence.md](mechanics/03_action_sequence.md) |
| **4. 击破机制** | 韧性削减、弱点击破、击破伤害、超击破 | [mechanics/04_break_system.md](mechanics/04_break_system.md) |
| **5. 能量机制** | 能量获取、终结技释放、能量恢复效率 | [mechanics/05_energy_system.md](mechanics/05_energy_system.md) |
| **6. 战技点机制** | 战技点上限、获取与消耗规则 | [mechanics/06_skill_points.md](mechanics/06_skill_points.md) |
| **7. Buff / Debuff** | 持续时间、结算机制、层数叠加、驱散规则 | [mechanics/07_buff_system.md](mechanics/07_buff_system.md) |
| **8. 欢愉命途** | 欢愉伤害、阿哈时刻、笑点、好活当赏 | [mechanics/08_elation_system.md](mechanics/08_elation_system.md) |
| **9. 追加攻击** | 触发条件、反击（Counter）、追加攻击限制 | [mechanics/09_follow_up_attacks.md](mechanics/09_follow_up_attacks.md) |
| **10. 嘲讽机制** | 基础嘲讽值、受击概率计算 | [mechanics/10_taunt_system.md](mechanics/10_taunt_system.md) |
| **11. 特殊机制** | 专属效果、控制效果、HP 事件 vs 伤害事件、结界/境界/连携攻击 | [mechanics/11_special_mechanics.md](mechanics/11_special_mechanics.md) |
| **12. 秘技系统** | 秘技点（TP）、秘技分类、战前策略 | [mechanics/12_technique_system.md](mechanics/12_technique_system.md) |

---

## 核心公式速查

公式不双份存放（防腐）——查询入口：

- **可执行唯一来源**：`src/hsr_nous/sim_schema/rulebook.yaml`（伤害公式/乘区/常数/模式表，引擎直接消费）
- **文档镜像**：`src/hsr_nous/sim_schema/docs/01_formula.md`（与 rulebook 逐字一致，lint 镜像闸保证）
- **数值事实与各乘区讲解**：[mechanics/02_damage_formula.md](mechanics/02_damage_formula.md)（伤害）、[mechanics/03_action_sequence.md](mechanics/03_action_sequence.md)（行动值/拉条）、[mechanics/04_break_system.md](mechanics/04_break_system.md)（削韧/击破）

---

## 待确认事项

- [ ] 追加攻击的触发条件分类是否需要进一步细化（关联 BACKLOG B19"追加攻击事件流"待实测行）
- [ ] 强烈震荡的触发来源与抵抗机制

## 修改记录

- 2026-08-25：核心公式速查去双份——公式表达式改指路 rulebook.yaml（可执行唯一来源）/01_formula.md（文档镜像）/mechanics 02–04（防腐，lint 镜像闸同步收缩）；待确认事项核销（真实伤害条已确认移除，余两条保留）

- 2026-07-22（四批，审计 R4/R5/R6/R7 工作表落地）：`grant_extra_turn` 原语落地（05_effects 新增"授予额外回合"节：insert=第 2 层 FIFO 不耗 buff 不受推条、after_action=视同普通回合；09_faq 再现示例改用原语）；欢愉增伤区独立成池 `elationDmgBoostMulti`（02 定义/公式/生效表/乘区表、08 公式、01 表达式+参数+矩阵、21 表达式+参数，当前无实例预留槽）；击破效果框架补 `× 韧性减伤`（裂伤等 2 回合 DOT 第二跳正确吃 0.9）、回滚击破增伤（fandom piecewise "if Break DMG; 1 otherwise"——击破 DOT/附加伤害不吃）；`override` 字段落地（04 §4.2：最终面板覆写如万敌血仇 DEF=0，冲突即错+互斥即错，13 validator 两条检查）；02 生效表与 2.12 表多轮补全（DOT 行"2.1 常规乘区（除双暴）+ ehrMulti"、独立增伤/超击破增伤/最终伤害/韧性减伤行、表下待实测与外推标注）；DOT 公式删除跳数系数、卡芙卡类引爆注改"引爆技能给定的固定百分比"；真实伤害补"来源间加算稀释、被护盾抵挡"（紫喵 11 置顶）；角色附加伤害 vs 击破附加伤害限定词全局统一（02/04/11/01）；§7.7.3 "属性→增伤也纳入转化标签"明示、§7.7.4 知更鸟行注实测来源、§7.7.4 范围限定为"百分比+固定点数"、§7.7.6 链式例子补阮·梅；ability 命名全库统一 `ability_multiplier`（01 表达式+参数+矩阵、09、15、02 驼峰）；merge_to_matrix.py 清理 17 处同键冲突+注册 drain_hp/grant_extra_turn 家族；01 §1.4 裂伤 min 显式注（min 整体替代 level_base×effect_multiplier）；01 矩阵补"击破列≠击破效果"注；小伊卡三处 hook 统一 drain 模型；23:208 风堇 M2 rank id 注；03:133/147 "视同普通回合"限定到 buff 维度
- 2026-07-21（三批，审计 R3 工作表 47 项落地）：欢愉伤害公式补 `finalDmgMulti`（02/01/矩阵/生效表；§2.7 术语对照注：角色文本="为原伤害的 X%"、fandom=Original DMG Multiplier、模式 buff="最终伤害提高"，同属推断已标注）；普攻扩散削韧修正（基线 20/10 刃、饮月特例 30/10·40/20，04/01/22 三处）；卡芙卡类引爆注改"引爆技能给定的固定百分比"；04 削韧表表头改"邻/主/邻"并补弹射列、超击破补大丽花例外；§4.8 删除 7 行与总线重复的事件糖（能量阈值/死亡/HP 变化/受击/护盾/资源持有），`on_dot_retrigger` 补入 §23.4；函数白名单统一（§22.10 为唯一事实来源，effect 层补 sum/lookup_table/zone_owner、chance/in_zone 限 condition）；秘技 effects 队列模型落地（20.2 `battle_start_effects` 字段 + 20.4 流程）；小伊卡示例统一 drain 模型（22.11/23.9 对齐 07）；受击事件统一 `before_take_damage`/`after_being_hit`；生效表补韧性减伤/原始欢愉伤害倍率/独立增伤独立易伤不生效列；风化 5 层+精英首领；残梅绽补 30% 系数与不可重复附加；治疗"受治疗量可为负"（萨姆领域）；22.11/07 示例变量绑定修正；白厄 TP+3 出处统一为秘技「终结之始」；01_base_stats/06 节号重排；索引补 00_game_basics；异相仲裁 Anomaly Arbitration；validator/17/18/20/21 等一批字段级修正
- 2026-07-21（二批，审计 R2 工作表 30 项裁决落地）：**超击破三池拆分**——超击破公式改 `× 超击破转换倍率 × 击破增伤区 × 超击破增伤区`（三池各自池内加算、池间乘算；米游社 67198368 实测 + fandom + optimizer 一致），击破公式补 `× 击破增伤区`，SUPER_BREAK_MODIFIER 注释纠正为转换倍率；裂伤 cap 改写为 `2×韧性系数(0.5+最大韧性/40)` 并注基数层比较有实测（米游社 58632087）；通用 DOT 公式删除跳数系数（卡芙卡类手动引爆按比例单独结算）；03 行动序轮次定义与示例按全局时间轴重写、插入行动改三层 FIFO 模型（追加行动 > 额外回合含终结技同层 FIFO > 普通回合）；04 冻结/残梅绽（真跳过+锁韧性恢复）与纠缠/禁锢（仅延后）分流；`drain_hp` 改触发 `on_hp_decrease`（reason='drain'）；01 断点表 6 格重算；07 星期日 E6 散文与连续标签修正；`04_modifier`/`23_event_hook_system` 按合并口径扫清"保持分离 TBD"残留并去重事件定义；刃地狱变（战技 120502、嘲讽 +1000% scaling）、validator 等级/modifier_type、秘技强制进战与扣 TP、遗器副词条三档、异相仲裁 `anomaly_arbitration` 等 schema 修正
- 2026-07-21：击破系公式回滚虚弱乘区——击破伤害/超击破伤害/击破效果伤害/纠缠均**不受虚弱影响**（fandom `Weaken`、`Toughness` 两页 + hsr-optimizer 实现 + 紫喵Azunya 入坑指南 07 四方一致）；常规 DOT 仍受虚弱影响（紫喵入坑指南 10）；`02_damage_formula.md` 生效表/DOT 乘区表同步，`01_formula.md`、`15_data_separation.md` 公式同步删除 `weaken_multi`
- 2026-06-15：大量补充
  - 新建 `00_game_basics.md`：命途/属性/光锥/遗器/养成/基础属性总览
  - 新建 `12_technique_system.md`：秘技系统（TP 秘技点、分类、战前策略），基于 [Fandom - Technique](https://honkai-star-rail.fandom.com/wiki/Technique)
  - `06_skill_points.md`：新增 §6.5（当时节号，现为 §6.3）战技点（SP）vs 秘技点（TP）对比
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
