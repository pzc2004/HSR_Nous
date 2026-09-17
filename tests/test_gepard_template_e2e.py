"""杰帕德 1104 模板端到端对轴（验收型批·组2）：真模板 YAML → 编译 → 冻结链/
全体护盾/免死三钩/行迹门控/星魂全链 → 手算全等.

过堂三件（fixture 头注同录）：mechanic_chance 签名勘正 / shield param 收编 /
Integrity aggro_boost 收编。

口径常数：杰帕德 atk 543.312、def 736.745625（白值 654.885×1.125——行迹 def_pct
0.125 B-TR① 回填）、hp 1397.088、crit 0.05/0.5（期望暴击区 1.025）、冰伤池
1.224（行迹 dmg_ice 0.224 同回填）；假人 def 0 → 防御区 0.5、冰弱点 →
抗性区 1.0、未击破 0.9。普攻 lv6=1.0。护盾 lv10 = 0.45×736.745625+600；
E3 lv12 = 0.48×736.745625+667.5。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

GE_ATK = 543.312
GE_DEF = 654.885 * 1.125   # 736.745625（行迹 def_pct 0.125 回填——B-TR①）
GE_HP = 1397.088
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
ICE = 1.224                # 冰伤池（行迹 dmg_ice 0.224 回填——B-TR①）


def _build(*, eidolon: int = 0):
    member = {"character_template": "1104", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "ice",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _ge(eng):
    return eng.state.actors["1104"]


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
    m7 = _ge(eng)
    m7.current_energy = 100.0
    ult = next(a for a in eng.actions_by_actor["1104"] if a.action_id == "110403")
    assert eng._fire_ultimate(m7, ult) is True


class TestGepardCompile:
    def test_resources(self, compiled):
        assert "_talent_used" in compiled.resource_decls_by_actor["1104"]
        acts = {a.action_id: a for a in compiled.actions_by_actor["1104"]}
        assert acts["110403"].energy_cost == 100


class TestFreezeChain:
    def test_skill_freeze_and_dot(self, compiled):
        """战技：2.0 对轴 + 冻结挂载（mechanic_chance 单参勘正实证——0.65≥0.5 恒中）
        + 冻结期附伤 0.6×ATK（lv10 #4）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1104", "110402")
        assert math.isclose(hp1 - e1.current_hp, 2.0 * GE_ATK * Z * ICE, rel_tol=1e-9)
        assert "FROZEN_BY_SKILL" in e1.modifiers, "三参死钩勘正后冻结实证"
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 0.6 * GE_ATK * Z * ICE, rel_tol=1e-9)


class TestUltimateShield:
    def test_team_shield_param(self, compiled):
        """大招：全体护盾 = param(110403,1)×DEF + param(110403,3)（lv10=0.45×654.885+600
        ——shield param 随档收编实证）."""
        eng = _make(compiled)
        _ult(eng)
        want = 0.45 * GE_DEF + 600.0
        for aid in ("1104", "ally"):
            st = eng.state.actors[aid]
            assert st.shields, f"{aid} 护盾在"
            assert math.isclose(st.shields[0].remaining, want, rel_tol=1e-9)
        assert math.isclose(_ge(eng).current_energy, 5.0)

    def test_e3_shield_lv12(self):
        """E3 终结技+2：护盾随档 lv12=0.48×654.885+667.5（shield param 收编核心实证）."""
        compiled = compile_encounter(_build(eidolon=3), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _ult(eng)
        assert math.isclose(_ge(eng).shields[0].remaining,
                            0.48 * GE_DEF + 667.5, rel_tol=1e-9)


class TestTalentUndying:
    def test_lethal_cancel_heal_energy(self, compiled):
        """免死三钩同帧：cancel 致命 + 回血 50% Max + Commander 回满 100——闩后不再触发."""
        eng = _make(compiled)
        a = _ge(eng)
        a.current_hp = 100.0
        out = eng.bus.waterfall("before_take_damage",
                                {"target": "1104", "amount": 500.0, "source": "e1"}, eng.state)
        assert out.get("cancel"), "cancel_event 免死"
        assert math.isclose(a.current_hp, 100.0 + 0.5 * GE_HP, rel_tol=1e-9)
        assert math.isclose(a.current_energy, 100.0), "Commander 回满能"
        assert math.isclose(a.resources["_talent_used"], 1.0)
        a.current_hp = 50.0
        out = eng.bus.waterfall("before_take_damage",
                                {"target": "1104", "amount": 500.0, "source": "e1"}, eng.state)
        assert not out.get("cancel"), "闩后不再免死"
        assert math.isclose(a.current_hp, 50.0)


class TestTraces:
    def test_grit_atk_and_integrity_taunt(self, compiled):
        """Grit：回合开始 ATK +35%×当前 DEF（stat_exprs 活读）；
        Integrity：taunt_eff = taunt×(1+3)（aggro_boost 收编实证）."""
        eng = _make(compiled)
        a = _ge(eng)
        eff = eng.pipeline.effective_stats(a)
        assert math.isclose(eff["taunt_eff"], eff["taunt"] * 4.0, rel_tol=1e-9)
        eng.bus.emit("on_turn_start", {"actor": "1104"}, eng.state)
        assert math.isclose(eng.pipeline.effective_stats(a)["atk"],
                            GE_ATK + 0.35 * GE_DEF, rel_tol=1e-9)


class TestEidolons:
    def test_e2_lingering_cold(self):
        """E2：被战技冻结的敌方解冻后 SPD −20%（after_remove_modifier 契约在册）."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1104", "110402")
        assert "FROZEN_BY_SKILL" in e1.modifiers
        eng._remove_modifier(e1, "FROZEN_BY_SKILL", "test")
        assert "E2_LINGERING_COLD" in e1.modifiers
        assert math.isclose(eng.pipeline.effective_stats(e1)["spd"], 100 * 0.8, rel_tol=1e-9)

    def test_e4_team_effect_res(self):
        """E4：全队效果抵抗 +20%（team 光环）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["effect_res"], 0.2, rel_tol=1e-9)

    def test_e6_extra_heal(self):
        """E6：免死帧额外回血 50% Max（与天赋 0.55/E3 合计）——eidolon=6 全联动."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        a = _ge(eng)
        a.current_hp = 100.0
        out = eng.bus.waterfall("before_take_damage",
                                {"target": "1104", "amount": 500.0, "source": "e1"}, eng.state)
        assert out.get("cancel")
        assert math.isclose(a.current_hp, GE_HP, rel_tol=1e-9), (
            "E3 天赋 lv12=0.55 + E6 额外 0.5 → 100+1.05×Max 超上限 clamp 满血（同帧快照读旧闩）")
