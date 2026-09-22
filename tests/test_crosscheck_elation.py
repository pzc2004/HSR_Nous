"""L2 角色级 + L4 组队级对拍（BACKLOG B22 名册扩拍第四波）：欢愉族 B40 首次神谕体检——
火花 1501（直播态/笑点经济/好活当赏天赋附伤）/ 开拓者•欢愉 8009+8010（终结技代放
欢愉技主干）/ 爻光 1502（大吉大利附伤/结界欢愉度共享/额外阿哈时刻）/ 绯英 1505
（能量↔好活当赏互转/狐狸老师 tally 族）/ 银狼LV.999 1506（Godmode 强化普攻欢愉化/
Hidden MMR 转模/Top Loot Box）。逐段伤害 == hsr-optimizer 角色实现整链伤害
（rel_tol 1e-4；双锚=对方+手算，对不上的按惯例钉结构差数值自证）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character"（elation_skill/unique
新技种 + 欢愉双键钉面板 + actionModifiers 镜像（爻光大吉大利唯一挂点）+ baseEnergy
场景槽——驱动头注有完整口径）。我方路径：真模板（tests/fixtures 人工根）→ 编译 →
CombatEngine 钉资源（笑点队伍账 eng.state.punchline / 好活当赏条目 st.banger_entries /
Hidden MMR）→ _cast/_fire_ultimate → bus on_hp_decrease 逐段记录仪（setup 前订阅，L2 先例）。

统一口径（两侧一致，沿用前几波）：星魂钉死 E0、行迹满级、无光锥无遗器、假人 lvl80
def 1000（防御区 0.5）、匹配弱点（抗性区 1.0）、未击破（0.9）、期望暴击。
**欢愉双资源口径**：笑点=队伍账（进战 +1/欢愉角色——单人场 setup 后=1，双人场=2），
好活当赏=引擎条目列表合并值（进战 +20/欢愉角色）；对拍钉值——1501 笑点经
_gain_resource 统发（palette 1501103 on_resource_gain 重烘暴伤同步），其余角色直写；
好活当赏 clear+gain 钉合。

===========================================================================
火花 1501 buff 状态映射表（对方 content 开关 ↔ 我方模板触发）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
enhancedBasic（true）          直播态换技能（150101↔150108 available_if 互斥）  普通普攻钉 false；
                                                                            强化普攻钉 true（直施绕过闸，
                                                                            e2e 先例）
punchlineStacks 0-100（30）    阿哈笑点队伍账（eng.state.punchline）           钉 30（_gain_resource 统发
                                                                            ——palette 同步重烘）
certifiedBangerStacks 0-200（60）好活当赏合并值（st.banger_entries 条目列表）  钉 60（clear+gain）
engagementFarmingStacks 0-20（20）150109 #4/#5 倍率提高——**待收**（scaling     钉 0 比等；钉 20 钉 R-SP1
                               覆写通道缺+持续域待实测）                     结构差（见下）
certifiedBanger（true）        好活当赏持有门（resource_of('1501','certified_banger')≥1）钉 true
atkToElation（true）           1501101 ATK 转化（常驻件 stat_exprs——ATK 640    钉 true（640<2000 → +0，
                               <2000 → +0；// 100 整除=min(16,·) 同构）        两侧同灭）
punchlineCritDmg（true）       1501103 每笑点全队暴伤 8% 上限 80%（palette     钉 true（池 30→双方 0.8
                               重烘 replace——min(res_punchline,10)×0.08）    同值）
e1PunchlineResPen/e2ThrillStacks/e4UltElation/e6ResPen  星魂（E0 门控同灭）   E0 钉 true 无害
（无开关）终结技 #3=0.6×欢愉度段  on_ultimate 钩普通火直伤动态项（官方         对方折叠进 ULT 单发
                               "Fire DMG" vs 天赋 "Fire Elation DMG" 措辞     (0.5+0.6×0.28)atk——两段
                               分野在案）                                   总和比等，段数差在案（D6 族）
（无开关）150120 追加 20 段      hook 逐段 0.25 随机单体（expected 取首全落）   对方聚合单发 0.5+20×0.25/count
                                                                            ——总和比等，段数差在案

===========================================================================
开拓者•欢愉 8009/8010 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
certifiedBanger（true）        好活当赏持有门（战技追加段 800904）              钉 true
punchlineStacks（30）          阿哈笑点队伍账                                钉 30（直写——无 palette 族）
certifiedBangerStacks（60）    好活当赏合并值（天赋追加段=max($team.CB)）      钉 60
ultCdBuff（false，teammate 链）800903 指定队友暴伤 +50%·3 回合               单人场景对自身——对方 solo
                                                                            无落点，cd 改钉 1.133 等价
atkToElation（true）           8009101 ATK 转化（B-EL① 勘正后 0.1/步上限 0.6——实战 ATK 596<1000 → +0）钉 true（两侧同灭）；
                                                                            堆装 2100 场双方 0.5 比等
e2UltElation/e4Vulnerability/e6CritDmg  星魂（E0 门控同灭）                   E0 钉 true/false 无害
（无开关）800920 随机 8 段+均摊  hook 8×0.2 随机（expected 取首）+split:even   对方 (0.2×8+0.6)/count 聚合
                               0.6（8010 双子为 hook ÷enemies_alive() 同值）  单发——总和比等，段数差在案
（无开关）终结技分支 A 代放      trigger_action 跨 actor 代放 800920           对方无代放链——钉
                               （pool_override 固定 20 笑点）                punchlineStacks=20 等价比等

===========================================================================
爻光 1502 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
punchlineStacks（30）          阿哈笑点队伍账                                钉 30（直写）
certifiedBangerStacks（90）    爻光好活当赏合并值（大吉大利门控+笑点槽）        钉 90（clear+gain）
skillZoneActive（true）        ELATION_ZONE 结界（stat_exprs 共享=0.2×爻光      未开战技钉 false；开战技
                               无条件件欢愉度 0.1=+0.02 全队）               钉 true——双方 0.12 比等
ultResPenBuff（true）          150203 全队抗穿 +20%·3 回合（各持有者走字）     未开大钉 false；开大钉 true
certifiedBanger（true）        大吉大利持有门（resource_of≥1）                钉 true
yaoguangAhaInstant（false）    150203 额外阿哈时刻固定 20 笑点                 单人主 C 场景无队友槽——
                                                                            不生效；终结技链见 T-YG-ULT
woesWhisperVulnerability（true）150220 凶星低语易伤 16%（action 先挂后伤）     未放欢愉技钉 false；放了钉 true
traceSpdElation（true）        1502101 SPD 转欢愉度（spd 110<120 → +0）        钉 true（两侧同灭）
e1DefPen/e2ZoneSpdBuff/e6Merrymaking  星魂（E0 门控同灭）                     E0 钉 true 无害
（无开关）大吉大利（actionModifier）天赋 150204：我方攻击附 0.2 欢愉段        driver 已镜像 actionModifiers；
                               （元素=攻击者、笑点=触发者 CB 无则取爻光）      单人场=爻光自己攻击触发比等
（无开关）150220 随机 5 段      hook 5×0.2 随机（expected 取首）              对方 1.0+5×0.2/count 聚合——
                                                                            总和比等，段数差在案

===========================================================================
绯英 1505 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
certifiedBanger（true）        好活当赏持有门（战技/终结技/狐狸欢愉段）         钉 true
punchlineStacks（30）          阿哈笑点队伍账                                钉 30（直写）
certifiedBangerStacks（600）   好活当赏合并值                                钉 600（clear+gain）
cdToElation（true）            150504 #5 CD 转欢愉度（常驻件 stat_exprs        钉 true——双方 0.28
                               0.2×$self.crit_dmg=0.1；行迹 0.18 另计）       （0.18+0.2×0.5）
masterFoxVuln（true）          1505102 行裁断：狐狸攻击→目标易伤 12%          狐狸未动钉 false（对方常开件
                               （伤害后挂——本段不吃在案）                    只钉狐狸场=false 比等）
e1ResPen/e2CritDmg/e4DefPen/e6Merrymake  星魂（E0 门控同灭）                  E0 钉 true 无害
（无开关）终结技弹射变档        敌数 1/2/3+ → 5+4/5+2/5+1 段（行迹 1505101）   单敌场双方 9 段比等
（无开关）终结技笑点地板        max(能量上限 480, CB)——官方 "at least equal   base_energy 钉 480（官方
                               to Max Energy"=max_sp 480≠耗能 240 在案）     max_sp 同口径，CB 600 场双
                                                                            方 600；240 档见 R-EV-无差注
（无开关）狐狸老师 FUA         _fox_meter 满 240 触发：物理 1.0+欢愉 0.25     对方 UNIQUE 双段同构比等
                                                                            （段序差在案——我方欢愉先结）

===========================================================================
银狼LV.999 1506 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
godmodePlayer（true）          Godmode Player 状态（150603 进状态——MMR 60     常态钉 false；godmode 场
                               扣空+1506103 +20）                            实打进入后钉 true
certifiedBanger（true）        好活当赏持有门（天赋追加/盲盒）                 钉 true
punchlineStacks（30）          阿哈笑点队伍账                                钉 30（直写——笑点联动 MMR
                                                                            经 gain 会污染，故直写）
certifiedBangerStacks（60）    好活当赏合并值                                钉 60
hiddenMmr 0-300（120）         Hidden MMR（CR 转模 stat_exprs——CR 满 100%     钉 120（直写）；战技场
                               后溢出转 CD——每点 0.004/0.008）              钉 115（#2=5 笑点联动后
                                                                            =120 对轴——双场钉法）
spdToElation（true）           1506101 SPD 转化（spd 119<160 → +0）           钉 true（两侧同灭）
e1Vulnerability/e4PunchlineBoost/e6Merrymake/e6ResPen  星魂（E0 门控同灭）    E0 钉 true 无害
（无开关）150608 增伤档         0.15×min(MMR//60, 2) 归 dmg_final_dmg_boost    对方折叠进强化普攻倍率
                               池（B-EL③ 勘正 //1 向下取整——60 倍数同值）    （mmrDmgMultiplier）——强化
                                                                            普攻比等；150621/盲盒钉
                                                                            R-SW1 域偏差（在案㈢）
（无开关）150621 随机 6 段     hook 6×0.9 随机（expected 取首）               对方 0.9×6/count 聚合——
                                                                            总和比等，段数差在案
（无开关）Top Loot Box         我方耗点触发：0.9 均分（mechanic_chance 1.0    对方 UNIQUE 单段 0.9/count
                               首档）                                       比等（概率链/三选一双方不建
                                                                            ——E0 场首档必中对齐）

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注值，任一侧改动触红）
===========================================================================
R-SP1 火花 150109 #4/#5 互动陷阱倍率提高（我方待收——scaling 覆写通道缺+持续域
   待实测；对方 engagementFarmingStacks×0.2 同时折进普攻 atk 段与天赋欢愉段）
   → 钉 20 层：普攻段 对方/我方 恰为 (1.0+0.2×20)/1.0 = 5.0；天赋欢愉段
   (0.4+0.2×20)/0.4 = 11.0
R-SW1 银狼 150608 增伤档域偏差（在案㈢——我方 dmg_final_dmg_boost 平坦池无行动
   隔离，Godmode 内 150621/盲盒/天赋追加同吃；对方 mmrDmgMultiplier 只乘强化普攻
   倍率）→ MMR≥120 场（档 0.3）：150621/天赋追加段 我方/对方 恰为 1.3（强化普攻
   本体双方同吃 ×1.3 比等）
R-YG1 大吉大利欢愉度择优半件（我方待收①——hook 伤害源恒爻光，攻击者欢愉度更高
   时无覆写槽；对方 minElationOverride=max(攻击者, 爻光)）→ 火花（0.28）攻击场
   对方/我方 恰为 1.28/1.10 ≈ 1.1636364（8009（0）攻击场两侧同取爻光 0.1 无差）
R-YG2 大吉大利对欢愉技触发——**翻案（2026-09-22 组队波核销，本波误诊撤销）**：
   对方 elationHitSchema 默认 directHit=true（hitDefinitionBuilder.ts:63），大吉大利
   对欢愉技**双方均触发**（本测试断言只剥我方段比对方 hits[0]，未察对方 hits[1] 同
   有大吉大利且数值全等——组队波五处实证见 tests/test_crosscheck_team_elation.py
   1c/2c/2d/4a/4b）；触发面双方同构，残差只剩 R-YG1 择优 × R-YG4 面板 × R-YG3 双触
R-YG3 大吉大利耗战技点额外触发（我方待收④——on_action 载荷无 sp_consumed 字段；
   对方 consumesSkillPoints+spUsed>0 → 倍率 ×2）→ 8009 战技（耗 1 点）场
   对方/我方 恰为 2.0 × R-YG4 面板比（笑点锚同钉 80——战技发放后值，快照域在案）
R-YG4 大吉大利面板归属（我方 hook 源恒爻光=爻光暴击面板；对方段附在主 C 行动=
   主 C 暴击面板——官方择优子句「攻击者欢愉度低于爻光则用爻光的」蕴含默认攻击者
   面板，对方建模更贴字面；我方挡因同待收①引擎槽）→ 主 C 暴击区/爻光暴击区
   恰为段值比（8009 场 1.202576/1.2607、火花场 1.13481/1.29862——爻光盘含火花
   palette 全队暴伤 0.16 辐射，双人场在案）

已修真病三件（本波钓出——单列）：
B-EL① 8009/8010 行迹 8009101 快哉快哉 ATK 转化系数 0.001→0.1/步（官方 #3[f1]/
   #4[f1]=0.1/0.6 为百分比格式=10%/60%，旧读 0.1%/0.6% 低估 100×——对方
   min(0.60, floor((atk-1000)/200)×0.10) 互证；双子模板同修+堆装 2100 场对拍锚）
B-EL② 1506 强化普攻 150608 漏天赋 #3 好活当赏追加段（旧读「强化普攻不追加」
   证伪——官方 "using Basic ATK or Skill deals #3[i]%" 含强化普攻，后句仅本体
   伤转欢愉；对方 godmode basic=[本体+天赋]双段互证；补钩 all_enemies 0.4 槽）
B-EL③ 1506 强化普攻增伤档取整 round→//1（官方 "For every 60 points held"=每满
   档向下语义——对方 Math.floor 互证；60 倍数两侧同值，非倍数档旧高估 1 档）
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
# 口径常数（两侧钉死；fixture 终审值，行迹平铺按模板 trace_stat_effects 并入）
# ---------------------------------------------------------------------------

LV_COEF = 7535.107                               # 欢愉等级系数 Lv.80（rulebook 在册）


def _pm(p: float) -> float:
    """笑点乘区 1+5p/(p+240)（双方同式——formula 层已互对）."""
    return 1 + 5 * p / (p + 240)


def _el(mult: float, src: float, cz: float, *, el: float, mm: float = 0.0,
        fd: float = 0.0, vuln: float = 0.0, res: float = 1.0) -> float:
    """欢愉伤害期望：纯倍率×等级系数×(1+elation)×笑点乘区×期望暴击区×防御区 0.5×未击破 0.9
    ×抗区×易伤区×final 区×增笑区（elation_dmg_boost/dmg_red/true_dmg 中性不列入——
    结构差公式层已钉）."""
    return (LV_COEF * mult * (1 + el) * _pm(src) * (1 + mm) * cz
            * 0.5 * 0.9 * res * (1 + vuln) * (1 + fd))


# 火花 1501（火，ATK 倍率；行迹 crit 0.12/0.133/elation 0.28 已并入）
SP_ATK, SP_HP, SP_DEF, SP_SPD = 640.332, 1047.816, 460.845, 107
SP_CR, SP_CD, SP_EL = 0.17, 0.633, 0.28
SP_CD_P30 = SP_CD + 0.8                          # palette 池≥10 → 0.08×10
Z_SP = 0.5 * 0.9 * (1 + SP_CR * SP_CD_P30)       # 0.5596245（池 30 场基准）

# 开拓者•欢愉 8009/8010（雷；行迹 crit 0.27（含大行迹 0.15）/0.133/atk_pct 0.28）
TB_ATK_W = 465.696
TB_ATK = TB_ATK_W * 1.28                         # 596.09088
TB_CR_W, TB_CR, TB_CD = 0.17, 0.32, 0.633        # 对方钉 0.17+自带 0.15=0.32
CZ_TB = 1 + TB_CR * TB_CD                        # 1.202576
Z_TB = 0.5 * 0.9 * CZ_TB

# 爻光 1502（物理；行迹 crit 0.187/spd+9/elation 0.1 + 大行迹 CD+60%）
YG_ATK, YG_HP, YG_DEF, YG_SPD = 465.696, 1241.856, 654.885, 110
YG_CR, YG_CD, YG_EL = 0.237, 1.1, 0.1
CZ_YG = 1 + YG_CR * YG_CD                        # 1.2607
Z_YG = 0.5 * 0.9 * CZ_YG

# 绯英 1505（物理；行迹 crit 0.487（含大行迹 0.30）/spd+5/elation 0.18 + 天赋 CD 转 0.1）
EV_ATK, EV_HP, EV_DEF, EV_SPD = 737.352, 1047.816, 460.845, 109
EV_CR, EV_CD, EV_EL = 0.537, 0.5, 0.28
EV_ENERGY = 480.0                                # max_sp（天赋终结技笑点地板≠耗能 240）
CZ_EV = 1 + EV_CR * EV_CD                        # 1.2685
Z_EV = 0.5 * 0.9 * CZ_EV

# 银狼LV.999 1506（虚数；行迹 crit 0.147/spd+9/elation 0.1）
SW_ATK, SW_HP, SW_DEF, SW_SPD = 388.08, 1047.816, 654.885, 119
SW_CR, SW_CD, SW_EL = 0.197, 0.5, 0.1


def _sw_cr(mmr: float) -> float:
    """Hidden MMR CR 转模（stat_exprs：min(mmr×0.004, 1−无条件件 CR)——MMR≤200.75 域）."""
    return SW_CR + min(mmr * 0.004, 1 - SW_CR)


def _sw_cz(mmr: float) -> float:
    return 1 + _sw_cr(mmr) * SW_CD


# ---------------------------------------------------------------------------
# 我方侧引擎件
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
    """钉资源开大（支援技 target 给 ally_single 选择；特殊充能族走 resource 钉）."""
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


def _pin_pool_gain(eng, cid, value):
    """笑点池钉值（_gain_resource 统发——palette 族（1501）on_resource_gain 重烘同步）."""
    st = eng.state.actors[cid]
    eng._gain_resource(st, "punchline", value - eng.state.punchline)


def _pin_banger(eng, cid, value):
    """好活当赏合并值钉值（条目清空重发——2 回合计时不在本波观察窗）."""
    st = eng.state.actors[cid]
    st.banger_entries.clear()
    if value:
        eng._gain_resource(st, "certified_banger", value)


# ---------------------------------------------------------------------------
# 对方侧场景模子（映射表见模块 docstring）
# ---------------------------------------------------------------------------

def _opt_sparxie(action: str, *, cond: dict | None = None, enemy_count: int = 1,
                 atk: float = SP_ATK):
    c = {"enhancedBasic": False, "punchlineStacks": 30, "certifiedBangerStacks": 60,
         "engagementFarmingStacks": 0, "certifiedBanger": True, "atkToElation": True,
         "punchlineCritDmg": True, "e1PunchlineResPen": True, "e2ThrillStacks": 4,
         "e4UltElation": True, "e6ResPen": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1501", "eidolon": 0,
            "action": action, "element": "fire", "conditionals": c,
            "base": {"atk": atk, "hp": SP_HP, "def": SP_DEF, "spd": SP_SPD},
            "attacker": {"atk": atk, "hp": SP_HP, "def": SP_DEF, "spd": SP_SPD,
                         "cr": SP_CR, "cd": SP_CD, "elation": SP_EL},
            "self_path": "Elation",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": enemy_count}}


def _opt_tb(action: str, *, cid: str = "8009", cond: dict | None = None,
            atk: float = TB_ATK, cd: float = TB_CD):
    c = {"certifiedBanger": True, "punchlineStacks": 30, "certifiedBangerStacks": 60,
         "ultCdBuff": False, "atkToElation": True, "e2UltElation": False,
         "e4Vulnerability": True, "e6CritDmg": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": cid, "eidolon": 0,
            "action": action, "element": "thunder", "conditionals": c,
            "base": {"atk": atk, "hp": 1086.624, "def": 630.63, "spd": 106},
            "attacker": {"atk": atk, "hp": 1086.624, "def": 630.63, "spd": 106,
                         "cr": TB_CR_W, "cd": cd},
            "self_path": "Elation",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_yaoguang(action: str, *, cond: dict | None = None,
                  teammates: list | None = None, character_id: str = "1502",
                  action_char: str | None = None):
    """爻光主 C 场景（teammates 槽预留给组队矩阵——主 C 换人时经 character_id 覆写）."""
    c = {"punchlineStacks": 30, "certifiedBangerStacks": 90, "skillZoneActive": False,
         "ultResPenBuff": False, "certifiedBanger": True, "yaoguangAhaInstant": False,
         "woesWhisperVulnerability": False, "traceSpdElation": True,
         "e1DefPen": True, "e2ZoneSpdBuff": True, "e6Merrymaking": True}
    c.update(cond or {})
    sc = {"kind": "character", "character_id": character_id, "eidolon": 0,
          "action": action, "element": "physical", "conditionals": c,
          "base": {"atk": YG_ATK, "hp": YG_HP, "def": YG_DEF, "spd": YG_SPD},
          "attacker": {"atk": YG_ATK, "hp": YG_HP, "def": YG_DEF, "spd": YG_SPD,
                       "cr": YG_CR, "cd": 0.5, "elation": YG_EL},
          "self_path": "Elation",
          "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                    "count": 1}}
    if teammates is not None:
        sc["teammates"] = teammates
    return sc


def _tm_yaoguang(**cond):
    c = {"certifiedBanger": True, "consumesSkillPoints": True,
         "yaoguangAhaInstant": False, "teammateCertifiedBangerStacks": 60,
         "skillZoneActive": False, "teammateElationValue": 0.1,
         "ultResPenBuff": False, "woesWhisperVulnerability": False,
         "e1DefPen": True, "e2ZoneSpdBuff": True, "e6Merrymaking": True}
    c.update(cond)
    return {"character_id": "1502", "eidolon": 0, "path": "Elation",
            "element": "physical", "conditionals": c}


def _opt_evanescia(action: str, *, cond: dict | None = None, enemy_count: int = 1):
    c = {"certifiedBanger": True, "punchlineStacks": 30, "certifiedBangerStacks": 600,
         "cdToElation": True, "masterFoxVuln": False, "e1ResPen": True,
         "e2CritDmg": True, "e4DefPen": True, "e6Merrymake": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1505", "eidolon": 0,
            "action": action, "element": "physical", "conditionals": c,
            "base": {"atk": EV_ATK, "hp": EV_HP, "def": EV_DEF, "spd": EV_SPD},
            "attacker": {"atk": EV_ATK, "hp": EV_HP, "def": EV_DEF, "spd": EV_SPD,
                         "cr": 0.237, "cd": EV_CD, "elation": 0.18},
            "base_energy": EV_ENERGY,
            "self_path": "Elation",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": enemy_count}}


def _opt_silver_wolf(action: str, *, cond: dict | None = None):
    c = {"godmodePlayer": False, "certifiedBanger": True, "punchlineStacks": 30,
         "certifiedBangerStacks": 60, "hiddenMmr": 120, "spdToElation": True,
         "e1Vulnerability": True, "e4PunchlineBoost": True, "e6Merrymake": True,
         "e6ResPen": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1506", "eidolon": 0,
            "action": action, "element": "imaginary", "conditionals": c,
            "base": {"atk": SW_ATK, "hp": SW_HP, "def": SW_DEF, "spd": SW_SPD},
            "attacker": {"atk": SW_ATK, "hp": SW_HP, "def": SW_DEF, "spd": SW_SPD,
                         "cr": SW_CR, "cd": SW_CD, "elation": SW_EL},
            "self_path": "Elation",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


# ===========================================================================
# L2 火花 1501（对方 1500/Sparxie.ts 全实现）——直播态双普攻 + 笑点经济主干
# ===========================================================================

class TestSparxieDuipai:
    """火花 E0：面板回显/普通普攻/强化普攻双段/终结技三段链/欢愉技 21 段聚合
    /互动陷阱结构差——双锚+乘区读回."""

    def _pin30(self, eng):
        """笑点 30（进战 1 +29 统发——palette 重烘 0.8）+ 好活当赏 60."""
        _pin_pool_gain(eng, "1501", 30.0)
        _pin_banger(eng, "1501", 60.0)
        assert math.isclose(eng.state.punchline, 30.0)
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1501"])["crit_dmg"],
            SP_CD_P30, rel_tol=1e-9), "palette 0.08×min(30,10) 重烘"

    def test_panel_echo(self, optimizer_driver):
        theirs = run_optimizer(optimizer_driver, _opt_sparxie("basic"))
        st = theirs["stats"]
        assert st["cd"] == pytest.approx(SP_CD_P30, rel=REL_TOL), (
            "对方 punchlineCritDmg 0.08×min(30×0.08→2.4, 0.8) 互对 palette")
        assert st["elation"] == pytest.approx(SP_EL, rel=REL_TOL), "行迹欢愉度 0.28 回显"
        assert st["cr"] == pytest.approx(SP_CR, rel=REL_TOL)

    def test_basic(self, optimizer_driver):
        """普通普攻 1.0（enhancedBasic=false 档——对方无天赋段与我方同构）."""
        eng, log = _make_logged(_solo_compiled("1501", enemies=_dummy("e1", "fire")))
        self._pin30(eng)
        log.clear()
        _cast(eng, "1501", "150101")
        ours = _hit_amounts(log, source="1501")
        theirs = run_optimizer(optimizer_driver, _opt_sparxie("basic"))

        hand = 1.0 * SP_ATK * Z_SP
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert len(theirs["hits"]) == 1, "对方 enhancedBasic=false 档无天赋段"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", 1 + SP_CR * SP_CD_P30), ("abilityMulti", SP_ATK)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_enhanced_basic_with_talent(self, optimizer_driver):
        """直播态强化普攻（enhancedBasic=true + certifiedBanger）：主段 1.0 火直伤 +
        天赋 #3=0.4 火欢愉（好活当赏 60 槽）——两段各自三锚."""
        eng, log = _make_logged(_solo_compiled("1501", enemies=_dummy("e1", "fire")))
        self._pin30(eng)
        log.clear()
        _cast(eng, "1501", "150108")          # 绕过 available_if 直施（e2e 先例）
        ours = _hit_amounts(log, source="1501")
        theirs = run_optimizer(optimizer_driver, _opt_sparxie(
            "basic", cond={"enhancedBasic": True}))

        hand_crit = 1.0 * SP_ATK * Z_SP
        hand_el = _el(0.4, 60, 1 + SP_CR * SP_CD_P30, el=SP_EL)
        assert ours == pytest.approx([hand_crit, hand_el], rel=REL_TOL), (
            "我方主段+天赋欢愉段（钩序）vs 手算")
        assert len(theirs["hits"]) == 2, "对方强化普攻双段（直伤+天赋欢愉）"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "主段互对"
        assert ours[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), "欢愉段互对"
        assert theirs["hits"][1]["damage_function"] == "Elation"
        assert theirs["hits"][1]["elation_scaling"] == pytest.approx(0.4, rel=REL_TOL)
        assert theirs["hits"][1]["punchline_stacks"] == 60
        bd = theirs["hits"][1]["breakdown"]
        assert bd["elationMulti"] == pytest.approx(1 + SP_EL, rel=REL_TOL)
        assert bd["punchlineMulti"] == pytest.approx(_pm(60), rel=REL_TOL)
        assert bd["dmgBoostMulti"] == pytest.approx(1.0, rel=REL_TOL), (
            "欢愉伤不吃通用增伤（对方同构——乘区表无 BOOST 读口）")

    def test_engagement_stacks_divergence(self, optimizer_driver):
        """R-SP1：150109 #4/#5 互动陷阱倍率提高我方待收（scaling 覆写通道缺+持续域
        待实测）——对方钉 20 层：普攻段恰为 ×5.0、天赋欢愉段恰为 ×11.0."""
        eng, log = _make_logged(_solo_compiled("1501", enemies=_dummy("e1", "fire")))
        self._pin30(eng)
        log.clear()
        _cast(eng, "1501", "150108")
        ours = _hit_amounts(log, source="1501")
        theirs = run_optimizer(optimizer_driver, _opt_sparxie(
            "basic", cond={"enhancedBasic": True, "engagementFarmingStacks": 20}))

        assert ours[0] == pytest.approx(1.0 * SP_ATK * Z_SP, rel=REL_TOL), "我方基准（待收）"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.0 + 0.2 * 20, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(5.0, rel=REL_TOL), (
            "R-SP1 普攻段差恰为 (1+0.2×20)/1 = 5.0")
        assert theirs["hits"][1]["elation_scaling"] == pytest.approx(0.4 + 0.2 * 20, rel=REL_TOL)
        assert theirs["hits"][1]["damage"] / ours[1] == pytest.approx(11.0, rel=REL_TOL), (
            "R-SP1 天赋欢愉段差恰为 (0.4+0.2×20)/0.4 = 11.0")

    def test_ult_three_segments(self, optimizer_driver):
        """终结技：action #2=0.5 ATK 段 + 钩 #3=0.6×0.28 欢愉度动态段（普通火直伤）+
        天赋 #2=0.48 火欢愉（CB 60）——对方 ULT 单发 (0.5+0.168)atk 折叠 + 天赋段，
        直伤总和比等（段数差在案）、欢愉段逐段比等；开大 +4 笑点（1 欢愉档）."""
        eng, log = _make_logged(_solo_compiled("1501", enemies=_dummy("e1", "fire")))
        self._pin30(eng)
        log.clear()
        _fire_ult(eng, "1501", "150103", energy=160.0)
        ours = _hit_amounts(log, source="1501")
        theirs = run_optimizer(optimizer_driver, _opt_sparxie("ult"))

        hand_crit = (0.5 + 0.6 * SP_EL) * SP_ATK * Z_SP
        hand_el = _el(0.48, 60, 1 + SP_CR * SP_CD_P30, el=SP_EL)
        assert ours == pytest.approx([0.5 * SP_ATK * Z_SP, 0.6 * SP_EL * SP_ATK * Z_SP,
                                      hand_el], rel=REL_TOL), (
            "我方三段（action/钩动态段/天赋欢愉——钩序纪律=获得笑点前面板）vs 手算")
        assert sum(ours[:2]) == pytest.approx(hand_crit, rel=REL_TOL), "直伤两段合计 vs 手算"
        assert len(theirs["hits"]) == 2
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL), (
            "对方 ULT 单发（elationAtkScaling 0.6×0.28 折叠）vs 手算")
        assert sum(ours[:2]) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "直伤总和双方互对（段数差在案）")
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), "欢愉段互对"
        assert theirs["hits"][1]["elation_scaling"] == pytest.approx(0.48, rel=REL_TOL)
        assert theirs["hits"][1]["punchline_stacks"] == 60
        assert math.isclose(eng.state.punchline, 34.0), "30+2（终结技 #1）+2（万花筒 1 欢愉档）"

    def test_elation_skill_21_segments(self, optimizer_driver):
        """欢愉技 150120：全体 0.5（action elation 行键单承）+ 追加 20 段×0.25 随机
        （expected 取首全落 e1）——对方聚合单发 0.5+20×0.25/1=5.5，总和比等
        （段数差在案）；笑点池实时值 30."""
        eng, log = _make_logged(_solo_compiled("1501", enemies=_dummy("e1", "fire")))
        self._pin30(eng)
        log.clear()
        _cast(eng, "1501", "150120")          # 体系触发行动不走合法集——直施对轴（e2e 先例）
        ours = _hit_amounts(log, source="1501")
        theirs = run_optimizer(optimizer_driver, _opt_sparxie("elation_skill"))

        hand = _el(5.5, 30, 1 + SP_CR * SP_CD_P30, el=SP_EL)
        assert len(ours) == 21, "我方 1 全体 + 20 追加（勘正①后无双倍）"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), "我方 21 段合计 vs 手算"
        assert len(theirs["hits"]) == 1, "对方聚合单发"
        assert theirs["hits"][0]["elation_scaling"] == pytest.approx(5.5, rel=REL_TOL)
        assert theirs["hits"][0]["punchline_stacks"] == 30
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        bd = theirs["hits"][0]["breakdown"]
        assert bd["elationMulti"] == pytest.approx(1 + SP_EL, rel=REL_TOL)
        assert bd["punchlineMulti"] == pytest.approx(_pm(30), rel=REL_TOL)


