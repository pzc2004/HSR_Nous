"""L3 装备级对拍·残部收官波（BACKLOG B22 扩展②续四）：首批 6+4（equipment.py）、
批量波 25+14（equipment_batch.py）、专光扫荡 22（equipment_batch2.py）、残部续波
37+6（equipment_batch3.py）之后的收官波——本批 33 光锥 + 9 遗器（batch3 docstring
已映射未实现的 107/119/121/125/126/128 六遗器本波补齐），目标=把「能拍的」全部
拍完，剩下的全是缺读出端的。每件等式场景三方比对（我方引擎 vs 对方 vs 手算，
rel_tol 1e-4）+ 结构差钉倍数。

载体（映射表现成，见各源文件；智识=黑塔 1013/巡猎=真理医生 1305/毁灭=白厄 1408·
刃 1205·云璃 1221/虚无=黄泉 1308·桑博 1108/存护=杰帕德 1104/丰饶=罗刹 1203/
同谐=刻律德菈 1412/记忆=遐蝶 1407/欢愉=火花 1501/火=虎克 1109）。裁判链路与统一
口径同前四批（driver 头注 + 首批 docstring）；本文件只增映射表与场景。对方侧光锥
属性段（对方控制器不承载的 properties）一律钉进 attacker.*

===========================================================================
光锥 buff 状态映射表（对方条件开关 ↔ 我方模板 hooks；属性段=对方钉面板）
===========================================================================
--- 智识（黑塔 1013；Z=0.5×0.9×1.025，面板=白值无行迹 atk%）---
23033 忍法帖•缭乱破魔 S1——BE+60%（对方控制器全空=未建模，21031 先例）
（无开关）                  on_battle_start 常驻 break_effect 60%        基线比等+BE 面板互对；
                                                                    击破段我方 vs 手算 ×1.6
23037 向着不可追问处 S1——属性段 CR+12%（对方钉 cr）
skillUltDmgBoost（true）    on_ultimate 钩【战技/终结技增伤 60%】（#3=140   大招后战技比等；
                            能量闸——黑塔 110<140 回能半两侧同灭列注）      当次大招钉 S1
23060 当一颗星照亮夜空 S1
（无开关）                  常驻 def_pen 32%（对方同值 DEF_PEN 自件）       普攻比等（穿透区）；
                            叠层半（助战技层→追击/终结技增伤）需 assist    assist 载体链重未拍
                            载体——在册 51 角色仅 1510 有助战技（R-HN1     列注
                            序列模型差未收口），本波不拍列注
23061 星火悄然闪耀 S1——属性段 CR+18%（对方钉 cr）
radiantCrown（true）        战技增伤 72%+全队 def_pen 20%——**我方待收**    基线比等；
                            （fixture 仅挂暴击率常驻件， radiant 半未收编    钉 true 钉 S2
                            在案）→ 对方 DEF_PEN+SKILL BOOST 双件
21045 谐乐静默之后 S1——BE+28%（对方钉 be 面板）+ 大招后 spd 8%
spdBuff（true）             on_ultimate 钩 spd_pct 8% 2回合（对方 SPD_P      面板互对；
                            同值——速度无伤害消费）                         击破段 ×1.28 vs 手算
--- 巡猎（真理医生 1305；面板 = 白值×1.28 行迹）---
23027 驶向第二次生命 S1——BE+60%（对方钉 be 面板）
spdBuffConditional（动态）   enable_if BE≥150% → spd_pct 12%（双方 BE 面板     BE 面板互对+基线比等；
                            0.6 未达同灭）                                 击破无视防御半
                            （对方 breakDmgDefShred DEF_PEN·BREAK 标签——    我方待收列注 S3
                            kind=character 无击破段不可见，23050 先例）
--- 毁灭（云璃 1221 / 刃 1205；物理·白值×1.28 行迹）---
23030 落日时起舞 S1——属性段 CD+36%（对方钉 cd）
fuaDmgStacks 0-2（2）       on_ultimate 钩【焰舞】追击增伤 36%×N（钳 2）     分类结构差钉 S-分
                            （对方 FUA 标签 BOOST 同值——但我方云璃 Cull    类（见下，非窗口）
                            =ultimate 标签（fixture ③ 官方归 Ultimate DMG
                            域）不吃 follow_up 桶）
23062 所见即我 S1——属性段 ATK+18%/回能 10%（对方钉面板）
ultimateEnergyDmgBoost      常驻 dmg_ultimate=min(max_energy×0.2%, 72%)    刃大招（2.1×HP
（true）                    （对方读 context.baseEnergy 场景槽同式——刃      折叠段）比等；
                            max_energy=130 → 26%）                           娱乐半（暴伤 24%）
kingsEntertainment（true）  同钩第二件 crit_dmg 24%（对方 mutual FullTeam    双方常驻互对
                            CD 同值——driver LC mutual 折主 C 口径，不钉）
--- 虚无（黄泉 1308 / 桑博 1108）---
23059 灼尽炼狱的新骸 S1——属性段 HP+30%（对方钉 hp 面板）
purgatoryState（true）      【炼狱】暴伤 30%（我方 fixture 炼狱=空标记件    基线比等；
                            ——受暴击伤半未收编在案；对方 CD_BOOST 30%       钉 true 钉 S4
                            自件+team 件双吃——driver LC mutual 折主 C）
24003 孤独的疗愈 S1——BE+20%（对方钉 be 面板）
postUltDotDmgBuff（true）   终结技 DoT 增伤 24%——**我方待收**（fixture 勘正    基线比等；
                            ②在案——dot_dmg 桶 2026-09-16 B27#3 已接线但      钉 true 钉 S5
                            staging 钩退役未补挂；对方 DOT 标签 BOOST 同值）
21008 猎物的视线 S1——属性段 EHR+20%（对方钉 effect_hit 面板锚）
（无开关）                  常驻 dmg_dot_dmg_boost 24%——S-消费端已收官            风化跳双方
                            （2026-09-22：hook tick 声明 "dot" 吃桶，             DoT 增伤
                            对方 DOT 标签 BOOST 全等消灭；剩余差=EHR 抬            全等；剩余
                            期望权重 0.65×1.2×R-SA1 暴击区差在案）                差在案折比
21047 黑夜如影随行 S1——BE+28%（对方钉 be 面板）+ spd 8%
spdBuff（true）             on_break 钩 spd_pct 8% 2回合（对方 SPD_P 同值）  面板互对+基线比等
--- 存护（杰帕德 1104；Grit 防转攻 0.35×DEF 经 on_turn_start 活读）---
21016 宇宙市场趋势 S1——属性段 DEF+16%（对方钉 def 面板——Grit 转化读出）
（对方控制器全空）           受击挂【灼烧】（100% 固定概率 expected 恒生效）→  我方 vs 手算单钉
                            敌方回合开始跳 def×40% 火伤（对方未建模列注）    （对方基线列注非病）
21030 这就是我啦！S1——属性段 DEF+16%（对方钉 def 面板——Grit 转化读出）
（对方 TODO 未实现）         终结技附加基础伤害 DEF×60%（base_dmg_add 通道    我方 vs 手算单钉
                            正主——决策卡 #17 正例；对方控制器空壳列注；      （对方基线列注非病）
                            杰帕德终结技=护盾行动无伤害段，附加伤害半无
                            读出载体不单拍）
21053 愿旅途永远坦然 S1
shieldBoost（true）         常驻 shield_bonus 12%（对方 OutputTag.SHIELD    盾值我方 vs 手算
                            BOOST 同值——对方 ULT_SHIELD 技种未注册，          单钉；增伤半钉 S6
                            128 先例单钉）+ 我方增伤半待收（team 光环无通道
                            在案）→ 对方 dmgBoost mutual FullTeam BOOST 12%
--- 丰饶（罗刹 1203；面板 = 白值×1.28 行迹；普攻 1.0 虚数 lv6）---
23008 棺的回响 S1——属性段 ATK+24%（对方钉 atk 面板——对方控制器仅
                            teammate SPD 半（mutual 链不拍），atk 段走属性段   普攻比等
                            双方同值）
--- 同谐（刻律德菈 1412；面板 = 白值×1.18 行迹；CR 1.05 封顶 1.0 → 期望 1.5）---
23026 夜色流光溢彩 S1
cantillationStacks 0-5（0） on_action 叠层 energy_regen 3%×N（无伤害读出      面板锚（err 回显）
                            随挂不测；对方 ERR 滑条同值）
cadenzaActive（true）       on_ultimate 钩【华彩】自身 atk_pct 48%+全队        大招后普攻钉 S7
                            all_dmg 24%（对方自件 ATK_P 同值比等；全队件走
                            teammateEffects——真实管线只对队友穿戴调用
                            （comboStateTransform.ts:196），主 C 穿戴不折
                            主 C=对方无此 24%，我方单人队折自身）
21004 记忆中的模样 S1——BE+28%（对方钉 be 面板）+ 行动回能（无伤害读出）
（无开关）                  on_battle_start 常驻 break_effect 28%            基线比等+BE 面板互对；
                                                                    击破段 ×1.28 vs 手算
22007 未来，有我们一起 S1——属性段 CD+12%（对方钉 cd 面板）
elationBuff（true）         终结技后全队欢愉度 8%（对方 mutual FullTeam       普攻比等（CD 属性段）；
                            ELATION 同值——刻律无欢愉伤读出，欢愉度面板       欢愉度面板互对列注
                            回显互对列注）
--- 记忆（遐蝶 1407；普攻 0.5×HP；死龙链 140703 新蕊钉满实打——遗世冥域
    res_pen 0.2（×1.2 抗区）+ 怒啸 0.1（增伤池）两侧同挂）---
23036 将光阴织成黄金 S1——基础速度 +12（对方钉 spd 面板）
brocadeStacks 0-6（6）     on_action 命中叠【织金】暴伤 9%×N（钳 6）+ 满层   普攻 ×7 @6 层比等
                            【普攻增伤 9%×6】（对方 CD+SelfAndMemosprite
                            BASIC BOOST 同值——双方叠层窗口内当次不吃）
23040 让告别，更美一些 S1——属性段 HP+30%（对方钉 hp 面板）
deathFlower（true）         on_hp_decrease 钩【冥花】def_pen 30% 2回合        事件后普攻比等；
                            （对方 DEF_PEN SelfAndMemosprite 同值；耗血事件    事件前钉 S8
                            同发荒芜 1 层——对方 talentDmgStacks=1 同挂）
23049 致长夜的星光 S1——属性段 HP+30%（对方钉 hp 面板）
dmgBoost（true）            忆灵行动后【夜色】自身 all_dmg 30%（对方 BOOST     忆灵行动后普攻比等
                            SelfAndMemosprite 同值——忆灵技耗血荒芜 1 层
                            对方 talentDmgStacks=1 同挂；忆灵 def_pen 半
                            对方 mutual Memosprite 槽 driver 无忆灵队友不拍）
21050 胜利只在朝夕间 S1——属性段 CD+12%（对方钉 cd 面板）
teamDmgBuff（false）        忆灵 ally 指向技触发全队增伤 8%——死龙忆灵技指敌    普攻比等（CD 属性段）；
                            不触发（ally 指向忆灵技载体缺在案，batch3 案       增伤半列注
                            列注），对方 mutual FullTeam BOOST 同值亦不拍
21057 花儿不会忘记 S1——属性段 CD+24%（对方钉 cd 面板）
memoCdBoost（false）        忆灵暴伤 24%——**本波不拍**（对方 Memosprite      普攻比等（CD 属性段）
                            CD_BOOST 槽——死龙无暴伤读出在案列注）→ 钉 false
                            双方同灭
22006 飞向粉色的明天 S1——属性段 CD+12%（对方钉 cd 面板）
dmgBoost（true）            全队增伤 8%——双方同门控（我方 8007/8008 双 id     普攻比等（CD 属性段+
                            门=官方「开拓者•记忆装备时」；对方控制器亦硬编码    全队增伤双方同灭）
                            8007/8008 门）→ 遐蝶场双方同灭比等；强化普攻
                            60% 半我方待收（8007/8008 链 batch3 案）钉 false
21035 何物为真 S1——BE+24%（对方钉 be 面板，无直伤消费=面板锚）
（无开关）                  on_battle_start 常驻 break_effect 24%            基线比等+BE 面板互对
--- 欢愉（火花 1501；火，ATK 倍率；行迹 crit 0.12/0.133/elation 0.28 已并入；
    欢愉技 150120=21 段聚合 5.5、笑点池 30；欢愉伤害=7535.107×倍率×
    (1+elation)×笑点乘区×期望暴击×0.5×0.9；段时序=on_action 钩在主段后/
    追加段前发射——当技 0.5 主段不吃当技挂的件、0.25 追加段已吃）---
21064 菇菇嘎嘎历险记 S1——欢愉度常驻 12%（对方未建模列注）+ 欢愉技挂
elationVulnerability        【易伤】6%（对方 mutual FullTeam ELATION 标签     首/第 2 技钉 S9
（true）                    VULNERABILITY 同值——driver LC mutual 折主 C）
21065 今日好手气 S1——属性段 CR+12%（对方钉 cr）
elationStacks 0-2（N）      欢愉技叠层欢愉度 12%×N（对方 ELATION 滑条同值）   欢愉技 @0/@1/@2 钉
                            （段时序：当技主段@n 层/追加段@min(n+1,2) 层）
23053 花花世界迷人眼 S1——属性段 CD+48%（对方钉 cd 面板）
spConsumedStacks 0-4（4）    耗点叠层欢愉伤无视防御 5%×N——**已收编（2026-09-23，  普攻比等（CD 属性段）；
（elationBuff 钉 false）    sp_consumed 载荷叠层+hit_stat_exprs）                  欢愉技三方比等
23054 当她决定看见 S1——属性段 SPD+18%（对方钉 spd 面板）
greatFortune（true）        【上上签】暴击率 10%+暴伤 30%（对方 mutual        普攻比等（双暴双方
                            FullTeam CR/CD 同值——driver LC mutual 折主 C，    同挂常驻，不钉）
                            不钉面板防双计）
23057 欢迎来到银河城 S1——属性段 SPD+18%（对方钉 spd 面板）+ 终结技笑点
elationDefPen（true）       欢愉伤无视防御 20%——**已收编（2026-09-23，           欢愉技三方比等
                            hit_condition elation_damage + def_pen scoped）
23058 邂逅于下一个花季 S1——属性段 CD+60%（对方钉 cd 面板）+ ERR 公式
vulnerability（true）       欢愉技挂敌方易伤 15%（对方 mutual FullTeam         首/第 2 技钉 S12
                            VULNERABILITY 同值）
24006 欢愉满溢祝福 S1——属性段 ATK+20%（对方钉 atk 面板）
elationBuff（true）         战技/终结技对友方单体 → 目标欢愉度 12%（火花技能     普攻比等（ATK 属性段）；
                            指敌无落点=双方非同挂；对方自件 ELATION 同值）      欢愉技钉 S13
20023 嗤笑 S1
elationBuff（true）         阿哈时刻内欢愉度+16%（对方 actionKind==           欢愉技钉 S14（我方
                            ELATION_SKILL 门控 ELATION 同值——我方 aha_      aha 窗口不可达列注）
                            instant 窗口与对方行动门控口径差在案）
20024 残泪 S1
cdBuff（true）              笑点≥10 时暴伤+20%（对方 CD 开关同值——笑点      欢愉技比等（池 30≥10
                            30 场双方同闸开）                               双方同闸开）

===========================================================================
遗器 buff 状态映射表（基础件 p2c/p4c 两侧各自原生通道，不钉面板）
===========================================================================
107 火匠（虎克——自体战技载体；托帕+账账场撞 R-TP1 召唤物面板继承差
                   在案不取）2pc dmg_fire 10%（双方 stat/p2c 同值）；4pc 战技
                   增伤 12%（双方 stat/p4x 同值）+ 终结技后下一次攻击火伤 12%
                   （on_ultimate 钩 tick_anchor on_action 消费=当次大招不吃且
                   仅下次攻击；对方 enabled 开关恒开=近似）→ 大招生效后战技
                   比等；首次战技钉 S15（batch3 映射本波实现）
119 铁骑（白厄）     2pc break_effect 16%（p2c 面板回显互对+击破段 ×1.16 vs
                   手算）；4pc 击破/超击破无视防御——**待收**（类型限定无视防御
                   无通道在案）→ 对方 p4t DEF_PEN 同灭列注（batch3 映射本波实现）
121 司铎（星期日→真理） 2pc spd_pct 6%（面板回显互对）；4pc 对友方单体战技/终结技
                   → 目标 crit_dmg 18%×N 2回合（钳 2）——对方 value 滑条=self CD
                   简化模型（官方落点=技能目标，映射表注）；星期日战技污染件
                   （增伤 30%/CR 20%）摘除回空白 slate（_clean_knots 先例）
                   （batch3 映射本波实现；套装穿星期日——钩=穿戴者对友施技）
125 女武神（罗刹→真理） 2pc spd_pct 6%（面板回显互对）；4pc 治疗其他友方 →
                   【甘霖】spd 6%+全队 crit_dmg 15%（对方 enabled 开关=SPD_P 6%+
                   FullTeam CD 15%+BOOST 0.15 outputBuff(CD)——OutputTag.BUFF 无
                   命中承载=惰性，dmgBoostMulti 回显钉 1.0 自证）（batch3 映射本波实现）
126 船长（星期日→真理） 2pc crit_dmg 16%（p2c）；4pc 成为队友技能目标叠【助力】
                   （钳 2）→ 终结技消耗 → atk_pct 48% 1回合（当次大招不吃——
                   对方 enabled 开关恒开=建模近似）→ 大招后普攻比等；当次大招钉 S16
                   （batch3 映射本波实现）
128 隐士（杰帕德） 2pc/4pc 护盾量 +10%/+12%（对方 p2x/p4x SHIELD 标签 BOOST 同值
                   ——杰帕德 ULT_SHIELD 技种对方未注册，盾值我方 vs 手算单钉）；
                   4pc 后半「持盾友方 crit_dmg 15%」**待收**（逐目标持盾判定无通道
                   在案）→ 对方 enabled 开关 FullTeam CD 15%=近似 → 钉 S17
                   （batch3 映射本波实现）
124 诗人（遐蝶）     2pc dmg_quantum 10%（对方 p2c 元素门控同值）；4pc spd-8%
                   （双方 stat 通道同值——大行迹「倒置的火炬」HP≥50% 速度+40%
                   同池（1+0.4-0.08=1.32），半血场摘行迹档：有效 95×0.92=87.4
                   →<95 档 CR 32%）+ 速度档（我方有效面板档 vs 对方 x.c.a 平速档
                   ——driver set_threshold_spd 场景槽直钉同读数，语义差在案）
                   → 普攻比等（set_threshold_spd 槽实证首用例）
129 魔法少女（火花） 2pc crit_dmg 16%（双方 stat 通道同值）；4pc 欢愉伤无视防御
                   10% 基础半——**已收编（2026-09-23，hit_condition elation_damage
                   + def_pen scoped）→ 欢愉技三方比等；叠层半「每累计 5 笑点
                   +1%×N」待收（累计语义对齐——fixture notes 在案）
130 卜者（火花）     2pc spd_pct 6%（双方 stat 通道同值）；4pc 速度≥120/160 暴击
                   10%/18%（欢愉载体面版 spd<120 档不可达——tier CR 未拍列注；
                   set_threshold_spd 槽由 124 实证）+ 首次欢愉技全队欢愉度
                   10%（对方 enabled 开关恒开=当次即吃；我方 on_action 结算后挂=
                   当次不吃——段时序：首技 0.5 主段无欢愉/0.25 追加段吃 10%）
                   → 第 2 发欢愉技比等；首技钉 S19

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注倍数，任一侧改动触红）
===========================================================================
S1  23037 终结技增伤窗口（我方 on_ultimate 结算后挂=当次不吃；对方开关恒开）
    → 当次大招 1.60
S2  23061 战技增伤+穿透（我方 radiant 半待收在案）→ 钉 true：对方/我方 =
    1.72×(100/180)/0.5 ≈ 1.911111
S3  23027 击破无视防御（我方待收在案；对方 BREAK 标签 DEF_PEN——kind=character
    无击破段不可见，23050 先例）→ 列注不钉倍数
S4  23059 炼狱暴伤（我方空标记件=半未收编在案；对方 CD_BOOST 30% 自件+team
    件双吃）→ 钉 true：对方/我方 = (1+0.05×1.1)/1.025 ≈ 1.029268
S5  24003 终结技 DoT 增伤（我方待收在案；对方 DOT 标签 BOOST 24%）→ 钉 true：
    对方/我方 = 0.65×1.24/SA_CZ（R-SA1 暴击区差×期望权重在案折比值）
S6  21053 持盾增伤（我方 team 光环无通道在案；对方 mutual FullTeam BOOST 12%）
    → 钉 true：对方/我方 = (1+GP_ICE+0.12)/(1+GP_ICE)
S7  23026 华彩全队件口径（对方 teammateEffects 只对队友穿戴调用——真实管线
    comboStateTransform.ts:196，主 C 穿戴不折主 C；我方单人队 team 件折自身）
    → 大招后普攻对方/我方 = (1+CY_WIND)/(1+CY_WIND+0.24)；当次大招另钉
    1.66/1.18（对方自件 atk 48% 生效 vs 我方未挂）
S8  23040 冥花窗口（我方 on_hp_decrease 结算后挂=事件前不吃；对方恒开）→
    事件前普攻 def 区比（defMulti(0.3)/0.5 = 100/170 ≈ 1.176471）
S9  21064 易伤窗口×常驻欢愉度差（段时序：首技 0.5 主段无易伤/0.25 追加段吃
    6%——对方 mutual 恒开全段；常驻欢愉度我方 0.12 对方未建模各进各区）→
    首/第 2 技各钉复合比（见测试注）
~~S10 23053 耗点无视防御~~ **已收官（2026-09-23，sp_consumed 载荷叠层 +
   hit_stat_exprs per-hit 值——4 层场三方全等 100/180；叠层钩实打另测）**
~~S11 23057 欢愉无视防御~~ **已收官（2026-09-23，hit_condition elation_damage
   路由标识 + def_pen scoped——三方全等 100/180）**
S12 23058 易伤窗口（段时序同 S9 族：首技 0.5 主段无易伤/0.25 追加段吃 15%——
    对方 mutual 恒开全段）→ 首技对方/我方 = 6.325/6.25 ≈ 1.012；第 2 技比等
S13 24006 欢愉度归属（我方技能指敌无落点 vs 对方自件 ELATION 12%）→ 对方/我方
    = (1+SP_EL+0.12)/(1+SP_EL)
S14 20023 阿哈窗口（我方 aha_instant 链不可达 vs 对方 actionKind 门控 ELATION
    16%）→ 对方/我方 = (1+SP_EL+0.16)/(1+SP_EL)
S15 107 火匠终结技火伤窗口（我方 on_ultimate 后挂=当次大招不吃且仅下次攻击；
    对方 enabled 恒开）→ 首次战技 (1+0.1+0.12+0.12)/(1+0.1+0.12) = 1.34/1.22
    ≈ 1.098361（batch3 S15 手写值 1.444/1.324≈1.090634 为未实现笔误——分子
    误写（1.564 误作 1.444）且数值非 1.0831/1.0984，本波实现更正）
S16 126 助力爆发窗口（对方 enabled 恒开含当次大招=建模近似；我方 on_ultimate
    结算后挂=当次不吃）→ 当次大招 1.76/1.28 = 1.375（batch3 S15 手写值 1.48
    为未实现笔误——1.76/1.28≠1.48，本波实现更正；batch3 S15 编号与 107 撞号，
    本波 126 条目改 S16）
S17 128 持盾暴伤（我方待收在案）→ 钉 true：对方/我方 =
    (1+0.05×0.65)/(1+0.05×0.5) = 1.0325/1.025 ≈ 1.007317（batch3 S16 同钉本波实现）
~~S18 129 欢愉无视防御~~ **基础半已收官（2026-09-23，hit_condition elation_damage
   + def_pen scoped——三方全等 100/190；叠层半「每累计 5 笑点+1%」待收——累计语义
   对齐，fixture notes 在案）**
S19 130 首次欢愉技窗口（段时序：首技 0.5 主段无欢愉/0.25 追加段吃 10%——对方
    enabled 恒开全段）→ 首技复合比；第 2 发比等
S-分类 23030 分类结构差：我方云璃 Cull=ultimate 标签（fixture ③ 官方归
    Ultimate DMG 域）不吃 follow_up 桶焰舞；对方 Cull=FUA 标签吃 FUA BOOST
    72% → 对方/我方恰为 1.72（双方 Parry CD 1.5+LC 0.36 同池同值）
S-消费端【已收官 2026-09-22】21008 hook 承载 DoT tick 不吃 dot_dmg_boost 桶——
    修法：hook deal_damage 伪行动类别声明槽收 "dot"（扩展词表 _HOOK_DMG_ACTION_TYPES
    = ACTION_TYPES+dot——dot 非行动类别，03_actor §3.8 同口径）；声明后通用 deal_damage
    路径增伤区读 dot_dmg_boost 桶（攻击侧池与声明式 dot_tick 同口径），桑博 1108 风化
    tick 全族 17 处声明（卡芙卡/艾丝妲/希露瓦×2/桑博/虎克×2/卢卡/桂乃芬/椒丘/黑天鹅/
    海瑟音×6）。边界：暴击口径不变（事件承载含期望暴击 R-SV1/R-KF3 在案）+一次性结算
    读现值（快照切分不适用）。24003 半移正=S5 条件段未收编（非消费端缺，在案）

真病清单（本波新发现——单列；对方侧/external 只读报回，我方侧已修）：
- B4-F①（我方 fixture 笔误，已修）：1205_刃.yaml 大辟万死·tally 段缺
  action_type: "ultimate"——hook deal_damage 缺省 follow_up 桶路由，tally 段
  读不到终结技增伤池（23062 对拍钓出：主段吃 0.26 池 tally 段漏吃）。修复=
  补 action_type 声明（legacy_1300 刃大招 tally 链测试同步过——无
  ultimate_dmg_boost 源场行为零变化）
- 对方侧（external 只读报回，不修）：无新发现——fixtures 验收批质量持续稳定

跳过清单（缺读出端/载体未立，不硬造）：
- 同谐专光 teammates 镜像链群（23003/23019/23021/23034/23038/23042/23047/
  23048/23051/23052）：对方控制器全走 precomputeMutual/Teammate（队友链），
  driver 队友光锥未接入——维持 batch2/3 案
- 23013 时节不居（丰饶）：纯治疗/HP 件+对方控制器全空——无伤害读出
- 23017 惊魂夜/23008 的 SPD 半：teammate mutual 链（23008 atk 段已拍）
- 23023 命运从未公平（存护）：盲注=护盾暴击链——需护盾量读出+砂金载体链，
  本波未立（def% 属性段无独立读出价值不单拍）
- 光锥无伤害读出半件群（随挂不测）：23030 aggro/23033 雷遁回能/23036 忆灵
  叠层/23040 行动提前/23049 忆灵穿透/23053 耗点回能/23057 笑点/23058 ERR
  公式/23059 回能/23060 助战叠层/23062 回能/23037 能量闸回能/21045 spd
- 21000 术后对话/21007 同一种心情/21014 此时恰好/21028 暖夜/21054 故事的下一页/
  22001 嘿我在这儿（丰饶 4 星）：纯治疗/回能——治疗量对拍读出端未开（下波续）
- 21002 余生第一天/21009 朗道/21023 我们是地火/24002 记忆的质料（存护）：
  减伤/防御无伤害读出
- 21018 舞舞舞/21021 等价交换/21048 梦的蒙太奇/20012 轮契/20013 灵钥/20015
  蕃息/20019 调和/20021 焚影：推条/回能无伤害读出
- 21025 过往未来（同谐）：队友增伤链（对方 teammate 控制器）——batch3 案
- 21032 镂月裁云之意/20009 乐圮：我方 hooks 空（生成器未收编）——不硬造
- 20001 物穰/20003 琥珀/20004 幽邃/20008 嘉果/20010 戍御/20014 相抗/20017
  开疆/22000 新手任务开始前（3 星生存/回能/命中件）：无伤害读出（20004/22000
  纯 EHR 面板锚不单拍）
- 遗器残部：101 过客（治疗）/103 圣骑士（护盾——读出端 driver 无盾输出对拍
  缺）/106 铁卫（减伤）/118 钟表匠（FullTeam BE 需 teammates 镜像）/132 名冶
  （我方 data 模板 hooks 空——生成器未收编）
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
from tests.test_crosscheck_equipment_batch3 import (  # noqa: F401
    BREAK_BASE_10, BREAK_BASE_10_PHY, BREAK_BASE_10_WIND,
    _ca_opt, _cy_opt, _gp_opt, _lc55_opt, _summon_nw, _sunday_skill, _team_build2,
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
    BL_HP, BL_HP_W, BL_ATK_W, BL_CZ, LC_ATK, LC_ATK_W, LC_CZ, LC_DEF, LC_HP, LC_SPD,
    _bl, _opt_blade, _opt_luocha,
)
from tests.test_crosscheck_legacy_1000 import (  # noqa: F401
    GP_ATK_W, GP_CZ, GP_DEF, GP_DEF_W, GP_HP, GP_ICE, GP_SPD, HK_ATK, HK_ATK_W,
    HK_CZ, SA_ATK_W, SA_CZ, _opt_gepard, _opt_hook, _opt_sampo, _turn_start,
)
from tests.test_crosscheck_legacy_final import (  # noqa: F401
    YL_ATK, YL_ATK_W, YL_CD, YL_CR, YL_CZ, YL_CZ_PARRY, _arm_enemy, _dummy_atk,
    _fire_ult_yunli, _opt_yunli, _yl,
)
from tests.test_crosscheck_elation import (  # noqa: F401
    LV_COEF, SP_ATK, SP_CD, SP_CD_P30, SP_CR, SP_EL, SP_HP, Z_SP, _el,
    _opt_sparxie, _pm, _solo_compiled, _pin_banger, _pin_pool_gain,
)

# ---------------------------------------------------------------------------
# 口径常数（本批新增；载体既有常数从各波文件复用）
# ---------------------------------------------------------------------------

# 光锥白值（fixture base_stats 终审值；仅 atk/hp/def 进手算锚的才列）
LC23008_ATK = 582.1199999999999
LC23026_ATK = 635.04
LC23027_ATK = 582.1199999999999
LC23030_ATK = 582.1199999999999
LC23033_ATK = 582.1199999999999
LC23036_ATK = 635.04
LC23036_HP = 1058.4
LC23037_ATK = 635.04
LC23040_ATK = 529.2
LC23040_HP = 1270.08
LC23049_ATK = 529.2
LC23049_HP = 1164.2399999999998
LC23053_ATK = 582.1199999999999
LC23054_ATK = 529.2
LC23057_ATK = 476.28
LC23058_ATK = 635.04
LC23059_ATK = 423.36
LC23060_ATK = 635.04
LC23061_ATK = 635.04
LC23062_ATK = 635.04
LC23062_HP = 952.56
LC24003_ATK = 529.2
LC24006_ATK = 529.2
LC21008_ATK = 476.28
LC21016_ATK, LC21016_DEF = 370.44000000000005, 396.9
LC21030_ATK, LC21030_DEF = 370.44000000000005, 529.2
LC21045_ATK = 476.28
LC21047_ATK = 476.28
LC21050_ATK = 476.28
LC21050_HP = 846.72
LC21053_ATK = 370.44000000000005
LC21053_DEF = 529.2
LC21057_ATK = 529.2
LC21057_HP = 1058.4
LC21064_ATK = 476.28
LC21065_ATK = 529.2
LC22006_ATK = 476.28
LC22006_HP = 846.72
LC22007_ATK = 476.28
LC21004_ATK = 423.36
LC21035_ATK = 423.36
LC21035_HP = 1058.4
LC20023_ATK = 370.44000000000005
LC20024_ATK = 317.52

# 云璃/刃共用：物理属性（23030 云璃）/风属性（23062 刃）击破基准
BREAK_BASE_10_ICE = BREAK_BASE_10                     # 冰 scaling=1.0
BREAK_BASE_10_IMAG = BREAK_BASE_10 * 0.5              # 虚数 scaling=0.5（rulebook 在案）


# ---------------------------------------------------------------------------
# 对方侧场景模子（本批载体扩展版；LC 白值并入 base（ATK_P 换算基数）/
# 面板（终值），属性段钉 attacker——同前几波口径）
# ---------------------------------------------------------------------------

def _yunli_opt(action: str, *, lc_atk: float = 0.0, equipment=None, cond=None,
               extra_attacker=None):
    """云璃对方场景（_opt_yunli 装备扩展版；LC 白值并入 base/attacker 双写）."""
    sc = _opt_yunli(action, cond=cond)
    white = YL_ATK_W + lc_atk
    sc["base"]["atk"] = white
    sc["attacker"]["atk"] = white * 1.28
    sc["attacker"].update(extra_attacker or {})
    if equipment is not None:
        sc["equipment"] = equipment
    return sc


def _blade_opt(action: str, *, lc_atk: float = 0.0, lc_hp: float = 0.0,
               equipment=None, cond=None, extra_attacker=None, base_energy=None):
    """刃对方场景（_opt_blade 装备扩展版；LC 白值并入 base——刃 HP 基数=角色+光锥
    白值（HP_P 换算基数），atk 面板只作回显；base_energy 槽=对方终结技能量读口）."""
    sc = _opt_blade(action, cond=cond)
    sc["base"]["atk"] = BL_ATK_W + lc_atk
    if lc_hp:
        sc["base"]["hp"] = BL_HP_W + lc_hp
        sc["attacker"]["hp"] = (BL_HP_W + lc_hp) * 1.28
    sc["attacker"].update(extra_attacker or {})
    if base_energy is not None:
        sc["base_energy"] = base_energy
    if equipment is not None:
        sc["equipment"] = equipment
    return sc


def _hook_opt(action: str, *, equipment=None, cond=None, extra_attacker=None):
    """虎克对方场景（_opt_hook 装备扩展版；行迹 atk 28% 换算基数含 LC 白值——
    本波遗器件无 LC，白值不动）."""
    sc = _opt_hook(action, cond=cond)
    sc["attacker"].update(extra_attacker or {})
    if equipment is not None:
        sc["equipment"] = equipment
    return sc


def _sampo_opt(action: str, *, lc_atk: float = 0.0, equipment=None, cond=None,
               extra_attacker=None):
    """桑博对方场景（_opt_sampo 装备扩展版；LC 白值并入 base/attacker 双写——
    行迹 atk 28% 换算基数含 LC）."""
    sc = _opt_sampo(action, cond=cond)
    white = SA_ATK_W + lc_atk
    sc["base"]["atk"] = white
    sc["attacker"]["atk"] = white * 1.28
    sc["attacker"].update(extra_attacker or {})
    if equipment is not None:
        sc["equipment"] = equipment
    return sc


def _sparxie_opt(action: str, *, lc_atk: float = 0.0, equipment=None, cond=None,
                 extra_attacker=None):
    """火花对方场景（_opt_sparxie 装备扩展版；LC 白值并入 base/attacker 双写）."""
    sc = _opt_sparxie(action, cond=cond)
    white = SP_ATK + lc_atk
    sc["base"]["atk"] = white
    sc["attacker"]["atk"] = white
    sc["attacker"].update(extra_attacker or {})
    if equipment is not None:
        sc["equipment"] = equipment
    return sc


# ===========================================================================
# 光锥对拍——智识载体（黑塔 1013；面板 = 白值，Z=0.5×0.9×1.025）
# ===========================================================================

class TestLC23033Ninjutsu:
    """忍法帖•缭乱破魔 S1（黑塔）：常驻 BE 60%（对方控制器全空=未建模——
    21031 先例；雷遁回能半无伤害读出随挂不测）."""

    def test_be_panel_and_break(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="23033"), "ice",
            enemies=_fragile_toughness("ice")))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        breaks = _break_amounts(log, "1013")
        white = HT_ATK + LC23033_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white, extra_attacker={"be": 0.6},
            equipment=_lc("23033", "Erudition", {})))

        hand = 1.0 * white * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线（BE 无直伤消费）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1013")["break_effect"] == pytest.approx(0.6, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.6, rel=REL_TOL), "BE 面板互对"
        assert breaks[0] == pytest.approx(BREAK_BASE_10_ICE * 1.6, rel=REL_TOL), (
            "我方击破段（BE 60% 池）vs 手算——对方 kind=character 无击破段不可见")


class TestLC23037UnreachableVeil:
    """向着不可追问处 S1（黑塔）：常驻 CR 12%（属性段）+ 终结技后战技/终结技
    增伤 60%（#3=140 能量闸——黑塔 max_energy=110<140 回能半两侧同灭列注）."""

    def test_crit_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23037"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC23037_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white, extra_attacker={"cr": 0.17},
            equipment=_lc("23037", "Erudition", {"skillUltDmgBoost": False})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + 0.17 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CR 12% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_ult_skill_boost_window(self, optimizer_driver):
        """当次大招钉 S1（我方 on_ultimate 结算后挂=当次不吃；对方开关恒开）→
        1.60；大招后战技比等."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23037"), "ice"))
        eng.state.actors["e1"].current_hp = 0.4 * eng.pipeline.effective_stats(
            eng.state.actors["e1"])["hp"]   # 打残隔离黑塔 HP≥50% 增伤件（大招后战技段）
        white = HT_ATK + LC23037_ATK
        cz = 1 + 0.17 * 0.5
        _ult(eng, "1013", "101303", 120.0)
        ours_ult = _hit_amounts(log, source="1013")
        theirs_ult = run_optimizer(optimizer_driver, _herta_opt(
            "ult", atk=white, extra_attacker={"cr": 0.17},
            equipment=_lc("23037", "Erudition", {"skillUltDmgBoost": True})))

        assert ours_ult == pytest.approx([2.0 * white * 0.5 * 0.9 * cz], rel=REL_TOL), (
            "我方当次大招（无增伤段）vs 手算")
        assert theirs_ult["hits"][0]["damage"] / ours_ult[0] == pytest.approx(
            1.6, rel=REL_TOL)

        _cast(eng, "1013", "101302")
        ours = _hit_amounts(log, source="1013")[1]          # [0]=当次大招段
        hand = 1.0 * white * 0.5 * 0.9 * cz * 1.6
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方大招后战技（+60%）vs 手算"
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "skill", atk=white, extra_attacker={"cr": 0.17},
            equipment=_lc("23037", "Erudition", {"skillUltDmgBoost": True})))
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23060StarNight:
    """当一颗星照亮夜空 S1（黑塔）：常驻 def_pen 32%（对方同值自件）；叠层半
    （助战技→追击/终结技增伤）需 assist 载体——在册 51 角色仅 1510 有助战技
    （R-HN1 序列模型差未收口），本波不拍列注."""

    def test_def_pen(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23060"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC23060_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white,
            equipment=_lc("23060", "Erudition", {"sailStacks": 0})))

        def_multi = 100 / (100 * (1 - 0.32) + 100)
        hand = 1.0 * white * def_multi * 0.9 * 1.025
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 def_pen 32% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            def_multi, rel=REL_TOL)


class TestLC23061FlickeringStars:
    """星火悄然闪耀 S1（黑塔）：常驻 CR 18%（属性段）+ 战技增伤 72%/全队
    def_pen 20%（我方 radiant 半待收在案——fixture 仅挂暴击率常驻件）."""

    def test_crit_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23061"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC23061_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white, extra_attacker={"cr": 0.23},
            equipment=_lc("23061", "Erudition", {"radiantCrown": False})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + 0.23 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CR 18% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_skill_divergence(self, optimizer_driver):
        """S2 结构差：radiant 半（我方待收在案）→ 钉 true：对方/我方 =
        1.72×(100/180)/0.5 ≈ 1.911111."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23061"), "ice"))
        eng.state.actors["e1"].current_hp = 0.4 * eng.pipeline.effective_stats(
            eng.state.actors["e1"])["hp"]   # 打残隔离黑塔 HP≥50% 增伤件
        _cast(eng, "1013", "101302")
        ours = _hit_amounts(log, source="1013")[0]
        white = HT_ATK + LC23061_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "skill", atk=white, extra_attacker={"cr": 0.23},
            equipment=_lc("23061", "Erudition", {"radiantCrown": True})))

        assert ours == pytest.approx(1.0 * white * 0.5 * 0.9 * 1.115, rel=REL_TOL), (
            "我方无 radiant 段 vs 手算")
        ratio = 1.72 * (100 / (100 * (1 - 0.2) + 100)) / 0.5
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(ratio, rel=REL_TOL)


