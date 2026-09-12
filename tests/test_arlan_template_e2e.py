"""阿兰 1008 模板端到端对轴（验收型批·组1 收官）：真模板 YAML → 编译 → 战技自伤/
天赋活求值/Repel 免伤/Revival 回血/E1-E6 星魂闸全链 → 手算全等.

过堂四件（fixture 头注同录）：E1/E6 星魂件归位（全局 hooks=E0 也生效 bug）/
增伤键名 skill_dmg→dmg_skill_dmg_boost 族 / 天赋 stat_effects→stat_exprs
（快照烘焙=满血烘 0 永久死件，活求值正主）/ Endurance dot_resist 死键摘除。

口径常数：阿兰白值 atk 599.76、hp 1199.52、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、雷弱点 → 抗性区 1.0、未击破 0.9。天赋失 HP 线性增伤
上限 param(100804,1) lv10=0.72（stat_exprs 活求值——40% 血 → 0.72×0.6=0.432）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

AR_ATK = 599.76
AR_HP = 1199.52
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1008", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "thunder",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _ar(eng):
    return eng.state.actors["1008"]


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


class TestArlanCompile:
    def test_actions_and_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1008"]}
        assert acts["100802"].skill_point_cost == 0 and acts["100802"].skill_point_gain == 0, (
            "战技不耗点不产点（tbgd 权威——starguide'产点'表述不采纳）")
        assert acts["100803"].energy_cost == 110 and acts["100803"].scaling_blast
        assert "_repel_active" in compiled.resource_decls_by_actor["1008"]


class TestSkillDrain:
    def test_skill_damage_then_drain(self, compiled):
        """战技：2.4×ATK 对轴（满血天赋 0）；on_action 后自伤 15% Max（时序待实测在案）；
        第二发天赋按 15% 失血活求值 0.72×0.15=0.108."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1008", "100802")
        assert math.isclose(hp1 - e1.current_hp, 2.4 * AR_ATK * Z, rel_tol=1e-9)
        assert math.isclose(_ar(eng).current_hp, AR_HP * 0.85, rel_tol=1e-9), "自伤 15% Max"
        hp1 = e1.current_hp
        _cast(eng, "1008", "100802")
        assert math.isclose(hp1 - e1.current_hp, 2.4 * AR_ATK * Z * 1.108, rel_tol=1e-9), (
            "天赋活求值：失血 15% → all 0.108（stat_exprs 勘正实证——快照烘焙会恒 0）")
        assert math.isclose(_ar(eng).current_hp, AR_HP * 0.70, rel_tol=1e-9)

    def test_drain_floor_one(self, compiled):
        """floor 1 保底：HP 10 < 15% Max → 降至 1 不致死（官方'his HP will be reduced to 1'）."""
        eng = _make(compiled)
        a = _ar(eng)
        a.current_hp = 10.0
        _cast(eng, "1008", "100802")
        assert a.alive and math.isclose(a.current_hp, 1.0)


class TestTalentLiveEval:
    def test_low_hp_talent_and_no_e1_at_e0(self, compiled):
        """天赋 stat_exprs 活求值：40% 血 → all 0.432；E0 无 E1 件（星魂闸 bug 归位实证）."""
        eng = _make(compiled)
        a = _ar(eng)
        a.current_hp = 0.4 * AR_HP
        eff = eng.pipeline.effective_stats(a)
        assert math.isclose(eff["dmg_bonus"].get("all", 0.0), 0.432, rel_tol=1e-9)
        assert "E1_SKILL_DMG" not in a.modifiers and "E6_ULT_DMG" not in a.modifiers
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1008", "100801")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * AR_ATK * Z * 1.432, rel_tol=1e-9)


class TestRepelAndRevival:
    def test_repel_cancel_path(self, compiled):
        """Repel：闩在场 → before_take_damage 免伤（cancel）并清闩——sim 开战恒满血
        闩自然不可达（在案），cancel 路径手动置闩钉死."""
        eng = _make(compiled)
        a = _ar(eng)
        assert math.isclose(a.resources.get("_repel_active", 0.0), 0.0), "满血开战闩不置"
        a.resources["_repel_active"] = 1.0
        out = eng.bus.waterfall("before_take_damage",
                                {"target": "1008", "amount": 500.0, "source": "e1"}, eng.state)
        assert out.get("cancel"), "免伤闩 cancel 实证"
        assert math.isclose(a.resources["_repel_active"], 0.0), "首次被攻击清闩"

    def test_revival_on_kill_low_hp(self, compiled):
        """Revival：HP≤30% 击杀 → 回 20% Max HP（on_kill 逐杀）."""
        eng = _make(compiled)
        a = _ar(eng)
        a.current_hp = 0.25 * AR_HP
        e2 = eng.state.actors["e2"]
        e2.current_hp = 50.0
        _cast(eng, "1008", "100801", target=e2)
        assert not e2.alive
        assert math.isclose(a.current_hp, 0.45 * AR_HP, rel_tol=1e-9), "0.25+0.20 Max"


class TestEidolons:
    def test_e1_gate_and_e2_cleanse(self):
        """E1：40% 血战技吃 0.1 类型桶（+天赋 0.432）；E2：战技后净化 1 负面（LIFO 新先摘）."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        a = _ar(eng)
        a.current_hp = 0.4 * AR_HP
        eng._apply_modifier(a, Modifier(
            modifier_id="D1", name="旧负面", modifier_type="debuff", duration=2))
        eng._apply_modifier(a, Modifier(
            modifier_id="D2", name="新负面", modifier_type="debuff", duration=2))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1008", "100802")
        assert math.isclose(hp1 - e1.current_hp,
                            2.4 * AR_ATK * Z * (1 + 0.432 + 0.1), rel_tol=1e-9), (
            "E1 战技增伤 10%（dmg_skill_dmg_boost 类型桶勘正实证）")
        assert "D2" not in a.modifiers and "D1" in a.modifiers, "E2 净化 1 负面 LIFO"

    def test_e4_lethal_intercept(self):
        """E4：致死量 → 回 25% Max + 摘件 + cancel（before_take_damage 通道）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        a = _ar(eng)
        assert "E4_TURN_THE_TABLES" in a.modifiers
        a.current_hp = 100.0
        out = eng.bus.waterfall("before_take_damage",
                                {"target": "1008", "amount": 500.0, "source": "e1"}, eng.state)
        assert out.get("cancel"), "致死拦截 cancel"
        assert math.isclose(a.current_hp, 100.0 + 0.25 * AR_HP, rel_tol=1e-9)
        assert "E4_TURN_THE_TABLES" not in a.modifiers, "拦截后摘件"

    def test_e5_talent_lv12(self):
        """E5 天赋+2：上限 lv12=0.792（40% 血 → 0.4752）；E5 终结技+2 → 主 3.456/邻 1.728."""
        compiled = compile_encounter(_build(eidolon=5), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        a = _ar(eng)
        a.current_hp = 0.4 * AR_HP
        assert math.isclose(eng.pipeline.effective_stats(a)["dmg_bonus"].get("all", 0.0),
                            0.4752, rel_tol=1e-9)
        a.current_energy = 110.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        ult = next(x for x in eng.actions_by_actor["1008"] if x.action_id == "100803")
        assert eng._fire_ultimate(a, ult) is True
        boost = 1 + 0.4752
        assert math.isclose(hp1 - e1.current_hp, 3.456 * AR_ATK * Z * boost, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 1.728 * AR_ATK * Z * boost, rel_tol=1e-9)
