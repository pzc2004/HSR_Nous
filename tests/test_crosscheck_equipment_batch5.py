"""L3 装备级对拍·残部收官②波（BACKLOG B22 扩展②续五）：首批 6+4（equipment.py）、
批量波 25+14（equipment_batch.py）、专光扫荡 22（equipment_batch2.py）、残部续波
37+6（equipment_batch3.py）、收官波 33+9（equipment_batch4.py）之后的收官②波——
本批 11 光锥（同谐专光 teammates 镜像链 10 件 + 23023 砂金载体件）+ 位面饰品
（301-328 有伤害机制件），目标=「能拍的」全拍完。每件等式场景三方比对（我方引擎
vs 对方 vs 手算，rel_tol 1e-4）+ 结构差钉倍数。

前置 driver 通道（本波硬指标，crosscheck.mts 头注有完整口径）：
- 队友光锥链（teammates 块 light_cone 子块——镜像 precomputeTeammates LC 槽
  comboStateTransform.ts:193-197：resolver 门控 lc.path≠队友 path→空控制器 +
  teammateDefaults 开关表 + mutual/teammateEffects **三参**调用（原生无第四参））。
- 位面饰品链（equipment.relic_sets 同口收 3xx——setsArray[4]=[5]=位面 index；
  p2c 原生分支 / p2x 同块 / **p2t 终端件接入**（evaluateTerminalSetConditionals
  镜像补全）+ 位面 dyn 件（evaluateDynamicSetConditionals 镜像）+ set_threshold_cd
  场景槽（305 读 x.c.a[CD] 档））。

载体（映射表现成，见各源文件；主 C=刻律德菈 1412·风（普攻 1.0×ATK，行迹 atk18%/
风伤 22.4%，CR 1.05 封顶 1.0 → 期望 1.5）/真理医生 1305（普攻 1.0/战技 1.5/追击
2.7×ATK，行迹 atk28%）/黑塔 1013（普攻 1.0/大招 2.0×ATK）/桑博 1108（风化 DoT）/
砂金 1304（普攻 1.0×DEF——fixture 过堂勘正⑪ DEF 倍率收编）/遐蝶 1407（普攻
0.5×HP）/长夜月 1413（普攻 0.5×HP）/杰帕德 1104（Grit 防转攻 0.35×DEF））。队友
载体=星期日 1313（同谐——战技 131302 指友/终结技 131303 指友，污染件随摘先例）/
遐蝶 1407（记忆——忆灵技 1140702 触发器）/佩拉 1106（虚无——终结技挂负面触发器）/
杰帕德 1104（存护——终结技触发器）。

===========================================================================
光锥 buff 状态映射表（对方条件开关 ↔ 我方模板 hooks；属性段=对方钉面板）
===========================================================================
--- 同谐专光 teammates 镜像链（对方 teammate LC conditionals 挂载点逐件 recon；
    我方 fixture=验收版全 hooks；队友=星期日 1313（开关全钉 off 回空白 slate），
    对方 teammate 角色污染件同摘（Sunday 全 off / Castorice memospriteActive+
    teamDmgBoost off / Pela 三开关 off / Gepard E4 闸天然灭）---
23003 但战斗还未结束 S1（星期日）
postSkillDmgBuff（true）  precomputeTeammateEffects：SingleTarget BOOST 30%    普攻比等（战技→下
                            （官方=战技后下一行动队友增伤——对方开关恒开=近似；     一行动我方挂
                            我方 on_action 挂标→on_turn_start 非装备者友方        30% 1回合）
                            消费=事件序等价）
23019 镜中故我 S1（星期日）——BE+60% 属性段（挂星期日面板无主 C 读出，随挂不测）
postUltDmgBuff（true）    precomputeMutual：FullTeam BOOST 24%（大招后全队增伤       普攻比等（星期日
                            3回合——对方恒开；我方 on_ultimate 钩 all_allies         大→全队 24%）
                            24% 3回合）
23021 游戏尘寰 S1（星期日）——自身 CD+32% 属性段（挂星期日面板无读出，随挂不测）
maskActive（true）        precomputeTeammateEffects：FullTeam CR 10%+CD 28%      普攻比等（进战假面
                            （假面持有期队友双暴——对方恒开；我方 on_battle_start    →队友双爆）
                            假面标记+other_allies 光环 enable_if 懒求值）
23034 回到大地的飞行 S1（星期日）——回能/产点半无伤害读出随挂不测
dmgBuffStacks 0-3（3）   precomputeMutual：BOOST 15%×N（wearer=Sunday →            普攻 @1/@3 层
                            SelfAndMemosprite deferrable 落主 C；我方战技/大招        比等（星期日
                            指友→目标【圣咏】叠层 all_dmg 15%×N——refresh 自动叠层）  战技×N）
23038 如果时间是一朵花 S1（星期日）——自身 CD+36% 属性段（无读出随挂不测）+
                            进战回能/追加回能（无伤害读出随挂不测）
presage（true）           precomputeMutual：FullTeam CD 48%（谕示持有期全队暴伤     普攻比等（进战
                            ——对方恒开；我方 on_battle_start 谕示 team 光环）       谕示→全队 CD）
23042 愿虹光永驻天空 S1（遐蝶 1407——记忆）——spd+18% 属性段（无伤害读出随挂不测）
vulnerability（true）     precomputeMutual：FullTeam VULNERABILITY 18%（忆灵技后     普攻比等（死龙
                            敌方承伤——对方恒开；我方忆灵技钩 all_enemies 18% 2回合）  忆灵技→承伤）
23047 海洋为何而歌 S1（佩拉 1106——虚无）——EHR+40% 属性段（挂佩拉面版无读出）
dotVulnStacks 0-N（4）   precomputeMutual：FullTeam DOT 标签 VULNERABILITY 5%×N     风化跳钉 S1
spdBuff（false）          +SPD_P 10%（魂迷 DoT 易伤叠层——**我方待收**（装备者施加     （DoT 易伤
                            负面计数无来源过滤通道在案）+加速（无伤害读出）；        我方待收在案）
                            我方魂迷标记/加速无伤害段 → 对方/我方 = 1+0.05×N）
23048 金血铭刻的时代 S1（星期日）——atk+64% 属性段（挂星期日面板无读出）+回点
                            （无伤害读出随挂不测）
skillDmgBoost（true）     precomputeTeammateEffects：SKILL 标签 BOOST 54%（默认      战技比等（真理
                            SelfAndPet 落主 C；我方战技指友→目标 dmg_skill 54%        战技）
                            3回合）
23051 纵然山河万程 S1（杰帕德 1104——存护）——atk+64% 属性段（无读出随挂不测）+
                            大招全队回血（治疗读出端未开随挂不测）
dmgBoost（true）          precomputeMutual：FullTeam BOOST 24%（+hasSummons 时       普攻比等（杰帕德
                            另 12%——我方场无召唤物双灭；卫戍 3回合对方恒开=近似；     大→全队 24%）
                            我方 on_ultimate 钩 all_allies 24% 3回合+召唤物 12%
                            enable_if has_summon（杰帕德无召唤物灭））
23052 爱如此刻永恒 S1（遐蝶 1407——记忆）——spd+18% 属性段（无伤害读出随挂不测）
vulnerability（false）    precomputeMutual：FullTeam VULNERABILITY 10%×(1+60%)        普攻比等（死龙
cdBoost（true）             （双持增强）+CD 16%×(1+60%)——诗行（忆灵技对敌）→全队      忆灵技→诗行
                            CD 双方同挂比等；空白（忆灵技对友）→敌方承伤——在册忆灵    →全队 CD 16%）
                            技无 ally 指向载体（21050 案）我方不可达 → 钉 false 双方
                            同灭（列注）
--- 存护（砂金 1304 载体——盲注护盾暴击链；主 LC 链，非 teammates 链）---
23023 命运从未公平 S1——DEF+40% 属性段（双方同挂——对方 LC properties 无控制器
                            承载钉进 attacker；我方 on_battle_start 常驻 def_pct）
shieldCdBuff（true）      precomputeEffects：自身 CD 40%（官方=供盾时暴伤 2 回合        基线比等（双方
                            ——对方无条件=建模近似；我方「提供护盾」无发射点待收         普攻全 DEF
                            在案）；杠杆 trace 双方同值（DEF 2303.67 档 floor/round      倍率同构+
                            同档 7 → CR+14%——fixture 过堂勘正⑪ DEF 倍率收编在案）       杠杆同档）；
                                                                                    钉 S2（对方
                                                                                    CD 40% vs
                                                                                    我方无段）
targetVulnerability       precomputeMutual：FullTeam VULNERABILITY 10%（追加命中          钉 S3（对方
（true）                    易伤——对方无条件；我方 after_being_hit follow_up 钩在         易伤 10% vs
                            ——盲注满 7 触发天赋追击链可直达，本波不拍列注）              我方无段）

===========================================================================
位面饰品 buff 状态映射表（基础件 p2c 两侧各自原生通道，不钉面板；对方 p2x/p2t/dyn
读口逐件 recon——p2t=终端件（CR/SPD 阈值读**终值面板**）、dyn=阈值动态件（读终值
面板）、305 p2x 读 x.c.a[CD]（c 只含套装件——set_threshold_cd 场景槽直钉同 124 先例）
===========================================================================
301 太空封印站（黑塔） p2c atk 12%（双方 stat 同值）+SPD≥120 → atk+12%（对方 dyn
                   读终值 SPD 面板 buffDynamic 平值；我方 enable_if 懒求值 atk_pct）→
                   spd 注入 120 档普攻比等
302 不老者的仙舟（黑塔） p2c hp 12%（无伤害读出）+SPD≥120 → 攻击+8%（对方 dyn  wearer
                   +8%×baseAtk 平值 SelfAndMemosprite + outputBuff(ATK) 惰性件；我方
                   team 光环 atk_pct 8% enable_if—— wearer 读出口径同值，team 语义差
                   在案）→ spd 注入 120 档普攻比等
303 泛银河商业公司（桑博） p2c EHR+10%（无直伤消费=面板锚）+攻击=当前 EHR×25%
                   （上限 25%）（双方同式连续口径——对方 dyn CONTINUOUS min(0.25,
                   0.25×EHR)×baseAtk；我方 stat_exprs clamp(EHR×0.25,0,0.25)）→
                   EHR 0.9 档普攻比等
304 筑城者的贝洛伯格（杰帕德） p2c def 15%（无注入比等——Grit 防转攻 0.35×DEF
                   双方同读）+EHR≥50% → def+15%（对方 dyn 读终值 EHR 面板
                   buffDynamic 0.15×baseDef；我方 enable_if def_pct）→ dyn 半钉 S6
                   （条件件互观察口径差：对方 grit 读全面板 vs 我方 §4.16 无条件面板）
305 星体差分机（真理） p2c CD 16%+CD≥120% → CR+60% 至首次攻击（对方 p2x 读
                   x.c.a[CD]（c 只含套装件——set_threshold_cd 槽直钉 1.25 镜像「遗器
                   暴伤」读数域）；我方 on_battle_start 快照条件 crit_dmg≥1.2（setup
                   前注入）——**首攻前比等；摘除窗口对方无概念（恒开）→ 第 2 击钉 S4**
306 停转的萨尔索图（黑塔） p2c CR 8%+当前 CR≥50% → 终结技/追击+15%（对方 p2t 读
                   终值 CR 面板 ULT|FUA BOOST；我方 enable_if dmg_ultimate/follow_up）
                   → CR 注入档大招比等（**p2t 通道首证**）
307 盗贼公国塔利亚（白厄） p2c BE 16%+SPD≥145 → BE+20%（对方 dyn 读终值 SPD 面板；
                   我方 enable_if——BE 面板互对+击破段 ×1.2 vs 手算（对方 kind=
                   character 无击破段不可见，119 先例）→ spd 注入 145 档
309 繁星竞技场（真理） p2c CR 8%+当前 CR≥70% → 普攻/战技+20%（对方 p2t BASIC|
                   SKILL BOOST；我方 dmg_basic/skill）→ CR 注入档普攻比等（p2t 证②）
310 折断的龙骨（黑塔） p2c 效果抵抗 10%+RES≥30% → 全队 CD+10%（对方 dyn 读终值
                   RES 面板 FullTeam buffDynamic 0.10；我方 team 光环 crit_dmg 0.1
                   enable_if）→ RES 注入档大招比等
311 苍穹战线格拉默（真理） p2c atk 12%+SPD≥135/160 → 增伤 12%/18%（对方 p2t 读
                   终值 SPD 面板分档 BOOST；我方 stat_exprs 三元分档）→ 两档普攻
                   比等（p2t 证③）
313 无主荒星茨冈尼亚（黑塔） p2c CR 4%+击杀叠 CD 4%×N（钳 10）（对方 value 滑条
                   0-10=层数；我方 on_kill 钩 stat_exprs 活读层）→ 杀 3 后普攻比等
314 出云显世与高天神国（真理） p2c atk 12%+同命途队友≥1 → CR+12%（对方 p2x 开关
                   （countTeamPath 闸在 UI overrideConditional 层——p2x 直读开关；
                   我方 count_team(path)≥2 闸——双人队两侧同开）→ 普攻比等
315 奔狼的都蓝王朝（真理） 功勋叠层：追击+5%×N/满 5 层 CD+25%（对方 value 滑条
                   0-5；我方 after_being_hit follow_up 钩叠层（315 勘正④改道——
                   on_action 对 hook FUA 死钩）——**段时序：叠层在追击伤害
                   结算后=当次不吃**→第 6 发追击 @5 层比等；第 5 发钉 S5）
318 奇想蕉乐园（遐蝶） p2c CD 16%+召唤物在场 → CD+32%（对方 p2x 开关；我方
                   enable_if has_summon）→ 召死龙后普攻比等
319 谧宁拾骨地（遐蝶） p2c hp 12%+HP≥5000 → CD+28%（对方 dyn 读终值 HP 面板
                   buffDynamic 0.28 SelfAndMemosprite；我方 enable_if——忆灵侧同挂
                   不重复钉）→ HP 注入 5523 档普攻比等
321 妖精织梦的乐园（黑塔） 队伍数≠4 → 每差 1 名增伤 12%/9%（对方 value 滑条=队伍
                   数（arcadiaSetIndexToDmg 表）；我方 count($team.actor_id) 活读）→
                   单人队（count=1 → +36%）普攻比等
324 天国@直播间（真理） p2c CD 16%+单回合耗点≥3 → CD+32% 3回合（对方 p2x 开关
                   恒开=建模近似；我方 before_consume 计数≥3 挂——同事件快照第 4 耗
                   触发）→ 耗 4 点击后普攻比等
325 零号关卡朋克洛德（火花） p2c 欢愉度 8%+欢愉度≥40%/80% → CD 20%/32%（对方
                   dyn 读终值 ELATION 面板两档；我方 stat_exprs 三元分档）→ 两档
                   欢愉技比等
326 千星荟萃之城（黑塔） 追击→atk+24% 2回合+击杀→全队 CD+12%（对方 value 滑条
                   0-3（1=追击攻/2=击杀 CD/3=双件）；我方 after_being_hit follow_up 钩
                   （326 勘正④——on_action 对 hook FUA 死钩改道 115 先例）+on_kill 钩——
                   黑塔击杀跨线追击天紧张追击半，value=3 双件同挂）→ 杀 1 后普攻比等
328 寰宇生研院（长夜月） 能量上限≥200 → 每超 1 点增伤 0.2%（上限 32%）（对方 p2x
                   读 context.baseEnergy 场景槽同式；我方 on_battle_start max_energy
                   活读——长夜月 240 → 8%）→ 普攻比等

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注倍数，任一侧改动触红）
===========================================================================
S1  23047 魂迷 DoT 易伤叠层（我方待收在案——装备者施加负面计数无来源过滤通道）
    → 钉 4 层：对方/我方 = 1+0.05×4 = 1.20
S2  23023 供盾暴伤（我方待收在案——提供护盾无发射点；对方无条件 CD 40%）→
    钉 true（targetVulnerability false 隔离）：对方/我方 = (1+0.19×0.9)/1.095
    ≈ 1.068950（杠杆 CR+14% 双方同档）
S3  23023 追加命中易伤（对方无条件 VULNERABILITY 10%；我方钩在 FUA 触发链本波
    不拍）→ 钉 true 复合：对方/我方 = (1+0.19×0.9)×1.10/1.095 ≈ 1.175845
S4  305 星体差分机摘除窗口（官方「持续到施放首次攻击后结束」——我方 on_action
    摘除；对方 p2x 恒开无窗口概念）→ 第 2 击：对方/我方 = (1+0.77×1.41)/
    (1+0.17×1.41) = 2.0857/1.2397 ≈ 1.682459
S5  315 功勋叠层段时序（我方叠层在追击伤害结算后=当次不吃；对方滑条恒满档）
    → 第 5 发追击：对方/我方 = (1.25×1.336)/(1.20×1.22125) ≈ 1.139542
S6  304 dyn 防御的条件件互观察口径（对方 grit 转化读全面板 DEF 933.21 vs
    我方 §4.16 条件件彼此不可互观察——grit 读无条件面板 DEF 834.98）→
    对方/我方 = (543.312+0.35×933.21)/(543.312+0.35×834.98) ≈ 1.041148

真病清单（本波新发现——单列；对方侧/external 只读报回，我方侧已修）：
- B5-F①（我方 fixture 钩通道病，已修）：315 奔狼/326 千星追击触发钩挂 on_action
  ——hook deal_damage 系 FUA（真理/托帕天赋族）不发 on_action=死钩（115 大公
  after_being_hit 先例为正解）→ 两件改道 after_being_hit × follow_up ×
  seg_index==0（315 任意我方源 + actor_type 过滤承原意；326 装备者源）——
  315 对拍钓出（真理 6 连战技功勋 0 层实证），326 同案顺手同修
- 对方侧（external 只读报回，不修）：无新发现

跳过清单（缺读出端/载体未立，不硬造）：
- 23052 空白半（忆灵技对友→敌方承伤 10%×(1+60%)）：在册忆灵技无 ally 指向
  载体（21050 案列注）——双方同灭不拍
- 位面饰品：308 生命的翁瓦克（回能无伤害读出）/312 梦想之地匹诺康尼（同元素
  队友增伤走对方 teammate 套装槽 getTeammateOption——未接入；穿戴侧对方 p2x=
  Memosprite BOOST 近似与我方口径差大不取）/316 劫火莲灯（我方 fixture hooks 空
  ——生成器未收编）/317 沉陆海域露莎卡（对方穿戴侧 outputBuff(ATK) 惰性未建模+
  teammate 槽未接入）/320 渊思寂虑的巨树（治疗量无伤害读出）/322 沉欢醉饮的海隅
  （我方 fixture hooks 空）/323 永恒之地翁法罗斯（全队速度 8% 无伤害读出）/
  327 坠星启航地（开拓同行组名册未立——in_group 无载体，不硬造）
- 队友遗器/位面套装槽（118 钟表匠 FullTeam BE、312/317 teammate 选项等）：
  getTeammateOption 链未接入（本波硬指标不含——后续波次）
"""
from __future__ import annotations