class TestLC21045AfterCharmonyFall:
    """谐乐静默之后 S1（黑塔）：常驻 BE 28% + 终结技后 spd 8%（2 回合）."""

    def test_be_panel_and_break(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="21045"), "ice",
            enemies=_fragile_toughness("ice")))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        breaks = _break_amounts(log, "1013")
        white = HT_ATK + LC21045_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white, extra_attacker={"be": 0.28},
            equipment=_lc("21045", "Erudition", {"spdBuff": False})))

        hand = 1.0 * white * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1013")["break_effect"] == pytest.approx(0.28, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.28, rel=REL_TOL), "BE 面板互对"
        assert breaks[0] == pytest.approx(BREAK_BASE_10_ICE * 1.28, rel=REL_TOL), (
            "我方击破段（BE 28% 池）vs 手算")

    def test_spd_after_ult(self, optimizer_driver):
        """大招后 spd 面板互对（对方 SPD_P 8% 同值——速度无伤害消费）."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="21045"), "ice"))
        _ult(eng, "1013", "101303", 120.0)
        assert "LC_21045_SPD_UP_AFTER_ULT" in eng.state.actors["1013"].modifiers
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK + LC21045_ATK,
            equipment=_lc("21045", "Erudition", {"spdBuff": True})))
        assert theirs["stats"]["spd"] == pytest.approx(100 * 1.08, rel=REL_TOL), (
            "对方 SPD_P 8% 面板回显")


# ===========================================================================
# 光锥对拍——巡猎载体（真理医生 1305；面板 = 白值×1.28 行迹）
# ===========================================================================

class TestLC23027SailingSecondLife:
    """驶向第二次生命 S1（真理医生）：常驻 BE 60% + BE≥150% 闸 spd 12%（两侧
    BE 面板 0.6 未达同灭）；击破无视防御半（对方 BREAK 标签 DEF_PEN——
    kind=character 无击破段不可见，23050 先例）钉 false 列注 S3."""

    def test_be_panel_and_break(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="23027"), "imaginary",
            enemies=_fragile_toughness("imaginary")))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        breaks = _break_amounts(log, "1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC23027_ATK, extra_attacker={"be": 0.6},
            equipment=_lc("23027", "Hunt",
                          {"breakDmgDefShred": False, "spdBuffConditional": True})))

        hand = 1.0 * _rt_panel(LC23027_ATK) * ZR
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1305")["break_effect"] == pytest.approx(0.6, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.6, rel=REL_TOL), "BE 面板互对"
        assert breaks[0] == pytest.approx(BREAK_BASE_10_IMAG * 1.6, rel=REL_TOL), (
            "我方击破段（BE 60% 池）vs 手算——S3 对方击破穿透段不可见列注")


# ===========================================================================
# 光锥对拍——毁灭载体（云璃 1221 / 刃 1205；物理/风）
# ===========================================================================

class TestLC23030DanceAtSunset:
    """落日时起舞 S1（云璃）：常驻 CD 36%（属性段）+ 终结技后【焰舞】追击增伤
    36%×N（钳 2；受击概率提高半无伤害读出随挂不测）."""

    def test_crit_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1221", lc="23030"), "physical"))
        _cast(eng, "1221", "122101")
        ours = _hit_amounts(log, source="1221")
        white = YL_ATK_W + LC23030_ATK
        theirs = run_optimizer(optimizer_driver, _yunli_opt(
            "basic", lc_atk=LC23030_ATK, extra_attacker={"cd": 0.86},
            equipment=_lc("23030", "Destruction", {"fuaDmgStacks": 0})))

        hand = 1.0 * white * 1.28 * 0.5 * 0.9 * (1 + YL_CR * 0.86)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CD 36% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_firedance_fua(self, optimizer_driver):
        """S-结构差（分类口径）：焰舞=追击桶件，但我方云璃 Cull 归 ultimate 标签
        （fixture ③ 官方归 Ultimate DMG 域）不吃 follow_up 桶——对方 Cull=FUA
        标签吃 FUA BOOST 72% → 对方/我方恰为 1.72（双方 Parry CD 1.5+LC 0.36
        同池同值）."""
        eng, log = _make_logged(_compiled(
            _member_build("1221", lc="23030"), "physical",
            enemies=_dummy_atk("e1", "physical")))
        _arm_enemy(eng)
        _fire_ult_yunli(eng)
        assert "LC_23030_FIREDANCE" in eng.state.actors["1221"].modifiers
        log.clear()
        _cast(eng, "e1", "e_hit", target="1221")
        ours = _hit_amounts(log, source="1221")
        white = YL_ATK_W + LC23030_ATK
        cz = 1 + YL_CR * (1.5 + 0.36)               # Parry CD 1.5 + LC CD 0.36
        theirs = run_optimizer(optimizer_driver, _yunli_opt(
            "fua", lc_atk=LC23030_ATK, extra_attacker={"cd": 0.86},
            cond={"blockActive": True},
            equipment=_lc("23030", "Destruction", {"fuaDmgStacks": 2})))

        hand = 6.52 * white * 1.28 * 0.5 * 0.9 * cz
        assert len(ours) == 7, "Cull 主段+追加 6 段"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), (
            "我方 Cull（ultimate 标签，焰舞不吃）vs 手算")
        assert theirs["hits"][0]["damage"] / sum(ours) == pytest.approx(
            1.72, rel=REL_TOL), "分类结构差：对方 FUA 标签吃焰舞 72% vs 我方 ultimate 标签不吃"


class TestLC23062IAmAsYouBehold:
    """所见即我 S1（刃）：常驻 ATK 18%/回能 10%（属性段面板锚——刃伤害 HP 基数
    不吃 ATK）+ 终结技增伤 min(max_energy×0.2%, 72%)（刃 130 → 26%；对方读
    base_energy 场景槽同式）+【王的娱乐】暴伤 24%（对方 mutual FullTeam CD
    同值——driver LC mutual 折主 C 口径，双方常驻互对）."""

    def test_atk_panel_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1205", lc="23062"), "wind"))
        _cast(eng, "1205", "1120501")
        ours = _hit_amounts(log, source="1205")
        theirs = run_optimizer(optimizer_driver, _blade_opt(
            "basic", lc_atk=LC23062_ATK, lc_hp=LC23062_HP,
            equipment=_lc("23062", "Destruction",
                          {"ultimateEnergyDmgBoost": False,
                           "kingsEntertainment": True})))

        hp = (BL_HP_W + LC23062_HP) * 1.28          # 刃 HP 基数=角色+光锥白值×行迹
        hand = 0.5 * hp * 0.5 * 0.9 * (1 + 0.17 * 0.74)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻（娱乐 CD 24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_ult_energy_boost(self, optimizer_driver):
        """终结技 tally 链（战技+强化普攻预叠 0.4×Max → HP 设 50% 差量 +0.1——
        legacy_1300 先例）→ 大招总和大乐透：我方双段（主 1.5+tally 0.6）vs 对方
        折叠 2.10 单发（段数差在案总和互对）；增伤池 1.4+0.26 双方同值."""
        eng, log = _make_logged(_compiled(_member_build("1205", lc="23062"), "wind"))
        st = eng.state.actors["1205"]
        _cast(eng, "1205", "1120502")               # tally 0.3 / hp 0.7
        _cast(eng, "1205", "1120508")               # tally 0.4 / hp 0.6
        log.clear()
        _fire_ult(eng, "1205", "1120503", energy=130.0)
        ours = _hit_amounts(log, source="1205")
        theirs = run_optimizer(optimizer_driver, _blade_opt(
            "ult", lc_atk=LC23062_ATK, lc_hp=LC23062_HP,
            cond={"enhancedStateActive": True, "hpPercentLostTotal": 0.5},
            base_energy=130.0,
            equipment=_lc("23062", "Destruction",
                          {"ultimateEnergyDmgBoost": True,
                           "kingsEntertainment": True})))

        boost = 0.4 + 0.26                          # HELLSCAPE 0.4 + LC 终结技增伤 0.26
        hp = (BL_HP_W + LC23062_HP) * 1.28
        hand = _bl(1.5 + 1.2 * 0.5, hp=hp, cz=1 + 0.17 * 0.74, boost=boost)
        assert len(ours) == 2, "主段+tally 段（对方折叠单发——段数差在案）"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), "我方大招总和 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1 + boost, rel=REL_TOL), "对方增伤池回显 1.66"


# ===========================================================================
# 光锥对拍——虚无载体（黄泉 1308 / 希露瓦 1103）
# ===========================================================================

class TestLC23059ReforgedInHellfire:
    """灼尽炼狱的新骸 S1（黄泉）：常驻 HP 30%（属性段）+【炼狱】暴伤 30%
    （我方 fixture 炼狱=空标记件——受暴击伤半未收编在案；对方 CD_BOOST 30%
    自件+team 件——driver LC mutual 折主 C 同吃）."""

    def test_hp_panel_baseline(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23059"), "thunder"))
        _clean_knots(eng)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC23059_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"hp": 1125.432 * 1.3},
            equipment=_lc("23059", "Nihility", {"purgatoryState": False})))

        hand = 1.0 * white * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_purgatory_divergence(self, optimizer_driver):
        """S4 结构差：炼狱暴伤（我方空标记件=半未收编在案）→ 钉 true：对方/我方
        = (1+0.05×1.1)/1.025 ≈ 1.029268（对方自件+team 双 CD_BOOST 30% 同吃
        ——driver LC mutual 折主 C 口径）."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23059"), "thunder"))
        _clean_knots(eng)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")[0]
        white = AC_ATK + LC23059_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"hp": 1125.432 * 1.3},
            equipment=_lc("23059", "Nihility", {"purgatoryState": True})))

        assert ours == pytest.approx(1.0 * white * Z, rel=REL_TOL), (
            "我方无炼狱数值段 vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1 + 0.05 * 1.1) / 1.025, rel=REL_TOL)


class TestLC24003SolitaryHealing:
    """孤独的疗愈 S1（桑博——虚无命途门：希露瓦智识吃不上的教训在案）：常驻
    BE 40%（属性段）+ 终结技 DoT 增伤 24%（我方待收——fixture 勘正②在案；
    对方 DOT 标签 BOOST 同值）."""

    def test_be_panel_baseline(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1108", lc="24003"), "wind"))
        _cast(eng, "1108", "110801")
        ours = _hit_amounts(log, source="1108")
        white = SA_ATK_W + LC24003_ATK
        theirs = run_optimizer(optimizer_driver, _sampo_opt(
            "basic", lc_atk=LC24003_ATK, extra_attacker={"be": 0.2},
            equipment=_lc("24003", "Nihility", {"postUltDotDmgBuff": False})))

        hand = 1.0 * white * 1.28 * 0.5 * 0.9 * SA_CZ
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1108")["break_effect"] == pytest.approx(0.2, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.2, rel=REL_TOL), "BE 面板互对"

    def test_dot_divergence(self, optimizer_driver):
        """S5 结构差：终结技 DoT 增伤（我方待收在案）→ 钉 true：对方/我方 =
        1.24（DoT 增伤段；R-SA1 暴击区差已随双通道合并消灭、EHR 权重双方
        同口径 0.65×1.18=0.767——2026-09-22）."""
        eng, log = _make_logged(_compiled(_member_build("1108", lc="24003"), "wind"))
        _cast(eng, "1108", "110801")               # 普攻挂风化（天赋恒中档）
        log.clear()
        eng._tick_dots(eng.state.actors["e1"])     # 声明式跳伤走引擎 A 类结算
        ours = [e["amount"] for e in log
                if e.get("reason") == "dot" and e.get("source") == "1108"]
        white = SA_ATK_W + LC24003_ATK
        theirs = run_optimizer(optimizer_driver, _sampo_opt(
            "dot", lc_atk=LC24003_ATK, extra_attacker={"be": 0.2},
            equipment=_lc("24003", "Nihility", {"postUltDotDmgBuff": True})))

        hand = 0.52 * white * 1.28 * 0.5 * 0.9 * (0.65 * 1.18)   # 不暴击×0.767 期望权重
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方风化跳（无 DoT 增伤段）vs 手算"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(1.24, rel=REL_TOL), (
            "对方 DoT 增伤 24%（暴击区差已消灭、EHR 权重双方同口径——净差=增伤段）")


class TestLC21008EyesOfThePrey:
    """猎物的视线 S1（桑博）：常驻 EHR 20%（属性段面板锚）+ DoT 增伤 24%
    （2026-09-22 双通道合并收官：声明式 dot_tick 增伤区读 dot_dmg_boost 桶
    （施加时刻快照）+ EHR 经 ehr_multi 期望权重——对方 standardDot 同口径，
    三方全等）."""

    def test_dot_boost(self, optimizer_driver):
        """DoT 增伤 24% + EHR 期望权重三方全等（2026-09-22 双通道合并收官——
        声明式 dot_tick 增伤区读 dot_dmg_boost 桶（快照），EHR 0.38（行迹 0.18+
        LC 0.2）经 ehr_multi 0.65×1.38=0.897 乘进跳伤；对方 standardDot 同口径，
        原「增伤 24% 双方全等+剩余 EHR×暴击区差」双因子全灭转三方全等）."""
        eng, log = _make_logged(_compiled(_member_build("1108", lc="21008"), "wind"))
        _cast(eng, "1108", "110801")               # 普攻挂风化（天赋恒中档）
        log.clear()
        eng._tick_dots(eng.state.actors["e1"])     # 声明式跳伤走引擎 A 类结算
        ours = [e["amount"] for e in log
                if e.get("reason") == "dot" and e.get("source") == "1108"]
        white = SA_ATK_W + LC21008_ATK
        theirs = run_optimizer(optimizer_driver, _sampo_opt(
            "dot", lc_atk=LC21008_ATK, extra_attacker={"effect_hit": 0.38},
            equipment=_lc("21008", "Nihility", {})))

        hand = 0.52 * white * 1.28 * 1.24 * 0.5 * 0.9 * (0.65 * 1.38)   # 增伤 1.24×期望权重 0.897
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方风化跳（dot_dmg_boost 桶 24% 快照 + EHR 0.38 期望权重）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 dot vs 手算（三方全等）")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1108")["effect_hit"] == pytest.approx(0.38, rel=REL_TOL), (
            "EHR 面板：0.18 行迹+0.2 LC（对方 stats 无 EHR 回显键——钉面板口径列注）")


