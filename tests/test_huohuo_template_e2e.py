"""藿藿 1217 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 战技治疗/
天赋 Divine Provision 链/终结技排自身/E2 免死/星魂全链 → 手算全等.

过堂勘正七件+引擎补口两件（fixture 头注同录）：ally_single / 控制特化抵抗
删件 / 回能天赋链限定 / E2 set_hp+cancel 序 / 终结技排自身代数 / E1 跨人 /
能量上限命名空间键 / gain_energy 代数接线 / set_hp target 通道。

口径常数：藿藿白值 hp 1358.28、spd 100；辅手 hp 3000、max_energy 100。
战技 lv10：主目标 0.24×HP+640；天赋 lv10：治疗 0.045×HP+120、触发 6 次、
阈值 0.5；终结技 lv10：除自身按 Max Energy 20% 回能。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

HH_HP = 1358.28


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1217", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "wind",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["wind"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _hh(eng):
    return eng.state.actors["1217"]


def _cast_skill(eng, target_id="ally"):
    hh = _hh(eng)
    a = next(x for x in eng.actions_by_actor["1217"] if x.action_id == "1121702")
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(hh, a)
    eng.bus.emit("on_action", {
        "actor": "1217", "action_type": "skill", "action_id": "1121702",
        "target_type": "ally_single", "target": tgt.actor.actor_id,
        "actor_type": hh.actor.actor_type}, eng.state)


class TestHuohuoCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1217"]
        assert {"divine_provision", "divine_trigger_count", "_e2_used"} <= set(decls)

    def test_battle_start(self, compiled):
        """Fearful to Act：进战 +30 能 + provision 2 回合 + 触发 6 次."""
        eng = _make(compiled)
        hh = _hh(eng)
        assert math.isclose(hh.current_energy, 30.0)
        assert math.isclose(hh.resources["divine_provision"], 2.0)
        assert math.isclose(hh.resources["divine_trigger_count"], 6.0)


class TestSkill:
    def test_skill_heal_and_provision(self, compiled):
        """战技：主目标 0.24×HP+640（lv10）+ provision 3 回合（获后重置触发 6 次）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        hh = _hh(eng)
        ally.current_hp = 1000.0
        ally.modifiers["D1"] = Modifier(
            modifier_id="D1", name="负面", modifier_type="debuff", duration=2)
        _cast_skill(eng)
        assert math.isclose(ally.current_hp,
                            1000 + 0.24 * HH_HP + 640, rel_tol=1e-9)
        assert "D1" not in ally.modifiers, "净化 1（LIFO）"
        assert math.isclose(hh.resources["divine_provision"], 2 + 3.0), (
            "加强版战技获 provision 3 回合")
        assert math.isclose(hh.resources["divine_trigger_count"], 6.0), "重置触发次数"


class TestTalentProvision:
    def test_turn_start_heal_chain(self, compiled):
        """天赋：友方回合开始三批治疗（本目标+最低 HP% 批+≤50% 批）+按目标计回能."""
        eng = _make(compiled)
        hh = _hh(eng)
        ally = eng.state.actors["ally"]
        ally.current_hp = 1000.0   # 33% ≤50%——三批全中（不去重在案）
        hh.current_energy = 50.0
        heal_one = 0.045 * HH_HP + 120
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        assert math.isclose(ally.current_hp, 1000 + 3 * heal_one, rel_tol=1e-9)
        assert math.isclose(hh.current_energy, 53.0), "11217103 按目标计 3 能"
        assert math.isclose(hh.resources["divine_trigger_count"], 5.0), "触发次数 −1"

    def test_provision_countdown(self, compiled):
        """provision 倒计时：藿藿回合开始 −1."""
        eng = _make(compiled)
        hh = _hh(eng)
        eng.bus.emit("on_turn_start", {"actor": "1217"}, eng.state)
        assert math.isclose(hh.resources["divine_provision"], 1.0)


