"""F07：死者/放逐者不占行动条首位（is_top_action_delay_target 谓词自滤死亡）。

preview 只滤冻结不滤死亡，死者留树到下次 pop；谓词须自滤 alive/banished，
否则任意死亡后一整个回合内 ByIsTopActionDelayEntity 指向错误单位。
"""
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _enemy(aid: str, spd: float) -> Actor:
    return Actor(actor_id=aid, name=aid, actor_type="monster", level=80,
                 stats=StatBlock(hp=1000, atk=100, spd=spd, max_toughness=30))


def _atk() -> Action:
    return Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0)


def _eng():
    enc = Encounter(encounter_id="t", name="t",
                    actors=[_enemy("e1", 200), _enemy("e2", 100)],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=250))
    eng = CombatEngine(enc, actions_by_actor={"e1": [_atk()], "e2": [_atk()]},
                       policy=ScriptedPolicy(rotation=["basic"]),
                       mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def test_dead_unit_not_top_action_delay():
    eng = _eng()
    top = eng._hooks._hook_functions(eng.state.actors["e1"])["is_top_action_delay_target"]
    assert top("e1", "dark") == 1.0          # e1 spd200 居首
    eng.state.actors["e1"].alive = False     # 杀死 e1（留树未 pop）
    assert top("e1", "dark") == 0.0          # 死者不占首位
    assert top("e2", "dark") == 1.0          # 活着的 e2 顶上


def test_banished_unit_not_top_action_delay():
    eng = _eng()
    top = eng._hooks._hook_functions(eng.state.actors["e1"])["is_top_action_delay_target"]
    eng.state.actors["e1"].banished = True
    assert top("e1", "dark") == 0.0
    assert top("e2", "dark") == 1.0
