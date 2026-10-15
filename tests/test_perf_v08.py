"""v0.8 性能看守：典型场景单局耗时防退化.

基准事实（2026-08-21）：4v3、450AV≈33 回合、含 blast 多目标 → 单局 ~0.8ms。
断言只拦量级退化（100 局 < 5s，50 倍余量防机器差异），不锁精确耗时。
优化器级批量换算：万局 ≈ 8s——当前无性能瓶颈，故 v0.8 不做引擎优化（数据说话，不引入复杂度）。
"""
from __future__ import annotations

import time

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _build() -> CombatEngine:
    heroes = [
        Actor(actor_id=f"h{i}", name=f"角色{i}", level=80,
              stats=StatBlock(atk=2000, spd=120 + i * 5, hp=3000, max_energy=120,
                              crit_rate=0.5, crit_dmg=1.0))
        for i in range(4)
    ]
    enemies = [
        Actor(actor_id=f"e{i}", name=f"怪{i}", actor_type="monster", level=80,
              stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["fire"]))
        for i in range(3)
    ]

    def actions(prefix: str):
        return [
            Action(action_id=f"{prefix}_basic", name="普攻", action_type="basic",
                   target_type="single", damage_type="fire",
                   scaling=[{"atk": 1.0}], toughness_dmg=10),
            Action(action_id=f"{prefix}_skill", name="战技", action_type="skill",
                   target_type="blast", damage_type="fire",
                   scaling=[{"atk": 2.0}], scaling_blast=[{"atk": 1.0}],
                   toughness_dmg=20, skill_point_cost=1),
        ]

    acts = {f"h{i}": actions(f"h{i}") for i in range(4)}
    acts.update({f"e{i}": actions(f"e{i}") for i in range(3)})
    enc = Encounter(encounter_id="t", name="t", actors=heroes + enemies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=450))
    eng = CombatEngine(enc, actions_by_actor=acts,
                       policy=ScriptedPolicy(rotation=["skill", "basic"]),
                       mode=MODE_EXPECTED, initial_sp=5, initial_energy_ratio=0.5)
    eng.setup()
    return eng


def test_perf_guard_typical_battle():
    """100 局典型战斗 < 5s（实测 ~0.1s；超时=量级退化警报）."""
    n = 100
    t0 = time.perf_counter()
    for _ in range(n):
        _build().run()
    dt = time.perf_counter() - t0
    per_battle_ms = dt / n * 1000
    print(f"\n[perf] 单局 {per_battle_ms:.2f}ms（100 局 {dt:.2f}s）")
    assert dt < 5.0, f"性能量级退化：100 局 {dt:.1f}s（单局 {per_battle_ms:.1f}ms），基准 ~0.8ms/局"
