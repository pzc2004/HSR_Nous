"""受击回能（v0.9，mechanics 05 §5.1/§5.3 为唯一事实来源）.

- 档位 5/10/15/20/25，per-attack 归属（敌人攻击自带 energy_grant）
- 吃受击方 ERR（不在具名豁免清单）；护盾挡住照样回能（owner 实战确认）
- 多段攻击按段拆分（Fandom Hit Split）
- 忆灵受击归忆师；忆师+忆灵同被多目标命中，两次都归忆师
- 发射点：on_gain_energy waterfall（before_gain 模式）
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _ally(aid="h", taunt=100.0, err=1.0, atk=0.0):
    return Actor(actor_id=aid, name=aid, level=80,
                 stats=StatBlock(hp=3000, def_=1000, spd=100, max_energy=100,
                                 energy_regen=err, taunt=taunt, atk=atk))


def _summon():
    return Actor(actor_id="m", name="忆灵", actor_type="summon", level=80, summoner_id="h",
                 stats=StatBlock(hp=2000, def_=1000, spd=90, max_energy=0, taunt=100))


def _enemy(atk=1000.0):
    return Actor(actor_id="e", name="敌", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=atk, spd=50, max_toughness=9999,
                                 weakness=["fire"]))


def _enemy_atk(grant, instances=1, tt="single"):
    return Action(action_id="e_atk", name="爪击", action_type="basic", target_type=tt,
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0,
                  energy_grant=grant, instances=instances)


def _engine(allies, enemy_act, av=250.0):
    enc = Encounter(encounter_id="t", name="t", actors=list(allies) + [_enemy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"e": [enemy_act]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestHitEnergy:
    @pytest.mark.parametrize("grant", [5, 10, 15, 20, 25])
    def test_five_tiers(self, grant):
        """五档受击回能：ERR=100% 时获得 = 档位值."""
        eng = _engine([_ally()], _enemy_atk(grant))
        eng._execute_action(eng.state.actors["e"], _enemy_atk(grant))
        assert math.isclose(eng.state.actors["h"].current_energy, float(grant))

    def test_err_amplifies(self):
        """吃 ERR：energy_regen 1.2 → 10 档回 12."""
        eng = _engine([_ally(err=1.2)], _enemy_atk(10))
        eng._execute_action(eng.state.actors["e"], _enemy_atk(10))
        assert math.isclose(eng.state.actors["h"].current_energy, 12.0)

    def test_shielded_hit_still_grants(self):
        """护盾挡住照样回能（owner 实战确认）."""
        eng = _engine([_ally()], _enemy_atk(10))
        st = eng.state.actors["h"]
        eng._apply_modifier_spec(st, {"modifier_id": "SH", "name": "盾", "duration": 3,
                                      "shield": {"flat": 5000.0}}, st)
        eng._execute_action(eng.state.actors["e"], _enemy_atk(10))
        assert math.isclose(st.current_hp, 3000.0), "伤害全被盾吸收"
        assert math.isclose(st.current_energy, 10.0), "打盾照回"

    def test_multi_instance_grants_per_segment(self):
        """多段攻击按段拆分：3 段 × 10 档 = 30."""
        eng = _engine([_ally()], _enemy_atk(10, instances=3))
        eng._execute_action(eng.state.actors["e"], _enemy_atk(10, instances=3))
        assert math.isclose(eng.state.actors["h"].current_energy, 30.0)

    def test_memosprite_hit_goes_to_master(self):
        """忆灵受击归忆师；忆灵自己不持能量."""
        eng = _engine([_ally(), _summon()], _enemy_atk(10))
        m = eng.state.actors["m"]
        m.actor.stats.taunt = 500.0  # 期望模式锁定忆灵为目标
        eng._execute_action(eng.state.actors["e"], _enemy_atk(10))
        assert math.isclose(eng.state.actors["h"].current_energy, 10.0)
        assert math.isclose(m.current_energy, 0.0)

    def test_aoe_hitting_both_grants_master_twice(self):
        """多目标同中忆师+忆灵：两次受击回能都归忆师（05:79-80）."""
        eng = _engine([_ally(), _summon()], _enemy_atk(10, tt="aoe"))
        eng._execute_action(eng.state.actors["e"], _enemy_atk(10, tt="aoe"))
        assert math.isclose(eng.state.actors["h"].current_energy, 20.0)

    def test_lethal_hit_grants_nothing(self):
        """被一击打死：死亡单位不回能."""
        enc = Encounter(encounter_id="t", name="t",
                        actors=[_ally(), Actor(actor_id="e", name="强敌", actor_type="monster",
                                               level=80, stats=StatBlock(
                                                   hp=1e9, atk=100000, spd=50,
                                                   max_toughness=9999, weakness=["fire"]))],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=250))
        eng = CombatEngine(enc, actions_by_actor={"e": [_enemy_atk(10)]},
                           policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        eng._execute_action(eng.state.actors["e"], _enemy_atk(10))
        st = eng.state.actors["h"]
        assert not st.alive
        assert math.isclose(st.current_energy, 0.0)

    def test_on_gain_energy_waterfall_payload(self):
        """发射点载荷：actor/amount/source/reason，waterfall 可改写量."""
        eng = _engine([_ally()], _enemy_atk(10))
        seen = []
        eng.bus.subscribe_waterfall(
            "on_gain_energy",
            lambda et, p, ctx: (seen.append(dict(p)), {"amount": p["amount"] * 2})[1])
        eng._execute_action(eng.state.actors["e"], _enemy_atk(10))
        assert seen and seen[0]["actor"] == "h" and seen[0]["reason"] == "being_hit"
        assert seen[0]["source"] == "e" and seen[0]["amount"] == 10
        assert math.isclose(eng.state.actors["h"].current_energy, 20.0), "waterfall 改写 10→20"
