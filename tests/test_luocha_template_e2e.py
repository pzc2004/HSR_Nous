"""罗刹 1203 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 战技三段/
被动等效/终结技驱散/结界回复双段/行迹/星魂全链 → 手算全等.

过堂四件（fixture 头注同录）：ally_single / E2 scoped 时序勘正 /
E4 all_dmg 负值 / E6 待收。

口径常数：罗刹白值 atk 756.756、crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 →
防御区 0.5、虚数弱点 → 抗性区 1.0、未击破 0.9。战技治疗 lv10 = 0.60×756.756+800
= 1254.05；结界回复 = 0.18×756.756+240 = 376.22；A2 = 0.07×756.756+93 = 145.97。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

LC_ATK = 756.756
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
SKILL_HEAL = 0.60 * LC_ATK + 800.0
ZONE_HEAL = 0.18 * LC_ATK + 240.0
A2_HEAL = 0.07 * LC_ATK + 93.0


def _build(*, eidolon: int = 0):
    member = {"character_template": "1203", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "imaginary",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _lc(eng):
    return eng.state.actors["1203"]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["ally"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


class TestLuochaCompile:
    def test_ally_single_resource_trace(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1203"]}
        assert acts["120302"].target_type == "ally_single"
        assert compiled.resource_decls_by_actor["1203"]["_abyss_flower"]["max"] == 2
        eng = _make(compiled)
        assert math.isclose(eng.pipeline.effective_stats(_lc(eng))["effect_res"], 0.7), (
            "A3 渡厄 70%（trace_stat_effects 通道）")


class TestSkillAndZone:
    def test_skill_heal_cleanse_flower(self, compiled):
        """战技：治疗 1254.05 + A1 驱散 LIFO + 1 层深渊之花."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 1500.0
        eng._apply_modifier(ally, Modifier(
            modifier_id="D1", name="旧负面", modifier_type="debuff", duration=2))
        eng._apply_modifier(ally, Modifier(
            modifier_id="D2", name="新负面", modifier_type="debuff", duration=2))
        _cast(eng, "1203", "120302", target=ally)
        assert math.isclose(ally.current_hp, 1500.0 + SKILL_HEAL, rel_tol=1e-9)
        assert "D2" not in ally.modifiers and "D1" in ally.modifiers
        assert math.isclose(_lc(eng).resources["_abyss_flower"], 1.0)

    def test_zone_open_and_heals(self, compiled):
        """天赋：2 层耗 → 结界 2 回合；结界内敌被我方攻击 → 攻击者回 376.22、
        A2 其余友方回 145.97."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 100.0   # 预压血线避免治疗 clamp（两发战技 2508 + 结界回 376）
        m7 = _lc(eng)
        m7.current_hp = 800.0
        _cast(eng, "1203", "120302", target=ally)
        _cast(eng, "1203", "120302", target=ally)
        assert "LUOCHA_ZONE" in m7.modifiers, "2 层展开结界"
        assert math.isclose(m7.resources["_abyss_flower"], 0.0), "消耗全部层"
        _cast(eng, "ally", "ally_basic", target=eng.state.actors["e1"])
        assert math.isclose(ally.current_hp, 100.0 + 2 * SKILL_HEAL + ZONE_HEAL, rel_tol=1e-9), (
            "攻击者本人回 0.18×ATK+240")
        assert math.isclose(m7.current_hp, 800.0 + A2_HEAL, rel_tol=1e-9), (
            "A2：除攻击者外友方回 0.07×ATK+93")


class TestPassiveSkill:
    def test_passive_trigger_and_cd(self, compiled):
        """被动等效：友方跌破 50% → 同效治疗+净化+1 层+CD 2 回合（不耗点）；
        CD 内不再触发."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 1200.0   # 40% ≤ 50%
        sp0 = eng.state.skill_points
        eng.bus.emit("on_hp_decrease", {
            "amount": 100.0, "source": "e1", "reason": "hit",
            "target": "ally", "damage_type": "imaginary"}, eng.state)
        assert math.isclose(ally.current_hp, 1200.0 + SKILL_HEAL, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, sp0), "被动不耗点（官方明示）"
        assert math.isclose(_lc(eng).resources["_abyss_flower"], 1.0)
        assert "SKILL_PASSIVE_CD" in _lc(eng).modifiers
        hp0 = ally.current_hp
        eng.bus.emit("on_hp_decrease", {
            "amount": 100.0, "source": "e1", "reason": "hit",
            "target": "ally", "damage_type": "imaginary"}, eng.state)
        assert math.isclose(ally.current_hp, hp0), "CD 内不再触发"


class TestUltimate:
    def test_ult_aoe_dispel_flower(self, compiled):
        """大招：AoE 2.0 对轴 + 驱散全体敌 1 增益（LIFO——dispel 语义正闸）+ 1 层."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="B1", name="旧增益", modifier_type="buff", duration=2))
        eng._apply_modifier(e1, Modifier(
            modifier_id="B2", name="新增益", modifier_type="buff", duration=2))
        hp1 = e1.current_hp
        m7 = _lc(eng)
        m7.current_energy = 100.0
        ult = next(a for a in eng.actions_by_actor["1203"] if a.action_id == "120303")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 2.0 * LC_ATK * Z, rel_tol=1e-9)
        assert "B2" not in e1.modifiers and "B1" in e1.modifiers, "驱散 LIFO 新先摘"
        assert math.isclose(m7.resources["_abyss_flower"], 1.0)


class TestEidolons:
    def test_e1_zone_team_atk(self):
        """E1：结界期间全队 ATK+20%（enable_if 门控——无结界不吃）."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["atk"], 1500.0, rel_tol=1e-9), (
            "无结界光环不起（门控实证）")
        ally.current_hp = 1000.0
        _cast(eng, "1203", "120302", target=ally)
        _cast(eng, "1203", "120302", target=ally)
        assert math.isclose(eng.pipeline.effective_stats(ally)["atk"], 1800.0, rel_tol=1e-9)

    def test_e2_scoped_heal_and_shield(self):
        """E2 双分支：低血目标该次治疗 ×1.3（scoped 当次就吃——时序勘正实证）；
        高血目标获护盾 376.22."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 1200.0   # 40% < 50%
        _cast(eng, "1203", "120302", target=ally)
        assert math.isclose(ally.current_hp, 1200.0 + SKILL_HEAL * 1.3, rel_tol=1e-9), (
            "scoped 当次治疗 +30%（hit_condition 正主——非后挂不吃）")
        ally.current_hp = 2700.0   # 90% ≥ 50%
        _cast(eng, "1203", "120302", target=ally)
        assert ally.shields, "高血护盾分支"
        assert math.isclose(ally.shields[0].remaining,
                            0.18 * (LC_ATK * 1.2) + 240.0, rel_tol=1e-9), (
            "E1 结界联动——两发战技后结界在场，罗刹有效 ATK ×1.2")

    def test_e4_weakened(self):
        """E4：结界期间敌方回合开始挂弱化（造成伤害 −12%——all_dmg 负值勘正实证）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1203", "120302", target=ally)
        _cast(eng, "1203", "120302", target=ally)
        e1 = eng.state.actors["e1"]
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert "E4_WEAKENED" in e1.modifiers
        assert math.isclose(eng.pipeline.effective_stats(e1)["dmg_bonus"].get("all", 0.0),
                            -0.12, rel_tol=1e-9)
