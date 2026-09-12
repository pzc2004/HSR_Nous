"""白露 1211 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 三跳治疗/
生息受击奶/免死 cancel/A2 溢出联动/星魂全链 → 手算全等.

过堂勘正四件+引擎补口一件（fixture 头注同录）：on_hp_increase 载荷 enrich
（excess+action_id）/ 死键三件（dmg_dmg_reduction/hp_pct/heal_bonus）/
A2 溢出语义（excess>0）/ E4 action_id 通道。

口径常数：白露天白值 hp 1319.472、spd 100；辅手 hp 3000。
战技 lv10 [0.117, 312]、大招 lv10 [0.135, 360]、受击奶 lv10 [0.054, 144]、
免死 lv10 [0.18, 480]。A2 挂后白露 HP 1451.42（×1.1）——治疗基数联动钉。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

BL_HP = 1319.472


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1211", "level": 80}
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
     "max_toughness": 9999, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _bl(eng):
    return eng.state.actors["1211"]


def _cast_skill(eng, target_id="ally"):
    bl = _bl(eng)
    a = next(x for x in eng.actions_by_actor["1211"] if x.action_id == "121102")
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(bl, a)
    eng.bus.emit("on_action", {
        "actor": "1211", "action_type": "skill", "action_id": "121102",
        "target_type": "single", "target": tgt.actor.actor_id,
        "actor_type": bl.actor.actor_type}, eng.state)


class TestBailuCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1211"]
        assert {"_inv_heal_left", "_revive_left"} <= set(decls)


class TestSkillHeal:
    def test_three_bounce_heal(self, compiled):
        """战技三跳：首跳指定 0.117×HP+312（lv10）；随机跳 B22 确定化序首=白露 ×0.85 递减."""
        eng = _make(compiled)
        bl, ally = _bl(eng), eng.state.actors["ally"]
        ally.current_hp = 1000.0
        bl.current_hp = 500.0
        _cast_skill(eng)
        first = 0.117 * BL_HP + 312   # 466.38
        assert math.isclose(ally.current_hp, 1000 + first, rel_tol=1e-9)
        # 随机两跳确定化序首=1211：×0.85 / ×0.7225
        assert math.isclose(bl.current_hp,
                            500 + first * 0.85 + first * 0.7225, rel_tol=1e-9), (
            "B22 确定化同序首 + 逐跳 −15% 递减")


class TestUltimateInvigoration:
    def test_ult_heal_and_invigoration(self, compiled):
        """大招全队 0.135×HP+360（lv10）+ 生息/计数 3 + 减伤 10%（dmg_dmg_reduction 键）."""
        eng = _make(compiled)
        bl, ally = _bl(eng), eng.state.actors["ally"]
        bl.current_hp = BL_HP   # 满血防 A2 干扰本例基数
        ally.current_hp = 1000.0
        bl.current_energy = 100.0
        ult = next(x for x in eng.actions_by_actor["1211"] if x.action_id == "121103")
        assert eng._fire_ultimate(bl, ult) is True
        # 白露满血溢出仍触发 A2（excess>0——联动：ally 后吃按新基数 1451.42）
        assert "QIHUANG_MAX_HP" in bl.modifiers
        assert math.isclose(ally.current_hp,
                            1000 + 0.135 * BL_HP * 1.1 + 360, rel_tol=1e-9), (
            "A2 治疗基数联动：奶序池首白露溢出挂→ally 按新上限")
        assert "INVIGORATION" in ally.modifiers
        assert ally.modifiers["INV_HEAL_COUNT"].stacks == 3
        assert math.isclose(
            eng.pipeline.effective_stats(ally)["dmg_bonus"].get("dmg_reduction", 0.0),
            0.1, rel_tol=1e-9), "A6 减伤并入生息件（dmg_dmg_reduction 键）"

    def test_invigoration_hit_heal(self, compiled):
        """生息受击奶：0.054×HP+144（lv10）+ 计数递减；计数尽不触发."""
        eng = _make(compiled)
        bl, ally = _bl(eng), eng.state.actors["ally"]
        bl.current_hp = BL_HP
        bl.current_energy = 100.0
        ult = next(x for x in eng.actions_by_actor["1211"] if x.action_id == "121103")
        eng._fire_ultimate(bl, ult)
        # A2 已挂（大招溢出）——受击奶基数 1451.42
        ally.current_hp = 1000.0
        eng.bus.emit("on_hp_decrease", {"amount": 300.0, "source": "e1", "reason": "hit",
                                        "target": "ally", "damage_type": "thunder",
                                        "action_type": "basic"}, eng.state)
        assert math.isclose(ally.current_hp,
                            1000 + 0.054 * BL_HP * 1.1 + 144, rel_tol=1e-9)
        assert ally.modifiers["INV_HEAL_COUNT"].stacks == 2


class TestRevive:
    def test_death_save_cancel(self, compiled):
        """免死：队友致死 cancel 伤害 + 回 0.18×HP+480（lv10）；每场 1 次闩；排自在案."""
        eng = _make(compiled)
        bl, ally = _bl(eng), eng.state.actors["ally"]
        ally.current_hp = 400.0
        wp = eng.bus.waterfall("before_take_damage", {
            "amount": 9999.0, "damage_type": "thunder", "source": "e1",
            "target": "ally", "action_type": "basic", "is_critical": False}, eng.state)
        assert wp.get("cancel") is True, "致死 cancel 伤害本身"
        assert math.isclose(ally.current_hp, 400 + 0.18 * BL_HP + 480, rel_tol=1e-9)
        assert math.isclose(bl.resources["_revive_left"], 0.0)
        ally.current_hp = 100.0
        wp2 = eng.bus.waterfall("before_take_damage", {
            "amount": 9999.0, "damage_type": "thunder", "source": "e1",
            "target": "ally", "action_type": "basic", "is_critical": False}, eng.state)
        assert not wp2.get("cancel"), "闩后不再救"
        bl.current_hp = 100.0
        wp3 = eng.bus.waterfall("before_take_damage", {
            "amount": 9999.0, "damage_type": "thunder", "source": "e1",
            "target": "1211", "action_type": "basic", "is_critical": False}, eng.state)
        assert not wp3.get("cancel"), "teammate 排自（在案）"


class TestA2Overflow:
    def test_overflow_only(self, compiled):
        """A2：满血被奶挂 hp_pct+10%；残血奶满溢出同挂（excess>0 官方语义）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]   # 满血 3000
        _cast_skill(eng)
        assert "QIHUANG_MAX_HP" in ally.modifiers, "满血溢出奶触发（excess>0）"
        assert math.isclose(eng.pipeline.effective_stats(ally)["hp"], 3300.0, rel_tol=1e-9)
        ally.modifiers.pop("QIHUANG_MAX_HP", None)
        ally.current_hp = 2950.0   # 残血：拟回 466.38 超 50 差值 → excess>0
        _cast_skill(eng)
        assert "QIHUANG_MAX_HP" in ally.modifiers, "残血奶满溢出同挂（官方语义）"


