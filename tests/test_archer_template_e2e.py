"""Archer 1015 模板端到端对轴（验收型批·组2 复杂件）：真模板 YAML → 编译 →
回路连接循环/增伤叠层/天赋追击/星魂全链 → 手算全等.

过堂七件（fixture 头注同录）：追击过滤+回能+产点 / 叠层类型桶 / grant_extra_turn /
E1 SP / E4 类型桶 / E6① SP / E2 死键摘除。

口径常数：Archer 白值 atk 620.928、crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 →
防御区 0.5、量子弱点 → 抗性区 1.0、未击破 0.9。普攻 lv6=1.1（官方上限 9 档）。
增伤叠层：stat_exprs 活读——快照见旧值，第 N 发放大时读 N-1 层（首次不吃）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

AR_ATK = 620.928
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1015", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "quantum",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


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


def _ar(eng):
    return eng.state.actors["1015"]


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


class TestArcherCompile:
    def test_resources_actions(self, compiled):
        decls = compiled.resource_decls_by_actor["1015"]
        assert decls["charge"]["max"] == 4 and decls["_circuit"]["max"] == 1
        assert decls["_skill_casts"]["max"] == 5 and decls["_e1_casts"]["max"] == 5
        acts = {a.action_id: a for a in compiled.actions_by_actor["1015"]}
        assert acts["101502"].skill_point_cost == 2
        assert acts["101503"].energy_cost == 220 and acts["101503"].target_type == "single"
        assert acts["101509"].available_if == "res__circuit >= 1", "结束技仅回路连接可用"

    def test_battle_start_charge(self, compiled):
        eng = _make(compiled)
        assert math.isclose(_ar(eng).resources["charge"], 1.0), "Hero of Justice 开战 +1"


class TestCircuitAndStacks:
    def test_skill_stack_escalation_and_exit(self, compiled):
        """叠层活读：第 1 发不吃（快照）、第 2 发吃 1 层（×2.0）、第 3 发起吃 2 层
        （×3.0——lv10 增伤 1.0/层）；第 5 发后退出回路连接——叠层清零第 6 发回 ×1.0."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        # 第 1 发：叠层 0（快照不吃）
        hp1 = e1.current_hp
        _cast(eng, "1015", "101502")
        assert math.isclose(hp1 - e1.current_hp, 3.6 * AR_ATK * Z * 1.0, rel_tol=1e-9)
        assert math.isclose(_ar(eng).resources["_circuit"], 1.0)
        # 第 2 发：读 1 层 → 增伤区 2.0
        hp1 = e1.current_hp
        _cast(eng, "1015", "101502")
        assert math.isclose(hp1 - e1.current_hp, 3.6 * AR_ATK * Z * 2.0, rel_tol=1e-9)
        # 第 3、4 发：读 2 层 → 3.0
        for _ in range(2):
            hp1 = e1.current_hp
            _cast(eng, "1015", "101502")
            assert math.isclose(hp1 - e1.current_hp, 3.6 * AR_ATK * Z * 3.0, rel_tol=1e-9)
        # 第 5 发：退出阈（res__skill_casts 4+1>=5）→ 退出 + 清零
        hp1 = e1.current_hp
        _cast(eng, "1015", "101502")
        assert math.isclose(hp1 - e1.current_hp, 3.6 * AR_ATK * Z * 3.0, rel_tol=1e-9)
        assert math.isclose(_ar(eng).resources["_circuit"], 0.0), "5 次退出回路连接"
        assert "ARCHER_SKILL_STACK" not in _ar(eng).modifiers, "退出摘叠层件"
        # 第 6 发：重新进入——叠层从 0 重计（本发不吃）
        hp1 = e1.current_hp
        _cast(eng, "1015", "101502")
        assert math.isclose(hp1 - e1.current_hp, 3.6 * AR_ATK * Z * 1.0, rel_tol=1e-9)
        assert math.isclose(_ar(eng).resources["_circuit"], 1.0)


class TestTalentFua:
    def test_fua_damage_energy_sp(self, compiled):
        """追击：队友攻击怪物 → 耗 1 Charge 追击 2.0×ATK + 回能 5 + 产点 1（三件收编）."""
        eng = _make(compiled)
        sp0 = eng.state.skill_points
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        dmg = 1500 * Z + 2.0 * AR_ATK * Z
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9)
        assert math.isclose(_ar(eng).resources["charge"], 0.0)
        assert math.isclose(_ar(eng).current_energy, 5.0), "追击回能 5（gain_energy 收编）"
        assert math.isclose(eng.state.skill_points, sp0 + 1.0), (
            "追击产点 +1（gain_skill_point 收编——辅手 inline 普攻未配产点键，delta 0 对照）")

    def test_fua_dead_target_fallback(self, compiled):
        """兜底：主目标已死 → 随机敌方（expected 取首存活 e2）；无 Charge 不发."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.current_hp = 1.0
        _cast(eng, "ally", "ally_basic")   # 辅手击杀 e1
        assert not e1.alive
        assert math.isclose(e2.current_hp, 1e9 - 2.0 * AR_ATK * Z, rel_tol=1e-9), (
            "兜底随机命中 e2（hp_of(target)<=0 支）")
        assert math.isclose(_ar(eng).resources["charge"], 0.0)
        hp2 = e2.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp2 - e2.current_hp, 1500 * Z, rel_tol=1e-9), "无 Charge 不追击"


class TestEidolons:
    def test_e1_skill_sp_refund(self):
        """E1：回合计数第三发战技 +2 SP（快照判据 res+1==3）；自身回合开始清零."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        sp_before = None
        for i in range(3):
            sp_before = eng.state.skill_points
            _cast(eng, "1015", "101502")
        assert math.isclose(_ar(eng).resources["_e1_casts"], 3.0)
        assert eng.state.skill_points >= 2.0, "第三发 +2 SP（gain_skill_point 收编）"
        eng.bus.emit("on_turn_start", {"actor": "1015"}, eng.state)
        assert math.isclose(_ar(eng).resources["_e1_casts"], 0.0), "自身回合开始清零"

    def test_e4_ult_boost(self):
        """E4：终结技伤害 +150%（dmg_ultimate_dmg_boost 收编）——10.0×(1+1.5) 对轴."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        m7 = _ar(eng)
        m7.current_energy = 220.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1015"] if a.action_id == "101503")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 10.0 * AR_ATK * Z * 2.5, rel_tol=1e-9)
        assert math.isclose(m7.resources["charge"], 3.0), "1+2（大招获 Charge）"
        assert math.isclose(m7.current_energy, 5.0)

    def test_e6_turn_start_sp(self):
        """E6①：回合开始 +1 SP（无条件读——时点口径待实测在案）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        sp0 = eng.state.skill_points
        eng.bus.emit("on_turn_start", {"actor": "1015"}, eng.state)
        assert math.isclose(eng.state.skill_points, sp0 + 1.0)
