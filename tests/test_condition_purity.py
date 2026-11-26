"""G2 求值域纯度闸：condition 不消耗主 RNG + count_selected 与目标选择计数一致。

condition 是快照域（_roll_readonly=True，§23.15 分域规则）——只读已绑定 roll、禁采样。
count_selected 与 _hook_target_states 同走目标代数（resolve_pool + eval_algebra），
对同一 spec 须同计数——防 dict/concat 自实现分叉（报告 F02 病灶：WIP 引入分叉时本闸当场红）。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_ROLL
from tests.test_compile_gates import _build, _stage


def _roll_engine() -> CombatEngine:
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(), _stage()), mode=MODE_ROLL, seed=1)
    eng.setup()
    return eng


_SPECS = [
    ("enemies", "true"),
    ("allies", "true"),
    ("enemies", "actor_alive($it)"),
    ("allies", "actor_type_of($it) != 'summon'"),
]


@pytest.mark.parametrize("pool,where", _SPECS)
def test_count_selected_matches_target_states(pool, where):
    """count_selected 与 _hook_target_states 对同一 pool/where 须同计数。"""
    eng = _roll_engine()
    st = eng.state.actors["hero"]
    funcs = eng._hooks._hook_functions(st, _roll_readonly=True)
    n_count = funcs["count_selected"](pool, where)
    n_states = len(eng._hooks._hook_target_states(
        {"pool": pool, "where": where}, st, {}))
    assert n_count == n_states, (
        f"count_selected({pool!r},{where!r})={n_count} 与目标选择计数 {n_states} 分叉")


@pytest.mark.parametrize("pool,where", _SPECS)
def test_condition_count_selected_does_not_advance_rng(pool, where):
    """condition 域求值（含 count_selected）不得推进主随机流——世界线静默漂移闸。"""
    eng = _roll_engine()
    st = eng.state.actors["hero"]
    rng = eng.pipeline.rng
    funcs = eng._hooks._hook_functions(st, _roll_readonly=True)
    before = rng.getstate()
    funcs["count_selected"](pool, where)
    assert rng.getstate() == before, (
        f"condition 求值消耗了主随机流：count_selected({pool!r},{where!r})")