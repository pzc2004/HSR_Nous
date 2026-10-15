"""开拓者•存护 8003 模板端到端对轴（验收型批）：真模板 YAML → 编译 →
普攻/战技减伤+嘲讽/终结技双系/天赋护盾/灼热意志/强化普攻/行迹/星魂全链 → 手算全等.

口径常数：火主白值 atk 601.524、def 606.375、hp 1241.856、spd 95、crit 0.05/0.5、
max_energy 120；行迹小节点 atk_pct 0.18 / def_pct 0.35 / hp_pct 0.10（trace_stat_effects）。
有效面板：ATK = 601.524×1.18、DEF = 606.375×1.35、HP = 1241.856×1.10。
等级轨道：basic lv6（E5→lv7）、skill/ultimate/talent lv10（E3→lv12）。
假人 def 1000 → 防御区 0.5；火弱点 → 抗性区 1.0；未击破 0.9；期望暴击 1.025
→ Z = 0.5×0.9×1.025 = 0.46125。辅手 taunt 300（>存护 150）——嘲讽 A/B 断言用。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

TB_ATK = 601.524 * 1.18          # 白值 × (1+行迹 atk_pct 0.18) = 709.79832
TB_DEF = 606.375 * 1.35          # 白值 × (1+行迹 def_pct 0.35) = 818.60625
TB_HP = 1241.856 * 1.10          # 白值 × (1+行迹 hp_pct 0.10) = 1366.0416
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)  # 防御区×未击破×期望暴击 = 0.46125

SHIELD_LV10 = 0.06 * TB_DEF + 80          # 天赋盾 lv10 = 129.116375
E2_SHIELD = 0.02 * TB_DEF + 27            # E2 追加 = 43.372125
TECH_SHIELD = 0.3 * TB_DEF + 384          # 秘技盾 = 629.581875


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "8003", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100,
                        "taunt": 300},   # 高于存护 150——无嘲讽时敌方必选辅手（A/B 对照）
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "8003", "technique": "800307"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["fire"]}],
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


def _tb(eng):
    return eng.state.actors["8003"]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or (st if a.target_type == "self" else eng.state.actors["e1"])
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    st = _tb(eng)
    st.current_energy = 120.0
    ult = next(a for a in eng.actions_by_actor["8003"] if a.action_id == "800303")
    assert eng._fire_ultimate(st, ult) is True


def _hit_tb(eng, source="e1"):
    eng.bus.emit("after_being_hit", {
        "target": "8003", "source": source, "amount": 100.0,
        "action_type": "basic", "damage_type": "fire"}, eng.state)


def _pool(eng, aid):
    return sum(s.remaining for s in eng.state.actors[aid].shields if s.pool == "FTB_SHIELD")


class TestTrailblazerCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["8003"]}
        assert set(acts) == {"800301", "800302", "800303", "800308"}
        assert acts["800303"].energy_cost == 120
        decls = compiled.resource_decls_by_actor["8003"]
        assert decls["magma_will"]["max"] == 8

    def test_trace_panel(self, compiled):
        """行迹小节点聚合：ATK×1.18 / DEF×1.35 / HP×1.10（勘正③实证）."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_tb(eng))
        assert math.isclose(eff["atk"], TB_ATK, rel_tol=1e-9)
        assert math.isclose(eff["def_"], TB_DEF, rel_tol=1e-9)
        assert math.isclose(eff["hp"], TB_HP, rel_tol=1e-9)


class TestBasic:
    def test_damage_energy_sp_toughness(self, compiled):
        """普攻 lv6=100% ATK：伤害 1.0×ATK×Z；回能 20；SP+1；削韧 10；灼热意志+1."""
        eng = _make(compiled)
        st, e1 = _tb(eng), eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "8003", "800301")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * TB_ATK * Z, rel_tol=1e-9)
        assert math.isclose(e1.toughness, 9999 - 10)
        assert math.isclose(eng.state.skill_points, 4.0)
        assert math.isclose(st.current_energy, 20.0)
        assert math.isclose(st.resources["magma_will"], 1.0), "施放普攻 +1 层（800301 文本）"

    def test_talent_shield_and_accumulate(self, compiled):
        """天赋：施放后全体护盾 6%DEF+80（lv10，param 随档）；二次施放同池叠算."""
        eng = _make(compiled)
        _cast(eng, "8003", "800301")
        for aid in ("8003", "ally"):
            assert math.isclose(_pool(eng, aid), SHIELD_LV10, rel_tol=1e-9), f"{aid} 盾量"
            mod = eng.state.actors[aid].modifiers["FTB_TALENT_SHIELD"]
            assert mod.duration == 2 and mod.stacks == 1
        _cast(eng, "8003", "800301")
        assert math.isclose(_pool(eng, "8003"), 2 * SHIELD_LV10, rel_tol=1e-9), (
            "accumulate 同池加算（叠算模型待实测在案）")


