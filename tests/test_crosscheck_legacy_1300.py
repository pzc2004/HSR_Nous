"""L2 角色级对拍（BACKLOG B22 名册扩拍第八波）：老角色批量扫荡③ 1200-1300 号段——
镜流 1212（冰/毁灭，B1 加强版 HP 倍率+朔望转魄族，对方 1212b1 直呼——我方
fixture=现役加强版 1121xxx 轨，1005b1/1004b1 先例；legacy 双轨不拍）。

逐段伤害 == hsr-optimizer 角色实现整链伤害（rel_tol 1e-4；双锚=对方+手算，
对不上的按惯例钉结构差数值自证）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character"（CHARACTER_REGISTRY
+8 import +8 登记——本波 1212b1/1213/1205b1/1208/1203/1217b1/1302/1303）。
我方路径：真模板（tests/fixtures 人工根）→ 编译 → CombatEngine 钉资源/血量/回合
开始 → _cast/_fire_ultimate → bus on_hp_decrease 逐段记录仪（setup 前订阅，L2 先例）。

统一口径（两侧一致，沿用前几波）：星魂钉死 E0、行迹满级（普攻 lv6/技能·终结技·
天赋 lv10）、无光锥无遗器、假人 lvl80 def 1000（防御区 0.5）、匹配弱点（抗性区
1.0）、未击破 0.9、期望暴击 1+cr·cd。**行迹属性节点本波开局即回填**（B-TR③——
B-TR①/② 同例：character_skill_trees 官方十节点聚合 → trace_stat_effects；
B1 双轨角色新旧两版节点值相同已核实，双 fixture 同填）。

===========================================================================
镜流 1212（B1 加强版套件，对方 1212b1）buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
talentEnhancedState（true）    SPECTRAL_TRANS crit_rate+0.5（朔望 2 层进转魄          转魄外钉 false 比等；转魄中钉
                               apply_modifier enable_if 门控）                    true 比等（CR 0.55 双方同值）
moonlightStacks 0-5（5）       MOONLIGHT_BOOST crit_dmg 0.44×层（转魄攻击耗队友        月色 0 层钉 0 比等；1 层钉 1
                               血 → on_hp_decrease 叠层）                         三方全等（CD 0.873+0.44 双方
                                                                                同值）
maxSyzygyDefPen（true）        霜魄 11212103（朔望上限后再获得→下次攻击无视 25%         常态钉 false 比等；钉 true 钉
                               防御）**待收**（def_ignore 键缺 fixture 在案 0.25）； R-JL2（对方 DEF_PEN 0.25 常驻
                               对方 DEF_PEN 0.25 toggle                          化——defMulti 4/7 vs 0.5，
                                                                                差恰为 8/7）
e1Buffs/e2SkillDmgBuff/e4      E1/E2/E4（E0 门控同灭）                            E0 钉 true 无害
（无开关）死境 11212101 终结技+20%  **待收**（ultimate 技能类增伤键缺 fixture 在案     转魄中终结技钉 R-JL1（对方
                                    0.2）；对方 BOOST 0.20 damageType ULT 过滤      BOOST ULT 过滤落终结技段，
（无开关）死境 11212101 效果抵抗+35%  同待收（不伤）                                  差恰为 ×1.2）；转魄外双方同
（无开关）剑首 11212102 回能 15/8   on_action gain_energy（无罅飞光 15/寒川 8）      灭不拍
（无开关）行迹属性节点 暴伤 0.373/   fixture trace_stat_effects 已回填              B-TR③ 收官（spd+9/HP+10% 同填
  速度+9/生命+10%                                                                ——HP 1579.4856/spd 105 面板
                                                                                双方同值）
（无开关）E1 追伤 0.8×Max         E1（E0 门控同灭）                                E0 双方无段

===========================================================================
丹恒•饮月 1213 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
basicEnhanced 0-3（3）         泽芝 121301/瞬华 121308/天矢阴 121310/盘拏耀跃         逐档钉（0/1/2/3 ↔ 四档普攻）
                               121312 四档独立 basic 行动                         主段倍率 1.0/2.6/3.8/5.0 双方
                                                                                同值（相邻段单假人无落点）
skillOutroarStacks 0-4（4）    OUTROAR_CD crit_dmg 0.12×层（天矢阴+2/盘拏耀跃+4     0 层钉 0 比等；2 层钉 2/4 层
                               on_action 后叠——本发不吃 e2e 时序钉）              钉 4 三方全等（CD+0.24/0.48
                                                                                双方同值）
talentRighteousHeartStacks     RH_DMG all_dmg 0.10×层（泽芝+2/瞬华+3/天矢阴+5/      各档钉层三方全等（增伤池
 0-6（6）                      盘拏耀跃+7 clamp 6/终结技+3 on_action 后叠）         1.224+0.1×层 双方同值）
e6ResPenStacks 0-3（3）        E6（E0 门控同灭）                                  E0 钉 3 无害
（无开关）盘龙再临 1213103      **待收**（weakness 查询通道缺 fixture 待收 #2——      driver elemental_weak=true 钉
  虚无弱点暴伤+24%              1209 Icing 同族）；对方 enemyElementalWeak→        R-IL1（对方 CD+0.24 双方假人
                               CD 0.24                                          虚数弱点=官方触发域内——差恰
                                                                                为 crit 区 1.1258/1.085）；
                                                                                钉 false 比等
（无开关）逆鳞抵扣 SP           before_consume waterfall（SP 对账不伤伤害段）        终结技+2 对账
（无开关）星穹奔涌 1213101      on_battle_start gain_energy 15（开局 15 能对账）     不伤不拍
（无开关）行迹属性节点 虚数      fixture trace_stat_effects 已回填                  B-TR③ 收官（暴击 0.12/生命
  0.224/暴击 0.12/生命+10%                                                       +10% 同填——CR 0.17/增伤池
                                                                                1.224 双方同值）

===========================================================================
符玄 1208 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
skillActive（true）            慧明（战技挂 team 辐射：hp flat 0.06×stat_of 符玄      未开战技钉 false 比等；开后钉
                               有效面板+crit_rate 0.12+dmg_dmg_reduction 0.18）；   true 比等（self HP×1.06/CR
                               对方 mutual CR 0.12 FullTeam+dynamic conversion      0.357 双方同值；减伤不伤不拍）
                               HP→HP ×0.06（dynamicConditionals 镜像槽 driver
                               早有）+teammateEffects HP flat
talentActive（true）           天赋减伤并入慧明（承伤侧——outgoing 无伤）              不伤不拍
e6TeamHpLostPercent 0-1.2（1.2） E6（E0 门控同灭）                                 E0 钉 1.2 无害
（无开关）太一璇宫阵下战技+20 能  on_action gain_energy 20（能量对账）               阵下战技回能 50 对账
（无开关）遁甲幽隐终结技治疗      on_ultimate heal 队友 5%×Max+133                   治疗段无伤不拍
（无开关）天赋回血/免控/E2 免死   承伤侧机制                                       不伤不拍
（无开关）行迹属性节点 暴击      fixture trace_stat_effects 已回填                  B-TR③ 收官（生命+18%/效果
  0.187/生命+18%/效果抵抗 0.10                                                    抵抗 0.10 同填——HP 1740.15072
                                                                                /CR 0.237 双方同值）

===========================================================================
罗刹 1203 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
fieldActive（true）            LUOCHA_ZONE 结界（2 层深渊之花展开）——E1 ATK_P         E0 门控同灭钉 true 无害（结界
                               0.20 全队（e≥1 门控）                                回复治疗段无伤不拍）
e6ResReduction（true）         E6（E0 门控同灭）                                  E0 钉 true 无害
（无开关）战技/结界/A2 治疗三段   heal 系（治疗量=ATK 倍率——e2e 已全链对轴）          无伤不拍
（无开关）A3 渡厄 effect_res    trace_stat_effects effect_res 0.7（承伤侧）          不伤不拍
  0.7
（无开关）行迹属性节点 攻击     fixture trace_stat_effects 已回填                  B-TR③ 收官（生命+18%/防御
  +28%/生命+18%/防御+12.5%                                                       +12.5% 同填——ATK 968.64768
                                                                                双方同值）

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注值，任一侧改动触红）
===========================================================================
R-JL1 镜流死境 11212101 终结技增伤我方待收（ultimate 技能类增伤键缺 fixture 在案
   0.2；对方 BOOST 0.20 damageType ULT 过滤——转魄中常驻化）→ 转魄中终结技
   对方/我方 恰为 ×1.2（转魄外 talentEnhancedState=false 双方同灭全等）
R-JL2 镜流霜魄 11212103 无视防御我方待收（def_ignore 键缺 fixture 在案 0.25——
   1015 Archer/1310 流萤同案；对方 maxSyzygyDefPen toggle DEF_PEN 0.25 常驻化）
   → 钉 true 场 对方/我方 恰为 defMulti (4/7)/0.5 = 8/7 ≈ 1.142857
===========================================================================
刃 1205（B1 加强版套件，对方 1205b1）buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
enhancedStateActive（true）    HELLSCAPE all_dmg 0.4（战技 1120502 挂 3 回合）        未开战技钉 false 比等；开后钉
                                                                                true 比等（增伤池 1.4 双方同值）
hpPercentLostTotal 0-0.9（0.9） _hp_tally 累计（耗血/受击/set_hp 差量记账，cap       终结技场钉 0.5（战技+强化普攻
                               0.9×Max）→ 终结技 tally 段 1.2×累计                  +set_hp 差量=0.5×Max 实证）——
                                                                                我方主+tally 双段 vs 对方折叠
                                                                                2.1 单发，段数差在案总和三方
                                                                                全等
e1BasicUltMultiBoost/e2CrBuff  E1/E2/E4（E0 门控同灭）                            E0 钉 true/2 无害
  /e4MaxHpIncreaseStacks 0-2（2）
（无开关）A3 Cyclone 天赋追击   （param(1120504,2)+0.2）乘算并入 deal_damage          R-BL1 双档钉（空池 1.04/
  +20%                        表达式（R-CL1 同族承载）；对方 BOOST 0.20             非空池 2.1/2.08——见下）
                               damageType FUA 过滤加算
（无开关）A3 追加回能 15        gain_energy 15（FUA 钩）                           能量对账
（无开关）Neverending Deaths    incoming_heal 0.25 常驻+受治疗 20% 计入 tally        不伤不拍
（无开关）行迹属性节点 生命     fixture trace_stat_effects 已回填                  B-TR③ 收官（暴击 0.12/效果
  +28%/暴击 0.12/效果抵抗 0.10                                                   抵抗 0.10 同填——HP 1738.5984
                                                                                双方同值）

R-IL1 饮月盘龙再临 1213103 我方待收（weakness 查询通道缺 fixture 待收 #2 在案——
   1209 Icing/1112 A4 同族；对方 enemyElementalWeak→CD 0.24 常驻化）→
   elemental_weak=true 场 对方/我方 恰为 crit 区 1.1258/1.085 ≈ 1.037604
R-BL1 刃 A3 Cyclone 乘算并入 vs 加算池差（我方（1.3+0.2）×Max 乘算并入——R-CL1
   同族承载；对方 BOOST 0.20 damageType FUA 过滤加算）：乘算并入按缩放记账
   1.3→1.50（×1.1538），官方「追加攻击伤害+20%」加算池 1.3×1.2=1.56——
   空池下 对方/我方 恰为 1.56/1.50 = 1.04；HELLSCAPE 增伤 0.4 非空池下
   我方/对方 恰为 (1.5×1.4)/(1.3×1.6) = 2.1/2.08 ≈ 1.009615（比值随池翻转
   在案；官方加算读法占优，列真病候选待过堂——R-CL1 同例）
R-HH1 藿藿终结技 ATK 增益目标域差（官方 EN「all teammates (i.e., excluding this
   unit)」=除自身——我方 on_ultimate 代数排自身；对方 ATK_P 0.40 FullTeam 含
   自身）→ ultBuff=true 场 自身 ATK 面板 对方/我方 恰为 ×1.40（普攻 HP 倍率
   伤害不受影响仍三方全等；对方 context.baseEnergy≥160 一刀切 vs 我方个体
   max_energy 门控同案——均列对方侧疑病存目）

===========================================================================
藿藿 1217（B1 加强版套件，对方 1217b1）buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
ultBuff（true）                TAIL_ATK_BUFF atk_pct 0.40（终结技 on_ultimate 挂      **排自身差 R-HH1**：官方/我方
                               全体**除自身**——官方 EN「excluding this unit」）；   =除自身（self ATK 601.524 不
                               对方 ATK_P 0.40 FullTeam **含自身**                  变）；对方 FullTeam 含自身
                                                                                （×1.40）——面板比恰为 1.40；
                                                                                普攻 HP 倍率伤害不受 ATK 差
                                                                                影响仍三方全等
（无开关）The Cursed One 后半   CURSED_ONE_ATK atk_pct 0.24（友方 max_energy≥160     双 ally 门控对账（100→0.40 单
  ≥160 能量者额外+24%           个体门控——fixture 已收）；对方 context.baseEnergy    件/200→0.64 双件 vs 手算）；
                               ≥160 全场一刀切（base_energy 槽）                  对方一刀切无个体门控落点
skillBuff（true）/e6DmgBuff    E1/E6（E0 门控同灭）                              E0 钉 true 无害
（无开关）战技/天赋治疗三段      heal 系（e2e 已全链对轴）                          无伤不拍
（无开关）Fearful to Act 进战   on_battle_start gain_energy 30+provision 2 回合      开局 30 能对账
  +30 能
（无开关）行迹属性节点 生命     fixture trace_stat_effects 已回填                  B-TR③ 收官（效果抵抗 0.18/
  +28%/效果抵抗 0.18/速度+5                                                      速度+5 同填——HP 1738.5984
                                                                                双方同值）

===========================================================================
银枝 1302 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
ultEnhanced（false）           双阈值终结技（130203 耗 90=1.6 / 130214 耗 180=         逐档钉（false↔130203 / true
                               2.8+弹射 0.95×6）                                  ↔130214）
talentStacks 0-10（10）        APOTHEOSIS_CRIT_RATE stat_exprs 0.025×层（命中钩       逐档钉层三方全等（CR 0.05+
                               按存活敌数+虔诚 on_turn_start+1——本发不吃）          0.025×层 双方同值）
ultEnhancedExtraHits 0-6（6）  130214 弹射 6 段 deal_damage 逐段自结（段序暴击        钉 6：我方 7 段 vs 对方折叠
                               爬坡——弹射 i 吃 主段+i 层；per-hit 读法在案）       8.5 单发静态档——R-AG2 段数
                                                                                差+爬坡差在案；钉 0 主段
                                                                                双方同值
e2UltAtkBuff（true）           E2（E0 门控同灭）                                  E0 钉 true 无害
enemyHp50（true）              勇气 1302103（敌 HP≤50% 增伤 15%——before_take_        满血假人钉 false 双方同灭；
                               damage modify_amount **乘法**改写承载，乘区归属      低血场钉 R-AG1（乘法 1.144
                               待实测 fixture 在案）；对方 BOOST 0.15 加算池       ×1.15=1.3156 vs 加算 1.294）
（无开关）慷慨 1302102 敌入战   actor_enter +2 能量                                能量对账
  +2 能
（无开关）E6 终结技无视防御 30%  **待收**（技域 def 区限定通道缺——1302 头注⑤        E0 双方同灭（对方 e<6 门控）
                               1015/1310/1212/1004 同案 0.3 在案）
（无开关）行迹属性节点 攻击     fixture trace_stat_effects **前置波次已填**           无回填差（攻击 0.28/物理
  0.28/物理 0.144/生命+10%                                                       0.144/生命+10% 双方同值）

R-AG1 银枝勇气 1302103 乘法改写 vs 加算池差（我方 before_take_damage modify_amount
   ×1.15 乘法承载——fixture「增伤乘区归属待实测」在案；对方 BOOST 0.15 加算池）
   → 行迹物理 0.144 非空池下 低血场 我方/对方 恰为 (1.144×1.15)/1.294 = 1.3156/
   1.294 ≈ 1.016691（空池等价在案——1.0×1.15=1+0.15 恒等；官方「增伤」加算
   读法占优，列真病候选待过堂——R-CL1 同族；弹射/秘技段不过 waterfall 不吃
   勇气=引擎缺口 fixture 待收⑦在案，与本差同场时另算）
R-AG2 银枝 130214 弹射折叠+段序暴击爬坡差（我方 主 2.8+弹射 0.95×6 共 7 段——
   弹射 i 吃 主段+i 层 per-hit 顺次读法 fixture 在案待实测；对方折叠 8.5 单发
   静态 talentStacks 档）→ 升格 0 起放场 总和 我方/对方 恰为 8.961875/8.7125
   ≈ 1.028621（段数差在案；主段双方同值三方全等）

===========================================================================
阮•梅 1303 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
skillOvertoneBuff（true）      XWY all_dmg 0.32+击破效率 0.5（战技挂阮梅辐射全队        未开战技钉 false 比等；开后钉
                               3 回合）                                          true 比等（增伤池 1.32 双方同值）
teamBEBuff（true）             1303101 RM_TRACE_BE break_effect 0.2 常驻（B-RM①       钉 true 比等（BE 0.573 双方
                               收编——fixture 原缺大行迹三件，见真病清单）           同值；不进直伤乘区）
ultFieldActive（true）         RM_ZONE res_pen 0.25（终结技挂 2 回合）               未开大钉 false 比等；开大钉
                                                                                true 比等（抗区 1.25 双方同值）
e2AtkBoost/e4BeBuff（false）   E2/E4（E0 门控同灭）                                E0 钉 false
（无开关）1303103 BE 阶梯转换   XWY stat_exprs min(0.36,(BE−1.2)/0.1×0.06)——**官方      BE 0.573<1.2 双方同灭；注入
  增伤（B-RM① 收编）            「战技额外使」门控=挂弦外音同生同灭**；对方 finalize   BE 1.8 档钉 0.36 双方同值
                               无门控常驻+teammateDmgBuff 0.36 静态（R-RM1——        （整数档恒等——floor 通道缺
                               对方侧疑病存目）；floor 阶梯通道缺连续近似在案        连续近似高估非整数档在案）
（无开关）1303102 回合开始回能 5  on_turn_start gain_energy（B-RM① 收编）            能量对账
（无开关）天赋 SPD/击破追加      other_allies spd_pct 0.1 / on_break 冰击破追加         **对方无落点**（teammate 槽
  /残梅绽                     /toughness_recovered 残梅绽                         才见 SPD；击破追加/残梅绽无
                                                                                行动注册）——无伤不拍
（无开关）行迹属性节点 防御     fixture trace_stat_effects 已回填（BE 0.373/          B-TR③ 收官（spd 109=104+5
  +22.5%（BE 0.373/spd+5 已并   spd+5 前置已并 base_stats）                        前置同值）
  base_stats）

R-RM1 阮•梅 1303103 门控差（官方「战技额外使我方全体伤害提高」=挂弦外音同生
   同灭——我方 XWY stat_exprs 承载；对方 finalize 无门控常驻+teammateEffects
   teamDmgBuff 0.36 静态）→ BE 1.8 注入档无战技场 增伤池 对方/我方 恰为
   1.36/1.0（开战技场双方 0.68 同值全等——对方侧疑病存目）

===========================================================================
花火 1306（B1 加强版套件，对方 1306b1）buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
skillBuffs（false）            SPK_CRIT_DMG crit_dmg 0.24×stat_of(花火 cd)+0.45         自指链钉 true 比等（CD
                               +SPK_NOCTURNE_RESPEN res_pen 0.10（战技挂目标）；     0.74+0.6276=1.3676+抗区 1.10
                               对方 CD base 0.45（UNCONVERTIBLE 标记——conversion      双方同值——对方 UNCONVERTIBLE
                               不读）+dynamic conversion 0.24×可转换 CD+RES_PEN      槽与我方 stat_of 条件域不含
                               0.10 SingleTarget                                  条件件口径同构）
cipherBuff（true）             SPK_CIPHER（终结技挂我方全体 3 回合）——谜诡在时易       幻景 3 层+谜诡场钉 true 比等
  talentStacks 0-3（3）         伤率+6%/层；SPK_FIGMENT（SP 消费叠层）→SPK_VULN       （承伤区 1.30 双方同值）
                               vulnerability 层×(0.04+谜诡 0.06) 挂敌方；对方
                               VULNERABILITY 层×(0.04+0.06) FullTeam——同承伤区
teamAtkBuff（true）            SPK_NOCTURNE_ATK atk_pct 0.45（11306103 开战光环        双方常驻同值（ATK×1.45——
                               team 辐射——B1 加强版 vs 旧版 0.15）                 fixture  atk_pct 在案键）
e1SpdBuff/e2DefPen（true）     E1/E2（E0 门控同灭）                                E0 钉 true 无害
（无开关）星历普攻额外回 10 能   on_action gain_energy 10                            普攻合计 30 能对账
（无开关）星历②SP 消费回 1 能   on_skill_point_change gain_energy 1                 战技消费后对账
（无开关）行迹属性节点 生命     fixture trace_stat_effects 已回填                    B-TR③ 收官（暴伤 0.24/效果
  +28%/暴伤 0.24/效果抵抗 0.10                                                    抵抗 0.10 同填——CD 0.74 双方
                                                                                同值）

===========================================================================
流萤 1310（B1 加强版套件，对方 1310b1）buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
enhancedStateActive（true）    完全燃烧 state_config（速度+60/弱点击破效率+0.5/        燃烧外钉 false 比等；燃烧内钉
                               效果抵抗+0.30/减伤 0.40 维持）                       true 比等（spd 169/BE 0.623
                                                                                双方同值）
enhancedStateSpdBuff（true）   同上速度件                                        钉 true 比等（spd 169 面板
                                                                                回显同值）
superBreakDmg（true）          β模组 super_break_modifier 池（BE≥1.5→1.0/≥3.0        未击破场钉 false（双方同灭）；
                               →+0.5——stat_exprs 现场求值燃烧门控）；对方            击破场钉 true 钉 R-FF1（对方
                               SUPER_BREAK_MODIFIER 同档+initialize 翻             击破易伤 0.20 落超击破段——
                               config.enemyWeaknessBroken=true（driver 本波新      我方终结技击破易伤窗口待收
                               镜像——baseUniversal/易伤门控读口）                  fixture 在案，差恰为 ×1.2）
atkToBeConversion（true）      γ模组阶梯转化（ATK>1800 每超 10 点 BE+0.8%）**待收**   ATK 523.908<1800 双方同灭
                               （step/per_step_bonus 未进词表 fixture 在案）；      （对方 dynamic 条件同灭）
                               对方 dynamic conversion 同档
talentDmgReductionBuff（true） 减伤 0.40（承伤侧——outgoing 无伤）                  不伤不拍
e1DefShred/e4ResBuff/e6Buffs   E1/E4/E6（E0 门控同灭）                            E0 钉 true 无害
（无开关）强化战技 BE 转换       **B-FF② 已收官**（deal_damage 补段 0.2×min(BE,3.6)   燃烧内强战场：我方主 2.0+
  主 0.2×BE/邻 0.1×BE cap 3.6  ×ATK——段数差在案：对方折叠 (2.0+0.2×BE) 单发；      BE 转换段 vs 对方折叠 2.1246
                               相邻 0.1×BE 转换待收——主/邻区分通道缺在案）         单发——段数差在案总和三方
                                                                                全等
（无开关）终结技击破易伤 20%    **待收**（击破易伤 scoped 通道缺 fixture 在案）；     击破场超击破段 R-FF1（见
                               对方 VULNERABILITY 0.20 BREAK|SUPER_BREAK 过滤       superBreakDmg 行）
（无开关）行迹属性节点 BE       fixture base_stats（B-FF① 勘正——旧 0.746/0.36/       B-FF① 收官（spd 109/RES
  0.373/RES 0.18/spd+5          114 为双轨节点重复并账整两倍——见真病清单）          0.18 同案）

R-FF1 流萤终结技击破易伤窗口我方待收（hit_condition 命中域不进击破管线 fixture
   在案；对方 VULNERABILITY 0.20 damageType BREAK|SUPER_BREAK 过滤——已击破
   常驻化）→ 已击破场超击破段 对方/我方 恰为 ×1.2（直伤段不吃类型过滤同灭
   全等）

===========================================================================
未完清单（下波起始点）
===========================================================================
已拍 10（本波）：1212 镜流（B1）/ 1213 丹恒•饮月 / 1205 刃（B1）/ 1208 符玄 /
1203 罗刹 / 1217 藿藿（B1）/ 1302 银枝 / 1303 阮•梅 / 1306 花火（B1）/
1310 流萤（B1——legacy 双轨不拍，拍现役）。
下波候选（优先级序）：1314 翡翠 / 1221 云璃 / 1218 椒丘 / 1220 飞霄 /
1222 灵砂 / 1321 大丽花（trace_stat_effects 除 1314 外均空——B-TR④ 候选；
1321 按 fixture 注「平铺已并 base_stats」需先核 BE/spd 单轨口径）；希儿 1102
对方 stub 壳跳过；9999xx 测试假人跳过。
真病清单（本波钓出——单列，均 fixture 数据层非引擎层）：
B-RM①【已收官 2026-09-18】阮•梅 fixture 大行迹三件全缺（对拍钓出——对方
   teamBEBuff/finalize 转换/teammateDmgBuff 三锚证伪「已收录」表象）：1303101
   全队 BE+20%（on_battle_start team 辐射）/1303102 回合开始回能 5
   （on_turn_start gain_energy）/1303103 BE 阶梯转换增伤（官方「战技额外使」
   门控→XWY stat_exprs 承载——floor 阶梯通道缺连续近似，整数档恒等在案）。
   e2e 5 例（期望值 live 计算天然兼容）免重基线绿。
B-FF①【已收官 2026-09-18】流萤 fixture base_stats 行迹节点双轨重复并账（对拍
   钓出——13102xx/113102xx 同节点两轨全并=官方单轨整两倍）：BE 0.746→0.373 /
   效果抵抗 0.36→0.18 / spd 114→109（双 fixture 同修）；e2e 重基线=注入档重选
   （β 阈值用例档值随基线平移，超击破链 BE 抬至 2.0 干净档）+AV 窗 360→430
   （速度 109 时间线重排截断修正），16 例绿。
B-FF②【已收官 2026-09-18】流萤强化战技 1131009 BE 转换系数+相邻段双缺（对拍
   钓出——对方 beScaling 0.2 beCap 3.6 锚 + 官方 params #5/#6/#7 列实证加强版
   新增）：主 0.2×min(BE,3.6)×ATK deal_damage 补段+相邻静态列 #2 入
   scaling_blast；相邻 0.1×BE 转换待收（主/邻区分通道缺——1212 E1/1205 E1
   同族在案）。e2e 裸 _execute_action 路径不经 on_action 不产段（注释在案），
   补段覆盖归本文件对拍。
B-FF③【已收官 2026-09-18】流萤强化技削韧列滞留加强前值（对拍钓出——对方
   B1 toughnessDmg 30/15 锚 + 米游社五项权威「削韧15 / 削韧 30+15*2」双源
   实证）：1131008 10→15、1131009 20→30+toughness_dmg_blast 15 补列；e2e
   超击破链有效削韧 30→45 重基线（16 例绿）。
行迹补收清单（B-TR③，本波回填——官方 character_skill_trees 十节点聚合）：
1212 镜流（双轨同填）：暴伤 0.373/速度+9/生命+10%（e2e 重基线 Z0/Z_TRANS/CD 三
   常量+E1/E4/E6 暴伤断言 4 处，14 例绿）。
1213 丹恒•饮月：虚数 0.224/暴击 0.12/生命+10%（e2e 重基线 Z 常量+终结技/E6 三
   处期望，10 例绿）。
1205 刃：生命+28%/暴击 0.12/效果抵抗 0.10（e2e 重基线 BL_HP/Z/耗血常量+E2/E4
   断言，8 例绿）。
1208 符玄：暴击 0.187/生命+18%/效果抵抗 0.10（e2e 重基线 FX_HP 基数+E6 crit 区，
   9 例绿）。
1203 罗刹：攻击+28%/生命+18%/防御+12.5%（e2e 重基线 LC_ATK 常量+ally 血池
   3000→5000 越限 clamp 修正+E1 pct 池加算期望勘正，8 例绿）。
1217 藿藿：生命+28%/效果抵抗 0.18/速度+5（e2e 重基线 HH_HP 常量，10 例绿）。
1302 银枝：**前置波次已填**（攻击 0.28/物理 0.144/生命+10%——本波复核无需回填，
   e2e 19 例基线绿）。
1303 阮•梅：防御+22.5%（BE 0.373/spd+5 前置已并 base_stats——本波补尾矿，
   e2e 5 例绿）。
1306 花火：生命+28%/暴伤 0.24/效果抵抗 0.10（e2e 重基线梦游鱼/E6 两处暴伤
   基数断言——Skill 基数=自身暴伤联动，13 例绿）。
1310 流萤：B-FF① 双轨重复并账勘正（BE 0.373/RES 0.18/spd+5 官方单轨值——
   双 fixture 同修，e2e 16 例绿）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
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


def _solo_build(cid, *, extra_members: list | None = None):
    team = [{"character_template": cid, "level": 80}] + list(extra_members or [])
    return {"build": {"team": team, "policy": _POLICY}}


def _solo_compiled(cid, *, enemies, extra_members: list | None = None):
    return compile_encounter(_solo_build(cid, extra_members=extra_members), _stage(enemies),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _ally(aid="ally", *, atk=1500.0, element="physical"):
    """inline 辅手队友（镜流耗血月色驱动用——满机制模板队友的干净替代）."""
    return {"actor_id": aid, "name": "辅手", "inline": True,
            "base_stats": {"atk": atk, "spd": 90, "hp": 3000, "max_energy": 100},
            "actions": [{"action_id": f"{aid}_basic", "name": "普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": element,
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}


# ---------------------------------------------------------------------------
# 口径常数（两侧钉死；fixture base_stats 白值 × 行迹聚合（B-TR③ 已回填））
# ---------------------------------------------------------------------------

# 镜流 1212 B1（冰；行迹 暴伤 0.373/速度+9/生命+10%——B-TR③ 已回填 fixture）
JL_HP_W, JL_ATK_W, JL_DEF, JL_SPD_W = 1435.896, 679.14, 485.1, 96
JL_HP = JL_HP_W * 1.1                         # 1579.4856
JL_SPD = JL_SPD_W + 9                         # 105
JL_CR, JL_CD = 0.05, 0.5 + 0.373              # 0.873
JL_CZ = 1 + JL_CR * JL_CD                     # 1.04365
JL_CZ_TRANS = 1 + 0.55 * JL_CD                # 1.48015（转魄 CR 0.55）


def _jl(mult: float, *, hp: float = JL_HP, cz: float = JL_CZ, boost: float = 0.0) -> float:
    """1212 期望伤害：倍率×HP×防御区 0.5×未击破 0.9×期望暴击×增伤池."""
    return mult * hp * 0.5 * 0.9 * cz * (1 + boost)


# ---------------------------------------------------------------------------
# 对方侧场景模子（映射表见模块 docstring）
# ---------------------------------------------------------------------------

def _opt_jingliu(action: str, *, cond: dict | None = None):
    c = {"talentEnhancedState": False, "maxSyzygyDefPen": False, "moonlightStacks": 0,
         "e1Buffs": True, "e2SkillDmgBuff": True, "e4MoonlightCdBuff": True,
         "e6ResPen": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1212b1", "eidolon": 0,
            "action": action, "element": "ice", "conditionals": c,
            "base": {"atk": JL_ATK_W, "hp": JL_HP_W, "def": JL_DEF, "spd": JL_SPD_W},
            "attacker": {"atk": JL_ATK_W, "hp": JL_HP, "def": JL_DEF, "spd": JL_SPD,
                         "cr": JL_CR, "cd": JL_CD},
            "self_path": "Destruction",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _enter_transmigration(eng):
    """两战技进转魄（朔望 1+1 → 满 2 触发额外+1=3 + 提前 100% + SPECTRAL_TRANS CR 0.5）."""
    st = eng.state.actors["1212"]
    _cast(eng, "1212", "1121202")
    _cast(eng, "1212", "1121202")
    assert st.resources["_transmigration"] == 1.0, "两战技进转魄"
    assert st.resources["syzygy"] == 3.0, "2 层进转魄额外+1"


# ===========================================================================
# L2 镜流 1212（对方 1200/JingliuB1.ts 全实现——BASIC/SKILL/ULT/BREAK 四行动注册，
# SKILL 段=无罅飞光/寒川映月同倍率 1.5 共段）——HP 倍率+朔望转魄族
# ===========================================================================

class TestJingliuDuipai:
    """镜流 E0（B1）：普攻/战技/进转魄链/寒川映月/月色叠层三方全等（B-TR③ 收官）/
    终结技死境 R-JL1/霜魄 R-JL2."""

    def test_basic(self, optimizer_driver):
        """普攻 0.5×HP 冰（lv6 档）：行迹暴伤 0.373/HP+10%（fixture 回填）三方全等."""
        eng, log = _make_logged(_solo_compiled("1212", enemies=_dummy("e1", "ice")))
        log.clear()
        _cast(eng, "1212", "1121201")
        ours = _hit_amounts(log, source="1212")
        theirs = run_optimizer(optimizer_driver, _opt_jingliu("basic"))

        hand = _jl(0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", JL_CZ), ("dmgBoostMulti", 1.0),
                     ("abilityMulti", 0.5 * JL_HP)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_skill_and_transmigration_chain(self, optimizer_driver):
        """战技 1.5×HP（lv10）→ 两发进转魄（朔望 3+CR 0.55）→ 寒川映月 1.5×HP
        转魄区：三段逐段三方全等；剑首回能 15/8 对账."""
        eng, log = _make_logged(_solo_compiled("1212", enemies=_dummy("e1", "ice")))
        st = eng.state.actors["1212"]
        log.clear()
        _cast(eng, "1212", "1121202")
        _cast(eng, "1212", "1121202")
        assert st.resources["_transmigration"] == 1.0
        assert st.resources["syzygy"] == 3.0, "2 层进转魄额外+1"
        _cast(eng, "1212", "1121209")
        ours = _hit_amounts(log, source="1212")
        theirs_skill = run_optimizer(optimizer_driver, _opt_jingliu("skill"))
        theirs_trans = run_optimizer(optimizer_driver, _opt_jingliu(
            "skill", cond={"talentEnhancedState": True}))

        assert len(ours) == 3, "两战技+寒川三段"
        assert ours[0] == pytest.approx(_jl(1.5), rel=REL_TOL), "战技①（转魄外）vs 手算"
        assert ours[1] == pytest.approx(_jl(1.5), rel=REL_TOL), (
            "战技②（进转魄于 on_action 后挂——本发仍转魄外区）vs 手算")
        assert ours[2] == pytest.approx(_jl(1.5, cz=JL_CZ_TRANS), rel=REL_TOL), (
            "寒川映月（转魄 CR 0.55，solo 无队友耗血月色 0 层）vs 手算")
        assert ours[0] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs_trans["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_trans["stats"]["cr"] == pytest.approx(0.55, rel=REL_TOL), (
            "对方转魄 CR 0.55 面板回显")
        assert math.isclose(st.current_energy, (20 + 15) * 2 + 30 + 8), (
            "两战技（20+15 剑首）+ 寒川（30+8 剑首）=108")
        assert st.resources["syzygy"] == 2.0, "寒川耗 1 层"

    def test_moonlight_stacks_chain(self, optimizer_driver):
        """月色叠层（辅手在场耗血驱动）：转魄中寒川第①发后月色 1 层 → 第②发吃
        CD 0.873+0.44——对方 moonlightStacks=1 档三方全等（E4 E0 门控同灭）."""
        eng, log = _make_logged(_solo_compiled("1212", enemies=_dummy("e1", "ice"),
                                               extra_members=[_ally()]))
        log.clear()
        _enter_transmigration(eng)
        log.clear()
        _cast(eng, "1212", "1121209")
        _cast(eng, "1212", "1121209")
        ours = _hit_amounts(log, source="1212")
        theirs0 = run_optimizer(optimizer_driver, _opt_jingliu(
            "skill", cond={"talentEnhancedState": True, "moonlightStacks": 0}))
        theirs1 = run_optimizer(optimizer_driver, _opt_jingliu(
            "skill", cond={"talentEnhancedState": True, "moonlightStacks": 1}))

        cz_m1 = 1 + 0.55 * (JL_CD + 0.44)       # 1.72215
        assert ours[0] == pytest.approx(_jl(1.5, cz=JL_CZ_TRANS), rel=REL_TOL), (
            "寒川①（耗血在 on_action 后发——本发月色 0 层）vs 手算")
        assert ours[1] == pytest.approx(_jl(1.5, cz=cz_m1), rel=REL_TOL), (
            "寒川②（月色 1 层 CD+0.44）vs 手算")
        assert ours[0] == pytest.approx(theirs0["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs1["hits"][0]["damage"], rel=REL_TOL)
        assert theirs1["stats"]["cd"] == pytest.approx(JL_CD + 0.44, rel=REL_TOL), (
            "对方月色 1 层 CD 面板回显 1.313")

    def test_ult_outside_transmigration(self, optimizer_driver):
        """终结技 1.8×HP 转魄外：死境 ULT 增伤双方同灭（talentEnhancedState=false
        门控）三方全等；朔望+1/回能 5 对账."""
        eng, log = _make_logged(_solo_compiled("1212", enemies=_dummy("e1", "ice")))
        st = eng.state.actors["1212"]
        log.clear()
        _fire_ult(eng, "1212", "1121203", energy=140.0)
        ours = _hit_amounts(log, source="1212")
        theirs = run_optimizer(optimizer_driver, _opt_jingliu("ult"))

        hand = _jl(1.8)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方终结技 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.0, rel=REL_TOL), "死境转魄外双方同灭"
        assert st.resources["syzygy"] == 1.0, "终结技朔望+1"
        assert math.isclose(st.current_energy, 5.0), "终结技回能 5"

    def test_ult_in_transmigration_r_jl1(self, optimizer_driver):
        """R-JL1：转魄中终结技——我方死境 20% 待收（增伤池 1.0）vs 对方 BOOST 0.20
        ULT 过滤（增伤池 1.2），差恰为 ×1.2；主段倍率/crit 区双方同值."""
        eng, log = _make_logged(_solo_compiled("1212", enemies=_dummy("e1", "ice")))
        log.clear()
        _enter_transmigration(eng)
        log.clear()
        _fire_ult(eng, "1212", "1121203", energy=140.0)
        ours = _hit_amounts(log, source="1212")
        theirs = run_optimizer(optimizer_driver, _opt_jingliu(
            "ult", cond={"talentEnhancedState": True}))

        hand_ours = _jl(1.8, cz=JL_CZ_TRANS)
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), (
            "我方转魄终结技（死境待收——增伤池 1.0）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            hand_ours * 1.2, rel=REL_TOL), "对方（ULT 增伤 0.2 常驻化）vs 手算"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(1.2, rel=REL_TOL), (
            "R-JL1 差恰为 ×1.2（死境 ULT 增伤待收——fixture 在案）")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.2, rel=REL_TOL), "对方增伤池回显 1.2"

    def test_max_syzygy_def_pen_r_jl2(self, optimizer_driver):
        """R-JL2：霜魄朔望上限后无视防御 25%——我方待收（defMulti 0.5）vs 对方
        maxSyzygyDefPen DEF_PEN 0.25 常驻化（defMulti 4/7），差恰为 8/7."""
        eng, log = _make_logged(_solo_compiled("1212", enemies=_dummy("e1", "ice")))
        log.clear()
        _cast(eng, "1212", "1121201")
        ours = _hit_amounts(log, source="1212")
        theirs = run_optimizer(optimizer_driver, _opt_jingliu(
            "basic", cond={"maxSyzygyDefPen": True}))

        assert ours == pytest.approx([_jl(0.5)], rel=REL_TOL), "我方普攻（霜魄待收）vs 手算"
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            4 / 7, rel=REL_TOL), "对方 DEF_PEN 0.25 defMulti 回显"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            8 / 7, rel=REL_TOL), "R-JL2 差恰为 8/7（霜魄 DEF_PEN 待收——fixture 在案）"


# 丹恒•饮月 1213（虚数；行迹 虚数 0.224/暴击 0.12/生命+10%——B-TR③ 已回填 fixture）
IL_ATK_W, IL_HP_W, IL_DEF, IL_SPD = 698.544, 1241.856, 363.825, 102
IL_HP = IL_HP_W * 1.1                         # 1366.0416
IL_CR, IL_CD = 0.05 + 0.12, 0.5               # 0.17
IL_IMG = 0.224
IL_CZ = 1 + IL_CR * IL_CD                     # 1.085


def _il(mult: float, *, cz: float = IL_CZ, boost: float = 0.0) -> float:
    """1213 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池（1+虚数 0.224+叠层）."""
    return mult * IL_ATK_W * 0.5 * 0.9 * cz * (1 + IL_IMG + boost)


def _opt_imbibitor(action: str, *, cond: dict | None = None,
                   elemental_weak: bool = False):
    c = {"basicEnhanced": 0, "skillOutroarStacks": 0, "talentRighteousHeartStacks": 0,
         "e6ResPenStacks": 3}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1213", "eidolon": 0,
            "action": action, "element": "imaginary", "conditionals": c,
            "base": {"atk": IL_ATK_W, "hp": IL_HP_W, "def": IL_DEF, "spd": IL_SPD},
            "attacker": {"atk": IL_ATK_W, "hp": IL_HP, "def": IL_DEF, "spd": IL_SPD,
                         "cr": IL_CR, "cd": IL_CD, "element_boost": IL_IMG},
            "self_path": "Destruction",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1, "elemental_weak": elemental_weak}}


# ===========================================================================
# L2 丹恒•饮月 1213（对方 1200/ImbibitorLunae.ts 全实现——BASIC 四档滑块/ULT/
# BREAK 三行动注册）——强化普攻四档+擎手喝破叠层族
# ===========================================================================

class TestImbibitorDuipai:
    """饮月 E0：普攻四档（0/1/2/3 耗）/擎手喝破叠层逐档三方全等（B-TR③ 收官）/
    终结技叠层窗/盘龙再临 R-IL1."""

    def test_basic(self, optimizer_driver):
        """泽芝 1.0 虚数（lv6 档）：行迹虚数 0.224/暴击 0.12（fixture 回填）三方全等."""
        eng, log = _make_logged(_solo_compiled("1213", enemies=_dummy("e1", "imaginary")))
        log.clear()
        _cast(eng, "1213", "121301")
        ours = _hit_amounts(log, source="1213")
        theirs = run_optimizer(optimizer_driver, _opt_imbibitor("basic"))

        hand = _il(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", IL_CZ), ("dmgBoostMulti", 1.224)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_enhanced1_shunhua(self, optimizer_driver):
        """瞬华 2.6（1 耗）：首发裸三方全等；次发吃擎手 3 层（增伤池 1.524）——
        对方 basicEnhanced=1+talentRighteousHeartStacks=3 双钉比等."""
        eng, log = _make_logged(_solo_compiled("1213", enemies=_dummy("e1", "imaginary")))
        log.clear()
        _cast(eng, "1213", "121308")
        _cast(eng, "1213", "121308")
        ours = _hit_amounts(log, source="1213")
        theirs0 = run_optimizer(optimizer_driver, _opt_imbibitor(
            "basic", cond={"basicEnhanced": 1}))
        theirs3 = run_optimizer(optimizer_driver, _opt_imbibitor(
            "basic", cond={"basicEnhanced": 1, "talentRighteousHeartStacks": 3}))

        assert ours[0] == pytest.approx(_il(2.6), rel=REL_TOL), "瞬华首发（无叠层）vs 手算"
        assert ours[1] == pytest.approx(_il(2.6, boost=0.3), rel=REL_TOL), (
            "瞬华次发（擎手 3 层增伤 0.3）vs 手算")
        assert ours[0] == pytest.approx(theirs0["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs3["hits"][0]["damage"], rel=REL_TOL)

    def test_enhanced2_tianshiyin(self, optimizer_driver):
        """天矢阴 3.8（2 耗）：次发吃擎手 5 层+喝破 2 层（增伤 0.5/CD+0.24）——
        对方 basicEnhanced=2+5/2 双钉比等."""
        eng, log = _make_logged(_solo_compiled("1213", enemies=_dummy("e1", "imaginary")))
        log.clear()
        _cast(eng, "1213", "121310")
        _cast(eng, "1213", "121310")
        ours = _hit_amounts(log, source="1213")
        theirs = run_optimizer(optimizer_driver, _opt_imbibitor(
            "basic", cond={"basicEnhanced": 2, "skillOutroarStacks": 2,
                           "talentRighteousHeartStacks": 5}))

        cz_o2 = 1 + IL_CR * (IL_CD + 0.24)      # 1.1258
        assert ours[0] == pytest.approx(_il(3.8), rel=REL_TOL), "天矢阴首发 vs 手算"
        assert ours[1] == pytest.approx(_il(3.8, cz=cz_o2, boost=0.5), rel=REL_TOL), (
            "天矢阴次发（擎手 5+喝破 2）vs 手算")
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.224 + 0.5, rel=REL_TOL)

    def test_enhanced3_panna(self, optimizer_driver):
        """盘拏耀跃 5.0（3 耗）：次发吃擎手 6 层（7 击 clamp）+喝破 4 层（增伤 0.6/
        CD+0.48）——对方默认档 basicEnhanced=3+6/4 比等；SP 对账."""
        eng, log = _make_logged(_solo_compiled("1213", enemies=_dummy("e1", "imaginary")))
        log.clear()
        _cast(eng, "1213", "121312")
        _cast(eng, "1213", "121312")
        ours = _hit_amounts(log, source="1213")
        theirs = run_optimizer(optimizer_driver, _opt_imbibitor(
            "basic", cond={"basicEnhanced": 3, "skillOutroarStacks": 4,
                           "talentRighteousHeartStacks": 6}))

        cz_o4 = 1 + IL_CR * (IL_CD + 0.48)      # 1.1666
        assert ours[0] == pytest.approx(_il(5.0), rel=REL_TOL), "盘拏耀跃首发 vs 手算"
        assert ours[1] == pytest.approx(_il(5.0, cz=cz_o4, boost=0.6), rel=REL_TOL), (
            "盘拏耀跃次发（擎手 6+喝破 4）vs 手算")
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["cd"] == pytest.approx(0.98, rel=REL_TOL), (
            "对方喝破 4 层 CD 0.98 面板回显")
        assert math.isclose(eng.state.skill_points, 0.0), "5-3-3 → 0 截断（SP 下界钳 0）"

    def test_ult_stacked_window(self, optimizer_driver):
        """终结技 3.0（盘拏耀跃预叠 6/4 窗内）：增伤池 1.824+CD 0.98 双方同值
        三方全等；逆鳞+2/回能 5 对账."""
        eng, log = _make_logged(_solo_compiled("1213", enemies=_dummy("e1", "imaginary")))
        st = eng.state.actors["1213"]
        _cast(eng, "1213", "121312")
        log.clear()
        _fire_ult(eng, "1213", "121303", energy=140.0)
        ours = _hit_amounts(log, source="1213")
        theirs = run_optimizer(optimizer_driver, _opt_imbibitor(
            "ult", cond={"skillOutroarStacks": 4, "talentRighteousHeartStacks": 6}))

        hand = _il(3.0, cz=1 + IL_CR * 0.98, boost=0.6)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方终结技（6/4 窗）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert st.resources["squama"] == 2.0, "终结技逆鳞+2"
        assert math.isclose(st.current_energy, 5.0), "终结技回能 5"

    def test_imaginary_weak_trace_cd_r_il1(self, optimizer_driver):
        """R-IL1：盘龙再临 1213103（虚数弱点暴伤+24%）我方待收（weakness 查询通道缺
        fixture 在案）——对方 enemyElementalWeak→CD+0.24：elemental_weak=true 场
        对方/我方 恰为 crit 区 1.1258/1.085；钉 false 双方同灭全等."""
        eng, log = _make_logged(_solo_compiled("1213", enemies=_dummy("e1", "imaginary")))
        log.clear()
        _cast(eng, "1213", "121301")
        ours = _hit_amounts(log, source="1213")
        theirs = run_optimizer(optimizer_driver, _opt_imbibitor(
            "basic", elemental_weak=True))

        assert ours == pytest.approx([_il(1.0)], rel=REL_TOL), "我方普攻（盘龙再临待收）vs 手算"
        assert theirs["stats"]["cd"] == pytest.approx(0.74, rel=REL_TOL), (
            "对方 CD 0.5+0.24 面板回显")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            (1 + IL_CR * 0.74) / IL_CZ, rel=REL_TOL), (
            "R-IL1 差恰为 crit 区 1.1258/1.085（盘龙再临待收——fixture 在案）")


# 刃 1205 B1（风；行迹 生命+28%/暴击 0.12/效果抵抗 0.10——B-TR③ 已回填 fixture）
BL_HP_W, BL_ATK_W, BL_DEF, BL_SPD = 1358.28, 543.312, 485.1, 97
BL_HP = BL_HP_W * 1.28                        # 1738.5984
BL_CR, BL_CD = 0.05 + 0.12, 0.5               # 0.17
BL_CZ = 1 + BL_CR * BL_CD                     # 1.085
BL_BOOST = 0.4                                # HELLSCAPE all_dmg lv10


def _bl(mult: float, *, hp: float = BL_HP, cz: float = BL_CZ, boost: float = 0.0) -> float:
    """1205 期望伤害：倍率×HP×防御区 0.5×未击破 0.9×期望暴击×增伤池."""
    return mult * hp * 0.5 * 0.9 * cz * (1 + boost)


def _opt_blade(action: str, *, cond: dict | None = None):
    c = {"enhancedStateActive": False, "hpPercentLostTotal": 0.0,
         "e1BasicUltMultiBoost": True, "e2CrBuff": True, "e4MaxHpIncreaseStacks": 2}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1205b1", "eidolon": 0,
            "action": action, "element": "wind", "conditionals": c,
            "base": {"atk": BL_ATK_W, "hp": BL_HP_W, "def": BL_DEF, "spd": BL_SPD},
            "attacker": {"atk": BL_ATK_W, "hp": BL_HP, "def": BL_DEF, "spd": BL_SPD,
                         "cr": BL_CR, "cd": BL_CD},
            "self_path": "Destruction",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 刃 1205（对方 1200/BladeB1.ts 全实现——BASIC/ULT/FUA/BREAK 四行动注册）
# ——耗血循环+HELLSCAPE 换技能族
# ===========================================================================

class TestBladeDuipai:
    """刃 E0（B1）：普攻/HELLSCAPE 强化普攻三方全等（B-TR③ 收官）/天赋追击
    R-BL1 双档（空池 1.04/HELLSCAPE 2.1/2.08）/终结技 tally 链段数差在案总和
    三方全等."""

    def test_basic(self, optimizer_driver):
        """普攻 0.5×HP 风（lv6 档，HELLSCAPE 外）：行迹生命+28%/暴击 0.12（fixture
        回填）三方全等."""
        eng, log = _make_logged(_solo_compiled("1205", enemies=_dummy("e1", "wind")))
        log.clear()
        _cast(eng, "1205", "1120501")
        ours = _hit_amounts(log, source="1205")
        theirs = run_optimizer(optimizer_driver, _opt_blade("basic"))

        hand = _bl(0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", BL_CZ), ("dmgBoostMulti", 1.0),
                     ("abilityMulti", 0.5 * BL_HP)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_hellscape_enhanced_basic(self, optimizer_driver):
        """地狱变（耗 0.3×Max+HELLSCAPE 增伤 0.4）→ 无间剑树 1.3×Max 主段（lv6 档
        ——对方 skill 轨 lv10 同值 1.30）：增伤池 1.4 双方同值三方全等；tally/
        charge/能量对账."""
        eng, log = _make_logged(_solo_compiled("1205", enemies=_dummy("e1", "wind")))
        st = eng.state.actors["1205"]
        log.clear()
        _cast(eng, "1205", "1120502")
        assert "HELLSCAPE" in st.modifiers
        _cast(eng, "1205", "1120508")
        ours = _hit_amounts(log, source="1205")
        theirs = run_optimizer(optimizer_driver, _opt_blade(
            "basic", cond={"enhancedStateActive": True}))

        hand = _bl(1.3, boost=BL_BOOST)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方强化普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.4, rel=REL_TOL), "对方增伤池回显 1.4"
        assert math.isclose(st.resources["_hp_tally"], 0.4 * BL_HP), "耗血累计 0.3+0.1"
        assert math.isclose(st.resources["_talent_charge"], 2.0)
        assert math.isclose(st.current_energy, 30.0), "强化普攻回能 30"

    def test_fua_empty_pool_r_bl1(self, optimizer_driver):
        """R-BL1（HELLSCAPE 外空池）：我方（1.3+0.2）×Max 乘算并入=1.50×Max vs
        对方 1.3×Max×1.2（FUA BOOST 过滤加算）=1.56×Max——差恰为 1.56/1.50=1.04
        （乘算并入按缩放记账=×1.1538，官方「伤害+20%」加算池=×1.2——R-CL1 同族，
        官方加算读法占优列真病候选待过堂）；自疗/回能/清层对账."""
        eng, log = _make_logged(_solo_compiled("1205", enemies=_dummy("e1", "wind")))
        st = eng.state.actors["1205"]
        st.resources["_talent_charge"] = 4.0
        log.clear()
        eng.bus.emit("on_hp_decrease", {
            "amount": 100.0, "source": "e1", "reason": "hit",
            "target": "1205", "damage_type": "wind"}, eng.state)
        ours = _hit_amounts(log, source="1205")
        theirs = run_optimizer(optimizer_driver, _opt_blade("fua"))

        hand_ours = _bl(1.3 + 0.2)                     # 1.50×Max（乘算并入）
        hand_theirs = _bl(1.3, boost=0.2)              # 1.56×Max（加算池）
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方天赋追击 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方 1.3×1.2 vs 手算")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(1.04, rel=REL_TOL), (
            "R-BL1 空池差恰为 1.56/1.50=1.04")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.2, rel=REL_TOL), "对方 FUA BOOST 0.2 回显"
        assert math.isclose(st.resources["_talent_charge"], 0.0), "追击后清层"
        assert math.isclose(st.current_energy, 15.0), "A3 追加回能 15"

    def test_fua_hellscape_r_bl1(self, optimizer_driver):
        """R-BL1：HELLSCAPE 在场天赋追击——我方 1.5×Max×1.4 乘算并入 vs 对方
        1.3×Max×1.6（0.4+0.2 加算池），差恰为 2.1/2.08（空池等价、非空池在案——
        R-CL1 同族，官方加算读法占优列真病候选待过堂）."""
        eng, log = _make_logged(_solo_compiled("1205", enemies=_dummy("e1", "wind")))
        st = eng.state.actors["1205"]
        _cast(eng, "1205", "1120502")               # HELLSCAPE 开
        st.resources["_talent_charge"] = 4.0
        log.clear()
        eng.bus.emit("on_hp_decrease", {
            "amount": 100.0, "source": "e1", "reason": "hit",
            "target": "1205", "damage_type": "wind"}, eng.state)
        ours = _hit_amounts(log, source="1205")
        theirs = run_optimizer(optimizer_driver, _opt_blade(
            "fua", cond={"enhancedStateActive": True}))

        hand_ours = _bl(1.3 + 0.2, boost=BL_BOOST)          # 2.1×Max
        hand_theirs = _bl(1.3, boost=BL_BOOST + 0.2)        # 2.08×Max
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方追击 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方追击 vs 手算")
        assert ours[0] / theirs["hits"][0]["damage"] == pytest.approx(
            2.1 / 2.08, rel=REL_TOL), (
            "R-BL1 非空池差恰为 2.1/2.08（A3 乘算并入 vs 加算池——比值随池翻转在案）")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.6, rel=REL_TOL), "对方增伤池回显 1.6"

    def test_ult_tally_chain(self, optimizer_driver):
        """终结技大辟万死：战技+强化普攻预叠 tally 0.4×Max → HP 设 50% 差量计入
        （+0.1）→ 主 1.5×Max+tally 段 1.2×0.5×Max=0.6×Max vs 对方折叠 2.10 单发
        （hpPercentLostTotal 钉 0.5）——段数差在案总和三方全等；Vita 清半对账."""
        eng, log = _make_logged(_solo_compiled("1205", enemies=_dummy("e1", "wind")))
        st = eng.state.actors["1205"]
        _cast(eng, "1205", "1120502")               # tally 0.3 / hp 0.7
        _cast(eng, "1205", "1120508")               # tally 0.4 / hp 0.6
        log.clear()
        _fire_ult(eng, "1205", "1120503", energy=130.0)
        ours = _hit_amounts(log, source="1205")
        theirs = run_optimizer(optimizer_driver, _opt_blade(
            "ult", cond={"enhancedStateActive": True, "hpPercentLostTotal": 0.5}))

        assert len(ours) == 2, "主段+tally 段（对方折叠单发——段数差在案）"
        assert ours[0] == pytest.approx(_bl(1.5, boost=BL_BOOST), rel=REL_TOL), (
            "主段 1.5×Max vs 手算")
        assert ours[1] == pytest.approx(_bl(1.2 * 0.5, boost=BL_BOOST), rel=REL_TOL), (
            "tally 段 1.2×(0.4+set 差量 0.1)×Max=0.6×Max vs 手算")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "双段总和 vs 对方折叠 2.10 单发互对")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _bl(1.5 + 1.2 * 0.5, boost=BL_BOOST), rel=REL_TOL), "对方 vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(0.0, abs=1e-9)
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(2.1, rel=REL_TOL), (
            "对方折叠 hpScaling 1.5+1.2×0.5=2.10")
        assert math.isclose(st.current_hp, 0.5 * BL_HP, rel_tol=1e-9), "HP 设 50%"
        assert math.isclose(st.resources["_hp_tally"], 0.25 * BL_HP), "Vita 清半 0.5→0.25"
        assert math.isclose(st.current_energy, 5.0), "终结技回能 5"


# 符玄 1208（量子；行迹 暴击 0.187/生命+18%/效果抵抗 0.10——B-TR③ 已回填 fixture）
FX_HP_W, FX_ATK_W, FX_DEF, FX_SPD = 1474.704, 465.696, 606.375, 100
FX_HP = FX_HP_W * 1.18                        # 1740.15072（慧明 stat_of 基数）
FX_CR, FX_CD = 0.05 + 0.187, 0.5              # 0.237
FX_CZ = 1 + FX_CR * FX_CD                     # 1.1185


def _fx2(mult: float, *, hp: float = FX_HP, cz: float = FX_CZ) -> float:
    """1208 期望伤害：倍率×HP×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0）."""
    return mult * hp * 0.5 * 0.9 * cz


def _opt_fuxuan(action: str, *, cond: dict | None = None):
    c = {"skillActive": False, "talentActive": True, "e6TeamHpLostPercent": 1.2}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1208", "eidolon": 0,
            "action": action, "element": "quantum", "conditionals": c,
            "base": {"atk": FX_ATK_W, "hp": FX_HP_W, "def": FX_DEF, "spd": FX_SPD},
            "attacker": {"atk": FX_ATK_W, "hp": FX_HP, "def": FX_DEF, "spd": FX_SPD,
                         "cr": FX_CR, "cd": FX_CD},
            "self_path": "Preservation",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 符玄 1208（对方 1200/FuXuan.ts 全实现——BASIC/ULT/TALENT_HEAL/BREAK 注册）
# ——穷观阵慧明辐射族（HP 倍率生存位）
# ===========================================================================

class TestFuXuanDuipai:
    """符玄 E0：普攻裸发三方全等（B-TR③ 收官）/慧明链（self HP×1.06+CR 0.357）
    普攻/终结技三方全等."""

    def test_basic(self, optimizer_driver):
        """普攻 0.5×HP 量子（lv6 档，慧明外）：行迹暴击 0.187/生命+18%（fixture
        回填）三方全等."""
        eng, log = _make_logged(_solo_compiled("1208", enemies=_dummy("e1", "quantum")))
        log.clear()
        _cast(eng, "1208", "120801")
        ours = _hit_amounts(log, source="1208")
        theirs = run_optimizer(optimizer_driver, _opt_fuxuan("basic"))

        hand = _fx2(0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", FX_CZ), ("dmgBoostMulti", 1.0),
                     ("abilityMulti", 0.5 * FX_HP)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_knowledge_chain(self, optimizer_driver):
        """慧明链：战技挂阵 → self HP 1740.15072×1.06=1844.56（对方 dynamic
        conversion 同值）+CR 0.357 → 普攻窗内三方全等；阵下战技回能 30+20 对账."""
        eng, log = _make_logged(_solo_compiled("1208", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1208"]
        log.clear()
        _cast(eng, "1208", "120802", target="1208")
        assert "FU_XUAN_KNOWLEDGE" in st.modifiers
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["hp"], FX_HP * 1.06, rel_tol=1e-9), "慧明 self HP×1.06"
        assert math.isclose(eff["crit_rate"], FX_CR + 0.12, rel_tol=1e-9), "慧明 CR+0.12"
        _cast(eng, "1208", "120801")
        ours = _hit_amounts(log, source="1208")
        theirs = run_optimizer(optimizer_driver, _opt_fuxuan(
            "basic", cond={"skillActive": True}))

        fx_hp_k = FX_HP * 1.06                        # 1844.5598
        cz_k = 1 + (FX_CR + 0.12) * FX_CD             # 1.1785
        hand = _fx2(0.5, hp=fx_hp_k, cz=cz_k)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方慧明普攻 vs 手算"
        assert theirs["stats"]["hp"] == pytest.approx(fx_hp_k, rel=REL_TOL), (
            "对方 dynamic conversion HP 面板回显 1844.56")
        assert theirs["stats"]["cr"] == pytest.approx(0.357, rel=REL_TOL), (
            "对方 CR 0.357 面板回显")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert math.isclose(st.current_energy, 50.0 + 20.0), "阵下战技 30+20+普攻 20"

    def test_ult_knowledge_window(self, optimizer_driver):
        """终结技 1.0×HP（慧明窗内）：HP×1.06+CR 0.357 双方同值三方全等；天赋回血
        次数+1 对账."""
        eng, log = _make_logged(_solo_compiled("1208", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1208"]
        _cast(eng, "1208", "120802", target="1208")
        assert st.resources["_fx_restore"] == 1.0
        log.clear()
        _fire_ult(eng, "1208", "120803", energy=135.0)
        ours = _hit_amounts(log, source="1208")
        theirs = run_optimizer(optimizer_driver, _opt_fuxuan(
            "ult", cond={"skillActive": True}))

        hand = _fx2(1.0, hp=FX_HP * 1.06, cz=1 + (FX_CR + 0.12) * FX_CD)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方终结技 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert st.resources["_fx_restore"] == 2.0, "终结技天赋回血次数+1"


# 罗刹 1203（虚数；行迹 攻击+28%/生命+18%/防御+12.5%——B-TR③ 已回填 fixture）
LC_ATK_W, LC_HP_W, LC_DEF_W, LC_SPD = 756.756, 1280.664, 363.825, 101
LC_ATK = LC_ATK_W * 1.28                      # 968.64768
LC_HP = LC_HP_W * 1.18                        # 1511.18352
LC_DEF = LC_DEF_W * 1.125                     # 409.303125
LC_CZ = 1 + 0.05 * 0.5                        # 1.025


def _lc2(mult: float) -> float:
    """1203 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0）."""
    return mult * LC_ATK * 0.5 * 0.9 * LC_CZ


def _opt_luocha(action: str, *, cond: dict | None = None):
    c = {"fieldActive": True, "e6ResReduction": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1203", "eidolon": 0,
            "action": action, "element": "imaginary", "conditionals": c,
            "base": {"atk": LC_ATK_W, "hp": LC_HP_W, "def": LC_DEF_W, "spd": LC_SPD},
            "attacker": {"atk": LC_ATK, "hp": LC_HP, "def": LC_DEF, "spd": LC_SPD,
                         "cr": 0.05, "cd": 0.5},
            "self_path": "Abundance",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 罗刹 1203（对方 1200/Luocha.ts 全实现——BASIC/ULT/SKILL_HEAL/TALENT_HEAL/
# BREAK 注册）——结界治疗族（E0 无伤相关条件件）
# ===========================================================================

class TestLuochaDuipai:
    """罗刹 E0：普攻/终结技三方全等（B-TR③ 收官——E0 无 buff 裸链）."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 虚数（lv6 档）：行迹攻击+28%（fixture 回填）三方全等."""
        eng, log = _make_logged(_solo_compiled("1203", enemies=_dummy("e1", "imaginary")))
        log.clear()
        _cast(eng, "1203", "120301")
        ours = _hit_amounts(log, source="1203")
        theirs = run_optimizer(optimizer_driver, _opt_luocha("basic"))

        hand = _lc2(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", LC_CZ), ("dmgBoostMulti", 1.0),
                     ("abilityMulti", LC_ATK)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_ult(self, optimizer_driver):
        """终结技 2.0 虚数 AoE（lv10）：E0 裸链三方全等；深渊之花+1/回能 5 对账."""
        eng, log = _make_logged(_solo_compiled("1203", enemies=_dummy("e1", "imaginary")))
        st = eng.state.actors["1203"]
        log.clear()
        _fire_ult(eng, "1203", "120303", energy=100.0)
        ours = _hit_amounts(log, source="1203")
        theirs = run_optimizer(optimizer_driver, _opt_luocha("ult"))

        hand = _lc2(2.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方终结技 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert st.resources["_abyss_flower"] == 1.0, "终结技深渊之花+1"
        assert math.isclose(st.current_energy, 5.0), "终结技回能 5"


# 藿藿 1217 B1（风；行迹 生命+28%/效果抵抗 0.18/速度+5——B-TR③ 已回填 fixture）
HH_HP_W, HH_ATK_W, HH_DEF, HH_SPD_W = 1358.28, 601.524, 509.355, 98
HH_HP = HH_HP_W * 1.28                        # 1738.5984
HH_SPD = HH_SPD_W + 5                         # 103
HH_CZ = 1 + 0.05 * 0.5                        # 1.025


def _hh2(mult: float) -> float:
    """1217 期望伤害：倍率×HP×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0）."""
    return mult * HH_HP * 0.5 * 0.9 * HH_CZ


def _opt_huohuo(action: str, *, cond: dict | None = None, base_energy: float = 140.0):
    c = {"ultBuff": False, "skillBuff": True, "e6DmgBuff": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1217b1", "eidolon": 0,
            "action": action, "element": "wind", "conditionals": c,
            "base": {"atk": HH_ATK_W, "hp": HH_HP_W, "def": HH_DEF, "spd": HH_SPD_W},
            "attacker": {"atk": HH_ATK_W, "hp": HH_HP, "def": HH_DEF, "spd": HH_SPD,
                         "cr": 0.05, "cd": 0.5},
            "self_path": "Abundance", "base_energy": base_energy,
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 藿藿 1217（对方 1200/HuohuoB1.ts 全实现——BASIC/SKILL_HEAL/TALENT_HEAL/
# BREAK 注册）——禳命增益+治疗族（R-HH1 终结技排自身差）
# ===========================================================================

class TestHuohuoDuipai:
    """藿藿 E0（B1）：普攻三方全等（B-TR③ 收官）/终结技增益链 R-HH1 排自身差
    +160 能量门控双 ally 对账."""

    def test_basic(self, optimizer_driver):
        """普攻 0.5×HP 风（lv6 档）：行迹生命+28%（fixture 回填）三方全等."""
        eng, log = _make_logged(_solo_compiled("1217", enemies=_dummy("e1", "wind")))
        log.clear()
        _cast(eng, "1217", "1121701")
        ours = _hit_amounts(log, source="1217")
        theirs = run_optimizer(optimizer_driver, _opt_huohuo("basic"))

        hand = _hh2(0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", HH_CZ), ("dmgBoostMulti", 1.0),
                     ("abilityMulti", 0.5 * HH_HP)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_ult_buff_r_hh1(self, optimizer_driver):
        """R-HH1：终结技 ATK 增益——官方/我方除自身（self ATK 601.524 不变）vs
        对方 FullTeam 含自身（×1.40=842.13），面板比恰为 1.40；双 ally 门控
        （max_energy 100→0.40 单件 / 200→0.64 双件）vs 手算；回能排自身对账；
        普攻 HP 倍率伤害不受 ATK 差影响仍三方全等."""
        ally2 = _ally("ally2", atk=1500.0)
        ally2["base_stats"]["max_energy"] = 200
        eng, log = _make_logged(_solo_compiled(
            "1217", enemies=_dummy("e1", "wind"),
            extra_members=[_ally(), ally2]))
        st = eng.state.actors["1217"]
        al1, al2 = eng.state.actors["ally"], eng.state.actors["ally2"]
        assert math.isclose(st.current_energy, 30.0), "Fearful to Act 进战 30 能"
        log.clear()
        _fire_ult(eng, "1217", "1121703", energy=140.0)
        ours_atk = eng.pipeline.effective_stats(st)["atk"]
        al1_atk = eng.pipeline.effective_stats(al1)["atk"]
        al2_atk = eng.pipeline.effective_stats(al2)["atk"]
        theirs = run_optimizer(optimizer_driver, _opt_huohuo(
            "basic", cond={"ultBuff": True}, base_energy=140.0))

        assert math.isclose(ours_atk, HH_ATK_W, rel_tol=1e-9), "我方排自身：self ATK 不变"
        assert theirs["stats"]["atk"] == pytest.approx(HH_ATK_W * 1.4, rel=REL_TOL), (
            "对方 FullTeam 含自身 ×1.40 面板回显")
        assert theirs["stats"]["atk"] / ours_atk == pytest.approx(1.4, rel=REL_TOL), (
            "R-HH1 面板比恰为 1.40（官方除自身——对方侧疑病存目）")
        assert math.isclose(al1_atk, 1500 * 1.4, rel_tol=1e-9), (
            "ally（max_energy 100<160）：0.40 单件 vs 手算")
        assert math.isclose(al2_atk, 1500 * 1.64, rel_tol=1e-9), (
            "ally2（max_energy 200≥160）：0.40+0.24 双件 vs 手算（对方一刀切无落点在案）")
        assert math.isclose(al1.current_energy, 20.0), "回能 20%×100"
        assert math.isclose(al2.current_energy, 40.0), "回能 20%×200"
        assert math.isclose(st.current_energy, 5.0 + 3.0), (
            "排自身：基础 5+provision 三批治疗回 3（钉能开大覆盖进战 30）")
        # 普攻伤害（HP 倍率）不受 ATK 增益差影响——仍三方全等
        _cast(eng, "1217", "1121701")
        ours = _hit_amounts(log, source="1217")
        assert ours == pytest.approx([_hh2(0.5)], rel=REL_TOL), "普攻 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "普攻段双方互对（ATK 差不伤 HP 倍率段）")


# 银枝 1302（物理；行迹 攻击 0.28/物理 0.144/生命+10%——前置波次已填 fixture）
AG_ATK_W, AG_HP_W, AG_DEF, AG_SPD = 737.352, 1047.816, 363.825, 103
AG_ATK = AG_ATK_W * 1.28                      # 943.81056
AG_HP = AG_HP_W * 1.1                         # 1152.5976
AG_PHYS = 0.144
AG_CR, AG_CD = 0.05, 0.5


def _ag(mult: float, *, cr: float = AG_CR, boost: float = 0.0) -> float:
    """1302 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池（1+物理 0.144）."""
    return mult * AG_ATK * 0.5 * 0.9 * (1 + cr * AG_CD) * (1 + AG_PHYS + boost)


def _opt_argenti(action: str, *, cond: dict | None = None):
    c = {"ultEnhanced": False, "talentStacks": 0, "ultEnhancedExtraHits": 6,
         "e2UltAtkBuff": True, "enemyHp50": False}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1302", "eidolon": 0,
            "action": action, "element": "physical", "conditionals": c,
            "base": {"atk": AG_ATK_W, "hp": AG_HP_W, "def": AG_DEF, "spd": AG_SPD},
            "attacker": {"atk": AG_ATK, "hp": AG_HP, "def": AG_DEF, "spd": AG_SPD,
                         "cr": AG_CR, "cd": AG_CD, "element_boost": AG_PHYS},
            "self_path": "Erudition",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 银枝 1302（对方 1300/Argenti.ts 全实现——BASIC/SKILL/ULT/BREAK 注册，
# 强化终结技折叠段）——升格叠层+双阈值终结技族
# ===========================================================================

class TestArgentiDuipai:
    """银枝 E0：普攻/战技/终结技（90）/升格 CR 叠层三方全等/强化终结技（180）
    R-AG2 折叠爬坡差/勇气低血场 R-AG1."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 物理（lv6 档）：行迹攻击 0.28/物理 0.144 三方全等；命中+1 层
        +3 能对账."""
        eng, log = _make_logged(_solo_compiled("1302", enemies=_dummy("e1", "physical")))
        st = eng.state.actors["1302"]
        log.clear()
        _cast(eng, "1302", "130201")
        ours = _hit_amounts(log, source="1302")
        theirs = run_optimizer(optimizer_driver, _opt_argenti("basic"))

        hand = _ag(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("dmgBoostMulti", 1.144), ("abilityMulti", AG_ATK)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert st.resources["apotheosis"] == 1.0, "单体命中+1 层"
        assert math.isclose(st.current_energy, 20.0 + 3.0), "普攻 20+天赋 3"

    def test_skill_and_talent_cr_stacks(self, optimizer_driver):
        """战技 1.2 三方全等；两发后升格 2 层（CR 0.10）→ 第三发窗内对方
        talentStacks=2 双钉比等（CR+0.025×层 双方同值）."""
        eng, log = _make_logged(_solo_compiled("1302", enemies=_dummy("e1", "physical")))
        st = eng.state.actors["1302"]
        log.clear()
        _cast(eng, "1302", "130202")
        ours_first = _hit_amounts(log, source="1302")
        theirs_skill = run_optimizer(optimizer_driver, _opt_argenti("skill"))
        assert ours_first == pytest.approx([_ag(1.2)], rel=REL_TOL), "战技首发 vs 手算"
        assert ours_first[0] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)

        _cast(eng, "1302", "130202")
        assert st.resources["apotheosis"] == 2.0, "两发 2 层（单敌命中口径）"
        log.clear()
        _cast(eng, "1302", "130202")
        ours = _hit_amounts(log, source="1302")
        theirs = run_optimizer(optimizer_driver, _opt_argenti(
            "skill", cond={"talentStacks": 2}))

        hand = _ag(1.2, cr=AG_CR + 0.05)
        assert ours == pytest.approx([hand], rel=REL_TOL), "战技（升格 2 层 CR 0.10）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["cr"] == pytest.approx(0.10, rel=REL_TOL), (
            "对方升格 2 层 CR 0.10 面板回显")

    def test_ult_90(self, optimizer_driver):
        """终结技（90 档）130203 1.6 AoE 三方全等；耗 90 返 5+天赋 3 对账."""
        eng, log = _make_logged(_solo_compiled("1302", enemies=_dummy("e1", "physical")))
        st = eng.state.actors["1302"]
        log.clear()
        _fire_ult(eng, "1302", "130203", energy=90.0)
        ours = _hit_amounts(log, source="1302")
        theirs = run_optimizer(optimizer_driver, _opt_argenti("ult"))

        hand = _ag(1.6)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方终结技 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert math.isclose(st.current_energy, 5.0 + 3.0), "耗 90 返 5+天赋 3"

    def test_enhanced_ult_r_ag2(self, optimizer_driver):
        """R-AG2：强化终结技（180）130214——我方 主 2.8+弹射 0.95×6 共 7 段（弹射
        i 吃 主段+i 层 CR 爬坡）vs 对方折叠 8.5 单发静态档；主段三方全等，总和
        差恰为 8.961875/8.7125（段数差在案）."""
        eng, log = _make_logged(_solo_compiled("1302", enemies=_dummy("e1", "physical")))
        st = eng.state.actors["1302"]
        log.clear()
        _fire_ult(eng, "1302", "130214", energy=180.0)
        ours = _hit_amounts(log, source="1302")
        theirs = run_optimizer(optimizer_driver, _opt_argenti(
            "ult", cond={"ultEnhanced": True, "ultEnhancedExtraHits": 6,
                         "talentStacks": 0}))

        assert len(ours) == 7, "主段+弹射 6 段（对方折叠单发——段数差在案）"
        assert ours[0] == pytest.approx(_ag(2.8), rel=REL_TOL), "主段 2.8（0 层）vs 手算"
        for i in range(1, 7):
            cr_i = AG_CR + 0.025 * i
            assert ours[i] == pytest.approx(_ag(0.95, cr=cr_i), rel=REL_TOL), (
                f"弹射 {i}（{i} 层 CR {cr_i:.2f}）vs 手算")
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(8.5, rel=REL_TOL), (
            "对方折叠 2.8+6×0.95=8.50")
        assert theirs["hits"][0]["damage"] == pytest.approx(_ag(8.5), rel=REL_TOL), (
            "对方折叠（静态 0 层）vs 手算")
        assert sum(ours) / theirs["hits"][0]["damage"] == pytest.approx(
            8.961875 / 8.7125, rel=REL_TOL), (
            "R-AG2 总和差恰为 8.961875/8.7125（段序暴击爬坡——对方静态档无通道）")
        assert st.resources["apotheosis"] == 7.0, "主段 1+弹射 6 层"
        assert math.isclose(st.current_energy, 5.0 + 3.0 + 6 * 3.0), (
            "耗 180 返 5+主段 3+弹射 6×3=32")

    def test_courage_r_ag1(self, optimizer_driver):
        """R-AG1：勇气 1302103（敌 HP≤50%）——我方 before_take_damage ×1.15 乘法
        （物理 0.144 非空池→1.3156）vs 对方 BOOST 0.15 加算（1.294），差恰为
        1.3156/1.294（空池等价在案；官方加算读法占优列真病候选待过堂）."""
        eng, log = _make_logged(_solo_compiled("1302", enemies=_dummy("e1", "physical")))
        eng.state.actors["e1"].current_hp = 0.4e9          # 40% ≤50% 触发域
        log.clear()
        _cast(eng, "1302", "130201")
        ours = _hit_amounts(log, source="1302")
        theirs = run_optimizer(optimizer_driver, _opt_argenti(
            "basic", cond={"enemyHp50": True}))

        hand_ours = _ag(1.0) * 1.15                        # 乘法改写（增伤池外）
        hand_theirs = _ag(1.0, boost=0.15)                 # 加算池 1.294
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方（乘法×1.15）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方（加算 1.294）vs 手算")
        assert ours[0] / theirs["hits"][0]["damage"] == pytest.approx(
            1.3156 / 1.294, rel=REL_TOL), (
            "R-AG1 差恰为 1.3156/1.294（乘法改写 vs 加算池——空池等价在案）")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.294, rel=REL_TOL), "对方增伤池回显 1.294"


# 阮•梅 1303（冰；行迹 BE 0.373/spd+5 前置已并 base_stats + 防御+22.5% B-TR③ 补尾矿）
RM_ATK_W, RM_HP_W, RM_DEF_W, RM_SPD = 659.736, 1086.624, 485.1, 109
RM_DEF = RM_DEF_W * 1.225                     # 594.2475
RM_BE = 0.373                                 # base_stats 已并（行迹节点）
RM_BE_TEAM = RM_BE + 0.2                      # 0.573（1303101 全队 BE+20%——B-RM①）
RM_CZ = 1 + 0.05 * 0.5                        # 1.025


def _rm(mult: float, *, boost: float = 0.0, res_pen: float = 0.0) -> float:
    """1303 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池×抗区."""
    return mult * RM_ATK_W * 0.5 * 0.9 * RM_CZ * (1 + boost) * (1 + res_pen)


def _opt_ruanmei(action: str, *, cond: dict | None = None, be: float = RM_BE):
    c = {"skillOvertoneBuff": False, "teamBEBuff": True, "ultFieldActive": False,
         "e2AtkBoost": False, "e4BeBuff": False}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1303", "eidolon": 0,
            "action": action, "element": "ice", "conditionals": c,
            "base": {"atk": RM_ATK_W, "hp": RM_HP_W, "def": RM_DEF_W, "spd": RM_SPD},
            "attacker": {"atk": RM_ATK_W, "hp": RM_HP_W, "def": RM_DEF, "spd": RM_SPD,
                         "cr": 0.05, "cd": 0.5, "be": be},
            "self_path": "Harmony",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 阮•梅 1303（对方 1300/RuanMei.ts 全实现——BASIC/BREAK/BUFF 注册+BUFF 段
# BE 转换）——弦外音/结界光环族（B-RM① 大行迹三件收编后全链对拍）
# ===========================================================================

class TestRuanMeiDuipai:
    """阮•梅 E0：普攻裸发三方全等/弦外音增伤链/结界抗穿链三方全等（B-TR③+B-RM①
    双收官）/BE 转换注入档+R-RM1 门控差."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 冰（lv6 档，裸链）：1303101 全队 BE 0.2（B-RM①）不进直伤
        乘区——双方同值三方全等."""
        eng, log = _make_logged(_solo_compiled("1303", enemies=_dummy("e1", "ice")))
        st = eng.state.actors["1303"]
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["break_effect"], RM_BE_TEAM, rel_tol=1e-9), (
            "1303101 全队 BE+20%（0.373+0.2=0.573——B-RM① 收编）")
        log.clear()
        _cast(eng, "1303", "130301")
        ours = _hit_amounts(log, source="1303")
        theirs = run_optimizer(optimizer_driver, _opt_ruanmei("basic"))

        hand = _rm(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["be"] == pytest.approx(RM_BE_TEAM, rel=REL_TOL), (
            "对方 BE 0.573 面板回显（teamBEBuff 0.2）")
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", RM_CZ), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_skill_overtone_chain(self, optimizer_driver):
        """弦外音链：战技挂 → 全队 all_dmg 0.32（BE 0.573<1.2 转换不点火）→
        普攻增伤池 1.32 双方同值三方全等."""
        eng, log = _make_logged(_solo_compiled("1303", enemies=_dummy("e1", "ice")))
        log.clear()
        _cast(eng, "1303", "130302", target="1303")
        st = eng.state.actors["1303"]
        assert "XWY" in st.modifiers
        _cast(eng, "1303", "130301")
        ours = _hit_amounts(log, source="1303")
        theirs = run_optimizer(optimizer_driver, _opt_ruanmei(
            "basic", cond={"skillOvertoneBuff": True}))

        hand = _rm(1.0, boost=0.32)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方弦外音普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.32, rel=REL_TOL), "对方增伤池回显 1.32"

    def test_ult_field_res_pen(self, optimizer_driver):
        """结界链：终结技挂 RM_ZONE → 全队 res_pen 0.25（抗区 1.25）→ 普攻双方
        同值三方全等；1303102 回合开始回能 5 对账（B-RM①）."""
        eng, log = _make_logged(_solo_compiled("1303", enemies=_dummy("e1", "ice")))
        st = eng.state.actors["1303"]
        log.clear()
        _fire_ult(eng, "1303", "130303", energy=130.0)
        assert "RM_ZONE" in st.modifiers
        _cast(eng, "1303", "130301")
        ours = _hit_amounts(log, source="1303")
        theirs = run_optimizer(optimizer_driver, _opt_ruanmei(
            "basic", cond={"ultFieldActive": True}))

        hand = _rm(1.0, res_pen=0.25)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方结界普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["resMulti"] == pytest.approx(
            1.25, rel=REL_TOL), "对方抗区回显 1.25"
        e0 = st.current_energy
        eng.bus.emit("on_turn_start", {"actor": "1303"}, eng.state)
        assert math.isclose(st.current_energy, e0 + 5.0), "1303102 回合开始回能 5（B-RM①）"

    def test_be_conversion_injected(self, optimizer_driver):
        """BE 转换注入档（B-RM①）：注入 BE+1.227 → 面板 1.8 → 开战技转换 0.36
        （整数档 floor≡连续）→ 增伤池 1.32+0.36=1.68 双方同值三方全等."""
        eng, log = _make_logged(_solo_compiled("1303", enemies=_dummy("e1", "ice")))
        _inject(eng, "1303", "RM_BE_INJ", {"break_effect": 1.227})
        eff = eng.pipeline.effective_stats(eng.state.actors["1303"])
        assert math.isclose(eff["break_effect"], 1.8, rel_tol=1e-9), "注入后 BE 1.8"
        log.clear()
        _cast(eng, "1303", "130302", target="1303")
        _cast(eng, "1303", "130301")
        ours = _hit_amounts(log, source="1303")
        theirs = run_optimizer(optimizer_driver, _opt_ruanmei(
            "basic", cond={"skillOvertoneBuff": True}, be=1.6))

        hand = _rm(1.0, boost=0.32 + 0.36)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方转换普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方（floor(60/10)×0.06=0.36）vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.68, rel=REL_TOL), "对方增伤池回显 1.68"

    def test_be_conversion_gating_r_rm1(self, optimizer_driver):
        """R-RM1：转换门控差——无战技场（弦外音不在）我方转换同灭（增伤池 1.0）
        vs 对方 finalize 无门控常驻（0.36），差恰为 1.36（官方「战技额外使」
        门控读法占优——对方侧疑病存目）."""
        eng, log = _make_logged(_solo_compiled("1303", enemies=_dummy("e1", "ice")))
        _inject(eng, "1303", "RM_BE_INJ", {"break_effect": 1.227})
        log.clear()
        _cast(eng, "1303", "130301")
        ours = _hit_amounts(log, source="1303")
        theirs = run_optimizer(optimizer_driver, _opt_ruanmei("basic", be=1.6))

        assert ours == pytest.approx([_rm(1.0)], rel=REL_TOL), (
            "我方无战技（转换随弦外音同灭）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _rm(1.0, boost=0.36), rel=REL_TOL), "对方（无门控常驻 0.36）vs 手算"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(1.36, rel=REL_TOL), (
            "R-RM1 差恰为 1.36（官方门控读法占优——对方侧疑病存目）")


