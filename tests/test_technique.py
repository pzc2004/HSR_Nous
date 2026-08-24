"""秘技（战前系统）测试：点池校验 + 进战装填 effects + 波次常驻 hook."""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import materialize_template


@pytest.fixture(scope="module", autouse=True)
def _materialize():
    materialize_template("1408_phainon.yaml")


def _build(with_technique: bool):
    build = {"build": {"team": [
        {"character_template": "1408", "level": 80},
        {"actor_id": "ally_a", "name": "队友A", "inline": True,
         "base_stats": {"atk": 1000, "spd": 120, "hp": 3000, "max_energy": 100}, "actions": []},
    ], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0}]}}}
    if with_technique:
        build["build"]["pre_battle"] = [{"actor_id": "1408", "technique": "140807"}]
    return build


def _stage():
    return {"stage": {"stage_id": "s",
        "enemies": [{"actor_id": "e1", "name": "一波怪", "hp": 1, "spd": 50,
                     "max_toughness": 10, "weakness": ["physical"]}],
        "waves": [{"wave_index": 1, "enemies": [
            {"actor_id": "e2", "name": "二波怪", "hp": 1e9, "spd": 50,
             "max_toughness": 9999, "weakness": ["physical"]}]}],
        "termination": {"mode": "fixed_av", "max_action_value": 500}}}


class TestTechnique:
    def test_prebattle_loadout_effects(self):
        """秘技装填：进战 ruin+2、全队能量+25、战技点+1（on_battle_start 前 fire）."""
        eng = CombatEngine.from_compiled(
            compile_encounter(_build(True), _stage()), mode=MODE_EXPECTED,
            initial_sp=3, initial_energy_ratio=0.0)
        eng.setup()
        st = eng.state.actors["1408"]
        ally = eng.state.actors["ally_a"]
        assert math.isclose(st.resources["ruin"], 2.0), f"秘技毁伤：{st.resources}"
        assert math.isclose(ally.current_energy, 25.0), f"秘技回能：{ally.current_energy}"
        assert eng.skill_points == 4, f"秘技战技点：{eng.skill_points}"

    def test_wave_start_hook_fires(self):
        """秘技常驻 hook：第二波开始时全体伤害（终结之始）."""
        state = CombatEngine.from_compiled(
            compile_encounter(_build(True), _stage()), mode=MODE_EXPECTED,
            initial_sp=3, initial_energy_ratio=0.0).run()
        log = state.log
        assert any("第 2 波" in l for l in log), f"应有波次切换：{log[:10]}"
        wave2_idx = next(i for i, l in enumerate(log) if "第 2 波" in l)
        window = log[max(0, wave2_idx - 3):wave2_idx + 4]
        assert any("终结之始" in l for l in window), (
            f"波次切换前后应有秘技伤害：{window}"
        )

    def test_no_technique_no_effects(self):
        """未声明 pre_battle：秘技不生效（耗点制——选择才施放）."""
        eng = CombatEngine.from_compiled(
            compile_encounter(_build(False), _stage()), mode=MODE_EXPECTED,
            initial_sp=3, initial_energy_ratio=0.0)
        eng.setup()
        assert math.isclose(eng.state.actors["1408"].resources["ruin"], 0.0)
        assert math.isclose(eng.state.actors["ally_a"].current_energy, 0.0)

    def test_point_pool_overflow_rejected(self):
        """秘技点超支编译期报错（池 = 5+3=8，5 次 ×2 点 = 10 > 8）."""
        build = _build(True)
        build["build"]["pre_battle"] = [{"actor_id": "1408", "technique": "140807"}] * 5
        with pytest.raises(ValueError, match="秘技点超支"):
            compile_encounter(build, _stage())