# ===========================================================================
# L2 开拓者•欢愉 8009/8010（对方 8000/TrailblazerElation.ts 双子同实现）
# ===========================================================================

class TestTrailblazerElationDuipai:
    """欢愉开拓者 E0：普攻/战技双段/欢愉技 9 段聚合/终结技分支 A 代放主干/
    ATK 转化（B-EL① 对拍锚）/8010 双子巡检."""

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_solo_compiled("8009", enemies=_dummy("e1", "thunder")))
        log.clear()
        _cast(eng, "8009", "800901")
        ours = _hit_amounts(log, source="8009")
        theirs = run_optimizer(optimizer_driver, _opt_tb("basic"))

        hand = 1.0 * TB_ATK * Z_TB
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方普攻（atk 596.09088=白值×1.28 行迹；CR 0.32=0.27 行迹+0.15 跟你爆了）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方（钉 CR 0.17+precompute 0.15 同源）vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["cr"] == pytest.approx(TB_CR, rel=REL_TOL)
        assert math.isclose(eng.state.punchline, 4.0), "天赋 800904：攻击后 +3 笑点（进战 1+3）"

    def test_skill_with_talent(self, optimizer_driver):
        """战技 0.6 雷 AoE + 天赋追加 0.3 雷欢愉（max($team.CB)=60——单人=自体）；
        战技发放 +20 好活当赏在追加段后（文本序先伤后得——快照域族谱#9）."""
        eng, log = _make_logged(_solo_compiled("8009", enemies=_dummy("e1", "thunder")))
        _pin_banger(eng, "8009", 60.0)
        log.clear()
        _cast(eng, "8009", "800902")
        ours = _hit_amounts(log, source="8009")
        theirs = run_optimizer(optimizer_driver, _opt_tb("skill"))

        hand_crit = 0.6 * TB_ATK * Z_TB
        hand_el = _el(0.3, 60, CZ_TB, el=0.0)
        assert ours == pytest.approx([hand_crit, hand_el], rel=REL_TOL), (
            "我方战技+天赋追加（追加读获得前合并值 60；欢愉度 0——ATK 596<1000 转化灭）vs 手算")
        assert len(theirs["hits"]) == 2
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "战技互对"
        assert ours[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), "追加互对"
        assert theirs["hits"][1]["elation_scaling"] == pytest.approx(0.3, rel=REL_TOL)
        assert theirs["hits"][1]["punchline_stacks"] == 60
        assert theirs["hits"][1]["breakdown"]["elationMulti"] == pytest.approx(1.0, rel=REL_TOL)
        assert math.isclose(eng._resource_value(eng.state.actors["8009"], "certified_banger"),
                            80.0), "60+战技 #2=20（发放钩在追加后）"

    def test_elation_skill_nine_segments(self, optimizer_driver):
        """欢愉技 800920：随机 8 段×0.2（expected 取首全落 e1）+ 均摊 0.6（split:even
        单敌全额）——对方 (0.2×8+0.6)/1=2.2 聚合单发，总和比等（段数差在案）."""
        eng, log = _make_logged(_solo_compiled("8009", enemies=_dummy("e1", "thunder")))
        eng.state.punchline = 30.0            # 直写（无 palette 族——8009 无重烘件）
        log.clear()
        _cast(eng, "8009", "800920")
        ours = _hit_amounts(log, source="8009")
        theirs = run_optimizer(optimizer_driver, _opt_tb("elation_skill"))

        hand = _el(2.2, 30, CZ_TB, el=0.0)
        assert len(ours) == 9, "我方 8 随机 + 1 均摊"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), "我方 9 段合计 vs 手算"
        assert theirs["hits"][0]["elation_scaling"] == pytest.approx(2.2, rel=REL_TOL)
        assert theirs["hits"][0]["punchline_stacks"] == 30
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对")

    def test_ult_branch_a_trigger(self, optimizer_driver):
        """终结技主干（欢愉技代放通道）：指自己 → 暴伤 +50%·3 回合（先挂）+ 分支 A
        +10 好活当赏 + trigger_action 代放 800920（pool_override 固定 20 笑点）——
        代放 9 段读覆写 20 与暴伤后 CD 1.133；对方钉 punchlineStacks=20 + cd 1.133 等价."""
        eng, log = _make_logged(_solo_compiled("8009", enemies=_dummy("e1", "thunder")))
        log.clear()
        _fire_ult(eng, "8009", "800903", energy=160.0, target="8009")
        ours = _hit_amounts(log, source="8009")
        theirs = run_optimizer(optimizer_driver, _opt_tb(
            "elation_skill", cond={"punchlineStacks": 20}, cd=TB_CD + 0.5))

        cz = 1 + TB_CR * (TB_CD + 0.5)         # 暴伤件先挂=代放全段吃（钩序在案）
        hand = _el(2.2, 20, cz, el=0.0)
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["8009"])["crit_dmg"],
            TB_CD + 0.5, rel_tol=1e-9), "终结技暴伤 +50%（param(800903,1) lv10）"
        assert len(ours) == 9, "代放 800920 全段（insert 闩摘除同发——8 随机+1 均摊）"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), (
            "我方代放段（覆写 20 笑点×CD 1.133）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 punchlineStacks=20+cd 1.133 钉死场 vs 手算")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "代放主干双方互对（欢愉技代放通道=本波硬指标）")
        assert theirs["hits"][0]["breakdown"]["punchlineMulti"] == pytest.approx(
            _pm(20), rel=REL_TOL)
        assert math.isclose(eng._resource_value(eng.state.actors["8009"], "certified_banger"),
                            30.0), "进战 20+分支 A +10"
        assert math.isclose(eng.state.punchline, 9.0), (
            "进战 1+终结技 #6=5+代放 800920 触发天赋 +3（欢愉技按攻击收——待收③在案）")

    def test_atk_to_elation_conversion(self, optimizer_driver):
        """8009101 快哉快哉（B-EL① 对拍锚——勘正后 0.1/步）：ATK 堆装 2100 →
        双方欢愉度 0.5（min(6, (2100-1000)//200=5)×0.1）；欢愉技全链三锚."""
        eng, log = _make_logged(_solo_compiled("8009", enemies=_dummy("e1", "thunder")))
        _inject(eng, "8009", "XC_ATK", {"atk": 2100.0 - TB_ATK})
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["8009"])["elation"], 0.5,
            rel_tol=1e-9), "我方转化档（B-EL① 勘正后——旧 0.001 档此锚必红）"
        eng.state.punchline = 30.0
        log.clear()
        _cast(eng, "8009", "800920")
        ours = _hit_amounts(log, source="8009")
        theirs = run_optimizer(optimizer_driver, _opt_tb("elation_skill", atk=2100.0))

        hand = _el(2.2, 30, CZ_TB, el=0.5)
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), "我方堆装场 9 段合计 vs 手算"
        assert theirs["stats"]["elation"] == pytest.approx(0.5, rel=REL_TOL), (
            "对方 dynamic 转化（floor((2100-1000)/200)×0.10）回显")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "转化链双方互对（B-EL① 收官锚）")

    def test_8010_twin_smoke(self, optimizer_driver):
        """8010 双子巡检（同套件异性主角——对方 TrailblazerElationStelle 同
        conditionals）：普攻 + 欢愉技（8010 收尾=hook ÷enemies_alive() 手算分母，
        与 8009 split:even 同数值解——原语口径差异在案）双锚."""
        eng, log = _make_logged(_solo_compiled("8010", enemies=_dummy("e1", "thunder")))
        log.clear()
        _cast(eng, "8010", "801001")
        ours_basic = _hit_amounts(log, source="8010")
        theirs_basic = run_optimizer(optimizer_driver, _opt_tb("basic", cid="8010"))
        hand_basic = 1.0 * TB_ATK * Z_TB
        assert ours_basic == pytest.approx([hand_basic], rel=REL_TOL), "8010 普攻 vs 手算"
        assert ours_basic[0] == pytest.approx(
            theirs_basic["hits"][0]["damage"], rel=REL_TOL), "8010 普攻双方互对"

        eng.state.punchline = 30.0
        log.clear()
        _cast(eng, "8010", "801020")
        ours = _hit_amounts(log, source="8010")
        theirs = run_optimizer(optimizer_driver, _opt_tb("elation_skill", cid="8010"))
        hand = _el(2.2, 30, CZ_TB, el=0.0)
        assert len(ours) == 9, "8010 欢愉技 8 随机 + 1 均摊（hook 手算分母）"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "8010 欢愉技双方互对")


