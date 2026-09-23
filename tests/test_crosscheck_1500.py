"""L2 角色级对拍（BACKLOG B22 名册扩拍第五波）：1500 号段剩余 5 角色各命途混编——
姬子•启行 1510（火/智识，HimekoNova——owner 版本更新点名本波头号）/ 千冶•刃 1507
（火/虚无，MortenaxBlade——HP 倍率结界族）/ 远坂凛 1508（量子/智识，RinTohsaka——
UNIQUE 联携族）/ 吉尔伽美什 1509（雷/毁灭，Gilgamesh——兴致经济+UNIQUE 联携族）/
不死途 1504（雷/巡猎，Ashveil——饲饵标记+婪酣追加族）。逐段伤害 == hsr-optimizer
角色实现整链伤害（rel_tol 1e-4；双锚=对方+手算，对不上的按惯例钉结构差数值自证）。

SP 消歧在案（AGENTS.md 规矩）：姬子•启行（1510）≠姬子（1003）、千冶•刃（1507）≠刃
（1205）——引用机制全带 ID。1504 英文名核实：对方 1500/Ashveil.ts id='1504' ↔
StarRailRes 1504 不死途 ✓（对得上才拍）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character"（技种注册法——本波
5 角色全走已注册 basic/skill/ult/fua/unique，无新技种；CHARACTER_REGISTRY +5 import
+5 登记）。我方路径：真模板（tests/fixtures 人工根）→ 编译 → CombatEngine 钉资源
（源能/助战次数/Beam 计数/充能/兴致/婪酣/宝石能量）→ _cast/_fire_ultimate/fire_assist →
bus on_hp_decrease 逐段记录仪（setup 前订阅，L2 先例）。

统一口径（两侧一致，沿用前几波）：星魂钉死 E0、行迹满级、无光锥无遗器、假人 lvl80
def 1000（防御区 0.5——减防件另算）、匹配弱点（抗性区 1.0，抗穿件另算）、未击破
0.9、期望暴击。HP 倍率族（1507）钉 max_hp 同构。对方 ATK_P 条件件（秉持优雅 1.5/
王霸竞逐 0.2+溢出/王来承认 E1 0.6）走 base=真白值、attacker=扣除对方 precompute
新增量后的钉值——applyPercentStats 白值换算后双方终值对齐（前几波无 ATK_P 条件件
同槽先例，本波首接）。

===========================================================================
姬子•启行 1510 buff 状态映射表（对方 content 开关 ↔ 我方模板触发）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
navigatorsSemaphore（true）    151002 战技→NAV_SEMAPHORE 全队增伤 0.2·3 回合    未放战技钉 false；
                                                                            放战技后钉 true 比等
selfUseAssistSkill（true）     助战三技姬子使用分支（#4 全体+#5×#6 随机段）      钉 true（模板内唯一
                                                                            施放者=姬子本人）
assistSkillBuff（true）        天赋 151004 常驻暴伤 0.8/全抗穿 0.2              钉 true（双方常驻同值）
companionVerdict（true）       151025→COMPANION_VERDICT 增伤 1.0+终结技增伤 1.0  未放 151025 钉 false；
                                                                            放后钉 true 比等
companionDecimation（false）   151026→COMPANION_DECIMATION 全队暴伤 1.0        本波未拍（E0 默认
                                                                            false 两侧同灭）
e4ResPen/e6（true）            星魂（E0 门控同灭）                             E0 钉 true 无害
（无开关）终结技 Starblazer 双模式  state_config「拓星者」形态：Beam（计数资源    对方 ashblazing 聚合单发
                               6 次）/Pulse（耗源能）形态内普攻位二选一，         （P,B×3,P,B×3,autoP,F 混插
                               policy 按 action_id 选招；Beam 耗尽→自动           档 10.32——同序列对我方
                               Pulse→Final Hit；全场致命/锁血（damageable_        8.52，差=R-HN1 段数读法，
                               enemies()==0）→立即 Final Hit；子段全             见下）
                               action_type ultimate 钩承载（Beam 0.32/
                               Pulse s3 1.4/Final 2.4）
（无开关）1510103② 随机段 +0.30 (res_source_energy>=3 ? 0.3:0) 表达式随档      对方 a6Multiplier 0.30
                                                                            同值——段值双方一致，
                                                                            差只在段数（R-HN1）

===========================================================================
千冶•刃 1507 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
infiniteFuryActive（true）     INFINITE_FURY（150703 闩+双暴 0.2/0.6 modifier） 常态钉 false；150703 后
                                                                            钉 true 比等
ultZone（true）                150703 结界主链（BALEFIRE_BIND 减防 0.3/易伤     常态钉 false；150703 后
                               0.5 + MORTENAX_ZONE_TEAM_DMG 全队增伤 0.5）    钉 true——大行迹3#3 分叉
                                                                            差=R-MB1（见下）
e1ResPen/e2FuaDmgBoost/e4DmgBoost/e6EnhancedUlt  星魂（E0 门控同灭）           E0 钉 true 无害
（无开关）虚无计数分叉           大行迹1507103 #3：无其他虚无→自身增伤 0.75      我方待收（作用域乘区键
                               （我方 1507103 只收 #1 全队 0.5）              缺）——R-MB1 钉 1.5 倍；
                                                                            _inject 0.75 后全链全等
（无开关）FUA 双标签            对方 FUA=SKILL|FUA 双 type（150709「视为追加    结界外类型桶全中性——
                               攻击的战技」）=战技倍率 1.68                  倍率差=R-MB2（见下）

===========================================================================
远坂凛 1508 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
enhancedSkill（true）          150802↔150809 available_if 互斥（gem 15 闸）     普通钉 false；强化钉 true
skillBounces 0-33（10）        150809 弹射循环——**待收**（动态循环结算通道缺，  钉 10 钉 R-RT3 结构差
                               值在案：每跳 0.9×ATK）                         （见下）
enhancedSkillSpConsumed（11）  SP 消耗（不伤）                                 钉 0 无害
talentCdBuff（true）           天赋 150804 SP 流转暴伤 0.7——**待收**（载荷无    常态钉 false 比等；钉 true
                               消费主体字段，1306 星历②同族）               钉 R-RT1 结构差；_inject
                                                                            0.7 后全等
elegantConduct（true）         1508101 秉持优雅（ATK+150%/量子穿抗 0.15/SP      钉 true——base/attacker
                               上限 7 常驻）                                 拆钉首接（ATK_P 换算链）
ladylikePoise（true）          1508102 淑女风范 SPD+20%（不伤）                钉 false 保面板干净
ultDmgTakenDebuff（true）      150803 全体易伤 0.2×3 回合（action 后挂——本发    终结技本发钉 false 比等；
                               不吃——文本序先伤后易伤）                      钉 true 钉 R-RT2 时序差；
                                                                            后续行动双方同吃比等
e2Buffs/e4TalentCdStacks/e6ResPen  星魂（E0 门控同灭）                        E0 钉 true 无害
（无开关）150805 联携追击        Archer 侧触发链待收（双通道缺）                对方 solo 同灭（archerInTeam
                                                                            闸）——双方无段一致

===========================================================================
吉尔伽美什 1509 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
herosHauteurStacks 0-6（6）    1509102 HERO_HAUTEUR 暴伤层（0.25/层，兴致       开局钉 0 比等；开大后
                               获得 +N=+N 层，本场累计）                     兴致+2=2 层钉 2 比等
interestSpdStacks 0-20（10）   INTEREST_SPD 兴致速度（不伤）                   钉 0 保面板干净
kingsAcknowledgement（true）   150902 王来承认 def_pen 0.3·3 回合              未放战技钉 false；放后
                                                                            钉 true 比等
kingsBurden（true）            150904 王来背负终结技增伤 0.4（**队友开大**才     solo 我方不发——对方常开
                               挂，排自身在案）                              近似钉 R-GG2 结构差
a6TeamBuff（true）             1509103 王霸的竞逐基础半（team atk 0.2/暴伤      钉 true 比等（base_energy
                               0.2）；溢出段（能量上限>140 逐目标加成）待收    缺省=0 档）；钉 360 钉
                                                                            R-GG3 结构差
goldenRuleStacks（2）/e6ResPen 星魂（E0 门控同灭）                             E0 钉 true/无害
（无开关）150905 连携追击        计数 8（吉/Saber 攻击）→雷 4.0 AoE——solo 吉     对方 UNIQUE solo 空段
                               本人计数在案（官方双主体含吉）                （Saber 依赖建模）——R-GG1
（无开关）终结技 10 段弹射       on_action 钩 10×1.0 随机（expected 取首）       对方聚合 4.0+1.0×10=14.0
                                                                            单发——总和比等，段数差在案

===========================================================================
不死途 1504 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
baitActive（true）             饲饵存在性减防 BAIT_DEFR（敌方 def_pct −0.4 ≡     钉 true 比等（减防≡防穿
                               我方防穿 0.4——L1 公式层已互对）               同值，开战自动标记）
targetBait（true）             战技目标已是饲饵→追加段 1.0+返 1 SP             钉 true——我方 2 段 vs
                                                                            对方聚合单发 3.0，段数差在案
enhancedFua（false）           终结技链强化 FUA（150404 #4=2.0）                常态钉 false（2.0 比等）；
gluttonyStacks 0-12（12）      婪酣层（影肢 0.8+0.1×层 现场追值）               钉 4 钉 R-AV2 结构差
e1DmgVulnerability/e1TargetHpBelow50/e4AtkBuff/e6GluttonyGainedStacks  星魂    E0 钉 true 无害
（E0 门控同灭）
（无开关）头狼② FUA 暴伤 +80%   **待收**（类型分域暴伤键缺——hit_condition        对方 mutual 常开——R-AV1
                               scoped 不载 crit_dmg）                       钉 FUA 段暴击区比
（无开关）天赋反追加 150404      我方其他目标攻击饲饵才触发（solo 无队友不发）    对方 FUA 静态行动——本体
                                                                            倍率经终结技链强化 FUA 同
                                                                            模比等（2.0 同档）
（无开关）强化 FUA 连杀循环      婪酣≥4 耗 4 追加 1 段（循环「直至<4」待收——     对方 floor(层/4) 段聚合+
                               hook 无循环原语，单段建模）                    平均化层读——R-AV2（见下）

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注值，任一侧改动触红）
===========================================================================
R-HN1 1510 终结技 Starblazer Pulse 随机段数读法差（2026-09-23 双模式改建核销改写）：
   ① 序列模型差已消解——官方双模式（形态内玩家 Beam/Pulse 二选一）我方已建
   （state_config「拓星者」形态），对方 Pulse 混插序列（P,B×3,P,B×3,autoP,F）
   是合法玩家选择之一，两侧同序列可比（旧「对方 Pulse×3 混插 vs 我方固定
   Beam×6→Pulse×1→Final」双读法捆绑解除，258/143 钉差作废）；② 段数读法差仍在：
   对方 bounce=源能 3 段（「每消耗 1 点→1 段」含 AoE 本点读法）vs 官方 151009
   文本「消耗 1 点…当前源能大于 1 点时，每消耗 1 点额外 1 段」=AoE 耗 1 余 (s−1) 段
   （中英双源一致，对方每 Pulse 多读 1 段）。同序列（P,B×3,P,B×3,autoP,F）
   对方/我方 恰为 10.32/8.52 = 86/71 ≈ 1.2113（Beam 6×0.32 与 Final 3×0.8 两侧
   同值剥离后，差全部落在 Pulse 段数：3 Pulse × 1 段 × 0.6 = +1.8）
R-MB1 1507 大行迹1507103 #3 分叉（无其他虚无队友→自身增伤 +75%）我方待收（作用域
   乘区键未登记；对方 solo 虚无计数 1 → BOOST 0.75 常开）→ 结界场 对方/我方 恰为
   2.25/1.5 = 1.5（增伤池 1+0.5+0.75 vs 1+0.5）；_inject all_dmg 0.75 后全链全等
R-MB2 150709 追加技倍率读法差（我方照抄官方 params 第 1 列占位原值 0.1——desc 空
   占位、倍率待实测在案；对方按官方文本「视为发动了追加攻击的战技」=战技倍率
   0.72+4×0.24）→ 结界外场 对方/我方 恰为 1.68/1.06 = 84/53 ≈ 1.5849
R-RT1 1508 天赋 SP 流转暴伤 0.7 我方待收（on_skill_point_change 载荷无消费主体字
   段——1306 星历②同族；对方 talentCdBuff 常开）→ 对方暴击区/我方 恰为
   (1+0.05×1.573)/(1+0.05×0.873)；_inject crit_dmg 0.7 后全等
R-RT2 1508 终结技易伤时序差（我方按文本序先伤后挂——本发不吃；对方常开件折叠进
   本发）→ 终结技本发 对方/我方 恰为 1.2；后续行动双方同吃 0.2 比等
R-RT3 150809 强化战技弹射循环我方待收（动态循环结算通道缺——逐跳耗 3 gem/≤33 跳
   值在案；对方 skillBounces 档聚合）→ 钉 10 跳场 对方/我方 恰为 11.0
R-GG1 150905 连携追击 solo 建模差（官方计数双主体=「吉尔伽美什或 Saber 攻击」含吉
   本人——我方计数 8 触发 4.0 AoE；对方 UNIQUE 以 Saber 在队为闸，solo 空段）
   → 无对方落点，我方段 vs 手算钉（对方 hits==[] 同钉）
R-GG2 150904 王来背负归属/时序差（官方「我方队友施放终结技」——我方按排自身收，
   solo 不发；对方常开近似）→ 终结技场 对方/我方 恰为 (1+0.08+0.4)/(1+0.08)
   = 37/27 ≈ 1.3704
R-GG3 1509103 王霸的竞逐溢出段我方待收（能量上限>140 逐目标加成——逐目标动态光环
   通道缺；对方 baseEnergy 档 min(1,(E-140)×0.01)）→ base_energy 钉 360 场对方
   atk 区/暴伤区双差，比值恰为 (1708.71624×(1+0.237×1.7))/(990.76824×(1+0.237×0.7))
R-AV1 1504 头狼② FUA 暴伤 +80% 我方待收（类型分域暴伤键缺；对方 mutual 常开）
   → FUA 段 对方暴击区/我方 恰为 (1+0.05×2.073)/(1+0.05×1.273)
R-AV2 1504 强化 FUA 婪酣模型差（双件捆绑）：① 段数——我方「≥4 耗 4 追加 1 段」
   单段建模（连杀循环待收）vs 对方 floor(层/4) 段聚合；② 层读时序——我方影肢
   现场追值（段段读活层）vs 对方平均化（(4+0)/2=2）→ 婪酣 4 场 FUA 合计
   对方/我方 恰为 (1.10365×2.144)/(1.06365×2.344)（含 R-AV1 暴伤差，在案捆绑）

已修真病一件（本波钓出——单列）：
B-MB① 1507 追加技 150709 随机段继承钩 `!$event.insert` 全哑——150709 唯一入口=
   天赋满充 trigger_action（insert=True），合写 insert 滤=继承段死件（模板头注
   「追加技 150709 同形继承」自证意图；1510 勘正⑦ 助战钩同族）。修复=拆条件
   （150702 主动施放才滤 insert，150709 免滤）——production 满充链 0.1 → 1.06
   （0.1 全体 + 4×0.24 随机），对拍 R-MB2 钉法随之以 1.06 为基。
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
# 我方侧引擎件（elation 波同模——本文件自足，不跨 test 文件 import 波次件）
# ---------------------------------------------------------------------------


def _solo_build(cid, *, eidolon: int = 0):
    member = {"character_template": cid, "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member], "policy": _POLICY}}


def _solo_compiled(cid, *, enemies):
    return compile_encounter(_solo_build(cid), _stage(enemies),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _fire_ult(eng, owner, aid, *, energy=None, resource=None, target=None):
    """钉资源开大（elation 波同模；单体敌目标 ult 经 target 钉选择器）."""
    st = eng.state.actors[owner]
    if energy is not None:
        st.current_energy = energy
    if resource is not None:
        rid, val = resource
        st.resources[rid] = val
    if target is not None:
        tgt = eng.state.actors[target]
        eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
            tgt if tgt in candidates else (candidates[0] if candidates else None))
    ult = next(a for a in eng.actions_by_actor[owner] if a.action_id == aid)
    assert eng._fire_ultimate(st, ult) is True


def _fire_assist(eng, owner, aid):
    """助战技发动（1510 族——唯一入口 fire_assist，额度=assist_uses）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    assert eng.fire_assist(st, a) is True


