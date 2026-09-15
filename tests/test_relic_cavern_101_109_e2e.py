"""遗器 101-109 族（开服洞穴遗器第一批）e2e：staging→fixtures 验收批.

8 套（101/102/104/105/106/107/108/109），每套 2 件/4 件分例——2 件只触发 2pc、
4 件全触发。fixture 勘正条目见各 fixture 头注。

口径常数（手算对轴）：装备员 atk 1000 / spd 100 / hp 3000，inline 行动 scaling atk 1.0；
假人 def 1000 → 防御区 0.5（lv80：1000/(1000+1000)），弱点全配 → 抗性区 1.0，
未击破 0.9，期望暴击区 = 0.05×1.5+0.95 = 1.025。直伤基准（无增伤）=
1000×0.5×0.9×1.025 = 461.25；带 2pc 元素增伤 0.1 → 507.375。
敌方反打装备员（无套装）：res 区 0.8（非弱点默认抗 0.2）→ 1000×0.5×0.8×0.9×1.025 = 369。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

Z = 0.5 * 0.9 * 1.025          # 直伤链：防御区×未击破×期望暴击区
CZ = 1.025                     # 期望暴击区（crit 0.05/0.5）


def _build(set_id, pieces=4, dmg_type="fire", extra_actions=()):
    actions = [{"action_id": "t_basic", "name": "普攻", "action_type": "basic",
                "target_type": "single", "damage_type": dmg_type,
                "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]
    actions += extra_actions
    member = {"actor_id": "w", "name": "装备员", "inline": True,
              "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
              "relics": {f"slot{i}": {"set_id": set_id} for i in range(pieces)},
              "actions": actions}
    return {"build": {"team": [member],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

_SKILL = {"action_id": "t_skill", "name": "战技", "action_type": "skill",
          "target_type": "single", "damage_type": "fire",
          "scaling": [{"atk": 1.0}], "toughness_dmg": 20, "skill_point_cost": 1}
_ULT = {"action_id": "t_ult", "name": "终结技", "action_type": "ultimate",
        "target_type": "single", "damage_type": "fire",
        "scaling": [{"atk": 1.0}], "toughness_dmg": 30}


def _make(set_id, pieces=4, dmg_type="fire", extra_actions=()):
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(set_id, pieces, dmg_type, extra_actions), _STAGE,
                          template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _panel(eng):
    return eng.pipeline.effective_stats(eng.state.actors["w"])


def _cast(eng, aid, target_id="e1"):
    """施放行动走真漏斗（含 on_action 广播——引擎 _run_turn 同形状）."""
    st = eng.state.actors["w"]
    a = next(x for x in eng.actions_by_actor["w"] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    before = eng.state.total_damage
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "w", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)
    return eng.state.total_damage - before


def _ult(eng):
    st = eng.state.actors["w"]
    tgt = eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    st.current_energy = 100.0
    ult = next(a for a in eng.actions_by_actor["w"] if a.action_id == "t_ult")
    before = eng.state.total_damage
    assert eng._fire_ultimate(st, ult) is True
    return eng.state.total_damage - before


class TestRelic101Passerby:
    """云无留迹的过客（101）：2pc 治疗量+10%（heal_bonus）；4pc 开局+1 战技点."""

    def test_2pc_heal_bonus(self):
        eng = _make("101", pieces=2)
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.1)
        # 行为：治疗管线 100 基数 → 110
        w = eng.state.actors["w"]
        assert eng.pipeline.heal(w, w, 100.0).value == pytest.approx(110.0)

    def test_2pc_no_4pc_sp(self):
        eng = _make("101", pieces=2)
        assert eng.state.skill_points == 3, "2 件不触发 4pc 开局战技点"

    def test_4pc_battle_start_sp(self):
        eng = _make("101", pieces=4)
        assert eng.state.skill_points == 4, "战斗开始立即恢复 1 战技点（3→4）"
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.1), "4 件仍持 2pc"


class TestRelic102Musketeer:
    """野穗伴行的快枪手（102）：2pc atk+12%；4pc spd+6% + 普攻增伤 10%."""

    def test_2pc_atk(self):
        eng = _make("102", pieces=2)
        p = _panel(eng)
        assert p["atk"] == pytest.approx(1120.0), "atk = 1000×1.12"
        assert p["spd"] == pytest.approx(100.0), "2 件无 4pc 速度"
        assert _cast(eng, "t_basic") == pytest.approx(1120.0 * Z), (
            "普攻 = 1120×0.5×0.9×1.025 = 516.6（无普攻增伤桶）")

    def test_4pc_spd_and_basic_boost(self):
        eng = _make("102", pieces=4)
        p = _panel(eng)
        assert p["atk"] == pytest.approx(1120.0)
        assert p["spd"] == pytest.approx(106.0), "spd = 100×1.06"
        assert p["dmg_bonus"].get("basic_dmg_boost", 0.0) == pytest.approx(0.1)
        assert _cast(eng, "t_basic") == pytest.approx(1120.0 * 1.1 * Z), (
            "普攻 = 1120×1.1×0.5×0.9×1.025 = 568.26")


class TestRelic104GlacialForest:
    """密林卧雪的猎人（104）：2pc 冰伤+10%；4pc 终结技后暴伤+25% 持续 2 回合."""

    def test_2pc_ice_dmg_no_ult_buff(self):
        eng = _make("104", pieces=2, dmg_type="ice", extra_actions=[dict(_ULT, damage_type="ice")])
        assert _panel(eng)["dmg_bonus"].get("ice", 0.0) == pytest.approx(0.1)
        _ult(eng)
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5), "2 件终结技不挂暴伤"
        assert "SET_104_ULT_CRITDMG" not in eng.state.actors["w"].modifiers

    def test_4pc_crit_dmg_after_ult(self):
        eng = _make("104", pieces=4, dmg_type="ice", extra_actions=[dict(_ULT, damage_type="ice")])
        _ult(eng)
        mod = eng.state.actors["w"].modifiers.get("SET_104_ULT_CRITDMG")
        assert mod is not None and mod.duration == 2, "暴伤 buff 持续 2 回合"
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.75)
        # 暴伤 0.75 后期望暴击区 = 0.05×1.75+0.95 = 1.0375
        cz = 0.05 * 1.75 + 0.95
        assert _cast(eng, "t_basic") == pytest.approx(1000.0 * 1.1 * 0.5 * 0.9 * cz), (
            "冰普攻 = 1000×1.1×0.5×0.9×1.0375 = 513.5625")


class TestRelic105StreetwiseBoxing:
    """街头出身的拳王（105）：2pc 物理+10%；4pc 攻击/受击叠攻 5%/层，上限 5 层."""

    def test_2pc_physical_no_stacks(self):
        eng = _make("105", pieces=2, dmg_type="physical")
        assert _panel(eng)["dmg_bonus"].get("physical", 0.0) == pytest.approx(0.1)
        _cast(eng, "t_basic")
        assert "SET105_4PC_ATK" not in eng.state.actors["w"].modifiers, "2 件行动不叠层"

    def test_4pc_stacking(self):
        eng = _make("105", pieces=4, dmg_type="physical")
        w = eng.state.actors["w"]
        _cast(eng, "t_basic")
        assert w.modifiers["SET105_4PC_ATK"].stacks == 1
        assert _panel(eng)["atk"] == pytest.approx(1050.0), "1 层 atk = 1000×1.05"
        # 受击叠层（after_being_hit 真事件载荷）
        eng.bus.emit("after_being_hit", {
            "amount": 100.0, "absorbed": 0.0, "damage_type": "fire", "source": "e1",
            "target": "w", "is_critical": False, "action_type": "basic",
            "actor_type": "monster", "hit_targets": ["w"], "seg_index": 0}, eng.state)
        assert w.modifiers["SET105_4PC_ATK"].stacks == 2
        assert _panel(eng)["atk"] == pytest.approx(1100.0), "2 层 atk = 1000×1.10"
        # 再 4 动 → 6 层触发，上限 5 截断
        for _ in range(4):
            _cast(eng, "t_basic")
        assert w.modifiers["SET105_4PC_ATK"].stacks == 5, "上限 5 层"
        assert _panel(eng)["atk"] == pytest.approx(1250.0), "5 层 atk = 1000×1.25"
        assert _cast(eng, "t_basic") == pytest.approx(1250.0 * 1.1 * Z), (
            "满层物理普攻 = 1250×1.1×0.5×0.9×1.025 = 634.21875")


class TestRelic106GuardOfSnow:
    """戍卫风雪的铁卫（106）：2pc 减伤 8%；4pc 回合开始 hp≤50% 回血 8% 上限 + 5 能量."""

    def test_2pc_dmg_reduction(self):
        eng = _make("106", pieces=2)
        assert _panel(eng)["dmg_bonus"].get("dmg_reduction", 0.0) == pytest.approx(0.08)
        # 行为：敌方反打（atk 1000/scaling 1.0/fire）——res 0.8、def 0.5、未击破 0.9、
        # 期望暴击 1.025、减伤区 0.92 → 339.48
        e1, w = eng.state.actors["e1"], eng.state.actors["w"]
        act = next(a for a in eng.actions_by_actor["w"] if a.action_id == "t_basic")
        assert eng.pipeline.deal_damage(act, e1, w).value == pytest.approx(339.48)

    def test_2pc_no_4pc_heal(self):
        eng = _make("106", pieces=2)
        w = eng.state.actors["w"]
        w.current_hp = 1000.0
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert w.current_hp == 1000.0 and w.current_energy == 0.0, "2 件无 4pc 回血回能"

    def test_4pc_turn_start_heal_energy(self):
        eng = _make("106", pieces=4)
        w = eng.state.actors["w"]
        w.current_hp = 1000.0   # 33% ≤ 50% 触发
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert w.current_hp == pytest.approx(1240.0), "回血 = 3000×0.08×(1+0) = 240"
        assert w.current_energy == pytest.approx(5.0), "回能 5 点（ERR=1.0）"

    def test_4pc_hp_gate(self):
        eng = _make("106", pieces=4)
        w = eng.state.actors["w"]
        w.current_hp = 2000.0   # 67% > 50% 不触发
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert w.current_hp == 2000.0 and w.current_energy == 0.0
        # 敌方回合开始不触发（$event.actor 门）
        w.current_hp = 1000.0
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert w.current_hp == 1000.0


class TestRelic107Firesmith:
    """熔岩锻铸的火匠（107）：2pc 火伤+10%；4pc 战技增伤 12% + 终结技后下一击火伤 12%."""

    def test_2pc_fire_no_skill_boost(self):
        eng = _make("107", pieces=2, extra_actions=[_SKILL])
        assert _panel(eng)["dmg_bonus"].get("fire", 0.0) == pytest.approx(0.1)
        assert _cast(eng, "t_skill") == pytest.approx(1000.0 * 1.1 * Z), (
            "2 件战技只吃火伤桶 = 507.375（无战技增伤桶）")

    def test_4pc_skill_boost(self):
        eng = _make("107", pieces=4, extra_actions=[_SKILL, _ULT])
        assert _panel(eng)["dmg_bonus"].get("skill_dmg_boost", 0.0) == pytest.approx(0.12)
        assert _cast(eng, "t_skill") == pytest.approx(1000.0 * 1.22 * Z), (
            "战技 = 1000×(1+0.1+0.12)×0.5×0.9×1.025 = 562.725")

    def test_4pc_next_attack_fire_boost(self):
        eng = _make("107", pieces=4, extra_actions=[_SKILL, _ULT])
        assert _cast(eng, "t_basic") == pytest.approx(1000.0 * 1.1 * Z), "开大前普攻无 buff"
        _ult(eng)
        assert "SET_107_FIRE_DMG_NEXT_ATK" in eng.state.actors["w"].modifiers
        assert _cast(eng, "t_basic") == pytest.approx(1000.0 * 1.22 * Z), (
            "开大后下一击 = 1000×(1+0.1+0.12)×0.5×0.9×1.025 = 562.725")
        assert "SET_107_FIRE_DMG_NEXT_ATK" not in eng.state.actors["w"].modifiers, (
            "下一击结算后 buff 消费（tick_anchor on_action）")
        assert _cast(eng, "t_basic") == pytest.approx(1000.0 * 1.1 * Z), "第二击回归无 buff"


class TestRelic108GeniusOfStars:
    """繁星璀璨的天才（108）：2pc 量子+10%；4pc 无条件无视 10% 防御（量子弱点额外 10% 待收编）."""

    def test_2pc_quantum_no_def_pen(self):
        eng = _make("108", pieces=2, dmg_type="quantum")
        assert _panel(eng)["dmg_bonus"].get("quantum", 0.0) == pytest.approx(0.1)
        assert _panel(eng)["def_pen"] == pytest.approx(0.0), "2 件无防御无视"
        assert _cast(eng, "t_basic") == pytest.approx(1000.0 * 1.1 * Z)

    def test_4pc_def_pen(self):
        eng = _make("108", pieces=4, dmg_type="quantum")
        assert _panel(eng)["def_pen"] == pytest.approx(0.1)
        # 防御区 = 1000/(1000×0.9+1000) = 1000/1900
        assert _cast(eng, "t_basic") == pytest.approx(
            1000.0 * 1.1 * (1000.0 / 1900.0) * 0.9 * CZ), (
            "量子普攻 = 1100×(1000/1900)×0.9×1.025 = 534.079")


class TestRelic109SizzlingThunder:
    """激奏雷电的乐队（109）：2pc 雷伤+10%；4pc 施放战技后攻+20% 持续 1 回合."""

    def test_2pc_thunder_no_atk_buff(self):
        eng = _make("109", pieces=2, dmg_type="thunder",
                    extra_actions=[dict(_SKILL, damage_type="thunder")])
        assert _panel(eng)["dmg_bonus"].get("thunder", 0.0) == pytest.approx(0.1)
        _cast(eng, "t_skill")
        assert _panel(eng)["atk"] == pytest.approx(1000.0), "2 件战技不挂加攻"

    def test_4pc_atk_after_skill(self):
        eng = _make("109", pieces=4, dmg_type="thunder",
                    extra_actions=[dict(_SKILL, damage_type="thunder")])
        assert _cast(eng, "t_skill") == pytest.approx(1000.0 * 1.1 * Z), (
            "当次战技在 on_action（结算后）前出手——不自吃加攻（时序待实测见 fixture 头注）")
        mod = eng.state.actors["w"].modifiers.get("SET_109_4PC_ATK")
        assert mod is not None and mod.duration == 2, (
            "加攻 buff 已挂（duration 2 owner_turn_end = 覆盖至下回合末，勘正②）")
        assert _panel(eng)["atk"] == pytest.approx(1200.0), "atk = 1000×1.20"
        assert _cast(eng, "t_basic") == pytest.approx(1200.0 * 1.1 * Z), (
            "buff 后普攻 = 1200×1.1×0.5×0.9×1.025 = 608.85")
