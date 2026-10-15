"""雪衣 1214 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 业报循环/
明察动态/追击/星魂全链 → 手算全等.

过堂勘正五件+回滚一件（fixture 头注同录）：_karma_cap 初始化 / 明察 stat_exprs
动态 / E1 follow_up 桶 / 追击回能翻案 / 灼见主机记账池删除 / 触发判定 +1
回滚（emit 快照语义钉）。

口径常数：雪衣白值 atk 599.76、spd 103、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、量子弱点 → 抗性区 1.0、未击破 0.9。
追击 lv10 #2=0.9×3 弹射；业报 cap 8（E6=6）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

XY_ATK = 599.76
Z = 0.5 * 0.9 * 1.025


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1214", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member],
         "policy": {"name": "p", "action_rules": [
             {"condition": "true", "action": "skill", "priority": 50},
             {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


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


def _xy(eng):
    return eng.state.actors["1214"]


def _toughness_hit(eng, source="1214"):
    eng.bus.emit("on_toughness_damage", {"amount": 20.0, "bar_index": 0,
                                         "source": source, "target": "e1"}, eng.state)


class TestXueyiCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1214"]
        assert decls["_karma"]["max"] == 8
        assert "_karma_cap" not in decls and "_karma_overflow" not in decls, (
            "上限字面化+记账池删除（装填钩序病/只进不出双案在案）")


class TestSkill:
    def test_skill_blast(self, compiled):
        """战技：主 1.4 邻 0.7 lv10 对轴."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        xy = _xy(eng)
        a = next(x for x in eng.actions_by_actor["1214"] if x.action_id == "121402")
        tgt = e1
        eng.decision.select_target = lambda actor_state, action_type, candidates, engine: tgt
        hp1, hp2 = e1.current_hp, e2.current_hp
        eng._execute_action(xy, a)
        assert math.isclose(hp1 - e1.current_hp, 1.4 * XY_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.7 * XY_ATK * Z, rel_tol=1e-9)


class TestKarma:
    def test_karma_cycle_snapshot(self, compiled):
        """业报循环：7 次未触发 → 第 8 次触发 3 弹射+消耗清零+回能 2 → 第 9 次不触发（快照语义钉）."""
        eng = _make(compiled)
        xy = _xy(eng)
        e1 = eng.state.actors["e1"]
        for _ in range(7):
            _toughness_hit(eng)
        assert math.isclose(xy.resources["_karma"], 7.0)
        assert math.isclose(e1.current_hp, 1e9), "7 次未触发（快照 7+1<8）"
        xy.current_energy = 50.0
        _toughness_hit(eng)
        assert math.isclose(xy.resources["_karma"], 0.0), "消耗全部业报"
        assert math.isclose(1e9 - e1.current_hp, 3 * 0.9 * XY_ATK * Z, rel_tol=1e-9), (
            "3 弹射 ×0.9 确定化同序首")
        assert math.isclose(xy.current_energy, 52.0), "追击回能 +2"
        hp1 = e1.current_hp
        _toughness_hit(eng)
        assert math.isclose(xy.resources["_karma"], 1.0)
        assert math.isclose(e1.current_hp, hp1), "第 9 次快照 1+1<8 不触发"

    def test_karma_ally_source_counts(self, compiled):
        """队友削韧同计（官方「我方目标」域）；敌方不触发."""
        eng = _make(compiled)
        xy = _xy(eng)
        xy.resources["_karma"] = 7.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _toughness_hit(eng, source="ally")   # 队方非怪物源
        assert math.isclose(xy.resources["_karma"], 0.0), "队友削韧达上限同触发"
        assert (1e9 - e1.current_hp) > 0
        xy.resources["_karma"] = 7.0
        hp1 = e1.current_hp
        _toughness_hit(eng, source="e2")     # 怪物源不计
        assert math.isclose(e1.current_hp, hp1), "敌方削韧不计"


class TestClairvoyant:
    def test_be_dynamic(self, compiled):
        """明察：增伤=100%×BE cap 240%——stat_exprs 动态（E4 BE 挂后自动跟随）."""
        eng = _make(compiled)
        xy = _xy(eng)
        assert math.isclose(
            eng.pipeline.effective_stats(xy)["dmg_bonus"].get("all", 0.0), 0.0), "BE=0 基线"
        xy.modifiers["E4_BREAK_EFFECT"] = Modifier(
            modifier_id="E4_BREAK_EFFECT", name="t", modifier_type="buff", duration=2,
            stat_effects={"break_effect": 0.4})
        assert math.isclose(
            eng.pipeline.effective_stats(xy)["dmg_bonus"].get("all", 0.0), 0.4, rel_tol=1e-9), (
            "stat_exprs 动态重估（一次性烘焙旧案已废）")
        xy.modifiers["E4_BREAK_EFFECT"].stat_effects["break_effect"] = 3.0
        assert math.isclose(
            eng.pipeline.effective_stats(xy)["dmg_bonus"].get("all", 0.0), 2.4, rel_tol=1e-9), (
            "cap 240% 上限")


class TestUltimate:
    def test_ult_damage(self, compiled):
        """大招：2.5 lv10 对轴 + toughness_scope all（无视弱点削韧）."""
        eng = _make(compiled)
        xy = _xy(eng)
        xy.current_energy = 120.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        ult = next(x for x in eng.actions_by_actor["1214"] if x.action_id == "121403")
        assert eng._fire_ultimate(xy, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 2.5 * XY_ATK * Z, rel_tol=1e-9)


class TestEidolons:
    def test_e1_followup_boost(self):
        """E1：追击增伤 40% 归 follow_up 类型桶（明察共存不重复乘算）."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        xy = _xy(eng)
        xy.resources["_karma"] = 7.0
        e1 = eng.state.actors["e1"]
        _toughness_hit(eng)
        assert math.isclose(1e9 - e1.current_hp,
                            3 * 0.9 * XY_ATK * Z * 1.4, rel_tol=1e-9)

    def test_e2_followup_heal(self):
        """E2：追击后自回 5%×MaxHP（整套一次粒度在案）."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        xy = _xy(eng)
        xy.resources["_karma"] = 7.0
        xy.current_hp = 500.0
        _toughness_hit(eng)
        assert math.isclose(xy.current_hp,
                            500 + 0.05 * eng.pipeline.effective_stats(xy)["hp"], rel_tol=1e-9)

    def test_e6_cap_six(self):
        """E6：业报 cap 6——第 6 次即触发."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        xy = _xy(eng)
        e1 = eng.state.actors["e1"]
        for _ in range(5):
            _toughness_hit(eng)
        assert math.isclose(e1.current_hp, 1e9), "5 次未触发"
        _toughness_hit(eng)
        assert math.isclose(xy.resources["_karma"], 0.0), "第 6 次触发消耗"
        assert (1e9 - e1.current_hp) > 0


class TestTechnique:
    def test_tech_aoe(self):
        """秘技：全体 80% ATK + 削韧 20."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1214", "technique": "121407"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        assert math.isclose(1e9 - e1.current_hp, 0.8 * XY_ATK * Z, rel_tol=1e-9)
        assert math.isclose(1e9 - e2.current_hp, 0.8 * XY_ATK * Z, rel_tol=1e-9)