class TestSkill:
    def test_cost_energy_and_charge(self, compiled):
        """战技：SP-1、回能 30、灼热意志+1（800302 文本「并叠加1层」）."""
        eng = _make(compiled)
        st = _tb(eng)
        _cast(eng, "8003", "800302")
        assert math.isclose(eng.state.skill_points, 2.0)
        assert math.isclose(st.current_energy, 30.0)
        assert math.isclose(st.resources["magma_will"], 1.0)

    def test_dmg_reduction_and_trace(self, compiled):
        """自体减伤 50%（lv10 param）+ 大行迹全体 15%：火主乘算折叠 0.575、辅手 0.15."""
        eng = _make(compiled)
        _cast(eng, "8003", "800302")
        red_self = eng.pipeline.effective_stats(_tb(eng))["dmg_bonus"]["dmg_reduction"]
        assert math.isclose(red_self, 1 - (1 - 0.5) * (1 - 0.15), rel_tol=1e-9), (
            "0.5 与 0.15 乘算折叠（dmg_dmg_reduction 同口径）")
        red_ally = eng.pipeline.effective_stats(eng.state.actors["ally"])["dmg_bonus"]["dmg_reduction"]
        assert math.isclose(red_ally, 0.15, rel_tol=1e-9), "8003101 全体减伤 15% 一回合"
        assert eng.state.actors["ally"].modifiers["STRONG_DEFEND_WEAK"].duration == 1

    def test_forced_taunt(self, compiled):
        """嘲讽 forced_taunt 收编实证：施放前敌方按权重选辅手（300>150）；
        施放后 e1/e2 均强制攻击火主."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        assert eng._pick_ally_target(eng.state.actors["e1"]) is ally, "施放前权重选辅手"
        _cast(eng, "8003", "800302")
        for eid in ("e1", "e2"):
            enemy = eng.state.actors[eid]
            assert "AMBER_TAUNT" in enemy.modifiers
            assert enemy.modifiers["AMBER_TAUNT"].duration == 1
            assert eng._pick_ally_target(enemy) is _tb(eng), f"{eid} 强制嘲讽打火主"


class TestUltimate:
    def test_aoe_damage_energy_mark(self, compiled):
        """终结技 lv10：全体 (100%ATK + 150%DEF)×Z；削韧 20；能量 120→返 5；免耗标记挂上."""
        eng = _make(compiled)
        st = _tb(eng)
        hps = {eid: eng.state.actors[eid].current_hp for eid in ("e1", "e2")}
        _ult(eng)
        want = (1.0 * TB_ATK + 1.5 * TB_DEF) * Z
        for eid in ("e1", "e2"):
            e = eng.state.actors[eid]
            assert math.isclose(hps[eid] - e.current_hp, want, rel_tol=1e-9), f"{eid} 双系倍率"
            assert math.isclose(e.toughness, 9999 - 20)
        assert math.isclose(st.current_energy, 5.0), "满 120 消耗后返还 5"
        assert "ULT_FREE_ENHANCED" in st.modifiers
        assert math.isclose(_pool(eng, "ally"), SHIELD_LV10, rel_tol=1e-9), (
            "终结技同触发天赋盾（EN uses Ultimate 在域）")

    def test_mark_enhances_without_cost(self, compiled):
        """免耗标记：0 层也可强化普攻——不耗层 + 摘除标记 + 800301 入口互斥."""
        eng = _make(compiled)
        st = _tb(eng)
        basic = next(a for a in eng.actions_by_actor["8003"] if a.action_id == "800301")
        enh = next(a for a in eng.actions_by_actor["8003"] if a.action_id == "800308")
        assert eng._available_if_ok(st, basic) and not eng._available_if_ok(st, enh), "0 层初始态"
        _ult(eng)
        assert not eng._available_if_ok(st, basic) and eng._available_if_ok(st, enh), (
            "标记在身 → 入口互换")
        assert math.isclose(st.resources["magma_will"], 0.0)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        st.current_hp = 500.0
        _cast(eng, "8003", "800308")
        assert math.isclose(hp1 - e1.current_hp, 1.35 * TB_ATK * Z, rel_tol=1e-9), (
            "强化普攻 lv6 主段 135%")
        assert math.isclose(st.resources["magma_will"], 0.0), "免耗标记 → 不扣 4 层"
        assert "ULT_FREE_ENHANCED" not in st.modifiers, "一次性标记摘除"
        assert math.isclose(st.current_hp, 500.0 + 0.05 * TB_HP, rel_tol=1e-9), (
            "8003102 强化普攻后自回 5% 最大生命")


class TestEnhancedBasic:
    def test_blast_cost_and_toughness(self, compiled):
        """≥4 层强化普攻：主 135%/相邻 54%（lv6 双表）；耗 4 层；削韧 20+10；回能 30 产点."""
        eng = _make(compiled)
        st, e1, e2 = _tb(eng), eng.state.actors["e1"], eng.state.actors["e2"]
        st.resources["magma_will"] = 4.0
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8003", "800308")
        assert math.isclose(hp1 - e1.current_hp, 1.35 * TB_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.54 * TB_ATK * Z, rel_tol=1e-9), (
            "scaling_blast 相邻档 54%")
        assert math.isclose(st.resources["magma_will"], 0.0), "耗 4 层"
        assert math.isclose(e1.toughness, 9999 - 20)
        assert math.isclose(e2.toughness, 9999 - 10), "toughness_dmg_blast 相邻 10"
        assert math.isclose(st.current_energy, 30.0)
        assert math.isclose(eng.state.skill_points, 4.0)

    def test_enhance_gate(self, compiled):
        """灼热意志 ≥4 → 入口互换（available_if 双声明）."""
        eng = _make(compiled)
        st = _tb(eng)
        basic = next(a for a in eng.actions_by_actor["8003"] if a.action_id == "800301")
        enh = next(a for a in eng.actions_by_actor["8003"] if a.action_id == "800308")
        st.resources["magma_will"] = 4.0
        assert not eng._available_if_ok(st, basic) and eng._available_if_ok(st, enh)


class TestTalentCharge:
    def test_hit_charge_and_cap(self, compiled):
        """受击充能：火主被击中 +1 层；辅手受击不计；上限 8."""
        eng = _make(compiled)
        st = _tb(eng)
        _hit_tb(eng)
        _hit_tb(eng)
        assert math.isclose(st.resources["magma_will"], 2.0)
        eng.bus.emit("after_being_hit", {
            "target": "ally", "source": "e1", "amount": 100.0,
            "action_type": "basic", "damage_type": "fire"}, eng.state)
        assert math.isclose(st.resources["magma_will"], 2.0), "辅手受击不充能"
        st.resources["magma_will"] = 8.0
        _hit_tb(eng)
        assert math.isclose(st.resources["magma_will"], 8.0), "上限 8（资源 max 承担）"


class TestTechnique:
    def test_pre_battle_shield(self):
        """秘技 800307：进战火主自体护盾 30%DEF+384（辅手无）."""
        eng = _make(_compiled(pre_battle=True))
        assert math.isclose(_tb(eng).shields[0].remaining, TECH_SHIELD, rel_tol=1e-9)
        assert not eng.state.actors["ally"].shields, "秘技盾只给自身"


class TestEidolons:
    def test_e1_additional_damage(self):
        """E1：普攻追加 25%DEF、强化普攻追加 50%DEF（category additional——同 Z 乘区）."""
        eng = _make(_compiled(eidolon=1))
        st, e1 = _tb(eng), eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "8003", "800301")
        assert math.isclose(hp1 - e1.current_hp,
                            (1.0 * TB_ATK + 0.25 * TB_DEF) * Z, rel_tol=1e-9)
        st.resources["magma_will"] = 4.0
        hp1 = e1.current_hp
        _cast(eng, "8003", "800308")
        assert math.isclose(hp1 - e1.current_hp,
                            (1.35 * TB_ATK + 0.5 * TB_DEF) * Z, rel_tol=1e-9)

    def test_e2_shield_pool(self):
        """E2：天赋盾同池追加 2%DEF+27（合计 129.116375+43.372125）."""
        eng = _make(_compiled(eidolon=2))
        _cast(eng, "8003", "800301")
        for aid in ("8003", "ally"):
            assert math.isclose(_pool(eng, aid), SHIELD_LV10 + E2_SHIELD, rel_tol=1e-9), (
                f"{aid} 同池加算")

    def test_e3_levels(self):
        """E3 战技/天赋+2：减伤 lv12=52%、天赋盾 lv12=6.4%DEF+89（param 随档实证）."""
        eng = _make(_compiled(eidolon=3))
        _cast(eng, "8003", "800302")
        red = eng.pipeline.effective_stats(_tb(eng))["dmg_bonus"]["dmg_reduction"]
        assert math.isclose(red, 1 - (1 - 0.52) * (1 - 0.15), rel_tol=1e-9)
        assert math.isclose(_pool(eng, "ally"),
                            (0.064 * TB_DEF + 89) + E2_SHIELD, rel_tol=1e-9), (
            "eidolon=3 含 E2 同池追加")

    def test_e4_battle_start_charge(self):
        """E4：进战即 4 层灼热意志（开局可强化普攻）."""
        eng = _make(_compiled(eidolon=4))
        st = _tb(eng)
        assert math.isclose(st.resources["magma_will"], 4.0)
        enh = next(a for a in eng.actions_by_actor["8003"] if a.action_id == "800308")
        assert eng._available_if_ok(st, enh)

    def test_e5_levels(self):
        """E5 终结技+2/普攻+1：大招 lv12=(110%ATK+165%DEF)×Z；普攻 lv7=110%（含 E1 追加）."""
        eng = _make(_compiled(eidolon=5))
        st, e1 = _tb(eng), eng.state.actors["e1"]
        hps = {eid: eng.state.actors[eid].current_hp for eid in ("e1", "e2")}
        _ult(eng)
        want = (1.1 * TB_ATK + 1.65 * TB_DEF) * Z
        for eid in ("e1", "e2"):
            assert math.isclose(hps[eid] - eng.state.actors[eid].current_hp, want, rel_tol=1e-9)
        st.resources["magma_will"] = 0.0   # 撤 E4 充能 + 摘标记走普通普攻
        if "ULT_FREE_ENHANCED" in st.modifiers:
            eng._remove_modifier(st, "ULT_FREE_ENHANCED", "test")
        hp1 = e1.current_hp
        _cast(eng, "8003", "800301")
        assert math.isclose(hp1 - e1.current_hp,
                            (1.1 * TB_ATK + 0.25 * TB_DEF) * Z, rel_tol=1e-9), (
            "普攻 lv7=110% + E1 追加 25%DEF")

    def test_e6_stacking_def(self):
        """E6：强化普攻/终结技后 DEF+10%×≤3——stat_exprs 活读层数（勘正⑥实证）."""
        eng = _make(_compiled(eidolon=6))
        st = _tb(eng)
        for want_stacks in (1, 2, 3):
            st.resources["magma_will"] = 4.0
            _cast(eng, "8003", "800308")
            assert math.isclose(st.modifiers["E6_CITY_FORGING"].stacks, want_stacks)
            assert math.isclose(eng.pipeline.effective_stats(st)["def_"],
                                606.375 * (1 + 0.35 + 0.1 * want_stacks), rel_tol=1e-9), (
                f"{want_stacks} 层 → DEF 白值×(1+0.35+0.1×{want_stacks})")
        st.resources["magma_will"] = 4.0
        _cast(eng, "8003", "800308")
        assert math.isclose(st.modifiers["E6_CITY_FORGING"].stacks, 3.0), "至多 3 层"
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"],
                            606.375 * 1.65, rel_tol=1e-9)
