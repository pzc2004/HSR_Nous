"""翡翠 1314 模板端到端对轴（验收型批·单轨现役）：真模板 YAML → 编译 →
收债人全件/充能-追击-当品链/终结技强化/行迹/秘技/星魂全链 → 手算全等.

口径常数：翡翠 atk 659.736、行迹 atk_pct 0.18 + 量子增伤 0.224（元素桶）、
crit 0.05/0.5（每层当品 +0.024 暴伤 +0.005 atk_pct——lv10 param(131404,1)）。
假人 def 1000 → 防御区 (80×10+200)/(1000+1000)=0.5；量子弱点 → 抗性区 1.0；
未击破 0.9；期望暴击区 = 1+0.05×crit_dmg（rate<1）。双假人 → 开局逆回购① +2 当品
（基准 mortgage=2：atk=659.736×1.19=785.08584，crit_dmg=0.548，期望暴击区 1.0274）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK0 = 659.736
TRACE_ATK_PCT = 0.18          # 行迹攻击小节点 ×3
TRACE_QUANTUM = 0.224         # 行迹量子增伤小节点 ×5（dmg_quantum 元素桶）
GOODS_CRIT = 0.024            # 当品每层暴伤（lv10 param(131404,1)）
GOODS_ATK = 0.005             # 绝当品每层 atk_pct（行迹 1314103 #1）


def _atk(mortgage: float) -> float:
    return ATK0 * (1 + TRACE_ATK_PCT + GOODS_ATK * mortgage)


def _crit_zone(mortgage: float, *, talent_lv12: bool = False, e2: bool = False) -> float:
    per_stack = 0.0264 if talent_lv12 else GOODS_CRIT
    crit_dmg = 0.5 + per_stack * mortgage
    rate = 0.05 + (0.18 if e2 else 0.0)
    return min(1.0, rate) * (1 + crit_dmg) + (1 - min(1.0, rate))


#: 直伤乘区合（不含暴击）：增伤 1.224 × 防御 × 抗性 × 未击破 0.9
def _zones(*, def_pen: float = 0.0, res_pen: float = 0.0) -> float:
    def_multi = (80 * 10 + 200) / (1000 * (1 - def_pen) + 80 * 10 + 200)
    res_multi = 1 - max(-1.0, min(0.0 - res_pen, 0.9))
    return (1 + TRACE_QUANTUM) * def_multi * res_multi * 0.9


ALLY_Z = 1.0 * 0.5 * 1.0 * 0.9 * (1 + 0.05 * 0.5)   # 辅手（无量子行迹）：1500 攻量子伤


def _build(*, eidolon: int = 0, pre_battle: bool = False, initial_sp: int = 3):
    member = {"character_template": "1314", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "quantum",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10,
                      "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1314", "technique": "131407"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["quantum"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["quantum"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _jade(eng):
    return eng.state.actors["1314"]


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    st = _jade(eng)
    st.current_energy = 140.0
    ult = next(a for a in eng.actions_by_actor["1314"] if a.action_id == "131403")
    assert eng._fire_ultimate(st, ult) is True


def _sign(eng, target=None):
    """战技签约：默认挂辅手（收债人）."""
    _cast(eng, "1314", "131402", target=target or eng.state.actors["ally"])


class TestJadeCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1314"]}
        assert set(acts) == {"131401", "131402", "131403", "131404"}
        assert acts["131402"].target_type == "ally_single", "战技=我方单体（过堂⑱）"
        assert acts["131402"].available_if, "收债人在场战技硬闸"
        assert acts["131402"].skill_point_cost == 1 and acts["131402"].energy_gain == 30
        assert acts["131403"].energy_cost == 140
        assert acts["131403"].scaling[9] == {"atk": 2.4}, "终结技 scaling=第 3 列 lv10（过堂①）"
        assert acts["131404"].action_type == "follow_up"
        assert acts["131404"].level_key == "talent", "天赋追击走天赋轨道（过堂⑲）"
        assert acts["131404"].scaling[9] == {"atk": 1.2}, "天赋 scaling=第 5 列 lv10（过堂①）"
        decls = compiled.resource_decls_by_actor["1314"]
        assert {"_charge", "_mortgage", "_ult_stacks", "_debtor_on_field",
                "_debtor_turns", "_in_fua"} <= set(decls)
        assert decls["_mortgage"]["max"] == 50


class TestTracesBattleStart:
    def test_trace_stats_and_goods_live(self, compiled):
        """行迹小节点（trace_stat_effects 收编）+ 当品 stat_exprs 现场读（过堂③④）."""
        eng = _make(compiled)
        st = _jade(eng)
        assert math.isclose(st.resources["_mortgage"], 2.0), "逆回购①：双假人入战 +2 当品"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], _atk(2), rel_tol=1e-9), "行迹 18%+当品 2×0.5%"
        assert math.isclose(eff["crit_dmg"], 0.5 + GOODS_CRIT * 2, rel_tol=1e-9)
        assert math.isclose(eff["effect_res"], 0.1, rel_tol=1e-9), "行迹效果抵抗小节点"
        assert math.isclose(eff["dmg_bonus"].get("quantum", 0.0), TRACE_QUANTUM, rel_tol=1e-9)
        st.resources["_mortgage"] = 40.0
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], _atk(40), rel_tol=1e-9), "stat_exprs 现场重估非烘焙"
        assert math.isclose(eff["crit_dmg"], 0.5 + GOODS_CRIT * 40, rel_tol=1e-9)

    def test_battle_start_advance(self, compiled):
        """折牙票：战斗开始行动提前 50%（剩余距离 10000→5000）."""
        eng = _make(compiled)
        assert math.isclose(_remaining(eng, "1314"), 5000.0, rel_tol=1e-9)


class TestSkillDebtor:
    def test_sign_spd_latch_and_lock(self, compiled):
        """战技：耗 1 点回 30 能；收债人 +30 SPD（固定值）；闩到位 → 战技硬闸."""
        eng = _make(compiled)
        st, ally = _jade(eng), eng.state.actors["ally"]
        _sign(eng)
        assert math.isclose(eng.state.skill_points, 2.0), "战技耗 1 点"
        assert math.isclose(st.current_energy, 30.0), "战技回能 30（tbgd）"
        assert "JADE_DEBTOR" in ally.modifiers
        assert math.isclose(eng.pipeline.effective_stats(ally)["spd"], 120.0, rel_tol=1e-9), (
            "90+30 固定值")
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 103.0, rel_tol=1e-9), (
            "翡翠不加速")
        assert "JADE_DEBTOR" not in st.modifiers, "E0 指定他人时翡翠无收债人"
        assert math.isclose(st.resources["_debtor_on_field"], 1.0)
        assert math.isclose(st.resources["_debtor_turns"], 3.0)
        skill = next(a for a in eng.actions_by_actor["1314"] if a.action_id == "131402")
        assert eng._legal_with_available_if(st, [skill]) == [], "场上存在收债人时无法施放战技"

    def test_debtor_attack_chain(self, compiled):
        """收债人攻击：逐击附加伤害（翡翠 ATK×0.25，additional 正籍）+ 烧血 2% + 充能 +1."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _sign(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        fuju = _atk(2) * 0.25 * _zones() * _crit_zone(2)
        assert math.isclose(hp1 - e1.current_hp, 1500 * ALLY_Z + fuju, rel_tol=1e-9), (
            "辅手普攻 + 附加伤害 lv10=0.25")
        assert math.isclose(ally.current_hp, 3000 - 0.02 * 3000, rel_tol=1e-9), (
            "烧血 2% 最大生命")
        assert math.isclose(_jade(eng).resources["_charge"], 1.0), "每击中 1 名 +1 充能"

    def test_debtor_countdown(self, compiled):
        """收债人计时：翡翠 3 回合开始走字（source_turn_start 精确锚）→ 摘闩 → 战技解禁."""
        eng = _make(compiled)
        st, ally = _jade(eng), eng.state.actors["ally"]
        _sign(eng)
        for i, left in enumerate((2, 1), start=1):
            eng.bus.emit("on_turn_start", {"actor": "1314"}, eng.state)
            eng._tick_source_modifiers(st.actor, "source_turn_start")
            assert math.isclose(st.resources["_debtor_turns"], float(left))
            assert math.isclose(ally.modifiers["JADE_DEBTOR"].duration, float(left))
        eng.bus.emit("on_turn_start", {"actor": "1314"}, eng.state)
        eng._tick_source_modifiers(st.actor, "source_turn_start")
        assert math.isclose(st.resources["_debtor_on_field"], 0.0), "3 翡翠回合后摘闩"
        assert "JADE_DEBTOR" not in ally.modifiers, "modifier 同刻到期"
        skill = next(a for a in eng.actions_by_actor["1314"] if a.action_id == "131402")
        assert eng._legal_with_available_if(st, [skill]), "战技解禁"