class TestUltimate:
    def test_ult_exclude_self(self, compiled):
        """终结技：除自身按 Max Energy 20% 回能（代数排自身）+除自身 ATK+40% 2 回合."""
        eng = _make(compiled)
        hh = _hh(eng)
        ally = eng.state.actors["ally"]
        hh.current_energy = 140.0
        ally.current_energy = 0.0
        ult = next(x for x in eng.actions_by_actor["1217"] if x.action_id == "1121703")
        assert eng._fire_ultimate(hh, ult) is True
        assert math.isclose(ally.current_energy, 0.2 * 100, rel_tol=1e-9), (
            "$target.max_energy 命名空间急切字段")
        assert math.isclose(hh.current_energy, 5 + 3.0), (
            "藿藿只基础 5（排自身）+天赋触发半②三批回 3")
        assert "TAIL_ATK_BUFF" in ally.modifiers
        assert "TAIL_ATK_BUFF" not in hh.modifiers, "ATK 增益同排自身"


class TestEidolons:
    def test_e1_spd_cross_actor(self):
        """E1：provision 在场全队 SPD+12%（resource_of 跨人门控）——耗尽即失效."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        hh = _hh(eng)
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["spd"],
                            90 * 1.12, rel_tol=1e-9)
        hh.resources["divine_provision"] = 0.0
        assert math.isclose(eng.pipeline.effective_stats(ally)["spd"], 90.0), (
            "provision 耗尽即失效（跨人门控动态）")

    def test_e2_death_save_set_hp(self):
        """E2 免死：cancel+set HP 50%（set 语义不超出）+provision−1+每场 2 闩+藿藿不自残."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        hh = _hh(eng)
        ally = eng.state.actors["ally"]
        hh_hp0 = hh.current_hp
        ally.current_hp = 400.0
        wp = eng.bus.waterfall("before_take_damage", {
            "amount": 9999.0, "damage_type": "wind", "source": "e1",
            "target": "ally", "action_type": "basic", "is_critical": False}, eng.state)
        assert wp.get("cancel") is True
        assert math.isclose(ally.current_hp, 1500.0, rel_tol=1e-9), "set 50%（非 heal 加算）"
        assert math.isclose(hh.current_hp, hh_hp0), "set 作用于目标——藿藿不自残（引擎补口 B）"
        assert math.isclose(hh.resources["divine_provision"], 1.0)
        assert math.isclose(hh.resources["_e2_used"], 1.0)
        # 满血被秒同 set 50%（不超出）；第 2 次后闩
        ally.current_hp = 3000.0
        wp2 = eng.bus.waterfall("before_take_damage", {
            "amount": 9999.0, "damage_type": "wind", "source": "e1",
            "target": "ally", "action_type": "basic", "is_critical": False}, eng.state)
        assert math.isclose(ally.current_hp, 1500.0, rel_tol=1e-9), "满血被秒同 set 50%"
        ally.current_hp = 100.0
        wp3 = eng.bus.waterfall("before_take_damage", {
            "amount": 9999.0, "damage_type": "wind", "source": "e1",
            "target": "ally", "action_type": "basic", "is_critical": False}, eng.state)
        assert not wp3.get("cancel"), "每场 2 次闩后不再救"

    def test_e6_heal_dmg_up(self):
        """E6：治疗目标伤害 +50% 2 回合（挂被治疗者）."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        ally = eng.state.actors["ally"]
        ally.current_hp = 1000.0
        _cast_skill(eng)
        assert "E6_HEAL_DMG" in ally.modifiers
        assert math.isclose(
            eng.pipeline.effective_stats(ally)["dmg_bonus"].get("all", 0.0),
            0.5, rel_tol=1e-9)


class TestTechnique:
    def test_tech_atk_down(self):
        """秘技：进战全体 ATK−25% 2 回合."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1217", "technique": "1121707"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        e1 = eng.state.actors["e1"]
        assert "HORROR_STRUCK" in e1.modifiers
        assert math.isclose(eng.pipeline.effective_stats(e1)["atk"],
                            1000 * 0.75, rel_tol=1e-9)
