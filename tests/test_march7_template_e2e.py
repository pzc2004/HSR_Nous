"""三月七 1001 模板端到端对轴（验收型批①）：真模板 YAML → 编译 → 护盾/净化/反击限次/
大招冻结/星魂全链 → 手算全等.

过堂钓出幻视：战技护盾 draft 写 60.8% DEF+845.5（官方 100102 lv10=[0.57,3,0.3,760,5]
——57% DEF+760）——幻脑旧值，勘正并接 param() 随档（shield 槽 B27 #6 已收）。

口径常数：三月七白值 def 573.3（护盾基数）、atk 511.56（反击基数）；
假人 def 0 → 防御区 0.5、冰弱点 → 抗性区 1.0、未击破 0.9；暴击 0.05/0.5 → 期望暴击区 1.025。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

M7_DEF = 573.3
M7_ATK = 511.56
SHIELD_V = M7_DEF * 0.57 + 760.0     # lv10 护盾值（勘正后）
DEF_RES, UNBROKEN = 0.5, 0.9
CRIT_EXP = 1 + 0.05 * 0.5
COUNTER_DMG = M7_ATK * 1.0 * DEF_RES * UNBROKEN * CRIT_EXP   # 反击 lv10 #1=1.0


def _build(*, eidolon: int = 0, pre_battle=None):
    member = {"character_template": "1001", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        b["build"]["pre_battle"] = pre_battle
    return b


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


def _m7(eng):
    return eng.state.actors["1001"]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng._pick_ally_target = lambda attacker=None: tgt
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _foe_hit(eng, *, target="ally", scaling=1.0):
    from hsr_nous.sim_schema.action import Action
    eng.actions_by_actor = {**eng.actions_by_actor, "e1": [Action(
        action_id="e_hit", name="重击", action_type="basic", target_type="single",
        damage_type="physical", scaling=[{"atk": scaling}])]}
    eng._pick_ally_target = lambda attacker=None: eng.state.actors[target]
    eng._enemy_turn(eng.state.actors["e1"])


class TestMarchCompile:
    def test_resources_actions(self, compiled):
        assert "_counter_n" in compiled.resource_decls_by_actor["1001"]
        acts = {a.action_id: a for a in compiled.actions_by_actor["1001"]}
        assert acts["100104"].action_type == "follow_up", "天赋反击归 follow_up（无 talent 键）"
        assert acts["100104"].energy_gain == 10
        assert acts["100103"].energy_cost == 120 and acts["100103"].toughness_dmg == 20


class TestShieldAndPurify:
    def test_skill_shield_value_and_purify(self, compiled):
        """战技：护盾 = 57% DEF + 760（幻视勘正实证）+ 净化 1 负面（LIFO 新先摘）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        eng._apply_modifier(ally, Modifier(
            modifier_id="D1", name="旧负面", modifier_type="debuff", duration=2))
        eng._apply_modifier(ally, Modifier(
            modifier_id="D2", name="新负面", modifier_type="debuff", duration=2))
        _cast(eng, "1001", "100102", target=ally)
        shield = ally.shields[0]
        assert math.isclose(shield.remaining, SHIELD_V, rel_tol=1e-9), (
            "护盾值 = 57%×573.3 + 760 = 1086.781（幻视 845.5/60.8% 勘正实证）")
        assert "D2" not in ally.modifiers and "D1" in ally.modifiers, (
            "净化 LIFO 新先摘（max_count 1）")
        assert ally.modifiers["MARCH_SKILL_SHIELD"].duration == 4, "Reinforce 3→4 回合"


class TestCounter:
    def test_counter_hit_and_limit_and_reset(self, compiled):
        """反击：带战技盾我方受击 → 1.0×三月七 ATK 反击（门控每回合 2 次，回合开始重置）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1001", "100102", target=ally)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _foe_hit(eng, target="ally")
        assert math.isclose(hp1 - e1.current_hp, COUNTER_DMG, rel_tol=1e-9), (
            "反击 1.0×511.56×乘区（天赋 lv10 #1=1.0）")
        assert math.isclose(_m7(eng).resources["_counter_n"], 1.0)
        _foe_hit(eng, target="ally", scaling=0.3)
        assert math.isclose(_m7(eng).resources["_counter_n"], 2.0)
        hp1 = e1.current_hp
        _foe_hit(eng, target="ally", scaling=0.3)
        assert math.isclose(hp1 - e1.current_hp, 0.0), "第 3 次受击限次不反击（每回合 2 次）"
        eng.bus.emit("on_turn_start", {"actor": "1001"}, eng.state)
        _foe_hit(eng, target="ally", scaling=0.3)
        assert math.isclose(_m7(eng).resources["_counter_n"], 1.0), "回合开始重置可再反击"


class TestUltimate:
    def test_ult_aoe_and_freeze_dot(self, compiled):
        """大招：全体冻结（必冻承载——chance 通道待收在案）+ 冻结附伤 0.6×ATK（#4 随档）."""
        eng = _make(compiled)
        m7 = _m7(eng)
        m7.current_energy = 120.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        ult = next(a for a in eng.actions_by_actor["1001"] if a.action_id == "100103")
        assert eng._fire_ultimate(m7, ult) is True
        assert "MARCH_FROZEN" in e1.modifiers and "MARCH_FROZEN" in e2.modifiers
        ult_dmg = M7_ATK * 1.5 * DEF_RES * UNBROKEN * CRIT_EXP
        assert math.isclose(hp1 - e1.current_hp, ult_dmg, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, ult_dmg, rel_tol=1e-9)
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 0.6 * M7_ATK * DEF_RES * UNBROKEN * CRIT_EXP,
                            rel_tol=1e-9), "冻结附伤 0.6×ATK（param(100103,4) lv10）"


class TestEidolon2And4:
    def test_e2_battle_start_shield_lowest_hp(self):
        """E2：开战盾 order_by hp/max_hp 取首 + 24% DEF + 320——满血平票走确定性首员
        （我方全员开局皆满血=比值并列，take 1 取编队首；低血%选择语义由 order_by 表达式承载）."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        m7 = _m7(eng)
        assert m7.shields, "满血平票：E2 盾给编队首员（确定性 take 1）"
        assert math.isclose(m7.shields[0].remaining, 0.24 * M7_DEF + 320, rel_tol=1e-9), (
            "E2 盾 = 24%×573.3 + 320 = 457.592")

    def test_e4_third_counter_bonus_def(self):
        """E4：第 3 发反击附加 +30% DEF（仅第 3 发承载——1/2 发同生效挡因在案）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1001", "100102", target=ally)
        e1 = eng.state.actors["e1"]
        _foe_hit(eng, target="ally", scaling=0.5)
        _foe_hit(eng, target="ally", scaling=0.5)
        assert math.isclose(_m7(eng).resources["_counter_n"], 2.0)
        hp1 = e1.current_hp
        _foe_hit(eng, target="ally", scaling=0.5)   # 第 3 发（E4 钩 res__counter_n == 2 放行）
        assert math.isclose(hp1 - e1.current_hp,
                            (M7_ATK + 0.3 * M7_DEF) * DEF_RES * UNBROKEN * CRIT_EXP, rel_tol=1e-9), (
            "E4 第 3 发 = (1.0×ATK + 0.3×DEF)×乘区")
