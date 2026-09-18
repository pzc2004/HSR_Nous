"""L2 角色级对拍（BACKLOG B22 名册扩拍第九波）：老角色批量扫荡④——**全名册收官**。
翡翠 1314（量子/智识，当品叠层+充能追击族）/ 云璃 1221（物理/毁灭，敌方驱动
反击+Parry 双变体族）/ 椒丘 1218（火/虚无，烬煨层数易伤+灼烧 DoT 族）/
飞霄 1220（风/巡猎，飞黄计数+FUA 链族）/ 灵砂 1222（火/丰饶，浮元召唤双实体
+BE 转换治疗族）/ 大丽花 1321（火/虚无，共舞者超击破+FUA 弹射族）。

逐段伤害 == hsr-optimizer 角色实现整链伤害（rel_tol 1e-4；双锚=对方+手算，
对不上的按惯例钉结构差数值自证）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character"（CHARACTER_REGISTRY
+6 import +6 登记——本波 1314/1221/1218/1220/1222/1321；ACTION_KIND_MAP +fua_heal
灵砂浮元治疗段）。我方路径：真模板（tests/fixtures 人工根）→ 编译 → CombatEngine
钉资源/血量/回合开始 → _cast/_fire_ultimate → bus on_hp_decrease/on_hp_increase
逐段记录仪（setup 前订阅，L2 先例）。

统一口径（两侧一致，沿用前几波）：星魂钉死 E0、行迹满级（普攻 lv6/技能·终结技·
天赋 lv10）、无光锥无遗器、假人 lvl80 def 1000（防御区 0.5）、匹配弱点（抗性区
1.0）、未击破 0.9、期望暴击 1+cr·cd。**行迹属性节点本波开局即回填**（B-TR④——
B-TR①/②/③ 同例：character_skill_trees 官方十节点聚合 → trace_stat_effects；
灵砂 BE 0.373 走平铺并 base_stats——流萤/阮•梅/大丽花平铺同例；1321 经核「平铺
已并 base_stats」口径早已落账，本波不动）。

===========================================================================
翡翠 1314 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
enhancedFollowUp（true）       _ult_stacks≥1（终结技武装追击倍率强化 2 次——            未开大钉 false 比等（1.2）；
                               hook min(res__ult_stacks,1) 门控加算 #1 列）           开大后钉 true 比等（1.2+0.8=
                                                                                     2.0 倍率区加算双方同值）
pawnedAssetStacks 0-50（50）   JADE_GOODS_STAT stat_exprs（当品 CD 0.024×层+             开局逆回购①补 1 层（1 敌）钉 1
                               ATK 0.5%×层——行迹绝当品并入同件）                      比等（CD 0.524/ATK 781.78716）；
                                                                                     钉 50 比等（CD 1.7/ATK
                                                                                     943.42248 双方同值）
e1FuaDmgBoost/e2CrBuff/e4      E1 真伤段 0.32×原伤（遐蝶 E1 同构——对方 BOOST            E0 钉 true 无害（E1 结构差候选
  DefShredBuff/e6ResShredBuff  0.32 FUA 过滤加算=E1 读法差存目）/E2/E4/E6（E0          另案；E2 层数门控/E4 def_pen/
                               门控同灭）                                             E6 res_pen E0 同灭）
（无开关）收债人三件（SPD+30/   战技挂 JADE_DEBTOR：附加伤害 0.25×翡翠 ATK               **对方无落点**（Jade.ts 头注
  烧血 2%/逐击附加伤害）        （category additional）+烧血+充能逐击记账              "Assuming jade is not the debt
                                                                                     collector - skill disabled"——
                                                                                     收债人链无建模）→ 我方段 vs
                                                                                     手算钉（链内充能/烧血对账）
（无开关）折牙票开局拉条 50%    on_battle_start advance_action 50                     不伤不拍
（无开关）逆回购双源当品        on_battle_start enemies_alive() 补首发+actor_enter      开局 1 层（1 敌）面板回显同值
（无开关）充能 8 阈值追击/       hook 链（gain+阈值发射+溢出结转 max(0,res-8)+          逐段三方全等（追击 1.2/强化
  溢出结转/当品 +5/回能 10      当品 param(131404,4)=5+gain_energy 10）                2.0；资源账逐项对账）
（无开关）行迹属性节点 量子     fixture trace_stat_effects **前置波次已填**              无回填差（量子 0.224/攻击
  0.224/攻击 0.18/抵抗 0.10                                                            0.18/抵抗 0.10 双方同值）

===========================================================================
云璃 1221 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
blockActive（true）            YUNLI_PARRY 招架（终结技挂：免疫控制+减伤 0.2+           非 Parry 钉 false 比等；Parry
                               下一次反击 crit_dmg+1.0）                             钉 true 比等（CD 1.5 双方同值）
ultCull（true）/ultCullHits    Parry 中受击 Cull（主 2.2+追加 6×0.72——我方 7            逐档钉（Cull 钉 6：段数差在案
 0-6（6）                      段逐段自结 vs 对方折叠 6.52 单发）/兜底 Slash           总和三方全等；Slash 单发 2.2
                               （主 2.2 单发，Fiery Wheel 交替闩）                    双方同值）
counterAtkBuff（true）         TRUE_SUNDER_ATK atk_pct 0.3（反击后挂 1 回合——          首发钉 false 比等；次发钉 true
                               本发不吃 e2e 时序钉）                                 比等（ATK 1073.0412 双方同值）
e1UltBuff/e2DefShred/e4ResBuff E1/E2/E4/E6（E0 门控同灭）                            E0 钉 true 无害
  /e6Buffs
（无开关）Demon Quell 减伤     dmg_dmg_reduction 0.2+grants_immune control            承伤侧不伤不拍
  20%/免疫控制
（无开关）天赋反击回能 15       gain_energy 15（params #3 双证权威收编）               能量对账
（无开关）Cull/Slash 归         我方 hook deal_damage action_type:"ultimate" 声明；    无类型增伤件场双方同值
  Ultimate 伤害域              对方 damageType ULT|FUA（FUA 过滤件同吃）
（无开关）行迹属性节点 攻击     fixture trace_stat_effects 已回填（B-TR④）             攻 0.28/生命 0.18/暴击 0.067——
  0.28/生命 0.18/暴击 0.067                                                          ATK 869.2992/CR 0.117 双方同值
（无开关）Cull 削韧            我方 hook 段未逐段登记（fixture 待收在案）；对方        不伤不拍（削韧不入直伤乘区）
                               折叠 20+6×5=50

===========================================================================
椒丘 1218 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
ashenRoastStacks 0-5（5）      ASHEN_ROAST 层数（after_being_hit 命中挂 1 层           逐档钉层三方全等（易伤
                               mechanic_chance(1.0) expected 恒中；易伤               0.15/0.20 双方同值——当发不吃
                               stat_exprs 0.15+(N−1)×0.05 动态读敌方层数）           本发挂载，次发起吃——时序钉）
ultFieldActive（true）         ASHEN_ZONE_ULT_VULN vulnerability 0.15                  未开大钉 false 比等；开大钉
                               hit_condition ultimate（鼎阵结界 3 回合——承伤区        true 比等（终结技自吃 0.15+
                               scoped 补口首实例）                                   0.15，普攻不吃结界件——类型
                                                                                     限定双方同值）
ehrToAtkBoost（true）          **待收**（1218102 命中转攻 floor/cap 槽缺 fixture       行迹 EHR 0.28<0.80 双方同灭；
                               在案）；对方 dynamic conversion min(2.40,              注入 EHR 1.28 钉 R-JQ2（对方
                               0.60×floor((EHR−0.80)/0.15))×baseATK                  +1.8×baseATK——差恰为 ATK
                                                                                     ×2.8）
e1DmgBoost/e2Dot/e6ResShred    E1 易伤 ×1.4 读法（对方 BOOST 0.40 FullTeam            E0 钉 true 无害（E1 双方读法
                               =读法差存目）/E2/E6（E0 门控同灭）                      差另案；E2 灼烧 ×4/E6 全抗
                                                                                     E0 同灭）
（无开关）灼烧跳伤 1.8          ASHEN_BURN on_turn_start deal_damage（含期望暴击        对方 standardDot 无暴击区——
                               承载——R-SV1/R-KF3 同族在案）                          钉 R-JQ1（差恰为 1/1.025；
                                                                                     dotBaseChance 1.0×(1+EHR
                                                                                     0.28) 截 1.0 权重中性）
（无开关）Pyre Cleanse 进战     on_battle_start gain_energy 15                        开局 15 能对账
  15 能
（无开关）行迹属性节点 EHR     fixture trace_stat_effects 已回填（B-TR④）             EHR 0.28/火 0.144/spd+5——
  0.28/火 0.144/spd+5                                                                增伤池 1.144/spd 103 双方
                                                                                     同值（EHR 不伤直伤）

===========================================================================
飞霄 1220 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
weaknessBrokenUlt（true）      终结技 6 子击逐击切换（broken_of 现场读——                未击破场钉 false 比等（0.9 区
                               122008/122009 lv10 同值 0.6+0.3=0.9）；对方             双方同值）；真击破场钉 true
                               initialize 翻 config.enemyWeaknessBroken=true         比等（1.0 区双方同值——R-FX1
                               （driver ③ 镜像在案）                                 同比）
talentDmgBuff（true）          FEIXIAO_TALENT_DMG all_dmg 0.6（天赋 FUA/战技           首发钉 false 比等；FUA/战技
                               钩同钩后挂——本发不吃 e2e 时序钉）                     后钉 true 比等（增伤池 1.6
                                                                                     双方同值）
skillAtkBuff（true）           FEIXIAO_BOLTCATCH atk_pct 0.48（大行迹战技后挂          未开战技钉 false 比等；开后
                               3 回合——同钩后挂本发不吃）                            钉 true 比等（ATK 1058.68224
                                                                                     双方同值）
e1OriginalDmgBoost/e4Buffs     E1/E4/E6（E0 门控同灭；E1 我方逐段递增 ×1.0→1.5         E0 钉 true 无害（E1 读法差
  /e6Buffs                     vs 对方 multiplicative FINAL_DMG ×1.3071=读法差        另案）
                               存目）
（无开关）Formshift FUA         **待收**（fixture 头注——scoped follow_up 通道可收      **R-FX1 全 FUA/终结技段**：
  暴伤+36%                     未收+终结技伤害视为追加攻击身份改写）；对方 CD            对方 crit 区 1.1462（CD 0.86）
                               0.36 damageType FUA 常驻+终结技 damageType            vs 我方 1.085——差恰为
                               ULT|FUA（双吃）                                       1.1462/1.085≈1.056406
（无开关）飞黄计数/开大扣 6     flying_aureus（我方攻击 +0.5+计数槽；终结技              资源账逐项对账
                               122003 排除；扣 6——全清或扣 6 按扣 6 在案）
（无开关）行迹属性节点 攻击     fixture trace_stat_effects 已回填（B-TR④）             攻 0.28/暴击 0.12/防御 0.125——
  0.28/暴击 0.12/防御 0.125                                                          ATK 769.95072/CR 0.17 双方
                                                                                     同值

===========================================================================
灵砂 1222 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
beConversion（true）           VERMILION_WAFT stat_exprs（BE 25% 转攻 cap 50%/         钉 true 比等（BE 0.373 档——
                               10% 转治疗量 cap 20%——现场面板 BE 动态）              ATK 810.383805/OHB 0.0373
                                                                                     双方同值；对方 dynamic
                                                                                     conversion SelfAndPet 双落——
                                                                                     浮元段同吃）
befogState（true）             BEFOG vulnerability 0.25 hit_condition break           钉 true 比等（直伤承伤区 1.0
                               （终结技/秘技挂 2 回合——类型限定承伤）                 双方同值——BREAK 过滤同构）
e1DefShred/e2BeBuff/e6ResShred E1/E2/E6（E0 门控同灭）                               E0 钉 true 无害
（无开关）浮元行动 0.75×2       全体 0.75+随机单体 0.75 lv10（stat_of 跨人读灵砂        我方 2 段 vs 对方折叠 1.5 单发
                               有效面板——浮元 inheritance none 不继承）             （sourceEntity Fuyuan pet 面板
                                                                                     镜像）——段数差在案总和三方
                                                                                     全等
（无开关）浮元治疗              浮元钩 heal（**源=浮元**——浮元面板无 heal_bonus       **R-LS1**：对方 talentHeal
                               不加成——源归属在案）                                  （entity 0 灵砂）吃 OHB
                                                                                     0.0373——差恰为 ×1.0373
                                                                                     （真病候选待过堂——官方
                                                                                     「治疗量提高」主体灵砂，
                                                                                     浮元治疗源应归灵砂面板）
（无开关）战技召唤/+3 次/       summon+set _fy_count 3+advance 20%/终结技立即           状态对账（无伤不拍）
  拉条 20%/终结技立即行动       行动+heal 全链（e2e 已全链对轴）
（无开关）余烬回响              受击者 ≤60% 浮元追击不耗次数+2 回合冷却                 **对方无落点**（Lingsha.ts 无
                                                                                     回响建模）——e2e 已拍不重复
（无开关）行迹属性节点 BE      fixture 已回填（B-TR④——BE 0.373 平铺并                BE 0.373/生命 0.18/攻 0.10——
  0.373/生命 0.18/攻 0.10      base_stats——流萤/阮•梅/大丽花平铺同例；                转化后 ATK 810.383805 双方
                               pct 走 trace_stat_effects）                           同值

===========================================================================
大丽花 1321 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
zoneActive（true）             SKILL_ZONE weakness_break_efficiency_boost 0.5         开战技钉 true 比等（超击破
                               team 辐射（战技结界 3 回合）                           有效削韧 ×1.5 双方同值——
                                                                                     我方 WBE 池与对方 BE 池单池
                                                                                     非零下等价；双池乘算结构差
                                                                                     本场不触发在案）
ultDefPen（true）              WILT def_pct −0.18（终结技先挂后结算——本发              未开大钉 false 比等；开大钉
                               自吃）                                                true 比等（defMulti 100/182
                                                                                     双方同值——敌降防/攻击穿透
                                                                                     数值等价）
dancePartner（true）           DANCE_PARTNER_SELF super_break_modifier 0.6            钉 true 比等（转化池 0.6 双方
                               （大丽花自身恒为共舞者——天赋 #5）                     同值；solo 队友位共舞者挂
                                                                                     辅手——本体链不拍）
superBreakDmg（true）          共舞者转化池>0+目标已击破 → 超击破段（我方              未击破场钉 false 比等；真击破
                               _try_super_break was_broken 硬门）+对方                场钉 true 比等（baseUniversal
                               initialize 翻 config.enemyWeaknessBroken=true         1.0 双方同值）——R-DH1/R-DH2
                               （破击那一下 0.9 vs 对方静态已破 1.0=时序差在案，       见下
                               破击发本身不拍）
spdBuff（true）                **待收**（行迹3 weakness_implant 事件通道缺 fixture     钉 false 比等（SPD 不伤伤害
                               在案——SPD+30% 三件套同挂）；对方 SPD_P 0.30            段——面板回显 101 双方同值）
e1Buffs/e2ResPen/e4Vuln        E1/E2/E4/E6（E0 门控同灭）                            E0 钉 true 无害
  /e6BeBuff
（无开关）天赋 FUA 5 段弹射     132104 instances 5 逐段随机（单假人全落 e1）           我方 5 段 vs 对方折叠
                               （0.3/段）                                            0.3×5=1.5 单发——段数差在案
                                                                                     总和三方全等
（无开关）行迹1 BE 分享/        FUNERAL_BE_ENTRY 队友 BE=0.24×自 BE+0.5（solo          solo 场无观察差不拍（对方
  行迹2 每 2 次 FUA 产点       无队友落点）/双钩闩 gain_skill_point（每 2 次 FUA       BUFF 行动=队友链槽未接入）；
                               +1 点）                                              产点逐项对账
（无开关）行迹平铺节点 BE      fixture **前置已并 base_stats**（BE 0.373/RES            无回填差（spd 101=96+5/BE
  0.373/RES 0.18/spd+5         0.18/spd 96+5——生成器同口径：平铺并白值，本波            0.373 双方同值）
                               核毕不动）

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注值，任一侧改动触红）
===========================================================================
R-JQ1 椒丘灼烧跳伤暴击区差（R-SV1/R-KF3 同族——我方 on_turn_start 事件承载
   deal_damage 含期望暴击 ×1.025；对方 standardDot 无暴击区，dotBaseChance
   1.0×(1+EHR 0.28) 截 1.0 权重中性）→ 灼烧跳 对方/我方 恰为 1/1.025
R-JQ2 椒丘 1218102 Hearth Kindle 命中转攻我方待收（floor/cap 转化槽缺 fixture
   在案；对方 dynamic conversion：EHR>0.80 → min(2.40, 0.60×floor((EHR−0.80)/
   0.15))×baseATK）→ 注入 EHR 1.28 场（floor 3 档 +1.8×601.524）对方/我方
   恰为 ATK 1684.2672/601.524 = ×2.8（行迹 EHR 0.28<0.80 常态双方同灭）
R-FX1 飞霄 Formshift 1220102 FUA 暴伤+36% 我方待收（fixture 头注——scoped
   follow_up 通道可收未收+终结技伤害视为追加攻击身份改写连锁）；对方 CD 0.36
   damageType FUA 常驻化+终结技 damageType ULT|FUA 双吃 → FUA/终结技段
   对方/我方 恰为 crit 区 (1+0.17×0.86)/(1+0.17×0.5) = 1.1462/1.085 ≈
   1.056406（普攻/战技不吃 FUA 域双方同值全等）
R-LS1 灵砂浮元治疗源归属差（我方浮元钩 heal 源=浮元——浮元面板无 heal_bonus
   不加成（inheritance none 不继承，源归属 fixture 在案）；对方 talentHeal
   entity 0 灵砂吃 OHB 0.0373）→ 浮元治疗段 对方/我方 恰为 ×1.0373（官方
   「治疗量提高」主体为灵砂——浮元治疗源应归灵砂面板，列真病候选待过堂）
R-DH1 大丽花 FUA 超击破转化覆盖 vs 加算差（我方窗口件 _FUA_SB_WINDOW 补
   #3−#5=1.4 → 池 0.6+1.4=2.0 覆盖——官方 EN「converted into 1 instance of
   Super Break DMG **at #3[i]%**」直读+「1 instance」单段语义双证；对方
   panel 池 0.6+hit.extraSuperBreakModifier 2.0=2.6 加算——对方侧疑病存目，
   fixture 待实测⑧同案）→ FUA 超击破段 对方/我方 恰为 ×1.3
R-DH2 大丽花终结技削韧值差（我方米游社对轴 toughness_dmg 20 单源在案；对方
   toughnessDmg 30+fixedToughnessDmg 20=50 无官方源——leak 期数据存目）→
   终结技超击破段有效削韧 对方/我方 恰为 (30×1.5+20)/(20×1.5) = 65/30 =
   13/6 ≈ 2.166667（直伤段削韧不入乘区双方同值全等）

===========================================================================
行迹补收清单（B-TR④，本波回填——官方 character_skill_trees 十节点聚合）
===========================================================================
1314 翡翠：**前置波次已填**（量子 0.224/攻击 0.18/抵抗 0.10——本波复核无需
   回填，e2e 基线绿）。
1221 云璃：攻击 0.28/生命 0.18/暴击 0.067（e2e 重基线 YL_ATK_E×1.28/Z·Z_PARRY
   暴击区 1.0585/1.1755+真式同池 1.58 档，9 例绿）。
1218 椒丘：EHR 0.28/火伤 0.144/速度+5（e2e 重基线 Z_FIRE=增伤池 1.144 七处
   期望，11 例绿；EHR 不伤直伤）。
1220 飞霄：攻击 0.28/暴击 0.12/防御 0.125（e2e 重基线 FX_ATK_E×1.28/Z_FX
   暴击区 1.085+辅手 Z_ALLY 拆区——官方十节点无暴伤/风伤/速度节点，fixture
   旧注猜测节点集同步勘正，11 例绿）。
1222 灵砂：BE 0.373 平铺并 base_stats（流萤/阮•梅/大丽花同例）+生命 0.18/
   攻击 0.10 走 trace_stat_effects（e2e 重基线 LS_ATK_E=×(1.10+转化 0.09325)
   +治疗段源归属拆账——灵砂源 ×1.0373/浮元源不加成，10 例绿）。
1321 大丽花：**前置已并 base_stats**（BE 0.373/RES 0.18/spd 96+5——生成器
   同口径核毕不动，e2e 基线绿）。

===========================================================================
覆盖清单（全名册收官——已拍角色全绿后名册无遗漏）
===========================================================================
已拍 6（本波）：1314 翡翠 / 1221 云璃 / 1218 椒丘 / 1220 飞霄 / 1222 灵砂 /
1321 大丽花。对方侧名册至此全拍（1102 希儿 stub 壳与 9999xx 测试假人不拍
——前几波已注）。
真病清单（本波钓出——单列）：
R-LS1【待过堂】灵砂浮元治疗源归属（浮元钩 heal 源=浮元不吃灵砂 heal_bonus
   ——对方 talentHeal entity 0 吃 OHB 0.0373 锚+官方「治疗量提高」主体灵砂
   双证；修法=浮元治疗钩源归灵砂/浮元继承 heal_bonus——引擎语义连锁非笔误，
   报回待裁决）。
对方侧疑病存目：
R-DH1 大丽花 FUA 超击破 2.6 加算（官方 EN「at #3[i]%」+「1 instance」双证
   覆盖 2.0——我方口径占优）。
R-DH2 大丽花终结技削韧 30+20=50（米游社对轴 20 单源——leak 期数据存目）。
椒丘 E1 BOOST 0.40 加算池（我方/官方 EN「Vulnerability effect increased by
   40%」易伤 ×1.4 读法——E0 同灭另案）。
未完清单：**空（全名册收官）**。
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
    """inline 辅手队友（翡翠收债人/飞霄 FUA 计数/大丽花共舞者驱动用——克拉拉波同模）."""
    return {"actor_id": aid, "name": "辅手", "inline": True,
            "base_stats": {"atk": atk, "spd": 90, "hp": 3000, "max_energy": 100},
            "actions": [{"action_id": f"{aid}_basic", "name": "普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": element,
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}


def _dummy_atk(aid, element, *, hp=1e9):
    """带攻击行动的假人（云璃反击驱动——克拉拉 R-CL1 先例：注入后 actions[0] 必攻）."""
    return _dummy(aid, element, hp=hp)


def _arm_enemy(eng, aid="e1", *, element="physical"):
    """假人注入攻击行动（e2e 先例同模——stage inline 敌无 actions 键，编译后直注）."""
    from hsr_nous.sim_schema.action import Action
    eng.actions_by_actor = {**eng.actions_by_actor, aid: [Action(
        action_id="e_hit", name="重击", action_type="basic", target_type="single",
        damage_type=element, scaling=[{"atk": 1.0}], toughness_dmg=10)]}


def _inc_log(eng):
    """治疗记录仪：on_hp_increase 有序事件流（amount=实回值——记忆战舰波同模）."""
    log = []
    eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: log.append(dict(p)))
    return log


def _fuyuan_act(eng):
    """浮元行动（灵砂 e2e 同模——_execute_action + on_action 发射）."""
    fy = eng.state.actors["1222_fuyuan"]
    a = next(x for x in eng.actions_by_actor["1222_fuyuan"] if x.action_id == "122204")
    eng._execute_action(fy, a)
    eng.bus.emit("on_action", {
        "actor": "1222_fuyuan", "action_type": "follow_up", "action_id": "122204",
        "target_type": "aoe", "target": "e1",
        "actor_type": fy.actor.actor_type}, eng.state)


# ---------------------------------------------------------------------------
# 口径常数（两侧钉死；fixture base_stats 白值 × 行迹聚合）
# ---------------------------------------------------------------------------

# 翡翠 1314（量子；行迹 量子 0.224/攻击 0.18/抵抗 0.10——前置波次已填 fixture）
JD_HP_W, JD_ATK_W, JD_DEF, JD_SPD = 1086.624, 659.736, 509.355, 103
JD_ATK = JD_ATK_W * 1.18                      # 778.48848
JD_QUANTUM = 0.224
JD_CR, JD_CD = 0.05, 0.5


def _jd(mult: float, *, stacks: float = 1.0) -> float:
    """1314 期望伤害：倍率×ATK（攻 1.18+当品 0.005×层）×防御区 0.5×未击破 0.9
    ×期望暴击（CD 0.5+0.024×层）×增伤池（1+量子 0.224）."""
    atk = JD_ATK_W * (1.18 + 0.005 * stacks)
    cd = JD_CD + 0.024 * stacks
    return mult * atk * 0.5 * 0.9 * (1 + JD_CR * cd) * (1 + JD_QUANTUM)


def _opt_jade(action: str, *, cond: dict | None = None):
    c = {"enhancedFollowUp": False, "pawnedAssetStacks": 1,
         "e1FuaDmgBoost": True, "e2CrBuff": True, "e4DefShredBuff": True,
         "e6ResShredBuff": True}
    c.update(cond or {})
    stacks = c["pawnedAssetStacks"]
    return {"kind": "character", "character_id": "1314", "eidolon": 0,
            "action": action, "element": "quantum", "conditionals": c,
            "base": {"atk": JD_ATK_W, "hp": JD_HP_W, "def": JD_DEF, "spd": JD_SPD},
            "attacker": {"atk": JD_ATK, "hp": JD_HP_W, "def": JD_DEF, "spd": JD_SPD,
                         "cr": JD_CR, "cd": JD_CD, "element_boost": JD_QUANTUM},
            "self_path": "Erudition",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 翡翠 1314（对方 1300/Jade.ts 全实现——BASIC/ULT/FUA/BREAK 四行动注册；
# 收债人链对方无建模"skill disabled"在案）——当品叠层+充能追击族
# ===========================================================================

class TestJadeDuipai:
    """翡翠 E0：普攻（当品 1/50 层档）/充能追击 1.2/终结技+强化追击 2.0 三方
    全等（行迹前置已填收官）/收债人附加伤害链对方无落点（我方段 vs 手算）."""

    def test_basic(self, optimizer_driver):
        """普攻主段 0.9 量子（lv6 档；blast 相邻单假人无落点）：开局逆回购①补
        当品 1 层（1 敌——CD 0.524/ATK 781.78716）三方全等；充能 +1 对账."""
        eng, log = _make_logged(_solo_compiled("1314", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1314"]
        assert st.resources["_mortgage"] == 1.0, "逆回购①：开局 1 敌 → 当品 1 层"
        log.clear()
        _cast(eng, "1314", "131401")
        ours = _hit_amounts(log, source="1314")
        theirs = run_optimizer(optimizer_driver, _opt_jade("basic"))

        hand = _jd(0.9)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["atk"] == pytest.approx(
            JD_ATK_W * 1.185, rel=REL_TOL), "对方当品 1 层 ATK 面板回显"
        assert theirs["stats"]["cd"] == pytest.approx(0.524, rel=REL_TOL), (
            "对方当品 1 层 CD 0.524 面板回显")
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("dmgBoostMulti", 1.224)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert st.resources["_charge"] == 1.0, "翡翠攻击命中 1 敌 → 充能 +1"

    def test_goods_full_stacks(self, optimizer_driver):
        """当品 50 层档（钉资源）：CD 1.7/ATK 943.42248（攻 1.18+当品 0.25）双方
        同值三方全等——绝当品 ATK 件与当品 CD 件同链验证."""
        eng, log = _make_logged(_solo_compiled("1314", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1314"]
        st.resources["_mortgage"] = 50.0
        log.clear()
        _cast(eng, "1314", "131401")
        ours = _hit_amounts(log, source="1314")
        theirs = run_optimizer(optimizer_driver, _opt_jade(
            "basic", cond={"pawnedAssetStacks": 50}))

        hand = _jd(0.9, stacks=50.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方满当品普攻 vs 手算"
        assert theirs["stats"]["atk"] == pytest.approx(
            JD_ATK_W * 1.43, rel=REL_TOL), "对方 50 层 ATK 943.42248 面板回显"
        assert theirs["stats"]["cd"] == pytest.approx(1.7, rel=REL_TOL), (
            "对方 50 层 CD 1.7 面板回显")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_fua_unenhanced(self, optimizer_driver):
        """充能 8 阈值发射剔烁之牙 1.2（未武装——_ult_stacks 0）：钉充能 7+普攻
        触发，逐段三方全等；溢出结转/当品 +5/回能对账."""
        eng, log = _make_logged(_solo_compiled("1314", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1314"]
        st.resources["_charge"] = 7.0
        log.clear()
        _cast(eng, "1314", "131401")
        ours = _hit_amounts(log, source="1314")
        theirs = run_optimizer(optimizer_driver, _opt_jade("fua"))

        assert len(ours) == 2, "普攻+追击双段"
        assert ours[0] == pytest.approx(_jd(0.9), rel=REL_TOL), "普攻段 vs 手算"
        assert ours[1] == pytest.approx(_jd(1.2), rel=REL_TOL), "追击段（未强化 1.2）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(_jd(1.2), rel=REL_TOL), (
            "对方追击 vs 手算")
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert st.resources["_charge"] == 0.0, "max(0, 8-8) 结转"
        assert st.resources["_mortgage"] == 6.0, "开局 1+追击 5=6 层当品"
        assert math.isclose(st.current_energy, 20.0 + 10.0), "普攻 20+追击回能 10"
        assert st.resources["_ult_stacks"] == 0.0, "未武装——不耗强化次数"

    def test_ult_and_enhanced_fua(self, optimizer_driver):
        """终结技 2.4 AoE（lv10）+武装 2 次 → 强化追击 1.2+0.8=2.0（倍率区加算
        ——米游社读法双方同构）：三段逐段三方全等；强化次数 2→1 对账."""
        eng, log = _make_logged(_solo_compiled("1314", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1314"]
        log.clear()
        _fire_ult(eng, "1314", "131403", energy=140.0)
        assert st.resources["_ult_stacks"] == 2.0, "终结技武装追击强化 2 次"
        st.resources["_charge"] = 7.0          # 终结技命中 +1 后钉 7（普攻再 +1=8 发射）
        log.clear()
        _cast(eng, "1314", "131401")
        ours = _hit_amounts(log, source="1314")
        theirs_ult = run_optimizer(optimizer_driver, _opt_jade("ult"))
        theirs_fua = run_optimizer(optimizer_driver, _opt_jade(
            "fua", cond={"enhancedFollowUp": True}))

        assert len(ours) == 2, "普攻+强化追击双段"
        assert ours[1] == pytest.approx(_jd(1.2 + 0.8), rel=REL_TOL), (
            "强化追击 2.0（倍率区加算）vs 手算")
        assert theirs_fua["hits"][0]["damage"] == pytest.approx(_jd(2.0), rel=REL_TOL), (
            "对方强化追击（1.2+0.8）vs 手算")
        assert ours[1] == pytest.approx(theirs_fua["hits"][0]["damage"], rel=REL_TOL), (
            "双方互对")
        assert theirs_ult["hits"][0]["damage"] == pytest.approx(_jd(2.4), rel=REL_TOL), (
            "对方终结技 2.4 vs 手算（我方终结技段同值——log 已清另测）")
        assert st.resources["_ult_stacks"] == 1.0, "强化次数 2→1"
        assert math.isclose(st.current_energy, 5.0 + 20.0 + 10.0), "终结技 5+普攻 20+追击 10"

    def test_debtor_additional_chain(self, optimizer_driver):
        """收债人链（对方无落点——Jade.ts "skill disabled" 在案）：战技挂辅手
        收债人（SPD+30/在场闩）→ 辅手普攻触发附加伤害 0.25×翡翠 ATK（category
        additional——不吃追击桶、吃量子/双暴全区）vs 手算；烧血/充能对账."""
        eng, log = _make_logged(_solo_compiled("1314", enemies=_dummy("e1", "quantum"),
                                               extra_members=[_ally()]))
        st = eng.state.actors["1314"]
        ally = eng.state.actors["ally"]
        log.clear()
        _cast(eng, "1314", "131402", target="ally")
        assert "JADE_DEBTOR" in ally.modifiers, "收债人挂辅手"
        assert st.resources["_debtor_on_field"] == 1.0
        eff_spd = eng.pipeline.effective_stats(ally)["spd"]
        assert math.isclose(eff_spd, 90 + 30, rel_tol=1e-9), "收债人 SPD+30（固定值）"
        hp_ally = ally.current_hp
        log.clear()
        _cast(eng, "ally", "ally_basic")
        ours = _hit_amounts(log, source="1314")

        assert len(ours) == 1, "附加伤害单段（category additional——非追击桶）"
        assert ours[0] == pytest.approx(_jd(0.25), rel=REL_TOL), (
            "附加伤害 0.25×翡翠 ATK vs 手算（对方无落点——我方段自证）")
        assert math.isclose(hp_ally - ally.current_hp, 0.02 * 3000), "收债人烧血 2%×Max"
        assert st.resources["_charge"] == 1.0, "收债人命中 1 敌 → 充能 +1（附加伤害出集）"
        assert math.isclose(st.current_energy, 30.0), "战技回能 30"


# 云璃 1221（物理；行迹 攻击 0.28/生命 0.18/暴击 0.067——B-TR④ 已回填 fixture）
YL_HP_W, YL_ATK_W, YL_DEF, YL_SPD = 1358.28, 679.14, 460.845, 94
YL_ATK = YL_ATK_W * 1.28                      # 869.2992
YL_CR, YL_CD = 0.05 + 0.067, 0.5              # 0.117
YL_CZ = 1 + YL_CR * YL_CD                     # 1.0585
YL_CZ_PARRY = 1 + YL_CR * (YL_CD + 1.0)       # 1.1755（Parry 反击暴伤+1.0）


def _yl(mult: float, *, atk: float = YL_ATK, cz: float = YL_CZ) -> float:
    """1221 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0——
    行迹无物理节点）."""
    return mult * atk * 0.5 * 0.9 * cz


def _opt_yunli(action: str, *, cond: dict | None = None):
    c = {"blockActive": False, "ultCull": True, "ultCullHits": 6,
         "counterAtkBuff": False, "e1UltBuff": True, "e2DefShred": True,
         "e4ResBuff": True, "e6Buffs": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1221", "eidolon": 0,
            "action": action, "element": "physical", "conditionals": c,
            "base": {"atk": YL_ATK_W, "hp": YL_HP_W, "def": YL_DEF, "spd": YL_SPD},
            "attacker": {"atk": YL_ATK, "hp": YL_HP_W, "def": YL_DEF, "spd": YL_SPD,
                         "cr": YL_CR, "cd": YL_CD},
            "self_path": "Destruction",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _fire_ult_yunli(eng):
    _fire_ult(eng, "1221", "122103", energy=120.0)
    assert "YUNLI_PARRY" in eng.state.actors["1221"].modifiers


# ===========================================================================
# L2 云璃 1221（对方 1200/Yunli.ts 全实现——BASIC/SKILL/FUA/BREAK 四行动注册，
# FUA 三形态折叠：天赋反击/Cull 6.52/Slash 2.2）——敌方驱动反击+Parry 族
# ===========================================================================

class TestYunliDuipai:
    """云璃 E0：普攻/战技主段三方全等（B-TR④ 收官）/敌方驱动天赋反击（R-CL1
    先例：敌 actions[0] 必攻+solo 唯一目标）/Parry-Cull 段数差在案总和全等/
    兜底 Slash/真式时序钉."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 物理（lv6 档）：行迹攻 0.28/暴击 0.067（fixture B-TR④ 回填）
        三方全等."""
        eng, log = _make_logged(_solo_compiled("1221", enemies=_dummy("e1", "physical")))
        log.clear()
        _cast(eng, "1221", "122101")
        ours = _hit_amounts(log, source="1221")
        theirs = run_optimizer(optimizer_driver, _opt_yunli("basic"))

        hand = _yl(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", YL_CZ), ("dmgBoostMulti", 1.0),
                     ("abilityMulti", YL_ATK)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_skill(self, optimizer_driver):
        """战技主段 1.2（lv10 档；blast 相邻 0.6 单假人无落点）三方全等；自奶钩
        无伤不拍."""
        eng, log = _make_logged(_solo_compiled("1221", enemies=_dummy("e1", "physical")))
        log.clear()
        _cast(eng, "1221", "122102")
        ours = _hit_amounts(log, source="1221")
        theirs = run_optimizer(optimizer_driver, _opt_yunli("skill"))

        hand = _yl(1.2)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方战技 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_talent_counter_chain(self, optimizer_driver):
        """敌方普攻云璃 → 天赋反击 1.2：首发无真式（对方 counterAtkBuff=false
        比等）→ 挂真式 → 次发吃 ATK+30%（攻池 1.58——对方钉 true 比等 ATK
        1073.0412 双方同值）；回能 15 对账."""
        eng, log = _make_logged(_solo_compiled("1221", enemies=_dummy_atk("e1", "physical")))
        _arm_enemy(eng)
        st = eng.state.actors["1221"]
        log.clear()
        _cast(eng, "e1", "e_hit", target="1221")
        _cast(eng, "e1", "e_hit", target="1221")
        ours = _hit_amounts(log, source="1221")
        theirs0 = run_optimizer(optimizer_driver, _opt_yunli("fua"))
        theirs1 = run_optimizer(optimizer_driver, _opt_yunli(
            "fua", cond={"counterAtkBuff": True}))

        assert len(ours) == 2, "两发天赋反击"
        assert ours[0] == pytest.approx(_yl(1.2), rel=REL_TOL), (
            "反击①（真式同钩后挂——本发不吃）vs 手算")
        assert ours[1] == pytest.approx(_yl(1.2, atk=YL_ATK_W * 1.58), rel=REL_TOL), (
            "反击②（真式 atk_pct 0.3 与行迹 0.28 同池 → ×1.58）vs 手算")
        assert ours[0] == pytest.approx(theirs0["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs1["hits"][0]["damage"], rel=REL_TOL)
        assert theirs1["stats"]["atk"] == pytest.approx(YL_ATK_W * 1.58, rel=REL_TOL), (
            "对方真式 ATK 1073.0412 面板回显")
        assert "TRUE_SUNDER_ATK" in st.modifiers, "反击后真式挂上"
        assert math.isclose(st.current_energy, 15.0 * 2), "反击回能 15×2"

    def test_parry_cull(self, optimizer_driver):
        """Parry 中受击 → Cull 主 2.2+追加 6×0.72（我方 7 段逐段自结 vs 对方折叠
        6.52 单发——段数差在案总和三方全等；crit 区 1.1755 双方同值）；摘
        Parry/闩复位对账."""
        eng, log = _make_logged(_solo_compiled("1221", enemies=_dummy_atk("e1", "physical")))
        _arm_enemy(eng)
        st = eng.state.actors["1221"]
        _fire_ult_yunli(eng)
        log.clear()
        _cast(eng, "e1", "e_hit", target="1221")
        ours = _hit_amounts(log, source="1221")
        theirs = run_optimizer(optimizer_driver, _opt_yunli(
            "fua", cond={"blockActive": True}))

        assert len(ours) == 7, "Cull 主段+追加 6 段"
        assert ours[0] == pytest.approx(_yl(2.2, cz=YL_CZ_PARRY), rel=REL_TOL), "主段 vs 手算"
        assert sum(ours) == pytest.approx(
            _yl(2.2 + 6 * 0.72, cz=YL_CZ_PARRY), rel=REL_TOL), "总和 vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(6.52, rel=REL_TOL), (
            "对方折叠 2.2+6×0.72=6.52")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _yl(6.52, cz=YL_CZ_PARRY), rel=REL_TOL), "对方折叠 vs 手算"
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        assert theirs["stats"]["cd"] == pytest.approx(1.5, rel=REL_TOL), (
            "对方 Parry CD 1.5 面板回显")
        assert "YUNLI_PARRY" not in st.modifiers, "Cull 后摘 Parry"
        assert st.resources["_slash_toggle"] == 0.0, "Cull 施放后交替闩复位（下次兜底回 Slash）"

    def test_parry_expire_slash(self, optimizer_driver):
        """兜底：Parry 到期未受击 → Slash 2.2 单发（任一回合结束——敌回合末同
        触发；crit 区 1.1755）三方全等；Fiery Wheel 闩置 1（下次兜底回 Cull）."""
        eng, log = _make_logged(_solo_compiled("1221", enemies=_dummy("e1", "physical")))
        st = eng.state.actors["1221"]
        _fire_ult_yunli(eng)
        log.clear()
        eng.bus.emit("on_turn_end", {"actor": "e1"}, eng.state)
        ours = _hit_amounts(log, source="1221")
        theirs = run_optimizer(optimizer_driver, _opt_yunli(
            "fua", cond={"blockActive": True, "ultCull": False}))

        assert ours == pytest.approx([_yl(2.2, cz=YL_CZ_PARRY)], rel=REL_TOL), (
            "兜底 Slash vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _yl(2.2, cz=YL_CZ_PARRY), rel=REL_TOL), "对方 Slash vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert "YUNLI_PARRY" not in st.modifiers
        assert st.resources["_slash_toggle"] == 1.0, "本次 Slash → 下次兜底回 Cull"


# 椒丘 1218（火；行迹 EHR 0.28/火伤 0.144/速度+5——B-TR④ 已回填 fixture）
JQ_HP_W, JQ_ATK_W, JQ_DEF, JQ_SPD_W = 1358.28, 601.524, 509.355, 98
JQ_ATK = JQ_ATK_W                             # 601.524（行迹无攻击节点）
JQ_SPD = JQ_SPD_W + 5                         # 103
JQ_FIRE = 0.144
JQ_EHR = 0.28
JQ_CZ = 1 + 0.05 * 0.5                        # 1.025


def _jq(mult: float, *, atk: float = JQ_ATK, cz: float = JQ_CZ,
        vuln: float = 0.0) -> float:
    """1218 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池（1+火
    0.144）×承伤区（1+烬煨/结界易伤）."""
    return mult * atk * 0.5 * 0.9 * cz * (1 + JQ_FIRE) * (1 + vuln)


def _opt_jiaoqiu(action: str, *, cond: dict | None = None, ehr: float = JQ_EHR):
    c = {"ashenRoastStacks": 0, "ultFieldActive": False, "ehrToAtkBoost": True,
         "e1DmgBoost": True, "e2Dot": True, "e6ResShred": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1218", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": JQ_ATK_W, "hp": JQ_HP_W, "def": JQ_DEF, "spd": JQ_SPD_W},
            "attacker": {"atk": JQ_ATK, "hp": JQ_HP_W, "def": JQ_DEF, "spd": JQ_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": JQ_FIRE,
                         "effect_hit": ehr},
            "self_path": "Nihility",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 椒丘 1218（对方 1200/Jiaoqiu.ts 全实现——BASIC/SKILL/ULT/DOT/BREAK 五
# 行动注册+dynamic EHR→ATK conversion）——烬煨层数易伤+灼烧 DoT 族
# ===========================================================================

class TestJiaoqiuDuipai:
    """椒丘 E0：普攻/战技主段+烬煨层数逐档三方全等（B-TR④ 收官）/终结技结界
    scoped 易伤/灼烧跳伤 R-JQ1/EHR 转攻 R-JQ2."""

    def test_basic_and_roast_stacks(self, optimizer_driver):
        """普攻 1.0 火（lv6 档）两连发：首发无烬煨（对方 stacks=0 比等）→ 命中
        挂 1 层 → 次发吃易伤 0.15（对方 stacks=1 比等）；灼烧/易伤件挂载对账."""
        eng, log = _make_logged(_solo_compiled("1218", enemies=_dummy("e1", "fire")))
        e1 = eng.state.actors["e1"]
        log.clear()
        _cast(eng, "1218", "121801")
        _cast(eng, "1218", "121801")
        ours = _hit_amounts(log, source="1218")
        theirs0 = run_optimizer(optimizer_driver, _opt_jiaoqiu("basic"))
        theirs1 = run_optimizer(optimizer_driver, _opt_jiaoqiu(
            "basic", cond={"ashenRoastStacks": 1}))

        assert len(ours) == 2, "两发普攻"
        assert ours[0] == pytest.approx(_jq(1.0), rel=REL_TOL), "首发（无烬煨）vs 手算"
        assert ours[1] == pytest.approx(_jq(1.0, vuln=0.15), rel=REL_TOL), (
            "次发（烬煨 1 层易伤 0.15）vs 手算")
        assert ours[0] == pytest.approx(theirs0["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs1["hits"][0]["damage"], rel=REL_TOL)
        assert e1.modifiers["ASHEN_ROAST"].stacks == 2, "两发命中 → 烬煨 2 层"
        assert "ASHEN_BURN" in e1.modifiers and "ASHEN_VULN" in e1.modifiers
        bd = theirs1["hits"][0]["breakdown"]
        assert bd["dmgBoostMulti"] == pytest.approx(1.144, rel=REL_TOL), "行迹火 0.144 回显"
        assert bd["vulnMulti"] == pytest.approx(1.15, rel=REL_TOL), "对方易伤区回显 1.15"

    def test_skill_and_vuln_ramp(self, optimizer_driver):
        """战技主段 1.5（lv10 档；blast 相邻 0.9 单假人无落点）：首发无烬煨 →
        次发吃 0.15；层数驱动 stat_exprs 动态（1 层 0.15 → 2 层 0.20）对账."""
        eng, log = _make_logged(_solo_compiled("1218", enemies=_dummy("e1", "fire")))
        e1 = eng.state.actors["e1"]
        log.clear()
        _cast(eng, "1218", "121802")
        _cast(eng, "1218", "121802")
        ours = _hit_amounts(log, source="1218")
        theirs0 = run_optimizer(optimizer_driver, _opt_jiaoqiu("skill"))
        theirs1 = run_optimizer(optimizer_driver, _opt_jiaoqiu(
            "skill", cond={"ashenRoastStacks": 1}))

        assert ours[0] == pytest.approx(_jq(1.5), rel=REL_TOL), "战技首发 vs 手算"
        assert ours[1] == pytest.approx(_jq(1.5, vuln=0.15), rel=REL_TOL), "战技次发 vs 手算"
        assert ours[0] == pytest.approx(theirs0["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs1["hits"][0]["damage"], rel=REL_TOL)
        assert math.isclose(eng.pipeline.effective_stats(e1).get("vulnerability", 0.0),
                            0.20, rel_tol=1e-9), "2 层易伤 0.20（stat_exprs 动态）"
        theirs2 = run_optimizer(optimizer_driver, _opt_jiaoqiu(
            "basic", cond={"ashenRoastStacks": 2}))
        assert theirs2["hits"][0]["damage"] == pytest.approx(
            _jq(1.0, vuln=0.20), rel=REL_TOL), "对方 2 层档 vs 手算"

    def test_ult_zone_scoped_vuln(self, optimizer_driver):
        """鼎阵结界终伤易伤 scoped：终结技自吃 烬煨 0.15+结界 0.15（对方
        ultFieldActive=true+stacks=1 比等）；普攻不吃结界件（类型限定——2 层
        烬煨 0.20 单方生效）."""
        eng, log = _make_logged(_solo_compiled("1218", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1218"]
        _cast(eng, "1218", "121802")          # 烬煨 1 层（易伤 0.15）
        log.clear()
        _fire_ult(eng, "1218", "121803", energy=100.0)
        _cast(eng, "1218", "121801")          # 普攻 → 2 层烬煨（0.20），结界不计
        ours = _hit_amounts(log, source="1218")
        theirs_ult = run_optimizer(optimizer_driver, _opt_jiaoqiu(
            "ult", cond={"ashenRoastStacks": 1, "ultFieldActive": True}))
        theirs_basic = run_optimizer(optimizer_driver, _opt_jiaoqiu(
            "basic", cond={"ashenRoastStacks": 2, "ultFieldActive": True}))

        assert "ASHEN_ZONE" in st.modifiers, "鼎阵结界挂上"
        assert ours[0] == pytest.approx(_jq(1.0, vuln=0.15 + 0.15), rel=REL_TOL), (
            "终结技（烬煨 0.15+结界 scoped 0.15 自吃）vs 手算")
        assert ours[0] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL), (
            "对方终结技（双易伤）互对")
        assert ours[1] == pytest.approx(_jq(1.0, vuln=0.20), rel=REL_TOL), (
            "普攻（2 层烬煨 0.20——结界 ultimate 限定不吃）vs 手算")
        assert ours[1] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL), (
            "对方普攻（ULT 过滤结界件不落——类型限定同构）互对")

    def test_burn_tick_r_jq1(self, optimizer_driver):
        """R-JQ1：灼烧跳伤 1.8——我方 on_turn_start 事件承载含期望暴击（×1.025
        ——R-SV1/R-KF3 同族在案）vs 对方 standardDot 无暴击区，差恰为 1/1.025
        （dotBaseChance 1.0×(1+EHR 0.28) 截 1.0 权重中性；烬煨 1 层易伤双方
        同值）."""
        eng, log = _make_logged(_solo_compiled("1218", enemies=_dummy("e1", "fire")))
        _cast(eng, "1218", "121802")          # 烬煨 1 层+灼烧挂上
        log.clear()
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        ours = _hit_amounts(log, source="1218")
        theirs = run_optimizer(optimizer_driver, _opt_jiaoqiu(
            "dot", cond={"ashenRoastStacks": 1}))

        hand_ours = _jq(1.8, vuln=0.15)                       # 含期望暴击 1.025
        hand_theirs = 1.8 * JQ_ATK * 0.5 * 0.9 * (1 + JQ_FIRE) * 1.15   # 无暴击区
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方灼烧跳 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方 dot vs 手算")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            1 / JQ_CZ, rel=REL_TOL), "R-JQ1 差恰为 1/1.025（DoT 暴击区差——同族在案）"

    def test_ehr_to_atk_r_jq2(self, optimizer_driver):
        """R-JQ2：1218102 Hearth Kindle 命中转攻我方待收（floor/cap 转化槽缺
        fixture 在案）——注入 EHR 1.28 档：对方 dynamic conversion +1.8×baseATK
        （floor((1.28−0.80)/0.15)=3 档）→ ATK 1684.2672 vs 我方 601.524，差
        恰为 ×2.8；行迹 EHR 0.28<0.80 常态双方同灭."""
        eng, log = _make_logged(_solo_compiled("1218", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1218"]
        eff_ehr = eng.pipeline.effective_stats(st)["effect_hit"]
        assert math.isclose(eff_ehr, JQ_EHR, rel_tol=1e-9), "行迹 EHR 0.28（<0.80 门控不达）"
        log.clear()
        _cast(eng, "1218", "121801")
        ours = _hit_amounts(log, source="1218")
        theirs = run_optimizer(optimizer_driver, _opt_jiaoqiu(
            "basic", ehr=1.28))

        assert ours == pytest.approx([_jq(1.0)], rel=REL_TOL), "我方普攻（转攻待收）vs 手算"
        assert theirs["stats"]["atk"] == pytest.approx(
            JQ_ATK * 2.8, rel=REL_TOL), "对方转化后 ATK 1684.2672 面板回显"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(2.8, rel=REL_TOL), (
            "R-JQ2 差恰为 ATK ×2.8（1218102 命中转攻待收——fixture 在案）")


# 飞霄 1220（风；行迹 攻击 0.28/暴击 0.12/防御 0.125——B-TR④ 已回填 fixture）
FX_HP_W, FX_ATK_W, FX_DEF_W, FX_SPD = 1047.816, 601.524, 388.08, 112
FX_ATK = FX_ATK_W * 1.28                      # 769.95072
FX_DEF = FX_DEF_W * 1.125                     # 436.59
FX_CR, FX_CD = 0.05 + 0.12, 0.5               # 0.17
FX_CZ = 1 + FX_CR * FX_CD                     # 1.085
FX_CZ_FUA = 1 + FX_CR * (FX_CD + 0.36)        # 1.1462（对方 Formshift CD 0.36 FUA 域）


def _fx(mult: float, *, atk: float = FX_ATK, cz: float = FX_CZ, boost: float = 0.0,
        universal: float = 0.9) -> float:
    """1220 期望伤害：倍率×ATK×防御区 0.5×未击破/已击破×期望暴击×增伤池（行迹
    无风伤节点）."""
    return mult * atk * 0.5 * universal * cz * (1 + boost)


def _opt_feixiao(action: str, *, cond: dict | None = None):
    c = {"weaknessBrokenUlt": False, "talentDmgBuff": False, "skillAtkBuff": False,
         "e1OriginalDmgBoost": True, "e4Buffs": True, "e6Buffs": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1220", "eidolon": 0,
            "action": action, "element": "wind", "conditionals": c,
            "base": {"atk": FX_ATK_W, "hp": FX_HP_W, "def": FX_DEF_W, "spd": FX_SPD},
            "attacker": {"atk": FX_ATK, "hp": FX_HP_W, "def": FX_DEF, "spd": FX_SPD,
                         "cr": FX_CR, "cd": FX_CD},
            "self_path": "Hunt",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 飞霄 1220（对方 1200/Feixiao.ts 全实现——BASIC/SKILL/ULT/FUA/BREAK 五
# 行动注册+initialize 翻击破档+Formshift CD 0.36 FUA 域常驻）——飞黄+FUA 链族
# ===========================================================================

class TestFeixiaoDuipai:
    """飞霄 E0：普攻三方全等（B-TR④ 收官）/战技+FUA 双段链（自增伤/Boltcatch
    时序钉）/天赋 FUA 队友驱动/终结技折叠段+击破分支——Formshift CD R-FX1
    贯穿 FUA/终结技段."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 风（lv6 档，无叠层裸发）：行迹攻 0.28/暴击 0.12（fixture
        B-TR④ 回填）三方全等；飞黄 +0.5 对账."""
        eng, log = _make_logged(_solo_compiled("1220", enemies=_dummy("e1", "wind")))
        st = eng.state.actors["1220"]
        assert st.resources["flying_aureus"] == 3.0, "Heavenpath 开战 +3 飞黄"
        log.clear()
        _cast(eng, "1220", "122001")
        ours = _hit_amounts(log, source="1220")
        theirs = run_optimizer(optimizer_driver, _opt_feixiao("basic"))

        hand = _fx(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", FX_CZ), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert st.resources["flying_aureus"] == 3.5, "普攻 +0.5 飞黄"

    def test_skill_fua_chain_r_fx1(self, optimizer_driver):
        """战技 2.0+立即 FUA 1.1（同钩后挂自增伤/Boltcatch——本发双段均不吃）：
        战技段双方同值三方全等；FUA 段 R-FX1（对方 CD 0.36 FUA 域常驻——
        crit 区 1.1462 vs 我方 1.085）；次发吃 0.6 增伤+0.48 攻（对方双钉比等，
        R-FX1 同比）."""
        eng, log = _make_logged(_solo_compiled("1220", enemies=_dummy("e1", "wind")))
        st = eng.state.actors["1220"]
        log.clear()
        _cast(eng, "1220", "122002")
        ours1 = _hit_amounts(log, source="1220")
        theirs_skill0 = run_optimizer(optimizer_driver, _opt_feixiao("skill"))
        theirs_fua0 = run_optimizer(optimizer_driver, _opt_feixiao("fua"))

        assert ours1 == pytest.approx([_fx(2.0), _fx(1.1)], rel=REL_TOL), (
            "首发战技+FUA（双 buff 同钩后挂——本发不吃）vs 手算")
        assert ours1[0] == pytest.approx(theirs_skill0["hits"][0]["damage"], rel=REL_TOL), (
            "战技段双方互对（不吃 FUA 域——全等）")
        assert theirs_fua0["hits"][0]["damage"] / ours1[1] == pytest.approx(
            FX_CZ_FUA / FX_CZ, rel=REL_TOL), (
            "R-FX1：FUA 段 对方/我方 恰为 crit 区 1.1462/1.085（Formshift CD 待收）")
        assert "FEIXIAO_TALENT_DMG" in st.modifiers and "FEIXIAO_BOLTCATCH" in st.modifiers

        log.clear()
        _cast(eng, "1220", "122002")
        ours2 = _hit_amounts(log, source="1220")
        theirs_skill1 = run_optimizer(optimizer_driver, _opt_feixiao(
            "skill", cond={"talentDmgBuff": True, "skillAtkBuff": True}))
        theirs_fua1 = run_optimizer(optimizer_driver, _opt_feixiao(
            "fua", cond={"talentDmgBuff": True, "skillAtkBuff": True}))

        atk_buffed = FX_ATK_W * (1.28 + 0.48)               # 1058.68224
        assert ours2 == pytest.approx(
            [_fx(2.0, atk=atk_buffed, boost=0.6),
             _fx(1.1, atk=atk_buffed, boost=0.6),
             _fx(1.1, atk=atk_buffed, boost=0.6)], rel=REL_TOL), (
            "次发战技+双 FUA（天赋钩快照 1+1>=2 与战技钩并发——自增伤 0.6+Boltcatch "
            "0.48 全程）vs 手算")
        assert ours2[0] == pytest.approx(theirs_skill1["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_fua1["hits"][0]["damage"] / ours2[1] == pytest.approx(
            FX_CZ_FUA / FX_CZ, rel=REL_TOL), "R-FX1 同比（非空池，天赋 FUA 段）"
        assert theirs_fua1["hits"][0]["damage"] / ours2[2] == pytest.approx(
            FX_CZ_FUA / FX_CZ, rel=REL_TOL), "R-FX1 同比（非空池，战技 FUA 段）"
        assert theirs_fua1["stats"]["atk"] == pytest.approx(atk_buffed, rel=REL_TOL), (
            "对方 Boltcatch ATK 1058.68224 面板回显")
        assert math.isclose(st.resources["flying_aureus"], 3.0 + 1.0 + 1.5), (
            "首发 +1.0（本体 0.5+FUA 0.5）+次发 +1.5（本体 0.5+双 FUA 各 0.5——非双记在案）")

    def test_talent_fua_ally_driven_r_fx1(self, optimizer_driver):
        """天赋 FUA 队友驱动：辅手第 2 次攻击触发（快照 off-by-one 在案）1.1——
        首发无自增伤；R-FX1（对方 crit 区 1.1462）钉差；闩/计数/飞黄对账."""
        eng, log = _make_logged(_solo_compiled("1220", enemies=_dummy("e1", "wind"),
                                               extra_members=[_ally(element="wind")]))
        st = eng.state.actors["1220"]
        _cast(eng, "ally", "ally_basic")      # tally 0→1 不触发
        log.clear()
        _cast(eng, "ally", "ally_basic")      # 快照 1+1>=2 触发
        ours = _hit_amounts(log, source="1220")
        theirs = run_optimizer(optimizer_driver, _opt_feixiao("fua"))

        assert ours == pytest.approx([_fx(1.1)], rel=REL_TOL), (
            "天赋 FUA（首发无自增伤）vs 手算")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            FX_CZ_FUA / FX_CZ, rel=REL_TOL), "R-FX1：对方/我方 恰为 1.1462/1.085"
        assert st.resources["_fua_turn_used"] == 1.0, "每回合闩"
        assert math.isclose(st.resources["flying_aureus"], 3.0 + 1.0 + 0.5), (
            "辅手两击各 0.5+FUA 自身 0.5")

    def test_ult_segments_r_fx1(self, optimizer_driver):
        """终结技：6 子击+终结段（未击破 122009 支 lv10 同值 0.9——逐击三元现场
        读）我方 7 段 vs 对方折叠 7.0 单发——段数差在案；R-FX1（对方终结技
        damageType ULT|FUA 同吃 CD 0.36——总和 对方/我方 恰为 1.1462/1.085）；
        飞黄扣 6/效率件挂摘对账."""
        eng, log = _make_logged(_solo_compiled("1220", enemies=_dummy("e1", "wind")))
        st = eng.state.actors["1220"]
        st.resources["flying_aureus"] = 8.0
        log.clear()
        _fire_ult(eng, "1220", "122003")
        ours = _hit_amounts(log, source="1220")
        theirs = run_optimizer(optimizer_driver, _opt_feixiao("ult"))

        assert len(ours) == 7, "6 子击+终结段（对方折叠 7.0 单发——段数差在案）"
        assert ours[:6] == pytest.approx([_fx(0.9)] * 6, rel=REL_TOL), "子击段 vs 手算"
        assert ours[6] == pytest.approx(_fx(1.6), rel=REL_TOL), "终结段 vs 手算"
        assert sum(ours) == pytest.approx(_fx(7.0), rel=REL_TOL), "总和 vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(7.0, rel=REL_TOL), (
            "对方折叠 6×(0.6+0.3)+1.6=7.0")
        assert theirs["hits"][0]["damage"] / sum(ours) == pytest.approx(
            FX_CZ_FUA / FX_CZ, rel=REL_TOL), (
            "R-FX1：终结技总和 对方/我方 恰为 1.1462/1.085（Formshift 双吃域）")
        assert st.resources["flying_aureus"] == 2.0, "扣 6（按扣 6 收在案）"
        assert "FEIXIAO_ULT_EFFICIENCY" not in st.modifiers, "效率件终结段后摘"

    def test_ult_broken_branch_r_fx1(self, optimizer_driver):
        """击破分支：真击破（削韧破 30 档假人）后终结技——子击全程 122008 支
        （lv10 同值 0.9）已击破 1.0 区；对方 weaknessBrokenUlt=true（initialize
        翻档——driver ③ 镜像）折叠 7.0 单发 1.0 区；R-FX1 同比."""
        eng, log = _make_logged(_solo_compiled("1220", enemies=[
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 30, "weakness": ["wind"]}]))
        st = eng.state.actors["1220"]
        e1 = eng.state.actors["e1"]
        e1.toughness = 10.0
        log.clear()
        _cast(eng, "1220", "122001")          # 削 10 → 击破（破击发 0.9 区不拍）
        assert e1.broken, "普攻削 10 ≥10 首发即破"
        st.resources["flying_aureus"] = 8.0
        log.clear()
        _fire_ult(eng, "1220", "122003")
        ours = _hit_amounts(log, source="1220")
        theirs = run_optimizer(optimizer_driver, _opt_feixiao(
            "ult", cond={"weaknessBrokenUlt": True}))

        assert len(ours) == 7, "击破后子击全程 122008 高伤变体（lv10 同值 0.9）"
        assert sum(ours) == pytest.approx(
            _fx(7.0, universal=1.0), rel=REL_TOL), "已击破 1.0 区总和 vs 手算"
        assert theirs["hits"][0]["breakdown"]["baseUniversalMulti"] == pytest.approx(
            1.0, rel=REL_TOL), "对方 initialize 翻档 → baseUniversal 1.0 回显"
        assert theirs["hits"][0]["damage"] / sum(ours) == pytest.approx(
            FX_CZ_FUA / FX_CZ, rel=REL_TOL), "R-FX1 同比（已击破场）"


# 灵砂 1222（火；行迹 BE 0.373 平铺 base_stats/生命 0.18/攻 0.10——B-TR④ 已回填）
LS_HP_W, LS_ATK_W, LS_DEF, LS_SPD = 1358.28, 679.14, 436.59, 98
LS_BE = 0.373
LS_ATK_T = LS_ATK_W * 1.10                    # 747.054（行迹 atk_pct 0.10——对方场景钉死面板值）
LS_ATK = LS_ATK_W * (1.10 + 0.09325)          # 810.383805（+朱殷焚心转化 min(0.25×BE,0.5)）
LS_HEAL_B = 1.0373                            # 朱殷焚心治疗量转化 min(0.10×0.373, 0.2)
LS_CZ = 1 + 0.05 * 0.5                        # 1.025


def _ls(mult: float, *, atk: float = LS_ATK) -> float:
    """1222 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0——
    行迹无火伤节点）."""
    return mult * atk * 0.5 * 0.9 * LS_CZ


def _opt_lingsha(action: str, *, cond: dict | None = None):
    c = {"beConversion": True, "befogState": True, "e1DefShred": True,
         "e2BeBuff": True, "e6ResShred": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1222", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": LS_ATK_W, "hp": LS_HP_W, "def": LS_DEF, "spd": LS_SPD},
            "attacker": {"atk": LS_ATK_T, "hp": LS_HP_W, "def": LS_DEF, "spd": LS_SPD,
                         "cr": 0.05, "cd": 0.5, "be": LS_BE},
            "self_path": "Abundance",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 灵砂 1222（对方 1200/Lingsha.ts 全实现——双实体（Fuyuan pet）+BASIC/
# SKILL/ULT/FUA/BREAK+SKILL_HEAL/ULT_HEAL/FUA_HEAL 八行动注册+dynamic BE→
# ATK/OHB 双 conversion SelfAndPet）——浮元召唤+BE 转换治疗族
# ===========================================================================

class TestLingshaDuipai:
    """灵砂 E0：普攻/战技/终结技直伤三段三方全等（B-TR④ 收官——BE 转化后
    ATK 810.383805 双方同值）/战技·终结技治疗（灵砂源吃 OHB 双方同值）/
    浮元 FUA 折叠段总和全等/浮元治疗 R-LS1."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 火（lv6 档）：行迹 BE 0.373 平铺+攻 0.10（fixture B-TR④
        回填）→ 转化后 ATK 810.383805 双方同值三方全等；回能 30 对账."""
        eng, log = _make_logged(_solo_compiled("1222", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1222"]
        log.clear()
        _cast(eng, "1222", "122201")
        ours = _hit_amounts(log, source="1222")
        theirs = run_optimizer(optimizer_driver, _opt_lingsha("basic"))

        hand = _ls(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["atk"] == pytest.approx(LS_ATK, rel=REL_TOL), (
            "对方 BE 转化后 ATK 810.383805 面板回显（dynamic conversion）")
        assert theirs["stats"]["be"] == pytest.approx(LS_BE, rel=REL_TOL), "对方 BE 0.373 回显"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", LS_CZ), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert math.isclose(st.current_energy, 30.0), "普攻 20+大行迹青烟 10=30"

    def test_skill_damage_and_heal(self, optimizer_driver):
        """战技全体 0.8（lv10）+全体治疗（0.14×ATK+420——灵砂源吃 OHB 0.0373
        双方同值）；召唤浮元+3 次状态对账."""
        eng, log = _make_logged(_solo_compiled("1222", enemies=_dummy("e1", "fire")))
        inc = _inc_log(eng)
        st = eng.state.actors["1222"]
        st.current_hp = 1000.0
        log.clear()
        _cast(eng, "1222", "122202")
        ours = _hit_amounts(log, source="1222")
        theirs = run_optimizer(optimizer_driver, _opt_lingsha("skill"))
        theirs_heal = run_optimizer(optimizer_driver, _opt_lingsha("skill_heal"))

        assert ours == pytest.approx([_ls(0.8)], rel=REL_TOL), "我方战技 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        hand_heal = (0.14 * LS_ATK + 420) * LS_HEAL_B
        heals = {(e["source"], e["target"]): e["amount"] for e in inc
                 if e.get("reason") == "heal"}
        assert heals[("1222", "1222")] == pytest.approx(hand_heal, rel=REL_TOL), (
            "我方战技治疗（灵砂源吃 heal_bonus 0.0373）vs 手算")
        assert theirs_heal["hits"][0]["damage"] == pytest.approx(hand_heal, rel=REL_TOL), (
            "对方 SKILL_HEAL（OHB 0.0373——dynamic conversion）vs 手算")
        assert heals[("1222", "1222")] == pytest.approx(
            theirs_heal["hits"][0]["damage"], rel=REL_TOL), "治疗段双方互对"
        assert "1222_fuyuan" in eng.state.actors, "战技召唤浮元"
        assert st.resources["_fy_count"] == 3.0, "初始行动次数 3"

    def test_ult_damage_heal_befog(self, optimizer_driver):
        """终结技全体 1.5（lv10）+全体治疗（灵砂源吃 OHB）+BEFOG（break scoped
        ——直伤承伤区 1.0 双方同值：对方 VULNERABILITY BREAK 过滤同构）."""
        eng, log = _make_logged(_solo_compiled("1222", enemies=_dummy("e1", "fire")))
        inc = _inc_log(eng)
        st = eng.state.actors["1222"]
        st.current_hp = 1000.0
        log.clear()
        _fire_ult(eng, "1222", "122203", energy=110.0)
        ours = _hit_amounts(log, source="1222")
        theirs = run_optimizer(optimizer_driver, _opt_lingsha("ult"))
        theirs_heal = run_optimizer(optimizer_driver, _opt_lingsha("ult_heal"))

        assert ours == pytest.approx([_ls(1.5)], rel=REL_TOL), "我方终结技 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(
            1.0, rel=REL_TOL), "BEFOG 直伤承伤区 1.0（BREAK 类型过滤——同构不落）"
        m = eng.state.actors["e1"].modifiers["BEFOG"]
        assert m.hit_condition_expr is not None, "BEFOG 是 break scoped 件"
        hand_heal = (0.12 * LS_ATK + 360) * LS_HEAL_B
        heals = {(e["source"], e["target"]): e["amount"] for e in inc
                 if e.get("reason") == "heal"}
        assert heals[("1222", "1222")] == pytest.approx(hand_heal, rel=REL_TOL), (
            "我方终结技治疗 vs 手算")
        assert theirs_heal["hits"][0]["damage"] == pytest.approx(hand_heal, rel=REL_TOL), (
            "对方 ULT_HEAL vs 手算")

    def test_fuyuan_fua(self, optimizer_driver):
        """浮元行动：全体 0.75+随机单体 0.75（我方 2 段 vs 对方折叠 1.5 单发
        sourceEntity Fuyuan——段数差在案总和三方全等；pet 面板镜像双落 BE 转化
        ——浮元 ATK 810.383805 双方同值）；次数账挂忆师对账."""
        eng, log = _make_logged(_solo_compiled("1222", enemies=_dummy("e1", "fire")))
        _cast(eng, "1222", "122202")          # 召唤浮元+3 次
        log.clear()
        _fuyuan_act(eng)
        ours = _hit_amounts(log, source="1222_fuyuan")
        theirs = run_optimizer(optimizer_driver, _opt_lingsha("fua"))

        assert ours == pytest.approx([_ls(0.75), _ls(0.75)], rel=REL_TOL), (
            "全体 0.75+随机单体 0.75（确定化同序首——单假人全落 e1）vs 手算")
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.5, rel=REL_TOL), (
            "对方折叠 0.75×2=1.5")
        assert theirs["hits"][0]["source_entity"] == "Fuyuan", "对方段实体归属 Fuyuan"
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        fy_stats = next(e for e in theirs["entity_stats"] if e["name"] == "Fuyuan")
        assert fy_stats["atk"] == pytest.approx(LS_ATK, rel=REL_TOL), (
            "对方浮元 ATK 810.383805 实体回显（pet 镜像+conversion SelfAndPet 双落）")
        st = eng.state.actors["1222"]
        assert st.resources["_fy_count"] == 2.0, "次数扣在灵砂账（账挂忆师）"

    def test_fuyuan_heal_r_ls1(self, optimizer_driver):
        """R-LS1：浮元治疗源归属差——我方浮元钩 heal 源=浮元（浮元面板无
        heal_bonus 不加成——inheritance none 源归属 fixture 在案）vs 对方
        talentHeal（entity 0 灵砂）吃 OHB 0.0373，差恰为 ×1.0373（官方
        「治疗量提高」主体灵砂——真病候选待过堂）."""
        eng, log = _make_logged(_solo_compiled("1222", enemies=_dummy("e1", "fire")))
        inc = _inc_log(eng)
        _cast(eng, "1222", "122202")
        st = eng.state.actors["1222"]
        st.current_hp = 1000.0
        log.clear()
        _fuyuan_act(eng)
        theirs = run_optimizer(optimizer_driver, _opt_lingsha("fua_heal"))

        hand_ours = 0.12 * LS_ATK + 360                    # 457.2460566（无 heal_bonus）
        heals = {(e["source"], e["target"]): e["amount"] for e in inc
                 if e.get("reason") == "heal"}
        assert heals[("1222_fuyuan", "1222")] == pytest.approx(hand_ours, rel=REL_TOL), (
            "我方浮元治疗（源=浮元——不吃灵砂 heal_bonus）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            hand_ours * LS_HEAL_B, rel=REL_TOL), "对方 talentHeal（吃 OHB 0.0373）vs 手算"
        assert theirs["hits"][0]["damage"] / heals[("1222_fuyuan", "1222")] == pytest.approx(
            LS_HEAL_B, rel=REL_TOL), (
            "R-LS1 差恰为 ×1.0373（浮元治疗源归属——真病候选待过堂）")


# 大丽花 1321（火；行迹平铺已并 base_stats——BE 0.373/RES 0.18/spd 96+5，核毕不动）
DH_HP_W, DH_ATK_W, DH_DEF, DH_SPD = 1086.624, 679.14, 606.375, 101
DH_ATK = DH_ATK_W                             # 679.14（行迹无攻击节点）
DH_BE = 0.373
DH_CZ = 1 + 0.05 * 0.5                        # 1.025
DH_SB_BASE = 376.75533                        # 超击破等级系数（lvl80——B38 同档）


def _dh(mult: float, *, universal: float = 0.9, def_multi: float = 0.5) -> float:
    """1321 期望直伤：倍率×ATK×防御区×未击破/已击破×期望暴击（增伤池 1.0——
    行迹无火伤节点）."""
    return mult * DH_ATK * def_multi * universal * DH_CZ


def _dh_sb(eff_toughness: float, conversion: float, *, def_multi: float = 0.5) -> float:
    """1321 期望超击破：等级系数×有效削韧×(1+BE 0.373)×转化池×防御区×已击破 1.0
    （超击破吃防御区——WILT/DEF_PEN 场同直伤 100/182）."""
    return DH_SB_BASE * eff_toughness * (1 + DH_BE) * conversion * def_multi * 1.0


def _opt_dahlia(action: str, *, cond: dict | None = None):
    c = {"zoneActive": False, "ultDefPen": False, "dancePartner": True,
         "superBreakDmg": False, "spdBuff": False, "e1Buffs": True,
         "e2ResPen": True, "e4Vuln": True, "e6BeBuff": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1321", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": DH_ATK_W, "hp": DH_HP_W, "def": DH_DEF, "spd": DH_SPD},
            "attacker": {"atk": DH_ATK, "hp": DH_HP_W, "def": DH_DEF, "spd": DH_SPD,
                         "cr": 0.05, "cd": 0.5, "be": DH_BE},
            "self_path": "Nihility",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _sb_amounts(log, *, source="1321"):
    """超击破段记录仪（reason=='break' 击破族词表——Firefly 波同模）."""
    return [e["amount"] for e in log
            if e.get("reason") == "break" and e.get("source") == source]


# ===========================================================================
# L2 大丽花 1321（对方 1300/TheDahlia.ts 全实现——BASIC/SKILL/ULT/FUA/BREAK/
# BUFF 六行动注册+actionModifiers 附超击破段+initialize 翻击破档）——共舞者
# 超击破+FUA 弹射族
# ===========================================================================

class TestDahliaDuipai:
    """大丽花 E0：普攻/战技/终结技直伤三方全等（行迹平铺前置收官）/WILT 减防
    自吃/FUA 弹射折叠段总和全等/击破链超击破（结界效率 ×1.5 双方同值）——
    FUA 转化 R-DH1/终结技削韧 R-DH2."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0 火（lv6 档，未击破裸发）：行迹平铺 BE 0.373/spd 101 面板
        双方同值三方全等."""
        eng, log = _make_logged(_solo_compiled("1321", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1321"]
        assert math.isclose(st.current_energy, 35.0), "天赋入战回能 35"
        assert "DANCE_PARTNER_SELF" in st.modifiers, "大丽花自身恒为共舞者"
        log.clear()
        _cast(eng, "1321", "132101")
        ours = _hit_amounts(log, source="1321")
        theirs = run_optimizer(optimizer_driver, _opt_dahlia("basic"))

        hand = _dh(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["be"] == pytest.approx(DH_BE, rel=REL_TOL), "对方 BE 0.373 回显"
        assert theirs["stats"]["spd"] == pytest.approx(101.0, rel=REL_TOL), (
            "对方 spd 101=96+5（spdBuff=false——行迹3 待收钉灭）面板回显")
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", DH_CZ), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_skill_and_zone(self, optimizer_driver):
        """战技主段 1.6（lv10 档；blast 相邻同倍率单假人无落点）+结界挂上——
        对方 zoneActive=true（效率件不伤直伤）比等."""
        eng, log = _make_logged(_solo_compiled("1321", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1321"]
        log.clear()
        _cast(eng, "1321", "132102")
        ours = _hit_amounts(log, source="1321")
        theirs = run_optimizer(optimizer_driver, _opt_dahlia(
            "skill", cond={"zoneActive": True}))

        assert ours == pytest.approx([_dh(1.6)], rel=REL_TOL), "我方战技 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert "SKILL_ZONE" in st.modifiers, "战技结界挂上（WBE+50% team 辐射）"

    def test_ult_wilt_self_apply(self, optimizer_driver):
        """终结技 3.0（lv10，split even 单怪全额）+WILT 先挂后结算（本发自吃
        减防——def_pct −0.18 → defMulti 100/182；对方 ultDefPen DEF_PEN 0.18
        同区数值等价）三方全等."""
        eng, log = _make_logged(_solo_compiled("1321", enemies=_dummy("e1", "fire")))
        log.clear()
        _fire_ult(eng, "1321", "132103", energy=130.0)
        ours = _hit_amounts(log, source="1321")
        theirs = run_optimizer(optimizer_driver, _opt_dahlia(
            "ult", cond={"ultDefPen": True}))

        hand = _dh(3.0, def_multi=1000 / 1820)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方终结技（WILT 自吃——1000→820 → 1000/1820）vs 手算")
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            100 / 182, rel=REL_TOL), "对方 DEF_PEN 0.18 defMulti 回显"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert "WILT" in eng.state.actors["e1"].modifiers, "WILT 败谢挂上"

    def test_fua_bounce_ally_driven(self, optimizer_driver):
        """天赋 FUA 共舞者驱动（未击破）：辅手（DANCE_PARTNER 绑定）普攻 →
        大丽花 FUA 5 段弹射（单假人全落 e1）——我方 5 段 vs 对方折叠
        0.3×5=1.5 单发（段数差在案总和三方全等）；闩/回能/行迹2 计数对账."""
        eng, log = _make_logged(_solo_compiled("1321", enemies=_dummy("e1", "fire"),
                                               extra_members=[_ally()]))
        st = eng.state.actors["1321"]
        ally = eng.state.actors["ally"]
        assert "DANCE_PARTNER" in ally.modifiers, "开战绑定最高 BE 队友（唯一辅手）"
        log.clear()
        _cast(eng, "ally", "ally_basic")
        ours = _hit_amounts(log, source="1321")
        theirs = run_optimizer(optimizer_driver, _opt_dahlia("fua"))

        assert ours == pytest.approx([_dh(0.3)] * 5, rel=REL_TOL), (
            "FUA 5 段弹射（0.3/段——单假人全落 e1）vs 手算")
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.5, rel=REL_TOL), (
            "对方折叠 0.3×5=1.5")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        assert st.resources["_fua_turns"] == 1.0, "每回合闩"
        assert st.resources["_fua_sp_count"] == 1.0, "行迹2 计数 +1（每 2 次产 1 点）"
        assert math.isclose(st.current_energy, 35.0 + 2.0), "入战 35+FUA 回能 2"

    def test_super_break_chain_broken_r_dh1(self, optimizer_driver):
        """击破链（真击破 30 档假人）：战技破击开结界（破击发 0.9 区不拍——
        对方静态已破档无时序落点在案）→ 普攻直伤 1.0 区+超击破段（有效削韧
        10×1.5=15，转化 0.6——双方同值）→ 辅手驱动 FUA 5 段+5 段超击破
        （有效削韧逐段 3×1.5，转化 2.0 覆盖——对方折叠段 modMulti 0.6+2.0=2.6
        加算——R-DH1：总和 对方/我方 恰为 ×1.3）."""
        eng, log = _make_logged(_solo_compiled("1321", enemies=[
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 30, "weakness": ["fire"]}],
            extra_members=[_ally(element="fire")]))
        st = eng.state.actors["1321"]
        e1 = eng.state.actors["e1"]
        e1.toughness = 10.0
        log.clear()
        _cast(eng, "1321", "132102")          # 削 10 → 击破+结界开（破击发不拍）
        assert e1.broken, "战技削 10 ≥10 首发即破"
        theirs_skill = run_optimizer(optimizer_driver, _opt_dahlia(
            "skill", cond={"zoneActive": True}))
        assert _hit_amounts(log, source="1321")[0] == pytest.approx(
            theirs_skill["hits"][0]["damage"], rel=REL_TOL), (
            "破击发直伤 0.9 区双方同值（对方 superBreakDmg=false 静态未破档）")

        log.clear()
        _cast(eng, "1321", "132101")          # 已击破：直伤 1.0+超击破（10×1.5，0.6）
        ours_hit = _hit_amounts(log, source="1321")
        ours_sb = _sb_amounts(log)
        theirs_basic = run_optimizer(optimizer_driver, _opt_dahlia(
            "basic", cond={"zoneActive": True, "superBreakDmg": True}))

        assert ours_hit == pytest.approx([_dh(1.0, universal=1.0)], rel=REL_TOL), (
            "已击破普攻直伤 1.0 区 vs 手算")
        assert ours_sb == pytest.approx([_dh_sb(15.0, 0.6)], rel=REL_TOL), (
            "我方超击破（有效削韧 10×1.5 结界档，转化池 0.6）vs 手算")
        assert len(theirs_basic["hits"]) == 2, "对方直伤+超击破双发（actionModifiers 附段）"
        assert theirs_basic["hits"][0]["damage"] == pytest.approx(
            ours_hit[0], rel=REL_TOL), "直伤段双方互对"
        assert theirs_basic["hits"][1]["damage"] == pytest.approx(
            ours_sb[0], rel=REL_TOL), "超击破段双方互对（转化 0.6 同值——共舞者双方同档）"

        log.clear()
        _cast(eng, "ally", "ally_basic")      # 共舞者攻击 → FUA 5 段+逐段超击破
        ours_fua = _hit_amounts(log, source="1321")
        ours_fua_sb = _sb_amounts(log)
        theirs_fua = run_optimizer(optimizer_driver, _opt_dahlia(
            "fua", cond={"zoneActive": True, "superBreakDmg": True}))

        assert ours_fua == pytest.approx([_dh(0.3, universal=1.0)] * 5, rel=REL_TOL), (
            "FUA 5 段 1.0 区 vs 手算")
        assert ours_fua_sb == pytest.approx([_dh_sb(4.5, 2.0)] * 5, rel=REL_TOL), (
            "我方逐段超击破（有效削韧 3×1.5，窗口覆盖转化 2.0——官方「at #3[i]%」直读）")
        assert theirs_fua["hits"][1]["damage"] == pytest.approx(
            _dh_sb(22.5, 2.6), rel=REL_TOL), (
            "对方折叠超击破（有效削韧 15×1.5，panel 0.6+extra 2.0=2.6 加算）vs 手算")
        assert theirs_fua["hits"][1]["damage"] / sum(ours_fua_sb) == pytest.approx(
            2.6 / 2.0, rel=REL_TOL), (
            "R-DH1 差恰为 ×1.3（覆盖 2.0 vs 加算 2.6——官方 EN 直读占优，对方侧疑病存目）")

    def test_ult_super_break_r_dh2(self, optimizer_driver):
        """R-DH2：终结技超击破削韧值差——我方米游社对轴 toughness_dmg 20
        （有效削韧 20×1.5=30）vs 对方 toughnessDmg 30+fixedToughnessDmg 20
        （有效削韧 30×1.5+20=65——无官方源 leak 期存目），差恰为 65/30=13/6；
        直伤段（WILT 自吃 100/182、1.0 区）双方同值全等."""
        eng, log = _make_logged(_solo_compiled("1321", enemies=[
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 30, "weakness": ["fire"]}]))
        st = eng.state.actors["1321"]
        e1 = eng.state.actors["e1"]
        e1.toughness = 10.0
        _cast(eng, "1321", "132102")          # 破击+结界开
        assert e1.broken
        log.clear()
        _fire_ult(eng, "1321", "132103", energy=130.0)
        ours_hit = _hit_amounts(log, source="1321")
        ours_sb = _sb_amounts(log)
        theirs = run_optimizer(optimizer_driver, _opt_dahlia(
            "ult", cond={"zoneActive": True, "ultDefPen": True, "superBreakDmg": True}))

        hand_direct = _dh(3.0, universal=1.0, def_multi=1000 / 1820)
        assert ours_hit == pytest.approx([hand_direct], rel=REL_TOL), (
            "我方终结技直伤（WILT 自吃+1.0 区）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_direct, rel=REL_TOL), (
            "对方直伤段 vs 手算（DEF_PEN 0.18 同区等价）")
        assert ours_sb == pytest.approx(
            [_dh_sb(30.0, 0.6, def_multi=1000 / 1820)], rel=REL_TOL), (
            "我方终结技超击破（有效削韧 20×1.5=30，转化 0.6——WILT 同吃防御区）vs 手算")
        assert theirs["hits"][1]["damage"] == pytest.approx(
            _dh_sb(65.0, 0.6, def_multi=1000 / 1820), rel=REL_TOL), (
            "对方终结技超击破（有效削韧 30×1.5+20=65——30+20 双列；DEF_PEN 同区）vs 手算")
        assert theirs["hits"][1]["damage"] / ours_sb[0] == pytest.approx(
            65.0 / 30.0, rel=REL_TOL), (
            "R-DH2 差恰为 65/30=13/6（终结技削韧值差——米游社对轴 20 vs 对方 30+20）")
