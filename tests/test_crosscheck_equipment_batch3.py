"""L3 装备级对拍·残部续波（BACKLOG B22 扩展②续三）：首批 6+4（equipment.py）、
批量波 25+14（equipment_batch.py）、专光扫荡 22（equipment_batch2.py）之后的
残部续波——本批 37 光锥（3/4 星功能件为主）+ 6 遗器，每件等式场景三方比对
（我方引擎 vs 对方 vs 手算，rel_tol 1e-4）+ 结构差钉倍数。

载体（映射表现成，见各源文件）：黑塔 1013（智识）/黄泉 1308（虚无）/真理医生
1305（巡猎）/白厄 1408（毁灭）/刻律德菈 1412（同谐·风）/遐蝶 1407（记忆）/
罗刹 1203（丰饶）/杰帕德 1104（存护·Grit 防转攻）/托帕 1112（巡猎·火——107
火匠载体）。裁判链路与统一口径同前三批（driver 头注 + 首批 docstring）；本文件
只增映射表与场景。对方侧光锥属性段（对方控制器不承载的 properties）一律钉进
attacker.*。

===========================================================================
光锥 buff 状态映射表（对方条件开关 ↔ 我方模板 hooks；属性段=对方钉面板）
===========================================================================
--- 智识（黑塔 1013）---
21034 今日亦是和平的一日 S1
maxEnergyDmgBoost（true）   常驻 all_dmg=min(能量上限,160)×0.2%/点              普攻比等
                            （黑塔上限 110 → 22%——对方同式读 context.baseEnergy
                            场景槽，两侧 110 同值）
21040 银河沦陷日 S1——属性段 ATK+16%（对方钉 atk 面板）
cdBuffActive（true）        常驻 crit_dmg 20%（=对方 CD 开关——双方同区同值）    普攻比等
21060 氤氲麦香的梦 S1——属性段 CR+12%（对方钉 cr）
ultFuaDmgBoost（true）      常驻 dmg_ultimate/dmg_follow_up 24%（对方 ULT|FUA    大招比等
                            标签 BOOST 同值）
22004 宇宙大生意 S1——属性段 ATK+8%（对方钉 atk 面板）
weaknessTypes 0-7（0）      敌方弱点种类增伤 4%/种——**待收**（目标弱点计数       基线比等；
                            无查询通道在案）→ 对方滑条无条件=近似                 钉 7 层钉 S1
--- 虚无（黄泉 1308；负面计数类场景先 _clean_knots 清开局层）---
20018 匿影 S1
basicAtkBuff（true）        战技闩 → 下一次普攻首段附加 0.6×ATK（对方            普攻双段（1.0+0.6
                            actionModifiers 向 directHit 行动追加同倍率段——          附加）比等
                            LC actionModifiers 镜像首挂）
21044 无边曼舞 S1——属性段 CR+8%（对方钉 cr）
enemyDefReducedSlowed       对防御降低/减速敌暴伤 24%——**待收**（目标条件化       基线比等；
（false）                    面板无通道在案）→ 对方 CD 开关=近似                   钉 true 钉 S2
21061 假日浴场大冒险 S1——属性段 增伤 16%（对方钉 dmg_boost）
vulnerability（true）       after_being_hit 首段挂【易伤】10% 2回合              第 2 次命中比等；
                            （对方 mutual FullTeam VULNERABILITY 恒开）            首击钉 S3
21041 好戏开演 S1
trickStacks 0-3（3）        对敌施加减益叠层 all_dmg 6%×N（经引擎注入 3 负面       钉 3 层比等
                            正规激发 after_apply_modifier——117 先例）
（无开关）EHR≥80% 攻击 20%   enable_if $self.effect_hit≥0.8 → atk_pct 20%         双方 EHR 钉 0.9
                            （对方同闸读 action EHR——两侧同挂列注）               比等
21029 后会有期 S1
extraDmgProc（true）        on_action 普攻/战技 → 附加 0.48×ATK（对方             普攻双段（1.0+0.48
                            actionModifiers 同倍率段——LC actionModifiers            附加）比等
                            镜像首挂②）
23029 那无数个春天 S1——属性段 EHR+60%（对方钉 effect_hit，无直伤消费=面板锚）
unarmoredVulnerability      after_being_hit 首段（60% 固定概率——expected 模       第 2 次命中比等；
（true）                    式 ≥0.5 恒生效同 21015 口径）挂【卸甲】易伤 10%         首击钉 S4
corneredVulnerability       【困兽】易伤 14%——**待收**（DoT 种类计数通道缺        钉 false（对方
（false）                    在案）→ 对方第二开关无条件=近似                       同灭列注）
--- 巡猎（真理医生 1305；面板 = 白值×1.28 行迹）---
20000 锋镝 S1
critBuff（true）            on_battle_start 常驻 crit_rate 12% 3回合             普攻比等
21031 重返幽冥 S1
（对方控制器全空）           on_battle_start 常驻 crit_rate 12% + 暴击命中驱散 1    我方 vs 手算单钉
                            增益（驱散无伤害读出随挂不测）                        （对方未建模列注）
21024 春水初生 S1
spdDmgBuff（true）          on_battle_start 常驻 spd_pct 8%+all_dmg 12%；          普攻比等；耗血
                            on_hp_decrease 摘除/on_turn_end 恢复                  事件后钉 S5
                            （对方开关恒开=无断档概念）
21062 于那终点再见 S1——属性段 CD+24%（对方钉 cd）
skillFuaDmgBoost（true）    常驻 dmg_skill/dmg_follow_up 24%（对方 SKILL|FUA      战技段比等
                            标签 BOOST 同值）
23056 一场谎言的终幕 S1——属性段 CR+18%（对方钉 cr）
umbraDevourerBuff（true）   常驻【影噬】atk_pct 40% + 全体易伤 20%（对方同        普攻比等
                            开关双件：ATK_P 40% + VULNERABILITY 20%——双方
                            常驻无窗口；追击计数重挂段 3 回合内不可达列注）
--- 毁灭（白厄 1408；行迹 atk_pct 0.5 白值换算两侧同）---
20002 天倾 S1
basicSkillDmgBuff（true）   on_battle_start 常驻 dmg_basic/dmg_skill 20%           普攻比等
21005 鼹鼠党欢迎你 S1
atkBuffStacks 0-3（N）      on_action 普攻/战技/终结技各叠 atk_pct 12%（三         第 2/3 发普攻
                            modifier 各 max_stack 1=「分别获取一层」）→            @1/@2 层比等
                            对方单池滑条 12%×N 同值
21038 在火的远处 S1
dmgBuff（true）             on_hp_decrease 单次超 25% 上限 → all_dmg 25% 2回合     事件后普攻比等；
                            +治疗 15% 上限+3 回合锁（对方 BOOST 恒开=无冷却     事件前钉 S6；
                            概念）；治疗=上限×15%（我方状态锚单钉）               治疗锚
21042 铭记于心的约定 S1——属性段 BE+40%（对方钉 be 面板，无直伤消费=面板锚）
crBuff（true）              on_ultimate 钩 crit_rate 15% 2回合（合成大招事件       事件后普攻比等；
                            后挂——白厄 140803 变身链重不实打，wave-1 合成先例）   事件前钉 S7
22003 忍事录•音律狩猎 S1——属性段 HP+12%（对方钉 hp 面板，无直伤消费）
cdBuff（true）              on_hp_decrease/on_hp_increase 钩 crit_dmg 18%          事件后普攻比等；
                            2回合（每回合触发锁）                                事件前钉 S8
21026 汪！散步时间！S1——属性段 ATK+10%（对方钉 atk 面板）
enemyBurnedBleeding         对灼烧/裂伤敌增伤 16%——**待收**（命中域无目标 DoT     基线比等；
（false）                    状态通道在案）→ 对方 BOOST 开关=近似                   钉 true 钉 S9
--- 同谐（刻律德菈 1412；面板 = 白值×1.18 行迹；CR 1.05 封顶 1.0 → 期望 1.5）---
20005 齐颂 S1
inBattleAtkBuff（true）     on_battle_start 常驻 all_allies atk_pct 8%             普攻比等
                            （对方 mutual FullTeam ATK_P 同值）
21036 美梦小镇大冒险 S1
basicDmgBuff（true）        on_action 普攻/战技/终结技 → all_allies 对应类型        第 2 发普攻比等；
                            增伤 12%（先摘他型=童心唯一；对方三开关               当次普攻钉 S10
                            FullTeam 标签 BOOST 恒开无窗口）
22002 为了明日的旅途 S1——属性段 ATK+16%（对方钉 atk 面板）
ultDmgBuff（true）          on_ultimate 钩 all_dmg 18% 1回合                       大招后普攻比等；
                            （对方 BOOST 恒开）                                   当次大招钉 S11
21056 追逐风的时候 S1
breakDmgBoost（true）       on_battle_start 常驻 all_allies dmg_break_dmg_boost    击破段 vs 手算
                            16%（对方 FullTeam BREAK 标签 BOOST 同值——              ×1.16；直伤
                            kind=character 无击破段不可见，23050 先例）              比等列注
22005 永远的迷境饭 S1——属性段 ATK+16%（对方钉 atk 面板）
atkStacks 0-3（N）          on_action 战技叠层 stat_exprs atk_pct 8%×N（钳 3）      第 2/3 发后普攻
                            （对方滑条 ATK_P 8%×N 同值；战技对友需队友载体）        @1/@2 层比等
21011 与行星相会 S1
alliesSameElement（true）   on_battle_start 同元素友方 all_dmg 12%（单人队         普攻比等
                            自吃；对方 wearer 元素==context 元素闸 FullTeam BOOST）
21046 芳华待灼 S1——属性段 ATK+16%（对方钉 atk 面板）
cdBuff（true）              on_battle_start 常驻 all_allies crit_dmg 16%            普攻比等（双人
                            enable_if count_team(同命途)≥2（对方 countTeamPath      同谐队）
                            同闸——队友=星期日 1313 双人队）
--- 记忆（遐蝶 1407；白值 HP 基数 0.5×HP 普攻；死龙链 140703 新蕊钉满实打）---
20022 溯忆 S1
dmgStacks 0-4（N）          忆灵回合开始叠层 stat_exprs all_dmg 8%×N（合成          普攻 @1/@4 层
                            on_turn_start 事件补发——忆灵独立行动链重不驱动）        比等
21051 天才们的问候 S1——属性段 ATK+16%（对方钉 atk 面板）
basicDmgBoost（true）       on_ultimate 钩 all_dmg 20% 3回合（hit_condition       大招后普攻比等
                            basic——对方 BASIC 标签 BOOST SelfAndMemosprite 同值）
21052 多流汗，少流泪 S1——属性段 CR+12%（对方钉 cr）
dmgBoost（true）            常驻 all_dmg 24% enable_if has_summon（对方 BOOST       召死龙后普攻比等
                            无条件=建模近似——无忆灵场两侧同灭列注）
--- 丰饶（罗刹 1203；面板 = 白值×1.28 行迹；普攻 1.0 虚数 lv6）---
21055 直到明天的明天 S1
hp50DmgBoost（true）        on_battle_start all_allies all_dmg 12% enable_if       满血普攻比等；
                            自身 HP≥50%（对方 FullTeam BOOST 开关=状态钉——        半血两侧同灭
                            半血场钉 false 两侧同灭比等）；治疗量段无伤害读出       比等
                            随挂不测
--- 存护（杰帕德 1104；Grit 防转攻 0.35×DEF 经 on_turn_start 活读）---
21039 织造命运之线 S1
（无开关）                  常驻 effect_res（无伤害读出）+ all_dmg=min            DEF 700 档比等；
                            (DEF/100×0.8%, 32%)（对方 min(32%, floor(DEF/100)      自然 DEF 档
                            ×0.8%)——连续 vs floor 阶梯口径差）                      钉 S12
21043 两个人的演唱会 S1——属性段 DEF+16%（对方钉 def 面板）
teammateShieldStacks        场上持盾角色增伤 4%/层——**待收**（持盾角色计数无       基线比等；
0-4（0）                    查询通道在案）→ 对方 BOOST 滑条=近似                    钉 4 层钉 S13
23011 她已闭上双眼 S1——属性段 HP+24%/回能（对方钉 hp 面板，无直伤消费）
hpLostDmgBuff（true）       on_hp_decrease 钩 all_allies all_dmg 9% 2回合           事件后普攻比等；
                            （对方 FullTeam BOOST 恒开）                            事件前钉 S14

===========================================================================
遗器 buff 状态映射表（基础件 p2c/p4c 两侧各自原生通道，不钉面板）
===========================================================================
（2026-09-22 收官波注记：本表 6 遗器（107/119/121/125/126/128）映射当时
只写表未实现——测试实体在 tests/test_crosscheck_equipment_batch4.py 补齐；
S 编号与数值以 batch4 为准（本表 S15/S16/S17 手写值有两处笔误：107 首次
战技比值、126 当次大招比值——batch4 实现时更正并注记原值）。下表保留
原映射存档。）
121 司铎（星期日→真理） 2pc spd_pct 6%（面板回显互对）；4pc 对友方单体战技/终结技
                   → 目标 crit_dmg 18%×N 2回合（钳 2）——对方 value 滑条=self CD
                   简化模型（官方落点=技能目标，映射表注）；星期日战技污染件
                   （增伤 30%/CR 20%）摘除回空白 slate（_clean_knots 先例）
126 船长（星期日→真理） 2pc crit_dmg 16%（p2c）；4pc 成为队友技能目标叠【助力】
                   （钳 2）→ 终结技消耗 → atk_pct 48% 1回合（当次大招不吃——
                   对方 enabled 开关恒开=建模近似）→ 大招后普攻比等；当次大招钉 S15
125 女武神（罗刹→真理） 2pc spd_pct 6%（面板回显互对）；4pc 治疗其他友方 →
                   【甘霖】spd 6%+全队 crit_dmg 15%（对方 enabled 开关=SPD_P 6%+
                   FullTeam CD 15%+BOOST 0.15 outputBuff(CD)——OutputTag.BUFF 无
                   命中承载=惰性，dmgBoostMulti 回显钉 1.0 自证）
128 隐士（杰帕德） 2pc/4pc 护盾量 +10%/+12%（对方 p2x/p4x SHIELD 标签 BOOST 同值
                   ——杰帕德 ULT_SHIELD 技种对方未注册，盾值我方 vs 手算单钉）；
                   4pc 后半「持盾友方 crit_dmg 15%」**待收**（逐目标持盾判定无通道
                   在案）→ 对方 enabled 开关 FullTeam CD 15%=近似 → 钉 S16
107 火匠（托帕）     2pc dmg_fire 10%（对方 p2c 元素门控同值）；4pc 战技增伤 12%
                   （对方 SKILL 标签 BOOST 同值）+ 终结技后下一次攻击火伤 12%
                   （on_ultimate 钩 tick_anchor on_action 消费=当次大招不吃且仅
                   下次攻击；对方 enabled 开关恒开=近似）→ 战技/大招生效后战技比等；
                   首次战技钉 S17
119 铁骑（白厄）     2pc break_effect 16%（p2c 面板回显互对+击破段 ×1.16 vs
                   手算）；4pc 击破/超击破无视防御——**待收**（类型限定无视防御
                   无通道在案）→ 对方 p4t DEF_PEN 同灭列注（kind=character 无
                   击破段不可见，23050 先例）

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注倍数，任一侧改动触红）
===========================================================================
~~S1  22004 弱点种类增伤~~ **已收官（2026-09-23，weakness_count + hit_stat_exprs
    命中域表达式值槽——7 弱点假人场三方全等 1.28）**
~~S2  21044 对减速/降防敌暴伤~~ **已收官（2026-09-23，has_stat_penalty + scoped
    crit_dmg——降防假人场三方全等 CD 0.74 档）**
S3  21061 易伤窗口（我方首段后挂=首击不吃；对方 VULNERABILITY 恒开）→ 首击 1.10
S4  23029 卸甲窗口（同 S3 族）→ 首击 1.10
S5  21024 断档窗口（我方耗血摘除/回合结束恢复；对方恒开）→ 耗血后普攻 1.12
S6  21038 阈值窗口（我方单次超 25% 上限才挂+3 回合冷却；对方恒开）→ 事件前普攻 1.25
S7  21042 大招暴击窗口（我方 on_ultimate 结算后挂=当次及之前不吃；对方恒开）
    → 事件前普攻 (1+0.32×0.873)/(1+0.17×0.873) = 1.27936/1.14841 ≈ 1.114032
S8  22003 暴伤窗口（我方事件后挂；对方恒开）→ 事件前普攻
    (1+0.17×1.053)/(1+0.17×0.873) = 1.17901/1.14841 ≈ 1.026644
S9  21026 灼烧/裂伤增伤（我方待收在案）→ 钉 true：对方/我方 = 1.16
S10 21036 童心窗口（我方 on_action 结算后挂=当次不吃；对方恒开）→ 当次普攻 1.12
S11 22002 大招增伤窗口（同 S7 族）→ 当次大招 1.18
S12 21039 防御转增伤连续 vs floor（我方 min(DEF/100×0.8%,32%) 连续近似 vs
    对方 floor(DEF/100)×0.8% 阶梯——DEF 700 整百档双方同值 5.6% 比等；
    自然 DEF 736.745625 档：对方/我方 = 1.056/1.05893965 ≈ 0.997223）
S13 21043 持盾计数增伤（我方待收在案）→ 钉 4 层：对方/我方 = 1.16
S14 23011 全队增伤窗口（我方 on_hp_decrease 结算后挂=事件前不吃；对方恒开）
    → 事件前普攻 1.09
S15 126 助力爆发窗口（对方 enabled 恒开含当次大招=建模近似；我方 on_ultimate
    结算后挂=当次不吃）→ 当次大招 1.48
S16 128 持盾暴伤（我方待收在案）→ 钉 true：对方/我方 =
    (1+0.05×0.65)/(1+0.05×0.5) = 1.0325/1.025 ≈ 1.007317
S17 107 火匠终结技火伤窗口（我方 on_ultimate 后挂=当次大招不吃且仅下次攻击；
    对方 enabled 恒开）→ 首次战技 (1+0.224+0.1+0.12+0.12)/(1+0.224+0.1+0.12)
    = 1.444/1.324 ≈ 1.090634

真病清单（本波新发现，均对方侧/external 只读报回）：
（暂无——本波 42 件数值全等或结构差如钉）

跳过清单（缺读出端/载体未立，不硬造）：
- 21046 外的同谐专光群（23003/23019/23021/23026/23034/23038/23048/23051）：
  团队 buff 链需 teammates 真队友镜像+我方队友在场——链路重，未拍（同 batch2 案）
- 22006 飞向粉色的明天（记忆）：强化普攻链绑定 8007/8008 记忆开拓者——载体
  未注册，未拍
- 21050 胜利只在朝夕间/21057 花儿不会忘记（记忆）：忆灵 ally 指向技/忆灵暴伤
  读出需忆灵行动驱动链（长夜月 1413 链）——链重未拍，下波续
- 23047 海洋为何而歌（虚无）：魂迷标记+DoT 易伤叠层——我方模板与对轴未及核对，
  未拍；24003 孤独的疗愈：终结技 DoT 增伤半**待收**在案（fixture 注释），未拍
- 23030 落日时起舞（毁灭·追击叠层）：需毁灭追击载体——白厄无追击读出（batch2 案）
- 23040 让告别更美一些（记忆·遐蝶专光）：忆灵多实体链重（batch2 案）
- 23042/23052（记忆 5star）：忆灵指向技链重，未拍
- 23023 命运从未公平（存护）：盲注=护盾暴击链——需护盾量读出+砂金载体，未拍
- 23013/23017/23008（丰饶 5star）：治疗/团队读出链（batch2 案）
- 24002 记忆的质料（存护·护盾减伤）：无伤害读出（batch2 案）
- 20001 物穰/21000 术后对话/21007 同一种心情/21014 此时恰好/21021 等价交换/
  21028 暖夜/21035 何物为真/22001 嘿我在这儿（丰饶 3/4 星）：纯治疗/回能——
  无伤害读出，未拍（治疗量对拍读出端=driver heal 输出，下波续）
- 20003 琥珀/20004 幽邃/20008 嘉果/20009 乐圮/20010 戍御/20012 轮契/20013 灵钥/
  20014 相抗/20015 蕃息/20017 开疆/20019 调和/20021 焚影/20023 嗤笑/20024 残泪
  （3 星生存/速度/回能/命中件+20009 我方 hooks 空）：无伤害读出，未拍
- 21002 余生第一天/21009 朗道/21016 宇宙市场/21023 我们是地火（存护 4 星）：
  减伤/防御无伤害读出，未拍；21004 记忆中的模样/21018 舞舞舞/21025 过往未来/
  21032 镂月裁云（我方 hooks 空）/21045 谐乐静默之后/21047 黑夜如影随行/
  21048 梦的蒙太奇/21054 故事的下一页（治疗）：无伤害读出或未收编，未拍
- 5 星残部：23033 忍法帖（BE 面板件无直伤）/23051 纵然山河万程（同谐专光群）/
  23059 灼尽炼狱的新骸（我方 hp 段已挂、伤害段对轴未及）/23063/23064 无模板/
  21066/22008 无模板/AStarThatLightsTheNight/FlickeringStars/IAmAsYouBehold
  无模板（我方模板缺，不硬造）
- 遗器残部：101 过客（治疗）/103 圣骑士（护盾——读出端 driver 无盾输出对拍
  缺）/106 铁卫（减伤）/118 钟表匠（FullTeam BE 需 teammates 镜像）/124 诗人/
  130 卜者（速度档 driver c.a 缺口在案——报回 owner）/129 魔法少女（欢愉
  DEF_PEN——欢愉载体链重）/132 名冶（我方 data 模板 hooks 空——生成器未收编）
- 位面饰品 301-328：driver p2t 未接入（在案）——全部未拍
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.state import Modifier

# 同前几波：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    AC_ATK, HT_ATK, Z, _POLICY, _cast, _dummy, _hit_amounts, _inject, _make_logged,
    _stage,
)
from tests.test_crosscheck_equipment import (  # noqa: F401
    RT_ATK, RT_CD, RT_CR, RT_DEF, RT_HP, RT_SPD, ZR, _acheron_opt, _clean_knots,
    _compiled, _herta_opt, _inject_debuffs, _member_build, _ratio_opt, _rt_panel, _ult,
)
from tests.test_crosscheck_equipment_batch import (  # noqa: F401
    _eff, _fragile_toughness, _kill_enemies, _lc, _low_hp_enemy, _pha_opt, _relic,
)
from tests.test_crosscheck_equipment_batch2 import (  # noqa: F401
    _break_amounts, _emit, _hits_of, _member_build2,
)
from tests.test_crosscheck_team_phainon import (  # noqa: F401
    CY_ATK, CY_ATK_W, CY_WIND, PH_ATK, PH_CR, PH_CD, PH_HP, Z_CY, Z_PH,
    _opt_cerydra, _ult_at,
)
from tests.test_crosscheck_team_remembrance import (  # noqa: F401
    CA_ATK, CA_CD, CA_CR, CA_DEF, CA_HP, CA_Q, CA_SPD, Z_CA_CRIT, _fire_ult,
    _opt_castorice,
)
from tests.test_crosscheck_legacy_1300 import (  # noqa: F401
    LC_ATK, LC_ATK_W, LC_CZ, LC_DEF, LC_HP, LC_SPD, _opt_luocha,
)
from tests.test_crosscheck_legacy_1000 import (  # noqa: F401
    GP_ATK_W, GP_CZ, GP_DEF, GP_DEF_W, GP_HP, GP_ICE, GP_SPD, _opt_gepard,
)
from tests.test_crosscheck_legacy_1200 import (  # noqa: F401
    TP_ATK, TP_ATK_W, TP_CZ, TP_FIRE, _opt_topaz,
)

# ---------------------------------------------------------------------------
# 口径常数（本批新增；载体既有常数从各波文件复用）
# ---------------------------------------------------------------------------

# 光锥白值（fixture base_stats 终审值；仅 atk 进手算锚，hp/def 本波不进伤害式）
LC20000_ATK = 317.52
LC20002_ATK = 370.44000000000005
LC20005_ATK = 317.52
LC20018_ATK = 317.52
LC20022_ATK = 423.36
LC20022_HP = 635.04
LC21005_ATK = 476.28
LC21011_ATK = 423.36
LC21024_ATK = 476.28
LC21026_ATK = 476.28
LC21029_ATK = 529.2
LC21031_ATK = 529.2
LC21034_ATK = 529.2
LC21036_ATK = 423.36
LC21038_ATK = 476.28
LC21039_ATK = 370.44000000000005
LC21040_ATK = 476.28
LC21041_ATK = 476.28
LC21042_ATK = 476.28
LC21043_ATK, LC21043_DEF = 370.44000000000005, 463.04999999999995
LC21044_ATK = 476.28
LC21046_ATK = 423.36
LC21051_ATK = 476.28
LC21051_HP = 952.56
LC21052_ATK = 529.2
LC21052_HP = 1058.4
LC21055_ATK = 476.28
LC21056_ATK = 476.28
LC21060_ATK = 529.2
LC21061_ATK = 529.2
LC21062_ATK = 529.2
LC22002_ATK = 476.28
LC22003_ATK = 476.28
LC22004_ATK = 476.28
LC22005_ATK = 476.28
LC23011_ATK = 423.36
LC23027_ATK = 582.1199999999999
LC23029_ATK = 582.1199999999999
LC23037_ATK = 635.04
LC23056_ATK = 635.04

# 击破基准（我方口径：3767.5533×scaling×(0.5+maxToughness/40)×def0.5——
# 对方 kind=character 不出击破段，击破段一律我方 vs 手算单钉）
BREAK_BASE_10 = 3767.5533 * (0.5 + 10 / 40) * 0.5          # scaling=1.0，韧性 10
BREAK_BASE_10_PHY = BREAK_BASE_10 * 2.0                    # 物理 scaling=2.0
BREAK_BASE_10_WIND = BREAK_BASE_10 * 1.5                   # 风 scaling=1.5


# ---------------------------------------------------------------------------
# 对方侧场景模子（装备/队友扩展版；载体本体条件开关从各波文件复用）
# ---------------------------------------------------------------------------

def _cy_opt(action: str, *, lc_atk: float = 0.0, equipment=None,
            extra_attacker=None, teammates=None, cond=None):
    """刻律德菈对方场景（_opt_cerydra 装备/队友扩展版——本波同谐光锥载体；
    LC 白值并入 base（ATK_P 换算基数），行迹 18% 钉面板（对方无此角色条件件
    通道——与 _opt_cerydra 同口径））."""
    c = {"spdBuff": True, "crBuff": True, "atkToCd": True,
         "e2DmgBoost": True, "e4UltDmg": True, "e6Buffs": True}
    c.update(cond or {})
    white = CY_ATK_W + lc_atk
    base = {"atk": white, "hp": 1358.2800000000002, "def": 485.1, "spd": 99}
    sc = {"kind": "character", "character_id": "1412", "eidolon": 0,
          "action": action, "element": "wind", "conditionals": c,
          "base": base,
          "attacker": {**base, "atk": white * 1.18,
                       "hp": 1358.2800000000002 * 1.1,
                       "cr": 0.05, "cd": 0.5, "element_boost": CY_WIND,
                       **(extra_attacker or {})},
          "self_path": "Harmony",
          "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                    "count": 1}}
    if teammates is not None:
        sc["teammates"] = teammates
    if equipment is not None:
        sc["equipment"] = equipment
    return sc


def _ca_opt(action: str, *, lc_hp: float = 0.0, equipment=None, cond=None,
            teammates=None, extra_attacker=None):
    """遐蝶对方场景（_opt_castorice 装备扩展版；死龙在场场 memospriteActive/
    teamDmgBoost 钉 true 为默认——遗世冥域 res_pen 0.2+怒啸 0.1 两侧同；
    LC 生命白值并入 hp 面板——普攻 0.5×HP 基数消费通道）."""
    c = {"memospriteActive": True, "teamDmgBoost": True}
    sc = _opt_castorice(action, cond=c, teammates=teammates)
    sc["base"]["hp"] = CA_HP + lc_hp
    sc["attacker"]["hp"] = CA_HP + lc_hp
    sc["attacker"].update(extra_attacker or {})
    if equipment is not None:
        sc["equipment"] = equipment
    return sc


def _gp_opt(action: str, *, equipment=None, extra_attacker=None, extra_base=None):
    """杰帕德对方场景（_opt_gepard 装备扩展版；Grit 防转攻对方 dynamic
    conversion 读钉死 def 面板——def 区改动经 base/attacker 双写）."""
    sc = _opt_gepard(action)
    sc["attacker"].update(extra_attacker or {})
    sc["base"].update(extra_base or {})
    if equipment is not None:
        sc["equipment"] = equipment
    return sc


def _lc55_opt(action: str, *, lc_atk: float = 0.0, equipment=None,
              extra_attacker=None):
    """罗刹对方场景（_opt_luocha 装备扩展版；LC 白值并入 base/attacker 双写）."""
    sc = _opt_luocha(action)
    sc["base"]["atk"] = LC_ATK_W + lc_atk
    sc["attacker"].update({"atk": (LC_ATK_W + lc_atk) * 1.28,
                           **(extra_attacker or {})})
    if equipment is not None:
        sc["equipment"] = equipment
    return sc


def _sunday_skill(eng, target: str):
    """星期日 131302 指队友 → 摘除战技/天赋污染件（增伤 30%/CR 20%）回空白
    slate（_clean_knots 先例——121/126 只留套装件）."""
    _cast(eng, "1313", "131302", target=target)
    for mid in ("SUNDAY_SKILL_DMG", "SUNDAY_TALENT_CR"):
        eng.state.actors[target].modifiers.pop(mid, None)


# ===========================================================================
# 光锥对拍——智识载体（黑塔 1013）
# ===========================================================================

class TestLC21034PeacefulDay:
    """今日亦是和平的一日 S1（黑塔）：常驻增伤 min(能量上限,160)×0.2%/点 = 22%."""

    def test_max_energy_dmg(self, optimizer_driver):
        """黑塔能量上限 110 → 增伤 22%（min(110,160)×0.2%——对方读 base_energy
        场景槽同式）."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="21034"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC21034_ATK
        sc = _herta_opt(
            "basic", atk=white,
            equipment=_lc("21034", "Erudition", {"maxEnergyDmgBoost": True}))
        sc["base_energy"] = 110.0
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 1.0 * white * Z * 1.22
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 22%（110 点×0.2%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21040CosmosFell:
    """银河沦陷日 S1（黑塔）：常驻攻击 16%（属性段）+ 暴伤 20%（待收——施放攻击后
    ≥2 被击目标带弱点才挂，has_weakness 双缺口在案）."""

    def test_permanent_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="21040"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC21040_ATK
        atk = white * 1.16                       # LC 属性段（对方钉面板）
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white, extra_attacker={"atk": atk},
            equipment=_lc("21040", "Erudition", {"cdBuffActive": False})))

        hand = 1.0 * atk * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻攻击 16% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_cd_divergence(self, optimizer_driver):
        """S12 结构差：暴伤 20%（我方待收在案）→ 钉 true：对方/我方 =
        (1+0.05×0.7)/1.025 = 1.035/1.025 ≈ 1.009756."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="21040"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")[0]
        white = HT_ATK + LC21040_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white, extra_attacker={"atk": white * 1.16},
            equipment=_lc("21040", "Erudition", {"cdBuffActive": True})))

        assert ours == pytest.approx(1.0 * white * 1.16 * Z, rel=REL_TOL), (
            "我方无暴伤段 vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.035 / 1.025, rel=REL_TOL)


class TestLC21060WheatDream:
    """氤氲麦香的梦 S1（黑塔）：常驻 CR 12%（属性段）+ 终结技/追击增伤 24%."""

    def test_ult_fua_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="21060"), "ice"))
        _ult(eng, "1013", "101303", 120.0)
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC21060_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "ult", atk=white, extra_attacker={"cr": 0.17},
            equipment=_lc("21060", "Erudition", {"ultFuaDmgBoost": True})))

        hand = 2.0 * white * 0.5 * 0.9 * (1 + 0.17 * 0.5) * 1.24
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方大招（+24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC22004CosmicEnterprise:
    """宇宙大生意 S1（黑塔）：常驻攻击 8%（属性段）+ 弱点种类增伤 4%/种（待收）."""

    def test_permanent_atk(self, optimizer_driver):
        """常驻攻击 8% + 1 弱点增伤 4%（2026-09-23 收编后常驻件按假人现场弱点计数
        ——匹配弱点假人=1 种 → 1.04 池，对方 weaknessTypes=1 同钉）."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="22004"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC22004_ATK
        atk = white * 1.08
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white, extra_attacker={"atk": atk},
            equipment=_lc("22004", "Erudition", {"weaknessTypes": 1})))

        hand = 1.0 * atk * Z * 1.04
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 8%+1 弱点 4% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_weakness_types_divergence(self, optimizer_driver):
        """S1 已收官（2026-09-23）：弱点种类增伤——weakness_count 宿主函数 +
        hit_stat_exprs 命中域表达式值槽收编（LC_22004_WEAKNESS 常驻件
        all_dmg=param_2×min(weakness_count,7)）。7 弱点假人场双方同池 1.28，三方全等."""
        seven = [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
                  "def": 1000, "max_toughness": 9999,
                  "weakness": ["physical", "fire", "ice", "thunder", "wind",
                               "quantum", "imaginary"]}]
        eng, log = _make_logged(_compiled(_member_build("1013", lc="22004"), "ice",
                                          enemies=seven))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")[0]
        white = HT_ATK + LC22004_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white, extra_attacker={"atk": white * 1.08},
            equipment=_lc("22004", "Erudition", {"weaknessTypes": 7})))

        hand = 1.0 * white * 1.08 * Z * 1.28
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方 7 弱点场（1.28 池）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