# ---------------------------------------------------------------------------
# 口径常数（两侧钉死；fixture 终审值，行迹平铺按模板 trace_stat_effects 并入）
# ---------------------------------------------------------------------------

# 姬子•启行 1510（火，ATK 倍率；行迹 atk_pct 0.28/crit 0.12/dmg_fire 0.08 已并入；
# 天赋暴伤 0.8/全抗穿 0.2 常驻件）
HN_ATK_W, HN_HP, HN_DEF, HN_SPD = 756.756, 1125.432, 485.1, 98
HN_ATK = HN_ATK_W * 1.28                         # 968.64768
HN_CR, HN_CD, HN_PEN, HN_FIRE = 0.17, 1.3, 0.2, 0.08
HN_CZ = 1 + HN_CR * HN_CD                        # 1.221
HN_BEAM = 0.32                                     # Beam 单体段（全体 0.32×1 敌）
HN_PULSE_S3 = 0.2 + 2 * 0.6                        # Pulse 单体段（源能 3：全体 0.2+2 随机段 0.6）
HN_FINAL = 3 * 0.8                                 # Final Hit（3 段×0.8）
HN_ULT_BEAM_FIRST = 6 * HN_BEAM + HN_PULSE_S3 + HN_FINAL       # 5.72（Beam×6→自动 Pulse→Final）
HN_ULT_PULSE_FIRST = 3 * HN_PULSE_S3 + 6 * HN_BEAM + HN_FINAL  # 8.52（P,B×3,P,B×3,autoP,F——官方最大档）
HN_ULT_THEIRS = 2.4 + 3 * (0.2 + 1.8) + 6 * 0.32     # 10.32（对方 P,B×3,P,B×3,autoP,F 聚合——
                                                     # pulseScaling=0.2+3×0.6 bounce=源能 3 段读法）


