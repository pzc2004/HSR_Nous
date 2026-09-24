"""B5 事件/表达式杂项：before_consume 抵扣 + after_consume + $last/$prev + $modifier.source.

语义钉：before_consume=waterfall（改写消耗量/取消，抵扣发生在扣减前）；after_consume=emit
（实际消耗量）；$last/$prev 同值（决策卡 #20 合并命名）= effects 链上一个 effect 的主数值
（deal_damage/heal 的 actual_amount 合计）；$modifier.source 由发射点供给/实例反查兜底。
"""
from __future__ import annotations

import math
import types

import pytest

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _engine(decls=None):
    actors = [Actor(actor_id="hero", name="hero", level=80,
                    stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100,
                                    crit_rate=0.0, crit_dmg=0.5)),
              Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                    stats=StatBlock(hp=1e9, spd=50, max_toughness=9999, weakness=["physical"]))]
    enc = Encounter(encounter_id="t", name="t", actors=actors,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=MODE_EXPECTED, seed=None, initial_sp=3,
                       initial_energy_ratio=0.0, resource_decls=decls or {})
    eng.setup()
    return eng


class TestBeforeAfterConsume:
    def test_before_consume_reduce_amount(self):
        """抵扣：waterfall 改写消耗量减半 → 实际只扣一半（火花 climax 抵扣族同构）."""
        eng = _engine({"hero": {"r": {"max": 10, "current": 8.0}}})
        st = eng.state.actors["hero"]
        eng.bus.subscribe_waterfall("before_consume", lambda et, p, ctx: {"amount": p["amount"] / 2})
        seen = []
        eng.bus.subscribe("after_consume", lambda et, p, ctx: seen.append(p))
        eng._gain_resource(st, "r", -4.0)
        assert math.isclose(st.resources["r"], 6.0), "消耗量被 waterfall 改写为一半"
        assert seen and seen[0]["amount"] == 2.0 and seen[0]["current"] == 6.0

    def test_before_consume_cancel(self):
        """取消：消耗整笔被抵扣——资源不动、无 after_consume."""
        eng = _engine({"hero": {"r": {"max": 10, "current": 8.0}}})
        st = eng.state.actors["hero"]
        eng.bus.subscribe_waterfall("before_consume", lambda et, p, ctx: {"cancel": True})
        seen = []
        eng.bus.subscribe("after_consume", lambda et, p, ctx: seen.append(p))
        assert eng._gain_resource(st, "r", -4.0) == 0.0
        assert st.resources["r"] == 8.0 and seen == []

    def test_sp_consume_events(self):
        """SP 通道同接：before_consume 取消 → 战技不扣点；否则 after_consume 照常."""
        eng = _engine()
        seen = []
        eng.bus.subscribe("after_consume", lambda et, p, ctx: seen.append(p))
        eng._adjust_skill_points(-1)
        assert eng.state.skill_points == 2 and seen and seen[0]["resource_id"] == "sp"
        eng.bus.subscribe_waterfall("before_consume", lambda et, p, ctx: {"cancel": True})
        eng._adjust_skill_points(-2)
        assert eng.state.skill_points == 2, "before_consume cancel → 战技点不扣"


class TestLastPrevNamespace:
    def test_last_records_previous_effect(self):
        """$last.actual_amount = 上一个 effect 的伤害合计；$prev 同值（#20 合并命名）."""
        eng = _engine()
        st = eng.state.actors["hero"]
        hook = types.SimpleNamespace(effects=[
            {"effect_type": "deal_damage", "target": "enemy_first", "scaling_atk": 1.0,
             "damage_type": "physical", "name": "试探"},
            {"effect_type": "gain_resource", "resource_id": "r",
             "amount": "$last.actual_amount"},
            {"effect_type": "gain_resource", "resource_id": "r2",
             "amount": "$prev.actual_amount"},
        ])
        eng._hooks._run_hook_effects(st, hook, {})
        dealt = st.resources.get("r", 0.0)
        assert dealt > 0, "$last 应读到 deal_damage 的实际伤害"
        assert math.isclose(dealt, st.resources.get("r2", 0.0)), "$prev 与 $last 同值（#20）"

    def test_last_empty_at_chain_start(self):
        """链首 effect 的 $last 为空命名空间——引用字段按求值失败口径（不静默吞）."""
        eng = _engine()
        st = eng.state.actors["hero"]
        hook = types.SimpleNamespace(effects=[
            {"effect_type": "gain_resource", "resource_id": "r",
             "amount": "$last.actual_amount"},
        ])
        with pytest.raises(Exception):
            eng._hooks._run_hook_effects(st, hook, {})


class TestModifierSourceNamespace:
    def test_modifier_source_from_remove_payload(self):
        """after_remove_modifier payload 带原施加者 → $modifier.source 可寻址（昔涟回源族）."""
        eng = _engine()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(
            modifier_id="MARK_X", name="未来标记", modifier_type="buff",
            duration=1, source_id="cyrene"))
        fired = []
        hook_hit = types.SimpleNamespace(
            event="after_remove_modifier",
            condition_expr=None,
            effects=[{"effect_type": "gain_resource", "resource_id": "r", "amount": 1}])
        # 用条件闸验证寻址：source 命中才执行
        eng._hooks._run_hook_effects(st, hook_hit, {"modifier_id": "MARK_X", "source": "cyrene",
                                                    "target": "hero"})
        assert st.resources.get("r", 0.0) == 1.0
        # 真实摘除路径：payload 由发射点供给 source
        captured = []
        eng.bus.subscribe("after_remove_modifier", lambda et, p, ctx: captured.append(p))
        eng._remove_modifier(st, "MARK_X", "consume")
        assert captured and captured[0]["source"] == "cyrene"

    def test_modifier_namespace_condition(self):
        """$modifier.source 进 hook condition 求值（命名空间已注册，不是裸名炸）."""
        eng = _engine()
        st = eng.state.actors["hero"]
        ctx = eng._hooks._hook_ctx(st, {"modifier_id": "M", "source": "s1", "target": "hero"})
        assert ctx["modifier"].source == "s1"
        assert eng._expr.evaluate(
            eng._expr.compile("$modifier.source == 's1'", layer="effect"), ctx) is True