# ===========================================================================
# 光锥对拍——虚无载体（黄泉 1308）
# ===========================================================================

class TestLC20018HiddenShadow:
    """匿影 S1（黄泉）：战技闩 → 下一次普攻首段附加 0.6×ATK."""

    def test_skill_latch_additional(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="20018"), "thunder"))
        _clean_knots(eng)
        _cast(eng, "1308", "130802")               # 战技 → 闩
        log.clear()
        _cast(eng, "1308", "130801")               # 普攻 → 1.0 + 附加 0.6
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC20018_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white,
            equipment=_lc("20018", "Nihility", {"basicAtkBuff": True})))

        hand = [1.0 * white * Z, 0.6 * white * Z]
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方普攻+附加段 vs 手算"
        assert [h["damage"] for h in theirs["hits"]] == pytest.approx(hand, rel=REL_TOL)
        assert ours == pytest.approx(
            [h["damage"] for h in theirs["hits"]], rel=REL_TOL), "双方逐段互对"


class TestLC21044BoundlessChoreo:
    """无边曼舞 S1（黄泉）：常驻 CR 8%（属性段）+ 对减速/降防敌暴伤 24%（待收）."""

    def test_permanent_crit(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="21044"), "thunder"))
        _clean_knots(eng)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC21044_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"cr": 0.13},
            equipment=_lc("21044", "Nihility", {"enemyDefReducedSlowed": False})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + 0.13 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CR 8% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_debuffed_cd_divergence(self, optimizer_driver):
        """S2 已收官（2026-09-23）：对减速/降防敌暴伤 24%——has_stat_penalty 宿主函数
        （stat_effects 负值扫描非 buff 件）+ scoped crit_dmg 收编（LC_21044_CRIT_DMG
        hit_condition 四键析取）。减速假人（spd_pct -20% 注入件——防御区不动隔离
        单因子）双方 CD 池同 +24%，三方全等."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="21044"), "thunder"))
        _clean_knots(eng)
        eng.state.actors["e1"].modifiers["XC_SLOW"] = Modifier(
            modifier_id="XC_SLOW", name="对拍减速", modifier_type="debuff",
            duration=0, dispellable=False, stat_effects={"spd_pct": -0.2})
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")[0]
        white = AC_ATK + LC21044_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"cr": 0.13},
            equipment=_lc("21044", "Nihility", {"enemyDefReducedSlowed": True})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + 0.13 * 0.74)
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方降防场（CD 0.5+0.24）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


class TestLC21061HolidayThermae:
    """假日浴场大冒险 S1（黄泉）：常驻增伤 16%（属性段）+ 首段挂易伤 10%."""

    def test_vulnerability_window(self, optimizer_driver):
        """首击钉 S3（我方挂标在命中后=首击不吃；对方 VULNERABILITY 恒开）→
        首击 1.10；第 2 击双方比等."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="21061"), "thunder"))
        _clean_knots(eng)
        _cast(eng, "1308", "130801")
        first = _hit_amounts(log, source="1308")[0]
        white = AC_ATK + LC21061_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"dmg_boost": 0.16},
            equipment=_lc("21061", "Nihility", {"vulnerability": True})))

        assert first == pytest.approx(1.0 * white * Z * 1.16, rel=REL_TOL), (
            "我方首击（无易伤）vs 手算")
        assert theirs["hits"][0]["damage"] / first == pytest.approx(1.10, rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(
            1.10, rel=REL_TOL)

        _cast(eng, "1308", "130801")
        second = _hit_amounts(log, source="1308")[1]
        hand = 1.0 * white * Z * 1.16 * 1.10
        assert second == pytest.approx(hand, rel=REL_TOL), "我方第 2 击（易伤自吃）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21041ItsShowtime:
    """好戏开演 S1（黄泉）：减益叠层增伤 6%×3 + EHR≥80% 攻击 20%."""

    def test_trick_stacks_and_ehr_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="21041"), "thunder"))
        _clean_knots(eng)
        _inject(eng, "1308", "XC_EHR", {"effect_hit": 0.9})   # EHR 闸两侧同挂（列注）
        _inject_debuffs(eng, "e1", 3, source="1308", via_engine=True)
        assert "LC_21041_TRICK" in eng.state.actors["1308"].modifiers
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC21041_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"effect_hit": 0.9},
            equipment=_lc("21041", "Nihility", {"trickStacks": 3})))

        hand = 1.0 * white * 1.2 * Z * 1.18
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 3 层戏法+20% 攻击 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21029WeWillMeetAgain:
    """后会有期 S1（黄泉）：普攻/战技附加 0.48×ATK."""

    def test_additional_on_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="21029"), "thunder"))
        _clean_knots(eng)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC21029_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white,
            equipment=_lc("21029", "Nihility", {"extraDmgProc": True})))

        hand = [1.0 * white * Z, 0.48 * white * Z]
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方普攻+附加段 vs 手算"
        assert [h["damage"] for h in theirs["hits"]] == pytest.approx(hand, rel=REL_TOL)
        assert ours == pytest.approx(
            [h["damage"] for h in theirs["hits"]], rel=REL_TOL), "双方逐段互对"


