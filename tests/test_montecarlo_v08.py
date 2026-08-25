"""v0.8 方差聚合测试：run_distribution 多局统计.

场景设计：单角色单动打木桩（av=70 只放一动），roll 模式单发普攻 ∈ {900(不暴), 1800(暴)}，
两点分布——均值/分位数/标准差全部可手算对轴。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.montecarlo import run_distribution, summarize
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _factory(mode: str):
    def make(seed: int) -> CombatEngine:
        attacker = Actor(actor_id="atk", name="攻手", level=80,
                         stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                         crit_rate=0.5, crit_dmg=1.0))
        dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                      stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["fire"]))
        basic = Action(action_id="basic", name="普攻", action_type="basic", target_type="single",
                       damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10)
        enc = Encounter(encounter_id="t", name="t", actors=[attacker, dummy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=70.0))
        eng = CombatEngine(enc, actions_by_actor={"atk": [basic]},
                           policy=ScriptedPolicy(rotation=["basic"]), mode=mode, seed=seed,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        return eng
    return make


class TestSummarize:
    def test_hand_calc(self):
        """纯函数对轴：[900×50, 1800×50] → mean=1350, σ=450, p5=900, p95=1800."""
        stats = summarize([900.0] * 50 + [1800.0] * 50)
        assert stats.n == 100
        assert math.isclose(stats.mean, 1350.0)
        assert math.isclose(stats.stdev, 450.0)
        assert math.isclose(stats.p5, 900.0)
        assert math.isclose(stats.p95, 1800.0)
        assert math.isclose(stats.minimum, 900.0)
        assert math.isclose(stats.maximum, 1800.0)

    def test_constant_samples_zero_variance(self):
        stats = summarize([1350.0] * 20)
        assert math.isclose(stats.stdev, 0.0, abs_tol=1e-9)
        assert math.isclose(stats.p5, stats.p95)


class TestRunDistribution:
    def test_expected_mode_zero_variance(self):
        """期望模式 N 局：逐局全等，方差=0（B16 在聚合层的体现）."""
        stats = run_distribution(_factory(MODE_EXPECTED), n=20)
        assert math.isclose(stats.stdev, 0.0, abs_tol=1e-6)
        assert math.isclose(stats.mean, 1350.0, rel_tol=1e-6)

    def test_roll_mode_two_point_distribution(self):
        """roll 模式 N=200：均值收敛 1350，σ≈450，p5≈900，p95≈1800."""
        stats = run_distribution(_factory(MODE_ROLL), n=200, seed0=0)
        assert math.isclose(stats.mean, 1350.0, rel_tol=0.05)
        assert math.isclose(stats.stdev, 450.0, rel_tol=0.15)
        assert math.isclose(stats.p5, 900.0, rel_tol=1e-6)
        assert math.isclose(stats.p95, 1800.0, rel_tol=1e-6)

    def test_reproducible_same_seed0(self):
        """同 seed0 两趟聚合逐字段全等."""
        s1 = run_distribution(_factory(MODE_ROLL), n=50, seed0=7)
        s2 = run_distribution(_factory(MODE_ROLL), n=50, seed0=7)
        assert s1 == s2


class TestTruncatedFiltering:
    """truncated（没打完）的局不进分布样本——只统计完整局，截断局单独计数."""

    @staticmethod
    def _truncated_factory(seed: int) -> CombatEngine:
        """必截断局：互打不死 + fixed_av 永不触发 → 撞 MAX_TURNS_SAFETY."""
        hero = Actor(actor_id="atk", name="攻手", level=80,
                     stats=StatBlock(atk=1, spd=100, hp=1e9, max_energy=100))
        dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                      stats=StatBlock(hp=1e18, spd=100, atk=1, weakness=["fire"]))
        basic = Action(action_id="basic", name="普攻", action_type="basic", target_type="single",
                       damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10)
        enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=1e15))
        eng = CombatEngine(enc, actions_by_actor={"atk": [basic]},
                           policy=ScriptedPolicy(rotation=["basic"]),
                           mode=MODE_EXPECTED, seed=seed, initial_sp=3, initial_energy_ratio=0.0)
        eng.setup()
        return eng

    def _mixed_factory(self, seed: int) -> CombatEngine:
        """seed<2 截断局，其余正常局（期望模式单发 1350）."""
        if seed < 2:
            return self._truncated_factory(seed)
        return _factory(MODE_EXPECTED)(seed)

    def test_truncated_excluded_from_distribution(self):
        import pytest
        with pytest.warns(RuntimeWarning, match="截断"):
            stats = run_distribution(self._mixed_factory, n=6, seed0=0)
        assert stats.n == 4, "只有 4 个完整局进样本"
        assert stats.n_truncated == 2, "2 个截断局单独计数"
        assert math.isclose(stats.mean, 1350.0, rel_tol=1e-9), "分布只统计完整局"
        assert "truncated=2" in stats.summary()

    def test_all_truncated_raises(self):
        import pytest
        with pytest.warns(RuntimeWarning), \
                pytest.raises(ValueError, match="全部 truncated"):
            run_distribution(self._truncated_factory, n=2, seed0=0)
