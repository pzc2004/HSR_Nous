"""heal 的 ratio/amount 逐目标求值（$target 注入——"按受疗者生命上限治疗"族）.

首实例：阿格莱雅 1402 战技 `param(140202, 1) * $target.max_hp`（打标 1402 实证——此前数值槽
 caster 侧一次求值，$target 未注入 ExpressionError）。施放者侧 $self 写法求值不变。
"""

from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _engine(hooks) -> CombatEngine:
    hero = Actor(actor_id="hero", name="施放者", level=80,
                 stats=StatBlock(hp=5000, atk=2000, spd=200, max_energy=100))
    ally = Actor(actor_id="ally", name="队友", level=80,
                 stats=StatBlock(hp=2000, atk=500, spd=100, max_energy=100))
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["fire"]))
    basic = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                   damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=0)
    enc = Encounter(encounter_id="t", name="t", actors=[hero, ally, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=50))
    eng = CombatEngine(enc, actions_by_actor={"hero": [basic]},
                       policy=ScriptedPolicy(), mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    eng.state.actors["hero"].hooks = []  # 防默认干扰
    from hsr_nous.sim.hooks import HookRuntime
    _ = HookRuntime  # 标记：直接驱动 _run_hook_effect
    st = eng.state.actors["hero"]
    for h in hooks:
        eng._hooks._run_hook_effect(st, h, {})
    return eng


class _FakeHook(dict):
    """最小 effect 载体（_run_hook_effect 读 dict 键即可）."""


def _heal_effect(amount_expr):
    return {"effect_type": "heal", "target": "all_allies",
            "amount": amount_expr, "ratio": 0}


def test_heal_amount_per_target_max_hp():
    eng = _engine([_heal_effect("0.5 * $target.max_hp")])
    hero, ally = eng.state.actors["hero"], eng.state.actors["ally"]
    assert math.isclose(hero.current_hp, 5000.0), "施放者满血仍吃（clamp 上限）"
    assert math.isclose(ally.current_hp, 2000.0), "满血 clamp"
    # 打残再验按受疗者上限比例
    hero.current_hp, ally.current_hp = 1000.0, 500.0
    _engine_run(eng, amount_expr="0.5 * $target.max_hp")
    assert math.isclose(hero.current_hp, 1000.0 + 0.5 * 5000.0, rel_tol=1e-9), (
        "hero 按自己上限 50% 被治（$target=受疗者）")
    assert math.isclose(ally.current_hp, 500.0 + 0.5 * 2000.0, rel_tol=1e-9), (
        "ally 按自己上限 50% 被治——逐目标求值实证（非施放者口径）")


def _engine_run(eng, *, amount_expr):
    st = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(st, _heal_effect(amount_expr), {})


def test_heal_caster_side_expr_unchanged():
    eng = _engine([])
    hero = eng.state.actors["hero"]
    hero.current_hp = 1000.0
    eng._hooks._run_hook_effect(hero, _heal_effect("0.5 * $self.max_hp"), {})
    assert math.isclose(hero.current_hp, 1000.0 + 2500.0, rel_tol=1e-9), (
        "施放者侧 $self 写法求值不变（5000×0.5）")