class TestLC21047ShadowedByNight:
    """黑夜如影随行 S1（真理医生——巡猎命途门）：常驻 BE 28% + 击破后 spd 8%
    （2 回合——对方 SPD_P 滑条同值，速度无伤害消费）."""

    def test_be_spd_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="21047"), "imaginary",
            enemies=_fragile_toughness("imaginary")))
        _cast(eng, "1305", "130501")               # 击破当次挂 spd 钩
        breaks = _break_amounts(log, "1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21047_ATK, extra_attacker={"be": 0.28},
            equipment=_lc("21047", "Hunt", {"spdBuff": True})))

        hand = 1.0 * _rt_panel(LC21047_ATK) * ZR
        ours = _hit_amounts(log, source="1305")
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1305")["break_effect"] == pytest.approx(0.28, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.28, rel=REL_TOL), "BE 面板互对"
        assert breaks[0] == pytest.approx(BREAK_BASE_10_IMAG * 1.28, rel=REL_TOL), (
            "我方击破段（BE 28% 池）vs 手算")
        assert "LC_21047_SPD" in eng.state.actors["1305"].modifiers, "击破挂 spd 钩"
        assert _eff(eng, "1305")["spd"] == pytest.approx(RT_SPD * 1.08, rel=REL_TOL)
        assert theirs["stats"]["spd"] == pytest.approx(RT_SPD * 1.08, rel=REL_TOL), (
            "spd 面板互对（对方 SPD_P 8% 同值——速度无伤害消费）")


