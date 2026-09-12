"""桑博 1108 模板端到端对轴（验收型批·组2）：真模板 YAML → 编译 → 弹射/
风化施加与跳伤/终结技易伤账面/行迹/星魂全链 → 手算全等.

过堂六件（fixture 头注同录）：首段倍率列幻视勘正 / mechanic_chance 收编 /
风化 tick 收编（E6 并入）/ 1108102 回能收编 / 秘技选择器勘正 / 易伤口径。

口径常数：桑博白值 atk 617.4、crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 →
防御区 0.5、风弱点 → 抗性区 1.0、未击破 0.9。普攻 lv6=1.0。风化 tick lv10
= 层数×0.52×ATK（E6 层数×0.67）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

SA_ATK = 617.4
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
SEG = 0.56          # 战技单段 lv10（params 第 2 列——列勘正实证）


def _build(*, eidolon: int = 0):
    member = {"character_template": "1108", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "wind",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["wind"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["wind"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _sa(eng):
    return eng.state.actors["1108"]


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


class TestSampoCompile:
    def test_skill_scaling_column(self, compiled):
        """首段倍率列勘正实证：scaling lv10=0.56（params 第 2 列——非弹射次数列 4.0）."""
        acts = {a.action_id: a for a in compiled.actions_by_actor["1108"]}
        assert math.isclose(acts["110802"].scaling[9]["atk"], 0.56)
        assert acts["110803"].energy_cost == 120


class TestSkillBounce:
    def test_first_hit_bounces_and_shear(self, compiled):
        """战技：首段 0.56 + 4 段弹射 0.56（expected 全落 e1）+ 天赋风化挂载
        （mechanic_chance 0.65 恒中）+ tick 0.52×ATK（收编实证）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1108", "110802")
        assert math.isclose(hp1 - e1.current_hp, 5 * SEG * SA_ATK * Z, rel_tol=1e-9)
        assert "WIND_SHEAR" in e1.modifiers and e1.modifiers["WIND_SHEAR"].duration == 4
        assert math.isclose(_sa(eng).current_energy, 6.0)
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 0.52 * SA_ATK * Z, rel_tol=1e-9), (
            "tick = 1 层×0.52×ATK（on_turn_start 怪物主体收编）")


class TestUltimate:
    def test_ult_aoe_vuln_marker_energy(self, compiled):
        """大招：AoE 1.6 对轴 + DoT 易伤账面（空壳——tick 不吃易伤口径在案）
        + 回能 5+10（1108102 收编实证）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        m7 = _sa(eng)
        m7.current_energy = 120.0
        ult = next(a for a in eng.actions_by_actor["1108"] if a.action_id == "110803")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 1.6 * SA_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 1.6 * SA_ATK * Z, rel_tol=1e-9)
        assert "SAMPO_DOT_VULN" in e1.modifiers
        assert math.isclose(m7.current_energy, 15.0), "5 自身 + 10 Defensive Position 分槽"


class TestEidolons:
    def test_e1_fifth_bounce(self):
        """E1：第 5 段弹射（共 6 次命中）."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1108", "110802")
        assert math.isclose(hp1 - e1.current_hp, 6 * SEG * SA_ATK * Z, rel_tol=1e-9)

    def test_e2_kill_spreads_shear(self):
        """E2：击杀带风化者 → 全体敌人挂风化 1 层."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="WIND_SHEAR", name="风化", modifier_type="debuff",
            stacks=1, max_stack=5, duration=4))
        e1.current_hp = 100.0
        _cast(eng, "1108", "110801")
        assert not e1.alive
        assert "WIND_SHEAR" in e2.modifiers, "E2 传染全体"

    def test_e4_deep_love_bonus(self):
        """E4：战技命中 5 层风化目标追加 8%×5 层×0.52×ATK 现风化结算
        （E3 战技 lv12=0.616 + E1 第 5 段全联动；层数谓词 stacks 勘正实证）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="WIND_SHEAR", name="风化", modifier_type="debuff",
            stacks=5, max_stack=5, duration=4))
        hp1 = e1.current_hp
        _cast(eng, "1108", "110802")
        bonus = 0.08 * 5 * 0.52 * SA_ATK * Z
        assert math.isclose(hp1 - e1.current_hp,
                            6 * 0.616 * SA_ATK * Z + bonus, rel_tol=1e-9)

    def test_e6_shear_ratio_up(self):
        """E6：风化 tick 倍率 +0.15（marker 并入——E5 天赋 lv12=0.572+0.15=0.722 联动）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="WIND_SHEAR", name="风化", modifier_type="debuff",
            stacks=1, max_stack=5, duration=4))
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, (0.572 + 0.15) * SA_ATK * Z, rel_tol=1e-9)