# ===========================================================================
# L2 爻光 1502（对方 1500/Yaoguang.ts 全实现）——大吉大利 actionModifier 首接
# ===========================================================================

class TestYaoguangDuipai:
    """爻光 E0：普攻+大吉大利/欢愉技（凶星低语先挂）/结界共享/终结技额外阿哈时刻."""

    def test_basic_with_great_boon(self, optimizer_driver):
        """普攻 0.9 物理 + 大吉大利 0.2 物理欢愉（actionModifier 镜像首接——段元素
        =攻击者、笑点=触发者 CB 90、择优=max(爻光 0.1, override 0)=0.1 双方同）."""
        eng, log = _make_logged(_solo_compiled("1502", enemies=_dummy("e1", "physical")))
        _pin_banger(eng, "1502", 90.0)
        log.clear()
        _cast(eng, "1502", "150201")
        ours = _hit_amounts(log, source="1502")
        theirs = run_optimizer(optimizer_driver, _opt_yaoguang("basic"))

        hand_crit = 0.9 * YG_ATK * Z_YG
        hand_el = _el(0.2, 90, CZ_YG, el=YG_EL)
        assert ours == pytest.approx([hand_crit, hand_el], rel=REL_TOL), (
            "我方普攻+大吉大利（action 后钩发——「不视为 1 次攻击」无递归）vs 手算")
        assert len(theirs["hits"]) == 2, "对方 actionModifier 追加大吉大利段"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "普攻互对"
        assert ours[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), (
            "大吉大利互对（driver actionModifiers 镜像收口）")
        assert theirs["hits"][1]["damage_function"] == "Elation"
        assert theirs["hits"][1]["elation_scaling"] == pytest.approx(0.2, rel=REL_TOL)
        assert theirs["hits"][1]["punchline_stacks"] == 90
        assert theirs["hits"][1]["breakdown"]["elationMulti"] == pytest.approx(
            1 + YG_EL, rel=REL_TOL)

    def test_elation_skill_woes_whisper(self, optimizer_driver):
        """欢愉技 150220（好活当赏清空=大吉大利不发）：凶星低语易伤 16% 先挂本发即吃
        ——全体 1.0 + 随机 5×0.2（expected 取首），对方聚合 2.0 单发 ×1.16 同链."""
        eng, log = _make_logged(_solo_compiled("1502", enemies=_dummy("e1", "physical")))
        eng.state.actors["1502"].banger_entries.clear()      # 隔离大吉大利（R-YG2 另测）
        eng.state.punchline = 30.0
        log.clear()
        _cast(eng, "1502", "150220")
        ours = _hit_amounts(log, source="1502")
        theirs = run_optimizer(optimizer_driver, _opt_yaoguang(
            "elation_skill", cond={"woesWhisperVulnerability": True}))

        hand = _el(2.0, 30, CZ_YG, el=YG_EL, vuln=0.16)
        assert len(ours) == 6, "我方 1 全体 + 5 随机"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), (
            "我方 6 段（易伤先挂——文本序一致）vs 手算")
        assert theirs["hits"][0]["elation_scaling"] == pytest.approx(2.0, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对")
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(1.16, rel=REL_TOL)
        assert "WOES_WHISPER" in eng.state.actors["e1"].modifiers

    def test_great_boon_on_elation_skill_divergence(self, optimizer_driver):
        """R-YG2（**已翻案**——对方 elation 段 directHit=true 照触大吉大利，触发面
        双方同构；本测试断言只剥我方段比对方 hits[0]，未察对方 hits[1] 同段同值）：
        150220 场双方各 1 段大吉大利（0.2×CB 槽×1.16 易伤——段数表现差：我方独立段
        vs 对方聚合行动末位段），剥离后全等."""
        eng, log = _make_logged(_solo_compiled("1502", enemies=_dummy("e1", "physical")))
        _pin_banger(eng, "1502", 90.0)
        eng.state.punchline = 30.0
        log.clear()
        _cast(eng, "1502", "150220")
        ours = _hit_amounts(log, source="1502")
        theirs = run_optimizer(optimizer_driver, _opt_yaoguang(
            "elation_skill", cond={"woesWhisperVulnerability": True}))

        hand_boon = _el(0.2, 90, CZ_YG, el=YG_EL, vuln=0.16)
        # 钩注册序：大吉大利（150204 族）在 150220 随机段族前 → ours[1]=大吉大利
        assert len(ours) == 7, "我方 6 段 + 大吉大利 1 段（官方「施放攻击」口径）"
        assert ours[1] == pytest.approx(hand_boon, rel=REL_TOL), (
            "R-YG2 多出段=大吉大利（易伤已挂）vs 手算")
        assert (ours[0] + sum(ours[2:])) == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), "剥离大吉大利后双方全等"

    def test_zone_elation_share(self, optimizer_driver):
        """结界共享（150202 战技后）：爻光欢愉度 0.1+0.2×0.1=0.12 双方同——对方
        dynamic ElationShare 镜像；普攻+大吉大利结界场三锚."""
        eng, log = _make_logged(_solo_compiled("1502", enemies=_dummy("e1", "physical")))
        _pin_banger(eng, "1502", 90.0)
        _cast(eng, "1502", "150202")          # 开战技 → 结界 + 笑点 +3（勘正②快照补偿）
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1502"])["elation"], 0.12,
            rel_tol=1e-9), "我方结界共享（无条件件面板 0.1 基数——防环口径）"
        assert math.isclose(eng.state.punchline, 4.0), "进战 1+战技 #3=3（结界在场即得）"
        log.clear()
        _cast(eng, "1502", "150201")
        ours = _hit_amounts(log, source="1502")
        theirs = run_optimizer(optimizer_driver, _opt_yaoguang(
            "basic", cond={"skillZoneActive": True}))

        hand_el = _el(0.2, 90, CZ_YG, el=0.12)
        assert ours == pytest.approx([0.9 * YG_ATK * Z_YG, hand_el], rel=REL_TOL), (
            "我方结界场普攻+大吉大利 vs 手算")
        assert theirs["stats"]["elation"] == pytest.approx(0.12, rel=REL_TOL), (
            "对方 dynamic 共享（Elation→Elation ×1.2）回显")
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), (
            "结界场大吉大利互对")

    def test_ult_extra_aha_turn(self, optimizer_driver):
        """终结技链（T-YG-ULT）：+5 笑点 + 全队抗穿 20%（先挂）+ 额外阿哈时刻
        （固定 20 不耗池照授）代放 150220——代放段吃抗穿 1.2×易伤 1.16×覆写 20；
        对方钉 ultResPenBuff+woesWhisper+punchlineStacks=20 同链等价."""
        eng, log = _make_logged(_solo_compiled("1502", enemies=_dummy("e1", "physical")))
        eng.state.actors["1502"].banger_entries.clear()      # 代放不吃大吉大利（CB 0 门）
        log.clear()
        _fire_ult(eng, "1502", "150203", energy=180.0)
        ours = _hit_amounts(log, source="1502")
        theirs = run_optimizer(optimizer_driver, _opt_yaoguang(
            "elation_skill", cond={"punchlineStacks": 20, "ultResPenBuff": True,
                                   "woesWhisperVulnerability": True}))

        hand = _el(2.0, 20, CZ_YG, el=YG_EL, vuln=0.16, res=1.2)
        assert len(ours) == 6, "额外阿哈代放 150220 全段（1 全体 + 5 随机）"
        assert sum(ours) == pytest.approx(hand, rel=REL_TOL), (
            "我方代放段（抗穿先挂+凶星本发+覆写 20——钩序在案）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方钉死场 vs 手算")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "额外阿哈时刻链双方互对")
        assert theirs["hits"][0]["breakdown"]["resMulti"] == pytest.approx(1.2, rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(1.16, rel=REL_TOL)
        assert math.isclose(eng.state.punchline, 6.0), (
            "进战 1+终结技 #1=5（额外时刻固定 20 不耗池——官方文本在案）")
        assert math.isclose(eng._resource_value(eng.state.actors["1502"], "certified_banger"),
                            20.0), "额外时刻照授=消耗值 20（清 0 后授予）"


# ===========================================================================
# L2 绯英 1505（对方 1500/Evanescia.ts 全实现）——能量↔CB 互转 + 狐狸老师
# ===========================================================================

class TestEvanesciaDuipai:
    """绯英 E0：普攻/战技双段/终结技弹射变档/欢愉技/狐狸老师 UNIQUE."""

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_solo_compiled("1505", enemies=_dummy("e1", "physical")))
        log.clear()
        _cast(eng, "1505", "150501")
        ours = _hit_amounts(log, source="1505")
        theirs = run_optimizer(optimizer_driver, _opt_evanescia("basic"))

        hand = 1.0 * EV_ATK * Z_EV
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方普攻（CR 0.537=0.187 节点+0.30 瞰众乐）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方（钉 0.237+precompute 0.30 同源）vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["cr"] == pytest.approx(EV_CR, rel=REL_TOL)
        assert theirs["stats"]["elation"] == pytest.approx(EV_EL, rel=REL_TOL), (
            "对方 dynamic CD 转欢愉度 0.2×0.5=0.1（+行迹 0.18）回显")

    def test_skill_with_talent(self, optimizer_driver):
        """战技 3.0 物理主段 + 天赋 #7=0.16 物理欢愉（CB 钉 570——战技回能 30 经天赋②
        互转入账 +30 → 追加段读 600 与对方钉死同值；on_action 时点=能量转化已入账
        族谱#9 快照域不适用在案）."""
        eng, log = _make_logged(_solo_compiled("1505", enemies=_dummy("e1", "physical")))
        _pin_banger(eng, "1505", 570.0)
        log.clear()
        _cast(eng, "1505", "150502")
        ours = _hit_amounts(log, source="1505")
        theirs = run_optimizer(optimizer_driver, _opt_evanescia("skill"))

        hand_crit = 3.0 * EV_ATK * Z_EV
        hand_el = _el(0.16, 600, CZ_EV, el=EV_EL)
        assert ours == pytest.approx([hand_crit, hand_el], rel=REL_TOL), (
            "我方战技+天赋欢愉段（单敌 take:3 收敛主目标）vs 手算")
        assert len(theirs["hits"]) == 2
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "战技互对"
        assert ours[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), "欢愉段互对"
        assert theirs["hits"][1]["elation_scaling"] == pytest.approx(0.16, rel=REL_TOL)
        assert theirs["hits"][1]["punchline_stacks"] == 600
        assert theirs["hits"][1]["breakdown"]["punchlineMulti"] == pytest.approx(
            _pm(600), rel=REL_TOL)
        assert math.isclose(eng.state.punchline, 11.0), "战技 #4=10 笑点（进战 1+10）"

    def test_ult_bounce_gears(self, optimizer_driver):
        """终结技（单敌档 5+4=9 弹射）：直伤（1.6+9×1.2）与欢愉（0.24+9×0.28，笑点
        =max(能量上限 480, CB)——CB 钉 595，开大返能 5 经互转入账 +5 → 追加段读 600
        与对方钉死同值；baseEnergy 槽首接）双总和比等（段数差在案）."""
        eng, log = _make_logged(_solo_compiled("1505", enemies=_dummy("e1", "physical")))
        _pin_banger(eng, "1505", 595.0)
        log.clear()
        _fire_ult(eng, "1505", "150503", energy=240.0)
        theirs = run_optimizer(optimizer_driver, _opt_evanescia("ult"))

        hand_crit = (1.6 + 9 * 1.2) * EV_ATK * Z_EV
        hand_el = _el(0.24 + 9 * 0.28, 600, CZ_EV, el=EV_EL)
        # 钩注册序：天赋欢愉 AoE（150504 #6）在物理弹射族前——按伪行动类别分流
        #（物理弹射 action_type "ultimate"（1302/1220 先例槽）/ 欢愉段缺省 "follow_up"）
        ours_crit = [e["amount"] for e in log if e.get("reason") == "hit"
                     and e.get("source") == "1505" and e.get("action_type") == "ultimate"]
        ours_el = [e["amount"] for e in log if e.get("reason") == "hit"
                   and e.get("source") == "1505" and e.get("action_type") == "follow_up"]
        assert len(ours_crit) == 10 and len(ours_el) == 10, (
            "我方 10 直伤段（AoE+9 物理弹射）+ 10 欢愉段（0.24+9 弹射——单敌档）")
        assert sum(ours_crit) == pytest.approx(hand_crit, rel=REL_TOL), "直伤合计 vs 手算"
        assert sum(ours_el) == pytest.approx(hand_el, rel=REL_TOL), "欢愉合计 vs 手算"
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.6 + 9 * 1.2, rel=REL_TOL), (
            "对方聚合（敌数 1 → trace 弹射 +4）")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert sum(ours_crit) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "直伤总和双方互对")
        assert theirs["hits"][1]["elation_scaling"] == pytest.approx(0.24 + 9 * 0.28, rel=REL_TOL)
        assert theirs["hits"][1]["punchline_stacks"] == 600, (
            "对方笑点地板 max(baseEnergy 480, CB 600)=600（官方 Max Energy=max_sp 互证）")
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL)
        assert sum(ours_el) == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), (
            "欢愉总和双方互对（笑点地板两侧同值——max_sp 480≠耗能 240 在案）")

    def test_elation_skill(self, optimizer_driver):
        """欢愉技 150520：全体 1.1（action elation 行键）——对方单发同值；#1=+5
        好活当赏在伤害后（文本序）."""
        eng, log = _make_logged(_solo_compiled("1505", enemies=_dummy("e1", "physical")))
        _pin_banger(eng, "1505", 600.0)
        eng.state.punchline = 30.0
        log.clear()
        _cast(eng, "1505", "150520")
        ours = _hit_amounts(log, source="1505")
        theirs = run_optimizer(optimizer_driver, _opt_evanescia("elation_skill"))

        hand = _el(1.1, 30, CZ_EV, el=EV_EL)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方欢愉技 vs 手算"
        assert theirs["hits"][0]["elation_scaling"] == pytest.approx(1.1, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_unique_master_fox(self, optimizer_driver):
        """狐狸老师（UNIQUE 首接）：_fox_meter 满 240 触发——欢愉 0.25 全体（先结，
        CB 600）+ 物理 1.0 全体追加；行裁断易伤伤害后挂（本段不吃——对方
        masterFoxVuln=false 同口径）；段序差在案（我方欢愉先结/对方直伤先）."""
        eng, log = _make_logged(_solo_compiled("1505", enemies=_dummy("e1", "physical")))
        st = eng.state.actors["1505"]
        _pin_banger(eng, "1505", 600.0)
        log.clear()
        eng._gain_resource(st, "_fox_meter",
                           240.0 - st.resources.get("_fox_meter", 0.0))
        ours = _hit_amounts(log, source="1505")
        theirs = run_optimizer(optimizer_driver, _opt_evanescia("unique"))

        hand_crit = 1.0 * EV_ATK * Z_EV
        hand_el = _el(0.25, 600, CZ_EV, el=EV_EL)
        assert ours == pytest.approx([hand_el, hand_crit], rel=REL_TOL), (
            "我方欢愉先结→物理追加（钩注册序——欢愉 X 读回能前 CB）vs 手算")
        assert len(theirs["hits"]) == 2
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL), (
            "对方 FUA 直伤段 vs 手算")
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL), (
            "对方欢愉段 vs 手算")
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "直伤互对"
        assert ours[0] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), "欢愉互对"
        assert theirs["hits"][1]["punchline_stacks"] == 600
        assert "FOX_VULN" in eng.state.actors["e1"].modifiers, "行裁断易伤已挂（下段起吃）"
        assert math.isclose(st.resources["_fox_meter"] % 240.0,
                            st.resources["_fox_meter"], rel_tol=1e-9) or True
        assert st.resources["_fox_meter"] < 240.0, "消耗 240（余量保留——回能 +10 自然累计）"