# ===========================================================================
# 光锥对拍——存护载体（杰帕德 1104；Grit 防转攻 0.35×DEF 经 on_turn_start 活读）
# ===========================================================================

def _gp_shield_hand(def_panel: float, bonus: float) -> float:
    """杰帕德终结技护盾手算（110403 lv10：def×0.45+600——B27#6 param 槽在案；
    shield_bonus 池乘算）."""
    return (def_panel * 0.45 + 600.0) * (1 + bonus)


class TestLC21016TrendOfUniversalMarket:
    """宇宙市场趋势 S1（杰帕德）：常驻 DEF 16%（属性段——Grit 转化读出）+
    受击挂【灼烧】（100% 固定概率 expected 恒生效）→ 敌方回合开始跳 def×40%
    火伤（对方控制器全空=未建模，我方 vs 手算单钉——21031 先例）."""

    def test_def_and_burn(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1104", lc="21016"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})   # Grit 挂载
        white_def = GP_DEF_W + LC21016_DEF
        def_panel = white_def * (1.125 + 0.16)           # DEF_P 池加算（行迹 12.5%+LC 16%）
        atk = GP_ATK_W + LC21016_ATK + 0.35 * def_panel  # LC 攻击白值并面板 + Grit 转化
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": GP_ATK_W + LC21016_ATK, "def": white_def},
            extra_attacker={"atk": GP_ATK_W + LC21016_ATK, "def": def_panel},
            equipment=_lc("21016", "Preservation", {})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")

        hand = 1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 DEF 16%（Grit 转化）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

        # 灼烧链：受击（敌方源 100% 概率）→ 敌方回合开始跳 def×40% 火伤
        _emit(eng, "after_being_hit", {"target": "1104", "source": "e1"})
        assert "LC_21016_BURN" in eng.state.actors["e1"].modifiers
        log.clear()
        _turn_start(eng, "e1")
        ticks = _hit_amounts(log, source="1104")
        burn_hand = def_panel * 0.4 * 0.5 * 0.9 * 0.8 * GP_CZ   # 火伤 vs 冰敌抗性 0.8
        assert ticks == pytest.approx([burn_hand], rel=REL_TOL), (
            "我方灼烧跳（def×40%，对方未建模基线列注非病）vs 手算")


class TestLC21030ThisIsMe:
    """这就是我啦！S1（杰帕德）：常驻 DEF 16%（属性段——Grit 转化读出）+
    终结技附加基础伤害 DEF×60%（base_dmg_add 通道正主——决策卡 #17 正例；
    对方控制器 TODO 未实现空壳——我方 vs 手算单钉列注；杰帕德终结技=护盾
    行动无伤害段，附加伤害半在册 carrier 无读出，不单拍）."""

    def test_def_grit(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1104", lc="21030"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})   # Grit 挂载
        white_def = GP_DEF_W + LC21030_DEF
        def_panel = white_def * (1.125 + 0.16)
        atk = GP_ATK_W + LC21030_ATK + 0.35 * def_panel  # LC 攻击白值并面板 + Grit 转化
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": GP_ATK_W + LC21030_ATK, "def": white_def},
            extra_attacker={"atk": GP_ATK_W + LC21030_ATK, "def": def_panel},
            equipment=_lc("21030", "Preservation", {})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")

        hand = 1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 DEF 16%（Grit 转化）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1104")["def_"] == pytest.approx(def_panel, rel=REL_TOL)


class TestLC21053JourneyForeverPeaceful:
    """愿旅途永远坦然 S1（杰帕德）：常驻 shield_bonus 12%（对方 OutputTag.SHIELD
    BOOST 同值——盾值我方 vs 手算单钉，128 先例）+ 我方增伤半待收（team 光环
    无通道在案）→ 对方 dmgBoost mutual FullTeam BOOST 12% 钉 S6."""

    def test_shield_bonus(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1104", lc="21053"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})   # Grit 挂载
        white_def = GP_DEF_W + LC21053_DEF
        def_panel = white_def * 1.125
        _fire_ult(eng, "1104", "110403", energy=100.0)
        shields = eng.state.actors["1104"].shields
        assert len(shields) == 1
        assert shields[0].remaining == pytest.approx(
            _gp_shield_hand(def_panel, 0.12), rel=REL_TOL), (
            "我方护盾（×1.12 池——对方 ULT_SHIELD 技种未注册，单钉 128 先例）")

    def test_dmg_boost_divergence(self, optimizer_driver):
        """S6 结构差：持盾增伤（我方 team 光环无通道在案）→ 钉 true：对方/我方
        = (1+GP_ICE+0.12)/(1+GP_ICE)（对方 12% 与我方行迹冰伤同池加算）."""
        eng, log = _make_logged(_compiled(_member_build("1104", lc="21053"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})
        white_def = GP_DEF_W + LC21053_DEF
        def_panel = white_def * 1.125
        atk = GP_ATK_W + LC21053_ATK + 0.35 * def_panel  # LC 攻击白值并面板 + Grit 转化
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": GP_ATK_W + LC21053_ATK, "def": white_def},
            extra_attacker={"atk": GP_ATK_W + LC21053_ATK, "def": def_panel},
            equipment=_lc("21053", "Preservation",
                          {"shieldBoost": True, "dmgBoost": True})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")[0]

        assert ours == pytest.approx(
            1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE), rel=REL_TOL), (
            "我方无增伤段 vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1 + GP_ICE + 0.12) / (1 + GP_ICE), rel=REL_TOL)


# ===========================================================================
# 光锥对拍——丰饶载体（罗刹 1203；面板 = 白值×1.28 行迹；普攻 1.0 虚数 lv6）
# ===========================================================================

class TestLC23008EchoesOfTheCoffin:
    """棺的回响 S1（罗刹）：常驻 ATK 24%（属性段——对方控制器仅 teammate SPD
    半（mutual 链不拍），atk 段走属性段双方同值；受击回能/大招 SPD 半无伤害
    读出随挂不测）."""

    def test_atk_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1203", lc="23008"), "imaginary"))
        _cast(eng, "1203", "120301")
        ours = _hit_amounts(log, source="1203")
        white = LC_ATK_W + LC23008_ATK
        atk = white * (1.28 + 0.24)                  # ATK_P 池加算（行迹 28%+LC 24%）
        theirs = run_optimizer(optimizer_driver, _lc55_opt(
            "basic", lc_atk=LC23008_ATK, extra_attacker={"atk": atk},
            equipment=_lc("23008", "Abundance", {"postUltSpdBuff": False})))

        hand = 1.0 * atk * 0.5 * 0.9 * LC_CZ
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 ATK 24% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(atk, rel=REL_TOL), (
            "对方 atk 面板回显（ATK_P 池加算口径）")


# ===========================================================================
# 光锥对拍——同谐载体（刻律德菈 1412；面板 = 白值×1.18 行迹；
# CR 1.05 封顶 1.0 → 期望恒 1.5）
# ===========================================================================

class TestLC23026FlowingNightglow:
    """夜色流光溢彩 S1（刻律德菈）：咏叹调回能叠层（无伤害读出随挂不测）+
    终结技后【华彩】自身 atk 48%+全队 all_dmg 24%（对方自件 ATK_P+mutual
    FullTeam BOOST 同值——driver LC mutual 折主 C 口径）."""

    def test_cadenza_window(self, optimizer_driver):
        """S7 结构差（口径）：华彩 atk 48% 双方同挂（对方自件 ATK_P——比等）；
        全队 all_dmg 24%——对方 teammateEffects 只对队友穿戴调用（真实管线
        comboStateTransform.ts:196——主 C 穿戴不折主 C），我方单人队 team 件
        折自身 → 大招后普攻对方/我方 = (1+CY_WIND+0.24)/(1+CY_WIND)；
        当次大招对方另吃 atk 48%（我方结算后挂=当次不吃）→ 1.66/1.18."""
        eng, log = _make_logged(_compiled(_member_build("1412", lc="23026"), "wind"))
        white = CY_ATK_W + LC23026_ATK
        _ult_at(eng, "1412", "141203", 130.0, "1412")
        ours_ult = _hit_amounts(log, source="1412")
        assert "LC_23026_CADENZA_ATK" in eng.state.actors["1412"].modifiers
        theirs_ult = run_optimizer(optimizer_driver, _cy_opt(
            "ult", lc_atk=LC23026_ATK,
            equipment=_lc("23026", "Harmony",
                          {"cantillationStacks": 0, "cadenzaActive": True})))

        assert ours_ult == pytest.approx(
            [2.4 * white * 1.18 * (1 + CY_WIND) * Z_CY], rel=REL_TOL), (
            "我方当次大招（无华彩段）vs 手算")
        assert theirs_ult["hits"][0]["damage"] / ours_ult[0] == pytest.approx(
            1.66 / 1.18, rel=REL_TOL), "当次大招：对方自件 atk 48% 生效 vs 我方未挂"

        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")[1]      # [0]=当次大招段
        atk_panel = white * 1.66
        # 行迹 atkToCd 公式差（S-结构差②）：我方连续式 (atk-2000)×0.0018 vs
        # 对方 floor 阶梯 0.18×floor((atk-2000)/100)（S12 连续 vs floor 同族）——
        # 2084.9 档：我方 0.15283 vs 对方 0（batch3 各件 atk<2000 未触档，本件首实例）
        cd_ours = 0.5 + (atk_panel - 2000) * 0.0018
        hand = 1.0 * atk_panel * (1 + CY_WIND + 0.24) * 0.5 * 0.9 * (1 + 1.0 * cd_ours)
        assert ours == pytest.approx(hand, rel=REL_TOL), (
            "我方大招后普攻（华彩+atkToCd 连续档）vs 手算")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", lc_atk=LC23026_ATK,
            equipment=_lc("23026", "Harmony",
                          {"cantillationStacks": 0, "cadenzaActive": True})))
        # S7 复合钉：team 件口径（对方 1.224 vs 我方 1.464）× atkToCd 公式差
        # （对方 critMulti 1.5 floor 档 vs 我方 1.652825 连续档）
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.224, rel=REL_TOL), "对方 team 件不折主 C（增伤池回显自证）"
        assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(
            1.5, rel=REL_TOL), "对方 atkToCd floor 档（2084.9 → floor 0）回显自证"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1.224 * 1.5) / (1.464 * (1 + cd_ours)), rel=REL_TOL), (
            "S7 复合：team 件口径 × atkToCd 连续 vs floor")
        assert theirs["stats"]["atk"] == pytest.approx(white * 1.66, rel=REL_TOL), (
            "对方华彩 ATK_P 48% 面板回显（双方同值）")


