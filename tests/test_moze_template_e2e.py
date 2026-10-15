"""貊泽 1223 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 猎物标记/
充能追击循环/Nightfeather SP/离场/星魂全链 → 手算全等.

过堂勘正四件（fixture 头注同录）：E1/E6/1223101 三翻案收录（gain_energy/
gain_skill_point/旗模式全在库）+ E2 待收挡因改写。

口径常数：貊泽白值 atk 599.76、crit 0.05/0.5（期望暴击区 1.025）；假人
def 0 → 防御区 0.5、雷弱点 → 抗性区 1.0、未击破 0.9。附加 lv10 #1=0.3、
追击 lv10 #3=1.6、E3 lv12 附加 0.33 追击 1.76。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

MZ_ATK = 599.76
Z = 0.5 * 0.9 * 1.025


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1223", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "thunder",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


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
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _mz(eng):
    return eng.state.actors["1223"]


def _cast_skill(eng):
    mz = _mz(eng)
    a = next(x for x in eng.actions_by_actor["1223"] if x.action_id == "122302")
    tgt = eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(mz, a)
    eng.bus.emit("on_action", {
        "actor": "1223", "action_type": "skill", "action_id": "122302",
        "target_type": "single", "target": "e1",
        "actor_type": mz.actor.actor_type}, eng.state)


def _ally_hit(eng):
    ally = eng.state.actors["ally"]
    a = next(x for x in eng.actions_by_actor["ally"] if x.action_id == "ally_basic")
    tgt = eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(ally, a)
    eng.bus.emit("on_action", {
        "actor": "ally", "action_type": "basic", "action_id": "ally_basic",
        "target_type": "single", "target": "e1",
        "actor_type": ally.actor.actor_type}, eng.state)


class TestMozeCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1223"]
        assert {"_prey_charge", "_prey_used", "_prey_active",
                "_e6_flag", "_nightfeather_cd"} <= set(decls)
        assert decls["_prey_charge"]["max"] == 9


class TestPrey:
    def test_skill_mark_and_departed(self, compiled):
        """战技：1.5 lv10 + 猎物标记+充能 9+离场标记."""
        eng = _make(compiled)
        mz = _mz(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast_skill(eng)
        assert math.isclose(hp1 - e1.current_hp, 1.5 * MZ_ATK * Z, rel_tol=1e-9)
        assert "PREY_MARK" in e1.modifiers
        assert math.isclose(mz.resources["_prey_charge"], 9.0)
        assert "MOZE_DEPARTED" in mz.modifiers

    def test_additional_and_pursuit_cycle(self, compiled):
        """附加循环：队友攻击猎物 → 附加 0.3（充能 −1、used+1）→ 每满 3 段追击 1.6 归 0."""
        eng = _make(compiled)
        mz = _mz(eng)
        e1 = eng.state.actors["e1"]
        _cast_skill(eng)
        ally_base = 1.0 * 1500 * Z
        add_one = 0.3 * MZ_ATK * Z
        # 击 1/2：仅附加
        hp1 = e1.current_hp
        _ally_hit(eng)
        assert math.isclose(hp1 - e1.current_hp, ally_base + add_one, rel_tol=1e-9)
        assert math.isclose(mz.resources["_prey_charge"], 8.0)
        assert math.isclose(mz.resources["_prey_used"], 1.0)
        _ally_hit(eng)
        assert math.isclose(mz.resources["_prey_used"], 2.0)
        # 击 3：附加+追击 1.6+used 归 0
        hp1 = e1.current_hp
        _ally_hit(eng)
        assert math.isclose(hp1 - e1.current_hp,
                            ally_base + add_one + 1.6 * MZ_ATK * Z, rel_tol=1e-9)
        assert math.isclose(mz.resources["_prey_used"], 0.0), "满 3 段追击后归 0"

    def test_nightfeather_sp_latch(self, compiled):
        """Nightfeather：追击后回 1 SP（闩只挡 SP 不挡追击本体）."""
        eng = _make(compiled)
        _cast_skill(eng)
        sp0 = eng.state.skill_points
        for _ in range(3):
            _ally_hit(eng)
        assert eng.state.skill_points == min(sp0 + 1, 5), "追击后回 1 SP"
        sp1 = eng.state.skill_points
        for _ in range(3):
            _ally_hit(eng)
        assert eng.state.skill_points == sp1, "闩内不再回 SP（追击本体照样触发）"

    def test_charge_exhaust_cleanup(self, compiled):
        """充能耗尽：摘猎物+摘离场+拉条 20%+active 落 0."""
        eng = _make(compiled)
        mz = _mz(eng)
        e1 = eng.state.actors["e1"]
        _cast_skill(eng)
        mz.resources["_prey_charge"] = 1.0
        _ally_hit(eng)
        assert "PREY_MARK" not in e1.modifiers
        assert "MOZE_DEPARTED" not in mz.modifiers
        assert math.isclose(mz.resources["_prey_active"], 0.0)


class TestEidolons:
    def test_e1_energy(self):
        """E1：进战 20 能 + 附加段回 2 能."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        mz = _mz(eng)
        assert math.isclose(mz.current_energy, 20.0)
        _cast_skill(eng)
        e0 = mz.current_energy
        _ally_hit(eng)
        assert math.isclose(mz.current_energy, e0 + 2.0)

    def test_e4_ult_dmg(self):
        """E4：施放终结技后 all_dmg+30% 2 回合."""
        eng = _make(compile_encounter(_build(eidolon=4), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        mz = _mz(eng)
        mz.current_energy = 120.0
        ult = next(x for x in eng.actions_by_actor["1223"] if x.action_id == "122303")
        assert eng._fire_ultimate(mz, ult) is True
        assert math.isclose(
            eng.pipeline.effective_stats(mz)["dmg_bonus"].get("all", 0.0),
            0.3, rel_tol=1e-9)

    def test_e6_pursuit_amplified(self):
        """E6：追击 ×1.25 旗模式——E3 联动 lv12（附加 0.33/追击 1.76）全对轴."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        mz = _mz(eng)
        e1 = eng.state.actors["e1"]
        _cast_skill(eng)
        assert math.isclose(mz.resources["_e6_flag"], 1.0)
        ally_base = 1.0 * 1500 * Z
        for _ in range(2):
            _ally_hit(eng)
        hp1 = e1.current_hp
        _ally_hit(eng)
        # 第 3 击：附加 0.33（lv12）+ 追击 1.76×1.25（旗）
        assert math.isclose(
            hp1 - e1.current_hp,
            ally_base + 0.33 * MZ_ATK * Z + 1.76 * 1.25 * MZ_ATK * Z, rel_tol=1e-9)


class TestTechnique:
    def test_tech_dmg_up(self):
        """秘技：all_dmg+30% 2 回合."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1223", "technique": "122307"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        assert math.isclose(
            eng.pipeline.effective_stats(_mz(eng))["dmg_bonus"].get("all", 0.0),
            0.3, rel_tol=1e-9)