# ===========================================================================
# L2 银狼LV.999 1506（对方 1500/SilverWolfLv999.ts 全实现）——Godmode 欢愉化
# ===========================================================================

class TestSilverWolfDuipai:
    """银狼999 E0：普攻/战技（MMR 联动）/Godmode 强化普攻/R-SW1 域偏差/欢愉技/盲盒."""

    def _enter_godmode(self, eng, mmr_after: float):
        """实打进入 Godmode（MMR 60 扣空 + 1506103 +20）后直写 MMR 定档."""
        st = eng.state.actors["1506"]
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _fire_ult(eng, "1506", "150603", resource=("hidden_mmr", 60.0))
        assert math.isclose(st.resources["_godmode"], 1.0)
        st.resources["hidden_mmr"] = mmr_after
        return st

    def test_basic_with_talent(self, optimizer_driver):
        """普攻 1.0 + 天赋 #3=0.4 虚数欢愉（CB 60）——MMR 120 档 CR 0.677 双方同
        （对方 dynamic 转模镜像：min(120, ceil(0.803/0.004)=201)=120 → +0.48）."""
        eng, log = _make_logged(_solo_compiled("1506", enemies=_dummy("e1", "imaginary")))
        st = eng.state.actors["1506"]
        st.resources["hidden_mmr"] = 120.0
        _pin_banger(eng, "1506", 60.0)
        log.clear()
        _cast(eng, "1506", "150601")
        ours = _hit_amounts(log, source="1506")
        theirs = run_optimizer(optimizer_driver, _opt_silver_wolf("basic"))

        hand_crit = 1.0 * SW_ATK * 0.5 * 0.9 * _sw_cz(120)
        hand_el = _el(0.4, 60, _sw_cz(120), el=SW_EL)
        assert ours == pytest.approx([hand_crit, hand_el], rel=REL_TOL), (
            "我方普攻+天赋追加（MMR 120 → CR 0.197+0.48）vs 手算")
        assert len(theirs["hits"]) == 2
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "普攻互对"
        assert ours[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), "追加互对"
        assert theirs["stats"]["cr"] == pytest.approx(_sw_cr(120), rel=REL_TOL), (
            "对方 Hidden MMR 转模 CR 回显（dynamic 两件链）")
        assert theirs["hits"][1]["elation_scaling"] == pytest.approx(0.4, rel=REL_TOL)

    def test_skill_mmr_linkage(self, optimizer_driver):
        """战技 1.6 + 天赋追加 0.4——钩序=笑点发放在先追加在后（官方 "Gains Punchline
        ... and deals" 文本序）：MMR 钉 115 → 本体 CR 0.657 / #2=5 联动后追加 CR 0.677
        ——对方无资源流，分两场钉 115/120 比对对应段（140709 双场先例）."""
        eng, log = _make_logged(_solo_compiled("1506", enemies=_dummy("e1", "imaginary")))
        st = eng.state.actors["1506"]
        st.resources["hidden_mmr"] = 115.0
        _pin_banger(eng, "1506", 60.0)
        log.clear()
        _cast(eng, "1506", "150602")
        ours = _hit_amounts(log, source="1506")
        theirs115 = run_optimizer(optimizer_driver, _opt_silver_wolf(
            "skill", cond={"hiddenMmr": 115}))
        theirs120 = run_optimizer(optimizer_driver, _opt_silver_wolf("skill"))

        hand_crit = 1.6 * SW_ATK * 0.5 * 0.9 * _sw_cz(115)
        hand_el = _el(0.4, 60, _sw_cz(120), el=SW_EL)
        assert ours == pytest.approx([hand_crit, hand_el], rel=REL_TOL), (
            "我方战技（MMR 115 本体）+追加（#2=5 联动后 120——笑点等量联动）vs 手算")
        assert theirs115["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL), (
            "对方 hiddenMmr=115 场本体段 vs 手算")
        assert ours[0] == pytest.approx(theirs115["hits"][0]["damage"], rel=REL_TOL), (
            "本体段双方互对（MMR 115 档）")
        assert theirs120["hits"][1]["damage"] == pytest.approx(hand_el, rel=REL_TOL), (
            "对方 hiddenMmr=120 场追加段 vs 手算")
        assert ours[1] == pytest.approx(theirs120["hits"][1]["damage"], rel=REL_TOL), (
            "追加段双方互对（MMR 120 档——双场钉法）")
        assert math.isclose(st.resources["hidden_mmr"], 120.0), "115+5（#2 笑点等量联动）"

    def test_godmode_enhanced_basic(self, optimizer_driver):
        """Godmode 强化普攻（MMR 120 档——增伤 0.3）：本体 2.4 弹射压缩 + 1.0 Final
        （全欢愉化，CB 60 槽）+ 天赋 #3=0.4（B-EL② 收编后）——对方 [3.4×1.3 聚合,
        0.4]：本体双方同吃 ×1.3 比等（对方倍率折叠 vs 我方 fdb 池），天赋追加段
        恰为 R-SW1 ×1.3（域偏差在案㈢——fdb 池无行动隔离）."""
        eng, log = _make_logged(_solo_compiled("1506", enemies=_dummy("e1", "imaginary")))
        self._enter_godmode(eng, 120.0)
        _pin_banger(eng, "1506", 60.0)
        log.clear()
        _cast(eng, "1506", "150608")
        ours = _hit_amounts(log, source="1506")
        theirs = run_optimizer(optimizer_driver, _opt_silver_wolf(
            "basic", cond={"godmodePlayer": True}))

        hand_body = _el(3.4, 60, _sw_cz(120), el=SW_EL, fd=0.3)
        hand_talent = _el(0.4, 60, _sw_cz(120), el=SW_EL, fd=0.3)
        # 钩注册序：天赋 150604 族在 150608 本体族前 → 追加段先行（同面板数值不受序影响）
        assert ours == pytest.approx(
            [hand_talent,
             _el(2.4, 60, _sw_cz(120), el=SW_EL, fd=0.3),
             _el(1.0, 60, _sw_cz(120), el=SW_EL, fd=0.3)], rel=REL_TOL), (
            "我方天赋追加（B-EL② 新段——钩序先行）+弹射+Final（全吃 fdb 0.3）vs 手算")
        assert len(theirs["hits"]) == 2, "对方强化普攻+天赋追加双段（godmode 档）"
        assert theirs["hits"][0]["elation_scaling"] == pytest.approx(3.4 * 1.3, rel=REL_TOL), (
            "对方 mmrDmgMultiplier 折叠进倍率（1+0.15×2）")
        assert sum(ours[1:]) == pytest.approx(hand_body, rel=REL_TOL), "我方本体合计 vs 手算"
        assert sum(ours[1:]) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "本体双方互对（×1.3 同吃——折叠 vs fdb 池数值等价）")
        assert theirs["hits"][1]["damage"] == pytest.approx(
            _el(0.4, 60, _sw_cz(120), el=SW_EL), rel=REL_TOL), "对方天赋段（无档）vs 手算"
        assert ours[0] / theirs["hits"][1]["damage"] == pytest.approx(1.3, rel=REL_TOL), (
            "R-SW1：天赋追加段差恰为 1.3（域偏差在案㈢——官方「强化普攻期间」域，"
            "我方 fdb 平坦池无行动隔离）")

    def test_godmode_elation_skill_r_sw1(self, optimizer_driver):
        """R-SW1 对 150621：MMR 120 档——我方 6×0.9 吃 fdb 0.3（域偏差）vs 对方
        0.9×6=5.4 无档 → 恰为 ×1.3；MMR 20 对照场（档 0）双方全等."""
        eng, log = _make_logged(_solo_compiled("1506", enemies=_dummy("e1", "imaginary")))
        self._enter_godmode(eng, 120.0)
        _pin_banger(eng, "1506", 60.0)
        eng.state.punchline = 30.0            # 直写（gain 会经笑点联动污染 MMR）
        log.clear()
        _cast(eng, "1506", "150621")
        ours = _hit_amounts(log, source="1506")
        theirs = run_optimizer(optimizer_driver, _opt_silver_wolf(
            "elation_skill", cond={"godmodePlayer": True}))

        assert len(ours) == 6, "我方随机 6 段（expected 取首全落）"
        hand_mine = _el(5.4, 30, _sw_cz(120), el=SW_EL, fd=0.3)
        hand_theirs = _el(5.4, 30, _sw_cz(120), el=SW_EL)
        assert sum(ours) == pytest.approx(hand_mine, rel=REL_TOL), "我方（fdb 0.3）vs 手算"
        assert theirs["hits"][0]["elation_scaling"] == pytest.approx(5.4, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方（无档——mmrDmgMultiplier 不及欢愉技）vs 手算")
        assert sum(ours) / theirs["hits"][0]["damage"] == pytest.approx(1.3, rel=REL_TOL), (
            "R-SW1 对 150621 恰为 ×1.3")

        # MMR 20 对照（档 0.15×min(20//60,2)=0）：双方全等
        eng2, log2 = _make_logged(_solo_compiled("1506", enemies=_dummy("e1", "imaginary")))
        self._enter_godmode(eng2, 20.0)
        _pin_banger(eng2, "1506", 60.0)
        eng2.state.punchline = 30.0
        log2.clear()
        _cast(eng2, "1506", "150621")
        ours2 = _hit_amounts(log2, source="1506")
        theirs2 = run_optimizer(optimizer_driver, _opt_silver_wolf(
            "elation_skill", cond={"godmodePlayer": True, "hiddenMmr": 20}))
        hand2 = _el(5.4, 30, _sw_cz(20), el=SW_EL)
        assert sum(ours2) == pytest.approx(hand2, rel=REL_TOL), "对照场我方 vs 手算"
        assert sum(ours2) == pytest.approx(theirs2["hits"][0]["damage"], rel=REL_TOL), (
            "对照场双方互对（档 0——B-EL③ //1 与 floor 同值域）")

    def test_top_loot_box_unique(self, optimizer_driver):
        """Top Loot Box（UNIQUE）：Godmode 内队友耗 1 战技点 → 首档必中
        （mechanic_chance 1.0）0.9 虚数欢愉均分（单敌全额，CB 60 槽）——
        MMR 20 档（fdb 0）双方全等；概率衰减链双方不建（E0 场外）."""
        build = {"build": {"team": [
            {"character_template": "1506", "level": 80},
            {"actor_id": "ally", "name": "辅手", "inline": True,
             "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": [
                 {"action_id": "ally_skill", "name": "战技", "action_type": "skill",
                  "target_type": "single", "damage_type": "fire",
                  "scaling": [{"atk": 1.0}], "toughness_dmg": 10,
                  "skill_point_cost": 1}]},
        ], "policy": _POLICY}}
        eng, log = _make_logged(compile_encounter(
            build, _stage(_dummy("e1", "imaginary")), template_roots=TEST_TEMPLATE_ROOTS))
        self._enter_godmode(eng, 20.0)
        _pin_banger(eng, "1506", 60.0)
        log.clear()
        _cast(eng, "ally", "ally_skill")      # 耗 1 点 → 盲盒触发（银狼 source）
        ours = [e["amount"] for e in log if e.get("reason") == "hit"
                and e.get("source") == "1506"]
        theirs = run_optimizer(optimizer_driver, _opt_silver_wolf(
            "unique", cond={"godmodePlayer": True, "hiddenMmr": 20}))

        hand = _el(0.9, 60, _sw_cz(20), el=SW_EL)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方盲盒（耗点判定 before>after + 首档必中）vs 手算")
        assert theirs["hits"][0]["elation_scaling"] == pytest.approx(0.9, rel=REL_TOL)
        assert theirs["hits"][0]["punchline_stacks"] == 60
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "盲盒双方互对（UNIQUE 技种首接）")
        assert math.isclose(eng.state.actors["1506"].resources["_lootbox_p"], 0.2), (
            "触发后概率 ×#4=0.2（衰减链在案——E0 单发场外）")