import math

import pytest

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
from tests.test_crosscheck_equipment import _opt  # noqa: F401
from tests.test_crosscheck_equipment_batch import (  # noqa: F401
    _eff, _fragile_toughness, _kill_enemies, _lc, _low_hp_enemy, _pha_opt, _relic,
)
from tests.test_crosscheck_equipment_batch2 import (  # noqa: F401
    _break_amounts, _emit, _hits_of, _member_build2,
)
from tests.test_crosscheck_equipment_batch3 import (  # noqa: F401
    BREAK_BASE_10, BREAK_BASE_10_PHY, BREAK_BASE_10_WIND,
    _ca_opt, _cy_opt, _gp_opt, _lc55_opt, _summon_nw, _sunday_skill,
)
from tests.test_crosscheck_team_phainon import (  # noqa: F401
    CY_ATK, CY_ATK_W, CY_WIND, PH_ATK, PH_CR, PH_CD, PH_HP, Z_CY, Z_PH,
    _opt_cerydra, _ult_at,
)
from tests.test_crosscheck_team_remembrance import (  # noqa: F401
    CA_ATK, CA_CD, CA_CR, CA_DEF, CA_HP, CA_Q, CA_SPD, Z_CA_CRIT, _fire_ult,
    _opt_castorice, _opt_evernight,
)
from tests.test_crosscheck_team_remembrance import (  # noqa: F401
    EV_CD, EV_CR, EV_HP,
)
from tests.test_crosscheck_legacy_1000 import (  # noqa: F401
    GP_ATK_W, GP_CZ, GP_DEF, GP_DEF_W, GP_HP, GP_ICE, GP_SPD, SA_ATK, SA_ATK_W,
    SA_CZ, SA_DEF, SA_HP, SA_SPD, _opt_gepard, _opt_sampo,
)
from tests.test_crosscheck_elation import (  # noqa: F401
    LV_COEF, SP_ATK, SP_CD, SP_CD_P30, SP_CR, SP_EL, _el, _opt_sparxie,
    _pin_banger, _pin_pool_gain,
)

