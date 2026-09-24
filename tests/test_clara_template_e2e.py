"""克拉拉 1107 模板端到端对轴（验收型批·组2）：真模板 YAML → 编译 → 反击链/
强化反击/标记循环/减伤堆叠/星魂全链 → 手算全等.

过堂六件（fixture 头注同录）：chance→mechanic_chance / dmg_dmg_reduction 路由 /
反击回能收编 / E1 marker 门控 / 嘲讽 aggro_boost 疑读 / duration 纪律。

口径常数：克拉拉白值 atk 737.352、def 485.1、hp 1241.856、crit 0.05/0.5
（期望暴击区 1.025）；行迹 atk+28%/物理+14.4%（B-TR② 已回填——面板 943.81056、
增伤池 1.144）；假人 def 0 → 防御区 0.5、物理弱点 → 抗性区 1.0、未击破 0.9。
天赋反击倍率 1.3×param(110704,2) lv10=1.3×1.6=2.08；强化反击 1.3×(1.6+1.6)=4.16。
普攻 lv6=1.0。A1 mechanic_chance(0.35)<0.5 → expected 恒不生效（在案）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

CL_ATK = 737.352
CL_EFF = CL_ATK * 1.28                        # 943.81056（B-TR② 行迹 atk 0.28 回填后面板）
PHYS = 0.144                                  # 物理行迹增伤池（B-TR②）
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
COUNTER = 1.3 * 1.6          # 天赋反击 lv10
ENH_COUNTER = 1.3 * (1.6 + 1.6)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1107", "level": 80}
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


def _cl(eng):
    return eng.state.actors["1107"]


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


def _hit_clara(eng, source="e1"):
    eng.bus.emit("after_being_hit", {
        "target": "1107", "source": source, "amount": 100.0,
        "action_type": "basic", "damage_type": "physical"}, eng.state)


def _hit_ally(eng, source="e1"):
    eng.bus.emit("after_being_hit", {
        "target": "ally", "source": source, "amount": 100.0,
        "action_type": "basic", "damage_type": "physical"}, eng.state)


class TestClaraCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1107"]}
        assert acts["110704"].action_type == "follow_up"
        assert compiled.resource_decls_by_actor["1107"]["_enh_counter_left"]["max"] == 5


class TestTalentCounter:
    def test_counter_mark_damage_energy(self, compiled):
        """天赋反击：受击 → 攻击者挂标记 + 2.08×ATK 反击 + 回能 5（收编实证）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _hit_clara(eng)
        assert "MARK_OF_COUNTER" in e1.modifiers
        assert math.isclose(hp1 - e1.current_hp, COUNTER * CL_EFF * Z * (1 + PHYS), rel_tol=1e-9)
        assert math.isclose(_cl(eng).current_energy, 5.0), "反击回能 5（gain_energy 收编）"

    def test_skill_bonus_and_mark_clear(self, compiled):
        """战技：AoE 1.2 双敌 + 标记者追加 1.2 + 施放后清标记（E0 口径）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _hit_clara(eng)   # e1 挂标记
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1107", "110702")
        assert math.isclose(hp1 - e1.current_hp, (1.2 + 1.2) * CL_EFF * Z * (1 + PHYS),
                            rel_tol=1e-9), "e1 = 主段 + 标记追加段"
        assert math.isclose(hp2 - e2.current_hp, 1.2 * CL_EFF * Z * (1 + PHYS), rel_tol=1e-9), (
            "e2 仅主段")
        assert "MARK_OF_COUNTER" not in e1.modifiers, "E0 施放后清标记"


class TestUltimate:
    def test_ult_enhanced_counter(self, compiled):
        """大招：减伤 25%+嘲讽 aggro 5.0 二回合 + 强化反击装填 2——任意我方受击
        4.16×ATK 反击耗 1 次；普通反击互斥不发."""
        eng = _make(compiled)
        m7 = _cl(eng)
        m7.current_energy = 110.0
        ult = next(a for a in eng.actions_by_actor["1107"] if a.action_id == "110703")
        assert eng._fire_ultimate(m7, ult) is True
        buff = m7.modifiers["CLARA_ULT"]
        assert math.isclose(buff.stat_effects["dmg_dmg_reduction"], 0.25, rel_tol=1e-9)
        assert math.isclose(buff.stat_effects["aggro_boost"], 5.0)
        assert math.isclose(m7.resources["_enh_counter_left"], 2.0)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _hit_ally(eng)   # 辅手受击也触发强化反击
        assert math.isclose(hp1 - e1.current_hp, ENH_COUNTER * CL_EFF * Z * (1 + PHYS),
                            rel_tol=1e-9)
        assert math.isclose(m7.resources["_enh_counter_left"], 1.0)
        hp1 = e1.current_hp
        _hit_clara(eng)   # 克拉拉受击：强化（耗 1）非普通（互斥）
        assert math.isclose(hp1 - e1.current_hp, ENH_COUNTER * CL_EFF * Z * (1 + PHYS),
                            rel_tol=1e-9)
        assert math.isclose(_cl(eng).current_energy, 5.0), (
            "强化反击不吃天赋回能段（普通反击互斥——强化回能档待实测在案）")

    def test_damage_reduction_zone(self, compiled):
        """减伤堆叠：天赋 10%×大招 25% 乘算 → 区 1−(1−0.325)=0.675（引擎 product
        折叠修复实证——rulebook 注释 ∏(1-x_i) 口径，曾加算 0.65）；全链 =
        1000×def_multi×res 0.8×未击破 0.9×期望暴击 1.025×0.675."""
        eng = _make(compiled)
        m7 = _cl(eng)
        m7.current_energy = 110.0
        ult = next(a for a in eng.actions_by_actor["1107"] if a.action_id == "110703")
        assert eng._fire_ultimate(m7, ult) is True
        from hsr_nous.sim_schema.action import Action
        eng.actions_by_actor = {**eng.actions_by_actor, "e1": [Action(
            action_id="e_hit", name="重击", action_type="basic", target_type="single",
            damage_type="physical", scaling=[{"atk": 1.0}])]}
        eng._pick_ally_target = lambda attacker=None: m7
        hp0 = m7.current_hp
        eng._enemy_turn(eng.state.actors["e1"])
        def_multi = 1 - 485.1 / (485.1 + 1000.0)
        assert math.isclose(hp0 - m7.current_hp,
                            1000 * def_multi * 0.8 * 0.9 * 1.025 * 0.675, rel_tol=1e-9)


class TestEidolons:
    def test_e1_marks_kept(self):
        """E1：战技后标记保留（marker 门控收编——draft 曾标注 E1 未生效偏低修正点）."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _hit_clara(eng)
        _cast(eng, "1107", "110702")
        assert "MARK_OF_COUNTER" in e1.modifiers, "E1 不再移除标记"

    def test_e2_atk_buff(self):
        """E2：大招后 ATK +30% 二回合."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        m7 = _cl(eng)
        m7.current_energy = 110.0
        ult = next(a for a in eng.actions_by_actor["1107"] if a.action_id == "110703")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(eng.pipeline.effective_stats(m7)["atk"], CL_ATK * (1 + 0.28 + 0.30),
                            rel_tol=1e-9), "E2 atk_pct 0.30 与行迹 0.28 同池加算（×白值）"

    def test_e6_ally_hit_counter_and_charges(self):
        """E6①：队友受击 50% 反击（expected 恒中——mechanic_chance(0.5)）；非强化口径
        1.3×param(110704,2)（E5 天赋 lv12=1.76 联动）；E6②：强化装填 2+1=3."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _hit_ally(eng)
        assert math.isclose(hp1 - e1.current_hp, 1.3 * 1.76 * CL_EFF * Z * (1 + PHYS),
                            rel_tol=1e-9), "E5 天赋 lv12=1.76 → 反击 1.3×1.76=2.288"
        m7 = _cl(eng)
        m7.current_energy = 110.0
        ult = next(a for a in eng.actions_by_actor["1107"] if a.action_id == "110703")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(m7.resources["_enh_counter_left"], 3.0)

    def test_a1_cleanse_expected_off(self, compiled):
        """A1：受击 35% 驱散——expected 口径 <0.5 恒不生效（mechanic_chance 双态钉死）."""
        eng = _make(compiled)
        a = _cl(eng)
        eng._apply_modifier(a, Modifier(
            modifier_id="D1", name="负面", modifier_type="debuff", duration=2))
        _hit_clara(eng)
        assert "D1" in a.modifiers, "expected 口径 A1 不生效（roll 模式 35% 真掷）"