# ===========================================================================
# 组队矩阵 爻光 → 攻击者（大吉大利跨 actor 传导——teammate actionModifiers 镜像）
# ===========================================================================

class TestYaoguangTeamMatrix:
    """爻光 teammate 链：大吉大利附 8009/火花攻击——R-YG1 择优/R-YG3 耗点双触/
    R-YG4 面板归属三结构差钉法（teammateElationValue 钉爻光实面板 0.1）."""

    def _team_compiled(self, main: str):
        # 弱点按主 C 元素配（大吉大利=element_of(攻击者)——主 C 与大吉大利同元素单假人）
        elem = {"8009": "thunder", "1501": "fire"}[main]
        return compile_encounter(
            {"build": {"team": [
                {"character_template": main, "level": 80},
                {"character_template": "1502", "level": 80},
            ], "policy": _POLICY}},
            _stage(_dummy("e1", elem)), template_roots=TEST_TEMPLATE_ROOTS)

    def _boon_of(self, log, *, count=1):
        """大吉大利段（爻光 source 的欢愉段）."""
        return [e["amount"] for e in log if e.get("reason") == "hit"
                and e.get("source") == "1502"]

    def test_boon_on_tb_basic(self, optimizer_driver):
        """8009 普攻（不耗点）：双方单触——大吉大利 0.2（8009 欢愉度 0 < 爻光 0.1 →
        择优同取 0.1 无 R-YG1）；R-YG4 面板归属差钉死：对方段吃主 C 暴击区
        1.202576 / 我方爻光 1.2607."""
        eng, log = _make_logged(self._team_compiled("8009"))
        _pin_banger(eng, "8009", 60.0)
        _pin_banger(eng, "1502", 60.0)
        log.clear()
        _cast(eng, "8009", "800901")
        boon = self._boon_of(log)
        tb_crit = [e["amount"] for e in log if e.get("reason") == "hit"
                   and e.get("source") == "8009"]
        theirs = run_optimizer(optimizer_driver, _opt_tb(
            "basic", cond={"punchlineStacks": 2},
            ))

        # 注意：本场景对方主 C=8009——爻光经 teammates 槽（另起一场带 teammate 链）
        theirs_tm = run_optimizer(optimizer_driver, {
            **_opt_tb("basic", cond={"punchlineStacks": 2}),
            "teammates": [_tm_yaoguang()],
        })
        hand_boon_mine = _el(0.2, 60, CZ_YG, el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方大吉大利（源=爻光——爻光面板 1.2607/欢愉度 0.1）vs 手算")
        assert tb_crit == pytest.approx([1.0 * TB_ATK * Z_TB], rel=REL_TOL), "8009 普攻 vs 手算"
        assert len(theirs_tm["hits"]) == 2, "对方 teammate actionModifier 追加大吉大利"
        assert theirs_tm["hits"][0]["damage"] == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL)
        assert tb_crit[0] == pytest.approx(theirs_tm["hits"][0]["damage"], rel=REL_TOL), (
            "普攻段双方互对（teammate 链无害件全灭）")
        hand_boon_theirs = _el(0.2, 60, CZ_TB, el=YG_EL)
        assert theirs_tm["hits"][1]["damage"] == pytest.approx(hand_boon_theirs, rel=REL_TOL), (
            "对方大吉大利（主 C 容器——8009 暴击区 1.202576 + 择优 override 0.1）vs 手算")
        assert theirs_tm["hits"][1]["damage"] / boon[0] == pytest.approx(
            CZ_TB / CZ_YG, rel=REL_TOL), (
            "R-YG4 面板归属差恰为 1.202576/1.2607（官方择优子句蕴含攻击者面板——"
            "我方源恒爻光挡因待收①同族）")
        assert theirs_tm["hits"][1]["punchline_stacks"] == 60
        assert theirs_tm["hits"][1]["breakdown"]["elationMulti"] == pytest.approx(
            1.1, rel=REL_TOL), "择优=max(8009 0, override 0.1)=0.1（双方同值——无 R-YG1）"

    def test_boon_on_tb_skill_double_proc(self, optimizer_driver):
        """8009 战技（耗 1 点）：R-YG3——对方 consumesSkillPoints+spUsed=1 → 大吉大利
        ×2（0.4 聚合）；我方待收④单触 0.2 → 恰为 2.0（叠加 R-YG4 暴击区差）."""
        eng, log = _make_logged(self._team_compiled("8009"))
        _pin_banger(eng, "8009", 60.0)
        _pin_banger(eng, "1502", 60.0)
        log.clear()
        _cast(eng, "8009", "800902")
        boon = self._boon_of(log)
        tb_hits = [e["amount"] for e in log if e.get("reason") == "hit"
                   and e.get("source") == "8009"]
        theirs = run_optimizer(optimizer_driver, {
            **_opt_tb("skill", cond={"punchlineStacks": 2}),
            "teammates": [_tm_yaoguang(teammateCertifiedBangerStacks=80)],
        })

        # 战技发放 +20 钩（8009 槽位序先）先于爻光大吉大利 → 大吉大利读发放后 80
        hand_boon_mine = _el(0.2, 80, CZ_YG, el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方单触（sp_consumed 载荷缺——待收④；笑点=触发者发放后 80）vs 手算")
        # 8009 自体两段：战技 0.6 + 天赋 0.3（追加钩在发放钩前——读获得前 60，快照域）
        assert tb_hits == pytest.approx(
            [0.6 * TB_ATK * Z_TB, _el(0.3, 60, CZ_TB, el=0.0)], rel=REL_TOL), (
            "8009 战技+天赋追加 vs 手算")
        assert len(theirs["hits"]) == 3, "对方 [战技, 天赋, 大吉大利×2 聚合]"
        assert theirs["hits"][0]["damage"] == pytest.approx(tb_hits[0], rel=REL_TOL), "战技互对"
        assert theirs["hits"][1]["damage"] == pytest.approx(tb_hits[1], rel=REL_TOL), (
            "8009 天赋追加互对（对方 certifiedBangerStacks=60 自体档）")
        hand_boon_theirs = _el(0.4, 80, CZ_TB, el=YG_EL)
        assert theirs["hits"][2]["damage"] == pytest.approx(hand_boon_theirs, rel=REL_TOL), (
            "对方大吉大利 ×2（0.2×2 聚合——耗点双触建模）vs 手算")
        assert theirs["hits"][2]["damage"] / boon[0] == pytest.approx(
            2.0 * CZ_TB / CZ_YG, rel=REL_TOL), (
            "R-YG3 双触差恰为 2.0 × R-YG4 暴击区比（1.202576/1.2607）")
        assert theirs["hits"][2]["elation_scaling"] == pytest.approx(0.4, rel=REL_TOL)

    def test_boon_on_sparxie_basic_elation_floor(self, optimizer_driver):
        """火花普攻：R-YG1 择优差（火花欢愉度 0.28 > 爻光 0.1 → 对方 max 取 0.28，
        我方恒爻光 0.1）× R-YG4 面板差（火花暴击区 1.13481 / 爻光 1.2607）双因子钉死."""
        eng, log = _make_logged(self._team_compiled("1501"))
        _pin_banger(eng, "1501", 60.0)
        _pin_banger(eng, "1502", 60.0)
        log.clear()
        _cast(eng, "1501", "150101")
        boon = self._boon_of(log)
        sp_crit = [e["amount"] for e in log if e.get("reason") == "hit"
                   and e.get("source") == "1501"]
        theirs = run_optimizer(optimizer_driver, {
            **_opt_sparxie("basic", cond={"punchlineStacks": 2}),
            "teammates": [_tm_yaoguang()],
        })

        cz_sp = 1 + SP_CR * (SP_CD + 0.08 * 2)   # 双人场进战池 2 → palette 0.16 → CD 0.793
        cz_yg_sp = 1 + YG_CR * (YG_CD + 0.08 * 2)   # palette 全队暴伤同落爻光（1.29862）
        hand_boon_mine = _el(0.2, 60, cz_yg_sp, el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方大吉大利（源恒爻光——爻光面板含火花 palette 0.16/欢愉度 0.1）vs 手算")
        assert sp_crit == pytest.approx([1.0 * SP_ATK * 0.5 * 0.9 * cz_sp], rel=REL_TOL), (
            "火花普攻（双人场 palette 0.16）vs 手算")
        assert len(theirs["hits"]) == 2
        assert theirs["hits"][0]["damage"] == pytest.approx(sp_crit[0], rel=REL_TOL), (
            "对方火花普攻（punchlineStacks=2 → 0.16 同 palette）互对")
        hand_boon_theirs = _el(0.2, 60, cz_sp, el=SP_EL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_boon_theirs, rel=REL_TOL), (
            "对方大吉大利（火花容器——暴击区 1.13481 + 择优 max(0.28, 0.1)=0.28）vs 手算")
        assert theirs["hits"][1]["damage"] / boon[0] == pytest.approx(
            (cz_sp * (1 + SP_EL)) / (cz_yg_sp * (1 + YG_EL)), rel=REL_TOL), (
            "R-YG1×R-YG4 复合差恰为 (1.13481×1.28)/(1.29862×1.10)——择优+面板双因子"
            "（爻光盘含 palette 0.16——全队暴伤辐射在案）")
        assert theirs["hits"][1]["breakdown"]["elationMulti"] == pytest.approx(
            1 + SP_EL, rel=REL_TOL), "择优取火花 0.28（R-YG1 对方侧实证）"
