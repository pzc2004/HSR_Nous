"""v0.7B PolicyInterpreter 测试：target_rules 接线 + 选择器集合.

数值口径同 v0.7A：atk=2000 crit(0.5,1.0) 期望模式单发倍率 1.0 = 1350（未击破 ×0.9）/ 1500（已击破 ×1.0）。
"""
from __future__ import annotations

import math

from hsr_nous.sim.compile.compiled import CompiledPolicy, CompiledPolicyRule
from hsr_nous.sim.engine import CombatEngine, CompiledPolicyRuntime
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

_HP = {"e1": 1e9, "e2": 5e8, "e3": 2e9}  # e2 最低，e3 最高


def _attacker():
    return Actor(actor_id="atk", name="攻手", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy(eid):
    return Actor(actor_id=eid, name=f"假人{eid[1]}", actor_type="monster", level=80,
                 stats=StatBlock(hp=_HP[eid], spd=100, max_toughness=9999, weakness=["fire"]))


def _rule(selector, condition=None):
    return CompiledPolicyRule(action="basic", priority=0,
                              condition_expr=condition, selector=selector)


def _engine(target_rules, action=None):
    dummies = [_dummy(f"e{i}") for i in (1, 2, 3)]
    enc = Encounter(encounter_id="t", name="t", actors=[_attacker()] + dummies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70.0))
    eng = CombatEngine(enc, actions_by_actor={"atk": [action or _basic()]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.compiled_runtime = CompiledPolicyRuntime(CompiledPolicy(
        name="t", action_rules=(), target_rules=tuple(target_rules), parameters={}))
    eng.setup()
    return eng


def _basic():
    return Action(action_id="basic", name="普攻", action_type="basic", target_type="single",
                  damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10)


class TestTargetSelector:
    def test_lowest_hp(self):
        state = _engine([_rule("lowest_hp")]).run()
        assert math.isclose(state.actors["e2"].current_hp, _HP["e2"] - 1350.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"])
        assert math.isclose(state.actors["e3"].current_hp, _HP["e3"])

    def test_dict_max_key(self):
        state = _engine([_rule({"type": "max", "key": "stats.hp"})]).run()
        assert math.isclose(state.actors["e3"].current_hp, _HP["e3"] - 1350.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"])

    def test_broken_selector(self):
        eng = _engine([_rule("broken")])
        eng.state.actors["e1"].broken = True
        state = eng.run()
        # 已击破目标 base_universal=1.0（未击破 0.9）→ 1350/0.9=1500
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"] - 1500.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e2"].current_hp, _HP["e2"])

    def test_no_rule_falls_back_to_first(self):
        """空 target_rules：主目标=第一个存活敌人（默认行为不变）."""
        state = _engine([]).run()
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"] - 1350.0, rel_tol=1e-9)


class TestBlastPrimaryViaPolicy:
    def test_blast_expands_around_picked_primary(self):
        """policy 选中中间目标时，扩散以它为中心向两侧展开."""
        blast = Action(action_id="blast", name="扩散", action_type="basic", target_type="blast",
                       damage_type="fire", scaling=[{"atk": 1.0}],
                       scaling_blast=[{"atk": 0.5}], toughness_dmg=20)
        state = _engine([_rule("lowest_hp")], action=blast).run()
        # 主目标 e2（hp 最低），相邻 e1+e3 各吃副倍率
        assert math.isclose(state.actors["e2"].current_hp, _HP["e2"] - 1350.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"] - 675.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e3"].current_hp, _HP["e3"] - 675.0, rel_tol=1e-9)
        assert math.isclose(state.total_damage, 2700.0, rel_tol=1e-6)
