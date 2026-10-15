"""玲可 1110 模板端到端对轴（验收型批·组3 开批）：真模板 YAML → 编译 → 战技三段/
天赋 HoT 双段/终结技净化治疗/行迹/星魂全链 → 手算全等.

过堂六件（fixture 头注同录）：ally_single 勘正 / hp_max 死键→hp flat（E4/E6 同案）
/ stat_exprs→stat_effects 错基勘正 / 行迹 1 收编 / E1 scoped 收编 / E6 抵抗收编。

口径常数：玲可白值 atk 493.92、hp 1058.4、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、量子弱点 → 抗性区 1.0、未击破 0.9。普攻 lv6=0.5×Max。
战技治疗 lv10 = 0.12×1058.4+320；求生反应 hp flat = 0.075×1058.4+200（快照）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

LX_ATK = 493.92
LX_HP = 1058.4
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
SKILL_HEAL = 0.12 * LX_HP + 320.0
SR_HP = 0.075 * LX_HP + 200.0        # 求生反应 Max HP 提升（玲可快照）
HOT = 0.036 * LX_HP + 96.0           # 天赋 HoT lv10
HOT_SR = 0.045 * LX_HP + 120.0       # 求生反应额外段


def _build(*, eidolon: int = 0):
    member = {"character_template": "1110", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "quantum",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["quantum"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["quantum"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _lx(eng):
    return eng.state.actors["1110"]


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


class TestLynxCompile:
    def test_skill_ally_single(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1110"]}
        assert acts["111002"].target_type == "ally_single", "治疗技目标池勘正实证"
        assert acts["111001"].scaling[5] == {"hp": 0.5}, "普攻 lv6=0.5×Max HP"


class TestSkillChain:
    def test_skill_heal_maxhp_hot(self, compiled):
        """战技三段：指定治疗 447.0 + Max HP +279.38（hp flat 死键勘正实证——玲可快照）
        + HoT 3 回合（行迹 3 并入）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 2000.0
        _cast(eng, "1110", "111002", target=ally)
        assert math.isclose(ally.current_hp, 2000.0 + SKILL_HEAL, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["hp"],
                            3000.0 + SR_HP, rel_tol=1e-9), "Max HP +7.5%×1058.4+200（快照）"
        assert ally.modifiers["OUTDOOR_SURVIVAL_HOT"].duration == 3

    def test_hot_ticks_with_response(self, compiled):
        """天赋 HoT：持有求生反应者回合开始双段（0.036×HP+96 + 0.045×HP+120）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 2000.0   # 预压血线避免治疗 clamp
        _cast(eng, "1110", "111002", target=ally)
        hp0 = ally.current_hp
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        assert math.isclose(ally.current_hp - hp0, HOT + HOT_SR, rel_tol=1e-9)

    def test_trace1_hit_energy(self, compiled):
        """行迹 1：持求生反应目标受击 → 玲可回能 2（收编实证）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1110", "111002", target=ally)
        a = _lx(eng)
        e0 = a.current_energy
        eng.bus.emit("after_being_hit", {
            "target": "ally", "source": "e1", "amount": 100.0,
            "action_type": "basic", "damage_type": "quantum"}, eng.state)
        assert math.isclose(a.current_energy, e0 + 2.0)


class TestUltimate:
    def test_ult_cleanse_heal_hot(self, compiled):
        """大招：全体净化 1 负面（LIFO）+ 治疗 (0.135×HP+360) + 全体 HoT."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 2000.0
        eng._apply_modifier(ally, Modifier(
            modifier_id="D1", name="旧负面", modifier_type="debuff", duration=2))
        eng._apply_modifier(ally, Modifier(
            modifier_id="D2", name="新负面", modifier_type="debuff", duration=2))
        m7 = _lx(eng)
        m7.current_energy = 100.0
        ult = next(a for a in eng.actions_by_actor["1110"] if a.action_id == "111003")
        assert eng._fire_ultimate(m7, ult) is True
        heal = 0.135 * LX_HP + 360.0
        assert math.isclose(ally.current_hp, 2000.0 + heal, rel_tol=1e-9)
        assert "D2" not in ally.modifiers and "D1" in ally.modifiers
        assert "OUTDOOR_SURVIVAL_HOT" in ally.modifiers
        assert math.isclose(m7.current_energy, 5.0)


class TestEidolons:
    def test_e1_heal_boost_low_hp(self):
        """E1：治疗 ≤50% 我方 ×1.2（hit_condition 治疗命中域收编实证）."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 1400.0   # 46.7% ≤ 50%
        _cast(eng, "1110", "111002", target=ally)
        assert math.isclose(ally.current_hp, 1400.0 + SKILL_HEAL * 1.2, rel_tol=1e-9)

    def test_e4_atk_flat(self):
        """E4：求生反应目标 ATK +3%×玲可 Max HP（玲可快照——错基勘正实证）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1110", "111002", target=ally)
        assert math.isclose(eng.pipeline.effective_stats(ally)["atk"],
                            1500.0 + 0.03 * LX_HP, rel_tol=1e-9)

    def test_e6_hp_and_res(self):
        """E6：求生反应 Max HP +6%×玲可 Max + 效果抵抗 +30%（双段收编实证）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1110", "111002", target=ally)
        eff = eng.pipeline.effective_stats(ally)
        sr_lv12 = 0.08 * LX_HP + 222.5   # E3 战技+2 → 求生反应 lv12（联动在案）
        assert math.isclose(eff["hp"], 3000.0 + sr_lv12 + 0.06 * LX_HP, rel_tol=1e-9)
        assert math.isclose(eff["effect_res"], 0.3, rel_tol=1e-9)

    def test_e3_skill_lv12(self):
        """E3 战技+2：治疗 lv12=0.128×HP+356、求生反应 0.08×HP+222.5."""
        compiled = compile_encounter(_build(eidolon=3), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 2000.0
        _cast(eng, "1110", "111002", target=ally)
        assert math.isclose(ally.current_hp, 2000.0 + (0.128 * LX_HP + 356.0), rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["hp"],
                            3000.0 + (0.08 * LX_HP + 222.5), rel_tol=1e-9)
