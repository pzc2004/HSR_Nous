"""椒丘 1218 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 烬煨层数驱动/
灼烧/鼎阵结界/终伤易伤 scoped/星魂全链 → 手算全等.

过堂勘正六件+引擎补口一件（fixture 头注同录）：VULN 双勘正（vulnerability+
stat_exprs）/ 终伤易伤 hit_condition / chance×3 / E1 ×1.4 跨人 / E6 待收 /
承伤区 scoped 补口。

口径常数：椒丘白值 atk 601.524、spd 98+行迹 5=103、crit 0.05/0.5（期望暴击区
1.025）；行迹火伤 0.144（增伤池 1.144——B-TR④ 回填：EHR 0.28/火 0.144/spd+5
官方十节点聚合，EHR 不到 1218102 门控不伤直伤）；假人 def 0 → 防御区 0.5、
火弱点 → 抗性区 1.0、未击破 0.9。
烬煨易伤 lv10：0.15+(N−1)×0.05；灼烧 lv10 #6=1.8×atk；终伤易伤 lv10=0.15。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

JQ_ATK = 601.524
Z_FIRE = 0.5 * 0.9 * 1.025 * 1.144   # 防御区×未击破×期望暴击×增伤池（行迹火 0.144——B-TR④）


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1218", "level": 80}
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
     "max_toughness": 9999, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _jq(eng):
    return eng.state.actors["1218"]


def _cast(eng, aid, target_id="e1"):
    jq = _jq(eng)
    a = next(x for x in eng.actions_by_actor["1218"] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(jq, a)
    eng.bus.emit("on_action", {
        "actor": "1218", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": jq.actor.actor_type}, eng.state)


class TestJiaoqiuCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1218"]
        assert decls["_zone_proc"]["max"] == 6

    def test_pyre_cleanse(self, compiled):
        """Pyre Cleanse：进战 +15 能."""
        assert math.isclose(_make(compiled).state.actors["1218"].current_energy, 15.0)


class TestAshenRoast:
    def test_skill_blast_and_roast(self, compiled):
        """战技：主 1.5 邻 0.9 lv10 对轴 + 烬煨 1 层+灼烧+易伤件挂上."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "121802")
        assert math.isclose(hp1 - e1.current_hp, 1.5 * JQ_ATK * Z_FIRE, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.9 * JQ_ATK * Z_FIRE, rel_tol=1e-9)
        assert e1.modifiers["ASHEN_ROAST"].stacks == 1
        assert "ASHEN_BURN" in e1.modifiers
        assert "ASHEN_VULN" in e1.modifiers

    def test_vuln_stacks_dynamic(self, compiled):
        """易伤层数驱动（stat_exprs 动态——读敌方层数）：1 层 0.15 → 2 层 0.20."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _cast(eng, "121802")
        assert math.isclose(eng.pipeline.effective_stats(e1).get("vulnerability", 0.0),
                            0.15, rel_tol=1e-9)
        _cast(eng, "121801")
        assert e1.modifiers["ASHEN_ROAST"].stacks == 2
        assert math.isclose(eng.pipeline.effective_stats(e1).get("vulnerability", 0.0),
                            0.20, rel_tol=1e-9)

    def test_burn_tick(self, compiled):
        """灼烧 tick：1.8×atk lv10 #6 + 承伤区联动."""
        eng = _make(compiled)
        _cast(eng, "121802")
        e1 = eng.state.actors["e1"]
        vuln = eng.pipeline.effective_stats(e1).get("vulnerability", 0.0)
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp,
                            1.8 * JQ_ATK * Z_FIRE * (1 + vuln), rel_tol=1e-9)