# ---------------------------------------------------------------------------
# 口径常数（本批新增；载体既有常数从各波文件复用）
# ---------------------------------------------------------------------------

# 光锥白值（fixture base_stats 终审值；仅 atk/hp/def 进手算锚的才列）
LC23003_ATK = 529.2
LC23019_ATK = 529.2
LC23021_ATK = 529.2
LC23034_ATK = 476.28
LC23038_ATK = 529.2
LC23042_ATK = 476.28
LC23047_ATK = 635.04
LC23048_ATK = 635.04
LC23051_ATK = 582.1199999999999
LC23052_ATK = 476.28
LC23023_ATK = 423.36
LC23023_DEF = 661.5

# 砂金 1304 载体常量（fixture 终审值：白值三围 + 行迹 def_pct 0.35——普攻/终结技/
# 天赋全 DEF 倍率（过堂勘正⑪ 在案），与对方 defScaling 同构）
AV_ATK_W = 446.29200000000003
AV_DEF_W = 654.885
AV_HP_W = 1203.0479999999998
AV_SPD = 106
AV_TRACE_DEF_PCT = 0.35

# 物理/风击破基准复用（307 白厄物理——BREAK_BASE_10_PHY；310/311 无击破段）


# ---------------------------------------------------------------------------
# 队友链助手（对方侧：teammates 块带光锥——队友角色污染开关全 off 回空白 slate；
# 我方侧：队友带光锥 build + 污染件随摘）
# ---------------------------------------------------------------------------

# 对方侧队友模板（conditionals= teammateDefaults 全钉 off——队友角色自身 buff 链
# 清零，只留 LC 链；键集逐件 recon 自对方 teammateDefaults）
_SUNDAY_OFF = {
    "character_id": "1313", "eidolon": 0, "path": "Harmony",
    "conditionals": {"skillDmgBuff": False, "talentCrBuffStacks": 0,
                     "beatified": False, "teammateCDValue": 0,
                     "techniqueDmgBuff": False, "e1DefPen": False,
                     "e2DmgBoost": False, "e6CrToCdConversion": False},
}
_CASTORICE_OFF = {
    "character_id": "1407", "eidolon": 0, "path": "Remembrance",
    "conditionals": {"memospriteActive": False, "teamDmgBoost": False},
}
_PELA_OFF = {
    "character_id": "1106", "eidolon": 0, "path": "Nihility",
    "conditionals": {"teamEhrBuff": False, "ultDefPenDebuff": False,
                     "e4SkillResShred": False},
}
_GEPARD_OFF = {
    "character_id": "1104", "eidolon": 0, "path": "Preservation",
    "conditionals": {"e4TeamResBuff": False},
}


def _tm(base: dict, lc: str, path: str, cond: dict) -> dict:
    """队友 + 光锥场景块（对方侧 teammates 条目）."""
    return {**base, "light_cone": {"id": lc, "superimposition": 1,
                                   "path": path, "conditionals": cond}}


def _team_lc_build(main: str, teammate: str, lc: str):
    """我方侧双成员 build（主 C 裸装，队友带光锥——队友只承事件不出手）."""
    return {"build": {"team": [
        {"character_template": main, "level": 80},
        {"character_template": teammate, "level": 80,
         "light_cone_template": lc, "light_cone": {"superimposition": 1}},
    ], "policy": _POLICY}}


def _pop(eng, actor: str, *mids: str):
    """污染件随摘（_clean_knots/_sunday_skill 先例——只摘队友自身件，LC 件保留）."""
    for mid in mids:
        eng.state.actors[actor].modifiers.pop(mid, None)


def _sunday_cast_clean(eng, target: str):
    """星期日战技 131302 指友 → 摘目标侧污染件（增伤 30%/CR 20%——LC 件保留）."""
    _cast(eng, "1313", "131302", target=target)
    _pop(eng, target, "SUNDAY_SKILL_DMG", "SUNDAY_TALENT_CR")


def _cy_hand(pool_extra: float = 0.0, *, cz: float | None = None,
             vuln: float = 0.0) -> float:
    """刻律德菈普攻手算（1.0×ATK×(1+风伤+额外池)×0.5×0.9×期望暴击×易伤）."""
    crit = 1.5 if cz is None else cz
    return 1.0 * CY_ATK * (1 + CY_WIND + pool_extra) * 0.5 * 0.9 * crit * (1 + vuln)


def _ratio_tm(action: str, *, teammates, lc_atk: float = 0.0, cond=None,
              extra_attacker=None, equipment=None):
    """真理医生对方场景·队友扩展版（_ratio_opt 无 teammates 参——本波 teammates
    链载体；面板 atk 含行迹 28%）."""
    c = {"enemyDebuffStacks": 0, "summationStacks": 0}
    c.update(cond or {})
    white = RT_ATK + lc_atk
    atk = {**{"atk": _rt_panel(lc_atk), "hp": RT_HP, "def": RT_DEF, "spd": RT_SPD,
              "cr": RT_CR, "cd": RT_CD}, **(extra_attacker or {})}
    sc = _opt("1305", action, "imaginary", "Hunt", conditionals=c,
              base={"atk": white, "hp": RT_HP, "def": RT_DEF, "spd": RT_SPD},
              attacker=atk, equipment=equipment, enemy=None)
    sc["teammates"] = teammates
    return sc


