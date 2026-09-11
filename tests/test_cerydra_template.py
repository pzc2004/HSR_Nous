"""刻律德菈（1412）大行迹「来者」专项：条件光环 stat_exprs 现场求值对轴（暴风停歇同构）。

链：进战挂件（门控非挂摘）→ 基础攻击 732.695（620.928×1.18 行迹）< 2000 不生效
→ +1500 攻击激活 → 档 = 超出×0.0018 → 再 +3000 满档 3.6（超 2000 点计 20 档×18%）
→ 摘除回收（件仍在挂载、数值不计）。
数值口径：1412101 params [[2000, 100, 0.18, 3.6]]（#1 门槛/#2 步长/#3 每档/#4 上限）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

BASE_ATK = 620.9280000000001 * 1.18   # 732.69504（行迹 atk_pct 0.18，非条件件计入条件域面板）


@pytest.fixture(scope="module")
def compiled():
    build = {"build": {"team": [{"character_template": "1412", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["wind"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 800}}}
    return compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)


class TestVeniConditionalAura:
    """1412101 大行迹「来者」：atk>2000 门控 + 超档暴伤（enable_if/stat_exprs 条件光环）."""

    def test_gate_tier_cap_and_reclaim(self, compiled):
        eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        cyd = eng.state.actors["1412"]
        assert "CYD_VENI_CRIT_DMG" in cyd.modifiers, "进战即挂（门控非挂摘）"
        # 基础攻击 732.695 < 2000：不生效——暴伤维持面板 0.5
        assert math.isclose(eng.pipeline.effective_stats(cyd)["atk"], BASE_ATK)
        assert math.isclose(eng.pipeline.effective_stats(cyd)["crit_dmg"], 0.5)
        # +1500 → 2232.695 > 2000：激活——档 = 超出 232.695×0.0018（=232.695/100×18%）
        eng._apply_modifier(cyd, Modifier(
            modifier_id="ATK_TEST", name="测攻", modifier_type="buff", duration=0,
            stat_effects={"atk": 1500.0}))
        assert math.isclose(
            eng.pipeline.effective_stats(cyd)["crit_dmg"],
            0.5 + (BASE_ATK + 1500.0 - 2000.0) * 0.0018), "连续口径：超出/100×18%"
        # 再 +3000 → 5232.695：超 3232.695 → 至多计入 2000 点（满档 3.6）
        eng._apply_modifier(cyd, Modifier(
            modifier_id="ATK_TEST2", name="测攻二", modifier_type="buff", duration=0,
            stat_effects={"atk": 3000.0}))
        assert math.isclose(eng.pipeline.effective_stats(cyd)["crit_dmg"], 0.5 + 3.6), (
            "满档 360%（#4 上限）")
        # 摘回基础：失效回收=数值不计，件仍在挂载
        eng._remove_modifier(cyd, "ATK_TEST")
        eng._remove_modifier(cyd, "ATK_TEST2")
        assert math.isclose(eng.pipeline.effective_stats(cyd)["crit_dmg"], 0.5)
        assert "CYD_VENI_CRIT_DMG" in cyd.modifiers