class TestZone:
    def test_ult_zone_and_scoped_vuln(self, compiled):
        """大招：全体 1.0 + 结界 + 终伤易伤 scoped——ultimate 命中才计（普攻不吃）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _cast(eng, "121802")   # 烬煨 1 层 vuln 0.15
        jq = _jq(eng)
        jq.current_energy = 100.0
        hp1 = e1.current_hp
        ult = next(x for x in eng.actions_by_actor["1218"] if x.action_id == "121803")
        assert eng._fire_ultimate(jq, ult) is True
        assert "ASHEN_ZONE" in jq.modifiers
        assert math.isclose(hp1 - e1.current_hp,
                            1.0 * JQ_ATK * Z_FIRE * (1 + 0.15 + 0.15), rel_tol=1e-9), (
            "烬煨 0.15 + 结界 scoped 0.15（ultimate 命中域——承伤区补口）")
        hp1 = e1.current_hp
        _cast(eng, "121801")   # 普攻 → 2 层烬煨 0.20，结界不计
        assert math.isclose(hp1 - e1.current_hp,
                            1.0 * JQ_ATK * Z_FIRE * 1.2, rel_tol=1e-9), (
            "非 ultimate 命中：结界 scoped 不计（类型限定）")

    def test_zone_action_proc(self, compiled):
        """结界行动触发：敌方行动 60%（expected 恒挂）+占用件+计数."""
        eng = _make(compiled)
        jq = _jq(eng)
        jq.current_energy = 100.0
        ult = next(x for x in eng.actions_by_actor["1218"] if x.action_id == "121803")
        eng._fire_ultimate(jq, ult)
        e2 = eng.state.actors["e2"]
        eng.bus.emit("on_turn_start", {"actor": "e2"}, eng.state)
        assert "ASHEN_ROAST" in e2.modifiers
        assert "ASHEN_ZONE_PROC" in e2.modifiers, "每敌每回合 1 次占用"
        assert math.isclose(jq.resources["_zone_proc"], 1.0)


class TestEidolons:
    def test_e1_vuln_amplified(self, compiled):
        """E1：天赋易伤 ×1.4（永续标记+跨人反查——乘算口径在案）；E0 对照."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        e1 = eng.state.actors["e1"]
        _cast(eng, "121802")
        assert math.isclose(eng.pipeline.effective_stats(e1).get("vulnerability", 0.0),
                            0.15 * 1.4, rel_tol=1e-9)
        _cast(eng, "121801")
        assert math.isclose(eng.pipeline.effective_stats(e1).get("vulnerability", 0.0),
                            0.20 * 1.4, rel_tol=1e-9)
        eng0 = _make(compiled)
        _cast(eng0, "121802")
        e10 = eng0.state.actors["e1"]
        assert math.isclose(eng0.pipeline.effective_stats(e10).get("vulnerability", 0.0),
                            0.15, rel_tol=1e-9), "E0 无放大（跨人反查不误伤）"

    def test_e2_burn_amp(self):
        """E2：灼烧倍率 ×(1+3)（标记幂等——乘区口径在案）."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast(eng, "121802")
        e1 = eng.state.actors["e1"]
        vuln = eng.pipeline.effective_stats(e1).get("vulnerability", 0.0)
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp,
                            1.8 * 4 * JQ_ATK * Z_FIRE * (1 + vuln), rel_tol=1e-9)

    def test_e4_zone_atk_down(self):
        """E4：结界展开时敌方全体 ATK−15%."""
        eng = _make(compile_encounter(_build(eidolon=4), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        jq = _jq(eng)
        jq.current_energy = 100.0
        e1 = eng.state.actors["e1"]
        ult = next(x for x in eng.actions_by_actor["1218"] if x.action_id == "121803")
        eng._fire_ultimate(jq, ult)
        assert "E4_ZONE_ATK_DOWN" in e1.modifiers
        assert math.isclose(eng.pipeline.effective_stats(e1)["atk"],
                            1000 * 0.85, rel_tol=1e-9)


class TestTechnique:
    def test_tech_aoe_roast(self):
        """秘技：全体 100% ATK + 烬煨 1 层."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1218", "technique": "121807"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        assert math.isclose(1e9 - e1.current_hp, 1.0 * JQ_ATK * Z_FIRE, rel_tol=1e-9)
        assert e1.modifiers["ASHEN_ROAST"].stacks == 1
        assert e2.modifiers["ASHEN_ROAST"].stacks == 1