def _sampo_tm_opt(action: str, *, teammates, lc_atk: float = 0.0,
                  extra_attacker=None):
    """桑博对方场景·队友扩展版（_opt_sampo 无 teammates——本波 teammates 链载体；
    面板 atk 含行迹 28%，EHR 0.18 行迹面板锚）."""
    white = SA_ATK_W + lc_atk
    sc = _opt("1108", action, "wind", "Nihility",
              conditionals={"tickCoefficient": 1, "targetDotTakenDebuff": False,
                            "skillExtraHits": 4, "targetWindShear": True},
              base={"atk": white, "hp": SA_HP, "def": SA_DEF, "spd": SA_SPD},
              attacker={"atk": white * 1.28, "hp": SA_HP, "def": SA_DEF,
                        "spd": SA_SPD, "cr": 0.05, "cd": 0.5, "effect_hit": 0.18,
                        **(extra_attacker or {})},
              equipment=None, enemy=None)
    sc["teammates"] = teammates
    return sc


def _av_opt(action: str, *, equipment=None, cond=None, extra_attacker=None):
    """砂金对方场景（1304 载体常量首立——fixture 普攻/终结技/天赋全 DEF 倍率
    （过堂勘正⑪ 在案），与对方 defScaling 同构；杠杆 trace 双方同式（我方 round
    近似 vs 对方 floor——DEF 2303.67 档 floor(7.0367)=round(7.0367)=7 双方同值）."""
    c = {"defToCrBoost": True, "fuaHitsOnTarget": 7, "fortifiedWagerBuff": False,
         "enemyUnnervedDebuff": False, "e2ResShred": False, "e4DefBuff": False,
         "e6ShieldStacks": 0}
    c.update(cond or {})
    def_panel = (AV_DEF_W + LC23023_DEF) * (1 + AV_TRACE_DEF_PCT + 0.40)
    sc = _opt("1304", action, "imaginary", "Preservation", conditionals=c,
              base={"atk": AV_ATK_W + LC23023_ATK, "hp": AV_HP_W + 1058.4,
                    "def": AV_DEF_W + LC23023_DEF, "spd": AV_SPD},
              attacker={"atk": AV_ATK_W + LC23023_ATK, "hp": AV_HP_W + 1058.4,
                        "def": def_panel, "spd": AV_SPD, "cr": 0.05, "cd": 0.5,
                        "element_boost": 0.144, **(extra_attacker or {})},
              equipment=equipment, enemy=None)
    return sc


# ===========================================================================
# 光锥对拍——同谐专光 teammates 镜像链（队友=星期日 1313，主 C=刻律德菈 1412）
# ===========================================================================

class TestLC23003ButTheBattleIsntOver:
    """但战斗还未结束 S1（星期日→刻律德菈）：战技后下一个行动队友增伤 30%
    （对方 SingleTarget BOOST 30% 恒开=近似；我方挂标→on_turn_start 消费）."""

    def test_post_skill_dmg_buff(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1313", "23003"), "wind"))
        _sunday_cast_clean(eng, "1412")             # 星期日战技 → LC 挂标（在星期日）
        assert "LC_23003_SKILL_MARK" in eng.state.actors["1313"].modifiers
        _emit(eng, "on_turn_start", {"actor": "1412"})   # 刻律回合开始 → 标记消费
        assert "LC_23003_DMG_BOOST" in eng.state.actors["1412"].modifiers
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_SUNDAY_OFF, "23003", "Harmony",
                                    {"postSkillDmgBuff": True})]))

        hand = _cy_hand(0.30)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（下一行动增伤 30%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_switch_off_parity(self, optimizer_driver):
        """钉 false：对方无 buff ≡ 我方无标记消费（基线比等）."""
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1313", "23003"), "wind"))
        _sunday_cast_clean(eng, "1412")
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_SUNDAY_OFF, "23003", "Harmony",
                                    {"postSkillDmgBuff": False})]))

        hand = _cy_hand()
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方基线（标记未消费）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23019PastSelfInTheMirror:
    """镜中故我 S1（星期日→刻律德菈）：终结技后全队增伤 24% 3回合（对方
    FullTeam BOOST 24% 恒开；我方 on_ultimate 钩 all_allies 24%）——BE 60%
    属性段挂星期日面板无读出随挂不测."""

    def test_post_ult_team_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1313", "23019"), "wind"))
        _ult(eng, "1313", "131303", 130.0)          # 星期日终结技 → 全队增伤
        _pop(eng, "1412", "BEATIFIED")              # 蒙福者（CD 件）随摘
        assert "LC_23019_TEAM_DMG" in eng.state.actors["1412"].modifiers
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_SUNDAY_OFF, "23019", "Harmony",
                                    {"postUltDmgBuff": True})]))

        hand = _cy_hand(0.24)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（大招后全队 24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23021EarthlyEscapade:
    """游戏尘寰 S1（星期日→刻律德菈）：假面持有期队友 CR+10%/CD+28%（对方
    FullTeam 双件恒开；我方进战假面+other_allies 光环 enable_if 懒求值）——
    自身 CD+32% 属性段挂星期日面板无读出随挂不测."""

    def test_mask_aura(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1313", "23021"), "wind"))
        assert "LC_23021_MASK" in eng.state.actors["1313"].modifiers
        assert "LC_23021_MASK_AURA" in eng.state.actors["1412"].modifiers
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_SUNDAY_OFF, "23021", "Harmony",
                                    {"maskActive": True})]))

        # CR 双方同封顶 1.0（1.05+0.10 → 1.15 → 1.0）；CD 0.5+0.28=0.78
        hand = _cy_hand(cz=1 + 1.0 * 0.78)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（假面队友双爆）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23034AGroundedAscent:
    """回到大地的飞行 S1（星期日→刻律德菈）：战技/大招指友 → 目标【圣咏】叠层
    增伤 15%×N（钳 3；对方 BOOST 15%×N 滑条——wearer=Sunday 走 SelfAndMemosprite
    落主 C）."""

    def test_hymn_stacks(self, optimizer_driver):
        """星期日战技 ×3 → 圣咏 3 层（45%）→ 普攻比等；@1 层同钉."""
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1313", "23034"), "wind"))
        for _ in range(3):
            _sunday_cast_clean(eng, "1412")
        assert eng.state.actors["1412"].modifiers["LC_23034_HYMN"].stacks == 3
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_SUNDAY_OFF, "23034", "Harmony",
                                    {"dmgBuffStacks": 3})]))

        hand = _cy_hand(0.45)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（圣咏 3 层 45%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_hymn_one_stack(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1313", "23034"), "wind"))
        _sunday_cast_clean(eng, "1412")
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_SUNDAY_OFF, "23034", "Harmony",
                                    {"dmgBuffStacks": 1})]))

        hand = _cy_hand(0.15)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（圣咏 1 层 15%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23038IfTimeWereAFlower:
    """如果时间是一朵花 S1（星期日→刻律德菈）：谕示持有期全队 CD+48%（对方
    FullTeam CD 恒开；我方进战谕示 team 光环）——自身 CD+36%/回能半无读出随挂不测."""

    def test_presage_team_cd(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1313", "23038"), "wind"))
        assert "LC_23038_PRESAGE" in eng.state.actors["1313"].modifiers
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_SUNDAY_OFF, "23038", "Harmony",
                                    {"presage": True})]))

        hand = _cy_hand(cz=1 + 1.0 * 0.98)          # CD 0.5+0.48
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（谕示全队 CD 48%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# 光锥对拍——记忆/虚无/存护 teammates 链（队友=遐蝶 1407/佩拉 1106/杰帕德 1104）
# ===========================================================================

class TestLC23042MayRainbows:
    """愿虹光永驻天空 S1（遐蝶→刻律德菈）：忆灵技后敌方全体承伤 18%（对方
    FullTeam VULNERABILITY 恒开；我方忆灵技钩 all_enemies 18% 2回合）."""

    def test_memo_skill_vulnerability(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1407", "23042"), "wind"))
        _summon_nw(eng)                              # 遐蝶大招 → 死龙（污染件随摘）
        _pop(eng, "1407", "LOST_NETHERLAND")         # 遗世冥域（team 光环锚在遐蝶）
        _pop(eng, "1412", "NETHERWING_ROAR")         # 怒啸（all_allies 逐挂）
        _cast(eng, "1407_netherwing", "1140702")     # 忆灵技 → 敌方承伤
        assert "LC_23042_VULN" in eng.state.actors["e1"].modifiers
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_CASTORICE_OFF, "23042", "Remembrance",
                                    {"vulnerability": True})]))

        hand = _cy_hand(vuln=0.18)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（忆灵技承伤 18%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(
            1.18, rel=REL_TOL)