def _hn(mult: float, *, boost: float = 0.0) -> float:
    """1510 期望伤害：倍率×ATK×防御区 0.5×抗区 1.2×未击破 0.9×期望暴击×增伤池（1+火 0.08+附加）."""
    return mult * HN_ATK * 0.5 * (1 + HN_PEN) * 0.9 * HN_CZ * (1 + HN_FIRE + boost)


# 千冶•刃 1507（火，**Max HP 倍率**；无行迹属性件；Fury 双暴 0.2/0.6、结界减防 0.3/
# 易伤 0.5/全队增伤 0.5）
MB_HP_W, MB_ATK, MB_DEF, MB_SPD = 1358.28, 543.312, 485.1, 107
MB_CZ0 = 1 + 0.05 * 0.5                          # 1.025（常态）
MB_CR1, MB_CD1 = 0.25, 1.1                       # Fury 内
MB_CZ1 = 1 + MB_CR1 * MB_CD1                     # 1.275
MB_DEFZ_ZONE = 100 / (100 * 0.7 + 100)           # 结界减防 0.3 → 10/17


def _mb(mult: float, cz: float, *, defz: float = 0.5, vuln: float = 0.0,
        boost: float = 0.0) -> float:
    """1507 期望伤害：倍率×MaxHP×防御区×未击破 0.9×期望暴击×易伤区×增伤池."""
    return mult * MB_HP_W * defz * 0.9 * cz * (1 + vuln) * (1 + boost)


# 远坂凛 1508（量子，ATK 倍率；行迹 crit_dmg 0.373/atk_pct 0.18/dmg_quantum 0.08；
# 秉持优雅 ATK+150%/量子穿抗 0.15 常驻）
RT_ATK_W, RT_HP, RT_DEF, RT_SPD = 698.544, 1047.816, 460.845, 102
RT_ATK_PIN = RT_ATK_W * 1.18                     # 824.28192（对方钉值——ATK_P 1.5 换算前）
RT_ATK = RT_ATK_W * 2.68                         # 1872.09792（双方终值）
RT_CR, RT_CD, RT_PEN, RT_Q = 0.05, 0.873, 0.15, 0.08
RT_CZ = 1 + RT_CR * RT_CD                        # 1.04365
RT_CZ_T = 1 + RT_CR * (RT_CD + 0.7)              # 1.07865（R-RT1 对方天赋暴伤档）


def _rt(mult: float, *, cz: float = RT_CZ, vuln: float = 0.0) -> float:
    """1508 期望伤害：倍率×ATK×防御区 0.5×抗区 1.15×未击破 0.9×期望暴击×易伤区×增伤池 1.08."""
    return mult * RT_ATK * 0.5 * (1 + RT_PEN) * 0.9 * cz * (1 + vuln) * (1 + RT_Q)


# 吉尔伽美什 1509（雷，ATK 倍率；行迹 crit 0.187/atk_pct 0.18/dmg_thunder 0.08；
# 王霸竞逐 team atk 0.2/暴伤 0.2 常驻）
GG_ATK_W, GG_HP, GG_DEF, GG_SPD = 717.948, 1125.432, 509.355, 97
GG_ATK_PIN = GG_ATK_W * 1.18                     # 847.17864（对方钉值——ATK_P 0.2 换算前）
GG_ATK = GG_ATK_W * 1.38                         # 990.76824（双方终值）
GG_CR, GG_CD, GG_TH = 0.237, 0.7, 0.08
GG_CZ = 1 + GG_CR * GG_CD                        # 1.1659
GG_CZ_H2 = 1 + GG_CR * (GG_CD + 0.5)             # 1.2844（HERO 2 层=兴致+2 后）
GG_ENERGY = 360.0                                # max_sp（米游社/tbgd/fandom 三源）
GG_ATK_G3 = GG_ATK_PIN + 1.2 * GG_ATK_W          # 1708.71624（R-GG3 对方 360 档 ATK_P 1.2）
GG_CZ_G3 = 1 + GG_CR * 1.7                       # 1.4029（R-GG3 对方 360 档暴伤 1.2）


def _gg(mult: float, *, cz: float = GG_CZ, def_pen: float = 0.0,
        boost: float = 0.0) -> float:
    """1509 期望伤害：倍率×ATK×防御区（防穿档另算）×未击破 0.9×期望暴击×增伤池（1+雷 0.08+附加）."""
    defz = 100 / (100 * max(0.0, 1 - def_pen) + 100)
    return mult * GG_ATK * defz * 0.9 * cz * (1 + GG_TH + boost)


# 不死途 1504（雷，ATK 倍率；行迹 crit_dmg 0.373/dmg_thunder 0.144/atk_pct 0.1；
# 头狼 team 暴伤 0.4 常驻；饲饵减防 0.4 常驻 → 防御区 100/160）
AV_ATK_W, AV_HP, AV_DEF, AV_SPD = 776.16, 853.776, 388.08, 106
AV_ATK = AV_ATK_W * 1.1                          # 853.776
AV_CR, AV_CD, AV_TH = 0.05, 1.273, 0.144
AV_CZ = 1 + AV_CR * AV_CD                        # 1.06365
AV_CZ_FUA = 1 + AV_CR * (AV_CD + 0.8)            # 1.10365（R-AV1 对方头狼② FUA 暴伤档）
AV_DEFZ = 100 / (100 * 0.6 + 100)                # 0.625（饲饵减防 0.4）


def _av(mult: float, *, cz: float = AV_CZ, boost: float = 0.0) -> float:
    """1504 期望伤害：倍率×ATK×防御区 0.625×未击破 0.9×期望暴击×增伤池（1+雷 0.144+附加）."""
    return mult * AV_ATK * AV_DEFZ * 0.9 * cz * (1 + AV_TH + boost)


# ---------------------------------------------------------------------------
# 对方侧场景模子（映射表见模块 docstring）
# ---------------------------------------------------------------------------

