"""弱点植入（B25 weakness_add stat 本体）端到端：境界期间敌方全体物理弱点，退出解除.

口径：假人 weakness=["fire"] → 物理植前 res×0.8（1080）/ 植后 res×1.0（1350）；
削韧闸：植前物理不削韧、植后可削、退出后恢复不削。
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

ZONE_MOD = "ZONE_PHY_WEAK"


def _phainon():
    return Actor(actor_id="1408", name="白厄", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy():
    return Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["fire"]))


def _actions():
    return [
        Action(action_id="basic", name="普攻", action_type="basic", target_type="single",
               damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10),
        Action(action_id="khaslana_ult", name="永劫燔世", action_type="ultimate",
               target_type="single", ult_cost_resource="fire_seed", ult_cost_amount=12,
               apply_modifiers=[{
                   "target": "all_enemies", "modifier_id": ZONE_MOD, "name": "时墟铁墓",
                   "modifier_type": "debuff", "duration": 0, "dispellable": False,
                   "weakness_add": ["physical"]}]),
        Action(action_id="khaslana_basic", name="创生•血棘渡亡", action_type="basic",
               target_type="single", damage_type="physical", scaling=[{"atk": 3.0}],
               toughness_dmg=20, energy_gain=0),
    ]


def _engine(av=150.0):
    enc = Encounter(encounter_id="t", name="t", actors=[_phainon(), _dummy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"1408": _actions()},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    eng.register_state_config("1408", StateConfig(
        state="khaslana",
        replaces_actions={"basic": "khaslana_basic"},
        locked_actions=["skill"],
        exit_conditions=[{"trigger": "on_action_count", "value": 2}],
        exit_remove_modifiers=[ZONE_MOD],
    ), entry_action_id="khaslana_ult")
    eng.state.actors["1408"].resources["fire_seed"] = 12.0
    return eng


class TestWeaknessImplant:
    def test_implant_lifecycle(self):
        eng = _engine()
        state = eng.run()
        e1 = state.actors["e1"]

        # 1. 植入期间 modifier 存在，退出后清理
        assert ZONE_MOD not in e1.modifiers, "退出形态后境界植入件应已解除"
        # 2. 削韧：cd1/cd2 血棘各削 20（植入生效），其余行动不削（植前/植后）
        assert math.isclose(e1.toughness, 9999 - 40.0), (
            f"削韧应恰好 40（两动血棘，植前普攻与退出后普攻不削）：{e1.toughness}"
        )
        # 3. 伤害对轴：T1 普攻 1080（res×0.8）+ 血棘 4050×2（res×1.0）+ T2 普攻 1080 = 10260
        expected = 1080.0 + 2 * 4050.0 + 1080.0
        assert math.isclose(state.total_damage, expected, rel_tol=1e-6), (
            f"手算 {expected} vs 实际 {state.total_damage}"
        )

    def test_effective_weakness_during_state(self):
        """形态期间 effective_weakness 含植入属性（运行中快照验证）."""
        eng = _engine()
        eng.run()
        # 终局已退出——有效弱点恢复面板（仅 fire）
        w = eng.pipeline.effective_weakness(eng.state.actors["e1"])
        assert "physical" not in w and "fire" in w
