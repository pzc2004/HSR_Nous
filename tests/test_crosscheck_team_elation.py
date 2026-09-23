"""L4 组队级对拍（BACKLOG B22 扩展④）：欢愉队三主力（火花 1501 输出 + 爻光 1502 buff 源
+ 银狼LV.999 1506 副 C，开拓者 8009 备选）——欢愉跨角色协同首验：大吉大利跨 actor 传导
（teammate actionModifiers 镜像挂点）/择优/耗点双触/面板归属四结构差组队层逐条核销
（单人波 R-YG1/2/3/4 是坐实还是翻案）/三 buff 源叠一主 C 多源进池加算口径/额外阿哈时刻
代放链逐段（火花 21 段/银狼 6 段在大吉大利场）。逐段伤害 == hsr-optimizer 组队链整链伤害
（rel_tol 1e-4；双锚=对方+手算，对不上的按惯例钉结构差数值自证）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character" + teammates 块（驱动头注
有链路口径）——爻光 teammate 链：precomputeMutual（抗穿/凶星易伤 FullTeam 折叠进主 C
容器）+ precomputeTeammateEffects（结界共享 teammateElationValue×0.2 ELATION 件）+
actionModifiers（大吉大利向 directHit 行动附欢愉段：元素=攻击者、笑点=teammateCertified
BangerStacks、择优=minElationOverride、耗点双触=consumesSkillPoints×spUsed）；火花
teammate 链：mutual 调色盘 min(0.8, punchlineStacks×0.08) FullTeam 暴伤。我方路径：真模板
三角色队 → 编译 → CombatEngine 钉资源（笑点队伍账直写/统发、好活当赏条目、Hidden MMR
直写——笑点联动 MMR 经 gain 会污染，银狼场一律直写）→ _cast/_fire_ultimate → bus
on_hp_decrease 逐段记录仪（setup 前订阅，L2 先例；大吉大利段=爻光 source+钩默认 follow_up
类别，150220/150120/150621 段族标 elation_skill——链上按 (source, action_type) 分流）。

统一口径（两侧一致，沿用单人波）：星魂钉死 E0、行迹满级、无光锥无遗器、假人 lvl80
def 1000（防御区 0.5）、匹配弱点（抗性区 1.0——链上场按段元素源并集配多弱点）、未击破
（0.9）、期望暴击。**三人场笑点进战=3**（每欢愉角色 +1）→ 调色盘 0.24 双方同；palette
经 on_resource_gain 重烘件刷新（B-EL④ 后任何来源获得笑点都重烘——stat_effects 系
应用时烘焙非懒求值，重烘钩是唯一刷新通道），池变动即时生效——银狼战技 +5 笑点场
本体段读池 3（palette 0.24）/追加段读池 8（palette 0.64），对方双场钉法（115/120
先例）同构。
好活当赏：火花 60 / 爻光 90 / 银狼 60（大吉大利笑点=触发者合并值，链上=进战 20）。

===========================================================================
火花 1501 主 C 场映射表（对方 content 开关 ↔ 我方模板触发；teammates=[爻光, 银狼999]）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
punchlineStacks（30→3/8/11/30）阿哈笑点队伍账（调色盘 min(10)×0.08 双方同式） 按场钉池实时值
certifiedBangerStacks（60）    好活当赏合并值（st.banger_entries）             钉 60
enhancedBasic（false）         直播态换技能（150101↔150108 available_if 互斥）  普通普攻钉 false；
                                                                            强化普攻钉 true（直施绕过闸，
                                                                            e2e 先例）
certifiedBanger（true）        好活当赏持有门（天赋附伤段）                     钉 true
atkToElation（true）           1501101 ATK 转化（ATK 640<2000 → +0）           钉 true（两侧同灭）
punchlineCritDmg（true）       1501103 每笑点全队暴伤 8% 上限 80%（palette      钉 true（池 3→0.24
                               重烘 replace——懒求值读活池）                   双方同值）
engagementFarmingStacks（0）   150109 #4/#5 倍率提高——待收（R-SP1 在案）        钉 0（不触双触歧义）
爻光 teammate 链（_tm_yaoguang 映射见单人波，teammateElationValue 钉 0.1=     结界钉 false（1a/1b/1c）；
  爻光无条件件面板/teammateCertifiedBangerStacks=触发者 CB）                    true 见组合场 3a
银狼999 teammate 链（e1Vulnerability/e6ResPen） 星魂门控（E0 同灭）              teammateDefaults 原样

===========================================================================
银狼LV.999 1506 主 C 场映射表（teammates=[爻光, 火花]）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
godmodePlayer（false）         Godmode Player 状态（150603 进状态——MMR 60     常态钉 false；godmode 场
                               扣空+1506103 +20）                            实打进入后钉 true
hiddenMmr 0-300（120）         Hidden MMR（CR 转模 stat_exprs——笑点联动       钉 120 直写；战技场
                               经 gain 会污染，一律直写）                     钉 115（#2=5 联动后
                                                                            =120 对轴——双场钉法）
certifiedBangerStacks（60）    好活当赏合并值（天赋追加/大吉大利笑点）           钉 60
punchlineStacks（30→3/8/30）   阿哈笑点队伍账（150621 段=池实时值）             按场钉池实时值（直写）
spdToElation（true）           1506101 SPD 转化（spd 119<160 → +0）            钉 true（两侧同灭）
e1Vulnerability/e4PunchlineBoost/e6Merrymake/e6ResPen  星魂（E0 门控同灭）     E0 钉 true 无害
火花 teammate 链（punchlineStacks/e1PunchlineResPen/punchlineCritDmg）         调色盘钉池实时值（3/8）

===========================================================================
开拓者 8009 备选场映射表（teammates=[爻光, 火花]）
===========================================================================
ultCdBuff（true，teammate 链） 800903 指定队友暴伤 +50%·3 回合（ally_single   3b：指定火花双方
                               目标=$event.target；对方 SingleTarget 落主 C）  比等（CD 池 +0.5）；
                                                                            5：战技耗点双触核销
certifiedBangerStacks（60→80） 好活当赏合并值（战技 #2=+20 发放后钩序——      钉 60（天赋追加）/
                               大吉大利读发放后 80，单人波先例）               80（大吉大利）

===========================================================================
结构差清单（数值自证见各 divergence 断言——差值恰为标注值，任一侧改动触红）
===========================================================================
单人波 R-YG 族组队层核销（本波逐条复钉——结论：**R-YG1/3/4 坐实，R-YG2 翻案**）：
R-YG1 大吉大利欢愉度择优半件（我方待收①——hook 伤害源恒爻光；对方 minElationOverride=
   max(攻击者, 爻光)）→ 火花场（0.28>0.1）对方/我方 恰为 (1.28×CZ_火花)/(1.10×CZ_爻光)
   （三人场 palette 0.24 进双方暴击区——1a/1b 复钉）；银狼场（0.1=0.1）择优无差
   （2a/2b/2c/2d 纯 R-YG4 单因子）；组合场结界共享后（0.30 vs 爻光 0.12——3a 复钉）；
   链上火花触发场（4a 复钉）
R-YG2 大吉大利对欢愉技触发——**翻案（单人波误诊）**：对方 elationHitSchema 默认
   directHit=true（hitDefinitionBuilder.ts:63），大吉大利对欢愉技/强化普攻/链上代放
   双方均触发，触发面同构（对方=行动含 directHit 段即附；我方=目标为敌 on_action 即
   触——自伤/自体技（150620）双方同不触发）。单人波「对方 directHit 门不触发」系误诊：
   该波断言只剥我方段比对方 hits[0]，未察对方 hits[1] 同有大吉大利（本波 1c/2c/2d/
   4a/4b 五处实证：对方 [聚合段, 大吉大利] 双段全建）。撤销后大吉大利残差只剩
   R-YG1 择优 × R-YG4 面板 × ~~R-YG3 双触~~（R-YG3 已收官，2026-09-23）两因子
~~R-YG3 大吉大利耗战技点额外触发~~ **已收官（2026-09-23——on_action 载荷
   sp_consumed 槽落地，第二钩 `$event.sp_consumed > 0` 双触两段独立结算；对方
   倍率 ×2 聚合——段数差 D6 族总和一致）→ 残差只剩 R-YG4 面板比**（银狼 150602
   战技 2b 复钉、8009 战技三人场 5 复钉——palette 随天赋 +3 笑点池 3/6 双场钉法）
R-YG4 大吉大利面板归属（我方 hook 源恒爻光=爻光暴击面板；对方段附在主 C 行动=主 C
   暴击面板——官方择优子句蕴含默认攻击者面板，对方建模更贴字面）→ 逐场比值钉死
   （1a/1b/2a/2b/2c/2d/3a/3b/4a/4b/5；palette 辐射两侧同落——爻光盘同样吃火花调色盘，
   双人波在案）；唯一双方全等实例=爻光自触（对方段附自己行动=自己面板——4a 钉）
组合场多源进池（3a）：结界共享（ELATION +0.02）/终结技抗穿（RES_PEN +0.2）/凶星低语
   （VULN +0.16）/调色盘（CD +0.8）四源各进各池全加算——普攻段双方全等（无 D7 族
   加算/乘算近似显形；E0 场 final_dmg_boost 池空，R-SW1 域偏差见 2c/2d）
链上段序（4a/4b）：代放序=参演编号升序（爻光 116→火花 144→银狼 999——凶星低语由爻光
   代放先挂，其后各段全吃 1.16）；大吉大利非 Godmode 链 2 段（150620 自体目标双方同
   不触发）/Godmode 链 3 段（4b）

已修真病两件（本波钓出——小修笔误级，单列）：
B-EL④ 火花调色盘重烘 actor 过滤窄（模板级）：1501103 on_resource_gain 钩旧条件
   `$event.actor=='1501'`——笑点=队伍账（21.3），任何来源获得都应重烘（银狼 150604
   MMR 联动「不判 actor」同先例）；旧过滤在组队层漏烘（爻光战技 +3/终结技 +5 进池
   后 palette 停更在旧值——3a 场 palette 0.24 vs 对方 0.8 钓出）。fixture 条件删
   actor 过滤（单人场行为不变——单人池增益全来自 1501 自身）。
B-EL⑤ 额外阿哈覆写锚只认字面 "res_punchline"（引擎级）：hooks.py 特判字符串等值，
   复合表达式（150621 punchline_source "res_punchline*(1+res__e4_pl_mult)" 族）与
   钩条件（1506102 阈值判定）在额外阿哈时刻读活池而非锚定 20——1506 模板在案㈡
   「引擎侧待修已上报」兑现：engine._res_ns 的 res_punchline 改读
   _aha_pool_override（「覆写的是池本身，凡读池处同锚」——4b 链上 150621 读 20
   对拍锚；常规阿哈/非代放场行为不变——override None 走原路）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
# 同前几波：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    _POLICY, _cast, _hit_amounts, _make_logged, _stage,
)
from tests.test_crosscheck_elation import (  # noqa: F401
    SP_ATK, SP_CR, SP_CD, SP_EL, SW_ATK, SW_CR, SW_CD, SW_EL,
    TB_ATK, TB_CR, TB_CD, YG_CR, YG_CD, YG_EL,
    _el, _fire_ult, _opt_silver_wolf, _opt_sparxie, _opt_tb, _opt_yaoguang,
    _pin_banger, _pin_pool_gain, _sw_cr, _tm_yaoguang,
)
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 口径常数（两侧钉死；fixture 终审值同单人波——三人场唯一变量=调色盘随池）
# ---------------------------------------------------------------------------


def _palette(pool: float) -> float:
    """调色盘全队暴伤 0.08×min(池, 10)（1501103——双方同式，池实时值）."""
    return 0.08 * min(pool, 10)


def _cz_sp(pool: float, *, extra_cd: float = 0.0) -> float:
    """火花期望暴击区（调色盘 + 额外暴伤件（开拓者 800903 指定队友链）进同一 CD 池加算）."""
    return 1 + SP_CR * (SP_CD + _palette(pool) + extra_cd)


def _cz_yg(pool: float, *, extra_cd: float = 0.0) -> float:
    """爻光期望暴击区（调色盘全队辐射同落爻光—— palette effect_scope team）."""
    return 1 + YG_CR * (YG_CD + _palette(pool) + extra_cd)


def _cz_sw(pool: float, mmr: float) -> float:
    """银狼999 期望暴击区（Hidden MMR CR 转模 + 调色盘）."""
    return 1 + _sw_cr(mmr) * (SW_CD + _palette(pool))


def _cz_tb(pool: float, *, extra_cd: float = 0.0) -> float:
    """开拓者•欢愉期望暴击区（0.27 行迹含大行迹 0.15 + 调色盘）."""
    return 1 + TB_CR * (TB_CD + _palette(pool) + extra_cd)


def _crit(mult: float, atk: float, cz: float, *, res: float = 1.0,
          vuln: float = 0.0, fd: float = 0.0) -> float:
    """直伤期望：倍率×ATK×防御区 0.5×未击破 0.9×期望暴击区×抗区×易伤区×final 区."""
    return mult * atk * 0.5 * 0.9 * cz * res * (1 + vuln) * (1 + fd)


# ---------------------------------------------------------------------------
# 我方侧引擎件（三真模板队编成）
# ---------------------------------------------------------------------------

_MAIN_ELEM = {"1501": "fire", "1502": "physical", "1506": "imaginary", "8009": "thunder"}


def _team_dummy(*elements: str):
    """多弱点假人（链上场按段元素源并集——大吉大利=element_of(攻击者) 随触发者变）."""
    return [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 9999, "weakness": list(elements)}]


def _trio_build(main: str):
    """欢愉主队编成：main + 其余两名欢愉主力（1501/1502/1506 三主力轮换）."""
    team = [{"character_template": main, "level": 80}]
    for cid in ("1501", "1502", "1506"):
        if cid != main:
            team.append({"character_template": cid, "level": 80})
    return {"build": {"team": team, "policy": _POLICY}}


def _trio_compiled(main: str, *, weaknesses=None):
    w = weaknesses or [_MAIN_ELEM[main]]
    return compile_encounter(_trio_build(main), _stage(_team_dummy(*w)),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _mixed_compiled(main: str, others: list, *, weaknesses=None):
    """混编队（开拓者备选场：main + 指定队友名单）."""
    team = [{"character_template": main, "level": 80}]
    team += [{"character_template": cid, "level": 80} for cid in others]
    w = weaknesses or [_MAIN_ELEM[main]]
    return compile_encounter({"build": {"team": team, "policy": _POLICY}},
                             _stage(_team_dummy(*w)), template_roots=TEST_TEMPLATE_ROOTS)


def _pin_trio_banger(eng):
    """好活当赏三人钉值：火花 60 / 爻光 90 / 银狼 60（大吉大利笑点=触发者合并值）."""
    _pin_banger(eng, "1501", 60.0)
    _pin_banger(eng, "1502", 90.0)
    _pin_banger(eng, "1506", 60.0)


def _enter_godmode(eng, mmr_after: float):
    """实打进入 Godmode（MMR 60 扣空 + 1506103 +20）后直写 MMR 定档（单人波 helper 同形）."""
    st = eng.state.actors["1506"]
    eng._gain_resource(st, "hidden_mmr", 60.0)
    _fire_ult(eng, "1506", "150603", resource=("hidden_mmr", 60.0))
    assert math.isclose(st.resources["_godmode"], 1.0)
    st.resources["hidden_mmr"] = mmr_after
    return st


def _boon_hits(log):
    """大吉大利段（爻光 source + 钩默认 follow_up 类别——150220/150120/150621 段族
    标 elation_skill，action 层段随行动型——链上按 (source, action_type) 分流）."""
    return [e["amount"] for e in log if e.get("reason") == "hit"
            and e.get("source") == "1502" and e.get("action_type") == "follow_up"]


def _skill_hits(log, source: str):
    """欢愉技段（action 层 elation 行 + hook 段族均标 elation_skill）."""
    return [e["amount"] for e in log if e.get("reason") == "hit"
            and e.get("source") == source and e.get("action_type") == "elation_skill"]


# ---------------------------------------------------------------------------
# 对方侧场景模子（teammates 块；映射表见模块 docstring）
# ---------------------------------------------------------------------------

def _tm_sparxie(**cond):
    c = {"punchlineStacks": 3, "e1PunchlineResPen": True, "punchlineCritDmg": True}
    c.update(cond)
    return {"character_id": "1501", "eidolon": 0, "path": "Elation",
            "element": "fire", "conditionals": c}


def _tm_silver_wolf(**cond):
    c = {"e1Vulnerability": True, "e6ResPen": True}
    c.update(cond)
    return {"character_id": "1506", "eidolon": 0, "path": "Elation",
            "element": "imaginary", "conditionals": c}


def _tm_tb(**cond):
    c = {"ultCdBuff": True, "e2UltElation": True, "e4Vulnerability": True}
    c.update(cond)
    return {"character_id": "8009", "eidolon": 0, "path": "Elation",
            "element": "thunder", "conditionals": c}


def _opt_sp_team(action: str, *, cond: dict | None = None, yg=None, third=None):
    """火花主 C 场景：teammates=[爻光（大吉大利链）, 银狼999（E0 中性件）]."""
    sc = _opt_sparxie(action, cond=cond)
    sc["teammates"] = [yg if yg is not None else _tm_yaoguang(),
                       third if third is not None else _tm_silver_wolf()]
    return sc


def _opt_sw_team(action: str, *, cond: dict | None = None, yg=None, third=None):
    """银狼999 主 C 场景：teammates=[爻光（大吉大利链）, 火花（调色盘链）]."""
    sc = _opt_silver_wolf(action, cond=cond)
    sc["teammates"] = [yg if yg is not None else _tm_yaoguang(),
                       third if third is not None else _tm_sparxie()]
    return sc


# ===========================================================================
# 矩阵① 爻光 → 火花（大吉大利择优/触发/面板归属——R-YG1/2/4 三人场核销）
# ===========================================================================

class TestYaoguangToSparxie:
    """火花主 C（teammates=爻光+银狼999）：普攻/强化普攻/欢愉技 21 段逐段三方锚."""

    def test_basic_great_boon(self, optimizer_driver):
        """火花普攻 + 大吉大利：R-YG1（火花 0.28>爻光 0.1 → 对方 max 取 0.28，我方恒
        爻光 0.1）× R-YG4（对方段吃火花暴击区/我方吃爻光暴击区——palette 0.24 双方同）
        双因子钉死（三人场复钉， palette 随池 3）."""
        eng, log = _make_logged(_trio_compiled("1501"))
        assert math.isclose(eng.state.punchline, 3.0), "三人场进战笑点 3"
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1501"])["crit_dmg"],
            SP_CD + 0.24, rel_tol=1e-9), "palette 0.08×3=0.24（懒求值读活池）"
        _pin_trio_banger(eng)
        log.clear()
        _cast(eng, "1501", "150101")
        ours_sp = _hit_amounts(log, source="1501")
        boon = _boon_hits(log)
        theirs = run_optimizer(optimizer_driver, _opt_sp_team(
            "basic", cond={"punchlineStacks": 3}))

        hand_crit = _crit(1.0, SP_ATK, _cz_sp(3))
        hand_boon_mine = _el(0.2, 60, _cz_yg(3), el=YG_EL)
        assert ours_sp == pytest.approx([hand_crit], rel=REL_TOL), "火花普攻 vs 手算"
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方大吉大利（源恒爻光——爻光面板含 palette 0.24/欢愉度 0.1）vs 手算")
        assert len(theirs["hits"]) == 2, "对方普攻 + teammate actionModifier 大吉大利"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert ours_sp[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "普攻段双方互对（银狼 teammate E0 中性件无害）")
        hand_boon_theirs = _el(0.2, 60, _cz_sp(3), el=SP_EL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_boon_theirs, rel=REL_TOL), (
            "对方大吉大利（火花容器——暴击区 1.14841 + 择优 max(0.28, 0.1)=0.28）vs 手算")
        assert theirs["hits"][1]["damage"] / boon[0] == pytest.approx(
            (_cz_sp(3) * (1 + SP_EL)) / (_cz_yg(3) * (1 + YG_EL)), rel=REL_TOL), (
            "R-YG1×R-YG4 复合差恰为 (1.28×1.14841)/(1.10×1.31758)——择优+面板双因子坐实")
        assert theirs["hits"][1]["punchline_stacks"] == 60
        assert theirs["hits"][1]["breakdown"]["elationMulti"] == pytest.approx(
            1.28, rel=REL_TOL)
        st = theirs["stats"]
        assert st["cd"] == pytest.approx(SP_CD + 0.24, rel=REL_TOL), "调色盘回显"
        assert st["elation"] == pytest.approx(SP_EL, rel=REL_TOL)

    def test_enhanced_basic_great_boon(self, optimizer_driver):
        """直播态强化普攻（enhancedBasic=true 直施 150108）：主段 1.0 火直伤 + 天赋
        #3=0.4 火欢愉（CB 60）+ 大吉大利（单触——engagementStacks=0 无耗点歧义）
        三段各自三锚."""
        eng, log = _make_logged(_trio_compiled("1501"))
        _pin_trio_banger(eng)
        log.clear()
        _cast(eng, "1501", "150108")          # 绕过 available_if 直施（e2e 先例）
        ours_sp = _hit_amounts(log, source="1501")
        boon = _boon_hits(log)
        theirs = run_optimizer(optimizer_driver, _opt_sp_team(
            "basic", cond={"punchlineStacks": 3, "enhancedBasic": True}))

        hand_main = _crit(1.0, SP_ATK, _cz_sp(3))
        hand_talent = _el(0.4, 60, _cz_sp(3), el=SP_EL)
        assert ours_sp == pytest.approx([hand_main, hand_talent], rel=REL_TOL), (
            "我方主段+天赋欢愉段 vs 手算")
        assert len(theirs["hits"]) == 3, "对方 [主段, 天赋, 大吉大利]"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_main, rel=REL_TOL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_talent, rel=REL_TOL)
        assert ours_sp[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "主段互对")
        assert ours_sp[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), (
            "天赋欢愉段互对")
        hand_boon_theirs = _el(0.2, 60, _cz_sp(3), el=SP_EL)
        assert theirs["hits"][2]["damage"] == pytest.approx(hand_boon_theirs, rel=REL_TOL)
        assert theirs["hits"][2]["damage"] / boon[0] == pytest.approx(
            (_cz_sp(3) * (1 + SP_EL)) / (_cz_yg(3) * (1 + YG_EL)), rel=REL_TOL), (
            "大吉大利 R-YG1×R-YG4 复合差坐实（强化普攻场复钉）")

    def test_elation_skill_ryg2(self, optimizer_driver):
        """火花欢愉技 150120（21 段：全体 0.5 + 追加 20×0.25，池钉 30）：R-YG2 **翻案**——
        对方 elation 段 directHit=true（elationHitSchema 默认值），大吉大利对欢愉技
        双方均触发（单人波「对方 directHit 门不触发」系误诊：该波断言只剥我方段比对方
        hits[0]，未察对方 hits[1] 同有大吉大利）；21 段总和互对 + 大吉大利
        R-YG1×R-YG4 复合差钉死."""
        eng, log = _make_logged(_trio_compiled("1501"))
        _pin_pool_gain(eng, "1501", 30.0)     # palette 重烘 0.8（_gain_resource 统发）
        _pin_trio_banger(eng)
        log.clear()
        _cast(eng, "1501", "150120")          # 体系触发行动不走合法集——直施对轴
        ours = _skill_hits(log, "1501")
        boon = _boon_hits(log)
        theirs = run_optimizer(optimizer_driver, _opt_sp_team(
            "elation_skill", cond={"punchlineStacks": 30}))

        hand21 = _el(5.5, 30, _cz_sp(30), el=SP_EL)
        assert len(ours) == 21, "我方 1 全体 + 20 追加"
        assert sum(ours) == pytest.approx(hand21, rel=REL_TOL), "21 段合计 vs 手算"
        assert len(theirs["hits"]) == 2, "对方 [聚合单发, 大吉大利]——欢愉段 directHit=true"
        assert theirs["hits"][0]["elation_scaling"] == pytest.approx(5.5, rel=REL_TOL)
        assert theirs["hits"][0]["punchline_stacks"] == 30
        assert theirs["hits"][0]["damage"] == pytest.approx(hand21, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "21 段总和双方互对（段数差在案）")
        hand_boon_mine = _el(0.2, 60, _cz_yg(30), el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方大吉大利（源恒爻光——palette 0.8 辐射爻光盘）vs 手算")
        hand_boon_theirs = _el(0.2, 60, _cz_sp(30), el=SP_EL)
        assert theirs["hits"][1]["damage"] == pytest.approx(
            hand_boon_theirs, rel=REL_TOL), (
            "对方大吉大利（火花容器——触发面双方同构，R-YG2 翻案）vs 手算")
        assert theirs["hits"][1]["damage"] / boon[0] == pytest.approx(
            (_cz_sp(30) * (1 + SP_EL)) / (_cz_yg(30) * (1 + YG_EL)), rel=REL_TOL), (
            "大吉大利差只剩 R-YG1×R-YG4 双因子（择优+面板——R-YG2 误诊撤销）")
        assert math.isclose(eng.state.punchline, 30.0), "150120 不产笑点"


# ===========================================================================
# 矩阵② 爻光 → 银狼LV.999（大吉大利流转——笑点/欢愉度归属；R-YG3/4 核销）
# ===========================================================================

class TestYaoguangToSilverWolf:
    """银狼999 主 C（teammates=爻光+火花）：普攻/战技耗点双触/Godmode 强化普攻/
    欢愉技 6 段逐段三方锚."""

    def test_basic_great_boon(self, optimizer_driver):
        """银狼普攻 + 天赋 + 大吉大利：择优无差场（银狼 0.1=爻光 0.1 → max 双方同
        0.1）——R-YG4 纯面板差单因子（对方段吃银狼 MMR 转模暴击区 1.50098 / 我方
        吃爻光 1.31758）."""
        eng, log = _make_logged(_trio_compiled("1506"))
        eng.state.actors["1506"].resources["hidden_mmr"] = 120.0   # 直写（gain 会污染）
        _pin_trio_banger(eng)
        log.clear()
        _cast(eng, "1506", "150601")
        ours_sw = _hit_amounts(log, source="1506")
        boon = _boon_hits(log)
        theirs = run_optimizer(optimizer_driver, _opt_sw_team(
            "basic", cond={"hiddenMmr": 120, "punchlineStacks": 3}))

        hand_crit = _crit(1.0, SW_ATK, _cz_sw(3, 120))
        hand_talent = _el(0.4, 60, _cz_sw(3, 120), el=SW_EL)
        assert ours_sw == pytest.approx([hand_crit, hand_talent], rel=REL_TOL), (
            "我方普攻+天赋追加（MMR 120 → CR 0.677；palette 0.24）vs 手算")
        assert len(theirs["hits"]) == 3, "对方 [普攻, 天赋, 大吉大利]"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_talent, rel=REL_TOL)
        assert ours_sw[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "普攻互对")
        assert ours_sw[1] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), (
            "天赋追加互对")
        hand_boon_mine = _el(0.2, 60, _cz_yg(3), el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方大吉大利（源恒爻光——择优 0.1 双方同值，纯面板差）vs 手算")
        hand_boon_theirs = _el(0.2, 60, _cz_sw(3, 120), el=SW_EL)
        assert theirs["hits"][2]["damage"] == pytest.approx(hand_boon_theirs, rel=REL_TOL)
        assert theirs["hits"][2]["damage"] / boon[0] == pytest.approx(
            _cz_sw(3, 120) / _cz_yg(3), rel=REL_TOL), (
            "R-YG4 面板归属差恰为 1.50098/1.31758（择优同值消去——单因子坐实）")
        assert theirs["hits"][2]["breakdown"]["elationMulti"] == pytest.approx(
            1.1, rel=REL_TOL), "择优=max(银狼 0.1, override 0.1)=0.1"
        assert theirs["stats"]["cr"] == pytest.approx(_sw_cr(120), rel=REL_TOL), (
            "对方 Hidden MMR 转模 CR 回显")

    def test_skill_double_proc_ryg3(self, optimizer_driver):
        """银狼战技 150602（耗 1 点）：R-YG3——对方 consumesSkillPoints+spUsed=1 →
        大吉大利 ×2（0.4 聚合）；我方待收④单触 0.2 → 恰为 2.0 × R-YG4 面板比。
        钩序=笑点发放（#2=5 → MMR 115→120、池 3→8 palette 0.64）在先追加在后——
        本体段读 115/池 3、追加段读 120/池 8，对方双场钉法（140709 先例）."""
        eng, log = _make_logged(_trio_compiled("1506"))
        st = eng.state.actors["1506"]
        st.resources["hidden_mmr"] = 115.0
        _pin_trio_banger(eng)
        log.clear()
        _cast(eng, "1506", "150602")
        ours_sw = _hit_amounts(log, source="1506")
        boon = _boon_hits(log)
        theirs115 = run_optimizer(optimizer_driver, _opt_sw_team(
            "skill", cond={"hiddenMmr": 115, "punchlineStacks": 3},
            third=_tm_sparxie(punchlineStacks=3)))
        theirs120 = run_optimizer(optimizer_driver, _opt_sw_team(
            "skill", cond={"hiddenMmr": 120, "punchlineStacks": 8},
            third=_tm_sparxie(punchlineStacks=8)))

        hand_main = _crit(1.6, SW_ATK, _cz_sw(3, 115))
        hand_talent = _el(0.4, 60, _cz_sw(8, 120), el=SW_EL)
        assert ours_sw == pytest.approx([hand_main, hand_talent], rel=REL_TOL), (
            "我方战技（MMR 115 本体/池 3 palette 0.24）+追加（#2=5 联动后 120/池 8 "
            "palette 0.64——发放钩在先）vs 手算")
        assert theirs115["hits"][0]["damage"] == pytest.approx(hand_main, rel=REL_TOL), (
            "对方 hiddenMmr=115/池 3 场本体段 vs 手算")
        assert ours_sw[0] == pytest.approx(theirs115["hits"][0]["damage"], rel=REL_TOL), (
            "本体段双方互对（MMR 115 档）")
        assert theirs120["hits"][1]["damage"] == pytest.approx(hand_talent, rel=REL_TOL), (
            "对方 hiddenMmr=120/池 8 场追加段 vs 手算")
        assert ours_sw[1] == pytest.approx(theirs120["hits"][1]["damage"], rel=REL_TOL), (
            "追加段双方互对（MMR 120 档——双场钉法）")
        assert len(theirs120["hits"]) == 3, "对方 [战技, 天赋, 大吉大利×2 聚合]"
        hand_boon_mine = _el(0.2, 60, _cz_yg(8), el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine, hand_boon_mine], rel=REL_TOL), (
            "我方双触两段（sp_consumed=1 第二钩触发——R-YG3 已收官；palette 0.64 场）vs 手算")
        hand_boon_theirs = _el(0.4, 60, _cz_sw(8, 120), el=SW_EL)
        assert theirs120["hits"][2]["damage"] == pytest.approx(
            hand_boon_theirs, rel=REL_TOL), "对方大吉大利 ×2（0.2×2 聚合）vs 手算"
        assert theirs120["hits"][2]["damage"] / sum(boon) == pytest.approx(
            _cz_sw(8, 120) / _cz_yg(8), rel=REL_TOL), (
            "R-YG3 收官后残差恰为 R-YG4 暴击区比（1.77178/1.41238）")
        assert theirs120["hits"][2]["elation_scaling"] == pytest.approx(0.4, rel=REL_TOL)
        assert math.isclose(st.resources["hidden_mmr"], 120.0), "115+5（#2 笑点等量联动）"

    def test_godmode_enhanced_basic_ryg2(self, optimizer_driver):
        """Godmode 强化普攻（MMR 120 档——fdb 0.3）：对方双段 directHit=true → 大吉大利
        照触（R-YG2 翻案第二证）；本体/天赋段 R-SW1 ×1.3 复钉；大吉大利段源恒爻光——
        不吃银狼 fdb 池（R-SW1 域偏差不及大吉大利），R-YG4 纯面板差."""
        eng, log = _make_logged(_trio_compiled("1506"))
        _enter_godmode(eng, 120.0)
        _pin_trio_banger(eng)
        log.clear()
        _cast(eng, "1506", "150608")
        ours_sw = _hit_amounts(log, source="1506")
        boon = _boon_hits(log)
        theirs = run_optimizer(optimizer_driver, _opt_sw_team(
            "basic", cond={"godmodePlayer": True, "hiddenMmr": 120,
                           "punchlineStacks": 3}))

        hand_talent = _el(0.4, 60, _cz_sw(3, 120), el=SW_EL, fd=0.3)
        hand_bounce = _el(2.4, 60, _cz_sw(3, 120), el=SW_EL, fd=0.3)
        hand_final = _el(1.0, 60, _cz_sw(3, 120), el=SW_EL, fd=0.3)
        # 钩注册序：天赋 150604 族在 150608 本体族前 → 追加段先行（单人波先例）
        assert ours_sw == pytest.approx(
            [hand_talent, hand_bounce, hand_final], rel=REL_TOL), (
            "我方天赋追加+弹射+Final（全吃 fdb 0.3——平坦池无行动隔离）vs 手算")
        assert len(theirs["hits"]) == 3, "对方 [3.4×1.3 聚合, 天赋, 大吉大利]"
        assert theirs["hits"][0]["elation_scaling"] == pytest.approx(4.42, rel=REL_TOL)
        assert sum(ours_sw[1:]) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "本体双方互对（×1.3 同吃——对方倍率折叠 vs 我方 fdb 池数值等价）")
        assert ours_sw[0] / theirs["hits"][1]["damage"] == pytest.approx(
            1.3, rel=REL_TOL), "R-SW1：天赋追加段差恰为 1.3（域偏差在案㈢复钉）"
        hand_boon_mine = _el(0.2, 60, _cz_yg(3), el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方大吉大利（源恒爻光——palette 0.24；无 fdb 0.3）vs 手算")
        hand_boon_theirs = _el(0.2, 60, _cz_sw(3, 120), el=SW_EL)
        assert theirs["hits"][2]["damage"] == pytest.approx(
            hand_boon_theirs, rel=REL_TOL), "对方大吉大利（银狼容器）vs 手算"
        assert theirs["hits"][2]["damage"] / boon[0] == pytest.approx(
            _cz_sw(3, 120) / _cz_yg(3), rel=REL_TOL), (
            "大吉大利 R-YG4 纯面板差（择优同值 0.1 消去——1.50098/1.31758）")

    def test_godmode_elation_skill_ryg2(self, optimizer_driver):
        """银狼欢愉技 150621（Godmode 内 6×0.9，池钉 30）：R-SW1 对 150621 ×1.3 复钉
        + 大吉大利双方均触（R-YG2 翻案第三证——择优同值纯 R-YG4 面板差）."""
        eng, log = _make_logged(_trio_compiled("1506"))
        _enter_godmode(eng, 120.0)
        _pin_pool_gain(eng, "1501", 30.0)     # palette 重烘 0.8（统发——MMR 联动污染后直写复位）
        eng.state.actors["1506"].resources["hidden_mmr"] = 120.0
        _pin_trio_banger(eng)
        log.clear()
        _cast(eng, "1506", "150621")
        ours = _skill_hits(log, "1506")
        boon = _boon_hits(log)
        theirs = run_optimizer(optimizer_driver, _opt_sw_team(
            "elation_skill", cond={"godmodePlayer": True, "hiddenMmr": 120,
                                   "punchlineStacks": 30},
            third=_tm_sparxie(punchlineStacks=30)))

        assert len(ours) == 6, "我方随机 6 段（expected 取首全落）"
        hand_mine = _el(5.4, 30, _cz_sw(30, 120), el=SW_EL, fd=0.3)
        hand_theirs = _el(5.4, 30, _cz_sw(30, 120), el=SW_EL)
        assert sum(ours) == pytest.approx(hand_mine, rel=REL_TOL), (
            "我方 6 段合计（fdb 0.3×palette 0.8）vs 手算")
        assert len(theirs["hits"]) == 2, "对方 [聚合单发, 大吉大利]"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方（无档——mmrDmgMultiplier 不及欢愉技）vs 手算")
        assert sum(ours) / theirs["hits"][0]["damage"] == pytest.approx(
            1.3, rel=REL_TOL), "R-SW1 对 150621 恰为 ×1.3（三人场 palette 0.8 复钉）"
        hand_boon_mine = _el(0.2, 60, _cz_yg(30), el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方大吉大利（源恒爻光——palette 0.8；无 fdb）vs 手算")
        hand_boon_theirs = _el(0.2, 60, _cz_sw(30, 120), el=SW_EL)
        assert theirs["hits"][1]["damage"] == pytest.approx(
            hand_boon_theirs, rel=REL_TOL), "对方大吉大利（银狼容器）vs 手算"
        assert theirs["hits"][1]["damage"] / boon[0] == pytest.approx(
            _cz_sw(30, 120) / _cz_yg(30), rel=REL_TOL), (
            "大吉大利 R-YG4 纯面板差（择优同值——1.8801/1.4503）")


# ===========================================================================
# 矩阵③ 组合场：三 buff 源叠一主 C（多源进池加算口径——非空池下 D7 族近似显形钉法）
# ===========================================================================

class TestTripleBuffCombo:
    """火花主 C 吃满爻光（结界共享+抗穿+凶星）+火花 palette +银狼（E0 中性）全 buff 场；
    开拓者备选 800903 指定队友暴伤链."""

    def test_full_buff_field(self, optimizer_driver):
        """全 buff 场（结界 ELATION +0.02/终结技 RES_PEN +0.2/凶星 VULN +0.16/
        palette CD +0.8 四源各进各池全加算）：火花普攻段双方全等（无 D7 族乘算近似
        显形）；大吉大利 R-YG1'（0.30 vs 爻光 0.12——结界共享择优差）× R-YG4' 复合钉."""
        eng, log = _make_logged(_trio_compiled("1501"))
        _cast(eng, "1502", "150202")          # 结界（池 +3 → 6）
        _fire_ult(eng, "1502", "150203", energy=180.0)
        # 终结技链：抗穿先挂 → 额外阿哈代放（凶星低语经链上 150220 挂上；池 +5 → 11）
        _pin_trio_banger(eng)
        eng.state.actors["1506"].resources["hidden_mmr"] = 120.0
        assert math.isclose(eng.state.punchline, 11.0), "3+3（战技）+5（终结技）"
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1502"])["res_pen"],
            0.2, rel_tol=1e-9), "终结技全队抗穿 +20%"
        assert "WOES_WHISPER" in eng.state.actors["e1"].modifiers, "凶星低语已挂（链上代放）"
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1501"])["elation"],
            SP_EL + 0.02, rel_tol=1e-9), "结界共享 0.2×0.1=0.02 辐射火花"
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1502"])["elation"],
            YG_EL + 0.02, rel_tol=1e-9), "爻光自体 0.1+0.02=0.12"
        log.clear()
        _cast(eng, "1501", "150101")
        ours_sp = _hit_amounts(log, source="1501")
        boon = _boon_hits(log)
        theirs = run_optimizer(optimizer_driver, _opt_sp_team(
            "basic", cond={"punchlineStacks": 11},
            yg=_tm_yaoguang(skillZoneActive=True, teammateElationValue=0.1,
                            ultResPenBuff=True, woesWhisperVulnerability=True)))

        hand_crit = _crit(1.0, SP_ATK, _cz_sp(11), res=1.2, vuln=0.16)
        assert ours_sp == pytest.approx([hand_crit], rel=REL_TOL), (
            "我方普攻（palette 0.8×抗穿 1.2×易伤 1.16 四源全加算）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL), (
            "对方同链 vs 手算")
        assert ours_sp[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "普攻段双方全等（多源进池加算——无 D7 族近似）")
        hand_boon_mine = _el(0.2, 60, _cz_yg(11), el=YG_EL + 0.02,
                             res=1.2, vuln=0.16)
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方大吉大利（爻光盘含 palette 0.8/结界共享 0.12/抗穿/易伤）vs 手算")
        hand_boon_theirs = _el(0.2, 60, _cz_sp(11), el=SP_EL + 0.02,
                               res=1.2, vuln=0.16)
        assert theirs["hits"][1]["damage"] == pytest.approx(
            hand_boon_theirs, rel=REL_TOL), (
            "对方大吉大利（火花容器 0.30——择优 max(0.30, 0.1)）vs 手算")
        assert theirs["hits"][1]["damage"] / boon[0] == pytest.approx(
            (_cz_sp(11) * (1 + SP_EL + 0.02)) / (_cz_yg(11) * (1 + YG_EL + 0.02)),
            rel=REL_TOL), (
            "R-YG1'×R-YG4' 复合差（结界共享场择优 0.30 vs 爻光 0.12）坐实")
        st = theirs["stats"]
        assert st["elation"] == pytest.approx(SP_EL + 0.02, rel=REL_TOL), (
            "对方结界共享 teammateElationValue×0.2 回显")
        assert st["cd"] == pytest.approx(SP_CD + 0.8, rel=REL_TOL)
        assert st["res_pen"] == pytest.approx(0.2, rel=REL_TOL)
        assert st["vulnerability"] == pytest.approx(0.16, rel=REL_TOL)

    def test_trailblazer_cd_buff(self, optimizer_driver):
        """开拓者备选（800903 指定队友暴伤 +50%·3T → 火花）：跨 actor 指定链双方
        比等（对方 SingleTarget 落主 C 容器）；大吉大利不吃该 buff（指定火花非爻光）
        ——R-YG1×R-YG4 复合差在 TB buff 场复钉."""
        build = {"build": {"team": [
            {"character_template": "1501", "level": 80},
            {"character_template": "8009", "level": 80},
            {"character_template": "1502", "level": 80},
        ], "policy": _POLICY}}
        eng, log = _make_logged(compile_encounter(
            build, _stage(_team_dummy("fire")), template_roots=TEST_TEMPLATE_ROOTS))
        _fire_ult(eng, "8009", "800903", energy=160.0, target="1501")
        # 终结技链：暴伤先挂（指定火花）+ 分支 A 代放 800920（日志清后不进比对）+ 池 +5 → 8
        _pin_banger(eng, "1501", 60.0)
        _pin_banger(eng, "1502", 90.0)
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1501"])["crit_dmg"],
            SP_CD + 0.64 + 0.5, rel_tol=1e-9), "palette 0.64 + 指定暴伤 0.5 同池加算"
        assert math.isclose(eng.state.punchline, 8.0)
        log.clear()
        _cast(eng, "1501", "150101")
        ours_sp = _hit_amounts(log, source="1501")
        boon = _boon_hits(log)
        theirs = run_optimizer(optimizer_driver, _opt_sp_team(
            "basic", cond={"punchlineStacks": 8},
            third=_tm_tb()))

        hand_crit = _crit(1.0, SP_ATK, _cz_sp(8, extra_cd=0.5))
        assert ours_sp == pytest.approx([hand_crit], rel=REL_TOL), (
            "我方普攻（palette 0.64 + TB 暴伤 0.5 同池加算 1.30141）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert ours_sp[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "普攻段双方互对（指定队友链跨 actor 传导）")
        assert theirs["stats"]["cd"] == pytest.approx(
            SP_CD + 0.64 + 0.5, rel=REL_TOL), "对方 SingleTarget 落主 C 回显"
        hand_boon_mine = _el(0.2, 60, _cz_yg(8), el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine], rel=REL_TOL), (
            "我方大吉大利（爻光盘——无 TB buff（指定火花）；palette 0.64）vs 手算")
        hand_boon_theirs = _el(0.2, 60, _cz_sp(8, extra_cd=0.5), el=SP_EL)
        assert theirs["hits"][1]["damage"] == pytest.approx(
            hand_boon_theirs, rel=REL_TOL), (
            "对方大吉大利（火花容器含 TB buff——段附主 C 行动连带吃）vs 手算")
        assert theirs["hits"][1]["damage"] / boon[0] == pytest.approx(
            (_cz_sp(8, extra_cd=0.5) * (1 + SP_EL)) / (_cz_yg(8) * (1 + YG_EL)),
            rel=REL_TOL), (
            "R-YG1×R-YG4 复合差在 TB buff 场坐实（对方段连坐吃指定 buff——面板归属差放大）")


# ===========================================================================
# 矩阵④ 欢愉技代放链（额外阿哈时刻——火花 21 段/银狼 6 段在大吉大利场逐段）
# ===========================================================================

class TestAhaExtraChain:
    """爻光终结技 → 额外阿哈时刻：代放序=参演编号升序（爻光 116→火花 144→银狼 999），
    覆写 20 笑点 + 抗穿先挂 + 凶星由爻光代放先挂 + 大吉大利段（R-YG2——代放 on_action
    insert 无闩，目标为敌即触发：非 Godmode 链 2 段（爻光/火花——银狼 150620 自体目标
    不触发）、Godmode 链 3 段；笑点=触发者合并值（爻光自触读其钉值 90、余读进战 20））.
    对方无代放链——per-character 跑 elation_skill + yaoguangAhaInstant 覆写 20 等价
    （getYaoguangAhaPunchlineValue 读 teammate 链开关）."""

    def test_chain_segments_non_godmode(self, optimizer_driver):
        """非 Godmode 链：爻光 6 段（1.0+5×0.2 @20）+ 火花 21 段（0.5+20×0.25 @20）
        + 银狼 0 段（150620 无伤害段——对方 elationSkillHits 空数组同构）逐源互对；
        大吉大利 2 段（爻光/火花代放各触 1 次——150620 自体目标不触发；笑点=触发者
        合并值：爻光自触读钉值 90、火花读进战 20；源恒爻光无 fdb）手算钉；
        授好活当赏 20/人（§21.5）与池不耗（固定 20 结算）钉."""
        eng, log = _make_logged(_trio_compiled(
            "1501", weaknesses=["fire", "physical", "imaginary"]))
        _pin_banger(eng, "1502", 90.0)        # 爻光持好活当赏（大吉大利门）
        assert math.isclose(eng.state.punchline, 3.0)
        log.clear()
        _fire_ult(eng, "1502", "150203", energy=180.0)

        ours_yg = _skill_hits(log, "1502")
        ours_sp = _skill_hits(log, "1501")
        ours_sw = _skill_hits(log, "1506")
        boon = _boon_hits(log)
        theirs_yg = run_optimizer(optimizer_driver, _opt_yaoguang(
            "elation_skill",
            cond={"yaoguangAhaInstant": True, "ultResPenBuff": True,
                  "woesWhisperVulnerability": True},
            teammates=[_tm_sparxie(punchlineStacks=8), _tm_silver_wolf()]))
        theirs_sp = run_optimizer(optimizer_driver, _opt_sp_team(
            "elation_skill", cond={"punchlineStacks": 8},
            yg=_tm_yaoguang(yaoguangAhaInstant=True, ultResPenBuff=True,
                            woesWhisperVulnerability=True,
                            teammateCertifiedBangerStacks=20)))
        theirs_sw = run_optimizer(optimizer_driver, _opt_sw_team(
            "elation_skill", cond={"godmodePlayer": False, "punchlineStacks": 8},
            yg=_tm_yaoguang(yaoguangAhaInstant=True, ultResPenBuff=True,
                            woesWhisperVulnerability=True,
                            teammateCertifiedBangerStacks=20),
            third=_tm_sparxie(punchlineStacks=8)))

        # 链上面板：池 3+5（终结技 #1）=8 → palette 0.64；抗穿 1.2/凶星 1.16 全段同吃
        hand_yg = _el(2.0, 20, _cz_yg(8), el=YG_EL, vuln=0.16, res=1.2)
        assert len(ours_yg) == 6, "爻光代放 1 全体 + 5 随机"
        assert sum(ours_yg) == pytest.approx(hand_yg, rel=REL_TOL), (
            "爻光代放段（覆写 20×palette 0.64×抗穿×凶星——凶星本发即吃）vs 手算")
        assert len(theirs_yg["hits"]) == 2, "对方 [聚合单发, 大吉大利]（main=爻光自触）"
        assert theirs_yg["hits"][0]["damage"] == pytest.approx(hand_yg, rel=REL_TOL)
        assert sum(ours_yg) == pytest.approx(theirs_yg["hits"][0]["damage"], rel=REL_TOL), (
            "爻光代放段双方互对（yaoguangAhaInstant 覆写 20——对方 teammate 链接口）")
        assert theirs_yg["hits"][0]["punchline_stacks"] == 20

        hand_sp = _el(5.5, 20, _cz_sp(8), el=SP_EL, vuln=0.16, res=1.2)
        assert len(ours_sp) == 21, "火花代放 1 全体 + 20 追加"
        assert sum(ours_sp) == pytest.approx(hand_sp, rel=REL_TOL), (
            "火花代放 21 段（覆写 20——段段读 _aha_pool_override）vs 手算")
        assert theirs_sp["hits"][0]["damage"] == pytest.approx(hand_sp, rel=REL_TOL)
        assert sum(ours_sp) == pytest.approx(theirs_sp["hits"][0]["damage"], rel=REL_TOL), (
            "火花代放 21 段总和双方互对（段数差在案）")
        assert theirs_sp["hits"][0]["punchline_stacks"] == 20, (
            "对方覆写 20（getYaoguangAhaPunchlineValue 读爻光 teammate 链开关）")

        assert ours_sw == [], "银狼非 Godmode 代放 150620 无伤害段（+15 MMR  only）"
        assert theirs_sw["hits"] == [], "对方非 Godmode elationSkillHits 空数组同构"

        # 大吉大利（R-YG2 翻案——代放触发双方同构）：爻光自触段附自己行动=自己面板
        # （双方全等——R-YG4 无差）；火花触发段对方附火花容器（R-YG1×R-YG4 复合差）
        hand_boon_yg = _el(0.2, 90, _cz_yg(8), el=YG_EL, vuln=0.16, res=1.2)
        hand_boon_sp_mine = _el(0.2, 20, _cz_yg(8), el=YG_EL, vuln=0.16, res=1.2)
        assert boon == pytest.approx([hand_boon_yg, hand_boon_sp_mine], rel=REL_TOL), (
            "大吉大利 2 段（爻光代放触发自触读 CB 90 / 火花代放触发读进战 CB 20；"
            "源恒爻光无 fdb）vs 手算")
        assert theirs_yg["hits"][1]["damage"] == pytest.approx(
            hand_boon_yg, rel=REL_TOL), (
            "对方爻光大吉大利（自行动自面板——笑点=certifiedBangerStacks 90 双方同钉）"
            "双方全等（R-YG4 无差实例）")
        hand_boon_sp_theirs = _el(0.2, 20, _cz_sp(8), el=SP_EL, vuln=0.16, res=1.2)
        assert theirs_sp["hits"][1]["damage"] == pytest.approx(
            hand_boon_sp_theirs, rel=REL_TOL), "对方火花大吉大利（火花容器）vs 手算"
        assert theirs_sp["hits"][1]["damage"] / boon[1] == pytest.approx(
            (_cz_sp(8) * (1 + SP_EL)) / (_cz_yg(8) * (1 + YG_EL)), rel=REL_TOL), (
            "火花触发大吉大利差=R-YG1×R-YG4 双因子（链上场复合差坐实）")
        assert math.isclose(eng.state.punchline, 8.0), (
            "额外时刻固定 20 不耗池（3+5=8——官方文本在案）")
        for cid, want in (("1501", 40.0), ("1502", 110.0), ("1506", 40.0)):
            assert math.isclose(
                eng._resource_value(eng.state.actors[cid], "certified_banger"), want), (
                f"{cid} 好活当赏 进战 20+照授 20={'40' if cid != '1502' else '110'}"
                f"（爻光另有钉值 90 底）")

    def test_chain_segments_godmode(self, optimizer_driver):
        """Godmode 链（银狼 150621 代放 6 段 @20）：R-SW1 ×1.3 链上场复钉 +
        大吉大利 3 段（银狼 cast target=敌触发——150621 target_type single）。
        链上 MMR=125（钉值 120+终结技 +5 笑点经 150604 不判 actor 联动——钩序在
        银狼代放前）；palette 0.64（池 8）."""
        eng, log = _make_logged(_trio_compiled(
            "1501", weaknesses=["fire", "physical", "imaginary"]))
        _enter_godmode(eng, 120.0)
        _pin_banger(eng, "1502", 90.0)
        log.clear()
        _fire_ult(eng, "1502", "150203", energy=180.0)

        ours_sw = _skill_hits(log, "1506")
        boon = _boon_hits(log)
        theirs_sw = run_optimizer(optimizer_driver, _opt_sw_team(
            "elation_skill", cond={"godmodePlayer": True, "hiddenMmr": 125,
                                   "punchlineStacks": 8},
            yg=_tm_yaoguang(yaoguangAhaInstant=True, ultResPenBuff=True,
                            woesWhisperVulnerability=True,
                            teammateCertifiedBangerStacks=20),
            third=_tm_sparxie(punchlineStacks=8)))

        assert len(ours_sw) == 6, "银狼代放 150621（Godmode 内形态——available_if 闸实证）"
        hand_mine = _el(5.4, 20, _cz_sw(8, 125), el=SW_EL, vuln=0.16, res=1.2, fd=0.3)
        hand_theirs = _el(5.4, 20, _cz_sw(8, 125), el=SW_EL, vuln=0.16, res=1.2)
        assert sum(ours_sw) == pytest.approx(hand_mine, rel=REL_TOL), (
            "银狼代放 6 段（覆写 20×fdb 0.3×抗穿×凶星×MMR 125 暴击区）vs 手算")
        assert len(theirs_sw["hits"]) == 2, "对方 [聚合单发, 大吉大利]"
        assert theirs_sw["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL)
        assert sum(ours_sw) / theirs_sw["hits"][0]["damage"] == pytest.approx(
            1.3, rel=REL_TOL), "R-SW1 对链上 150621 恰为 ×1.3（域偏差在案㈢链上场坐实）"
        assert theirs_sw["hits"][0]["punchline_stacks"] == 20
        hand_boon_yg = _el(0.2, 90, _cz_yg(8), el=YG_EL, vuln=0.16, res=1.2)
        hand_boon_tm = _el(0.2, 20, _cz_yg(8), el=YG_EL, vuln=0.16, res=1.2)
        assert boon == pytest.approx(
            [hand_boon_yg, hand_boon_tm, hand_boon_tm], rel=REL_TOL), (
            "大吉大利 3 段（爻光/火花/银狼代放各触 1 次——R-YG2 翻案链上场：触发双方"
            "同构；爻光自触读 CB 90、火花/银狼读进战 CB 20；源恒爻光无 fdb）vs 手算")
        hand_boon_sw_theirs = _el(0.2, 20, _cz_sw(8, 125), el=SW_EL,
                                  vuln=0.16, res=1.2)
        assert theirs_sw["hits"][1]["damage"] == pytest.approx(
            hand_boon_sw_theirs, rel=REL_TOL), "对方银狼大吉大利（银狼容器）vs 手算"
        assert theirs_sw["hits"][1]["damage"] / boon[2] == pytest.approx(
            _cz_sw(8, 125) / _cz_yg(8), rel=REL_TOL), (
            "银狼触发大吉大利差=R-YG4 纯面板差（择优同值——CR 0.697 场 1.79458/1.41238）")


# ===========================================================================
# R-YG3 开拓者备选核销（8009 战技耗点三人场复钉——palette 随池 3/6 双场钉法）
# ===========================================================================

class TestRyg3TrailblazerBackup:
    """开拓者主 C（teammates=爻光+火花）：8009 战技耗 1 点 → R-YG3 ×2 三人场复钉."""

    def test_skill_double_proc_trio(self, optimizer_driver):
        """8009 战技（耗 1 点）：对方 consumesSkillPoints+spUsed=1 → 大吉大利 ×2
        （0.4 聚合，笑点=发放后 CB 80）；我方单触 0.2 → 恰为 2.0 × R-YG4 面板比。
        天赋 800904「施放攻击后 +3 笑点」在钩序中段的 8009 钩组内（模板 588 行——
        天赋追加段之后、爻光大吉大利之前）→ 池 3→6 palette 0.48 只有大吉大利吃，
        本体/追加段读池 3 palette 0.24——对方双场钉法（115/120 先例）."""
        eng, log = _make_logged(_mixed_compiled("8009", ["1502", "1501"]))
        _pin_banger(eng, "8009", 60.0)
        _pin_banger(eng, "1502", 60.0)
        log.clear()
        _cast(eng, "8009", "800902")
        ours_tb = _hit_amounts(log, source="8009")
        boon = _boon_hits(log)
        sc1 = _opt_tb("skill", cond={"punchlineStacks": 3})
        sc1["teammates"] = [_tm_yaoguang(teammateCertifiedBangerStacks=80),
                            _tm_sparxie(punchlineStacks=3)]
        theirs3 = run_optimizer(optimizer_driver, sc1)
        sc2 = _opt_tb("skill", cond={"punchlineStacks": 6})
        sc2["teammates"] = [_tm_yaoguang(teammateCertifiedBangerStacks=80),
                            _tm_sparxie(punchlineStacks=6)]
        theirs6 = run_optimizer(optimizer_driver, sc2)

        hand_crit = _crit(0.6, TB_ATK, _cz_tb(3))
        hand_talent = _el(0.3, 60, _cz_tb(3), el=0.0)
        assert ours_tb == pytest.approx([hand_crit, hand_talent], rel=REL_TOL), (
            "我方战技+天赋追加（追加读获得前 CB 60/池 3 palette 0.24——天赋 +3 笑点钩"
            "在追加段之后）vs 手算")
        assert len(theirs3["hits"]) == 3, "对方 [战技, 天赋, 大吉大利×2 聚合]"
        assert theirs3["hits"][0]["damage"] == pytest.approx(hand_crit, rel=REL_TOL)
        assert theirs3["hits"][1]["damage"] == pytest.approx(hand_talent, rel=REL_TOL)
        assert ours_tb[0] == pytest.approx(theirs3["hits"][0]["damage"], rel=REL_TOL), (
            "战技段双方互对（池 3 场）")
        assert ours_tb[1] == pytest.approx(theirs3["hits"][1]["damage"], rel=REL_TOL), (
            "天赋追加双方互对（池 3 场——双场钉法）")
        hand_boon_mine = _el(0.2, 80, _cz_yg(6), el=YG_EL)
        assert boon == pytest.approx([hand_boon_mine, hand_boon_mine], rel=REL_TOL), (
            "我方双触两段（sp_consumed=1 第二钩触发——R-YG3 已收官；笑点=触发者发放后 80；"
            "池 6 palette 0.48——天赋 +3 在爻光钩前入账）vs 手算")
        hand_boon_theirs = _el(0.4, 80, _cz_tb(6), el=YG_EL)
        assert theirs6["hits"][2]["damage"] == pytest.approx(
            hand_boon_theirs, rel=REL_TOL), "对方大吉大利 ×2（池 6 场）vs 手算"
        assert theirs6["hits"][2]["damage"] / sum(boon) == pytest.approx(
            _cz_tb(6) / _cz_yg(6), rel=REL_TOL), (
            "R-YG3 收官后残差恰为 R-YG4 暴击区比（池 6 palette 0.48 场复钉）")
        assert theirs6["hits"][2]["elation_scaling"] == pytest.approx(0.4, rel=REL_TOL)
        assert theirs6["hits"][2]["punchline_stacks"] == 80
