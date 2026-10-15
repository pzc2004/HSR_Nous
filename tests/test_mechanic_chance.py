"""可变概率变量通道 v1（B9 收官，银狼 LV.999 Top Loot Box 实例）：

概率 = 自定义资源（0-1），衰减/重置 = set_resource 表达式原语（零新原语），
裁判 = mechanic_chance(p)（roll zagreus 真掷 / expected ≥0.5 生效——
与 roll_debuff_apply 同一期望口径，全系统不许出现两种期望语义）。
"""
from __future__ import annotations

import math

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL

from tests.template_materialize import TEST_TEMPLATE_ROOTS

_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 600}}}

_BUILD = {"build": {"team": [{"character_template": "999908", "level": 80}],
                    "policy": {"name": "p", "action_rules": [
                        {"condition": "true", "action": "basic", "priority": 0}]}}}


def _engine(mode, seed=None):
    eng = CombatEngine.from_compiled(
        compile_encounter(_BUILD, _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=mode, seed=seed, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _act(eng, n=1):
    for _ in range(n):
        eng.bus.emit("on_action", {
            "actor": "999908", "action_type": "basic", "action_id": "t_basic",
            "target_type": "single", "target": "e1", "actor_type": "character"}, eng.state)


class TestMechanicChanceExpected:
    def test_decay_and_reset_sequence(self):
        """expected ≥0.5 生效：1.0 触发 → 0.5 触发 → 0.25 停 → 终结技重置 1.0 再触发."""
        eng = _engine(MODE_EXPECTED)
        st = eng.state.actors["999908"]
        sp0 = eng.state.skill_points
        _act(eng, 1)
        assert math.isclose(st.resources["loot_chance"], 0.5) and eng.state.skill_points == sp0 + 1
        _act(eng, 1)
        assert math.isclose(st.resources["loot_chance"], 0.25) and eng.state.skill_points == sp0 + 2
        _act(eng, 1)
        assert math.isclose(st.resources["loot_chance"], 0.25) and eng.state.skill_points == sp0 + 2, (
            "0.25 < 0.5：expected 不触发（概率停留）")
        # 终结技重置（150621 同构）
        eng.bus.emit("on_ultimate", {"source": "999908", "action": "t_ult", "target": "999908"},
                     eng.state)
        assert math.isclose(st.resources["loot_chance"], 1.0)
        _act(eng, 1)
        assert math.isclose(st.resources["loot_chance"], 0.5), "重置后恢复触发并再次衰减"


class TestMechanicChanceRoll:
    def test_roll_seed_reproducible(self):
        """roll 模式 zagreus 真掷：同 seed 触发序列逐项复现."""
        def run():
            eng = _engine(MODE_ROLL, seed=42)
            _act(eng, 8)
            return (eng.state.actors["999908"].resources["loot_chance"],
                    eng.state.skill_points)
        assert run() == run()


class TestExpectedParity:
    def test_same_semantics_as_debuff_roll(self):
        """mechanic_chance 与 roll_debuff_apply 同一期望口径（不许两种期望语义并存）."""
        eng = _engine(MODE_EXPECTED)
        for p in (0.49, 0.5, 0.51, 1.0, 0.0):
            assert eng.pipeline.mechanic_chance(p) == eng.pipeline.roll_debuff_apply(p)
