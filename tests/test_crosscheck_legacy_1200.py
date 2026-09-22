"""L2 角色级对拍（BACKLOG B22 名册扩拍第七波）：老角色批量扫荡② 1100-1200 号段续波——
停云 1202（雷/同谐，祝福增益链+附加段族）/ 素裳 1206（物理/巡猎，剑势直伤族）/
彦卿 1209（冰/巡猎，智剑连心双暴+冻结族）/ 青雀 1201（量子/智识，麻将叠层
RNG 族）/ 克拉拉 1107（物理/毁灭，敌方攻击驱动反击 FUA 族）/ 卡芙卡 1005
（雷/虚无，B1 加强版触电+引爆族）/ 托帕&账账 1112（火/巡猎，召唤物链族）。
逐段伤害 == hsr-optimizer 角色实现整链伤害（rel_tol 1e-4；双锚=对方+手算，
对不上的按惯例钉结构差数值自证）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character"（CHARACTER_REGISTRY
+7 import +7 登记——1005 按对方 B1 id 直呼（1005b1——我方 fixture=现役加强版
11005xx 轨，1006 单轨先例）；enemy.elemental_weak 场景槽 → context.enemyElementalWeak
（彦卿 Icing/托帕 A4 读口）；召唤物 pet 面板镜像（SelfAndPet——账账继承主面板
含条件 buff，托帕首实例））。我方路径：真模板（tests/fixtures 人工根）→ 编译 →
CombatEngine 钉资源/血量/回合开始 → _cast/_fire_ultimate → bus on_hp_decrease
逐段记录仪（setup 前订阅，L2 先例）。

统一口径（两侧一致，沿用前几波）：星魂钉死 E0、行迹满级（普攻 lv6/技能·终结技·
天赋 lv10）、无光锥无遗器、假人 lvl80 def 1000（防御区 0.5）、匹配弱点（抗性区
1.0）、未击破 0.9、期望暴击 1+cr·cd。**行迹属性节点本波开局即回填**（B-TR②——
R-TR1 同例：character_skill_trees 官方十节点聚合 → trace_stat_effects，原
「社区未给不留空」七 fixture 注记同步改写）。

===========================================================================
停云 1202 buff 状态映射表（对方 content 开关 ↔ 我方模板触发）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
benedictionBuff（false）       BENEDICTION（战技 120202 挂持有者：ATK+min(#2     自祝福链钉 true（战技自指）；
                               ×停云 atk, #4×持有者 atk)——hook 物化烘焙；        面板 846.72 双方同值（对方
                               对方 dynamic conversion ATK→ATK ×0.25 常开       dynamic ×1.25≡我方快照
                               （self-bless min 收敛 #4 支））                  +0.25×677.376 平值）
ultDmgBuff（false）            TINGYUN_ULT_DMG all_dmg 0.5（终结技 120203        未开大钉 false；teammate 链
                               挂持有者 2 回合）                                钉 true 比等（BOOST 0.50）
skillSpdBuff（false）          Nourished Joviality spd_pct 0.2（战技后 1 回合     钉 false 保面板干净（不伤）
ultSpdBuff（false）            E1（E0 门控同灭）                                 E0 钉 false
（无开关）Knell Subdual 普攻+40%  TINGYUN_KNELL_SUBDUAL dmg_basic_dmg_boost 0.4   双方常驻同值（对方 BOOST 0.4
                                                                            damageType BASIC 过滤——只落普攻段）
（无开关）祥音和韵/紫电扶摇附加段  after_being_hit 双钩（B-TY① 已修——category        自祝福普攻：我方 [0.40, 0.60]
                               additional 决策卡 #19 不发受击链；旧版 follow_up     双段 vs 对方折叠 1.00 单发——
                               伪行动自祝福场自供能死循环已灭）                   段数差在案总和三方全等
（无开关）祝福挂队友的附加段       同上双钩（持有=队友——基数 stat_of(队友 atk)）      **对方无落点**（teammate 链不
                                                                            建模附加段进主 C hits）——R-TY2
                                                                            我方段 vs 手算钉（归因差在案：
                                                                            停云记账吃停云增伤 vs 官方持有
                                                                            者携带语义，fixture 待收①）
（无开关）行迹属性节点 atk+28%/雷伤+8%  fixture trace_stat_effects 已回填          B-TR② 收官（def+22.5% 同填不伤）

===========================================================================
素裳 1206 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
ultBuffedState（true）         SUSHANG_ULT_ATK atk_pct 0.3 两回合（终结技           未开大钉 false；开大后钉 true
                               apply_modifiers——先挂后伤本发同吃）               比等（ATK_P 0.30 双方同值）
skillExtraHits 0-3（3）        剑势 33% mechanic_chance——expected <0.5 恒不触发   常态对拍钉 0 比等；默认 3+强化
（R-SS1 主场）                 （克拉拉 A1/青雀 E4 同族双态钉）                   档钉 R-SS1（见下）
skillTriggerStacks 0-10（10）  剑胆烘焙进剑势倍率（expected 不触发=死段）          钉 0 比等（对方 BOOST+0.25
                                                                            damageType ADDITIONAL 过滤）
talentSpdBuffStacks 0-1（1）   天赋 120604（击破查询通道缺——hook 未落地在案）      钉 0 保面板干净（SPD 不伤）
e2DmgReductionBuff（true）     E2（E0 门控同灭）                                 E0 钉 true 无害
（无开关）终结技立即行动         advance_action 100（on_ultimate 钩）              行动条对账（不伤伤害段）
（无开关）行迹属性节点 atk+28%   fixture trace_stat_effects 已回填                B-TR② 收官（HP+18%/DEF+12.5% 同填不伤）

===========================================================================
彦卿 1209 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
ultBuffActive（true）          ULT_CRIT_RATE crit_rate+0.6（apply_modifiers       未开大钉 false；开大钉 true
                               先挂后伤——e2e 时序钉本发可吃）                    比等（CR+0.60 双方同值）
soulsteelBuffActive（true）    SOULSTEEL_SYNC（战技后挂——本发不吃 e2e 时序钉）；   战技本发钉 false 比等；后续
                               天赋 CR+0.20/CD+0.30 enable_if 门控               行动钉 true 比等（CR 0.25/
                                                                            CD 0.80 双方同值）
critSpdBuff（true）            行迹 1209103 暴击提速——**待收**（on_crit 事件缺     钉 true 无害（SPD 不伤）；
                                                                            fixture trace_notes 在案）
e1TargetFrozen（true）/e4      E1/E4（E0 门控同灭）                              E0 钉 true 无害
（无开关）Icing 冰弱点追加 0.30  on_action 全敌 0.30（**上位近似**——弱点查询通道    driver elemental_weak=true 钉
                               缺 fixture 在案）；对方 context.enemyElementalWeak  后双方同出段三方全等（假人
                               门控（driver 本波新槽）                          冰弱点=官方触发域内）
（无开关）天赋追击 0.50          mechanic_chance 0.60——expected ≥0.5 恒触发        普攻后我方 FUA vs 对方 fua
                                                                            行动逐段比等
（无开关）追击冻结 65%+冻结附加伤  FUA 命中挂 FREEZE（expected 恒中）；on_turn_start  **对方无落点**（无冻结 DoT 行动
                               0.50×ATK 冰附加                                   注册）——R-YQ2 我方段 vs 手算钉
（无开关）行迹属性节点 atk+28%/冰伤+14.4%  fixture trace_stat_effects 已回填       B-TR② 收官（HP+10% 同填不伤）

===========================================================================
青雀 1201 buff 状态映射表（RNG 确定化钉法见 R-QQ0）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
basicEnhanced（true）          暗杠闩（_tiles_hand≥4 → on_turn_start 消耗全部      钉资源 _tiles_hand=4+回合开始
                               +ANGANG_ATK atk_pct 0.72）                        入暗杠后施放 120108 比等
                                                                            （ATK_P 0.72 双方同值 1305.36）
skillDmgIncreaseStacks 0-4（4） SKILL_DMG_STACKS 计数+SKILL_DMG_BOOST 烘焙          1 层钉 1 三方全等（B-QQ① 已修——
                               0.28×层 + 听牌 BIDE_TIME 0.1×层（B-QQ① 修后=         听牌每层读社区层定谳）；4 层
                               (0.28+0.10)×层≡对方 0.38×层）                      钉 4 比等（增伤池 1.52+量子
                                                                            0.144 双方同值）
basicEnhancedSpdBuff（false）  抢杠 spd_pct 0.1（强化普攻后 1 回合——不伤）         钉 false 保面板干净
（无开关）E4 Self-Sufficer FUA E4（E0 门控同灭——对方 e<4 空段）                   E0 双方 hits==[] 同钉
（无开关）行迹属性节点 atk+28%/量子+14.4%  fixture trace_stat_effects 已回填       B-TR② 收官（DEF+12.5% 同填不伤）

===========================================================================
克拉拉 1107 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
ultBuff（true）                CLARA_ULT（减伤 25%+嘲讽 2 回合+强化反击装填 2）     强化反击场钉 true（倍率双方
                                                                            1.6+1.6=3.2 同值）
talentEnemyMarked（true）      MARK_OF_COUNTER（受击挂载——战技对被标记者追加         战技场钉 true：我方主段 1.2+
                               1.2；E0 施放后清标记）                            追加段 1.2 vs 对方折叠 2.4
                                                                            单发——段数差在案总和比等
e2UltAtkBuff（true）/e4        E2/E4（E0 门控同灭）                              E0 钉 true 无害
（无开关）天赋反击 1.6           after_being_hit（敌攻克拉拉）→ 1.3×1.6 反击        敌方驱动场钉 R-CL1（A3 通道差
（R-CL1 主场）                 （A3 Revenge +30% 乘算烘焙）；对方 BOOST+0.30       ——见下）
                               damageType FUA 过滤（加算）
（无开关）减伤三件套             dmg_dmg_reduction（受击侧——outgoing 无伤）          不伤不拍
（无开关）行迹属性节点 atk+28%/物理+14.4%  fixture trace_stat_effects 已回填       B-TR② 收官（HP+10% 同填不伤；
                                                                            行迹回填后 A3 乘算 vs 加算差
                                                                            显形=R-CL1 主战场）

===========================================================================
卡芙卡 1005（B1 加强版套件）buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
ehrBasedBuff（true）           Torture 11005101（EHR≥75% 全队 ATK+100%——          行迹 EHR 0.18 钉档双方同灭；
                               on_battle_start stat_of 门控）                    EHR 0.80 钉档（我方开局前注入
                                                                            EHR 件）双方 +100% 同值比等
tickCoefficient 0-20（4）      DoT 频次权重（对方评分模型槽——乘数原值）            钉 1 裸跳值对拍（桑博/卢卡先例）
e1DotDmgReceivedDebuff（true）/e2TeamDotDmg  E1/E2（E0 门控同灭；我方 E1/E2        E0 钉 true 无害
                               同挡因待收——fixture 在案 B27#3）
（无开关）战技/终结技/FUA 引爆   引爆三段（主 0.75/全体 1.0/Thorns 0.8 ×触电单跳     **对方无落点**（tickCoefficient
                               2.9——快照/全 DoT 源近似 fixture 在案）             评分槽吸收）——R-KF1 我方段
                                                                            vs 手算钉（引爆段含期望暴击
                                                                            承载口径在案）
（无开关）触电跳伤 2.9          KAFKA_SHOCK 声明式 dot 通道跳伤——不暴击+      对方 standardDot 无暴击区——
                               施加时刻快照+EHR 命中区截 1.0 中性（2026-09-22    R-KF3 已收官（见下；dotBaseChance 1.0
                               双通道合并）                                     EHR 0.18 调后仍截 1.0 权重中性）
（无开关）天赋 FUA 1.4          队友攻击怪物+充能闩 → 1.4+回能 10+触电 refresh      钉 _fua_charges=1+队友普攻带发
                                                                            vs 对方 fua 行动比等
（无开关）行迹属性节点 atk+28%/EHR+18%  fixture trace_stat_effects 已回填          B-TR② 收官（HP+10% 同填不伤；
                                                                            EHR 0.18<0.75 双方同灭——只进
                                                                            Torture 钉档场）

===========================================================================
托帕&账账 1112 buff 状态映射表（召唤物链——账账挂点 R-CY3 族：挂谁侧按谁面板）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
enemyProofOfDebtDebuff（true） PROOF_OF_DEBT（B-TP① 已修——vulnerability+           追击类段钉 true 比等（易伤 0.5
                               hit_condition follow_up 承伤；旧 follow_up_dmg_     双方同值）；普攻场钉 R-TP3
                               taken 死键已摘除）                                （A6 类型标签差——见下）
numbyEnhancedState（true）     WINDFALL_BONANZA（终结技挂账账：all_dmg 1.5+         常态钉 false；强化场钉 true
                               crit_dmg 0.25）                                  钉 R-TP4（倍率通道差——见下）
e1DebtorStacks 0-2（2）        E1 DEBTOR（E0 门控同灭；follow_up_crit_dmg 同族     E0 钉 2 无害（E1 族死键
                               死键待收在案——E0 无观察差）                        另列待查）
（无开关）A4 金融动荡火弱点+15%   **待收**（宿主函数无 weakness 读取口——fixture      driver elemental_weak 钉 false
                               挡因在案）；对方 context.enemyElementalWeak→        比等；钉 true 钉 R-TP2（×1.15
                               BOOST 0.15 SelfAndPet 双实体                     双方实体同吃——我方 0）
（无开关）账账面板归属           summon 独立烘焙白值（不含行迹/条件 buff——           R-TP1（召唤物继承差：对方
                               fixture 待实测 B19 在案）；对方 SelfAndPet          SelfAndPet 继承火伤 0.224+
                               继承主面板（driver 本波新镜像）                    暴击 0.12 vs 我方独立白值）
（无开关）行迹属性节点 火伤+22.4%/暴击+12%  fixture trace_stat_effects 已回填      B-TR② 收官（HP+10% 同填不伤；
                                                                            托帕白值 620.928 首查=管线实值
                                                                            （query 不返 stats=波①「失配」
                                                                            源头勘明，无失配本体））

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注值，任一侧改动触红）
===========================================================================
R-SS1 素裳剑势触发模型差（我方 mechanic_chance 0.33 expected 恒不触发=0 段——
   官方「击破必触发」查询通道缺 fixture 挡因③在案；对方 slider 期望档默认
   skillExtraHits 3+ultBuffedState → 折叠 2.00 附加段+剑胆 BOOST additional
   +0.25）→ 默认档战技 对方附加段（2.00×ATK×1.25 增伤池）vs 我方无段钉；
   钉 skillExtraHits=0 两侧同无段三方全等
R-YQ2 彦卿冻结附加段对方无落点（我方 on_turn_start 0.50×ATK 冰附加——对方无
   冻结 DoT 行动注册）→ 我方段 vs 手算钉（冻结「无法行动」控制语义引擎
   FREEZE 状态机待接 fixture 在案）
R-QQ0 青雀 RNG 确定化钉法（非差值——口径登记）：我方 _tiles_hand 计数近似吸收
   花色随机（≥4 总牌数入暗杠——花色分桶通道缺 fixture 待收在案）+MODE_EXPECTED
   mechanic_chance 阈值钉（E4 0.24<0.5 恒不授予）；对方 basicEnhanced toggle+
   skillDmgIncreaseStacks slider 期望档——两侧同为「确定化」不同层，逐档钉死对拍
R-QQ1【已收官 2026-09-18（B-QQ①）】青雀听牌叠读差——旧版我方独立 +10% 件
  （4 层=1.22 池）vs 官方/对方每层 +10%（4 层=1.52 池）；社区层定谳=每层
  （Prydwen 满层 152%、HoYoLAB 'on every cast'；CN「额外提高」/EN 'extra 10%'
  措辞歧义在案）→ 修=听牌 BIDE_TIME 换 0.1×层 烘焙（1 层双方 0.38 不变、
  4 层 1.52 三方全等，原差 1.52/1.22 消灭）
R-CL1 克拉拉 A3 Revenge 乘算烘焙 vs 加算池差（我方 1.3×反击倍率乘算——R-PL1
   同族承载；对方 BOOST+0.30 damageType FUA 过滤加算）→ 行迹物理 0.144 非空
   池下 反击（含强化）我方/对方 恰为 1.4872/1.444 = 1.0299（空池等价在案——
   B-TR② 回填后差显形；官方「反击伤害+30%」加算池读法占优，列真病候选待过堂）
R-KF1 卡芙卡引爆段对方无落点（R-LK1 同族——对方 tickCoefficient 评分槽吸收；
   我方主 0.75/全体 1.0/Thorns 0.8×触电单跳近似段——DoT 快照/全源注册表通道缺
   fixture 在案；**2026-09-22 双通道合并实证**：触电迁声明式 dot 通道后引爆段
   不受影响（param 表达式独立结算+has_modifier 型无关挂载点）——声明式 DoT
   可被引爆原语就绪）→ 我方引爆段 vs 手算钉（引爆段含期望暴击承载口径在案——
   直击段非 tick，暴击口径不动）
R-KF3【已收官 2026-09-22（DoT 双通道合并）】卡芙卡触电跳伤——声明式 dot
   通道承载（不暴击+施加时刻快照；EHR 0.18 命中区 min(1, 1.0×1.18) 截 1.0
   权重中性）→ 触电跳三方全等（原差 1/1.025 消灭——R-SV1 族最后一环收官）
R-TY2 停云附加段对方无落点+归因差（teammate 链对方不建模祥音和韵/紫电扶摇
   进主 C hits；我方段停云记账吃停云雷伤 0.08 vs 官方持有者携带语义——fixture
   待收①在案）→ 我方双段 vs 手算钉
R-TP1 托帕账账面板继承差（R-CY3 族——对方 SelfAndPet 继承主面板含行迹火伤
   0.224/暴击 0.12（crit 区 1.085）；我方 summon 独立烘焙白值（crit 区 1.025、
   增伤池 1.0——owner 面板通道未接线 fixture 待实测 B19 在案））→ 账账 FUA
   对方/我方 恰为 (1.085×1.224)/1.025 ≈ 1.29571；引擎接 summon 继承通道
   前不硬绕（大改报回候选）
R-TP2 托帕 A4 金融动荡我方待收（宿主函数无 weakness 读取口——fixture 挡因
   在案；对方 BOOST 0.15 SelfAndPet 双实体）→ elemental_weak=true 场 对方/
   我方 恰为 ×1.15（托帕普攻/账账段同倍）
R-TP3 托帕 A6 透支类型标签差（官方普攻视为追加攻击吃 PoD 易伤——我方事件层
   等值建模不带类型标签（deal_damage 标签通道缺 fixture 待收在案），普攻承伤
   区 1.0；对方 BASIC|FUA 双标签吃 FUA 易伤 0.5）→ PoD 场普攻 对方/我方 恰为 1.5
R-TP4 托帕 Windfall 倍率通道差（官方「倍率提高 150%」=scaling 1.5→3.0——对方
   enhancedStateFuaScalingBoost +1.5 正读；我方 all_dmg 1.5 增伤池加算——fixture
   scaling_notes「独立倍率乘区通道缺再迁移」在案）→ 强化账账段 我方/对方 恰为
   (1.5×(1.224+1.5))/(3.0×1.224) = 1.1127（叠加 R-TP1 面板差后复合比另算——
   各测试逐区钉）

===========================================================================
未完清单（下波起始点）
===========================================================================
已拍 7（本波）：1202 停云 / 1206 素裳 / 1209 彦卿 / 1201 青雀 / 1107 克拉拉 /
1005 卡芙卡（B1）/ 1112 托帕&账账。
真病清单（本波钓出——单列，均 fixture 数据层非引擎层）：
B-TR②【已收官 2026-09-18】老角色 fixture 行迹属性节点漏收延伸波（B-TR① 同族——
   7/7 角色 trace_stat_effects 全空）：停云 atk 0.28+雷 0.08+def 0.225/素裳 atk
   0.28+HP 0.18+def 0.125/彦卿 atk 0.28+冰 0.144+HP 0.10/青雀 atk 0.28+量子
   0.144+def 0.125/克拉拉 atk 0.28+物理 0.144+HP 0.10/卡芙卡 atk 0.28+EHR 0.18
   +HP 0.10/托帕 火 0.224+暴击 0.12+HP 0.10——官方 character_skill_trees 十节点
   逐项加总回填（受影响 e2e 期望逐一手算核销在案）；旧「社区未给」注记同步改写。
B-TY①【已收官 2026-09-18】停云附加双段递归/触发域双病（对拍钓出）：紫电扶摇
   follow_up 伪行动发受击链→自祝福场自供能死循环（bus 重入硬帽 128 实证）；
   祥音和韵 `$event.source != '1202'` 闸兼杀自祝福合法触发。修=双段换 category
   additional（决策卡 #19 附加伤害不发受击链=结构性防递归——B-WT① 同族正主，
   不吃类型限定增伤与官方附加伤害语义同构）。
B-QQ①【已收官 2026-09-18】青雀听牌 Bide Time 叠读差（对拍钓出——官方 CN/EN
   措辞歧义，社区层定谳=每层 +10%）：旧独立 +10% 件 → 0.1×层 烘焙（e2e 1 层
   档期望不变天然兼容；4 层档对拍三方全等实证）。
B-TP①【已收官 2026-09-18】托帕 PoD follow_up_dmg_taken 死键（src 全仓无消费
   端+e2e 期望按无易伤口径同漏——对拍钓出）：换 vulnerability+hit_condition
   follow_up（1218 椒丘/1203 罗刹先例）——战技结算段/账账 FUA 三方全等；
   E1 DEBTOR follow_up_crit_dmg 同族死键列待查（E0 无观察差未动）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.state import Modifier
# 同前几波：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    _POLICY, _cast, _dummy, _hit_amounts, _inject, _make_logged, _stage,
)
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 我方侧引擎件（前几波同模——本文件自足，不跨 test 文件 import 波次件）
# ---------------------------------------------------------------------------


def _fire_ult(eng, owner, aid, *, energy=None, target=None):
    """钉资源开大（前几波同模；ally_single 终结技经 target 钉受加持者）."""
    st = eng.state.actors[owner]
    if energy is not None:
        st.current_energy = energy
    if target is not None:
        tgt = eng.state.actors[target]
        eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
            tgt if tgt in candidates else (candidates[0] if candidates else None))
    ult = next(a for a in eng.actions_by_actor[owner] if a.action_id == aid)
    assert eng._fire_ultimate(st, ult) is True


def _turn_start(eng, actor):
    """回合开始事件（青雀暗杠/卡芙卡触电跳伤/托帕 PoD 补挂族——on_turn_start 钩入口）."""
    eng.bus.emit("on_turn_start", {"actor": actor}, eng.state)


def _solo_build(cid, *, eidolon: int = 0, extra_members: list | None = None):
    member = {"character_template": cid, "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    team = [member] + list(extra_members or [])
    return {"build": {"team": team, "policy": _POLICY}}


def _solo_compiled(cid, *, enemies, extra_members: list | None = None):
    return compile_encounter(_solo_build(cid, extra_members=extra_members), _stage(enemies),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _team_compiled(cids, *, enemies):
    """双模板队友场（停云→素裳增益链——_solo_build 多 character_template 直拼）."""
    team = [{"character_template": c, "level": 80} for c in cids]
    return compile_encounter({"build": {"team": team, "policy": _POLICY}},
                             _stage(enemies), template_roots=TEST_TEMPLATE_ROOTS)


def _ally(aid="ally", *, atk=1500.0, element="physical"):
    """inline 辅手队友（停云祝福/卡芙卡 FUA 驱动用——满机制模板队友的干净替代）."""
    return {"actor_id": aid, "name": "辅手", "inline": True,
            "base_stats": {"atk": atk, "spd": 90, "hp": 3000, "max_energy": 100},
            "actions": [{"action_id": f"{aid}_basic", "name": "普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": element,
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}


def _dummy_atk(aid, element, *, hp=1e9):
    """带攻击行动的假人（克拉拉反击驱动——敌方 actions[0] 必攻；solo 场唯一目标=克拉拉）.
    stage inline 敌无 actions 键（编译键闸——敌行动只走 enemy_template），按
    test_clara_template_e2e 先例编译后直注 actions_by_actor."""
    return _dummy(aid, element, hp=hp)


def _arm_enemy(eng, aid="e1", *, element="physical"):
    """假人注入攻击行动（e2e 先例同模——敌 actions[0] 必攻）."""
    from hsr_nous.sim_schema.action import Action
    eng.actions_by_actor = {**eng.actions_by_actor, aid: [Action(
        action_id="e_hit", name="重击", action_type="basic", target_type="single",
        damage_type=element, scaling=[{"atk": 1.0}], toughness_dmg=10)]}


# ---------------------------------------------------------------------------
# 口径常数（两侧钉死；fixture base_stats 白值 × 行迹聚合（B-TR② 已回填））
# ---------------------------------------------------------------------------

# 停云 1202（雷；行迹 atk 0.28/雷伤 0.08——B-TR② 已回填 fixture）
TY_ATK_W, TY_HP, TY_DEF, TY_SPD = 529.2, 846.72, 396.9, 112
TY_ATK = TY_ATK_W * 1.28                        # 677.376
TY_THUNDER = 0.08
TY_CZ = 1 + 0.05 * 0.5                          # 1.025
TY_BLESS_SELF = 0.25 * TY_ATK                   # 169.344（self-bless min 收敛 #4 支）
TY_ATK_BLESSED = TY_ATK + TY_BLESS_SELF         # 846.72


def _ty(mult: float, *, atk: float = TY_ATK_BLESSED, boost: float = TY_THUNDER) -> float:
    """1202 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池."""
    return mult * atk * 0.5 * 0.9 * TY_CZ * (1 + boost)


# 素裳 1206（物理；行迹 atk 0.28——B-TR② 已回填 fixture；无元素/暴击节点）
SU_ATK_W, SU_HP, SU_DEF, SU_SPD = 564.48, 917.28, 418.95, 107
SU_ATK = SU_ATK_W * 1.28                        # 722.5344
SU_CZ = 1 + 0.05 * 0.5                          # 1.025


def _su(mult: float, *, atk: float = SU_ATK, boost: float = 0.0) -> float:
    """1206 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池."""
    return mult * atk * 0.5 * 0.9 * SU_CZ * (1 + boost)


# 彦卿 1209（冰；行迹 atk 0.28/冰伤 0.144——B-TR② 已回填 fixture）
YQ_ATK_W, YQ_HP, YQ_DEF, YQ_SPD = 679.14, 892.584, 412.335, 109
YQ_ATK = YQ_ATK_W * 1.28                        # 869.2992
YQ_ICE = 0.144
YQ_CZ = 1 + 0.05 * 0.5                          # 1.025（无 Sync）
YQ_CZ_SYNC = 1 + 0.25 * 0.8                     # 1.20（Sync：CR 0.25/CD 0.80）
YQ_CZ_ULT = 1 + 0.85 * 1.3                      # 2.105（大招+Sync：CR 0.85/CD 1.30）


def _yq(mult: float, *, cz: float = YQ_CZ, boost: float = YQ_ICE) -> float:
    """1209 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池（1+冰 0.144）."""
    return mult * YQ_ATK * 0.5 * 0.9 * cz * (1 + boost)


# 青雀 1201（量子；行迹 atk 0.28/量子 0.144——B-TR② 已回填 fixture）
QQ_ATK_W, QQ_HP, QQ_DEF, QQ_SPD = 652.68, 1023.12, 441, 98
QQ_ATK = QQ_ATK_W * 1.28                        # 835.4304
QQ_ATK_ANGANG = QQ_ATK_W * 2.0                  # 1305.36（暗杠 atk_pct 0.72 同池）
QQ_QUANTUM = 0.144
QQ_CZ = 1 + 0.05 * 0.5                          # 1.025


def _qq(mult: float, *, atk: float = QQ_ATK, boost: float = 0.0) -> float:
    """1201 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池（1+量子 0.144+叠层）."""
    return mult * atk * 0.5 * 0.9 * QQ_CZ * (1 + QQ_QUANTUM + boost)


# 克拉拉 1107（物理；行迹 atk 0.28/物理 0.144——B-TR② 已回填 fixture）
CL_ATK_W, CL_HP, CL_DEF, CL_SPD = 737.352, 1241.856, 485.1, 90
CL_ATK = CL_ATK_W * 1.28                        # 943.81056
CL_PHYS = 0.144
CL_CZ = 1 + 0.05 * 0.5                          # 1.025


def _cl(mult: float, *, boost: float = CL_PHYS) -> float:
    """1107 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池（1+物理 0.144）."""
    return mult * CL_ATK * 0.5 * 0.9 * CL_CZ * (1 + boost)


# 卡芙卡 1005 B1（雷；行迹 atk 0.28/EHR 0.18——B-TR② 已回填 fixture；无雷伤节点）
KF_ATK_W, KF_HP, KF_DEF, KF_SPD = 679.14, 1086.624, 485.1, 100
KF_ATK = KF_ATK_W * 1.28                        # 869.2992
KF_EHR = 0.18
KF_CZ = 1 + 0.05 * 0.5                          # 1.025


def _kf(mult: float, *, atk: float = KF_ATK, cz: float = KF_CZ) -> float:
    """1005 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0）."""
    return mult * atk * 0.5 * 0.9 * cz


# 托帕&账账 1112（火；行迹 火伤 0.224/暴击 0.12——B-TR② 已回填 fixture；无攻击节点）
TP_ATK_W, TP_HP, TP_DEF, TP_SPD = 620.928, 931.392, 412.335, 110
TP_ATK = TP_ATK_W                               # 620.928（行迹无 atk 节点）
TP_FIRE = 0.224
TP_CR, TP_CD = 0.05 + 0.12, 0.5                 # 0.17
TP_CZ = 1 + TP_CR * TP_CD                       # 1.085
NB_CZ = 1 + 0.05 * 0.5                          # 1.025（我方账账独立烘焙——无行迹继承）


def _tp(mult: float, *, cz: float = TP_CZ, boost: float = TP_FIRE, vuln: float = 0.0) -> float:
    """1112 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池×承伤区."""
    return mult * TP_ATK * 0.5 * 0.9 * cz * (1 + boost) * (1 + vuln)


# ---------------------------------------------------------------------------
# 对方侧场景模子（映射表见模块 docstring）
# ---------------------------------------------------------------------------

def _opt_tingyun(action: str, *, cond: dict | None = None):
    c = {"benedictionBuff": False, "skillSpdBuff": False, "ultSpdBuff": False,
         "ultDmgBuff": False}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1202", "eidolon": 0,
            "action": action, "element": "thunder", "conditionals": c,
            "base": {"atk": TY_ATK_W, "hp": TY_HP, "def": TY_DEF, "spd": TY_SPD},
            "attacker": {"atk": TY_ATK, "hp": TY_HP, "def": TY_DEF, "spd": TY_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": TY_THUNDER},
            "self_path": "Harmony",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_sushang(action: str, *, cond: dict | None = None, teammates: list | None = None):
    c = {"ultBuffedState": False, "e2DmgReductionBuff": True,
         "skillExtraHits": 0, "skillTriggerStacks": 0, "talentSpdBuffStacks": 0}
    c.update(cond or {})
    sc = {"kind": "character", "character_id": "1206", "eidolon": 0,
          "action": action, "element": "physical", "conditionals": c,
          "base": {"atk": SU_ATK_W, "hp": SU_HP, "def": SU_DEF, "spd": SU_SPD},
          "attacker": {"atk": SU_ATK, "hp": SU_HP, "def": SU_DEF, "spd": SU_SPD,
                       "cr": 0.05, "cd": 0.5},
          "self_path": "Hunt",
          "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                    "count": 1}}
    if teammates is not None:
        sc["teammates"] = teammates
    return sc


def _opt_yanqing(action: str, *, cond: dict | None = None, elemental_weak: bool = False):
    c = {"ultBuffActive": False, "soulsteelBuffActive": False, "critSpdBuff": True,
         "e1TargetFrozen": True, "e4CurrentHp80": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1209", "eidolon": 0,
            "action": action, "element": "ice", "conditionals": c,
            "base": {"atk": YQ_ATK_W, "hp": YQ_HP, "def": YQ_DEF, "spd": YQ_SPD},
            "attacker": {"atk": YQ_ATK, "hp": YQ_HP, "def": YQ_DEF, "spd": YQ_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": YQ_ICE},
            "self_path": "Hunt",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1, "elemental_weak": elemental_weak}}


def _opt_qingque(action: str, *, cond: dict | None = None):
    c = {"basicEnhanced": False, "basicEnhancedSpdBuff": False,
         "skillDmgIncreaseStacks": 0}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1201", "eidolon": 0,
            "action": action, "element": "quantum", "conditionals": c,
            "base": {"atk": QQ_ATK_W, "hp": QQ_HP, "def": QQ_DEF, "spd": QQ_SPD},
            "attacker": {"atk": QQ_ATK, "hp": QQ_HP, "def": QQ_DEF, "spd": QQ_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": QQ_QUANTUM},
            "self_path": "Erudition",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_clara(action: str, *, cond: dict | None = None):
    c = {"ultBuff": False, "talentEnemyMarked": False, "e2UltAtkBuff": True,
         "e4DmgReductionBuff": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1107", "eidolon": 0,
            "action": action, "element": "physical", "conditionals": c,
            "base": {"atk": CL_ATK_W, "hp": CL_HP, "def": CL_DEF, "spd": CL_SPD},
            "attacker": {"atk": CL_ATK, "hp": CL_HP, "def": CL_DEF, "spd": CL_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": CL_PHYS},
            "self_path": "Destruction",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_kafka(action: str, *, cond: dict | None = None, ehr: float = KF_EHR):
    c = {"tickCoefficient": 1, "ehrBasedBuff": True,
         "e1DotDmgReceivedDebuff": True, "e2TeamDotDmg": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1005b1", "eidolon": 0,
            "action": action, "element": "thunder", "conditionals": c,
            "base": {"atk": KF_ATK_W, "hp": KF_HP, "def": KF_DEF, "spd": KF_SPD},
            "attacker": {"atk": KF_ATK, "hp": KF_HP, "def": KF_DEF, "spd": KF_SPD,
                         "cr": 0.05, "cd": 0.5, "effect_hit": ehr},
            "self_path": "Nihility",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_topaz(action: str, *, cond: dict | None = None, elemental_weak: bool = False):
    c = {"enemyProofOfDebtDebuff": False, "numbyEnhancedState": False,
         "e1DebtorStacks": 2}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1112", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": TP_ATK_W, "hp": TP_HP, "def": TP_DEF, "spd": TP_SPD},
            "attacker": {"atk": TP_ATK, "hp": TP_HP, "def": TP_DEF, "spd": TP_SPD,
                         "cr": TP_CR, "cd": 0.5, "element_boost": TP_FIRE},
            "self_path": "Hunt",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1, "elemental_weak": elemental_weak}}


# ===========================================================================
# L2 停云 1202（对方 1200/Tingyun.ts 全实现——BASIC/BREAK 两行动注册）——祝福增益链+附加段族
# ===========================================================================

class TestTingyunDuipai:
    """停云 E0：普攻裸发三方全等（B-TR② 收官）/自祝福链（增益 ATK 面板+附加双段
    总和）三方全等（B-TY① 收官）/teammate 增益链 ATK_P+BOOST 比等+附加段 R-TY2."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 雷（lv6 档）：行迹 atk 0.28/雷 0.08（fixture 回填）+Knell 普攻
        增伤 0.40（双方常驻）——增伤池 1.48 三方全等."""
        eng, log = _make_logged(_solo_compiled("1202", enemies=_dummy("e1", "thunder")))
        log.clear()
        _cast(eng, "1202", "120201")
        ours = _hit_amounts(log, source="1202")
        theirs = run_optimizer(optimizer_driver, _opt_tingyun("basic"))

        hand = _ty(1.0, atk=TY_ATK, boost=TY_THUNDER + 0.4)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", TY_CZ), ("dmgBoostMulti", 1.48), ("abilityMulti", TY_ATK)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_self_bless_chain(self, optimizer_driver):
        """自祝福链（B-TY① 收官）：战技自指 → BENEDICTION ATK+0.25×677.376=169.344
        （对方 dynamic conversion ×1.25——面板 846.72 双方同值）→ 普攻 [1.0 池 1.48,
        祥音和韵 0.40, 紫电扶摇 0.60]（池 1.08）vs 对方 [basic, 折叠 1.00]——段数差
        在案总和三方全等；能量对账."""
        eng, log = _make_logged(_solo_compiled("1202", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1202"]
        log.clear()
        _cast(eng, "1202", "120202", target="1202")
        assert "BENEDICTION" in st.modifiers, "战技自指祝福挂载"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], TY_ATK_BLESSED, rel_tol=1e-9), (
            "祝福 ATK = 677.376 + 0.25×677.376（min(#2×0.5, #4×0.25) 收敛 #4 支）")
        _cast(eng, "1202", "120201")
        ours = _hit_amounts(log, source="1202")
        theirs = run_optimizer(optimizer_driver, _opt_tingyun(
            "basic", cond={"benedictionBuff": True}))

        assert theirs["stats"]["atk"] == pytest.approx(TY_ATK_BLESSED, rel=REL_TOL), (
            "对方 dynamic conversion 面板回显 846.72")
        assert len(ours) == 3, "普攻+祥音和韵+紫电扶摇三段"
        assert ours[0] == pytest.approx(_ty(1.0, boost=TY_THUNDER + 0.4), rel=REL_TOL), (
            "普攻段 vs 手算")
        assert ours[1] == pytest.approx(_ty(0.4), rel=REL_TOL), "祥音和韵 0.40 vs 手算"
        assert ours[2] == pytest.approx(_ty(0.6), rel=REL_TOL), "紫电扶摇 0.60 vs 手算"
        assert len(theirs["hits"]) == 2, "对方 basic+折叠附加双发"
        assert theirs["hits"][1]["atk_scaling"] == pytest.approx(1.0, rel=REL_TOL), (
            "对方折叠 0.40+0.60=1.00")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "普攻段互对"
        assert sum(ours[1:]) == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), (
            "附加双段总和 vs 对方折叠单发互对（段数差在案）")
        assert sum(ours[1:]) == pytest.approx(_ty(1.0), rel=REL_TOL), "附加总和 vs 手算"
        bd = theirs["hits"][1]["breakdown"]
        assert bd["dmgBoostMulti"] == pytest.approx(1.08, rel=REL_TOL), (
            "附加段增伤池 1.08（Knell BASIC 过滤不落附加段）")
        assert math.isclose(st.current_energy, 50.0), "战技 30+普攻 20（亨通回合开始未发）"

    def test_teammate_bless_chain(self, optimizer_driver):
        """teammate 增益链（buff 归属）：停云祝福+终结技挂素裳 → 素裳 ATK 722.5344+
        min(0.5×677.376, 0.25×722.5344)=180.6336=903.168（对方 teammateAtkBuffValue
        钉 0.32=180.6336/564.48 白值换算档——ATK_P 槽官方 flat 等值）+BOOST 0.50
        双方比等；停云附加双段（停云记账吃雷伤 0.08）对方无落点——R-TY2 我方段 vs 手算."""
        eng, log = _make_logged(_team_compiled(["1206", "1202"],
                                               enemies=_dummy("e1", "physical")))
        su = eng.state.actors["1206"]
        log.clear()
        _cast(eng, "1202", "120202", target="1206")
        _fire_ult(eng, "1202", "120203", energy=130.0, target="1206")
        _cast(eng, "1206", "120601")
        ours_su = _hit_amounts(log, source="1206")
        ours_ty = _hit_amounts(log, source="1202")
        theirs = run_optimizer(optimizer_driver, _opt_sushang(
            "basic", teammates=[{"character_id": "1202", "path": "Harmony",
                                 "element": "thunder",
                                 # 官方祝福 flat=min(0.5×停云eff, 0.25×素裳eff)=180.6336
                                 # → 对方 ATK_P 槽×白值换算=180.6336/564.48=0.32 钉档
                                 "conditionals": {"teammateAtkBuffValue": 0.32}}]))

        su_atk = SU_ATK + 0.25 * SU_ATK           # 903.168（cap #4 支收敛）
        assert ours_su == pytest.approx([_su(1.0, atk=su_atk, boost=0.5)], rel=REL_TOL), (
            "素裳普攻（祝福+终结技增伤 0.5）vs 手算")
        assert theirs["stats"]["atk"] == pytest.approx(su_atk, rel=REL_TOL), (
            "对方 ATK_P+0.25 面板回显 903.168")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _su(1.0, atk=su_atk, boost=0.5), rel=REL_TOL), "对方 vs 手算"
        assert ours_su[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "主段双方互对")
        assert len(theirs["hits"]) == 1, "对方 teammate 链不建模附加段（R-TY2 无落点）"
        assert len(ours_ty) == 2, "停云附加双段（祥音和韵+紫电扶摇——停云记账吃雷伤 0.08）"
        hand_ty = lambda m: m * su_atk * 0.5 * 0.9 * TY_CZ * (1 + TY_THUNDER) * 0.8
        assert ours_ty[0] == pytest.approx(hand_ty(0.4), rel=REL_TOL), (
            "R-TY2 祥音和韵 vs 手算（雷段打物理弱点假人——抗区 0.8 入账）")
        assert ours_ty[1] == pytest.approx(hand_ty(0.6), rel=REL_TOL), "R-TY2 紫电扶摇 vs 手算"
        assert math.isclose(su.current_energy, 50.0 + 20.0), "充能 50+普攻 20"


# ===========================================================================
# L2 素裳 1206（对方 1200/Sushang.ts 全实现）——剑势直伤族
# ===========================================================================

class TestSushangDuipai:
    """素裳 E0：普攻/战技/终结技三方全等（B-TR② 收官——expected 剑势恒不触发双钉
    skillExtraHits=0）/终结技 ATK 窗/剑势默认档 R-SS1."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 物理（lv6 档）：行迹 atk 0.28（fixture 回填）三方全等."""
        eng, log = _make_logged(_solo_compiled("1206", enemies=_dummy("e1", "physical")))
        log.clear()
        _cast(eng, "1206", "120601")
        ours = _hit_amounts(log, source="1206")
        theirs = run_optimizer(optimizer_driver, _opt_sushang("basic"))

        hand = _su(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", SU_CZ), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_skill_no_stance(self, optimizer_driver):
        """战技 2.1：expected 剑势 0.33<0.5 恒不触发（ fixture 挡因③在案）——
        对方 skillExtraHits=0 双钉无附加段，三方全等."""
        eng, log = _make_logged(_solo_compiled("1206", enemies=_dummy("e1", "physical")))
        log.clear()
        _cast(eng, "1206", "120602")
        ours = _hit_amounts(log, source="1206")
        theirs = run_optimizer(optimizer_driver, _opt_sushang("skill"))

        assert ours == pytest.approx([_su(2.1)], rel=REL_TOL), "我方战技单段 vs 手算"
        assert len(theirs["hits"]) == 1, "对方钉 0 层无附加段"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(2.1, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_ult_atk_window(self, optimizer_driver):
        """终结技 3.2 + ATK_P 0.30（先挂后伤本发同吃）：开大后普攻/战技窗内比等."""
        eng, log = _make_logged(_solo_compiled("1206", enemies=_dummy("e1", "physical")))
        log.clear()
        _fire_ult(eng, "1206", "120603", energy=120.0)
        _cast(eng, "1206", "120601")
        ours = _hit_amounts(log, source="1206")
        cond = {"ultBuffedState": True}
        theirs_ult = run_optimizer(optimizer_driver, _opt_sushang("ult", cond=cond))
        theirs_basic = run_optimizer(optimizer_driver, _opt_sushang("basic", cond=cond))

        su_atk = SU_ATK + 0.3 * SU_ATK_W          # 891.8784（pct 池加算 0.28+0.30×白值，双方同值）
        assert len(ours) == 2, "终结技+普攻（expected 无剑势段）"
        assert ours[0] == pytest.approx(_su(3.2, atk=su_atk), rel=REL_TOL), (
            "终结技本发（ATK buff 先挂后伤）vs 手算")
        assert ours[1] == pytest.approx(_su(1.0, atk=su_atk), rel=REL_TOL), "窗内普攻 vs 手算"
        assert ours[0] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_ult["stats"]["atk"] == pytest.approx(su_atk, rel=REL_TOL), (
            "对方 ATK_P 面板回显")

    def test_skill_stance_r_ss1_divergence(self, optimizer_driver):
        """R-SS1：对方默认档（skillExtraHits 3+ultBuffedState+剑胆 10）折叠剑势附加
        2.00（增伤池 1+0.25 剑胆）——我方 expected 恒不触发无段；对方附加段 vs 手算钉
        （主段 2.1 双方仍比等——增伤池 1.0 主段不吃剑胆 additional 过滤）."""
        eng, log = _make_logged(_solo_compiled("1206", enemies=_dummy("e1", "physical")))
        log.clear()
        _fire_ult(eng, "1206", "120603", energy=120.0)
        _cast(eng, "1206", "120602")
        ours = _hit_amounts(log, source="1206")
        theirs = run_optimizer(optimizer_driver, _opt_sushang(
            "skill", cond={"ultBuffedState": True, "skillExtraHits": 3,
                           "skillTriggerStacks": 10}))

        su_atk = SU_ATK + 0.3 * SU_ATK_W          # 891.8784（pct 池加算 0.28+0.30×白值，双方同值）
        assert len(ours) == 2, "终结技+战技两段（expected 无剑势段）"
        assert ours[0] == pytest.approx(_su(3.2, atk=su_atk), rel=REL_TOL), "终结技 vs 手算"
        assert ours[1] == pytest.approx(_su(2.1, atk=su_atk), rel=REL_TOL), (
            "我方战技单段（剑势恒不触发）vs 手算")
        assert len(theirs["hits"]) == 2, "对方默认档折叠剑势附加段"
        assert theirs["hits"][0]["damage"] == pytest.approx(_su(2.1, atk=su_atk), rel=REL_TOL), (
            "主段双方仍互对（剑胆 additional 过滤不落主段）")
        assert theirs["hits"][1]["atk_scaling"] == pytest.approx(2.0, rel=REL_TOL), (
            "对方剑势折叠 1.0+0.5+0.5=2.00")
        assert theirs["hits"][1]["damage"] == pytest.approx(
            _su(2.0, atk=su_atk, boost=0.25), rel=REL_TOL), (
            "R-SS1 对方剑势段（剑胆 BOOST 0.25 additional 过滤）vs 手算")


# ===========================================================================
# L2 彦卿 1209（对方 1200/Yanqing.ts 全实现）——智剑连心双暴+冻结族
# ===========================================================================

class TestYanqingDuipai:
    """彦卿 E0：普攻/战技/终结技+追击+Icing 逐段三方全等（B-TR② 收官——
    elemental_weak 双钉 Icing 双方同出段）/Sync 门控双暴链/冻结附加段 R-YQ2."""

    def test_basic_fua_icing(self, optimizer_driver):
        """普攻 1.0（无 Sync crit 1.025）+追击 0.5+Icing 0.3（elemental_weak=true
        双方同出段——假人冰弱点=官方触发域内）逐段三方全等."""
        eng, log = _make_logged(_solo_compiled("1209", enemies=_dummy("e1", "ice")))
        log.clear()
        _cast(eng, "1209", "120901")
        ours = _hit_amounts(log, source="1209")
        theirs_basic = run_optimizer(optimizer_driver, _opt_yanqing(
            "basic", elemental_weak=True))
        theirs_fua = run_optimizer(optimizer_driver, _opt_yanqing(
            "fua", elemental_weak=True))

        assert len(ours) == 3, "普攻+追击+Icing 三段（expected 追击 0.60 恒触发）"
        assert ours[0] == pytest.approx(_yq(1.0), rel=REL_TOL), "普攻 vs 手算"
        assert ours[1] == pytest.approx(_yq(0.5), rel=REL_TOL), "追击 vs 手算"
        assert ours[2] == pytest.approx(_yq(0.3), rel=REL_TOL), "Icing vs 手算"
        assert [h["atk_scaling"] for h in theirs_basic["hits"]] == pytest.approx(
            [1.0, 0.3], rel=REL_TOL), "对方 basic+Icing 双发"
        assert ours[0] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_fua["hits"][0]["damage"], rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs_basic["hits"][1]["damage"], rel=REL_TOL)
        assert theirs_fua["hits"][1]["damage"] == pytest.approx(ours[2], rel=REL_TOL), (
            "对方 fua 内 Icing 同值互证")
        bd = theirs_basic["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("critMulti", YQ_CZ), ("dmgBoostMulti", 1.144)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_skill_sync_chain(self, optimizer_driver):
        """战技 2.2（本发不吃 Sync——e2e 时序钉）+追击/Icing 按挂后 crit 1.2：
        对方 soulsteelBuffActive 分档钉（false 主段/true 后续段）逐段比等."""
        eng, log = _make_logged(_solo_compiled("1209", enemies=_dummy("e1", "ice")))
        log.clear()
        _cast(eng, "1209", "120902")
        ours = _hit_amounts(log, source="1209")
        theirs_skill = run_optimizer(optimizer_driver, _opt_yanqing(
            "skill", elemental_weak=True))
        theirs_fua = run_optimizer(optimizer_driver, _opt_yanqing(
            "fua", cond={"soulsteelBuffActive": True}, elemental_weak=True))

        assert len(ours) == 3, "战技+追击+Icing 三段"
        assert ours[0] == pytest.approx(_yq(2.2), rel=REL_TOL), (
            "战技本发（Sync 后挂不吃——crit 1.025）vs 手算")
        assert ours[1] == pytest.approx(_yq(0.5, cz=YQ_CZ_SYNC), rel=REL_TOL), (
            "追击（Sync 挂后 crit 1.2）vs 手算")
        assert ours[2] == pytest.approx(_yq(0.3, cz=YQ_CZ_SYNC), rel=REL_TOL), (
            "Icing（crit 1.2）vs 手算")
        assert ours[0] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_fua["hits"][0]["damage"], rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs_fua["hits"][1]["damage"], rel=REL_TOL)
        st = theirs_fua["stats"]
        assert st["cr"] == pytest.approx(0.25, rel=REL_TOL), "对方 Sync 面板 CR 0.25 回显"
        assert st["cd"] == pytest.approx(0.8, rel=REL_TOL), "对方 Sync 面板 CD 0.80 回显"

    def test_ult_crit_chain(self, optimizer_driver):
        """终结技 3.5（Sync 在场）：CR 0.85/CD 1.30 crit 区 2.105 双方同值——
        ULT_CRIT_RATE 先挂后伤+Sync 门控 ULT_CRIT_DMG（e2e 时序钉本发可吃）；
        追击/Icing 同区逐段比等."""
        eng, log = _make_logged(_solo_compiled("1209", enemies=_dummy("e1", "ice")))
        log.clear()
        _cast(eng, "1209", "120902")          # Sync 后挂
        _fire_ult(eng, "1209", "120903", energy=140.0)
        ours = _hit_amounts(log, source="1209")
        cond = {"ultBuffActive": True, "soulsteelBuffActive": True}
        theirs_ult = run_optimizer(optimizer_driver, _opt_yanqing(
            "ult", cond=cond, elemental_weak=True))
        theirs_fua = run_optimizer(optimizer_driver, _opt_yanqing(
            "fua", cond=cond, elemental_weak=True))

        assert len(ours) == 6, "战技 3 段+终结技/追击/Icing 3 段"
        ult_segs = ours[3:]
        assert ult_segs[0] == pytest.approx(_yq(3.5, cz=YQ_CZ_ULT), rel=REL_TOL), (
            "终结技（crit 2.105）vs 手算")
        assert ult_segs[1] == pytest.approx(_yq(0.5, cz=YQ_CZ_ULT), rel=REL_TOL), "追击 vs 手算"
        assert ult_segs[2] == pytest.approx(_yq(0.3, cz=YQ_CZ_ULT), rel=REL_TOL), "Icing vs 手算"
        assert ult_segs[0] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL)
        assert ult_segs[1] == pytest.approx(theirs_fua["hits"][0]["damage"], rel=REL_TOL)
        assert ult_segs[2] == pytest.approx(theirs_ult["hits"][1]["damage"], rel=REL_TOL)
        st = theirs_ult["stats"]
        assert st["cr"] == pytest.approx(0.85, rel=REL_TOL), "对方 CR 0.85 回显"
        assert st["cd"] == pytest.approx(1.3, rel=REL_TOL), "对方 CD 1.30 回显"

    def test_freeze_tick_r_yq2(self, optimizer_driver):
        """R-YQ2：冻结附加伤 0.50×ATK（追击 0.65 恒中挂 FREEZE → 敌方回合开始冰
        附加，含期望暴击承载=官方附加伤害可暴击口径）——对方无冻结 DoT 行动注册
        无落点，我方段 vs 手算钉（本发 crit 区读挂后 2.105）."""
        eng, log = _make_logged(_solo_compiled("1209", enemies=_dummy("e1", "ice")))
        _cast(eng, "1209", "120902")
        _fire_ult(eng, "1209", "120903", energy=140.0)
        assert "FREEZE" in eng.state.actors["e1"].modifiers, "追击冻结挂载（expected 恒中）"
        log.clear()
        _turn_start(eng, "e1")
        ours = _hit_amounts(log, source="1209")

        assert ours == pytest.approx([_yq(0.5, cz=YQ_CZ_ULT)], rel=REL_TOL), (
            "冻结附加伤 vs 手算（crit 区读彦卿挂后面板 2.105；对方无落点在案）")


