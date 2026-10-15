"""v0.7A 多目标结算测试：aoe 全体 / blast 主副分化（倍率+削韧）/ self 类.

数值锚点：atk=2000 crit(0.5,1.0) 期望模式下单发倍率 1.0 = 1350（同 v0.6 对轴口径）；
削韧基线 docs/mechanics/04_break_system.md——扩散 邻10/主20/邻10（副=主一半）。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _attacker():
    return Actor(actor_id="atk", name="攻手", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy(eid, name):
    return Actor(actor_id=eid, name=name, actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=100, max_toughness=30, weakness=["fire"]))


def _engine(actions, n_enemies=3, av=70.0):
    dummies = [_dummy(f"e{i+1}", f"假人{i+1}") for i in range(n_enemies)]
    enc = Encounter(encounter_id="t", name="t", actors=[_attacker()] + dummies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"atk": actions},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestAoE:
    def test_aoe_hits_all(self):
        aoe = Action(action_id="aoe", name="群攻", action_type="basic", target_type="aoe",
                     damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10)
        state = _engine([aoe]).run()
        assert math.isclose(state.total_damage, 3 * 1350.0, rel_tol=1e-6)
        for i in range(3):
            assert math.isclose(state.actors[f"e{i+1}"].current_hp, 1e9 - 1350.0, rel_tol=1e-9)
            # 群攻各目标同削韧 10
            assert math.isclose(state.actors[f"e{i+1}"].toughness, 20.0)


class TestBlast:
    def test_blast_main_secondary_split(self):
        """扩散：主目标全倍率+全削韧，相邻副目标副倍率+默认半削韧."""
        blast = Action(action_id="blast", name="扩散", action_type="basic", target_type="blast",
                       damage_type="fire", scaling=[{"atk": 1.0}],
                       scaling_blast=[{"atk": 0.5}], toughness_dmg=20)
        state = _engine([blast]).run()
        # 主目标=e1（边位），相邻=e2；e3 不受击
        assert math.isclose(state.actors["e1"].current_hp, 1e9 - 1350.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e2"].current_hp, 1e9 - 675.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e3"].current_hp, 1e9, rel_tol=1e-9)
        assert math.isclose(state.total_damage, 2025.0, rel_tol=1e-6)
        # 削韧：主 20，副默认一半=10（基线 10/20/10）
        assert math.isclose(state.actors["e1"].toughness, 10.0)
        assert math.isclose(state.actors["e2"].toughness, 20.0)

    def test_blast_explicit_secondary_toughness(self):
        """显式 toughness_dmg_blast 覆盖默认半削韧（饮月类特例的表达方式）."""
        blast = Action(action_id="blast", name="扩散", action_type="basic", target_type="blast",
                       damage_type="fire", scaling=[{"atk": 1.0}],
                       toughness_dmg=40, toughness_dmg_blast=20)
        state = _engine([blast], n_enemies=2).run()
        assert math.isclose(state.actors["e1"].toughness, 0.0)  # 40 打穿 30 → 击破
        assert state.actors["e1"].broken
        # 副目标 30-20=10，未击破
        assert math.isclose(state.actors["e2"].toughness, 10.0)
        assert not state.actors["e2"].broken

    def test_blast_defaults_to_main_scaling(self):
        """scaling_blast=None 时副目标与主目标同倍率."""
        blast = Action(action_id="blast", name="扩散", action_type="basic", target_type="blast",
                       damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=20)
        state = _engine([blast], n_enemies=2).run()
        assert math.isclose(state.actors["e2"].current_hp, 1e9 - 1350.0, rel_tol=1e-9)


class TestNonDamageTargets:
    def test_self_target_no_crash(self):
        """self 类无伤害技能：目标解析到自己、无伤害结算、不炸."""
        buff = Action(action_id="buff", name="自强", action_type="skill", target_type="self",
                      skill_point_cost=1)
        state = _engine([buff]).run()
        assert math.isclose(state.total_damage, 0.0)
        assert math.isclose(state.actors["atk"].current_hp, 3000.0)
