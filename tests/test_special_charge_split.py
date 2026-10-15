"""特殊充能（火种族）+ split 均分 + 形态内面板 测试.

场景：白厄主干迷你链——战技获火种（3/动）→ 火种≥4 激活变身技（不走能量）
→ 倒计时 2 动血棘渡亡（形态内 atk_pct+30%）→ 退出。
数值口径：atk=2000 crit(0.5,1.0) 期望模式，def×res=0.5，未击破 ×0.9 → 倍率 1.0 = 1350。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import StateConfig
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _phainon():
    return Actor(actor_id="phainon", name="白厄", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy(eid="e1"):
    return Actor(actor_id=eid, name="假人", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["physical"]))


def _actions():
    return [
        Action(action_id="skill", name="黎明创世", action_type="skill", target_type="single",
               damage_type="physical", scaling=[{"atk": 1.5}], toughness_dmg=20,
               skill_point_cost=1, resource_gain={"fire_seed": 3}),
        Action(action_id="khaslana_ult", name="永劫燔世", action_type="ultimate",
               target_type="single", damage_type="physical",
               ult_cost_resource="fire_seed", ult_cost_amount=4),
        Action(action_id="khaslana_basic", name="创生•血棘渡亡", action_type="basic",
               target_type="single", damage_type="physical", scaling=[{"atk": 3.0}],
               toughness_dmg=20, energy_gain=0),
    ]


def _engine(av=300.0):
    enc = Encounter(encounter_id="t", name="t", actors=[_phainon(), _dummy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"phainon": _actions()},
                       policy=ScriptedPolicy(rotation=["skill"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    eng.register_state_config("phainon", StateConfig(
        state="khaslana",
        replaces_actions={"basic": "khaslana_basic"},
        locked_actions=["skill"],
        exit_conditions=[{"trigger": "on_action_count", "value": 2}],
        stat_effects={"atk_pct": 0.3},
    ), entry_action_id="khaslana_ult")
    return eng


class TestSpecialChargeChain:
    def test_fire_seed_chain(self):
        """火种轨迹：3→6→(变身扣4)→2；终结技不走能量（能量恒 30×2=60 战技回能）."""
        eng = _engine(av=270.0)  # T1/T2 战技 + 变身 + 倒计时 2 动（占 AV）@200/@266.7；下一动 @333.3 截断
        state = eng.run()
        st = state.actors["phainon"]
        # 火种：两动战技 0→3→6，变身扣 4 → 2（倒计时强化普攻不给火种）
        assert math.isclose(st.resources["fire_seed"], 2.0), f"火种轨迹错：{st.resources}"
        # 变身与退出发生
        assert any("进入形态 khaslana" in l for l in state.log)
        assert any("退出形态 khaslana" in l for l in state.log)
        # 伤害对轴：战技 2025×2 + 血棘（atk 2000×1.3=2600 → 2600×3×1.5×0.5×0.9=5265）×2
        expected = 2 * 2025.0 + 2 * 5265.0
        assert math.isclose(state.total_damage, expected, rel_tol=1e-6), (
            f"手算 {expected} vs 实际 {state.total_damage}"
        )

    def test_ult_blocked_without_seeds(self):
        """火种不足时终结技不激活（特殊充能门槛真实生效）."""
        enc = Encounter(encounter_id="t", name="t", actors=[_phainon(), _dummy()],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=70.0))
        eng = CombatEngine(enc, actions_by_actor={"phainon": _actions()},
                           policy=ScriptedPolicy(rotation=["skill"]), mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        eng.register_state_config("phainon", StateConfig(
            state="khaslana", exit_conditions=[{"trigger": "on_action_count", "value": 2}],
        ), entry_action_id="khaslana_ult")
        state = eng.run()  # 只 1 动：火种 3 < 4
        assert not any("进入形态" in l for l in state.log), "火种不足不应变身"
        assert math.isclose(state.actors["phainon"].resources["fire_seed"], 3.0)


class TestSplitEven:
    def test_split_even_three_enemies(self):
        """aoe+split scaling 3.0：3 怪各吃 1.0 倍率（1350），总 4050."""
        split_aoe = Action(action_id="finale", name="最后一击", action_type="basic",
                           target_type="aoe", damage_type="physical",
                           scaling=[{"atk": 3.0}], toughness_dmg=0, split="even")
        dummies = [_dummy(f"e{i}") for i in (1, 2, 3)]
        enc = Encounter(encounter_id="t", name="t", actors=[_phainon()] + dummies,
                        termination=TerminationConfig(mode="fixed_av", max_action_value=70.0))
        eng = CombatEngine(enc, actions_by_actor={"phainon": [split_aoe]},
                           policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        state = eng.run()
        assert math.isclose(state.total_damage, 4050.0, rel_tol=1e-6)
        for i in (1, 2, 3):
            assert math.isclose(state.actors[f"e{i}"].current_hp, 1e9 - 1350.0, rel_tol=1e-9)
