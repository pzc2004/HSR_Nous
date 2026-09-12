"""素裳 1206 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 剑势概率链/
终结技强化/额外机会/行迹/星魂全链 → 手算全等.

过堂两件（fixture 头注同录）：chance→mechanic_chance（expected 0.33<0.5 恒不触发
双态钉）/ E2 减伤键 dmg_dmg_reduction。

口径常数：素裳白值 atk 564.48、spd 107、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、物理弱点 → 抗性区 1.0、未击破 0.9。普攻 lv6=1.0。
expected 口径下剑势/额外机会均不触发（roll 真掷 33%——击破必触发段查询缺在案）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

SS_ATK = 564.48
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1206", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "physical",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["physical"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _ss(eng):
    return eng.state.actors["1206"]


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


class TestSushangCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1206"]
        assert decls["_stance_extra"]["max"] == 2 and decls["_riposte"]["max"] == 10
        acts = {a.action_id: a for a in compiled.actions_by_actor["1206"]}
        assert acts["120603"].energy_cost == 120
        mods = {m["modifier_id"]: m for m in acts["120603"].apply_modifiers}
        assert math.isclose(mods["SUSHANG_ULT_ATK"]["stat_effects"]["atk_pct"], 0.3), (
            "终结技 ATK+30% lv10（编译期 param 求值）")


class TestSkill:
    def test_skill_damage_and_stance_expected_off(self, compiled):
        """战技：2.1 对轴（lv10）；剑势 expected 恒不触发（0.33<0.5 双态钉——
        mechanic_chance 勘正实证）：无附加段、剑胆不计数、E2 不挂."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1206", "120602")
        assert math.isclose(hp1 - e1.current_hp, 2.1 * SS_ATK * Z, rel_tol=1e-9), (
            "仅主伤——剑势 expected 不触发")
        s = _ss(eng)
        assert math.isclose(s.resources["_riposte"], 0.0), "剑胆未计数"
        assert "E2_SWORD_STANCE_GUARD" not in s.modifiers, "E2 同 roll 不挂（expected）"


class TestUltimate:
    def test_ult_buff_extra_chance(self, compiled):
        """大招：3.2 对轴 + ATK+30% 2 回合 + 授 2 次额外机会（expected 同不触发，
        战技后清空剩余机会）+ 回能 5."""
        eng = _make(compiled)
        m7 = _ss(eng)
        m7.current_energy = 120.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1206"] if a.action_id == "120603")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 3.2 * (SS_ATK * 1.3) * Z, rel_tol=1e-9), (
            "副作用先于伤害段——本发即吃 ATK+30%（时序在案）")
        assert math.isclose(eng.pipeline.effective_stats(m7)["atk"], SS_ATK * 1.3, rel_tol=1e-9)
        assert math.isclose(m7.resources["_stance_extra"], 2.0)
        assert math.isclose(m7.current_energy, 5.0)
        hp1 = e1.current_hp
        _cast(eng, "1206", "120602")
        assert math.isclose(hp1 - e1.current_hp, 2.1 * (SS_ATK * 1.3) * Z, rel_tol=1e-9), (
            "强化后战技主伤（额外机会 expected 不触发）")
        assert math.isclose(m7.resources["_stance_extra"], 0.0), "战技后清空剩余机会"


class TestEidolons:
    def test_e4_break_effect(self):
        """E4：击破特攻 +40%（break_effect 键在库——闸校验实证）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        assert math.isclose(eng.pipeline.effective_stats(_ss(eng))["break_effect"],
                            0.4, rel_tol=1e-9)

    def test_e6_opening_spd_stack(self):
        """E6：入场 1 层天赋速度（E3 天赋+2 → lv12=0.21 联动在案）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        assert "SUSHANG_TALENT_SPD" in _ss(eng).modifiers
        assert math.isclose(eng.pipeline.effective_stats(_ss(eng))["spd"],
                            107 * 1.21, rel_tol=1e-9), "E3 天赋 lv12=0.21（E6 含 E3 联动）"

    def test_e3_ult_lv12(self):
        """E3 终结技+2：lv12=3.456 对轴."""
        compiled = compile_encounter(_build(eidolon=3), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        m7 = _ss(eng)
        m7.current_energy = 120.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1206"] if a.action_id == "120603")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 3.456 * (SS_ATK * 1.324) * Z, rel_tol=1e-9), (
            "lv12=3.456 × ATK+32.4%（#4 lv12=0.324——副作用先于伤害段本发即吃）")