class TestLC22007TomorrowTogether:
    """未来，有我们一起 S1（刻律德菈）：常驻 CD 12%（属性段）+ 终结技后全队
    欢愉度 8%（对方 mutual FullTeam ELATION 同值——刻律无欢愉伤读出，欢愉度
    面板回显互对列注）."""

    def test_cd_panel_and_elation_echo(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1412", lc="22007"), "wind"))
        white = CY_ATK_W + LC22007_ATK
        _ult_at(eng, "1412", "141203", 130.0, "1412")
        assert "LC_22007_TEAM_ELATION" in eng.state.actors["1412"].modifiers
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")[1]
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", lc_atk=LC22007_ATK, extra_attacker={"cd": 0.62},
            equipment=_lc("22007", "Harmony", {"elationBuff": True})))

        hand = 1.0 * white * 1.18 * (1 + CY_WIND) * 0.5 * 0.9 * (1 + 1.0 * 0.62)
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方常驻 CD 12% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1412")["elation"] == pytest.approx(0.08, rel=REL_TOL)
        assert theirs["stats"]["elation"] == pytest.approx(0.08, rel=REL_TOL), (
            "欢愉度面板互对（对方 mutual FullTeam ELATION 8% 同值）")


class TestLC21004MemoriesOfThePast:
    """记忆中的模样 S1（刻律德菈）：常驻 BE 28%（属性段）+ 行动回能（无伤害
    读出随挂不测）."""

    def test_be_panel_and_break(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1412", lc="21004"), "wind",
            enemies=_fragile_toughness("wind")))
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        breaks = _break_amounts(log, "1412")
        white = CY_ATK_W + LC21004_ATK
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", lc_atk=LC21004_ATK, extra_attacker={"be": 0.28},
            equipment=_lc("21004", "Harmony", {})))

        hand = 1.0 * white * 1.18 * (1 + CY_WIND) * Z_CY
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1412")["break_effect"] == pytest.approx(0.28, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.28, rel=REL_TOL), "BE 面板互对"
        assert breaks[0] == pytest.approx(BREAK_BASE_10_WIND * 1.28, rel=REL_TOL), (
            "我方击破段（BE 28% 池）vs 手算")


# ===========================================================================
# 光锥对拍——记忆载体（遐蝶 1407；普攻 0.5×HP 量子；死龙链 140703 新蕊钉满
# 实打——遗世冥域 res_pen 0.2（×1.2 抗区）+ 怒啸 0.1（增伤池）两侧同挂）
# ===========================================================================

def _ca_hand(hp: float, pool: float, cz: float = Z_CA_CRIT) -> float:
    """遐蝶普攻手算（0.5×HP×增伤池×0.5×0.9×期望暴击×1.2 抗区——死龙在场场）."""
    return 0.5 * hp * pool * 0.5 * 0.9 * cz * 1.2


class TestLC23036TimeWovenIntoGold:
    """将光阴织成黄金 S1（遐蝶）：基础速度 +12（属性段）+【织金】暴伤 9%×N
    （钳 6，行动命中后叠）+ 满层普攻增伤 9%×6（对方 CD+BASIC BOOST 同值——
    双方叠层窗口内当次不吃）."""

    def test_brocade_stacks(self, optimizer_driver):
        """普攻 ×7：#7 @6 层（我方逐发叠层——当次不吃；对方 brocadeStacks=6
        滑条直接满档）比等."""
        eng, log = _make_logged(_compiled(_member_build("1407", lc="23036"), "quantum"))
        _summon_nw(eng)
        hp_panel = CA_HP + LC23036_HP
        for _ in range(7):
            _cast(eng, "1407", "140701")
        basics = _hits_of(log, source="1407", action_type="basic")
        assert len(basics) == 7
        got = basics[6]
        assert eng.state.actors["1407"].modifiers["LC_23036_BROCADE"].stacks == 6

        cd = CA_CD + 6 * 0.09
        cz = 1 + CA_CR * cd
        pool = 1 + CA_Q + 0.1 + 0.54
        theirs = run_optimizer(optimizer_driver, _ca_opt(
            "basic", lc_hp=LC23036_HP,
            equipment=_lc("23036", "Remembrance",
                          {"brocadeStacks": 6, "maxStacksBasicDmgBoost": True})))
        hand = _ca_hand(hp_panel, pool, cz)
        assert got == pytest.approx(hand, rel=REL_TOL), "我方普攻 @6 层织金 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert got == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["cd"] == pytest.approx(cd, rel=REL_TOL), (
            "对方织金 CD 面板回显")