def _opt_himeko(action: str, *, cond: dict | None = None):
    c = {"navigatorsSemaphore": False, "selfUseAssistSkill": True,
         "assistSkillBuff": True, "companionVerdict": False,
         "companionDecimation": False, "e4ResPen": True, "e6": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1510", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": HN_ATK_W, "hp": HN_HP, "def": HN_DEF, "spd": HN_SPD},
            "attacker": {"atk": HN_ATK, "hp": HN_HP, "def": HN_DEF, "spd": HN_SPD,
                         "cr": HN_CR, "cd": 0.5, "element_boost": HN_FIRE},
            "self_path": "Erudition",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_mortenax(action: str, *, cond: dict | None = None):
    c = {"infiniteFuryActive": False, "ultZone": False, "e1ResPen": True,
         "e2FuaDmgBoost": True, "e4DmgBoost": True, "e6EnhancedUlt": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1507", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": MB_ATK, "hp": MB_HP_W, "def": MB_DEF, "spd": MB_SPD},
            "attacker": {"atk": MB_ATK, "hp": MB_HP_W, "def": MB_DEF, "spd": MB_SPD,
                         "cr": 0.05, "cd": 0.5},
            "self_path": "Nihility",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_rin(action: str, *, cond: dict | None = None):
    c = {"enhancedSkill": False, "skillBounces": 0, "enhancedSkillSpConsumed": 0,
         "talentCdBuff": False, "elegantConduct": True, "ladylikePoise": False,
         "ultDmgTakenDebuff": False, "e2Buffs": True, "e4TalentCdStacks": True,
         "e6ResPen": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1508", "eidolon": 0,
            "action": action, "element": "quantum", "conditionals": c,
            "base": {"atk": RT_ATK_W, "hp": RT_HP, "def": RT_DEF, "spd": RT_SPD},
            "attacker": {"atk": RT_ATK_PIN, "hp": RT_HP, "def": RT_DEF, "spd": RT_SPD,
                         "cr": RT_CR, "cd": RT_CD, "element_boost": RT_Q},
            "self_path": "Erudition",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_gilgamesh(action: str, *, cond: dict | None = None,
                   base_energy: float | None = None):
    c = {"herosHauteurStacks": 0, "interestSpdStacks": 0,
         "kingsAcknowledgement": False, "kingsBurden": False, "a6TeamBuff": True,
         "e6ResPen": True, "goldenRuleStacks": 2}
    c.update(cond or {})
    sc = {"kind": "character", "character_id": "1509", "eidolon": 0,
          "action": action, "element": "thunder", "conditionals": c,
          "base": {"atk": GG_ATK_W, "hp": GG_HP, "def": GG_DEF, "spd": GG_SPD},
          "attacker": {"atk": GG_ATK_PIN, "hp": GG_HP, "def": GG_DEF, "spd": GG_SPD,
                       "cr": GG_CR, "cd": 0.5, "element_boost": GG_TH},
          "self_path": "Destruction",
          "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                    "count": 1}}
    if base_energy is not None:
        sc["base_energy"] = base_energy
    return sc


def _opt_ashveil(action: str, *, cond: dict | None = None):
    c = {"baitActive": True, "targetBait": True, "enhancedFua": False,
         "gluttonyStacks": 0, "e1DmgVulnerability": True, "e1TargetHpBelow50": True,
         "e4AtkBuff": True, "e6GluttonyGainedStacks": 30}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1504", "eidolon": 0,
            "action": action, "element": "thunder", "conditionals": c,
            "base": {"atk": AV_ATK_W, "hp": AV_HP, "def": AV_DEF, "spd": AV_SPD},
            "attacker": {"atk": AV_ATK, "hp": AV_HP, "def": AV_DEF, "spd": AV_SPD,
                         "cr": AV_CR, "cd": 0.873, "element_boost": AV_TH},
            "self_path": "Hunt",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 姬子•启行 1510（对方 1500/HimekoNova.ts 全实现）——助战族+Starblazer 序列
# ===========================================================================

class TestHimekoNovaDuipai:
    """姬子•启行 E0：面板回显/普攻/旗语战技/助战 3.28 聚合/裁决增伤链/终结技
    Starblazer 双模式（Beam/Pulse 分段+全 Beam 先手序列+Pulse 混插序列 R-HN1
    段数读法差+致命/锁血立即 Final）——双锚+乘区读回."""

    def test_panel_echo(self, optimizer_driver):
        theirs = run_optimizer(optimizer_driver, _opt_himeko("basic"))
        st = theirs["stats"]
        assert st["atk"] == pytest.approx(HN_ATK, rel=REL_TOL), "行迹 atk×1.28 回显"
        assert st["cd"] == pytest.approx(HN_CD, rel=REL_TOL), "天赋暴伤 0.8（assistSkillBuff）"
        assert st["res_pen"] == pytest.approx(HN_PEN, rel=REL_TOL), "天赋全抗穿 0.2"
        assert st["cr"] == pytest.approx(HN_CR, rel=REL_TOL)

    def test_basic(self, optimizer_driver):
        """普攻 1.0（旗语/裁决双灭档）."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        log.clear()
        _cast(eng, "1510", "151001")
        ours = _hit_amounts(log, source="1510")
        theirs = run_optimizer(optimizer_driver, _opt_himeko("basic"))

        hand = _hn(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.2), ("baseUniversalMulti", 0.9),
                     ("critMulti", HN_CZ), ("dmgBoostMulti", 1.08)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_semaphore_skill_then_basic(self, optimizer_driver):
        """战技 151002（无伤增益技）→ NAV_SEMAPHORE 全队增伤 0.2：后续普攻增伤池
        1+0.08+0.2——对方 navigatorsSemaphore=true 同池比等；SP/回能/助战回满链对账."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1510"]
        st.resources["assist_uses"] = 0.0
        log.clear()
        _cast(eng, "1510", "151002")
        assert math.isclose(st.resources["assist_uses"], 1.0), "施放战技立即回满助战次数"
        assert math.isclose(st.current_energy, 30.0), "战技回能 30（米游社五项）"
        assert "NAV_SEMAPHORE" in st.modifiers
        _cast(eng, "1510", "151001")
        ours = _hit_amounts(log, source="1510")
        theirs = run_optimizer(optimizer_driver, _opt_himeko(
            "basic", cond={"navigatorsSemaphore": True}))

        hand = _hn(1.0, boost=0.2)
        assert ours == pytest.approx([hand], rel=REL_TOL), "旗语下普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "旗语增伤链双方互对")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.28, rel=REL_TOL)

    def test_assist_self_branch(self, optimizer_driver):
        """助战 151022（姬子使用分支）：全体 2.0 + 随机 4×0.32（expected 取首全落 e1）
        ——对方 UNIQUE 聚合单发 2.0+0.32×4=3.28，总和比等（段数差在案）；免耗返还对账."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        log.clear()
        _fire_assist(eng, "1510", "151022")
        ours = _hit_amounts(log, source="1510")
        theirs = run_optimizer(optimizer_driver, _opt_himeko("unique"))

        hand = _hn(3.28)
        assert len(ours) == 5, "我方 1 全体 + 4 随机"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), "我方 5 段合计 vs 手算"
        assert len(theirs["hits"]) == 1, "对方聚合单发"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(3.28, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        assert math.isclose(eng.state.actors["1510"].resources["assist_uses"], 1.0), (
            "1510101① 免耗：扣 1 后同钩返还 1")

    def test_assist_with_verdict(self, optimizer_driver):
        """151025→裁决（增伤 1.0+终结技增伤 1.0）后助战 151022：增伤池 1+0.08+1.0
        （终结技件对 assist 段不生效——双方同构）；对方 companionVerdict=true 比等."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        log.clear()
        _fire_assist(eng, "1510", "151025")
        _fire_assist(eng, "1510", "151022")
        ours = _hit_amounts(log, source="1510")
        theirs = run_optimizer(optimizer_driver, _opt_himeko(
            "unique", cond={"companionVerdict": True}))

        hand = _hn(3.28, boost=1.0)
        assert sum(ours[-5:]) == pytest.approx(hand, rel=REL_TOL), (
            "裁决后 151022 五段合计 vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert sum(ours[-5:]) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "裁决助战双方互对")
        assert sum(ours[:5]) == pytest.approx(_hn(3.28), rel=REL_TOL), (
            "151025 自身段（裁决在放后挂载——快照族：本发不吃本发增益）vs 手算")

    def test_beam_segment(self, optimizer_driver):
        """Beam 单体段（E0 档）：全体 0.32×1 敌 vs 手算——对方 beamScaling 0.32 同值
        （聚合分解，映射表在案）；计数 −1/源能钳 3/形态在场均对账."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        _fire_ult(eng, "1510", "151003", energy=150.0)
        st = eng.state.actors["1510"]
        assert st.state_config is not None and st.state_config.state == "starblazer", (
            "开大进入「拓星者」形态")
        assert math.isclose(st.resources["beam_uses"], 6.0), "Beam 计数装填 6"
        assert math.isclose(st.resources["source_energy"], 3.0), "1510103① 立即 +3 源能"
        log.clear()
        _cast(eng, "1510", "151008")
        ours = _hit_amounts(log, source="1510")
        assert ours == pytest.approx([_hn(HN_BEAM)], rel=REL_TOL), "我方 Beam 段 vs 手算"
        assert math.isclose(st.resources["beam_uses"], 5.0), "Beam 计数 −1"
        assert math.isclose(st.resources["source_energy"], 3.0), "源能 +1 钳 3 截断"
        assert st.state_config is not None, "未耗尽形态仍在"

    def test_pulse_segments_by_source(self, optimizer_driver):
        """Pulse 单体段按源能分档：s=3→0.2+2×0.6=1.4 / s=2→0.2+0.3=0.5 / s=1→0.2
        ——官方「耗 1 点全体，>1 时每额外 1 点 1 段」；对方 pulseScaling=0.2+3×0.6=2.0
        （bounce=源能 3 段读法），段数差=R-HN1（同序列比值在 sequence 测试钉）."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        _fire_ult(eng, "1510", "151003", energy=150.0)
        st = eng.state.actors["1510"]
        for src, mult, n in ((3, HN_PULSE_S3, 3), (2, 0.2 + 0.3, 2), (1, 0.2, 1)):
            st.resources["source_energy"] = float(src)
            log.clear()
            _cast(eng, "1510", "151009")
            ours = _hit_amounts(log, source="1510")
            assert len(ours) == n, f"源能 {src} 时段数（全体 1 + 随机 {n - 1}）"
            assert sum(ours) == pytest.approx(_hn(mult), rel=REL_TOL), (
                f"源能 {src} 档 Pulse 合计 vs 手算")
            assert math.isclose(st.resources["source_energy"], 0.0), "Pulse 耗全部源能"

    def test_final_hit_segment(self, optimizer_driver):
        """Final Hit 3 段随机单体 3×0.8=2.4（trigger 代放通道）+ 发动后退出形态
        ——对方 finalHitScaling=0.8×3=2.4 同值（聚合分解，映射表在案）."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        _fire_ult(eng, "1510", "151003", energy=150.0)
        st = eng.state.actors["1510"]
        log.clear()
        _cast(eng, "1510", "151014")               # trigger 通道（available_if 常假闸外直放）
        ours = _hit_amounts(log, source="1510")
        assert len(ours) == 3, "Final Hit 3 段"
        assert sum(ours) == pytest.approx(_hn(HN_FINAL), rel=REL_TOL), (
            "我方 Final Hit 合计 vs 手算")
        assert st.state_config is None, "Final Hit 发动后退出「拓星者」形态"
        assert math.isclose(st.resources["_final_fired"], 1.0), "Final 幂等闩置位"

    def test_ult_beam_first_sequence(self, optimizer_driver):
        """Beam×6→自动 Pulse→Final Hit（全 Beam 先手档）：12 段合计 5.72 vs 手算——
        官方双模式合法序列之一（对方无此序列档，纯手算锚）；形态退出+资源对账."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        _fire_ult(eng, "1510", "151003", energy=150.0)
        log.clear()
        for _ in range(6):
            _cast(eng, "1510", "151008")
        ours = _hit_amounts(log, source="1510")
        assert len(ours) == 12, "我方 6 Beam + 1 Pulse 全体 + 2 随机 + 3 Final"
        assert sum(ours) == pytest.approx(_hn(HN_ULT_BEAM_FIRST), rel=REL_TOL), (
            "我方 12 段合计 vs 手算")
        st = eng.state.actors["1510"]
        assert st.state_config is None, "序列终结形态退出"
        assert math.isclose(st.resources["beam_uses"], 0.0), "Beam 计数耗尽"
        assert math.isclose(st.resources["source_energy"], 0.0), "Pulse 消耗所有源能"
        assert math.isclose(st.current_energy, 5.0), "150 全扣 + 回 5"

    def test_ult_pulse_first_sequence_r_hn1(self, optimizer_driver):
        """R-HN1（核销改写）：Pulse 混插官方最大序列 P,B×3,P,B×3,autoP,F——
        我方 18 段合计 8.52 vs 对方同序列聚合单发 10.32，差恰为 86/71
        （Beam/Final 两侧同值剥离，差全部落在 Pulse 段数读法：3×1 段×0.6=+1.8）."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        _fire_ult(eng, "1510", "151003", energy=150.0)
        log.clear()
        for aid in ("151009", "151008", "151008", "151008",
                    "151009", "151008", "151008", "151008"):
            _cast(eng, "1510", aid)
        ours = _hit_amounts(log, source="1510")
        theirs = run_optimizer(optimizer_driver, _opt_himeko("ult"))

        assert len(ours) == 18, "我方 3 Pulse×3 段 + 6 Beam + 3 Final"
        assert sum(ours) == pytest.approx(_hn(HN_ULT_PULSE_FIRST), rel=REL_TOL), (
            "我方 18 段合计 vs 手算")
        assert len(theirs["hits"]) == 1
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(HN_ULT_THEIRS, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _hn(HN_ULT_THEIRS), rel=REL_TOL), "对方聚合单发 vs 手算"
        assert theirs["hits"][0]["damage"] / sum(ours) == pytest.approx(
            HN_ULT_THEIRS / HN_ULT_PULSE_FIRST, rel=REL_TOL), (
            "R-HN1 差恰为 10.32/8.52 = 86/71（Pulse 段数读法差）")
        st = eng.state.actors["1510"]
        assert st.state_config is None and math.isclose(st.resources["_final_fired"], 1.0)

    def test_ult_with_verdict_full_chain(self, optimizer_driver):
        """全链：裁决后 Pulse 混插序列——增伤池双方 1+0.08+1.0+1.0（终结技件），
        R-HN1 比值 86/71 不变."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire")))
        log.clear()
        _fire_assist(eng, "1510", "151025")
        _fire_ult(eng, "1510", "151003", energy=150.0)
        for aid in ("151009", "151008", "151008", "151008",
                    "151009", "151008", "151008", "151008"):
            _cast(eng, "1510", aid)
        ours = _hit_amounts(log, source="1510")[5:]     # 剥 151025 自身 5 段
        theirs = run_optimizer(optimizer_driver, _opt_himeko(
            "ult", cond={"companionVerdict": True}))

        assert sum(ours) == pytest.approx(
            _hn(HN_ULT_PULSE_FIRST, boost=2.0), rel=REL_TOL), (
            "我方裁决后 18 段合计 vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _hn(HN_ULT_THEIRS, boost=2.0), rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / sum(ours) == pytest.approx(
            HN_ULT_THEIRS / HN_ULT_PULSE_FIRST, rel=REL_TOL), "R-HN1 全链档比值不变"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            3.08, rel=REL_TOL), "对方增伤池回显 1+0.08+1.0+1.0（裁决+终结技件）"

    def test_ult_all_dead_immediate_final(self, optimizer_driver):
        """全场致命 → 立即 Final Hit（官方第三句；on_kill 发射点+damageable_enemies
        判定）：假人 1 血被 Beam 击杀 → Final 发动（全场无存活目标鞭尸无段）+ 形态退出；
        Beam 未耗尽不走自动 Pulse 链."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire", hp=1)))
        _fire_ult(eng, "1510", "151003", energy=150.0)
        st = eng.state.actors["1510"]
        log.clear()
        _cast(eng, "1510", "151008")
        ours = _hit_amounts(log, source="1510")
        assert len(ours) == 1, "仅 Beam 段（Final 全场无目标鞭尸无段）"
        assert ours[0] == pytest.approx(_hn(HN_BEAM), rel=REL_TOL)
        assert not eng.state.actors["e1"].alive, "假人被击杀"
        assert st.state_config is None, "全场致命立即 Final → 形态退出"
        assert math.isclose(st.resources["_final_fired"], 1.0), "Final 幂等闩置位"
        assert math.isclose(st.resources["beam_uses"], 5.0), "Beam 未耗尽（无自动 Pulse 链）"

    def test_ult_hp_lock_immediate_final(self, optimizer_driver):
        """锁血（无法被继续削减生命值）→ 立即 Final Hit（官方第三句；on_hp_lock 发射点）
        ：假人 1 血+hp_lock 被 Beam 钳 1 → Final 3 段照算（锁血照算伤害）+ 形态退出."""
        eng, log = _make_logged(_solo_compiled("1510", enemies=_dummy("e1", "fire", hp=1)))
        _fire_ult(eng, "1510", "151003", energy=150.0)
        st = eng.state.actors["1510"]
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="LOCK", name="锁血", modifier_type="buff", duration=0, hp_lock=True))
        log.clear()
        _cast(eng, "1510", "151008")
        ours = _hit_amounts(log, source="1510")
        assert len(ours) == 4, "Beam 1 段 + Final 3 段"
        assert sum(ours) == pytest.approx(_hn(HN_BEAM + HN_FINAL), rel=REL_TOL), (
            "Beam+Final 合计 vs 手算")
        assert math.isclose(e1.current_hp, 1.0), "锁血钳 1 不死"
        assert st.state_config is None, "锁血立即 Final → 形态退出"
        assert math.isclose(st.resources["_final_fired"], 1.0), "Final 幂等闩置位"



# ===========================================================================
# L2 千冶•刃 1507（对方 1500/MortenaxBlade.ts 全实现）——HP 倍率结界族
# ===========================================================================

class TestMortenaxBladeDuipai:
    """千冶•刃 E0（≠刃 1205，SP 消歧在案）：常态普攻/结界主链（Zone+Fury+Balefire）
    /R-MB1 虚无分叉结构差/强化普攻/150714/满充 150709 R-MB2 倍率读法差."""

    def test_basic_stance_off(self, optimizer_driver):
        """常态普攻 0.5×MaxHP（Fury/Zone 双灭档）."""
        eng, log = _make_logged(_solo_compiled("1507", enemies=_dummy("e1", "fire")))
        log.clear()
        _cast(eng, "1507", "150701")
        ours = _hit_amounts(log, source="1507")
        theirs = run_optimizer(optimizer_driver, _opt_mortenax("basic"))

        hand = _mb(0.5, MB_CZ0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(0.5, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", MB_CZ0), ("dmgBoostMulti", 1.0)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert "MORTENAX_TAUNT" in eng.state.actors["e1"].modifiers, "普攻 Taunt 1 回合"

    def test_zone_on_skill_r_mb1_divergence(self, optimizer_driver):
        """R-MB1：150703 结界主链后战技——我方增伤池 1+0.5（大行迹3#1 全队件）vs
        对方 1+0.5+0.75（#3 虚无分叉 solo 档，我方待收），差恰为 1.5；其余乘区全等."""
        eng, log = _make_logged(_solo_compiled("1507", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1507"]
        _fire_ult(eng, "1507", "150703", energy=160.0)
        assert st.resources["_zone_on"] == 1.0 and st.resources["_fury_on"] == 1.0
        log.clear()
        _cast(eng, "1507", "150702")
        ours = _hit_amounts(log, source="1507")
        theirs = run_optimizer(optimizer_driver, _opt_mortenax(
            "skill", cond={"infiniteFuryActive": True, "ultZone": True}))

        hand_ours = _mb(1.68, MB_CZ1, defz=MB_DEFZ_ZONE, vuln=0.5, boost=0.5)
        hand_theirs = _mb(1.68, MB_CZ1, defz=MB_DEFZ_ZONE, vuln=0.5, boost=1.25)
        assert len(ours) == 5, "我方 1 全体 + 4 随机段（expected 取首全落 e1）"
        assert sum(ours) == pytest.approx(hand_ours, rel=REL_TOL), (
            "我方战技 5 段合计（Fury 双暴+减防 0.3+易伤 0.5+增伤 0.5）vs 手算")
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(1.68, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / sum(ours) == pytest.approx(1.5, rel=REL_TOL), (
            "R-MB1 差恰为 2.25/1.5 = 1.5（大行迹3#3 虚无分叉 0.75 我方待收）")
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", MB_DEFZ_ZONE), ("vulnMulti", 1.5),
                     ("critMulti", MB_CZ1), ("dmgBoostMulti", 2.25)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert math.isclose(st.current_hp, 0.7 * MB_HP_W, rel_tol=1e-9), (
            "150703 耗 20% + 150702 耗 10%（均按 Max HP 计——加算 1−0.2−0.1）")

    def test_zone_on_full_chain_with_injection(self, optimizer_driver):
        """R-MB1 注入等价件后全链全等：战技 1.68/强化普攻 1.0/150714 3.5 三链."""
        eng, log = _make_logged(_solo_compiled("1507", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1507"]
        _fire_ult(eng, "1507", "150703", energy=160.0)
        _inject(eng, "1507", "XC_MB1", {"all_dmg": 0.75})
        log.clear()
        _cast(eng, "1507", "150702")
        _cast(eng, "1507", "150708")
        _fire_ult(eng, "1507", "150714", energy=160.0)
        ours = _hit_amounts(log, source="1507")
        cond = {"infiniteFuryActive": True, "ultZone": True}
        theirs_skill = run_optimizer(optimizer_driver, _opt_mortenax("skill", cond=cond))
        theirs_basic = run_optimizer(optimizer_driver, _opt_mortenax("basic", cond=cond))
        theirs_ult = run_optimizer(optimizer_driver, _opt_mortenax("ult", cond=cond))

        hand_skill = _mb(1.68, MB_CZ1, defz=MB_DEFZ_ZONE, vuln=0.5, boost=1.25)
        hand_basic = _mb(1.0, MB_CZ1, defz=MB_DEFZ_ZONE, vuln=0.5, boost=1.25)
        hand_ult = _mb(3.5, MB_CZ1, defz=MB_DEFZ_ZONE, vuln=0.5, boost=1.25)
        assert sum(ours[:5]) == pytest.approx(hand_skill, rel=REL_TOL), "注入后战技 vs 手算"
        assert ours[5] == pytest.approx(hand_basic, rel=REL_TOL), "注入后强化普攻 vs 手算"
        assert ours[6] == pytest.approx(hand_ult, rel=REL_TOL), "注入后 150714 vs 手算"
        assert sum(ours[:5]) == pytest.approx(
            theirs_skill["hits"][0]["damage"], rel=REL_TOL), "战技双方互对（注入等价）"
        assert ours[5] == pytest.approx(
            theirs_basic["hits"][0]["damage"], rel=REL_TOL), "强化普攻双方互对"
        assert ours[6] == pytest.approx(
            theirs_ult["hits"][0]["damage"], rel=REL_TOL), "150714 双方互对"
        assert theirs_ult["hits"][0]["hp_scaling"] == pytest.approx(3.5, rel=REL_TOL)

    def test_fua_r_mb2_divergence(self, optimizer_driver):
        """R-MB2 + B-MB① 修复锚：满充 trigger 150709（production 链 insert 档）——
        修复后 0.1 全体 + 4×0.24 随机 = 1.06 vs 对方「视为战技」1.68，差恰为 84/53；
        官方 150709 params 第 1 列 0.1 系 desc 空占位原值（倍率待实测在案）."""
        eng, log = _make_logged(_solo_compiled("1507", enemies=_dummy("e1", "fire")))
        st = eng.state.actors["1507"]
        log.clear()
        eng._gain_resource(st, "charge", 9.0)       # 满充兑现：扣 9 回 25 + trigger 150709
        ours = _hit_amounts(log, source="1507")
        theirs = run_optimizer(optimizer_driver, _opt_mortenax("fua"))

        hand_ours = _mb(1.06, MB_CZ0)
        hand_theirs = _mb(1.68, MB_CZ0)
        assert len(ours) == 5, (
            "B-MB① 修复后：1 全体（占位 0.1）+ 4 随机段（insert 档同形继承生效）")
        assert sum(ours) == pytest.approx(hand_ours, rel=REL_TOL), "我方 150709 vs 手算"
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(1.68, rel=REL_TOL), (
            "对方 FUA=战技倍率（SKILL|FUA 双标签——结界外类型桶中性）")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / sum(ours) == pytest.approx(
            1.68 / 1.06, rel=REL_TOL), "R-MB2 差恰为 1.68/1.06 = 84/53（倍率读法差）"
        assert math.isclose(st.resources["charge"], 0.0), "满 9 扣 9"
        assert math.isclose(st.current_energy, 160.0), (
            "120（大行迹1 保底）+25（满充 #2）+30（150709 继承回能）=175 → clamp 160")


# ===========================================================================
# L2 远坂凛 1508（对方 1500/RinTohsaka.ts 全实现）——Gem 经济+强化战技互斥
# ===========================================================================

class TestRinTohsakaDuipai:
    """远坂凛 E0：秉持优雅 ATK_P 换算链首接/普攻/普通战技/强化战技 R-RT3 弹射
    结构差/终结技 R-RT2 易伤时序差/天赋暴伤 R-RT1 结构差."""

    def test_panel_echo_and_basic(self, optimizer_driver):
        """秉持优雅常驻（ATK+150%/量子穿抗 0.15）：base=真白值、attacker=行迹档钉值
        ——对方 ATK_P 1.5 经 applyPercentStats 换算后双方终值 1872.09792 对齐."""
        eng, log = _make_logged(_solo_compiled("1508", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1508"]
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], RT_ATK, rel_tol=1e-9), "我方 698.544×(1+0.18+1.5)"
        assert math.isclose(eff["res_pen"], 0.15, rel_tol=1e-9)
        log.clear()
        _cast(eng, "1508", "150801")
        ours = _hit_amounts(log, source="1508")
        theirs = run_optimizer(optimizer_driver, _opt_rin("basic"))

        hand = _rt(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["atk"] == pytest.approx(RT_ATK, rel=REL_TOL), (
            "对方 ATK_P 1.5×698.544 换算后回显——钉值拆分正确")
        assert theirs["stats"]["res_pen"] == pytest.approx(0.15, rel=REL_TOL)
        assert math.isclose(st.resources["gem_energy"], 21.0), (
            "天赋 SP 流转：入场 20 + 普攻产 1 点 → +1 Gem")

    def test_skill_normal(self, optimizer_driver):
        """普通战技 150802 单体 1.8（gem<15 互斥半——清开局层钉 0 后施放）."""
        eng, log = _make_logged(_solo_compiled("1508", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1508"]
        st.resources["gem_energy"] = 0.0            # 清开局层（_clean_knots 先例）
        log.clear()
        _cast(eng, "1508", "150802")
        ours = _hit_amounts(log, source="1508")
        theirs = run_optimizer(optimizer_driver, _opt_rin("skill"))

        hand = _rt(1.8)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方战技 vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.8, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert math.isclose(st.resources["gem_energy"], 1.0), "耗 1 点 → +1 Gem"

    def test_enhanced_skill_r_rt3_divergence(self, optimizer_driver):
        """R-RT3：强化战技 150809 弹射循环我方待收（动态循环通道缺——只有首击全体
        0.9）vs 对方 skillBounces=10 档聚合 9.9，差恰为 11.0."""
        eng, log = _make_logged(_solo_compiled("1508", enemies=_dummy("e1", "quantum")))
        log.clear()
        _cast(eng, "1508", "150809")                # 入场 20 Gem ≥ 15 → 强化位可放
        ours = _hit_amounts(log, source="1508")
        theirs = run_optimizer(optimizer_driver, _opt_rin(
            "skill", cond={"enhancedSkill": True, "skillBounces": 10}))

        hand_ours = _rt(0.9)
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方首击全体 vs 手算（待收）"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(9.9, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(_rt(9.9), rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(11.0, rel=REL_TOL), (
            "R-RT3 差恰为 (0.9+0.9×10)/0.9 = 11.0")
        assert "LADYLIKE_POISE" in eng.state.actors["1508"].modifiers, (
            "淑女风范：强化战技后速度 +20%（EN 层裁定仅强化战技触发）")

    def test_ult_r_rt2_and_post_ult_vuln(self, optimizer_driver):
        """R-RT2：终结技易伤时序——我方文本序先伤后挂（本发不吃 6.0 裸）vs 对方常开
        折叠进本发（×1.2）；后续普攻双方同吃 0.2 易伤比等；产点/财源广进 Gem 链对账."""
        eng, log = _make_logged(_solo_compiled("1508", enemies=_dummy("e1", "quantum")))
        st = eng.state.actors["1508"]
        log.clear()
        _fire_ult(eng, "1508", "150803", energy=160.0, target="e1")
        ours = _hit_amounts(log, source="1508")
        theirs_off = run_optimizer(optimizer_driver, _opt_rin("ult"))
        theirs_on = run_optimizer(optimizer_driver, _opt_rin(
            "ult", cond={"ultDmgTakenDebuff": True}))

        hand = _rt(6.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方终结技本发（不吃本发易伤）vs 手算"
        assert theirs_off["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 ultDmgTakenDebuff=false 档互对")
        assert ours[0] == pytest.approx(theirs_off["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_on["hits"][0]["damage"] / ours[0] == pytest.approx(1.2, rel=REL_TOL), (
            "R-RT2 对方常开档/我方 恰为 1.2")
        assert math.isclose(st.resources["gem_energy"], 33.0), (
            "入场 20 + 财源广进 12 + 终结技产 1 点 → +1 Gem")
        # 后续行动：我方易伤已挂（0.2×3 回合）↔ 对方常开——双方同吃比等
        log.clear()
        _cast(eng, "1508", "150801")
        ours2 = _hit_amounts(log, source="1508")
        theirs2 = run_optimizer(optimizer_driver, _opt_rin(
            "basic", cond={"ultDmgTakenDebuff": True}))
        hand2 = _rt(1.0, vuln=0.2)
        assert ours2 == pytest.approx([hand2], rel=REL_TOL), "易伤后普攻 vs 手算"
        assert ours2[0] == pytest.approx(theirs2["hits"][0]["damage"], rel=REL_TOL), (
            "易伤链双方互对（时序差只落在终结技本发）")

    def test_talent_cd_r_rt1_divergence_and_injection(self, optimizer_driver):
        """R-RT1：天赋 SP 流转暴伤 0.7 我方待收（载荷无消费主体字段）——对方
        talentCdBuff 常开档暴击区差恰为 1.07865/1.04365；注入等价件后全等."""
        eng, log = _make_logged(_solo_compiled("1508", enemies=_dummy("e1", "quantum")))
        log.clear()
        _cast(eng, "1508", "150801")
        ours = _hit_amounts(log, source="1508")
        theirs = run_optimizer(optimizer_driver, _opt_rin(
            "basic", cond={"talentCdBuff": True}))

        assert theirs["stats"]["cd"] == pytest.approx(RT_CD + 0.7, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            RT_CZ_T / RT_CZ, rel=REL_TOL), "R-RT1 差恰为暴击区比"
        _inject(eng, "1508", "XC_RT1", {"crit_dmg": 0.7})
        log.clear()
        _cast(eng, "1508", "150801")
        ours2 = _hit_amounts(log, source="1508")
        assert ours2[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "注入 crit_dmg 0.7 等价件后全等——差值恰来自该待收项")

    def test_unique_solo_empty(self, optimizer_driver):
        """150805 联携追击：我方 Archer 侧触发链待收；对方 archerInTeam 闸 solo 空段
        ——双方无段一致（UNIQUE 族 solo 同灭）."""
        theirs = run_optimizer(optimizer_driver, _opt_rin("unique"))
        assert theirs["hits"] == [], "对方 solo 无 Archer → UNIQUE 空段"
        assert theirs["total"] == 0.0


# ===========================================================================
# L2 吉尔伽美什 1509（对方 1500/Gilgamesh.ts 全实现）——兴致经济+连携追击
# ===========================================================================

class TestGilgameshDuipai:
    """吉尔伽美什 E0：王霸竞逐 ATK_P 链/普攻/王来承认战技/终结技 11 段聚合/
    兴致→暴伤层链/R-GG2 王来背负归属差/R-GG3 溢出段结构差/连携追击 R-GG1."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0（王霸竞逐基础半 atk 0.2/暴伤 0.2 team 常驻——双方同值）."""
        eng, log = _make_logged(_solo_compiled("1509", enemies=_dummy("e1", "thunder")))
        eff = eng.pipeline.effective_stats(eng.state.actors["1509"])
        assert math.isclose(eff["atk"], GG_ATK, rel_tol=1e-9), "我方 717.948×(1+0.18+0.2)"
        assert math.isclose(eff["crit_dmg"], GG_CD, rel_tol=1e-9), "0.5+王霸竞逐 0.2"
        log.clear()
        _cast(eng, "1509", "150901")
        ours = _hit_amounts(log, source="1509")
        theirs = run_optimizer(optimizer_driver, _opt_gilgamesh("basic"))

        hand = _gg(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["atk"] == pytest.approx(GG_ATK, rel=REL_TOL), (
            "对方 ATK_P 0.2×717.948 换算后回显（base_energy 缺省=0 → 溢出段灭）")
        assert theirs["stats"]["cd"] == pytest.approx(GG_CD, rel=REL_TOL)

    def test_skill_kings_acknowledgement(self, optimizer_driver):
        """战技 150902 主目标 2.8（blast 邻段单敌无落点）+ 王来承认 def_pen 0.3·3 回合
        ——对方 kingsAcknowledgement=true 同值比等；施放后清空兴致对账."""
        eng, log = _make_logged(_solo_compiled("1509", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1509"]
        log.clear()
        _cast(eng, "1509", "150902")
        ours = _hit_amounts(log, source="1509")
        theirs = run_optimizer(optimizer_driver, _opt_gilgamesh(
            "skill", cond={"kingsAcknowledgement": True}))

        hand = _gg(2.8, def_pen=0.3)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方战技（王来承认防穿档）vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(2.8, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            100 / 170, rel=REL_TOL)
        assert "KINGS_ACKNOWLEDGEMENT" in st.modifiers
        assert math.isclose(st.resources["interest"], 0.0), "施放战技后清空兴致"
        assert math.isclose(st.resources["_atk_count"], 1.0), "天赋② 攻击计数 +1"

    def test_ult_ten_bounces_aggregation(self, optimizer_driver):
        """终结技 150903：全体 4.0 + 弹射 10×1.0（expected 取首全落 e1）——对方聚合
        单发 14.0，总和比等（段数差在案）；兴致 +2 在伤害后（快照族）→ HERO 2 层."""
        eng, log = _make_logged(_solo_compiled("1509", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1509"]
        log.clear()
        _fire_ult(eng, "1509", "150903", energy=GG_ENERGY)
        ours = _hit_amounts(log, source="1509")
        theirs = run_optimizer(optimizer_driver, _opt_gilgamesh("ult"))

        hand = _gg(14.0)
        assert len(ours) == 11, "我方 1 全体 + 10 弹射"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), "我方 11 段合计 vs 手算"
        assert len(theirs["hits"]) == 1, "对方聚合单发"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(14.0, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        assert math.isclose(st.resources["interest"], 2.0), "1509101③ 自开大兴致 +2"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_dmg"], 1.2, rel_tol=1e-9), (
            "HERO 2 层 ×0.25 = +0.5（获得 2 点=+2 层——勘正⑩精确建层）")

    def test_post_ult_hero_stacks_chain(self, optimizer_driver):
        """1509102 层模型链证：开大后 HERO 2 层 → 后续普攻暴伤 1.2——对方
        herosHauteurStacks=2 档同值比等."""
        eng, log = _make_logged(_solo_compiled("1509", enemies=_dummy("e1", "thunder")))
        _fire_ult(eng, "1509", "150903", energy=GG_ENERGY)
        log.clear()
        _cast(eng, "1509", "150901")
        ours = _hit_amounts(log, source="1509")
        theirs = run_optimizer(optimizer_driver, _opt_gilgamesh(
            "basic", cond={"herosHauteurStacks": 2}))

        hand = _gg(1.0, cz=GG_CZ_H2)
        assert ours == pytest.approx([hand], rel=REL_TOL), "HERO 2 层普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "兴致→暴伤层链双方互对")

    def test_r_gg2_kings_burden_divergence(self, optimizer_driver):
        """R-GG2：王来背负（官方「我方队友施放终结技」——我方排自身收 solo 不发）
        vs 对方常开近似 → 终结技场增伤池差恰为 1.48/1.08 = 37/27."""
        eng, log = _make_logged(_solo_compiled("1509", enemies=_dummy("e1", "thunder")))
        log.clear()
        _fire_ult(eng, "1509", "150903", energy=GG_ENERGY)
        ours = _hit_amounts(log, source="1509")
        theirs = run_optimizer(optimizer_driver, _opt_gilgamesh(
            "ult", cond={"kingsBurden": True}))

        assert "KINGS_BURDEN" not in eng.state.actors["1509"].modifiers, (
            "solo 无队友开大——王来背负不挂（排自身在案）")
        assert sum(ours) == pytest.approx(_gg(14.0), rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / sum(ours) == pytest.approx(
            (1 + GG_TH + 0.4) / (1 + GG_TH), rel=REL_TOL), (
            "R-GG2 差恰为 1.48/1.08 = 37/27（归属/时序差——对方常开件）")

    def test_r_gg3_a6_overflow_divergence(self, optimizer_driver):
        """R-GG3：王霸的竞逐溢出段我方待收（能量上限>140 逐目标加成——动态光环通道
        缺）——对方 base_energy=360 档 ATK_P 1.2/暴伤 1.2 vs 双方基础档 0.2，比值恰为
        (1708.71624×1.4029)/(990.76824×1.1659)."""
        eng, log = _make_logged(_solo_compiled("1509", enemies=_dummy("e1", "thunder")))
        log.clear()
        _cast(eng, "1509", "150901")
        ours = _hit_amounts(log, source="1509")
        theirs = run_optimizer(optimizer_driver, _opt_gilgamesh(
            "basic", base_energy=GG_ENERGY))

        assert theirs["stats"]["atk"] == pytest.approx(GG_ATK_G3, rel=REL_TOL), (
            "对方 360 档 ATK_P 1.2×717.948 换算回显")
        assert theirs["stats"]["cd"] == pytest.approx(1.7, rel=REL_TOL)
        assert ours[0] == pytest.approx(_gg(1.0), rel=REL_TOL), "我方基础档（待收）"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            (GG_ATK_G3 * GG_CZ_G3) / (GG_ATK * GG_CZ), rel=REL_TOL), (
            "R-GG3 差恰为 atk 区×暴伤区双差比值")

    def test_fua_counter_r_gg1(self, optimizer_driver):
        """R-GG1：连携追击 150905——官方计数双主体含吉本人（8 次攻击 → 雷 4.0 AoE），
        我方 solo 可触发；对方 UNIQUE 以 Saber 在队为闸 solo 空段 → 无对方落点，
        我方段 vs 手算钉（对方 hits==[] 同钉）；计数清零/兴致 +3/回能 10 对账."""
        eng, log = _make_logged(_solo_compiled("1509", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1509"]
        log.clear()
        for _ in range(8):
            _cast(eng, "1509", "150901")
        ours = _hit_amounts(log, source="1509")
        theirs = run_optimizer(optimizer_driver, _opt_gilgamesh("unique"))

        assert len(ours) == 9, "8 普攻 + 第 8 次触发的连携追击段"
        assert ours[:8] == pytest.approx([_gg(1.0)] * 8, rel=REL_TOL)
        assert ours[8] == pytest.approx(_gg(4.0), rel=REL_TOL), (
            "连携追击 4.0 AoE（天赋 lv10 #1）vs 手算")
        assert theirs["hits"] == [], "R-GG1：对方 Saber 依赖建模——solo UNIQUE 空段"
        assert math.isclose(st.resources["_atk_count"], 0.0), "触发即清零"
        assert math.isclose(st.resources["interest"], 3.0), "追击兴致 +3（150905 #3）"
        assert math.isclose(st.current_energy, 170.0), "8×20（普攻）+10（追击回能）"


# ===========================================================================
# L2 不死途 1504（对方 1500/Ashveil.ts 全实现）——饲饵标记+婪酣追加族
# ===========================================================================

class TestAshveilDuipai:
    """不死途 E0：饲饵减防光环/普攻/战技饲饵追加段/终结技主链（强化 FUA+婪酣追加）
    /R-AV1 头狼② FUA 暴伤结构差/R-AV2 婪酣模型差."""

    def test_basic(self, optimizer_driver):
        """普攻 1.0（饲饵开战自动标记 → 减防 0.4 常驻；头狼 team 暴伤 0.4 常驻）."""
        eng, log = _make_logged(_solo_compiled("1504", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1504"]
        assert "BAIT" in eng.state.actors["e1"].modifiers, "开战自动标记生命值最低敌人"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_dmg"], AV_CD, rel_tol=1e-9), "0.5+行迹 0.373+头狼 0.4"
        log.clear()
        _cast(eng, "1504", "150401")
        ours = _hit_amounts(log, source="1504")
        theirs = run_optimizer(optimizer_driver, _opt_ashveil("basic"))

        hand = _av(1.0)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["cd"] == pytest.approx(AV_CD, rel=REL_TOL), (
            "对方 mutual 头狼 0.4 回显")
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", AV_DEFZ), ("critMulti", AV_CZ), ("dmgBoostMulti", 1.144)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert math.isclose(st.resources["charge"], 2.0), "天赋 #1 初始充能 2（decl.current 布场）"

    def test_skill_with_bait_extra(self, optimizer_driver):
        """战技 150402：目标已是饲饵（开战自动标 e1）→ 本体 2.0 + 追加段 1.0（skill
        身份，不吃影肢 FUA 桶）+ 返 1 SP——对方 targetBait 聚合单发 3.0，段数差在案."""
        eng, log = _make_logged(_solo_compiled("1504", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1504"]
        sp0 = eng.state.skill_points
        log.clear()
        _cast(eng, "1504", "150402")
        ours = _hit_amounts(log, source="1504")
        theirs = run_optimizer(optimizer_driver, _opt_ashveil("skill"))

        hand = _av(3.0)
        assert ours == pytest.approx([_av(2.0), _av(1.0)], rel=REL_TOL), (
            "我方本体+追加段各自 vs 手算")
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL)
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(3.0, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        assert math.isclose(eng.state.skill_points, sp0), "耗 1 返 1 持平（#5=1）"
        assert math.isclose(st.resources["gluttony"], 1.0), "罪途①：施放战技 +1 层婪酣"

    def test_ult_chain_r_av1_divergence(self, optimizer_driver):
        """终结技主链：主段 4.0（比等）+ 强化 FUA 2.0 + 婪酣追加 2.0（快照补偿档——
        链内双份 +4 恰达阈值）vs 对方 FUA 静态档——R-AV1：对方头狼② FUA 暴伤 +80%
        常开（我方分域暴伤键缺待收），FUA 段暴击区差恰为 1.10365/1.06365."""
        eng, log = _make_logged(_solo_compiled("1504", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1504"]
        log.clear()
        _fire_ult(eng, "1504", "150403", energy=150.0, target="e1")
        ours = _hit_amounts(log, source="1504")
        theirs_ult = run_optimizer(optimizer_driver, _opt_ashveil("ult"))
        theirs_fua = run_optimizer(optimizer_driver, _opt_ashveil("fua"))

        assert ours[0] == pytest.approx(_av(4.0), rel=REL_TOL), "我方终结技主段 vs 手算"
        assert ours[0] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL), (
            "主段双方互对")
        hand_fua = _av(2.0, boost=0.8)                # 影肢 0.8+0.1×0（链内读取点婪酣 0）
        assert ours[1:] == pytest.approx([hand_fua, hand_fua], rel=REL_TOL), (
            "强化 FUA+婪酣追加（均读 0 层档）vs 手算")
        assert theirs_fua["hits"][0]["damage"] == pytest.approx(
            _av(2.0, cz=AV_CZ_FUA, boost=0.8), rel=REL_TOL)
        assert theirs_fua["hits"][0]["damage"] / ours[1] == pytest.approx(
            AV_CZ_FUA / AV_CZ, rel=REL_TOL), "R-AV1 FUA 段差恰为暴击区比（头狼②待收）"
        assert theirs_fua["hits"][0]["damage"] / ours[2] == pytest.approx(
            AV_CZ_FUA / AV_CZ, rel=REL_TOL)
        bd = theirs_fua["hits"][0]["breakdown"]
        assert bd["critMulti"] == pytest.approx(AV_CZ_FUA, rel=REL_TOL)
        assert bd["dmgBoostMulti"] == pytest.approx(1 + AV_TH + 0.8, rel=REL_TOL), (
            "影肢 0.8 双方同池——差只在暴伤")
        assert math.isclose(st.resources["charge"], 3.0), "2+3 → clamp 上限 3"
        assert math.isclose(st.resources["gluttony"], 0.0), "双份 +4 − 追加耗 4 = 0"

    def test_enhanced_fua_r_av2_divergence(self, optimizer_driver):
        """R-AV2：婪酣 4 开局档——我方强化 FUA/追加段影肢现场追值（0.8+0.1×4=1.2）
        vs 对方 enhancedFua 档平均化层读（(4+0)/2=2 → 1.0）+ floor(4/4)=1 段聚合 4.0
        ——段数模型与层读时序双件捆绑（R-AV1 暴伤差同在场），比值恰为
        (1.10365×2.144)/(1.06365×2.344)."""
        eng, log = _make_logged(_solo_compiled("1504", enemies=_dummy("e1", "thunder")))
        st = eng.state.actors["1504"]
        st.resources["gluttony"] = 4.0
        log.clear()
        _fire_ult(eng, "1504", "150403", energy=150.0, target="e1")
        ours = _hit_amounts(log, source="1504")
        theirs = run_optimizer(optimizer_driver, _opt_ashveil(
            "fua", cond={"enhancedFua": True, "gluttonyStacks": 4}))

        hand_fua = _av(2.0, boost=1.2)                # 影肢现场追值 0.8+0.1×4
        assert ours[1:] == pytest.approx([hand_fua, hand_fua], rel=REL_TOL), (
            "我方两段（各读 4 层档——追加段耗 4 后余 4+4−4=4 同档）vs 手算")
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(4.0, rel=REL_TOL), (
            "对方 floor(4/4)=1 追加 → 2.0+2.0 聚合")
        assert theirs["hits"][0]["damage"] == pytest.approx(
            _av(4.0, cz=AV_CZ_FUA, boost=1.0), rel=REL_TOL), (
            "对方平均化层读 (4+0)/2=2 → 影肢 1.0")
        assert theirs["hits"][0]["damage"] / sum(ours[1:]) == pytest.approx(
            (AV_CZ_FUA * (1 + AV_TH + 1.0)) / (AV_CZ * (1 + AV_TH + 1.2)), rel=REL_TOL), (
            "R-AV2 差恰为标注比值（层读时序+R-AV1 暴伤捆绑在案）")
        assert math.isclose(st.resources["gluttony"], 4.0), "4+2+2−4 = 4"