class TestLC23047WhyDoesTheOceanSing:
    """海洋为何而歌 S1（佩拉→桑博）：魂迷 DoT 易伤 5%×N——**我方待收**（装备者
    施加负面计数无来源过滤通道在案）；EHR+40% 属性段/加速半无伤害读出随挂不测."""

    def test_dot_vuln_divergence(self, optimizer_driver):
        """S1 结构差：DoT 易伤（我方待收在案）→ 钉 4 层：对方/我方 = 1.20."""
        eng, log = _make_logged(_compiled(
            _team_lc_build("1108", "1106", "23047"), "wind"))
        _ult(eng, "1106", "110603", 110.0)           # 佩拉终结技挂 Exposed → 魂迷（80% 期望）
        _pop(eng, "e1", "PELA_EXPOSED")              # 佩拉自身减防件随摘（基线隔离）
        _pop(eng, "1108", "PELA_SECRET_STRATEGY")    # 佩拉行迹全队 EHR+10% 随摘（基线隔离）
        assert "LC_23047_ENTHRALL" in eng.state.actors["e1"].modifiers
        _cast(eng, "1108", "110801")                 # 普攻挂风化（天赋恒中档）
        log.clear()
        eng._tick_dots(eng.state.actors["e1"])       # 声明式跳伤走引擎 A 类结算
        ours = [e["amount"] for e in log
                if e.get("reason") == "dot" and e.get("source") == "1108"]
        theirs = run_optimizer(optimizer_driver, _sampo_tm_opt(
            "dot", teammates=[_tm(_PELA_OFF, "23047", "Nihility",
                                  {"dotVulnStacks": 4, "spdBuff": False})]))

        hand = 0.52 * SA_ATK_W * 1.28 * 0.5 * 0.9 * (0.65 * 1.18)   # EHR 0.18 期望权重
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方风化跳（魂迷标记无数值段——DoT 易伤待收在案）vs 手算")
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(1.20, rel=REL_TOL), (
            "S1：对方 DoT 标签易伤 4 层 20% vs 我方待收")


class TestLC23048EpochEtchedInGoldenBlood:
    """金血铭刻的时代 S1（星期日→真理医生）：战技指友 → 目标战技增伤 54%
    （对方 SKILL 标签 BOOST 54% 默认 SelfAndPet 落主 C；我方 dmg_skill 54%）."""

    def test_skill_dmg_buff(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_lc_build("1305", "1313", "23048"), "imaginary"))
        _sunday_cast_clean(eng, "1305")
        assert "LC_23048_SKILL_DMG" in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130502")
        ours = _hits_of(log, source="1305", action_type="skill")
        theirs = run_optimizer(optimizer_driver, _ratio_tm(
            "skill", teammates=[_tm(_SUNDAY_OFF, "23048", "Harmony",
                                    {"skillDmgBoost": True})]))

        hand = 1.5 * _rt_panel() * 1.54 * 0.5 * 0.9 * (1 + RT_CR * RT_CD)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（战技增伤 54%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.54, rel=REL_TOL)


class TestLC23051ThoughWorldsApart:
    """纵然山河万程 S1（杰帕德→刻律德菈）：终结技后全队增伤 24% 3回合（对方
    FullTeam BOOST 恒开+hasSummons 12% 双方同灭；我方 on_ultimate 钩 all_allies）."""

    def test_redoubt_team_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1104", "23051"), "wind"))
        _ult(eng, "1104", "110403", 100.0)           # 杰帕德终结技 → 卫戍
        assert "LC_23051_REDOUBT" in eng.state.actors["1412"].modifiers
        # REDOUBT_SUMMON 挂载但 enable_if has_summon 懒求值灭（刻律无召唤物——
        # 数值零贡献，伤害比对自证）
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_GEPARD_OFF, "23051", "Preservation",
                                    {"dmgBoost": True})]))

        hand = _cy_hand(0.24)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（卫戍 24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23052ThisLoveForever:
    """爱如此刻永恒 S1（遐蝶→刻律德菈）：诗行（忆灵技对敌）→ 全队 CD+16%
    （对方 CD 16%×(1+60% 双持) 钉 vulnerability=false 双方同灭双持增强；
    空白半（忆灵技对友）在册无 ally 指向载体双方同灭——列注不拍）."""

    def test_poem_team_cd(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _team_lc_build("1412", "1407", "23052"), "wind"))
        _summon_nw(eng)
        _pop(eng, "1407", "LOST_NETHERLAND")         # 遗世冥域（team 光环锚在遐蝶）
        _pop(eng, "1412", "NETHERWING_ROAR")         # 怒啸（all_allies 逐挂）
        _cast(eng, "1407_netherwing", "1140702")     # 忆灵技对敌 → 诗行
        assert "LC_23052_POEM" in eng.state.actors["1407"].modifiers
        # 诗行·全队暴伤（team 光环锚在遐蝶，enable_if 懒求值——面板自证）
        assert _eff(eng, "1412")["crit_dmg"] == pytest.approx(0.5 + 0.16, rel=REL_TOL)
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cy_opt(
            "basic", teammates=[_tm(_CASTORICE_OFF, "23052", "Remembrance",
                                    {"vulnerability": False, "cdBoost": True})]))

        hand = _cy_hand(cz=1 + 1.0 * 0.66)          # CD 0.5+0.16
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（诗行全队 CD 16%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# 光锥对拍——存护载体（砂金 1304；主 LC 链——盲注护盾暴击链，scaling 基差在案）
# ===========================================================================

class TestLC23023InherentlyUnjustDestiny:
    """命运从未公平 S1（砂金）：DEF+40% 属性段（双方同挂——对方 LC properties
    无控制器承载钉进 attacker；我方 on_battle_start 常驻 def_pct）+【供盾暴伤 40%】
    （我方待收——提供护盾无发射点在案；对方无条件=建模近似）+【追加命中易伤
    10%】（对方无条件；我方 after_being_hit follow_up 钩在——盲注满 7 触发天赋
    追击链可直达，本波不拍列注）——双方普攻全 DEF 倍率同构（fixture 过堂勘正⑪
    在案）；杠杆 trace 双方同值（DEF 2303.67 档 floor/round 同档 7）."""

    def test_def_property_panel(self, optimizer_driver):
        """DEF+40% 属性段面板锚（我方 on_battle_start 常驻 vs 对方钉面板——
        防御区无伤害消费=面板互对列注）."""
        eng, log = _make_logged(_compiled(_member_build("1304", lc="23023"),
                                          "imaginary"))
        assert "LC_23023_DEF" in eng.state.actors["1304"].modifiers
        def_panel = (AV_DEF_W + LC23023_DEF) * (1 + AV_TRACE_DEF_PCT + 0.40)
        assert _eff(eng, "1304")["def_"] == pytest.approx(def_panel, rel=REL_TOL)

    def test_baseline_parity(self, optimizer_driver):
        """双方 LC 开关全灭：普攻 1.0×DEF 比等（杠杆 CR+14% 双方同档——
        crit 1+0.19×0.5=1.095；虚数行迹 14.4% 对方钉面板）."""
        eng, log = _make_logged(_compiled(_member_build("1304", lc="23023"),
                                          "imaginary"))
        _cast(eng, "1304", "130401")
        ours = _hit_amounts(log, source="1304")
        theirs = run_optimizer(optimizer_driver, _av_opt(
            "basic", equipment=_lc("23023", "Preservation",
                                   {"shieldCdBuff": False,
                                    "targetVulnerability": False})))

        def_panel = (AV_DEF_W + LC23023_DEF) * (1 + AV_TRACE_DEF_PCT + 0.40)
        hand = 1.0 * def_panel * 0.9 * 0.5 * (1 + 0.19 * 0.5) * 1.144
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方普攻（1.0×DEF×杠杆 14%×虚数 14.4%）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_shield_cd_divergence(self, optimizer_driver):
        """S2 结构差：供盾暴伤（我方待收在案）→ 钉 shieldCdBuff=true
        （targetVulnerability=false 隔离）：对方/我方 = (1+0.19×0.9)/1.095."""
        eng, log = _make_logged(_compiled(_member_build("1304", lc="23023"),
                                          "imaginary"))
        _cast(eng, "1304", "130401")
        ours = _hit_amounts(log, source="1304")[0]
        theirs = run_optimizer(optimizer_driver, _av_opt(
            "basic", equipment=_lc("23023", "Preservation",
                                   {"shieldCdBuff": True,
                                    "targetVulnerability": False})))

        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1 + 0.19 * 0.9) / 1.095, rel=REL_TOL)

    def test_vulnerability_divergence(self, optimizer_driver):
        """S3 结构差：追加命中易伤（对方无条件 VULNERABILITY 10%；我方钩在但
        FUA 触发链本波不拍——对方/我方 = (1+0.19×0.9)×1.10/1.095）."""
        eng, log = _make_logged(_compiled(_member_build("1304", lc="23023"),
                                          "imaginary"))
        _cast(eng, "1304", "130401")
        ours = _hit_amounts(log, source="1304")[0]
        theirs = run_optimizer(optimizer_driver, _av_opt(
            "basic", equipment=_lc("23023", "Preservation",
                                   {"shieldCdBuff": True,
                                    "targetVulnerability": True})))

        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1 + 0.19 * 0.9) * 1.10 / 1.095, rel=REL_TOL), (
            "S3 复合：对方无条件 CD 40%+易伤 10% vs 我方双段缺（待收/不拍在案）")