# 花火 1306 B1（量子；行迹 生命+28%/暴伤 0.24/效果抵抗 0.10——B-TR③ 已回填 fixture）
HH2_HP_W, SK_ATK_W, SK_DEF, SK_SPD = 1397.088, 523.908, 485.1, 101
SK_HP = HH2_HP_W * 1.28                       # 1788.27264
SK_CD = 0.5 + 0.24                            # 0.74
SK_CR = 0.05
SK_CZ = 1 + SK_CR * SK_CD                     # 1.037
SK_NOCTURNE = 0.45                            # 夜幕 atk_pct（B1）


def _sk(mult: float, *, atk: float = SK_ATK_W * (1 + SK_NOCTURNE), cz: float = SK_CZ,
        vuln: float = 0.0, res_pen: float = 0.0) -> float:
    """1306 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×承伤区×抗区."""
    return mult * atk * 0.5 * 0.9 * cz * (1 + vuln) * (1 + res_pen)


def _opt_sparkle(action: str, *, cond: dict | None = None):
    c = {"skillBuffs": False, "cipherBuff": False, "talentStacks": 0,
         "teamAtkBuff": True, "e1SpdBuff": True, "e2DefPen": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1306b1", "eidolon": 0,
            "action": action, "element": "quantum", "conditionals": c,
            "base": {"atk": SK_ATK_W, "hp": HH2_HP_W, "def": SK_DEF, "spd": SK_SPD},
            "attacker": {"atk": SK_ATK_W, "hp": SK_HP, "def": SK_DEF, "spd": SK_SPD,
                         "cr": SK_CR, "cd": SK_CD},
            "self_path": "Harmony",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 花火 1306（对方 1300/SparkleB1.ts 全实现——BASIC/BREAK/BUFF 注册+BUFF 段
# CD 转换）——梦游鱼暴伤+谜诡易伤族
# ===========================================================================

class TestSparkleDuipai:
    """花火 E0（B1）：普攻（夜幕 ATK×1.45 常驻）三方全等（B-TR③ 收官）/梦游鱼
    自指链（CD 转换+抗穿）/谜诡幻景易伤链三方全等."""

    def test_basic_nocturne_atk(self, optimizer_driver):
        """普攻 1.0 量子（lv6 档）：夜幕 ATK+45%（双方常驻——对方 teamAtkBuff
        FullTeam）+行迹暴伤 0.24（fixture 回填）三方全等；星历回能对账."""
        eng, log = _make_logged(_solo_compiled("1306", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1306"]
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], SK_ATK_W * 1.45, rel_tol=1e-9), (
            "夜幕 atk_pct 0.45 开战光环（759.67）")
        log.clear()
        _cast(eng, "1306", "1130601")
        ours = _hit_amounts(log, source="1306")
        theirs = run_optimizer(optimizer_driver, _opt_sparkle("basic"))

        hand = _sk(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["stats"]["atk"] == pytest.approx(SK_ATK_W * 1.45, rel=REL_TOL), (
            "对方 ATK_P 0.45 面板回显")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert math.isclose(st.current_energy, 30.0), "普攻 20+星历 10"

    def test_skill_self_cd_respen_chain(self, optimizer_driver):
        """梦游鱼自指链：战技自指 → CD 0.74+（0.24×0.74+0.45）=1.3676（对方 base
        0.45 UNCONVERTIBLE+conversion 0.24×0.74 同值）+抗穿 0.10 → 普攻窗内三方
        全等（自指不拉条在案）."""
        eng, log = _make_logged(_solo_compiled("1306", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1306"]
        log.clear()
        _cast(eng, "1306", "1130602", target="1306")
        assert "SPK_CRIT_DMG" in st.modifiers
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_dmg"], SK_CD + (0.24 * SK_CD + 0.45), rel_tol=1e-9), (
            "梦游鱼 CD 0.74+0.6276=1.3676")
        assert math.isclose(eff["res_pen"], 0.10, rel_tol=1e-9), "夜幕抗穿 0.10"
        _cast(eng, "1306", "1130601")
        ours = _hit_amounts(log, source="1306")
        theirs = run_optimizer(optimizer_driver, _opt_sparkle(
            "basic", cond={"skillBuffs": True, "talentStacks": 1}))

        cz_buff = 1 + SK_CR * (SK_CD + 0.24 * SK_CD + 0.45)   # 1.06838
        # 战技耗 1 点 → 幻景 1 层 → SPK_VULN 0.04 承伤（无谜诡）——对方 talentStacks=1 同值
        hand = _sk(1.0, cz=cz_buff, vuln=0.04, res_pen=0.10)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方梦游鱼普攻 vs 手算"
        assert theirs["stats"]["cd"] == pytest.approx(
            SK_CD + 0.45 + 0.24 * SK_CD, rel=REL_TOL), (
            "对方 CD 面板回显 1.3676（base 0.45 不可转换+conversion 0.24×0.74）")
        assert theirs["stats"]["res_pen"] == pytest.approx(0.10, rel=REL_TOL), (
            "对方 RES_PEN 0.10 面板回显")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert math.isclose(st.current_energy, 30.0 + 1.0 + 30.0), (
            "战技 30+星历②SP 消费回 1+普攻 20+星历① 10=61")

    def test_ult_cipher_figment_vuln(self, optimizer_driver):
        """谜诡幻景易伤链：终结技先挂谜诡 → 三战技耗 3 点叠幻景 3 层（SPK_VULN
        蒙福者快照烘焙=消费时点读谜诡在——先谜诡后消费官方动态域等价）→ 敌方
        承伤 3×(0.04+0.06)=0.30（对方 VULNERABILITY FullTeam 同区）→ 普攻承伤区
        1.30 双方同值三方全等；SP 6+溢出对账."""
        eng, log = _make_logged(_solo_compiled("1306", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1306"]
        log.clear()
        _fire_ult(eng, "1306", "1130603", energy=110.0)
        assert "SPK_CIPHER" in st.modifiers
        for _ in range(3):
            _cast(eng, "1306", "1130602", target="1306")
        assert st.modifiers["SPK_FIGMENT"].stacks == 3, "幻景 3 层（耗 3 点）"
        assert "SPK_VULN" in eng.state.actors["e1"].modifiers, "易伤挂敌方"
        _cast(eng, "1306", "1130601")
        ours = _hit_amounts(log, source="1306")
        theirs = run_optimizer(optimizer_driver, _opt_sparkle(
            "basic", cond={"skillBuffs": True, "cipherBuff": True, "talentStacks": 3}))

        cz_buff = 1 + SK_CR * (SK_CD + 0.24 * SK_CD + 0.45)   # 1.06838（自指 replace 重挂同值）
        hand = _sk(1.0, cz=cz_buff, vuln=0.30, res_pen=0.10)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方谜诡易伤普攻 vs 手算"
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(
            1.30, rel=REL_TOL), "对方承伤区回显 1.30"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert math.isclose(eng.state.skill_points, 5.0), "3+6→钳 7（溢出 2）-3+1=5"
        assert st.resources["sp_overflow"] == 2.0, "溢出 2 入池"


# 流萤 1310 B1（火；行迹 BE 0.373/RES 0.18/spd+5——B-FF① 勘正后官方单轨值）
FF_ATK_W, FF_HP_W, FF_DEF, FF_SPD = 523.908, 814.968, 776.16, 109
FF_BE = 0.373
FF_BE_COMB = FF_BE + 0.25                     # 0.623（α 模组燃烧内+25%）
FF_CZ = 1 + 0.05 * 0.5                        # 1.025


def _ff(mult: float, *, universal: float = 0.9) -> float:
    """1310 期望直伤：倍率×ATK×防御区 0.5×未击破/已击破×期望暴击（增伤池 1.0）."""
    return mult * FF_ATK_W * 0.5 * universal * FF_CZ


def _opt_firefly(action: str, *, cond: dict | None = None, be: float = FF_BE):
    c = {"enhancedStateActive": False, "enhancedStateSpdBuff": True,
         "superBreakDmg": False, "atkToBeConversion": True,
         "talentDmgReductionBuff": True, "e1DefShred": True, "e4ResBuff": True,
         "e6Buffs": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1310b1", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": FF_ATK_W, "hp": FF_HP_W, "def": FF_DEF, "spd": FF_SPD},
            "attacker": {"atk": FF_ATK_W, "hp": FF_HP_W, "def": FF_DEF, "spd": FF_SPD,
                         "cr": 0.05, "cd": 0.5, "be": be},
            "self_path": "Destruction",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _enter_combustion(eng):
    """终结技进完全燃烧（state_config：spd+60/效率+0.5/α BE+0.25/强化替换）."""
    st = eng.state.actors["1310"]
    _fire_ult(eng, "1310", "1131003", energy=240.0)
    assert st.state_config is not None, "进完全燃烧"


# ===========================================================================
# L2 流萤 1310（对方 1300/FireflyB1.ts 全实现——BASIC/SKILL/BREAK 注册+超击破
# 附段）——完全燃烧超击破族（B-FF①/B-FF② 双收官后全链对拍）
# ===========================================================================

class TestFireflyDuipai:
    """流萤 E0（B1 现役）：普攻裸发/完全燃烧强化普攻/强化战技（B-FF② BE 转换
    段）三方全等/击破场超击破 R-FF1."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 火（lv6 档，燃烧外）：B-FF① 勘正基线（BE 0.373 不入直伤乘区）
        三方全等."""
        eng, log = _make_logged(_solo_compiled("1310", enemies=_dummy("e1", "fire")))
        log.clear()
        _cast(eng, "1310", "1131001")
        ours = _hit_amounts(log, source="1310")
        theirs = run_optimizer(optimizer_driver, _opt_firefly("basic"))

        hand = _ff(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", FF_CZ), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_combustion_enhanced_basic(self, optimizer_driver):
        """完全燃烧强化普攻 2.0（1131008 lv6 档）：spd 169/BE 0.623（α+25%）面板
        双方同值三方全等."""
        eng, log = _make_logged(_solo_compiled("1310", enemies=_dummy("e1", "fire")))
        log.clear()
        _enter_combustion(eng)
        log.clear()
        _cast(eng, "1310", "1131008")
        ours = _hit_amounts(log, source="1310")
        theirs = run_optimizer(optimizer_driver, _opt_firefly(
            "basic", cond={"enhancedStateActive": True}))

        hand = _ff(2.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方强化普攻 vs 手算"
        assert theirs["stats"]["spd"] == pytest.approx(169.0, rel=REL_TOL), (
            "对方燃烧 spd 109+60=169 面板回显")
        assert theirs["stats"]["be"] == pytest.approx(FF_BE_COMB, rel=REL_TOL), (
            "对方 α BE 0.623 面板回显")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_enhanced_skill_be_conversion_b_ff2(self, optimizer_driver):
        """B-FF②：强化战技（燃烧内）——我方 主 2.0+BE 转换段 0.2×0.623=0.1246 双段
        vs 对方折叠 2.1246 单发（beScaling 0.2 beCap 3.6），段数差在案总和三方
        全等；植火弱对账."""
        eng, log = _make_logged(_solo_compiled("1310", enemies=_dummy("e1", "physical")))
        _enter_combustion(eng)
        log.clear()
        _cast(eng, "1310", "1131009")
        ours = _hit_amounts(log, source="1310")
        theirs = run_optimizer(optimizer_driver, _opt_firefly(
            "skill", cond={"enhancedStateActive": True}))

        assert "FF_FIRE_WEAK" in eng.state.actors["e1"].modifiers, "植火弱 2 回合"
        assert len(ours) == 2, "主段+BE 转换段（对方折叠单发——段数差在案）"
        assert ours[0] == pytest.approx(_ff(2.0), rel=REL_TOL), "主段 2.0 vs 手算"
        assert ours[1] == pytest.approx(_ff(0.2 * FF_BE_COMB), rel=REL_TOL), (
            "BE 转换段 0.2×0.623 vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _ff(2.0 + 0.2 * FF_BE_COMB), rel=REL_TOL), "对方折叠 2.1246 vs 手算"
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "双段总和 vs 对方折叠互对")

    def test_super_break_r_ff1(self, optimizer_driver):
        """R-FF1：击破场超击破——注入 BE+1.0（面板 1.623≥150% 转化 100% 双方同档）：
        我方超击破段（376.75533×45×2.623×0.5×1.0）vs 对方同基数×击破易伤 1.2
        （我方终结技易伤窗口待收），差恰为 ×1.2；直伤双段（BE 转换 0.3246）总
        和仍三方全等."""
        # 舞台韧性 100 档（击破基数按满韧读——e2e 先例；削韧 B-FF③ 后 30×1.5=45）
        eng, log = _make_logged(_solo_compiled("1310", enemies=[
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 100, "weakness": ["physical"]}]))
        st = eng.state.actors["1310"]
        _inject(eng, "1310", "FF_BE_INJ", {"break_effect": 1.0})
        _enter_combustion(eng)
        e1 = eng.state.actors["e1"]
        e1.toughness = 15.0
        log.clear()
        _cast(eng, "1310", "1131009")                # 植弱+45 削韧首发即破
        assert e1.broken, "强战 30×1.5=45 ≥15 首发即破（B-FF③ 削韧勘正）"
        _cast(eng, "1310", "1131009")                # 已击破 → 超击破
        hits = [e["amount"] for e in log
                if e.get("reason") == "hit" and e.get("source") == "1310"]
        breaks = [e["amount"] for e in log
                  if e.get("reason") == "break" and e.get("source") == "1310"]
        theirs = run_optimizer(optimizer_driver, _opt_firefly(
            "skill", cond={"enhancedStateActive": True, "superBreakDmg": True},
            be=1.623 - 0.25))

        be_inj = FF_BE_COMB + 1.0                    # 1.623
        assert hits == pytest.approx(
            [_ff(2.0), _ff(0.2 * be_inj, universal=1.0),
             _ff(2.0, universal=1.0), _ff(0.2 * be_inj, universal=1.0)], rel=REL_TOL), (
            "两发四段（首发主 0.9/段后发读已破 1.0；二发全 1.0）vs 手算")
        brk_hand = 3767.5533 * 2.0 * (0.5 + 100 / 40) * (1 + be_inj) * 0.5
        assert breaks[0] == pytest.approx(brk_hand, rel=REL_TOL), (
            "火击破（满韧 100 档——对方 BREAK 行动独立注册本场无落点）vs 手算")
        sb_hand = 376.75533 * (30 * 1.5) * (1 + be_inj) * 0.5 * 1.0
        assert breaks[1] == pytest.approx(sb_hand, rel=REL_TOL), (
            "我方超击破段（有效削韧 45——B-FF③ 同值；转化 100%）vs 手算")
        assert len(theirs["hits"]) == 2, "对方直伤+超击破双发"
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _ff(2.0 + 0.2 * be_inj, universal=1.0), rel=REL_TOL), "对方折叠 vs 手算"
        sb_theirs = theirs["hits"][1]
        assert sb_theirs["breakdown"]["vulnMulti"] == pytest.approx(1.2, rel=REL_TOL), (
            "对方超击破段承伤区回显 1.2（击破易伤 0.20 类型过滤落段）")
        assert sb_theirs["damage"] == pytest.approx(sb_hand * 1.2, rel=REL_TOL), (
            "对方超击破（击破易伤 0.20 类型过滤）vs 手算")
        assert sb_theirs["damage"] / breaks[1] == pytest.approx(1.2, rel=REL_TOL), (
            "R-FF1 差恰为 ×1.2（终结技击破易伤窗口待收——fixture 在案）")
