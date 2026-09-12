"""停云 1202 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 祝福双段/
天赋追加/终结技充能增伤/行迹/星魂全链 → 手算全等.

过堂四件（fixture 头注同录）：双 ally_single / 祝福双勘正（停云基数+持有者 cap）/
紫电扶摇触发域主客倒置勘正 / Knell 类型桶勘正。

口径常数：停云白值 atk 529.2、crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 →
防御区 0.5、雷弱点 → 抗性区 1.0、未击破 0.9。祝福 lv10：ATK+min(0.5×529.2,
0.25×持有者 atk)；附加 40%、紫电扶摇 60%（持有者 atk 基数）。普攻 lv6=1.0。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

TY_ATK = 529.2
ALLY_ATK = 1500.0
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
BLESS = min(0.5 * TY_ATK, 0.25 * ALLY_ATK)   # = 264.6（停云基数生效）
EFF_ATK = ALLY_ATK + BLESS                   # 1764.6


def _build(*, eidolon: int = 0):
    member = {"character_template": "1202", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "thunder",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


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
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _ty(eng):
    return eng.state.actors["1202"]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["ally"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)
    # on_become_target 由引擎 _execute_action 对每目标自发射（不手动补发——双发会
    # 双倍入账（充能 ×2、祝福转移双跑）实证在案）


class TestTingyunCompile:
    def test_ally_single_and_resource(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1202"]}
        assert acts["120202"].target_type == "ally_single"
        assert acts["120203"].target_type == "ally_single"
        assert "_e2_kills" in compiled.resource_decls_by_actor["1202"]


class TestBenediction:
    def test_bless_atk_cap_and_transfer(self, compiled):
        """祝福：ATK+min(0.5×529.2, 0.25×1500)=264.6（停云基数生效——cap 未触）；
        换目标 → 先摘全场再挂新（唯一持有者转移）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1202", "120202", target=ally)
        assert math.isclose(eng.pipeline.effective_stats(ally)["atk"], EFF_ATK, rel_tol=1e-9), (
            "min(264.6, 375)=264.6（双勘正：停云基数+cap 持有者基数）")
        assert ally.modifiers["BENEDICTION"].duration == 3
        _cast(eng, "1202", "120202", target=_ty(eng))
        assert "BENEDICTION" not in ally.modifiers, "唯一持有者——旧件先摘"
        assert "BENEDICTION" in _ty(eng).modifiers

    def test_holder_hit_bonus_and_talent(self, compiled):
        """持有者攻击：辅手普攻（1764.6）+ 祥音和韵附加 40% + 紫电扶摇 60%
        （触发域勘正实证——主客归位）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1202", "120202", target=ally)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic", target=e1)
        per = EFF_ATK * Z
        assert math.isclose(hp1 - e1.current_hp,
                            per * (1 + 0.4 + 0.6), rel_tol=1e-9), (
            "普攻 + 附加 40%（param(120202,1) lv10）+ 紫电扶摇 60%（param(120204,1) lv10）")


class TestUltimate:
    def test_ult_energy_and_dmg_buff(self, compiled):
        """大招：指定我方充能 50 + 增伤 50% 2 回合（lv10 #3）——持有者普攻吃 1.5 区，
        附加/紫电不吃（增伤挂持有者，附加段记停云侧在案）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1202", "120202", target=ally)
        ally.current_energy = 10.0
        _cast(eng, "1202", "120203", target=ally)
        assert math.isclose(ally.current_energy, 60.0), "充能 50（param(120203,1) 全档恒 50）"
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic", target=e1)
        per = EFF_ATK * Z
        assert math.isclose(hp1 - e1.current_hp,
                            per * 1.5 + per * (0.4 + 0.6), rel_tol=1e-9), (
            "普攻 1.5 区（ULT 增伤在持有者）+ 附加/紫电不吃区（记停云侧在案）")


class TestTraces:
    def test_knell_and_turn_energy(self, compiled):
        """Knell Subdual：停云普攻 ×1.4（dmg_basic_dmg_boost 类型桶勘正实证）;
        回合开始回能 5."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1202", "120201", target=e1)
        assert math.isclose(hp1 - e1.current_hp, 1.0 * TY_ATK * Z * 1.4, rel_tol=1e-9)
        e0 = _ty(eng).current_energy
        eng.bus.emit("on_turn_start", {"actor": "1202"}, eng.state)
        assert math.isclose(_ty(eng).current_energy, e0 + 5.0)


class TestEidolons:
    def test_e2_kill_energy_latch(self):
        """E2：持有者击杀 +5 能（每场闩 → 停云回合开始清零）."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _cast(eng, "1202", "120202", target=ally)
        ally.current_energy = 0.0
        e2 = eng.state.actors["e2"]
        e2.current_hp = 100.0
        _cast(eng, "ally", "ally_basic", target=e2)
        assert not e2.alive
        assert math.isclose(ally.current_energy, 20.0 + 5.0), "普攻 20 + E2 击杀 5"
        eng.bus.emit("on_turn_start", {"actor": "1202"}, eng.state)
        assert math.isclose(_ty(eng).resources["_e2_kills"], 0.0)

    def test_e6_extra_energy(self):
        """E6：终结技额外充能 +10（与主充能 50 分槽）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_energy = 10.0
        _cast(eng, "1202", "120203", target=ally)
        assert math.isclose(ally.current_energy, 70.0), "50 主充能 + 10 E6"