# ===========================================================================
# 位面饰品对拍——dyn 阈值件（301/302/303/304/307/310/319/325）
# ===========================================================================

class TestOrnament301SpaceSealing:
    """太空封印站（黑塔）：atk+12%（p2c 双方 stat 同值）+SPD≥120 → atk+12%
    （对方 dyn 读终值 SPD 面板 buffDynamic 平值；我方 enable_if 懒求值）."""

    def test_spd120_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="301", pieces=2), "ice"))
        _inject(eng, "1013", "XC_SPD", {"spd": 25.0})   # 100 → 125 ≥120
        assert "SET_301_SPD120_ATK" in eng.state.actors["1013"].modifiers
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK, extra_attacker={"spd": 125.0},
            equipment=_relic("301", 2, {})))

        hand = 1.0 * HT_ATK * 1.24 * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（SPD 档 atk+12%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(HT_ATK * 1.24, rel=REL_TOL), (
            "对方 dyn 平值面板回显（p2c 12%+dyn 12%）")


class TestOrnament302FleetOfAgeless:
    """不老者的仙舟（黑塔）：hp+12%（无伤害读出）+SPD≥120 → 攻击+8%（对方 dyn
    wearer +8%×baseAtk 平值；我方 team 光环 atk_pct 8% enable_if——wearer 读出
    口径同值，team 语义差在案）."""

    def test_spd120_team_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="302", pieces=2), "ice"))
        _inject(eng, "1013", "XC_SPD", {"spd": 25.0})
        assert "SET_302_TEAM_ATK" in eng.state.actors["1013"].modifiers
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK, extra_attacker={"spd": 125.0},
            equipment=_relic("302", 2, {})))

        hand = 1.0 * HT_ATK * 1.08 * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（SPD 档攻+8%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament303PanCosmic:
    """泛银河商业公司（桑博）：EHR+10%（面板锚）+攻击=当前 EHR×25%（上限 25%）
    （双方同式连续口径——对方 dyn CONTINUOUS min(0.25, 0.25×EHR)×baseAtk；
    我方 stat_exprs clamp(EHR×0.25, 0, 0.25)）."""

    def test_ehr_to_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1108", set_id="303", pieces=2), "wind"))
        _inject(eng, "1108", "XC_EHR", {"effect_hit": 0.62})   # 0.18+0.1+0.62=0.90
        _cast(eng, "1108", "110801")
        ours = _hit_amounts(log, source="1108")
        theirs_sc = _sampo_tm_opt("basic", teammates=[], extra_attacker={
            "effect_hit": 0.80})                          # 白值侧（p2c 10% 走对方 c→x）
        theirs_sc["equipment"] = _relic("303", 2, {})
        theirs = run_optimizer(optimizer_driver, theirs_sc)

        hand = 1.0 * (SA_ATK_W * 1.505) * 0.5 * 0.9 * SA_CZ   # atk 池 1.28+0.225
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（EHR 0.9 转攻 22.5%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament304Belobog:
    """筑城者的贝洛伯格（杰帕德）：def 15%+EHR≥50% → def+15%（对方 dyn 读终值
    EHR 面板 buffDynamic 0.15×baseDef；我方 enable_if def_pct）——Grit 防转攻
    0.35×DEF 读出。p2c 半（无注入）比等；dyn 半钉 S6（条件件互观察口径差——
    对方 dyn 件与 grit 转化互读全面板 vs 我方 §4.16 条件件彼此不可互观察，
    我方 grit 读无条件面板=不含 dyn 件）."""

    def test_p2c_def_grit(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1104", set_id="304", pieces=2), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})   # Grit 挂载
        def_panel = GP_DEF_W * (1.125 + 0.15)              # dyn 未激活（EHR 0）
        atk = GP_ATK_W + 0.35 * def_panel
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": GP_ATK_W, "def": GP_DEF_W},
            extra_attacker={"atk": GP_ATK_W, "def": GP_DEF_W * 1.125},
            equipment=_relic("304", 2, {})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")

        hand = 1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方（p2c DEF 15% → Grit 转化）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_dyn_def_divergence(self, optimizer_driver):
        """S6 结构差：dyn DEF+15%（EHR 0.6 档）——对方 grit 读全面板（DEF 933.21）
        vs 我方 grit 读无条件面板（DEF 834.98，§4.16 条件件互观察禁则）→
        对方/我方 = (GP_ATK_W+0.35×933.21)/(GP_ATK_W+0.35×834.98)."""
        eng, log = _make_logged(_compiled(
            _member_build("1104", set_id="304", pieces=2), "ice"))
        _inject(eng, "1104", "XC_EHR", {"effect_hit": 0.60})   # SET_304 懒激活
        _emit(eng, "on_turn_start", {"actor": "1104"})   # Grit 挂载
        assert "SET_304_EHR50_DEF" in eng.state.actors["1104"].modifiers
        def_panel = GP_DEF_W * (1.125 + 0.15 + 0.15)
        atk = GP_ATK_W + 0.35 * def_panel
        theirs = run_optimizer(optimizer_driver, _gp_opt(
            "basic", extra_base={"atk": GP_ATK_W, "def": GP_DEF_W},
            extra_attacker={"atk": GP_ATK_W, "def": GP_DEF_W * 1.125,
                            "effect_hit": 0.60},
            equipment=_relic("304", 2, {})))
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")[0]

        def_uncond = GP_DEF_W * (1.125 + 0.15)          # 我方 grit 读无条件面板
        hand_ours = 1.0 * (GP_ATK_W + 0.35 * def_uncond) * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE)
        assert ours == pytest.approx(hand_ours, rel=REL_TOL), (
            "我方（dyn DEF 激活但 grit 读无条件面板）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE), rel=REL_TOL), (
            "对方 vs 手算（grit 读全面板）")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (GP_ATK_W + 0.35 * def_panel) / (GP_ATK_W + 0.35 * def_uncond),
            rel=REL_TOL)


class TestOrnament307Talia:
    """盗贼公国塔利亚（白厄）：BE 16%+SPD≥145 → BE+20%（对方 dyn 读终值 SPD
    面板；我方 enable_if——BE 面板互对+击破段 ×1.36 vs 手算（对方 kind=character
    无击破段不可见，119 先例）."""

    def test_spd145_be(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1408", set_id="307", pieces=2), "physical",
            enemies=_fragile_toughness("physical")))
        _inject(eng, "1408", "XC_SPD", {"spd": 145.0 - 99.0})
        assert "SET_307_SPD145_BREAK" in eng.state.actors["1408"].modifiers
        _cast(eng, "1408", "140801")
        breaks = _break_amounts(log, "1408")
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", extra_attacker={"spd": 145.0},
            equipment=_relic("307", 2, {})))

        assert _eff(eng, "1408")["break_effect"] == pytest.approx(0.36, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.36, rel=REL_TOL), "BE 面板互对"
        assert breaks[0] == pytest.approx(BREAK_BASE_10_PHY * 1.36, rel=REL_TOL), (
            "我方击破段（BE 36% 池）vs 手算")
        hand = 1.0 * PH_ATK * 1.5 * Z_PH
        assert _hit_amounts(log, source="1408")[0] == pytest.approx(hand, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)


