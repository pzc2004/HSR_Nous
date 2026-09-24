"""heal 的 ratio/amount 逐目标求值（$target 注入——"按受疗者生命上限治疗"族）.

首实例：阿格莱雅 1402 战技 `param(140202, 1) * $target.max_hp`（打标 1402 实证——此前数值槽
 caster 侧一次求值，$target 未注入 ExpressionError）。施放者侧 $self 写法求值不变。
"""

from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from tests._builders import engine_vs_dummy, make_actor, make_dummy


def _engine(hooks) -> CombatEngine:
    eng = engine_vs_dummy(
        hero=make_actor("hero", "施放者"),
        allies=[make_actor("ally", "队友", hp=2000, atk=500, spd=100)],
        enemies=[make_dummy()])
    st = eng.state.actors["hero"]
    for h in hooks:
        eng._hooks._run_hook_effect(st, h, {})
    return eng


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
