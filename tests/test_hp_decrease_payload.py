"""on_hp_decrease 受击族载荷：is_critical 键（暴击门控族挂载点——丹恒 100202 战技暴击减速）.

两发射点（action 伤害 / hook deal_damage）同带；期望模式恒 False（期望暴击区并入伤害无离散
暴击），掷骰模式读判定 trace。挂载先例字段名与 before_take_damage/after_being_hit 同
（is_critical——打标稿 $event.crit 错拼族的对照钉：字段名以本件与 23 章事件表为准）。
"""

from __future__ import annotations

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _engine(*, mode: str, crit_rate: float = 0.05, seed: int = 7) -> CombatEngine:
    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(hp=5000, atk=2000, spd=200, max_energy=100,
                                 crit_rate=crit_rate, crit_dmg=1.0))
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["fire"]))
    basic = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                   damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10)
    enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=50))
    eng = CombatEngine(enc, actions_by_actor={"hero": [basic]},
                       policy=ScriptedPolicy(), mode=mode, initial_energy_ratio=0.0, seed=seed)
    eng.setup()
    return eng


def _hit_payloads(eng):
    drops = []
    eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: drops.append(p))
    st = eng.state.actors["hero"]
    a = eng.actions_by_actor["hero"][0]
    eng._execute_action(st, a)
    return [p for p in drops if p.get("reason") == "hit"]


def test_expected_mode_payload_carries_is_critical_false():
    hits = _hit_payloads(_engine(mode=MODE_EXPECTED))
    assert hits and all(p["is_critical"] is False for p in hits), (
        "受击族载荷带 is_critical 键——期望模式恒 False（无离散暴击）")


def test_roll_mode_guaranteed_crit_marks_true():
    hits = _hit_payloads(_engine(mode=MODE_ROLL, crit_rate=1.0))
    assert hits and all(p["is_critical"] is True for p in hits), (
        "掷骰模式 crit_rate=1.0 必暴 → is_critical=True（判定 trace 读法）")
