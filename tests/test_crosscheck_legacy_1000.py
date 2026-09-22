"""L2 角色级对拍（BACKLOG B22 名册扩拍第六波）：老角色批量扫荡① 1000-1100 号段——
娜塔莎 1105（物理/丰饶，basic-only 治疗族）/ 白露 1211（雷/丰饶，basic-only 治疗族）/
佩拉 1106（冰/虚无，驱散+减防 debuff 族）/ 杰帕德 1104（冰/存护，Grit 防转攻族）/
希露瓦 1103（雷/智识，触电+天赋附加族）/ 阿兰 1008（雷/毁灭，失 HP 增伤族）/
艾丝妲 1009（火/同谐，弹射+蓄能叠层族）/ 虎克 1109（火/毁灭，强化战技+灼烧天赋族）/
布洛妮娅 1101（风/同谐，增益辅助族——伤害仅普攻）/ 姬子 1003（火/智识，Charge
追击族——≠姬子•启行 1510，SP 消歧在案）/ 瓦尔特 1004（虚数/虚无，B1 加强版弹射+
失重族）/ 银狼 1006（量子/虚无，B1 加强版 debuff 族）/ 桑博 1108（风/虚无，弹射+
风化 DoT 族）/ 卢卡 1111（物理/虚无，战意循环+裂伤引爆族）。逐段伤害 ==
hsr-optimizer 角色实现整链伤害（rel_tol 1e-4；双锚=对方+手算，对不上的按惯例钉
结构差数值自证）。

任务候选清单 ID 勘正在案：候选表「1010 桑博/1011 娜塔莎/1012 佩拉/1014 卢卡/1105
克拉拉/1106 虎克/1107 停云/1108 素裳/1109 青雀/1110 彦卿/1111 白露」与官方 ID 不符
（官方：桑博 1108/娜塔莎 1105/佩拉 1106/卢卡 1111/克拉拉 1107/虎克 1109/停云 1202/
素裳 1206/青雀 1201/彦卿 1209/白露 1211）——本波一律按官方 ID 拍（fixture 文件名即
官方 ID，对方目录同）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character"（技种注册法——本波
新增 dot 技种（希露瓦/艾丝妲/虎克/姬子/桑博/卢卡触电·灼烧·风化·裂伤跳段）；
CHARACTER_REGISTRY +14 import +14 登记——B1 加强版套件按对方 id 直呼
（1004b1/1006b1——我方 fixture=现役加强版，1006 单轨 11006xx 先例））。我方路径：
真模板（tests/fixtures 人工根）→ 编译 → CombatEngine 钉资源/血量/回合开始 →
_cast/_fire_ultimate → bus on_hp_decrease 逐段记录仪（setup 前订阅，L2 先例）。

统一口径（两侧一致，沿用前几波）：星魂钉死 E0、行迹满级（普攻 lv6/技能·终结技·天赋
lv10）、无光锥无遗器、假人 lvl80 def 1000（防御区 0.5——减防件另算）、匹配弱点
（抗性区 1.0）、未击破 0.9、期望暴击 1+cr·cd。

===========================================================================
娜塔莎 1105 buff 状态映射表（对方 content 开关 ↔ 我方模板触发）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
（无——content 空表）           ——                                            ——
（无开关）行迹 Healer OHB+0.10   trace_stat_effects heal_bonus 0.10           双方常驻同值（不伤普攻）
（无开关）战技/终结技治疗段      110502/110503 治疗（非伤害行动）               治疗链非本对拍口径不拍
E6 普攻 HP 倍率附加段           E6 医者仁心（E0 门控同灭）                     E0 不出

===========================================================================
白露 1211 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
healingMaxHpBuff（true）       A2 岐黄要论（治疗溢出 Max HP+10%——我方事件      对方常开折叠近似：面板 hp
                               触发件，solo 无治疗不发）                      回显 ×1.1 在案；不伤普攻
talentDmgReductionBuff（true） 生息减伤 10%（受击侧—— outgoing 无伤）          钉 true 无害
e2UltHealingBuff（true）       E2（E0 门控同灭，OHB 不伤普攻）                 E0 钉 true 无害
e4SkillHealingDmgBuffStacks 0-3（0）  E4（E0 门控同灭）                        E0 钉 0
（无开关）战技/终结技/天赋治疗段 121102/121103/121104 治疗（非伤害行动）        治疗链不拍

===========================================================================
佩拉 1106 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
teamEhrBuff（true）            大行迹 1106102 全队 EHR+10% 常驻                双方常驻同值（不伤）
enemyDebuffed（true）          大行迹 Bash 1106101 对负面目标 +20%——真伤压缩    未减益钉 false；终结技后
                               承载（0.2×原伤 category true——乘算 ×1.2，空     钉 true 钉 R-PL1（乘算 vs
                               增伤池≡+0.2 加算、非空池不等价在案）             加算结构差，见下）
skillRemovedBuff（false）      大行迹 Wipe Out 1106103 战技后下次攻击 +20%     战技本发钉 false（钩在伤
                                                                            后挂——本发不吃双方同构）；
                                                                            后续普攻钉 true 比等
ultDefPenDebuff（true）        终结技 PELA_EXPOSED def_pct −0.4（先挂后伤      ≡DEF_PEN 0.4 同值（L1
                                                                            先例）——本发双方同吃
e4SkillResShred（true）        E4（E0 门控同灭；我方 E4 待收在案=死键摘除）     E0 钉 true 无害
（无开关）行迹属性节点 atk+18%/冰伤+22.4%   fixture trace_stat_effects 已回填      R-TR1 收官（B-TR①——见下）

===========================================================================
杰帕德 1104 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
e4TeamResBuff（true）          E4（E0 门控同灭）                               E0 钉 true 无害
（无开关）行迹 Grit 防转攻      1104103 on_turn_start 钩 atk += 0.35×当前 DEF   我方发 on_turn_start 后比等
                               （stat_exprs 活读）；对方 dynamic conversion   （fixture 行迹 def_pct 回填后两侧
                               常开（GepardConversionConditional）            同值 801.1729687）
（无开关）终结技永屹之壁        110403 全队护盾（非伤害行动）                    护盾链不拍（对方
                                                                            ULT_SHIELD 技种未注册 driver）
（无开关）行迹属性节点 def+12.5%/冰伤+22.4%  fixture trace_stat_effects 已回填   R-TR1 收官（B-TR①——def 经 Grit
                                                                            0.35×放大进 ATK 双方同值 801.1729687）

===========================================================================
希露瓦 1103 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
targetShocked（true）          天赋 110304 燃情和弦（自身行动后对全体触电者    未触电钉 false 比等；战技
                               0.72——hook 独立段）；对方折叠 standardAdditional  上触电后钉 true 逐段比等
                               段进同发                                      （折叠 vs 独立段序一致）
enemyDefeatedBuff（true）      行迹 Mania 1103103 击杀 ATK+20%                 无击杀钉 false 比等
E6（无独立开关，e<6 门控）      E6 触电命中 +30% 真伤段（E0 门控同灭）           E0 不出
（无开关）战技 blast 相邻段     scaling_blast 0.6（单假人无相邻落点）           对方只建主目标单发=建模
                                                                            收敛（黄泉 D6 先例）
（无开关）触电 DoT 跳伤 1.04    SHOCK_SKILL 声明式 dot 通道跳伤——不暴击+      对方 standardDot 无暴击区
                               施加时刻快照+EHR 命中区截 1.0 中性                ——R-SV1 已收官（见下）
（无开关）行迹属性节点 暴击+18.7%  fixture trace_stat_effects 已回填              R-TR1 收官（B-TR①——见下）

===========================================================================
阿兰 1008 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
selfCurrentHpPercent 0.01-1（1.00）  天赋 100804 至痛至怒 stat_exprs 活读       满血双方 0 比等；50% 钉
                               all_dmg = 0.72×失 HP 比（线性——社区 KQM/        0.5 钉 R-AR1 读法差（见下）
                               starguide 佐证在案）；对方 min(0.72, 失HP) 1:1 截断读
E1/E6（e 门控）                E1 战技增伤/E6 终结技增伤（E0 门控同灭）          E0 不出
（无开关）战技耗血 15%          on_action drain_hp（伤后扣——本发不吃）          血量对账
（无开关）终结技 blast 相邻段   scaling_blast 1.6（单假人无相邻落点）           对方只建主目标单发=建模收敛
（无开关）行迹属性节点 atk+28%  fixture trace_stat_effects 已回填                 R-TR1 收官（B-TR①——见下）

===========================================================================
艾丝妲 1009 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
talentBuffStacks 0-5（5）      天赋 100904 蓄能（命中 1 层/次，atk+14%/层       开局钉 0 比等；战技后 5 层
                               全队+def+6%/层自身——重烘焙双件）                钉 5 普攻比等；战技段内
                                                                            叠层=R-AS1（见下）
ultSpdBuff（true）             终结技 100903 全队 SPD+50（不伤）               钉 false 保面板干净
fireDmgBoost（true）           行迹 1009104 Ignite 全队火伤+18% 常驻            双方常驻同值比等
（无开关）战技弹射 5 段         主段 0.5 + hook 4 随机段（expected 取首全落     对方 enemyCount=1 聚合单发
                               e1）=2.5                                      2.5——段数差在案总和对拍
（无开关）普攻灼烧 80%          ASTA_BURN 声明式 dot 通道施加（恒挂，            对方 dotBaseChance 0.8 同值
                               dot_base_chance 0.8 期望权重）→ 跳 0.5——        ——跳伤=R-AS2 已收官（见下）
                               不暴击+施加时刻快照
（无开关）终结技 SPD 增益       100903 无伤段（对方 AstaAbilities 无 ULT 注册）  双方无伤段一致不拍
（无开关）行迹属性节点 火伤+22.4%/暴击+6.7%  fixture trace_stat_effects 已回填    R-TR1 收官（B-TR①——见下）

===========================================================================
虎克 1109 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
enhancedSkill（true）          110902↔110909 available_if 互斥（_enhanced_skill  常态钉 false；终结技后钉
                               闩——终结技授 1、110909 消费归 0）               true 比等
targetBurned（true）           天赋 110904 攻击灼烧目标追加 1.0+回能 5          未灼烧/挂上灼烧的本发钉
                               （on_hp_decrease 钩——灼烧伤后挂载，本发不吃；   false（双方同构——官方挂
                               后续攻击逐段触发；lock 防递归声明序）            烫后发序）；已灼烧钉 true
                                                                            逐段比等
E1/E6（e 门控）                E1 强化战技增伤/E6 灼烧增伤（E0 门控同灭；我方   E0 不出（E6 per-target 条件
                               E6 待收在案=通道缺）                            增伤槽缺在案）
（无开关）灼烧 DoT 跳伤 0.65    HOOK_BURN 声明式 dot 通道跳伤——不暴击+      对方 standardDot 无暴击区
                               施加时刻快照（dot_base_chance 1.0 中性）        ——R-HK1 已收官（见下）
（无开关）行迹属性节点 atk+28%/暴伤+13.3%  fixture trace_stat_effects 已回填     R-TR1 收官（B-TR①）

===========================================================================
布洛妮娅 1101 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
teamDmgBuff（true）            大行迹 1101103 Military Might 全队增伤 10% 光环   双方常驻同值比等
skillBuff（true）              战技 110102 单体增伤 0.66（ally_single——solo    钉 false（对方 SingleTarget
                               布洛妮娅伤害链不吃自身增益为口径主战场）          落点 driver 单实体场不挂）
ultBuff（true）                终结技 110103 全队 ATK+55%/暴伤 0.16×自身暴伤    未开大钉 false；开大后钉
                               +0.2（快照基数在案）                            true 比等（暴伤链双方同值
                                                                            1.0584——对方 base 0.2+
                                                                            dynamic 0.16×0.74 同构）
battleStartDefBuff（false）    大行迹 1101102 开战 DEF+20%（不伤）              钉 false 保面板干净
techniqueBuff（false）         秘技 ATK+15%（未装填）                           钉 false
e2SkillSpdBuff（false）        E2（E0 门控同灭）                               E0 钉 false
（无开关）大行迹 Command 普攻必暴  **待收**（hit_condition accept 词表只收       对方 damageType BASIC 过滤
                               dmg_*/all_dmg——crit_* 不在命中域）              CR+1.0 常开——R-BR1 结构差
（无开关）战技作战再部署         110102 拉条+增伤（非伤害行动；对方                 双方无伤段一致不拍
                               BronyaAbilities 无 SKILL 注册）
（无开关）E4 奇袭 FUA           E4（我方整件待收=风弱点谓词缺在案；对方 e<4     E0 双方空段一致（hits==[]
                               空段）                                        同钉）
（无开关）行迹属性节点 风伤+22.4%/暴伤+24%  fixture trace_stat_effects 已回填    R-TR1 收官（B-TR①）

===========================================================================
姬子 1003 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
targetBurned（true）           大行迹「熔核」战技对灼烧 +20%——**待收**（前置     钉 false 比等（星火/熔核
                               「星火」灼烧基础概率通道缺，双件不下树在案）      我方待收，无挂载对象）
selfCurrentHp80Percent（true） 大行迹「基准」HP≥80% 暴击+15%（enable_if 门控    满血钉 true 比等（双方常驻
                               ——已收）                                       同值 cr 0.2）
e1TalentSpdBuff（false）       E1（E0 门控同灭）                               E0 钉 false
e2EnemyHp50DmgBoost（true）    E2（E0 门控同灭）                               E0 钉 true 无害
e6UltExtraHits 0-2（2）        E6（E0 门控同灭）                               E0 钉 2 无害
（无开关）天赋 Charge 追击      charge 3（开战 1+击破 1）满层任一攻击 trigger    钉资源满层后普攻带发比等
                               100304 AoE 1.4（对方 FUA 静态行动）
（无开关）星火灼烧 DoT 0.3      **待收**（基础概率施加通道缺——我方无段）        对方 dot 段（×0.5 期望权
                                                                            重）vs 手算钉 R-HM1，我方
                                                                            无对应段在案
（无开关）战技 blast 相邻段     scaling_blast 0.8（单假人无相邻落点）           对方只建主目标单发=建模收敛
（无开关）行迹属性节点 atk+18%/火伤+22.4%  fixture trace_stat_effects 已回填     R-TR1 收官（B-TR①）

===========================================================================
瓦尔特 1004（B1 加强版套件）buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
enemySlowed（true）            天赋 1100404 攻击已减速目标追加 1.0——虚数附加段   常态钉 false 比等；钉 true 逐段比等
                               （B-WT① 换绑：category additional 全乘区+          （B-WT① 收官：乘区差消灭——见下；
                               _tw_proc 独立防递归闩——旧 category true           段数口径在案：我方逐 hit 触发
                               跳乘区+同键防递归退役）                            （含审判/弹射段），对方按行动折叠
                                                                                basic×1/skill×5/ult×2——官方逐 hit
                                                                                泛指待实测）
enemyWeightless（true）        终结技 WELT_WEIGHTLESS def_pct −0.4（apply_      未开大钉 false；开大后钉
                               modifiers 先挂后伤——本发双方同吃）              true 比等（≡DEF_PEN 0.4）
retributionDmgStacks 0-10（10） 大行迹 11004101 主件（攻击失重目标 +10%/层）     钉 0 比等；钉 10 钉 R-WT1
                               ——**待收**（方向勘正：官方 their=攻击方，        （增伤池 +1.0）
                               目标条件增伤通道缺在案）
ehrToAtkBoost（true）          大行迹 11004103 EHR>40% 转 ATK（每溢 10%→        EHR 0.28 钉档双方同灭；
                               +20%，上限 80%）——**待收**（转换表达式通道      钉 0.5 钉 R-WT3（对方
                               待证在案）；对方 dynamic conversion             +0.2×base）
traceAdditionalDmg（true）     大行迹 11004102 审判（普攻 +0.8×/战技 +1.2×       钉 true 逐段比等（虚数附加
                               虚数追加段——已收）                              段双方同构）
skillExtraHits 0-4（4）        战技弹射 4 段（主段 0.72+hook 4 随机段——           钉 4 段数差在案总和对拍
                               expected 取首全落 e1）                          （对方聚合 3.6 单发）
e1WeightlessAdditionalDmg（true）/e4/e6  星魂（E0 门控同灭）                    E0 钉 true 无害
（无开关）禁锢延后 12%/失重被击延后  **待收**（行动延后通道未登记——不伤）        双方无伤段一致
（无开关）禁锢/失重减速计天赋     我方天赋判据=自有 WELT_SLOW 单件（通用减速      终结技场钉 enemySlowed=false
                               字段待实测在案——禁锢/失重减速不入）             （对方折叠会带天赋段）
（无开关）行迹属性节点 atk+28%/虚数+28.8%  fixture trace_stat_effects 已回填     R-TR1 收官（B-TR①——EHR+28% 同填：
                                                                            0.28<0.4 双方同灭——只进 R-WT3 钉档）

===========================================================================
银狼 1006（B1 加强版套件）buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
ehrToAtkConversion（true）     大行迹 11006103 Side Note（每 10% EHR→+10%       **已收**（B-SW①——SW_SIDE_NOTE 常驻件
                               ATK，上限 50%——官方 B1 文本核实）               stat_exprs 活读：EHR 0.36 档 +0.3×白值
                                                                            =1191.01752 双方同值）；R-SW3 收官
skillWeaknessResShredDebuff（false）  战技弱点植入全抗削 20%——**待收**（植入     钉 false（本体+双降同挡因
                                     本体同挡因——过堂③ res_pen 挂敌方死键）    在案）
skillResShredDebuff（true）    战技全抗削 13%——**待收**（同上死键摘除在案）     常态钉 false 比等；钉 true
                                                                            钉 R-SW1（抗区 ×1.13）
talentDefShredDebuff（true）   天赋缺陷减防类 12%——**待收**（随机三类无通道     常态钉 false 比等；钉 true
                               ——我方按第 1 类减攻承载，对方按减防类常开       钉 R-SW2（防区 0.5319/0.5）
                               折叠）                                        
ultDefShredDebuff（true）      终结技 SW_DEF_DOWN def_pct −0.45（apply_         钉 true 比等（≡DEF_PEN
                               modifiers 先挂后伤——本发双方同吃）              0.45；官方 B1 AoE 双源
                                                                            核实——过堂②）
targetDebuffs 0-5（5）/e2Vulnerability  E2/E4/E6 计数族（E0 门控同灭；我方      E0 钉 5/无害
                               E1E4E6 同挡因待收——负面计数函数缺）
（无开关）行迹属性节点 atk+56%/量子+16%  fixture trace_stat_effects 已回填       R-TR1 收官（B-TR①——EHR+36% 同填：
                                                                            进旁注转换——B-SW①）

===========================================================================
桑博 1108 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
targetDotTakenDebuff（true）   终结技 SAMPO_DOT_VULN（DoT 易伤 30%——**已收**    直伤场钉 true 无害（对方
                               ——vulnerability+hit_condition dot 承伤            VULNERABILITY damageType
                               scoped 件，2026-09-22 双通道合并兑现）；           DOT 过滤同不伤直伤）；
                               对方 VULNERABILITY damageType DOT 过滤件          跳伤场钉 R-SA2（见下——已收官）
skillExtraHits 1-4（4）        战技弹射 4 段（主段 0.56+hook 4 随机段——           钉 4 段数差在案总和对拍
                               expected 取首全落 e1）                          （对方聚合 2.8 单发）
targetWindShear（true）        大行迹 Spice Up 受击减伤（**待收**——受击侧门控   钉 true 无害（对方 DMG_RED
                               通道缺在案——不伤 outgoing）                     受击侧同不伤）
tickCoefficient 0-100%（20）   DoT 跳伤频次期望权重（对方评分模型槽——直传原值    钉 1（×1.0 裸跳值对拍——
                               作乘数，表单 percent 换算不经场景覆盖）             默认 20=×20 评分档）
（无开关）天赋风化施加          攻击命中 65%  声明式 dot 通道施加（dot_base_    双方同构（dotBaseChance
                               chance 0.65 期望权重 ehr_multi 承载——施加恒挂）  0.65×(1+EHR 0.18)
                                                                                =0.767 期望权重——R-SA1 收官）
（无开关）风化 tick 层数        min(stacks,5)×0.52×ATK（弹射逐段叠层——战技      对方 dot 单层 0.52 摊平
                               后 5 层 tick=2.6；声明式通道 ×stacks 现值）        ——多层差在案（本波单层
                                                                                场对拍）
（无开关）风化 DoT tick 暴击    声明式 dot 通道 tick 不暴击（2026-09-22 双        对方 standardDot 无暴击区
                               通道合并——官方 DoT 不暴击落地）                   ——R-SA1 收官（R-SV1 同族）
（无开关）行迹属性节点 atk+28%  fixture trace_stat_effects 已回填                 R-TR1 收官（B-TR①——EHR+18%/RES 同填
                                                                            不伤）

===========================================================================
卢卡 1111 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
basicEnhanced（true）          111108 强化普攻（战意 ≥2 available_if、耗 2——     常态钉 false；战意 2 层后
                               直冲 3 段 instances+碎天 hook+粉碎 3 段 hook）   钉 true 比等（对方聚合
                                                                            0.2×3+0.8+3×0.2=2.0 单发
                                                                            ——段数差在案总和比等）
basicEnhancedExtraHits 0-3（3） 大行迹粉碎战意（直冲每段 50% 追加 1 段——         钉 3（mechanic_chance
                               mechanic_chance expected 恒中×3）                expected 恒中双方同值）
targetUltDebuffed（true）      终结技 LUKA_VULN vulnerability 0.2 三回合        终结技本发钉 false 比等
                               （on_action 伤后挂——本发不吃）                   （伤后挂双方同构）；后续
                                                                            攻击钉 true 比等；终结技
                                                                            本发钉 true 钉 R-LK3 时序差
e1TargetBleeding/e4TalentStacks  星魂（E0 门控同灭；E4 EN/CN 语义分歧待收在案）  E0 钉 true/4 无害
tickCoefficient 0-5（1）       DoT 频次权重（对方评分模型槽——乘数原值）          钉 1 裸跳值
（无开关）天赋引爆 85%          强化普攻命中裂伤 → 0.85×裂伤值追加段（物理        **对方无引爆段**（tick
                               全乘区——111104 #2）                             频次槽评分吸收）——R-LK1
                                                                            无对方落点我方段 vs 手算钉
（无开关）裂伤 DoT 3.38         min(24% 敌 Max, 338% ATK)——假人 1e9 走上限支    对方 dotScaling=上限支 3.38
                               （角色专属公式——事件承载 tick 含期望暴击）       同值；跳伤暴击区=R-LK2
                                                                            （R-SV1 同族，dotBaseChance
                                                                            1.0 权重中性）
（无开关）行迹面板节点          fixture trace_stat_effects 已回填（B-TR①——官方     R-TR1 收官（atk+28%/EHR/DEF 三
                               character_skill_trees 实测 atk 0.28+EHR 0.18+       节点值回填；EHR/DEF 不伤）
                               DEF 0.125 全收）

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注值，任一侧改动触红）
===========================================================================
R-TR1【已收官 2026-09-17（B-TR①）】老角色 fixture 行迹属性节点批量漏收——修复=
   逐 fixture 回填 trace_stat_effects 官方十节点聚合（本波 _inject 值即官方
   character_skill_trees 聚合，回填后拐杖全删）：佩拉 atk 0.18+冰 0.224+EHR 0.10/
   杰帕德 def 0.125+冰 0.224+RES 0.18/希露瓦 暴击 0.187+EHR 0.18+RES 0.10/
   阿兰 atk 0.28+HP 0.10+RES 0.18/艾丝妲 火 0.224+暴击 0.067+DEF 0.225/
   虎克 atk 0.28+暴伤 0.133+HP 0.18/布洛妮娅 风 0.224+暴伤 0.24+RES 0.10/
   姬子 atk 0.18+火 0.224+RES 0.10/瓦尔特 atk 0.28+虚数 0.288+EHR 0.28+RES 0.20
   （B1 双轨）/银狼 atk 0.56+量子 0.16+EHR 0.36（B1 双轨）/桑博 atk 0.28+EHR 0.18
   +RES 0.10/卢卡 atk 0.28+DEF 0.125+EHR 0.18/娜塔莎 HP 0.28+DEF 0.125+RES 0.18
   （不伤攻击面板）/白露 HP 0.28+DEF 0.225+RES 0.10（同）——原无注入场对方/我方
   差（1.44432/1.1185÷1.025/1.28/(1.0585×1.404)÷(1.025×1.18)/Grit 放大式/
   1.64864 等）全消灭，受影响 e2e 期望已逐一手算核销（各 test_*_template_e2e
   口径常数块在案）；附带引擎补口：开局满血顶到有效上限（hp% 初始件残血进场
   病——src/hsr_nous/sim/engine.py _init_state）
R-PL1 佩拉 Bash 真伤压缩乘算差（我方 0.2×原伤 category true=对全乘区乘算 ×1.2——
   fixture trace_notes ③「DMG% 分桶粒度未接线、真伤压缩口径数值等价、桶归属待实测」
   在案；对方 BOOST+0.2 加算）→ 空增伤池下两侧数值等价（1.0×1.2≡1+0.2），非空池
   （冰 0.224）场 我方/对方 恰为 (1.224×1.2)/1.424 = 1.4688/1.424 ≈ 1.03146
R-SV1【已收官 2026-09-22（DoT 双通道合并）】希露瓦触电跳伤——声明式 dot 通道
   承载（modifier_type dot + dot_element/dot_ratio spec 键，不暴击+施加时刻快照+
   EHR 命中区截 1.0 中性；1005 卡芙卡 R-KF3 同族待迁）→ 触电跳三方全等
   （原差 1/1.1185 消灭——暴击区差随「官方 DoT 不暴击」落地）
R-AS1 艾丝妲天赋段内叠层差（我方逐段命中即时叠层——主段 0 层、弹射段 k 读 k 层，
   战技合计 atk 系数 6.4；对方静态层档 0 档聚合 5×1.0=5.0）→ 0 层开场战技 对方/我方
   恰为 2.5/3.2 = 0.78125；静态 5 层（战技后）普攻双方全等
R-AS2【已收官 2026-09-22（DoT 双通道合并）】艾丝妲灼烧跳伤——声明式 dot 通道
   （dot_base_chance 0.8 期望权重 ehr_multi 承载，施加恒挂）→ 灼烧跳三方全等
   （原差 0.8/1.0585 消灭——暴击区差+挂烫判定分离双因子同灭）
R-AR1 阿兰天赋失 HP 增伤读法差（我方 all_dmg=0.72×失 HP 比 线性——官方「最多提高
   72%」+社区 KQM/starguide 线性读佐证在案；对方 min(0.72, 失 HP 比) 1:1 截断读）
   → 50% HP 场 对方/我方 恰为 1.5/1.36 = 75/68 ≈ 1.1029；满血场双方 0 增伤比等
R-HK1【已收官 2026-09-22（DoT 双通道合并）】虎克灼烧跳伤——声明式 dot 通道
   承载（dot_base_chance 1.0 权重中性）→ 灼烧跳三方全等（原差 1/1.03165 消灭；
   附带语义落定：跳伤 reason='dot' 不再触发天赋附加段——旧 hook 承载经 'hit'
   同通道误触口径退役，官方"attacking"是否含 DoT 待实测项按此承载）
R-BR1 布洛妮娅大行迹 Command 普攻必暴我方待收（hit_condition accept 词表只收
   dmg_*/all_dmg——crit_* 不在命中域，fixture 头注①在案；对方 damageType BASIC
   过滤 CR+1.0 常开——普攻必暴 vs 我方期望暴击）→ 常态普攻 对方暴击区/我方 恰为
   1.74/1.037；终结技暴伤链双方同值后同比（2.0584/1.05292）
R-HM1 姬子星火灼烧 DoT 我方无段（基础概率施加通道缺——熔核同因不下树，fixture
   待收①在案）→ 无我方落点，对方 dot 段（0.3×ATK、×dotBaseChance 0.5 期望权重、
   无暴击区）vs 手算钉
R-WT1 瓦尔特大行迹 11004101 Retribution 主件我方待收（官方 their DMG dealt=攻击方
   ——方向勘正摘除 draft 反挂敌方在案；目标条件增伤通道缺；对方 BOOST+10%/层×10
   常开折叠）→ 失重场钉 10 层 对方/我方 恰为 2.288/1.288 = 1.7770
R-WT2【已收官 2026-09-17（B-WT①）】瓦尔特天赋时空扭曲乘区差——修法（owner 裁决）=
   换普通虚数段+独立防递归：category additional 虚数附加段全乘区（决策卡 #19 正主
   ——吃常规乘区、不吃类型限定增伤、不发受击链）+ _tw_proc 递归闩（1308 _seg_guard/
   本文件 _e1_proc 同族——天赋段分发期间闩=1，天赋自身/减速掷/E1/E2 钩同闩出集），
   旧 category true 真伤平值跳乘区+damage_type!='true' 同键防递归退役——单发天赋段
   双方全等（原差 0.5×0.9×1.025×1.288≈0.5939 消灭）；段数口径差留在案（我方逐 hit
   触发——审判/弹射段各带 1 发；对方按行动折叠 basic×1/skill×5/ult×2——官方逐 hit
   泛指待实测，fixture 头注在案）
R-WT3 瓦尔特大行迹 11004103 EHR>40% 转 ATK 我方待收（转换表达式通道待证在案；
   对方 dynamic conversion 每溢 10%→+20%×base 上限 80%）→ EHR 钉 0.5 场 对方/
   我方 恰为 (794.78784+0.2×620.928)/794.78784 = 1.15625
R-SW1 银狼战技全抗削 13% 我方待收（res_pen 挂敌方=死键摘除在案——过堂③；对方
   RES_PEN 0.13 常开）→ 钉 skillResShredDebuff=true 场 对方/我方 恰为抗区比 1.13
R-SW2 银狼天赋减防类缺陷我方待收（随机三类无通道——我方按第 1 类减攻承载；对方
   按减防类 12% 常开折叠——随机读法双偏在案）→ 钉 talentDefShredDebuff=true 场
   对方/我方 恰为防区比 0.53191/0.5 ≈ 1.06383
R-SW3【已收官 2026-09-17（B-SW①）】银狼大行迹 11006103 Side Note EHR 转 ATK——
   已收：SW_SIDE_NOTE 常驻件 stat_exprs 活读（(ehr+1e-6)×10//1 地板除读档，每 10%
   EHR→+10% ATK 上限 50%，官方 B1 文本 params_max [0.1,0.1,0.5] 复核），EHR 0.36
   档 +0.3×白值 → 面板 1191.01752=640.332×1.86（pct 池 0.56+0.30 加算）双方全等
   （原差 1191.01752/998.91792≈1.19231 消灭）；11006102 Inject 同收（开战 +20 能/
   自身回合开始 +5 能——params_max [20,5]）；trace_notes 旧版 1006102/1006103 注记
   同步改写（旧版 Side Note ≥3 负面全抗 −3% 随 B1 版本更迭退役）
R-SA1【已收官 2026-09-22（DoT 双通道合并）】桑博风化 tick——声明式 dot 通道
   承载（不暴击+施加时刻快照+dot_base_chance 0.65×(1+EHR 0.18)=0.767 期望权重）
   → 风化跳（1 层）三方全等（原差 0.65/1.025 消灭；对方场景同补 EHR 0.18——
   行迹官方值，双方命中区同口径）
R-SA2【已收官 2026-09-22（DoT 双通道合并）】桑博终结技 DoT 易伤——收编
   vulnerability+hit_condition action_type=='dot' 承伤 scoped 件（声明式跳伤
   目标侧现值消费，椒丘结界同构；旧 dot_taken 死键账面件兑现）→ 易伤档跳伤
   三方全等（原差 1.3×0.65/1.025 消灭）
R-LK1 卢卡天赋引爆段对方无落点（我方 0.85×裂伤值追加段——官方「立即产生 1 次
   原流血 85% 伤害」；对方 hits 无引爆段——tickCoefficient 评分槽吸收在案）
   → 我方引爆段 vs 手算钉（物理全乘区 0.85×3.38=2.873×ATK）
R-LK2 卢卡裂伤跳伤暴击区差（R-SV1 同族；dotBaseChance 1.0 权重中性）→
   裂伤跳 对方/我方 恰为 1/1.025
R-LK3 卢卡终结技易伤时序差（我方 on_action 伤后挂——本发不吃；对方常开折叠
   进本发——凛 R-RT2 同族）→ 终结技本发 对方（易伤档）/我方 恰为 1.2；后续
   攻击双方同吃 0.2 比等

===========================================================================
未完清单（下波起始点）
===========================================================================
已拍 14（本波全绿）：1105 娜塔莎 / 1211 白露 / 1106 佩拉 / 1104 杰帕德 / 1103
希露瓦 / 1008 阿兰 / 1009 艾丝妲 / 1109 虎克 / 1101 布洛妮娅 / 1003 姬子 /
1004 瓦尔特（B1）/ 1006 银狼（B1）/ 1108 桑博 / 1111 卢卡。
跳过标注 2：1102 希儿（对方 Seele.ts stub 壳实证——60-140 行无 Scaling/buff 逻辑，
   任务点名跳过；SeeleB1.ts 全实现存目，下波可议）/ 1202 停云（任务「我方 demo
   白板」信息过期在案——fixture 实为打标全机制版 335 行已合入；伤害面=普攻+
   祝福持有者攻击触发天赋附加段，自祝福链可拍，列下波）。
下波候选（按先简后难）：1107 克拉拉（反击 FUA 族——需敌方攻击面驱动）/ 1202
停云（见上——自祝福天赋链）/ 1206 素裳（剑势追加段族）/ 1209 彦卿（智剑连心
双暴族）/ 1201 青雀（麻将 RNG 族——强化普攻/杠上开花确定化钉法先行）/ 1005
卡芙卡 B1（引爆族——任务预警我方引爆待收在案，撞上钉结构差）/ 1112 托帕&账账
（召唤物链——账账伤害挂点按 R-CY3 族先例挂谁侧按谁面板；query 白值 1112 首查
——本波 query 托帕失配在案）。
真病清单（本波钓出——单列，均 fixture 数据层非引擎层）：
B-TR①【已收官 2026-09-17】老角色 fixture 行迹属性节点批量漏收（R-TR1 伞——13/14
   角色 10 个面板受损；1510 勘正③同项）。修复=逐 fixture 回填 trace_stat_effects
   官方十节点聚合（_inject 值即官方 character_skill_trees 聚合——回填后拐杖全删、
   R-TR1 转正式三方相等；受影响角色 e2e 既有期望逐一手算核销——各
   test_*_template_e2e 口径常数块在案）；附带引擎补口一件：开局 current_hp 顶到
   有效上限（hp% 初始件角色残血进场病——阿兰天赋失血比 0.909 误读实证，
   src/hsr_nous/sim/engine.py _init_state）。
B-SW①【已收官 2026-09-17】银狼 fixture 新版大行迹 11006102（入战 +20 能/自身回合
   开始 +5 能——params_max [20,5]）/11006103（每 10% EHR→+10% ATK 上限 50%，
   SW_SIDE_NOTE 常驻件 stat_exprs 活读）已收（R-SW3——trace_notes 旧版注记同步
   改写；官方 B1 文本本波核实在案）。
B-WT①【已收官 2026-09-17】瓦尔特天赋时空扭曲 category true 真伤承载（R-WT2——
   跳乘区平值 vs 官方虚数附加段全乘区；防递归闸同键绑定）已修（owner 裁决）：换
   category additional 虚数段+_tw_proc 独立防递归闩，单发三方全等；段数口径差
   （逐 hit vs 按行动折叠）留在案待实测。
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


def _solo_build(cid, *, eidolon: int = 0):
    member = {"character_template": cid, "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member], "policy": _POLICY}}


def _solo_compiled(cid, *, enemies):
    return compile_encounter(_solo_build(cid), _stage(enemies),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _fire_ult(eng, owner, aid, *, energy=None, target=None):
    """钉资源开大（前几波同模；blast/aoe 单体敌目标经 target 钉选择器）."""
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
    """回合开始事件（杰帕德 Grit/DoT 跳伤族——on_turn_start 钩唯一入口）."""
    eng.bus.emit("on_turn_start", {"actor": actor}, eng.state)


# ---------------------------------------------------------------------------
# 口径常数（两侧钉死；fixture base_stats 白值，行迹聚合按官方 character_skill_trees
# 十节点值——B-TR① 已收官（2026-09-17）：聚合值回填各 fixture trace_stat_effects，
# 本文件 _inject 拐杖全退役）
# ---------------------------------------------------------------------------

# 娜塔莎 1105（物理；行迹节点 HP/DEF/RES 全不伤攻击面板——B-TR① 已回填 fixture）
NA_ATK, NA_HP, NA_DEF, NA_SPD = 476.28, 1164.24, 507.15, 98
NA_CZ = 1 + 0.05 * 0.5                          # 1.025


def _na(mult: float) -> float:
    """1105 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0）."""
    return mult * NA_ATK * 0.5 * 0.9 * NA_CZ


# 白露 1211（雷；行迹节点 HP/DEF/RES 全不伤攻击面板——B-TR① 已回填 fixture）
BL_ATK, BL_HP, BL_DEF, BL_SPD = 562.716, 1319.472, 485.1, 98
BL_CZ = 1 + 0.05 * 0.5                          # 1.025


def _bl(mult: float) -> float:
    """1211 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0）."""
    return mult * BL_ATK * 0.5 * 0.9 * BL_CZ


# 佩拉 1106（冰；行迹 atk 0.18/冰伤 0.224——B-TR① 已回填 fixture）
PL_ATK_W, PL_HP, PL_DEF, PL_SPD = 546.84, 987.84, 463.05, 105
PL_ATK = PL_ATK_W * 1.18                        # 645.2712
PL_ICE = 0.224
PL_CZ = 1 + 0.05 * 0.5                          # 1.025
PL_DEFZ_EXPOSED = 100 / (100 * 0.6 + 100)       # 0.625（终结技减防 0.4）


def _pl(mult: float, *, defz: float = 0.5, boost: float = 0.0) -> float:
    """1106 期望伤害：倍率×ATK×防御区×未击破 0.9×期望暴击×增伤池（1+冰 0.224+附加）."""
    return mult * PL_ATK * defz * 0.9 * PL_CZ * (1 + PL_ICE + boost)


# 杰帕德 1104（冰；行迹 def 0.125/冰伤 0.224——B-TR① 已回填 fixture；Grit 防转攻 0.35）
GP_ATK_W, GP_HP, GP_DEF_W, GP_SPD = 543.312, 1397.088, 654.885, 92
GP_DEF = GP_DEF_W * 1.125                       # 736.745625
GP_GRIT = 0.35 * GP_DEF                         # 257.8609687
GP_ATK = GP_ATK_W + GP_GRIT                     # 801.1729687
GP_ICE = 0.224
GP_CZ = 1 + 0.05 * 0.5                          # 1.025


def _gp(mult: float, *, atk: float = GP_ATK, boost: float = GP_ICE) -> float:
    """1104 期望伤害：倍率×ATK（含 Grit）×防御区 0.5×未击破 0.9×期望暴击×增伤池."""
    return mult * atk * 0.5 * 0.9 * GP_CZ * (1 + boost)


# 希露瓦 1103（雷；行迹 暴击 0.187——B-TR① 已回填 fixture）
SV_ATK, SV_HP, SV_DEF, SV_SPD = 652.68, 917.28, 374.85, 104
SV_CR, SV_CD = 0.05 + 0.187, 0.5                # 0.237
SV_CZ = 1 + SV_CR * SV_CD                       # 1.1185


def _sv(mult: float, *, cz: float = SV_CZ) -> float:
    """1103 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0）."""
    return mult * SV_ATK * 0.5 * 0.9 * cz


# 阿兰 1008（雷；行迹 atk 0.28/hp 0.10——B-TR① 已回填 fixture）
AR_ATK_W, AR_DEF, AR_SPD = 599.76, 330.75, 102
AR_HP = 1199.52 * 1.10                          # 1319.472（行迹 hp_pct 0.10 有效上限——天赋失血比判读基数）
AR_ATK = AR_ATK_W * 1.28                        # 767.6928
AR_CZ = 1 + 0.05 * 0.5                          # 1.025


def _ar(mult: float, *, atk: float = AR_ATK, boost: float = 0.0) -> float:
    """1008 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×增伤池（1+天赋失血档）."""
    return mult * atk * 0.5 * 0.9 * AR_CZ * (1 + boost)


# 艾丝妲 1009（火；行迹 火伤 0.224/暴击 0.067——B-TR① 已回填 fixture；Ignite 火伤 0.18 双方常驻）
AS_ATK, AS_HP, AS_DEF, AS_SPD = 511.56, 1023.12, 463.05, 106
AS_FIRE = 0.224 + 0.18                          # 0.404（行迹节点+Ignite 大行迹）
AS_CR, AS_CD = 0.05 + 0.067, 0.5                # 0.117
AS_CZ = 1 + AS_CR * AS_CD                       # 1.0585
AS_STACK_ATK = 0.14                             # 天赋蓄能每层 atk_pct（lv10）


def _as(mult: float, *, atk_mult: float = 1.0, cz: float = AS_CZ,
        fire: float = AS_FIRE) -> float:
    """1009 期望伤害：倍率×ATK×蓄能档×防御区 0.5×未击破 0.9×期望暴击×增伤池（1+火）."""
    return mult * AS_ATK * atk_mult * 0.5 * 0.9 * cz * (1 + fire)


# ---------------------------------------------------------------------------
# 对方侧场景模子（映射表见模块 docstring）
# ---------------------------------------------------------------------------

def _opt_natasha(action: str):
    return {"kind": "character", "character_id": "1105", "eidolon": 0,
            "action": action, "element": "physical", "conditionals": {},
            "base": {"atk": NA_ATK, "hp": NA_HP, "def": NA_DEF, "spd": NA_SPD},
            "attacker": {"atk": NA_ATK, "hp": NA_HP, "def": NA_DEF, "spd": NA_SPD,
                         "cr": 0.05, "cd": 0.5},
            "self_path": "Abundance",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_bailu(action: str):
    c = {"healingMaxHpBuff": True, "talentDmgReductionBuff": True,
         "e2UltHealingBuff": True, "e4SkillHealingDmgBuffStacks": 0}
    return {"kind": "character", "character_id": "1211", "eidolon": 0,
            "action": action, "element": "thunder", "conditionals": c,
            "base": {"atk": BL_ATK, "hp": BL_HP, "def": BL_DEF, "spd": BL_SPD},
            "attacker": {"atk": BL_ATK, "hp": BL_HP, "def": BL_DEF, "spd": BL_SPD,
                         "cr": 0.05, "cd": 0.5},
            "self_path": "Abundance",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_pela(action: str, *, cond: dict | None = None):
    c = {"teamEhrBuff": True, "enemyDebuffed": False, "skillRemovedBuff": False,
         "ultDefPenDebuff": False, "e4SkillResShred": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1106", "eidolon": 0,
            "action": action, "element": "ice", "conditionals": c,
            "base": {"atk": PL_ATK_W, "hp": PL_HP, "def": PL_DEF, "spd": PL_SPD},
            "attacker": {"atk": PL_ATK, "hp": PL_HP, "def": PL_DEF, "spd": PL_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": PL_ICE},
            "self_path": "Nihility",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_gepard(action: str):
    c = {"e4TeamResBuff": True}
    return {"kind": "character", "character_id": "1104", "eidolon": 0,
            "action": action, "element": "ice", "conditionals": c,
            "base": {"atk": GP_ATK_W, "hp": GP_HP, "def": GP_DEF, "spd": GP_SPD},
            "attacker": {"atk": GP_ATK_W, "hp": GP_HP, "def": GP_DEF, "spd": GP_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": GP_ICE},
            "self_path": "Preservation",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_serval(action: str, *, cond: dict | None = None):
    c = {"targetShocked": False, "enemyDefeatedBuff": False}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1103", "eidolon": 0,
            "action": action, "element": "thunder", "conditionals": c,
            "base": {"atk": SV_ATK, "hp": SV_HP, "def": SV_DEF, "spd": SV_SPD},
            "attacker": {"atk": SV_ATK, "hp": SV_HP, "def": SV_DEF, "spd": SV_SPD,
                         "cr": SV_CR, "cd": 0.5},
            "self_path": "Erudition",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_arlan(action: str, *, cond: dict | None = None):
    c = {"selfCurrentHpPercent": 1.00}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1008", "eidolon": 0,
            "action": action, "element": "thunder", "conditionals": c,
            "base": {"atk": AR_ATK_W, "hp": AR_HP, "def": AR_DEF, "spd": AR_SPD},
            "attacker": {"atk": AR_ATK, "hp": AR_HP, "def": AR_DEF, "spd": AR_SPD,
                         "cr": 0.05, "cd": 0.5},
            "self_path": "Destruction",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_asta(action: str, *, cond: dict | None = None):
    c = {"talentBuffStacks": 0, "ultSpdBuff": False, "fireDmgBoost": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1009", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": AS_ATK, "hp": AS_HP, "def": AS_DEF, "spd": AS_SPD},
            "attacker": {"atk": AS_ATK, "hp": AS_HP, "def": AS_DEF, "spd": AS_SPD,
                         "cr": AS_CR, "cd": 0.5, "element_boost": 0.224},
            "self_path": "Harmony",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 娜塔莎 1105（对方 1100/Natasha.ts 全实现）——basic-only 治疗族
# ===========================================================================

class TestNatashaDuipai:
    """娜塔莎 E0：面板回显/普攻 1.0——行迹节点全为 HP/DEF/RES/heal 不伤攻击面板，
    无注入双方全等."""

    def test_panel_echo(self, optimizer_driver):
        theirs = run_optimizer(optimizer_driver, _opt_natasha("basic"))
        st = theirs["stats"]
        assert st["atk"] == pytest.approx(NA_ATK, rel=REL_TOL)
        assert st["cr"] == pytest.approx(0.05, rel=REL_TOL)
        assert st["cd"] == pytest.approx(0.5, rel=REL_TOL)

    def test_basic(self, optimizer_driver):
        """普攻 1.0 物理（lv6 档）."""
        eng, log = _make_logged(_solo_compiled("1105", enemies=_dummy("e1", "physical")))
        log.clear()
        _cast(eng, "1105", "110501")
        ours = _hit_amounts(log, source="1105")
        theirs = run_optimizer(optimizer_driver, _opt_natasha("basic"))

        hand = _na(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", NA_CZ), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"


# ===========================================================================
# L2 白露 1211（对方 1200/Bailu.ts 全实现）——basic-only 治疗族
# ===========================================================================

class TestBailuDuipai:
    """白露 E0：面板回显（对方 A2 折叠 hp×1.1 在案）/普攻 1.0."""

    def test_panel_echo(self, optimizer_driver):
        theirs = run_optimizer(optimizer_driver, _opt_bailu("basic"))
        st = theirs["stats"]
        assert st["atk"] == pytest.approx(BL_ATK, rel=REL_TOL)
        assert st["hp"] == pytest.approx(BL_HP * 1.1, rel=REL_TOL), (
            "对方 A2 岐黄要论折叠常开（HP_P+10%）——不伤普攻，回显在案")
        assert st["cr"] == pytest.approx(0.05, rel=REL_TOL)

    def test_basic(self, optimizer_driver):
        """普攻 1.0 雷（lv6 档）."""
        eng, log = _make_logged(_solo_compiled("1211", enemies=_dummy("e1", "thunder")))
        log.clear()
        _cast(eng, "1211", "121101")
        ours = _hit_amounts(log, source="1211")
        theirs = run_optimizer(optimizer_driver, _opt_bailu("basic"))

        hand = _bl(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", BL_CZ), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"


# ===========================================================================
# L2 佩拉 1106（对方 1100/Pela.ts 全实现）——驱散+减防 debuff 族
# ===========================================================================

class TestPelaDuipai:
    """佩拉 E0：普攻/战技三方全等（R-TR1 收官——行迹回填 fixture）/终结技 Exposed
    减防+Bash 真伤压缩链/Wipe Out 攻击窗."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：普攻——我方 645.2712×1×1.224（fixture 回填）vs 对方同值，
        三方全等（原差 1.18×1.224 = 1.44432 消灭）."""
        eng, log = _make_logged(_solo_compiled("1106", enemies=_dummy("e1", "ice")))
        log.clear()
        _cast(eng, "1106", "110601")
        ours = _hit_amounts(log, source="1106")
        theirs = run_optimizer(optimizer_driver, _opt_pela("basic"))

        hand = _pl(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_basic_and_skill(self, optimizer_driver):
        """普攻 1.0/战技 2.1 双链全等（R-TR1 收官——fixture 行迹回填，无注入）."""
        eng, log = _make_logged(_solo_compiled("1106", enemies=_dummy("e1", "ice")))
        log.clear()
        _cast(eng, "1106", "110601")
        _cast(eng, "1106", "110602")
        ours = _hit_amounts(log, source="1106")
        theirs_basic = run_optimizer(optimizer_driver, _opt_pela("basic"))
        theirs_skill = run_optimizer(optimizer_driver, _opt_pela("skill"))

        assert ours[0] == pytest.approx(_pl(1.0), rel=REL_TOL), "普攻 vs 手算"
        assert ours[1] == pytest.approx(_pl(2.1), rel=REL_TOL), "战技 vs 手算"
        assert ours[0] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_skill["hits"][0]["atk_scaling"] == pytest.approx(2.1, rel=REL_TOL)
        assert theirs_skill["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.224, rel=REL_TOL)
        assert "PELA_WIPE_OUT" in eng.state.actors["1106"].modifiers, (
            "Wipe Out：战技后下一次攻击 +20%（伤后挂——本发不吃）")

    def test_ult_exposed_bash_chain(self, optimizer_driver):
        """终结技 1.0 AoE：先挂 Exposed（def −0.4）后伤——本发双方同吃减防；Bash
        R-PL1：我方真伤压缩 0.2×原伤（乘算 ×1.2）vs 对方 BOOST+0.2（加算）——非空
        增伤池下差恰为 (1.224×1.2)/1.424（空池时数值等价在案）；天赋回能对账."""
        eng, log = _make_logged(_solo_compiled("1106", enemies=_dummy("e1", "ice")))
        st = eng.state.actors["1106"]
        log.clear()
        _fire_ult(eng, "1106", "110603", energy=110.0)
        _cast(eng, "1106", "110601")
        ours = _hit_amounts(log, source="1106")
        cond = {"enemyDebuffed": True, "ultDefPenDebuff": True}
        theirs_ult = run_optimizer(optimizer_driver, _opt_pela("ult", cond=cond))
        theirs_basic = run_optimizer(optimizer_driver, _opt_pela("basic", cond=cond))

        hand_ult_ours = _pl(1.0, defz=PL_DEFZ_EXPOSED) * 1.2
        hand_ult_theirs = _pl(1.0, defz=PL_DEFZ_EXPOSED, boost=0.2)
        assert len(ours) == 4, "终结技 1 段+Bash 真伤 1 段 + 普攻 1 段+Bash 1 段"
        assert ours[0] == pytest.approx(_pl(1.0, defz=PL_DEFZ_EXPOSED), rel=REL_TOL), (
            "终结技本发（先挂后伤吃自身 Exposed）vs 手算")
        assert ours[1] == pytest.approx(0.2 * ours[0], rel=REL_TOL), (
            "Bash 真伤段 = 0.2×原伤（乘算压缩口径）")
        assert ours[0] + ours[1] == pytest.approx(hand_ult_ours, rel=REL_TOL), (
            "终结技+Bash 合计 vs 手算")
        assert sum(ours[2:]) == pytest.approx(hand_ult_ours, rel=REL_TOL), (
            "后续普攻+Bash 同形 vs 手算")
        assert (ours[0] + ours[1]) / theirs_ult["hits"][0]["damage"] == pytest.approx(
            (1.224 * 1.2) / 1.424, rel=REL_TOL), (
            "R-PL1 差恰为 1.4688/1.424（Bash 乘算 vs 加算——空池等价、非空池在案）")
        assert sum(ours[2:]) / theirs_basic["hits"][0]["damage"] == pytest.approx(
            (1.224 * 1.2) / 1.424, rel=REL_TOL), "R-PL1 后续普攻同比"
        bd = theirs_ult["hits"][0]["breakdown"]
        for k, v in (("defMulti", PL_DEFZ_EXPOSED), ("dmgBoostMulti", 1.424)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert math.isclose(st.current_energy, 45.0), (
            "110 全扣 + 回 5 + 天赋 +10（终结技打自身 Exposed）+ 普攻 20 + 天赋 +10")

    def test_wipe_out_next_attack(self, optimizer_driver):
        """Wipe Out：战技后普攻 +20%（对方 skillRemovedBuff=true 同池比等）."""
        eng, log = _make_logged(_solo_compiled("1106", enemies=_dummy("e1", "ice")))
        log.clear()
        _cast(eng, "1106", "110602")
        _cast(eng, "1106", "110601")
        ours = _hit_amounts(log, source="1106")
        theirs = run_optimizer(optimizer_driver, _opt_pela(
            "basic", cond={"skillRemovedBuff": True}))

        assert ours[1] == pytest.approx(_pl(1.0, boost=0.2), rel=REL_TOL), (
            "Wipe Out 窗内普攻 vs 手算")
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "双方互对")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.424, rel=REL_TOL)


# ===========================================================================
# L2 杰帕德 1104（对方 1100/Gepard.ts 全实现）——Grit 防转攻族
# ===========================================================================

class TestGepardDuipai:
    """杰帕德 E0：Grit 防转攻链（我方 on_turn_start 钩 vs 对方 dynamic conversion 常开）
    /普攻/战技三方全等（R-TR1 收官——def 回填经 Grit 放大进 ATK）."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：普攻——Grit 读 fixture 回填 def 736.745625 → ATK 801.1729687、
        冰伤 0.224，与对方全链同值（原差 (801.1729687×1.224)/(772.52175×1.0) 消灭）."""
        eng, log = _make_logged(_solo_compiled("1104", enemies=_dummy("e1", "ice")))
        log.clear()
        _turn_start(eng, "1104")
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")
        theirs = run_optimizer(optimizer_driver, _opt_gepard("basic"))

        hand = _gp(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_grit_chain(self, optimizer_driver):
        """Grit 全链全等（R-TR1 收官）：对方 dynamic conversion（ATK += 0.35×DEF）
        vs 我方 on_turn_start stat_exprs 活读（读 fixture 回填 def 736.745625）
        ——面板回显/普攻/战技三链."""
        eng, log = _make_logged(_solo_compiled("1104", enemies=_dummy("e1", "ice")))
        st = eng.state.actors["1104"]
        log.clear()
        _turn_start(eng, "1104")
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], GP_ATK, rel_tol=1e-9), (
            "我方 543.312 + 0.35×736.745625（Grit 读 fixture 回填 def）")
        _cast(eng, "1104", "110401")
        _cast(eng, "1104", "110402")
        ours = _hit_amounts(log, source="1104")
        theirs_basic = run_optimizer(optimizer_driver, _opt_gepard("basic"))
        theirs_skill = run_optimizer(optimizer_driver, _opt_gepard("skill"))

        assert theirs_basic["stats"]["atk"] == pytest.approx(GP_ATK, rel=REL_TOL), (
            "对方 dynamic conversion 面板回显 801.1729687")
        assert ours[0] == pytest.approx(_gp(1.0), rel=REL_TOL), "普攻 vs 手算"
        assert ours[1] == pytest.approx(_gp(2.0), rel=REL_TOL), "战技 vs 手算"
        assert ours[0] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_skill["hits"][0]["atk_scaling"] == pytest.approx(2.0, rel=REL_TOL)
        bd = theirs_basic["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("critMulti", GP_CZ), ("dmgBoostMulti", 1.224)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"


# ===========================================================================
# L2 希露瓦 1103（对方 1100/Serval.ts 全实现）——触电+天赋附加族
# ===========================================================================

class TestServalDuipai:
    """希露瓦 E0：普攻三方全等（R-TR1 收官）/战技上触电+天赋附加段逐段比等/
    终结技延长链/触电跳伤 R-SV1 收官（2026-09-22 双通道合并转三方全等）."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：普攻——我方暴击区 1.1185（fixture 回填 crit_rate 0.187）
        vs 对方同值，三方全等（原差 1.1185/1.025 消灭）."""
        eng, log = _make_logged(_solo_compiled("1103", enemies=_dummy("e1", "thunder")))
        log.clear()
        _cast(eng, "1103", "110301")
        ours = _hit_amounts(log, source="1103")
        theirs = run_optimizer(optimizer_driver, _opt_serval("basic"))

        hand = _sv(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_skill_talent_segments(self, optimizer_driver):
        """战技 1.4（相邻 0.6 对方收敛——单假人无落点）→ 触电挂载 → 天赋燃情和弦
        0.72：逐段 [1.4, 0.72] 双方比等（对方折叠 standardAdditional 段）."""
        eng, log = _make_logged(_solo_compiled("1103", enemies=_dummy("e1", "thunder")))
        log.clear()
        _cast(eng, "1103", "110302")
        ours = _hit_amounts(log, source="1103")
        theirs = run_optimizer(optimizer_driver, _opt_serval(
            "skill", cond={"targetShocked": True}))

        assert ours == pytest.approx([_sv(1.4), _sv(0.72)], rel=REL_TOL), (
            "我方战技+天赋附加段 vs 手算")
        assert [h["atk_scaling"] for h in theirs["hits"]] == pytest.approx(
            [1.4, 0.72], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "主段互对"
        assert ours[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), "附加段互对"
        assert "SHOCK_SKILL" in eng.state.actors["e1"].modifiers, "战技触电挂载（恒中）"

    def test_basic_and_ult_on_shocked(self, optimizer_driver):
        """触电后普攻/终结技：天赋附加段同发——[1.0, 0.72]/[1.8, 0.72] 逐段比等；
        终结技延长触电 +2 回合对账."""
        eng, log = _make_logged(_solo_compiled("1103", enemies=_dummy("e1", "thunder")))
        _cast(eng, "1103", "110302")
        dur0 = eng.state.actors["e1"].modifiers["SHOCK_SKILL"].duration
        log.clear()
        _cast(eng, "1103", "110301")
        _fire_ult(eng, "1103", "110303", energy=100.0)
        ours = _hit_amounts(log, source="1103")
        cond = {"targetShocked": True}
        theirs_basic = run_optimizer(optimizer_driver, _opt_serval("basic", cond=cond))
        theirs_ult = run_optimizer(optimizer_driver, _opt_serval("ult", cond=cond))

        assert ours[:2] == pytest.approx([_sv(1.0), _sv(0.72)], rel=REL_TOL), "普攻+附加段"
        assert ours[2:] == pytest.approx([_sv(1.8), _sv(0.72)], rel=REL_TOL), "终结技+附加段"
        assert ours[0] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_basic["hits"][1]["damage"], rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL)
        assert ours[3] == pytest.approx(theirs_ult["hits"][1]["damage"], rel=REL_TOL)
        assert eng.state.actors["e1"].modifiers["SHOCK_SKILL"].duration == dur0 + 2, (
            "终结技触电延长 +2（adjust_duration 收编族）")

    def test_shock_dot_r_sv1_closeout(self, optimizer_driver):
        """R-SV1 收官：触电跳伤 1.04 三方全等——声明式 dot 通道承载（不暴击+
        施加时刻快照；EHR 0.18 命中区 min(1, 1.0×1.18) 截 1.0 权重中性）vs 对方
        standardDot 无暴击区（dotBaseChance 1.0 中性），原差 1/1.1185 消灭
        （1005 卡芙卡 R-KF3 同族待迁）."""
        eng, log = _make_logged(_solo_compiled("1103", enemies=_dummy("e1", "thunder")))
        _cast(eng, "1103", "110302")
        log.clear()
        eng._tick_dots(eng.state.actors["e1"])   # 声明式跳伤走引擎 A 类结算
        ours = [e["amount"] for e in log
                if e.get("reason") == "dot" and e.get("source") == "1103"]
        theirs = run_optimizer(optimizer_driver, _opt_serval("dot"))

        hand = 1.04 * SV_ATK * 0.5 * 0.9    # 双方同口径（不暴击、权重 1.0）
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方触电跳 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 dot vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "R-SV1 收官：双方互对（原差 1/1.1185 消灭）")
        assert theirs["hits"][0]["damage_function"] == "Dot"


# ===========================================================================
# L2 阿兰 1008（对方 1000/Arlan.ts 全实现）——失 HP 增伤族
# ===========================================================================

class TestArlanDuipai:
    """阿兰 E0：满血普攻/战技/终结技三方全等（R-TR1 收官）/天赋失血增伤 R-AR1 读法差."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：普攻——我方 767.6928×1.0（fixture 回填）vs 对方同值，
        三方全等（原差 1.28 消灭）."""
        eng, log = _make_logged(_solo_compiled("1008", enemies=_dummy("e1", "thunder")))
        log.clear()
        _cast(eng, "1008", "100801")
        ours = _hit_amounts(log, source="1008")
        theirs = run_optimizer(optimizer_driver, _opt_arlan("basic"))

        hand = _ar(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_full_hp_chain(self, optimizer_driver):
        """满血链全等（R-TR1 收官）：普攻 1.0/终结技 3.2（相邻 1.6 对方收敛）/战技 2.4
        ——满血天赋双方 0 增伤（战技耗血殿后，伤害全在满血档结算）."""
        eng, log = _make_logged(_solo_compiled("1008", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1008"]
        log.clear()
        _cast(eng, "1008", "100801")
        _fire_ult(eng, "1008", "100803", energy=110.0, target="e1")
        _cast(eng, "1008", "100802")
        ours = _hit_amounts(log, source="1008")
        theirs_basic = run_optimizer(optimizer_driver, _opt_arlan("basic"))
        theirs_skill = run_optimizer(optimizer_driver, _opt_arlan("skill"))
        theirs_ult = run_optimizer(optimizer_driver, _opt_arlan("ult"))

        assert ours[0] == pytest.approx(_ar(1.0), rel=REL_TOL), "普攻 vs 手算"
        assert ours[1] == pytest.approx(_ar(3.2), rel=REL_TOL), "终结技主段 vs 手算"
        assert ours[2] == pytest.approx(_ar(2.4), rel=REL_TOL), "战技 vs 手算"
        assert ours[0] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_ult["hits"][0]["atk_scaling"] == pytest.approx(3.2, rel=REL_TOL)
        assert math.isclose(st.current_hp, AR_HP * 0.85, rel_tol=1e-9), (
            "战技耗血 15% Max（伤后扣——本发不吃天赋档）")
        assert math.isclose(st.current_energy, 35.0), (
            "110 全扣 + 回 5 + 战技回能 30（满血档链能量对账）")

    def test_half_hp_r_ar1_divergence(self, optimizer_driver):
        """R-AR1：50% HP 普攻——我方 all_dmg=0.72×0.5=0.36（线性读）vs 对方
        min(0.72, 0.5)=0.5（1:1 截断读），差恰为 1.5/1.36 = 75/68."""
        eng, log = _make_logged(_solo_compiled("1008", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1008"]
        st.current_hp = 0.5 * AR_HP
        log.clear()
        _cast(eng, "1008", "100801")
        ours = _hit_amounts(log, source="1008")
        theirs = run_optimizer(optimizer_driver, _opt_arlan(
            "basic", cond={"selfCurrentHpPercent": 0.5}))

        hand_ours = _ar(1.0, boost=0.36)
        hand_theirs = _ar(1.0, boost=0.5)
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方 50% 档 vs 手算（线性读）"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方 50% 档 vs 手算（1:1 截断读）")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            1.5 / 1.36, rel=REL_TOL), "R-AR1 差恰为 1.5/1.36 = 75/68（读法差）"
        bd = theirs["hits"][0]["breakdown"]
        assert bd["dmgBoostMulti"] == pytest.approx(1.5, rel=REL_TOL), "对方增伤池回显 1.5"


# ===========================================================================
# L2 艾丝妲 1009（对方 1000/Asta.ts 全实现）——弹射+蓄能叠层族
# ===========================================================================

class TestAstaDuipai:
    """艾丝妲 E0：普攻 0 层档三方全等（R-TR1 收官）/战技弹射 5 段 R-AS1 段内叠层差/
    静态 5 层普攻比等/灼烧跳伤 R-AS2 收官（2026-09-22 双通道合并转三方全等）."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：0 层普攻——我方火伤 0.404/暴击区 1.0585（fixture 回填）vs
        对方同值（原差 (1.0585×1.404)/(1.025×1.18) 消灭；蓄能叠层在伤后——本发 0 层档）."""
        eng, log = _make_logged(_solo_compiled("1009", enemies=_dummy("e1", "fire")))
        log.clear()
        _cast(eng, "1009", "100901")
        ours = _hit_amounts(log, source="1009")
        theirs = run_optimizer(optimizer_driver, _opt_asta("basic"))

        hand = _as(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_basic_zero_stacks(self, optimizer_driver):
        """0 层普攻面板回显（talentBuffStacks=0 双钉）：ATK/增伤池 1.404 对方回显
        与我方手算互证；普攻命中叠 1 层在伤后——本发仍 0 层档."""
        eng, log = _make_logged(_solo_compiled("1009", enemies=_dummy("e1", "fire")))
        log.clear()
        _cast(eng, "1009", "100901")
        ours = _hit_amounts(log, source="1009")
        theirs = run_optimizer(optimizer_driver, _opt_asta("basic"))

        # 普攻命中叠 1 层在伤后——本发仍 0 层档
        hand = _as(1.0)
        assert ours[0] == pytest.approx(hand, rel=REL_TOL), "我方（fixture 回填面板）0 层普攻 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["atk"] == pytest.approx(AS_ATK, rel=REL_TOL), "0 层 ATK 回显"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1 + AS_FIRE, rel=REL_TOL)

    def test_skill_r_as1_divergence(self, optimizer_driver):
        """R-AS1：战技 0 层开场——我方主段 0 层+弹射段逐段叠层（段 k 读 k 层，atk
        系数合计 6.4）vs 对方静态 0 档聚合 2.5 单发，差恰为 2.5/3.2 = 0.78125."""
        eng, log = _make_logged(_solo_compiled("1009", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1009"]
        log.clear()
        _cast(eng, "1009", "100902")
        ours = _hit_amounts(log, source="1009")
        theirs = run_optimizer(optimizer_driver, _opt_asta("skill"))

        segs = [_as(0.5, atk_mult=1 + AS_STACK_ATK * k) for k in range(5)]
        assert len(ours) == 5, "我方主段+4 弹射段（expected 取首全落 e1）"
        assert ours == pytest.approx(segs, rel=REL_TOL), "我方逐段（段 k 读 k 层）vs 手算"
        assert sum(ours) == pytest.approx(_as(0.5, atk_mult=6.4), rel=REL_TOL), (
            "合计 atk 系数 6.4")
        assert len(theirs["hits"]) == 1, "对方 enemyCount=1 聚合单发"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(2.5, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(_as(2.5), rel=REL_TOL), (
            "对方静态 0 档聚合 vs 手算")
        assert theirs["hits"][0]["damage"] / sum(ours) == pytest.approx(
            2.5 / 3.2, rel=REL_TOL), "R-AS1 差恰为 2.5/3.2 = 0.78125（段内叠层差）"
        assert math.isclose(st.resources["_charge"], 5.0), "5 段命中 → 5 层蓄能"
        assert math.isclose(st.current_energy, 30.0), "每段回能 6×5（tbgd 口径）"

    def test_basic_five_stacks(self, optimizer_driver):
        """战技后静态 5 层普攻：我方 atk×1.7 vs 对方 talentBuffStacks=5（ATK_P+0.7）
        ——全等（R-AS1 静态档收敛）."""
        eng, log = _make_logged(_solo_compiled("1009", enemies=_dummy("e1", "fire")))
        _cast(eng, "1009", "100902")
        log.clear()
        _cast(eng, "1009", "100901")
        ours = _hit_amounts(log, source="1009")
        theirs = run_optimizer(optimizer_driver, _opt_asta(
            "basic", cond={"talentBuffStacks": 5}))

        hand = _as(1.0, atk_mult=1.7)
        assert ours[0] == pytest.approx(hand, rel=REL_TOL), "5 层普攻 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["atk"] == pytest.approx(AS_ATK * 1.7, rel=REL_TOL), (
            "对方 5 层 ATK_P+0.7 回显")

    def test_burn_dot_r_as2_closeout(self, optimizer_driver):
        """R-AS2 收官：普攻灼烧跳伤 0.5（1 层档面板）三方全等——声明式 dot 通道
        （不暴击+施加时刻快照吃 1 层蓄能+dot_base_chance 0.8 期望权重）vs 对方
        standardDot 无暴击区且乘 dotBaseChance 0.8，原差 0.8/1.0585 消灭."""
        eng, log = _make_logged(_solo_compiled("1009", enemies=_dummy("e1", "fire")))
        _cast(eng, "1009", "100901")            # 灼烧施加（声明式通道恒挂）
        assert "ASTA_BURN" in eng.state.actors["e1"].modifiers
        log.clear()
        eng._tick_dots(eng.state.actors["e1"])   # 声明式跳伤走引擎 A 类结算
        ours = [e["amount"] for e in log
                if e.get("reason") == "dot" and e.get("source") == "1009"]
        theirs = run_optimizer(optimizer_driver, _opt_asta(
            "dot", cond={"talentBuffStacks": 1}))

        hand = 0.5 * AS_ATK * 1.14 * 0.5 * 0.9 * (1 + AS_FIRE) * 0.8
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方灼烧跳 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 dot（1 层档、无暴击区、×0.8 期望权重）vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "R-AS2 收官：双方互对（原差 0.8/1.0585 消灭）")


# ---------------------------------------------------------------------------
# 虎克 1109（火；行迹 atk 0.28/暴伤 0.133——B-TR① 已回填 fixture）
HK_ATK_W, HK_HP, HK_DEF, HK_SPD = 617.4, 1340.64, 352.8, 94
HK_ATK = HK_ATK_W * 1.28                        # 790.272
HK_CD = 0.5 + 0.133                             # 0.633
HK_CZ = 1 + 0.05 * HK_CD                        # 1.03165


def _hk(mult: float, *, atk: float = HK_ATK, cz: float = HK_CZ) -> float:
    """1109 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0）."""
    return mult * atk * 0.5 * 0.9 * cz


# 布洛妮娅 1101（风；行迹 风伤 0.224/暴伤 0.24——B-TR① 已回填 fixture；
# Military Might 全队增伤 0.10 双方常驻）
BY_ATK, BY_HP, BY_DEF, BY_SPD = 582.12, 1241.856, 533.61, 99
BY_WIND = 0.224 + 0.10                          # 0.324（行迹节点+军势大行迹）
BY_CD = 0.5 + 0.24                              # 0.74
BY_CZ = 1 + 0.05 * BY_CD                        # 1.037（我方期望暴击——Command 待收）
BY_ULT_CD = 0.16 * BY_CD + 0.20                 # 终结技暴伤件 0.3184（快照 0.74 基数）
BY_CD_ULT = BY_CD + BY_ULT_CD                   # 1.0584（双方同值）


def _by(mult: float, *, atk_mult: float = 1.0, cz: float = BY_CZ,
        boost: float = BY_WIND) -> float:
    """1101 期望伤害：倍率×ATK×增益档×防御区 0.5×未击破 0.9×暴击区×增伤池（1+风）."""
    return mult * BY_ATK * atk_mult * 0.5 * 0.9 * cz * (1 + boost)


def _by_theirs(mult: float, *, atk_mult: float = 1.0, cd: float = BY_CD,
               boost: float = BY_WIND) -> float:
    """1101 对方手算（普攻必暴——暴击区 1+cd 全暴击）."""
    return mult * BY_ATK * atk_mult * 0.5 * 0.9 * (1 + cd) * (1 + boost)


def _opt_hook(action: str, *, cond: dict | None = None):
    c = {"enhancedSkill": False, "targetBurned": False}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1109", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": HK_ATK_W, "hp": HK_HP, "def": HK_DEF, "spd": HK_SPD},
            "attacker": {"atk": HK_ATK, "hp": HK_HP, "def": HK_DEF, "spd": HK_SPD,
                         "cr": 0.05, "cd": HK_CD},
            "self_path": "Destruction",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_bronya(action: str, *, cond: dict | None = None):
    c = {"teamDmgBuff": True, "skillBuff": False, "ultBuff": False,
         "battleStartDefBuff": False, "techniqueBuff": False, "e2SkillSpdBuff": False}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1101", "eidolon": 0,
            "action": action, "element": "wind", "conditionals": c,
            "base": {"atk": BY_ATK, "hp": BY_HP, "def": BY_DEF, "spd": BY_SPD},
            "attacker": {"atk": BY_ATK, "hp": BY_HP, "def": BY_DEF, "spd": BY_SPD,
                         "cr": 0.05, "cd": BY_CD, "element_boost": 0.224},
            "self_path": "Harmony",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 虎克 1109（对方 1100/Hook.ts 全实现）——强化战技+灼烧天赋族
# ===========================================================================

class TestHookDuipai:
    """虎克 E0：普攻三方全等（R-TR1 收官）/战技灼烧+天赋附加段逐段比等/终结技→
    强化战技链/灼烧跳伤 R-HK1 收官（2026-09-22 双通道合并转三方全等）."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：普攻——我方 790.272/暴伤 0.633（fixture 回填）vs 对方同值，
        三方全等（原差 1.28×1.03165/1.025 消灭）."""
        eng, log = _make_logged(_solo_compiled("1109", enemies=_dummy("e1", "fire")))
        log.clear()
        _cast(eng, "1109", "110901")
        ours = _hit_amounts(log, source="1109")
        theirs = run_optimizer(optimizer_driver, _opt_hook("basic"))

        hand = _hk(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_skill_burn_talent_chain(self, optimizer_driver):
        """战技 2.4（灼烧伤后挂载——本发不触发天赋，对方 targetBurned=false 同构比等）
        → 后续普攻灼烧目标 [1.0, 1.0] 逐段比等；天赋回能 5 对账."""
        eng, log = _make_logged(_solo_compiled("1109", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1109"]
        log.clear()
        _cast(eng, "1109", "110902")
        _cast(eng, "1109", "110901")
        ours = _hit_amounts(log, source="1109")
        theirs_skill = run_optimizer(optimizer_driver, _opt_hook("skill"))
        theirs_basic = run_optimizer(optimizer_driver, _opt_hook(
            "basic", cond={"targetBurned": True}))

        assert ours[0] == pytest.approx(_hk(2.4), rel=REL_TOL), (
            "战技本发（灼烧伤后挂载不触发天赋——官方同序）vs 手算")
        assert ours[1:] == pytest.approx([_hk(1.0), _hk(1.0)], rel=REL_TOL), "普攻+附加段"
        assert ours[0] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL), (
            "战技双方互对（targetBurned=false——挂上灼烧的那发不吃天赋）")
        assert len(theirs_skill["hits"]) == 1
        assert ours[1] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs_basic["hits"][1]["damage"], rel=REL_TOL)
        assert "HOOK_BURN" in eng.state.actors["e1"].modifiers
        assert math.isclose(st.current_energy, 55.0), (
            "战技 30 + 普攻 20 + 天赋 5（普攻才触发）")

    def test_ult_enhanced_skill_chain(self, optimizer_driver):
        """终结技 4.0（灼烧目标 → [4.0, 1.0]）→ 强化战技 110909 2.8（[2.8, 1.0]）
        ——逐段双方比等；强化闩/大行迹回能对账."""
        eng, log = _make_logged(_solo_compiled("1109", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1109"]
        _cast(eng, "1109", "110902")
        st.current_energy = 120.0
        log.clear()
        _fire_ult(eng, "1109", "110903", energy=None, target="e1")
        assert st.resources["_enhanced_skill"] == 1.0, "终结技授强化战技态"
        _cast(eng, "1109", "110909")
        assert st.resources["_enhanced_skill"] == 0.0, "110909 消费归闩"
        ours = _hit_amounts(log, source="1109")
        cond = {"targetBurned": True}
        theirs_ult = run_optimizer(optimizer_driver, _opt_hook("ult", cond=cond))
        theirs_enh = run_optimizer(optimizer_driver, _opt_hook(
            "skill", cond={"enhancedSkill": True, "targetBurned": True}))

        assert ours[:2] == pytest.approx([_hk(4.0), _hk(1.0)], rel=REL_TOL), "终结技+附加段"
        assert ours[2:] == pytest.approx([_hk(2.8), _hk(1.0)], rel=REL_TOL), "强化战技+附加段"
        assert ours[0] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_ult["hits"][1]["damage"], rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs_enh["hits"][0]["damage"], rel=REL_TOL)
        assert ours[3] == pytest.approx(theirs_enh["hits"][1]["damage"], rel=REL_TOL)
        assert theirs_enh["hits"][0]["atk_scaling"] == pytest.approx(2.8, rel=REL_TOL)
        assert math.isclose(st.current_energy, 50.0), (
            "120 全扣 + 终结技 5+大行迹 5+天赋 5 + 强化战技 30+天赋 5")

    def test_burn_dot_r_hk1_closeout(self, optimizer_driver):
        """R-HK1 收官：灼烧跳伤 0.65 三方全等——声明式 dot 通道承载（不暴击+
        施加时刻快照，dot_base_chance 1.0 权重中性）vs 对方 standardDot 无暴击区，
        原差 1/1.03165 消灭；跳伤 reason='dot' 不触发天赋附加段（旧 hook 承载
        经 'hit' 同通道误触口径退役）."""
        eng, log = _make_logged(_solo_compiled("1109", enemies=_dummy("e1", "fire")))
        _cast(eng, "1109", "110902")
        log.clear()
        eng._tick_dots(eng.state.actors["e1"])   # 声明式跳伤走引擎 A 类结算
        ours = [e["amount"] for e in log
                if e.get("reason") == "dot" and e.get("source") == "1109"]
        theirs = run_optimizer(optimizer_driver, _opt_hook("dot"))

        hand = 0.65 * HK_ATK * 0.5 * 0.9
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方灼烧跳 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 dot vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "R-HK1 收官：双方互对（原差 1/1.03165 消灭）")


# ===========================================================================
# L2 布洛妮娅 1101（对方 1100/Bronya.ts 全实现）——增益辅助族（伤害仅普攻）
# ===========================================================================

class TestBronyaDuipai:
    """布洛妮娅 E0：普攻 R-TR1 收官+R-BR1 单因子留存/终结技增益链（暴伤换算双方同值）."""

    def test_basic_r_tr1_closeout(self, optimizer_driver):
        """R-TR1 收官：普攻——我方增伤 0.324/暴伤 0.74（fixture 回填）与对方同值，
        原复合差 (1.74×1.324)/(1.025×1.1) 的行迹因子消灭，仅留存 R-BR1 暴击区差
        （Command 必暴待收——期望暴击 1.037 vs 必暴 1.74）."""
        eng, log = _make_logged(_solo_compiled("1101", enemies=_dummy("e1", "wind")))
        log.clear()
        _cast(eng, "1101", "110101")
        ours = _hit_amounts(log, source="1101")
        theirs = run_optimizer(optimizer_driver, _opt_bronya("basic"))

        hand_ours = _by(1.0)
        hand_theirs = _by_theirs(1.0)
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方必暴档 vs 手算")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            (1 + BY_CD) / BY_CZ, rel=REL_TOL), "R-TR1 收官后仅余 R-BR1 单因子 1.74/1.037"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("dmgBoostMulti", 1 + BY_WIND)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}（行迹回填双方同值）"

    def test_basic_r_br1_divergence(self, optimizer_driver):
        """R-BR1：普攻——我方期望暴击 1.037 vs 对方 Command 必暴 1.74，
        差恰为 1.74/1.037（普攻必暴行迹待收）；其余乘区全等."""
        eng, log = _make_logged(_solo_compiled("1101", enemies=_dummy("e1", "wind")))
        log.clear()
        _cast(eng, "1101", "110101")
        ours = _hit_amounts(log, source="1101")
        theirs = run_optimizer(optimizer_driver, _opt_bronya("basic"))

        hand_ours = _by(1.0)
        hand_theirs = _by_theirs(1.0)
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方期望暴击档 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方必暴档 vs 手算")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            (1 + BY_CD) / BY_CZ, rel=REL_TOL), "R-BR1 差恰为 1.74/1.037（Command 待收）"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("critMulti", 1 + BY_CD),
                     ("dmgBoostMulti", 1 + BY_WIND)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_ult_buff_chain(self, optimizer_driver):
        """终结技增益链：我方 BRONYA_ULT_BUFF（atk 0.55/暴伤 0.16×0.74+0.2 快照）
        vs 对方 ultBuff（ATK_P 0.55 + base 0.2 + dynamic 0.16×0.74）——面板双方同值
        1.0584，普攻伤害差仍恰为 R-BR1 暴击区比."""
        eng, log = _make_logged(_solo_compiled("1101", enemies=_dummy("e1", "wind")))
        st = eng.state.actors["1101"]
        _fire_ult(eng, "1101", "110103", energy=120.0)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], BY_ATK * 1.55, rel_tol=1e-9), "终结技 ATK+55%"
        assert math.isclose(eff["crit_dmg"], BY_CD_ULT, rel_tol=1e-9), (
            "暴伤 0.74+0.16×0.74+0.2 = 1.0584")
        log.clear()
        _cast(eng, "1101", "110101")
        ours = _hit_amounts(log, source="1101")
        theirs = run_optimizer(optimizer_driver, _opt_bronya(
            "basic", cond={"ultBuff": True}))

        hand_ours = _by(1.0, atk_mult=1.55, cz=1 + 0.05 * BY_CD_ULT)
        hand_theirs = _by_theirs(1.0, atk_mult=1.55, cd=BY_CD_ULT)
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方终结技后普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            (1 + BY_CD_ULT) / (1 + 0.05 * BY_CD_ULT), rel=REL_TOL), (
            "R-BR1 终结技档差恰为 2.0584/1.05292（暴伤链同值剥离——差全在 Command）")
        assert theirs["stats"]["atk"] == pytest.approx(BY_ATK * 1.55, rel=REL_TOL), (
            "对方 ATK_P 0.55 换算回显")
        assert theirs["stats"]["cd"] == pytest.approx(BY_CD_ULT, rel=REL_TOL), (
            "对方 base 0.2+dynamic 0.16×0.74 暴伤回显 1.0584")
        assert math.isclose(st.current_energy, 25.0), "120 全扣 + 回 5 + 普攻 20"


# ---------------------------------------------------------------------------
# 姬子 1003（火；行迹 atk 0.18/火伤 0.224——B-TR① 已回填 fixture；基准 HP≥80% 暴击
# +15% 双方常驻）
HM_ATK_W, HM_HP, HM_DEF, HM_SPD = 756.756, 1047.816, 436.59, 96
HM_ATK = HM_ATK_W * 1.18                        # 892.97208
HM_FIRE = 0.224
HM_CR, HM_CD = 0.05 + 0.15, 0.5                 # 0.2（大行迹基准）
HM_CZ = 1 + HM_CR * HM_CD                       # 1.1


def _hm(mult: float, *, atk: float = HM_ATK, boost: float = HM_FIRE) -> float:
    """1003 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击 1.1×增伤池（1+火）."""
    return mult * atk * 0.5 * 0.9 * HM_CZ * (1 + boost)


# 瓦尔特 1004（虚数；行迹 atk 0.28/虚数 0.288——B-TR① 已回填 fixture）
WT_ATK_W, WT_HP, WT_DEF, WT_SPD = 620.928, 1125.432, 509.355, 102
WT_ATK = WT_ATK_W * 1.28                        # 794.78784
WT_IM = 0.288
WT_CZ = 1 + 0.05 * 0.5                          # 1.025
WT_DEFZ_WL = 100 / (100 * 0.6 + 100)            # 0.625（失重减防 0.4）
WT_EHR_CONV = 0.2 * WT_ATK_W                    # R-WT3：EHR 0.5 档 +20%×base


def _wt(mult: float, *, atk: float = WT_ATK, defz: float = 0.5,
        boost: float = WT_IM) -> float:
    """1004 期望伤害：倍率×ATK×防御区×未击破 0.9×期望暴击×增伤池（1+虚数+附加）."""
    return mult * atk * defz * 0.9 * WT_CZ * (1 + boost)


# 银狼 1006（量子；行迹 atk 0.56/量子 0.16/EHR 0.36——B-TR① 已回填 fixture；
# 11006103 旁注 EHR 转 ATK——B-SW① 已收 fixture 常驻件 stat_exprs）
SW_ATK_W, SW_HP, SW_DEF, SW_SPD = 640.332, 1047.816, 460.845, 107
SW_ATK = SW_ATK_W * 1.56                        # 998.91792
SW_Q = 0.16
SW_CZ = 1 + 0.05 * 0.5                          # 1.025
SW_EHR_CONV = 0.3 * SW_ATK_W                    # 旁注：EHR 0.36 档 floor(3.6)=3 → +30%×base
SW_ATK_FULL = SW_ATK + SW_EHR_CONV              # 1191.01752（pct 池 0.56+0.30=0.86 加算同值）
SW_DEFZ_ULT = 100 / (100 * 0.55 + 100)          # 0.64516（终结技减防 0.45）
SW_DEFZ_TALENT = 100 / (100 * 0.88 + 100)       # 0.53191（天赋减防缺陷 0.12）


def _sw(mult: float, *, atk: float = SW_ATK_FULL, defz: float = 0.5,
        res: float = 1.0) -> float:
    """1006 期望伤害：倍率×ATK×防御区×抗区×未击破 0.9×期望暴击×增伤池（1+量子）."""
    return mult * atk * defz * res * 0.9 * SW_CZ * (1 + SW_Q)


def _opt_himeko1003(action: str, *, cond: dict | None = None):
    c = {"targetBurned": False, "selfCurrentHp80Percent": True,
         "e1TalentSpdBuff": False, "e2EnemyHp50DmgBoost": True, "e6UltExtraHits": 2}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1003", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": HM_ATK_W, "hp": HM_HP, "def": HM_DEF, "spd": HM_SPD},
            "attacker": {"atk": HM_ATK, "hp": HM_HP, "def": HM_DEF, "spd": HM_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": HM_FIRE},
            "self_path": "Erudition",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_welt(action: str, *, cond: dict | None = None, ehr: float = 0.28):
    c = {"enemySlowed": False, "enemyWeightless": False, "retributionDmgStacks": 0,
         "ehrToAtkBoost": True, "traceAdditionalDmg": True, "skillExtraHits": 4,
         "e1WeightlessAdditionalDmg": True, "e4WeightlessResPen": True,
         "e6SlowedCrCdBoost": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1004b1", "eidolon": 0,
            "action": action, "element": "imaginary", "conditionals": c,
            "base": {"atk": WT_ATK_W, "hp": WT_HP, "def": WT_DEF, "spd": WT_SPD},
            "attacker": {"atk": WT_ATK, "hp": WT_HP, "def": WT_DEF, "spd": WT_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": WT_IM,
                         "effect_hit": ehr},
            "self_path": "Nihility",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_silverwolf(action: str, *, cond: dict | None = None):
    c = {"ehrToAtkConversion": True, "skillWeaknessResShredDebuff": False,
         "skillResShredDebuff": False, "talentDefShredDebuff": False,
         "ultDefShredDebuff": False, "targetDebuffs": 5, "e2Vulnerability": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1006b1", "eidolon": 0,
            "action": action, "element": "quantum", "conditionals": c,
            "base": {"atk": SW_ATK_W, "hp": SW_HP, "def": SW_DEF, "spd": SW_SPD},
            "attacker": {"atk": SW_ATK, "hp": SW_HP, "def": SW_DEF, "spd": SW_SPD,
                         "cr": 0.05, "cd": 0.5, "element_boost": SW_Q,
                         "effect_hit": 0.36},
            "self_path": "Nihility",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 姬子 1003（对方 1000/Himeko.ts 全实现）——Charge 追击族（≠姬子•启行 1510，
# SP 消歧在案）
# ===========================================================================

class TestHimekoDuipai:
    """姬子 E0：普攻三方全等（R-TR1 收官）/战技/终结技 AoE/满层天赋追击 1.4/
    星火 DoT R-HM1."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：普攻——我方 892.97208/火伤 0.224（fixture 回填；基准暴击 0.2
        双方同值）vs 对方同值，三方全等（原差 1.18×1.224 = 1.44432 消灭）."""
        eng, log = _make_logged(_solo_compiled("1003", enemies=_dummy("e1", "fire")))
        log.clear()
        _cast(eng, "1003", "100301")
        ours = _hit_amounts(log, source="1003")
        theirs = run_optimizer(optimizer_driver, _opt_himeko1003("basic"))

        hand = _hm(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["cr"] == pytest.approx(0.2, rel=REL_TOL), "基准暴击回显"

    def test_skill_and_ult(self, optimizer_driver):
        """战技 2.0（相邻 0.8 对方收敛）/终结技 2.3 AoE 双链全等（R-TR1 收官）."""
        eng, log = _make_logged(_solo_compiled("1003", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1003"]
        log.clear()
        _cast(eng, "1003", "100302")
        _fire_ult(eng, "1003", "100303", energy=120.0)
        ours = _hit_amounts(log, source="1003")
        theirs_skill = run_optimizer(optimizer_driver, _opt_himeko1003("skill"))
        theirs_ult = run_optimizer(optimizer_driver, _opt_himeko1003("ult"))

        assert ours[0] == pytest.approx(_hm(2.0), rel=REL_TOL), "战技主段 vs 手算"
        assert ours[1] == pytest.approx(_hm(2.3), rel=REL_TOL), "终结技 vs 手算"
        assert ours[0] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_ult["hits"][0]["atk_scaling"] == pytest.approx(2.3, rel=REL_TOL)
        assert math.isclose(st.current_energy, 5.0), "钉 120 全扣 + 回 5（战技 30 被钉值覆盖）"

    def test_fua_full_charge(self, optimizer_driver):
        """天赋追击：开战 1 层+钉 2 层=满 3 → 普攻带发 100304 AoE 1.4——对方 FUA
        静态行动比等；层数清空/追击回能对账."""
        eng, log = _make_logged(_solo_compiled("1003", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1003"]
        assert math.isclose(st.resources["charge"], 1.0), "开战 +1 层"
        eng._gain_resource(st, "charge", 2.0)
        assert math.isclose(st.resources["charge"], 3.0)
        log.clear()
        _cast(eng, "1003", "100301")
        ours = _hit_amounts(log, source="1003")
        theirs = run_optimizer(optimizer_driver, _opt_himeko1003("fua"))

        assert ours == pytest.approx([_hm(1.0), _hm(1.4)], rel=REL_TOL), (
            "普攻+追击两段 vs 手算")
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.4, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "追击段双方互对")
        assert math.isclose(st.resources["charge"], 0.0), "满层触发后清空"
        assert math.isclose(st.current_energy, 30.0), "普攻 20 + 追击 10（tbgd）"

    def test_dot_r_hm1_divergence(self, optimizer_driver):
        """R-HM1：星火灼烧我方无段（基础概率施加通道缺——熔核同因不下树在案）；
        对方 dot 段（0.3×ATK×0.5 期望权重、无暴击区）vs 手算钉."""
        theirs = run_optimizer(optimizer_driver, _opt_himeko1003("dot"))
        hand_theirs = 0.3 * HM_ATK * 0.5 * 0.9 * (1 + HM_FIRE) * 0.5
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方 dot vs 手算（R-HM1 我方无对应段在案）")
        assert theirs["hits"][0]["damage_function"] == "Dot"


# ===========================================================================
# L2 瓦尔特 1004（对方 1000/WeltB1.ts 全实现——B1 加强版套件，我方 fixture 同版）
# ===========================================================================

class TestWeltDuipai:
    """瓦尔特 E0：普攻+审判段三方全等（R-TR1 收官）/战技弹射 5 段+审判段/终结技
    失重链/天赋附加段 R-WT2 收官（段数口径在案）/Retribution R-WT1/EHR 转换 R-WT3."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：普攻+审判段——我方 794.78784/虚数 0.288（fixture 回填）vs
        对方同值，三方全等（原差 1.28×1.288 = 1.64864 消灭）."""
        eng, log = _make_logged(_solo_compiled("1004", enemies=_dummy("e1", "imaginary")))
        st = eng.state.actors["1004"]
        st.resources["_welt_slow_p"] = 0.0        # 关减速掷（隔离天赋触发——纯倍率场）
        log.clear()
        _cast(eng, "1004", "1100401")
        ours = _hit_amounts(log, source="1004")
        theirs = run_optimizer(optimizer_driver, _opt_welt("basic"))

        assert ours[:2] == pytest.approx([_wt(1.0), _wt(0.8)], rel=REL_TOL), (
            "我方普攻+审判段（fixture 回填面板）vs 手算")
        assert [h["atk_scaling"] for h in theirs["hits"]] == pytest.approx(
            [1.0, 0.8], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "主段互对"
        assert ours[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), "审判段互对"

    def test_basic_skill(self, optimizer_driver):
        """普攻 [1.0, 审判 0.8]/战技主段+4 弹射 3.6+审判 0.864 全等（R-TR1 收官）."""
        eng, log = _make_logged(_solo_compiled("1004", enemies=_dummy("e1", "imaginary")))
        st = eng.state.actors["1004"]
        st.resources["_welt_slow_p"] = 0.0        # 关减速掷（隔离天赋触发）
        log.clear()
        _cast(eng, "1004", "1100401")
        _cast(eng, "1004", "1100402")
        ours = _hit_amounts(log, source="1004")
        theirs_basic = run_optimizer(optimizer_driver, _opt_welt("basic"))
        theirs_skill = run_optimizer(optimizer_driver, _opt_welt("skill"))

        assert ours[:2] == pytest.approx([_wt(1.0), _wt(0.8)], rel=REL_TOL), (
            "普攻+审判段 vs 手算")
        assert ours[2] == pytest.approx(_wt(0.72), rel=REL_TOL), "战技主段 vs 手算"
        assert sum(ours[2:7]) == pytest.approx(_wt(3.6), rel=REL_TOL), (
            "战技主段+4 弹射合计（expected 取首全落 e1）")
        assert ours[7] == pytest.approx(_wt(0.864), rel=REL_TOL), "战技审判段 vs 手算"
        assert [h["atk_scaling"] for h in theirs_basic["hits"]] == pytest.approx(
            [1.0, 0.8], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_basic["hits"][1]["damage"], rel=REL_TOL)
        assert theirs_skill["hits"][0]["atk_scaling"] == pytest.approx(3.6, rel=REL_TOL), (
            "对方弹射聚合单发 3.6（段数差在案）")
        assert sum(ours[2:7]) == pytest.approx(
            theirs_skill["hits"][0]["damage"], rel=REL_TOL), "战技总和双方互对"
        assert ours[7] == pytest.approx(theirs_skill["hits"][1]["damage"], rel=REL_TOL), (
            "审判段双方互对")

    def test_ult_weightless_chain(self, optimizer_driver):
        """终结技 1.5 AoE：先挂失重（def −0.4）后伤——本发双方同吃比等；
        钉 10 层钉 R-WT1（Retribution 主件我方待收，对方增伤池 +1.0）."""
        eng, log = _make_logged(_solo_compiled("1004", enemies=_dummy("e1", "imaginary")))
        st = eng.state.actors["1004"]
        log.clear()
        _fire_ult(eng, "1004", "1100403", energy=120.0)
        ours = _hit_amounts(log, source="1004")
        cond = {"enemyWeightless": True}
        theirs_ult = run_optimizer(optimizer_driver, _opt_welt("ult", cond=cond))
        theirs_r10 = run_optimizer(optimizer_driver, _opt_welt(
            "ult", cond={"enemyWeightless": True, "retributionDmgStacks": 10}))

        hand = _wt(1.5, defz=WT_DEFZ_WL)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "终结技本发（先挂后伤吃自身失重）vs 手算")
        assert ours[0] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL), (
            "0 层档双方互对")
        assert "WELT_WEIGHTLESS" in eng.state.actors["e1"].modifiers
        assert theirs_r10["hits"][0]["damage"] == pytest.approx(
            _wt(1.5, defz=WT_DEFZ_WL, boost=WT_IM + 1.0), rel=REL_TOL), (
            "对方 10 层档 vs 手算")
        assert theirs_r10["hits"][0]["damage"] / ours[0] == pytest.approx(
            2.288 / 1.288, rel=REL_TOL), "R-WT1 差恰为 2.288/1.288（Retribution 待收）"
        bd = theirs_r10["hits"][0]["breakdown"]
        for k, v in (("defMulti", WT_DEFZ_WL), ("dmgBoostMulti", 2.288)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert math.isclose(st.current_energy, 10.0), (
            "120 全扣 + 终结技 5 + 大行迹 11004103 +5（已收）")

    def test_talent_r_wt2_closeout(self, optimizer_driver):
        """R-WT2 收官（B-WT① 换绑）：天赋时空扭曲=虚数附加段全乘区（category
        additional + _tw_proc 独立防递归闩——旧 category true 平值跳乘区退役），
        单发三方全等（原差 0.5×0.9×1.025×1.288 消灭）；段数口径差在案（我方逐 hit
        触发——普攻/审判段各带 1 发；对方按行动折叠 basic×1——官方逐 hit 泛指待实测）."""
        eng, log = _make_logged(_solo_compiled("1004", enemies=_dummy("e1", "imaginary")))
        st = eng.state.actors["1004"]
        st.resources["_welt_slow_p"] = 0.0        # 手动挂减速（隔离减速掷噪音）
        _inject(eng, "e1", "WELT_SLOW", {"spd_pct": -0.1})
        log.clear()
        _cast(eng, "1004", "1100401")
        ours = _hit_amounts(log, source="1004")
        theirs = run_optimizer(optimizer_driver, _opt_welt(
            "basic", cond={"enemySlowed": True}))

        hand_talent = 1.0 * WT_ATK * 0.5 * 0.9 * WT_CZ * (1 + WT_IM)   # 全乘区附加段
        assert ours[0] == pytest.approx(_wt(1.0), rel=REL_TOL), "普攻主段 vs 手算"
        assert ours[1] == pytest.approx(hand_talent, rel=REL_TOL), (
            "天赋附加段=1.0×ATK 全乘区（B-WT① 换绑后）vs 手算")
        assert ours[2] == pytest.approx(_wt(0.8), rel=REL_TOL), "审判段 vs 手算"
        assert ours[3] == pytest.approx(hand_talent, rel=REL_TOL), (
            "审判段同带 1 发天赋（我方逐 hit 触发口径——段数差在案）")
        assert [h["atk_scaling"] for h in theirs["hits"]] == pytest.approx(
            [1.0, 0.8, 1.0], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL)
        assert theirs["hits"][2]["damage"] == pytest.approx(hand_talent, rel=REL_TOL), (
            "对方天赋段（全乘区）vs 手算")
        assert ours[1] == pytest.approx(theirs["hits"][2]["damage"], rel=REL_TOL), (
            "R-WT2 收官：天赋段双方互对（乘区差消灭）")

    def test_ehr_conversion_r_wt3_divergence(self, optimizer_driver):
        """R-WT3：大行迹 11004103 EHR>40% 转 ATK 我方待收——EHR 钉 0.5 场对方
        +0.2×base（dynamic conversion），差恰为 1.15625."""
        eng, log = _make_logged(_solo_compiled("1004", enemies=_dummy("e1", "imaginary")))
        st = eng.state.actors["1004"]
        st.resources["_welt_slow_p"] = 0.0
        log.clear()
        _cast(eng, "1004", "1100401")
        ours = _hit_amounts(log, source="1004")
        theirs = run_optimizer(optimizer_driver, _opt_welt("basic", ehr=0.5))

        assert theirs["stats"]["atk"] == pytest.approx(
            WT_ATK + WT_EHR_CONV, rel=REL_TOL), "对方 EHR 0.5 档 +0.2×base 回显"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            (WT_ATK + WT_EHR_CONV) / WT_ATK, rel=REL_TOL), (
            "R-WT3 差恰为 1.15625（EHR 转 ATK 待收）")


# ===========================================================================
# L2 银狼 1006（对方 1000/SilverWolfB1.ts 全实现——B1 加强版套件，我方 fixture
# 同版单轨 11006xx）
# ===========================================================================

class TestSilverWolfDuipai:
    """银狼 E0：普攻/战技三方全等（R-TR1+R-SW3 双收官）/终结技 AoE 减防链/抗性削
    R-SW1/天赋减防缺陷 R-SW2."""

    def test_basic_closeout(self, optimizer_driver):
        """R-TR1+R-SW3 收官：普攻——我方 1191.01752/量子 0.16（fixture 行迹回填
        +11006103 旁注 EHR 0.36 档 +0.3 已收）vs 对方全链同值，三方全等
        （原复合差与 R-SW3 单因子 1.19231 全消灭）."""
        eng, log = _make_logged(_solo_compiled("1006", enemies=_dummy("e1", "quantum")))
        log.clear()
        _cast(eng, "1006", "1100601")
        ours = _hit_amounts(log, source="1006")
        theirs = run_optimizer(optimizer_driver, _opt_silverwolf("basic"))

        hand = _sw(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 全链面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1006"])["atk"],
            SW_ATK_FULL, rel_tol=1e-9), "我方旁注转换面板 1191.01752（0.56+0.30 加算）"
        assert theirs["stats"]["atk"] == pytest.approx(SW_ATK_FULL, rel=REL_TOL), (
            "对方 1.56 行迹+0.3×base EHR 转换回显")

    def test_basic_skill(self, optimizer_driver):
        """普攻 1.0/战技 1.96 双链全等（R-TR1+R-SW3 收官——无注入拐杖）."""
        eng, log = _make_logged(_solo_compiled("1006", enemies=_dummy("e1", "quantum")))
        log.clear()
        _cast(eng, "1006", "1100601")
        _cast(eng, "1006", "1100602")
        ours = _hit_amounts(log, source="1006")
        theirs_basic = run_optimizer(optimizer_driver, _opt_silverwolf("basic"))
        theirs_skill = run_optimizer(optimizer_driver, _opt_silverwolf("skill"))

        assert ours[0] == pytest.approx(_sw(1.0), rel=REL_TOL), "普攻 vs 手算"
        assert ours[1] == pytest.approx(_sw(1.96), rel=REL_TOL), "战技 vs 手算"
        assert ours[0] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_skill["hits"][0]["atk_scaling"] == pytest.approx(1.96, rel=REL_TOL)

    def test_ult_def_shred_chain(self, optimizer_driver):
        """终结技 3.8 AoE：先挂 SW_DEF_DOWN（def −0.45）后伤——本发双方同吃比等
        （≡DEF_PEN 0.45；官方 B1「all enemies」AoE 双源核实——过堂②）."""
        eng, log = _make_logged(_solo_compiled("1006", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1006"]
        log.clear()
        _fire_ult(eng, "1006", "1100603", energy=110.0)
        ours = _hit_amounts(log, source="1006")
        theirs = run_optimizer(optimizer_driver, _opt_silverwolf(
            "ult", cond={"ultDefShredDebuff": True}))

        hand = _sw(3.8, defz=SW_DEFZ_ULT)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "终结技本发（先挂后伤吃自身减防）vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(3.8, rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            SW_DEFZ_ULT, rel=REL_TOL)
        assert "SW_DEF_DOWN" in eng.state.actors["e1"].modifiers
        assert math.isclose(st.current_energy, 5.0), "110 全扣 + 回 5"

    def test_res_shred_r_sw1_divergence(self, optimizer_driver):
        """R-SW1：战技全抗削 13% 我方待收（res_pen 挂敌方死键摘除在案）——钉
        skillResShredDebuff=true 场 对方抗区 ×1.13."""
        eng, log = _make_logged(_solo_compiled("1006", enemies=_dummy("e1", "quantum")))
        log.clear()
        _cast(eng, "1006", "1100601")
        ours = _hit_amounts(log, source="1006")
        theirs = run_optimizer(optimizer_driver, _opt_silverwolf(
            "basic", cond={"skillResShredDebuff": True}))

        assert theirs["hits"][0]["damage"] == pytest.approx(
            _sw(1.0, res=1.13), rel=REL_TOL), "对方抗性削档 vs 手算"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(1.13, rel=REL_TOL), (
            "R-SW1 差恰为抗区 1.13")
        assert theirs["hits"][0]["breakdown"]["resMulti"] == pytest.approx(1.13, rel=REL_TOL)

    def test_talent_def_bug_r_sw2_divergence(self, optimizer_driver):
        """R-SW2：天赋减防类缺陷我方待收（随机三类无通道——我方第 1 类减攻承载；
        对方减防类 12% 常开折叠）——钉 talentDefShredDebuff=true 场防区比."""
        eng, log = _make_logged(_solo_compiled("1006", enemies=_dummy("e1", "quantum")))
        log.clear()
        _cast(eng, "1006", "1100601")
        ours = _hit_amounts(log, source="1006")
        theirs = run_optimizer(optimizer_driver, _opt_silverwolf(
            "basic", cond={"talentDefShredDebuff": True}))

        assert theirs["hits"][0]["damage"] == pytest.approx(
            _sw(1.0, defz=SW_DEFZ_TALENT), rel=REL_TOL), "对方减防缺陷档 vs 手算"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            SW_DEFZ_TALENT / 0.5, rel=REL_TOL), (
            "R-SW2 差恰为防区 0.53191/0.5（随机读法双偏在案）")
        assert "SW_BUG_ATK" in eng.state.actors["e1"].modifiers, (
            "我方天赋缺陷按第 1 类减攻挂载（随机通道缺在案）")


# ---------------------------------------------------------------------------
# 桑博 1108（风；行迹 atk 0.28——B-TR① 已回填 fixture；EHR/RES 节点不伤）
SA_ATK_W, SA_HP, SA_DEF, SA_SPD = 617.4, 1023.12, 396.9, 102
SA_ATK = SA_ATK_W * 1.28                        # 790.272
SA_CZ = 1 + 0.05 * 0.5                          # 1.025


def _sa(mult: float, *, atk: float = SA_ATK, cz: float = SA_CZ) -> float:
    """1108 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击（增伤池 1.0）."""
    return mult * atk * 0.5 * 0.9 * cz


def _opt_sampo(action: str, *, cond: dict | None = None):
    c = {"tickCoefficient": 1, "targetDotTakenDebuff": False,
         "skillExtraHits": 4, "targetWindShear": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1108", "eidolon": 0,
            "action": action, "element": "wind", "conditionals": c,
            "base": {"atk": SA_ATK_W, "hp": SA_HP, "def": SA_DEF, "spd": SA_SPD},
            "attacker": {"atk": SA_ATK, "hp": SA_HP, "def": SA_DEF, "spd": SA_SPD,
                         "cr": 0.05, "cd": 0.5, "effect_hit": 0.18},
            "self_path": "Nihility",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 桑博 1108（对方 1100/Sampo.ts 全实现）——弹射+风化 DoT 族
# ===========================================================================

class TestSampoDuipai:
    """桑博 E0：普攻三方全等（R-TR1 收官）/战技弹射 5 段/终结技 AoE/风化 tick
    R-SA1+R-SA2 收官（2026-09-22 双通道合并转三方全等）."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：普攻——我方 790.272×1.0（fixture 回填）vs 对方同值，
        三方全等（原差 1.28 消灭）."""
        eng, log = _make_logged(_solo_compiled("1108", enemies=_dummy("e1", "wind")))
        log.clear()
        _cast(eng, "1108", "110801")
        ours = _hit_amounts(log, source="1108")
        theirs = run_optimizer(optimizer_driver, _opt_sampo("basic"))

        hand = _sa(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_skill_and_ult(self, optimizer_driver):
        """战技主段+4 弹射 2.8（对方聚合单发——段数差在案）/终结技 1.6 AoE 双链
        全等（R-TR1 收官）；大行迹回能对账."""
        eng, log = _make_logged(_solo_compiled("1108", enemies=_dummy("e1", "wind")))
        st = eng.state.actors["1108"]
        log.clear()
        _cast(eng, "1108", "110802")
        _fire_ult(eng, "1108", "110803", energy=120.0)
        ours = _hit_amounts(log, source="1108")
        theirs_skill = run_optimizer(optimizer_driver, _opt_sampo("skill"))
        theirs_ult = run_optimizer(optimizer_driver, _opt_sampo("ult"))

        assert len(ours) == 6, "战技 5 段 + 终结技 1 段"
        assert sum(ours[:5]) == pytest.approx(_sa(2.8), rel=REL_TOL), "战技 5 段合计 vs 手算"
        assert ours[5] == pytest.approx(_sa(1.6), rel=REL_TOL), "终结技 vs 手算"
        assert theirs_skill["hits"][0]["atk_scaling"] == pytest.approx(2.8, rel=REL_TOL)
        assert sum(ours[:5]) == pytest.approx(
            theirs_skill["hits"][0]["damage"], rel=REL_TOL), "战技总和双方互对"
        assert ours[5] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL), (
            "终结技双方互对（DoT 易伤双方同不伤直伤）")
        assert math.isclose(st.current_energy, 15.0), (
            "钉 120 全扣 + 终结技 5 + 大行迹 1108102 +10（战技 6 被钉值覆盖）")

    def test_wind_shear_dot_r_sa1_sa2_closeout(self, optimizer_driver):
        """R-SA1+R-SA2 收官：风化 tick（普攻 1 层档 0.52）三方全等——声明式 dot
        通道承载（不暴击+施加时刻快照+dot_base_chance 0.65×(1+EHR 0.18)=0.767
        期望权重）vs 对方 standardDot 同口径（原差 0.65/1.025 消灭）；终结技 DoT
        易伤已收（vulnerability+hit_condition dot 承伤 scoped 件）→ 易伤档亦三方
        全等（原差 1.3×0.65/1.025 消灭）."""
        eng, log = _make_logged(_solo_compiled("1108", enemies=_dummy("e1", "wind")))
        _cast(eng, "1108", "110801")
        assert "WIND_SHEAR" in eng.state.actors["e1"].modifiers, "天赋风化挂载（恒中档）"
        log.clear()
        eng._tick_dots(eng.state.actors["e1"])   # 声明式跳伤走引擎 A 类结算
        ours = [e["amount"] for e in log
                if e.get("reason") == "dot" and e.get("source") == "1108"]
        theirs_off = run_optimizer(optimizer_driver, _opt_sampo("dot"))
        theirs_on = run_optimizer(optimizer_driver, _opt_sampo(
            "dot", cond={"targetDotTakenDebuff": True}))

        hand = 0.52 * SA_ATK * 0.5 * 0.9 * 0.65 * 1.18   # 不暴击×0.767 期望权重
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方风化跳 vs 手算"
        assert theirs_off["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert theirs_on["hits"][0]["damage"] == pytest.approx(hand * 1.3, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs_off["hits"][0]["damage"], rel=REL_TOL), (
            "R-SA1 收官：双方互对（原差 0.65/1.025 消灭）")
        # R-SA2：我方易伤件已收——终结技挂 SAMPO_DOT_VULN 后 tick 吃 ×1.3 双方同值
        #（清风化回 1 层口径：对方 dot 按 1 层建模——tickCoefficient 钉 1）
        eng2, log2 = _make_logged(_solo_compiled("1108", enemies=_dummy("e1", "wind")))
        _fire_ult(eng2, "1108", "110803", energy=120.0)   # 挂易伤 + 风化 1 层
        eng2._remove_modifier(eng2.state.actors["e1"], "WIND_SHEAR", "replace")
        _cast(eng2, "1108", "110801")   # 重新挂风化 1 层
        log2.clear()
        eng2._tick_dots(eng2.state.actors["e1"])
        ours_on = [e["amount"] for e in log2
                   if e.get("reason") == "dot" and e.get("source") == "1108"]
        assert ours_on == pytest.approx([hand * 1.3], rel=REL_TOL), (
            "我方风化跳（易伤档）vs 手算")
        assert ours_on[0] == pytest.approx(theirs_on["hits"][0]["damage"], rel=REL_TOL), (
            "R-SA2 收官：双方互对（原差 1.3×0.65/1.025 消灭）")


# ---------------------------------------------------------------------------
# 卢卡 1111（物理；行迹 atk 0.28——B-TR① 已回填 fixture；EHR/DEF 节点不伤）
LK_ATK_W, LK_HP, LK_DEF, LK_SPD = 582.12, 917.28, 485.1, 103
LK_ATK = LK_ATK_W * 1.28                        # 745.1136
LK_CZ = 1 + 0.05 * 0.5                          # 1.025
LK_BLEED = 3.38                                 # 裂伤上限支（min(24% Max, 338% ATK)——假人走上限）
LK_DETONATE = 0.85 * LK_BLEED                   # 2.873（天赋引爆 lv10）


def _lk(mult: float, *, atk: float = LK_ATK, vuln: float = 0.0) -> float:
    """1111 期望伤害：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击×易伤区（增伤池 1.0）."""
    return mult * atk * 0.5 * 0.9 * LK_CZ * (1 + vuln)


def _opt_luka(action: str, *, cond: dict | None = None):
    c = {"tickCoefficient": 1, "basicEnhanced": False, "targetUltDebuffed": False,
         "e1TargetBleeding": True, "basicEnhancedExtraHits": 3, "e4TalentStacks": 4}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1111", "eidolon": 0,
            "action": action, "element": "physical", "conditionals": c,
            "base": {"atk": LK_ATK_W, "hp": LK_HP, "def": LK_DEF, "spd": LK_SPD},
            "attacker": {"atk": LK_ATK, "hp": LK_HP, "def": LK_DEF, "spd": LK_SPD,
                         "cr": 0.05, "cd": 0.5},
            "self_path": "Nihility",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 卢卡 1111（对方 1100/Luka.ts 全实现）——战意循环+裂伤引爆族
# ===========================================================================

class TestLukaDuipai:
    """卢卡 E0：普攻三方全等（R-TR1 收官）/战技/裂伤 tick R-LK2/终结技易伤 R-LK3
    时序差/强化普攻 2.0 聚合比等+引爆段 R-LK1."""

    def test_basic(self, optimizer_driver):
        """R-TR1 收官：普攻——我方 745.1136×1.0（fixture 回填）vs 对方同值，
        三方全等（原差 1.28 消灭）."""
        eng, log = _make_logged(_solo_compiled("1111", enemies=_dummy("e1", "physical")))
        log.clear()
        _cast(eng, "1111", "111101")
        ours = _hit_amounts(log, source="1111")
        theirs = run_optimizer(optimizer_driver, _opt_luka("basic"))

        hand = _lk(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（fixture 回填面板）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_skill_and_bleed_dot(self, optimizer_driver):
        """战技 1.2 比等（裂伤挂载双方同构）；裂伤跳 R-LK2——我方事件承载含期望暴击
        vs 对方 standardDot 无暴击区，差恰为 1/1.025."""
        eng, log = _make_logged(_solo_compiled("1111", enemies=_dummy("e1", "physical")))
        log.clear()
        _cast(eng, "1111", "111102")
        ours_skill = _hit_amounts(log, source="1111")
        assert "LUKA_BLEED" in eng.state.actors["e1"].modifiers
        log.clear()
        _turn_start(eng, "e1")
        ours_dot = _hit_amounts(log, source="1111")
        theirs_skill = run_optimizer(optimizer_driver, _opt_luka("skill"))
        theirs_dot = run_optimizer(optimizer_driver, _opt_luka("dot"))

        assert ours_skill == pytest.approx([_lk(1.2)], rel=REL_TOL), "战技 vs 手算"
        assert ours_skill[0] == pytest.approx(
            theirs_skill["hits"][0]["damage"], rel=REL_TOL), "战技双方互对"
        hand_ours_dot = _lk(LK_BLEED)
        hand_theirs_dot = LK_BLEED * LK_ATK * 0.5 * 0.9
        assert ours_dot == pytest.approx([hand_ours_dot], rel=REL_TOL), (
            "我方裂伤跳（上限支+含期望暴击）vs 手算")
        assert theirs_dot["hits"][0]["damage"] == pytest.approx(
            hand_theirs_dot, rel=REL_TOL), "对方 dot vs 手算"
        assert theirs_dot["hits"][0]["damage"] / ours_dot[0] == pytest.approx(
            1 / LK_CZ, rel=REL_TOL), "R-LK2 差恰为 1/1.025（DoT 暴击区差）"

    def test_ult_r_lk3_and_post_ult_vuln(self, optimizer_driver):
        """R-LK3：终结技易伤时序——我方伤后挂（本发 3.3 裸）vs 对方常开折叠进本发
        （×1.2）；后续普攻双方同吃 0.2 比等；战意 +2 与循环制动回能对账."""
        eng, log = _make_logged(_solo_compiled("1111", enemies=_dummy("e1", "physical")))
        st = eng.state.actors["1111"]
        log.clear()
        _fire_ult(eng, "1111", "111103", energy=130.0, target="e1")
        ours_ult = _hit_amounts(log, source="1111")
        assert "LUKA_VULN" in eng.state.actors["e1"].modifiers
        assert math.isclose(st.resources["fighting_will"], 3.0), (
            "入场 1（on_battle_start）+ 终结技战意 +2")
        log.clear()
        _cast(eng, "1111", "111101")
        ours_basic = _hit_amounts(log, source="1111")
        theirs_off = run_optimizer(optimizer_driver, _opt_luka("ult"))
        theirs_on = run_optimizer(optimizer_driver, _opt_luka(
            "ult", cond={"targetUltDebuffed": True}))
        theirs_basic = run_optimizer(optimizer_driver, _opt_luka(
            "basic", cond={"targetUltDebuffed": True}))

        assert ours_ult == pytest.approx([_lk(3.3)], rel=REL_TOL), (
            "终结技本发（伤后挂不吃易伤）vs 手算")
        assert ours_ult[0] == pytest.approx(theirs_off["hits"][0]["damage"], rel=REL_TOL), (
            "钉 false 双方互对")
        assert theirs_on["hits"][0]["damage"] / ours_ult[0] == pytest.approx(
            1.2, rel=REL_TOL), "R-LK3 差恰为 1.2（时序差——对方折叠进本发）"
        assert ours_basic == pytest.approx([_lk(1.0, vuln=0.2)], rel=REL_TOL), (
            "后续普攻吃易伤 vs 手算")
        assert ours_basic[0] == pytest.approx(
            theirs_basic["hits"][0]["damage"], rel=REL_TOL), "后续攻击双方同吃比等"
        assert math.isclose(st.current_energy, 34.0), (
            "130 全扣 + 终结技 5 + 战意 +2×循环制动 6 + 普攻 20 + 普攻战意 +1×循环制动 3")

    def test_enhanced_basic_and_detonation(self, optimizer_driver):
        """强化普攻：直冲 3 段+碎天+粉碎 3 段=2.0 与对方聚合单发比等（段数差在案）；
        引爆段 R-LK1——对方无落点，我方 0.85×3.38=2.873 物理全乘区段 vs 手算钉."""
        eng, log = _make_logged(_solo_compiled("1111", enemies=_dummy("e1", "physical")))
        st = eng.state.actors["1111"]
        _cast(eng, "1111", "111102")               # 入场 1+战技 1=2 层 + 裂伤挂载
        log.clear()
        _cast(eng, "1111", "111108")
        ours = _hit_amounts(log, source="1111")
        theirs = run_optimizer(optimizer_driver, _opt_luka(
            "basic", cond={"basicEnhanced": True}))

        # 段序：直冲×3（instances）→ 碎天 hook → 引爆 hook → 粉碎×3 hook
        assert len(ours) == 8, "直冲 3+碎天 1+引爆 1+粉碎 3"
        direct = ours[0] + ours[1] + ours[2] + ours[3] + ours[5] + ours[6] + ours[7]
        assert direct == pytest.approx(_lk(2.0), rel=REL_TOL), (
            "直冲 0.6+碎天 0.8+粉碎 0.6=2.0 vs 手算")
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(2.0, rel=REL_TOL), (
            "对方聚合 0.2×3+0.8+3×0.2=2.0 单发")
        assert direct == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "直伤总和双方互对（段数差在案）")
        assert ours[4] == pytest.approx(_lk(LK_DETONATE), rel=REL_TOL), (
            "R-LK1 引爆段 0.85×3.38 物理全乘区 vs 手算（对方无落点在案）")
        assert math.isclose(st.resources["fighting_will"], 0.0), "强化普攻耗 2 层"