class TestOrnament310BrokenKeel:
    """折断的龙骨（黑塔）：效果抵抗 10%+RES≥30% → 全队 CD+10%（对方 dyn 读终值
    RES 面板 FullTeam buffDynamic 0.10；我方 team 光环 crit_dmg 0.1 enable_if）."""

    def test_res30_team_cd(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="310", pieces=2), "ice"))
        _inject(eng, "1013", "XC_RES", {"effect_res": 0.25})   # 0+0.1+0.25=0.35 ≥0.3
        assert "SET_310_TEAM_CRIT_DMG" in eng.state.actors["1013"].modifiers
        _ult(eng, "1013", "101303", 120.0)
        ours = _hit_amounts(log, source="1013")
        sc = _herta_opt("ult", atk=HT_ATK, extra_attacker={"effect_res": 0.25},
                        equipment=_relic("310", 2, {}))
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 2.0 * HT_ATK * 0.5 * 0.9 * (1 + 0.05 * 0.6)     # CD 0.5+0.1
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（RES 档全队 CD+10%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament319BoneCollections:
    """谧宁拾骨地（遐蝶）：hp 12%+HP≥5000 → CD+28%（对方 dyn 读终值 HP 面板
    buffDynamic 0.28；我方 enable_if）."""

    def test_hp5000_cd(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1407", set_id="319", pieces=2), "quantum"))
        _inject(eng, "1407", "XC_HP_FLAT", {"hp": 3500.0})
        assert "SET_319_MEMO_CRITDMG" in eng.state.actors["1407"].modifiers
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        hp_panel = CA_HP * 1.12 + 3500.0                       # 5523.26 ≥5000
        sc = _ca_opt("basic", lc_hp=0.0,
                     extra_attacker={"hp": CA_HP + 3500.0},   # 白值+注入（p2c 12% 走 c→x）
                     equipment=_relic("319", 2, {}))
        sc["conditionals"]["memospriteActive"] = False
        sc["conditionals"]["teamDmgBoost"] = False
        theirs = run_optimizer(optimizer_driver, sc)

        hand = (0.5 * hp_panel * (1 + CA_Q) * 0.5 * 0.9
                * (1 + CA_CR * (CA_CD + 0.28)))
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（HP 档 CD+28%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament325Punklorde:
    """零号关卡朋克洛德（火花）：欢愉度 8%+欢愉度≥40%/80% → CD 20%/32%
    （对方 dyn 读终值 ELATION 面板两档；我方 stat_exprs 三元分档）."""

    def test_elation_tiers(self, optimizer_driver):
        for el, tier_cd in ((0.48, 0.20), (0.81, 0.32)):
            eng, log = _make_logged(_compiled(
                _member_build("1501", set_id="325", pieces=2), "fire"))
            _pin_pool_gain(eng, "1501", 30.0)
            _pin_banger(eng, "1501", 60.0)
            _inject(eng, "1501", "XC_ELATION", {"elation": el - SP_EL - 0.08})
            assert "SET_325_CRITDMG" in eng.state.actors["1501"].modifiers
            log.clear()
            _cast(eng, "1501", "150120")
            ours = sum(_hit_amounts(log, source="1501"))
            sc = _opt_sparxie("elation_skill")
            sc["attacker"]["elation"] = el - 0.08            # p2c 8% 走对方 c→x
            sc["equipment"] = _relic("325", 2, {})
            theirs = run_optimizer(optimizer_driver, sc)

            cz = 1 + SP_CR * (SP_CD_P30 + tier_cd)
            hand = _el(5.5, 30, cz, el=el)
            assert ours == pytest.approx(hand, rel=REL_TOL), (
                f"我方（欢愉度 {el:.2f} 档 CD+{tier_cd:.0%}）vs 手算")
            assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
            assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# 位面饰品对拍——p2x 机制件（305/313/314/315/318/321/324/326/328）
# ===========================================================================

class TestOrnament305CelestialDifferentiator:
    """星体差分机（真理）：CD 16%+CD≥120% → CR+60% 至首次攻击（对方 p2x 读
    x.c.a[CD]——set_threshold_cd 槽直钉；我方 on_battle_start 快照条件——setup
    前注入）——首攻前比等；摘除窗口对方无概念 → 第 2 击钉 S4."""

    def _engine(self):
        eng, log = _make_logged(_compiled(
            _member_build("1305", set_id="305", pieces=2), "imaginary"))
        _inject(eng, "1305", "XC_CD", {"crit_dmg": 0.75})   # 注入后重发开局事件
        _emit(eng, "on_battle_start", {"encounter": "x"})  # （快照条件补触发——
        # 角色行迹走 stat_effects 非钩，重发无副作用；305 钩条件 crit_dmg≥1.2 方真）
        return eng, log

    def test_first_attack_crit(self, optimizer_driver):
        eng, log = self._engine()
        assert "SET_305_CRIT_RATE" in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        sc = _ratio_opt("basic", cd=0.5 + 0.75,
                        equipment=_relic("305", 2,
                                         {"enabledCelestialDifferentiator": True}))
        sc["set_threshold_cd"] = 1.25                       # c.a[CD] 档直钉（≥1.2 触发）
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 1.0 * _rt_panel() * 0.5 * 0.9 * (1 + 0.77 * 1.41)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方首攻（CD≥120% → CR+60%）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_removal_window_divergence(self, optimizer_driver):
        """S4 结构差：摘除窗口（官方「持续到施放首次攻击后结束」——我方摘除；
        对方恒开）→ 第 2 击对方/我方 = (1+0.77×1.41)/(1+0.17×1.41)."""
        eng, log = self._engine()
        _cast(eng, "1305", "130501")
        log.clear()
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")[0]
        sc = _ratio_opt("basic", cd=0.5 + 0.75,
                        equipment=_relic("305", 2,
                                         {"enabledCelestialDifferentiator": True}))
        sc["set_threshold_cd"] = 1.25
        theirs = run_optimizer(optimizer_driver, sc)

        assert ours == pytest.approx(
            1.0 * _rt_panel() * 0.5 * 0.9 * (1 + 0.17 * 1.41), rel=REL_TOL), (
            "我方第 2 击（CR+60% 已摘除）vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (1 + 0.77 * 1.41) / (1 + 0.17 * 1.41), rel=REL_TOL)


class TestOrnament313Sigonia:
    """无主荒星茨冈尼亚（黑塔）：CR 4%+击杀叠 CD 4%×N（钳 10；对方 value 滑条
    =层数；我方 on_kill 钩 stat_exprs 活读层）."""

    def test_kill_stacks(self, optimizer_driver):
        enemies = _dummy("e1", "ice") + [
            {"actor_id": f"e{i}", "name": f"假人{i}", "hp": 100.0, "spd": 100,
             "atk": 1000, "def": 1000, "max_toughness": 9999, "weakness": ["ice"]}
            for i in (2, 3, 4)]
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="313", pieces=2), "ice", enemies=enemies))
        for i in (2, 3, 4):
            _cast(eng, "1013", "101301", target=f"e{i}")   # 击杀 → 叠层
        assert eng.state.actors["1013"].modifiers["SET_313_KILL_CRIT_DMG"].stacks == 3
        log.clear()
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK,
            equipment=_relic("313", 2, {"valueSigoniaTheUnclaimedDesolation": 3})))

        hand = 1.0 * HT_ATK * 0.5 * 0.9 * (1 + 0.09 * 0.62)   # CR 0.09 CD 0.62
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（击杀 3 层 CD+12%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament314Izumo:
    """出云显世与高天神国（真理）：atk 12%+同命途队友≥1 → CR+12%（对方 p2x
    开关（countTeamPath 闸在 UI 层）；我方 count_team(path)≥2 闸——双人队两侧
    同开）."""

    def test_same_path_crit(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            {"build": {"team": [
                {"character_template": "1305", "level": 80,
                 "relics": {f"slot{i}": {"set_id": "314"} for i in range(2)}},
                {"character_template": "1206", "level": 80},
            ], "policy": _POLICY}}, "imaginary"))
        assert "SET_314_CRITRATE" in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        sc = _ratio_opt("basic", equipment=_relic(
            "314", 2, {"enabledIzumoGenseiAndTakamaDivineRealm": True}))
        sc["teammates"] = [{"path": "Hunt"}]
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 1.0 * (RT_ATK * 1.40) * 0.5 * 0.9 * (1 + 0.29 * 0.5)   # atk 池 1.28+0.12
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（同命途 CR+12%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament315Duran:
    """奔狼的都蓝王朝（真理）：功勋叠层——追击+5%×N/满 5 层 CD+25%（对方
    value 滑条恒满档；我方 after_being_hit follow_up 钩叠层（315 勘正④改道）——
    段时序：叠层在追击伤害结算后=当次不吃）→ 第 6 发 @5 层比等；第 5 发钉 S5."""

    def test_merit_fifth_fua(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", set_id="315", pieces=2), "imaginary"))
        for _ in range(6):
            _cast(eng, "1305", "130502")               # 战技×6 → 追击×6
        fuas = _hits_of(log, source="1305", action_type="follow_up")
        assert len(fuas) == 6
        assert eng.state.actors["1305"].modifiers["SET_315_MERIT"].stacks == 5
        sc = _ratio_opt("fua", conditionals={"summationStacks": 6},
                        equipment=_relic("315", 2,
                                         {"valueDuranDynastyOfRunningWolves": 5}))
        theirs = run_optimizer(optimizer_driver, sc)

        # 第 6 发（@5 层双方比等）：归纳 6 层 + 功勋 5 层（追击 25%+CD 25%）
        hand6 = 2.7 * _rt_panel() * 1.25 * 0.5 * 0.9 * (1 + 0.32 * 1.05)
        assert fuas[5] == pytest.approx(hand6, rel=REL_TOL), (
            "我方第 6 发追击（@5 层满功勋）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand6, rel=REL_TOL)
        assert fuas[5] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

        # S5 第 5 发（我方 @4 层当次不吃 vs 对方滑条恒 5 层）：
        # 对方/我方 = (1.25×1.336)/(1.20×1.22125)
        hand5_ours = 2.7 * _rt_panel() * 1.20 * 0.5 * 0.9 * (1 + 0.295 * 0.75)
        assert fuas[4] == pytest.approx(hand5_ours, rel=REL_TOL), (
            "我方第 5 发追击（@4 层——叠层在伤害结算后）vs 手算")
        assert theirs["hits"][0]["damage"] / fuas[4] == pytest.approx(
            (1.25 * 1.336) / (1.20 * 1.22125), rel=REL_TOL)


class TestOrnament318BananPark:
    """奇想蕉乐园（遐蝶）：CD 16%+召唤物在场 → CD+32%（对方 p2x 开关；我方
    enable_if has_summon）."""

    def test_summon_cd(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1407", set_id="318", pieces=2), "quantum"))
        _summon_nw(eng)
        assert "SET_318_SUMMON_CRITDMG" in eng.state.actors["1407"].modifiers
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        sc = _ca_opt("basic", lc_hp=0.0,
                     equipment=_relic("318", 2,
                                      {"enabledTheWondrousBananAmusementPark": True}))
        theirs = run_optimizer(optimizer_driver, sc)

        hand = (0.5 * CA_HP * (1 + CA_Q + 0.1) * 0.5 * 0.9
                * (1 + CA_CR * (CA_CD + 0.16 + 0.32)) * 1.2)   # p2c 16%+条件 32%
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（召唤物 CD+32%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament321Arcadia:
    """妖精织梦的乐园（黑塔）：队伍数≠4 → 每差 1 名增伤 12%/9%（对方 value
    滑条=队伍数（arcadiaSetIndexToDmg 表）；我方 count($team.actor_id) 活读）→
    单人队（count=1 → +36%）普攻比等."""

    def test_solo_team_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="321", pieces=2), "ice"))
        assert "SET_321_2PC_DMG" in eng.state.actors["1013"].modifiers
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK,
            equipment=_relic("321", 2, {"valueArcadiaOfWovenDreams": 1})))

        hand = 1.0 * HT_ATK * 1.36 * Z                  # count=1 → min(3,3)×0.12
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（单人队 +36%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament324Tengoku:
    """天国@直播间（真理）：CD 16%+单回合耗点≥3 → CD+32% 3回合（对方 p2x 开关
    恒开=建模近似；我方 before_consume 计数≥3 挂——同事件快照第 4 耗触发）."""

    def test_sp_consume_cd(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", set_id="324", pieces=2), "imaginary"))
        for _ in range(4):
            _cast(eng, "1305", "130502")               # 耗点 ×4（第 4 耗触发满堂彩）
        assert "SET_324_CRITDMG" in eng.state.actors["1305"].modifiers
        _pop(eng, "1305", "SUMMATION")                 # 归纳层随摘（战技叠层污染隔离）
        log.clear()
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", equipment=_relic("324", 2, {"enabledTengokuLivestream": True})))

        hand = 1.0 * _rt_panel() * 0.5 * 0.9 * (1 + 0.17 * 0.98)   # CD 0.5+0.16+0.32
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（耗点≥3 → CD+32%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament326CityOfConvergingStars:
    """千星荟萃之城（黑塔）：追击→atk+24% 2回合+击杀→全队 CD+12%（对方 value
    滑条 0-3（1=追击攻/2=击杀 CD/3=双件）；黑塔击杀跨线追击天紧张追击半——
    value=3 双件同挂）."""

    def test_kill_team_cd(self, optimizer_driver):
        enemies = _kill_enemies("ice")
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="326", pieces=2), "ice", enemies=enemies))
        _cast(eng, "1013", "101301", target="e2")      # 击杀 → 跨线追击（atk+24%）+全队 CD
        assert "SET_326_2PC_TEAM_CRITDMG" in eng.state.actors["1013"].modifiers
        assert "SET_326_2PC_ATK" in eng.state.actors["1013"].modifiers
        log.clear()
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK,
            equipment=_relic("326", 2, {"valueCityOfConvergingStars": 3})))

        hand = 1.0 * (HT_ATK * 1.24) * 0.5 * 0.9 * (1 + 0.05 * 0.62)   # 攻+24% CD+12%
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（击杀双件）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestOrnament328CosmicInstitute:
    """寰宇生研院（长夜月）：能量上限≥200 → 每超 1 点增伤 0.2%（上限 32%）
    （对方 p2x 读 context.baseEnergy 场景槽同式；我方 on_battle_start max_energy
    活读——长夜月 240 → 8%）."""

    def test_energy_cap_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1413", set_id="328", pieces=2), "ice"))
        assert "SET_328_2PC_DMG" in eng.state.actors["1413"].modifiers
        _cast(eng, "1413", "141301")                   # 天黑黑+天赋 CD 喂出
        log.clear()
        _cast(eng, "1413", "141301")
        ours = _hit_amounts(log, source="1413")
        sc = _opt_evernight("basic", cond={"talentMemoCdBuff": True})
        sc["base_energy"] = 240.0
        sc["equipment"] = _relic("328", 2, {})
        theirs = run_optimizer(optimizer_driver, sc)

        hand = (0.5 * EV_HP * 0.5 * 0.9
                * (1 + EV_CR * (EV_CD + 0.15 + 0.6)) * 1.58)   # 池 1.5+0.08 加算
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方（能量 240 → 增伤 8% 入 1.5 池加算）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.58, rel=REL_TOL)