class TestLC23040MakeFarewellsBeautiful:
    """让告别，更美一些 S1（遐蝶）：常驻 HP 30%（属性段）+ 耗血后【冥花】
    def_pen 30% 2回合（对方 DEF_PEN SelfAndMemosprite 同值）."""

    def test_hp_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1407", lc="23040"), "quantum"))
        _summon_nw(eng)
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        hp_panel = (CA_HP + LC23040_HP) * 1.3          # HP_P 30% 属性段（对方钉面板）
        theirs = run_optimizer(optimizer_driver, _ca_opt(
            "basic", lc_hp=LC23040_HP, extra_attacker={"hp": hp_panel},
            equipment=_lc("23040", "Remembrance", {"deathFlower": False})))

        hand = _ca_hand(hp_panel, 1 + CA_Q + 0.1)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线（HP 属性段）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_death_flower_window(self, optimizer_driver):
        """事件前钉 S8（我方 on_hp_decrease 结算后挂=事件前不吃；对方恒开）→
        def 区比 1.176471；事件后比等（耗血事件同时叠荒芜 1 层——对方
        talentDmgStacks=1 双方同挂）."""
        eng, log = _make_logged(_compiled(_member_build("1407", lc="23040"), "quantum"))
        _summon_nw(eng)
        hp_panel = (CA_HP + LC23040_HP) * 1.3
        _cast(eng, "1407", "140701")
        first = _hit_amounts(log, source="1407")[0]
        sc = _ca_opt(
            "basic", lc_hp=LC23040_HP, extra_attacker={"hp": hp_panel},
            equipment=_lc("23040", "Remembrance", {"deathFlower": True}))
        theirs = run_optimizer(optimizer_driver, sc)

        assert first == pytest.approx(_ca_hand(hp_panel, 1 + CA_Q + 0.1),
                                      rel=REL_TOL), "我方事件前普攻（无冥花）vs 手算"
        def_multi = 100 / (100 * (1 - 0.3) + 100)
        assert theirs["hits"][0]["damage"] / first == pytest.approx(
            def_multi / 0.5, rel=REL_TOL), "S8：对方恒开冥花 def 区自证"

        _emit(eng, "on_hp_decrease",
              {"target": "1407", "reason": "drain", "amount": 100.0})
        assert "LC_23040_DEATH_FLOWER" in eng.state.actors["1407"].modifiers
        _cast(eng, "1407", "140701")
        second = _hit_amounts(log, source="1407")[1]
        sc2 = _ca_opt(
            "basic", lc_hp=LC23040_HP, extra_attacker={"hp": hp_panel},
            equipment=_lc("23040", "Remembrance", {"deathFlower": True}))
        sc2["conditionals"]["talentDmgStacks"] = 1      # 耗血荒芜 1 层双方同挂
        theirs2 = run_optimizer(optimizer_driver, sc2)
        hand = (0.5 * hp_panel * (1 + CA_Q + 0.1 + 0.2) * def_multi * 0.9
                * Z_CA_CRIT * 1.2)
        assert second == pytest.approx(hand, rel=REL_TOL), (
            "我方事件后普攻（冥花+荒芜 1 层）vs 手算")
        assert theirs2["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs2["hits"][0]["damage"], rel=REL_TOL)


class TestLC23049ToEvernightsStars:
    """致长夜的星光 S1（遐蝶）：常驻 HP 30%（属性段）+ 忆灵行动后【夜色】
    自身 all_dmg 30%（对方 BOOST SelfAndMemosprite 同值）."""

    def test_night_self_dmg(self, optimizer_driver):
        """死龙在场 + 忆灵技（1140702）→【夜色】→ 遐蝶普攻比等（忆灵 def_pen
        半对方 mutual Memosprite 槽 driver 无忆灵队友不拍列注）."""
        eng, log = _make_logged(_compiled(_member_build("1407", lc="23049"), "quantum"))
        _summon_nw(eng)
        _cast(eng, "1407_netherwing", "1140702")       # 忆灵技 → 夜色标记
        assert "LC_23049_NIGHT" in eng.state.actors["1407"].modifiers
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        hp_panel = (CA_HP + LC23049_HP) * 1.3          # HP_P 30% 属性段（对方钉面板）
        sc = _ca_opt(
            "basic", lc_hp=LC23049_HP, extra_attacker={"hp": hp_panel},
            equipment=_lc("23049", "Remembrance", {"defPen": False, "dmgBoost": True}))
        sc["conditionals"]["talentDmgStacks"] = 1      # 忆灵技耗血荒芜 1 层双方同挂
        theirs = run_optimizer(optimizer_driver, sc)

        hand = _ca_hand(hp_panel, 1 + CA_Q + 0.1 + 0.3 + 0.2)   # 夜色 0.3+荒芜 0.2
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方夜色普攻（+30%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21050VictoryInABlink:
    """胜利只在朝夕间 S1（遐蝶）：常驻 CD 12%（属性段）；忆灵 ally 指向技
    触发全队增伤 8%——死龙忆灵技指敌不触发（ally 指向忆灵技载体缺在案，
    batch3 案列注），对方 mutual FullTeam BOOST 同值亦不拍."""

    def test_crit_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1407", lc="21050"), "quantum"))
        _summon_nw(eng)
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        hp_panel = CA_HP + LC21050_HP
        cd = CA_CD + 0.12
        cz = 1 + CA_CR * cd
        theirs = run_optimizer(optimizer_driver, _ca_opt(
            "basic", lc_hp=LC21050_HP, extra_attacker={"cd": cd},
            equipment=_lc("21050", "Remembrance", {"teamDmgBuff": False})))

        hand = _ca_hand(hp_panel, 1 + CA_Q + 0.1, cz)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CD 12% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21057TheFlowerRemembers:
    """花儿不会忘记 S1（遐蝶）：常驻 CD 24%（属性段）；忆灵暴伤半对方
    Memosprite CD_BOOST 槽（死龙无暴伤读出在案列注）钉 false 双方同灭."""

    def test_crit_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1407", lc="21057"), "quantum"))
        _summon_nw(eng)
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        hp_panel = CA_HP + LC21057_HP
        cd = CA_CD + 0.24
        cz = 1 + CA_CR * cd
        theirs = run_optimizer(optimizer_driver, _ca_opt(
            "basic", lc_hp=LC21057_HP, extra_attacker={"cd": cd},
            equipment=_lc("21057", "Remembrance", {"memoCdBoost": False})))

        hand = _ca_hand(hp_panel, 1 + CA_Q + 0.1, cz)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CD 24% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC22006FlyIntoAPinkTomorrow:
    """飞向粉色的明天 S1（遐蝶）：常驻 CD 12%（属性段）+ 全队 all_dmg 8%
    （对方 mutual FullTeam BOOST 同值——driver LC mutual 折主 C 口径；
    强化普攻 60% 半我方待收（8007/8008 链 batch3 案）钉 false）."""

    def test_crit_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1407", lc="22006"), "quantum"))
        _summon_nw(eng)
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        hp_panel = CA_HP + LC22006_HP
        cd = CA_CD + 0.12
        cz = 1 + CA_CR * cd
        theirs = run_optimizer(optimizer_driver, _ca_opt(
            "basic", lc_hp=LC22006_HP, extra_attacker={"cd": cd},
            equipment=_lc("22006", "Remembrance",
                          {"dmgBoost": False, "enhancedBasicBoost": False})))

        hand = _ca_hand(hp_panel, 1 + CA_Q + 0.1, cz)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CD 12% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_team_dmg_both_gated(self, optimizer_driver):
        """全队增伤 8%：双方同门控（我方 8007/8008 双 id 门=官方「开拓者•记忆
        装备时」；对方控制器亦硬编码 8007/8008 门——comboStateTransform 主 C
        穿戴不折主 C 同口径）→ 遐蝶场双方同灭比等."""
        eng, log = _make_logged(_compiled(_member_build("1407", lc="22006"), "quantum"))
        _summon_nw(eng)
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        hp_panel = CA_HP + LC22006_HP
        cd = CA_CD + 0.12
        cz = 1 + CA_CR * cd
        theirs = run_optimizer(optimizer_driver, _ca_opt(
            "basic", lc_hp=LC22006_HP, extra_attacker={"cd": cd},
            equipment=_lc("22006", "Remembrance",
                          {"dmgBoost": True, "enhancedBasicBoost": False})))

        hand = _ca_hand(hp_panel, 1 + CA_Q + 0.1, cz)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方无全队增伤段（门控双方同灭）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21035WhatIsReal:
    """何物为真 S1（罗刹——丰饶命途门）：常驻 BE 24%（属性段面板锚；受击
    治疗半无伤害读出随挂不测）."""

    def test_be_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1203", lc="21035"), "imaginary"))
        _cast(eng, "1203", "120301")
        ours = _hit_amounts(log, source="1203")
        white = LC_ATK_W + LC21035_ATK
        atk = white * 1.28
        theirs = run_optimizer(optimizer_driver, _lc55_opt(
            "basic", lc_atk=LC21035_ATK, extra_attacker={"atk": atk, "be": 0.24},
            equipment=_lc("21035", "Abundance", {})))

        hand = 1.0 * atk * 0.5 * 0.9 * LC_CZ
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1203")["break_effect"] == pytest.approx(0.24, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.24, rel=REL_TOL), "BE 面板互对"


# ===========================================================================
# 光锥对拍——欢愉载体（火花 1501；火，ATK 倍率；行迹 crit 0.12/0.133/
# elation 0.28 已并入；欢愉技 150120=21 段聚合 5.5、笑点池 30；
# 欢愉伤害=7535.107×倍率×(1+elation)×笑点乘区×期望暴击×0.5×0.9）
# ===========================================================================

def _sp_el(cz: float, *, el: float = SP_EL, vuln: float = 0.0) -> float:
    """火花欢愉技 21 段聚合手算（5.5×等级系数×(1+el)×笑点(30)×cz×0.5×0.9×易伤）."""
    return _el(5.5, 30, cz, el=el, vuln=vuln)


class TestLC21064MushyShroomys:
    """菇菇嘎嘎历险记 S1（火花）：欢愉度常驻 12%（对方未建模列注）+ 欢愉技
    挂【易伤】6%（对方 mutual FullTeam ELATION 标签 VULNERABILITY 同值——
    driver LC mutual 折主 C 口径）."""

    def test_vuln_window(self, optimizer_driver):
        """S9 复合钉（段时序在案——on_action 钩在主段后/追加段前发射）：首技
        0.5 主段无易伤/0.25 追加段吃易伤 6% × 常驻欢愉度差（我方 0.12 对方
        未建模）；第 2 技全段易伤自吃、只剩欢愉度差."""
        eng, log = _make_logged(_compiled(_member_build("1501", lc="21064"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150120")
        first = sum(_hit_amounts(log, source="1501"))
        white = SP_ATK + LC21064_ATK
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "elation_skill", lc_atk=LC21064_ATK,
            equipment=_lc("21064", "Elation", {"elationVulnerability": True})))

        cz = 1 + SP_CR * SP_CD_P30
        hand_first = _el(0.5, 30, cz, el=SP_EL + 0.12) + _el(
            5.0, 30, cz, el=SP_EL + 0.12, vuln=0.06)
        assert first == pytest.approx(hand_first, rel=REL_TOL), (
            "我方首技（主段无易伤/追加段吃易伤+常驻欢愉 12%）vs 手算")
        assert theirs["hits"][0]["damage"] / first == pytest.approx(
            _el(5.5, 30, cz, el=SP_EL, vuln=0.06) / hand_first, rel=REL_TOL), (
            "S9 首技：对方全段易伤恒开+无常驻欢愉度 vs 我方段时序+常驻")

        _cast(eng, "1501", "150120")
        second = sum(_hit_amounts(log, source="1501")[21:])
        hand_second = _sp_el(cz, el=SP_EL + 0.12, vuln=0.06)
        assert second == pytest.approx(hand_second, rel=REL_TOL), (
            "我方第 2 技（全段易伤自吃）vs 手算")
        assert theirs["hits"][0]["damage"] / second == pytest.approx(
            (1 + SP_EL) / (1 + SP_EL + 0.12), rel=REL_TOL), (
            "S9 第 2 技：只剩常驻欢愉度差（我方 0.12 对方未建模）")


class TestLC21065TodaysGoodLuck:
    """今日好手气 S1（火花）：常驻 CR 12%（属性段）+ 欢愉技叠层欢愉度
    12%×N（钳 2；对方 ELATION 滑条同值）."""

    def test_elation_stacks(self, optimizer_driver):
        """欢愉技 ×3 逐档钉（段时序在案——叠层钩在主段后/追加段前发射：
        当技 0.5 主段@n 层、0.25 追加段@min(n+1,2) 层；对方滑条全段直档）——
        @0/@1 段时序差钉复合比、@2 满层双方全等."""
        eng, log = _make_logged(_compiled(_member_build("1501", lc="21065"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        white = SP_ATK + LC21065_ATK
        cz = 1 + (SP_CR + 0.12) * SP_CD_P30
        log.clear()
        for _ in range(3):
            _cast(eng, "1501", "150120")
        ours = [sum(_hit_amounts(log, source="1501")[i * 21:(i + 1) * 21])
                for i in range(3)]
        assert eng.state.actors["1501"].modifiers["LC_21065_LUCKY_STACK"].stacks == 2

        # 段时序：@n 当技 = 0.5 主段@n 层 + 0.25 追加段@min(n+1, 2) 层
        # （叠层钩在主段后/追加段前发射——当技追加段已吃当层）
        def hand_ours(n):
            main_el = SP_EL + 0.12 * min(n, 2)
            add_el = SP_EL + 0.12 * min(n + 1, 2)
            return (_el(0.5, 30, cz, el=main_el)
                    + _el(5.0, 30, cz, el=add_el))

        for n, got in enumerate(ours):
            theirs = run_optimizer(optimizer_driver, _sparxie_opt(
                "elation_skill", lc_atk=LC21065_ATK, extra_attacker={"cr": SP_CR + 0.12},
                equipment=_lc("21065", "Elation", {"elationStacks": n})))
            hand_theirs = _sp_el(cz, el=SP_EL + 0.12 * n)
            assert got == pytest.approx(hand_ours(n), rel=REL_TOL), (
                f"我方欢愉技 @{n} 层（段时序）vs 手算")
            assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL)
            assert theirs["hits"][0]["damage"] / got == pytest.approx(
                hand_theirs / hand_ours(n), rel=REL_TOL), (
                f"双方复合互对 @{n} 层（对方全段直档 vs 我方段时序）")


class TestLC23053DazzledByFloweryWorld:
    """花花世界迷人眼 S1（火花）：常驻 CD 48%（属性段）+ 耗点叠层欢愉伤
    无视防御 5%×N（我方待收——scoped 无视防御无通道在案，23057/129 同案；
    对方 DEF_PEN·ELATION 标签同值；elationBuff  mutual 钉 false 隔离）."""

    def test_crit_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1501", lc="23053"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150101")
        ours = _hit_amounts(log, source="1501")
        white = SP_ATK + LC23053_ATK
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "basic", lc_atk=LC23053_ATK, extra_attacker={"cd": SP_CD + 0.48},
            equipment=_lc("23053", "Elation",
                          {"spConsumedStacks": 0, "elationBuff": False})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + SP_CR * (SP_CD_P30 + 0.48))
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CD 48% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_elation_def_pen_divergence(self, optimizer_driver):
        """S10 已收官（2026-09-23）：耗点叠层欢愉无视防御——sp_consumed 载荷槽叠
        LC_23053_SP 计数件 + hit_stat_exprs def_pen=param_6×min(stacks,4)（elation_damage
        命中域限定）收编。计数件对拍钉 4 层（叠层钩实打另测）→ 双方 0.20 穿透，三方全等."""
        eng, log = _make_logged(_compiled(_member_build("1501", lc="23053"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        eng._apply_modifier(eng.state.actors["1501"], Modifier(
            modifier_id="LC_23053_SP", name="花花世界·耗点计数", modifier_type="buff",
            stacks=4, max_stack=4, duration=0, dispellable=False))
        log.clear()
        _cast(eng, "1501", "150120")
        ours = sum(_hit_amounts(log, source="1501"))
        white = SP_ATK + LC23053_ATK
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "elation_skill", lc_atk=LC23053_ATK, extra_attacker={"cd": SP_CD + 0.48},
            equipment=_lc("23053", "Elation",
                          {"spConsumedStacks": 4, "elationBuff": False})))

        cz = 1 + SP_CR * (SP_CD_P30 + 0.48)
        def_multi = 100 / (100 * (1 - 0.20) + 100)
        hand = _sp_el(cz) * (def_multi / 0.5)
        assert ours == pytest.approx(hand, rel=REL_TOL), (
            "我方 4 层穿透场（defMulti 100/180）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_sp_consumed_stacking_mechanic(self, optimizer_driver):
        """S10 叠层钩实打（2026-09-23 收编）：战技耗 1 点 → LC_23053_SP +1
        （on_action sp_consumed 槽——实际耗点净值）；穿透件 hit_stat_exprs 随层
        求值（2 层 0.10 → defMulti 100/190）——我方 vs 手算."""
        eng, log = _make_logged(_compiled(_member_build("1501", lc="23053"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        st = eng.state.actors["1501"]
        assert "LC_23053_SP" not in st.modifiers
        _cast(eng, "1501", "150102")   # 耗 1 点 → 计数 1
        assert st.modifiers["LC_23053_SP"].stacks == 1
        _cast(eng, "1501", "150102")   # 再耗 1 点 → 计数 2
        assert st.modifiers["LC_23053_SP"].stacks == 2
        _pin_pool_gain(eng, "1501", 30.0)   # 池钉回 30（战技笑点收入隔离——palette 锚）
        log.clear()
        _cast(eng, "1501", "150120")
        ours = sum(_hit_amounts(log, source="1501"))
        cz = 1 + SP_CR * (SP_CD_P30 + 0.48)
        def_multi = 100 / (100 * (1 - 0.10) + 100)
        assert ours == pytest.approx(_sp_el(cz) * (def_multi / 0.5), rel=REL_TOL), (
            "2 层穿透场（defMulti 100/190）vs 手算")


class TestLC23054WhenSheDecidedToSee:
    """当她决定看见 S1（火花）：常驻 SPD 18%（属性段）+【上上签】暴击率
    10%+暴伤 30%（对方 mutual FullTeam CR/CD 同值——driver LC mutual 折主 C
    口径，双方常驻互对）."""

    def test_great_fortune(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1501", lc="23054"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150101")
        ours = _hit_amounts(log, source="1501")
        white = SP_ATK + LC23054_ATK
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "basic", lc_atk=LC23054_ATK,
            equipment=_lc("23054", "Elation", {"greatFortune": True})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + (SP_CR + 0.10) * (SP_CD_P30 + 0.30))
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方上上签双暴（CR 10%+CD 30%）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23057WelcomeCosmicCity:
    """欢迎来到银河城 S1（火花）：常驻 SPD 18%（属性段）+ 终结技笑点（对方
    未建模列注随挂不测）+ 欢愉伤无视防御 20%（我方待收——scoped 无通道在案；
    对方 DEF_PEN·ELATION 标签同值）."""

    def test_elation_def_pen_divergence(self, optimizer_driver):
        """S11 已收官（2026-09-23）：欢愉无视防御 20%——LC_23057_ELATION_DEF_PEN
        常驻件（hit_condition elation_damage 路由标识）收编，双方 0.20 穿透，三方全等."""
        eng, log = _make_logged(_compiled(_member_build("1501", lc="23057"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150120")
        ours = sum(_hit_amounts(log, source="1501"))
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "elation_skill", lc_atk=LC23057_ATK,
            equipment=_lc("23057", "Elation", {"elationDefPen": True})))

        cz = 1 + SP_CR * SP_CD_P30
        def_multi = 100 / (100 * (1 - 0.20) + 100)
        hand = _sp_el(cz) * (def_multi / 0.5)
        assert ours == pytest.approx(hand, rel=REL_TOL), (
            "我方欢愉穿透场（defMulti 100/180）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


class TestLC23058UntilFlowersBloom:
    """邂逅于下一个花季 S1（火花）：常驻 CD 60%（属性段）+ ERR 公式半（无
    伤害读出随挂不测）+ 欢愉技挂敌方易伤 15%（对方 mutual FullTeam
    VULNERABILITY 同值）."""

    def test_crit_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1501", lc="23058"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150101")
        ours = _hit_amounts(log, source="1501")
        white = SP_ATK + LC23058_ATK
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "basic", lc_atk=LC23058_ATK, extra_attacker={"cd": SP_CD + 0.60},
            equipment=_lc("23058", "Elation", {"vulnerability": False})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + SP_CR * (SP_CD_P30 + 0.60))
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CD 60% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_vuln_window(self, optimizer_driver):
        """S12 结构差（段时序在案——on_action 钩在主段后/追加段前发射）：首技
        0.5 主段无易伤/0.25 追加段吃易伤 15%（对方 mutual 恒开全段）→ 首技
        对方/我方 = 6.325/6.25 ≈ 1.012；第 2 技全段自吃比等."""
        eng, log = _make_logged(_compiled(_member_build("1501", lc="23058"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        white = SP_ATK + LC23058_ATK
        cz = 1 + SP_CR * (SP_CD_P30 + 0.60)
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "elation_skill", lc_atk=LC23058_ATK, extra_attacker={"cd": SP_CD + 0.60},
            equipment=_lc("23058", "Elation", {"vulnerability": True})))
        log.clear()
        _cast(eng, "1501", "150120")
        first = sum(_hit_amounts(log, source="1501"))
        hand_first = _el(0.5, 30, cz, el=SP_EL) + _el(5.0, 30, cz, el=SP_EL, vuln=0.15)
        assert first == pytest.approx(hand_first, rel=REL_TOL), (
            "我方首技（主段无易伤/追加段吃易伤）vs 手算")
        assert theirs["hits"][0]["damage"] / first == pytest.approx(
            _el(5.5, 30, cz, el=SP_EL, vuln=0.15) / hand_first, rel=REL_TOL), (
            "S12 首技：对方全段易伤恒开 vs 我方段时序（6.325/6.25）")

        _cast(eng, "1501", "150120")
        second = sum(_hit_amounts(log, source="1501")[21:])
        hand = _sp_el(cz, vuln=0.15)
        assert second == pytest.approx(hand, rel=REL_TOL), "我方第 2 技（全段自吃）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC24006ElationBrimming:
    """欢愉满溢祝福 S1（火花）：常驻 ATK 20%（属性段）+ 战技/终结技对友方
    单体 → 目标欢愉度 12%（火花技能指敌无落点=双方非同挂；对方自件
    ELATION 同值）."""

    def test_atk_panel(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1501", lc="24006"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150101")
        ours = _hit_amounts(log, source="1501")
        white = SP_ATK + LC24006_ATK
        atk = white * 1.2
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "basic", lc_atk=LC24006_ATK, extra_attacker={"atk": atk},
            equipment=_lc("24006", "Elation", {"elationBuff": False})))

        hand = 1.0 * atk * 0.5 * 0.9 * (1 + SP_CR * SP_CD_P30)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 ATK 20% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_elation_divergence(self, optimizer_driver):
        """S13 结构差：欢愉度归属（我方技能指敌无落点 vs 对方自件 ELATION
        12%）→ 对方/我方 = (1+SP_EL+0.12)/(1+SP_EL)."""
        eng, log = _make_logged(_compiled(_member_build("1501", lc="24006"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150120")
        ours = sum(_hit_amounts(log, source="1501"))
        white = SP_ATK + LC24006_ATK
        atk = white * 1.2
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "elation_skill", lc_atk=LC24006_ATK, extra_attacker={"atk": atk},
            equipment=_lc("24006", "Elation", {"elationBuff": True})))

        cz = 1 + SP_CR * SP_CD_P30
        assert ours == pytest.approx(_sp_el(cz), rel=REL_TOL), (
            "我方无目标欢愉段落点 vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1 + SP_EL + 0.12) / (1 + SP_EL), rel=REL_TOL)


class TestLC20023Sneering:
    """嗤笑 S1（火花）：阿哈时刻内欢愉度+16%（对方 actionKind==ELATION_SKILL
    门控 ELATION 同值——我方 aha_instant 窗口与对方行动门控口径差在案）."""

    def test_elation_divergence(self, optimizer_driver):
        """S14 结构差：阿哈窗口（我方 aha_instant 链不可达 vs 对方行动门控
        ELATION 16%）→ 对方/我方 = (1+SP_EL+0.16)/(1+SP_EL)."""
        eng, log = _make_logged(_compiled(_member_build("1501", lc="20023"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150120")
        ours = sum(_hit_amounts(log, source="1501"))
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "elation_skill", lc_atk=LC20023_ATK,
            equipment=_lc("20023", "Elation", {"elationBuff": True})))

        cz = 1 + SP_CR * SP_CD_P30
        assert ours == pytest.approx(_sp_el(cz), rel=REL_TOL), (
            "我方无阿哈窗口段（aha_instant 链不可达列注）vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1 + SP_EL + 0.16) / (1 + SP_EL), rel=REL_TOL)


class TestLC20024LingeringTear:
    """残泪 S1（火花）：笑点≥10 时暴伤+20%（对方 CD 开关同值——笑点 30 场
    双方同闸开）."""

    def test_cd_buff(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1501", lc="20024"), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150120")
        ours = sum(_hit_amounts(log, source="1501"))
        white = SP_ATK + LC20024_ATK
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "elation_skill", lc_atk=LC20024_ATK,
            equipment=_lc("20024", "Elation", {"cdBuff": True})))

        cz = 1 + SP_CR * (SP_CD_P30 + 0.20)
        hand = _sp_el(cz)
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方笑点≥10 暴伤 20% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# 遗器对拍——机制族（batch3 docstring 已映射未实现的 6 件本波补齐 + 124/129/130）
# ===========================================================================

def _team_relic_build(wearer: str, set_id: str, teammate: str):
    """双成员 build·遗器版（wearer 带套装，队友只承事件不出手——_team_build2
    同形；_team_build2 第二参是光锥模板，遗器套走本助手）."""
    return {"build": {"team": [
        {"character_template": wearer, "level": 80,
         "relics": {f"slot{i}": {"set_id": set_id} for i in range(4)}},
        {"character_template": teammate, "level": 80},
    ], "policy": _POLICY}}


class TestRelic107Firesmith:
    """熔岩锻铸的火匠（虎克——自体战技载体；托帕+账账场撞 R-TP1 召唤物面板
    继承差在案，不取）：2pc 火伤 10% + 4pc 战技增伤 12%（双方 stat/p4x
    通道同值）+ 终结技后下一次攻击火伤 12%（我方 on_ultimate 钩=当次大招
    不吃且仅下次攻击；对方 enabled 开关恒开=近似）."""

    def test_skill_and_ult_fire_window(self, optimizer_driver):
        """首次战技钉 S15（对方恒开含当次 vs 我方钩后挂）→ 1.34/1.22；
        大招后下一次战技双方比等（均 1.34 池）."""
        eng, log = _make_logged(_compiled(
            _member_build("1109", set_id="107", pieces=4), "fire"))
        _cast(eng, "1109", "110902")               # 首次战技（灼烧伤后挂载）
        first = _hit_amounts(log, source="1109")
        theirs = run_optimizer(optimizer_driver, _hook_opt(
            "skill", cond={"targetBurned": False},
            equipment=_relic("107", 4, {"enabledFiresmithOfLavaForging": True})))

        hand_first = 2.4 * HK_ATK * (1 + 0.1 + 0.12) * 0.5 * 0.9 * HK_CZ
        assert first == pytest.approx([hand_first], rel=REL_TOL), (
            "我方首次战技（2pc+4pc，终结技火伤未挂）vs 手算")
        assert theirs["hits"][0]["damage"] / first[0] == pytest.approx(
            (1 + 0.1 + 0.12 + 0.12) / (1 + 0.1 + 0.12), rel=REL_TOL), (
            "S15：对方终结技火伤 12% 恒开 vs 我方钩后挂")

        _fire_ult(eng, "1109", "110903", energy=120.0)
        _cast(eng, "1109", "110902")               # 大招后下一次战技
        second = _hits_of(log, source="1109", action_type="skill")[1]
        hand = 2.4 * HK_ATK * (1 + 0.1 + 0.12 + 0.12) * 0.5 * 0.9 * HK_CZ
        assert second == pytest.approx(hand, rel=REL_TOL), (
            "我方大招生效后战技（+12% 火伤）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestRelic119IronCavalry:
    """荡除蠹灾的铁骑（白厄）：2pc BE 16%（面板回显互对+击破段 ×1.16 vs
    手算）；4pc 击破/超击破无视防御——**待收**（类型限定无视防御无通道在案）
    → 对方 p4t DEF_PEN 同灭列注（kind=character 无击破段不可见，23050 先例）."""

    def test_be_panel_and_break(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1408", set_id="119", pieces=4), "physical",
            enemies=_fragile_toughness("physical")))
        _cast(eng, "1408", "140801")
        breaks = _break_amounts(log, "1408")
        white = PH_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", equipment=_relic("119", 4, {})))

        hand = 1.0 * white * 1.5 * Z_PH
        ours = _hit_amounts(log, source="1408")
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1408")["break_effect"] == pytest.approx(0.16, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.16, rel=REL_TOL), "BE 面板互对"
        assert breaks[0] == pytest.approx(BREAK_BASE_10_PHY * 1.16, rel=REL_TOL), (
            "我方击破段（BE 16% 池）vs 手算")


class TestRelic121Sacerdos:
    """重循苦旅的司铎（星期日→真理）：2pc spd 6%（面板回显互对）；4pc 对
    友方单体战技/终结技 → 目标 crit_dmg 18%×N（钳 2）——对方 value 滑条=
    self CD 简化模型（官方落点=技能目标，映射表注）；星期日战技污染件
    （增伤 30%/CR 20%）摘除回空白 slate（_clean_knots 先例）."""

    def test_4pc_two_stacks(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_relic_build("1313", "121", "1305"), "imaginary"))   # 星期日穿戴→真理承 stacks
        _sunday_skill(eng, "1305")                 # 星期日战技①（污染件随摘）
        _sunday_skill(eng, "1305")                 # 星期日战技②
        assert eng.state.actors["1305"].modifiers["SET_121_CRITDMG"].stacks == 2
        log.clear()
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", equipment=_relic("121", 4, {"valueSacerdosRelivedOrdeal": 2})))

        cd = RT_CD + 2 * 0.18
        hand = 1.0 * _rt_panel() * 0.5 * 0.9 * (1 + RT_CR * cd)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 2 层司铎 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["cd"] == pytest.approx(cd, rel=REL_TOL), (
            "对方司铎 CD 面板回显")
        assert theirs["stats"]["spd"] == pytest.approx(RT_SPD * 1.06, rel=REL_TOL), (
            "2pc spd 面板互对（真理侧——星期日侧同通道不重复钉）")


class TestRelic125WarriorGoddess:
    """烈阳惊雷的女武神（罗刹→真理）：2pc spd 6%（面板回显互对）；4pc 治疗
    其他友方 → 【甘霖】spd 6%+全队 crit_dmg 15%（对方 enabled 开关=SPD_P 6%+
    FullTeam CD 15%+BOOST 0.15 outputBuff(CD)——OutputTag.BUFF 无命中承载=
    惰性，dmgBoostMulti 回显钉 1.0 自证）."""

    def test_4pc_rain(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_relic_build("1203", "125", "1305"), "imaginary"))
        eng.state.actors["1305"].current_hp = 0.5 * _eff(eng, "1305")["hp"]
        _cast(eng, "1203", "120302", target="1305")   # 罗刹战技治疗真理（半血场）
        assert "SET_125_RAIN" in eng.state.actors["1203"].modifiers
        log.clear()
        _cast(eng, "1203", "120301")
        ours = _hit_amounts(log, source="1203")
        white = LC_ATK_W
        theirs = run_optimizer(optimizer_driver, _lc55_opt(
            "basic", equipment=_relic("125", 4, {"enabledWarriorGoddessOfSunAndThunder": True})))

        cd = 0.5 + 0.15
        hand = 1.0 * white * 1.28 * 0.5 * 0.9 * (1 + 0.05 * cd)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方甘霖后普攻（CD 15%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.0, rel=REL_TOL), "对方 outputBuff(CD) 惰性（OutputTag.BUFF 无命中承载）"


class TestRelic126Wavestrider:
    """恶海逐波的船长（星期日→真理）：2pc crit_dmg 16%（p2c）；4pc 成为队友
    技能目标叠【助力】（钳 2）→ 终结技消耗 → atk_pct 48% 1回合（当次大招
    不吃——对方 enabled 开关恒开=建模近似）→ 大招后普攻比等；当次大招钉 S16."""

    def test_4pc_help_burst(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_relic_build("1305", "126", "1313"), "imaginary"))
        _sunday_skill(eng, "1305")                 # 星期日战技①（污染件随摘）
        _sunday_skill(eng, "1305")                 # 星期日战技②
        assert eng.state.actors["1305"].modifiers["SET_126_HELP_STACK"].stacks == 2
        log.clear()
        _ult(eng, "1305", "130503", 140.0)
        ours_ult = _hit_amounts(log, source="1305")
        assert "SET_126_ATK_BOOST" in eng.state.actors["1305"].modifiers
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "ult", equipment=_relic("126", 4, {"enabledWavestriderCaptain": True})))

        cd = RT_CD + 0.16                            # 2pc crit_dmg 16%（p2c 双方同挂）
        cz = 1 + RT_CR * cd
        assert ours_ult == pytest.approx([2.4 * _rt_panel() * 0.5 * 0.9 * cz],
                                         rel=REL_TOL), (
            "我方当次大招（助力未 consumed 前挂=当次不吃）vs 手算")
        assert theirs["hits"][0]["damage"] / ours_ult[0] == pytest.approx(
            1.76 / 1.28, rel=REL_TOL), "S16：对方助力 48% 恒开含当次大招"

        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")[1]
        atk = _rt_panel() / 1.28 * 1.76
        hand = 1.0 * atk * 0.5 * 0.9 * cz
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方大招后普攻（助力 48%）vs 手算"
        theirs_basic = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", equipment=_relic("126", 4, {"enabledWavestriderCaptain": True})))
        assert theirs_basic["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)


class TestRelic128SelfEnshrouded:
    """自匿星芒的隐士（杰帕德）：2pc/4pc 护盾量 +10%/+12%（对方 p2x/p4x
    SHIELD 标签 BOOST 同值——杰帕德 ULT_SHIELD 技种对方未注册，盾值我方 vs
    手算单钉）；4pc 后半「持盾友方 crit_dmg 15%」**待收**（逐目标持盾判定
    无通道在案）→ 对方 enabled 开关 FullTeam CD 15%=近似 → 钉 S17."""

    def test_shield_bonus(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1104", set_id="128", pieces=4), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})   # Grit 挂载
        def_panel = (GP_DEF_W) * 1.125
        _fire_ult(eng, "1104", "110403", energy=100.0)
        shields = eng.state.actors["1104"].shields
        assert len(shields) == 1
        assert shields[0].remaining == pytest.approx(
            _gp_shield_hand(def_panel, 0.22), rel=REL_TOL), (
            "我方护盾（2pc 10%+4pc 12% 池——对方 ULT_SHIELD 未注册，单钉 128 先例）")

    def test_shield_cd_divergence(self, optimizer_driver):
        """S17 已收官（2026-09-23）：持盾暴伤 15%——has_shield 逐目标判定（source
        窄化=装备者提供的护盾）+ on_turn_start 懒扫描双钩收编。大招自盾 → 扫描挂
        CD 15% → 普攻双方同池，三方全等."""
        eng, log = _make_logged(_compiled(
            _member_build("1104", set_id="128", pieces=4), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})   # Grit 挂载
        _fire_ult(eng, "1104", "110403", energy=100.0)   # 自盾（source=1104）
        _emit(eng, "on_turn_start", {"actor": "1104"})   # 懒扫描：持盾挂 CD 15%
        assert "REC_128_SHIELD_CD" in eng.state.actors["1104"].modifiers
        def_panel = GP_DEF_W * 1.125
        atk = GP_ATK_W + 0.35 * def_panel
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": GP_ATK_W, "def": GP_DEF_W},
            extra_attacker={"atk": GP_ATK_W, "def": def_panel},
            equipment=_relic("128", 4, {"enabledSelfEnshroudedRecluse": True})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")[0]

        hand = 1.0 * atk * 0.5 * 0.9 * (1 + 0.05 * 0.65) * (1 + GP_ICE)
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方持盾场（CD 0.65）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


class TestRelic124Poet:
    """哀歌覆国的诗人（遐蝶）：2pc 量子 10%（对方 p2c 元素门控同值）；4pc
    spd-8%（双方 stat 通道同值）+ 速度<95/110 暴击 32%/20%（我方有效面板档
    vs 对方 x.c.a 平速档——driver set_threshold_spd 场景槽直钉同读数，
    语义差在案）→ 普攻比等."""

    def test_spd_tier_crit(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1407", set_id="124", pieces=4), "quantum"))
        # 大行迹「倒置的火炬」HP≥50% 速度+40% 与 4pc -8% 同池（1+0.4-0.08=1.32）
        # ——半血场摘掉行迹档：有效速度 95×0.92=87.4 → <95 档（CR 32%）
        eng.state.actors["1407"].current_hp = 0.4 * _eff(eng, "1407")["hp"]
        assert _eff(eng, "1407")["spd"] == pytest.approx(95 * 0.92, rel=REL_TOL)
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        sc = _ca_opt(
            "basic", lc_hp=0.0,
            equipment=_relic("124", 4, {}))
        sc["conditionals"]["memospriteActive"] = False    # 无死龙场（抗区/怒啸两侧同灭）
        sc["conditionals"]["teamDmgBoost"] = False
        sc["set_threshold_spd"] = 95 * 0.92               # 对方 x.c.a 平速档直钉
        theirs = run_optimizer(optimizer_driver, sc)

        cr = CA_CR + 0.32
        cz = 1 + cr * CA_CD
        hand = 0.5 * CA_HP * (1 + CA_Q + 0.1) * 0.5 * 0.9 * cz   # 2pc 量子 10% 同挂
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方速度<95 档（暴击 32%）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["cr"] == pytest.approx(cr, rel=REL_TOL), (
            "对方诗人速度档 CR 面板回显（set_threshold_spd 槽实证）")


class TestRelic129MagicalGirl:
    """闪耀功勋的魔法少女（火花）：2pc crit_dmg 16%（双方 stat 通道同值）；
    4pc 欢愉伤无视防御 10%+1%×N——**我方待收**（scoped 无视防御无通道在案
    ——23053/23057 同案）→ 对方 p4x DEF_PEN·ELATION 同灭列注 → 欢愉技钉 S18."""

    def test_2pc_crit_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1501", set_id="129", pieces=4), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150101")
        ours = _hit_amounts(log, source="1501")
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "basic", equipment=_relic("129", 4, {"valueEverGloriousMagicalGirl": 0})))

        hand = 1.0 * SP_ATK * 0.5 * 0.9 * (1 + SP_CR * (SP_CD_P30 + 0.16))
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 2pc 暴伤 16% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_4pc_elation_def_pen(self, optimizer_driver):
        """S18 已收官（2026-09-23）：欢愉无视防御 10% 基础半——REC_129_ELATION_DEF_PEN
        常驻件（hit_condition elation_damage 路由标识）收编，双方 0.10 穿透，三方全等；
        叠层半（每累计 5 笑点 +1%×N）待收在案（累计语义对齐——fixture notes）."""
        eng, log = _make_logged(_compiled(
            _member_build("1501", set_id="129", pieces=4), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        log.clear()
        _cast(eng, "1501", "150120")
        ours = sum(_hit_amounts(log, source="1501"))
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "elation_skill",
            equipment=_relic("129", 4, {"valueEverGloriousMagicalGirl": 0})))

        cz = 1 + SP_CR * (SP_CD_P30 + 0.16)          # 2pc 暴伤 16% 双方同挂
        def_multi = 100 / (100 * (1 - 0.10) + 100)
        hand = _sp_el(cz) * (def_multi / 0.5)
        assert ours == pytest.approx(hand, rel=REL_TOL), (
            "我方 10% 穿透场（defMulti 100/190）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


class TestRelic130Diviner:
    """应天涉远的卜者（火花）：2pc spd 6%（双方 stat 通道同值）；4pc 速度≥
    120/160 暴击 10%/18%（欢愉载体面版 spd<120 档不可达——tier CR 未拍
    列注；set_threshold_spd 槽由 124 实证）+ 首次欢愉技全队欢愉度 10%
    （对方 enabled 开关恒开=当次即吃；我方 on_action 结算后挂=当次不吃）
    → 第 2 发欢愉技比等；首技钉 S19."""

    def test_first_elation_window(self, optimizer_driver):
        """首技钉 S19（段时序在案——on_action 钩在主段后/追加段前发射：首技
        0.5 主段无欢愉/0.25 追加段吃 10%；对方 enabled 恒开全段）→ 首技复合
        比；第 2 发全段自吃比等."""
        eng, log = _make_logged(_compiled(
            _member_build("1501", set_id="130", pieces=4), "fire"))
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        theirs = run_optimizer(optimizer_driver, _sparxie_opt(
            "elation_skill",
            equipment=_relic("130", 4, {"enabledDivinerOfDistantReach": True})))
        log.clear()
        _cast(eng, "1501", "150120")
        first = sum(_hit_amounts(log, source="1501"))
        cz = 1 + SP_CR * SP_CD_P30
        hand_first = _el(0.5, 30, cz, el=SP_EL) + _el(5.0, 30, cz, el=SP_EL + 0.10)
        assert first == pytest.approx(hand_first, rel=REL_TOL), (
            "我方首技（主段无欢愉/追加段吃 10%）vs 手算")
        assert theirs["hits"][0]["damage"] / first == pytest.approx(
            _sp_el(cz, el=SP_EL + 0.10) / hand_first, rel=REL_TOL), (
            "S19 首技：对方 enabled 恒开全段 vs 我方段时序")

        _cast(eng, "1501", "150120")
        second = sum(_hit_amounts(log, source="1501")[21:])
        hand = _sp_el(cz, el=SP_EL + 0.10)
        assert second == pytest.approx(hand, rel=REL_TOL), "我方第 2 发（欢愉自吃）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert second == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
