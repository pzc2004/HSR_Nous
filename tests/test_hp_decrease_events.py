"""on_hp_decrease 发射点补齐 + 尸体 DoT 停跳（dead-skip）.

spec 锚点：23_event_hook_system §23.4（on_hp_decrease，payload amount/source/reason/target，emit）
+ mechanics 11 §11.3（受击/自伤/DOT/HP 消耗/流血等一切 HP 降低来源都触发）
+ 05_effects §生命汲取/生命流失（drain 族 reason='drain'；其余 reason 按扣血路径名冻结，见 engine._execute_action）。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier, ShieldInstance
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _ally(hp: float = 3000.0) -> Actor:
    return Actor(actor_id="h", name="实验员", level=80,
                 stats=StatBlock(hp=hp, atk=1000, def_=1000, spd=100, max_energy=100))


def _enemy() -> Actor:
    return Actor(actor_id="e", name="强敌", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=100000, spd=50, max_toughness=9999,
                                 weakness=["fire"]))


def _enemy_atk() -> Action:
    return Action(action_id="e_atk", name="重击", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0)


def _engine() -> CombatEngine:
    enc = Encounter(encounter_id="t", name="t", actors=[_ally(), _enemy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=250))
    eng = CombatEngine(enc, actions_by_actor={"e": [_enemy_atk()]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _collect(eng: CombatEngine) -> list:
    events: list = []
    eng.bus.subscribe("on_hp_decrease", lambda t, p, c: events.append(p))
    return events


def _dot_mod(mid: str, atk: float = 500.0) -> Modifier:
    return Modifier(modifier_id=mid, name=f"灼烧{mid}", modifier_type="dot", debuff_kind="dot",
                    duration=2, source_id="e", dot_element="fire", dot_ratio=1.0,
                    dot_source_atk=atk)


class TestOnHpDecrease:
    def test_hit_emits_once_with_payload(self):
        """受击扣血：发一次，载荷 amount/source/reason/target 齐全且与实扣一致."""
        eng = _engine()
        events = _collect(eng)
        ally = eng.state.actors["h"]
        before = ally.current_hp
        eng._execute_action(eng.state.actors["e"], _enemy_atk())
        assert len(events) == 1
        p = events[0]
        assert p["reason"] == "hit" and p["source"] == "e" and p["target"] == "h"
        assert p["amount"] > 0
        assert math.isclose(p["amount"], before - ally.current_hp, rel_tol=1e-9)

    def test_dot_emits_once_with_payload(self):
        """DoT 跳伤：发一次 reason='dot'，amount = 实际扣血."""
        eng = _engine()
        ally = eng.state.actors["h"]
        mod = _dot_mod("DOT1")
        ally.modifiers[mod.modifier_id] = mod
        events = _collect(eng)
        before = ally.current_hp
        eng._tick_dots(ally)
        assert len(events) == 1
        p = events[0]
        assert p["reason"] == "dot" and p["source"] == "e" and p["target"] == "h"
        assert math.isclose(p["amount"], 500.0, rel_tol=1e-9)
        assert math.isclose(ally.current_hp, before - 500.0, rel_tol=1e-9)

    def test_shield_full_absorb_no_emit(self):
        """护盾全额吸收：HP 未下降 → 不发（事件语义是 HP 变化，不是伤害）."""
        eng = _engine()
        ally = eng.state.actors["h"]
        ally.shields.append(ShieldInstance(shield_id="s1", name="盾", remaining=1e9, source_id="h"))
        events = _collect(eng)
        eng._execute_action(eng.state.actors["e"], _enemy_atk())
        assert events == []
        assert math.isclose(ally.current_hp, ally.actor.stats.hp, rel_tol=1e-9)

    def test_set_hp_to_percent_decrease_emits(self):
        """HP 消耗（set_hp_to_percent 下调）：发一次 reason='set_hp'."""
        eng = _engine()
        ally = eng.state.actors["h"]
        events = _collect(eng)
        eng._run_hook_effect(ally, {"effect_type": "set_hp_to_percent", "percent": 0.4}, {}, {})
        assert len(events) == 1
        p = events[0]
        assert p["reason"] == "set_hp" and p["target"] == "h"
        assert math.isclose(p["amount"], 3000.0 * 0.6, rel_tol=1e-9)

    def test_heal_does_not_emit_decrease(self):
        """治疗不发 on_hp_decrease（那是 on_hp_increase 的地盘）."""
        eng = _engine()
        ally = eng.state.actors["h"]
        ally.current_hp = 1000.0
        dec = _collect(eng)
        inc: list = []
        eng.bus.subscribe("on_hp_increase", lambda t, p, c: inc.append(p))
        eng._run_hook_effect(ally, {"effect_type": "heal_self", "ratio": 0.4}, {}, {})
        assert dec == []
        assert len(inc) == 1 and inc[0]["reason"] == "heal"


class TestCorpseDotSkip:
    def test_second_dot_skipped_after_lethal_first(self):
        """双 DoT 第一张致死：第二张不跳、不计 total_damage（与主循环/_run_turn dead-skip 同口径）."""
        eng = _engine()
        ally = eng.state.actors["h"]
        ally.current_hp = 100.0  # 第一张 500 即致死
        for mid in ("DOT1", "DOT2"):
            ally.modifiers[mid] = _dot_mod(mid)
        events = _collect(eng)
        total_before = eng.state.total_damage
        eng._tick_dots(ally)
        assert not ally.alive
        assert len(events) == 1, "只有第一张 DoT 的扣血事件"
        assert math.isclose(eng.state.total_damage - total_before, 500.0, rel_tol=1e-9)
        assert "DOT2" in ally.modifiers, "第二张未结算（仍挂在身上）"