class TestLC23029ThoseManySprings:
    """那无数个春天 S1（黄泉）：常驻 EHR 60%（属性段）+ 首段挂【卸甲】易伤 10%."""

    def test_unarmored_window(self, optimizer_driver):
        """首击钉 S4（同 S3 族——60% 固定概率 expected ≥0.5 恒生效）；第 2 击比等."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23029"), "thunder"))
        _clean_knots(eng)
        _cast(eng, "1308", "130801")
        first = _hit_amounts(log, source="1308")[0]
        white = AC_ATK + LC23029_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white,
            equipment=_lc("23029", "Nihility",
                          {"unarmoredVulnerability": True,
                           "corneredVulnerability": False})))

        assert first == pytest.approx(1.0 * white * Z, rel=REL_TOL), (
            "我方首击（无卸甲）vs 手算")
        assert theirs["hits"][0]["damage"] / first == pytest.approx(1.10, rel=REL_TOL)

        _cast(eng, "1308", "130801")
        second = _hit_amounts(log, source="1308")[1]
        hand = 1.0 * white * Z * 1.10
        assert second == pytest.approx(hand, rel=REL_TOL), "我方第 2 击（卸甲自吃）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# 光锥对拍——巡猎载体（真理医生 1305；面板 = 白值×1.28 行迹）
# ===========================================================================

class TestLC20000Arrows:
    """锋镝 S1（真理医生）：常驻暴击率 12%（3 回合——无回合流逝恒在）."""

    def test_crit_buff(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="20000"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC20000_ATK,
            equipment=_lc("20000", "Hunt", {"critBuff": True})))

        hand = 1.0 * _rt_panel(LC20000_ATK) * 0.5 * 0.9 * (1 + 0.29 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CR 12% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1305")["crit_rate"] == pytest.approx(0.29, rel=REL_TOL)


class TestLC21031ReturnToDarkness:
    """重返幽冥 S1（真理医生）：常驻暴击率 12%（对方控制器全空=未建模，我方 vs
    手算单钉；暴击驱散 1 增益无伤害读出随挂不测）."""

    def test_crit_ours_vs_hand(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21031"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21031_ATK,
            equipment=_lc("21031", "Hunt", {})))

        hand = 1.0 * _rt_panel(LC21031_ATK) * 0.5 * 0.9 * (1 + 0.29 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CR 12% vs 手算"
        assert _eff(eng, "1305")["crit_rate"] == pytest.approx(0.29, rel=REL_TOL)
        base = 1.0 * _rt_panel(LC21031_ATK) * ZR
        assert theirs["hits"][0]["damage"] == pytest.approx(base, rel=REL_TOL), (
            "对方控制器全空——基线（无暴击段）在案非病（21033 先例）")
        assert ours[0] / theirs["hits"][0]["damage"] == pytest.approx(
            (1 + 0.29 * 0.5) / (1 + 0.17 * 0.5), rel=REL_TOL)


class TestLC21024RiverFlowsInSpring:
    """春水初生 S1（真理医生）：常驻速度 8%+增伤 12%；耗血摘除/回合结束恢复."""

    def test_dmg_buff(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21024"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21024_ATK,
            equipment=_lc("21024", "Hunt", {"spdDmgBuff": True})))

        hand = 1.0 * _rt_panel(LC21024_ATK) * ZR * 1.12
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 12% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_drain_break_window(self, optimizer_driver):
        """S5 结构差：耗血摘除（对方开关恒开=无断档概念）→ 耗血后普攻 1.12；
        回合结束恢复后回等."""
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21024"), "imaginary"))
        _emit(eng, "on_hp_decrease", {"target": "1305", "reason": "drain"})
        assert "LC_21024_SPRING_WATER" not in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")[0]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21024_ATK,
            equipment=_lc("21024", "Hunt", {"spdDmgBuff": True})))

        assert ours == pytest.approx(1.0 * _rt_panel(LC21024_ATK) * ZR, rel=REL_TOL), (
            "我方断档期普攻（无增伤）vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.12, rel=REL_TOL)

        _emit(eng, "on_turn_end", {"actor": "1305"})   # 恢复重挂
        _cast(eng, "1305", "130501")
        restored = _hit_amounts(log, source="1305")[1]
        assert restored == pytest.approx(
            1.0 * _rt_panel(LC21024_ATK) * ZR * 1.12, rel=REL_TOL), "恢复后回等"


class TestLC21062SeeYouAtTheEnd:
    """于那终点再见 S1（真理医生）：常驻 CD 24%（属性段）+ 战技/追击增伤 24%."""

    def test_skill_fua_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21062"), "imaginary"))
        _cast(eng, "1305", "130502")
        ours = _hits_of(log, source="1305", action_type="skill")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "skill", lc_atk=LC21062_ATK, cd=RT_CD + 0.24,
            equipment=_lc("21062", "Hunt", {"skillFuaDmgBoost": True})))

        hand = 1.5 * _rt_panel(LC21062_ATK) * 0.5 * 0.9 * (1 + RT_CR * 0.74) * 1.24
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方战技（+24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23056FinaleOfALie:
    """一场谎言的终幕 S1（真理医生）：常驻 CR 18%（属性段）+【影噬】攻击 40%+
    全体易伤 20%（常驻无窗口；追击计数重挂段 3 回合内不可达列注）."""

    def test_umbra_devourer(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="23056"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        white = RT_ATK + LC23056_ATK
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC23056_ATK, cr=RT_CR + 0.18,
            equipment=_lc("23056", "Hunt", {"umbraDevourerBuff": True})))

        hand = (1.0 * white * (1.28 + 0.40) * 0.5 * 0.9
                * (1 + (RT_CR + 0.18) * RT_CD) * 1.2)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方影噬+易伤普攻 vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(
            1.2, rel=REL_TOL)


# ===========================================================================
# 光锥对拍——毁灭载体（白厄 1408；行迹 atk_pct 0.5 白值换算两侧同）
# ===========================================================================

class TestLC20002CollapsingSky:
    """天倾 S1（白厄）：常驻普攻/战技增伤 20%."""

    def test_basic_skill_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="20002"), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC20002_ATK,
            equipment=_lc("20002", "Destruction", {"basicSkillDmgBuff": True})))

        hand = 1.0 * (PH_ATK + LC20002_ATK) * 1.5 * Z_PH * 1.2
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 20% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21005MolesWelcomeYou:
    """鼹鼠党欢迎你 S1（白厄）：普攻/战技/终结技各叠攻击 12%（分别计层）."""

    def test_atk_stacks(self, optimizer_driver):
        """第 1 发当次不吃（0 层双方比等）；第 2 发 @1 / 技能后第 3 发 @2 比等."""
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21005"), "physical"))
        white = PH_ATK + LC21005_ATK
        z = 0.5 * 0.9 * (1 + PH_CR * PH_CD)
        _cast(eng, "1408", "140801")           # 第 1 发：当次无层（对方滑条 0）
        _cast(eng, "1408", "140801")           # 第 2 发：@1
        _cast(eng, "1408", "140802")           # 战技（挂层用，伤害不比对）
        _cast(eng, "1408", "140801")           # 第 3 发：@2
        basics = _hits_of(log, source="1408", action_type="basic")
        assert len(basics) == 3

        for n, got in ((0, basics[0]), (1, basics[1]), (2, basics[2])):
            theirs = run_optimizer(optimizer_driver, _pha_opt(
                "basic", lc_atk=LC21005_ATK,
                equipment=_lc("21005", "Destruction", {"atkBuffStacks": n})))
            hand = 1.0 * white * (1.5 + 0.12 * n) * z
            assert got == pytest.approx(hand, rel=REL_TOL), f"我方普攻 @{n} 层 vs 手算"
            assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
            assert got == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
                f"双方互对 @{n} 层")


class TestLC21038FlamesAfar:
    """在火的远处 S1（白厄）：单次耗血超 25% 上限 → 增伤 25% 2 回合+治疗 15%+
    3 回合冷却锁."""

    def test_threshold_dmg_buff(self, optimizer_driver):
        """事件前钉 S6（对方 BOOST 恒开=无阈值/冷却概念）→ 1.25；事件后比等+
        治疗锚（治疗=上限×15%，我方状态锚单钉——对方未建模）."""
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21038"), "physical"))
        mh = _eff(eng, "1408")["hp"]
        eng.state.actors["1408"].current_hp = 1000.0
        _cast(eng, "1408", "140801")
        first = _hit_amounts(log, source="1408")[0]
        white = PH_ATK + LC21038_ATK
        z = 0.5 * 0.9 * (1 + PH_CR * PH_CD)
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC21038_ATK,
            equipment=_lc("21038", "Destruction", {"dmgBuff": True})))

        assert first == pytest.approx(1.0 * white * 1.5 * z, rel=REL_TOL), (
            "我方阈值前普攻（无增伤）vs 手算")
        assert theirs["hits"][0]["damage"] / first == pytest.approx(1.25, rel=REL_TOL)

        _emit(eng, "on_hp_decrease",
              {"target": "1408", "reason": "drain", "amount": 0.3 * mh})
        assert "LC_21038_DMG_BOOST" in eng.state.actors["1408"].modifiers
        assert eng.state.actors["1408"].current_hp == pytest.approx(
            1000.0 + 0.15 * mh, rel=REL_TOL), "治疗锚：上限×15%"
        _cast(eng, "1408", "140801")
        second = _hit_amounts(log, source="1408")[1]
        hand = 1.0 * white * 1.5 * z * 1.25
        assert second == pytest.approx(hand, rel=REL_TOL), "我方事件后普攻（+25%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21042IndeliblePromise:
    """铭记于心的约定 S1（白厄）：常驻 BE 40%（属性段面板锚）+ 终结技后暴击 15%."""

    def test_ult_crit_buff(self, optimizer_driver):
        """合成大招事件（140803 变身链重不实打——wave-1 合成先例）→ 暴击比等；
        事件前钉 S7（对方 CR 恒开）→ (1+0.32×0.873)/(1+0.17×0.873) ≈ 1.114032."""
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21042"), "physical"))
        _cast(eng, "1408", "140801")
        first = _hit_amounts(log, source="1408")[0]
        white = PH_ATK + LC21042_ATK
        z = 0.5 * 0.9
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC21042_ATK, extra_attacker={"be": 0.28},
            equipment=_lc("21042", "Destruction", {"crBuff": True})))

        assert first == pytest.approx(
            1.0 * white * 1.5 * z * (1 + PH_CR * PH_CD), rel=REL_TOL), (
            "我方事件前普攻（无暴击段）vs 手算")
        assert theirs["hits"][0]["damage"] / first == pytest.approx(
            (1 + (PH_CR + 0.15) * PH_CD) / (1 + PH_CR * PH_CD), rel=REL_TOL)

        _emit(eng, "on_ultimate", {"source": "1408", "action": "140803"})
        assert "LC_21042_CRIT_RATE_MOD" in eng.state.actors["1408"].modifiers
        _cast(eng, "1408", "140801")
        second = _hit_amounts(log, source="1408")[1]
        hand = 1.0 * white * 1.5 * z * (1 + (PH_CR + 0.15) * PH_CD)
        assert second == pytest.approx(hand, rel=REL_TOL), "我方事件后普攻（+15% 暴击）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC22003NinjaRecord:
    """忍事录•音律狩猎 S1（白厄）：常驻 HP 12%（属性段面板锚）+ 耗血/回血后暴伤
    18%（每回合触发锁）."""

    def test_hp_change_cd_buff(self, optimizer_driver):
        """事件前钉 S8（对方 CD 恒开）→ (1+0.17×1.053)/(1+0.17×0.873) ≈ 1.026644；
        事件后比等."""
        eng, log = _make_logged(_compiled(_member_build("1408", lc="22003"), "physical"))
        _cast(eng, "1408", "140801")
        first = _hit_amounts(log, source="1408")[0]
        white = PH_ATK + LC22003_ATK
        z = 0.5 * 0.9
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC22003_ATK, extra_attacker={"hp": PH_HP * 1.12},
            equipment=_lc("22003", "Destruction", {"cdBuff": True})))

        assert first == pytest.approx(
            1.0 * white * 1.5 * z * (1 + PH_CR * PH_CD), rel=REL_TOL), (
            "我方事件前普攻（无暴伤段）vs 手算")
        assert theirs["hits"][0]["damage"] / first == pytest.approx(
            (1 + PH_CR * (PH_CD + 0.18)) / (1 + PH_CR * PH_CD), rel=REL_TOL)

        _emit(eng, "on_hp_decrease", {"target": "1408", "reason": "drain"})
        assert "LC_22003_CRIT_DMG" in eng.state.actors["1408"].modifiers
        _cast(eng, "1408", "140801")
        second = _hit_amounts(log, source="1408")[1]
        hand = 1.0 * white * 1.5 * z * (1 + PH_CR * (PH_CD + 0.18))
        assert second == pytest.approx(hand, rel=REL_TOL), "我方事件后普攻（+18% 暴伤）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21026WoofWalkTime:
    """汪！散步时间！S1（白厄）：常驻攻击 10%（属性段）+ 对灼烧/裂伤敌增伤 16%
    （待收——命中域无目标 DoT 状态通道在案）."""

    def test_permanent_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21026"), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC21026_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC21026_ATK, extra_attacker={"atk": white * 1.1},
            equipment=_lc("21026", "Destruction", {"enemyBurnedBleeding": False})))

        hand = 1.0 * white * 1.6 * Z_PH
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻攻击 10% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_burn_bleed_divergence(self, optimizer_driver):
        """S9 已收官（2026-09-23）：灼烧/裂伤增伤 16%——dot_count 宿主函数（dot 件
        严口径）+ scoped all_dmg 收编（LC_21026_DOT_DMG）。灼烧假人（dot 件注入）
        双方增伤池同 1.16，三方全等."""
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21026"), "physical"))
        eng.state.actors["e1"].modifiers["XC_BURN"] = Modifier(
            modifier_id="XC_BURN", name="对拍灼烧", modifier_type="dot",
            duration=0, dispellable=False, dot_element="fire", dot_ratio=0.0)
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")[0]
        white = PH_ATK + LC21026_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC21026_ATK, extra_attacker={"atk": white * 1.1},
            equipment=_lc("21026", "Destruction", {"enemyBurnedBleeding": True})))

        hand = 1.0 * white * 1.6 * Z_PH * 1.16
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方灼烧场（1.16 池）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


# ===========================================================================
# 光锥对拍——同谐载体（刻律德菈 1412；面板 = 白值×1.18 行迹；
# CR 1.05 封顶 1.0 → 期望恒 1.5；双人队队友=星期日 1313 同谐占位）
# ===========================================================================

def _team_build2(wearer: str, lc: str, teammate: str):
    """双成员 build（队友只承事件不出手——23014 先例）."""
    return {"build": {"team": [
        {"character_template": wearer, "level": 80,
         "light_cone_template": lc, "light_cone": {"superimposition": 1}},
        {"character_template": teammate, "level": 80},
    ], "policy": _POLICY}}


class TestLC20005Chorus:
    """齐颂 S1（刻律德菈）：常驻全队攻击 8%（含自身）."""

    def test_team_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1412", lc="20005"), "wind"))
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        white = CY_ATK_W + LC20005_ATK
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", lc_atk=LC20005_ATK,
            equipment=_lc("20005", "Harmony", {"inBattleAtkBuff": True})))

        hand = 1.0 * white * 1.26 * (1 + CY_WIND) * Z_CY
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方全队攻击 8% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(white * 1.26, rel=REL_TOL)


class TestLC21036DreamvilleAdventure:
    """美梦小镇大冒险 S1（刻律德菈）：行动后全队对应类型增伤 12%（童心唯一）."""

    def test_basic_dmg_window(self, optimizer_driver):
        """当次普攻钉 S10（我方结算后挂=当次不吃；对方恒开）→ 1.12；第 2 发比等."""
        eng, log = _make_logged(_compiled(_member_build("1412", lc="21036"), "wind"))
        white = CY_ATK_W + LC21036_ATK
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", lc_atk=LC21036_ATK,
            equipment=_lc("21036", "Harmony", {"basicDmgBuff": True,
                                               "skillDmgBuff": False,
                                               "ultDmgBuff": False})))
        _cast(eng, "1412", "141201")
        first = _hit_amounts(log, source="1412")[0]
        assert first == pytest.approx(1.0 * white * 1.18 * (1 + CY_WIND) * Z_CY,
                                      rel=REL_TOL), "我方当次普攻（无童心）vs 手算"
        # S10：对方 12% 与我方行迹风伤同池加算 → 1.344/1.224（空池才是 1.12）
        assert theirs["hits"][0]["damage"] / first == pytest.approx(
            (1 + CY_WIND + 0.12) / (1 + CY_WIND), rel=REL_TOL)

        _cast(eng, "1412", "141201")
        second = _hit_amounts(log, source="1412")[1]
        hand = 1.0 * white * 1.18 * (1 + CY_WIND + 0.12) * Z_CY
        assert second == pytest.approx(hand, rel=REL_TOL), "我方第 2 发（童心·普攻）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC22002ForTomorrowsJourney:
    """为了明日的旅途 S1（刻律德菈）：常驻攻击 16%（属性段）+ 终结技后增伤 18%."""

    def test_ult_dmg_window(self, optimizer_driver):
        """当次大招钉 S11（同 S7 族）→ 1.18；大招后普攻比等."""
        eng, log = _make_logged(_compiled(_member_build("1412", lc="22002"), "wind"))
        white = CY_ATK_W + LC22002_ATK
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "ult", lc_atk=LC22002_ATK, extra_attacker={"atk": white * 1.34},
            equipment=_lc("22002", "Harmony", {"ultDmgBuff": True})))
        _ult_at(eng, "1412", "141203", 130.0, "1412")
        ours = _hit_amounts(log, source="1412")
        assert ours[0] == pytest.approx(
            2.4 * white * 1.34 * (1 + CY_WIND) * Z_CY, rel=REL_TOL), (
            "我方当次大招（无增伤段）vs 手算")
        # S11：对方 18% 与我方行迹风伤同池加算 → 1.404/1.224（空池才是 1.18）
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            (1 + CY_WIND + 0.18) / (1 + CY_WIND), rel=REL_TOL)

        _cast(eng, "1412", "141201")
        basic = _hit_amounts(log, source="1412")[1]
        hand = 1.0 * white * 1.34 * (1 + CY_WIND + 0.18) * Z_CY
        assert basic == pytest.approx(hand, rel=REL_TOL), "我方大招后普攻（+18%）vs 手算"
        theirs_basic = run_optimizer(optimizer_driver, _cy_opt(
            "basic", lc_atk=LC22002_ATK, extra_attacker={"atk": white * 1.34},
            equipment=_lc("22002", "Harmony", {"ultDmgBuff": True})))
        assert theirs_basic["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert basic == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)


class TestLC21056InPursuitOfTheWind:
    """追逐风的时候 S1（刻律德菈）：常驻全队击破增伤 16%（击破池）."""

    def test_break_dmg_boost(self, optimizer_driver):
        """击破段 vs 手算 ×1.16（dmg_break_dmg_boost 击破池——双方常驻件）；
        直伤段比等列注（对方 FullTeam BREAK 标签 BOOST 对直伤不可见）."""
        eng, log = _make_logged(_compiled(
            _member_build("1412", lc="21056"), "wind",
            enemies=_fragile_toughness("wind")))
        _cast(eng, "1412", "141201")
        breaks = _break_amounts(log, "1412")
        hits = _hit_amounts(log, source="1412")
        white = CY_ATK_W + LC21056_ATK
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", lc_atk=LC21056_ATK,
            equipment=_lc("21056", "Harmony", {"breakDmgBoost": True})))

        assert breaks[0] == pytest.approx(BREAK_BASE_10_WIND * 1.16, rel=REL_TOL), (
            "我方击破段（×1.16 池）vs 手算")
        hand = 1.0 * white * 1.18 * (1 + CY_WIND) * Z_CY
        assert hits[0] == pytest.approx(hand, rel=REL_TOL), "我方直伤段 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 BREAK 标签 BOOST 对直伤不可见（双方互对）")


class TestLC22005ForeverVictual:
    """永远的迷境饭 S1（刻律德菈）：常驻攻击 16%（属性段）+ 战技叠层攻击 8%×3."""

    def test_atk_stacks(self, optimizer_driver):
        """战技对友（星期日）叠层——第 1 次后普攻 @1 / 第 2 次后普攻 @2 比等."""
        eng, log = _make_logged(_compiled(
            _team_build2("1412", "22005", "1313"), "wind"))
        white = CY_ATK_W + LC22005_ATK
        _cast(eng, "1412", "141202", target="1313")   # 战技①（对友）
        _cast(eng, "1412", "141201")
        _cast(eng, "1412", "141202", target="1313")   # 战技②
        _cast(eng, "1412", "141201")
        basics = _hits_of(log, source="1412", action_type="basic")
        assert len(basics) == 2

        for n, got in ((1, basics[0]), (2, basics[1])):
            theirs = run_optimizer(optimizer_driver, _cy_opt(
                "basic", lc_atk=LC22005_ATK, extra_attacker={"atk": white * 1.34},
                equipment=_lc("22005", "Harmony", {"atkStacks": n})))
            hand = 1.0 * white * (1.34 + 0.08 * n) * (1 + CY_WIND) * Z_CY
            assert got == pytest.approx(hand, rel=REL_TOL), f"我方普攻 @{n} 层 vs 手算"
            assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
            assert got == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
                f"双方互对 @{n} 层")


class TestLC21011PlanetaryRendezvous:
    """与行星相会 S1（刻律德菈）：同元素友方增伤 12%（单人队自吃）."""

    def test_same_element_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1412", lc="21011"), "wind"))
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        white = CY_ATK_W + LC21011_ATK
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", lc_atk=LC21011_ATK,
            equipment=_lc("21011", "Harmony", {"alliesSameElement": True})))

        hand = 1.0 * white * 1.18 * (1 + CY_WIND + 0.12) * Z_CY
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方同元素增伤 12% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21046PoisedToBloom:
    """芳华待灼 S1（刻律德菈）：常驻攻击 16%（属性段）+ 同命途≥2 时全队暴伤 16%."""

    def test_cd_buff(self, optimizer_driver):
        """双人同谐队（星期日占位）——count_team 同命途≥2 两侧同闸开."""
        eng, log = _make_logged(_compiled(
            _team_build2("1412", "21046", "1313"), "wind"))
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        white = CY_ATK_W + LC21046_ATK
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", lc_atk=LC21046_ATK, extra_attacker={"atk": white * 1.34},
            teammates=[{"path": "Harmony"}],
            equipment=_lc("21046", "Harmony", {"cdBuff": True})))

        hand = 1.0 * white * 1.34 * (1 + CY_WIND) * 0.5 * 0.9 * (1 + 1.0 * 0.66)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方全队暴伤 16%（CR 封顶后期望 1.66）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1412")["crit_dmg"] == pytest.approx(0.66, rel=REL_TOL)


# ===========================================================================
# 光锥对拍——记忆载体（遐蝶 1407；普攻 0.5×HP；死龙链 140703 新蕊钉满实打——
# 遗世冥域 res_pen 0.2 + 怒啸 0.1 两侧同挂）
# ===========================================================================

def _summon_nw(eng):
    """实打 140703 → 死龙在场（遗世冥域 res_pen 0.2 + 怒啸 0.1—— remembrance 先例）."""
    _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))
    assert "1407_netherwing" in eng.state.actors


class TestLC20022Reminiscence:
    """溯忆 S1（遐蝶）：忆灵回合开始叠层增伤 8%/层（至多 4；忆灵退场摘除）."""

    def test_dmg_stacks(self, optimizer_driver):
        """合成 on_turn_start（忆灵独立行动链重不驱动）→ 普攻 @1/@4 层比等."""
        eng, log = _make_logged(_compiled(_member_build("1407", lc="20022"), "quantum"))
        _summon_nw(eng)
        hp_panel = CA_HP + LC20022_HP          # LC 生命白值并入（0.5×HP 基数消费）

        def hand(n):
            return (0.5 * hp_panel * 0.5 * 0.9 * Z_CA_CRIT
                    * (1 + CA_Q + 0.1 + 0.08 * n) * 1.2)

        for n in (1, 4):
            while True:
                mods = eng.state.actors["1407"].modifiers
                if "LC_20022_REMEMBRANCE" in mods and mods["LC_20022_REMEMBRANCE"].stacks >= n:
                    break
                _emit(eng, "on_turn_start", {"actor": "1407_netherwing"})
            log.clear()
            _cast(eng, "1407", "140701")
            ours = _hit_amounts(log, source="1407")
            theirs = run_optimizer(optimizer_driver, _ca_opt(
                "basic", lc_hp=LC20022_HP,
                equipment=_lc("20022", "Remembrance", {"dmgStacks": n})))
            assert ours == pytest.approx([hand(n)], rel=REL_TOL), (
                f"我方普攻 @{n} 层 vs 手算")
            assert theirs["hits"][0]["damage"] == pytest.approx(hand(n), rel=REL_TOL)
            assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
                f"双方互对 @{n} 层")


class TestLC21051GeniusesGreetings:
    """天才们的问候 S1（遐蝶）：常驻攻击 16%（属性段）+ 终结技后普攻增伤 20%."""

    def test_ult_basic_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1407", lc="21051"), "quantum"))
        _summon_nw(eng)                        # 大招同事件挂【普攻增伤 20% 3回合】
        assert "LC_21051_BASIC_DMG" in eng.state.actors["1407"].modifiers
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        theirs = run_optimizer(optimizer_driver, _ca_opt(
            "basic", lc_hp=LC21051_HP,
            extra_attacker={"atk": (CA_ATK + LC21051_ATK) * 1.16},
            equipment=_lc("21051", "Remembrance", {"basicDmgBoost": True})))

        hand = (0.5 * (CA_HP + LC21051_HP) * 0.5 * 0.9 * Z_CA_CRIT
                * (1 + CA_Q + 0.1 + 0.2) * 1.2)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方大招后普攻（+20%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21052SweatNowCryLess:
    """多流汗，少流泪 S1（遐蝶）：常驻 CR 12%（属性段）+ 忆灵在场增伤 24%."""

    def test_summon_dmg_buff(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1407", lc="21052"), "quantum"))
        _summon_nw(eng)
        assert "LC_21052_SELF_DMG" in eng.state.actors["1407"].modifiers
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        theirs = run_optimizer(optimizer_driver, _ca_opt(
            "basic", lc_hp=LC21052_HP, extra_attacker={"cr": CA_CR + 0.12},
            equipment=_lc("21052", "Remembrance", {"dmgBoost": True})))

        hand = (0.5 * (CA_HP + LC21052_HP) * 0.5 * 0.9 * (1 + (CA_CR + 0.12) * CA_CD)
                * (1 + CA_Q + 0.1 + 0.24) * 1.2)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方召死龙后普攻（+24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["cr"] == pytest.approx(CA_CR + 0.12, rel=REL_TOL)


# ===========================================================================
# 光锥对拍——丰饶载体（罗刹 1203；面板 = 白值×1.28 行迹；普攻 1.0 虚数 lv6）
# ===========================================================================

class TestLC21055UntoTomorrowsMorrow:
    """直到明天的明天 S1（罗刹）：治疗量段（无伤害读出随挂不测）+ 自身 HP≥50%
    时全队增伤 12%."""

    def test_hp50_dmg_buff(self, optimizer_driver):
        """满血双方开（对方 FullTeam BOOST 开关=状态钉——比等）；半血双方同灭."""
        eng, log = _make_logged(_compiled(_member_build("1203", lc="21055"), "imaginary"))
        _cast(eng, "1203", "120301")
        ours = _hit_amounts(log, source="1203")
        white = LC_ATK_W + LC21055_ATK
        theirs = run_optimizer(optimizer_driver, _lc55_opt(
            "basic", lc_atk=LC21055_ATK,
            equipment=_lc("21055", "Abundance", {"hp50DmgBoost": True})))

        hand = 1.0 * white * 1.28 * 0.5 * 0.9 * LC_CZ * 1.12
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方满血普攻（+12%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_hp50_gate_off(self, optimizer_driver):
        """半血：我方 enable_if 灭件；对方钉 false——两侧同灭比等."""
        eng, log = _make_logged(_compiled(_member_build("1203", lc="21055"), "imaginary"))
        eng.state.actors["1203"].current_hp = 0.4 * _eff(eng, "1203")["hp"]
        _cast(eng, "1203", "120301")
        ours = _hit_amounts(log, source="1203")
        white = LC_ATK_W + LC21055_ATK
        theirs = run_optimizer(optimizer_driver, _lc55_opt(
            "basic", lc_atk=LC21055_ATK,
            equipment=_lc("21055", "Abundance", {"hp50DmgBoost": False})))

        hand = 1.0 * white * 1.28 * 0.5 * 0.9 * LC_CZ
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方半血普攻（灭件）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# 光锥对拍——存护载体（杰帕德 1104；Grit 防转攻 0.35×DEF 经 on_turn_start 活读）
# ===========================================================================

LC21039_DEF = 463.04999999999995
LC21043_DEF = 463.04999999999995
LC23011_DEF = 529.2


class TestLC21039DestinysThreads:
    """织造命运之线 S1（杰帕德）：常驻效果抵抗（无伤害读出）+ 防御转增伤
    min(DEF/100×0.8%, 32%)（我方连续 vs 对方 floor 阶梯）."""

    def test_def_scaling_dmg_round(self, optimizer_driver):
        """DEF 1200 整百档双方同值 9.6% 比等（注入 def flat 压到整百——对方 floor
        阶梯与我方连续式在整百点交汇）."""
        eng, log = _make_logged(_compiled(_member_build("1104", lc="21039"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})   # Grit 挂载
        white_def = GP_DEF_W + LC21039_DEF
        def_panel = white_def * 1.125
        _inject(eng, "1104", "XC_DEF_FLAT", {"def_": 1200.0 - def_panel})  # 压 1200 整百
        white_atk = GP_ATK_W + LC21039_ATK
        atk = white_atk + 0.35 * 1200.0
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": white_atk, "def": white_def},
            extra_attacker={"atk": white_atk, "def": 1200.0},
            equipment=_lc("21039", "Preservation", {})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")

        hand = 1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE + 0.096)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 DEF 1200 档（9.6%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(atk, rel=REL_TOL), (
            "对方 dynamic conversion（Grit）面板回显")

    def test_def_scaling_floor_divergence(self, optimizer_driver):
        """S12 结构差：自然 DEF 1257.677 档——对方 floor(12.577)=12 → 9.6% 阶梯
        vs 我方连续 10.061%：对方/我方 = 1.32/1.32461416 ≈ 0.996517."""
        eng, log = _make_logged(_compiled(_member_build("1104", lc="21039"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})
        white_atk = GP_ATK_W + LC21039_ATK
        white_def = GP_DEF_W + LC21039_DEF
        def_panel = white_def * 1.125
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": white_atk, "def": white_def},
            extra_attacker={"atk": white_atk, "def": def_panel},
            equipment=_lc("21039", "Preservation", {})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")[0]

        ours_hand = (1.0 * (white_atk + 0.35 * def_panel) * 0.5 * 0.9 * GP_CZ
                     * (1 + GP_ICE + def_panel / 100 * 0.008))
        assert ours == pytest.approx(ours_hand, rel=REL_TOL), (
            "我方连续式（10.061%）vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1 + GP_ICE + 0.096) / (1 + GP_ICE + def_panel / 100 * 0.008),
            rel=REL_TOL)


class TestLC21043ConcertForTwo:
    """两个人的演唱会 S1（杰帕德）：常驻 DEF 16%（属性段）+ 持盾角色增伤 4%/层
    （待收——持盾角色计数无查询通道在案）."""

    def test_permanent_def(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1104", lc="21043"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})
        white_atk = GP_ATK_W + LC21043_ATK
        white_def = GP_DEF_W + LC21043_DEF
        def_panel = white_def * (1.125 + 0.16)        # DEF_P 池加算（行迹 12.5%+LC 16%）
        atk = white_atk + 0.35 * def_panel
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": white_atk, "def": white_def},
            extra_attacker={"atk": white_atk, "def": def_panel},
            equipment=_lc("21043", "Preservation", {"teammateShieldStacks": 0})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")

        hand = 1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 DEF 16% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1104")["def_"] == pytest.approx(def_panel, rel=REL_TOL)

    def test_shield_stacks_divergence(self, optimizer_driver):
        """S13 结构差：持盾计数增伤（我方待收在案）→ 钉 4 层：对方/我方 = 1.16."""
        eng, log = _make_logged(_compiled(_member_build("1104", lc="21043"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})
        white_atk = GP_ATK_W + LC21043_ATK
        white_def = GP_DEF_W + LC21043_DEF
        def_panel = white_def * (1.125 + 0.16)        # DEF_P 池加算（行迹 12.5%+LC 16%）
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": white_atk, "def": white_def},
            extra_attacker={"atk": white_atk, "def": def_panel},
            equipment=_lc("21043", "Preservation", {"teammateShieldStacks": 4})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")[0]

        assert ours == pytest.approx(
            1.0 * (white_atk + 0.35 * def_panel) * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE),
            rel=REL_TOL), "我方无持盾增伤段 vs 手算"
        # S13：对方 16% 与我方行迹冰伤同池加算 → 1.384/1.224（空池才是 1.16）
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1 + GP_ICE + 0.16) / (1 + GP_ICE), rel=REL_TOL)


class TestLC23011SheShutHerEyes:
    """她已闭上双眼 S1（杰帕德）：常驻 HP 24%/回能（属性段面板锚）+ 耗血后
    全队增伤 9%（2 回合）."""

    def test_hp_lost_team_dmg(self, optimizer_driver):
        """事件前钉 S14（对方 FullTeam BOOST 恒开）→ 1.09；事件后比等."""
        eng, log = _make_logged(_compiled(_member_build("1104", lc="23011"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})
        _cast(eng, "1104", "110401")
        first = _hit_amounts(log, source="1104")[0]
        white_atk = GP_ATK_W + LC23011_ATK
        white_def = GP_DEF_W + LC23011_DEF
        def_panel = white_def * 1.125
        atk = white_atk + 0.35 * def_panel
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": white_atk, "def": white_def},
            extra_attacker={"atk": white_atk, "def": def_panel, "hp": GP_HP * 1.24},
            equipment=_lc("23011", "Preservation", {"hpLostDmgBuff": True})))

        assert first == pytest.approx(
            1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE), rel=REL_TOL), (
            "我方事件前普攻（无增伤段）vs 手算")
        # S14：对方 9% 与我方行迹冰伤同池加算 → 1.314/1.224（空池才是 1.09）
        assert theirs["hits"][0]["damage"] / first == pytest.approx(
            (1 + GP_ICE + 0.09) / (1 + GP_ICE), rel=REL_TOL)

        _emit(eng, "on_hp_decrease", {"target": "1104", "reason": "drain"})
        assert "LC_23011_TEAM_DMG" in eng.state.actors["1104"].modifiers
        _cast(eng, "1104", "110401")
        second = _hit_amounts(log, source="1104")[1]
        hand = 1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE + 0.09)
        assert second == pytest.approx(hand, rel=REL_TOL), "我方事件后普攻（+9%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