class TestTalentFuaChain:
    def test_fua_fire_mortgage_energy_toughness(self, compiled):
        """充能 7+1 → 剔烁之牙：全体 1.2×ATK + 5 层当品 + 回能 10 + 削韧 10 + 充能清零."""
        eng = _make(compiled)
        st = _jade(eng)
        _sign(eng)
        st.resources["_charge"] = 7.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "ally", "ally_basic")
        fua = _atk(2) * 1.2 * _zones() * _crit_zone(2)
        fuju = _atk(2) * 0.25 * _zones() * _crit_zone(2)
        assert math.isclose(hp2 - e2.current_hp, fua, rel_tol=1e-9), "e2 只吃追击"
        assert math.isclose(hp1 - e1.current_hp, 1500 * ALLY_Z + fuju + fua, rel_tol=1e-9)
        assert math.isclose(st.resources["_charge"], 0.0), "7+1-8=0（族谱#9 现场新值口径）"
        assert math.isclose(st.resources["_mortgage"], 2.0 + 5.0), "追击 +5 层当品"
        assert math.isclose(st.current_energy, 30.0 + 10.0), "战技 30 + 追击回能 10（hook 补记）"
        assert math.isclose(e1.toughness, 100 - 10 - 10), "普攻 10 + 追击 10"
        assert math.isclose(e2.toughness, 100 - 10)

    def test_ult_arms_enhanced_fua(self, compiled):
        """终结技：全体 2.4×ATK（scaling 第 3 列勘正实证）+ 武装 2 次强化；
        强化追击倍率 1.2+0.8=2.0（倍率区加算）、削韧 20、次数扣 1."""
        eng = _make(compiled)
        st = _jade(eng)
        _sign(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        aoe = _atk(2) * 2.4 * _zones() * _crit_zone(2)
        assert math.isclose(hp1 - e1.current_hp, aoe, rel_tol=1e-9), "终结技 lv10=2.4（过堂①）"
        assert math.isclose(hp2 - e2.current_hp, aoe, rel_tol=1e-9)
        assert math.isclose(st.resources["_ult_stacks"], 2.0), "强化 2 次"
        assert math.isclose(st.current_energy, 5.0), "终结技回能 5"
        st.resources["_charge"] = 7.0
        hp2 = e2.current_hp
        _cast(eng, "ally", "ally_basic")
        enhanced = _atk(2) * (1.2 + 0.8) * _zones() * _crit_zone(2)
        assert math.isclose(hp2 - e2.current_hp, enhanced, rel_tol=1e-9), "强化追击 2.0 倍率"
        assert math.isclose(e2.toughness, 100 - 20 - 20, rel_tol=1e-9), (
            "终结技 20 + 强化追击 20（米游社'强化后削韧 20'收编）")
        assert math.isclose(st.resources["_ult_stacks"], 1.0), "次数扣 1（并钩幂等）"


class TestSelfCast:
    def test_self_debtor_no_spd_double_charge(self, compiled):
        """自任收债人：无 SPD+30（官方明示）+ 不烧血 + 双倍叠层（社区证据逐击 +1）+
        附加伤害同触发（翡翠也是收债人）."""
        eng = _make(compiled)
        st = _jade(eng)
        _sign(eng, target=st)
        assert "JADE_DEBTOR" in st.modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 103.0, rel_tol=1e-9), (
            "自任收债人无法获得速度提高（过堂⑮）")
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1314", "131401")
        main = _atk(2) * 0.9 * _zones() * _crit_zone(2)
        blast = _atk(2) * 0.3 * _zones() * _crit_zone(2)
        fuju = _atk(2) * 0.25 * _zones() * _crit_zone(2)
        assert math.isclose(hp1 - e1.current_hp, main + fuju, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, blast + fuju, rel_tol=1e-9), (
            "翡翠为收债人→自身命中也带附加伤害")
        assert math.isclose(st.resources["_charge"], 4.0), "2 命中 ×（1+自任双倍 1）"
        assert math.isclose(st.current_hp, st.actor.stats.hp, rel_tol=1e-9), "翡翠不烧血"


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技：进战 AoE 0.5×ATK（伤害时当品 0——装填序：先伤后得）+ 15 层当品（+开局 2）."""
        eng = _make(_compiled(pre_battle=True))
        st = _jade(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        tech = (ATK0 * (1 + TRACE_ATK_PCT)) * 0.5 * _zones() * (1 + 0.05 * 0.5)
        assert math.isclose(1e9 - e1.current_hp, tech, rel_tol=1e-9)
        assert math.isclose(1e9 - e2.current_hp, tech, rel_tol=1e-9)
        assert math.isclose(st.resources["_mortgage"], 15.0 + 2.0), "秘技 15 + 逆回购① 2"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], _atk(17), rel_tol=1e-9), "17 层当品 ATK 现场档"
        assert math.isclose(eff["crit_dmg"], 0.5 + GOODS_CRIT * 17, rel_tol=1e-9)

    def test_technique_not_fua_for_e1(self):
        """秘技进战伤害非天赋追击——E1 真伤段不追加（_in_fua 闩实证，过堂⑳）."""
        eng = _make(_compiled(eidolon=1, pre_battle=True))
        e1 = eng.state.actors["e1"]
        tech = (ATK0 * (1 + TRACE_ATK_PCT)) * 0.5 * _zones() * (1 + 0.05 * 0.5)
        assert math.isclose(1e9 - e1.current_hp, tech, rel_tol=1e-9), "无 ×1.32 真伤段"


class TestEidolons:
    def test_e1_true_segment(self):
        """E1：天赋追击 +32%（追加真伤段等值——遐蝶同构；闩内命中才追加）."""
        eng = _make(_compiled(eidolon=1))
        st = _jade(eng)
        _sign(eng)
        st.resources["_charge"] = 7.0
        e2 = eng.state.actors["e2"]
        hp2 = e2.current_hp
        _cast(eng, "ally", "ally_basic")
        fua = _atk(2) * 1.2 * _zones() * _crit_zone(2)
        assert math.isclose(hp2 - e2.current_hp, fua * 1.32, rel_tol=1e-9), "追击×1.32 等值"

    def test_e2_crit_rate_gate(self):
        """E2：当品 ≥15 → 暴击率 +18%（enable_if 门控——14 层不启、15 层启）."""
        eng = _make(_compiled(eidolon=2))
        st = _jade(eng)
        st.resources["_mortgage"] = 14.0
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.05, rel_tol=1e-9)
        st.resources["_mortgage"] = 15.0
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.23, rel_tol=1e-9)

    def test_e3_skill_talent_lv12(self):
        """E3（联动 E1E2）：战技 lv12 → 附加伤害 0.27；天赋 lv12 → 每层暴伤 0.0264."""
        eng = _make(_compiled(eidolon=3))
        _sign(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        fuju = _atk(2) * 0.27 * _zones() * _crit_zone(2, talent_lv12=True)
        assert math.isclose(hp1 - e1.current_hp, 1500 * ALLY_Z + fuju, rel_tol=1e-9), (
            "E3 战技 lv12 附加伤害 0.27")

    def test_e4_def_pen(self):
        """E4：终结技后无视 12% 防御 3 回合（def_pen 收编）；当次终结技仍走 0.5 防御区
        （挂载点后行在案）→ 强化追击换防御区 1000/1880."""
        eng = _make(_compiled(eidolon=4))
        st = _jade(eng)
        _sign(eng)
        e2 = eng.state.actors["e2"]
        hp2 = e2.current_hp
        _ult(eng)
        aoe = _atk(2) * 2.4 * _zones() * _crit_zone(2, talent_lv12=True)
        assert math.isclose(hp2 - e2.current_hp, aoe, rel_tol=1e-9), "当次终结技不自吃（在案）"
        assert "E4_DEF_PEN" in st.modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["def_pen"], 0.12, rel_tol=1e-9)
        st.resources["_charge"] = 7.0
        hp2 = e2.current_hp
        _cast(eng, "ally", "ally_basic")
        enhanced = (_atk(2) * (1.32 + 0.8) * _zones(def_pen=0.12)
                    * _crit_zone(2, talent_lv12=True))
        assert math.isclose(hp2 - e2.current_hp, enhanced * 1.32, rel_tol=1e-9), (
            "强化追击吃 12% 无视防御（E3 天赋 lv12=1.32 + 强化 0.8 + E1×1.32 联动）")

    def test_e5_ult_basic_lv_up(self):
        """E5（联动 E1..E4）：普攻 lv7（主 0.99/邻 0.33）+ 终结技 lv12（2.64）+
        强化追击 1.32+0.88=2.20 换防御区 + E1 真伤."""
        eng = _make(_compiled(eidolon=5))
        st = _jade(eng)
        _sign(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1314", "131401")
        main = _atk(2) * 0.99 * _zones() * _crit_zone(2, talent_lv12=True)
        blast = _atk(2) * 0.33 * _zones() * _crit_zone(2, talent_lv12=True)
        assert math.isclose(hp1 - e1.current_hp, main, rel_tol=1e-9), "普攻 lv7 主 0.99"
        assert math.isclose(hp2 - e2.current_hp, blast, rel_tol=1e-9), "普攻 lv7 邻 0.33"
        hp2 = e2.current_hp
        _ult(eng)
        aoe = _atk(2) * 2.64 * _zones() * _crit_zone(2, talent_lv12=True)
        assert math.isclose(hp2 - e2.current_hp, aoe, rel_tol=1e-9), "终结技 lv12=2.64"
        st.resources["_charge"] = 7.0
        hp2 = e2.current_hp
        _cast(eng, "ally", "ally_basic")
        enhanced = (_atk(2) * (1.32 + 0.88) * _zones(def_pen=0.12)
                    * _crit_zone(2, talent_lv12=True))
        assert math.isclose(hp2 - e2.current_hp, enhanced * 1.32, rel_tol=1e-9), (
            "E5 强化追击 2.20 + E1×1.32 + E4 防御区")

    def test_e6_res_pen_and_self_debtor(self):
        """E6（联动全链）：收债人在场 → 翡翠抗穿 +20%（门控）+ 翡翠同获收债人（无 spd 形）；
        自任双倍叠层 + 附加伤害同盖 + 抗穿区 1.2."""
        eng = _make(_compiled(eidolon=6))
        st, ally = _jade(eng), eng.state.actors["ally"]
        _sign(eng)
        assert "JADE_DEBTOR" in st.modifiers and "JADE_DEBTOR" in ally.modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 103.0, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["spd"], 120.0, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.2, rel_tol=1e-9), (
            "场上存在收债人→抗穿 +20%")
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1314", "131401")
        main = _atk(2) * 0.99 * _zones(res_pen=0.2) * _crit_zone(2, talent_lv12=True)
        blast = _atk(2) * 0.33 * _zones(res_pen=0.2) * _crit_zone(2, talent_lv12=True)
        fuju = _atk(2) * 0.27 * _zones(res_pen=0.2) * _crit_zone(2, talent_lv12=True)
        assert math.isclose(hp1 - e1.current_hp, main + fuju, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, blast + fuju, rel_tol=1e-9)
        assert math.isclose(st.resources["_charge"], 4.0), "E6 自任双倍叠层（2 命中 ×2）"