# ===========================================================================
# 位面饰品对拍——p2t 终端件（306/309/311；evaluateTerminalSetConditionals 镜像）
# ===========================================================================

class TestOrnament306InertSalsotto:
    """停转的萨尔索图（黑塔）：CR 8%+当前 CR≥50% → 终结技/追击+15%（对方 p2t
    读终值 CR 面板 ULT|FUA BOOST；我方 enable_if dmg_ultimate/follow_up）——
    p2t 通道首证."""

    def test_cr50_ult_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="306", pieces=2), "ice"))
        _inject(eng, "1013", "XC_CR", {"crit_rate": 0.50})   # 0.05+0.5+0.08=0.63
        assert "SET_306_ULT_FUA_DMG" in eng.state.actors["1013"].modifiers
        _ult(eng, "1013", "101303", 120.0)
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "ult", atk=HT_ATK, extra_attacker={"cr": 0.55},
            equipment=_relic("306", 2, {})))

        hand = 2.0 * HT_ATK * 1.15 * 0.5 * 0.9 * (1 + 0.63 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（CR 档大招+15%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.15, rel=REL_TOL), "对方 p2t ULT|FUA BOOST 回显（终端件通道自证）"


class TestOrnament309RutilantArena:
    """繁星竞技场（真理）：CR 8%+当前 CR≥70% → 普攻/战技+20%（对方 p2t BASIC|
    SKILL BOOST；我方 dmg_basic/skill）——p2t 证②."""

    def test_cr70_basic_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", set_id="309", pieces=2), "imaginary"))
        _inject(eng, "1305", "XC_CR", {"crit_rate": 0.48})   # 0.17+0.48+0.08=0.73
        assert "SET_309_BASIC_SKILL_DMG" in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", cr=0.65, equipment=_relic("309", 2, {})))

        hand = 1.0 * _rt_panel() * 1.20 * 0.5 * 0.9 * (1 + 0.73 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方（CR 档普攻+20%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.20, rel=REL_TOL)


class TestOrnament311Glamoth:
    """苍穹战线格拉默（真理）：atk 12%+SPD≥135/160 → 增伤 12%/18%（对方 p2t
    读终值 SPD 面板分档 BOOST；我方 stat_exprs 三元分档）——p2t 证③."""

    def test_spd_tiers(self, optimizer_driver):
        for spd, tier in ((140.0, 0.12), (165.0, 0.18)):
            eng, log = _make_logged(_compiled(
                _member_build("1305", set_id="311", pieces=2), "imaginary"))
            _inject(eng, "1305", "XC_SPD", {"spd": spd - RT_SPD})
            assert "SET_311_SPD_TIER_DMG" in eng.state.actors["1305"].modifiers
            _cast(eng, "1305", "130501")
            ours = _hit_amounts(log, source="1305")
            theirs = run_optimizer(optimizer_driver, _ratio_opt(
                "basic", spd=spd, equipment=_relic("311", 2, {})))

            hand = 1.0 * (RT_ATK * 1.40) * (1 + tier) * 0.5 * 0.9 * (1 + RT_CR * RT_CD)
            assert ours == pytest.approx([hand], rel=REL_TOL), (
                f"我方（SPD {spd:.0f} 档增伤 {tier:.0%}）vs 手算")
            assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
            assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