# ===========================================================================
# L2 青雀 1201（对方 1200/Qingque.ts 全实现）——麻将叠层 RNG 族
# ===========================================================================

def _angang(eng):
    """RNG 确定化钉法（R-QQ0）：钉资源 _tiles_hand=4 + 回合开始——花色随机被计数
    近似吸收（fixture 待收在案），抽牌钩（声明序前）满 4 截断 → 暗杠判定消耗全部
    +ANGANG_ATK 0.72；对方侧等价物=basicEnhanced toggle（期望/toggle 模型）."""
    st = eng.state.actors["1201"]
    st.resources["_tiles_hand"] = 4.0
    _turn_start(eng, "1201")
    assert st.resources["_is_angang"] == 1.0, "暗杠入闩（4 张判满消耗）"
    assert "ANGANG_ATK" in st.modifiers


class TestQingqueDuipai:
    """青雀 E0：普攻/暗杠强化普攻（R-QQ0 钉法）/战技叠层 1 档三方全等+4 档比等
    （B-QQ① 收官）/终结技/E4 空段同钉."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 量子（无暗杠——对方 basicEnhanced=false 双钉）三方全等."""
        eng, log = _make_logged(_solo_compiled("1201", enemies=_dummy("e1", "quantum")))
        log.clear()
        _cast(eng, "1201", "120101")
        ours = _hit_amounts(log, source="1201")
        theirs = run_optimizer(optimizer_driver, _opt_qingque("basic"))

        hand = _qq(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("critMulti", QQ_CZ), ("dmgBoostMulti", 1.144)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_enhanced_basic_angang(self, optimizer_driver):
        """暗杠强化普攻 2.4（lv6 主段——相邻 1.0 单假人无落点）：ANGANG_ATK 0.72
        双方同值 1305.36（对方 ATK_P+0.72×白值）——R-QQ0 钉法三方全等；解闸对账."""
        eng, log = _make_logged(_solo_compiled("1201", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1201"]
        log.clear()
        _angang(eng)
        _cast(eng, "1201", "120108")
        ours = _hit_amounts(log, source="1201")
        theirs = run_optimizer(optimizer_driver, _opt_qingque(
            "basic", cond={"basicEnhanced": True}))

        hand = _qq(2.4, atk=QQ_ATK_ANGANG)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方强化普攻 vs 手算"
        assert theirs["stats"]["atk"] == pytest.approx(QQ_ATK_ANGANG, rel=REL_TOL), (
            "对方 ATK_P 面板回显 1305.36")
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(2.4, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert st.resources["_is_angang"] == 0.0, "施放后解闸"
        assert "ANGANG_ATK" not in st.modifiers, "ATK 件摘除"

    def test_one_skill_stack(self, optimizer_driver):
        """1 战技档（B-QQ① 收官——听牌每层读双方 0.38/层）：增伤池 1.144+0.38 三方
        全等（对方 skillDmgIncreaseStacks=1）；牌战返 SP/抽牌/不结束回合对账."""
        eng, log = _make_logged(_solo_compiled("1201", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1201"]
        log.clear()
        _cast(eng, "1201", "120102")
        assert "SKILL_DMG_BOOST" in st.modifiers and "BIDE_TIME" in st.modifiers
        _angang(eng)
        _cast(eng, "1201", "120108")
        ours = _hit_amounts(log, source="1201")
        theirs = run_optimizer(optimizer_driver, _opt_qingque(
            "basic", cond={"basicEnhanced": True, "skillDmgIncreaseStacks": 1}))

        hand = _qq(2.4, atk=QQ_ATK_ANGANG, boost=0.38)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方强化普攻（0.28+0.10=0.38/层×1）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.144 + 0.38, rel=REL_TOL)
        assert math.isclose(eng.state.skill_points, 3.0), "战技-1+牌战+1=净 0（首发）"
        assert math.isclose(st.resources["_tiles_hand"], 0.0), "暗杠消耗全部牌"

    def test_four_skill_stacks(self, optimizer_driver):
        """4 战技档（B-QQ① 主战场——旧独立 +10% 件 1.22 vs 官方/对方 1.52 差消灭）：
        增伤池 1.144+1.52 三方全等."""
        eng, log = _make_logged(_solo_compiled("1201", enemies=_dummy("e1", "quantum")))
        log.clear()
        for _ in range(4):
            _cast(eng, "1201", "120102")
        _angang(eng)
        _cast(eng, "1201", "120108")
        ours = _hit_amounts(log, source="1201")
        theirs = run_optimizer(optimizer_driver, _opt_qingque(
            "basic", cond={"basicEnhanced": True, "skillDmgIncreaseStacks": 4}))

        hand = _qq(2.4, atk=QQ_ATK_ANGANG, boost=1.52)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方强化普攻（(0.28+0.10)×4=1.52）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方（0.38×4=1.52）vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.144 + 1.52, rel=REL_TOL)
        assert math.isclose(eng.state.skill_points, 0.0), "3+1(牌战)-4=0"

    def test_ult(self, optimizer_driver):
        """终结技 2.0 AoE 三方全等（E0 无 E1 终结技增伤）；抽 4 张对账."""
        eng, log = _make_logged(_solo_compiled("1201", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1201"]
        log.clear()
        _fire_ult(eng, "1201", "120103", energy=140.0)
        ours = _hit_amounts(log, source="1201")
        theirs = run_optimizer(optimizer_driver, _opt_qingque("ult"))

        hand = _qq(2.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方终结技 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert math.isclose(st.resources["_tiles_hand"], 4.0), "终结技抽 4 张（set 语义）"

    def test_e4_fua_empty_both_sides(self, optimizer_driver):
        """E4 Self-Sufficer：E0 门控同灭——对方 e<4 FUA 空段 hits==[] 同钉."""
        theirs = run_optimizer(optimizer_driver, _opt_qingque("fua"))
        assert theirs["hits"] == [], "对方 E0 FUA 空段"


# ===========================================================================
# L2 克拉拉 1107（对方 1100/Clara.ts 全实现）——敌方攻击驱动反击 FUA 族
# ===========================================================================

class TestClaraDuipai:
    """克拉拉 E0：普攻三方全等（B-TR② 收官）/敌方驱动反击链（敌 actions[0] 必攻
    +solo 唯一目标钉克拉拉）/强化反击 R-CL1/战技标记追加段总和比等."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 物理（lv6 档）：行迹 atk 0.28/物理 0.144（fixture 回填）三方全等."""
        eng, log = _make_logged(_solo_compiled("1107", enemies=_dummy("e1", "physical")))
        log.clear()
        _cast(eng, "1107", "110701")
        ours = _hit_amounts(log, source="1107")
        theirs = run_optimizer(optimizer_driver, _opt_clara("basic"))

        hand = _cl(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", CL_CZ), ("dmgBoostMulti", 1.144)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_counter_r_cl1_divergence(self, optimizer_driver):
        """R-CL1：敌方普攻克拉拉 → 天赋反击——我方 1.3×1.6 乘算烘焙（增伤池 1.144）
        vs 对方 1.6+BOOST 0.30 FUA 过滤（增伤池 1.444），差恰为 1.4872/1.444；
        标记挂载+反击回能 5 对账."""
        eng, log = _make_logged(_solo_compiled("1107", enemies=_dummy_atk("e1", "physical")))
        _arm_enemy(eng)
        st = eng.state.actors["1107"]
        log.clear()
        _cast(eng, "e1", "e_hit", target="1107")
        ours = _hit_amounts(log, source="1107")
        theirs = run_optimizer(optimizer_driver, _opt_clara("fua"))

        assert "MARK_OF_COUNTER" in eng.state.actors["e1"].modifiers, "攻击者挂反击标记"
        hand_ours = _cl(1.3 * 1.6)                       # 乘算烘焙（增伤池 1.144）
        hand_theirs = _cl(1.6, boost=CL_PHYS + 0.30)     # 加算池（1.444）
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方反击 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方反击 vs 手算")
        assert ours[0] / theirs["hits"][0]["damage"] == pytest.approx(
            (1.3 * (1 + CL_PHYS)) / (1 + CL_PHYS + 0.30), rel=REL_TOL), (
            "R-CL1 差恰为 1.4872/1.444（A3 乘算 vs 加算——空池等价、非空池在案）")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.444, rel=REL_TOL), "对方增伤池回显 1.444"
        assert math.isclose(st.current_energy, 5.0), "反击回能 5（收编实证）"

    def test_enhanced_counter_r_cl1(self, optimizer_driver):
        """强化反击（终结技在场）：我方 1.3×(1.6+1.6) vs 对方 3.2（ultBuff=true）
        ——R-CL1 同比；装填次数 2→1 对账."""
        eng, log = _make_logged(_solo_compiled("1107", enemies=_dummy_atk("e1", "physical")))
        _arm_enemy(eng)
        st = eng.state.actors["1107"]
        log.clear()
        _fire_ult(eng, "1107", "110703", energy=110.0)
        assert math.isclose(st.resources["_enh_counter_left"], 2.0), "强化反击装填 2"
        _cast(eng, "e1", "e_hit", target="1107")
        ours = _hit_amounts(log, source="1107")
        theirs = run_optimizer(optimizer_driver, _opt_clara(
            "fua", cond={"ultBuff": True}))

        hand_ours = _cl(1.3 * 3.2)
        hand_theirs = _cl(3.2, boost=CL_PHYS + 0.30)
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方强化反击 vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(3.2, rel=REL_TOL), (
            "对方 1.6+1.6=3.2")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL)
        assert ours[0] / theirs["hits"][0]["damage"] == pytest.approx(
            (1.3 * (1 + CL_PHYS)) / (1 + CL_PHYS + 0.30), rel=REL_TOL), "R-CL1 同比"
        assert math.isclose(st.resources["_enh_counter_left"], 1.0), "强化次数耗 1"

    def test_skill_marked_chain(self, optimizer_driver):
        """战技对被标记者：我方主段 1.2+追加段 1.2 vs 对方折叠 2.4 单发——段数差
        在案总和三方全等（增伤池 1.144 双方同值）；E0 施放后清标记."""
        eng, log = _make_logged(_solo_compiled("1107", enemies=_dummy_atk("e1", "physical")))
        _arm_enemy(eng)
        _cast(eng, "e1", "e_hit", target="1107")   # 挂标记+反击（先行段）
        log.clear()
        _cast(eng, "1107", "110702")
        ours = _hit_amounts(log, source="1107")
        theirs = run_optimizer(optimizer_driver, _opt_clara(
            "skill", cond={"talentEnemyMarked": True}))

        assert len(ours) == 2, "战技主段+标记追加段"
        assert ours[0] == pytest.approx(_cl(1.2), rel=REL_TOL), "主段 vs 手算"
        assert ours[1] == pytest.approx(_cl(1.2), rel=REL_TOL), "追加段 vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(2.4, rel=REL_TOL), (
            "对方折叠 1.2×2=2.4")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        assert sum(ours) == pytest.approx(_cl(2.4), rel=REL_TOL), "总和 vs 手算"
        assert "MARK_OF_COUNTER" not in eng.state.actors["e1"].modifiers, "E0 施放后清标记"


# ===========================================================================
# L2 卡芙卡 1005 B1（对方 1000/KafkaB1.ts 全实现——1005b1 直呼）——触电+引爆族
# ===========================================================================

class TestKafkaDuipai:
    """卡芙卡 E0（B1 现役 11005xx 轨）：普攻/战技/终结技主段三方全等（B-TR②
    收官）/引爆三段 R-KF1 对方无落点（声明式 DoT 可引爆实证）/触电跳伤 R-KF3 收官
    （2026-09-22 双通道合并）/天赋 FUA 链/Torture 门控双档."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 雷（lv6 档）：行迹 atk 0.28（fixture 回填；EHR 0.18 不伤直伤）
        三方全等."""
        eng, log = _make_logged(_solo_compiled("1005", enemies=_dummy("e1", "thunder")))
        log.clear()
        _cast(eng, "1005", "1100501")
        ours = _hit_amounts(log, source="1005")
        theirs = run_optimizer(optimizer_driver, _opt_kafka("basic"))

        hand = _kf(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", KF_CZ), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_ult_and_detonation_r_kf1(self, optimizer_driver):
        """终结技 0.8 AoE 主段三方全等+触电挂载；全体引爆 1.0×2.9（R-KF1 对方无
        落点——tickCoefficient 评分槽吸收）我方段 vs 手算（含期望暴击承载口径
        ——DoT 快照/全源注册表通道缺 fixture 在案）."""
        eng, log = _make_logged(_solo_compiled("1005", enemies=_dummy("e1", "thunder")))
        log.clear()
        _fire_ult(eng, "1005", "1100503", energy=120.0)
        ours = _hit_amounts(log, source="1005")
        theirs = run_optimizer(optimizer_driver, _opt_kafka("ult"))

        assert "KAFKA_SHOCK" in eng.state.actors["e1"].modifiers, "终结技触电挂载"
        assert ours[0] == pytest.approx(_kf(0.8), rel=REL_TOL), "终结技主段 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "主段互对"
        assert len(theirs["hits"]) == 1, "对方无引爆段（R-KF1 无落点）"
        assert ours[1] == pytest.approx(_kf(1.0 * 2.9), rel=REL_TOL), (
            "R-KF1 全体引爆 1.0×触电单跳 2.9 vs 手算")

    def test_skill_detonation_r_kf1(self, optimizer_driver):
        """战技 1.6 主段（相邻 0.6 单假人无落点——对方只建主目标单发=建模收敛）
        三方全等；主引爆 0.75×2.9 R-KF1 我方段 vs 手算."""
        eng, log = _make_logged(_solo_compiled("1005", enemies=_dummy("e1", "thunder")))
        _fire_ult(eng, "1005", "1100503", energy=120.0)   # 先挂触电
        log.clear()
        _cast(eng, "1005", "1100502")
        ours = _hit_amounts(log, source="1005")
        theirs = run_optimizer(optimizer_driver, _opt_kafka("skill"))

        assert ours[0] == pytest.approx(_kf(1.6), rel=REL_TOL), "战技主段 vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.6, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "主段互对"
        assert ours[1] == pytest.approx(_kf(0.75 * 2.9), rel=REL_TOL), (
            "R-KF1 主引爆 0.75×触电单跳 vs 手算（相邻引爆单假人无落点不拍）")

    def test_shock_tick_r_kf3_closeout(self, optimizer_driver):
        """R-KF3 收官：触电跳伤 2.9 三方全等——声明式 dot 通道承载（不暴击+
        施加时刻快照；EHR 0.18 命中区 min(1, 1.0×1.18) 截 1.0 权重中性）vs 对方
        standardDot 无暴击区（tickCoefficient 钉 1 裸跳值；dotBaseChance 1.0×
        (1+EHR 0.18) 截 1.0 中性），原差 1/1.025 消灭。引爆族 R-KF1 不受影响
        （param 表达式独立结算——声明式 DoT 可被引爆实证）."""
        eng, log = _make_logged(_solo_compiled("1005", enemies=_dummy("e1", "thunder")))
        _fire_ult(eng, "1005", "1100503", energy=120.0)
        log.clear()
        eng._tick_dots(eng.state.actors["e1"])   # 声明式跳伤走引擎 A 类结算
        ours = [e["amount"] for e in log
                if e.get("reason") == "dot" and e.get("source") == "1005"]
        theirs = run_optimizer(optimizer_driver, _opt_kafka("dot"))

        hand = 2.9 * KF_ATK * 0.5 * 0.9     # 双方同口径（不暴击、权重 1.0）
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方触电跳 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 dot vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "R-KF3 收官：双方互对（原差 1/1.025 消灭）")
        assert theirs["hits"][0]["damage_function"] == "Dot"

    def test_fua_chain(self, optimizer_driver):
        """天赋 FUA 1.4：钉 _fua_charges=1+队友普攻怪物目标带发——回能 10+触电
        refresh+耗 1 充能对账；对方 fua 行动比等."""
        eng, log = _make_logged(_solo_compiled(
            "1005", enemies=_dummy("e1", "thunder"), extra_members=[_ally()]))
        st = eng.state.actors["1005"]
        st.resources["_fua_charges"] = 1.0
        log.clear()
        _cast(eng, "ally", "ally_basic")
        ours = _hit_amounts(log, source="1005")
        theirs = run_optimizer(optimizer_driver, _opt_kafka("fua"))

        assert ours == pytest.approx([_kf(1.4)], rel=REL_TOL), "我方 FUA vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.4, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert "KAFKA_SHOCK" in eng.state.actors["e1"].modifiers, "FUA 触电 refresh"
        assert math.isclose(st.current_energy, 10.0), "FUA 回能 10（过堂补记实证）"
        assert math.isclose(st.resources["_fua_charges"], 0.0), "耗 1 充能"

    def test_torture_threshold_branches(self, optimizer_driver):
        """Torture 门控双档：行迹 EHR 0.18 档双方同灭（基础场普攻比等——test_basic
        已钉）；EHR 0.78 档（我方 setup 后注入 EHR 0.60 件+重发 on_battle_start
        真走门控钩→0.18+0.60；对方钉 0.80）双方 ATK+100% 同值比等."""
        eng, log = _make_logged(_solo_compiled("1005", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1005"]
        assert "TORTURE_ATK" not in st.modifiers, "行迹 EHR 0.18 档门控同灭（0.18<0.75）"
        _inject(eng, "1005", "XC_EHR", {"effect_hit": 0.60})
        eng.bus.emit("on_battle_start", {}, eng.state)   # 重发真走 Torture 门控钩
        assert "TORTURE_ATK" in st.modifiers, "Torture 门控开（0.78≥0.75）"
        eff = eng.pipeline.effective_stats(st)
        kf_atk_torture = KF_ATK_W * (1 + 0.28 + 1.0)           # 1548.4392
        assert math.isclose(eff["atk"], kf_atk_torture, rel_tol=1e-9), (
            "Torture ATK = 白值×(1+0.28+1.0)（pct 池加算）")
        log.clear()
        _cast(eng, "1005", "1100501")
        ours = _hit_amounts(log, source="1005")
        theirs = run_optimizer(optimizer_driver, _opt_kafka("basic", ehr=0.80))

        assert theirs["stats"]["atk"] == pytest.approx(kf_atk_torture, rel=REL_TOL), (
            "对方 +1.00×baseATK 面板回显 1548.4392")
        hand = _kf(1.0, atk=kf_atk_torture)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 0.78 档普攻 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


# ===========================================================================
# L2 托帕&账账 1112（对方 1100/Topaz.ts 全实现——双实体召唤物链）——账账挂谁侧按谁面板
# ===========================================================================

class TestTopazDuipai:
    """托帕 E0：战技结算段三方全等（B-TP① 收官——PoD 易伤双通道同吃）/账账 FUA
    R-TP1 召唤物继承差/普攻 R-TP3 类型标签差/Windfall R-TP4/A4 R-TP2."""

    def test_skill_settlement(self, optimizer_driver):
        """战技结算段（B-TP① 收官）：账账火伤 1.5×托帕实时面板（hook 伪行动
        follow_up 吃 PoD 易伤 1.5——与对方 SKILL|FUA 双标签同构）三方全等；
        PoD 挂载+全局唯一对账."""
        eng, log = _make_logged(_solo_compiled("1112", enemies=_dummy("e1", "fire")))
        log.clear()
        _cast(eng, "1112", "111202")
        ours = _hit_amounts(log, source="1112")
        theirs = run_optimizer(optimizer_driver, _opt_topaz(
            "skill", cond={"enemyProofOfDebtDebuff": True}))

        assert "PROOF_OF_DEBT" in eng.state.actors["e1"].modifiers, "PoD 挂载"
        hand = _tp(1.5, vuln=0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方战技结算段 vs 手算"
        assert theirs["hits"][0]["source_entity"] == "Numby", "对方段挂账账侧"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.5, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("vulnMulti", 1.5), ("dmgBoostMulti", 1.224), ("critMulti", TP_CZ),
                     ("abilityMulti", TP_ATK * 1.5)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        es = theirs["entity_stats"]
        assert es[1]["name"] == "Numby" and es[1]["atk"] == pytest.approx(
            TP_ATK, rel=REL_TOL), "账账 SelfAndPet 继承面板回显（driver 镜像实证）"

    def test_numby_fua_r_tp1_divergence(self, optimizer_driver):
        """R-TP1：账账天赋 FUA 1.5——我方 summon 独立烘焙白值（crit 1.025/增伤池
        1.0+PoD 易伤 1.5）vs 对方 SelfAndPet 继承主面板（crit 1.085/火伤 0.224），
        差恰为 (1.085×1.224)/1.025."""
        eng, log = _make_logged(_solo_compiled("1112", enemies=_dummy("e1", "fire")))
        _cast(eng, "1112", "111202")          # PoD 挂 e1
        log.clear()
        _cast(eng, "1112_numby", "111204")
        ours = _hit_amounts(log, source="1112_numby")
        theirs = run_optimizer(optimizer_driver, _opt_topaz(
            "fua", cond={"enemyProofOfDebtDebuff": True}))

        hand_ours = 1.5 * TP_ATK * 0.5 * 0.9 * NB_CZ * 1.0 * 1.5
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), (
            "我方账账 FUA（独立白值+易伤）vs 手算")
        hand_theirs = _tp(1.5, vuln=0.5)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方账账 FUA（继承面板）vs 手算")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            (TP_CZ * (1 + TP_FIRE)) / NB_CZ, rel=REL_TOL), (
            "R-TP1 差恰为 (1.085×1.224)/1.025（召唤物面板继承差——fixture B19 在案）")

    def test_basic_r_tp3_divergence(self, optimizer_driver):
        """R-TP3：A6 透支——官方普攻视为追加攻击吃 PoD 易伤；我方事件层等值建模
        不带类型标签（普攻承伤区 1.0）vs 对方 BASIC|FUA 双标签（承伤区 1.5），
        差恰为 1.5."""
        eng, log = _make_logged(_solo_compiled("1112", enemies=_dummy("e1", "fire")))
        _cast(eng, "1112", "111202")          # PoD 挂 e1
        log.clear()
        _cast(eng, "1112", "111201")
        ours = _hit_amounts(log, source="1112")
        theirs = run_optimizer(optimizer_driver, _opt_topaz(
            "basic", cond={"enemyProofOfDebtDebuff": True}))

        hand_ours = _tp(1.0)                              # 承伤区 1.0（类型标签差）
        hand_theirs = _tp(1.0, vuln=0.5)                  # 双标签吃易伤 1.5
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方普攻 vs 手算")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(1.5, rel=REL_TOL), (
            "R-TP3 差恰为 1.5（A6 类型标签差——deal_damage 标签通道缺 fixture 待收在案）")
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(
            1.5, rel=REL_TOL), "对方承伤区回显 1.5"

    def test_windfall_r_tp4_divergence(self, optimizer_driver):
        """R-TP4：Windfall 强化账账——官方「倍率提高 150%」=scaling 1.5→3.0（对方
        +1.5 正读）vs 我方 all_dmg 1.5 增伤池加算（fixture scaling_notes 在案）；
        叠加 R-TP1 面板差后复合比逐区钉（暴伤 +0.25 双方同区同值——对方 CD 槽、
        我方 crit_dmg 件）."""
        eng, log = _make_logged(_solo_compiled("1112", enemies=_dummy("e1", "fire")))
        _cast(eng, "1112", "111202")          # PoD 挂 e1
        _fire_ult(eng, "1112", "111203", energy=130.0)
        nb = eng.state.actors["1112_numby"]
        assert "WINDFALL_BONANZA" in nb.modifiers, "Windfall 账账侧状态件"
        log.clear()
        _cast(eng, "1112_numby", "111204")
        ours = _hit_amounts(log, source="1112_numby")
        theirs = run_optimizer(optimizer_driver, _opt_topaz(
            "fua", cond={"enemyProofOfDebtDebuff": True, "numbyEnhancedState": True}))

        nb_cz_wf = 1 + 0.05 * 0.75                        # 我方账账 CD 0.75（all_dmg 件）
        tp_cz_wf = 1 + TP_CR * 0.75                       # 对方 CD 0.75（CD 槽）=1.1275
        hand_ours = 1.5 * TP_ATK * 0.5 * 0.9 * nb_cz_wf * (1 + 1.5) * 1.5
        hand_theirs = 3.0 * TP_ATK * 0.5 * 0.9 * tp_cz_wf * (1 + TP_FIRE) * 1.5
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), (
            "我方强化账账（1.5×增伤池 2.5）vs 手算")
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(3.0, rel=REL_TOL), (
            "对方倍率提升正读 1.5+1.5=3.0")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方强化账账 vs 手算")
        expect_ratio = (1.5 * nb_cz_wf * 2.5) / (3.0 * tp_cz_wf * (1 + TP_FIRE))
        assert ours[0] / theirs["hits"][0]["damage"] == pytest.approx(
            expect_ratio, rel=REL_TOL), (
            "R-TP4 复合差（倍率通道 ×R-TP1 面板）逐区钉：1.5×1.0375×2.5 / 3.0×1.1275×1.224")
        es = theirs["entity_stats"]
        assert es[1]["cd"] == pytest.approx(0.75, rel=REL_TOL), "对方账账 CD 槽回显 0.75"

    def test_a4_fire_weak_r_tp2_divergence(self, optimizer_driver):
        """R-TP2：A4 金融动荡——我方待收（宿主函数无 weakness 读取口 fixture 挡因
        在案）vs 对方 elemental_weak=true → BOOST 0.15 SelfAndPet 双实体，普攻场
        差恰为 ×1.15（无 PoD 隔离）."""
        eng, log = _make_logged(_solo_compiled("1112", enemies=_dummy("e1", "fire")))
        log.clear()
        _cast(eng, "1112", "111201")
        ours = _hit_amounts(log, source="1112")
        theirs = run_optimizer(optimizer_driver, _opt_topaz("basic", elemental_weak=True))

        hand_ours = _tp(1.0)
        hand_theirs = _tp(1.0, boost=TP_FIRE + 0.15)
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方（A4 +0.15）vs 手算")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            (1 + TP_FIRE + 0.15) / (1 + TP_FIRE), rel=REL_TOL), (
            "R-TP2 差恰为 1.374/1.224（A4 待收——我方 0 对方 +0.15）")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.374, rel=REL_TOL), "对方增伤池回显 1.374"
