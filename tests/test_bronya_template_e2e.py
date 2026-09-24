"""布洛妮娅 1101 模板端到端对轴（验收型批·组2）：真模板 YAML → 编译 → 战技三段/
终结技双增益/天赋拉条/大行迹光环/星魂全链 → 手算全等.

过堂三件（fixture 头注同录）：ally_single 目标池勘正 / E1 gain_skill_point 收编 /
E4 风弱点谓词证伪整件待收。

口径常数：布洛妮娅白值 atk 582.12、crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 →
防御区 0.5、风弱点 → 抗性区 1.0、未击破 0.9。拉条幅度（100%/30%）走调度器 AV，
手动驱动引擎不跑调度循环——拉条类断言以挂载/豁免为准，AV 精度不钉（在案）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

BR_ATK = 582.12
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1101", "level": 80}
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


def _br(eng):
    return eng.state.actors["1101"]


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


class TestBronyaCompile:
    def test_skill_target_pool_fixed(self, compiled):
        """战技 ally_single（过堂勘正实证——'single' 敌方池会打敌人）；终结技 self."""
        acts = {a.action_id: a for a in compiled.actions_by_actor["1101"]}
        assert acts["110102"].target_type == "ally_single"
        assert acts["110103"].target_type == "self" and acts["110103"].energy_cost == 120
        assert "_e1_cd" in compiled.resource_decls_by_actor["1101"]


class TestSkillThreeParts:
    def test_cleanse_advance_buff(self, compiled):
        """战技三段：净化 1 负面（LIFO 新先摘）+ 增伤 0.66 一回合（lv10 param(110102,1)）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        eng._apply_modifier(ally, Modifier(
            modifier_id="D1", name="旧负面", modifier_type="debuff", duration=2))
        eng._apply_modifier(ally, Modifier(
            modifier_id="D2", name="新负面", modifier_type="debuff", duration=2))
        _cast(eng, "1101", "110102", target=ally)
        assert "D2" not in ally.modifiers and "D1" in ally.modifiers, "净化 LIFO 新先摘"
        buff = ally.modifiers.get("BRONYA_SKILL_DMG")
        assert buff is not None and buff.duration == 1, "增伤 1 回合（E6 marker 未挂基础支）"
        assert math.isclose(buff.stat_effects["all_dmg"], 0.66, rel_tol=1e-9)

    def test_self_cast_buff_no_advance_exempt(self, compiled):
        """自指：增伤照挂；拉条豁免（官方 cannot immediately take action again——
        豁免分支条件 $event.target != '1101' 承载，AV 不钉在案）."""
        eng = _make(compiled)
        _cast(eng, "1101", "110102", target=_br(eng))
        assert "BRONYA_SKILL_DMG" in _br(eng).modifiers


class TestUltimate:
    def test_ult_team_buff(self, compiled):
        """大招：全体 ATK +55% + 暴伤 0.16×自身暴伤 0.74+0.2=0.3184（lv10，施加快照
        基数在案——0.74=0.5+行迹 crit_dmg 0.24 B-TR① 回填）."""
        eng = _make(compiled)
        m7 = _br(eng)
        m7.current_energy = 120.0
        ult = next(a for a in eng.actions_by_actor["1101"] if a.action_id == "110103")
        assert eng._fire_ultimate(m7, ult) is True
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["atk"], 1500 * 1.55, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["crit_dmg"], 0.8184, rel_tol=1e-9)
        assert math.isclose(m7.current_energy, 5.0)


class TestAuras:
    def test_military_might_and_battlefield(self, compiled):
        """Military Might 全队增伤 10%（team 光环）；Battlefield 开战 DEF+20% 二回合."""
        eng = _make(compiled)
        assert "BRONYA_BATTLEFIELD" in _br(eng).modifiers
        assert math.isclose(eng.pipeline.effective_stats(_br(eng))["def_"],
                            533.61 * 1.2, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, 1500 * Z * 1.1, rel_tol=1e-9), (
            "军势 10% 增伤辐射辅手")


class TestEidolons:
    def test_e1_sp_refund_and_cd(self):
        """E1：战技 50% 返还（expected 恒中）——首发净 0 耗（−1+1）+ CD 闩；
        同回合二发不返；自身回合开始清零."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        sp0 = eng.state.skill_points
        ally = eng.state.actors["ally"]
        _cast(eng, "1101", "110102", target=ally)
        assert math.isclose(eng.state.skill_points, sp0), "首发 −1+1 净 0（返还收编实证）"
        assert math.isclose(_br(eng).resources["_e1_cd"], 1.0)
        _cast(eng, "1101", "110102", target=ally)
        assert math.isclose(eng.state.skill_points, sp0 - 1), "CD 闩在场二发不返"
        eng.bus.emit("on_turn_start", {"actor": "1101"}, eng.state)
        assert math.isclose(_br(eng).resources["_e1_cd"], 0.0)

    def test_e2_spd_buff(self):
        """E2：战技后目标 SPD +30% 一回合."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1101", "110102", target=ally)
        assert "E2_QUICK_MARCH" in ally.modifiers
        assert math.isclose(eng.pipeline.effective_stats(ally)["spd"], 90 * 1.3, rel_tol=1e-9)

    def test_e6_buff_two_turns(self):
        """E6：marker 门控——增伤 duration 1→2（双分支字面值承载）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1101", "110102", target=ally)
        assert ally.modifiers["BRONYA_SKILL_DMG"].duration == 2
