"""L4 组队级对拍（BACKLOG B22 扩展③）：跨角色 buff 传导——队友条件 buff 折叠进主 C
面板（光环域跨 actor 寻址）/ A 挂 B 吃（上对敌 debuff 他方消费）/ 多源 buff 同池
加乘口径 / 缇宝境界附加伤害（after_being_hit 消费——86d1594 钩源伤害补发修复的
双盲验收）。逐段伤害 == hsr-optimizer 组队链整链伤害（rel_tol 1e-4）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character" + teammates 块
（驱动头注有链路口径）——镜像 comboStateTransform.precomputeTeammates：队友
controller（注册表 + 星魂构造钉死）的 teammateAction.characterConditionals =
teammateDefaults() 铺底 + 场景覆盖，precomputeMutualEffectsContainer(x, 队友 action,
context, 主 action) 落主角色容器（FullTeam 折叠进主 C 的原生口径）；path-only 占位
队友只进 countTeamPath 元数据。我方路径：真模板三角色队（黄泉 1308 + 缇宝 1403 +
砂金 1304——demo_黄泉队编成）→ 编译 → CombatEngine 钉资源 → _cast/_fire_ultimate →
bus on_hp_decrease 逐段记录仪（setup 前订阅，L2 先例）。

统一口径（两侧一致，沿用 L2/装备级）：星魂钉死、行迹满级、无光锥无遗器、假人
lvl80 def 1000（防御区 0.5）、未击破（0.9）、期望暴击；假人弱点 [thunder, quantum]
——黄泉本体（thunder）与缇宝境界附加（quantum）同享抗性区 1.0 基准。demo 队
countTeamPath(nihility)=1 → 黄泉 The Abyss 两侧同灭（对方 scaling[0]=0 原生，
我方 count_team<2 不出件）；D7 显形另起虚无×2 变体。

===========================================================================
缇宝 1403 buff 状态映射表（对方 teammateContent 开关 ↔ 我方模板触发）
===========================================================================
对方 teammate content（默认）  我方模板对应                                  对拍处置
numinosity（true）             战技神启 NUMINOSITY：挂缇宝、effect_scope      施放 140302 后比等——
                               team 辐射全队 res_pen 0.24（lv10）             光环跨 actor 传导主路径
ultZone（true）                终结技境界：TR_ZONE 标 + TR_ZONE_VULN 植       施放 140303 后比等——
                               敌方全体 vulnerability 0.30（lv10）            A 挂 B 吃主路径
e1TrueDmg / e4DefPen（true）   E1 真伤/E4 无视防御——星魂未收（1403 fixture   E0 两侧门控同灭
                               待收③在案；对方 e>=1/e>=4 构造钉死门控）
（无开关）境界附加伤害           after_being_hit 钩：境界中我方攻击每命中 1     逐段数值三方全等（双盲验收）；
                               目标 1 段 0.12×HP quantum 附加（lv10）          段数口径见 T2
（teammate 不建）天赋追加        on_ultimate 钩（他方开大→全体 0.18×HP）        缇宝本人 fua 行动比等
（teammate 不建）行迹 3 自增伤   talentFuaStacks×0.72 BOOST（主 C 侧 defaults   钉 0（开战 0 层——
                               3 层/alliesMaxHp 25000 HP 件为面板污染件）      中性面板口径）

===========================================================================
砂金 1304 buff 状态映射表
===========================================================================
对方 teammate content（默认）  我方模板对应                                  对拍处置
fortifiedWagerBuff（true）     天赋坚垣筹码：全队效果抵抗 +50%（param 随档）   无伤害消费——两侧同挂不比值
enemyUnnervedDebuff（true）    终结技「不安」：敌方暴伤承 +15%——**摘除记待收** 钉 T1 结构差（1.0325/1.025）；
                               （1304 fixture 头注⑧：目标侧 crit 承区无消费端）；+注入 crit_dmg 0.15 等价件比等
                               对方 FullTeam CD_BOOST 0.15 攻击侧近似          （隔离唯一差=待收通道）
e2ResShred（true，E2）         E2 全属性抗性 -12%——摘除记待收（同头注①）      E0 两侧门控同灭

结构差清单（数值自证见各 divergence 测试——差值恰为标注倍数，任一侧改动触红）：
T1 砂金「不安」暴伤承 15%（我方摘除待收；对方攻击侧 CD_BOOST 近似）→
   对方/我方 = (1+0.05×0.65)/(1+0.05×0.5) = 1.0325/1.025 ≈ 1.00732
T2 缇宝境界附加段数口径：对方不把队友附伤挂主 C 行动（只建缇宝本人行动上的
   Additional 段=建模收敛）；我方 after_being_hit 逐目标/逐发伤链 seg0 发射
   （每命中目标/每钩链 1 段 0.12——官方「每命中 1 个目标造成 1 次」逐段语义；
   「一次攻击一次」合并口径需攻击实例 id/攻击结束事件通道——缺，1314_翡翠
   同案在案）→ 单段数值三方全等，段数各按口径钉死（黄泉 13 段大招=5 段附伤：
   雨斩①/结爆×3/Core① 各开一链）
T3（D7 显形）黄泉 The Abyss 加算（我方 all_dmg 入增伤池）vs 乘算（对方
   FINAL_DMG ×1.6）：空池等价（L2 D7 在案），非空池（钉 dmg_boost 0.2）下
   对方/我方 = (1.2×1.6)/(1.8) = 16/15 ≈ 1.06667

已修真病两件（本批钓出，小修笔误级——单列）：
B-NEW③ 缇宝境界钩 n² 放大（模板级）：scaling_hp 旧值
   "0.12 * count($event.hit_targets)" × after_being_hit 逐目标发射（1314 在案
   引擎契约）→ 3 敌场 3 fires × 0.36 = 1.08×HP（官方 3×0.12=0.36）——
   1403 fixture 勘正为逐事件 0.12（逐段官方语义，暴击逐段独立掷骰同向）
B-NEW④ 钩源 0 伤害幻影发 after_being_hit（引擎级，86d1594 新发射口漏闸）：
   1308 结爆钩「×(res__knots_n > 0)」置零=不发的 0 伤害 deal_damage 仍发受击
   收尾 → 黄泉单大招境界被幻影触发 7 次（返渡 1 + Core 6）——hooks.py 发射
   闸 result.value>0（盾全吸收照发，置零幻影不算命中；链内命中序号同步不占段）
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
# 同 L2/装备级：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    AC_ATK, Z, _POLICY, _acheron_ult, _cast, _hit_amounts, _inject, _knots,
    _make_logged, _stage,
)
from tests.test_crosscheck_equipment import _clean_knots  # noqa: F401
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 口径常数（两侧钉死）
# ---------------------------------------------------------------------------

TR_HP = 1047.816           # 缇宝白值 HP（fixture 终审值——境界附加/天赋 FUA 的 HP 倍率基数）
TR_CR, TR_CD = 0.17, 0.873
TR_Z = 0.5 * 0.9 * (1 + TR_CR * TR_CD)   # 缇宝基准防御×未击破×期望暴击 = 0.5167845
AV_UNNERVED_RATIO = (1 + 0.05 * 0.65) / (1 + 0.05 * 0.5)   # T1 = 1.0325/1.025
D7_RATIO = (1.2 * 1.6) / 1.8                               # T3 = 16/15


# ---------------------------------------------------------------------------
# 我方侧引擎件（demo_黄泉队编成：黄泉+缇宝+砂金三真模板）
# ---------------------------------------------------------------------------

def _team_dummy(*, n=1):
    """双弱点假人：thunder（黄泉本体）+ quantum（缇宝附加）——抗性区 1.0 基准."""
    return [{"actor_id": f"e{i+1}" if n > 1 else "e1", "name": f"假人{i+1}",
             "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000, "max_toughness": 9999,
             "weakness": ["thunder", "quantum"]} for i in range(n)]


def _team_build(*, aventurine: bool = True, extra_nihility: int = 0):
    team = [{"character_template": "1308", "level": 80},
            {"character_template": "1403", "level": 80}]
    if aventurine:
        team.append({"character_template": "1304", "level": 80})
    for i in range(extra_nihility):   # 虚无假人（The Abyss 计数件——L2 同形）
        team.append({"actor_id": f"nih{i}", "name": f"虚无{i}", "inline": True,
                     "path": "nihility",
                     "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
                     "actions": [{"action_id": f"nih{i}_basic", "name": "普攻",
                                  "action_type": "basic", "target_type": "single",
                                  "damage_type": "ice", "scaling": [{"atk": 1.0}],
                                  "toughness_dmg": 10}]})
    return {"build": {"team": team, "policy": _POLICY}}


def _team_compiled(*, aventurine: bool = True, extra_nihility: int = 0, enemies=None):
    return compile_encounter(
        _team_build(aventurine=aventurine, extra_nihility=extra_nihility),
        _stage(enemies or _team_dummy()), template_roots=TEST_TEMPLATE_ROOTS)


def _tribbie_skill(eng):
    """战技 140302：神启 NUMINOSITY（挂缇宝、辐射全队 res_pen 0.24）."""
    _cast(eng, "1403", "140302")


def _tribbie_ult(eng):
    """终结技 140303：境界 TR_ZONE + 敌方全体 TR_ZONE_VULN（vulnerability 0.30）."""
    st = eng.state.actors["1403"]
    st.current_energy = 120.0
    ult = next(a for a in eng.actions_by_actor["1403"] if a.action_id == "140303")
    assert eng._fire_ultimate(st, ult) is True


def _prep_zone(eng, log, *, numinosity: bool = True):
    """缇宝铺场（skill±ult）+ 清记录仪——铺场段不进比对."""
    if numinosity:
        _tribbie_skill(eng)
    _tribbie_ult(eng)
    log.clear()


def _zone_adds(log, *, target=None):
    """缇宝境界附加段：source=1403 + action_type=additional（决策卡 #19 不再触发
    命中类监听——该类别段天然不会递归自引）."""
    return [e for e in log
            if e.get("reason") == "hit" and e.get("source") == "1403"
            and e.get("action_type") == "additional"
            and (target is None or e.get("target") == target)]


def _tr_fua(log):
    return [e for e in log
            if e.get("reason") == "hit" and e.get("source") == "1403"
            and e.get("action_type") == "follow_up"]


def _zone_add_hand(*, numinosity: bool = True):
    """境界附加单段手算锚：0.12×缇宝 HP × 基准区 ×（抗穿 1.24）× 承伤 1.3."""
    return 0.12 * TR_HP * TR_Z * (1.24 if numinosity else 1.0) * 1.3


# ---------------------------------------------------------------------------
# 对方侧场景模子（teammates 块；映射表见模块 docstring）
# ---------------------------------------------------------------------------

def _tm_tribbie(**cond):
    return {"character_id": "1403", "eidolon": 0, "path": "Harmony",
            "element": "quantum", "conditionals": cond}


def _tm_aventurine(**cond):
    return {"character_id": "1304", "eidolon": 0, "path": "Preservation",
            "element": "imaginary", "conditionals": cond}


def _opt_ac(action: str, teammates: list, *, cond: dict | None = None,
            extra_attacker: dict | None = None):
    """对方黄泉组队场景：E0 全开关中性钉死（同 L2 基准）；demo 队 countTeamPath=1
    → The Abyss 两侧同灭，nihilityTeammatesBuff 钉 false 明示."""
    c = {"crimsonKnotStacks": 9, "nihilityTeammatesBuff": False,
         "e1EnemyDebuffed": False, "thunderCoreStacks": 0,
         "stygianResurgeHitsOnTarget": 6, "e4UltVulnerability": True,
         "e6UltBuffs": True}
    c.update(cond or {})
    return {
        "kind": "character", "character_id": "1308", "eidolon": 0,
        "action": action, "element": "thunder", "conditionals": c,
        "base": {"atk": AC_ATK, "hp": 1125.432, "def": 436.59, "spd": 101},
        "attacker": {"atk": AC_ATK, "hp": 1125.432, "def": 436.59, "spd": 101,
                     "cr": 0.05, "cd": 0.5, **(extra_attacker or {})},
        "self_path": "Nihility",
        "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                  "count": 1},
        "teammates": teammates,
    }


def _opt_tr(action: str, *, numinosity: bool = True, ult_zone: bool = True):
    """对方缇宝本人场景（境界附加 oracle——对方只把附伤建在缇宝本人行动上）：
    中性件钉死（行迹 3 自增伤 0 层/境界 HP 件 0 基数/昔涟件无行动体）。"""
    cond = {"numinosity": numinosity, "ultZone": ult_zone, "talentFuaStacks": 0,
            "alliesMaxHp": 0, "cyreneSpecialEffect": False}
    base = {"atk": 523.908, "hp": TR_HP, "def": 727.65, "spd": 96}
    return {
        "kind": "character", "character_id": "1403", "eidolon": 0,
        "action": action, "element": "quantum", "conditionals": cond,
        "base": base, "attacker": {**base, "cr": TR_CR, "cd": TR_CD},
        "self_path": "Harmony",
        "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                  "count": 1},
    }


# ===========================================================================
# 矩阵① 缇宝 buff 单开 → 黄泉战技/终结技逐段（抗穿/承伤族跨 actor 传导）
# ===========================================================================

class TestTribbieToAcheron:
    """缇宝单开两态（numinosity only / zone only / 双件）→ 黄泉逐段三方全等."""

    def test_panel_echo_numinosity(self, optimizer_driver):
        """面板回显闸：numinosity → res_pen 0.24 落主 C 容器（FullTeam 折叠口径）."""
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_tribbie(numinosity=True, ultZone=False)]))
        st = theirs["stats"]
        assert st["res_pen"] == pytest.approx(0.24, rel=REL_TOL)
        assert st["vulnerability"] == pytest.approx(0.0, abs=1e-12), "zone 不开=承伤中性"

    def test_panel_echo_zone(self, optimizer_driver):
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_tribbie(numinosity=True, ultZone=True)]))
        st = theirs["stats"]
        assert st["res_pen"] == pytest.approx(0.24, rel=REL_TOL)
        assert st["vulnerability"] == pytest.approx(0.30, rel=REL_TOL)

    def test_skill_numinosity(self, optimizer_driver):
        """神启单开：黄泉战技 1.6 单段——抗穿 0.24 跨 actor 传导（我方 effect_scope
        team 光环辐射 vs 对方 FullTeam mutual 折叠）."""
        eng, log = _make_logged(_team_compiled())
        _tribbie_skill(eng)
        assert eng.pipeline.effective_stats(eng.state.actors["1308"])["res_pen"] \
            == pytest.approx(0.24, rel=1e-9), "我方光环辐射落黄泉面板"
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_tribbie(numinosity=True, ultZone=False)]))

        hand = 1.6 * AC_ATK * Z * 1.24
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["resMulti"] == pytest.approx(1.24, rel=REL_TOL)

    def test_skill_zone_only(self, optimizer_driver):
        """境界单开（神启不施放）：承伤 0.30 A 挂 B 吃（缇宝植敌身 debuff、黄泉消费）
        + 境界附加单段双盲（单开态 84.473231）."""
        eng, log = _make_logged(_team_compiled())
        _prep_zone(eng, log, numinosity=False)
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        adds = _zone_adds(log)
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_tribbie(numinosity=False, ultZone=True)]))
        theirs_tr = run_optimizer(optimizer_driver,
                                  _opt_tr("ult", numinosity=False, ult_zone=True))

        hand = 1.6 * AC_ATK * Z * 1.3
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(1.3, rel=REL_TOL)
        assert len(adds) == 1, "单敌单段攻击 → 1 段境界附加"
        assert adds[0]["amount"] == pytest.approx(_zone_add_hand(numinosity=False), rel=REL_TOL), (
            "我方附加段 vs 手算")
        assert theirs_tr["hits"][1]["damage"] == pytest.approx(
            _zone_add_hand(numinosity=False), rel=REL_TOL)
        assert adds[0]["amount"] == pytest.approx(theirs_tr["hits"][1]["damage"], rel=REL_TOL), (
            "附加段双盲：黄泉攻击消费 vs 对方缇宝本人段")

    def test_skill_numinosity_zone(self, optimizer_driver):
        """双件：抗穿 0.24 + 承伤 0.30 同发——两族乘区独立叠乘."""
        eng, log = _make_logged(_team_compiled())
        _prep_zone(eng, log)
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        adds = _zone_adds(log)
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_tribbie(numinosity=True, ultZone=True)]))

        hand = 1.6 * AC_ATK * Z * 1.24 * 1.3
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert len(adds) == 1
        assert adds[0]["amount"] == pytest.approx(_zone_add_hand(), rel=REL_TOL)

    def test_ult_full_chain_zone(self, optimizer_driver):
        """黄泉大招 13 段全链（结 9 起手）+ 缇宝双件：天赋 RES_PEN 注入等价（D4 隔离，
        L2 同口径）→ 抗穿 0.2+0.24=0.44 同池加算 + 承伤 1.3——13 段逐段手算 +
        总和双方互对（对方聚合 5.22 单发）."""
        eng, log = _make_logged(_team_compiled())
        _inject(eng, "1308", "XC_RES_PEN", {"res_pen": 0.2})   # 天赋大招 RES_PEN 等价件
        _clean_knots(eng)                                      # 行迹 1 开局结隔离
        _knots(eng, "e1", 9)
        _prep_zone(eng, log)
        _acheron_ult(eng)
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "ult", [_tm_tribbie(numinosity=True, ultZone=True)]))

        z_ult = Z * 1.44 * 1.3   # 防御 0.5 × 未击破 0.9 × 暴击 1.025 × 抗性 1.44 × 承伤 1.3
        scalings = [0.24, 0.6, 0.24, 0.6, 0.24, 0.6, 1.2] + [0.25] * 6
        assert len(ours) == 13, f"13 段齐发（实收 {len(ours)} 段）"
        for i, (amt, sc) in enumerate(zip(ours, scalings)):
            assert amt == pytest.approx(sc * AC_ATK * z_ult, rel=REL_TOL), f"段 {i}（{sc}）vs 手算"
        assert sum(ours) == pytest.approx(theirs["total"], rel=REL_TOL), "13 段总和双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("resMulti", 1.44), ("vulnMulti", 1.3), ("dmgBoostMulti", 1.0),
                     ("finalDmgMulti", 1.0), ("abilityMulti", 5.22 * AC_ATK)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert theirs["stats"]["res_pen"] == pytest.approx(0.44, rel=REL_TOL), (
            "天赋 0.2 + 神启 0.24 同池加算——多源抗穿口径")


# ===========================================================================
# 矩阵② 砂金 debuff 单开 → 黄泉消费（A 挂 B 吃——我方摘除待收，钉 T1 + 隔离件）
# ===========================================================================

class TestAventurineToAcheron:
    """砂金「不安」暴伤承 15%：我方 1304 fixture 摘除记待收（目标侧 crit 承区无
    消费端）→ 钉 T1 结构差；注入 crit_dmg 0.15 等价件 → 比等（隔离唯一差）."""

    def test_unnerved_pending_divergence(self, optimizer_driver):
        """T1：砂金大招实打（盲注 FUA 链全发）后黄泉 crit_dmg 仍 0.5——摘除待收
        实证；对方 CD_BOOST 0.15 落面板 → 对方恰为我方 ×(1.0325/1.025)."""
        eng, log = _make_logged(_team_compiled())
        st = eng.state.actors["1304"]
        st.current_energy = 110.0
        ult = next(a for a in eng.actions_by_actor["1304"] if a.action_id == "130403")
        assert eng._fire_ultimate(st, ult) is True
        assert eng.pipeline.effective_stats(eng.state.actors["1308"])["crit_dmg"] \
            == pytest.approx(0.5, abs=1e-12), "我方「不安」摘除待收——黄泉面板无暴伤承"
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_aventurine(fortifiedWagerBuff=True, enemyUnnervedDebuff=True)]))

        assert ours == pytest.approx([1.6 * AC_ATK * Z], rel=REL_TOL), "我方无暴伤承基准链"
        assert theirs["stats"]["cd"] == pytest.approx(0.65, rel=REL_TOL), (
            "对方 CD_BOOST 0.15 落面板（攻击侧近似口径）")
        assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(1.0325, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            AV_UNNERVED_RATIO, rel=REL_TOL), "T1 结构差恰为 1.0325/1.025"

    def test_unnerved_injected_equivalence(self, optimizer_driver):
        """注入 crit_dmg 0.15 等价件 → 三方全等——隔离证明唯一差 = 待收的目标侧
        暴伤承通道（其余跨 actor 传导链两侧同构）."""
        eng, log = _make_logged(_team_compiled())
        _inject(eng, "1308", "XC_CD", {"crit_dmg": 0.15})
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_aventurine(fortifiedWagerBuff=True, enemyUnnervedDebuff=True)]))

        hand = 1.6 * AC_ATK * 0.5 * 0.9 * 1.0325
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方注入件 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


# ===========================================================================
# 矩阵③ 双开组合 → 池内加算/乘算口径（T1 组合态 + D7 非空池显形）
# ===========================================================================

class TestCombinedPool:
    """缇宝+砂金双开：cd 注入对齐 → 全等；不注入 → 钉 T1 组合态；虚无队变体
    +非空增伤池 → D7 加乘近似显形钉 16/15."""

    def test_skill_both_injected(self, optimizer_driver):
        """双开+cd 注入：抗穿 0.24 × 承伤 1.3 × 暴伤承 0.15 三族跨 actor 同发——
        三乘区独立叠乘三方全等."""
        eng, log = _make_logged(_team_compiled())
        _inject(eng, "1308", "XC_CD", {"crit_dmg": 0.15})
        _prep_zone(eng, log)
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_tribbie(numinosity=True, ultZone=True),
                      _tm_aventurine(fortifiedWagerBuff=True, enemyUnnervedDebuff=True)]))

        hand = 1.6 * AC_ATK * 0.5 * 0.9 * 1.0325 * 1.24 * 1.3
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_skill_both_unpinned(self, optimizer_driver):
        """双开不注入：缇宝双件全等 + T1 砂金件钉差——组合结构差恰为 1.0325/1.025."""
        eng, log = _make_logged(_team_compiled())
        _prep_zone(eng, log)
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_tribbie(numinosity=True, ultZone=True),
                      _tm_aventurine(fortifiedWagerBuff=True, enemyUnnervedDebuff=True)]))

        assert ours == pytest.approx([1.6 * AC_ATK * Z * 1.24 * 1.3], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            AV_UNNERVED_RATIO, rel=REL_TOL), "T1 组合态结构差恰为 1.0325/1.025"

    def test_ult_both_injected(self, optimizer_driver):
        """双开+双注入（天赋 RES_PEN 0.2 + 暴伤承 0.15）→ 大招 13 段总和三方全等."""
        eng, log = _make_logged(_team_compiled())
        _inject(eng, "1308", "XC_RES_PEN", {"res_pen": 0.2})
        _inject(eng, "1308", "XC_CD", {"crit_dmg": 0.15})
        _clean_knots(eng)
        _knots(eng, "e1", 9)
        _prep_zone(eng, log)
        _acheron_ult(eng)
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "ult", [_tm_tribbie(numinosity=True, ultZone=True),
                    _tm_aventurine(fortifiedWagerBuff=True, enemyUnnervedDebuff=True)]))

        z_ult = 0.5 * 0.9 * 1.0325 * 1.44 * 1.3
        scalings = [0.24, 0.6, 0.24, 0.6, 0.24, 0.6, 1.2] + [0.25] * 6
        assert len(ours) == 13
        for i, (amt, sc) in enumerate(zip(ours, scalings)):
            assert amt == pytest.approx(sc * AC_ATK * z_ult, rel=REL_TOL), f"段 {i}（{sc}）vs 手算"
        assert sum(ours) == pytest.approx(theirs["total"], rel=REL_TOL), "13 段总和双方互对"
        assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(1.0325, rel=REL_TOL)

    def test_d7_pool_additive_vs_multiplicative(self, optimizer_driver):
        """T3（D7 显形）：The Abyss 加算（我方 all_dmg 入池 0.2+0.6=1.8）vs 乘算
        （对方 BOOST 1.2 × FINAL_DMG 1.6=1.92）——虚无×2 变体起 0.6 档 + 钉
        dmg_boost 0.2 非空池 → 对方恰为我方 ×16/15（空池等价在 L2 D7 在案）."""
        eng, log = _make_logged(_team_compiled(aventurine=False, extra_nihility=2))
        _inject(eng, "1308", "XC_BOOST", {"all_dmg": 0.2})
        assert eng.pipeline.effective_stats(eng.state.actors["1308"])["dmg_bonus"].get(
            "all", 0.0) == pytest.approx(0.8, rel=1e-9), (
            "我方 The Abyss 0.6 + 注入 0.2 同池加算（1.8）")
        _prep_zone(eng, log)
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_ac(
            "skill", [_tm_tribbie(numinosity=True, ultZone=True),
                      {"path": "Nihility"}, {"path": "Nihility"}],
            cond={"nihilityTeammatesBuff": True}, extra_attacker={"dmg_boost": 0.2}))

        hand_ours = 1.6 * AC_ATK * Z * 1.24 * 1.3 * 1.8
        hand_theirs = 1.6 * AC_ATK * Z * 1.24 * 1.3 * 1.2 * 1.6
        assert ours == pytest.approx([hand_ours], rel=REL_TOL), "我方加算池 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方乘算池 vs 手算")
        bd = theirs["hits"][0]["breakdown"]
        assert bd["dmgBoostMulti"] == pytest.approx(1.2, rel=REL_TOL)
        assert bd["finalDmgMulti"] == pytest.approx(1.6, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(D7_RATIO, rel=REL_TOL), (
            "D7 非空池显形——差值恰为 (1.2×1.6)/1.8 = 16/15")


# ===========================================================================
# 矩阵④ 缇宝境界附加伤害段（after_being_hit 消费——86d1594 修复双盲验收）
# ===========================================================================

class TestZoneAdditional:
    """境界附加 oracle = 对方缇宝本人行动上的 Additional 段（对方不把队友附伤挂
    主 C——建模收敛在案）；我方 = after_being_hit 钩消费。单段公式同构 → 逐段
    三方全等；段数按各自口径钉死（T2）."""

    def test_tribbie_own_ult_chain(self, optimizer_driver):
        """缇宝本人终结技：本体 0.30×HP + 境界附加 0.12×HP（自己的攻击消费自己的
        境界——单敌 1 段）逐段三方全等."""
        eng, log = _make_logged(_team_compiled())
        _tribbie_skill(eng)
        log.clear()
        _tribbie_ult(eng)
        ours = [e["amount"] for e in log
                if e.get("reason") == "hit" and e.get("source") == "1403"]
        theirs = run_optimizer(optimizer_driver, _opt_tr("ult"))

        hand_main = 0.30 * TR_HP * TR_Z * 1.24 * 1.3
        assert ours == pytest.approx([hand_main, _zone_add_hand()], rel=REL_TOL), (
            "我方两段：终结技本体 + 境界附加（vs 手算）")
        assert [h["damage"] for h in theirs["hits"]] == pytest.approx(
            [hand_main, _zone_add_hand()], rel=REL_TOL), "对方两段 vs 手算"
        assert theirs["hits"][1]["damage_function"] == "Additional"
        assert ours == pytest.approx([h["damage"] for h in theirs["hits"]], rel=REL_TOL), (
            "逐段双方互对")

    def test_tribbie_own_ult_zone_only(self, optimizer_driver):
        """单开态（神启不施放）：缇宝本人链抗穿 1.0——附加段 84.473231 三方全等."""
        eng, log = _make_logged(_team_compiled())
        log.clear()
        _tribbie_ult(eng)
        ours = [e["amount"] for e in log
                if e.get("reason") == "hit" and e.get("source") == "1403"]
        theirs = run_optimizer(optimizer_driver,
                               _opt_tr("ult", numinosity=False, ult_zone=True))

        hand_main = 0.30 * TR_HP * TR_Z * 1.3
        assert ours == pytest.approx([hand_main, _zone_add_hand(numinosity=False)],
                                     rel=REL_TOL)
        assert [h["damage"] for h in theirs["hits"]] == pytest.approx(
            [hand_main, _zone_add_hand(numinosity=False)], rel=REL_TOL)
        assert ours == pytest.approx([h["damage"] for h in theirs["hits"]], rel=REL_TOL)

    def test_tribbie_fua_pair(self, optimizer_driver):
        """天赋 FUA（他方开大触发——砂金大招实打）：FUA 本体 0.18×HP + 境界附加
        （钩源 FUA 发 after_being_hit——86d1594 修复后直接验收件）——对方 fua
        行动 [FUA, Additional] 双段结构同构互对；砂金大招段/砂金 FUA 首段亦各
        触发 1 段境界附加（逐攻击逐段口径——段数 T2 钉死）."""
        eng, log = _make_logged(_team_compiled())
        _prep_zone(eng, log)
        st = eng.state.actors["1304"]
        st.current_energy = 110.0
        ult = next(a for a in eng.actions_by_actor["1304"] if a.action_id == "130403")
        assert eng._fire_ultimate(st, ult) is True
        fua = _tr_fua(log)
        adds = _zone_adds(log)
        theirs = run_optimizer(optimizer_driver, _opt_tr("fua"))

        hand_fua = 0.18 * TR_HP * TR_Z * 1.24 * 1.3
        assert [e["amount"] for e in fua] == pytest.approx([hand_fua], rel=REL_TOL), (
            "我方天赋 FUA 本体 vs 手算（砂金大招触发）")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_fua, rel=REL_TOL), (
            "对方 fua 段 vs 手算")
        assert fua[0]["amount"] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert len(adds) == 3, (
            "砂金大招段 + 砂金 FUA 首段 + 缇宝 FUA——逐攻击逐段各 1 段境界附加（T2 口径）")
        for e in adds:
            assert e["amount"] == pytest.approx(_zone_add_hand(), rel=REL_TOL)
        assert theirs["hits"][1]["damage"] == pytest.approx(_zone_add_hand(), rel=REL_TOL), (
            "对方 Additional 段同值——每段双盲")

    def test_acheron_skill_zone_fire(self, optimizer_driver):
        """86d1594 修复验收（行动层单发）：黄泉战技 1 敌 → 恰好 1 段境界附加 ==
        对方缇宝 Additional 段（修复前行动层本就发——本件钉单发口径）."""
        eng, log = _make_logged(_team_compiled())
        _prep_zone(eng, log)
        _cast(eng, "1308", "130802")
        adds = _zone_adds(log)
        theirs_tr = run_optimizer(optimizer_driver, _opt_tr("ult"))

        assert len(adds) == 1
        assert adds[0]["amount"] == pytest.approx(_zone_add_hand(), rel=REL_TOL)
        assert adds[0]["amount"] == pytest.approx(theirs_tr["hits"][1]["damage"], rel=REL_TOL)

    def test_acheron_ult_zone_fires(self, optimizer_driver):
        """86d1594 修复验收（钩源链全链）+ B-NEW④ 幻影闸实证：黄泉 13 段大招 →
        境界附加恰 5 段（雨斩①行动段/结爆×3 钩链/Core① 钩链各 seg0——T2 每
        发伤链=一次攻击口径；修复前幻影 7 段（返渡/Core 0 伤害结爆族）已灭，
        86d1594 前钩源段全灭）+ 天赋 FUA 后续 1 段——每段数值双盲."""
        eng, log = _make_logged(_team_compiled())
        _inject(eng, "1308", "XC_RES_PEN", {"res_pen": 0.2})
        _clean_knots(eng)
        _knots(eng, "e1", 9)
        _prep_zone(eng, log)
        _acheron_ult(eng)
        adds = _zone_adds(log)
        fua = _tr_fua(log)
        theirs_tr = run_optimizer(optimizer_driver, _opt_tr("ult"))

        assert len(adds) == 6, (
            "5 段（大招链：雨斩①/结爆×3/Core①）+ 1 段（缇宝天赋 FUA）；"
            "幻影结爆 0 伤害不再误触发（B-NEW④ 闸）")
        for e in adds:
            assert e["amount"] == pytest.approx(_zone_add_hand(), rel=REL_TOL)
            assert e["amount"] == pytest.approx(theirs_tr["hits"][1]["damage"], rel=REL_TOL), (
                "每段双盲")
        assert len(fua) == 1, "他方开大 → 天赋 FUA 一触（TR_FUA_SPENT 计数）"

    def test_blast_three_targets_zone(self, optimizer_driver):
        """B-NEW③ 修复实证（n²→n）：3 敌场黄泉战技 blast 中位 → 3 段境界附加
        各 0.12×HP（官方「每命中 1 个目标造成 1 次」逐段语义——修复前
        3 fires × 0.36 = n² 放大 3 倍）；黄泉本体主/相邻三段同钉."""
        eng, log = _make_logged(_team_compiled(enemies=_team_dummy(n=3)))
        _prep_zone(eng, log)
        _cast(eng, "1308", "130802", target="e2")
        adj1 = _hit_amounts(log, source="1308", target="e1")
        main = _hit_amounts(log, source="1308", target="e2")
        adj3 = _hit_amounts(log, source="1308", target="e3")
        adds = _zone_adds(log)
        theirs_tr = run_optimizer(optimizer_driver, _opt_tr("ult"))

        z = Z * 1.24 * 1.3
        assert main == pytest.approx([1.6 * AC_ATK * z], rel=REL_TOL), "主目标段 vs 手算"
        assert adj1 == pytest.approx([0.6 * AC_ATK * z], rel=REL_TOL), "相邻段① vs 手算"
        assert adj3 == pytest.approx([0.6 * AC_ATK * z], rel=REL_TOL), "相邻段② vs 手算"
        assert len(adds) == 3, "3 目标命中 → 3 段附加（每目标 1 段——修复后 n 口径）"
        for e in adds:
            assert e["amount"] == pytest.approx(_zone_add_hand(), rel=REL_TOL)
        assert sum(e["amount"] for e in adds) == pytest.approx(
            3 * _zone_add_hand(), rel=REL_TOL), (
            "附加总量 3×0.12×HP×区（修复前为 3×0.36=n²）")
        assert adds[0]["amount"] == pytest.approx(theirs_tr["hits"][1]["damage"], rel=REL_TOL), (
            "单段双盲")