class TestEidolons:
    def test_e2_heal_bonus(self):
        """E2：终结技后 heal_bonus +15% 2 回合."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        bl = _bl(eng)
        assert math.isclose(eng.pipeline.effective_stats(bl).get("heal_bonus", 0.0), 0.0)
        bl.current_energy = 100.0
        ult = next(x for x in eng.actions_by_actor["1211"] if x.action_id == "121103")
        eng._fire_ultimate(bl, ult)
        assert math.isclose(eng.pipeline.effective_stats(bl).get("heal_bonus", 0.0),
                            0.15, rel_tol=1e-9)

    def test_e4_skill_heal_only(self):
        """E4：战技奶目标增伤 10% 叠层（action_id 透传限定）；大招奶不挂."""
        eng = _make(compile_encounter(_build(eidolon=4), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        bl, ally = _bl(eng), eng.state.actors["ally"]
        ally.current_hp = 1000.0
        _cast_skill(eng)
        assert "E4_EVIL_EXCISION" in ally.modifiers, "战技奶挂（三跳同带 121102）"
        ally.modifiers.pop("E4_EVIL_EXCISION", None)
        ally.current_hp = 1000.0
        bl.current_energy = 100.0
        ult = next(x for x in eng.actions_by_actor["1211"] if x.action_id == "121103")
        eng._fire_ultimate(bl, ult)
        assert "E4_EVIL_EXCISION" not in ally.modifiers, "大招奶不挂（action_id 分辨）"

    def test_e6_revive_plus_one(self):
        """E6：免死 +1 次（开局 2 次）."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        assert math.isclose(_bl(eng).resources["_revive_left"], 2.0)


class TestTechnique:
    def test_pre_battle_invigoration(self):
        """秘技：进战全体生息 2 回合 + 受击奶计数 3."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1211", "technique": "121107"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        ally = eng.state.actors["ally"]
        assert "INVIGORATION" in ally.modifiers
        assert ally.modifiers["INV_HEAL_COUNT"].stacks == 3
