"""11_combat_log 结构化战斗日志 v1：spec 事件序列 / before-after 槽 / 终局汇总 / 确定性.

语义钉：battle_start 首条、battle_end 末条（reason 正确、不重发）；damage/heal 的
target_hp_before/after 按序一致（上条 after=下条 before）；条目全部派生自总线事件
（B16：同 seed 同日志）；summary 与 state 对账一致。
"""
from __future__ import annotations

import math

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.structured_log import StructuredLogger

from tests.template_materialize import TEST_TEMPLATE_ROOTS

_BUILD = {"build": {"team": [{
    "character_template": "inline", "actor_id": "hero", "name": "英雄", "level": 80,
    "base_stats": {"atk": 3000, "spd": 134, "hp": 3000, "max_energy": 110,
                   "crit_rate": 0.5, "crit_dmg": 1.0},
    "actions": [
        {"action_id": "b", "name": "普攻", "action_type": "basic", "target_type": "single",
         "damage_type": "thunder", "scaling": [{"atk": 1.0}], "toughness_dmg": 10},
        {"action_id": "s", "name": "剑阵", "action_type": "skill", "target_type": "aoe",
         "damage_type": "thunder", "scaling": [{"atk": 1.2}], "skill_point_cost": 1,
         "toughness_dmg": 20}],
}], "policy": {"name": "default", "action_rules": [
    {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
    {"condition": "skill_points > 2", "action": "skill", "priority": 50},
    {"condition": "true", "action": "basic", "priority": 0}]}}}

_STAGE = {"stage": {"stage_id": "trio", "enemies": [
    {"actor_id": "enemy1", "name": "炎华造物", "level": 80,
     "hp": 1_000_000_000, "spd": 90, "weakness": ["thunder"], "max_toughness": 30},
    {"actor_id": "enemy2", "name": "霜晶造物", "level": 80,
     "hp": 1_000_000_000, "spd": 110, "weakness": ["thunder", "ice"], "max_toughness": 30},
    {"actor_id": "enemy3", "name": "虚数卒", "level": 80,
     "hp": 1_000_000_000, "spd": 130, "weakness": ["thunder"], "max_toughness": 90}],
    "termination": {"mode": "fixed_av", "max_action_value": 300}}}


def _run(seed=None):
    eng = CombatEngine.from_compiled(
        compile_encounter(_BUILD, _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, seed=seed)
    logger = StructuredLogger(eng)
    eng.setup()
    state = eng.run()
    return state, logger


class TestStructuredLogShape:
    def test_first_last_and_reason(self):
        _state, logger = _run()
        entries = logger.entries
        assert entries[0]["event_type"] == "battle_start"
        assert entries[-1]["event_type"] == "battle_end"
        assert entries[-1]["reason"] == "max_action_value_reached"
        assert sum(1 for e in entries if e["event_type"] == "battle_end") == 1, "battle_end 不重发"
        assert all("timestamp" in e for e in entries), "每条带 timestamp（可重建时间线）"

    def test_core_event_types_present(self):
        _state, logger = _run()
        kinds = {e["event_type"] for e in logger.entries}
        for want in ("battle_start", "battle_end", "turn_start", "turn_end", "action",
                     "damage", "break", "energy_change", "skill_point_change"):
            assert want in kinds, f"缺核心事件类型 {want}：{sorted(kinds)}"

    def test_damage_hp_chain_consistent(self):
        """同一目标：上一条 damage 的 hp_after == 下一条的 hp_before（可聚合口径）."""
        _state, logger = _run()
        by_target: dict = {}
        for e in logger.entries:
            if e["event_type"] in ("damage", "heal"):
                prev = by_target.get(e["target_id"])
                if prev is not None:
                    assert math.isclose(e["target_hp_before"], prev, abs_tol=0.2), (
                        f"{e['target_id']} 的 hp 链断裂：before {e['target_hp_before']} != 上条 after {prev}")
                by_target[e["target_id"]] = e["target_hp_after"]


class TestStructuredLogSummary:
    def test_summary_matches_state(self):
        state, logger = _run()
        s = logger.summary
        assert math.isclose(s["total_damage"], round(state.total_damage, 1))
        assert s["total_turns"] == state.turn_count
        assert math.isclose(s["total_action_value"], round(state.clock, 1))
        assert s["dps"] > 0 and s["kills"] == 0 and s["deaths"] == 0

    def test_determinism(self):
        """B16：同 seed（expected 无 rng）两局事件序列逐项全等."""
        _s1, l1 = _run()
        _s2, l2 = _run()
        assert l1.entries == l2.entries, "同种子结构化日志必须逐项全等"
