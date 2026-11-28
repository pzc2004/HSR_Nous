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


# ---------------------------------------------------------------------------
# dict/concat 规格面——F02 真正病灶（上面字符串 pool 路径本就一致，漏的是这些）：
# 旧 count_selected 自实现 concat，把外层 take 逐子块应用再求和、忽略函数级
# where/include_unselectable、random/pre_shuffle 经目标解析掷骰耗主 RNG。
# ---------------------------------------------------------------------------

def _multi_engine() -> CombatEngine:
    """两敌一友——concat/take/random 计数分歧需要多于一个候选。"""
    stage = _stage(enemies=[
        {"actor_id": "e1", "name": "假人甲", "hp": 1e6, "spd": 100, "max_toughness": 30},
        {"actor_id": "e2", "name": "假人乙", "hp": 1e6, "spd": 90, "max_toughness": 30},
    ])
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(), stage), mode=MODE_ROLL, seed=1)
    eng.setup()
    return eng


_DICT_SPECS = [
    {"pool": "enemies"},
    {"pool": "enemies", "where": "actor_alive($it)"},
    {"pool": "enemies", "take": 1},
    {"pool": "enemies", "order_by": "-$it.hp", "take": 1},
    {"pool": "enemies", "mode": "random", "take": 1},
    {"pool": "enemies", "mode": "shuffle"},
    {"pool": "enemies", "pre_shuffle": True, "take": 1},
    {"concat": [{"pool": "enemies"}, {"pool": "allies"}]},
    {"concat": [{"pool": "enemies"}, {"pool": "allies"}], "take": 1},
    {"concat": [{"pool": "enemies", "take": 1}, {"pool": "allies"}], "take": 1},
]


@pytest.mark.parametrize("spec", _DICT_SPECS)
def test_count_selected_dict_matches_effect_target(spec):
    """count_selected 与 effect 目标选择对同一 dict/concat 规格须同计数（单一解析路径）。"""
    eng = _multi_engine()
    st = eng.state.actors["hero"]
    funcs = eng._hooks._hook_functions(st, _roll_readonly=True)
    n_count = funcs["count_selected"](spec)
    n_effect = len(eng._hooks._hook_target_states(spec, st, {}))
    assert n_count == n_effect, (
        f"count_selected({spec})={n_count} 与 effect 选择 {n_effect} 分叉")


@pytest.mark.parametrize("spec", _DICT_SPECS)
def test_count_selected_dict_does_not_advance_rng(spec):
    """dict/concat（含 random/shuffle/pre_shuffle）计数不得推进主随机流。"""
    eng = _multi_engine()
    st = eng.state.actors["hero"]
    rng = eng.pipeline.rng
    funcs = eng._hooks._hook_functions(st, _roll_readonly=True)
    before = rng.getstate()
    funcs["count_selected"](spec)
    assert rng.getstate() == before, f"count_selected({spec}) 消耗了主随机流"


def test_concat_take_applies_once_to_union():
    """钉死：concat 外层 take 对并集应用一次，非逐子块各取再求和。"""
    eng = _multi_engine()
    st = eng.state.actors["hero"]
    funcs = eng._hooks._hook_functions(st, _roll_readonly=True)
    # 两敌 + 一友 = 并集 3，take:1 → 1（旧病灶：逐子块 take1 求和 → 2）
    spec = {"concat": [{"pool": "enemies"}, {"pool": "allies"}], "take": 1}
    assert funcs["count_selected"](spec) == 1.0


def test_function_level_where_applies_to_dict_spec():
    """钉死：函数级 where 并入 dict 规格（旧分支忽略 → 计数偏大）。"""
    eng = _multi_engine()
    st = eng.state.actors["hero"]
    eng.state.actors["e1"].broken = True  # 击破 e1，e2 未击破
    funcs = eng._hooks._hook_functions(st, _roll_readonly=True)
    assert funcs["count_selected"]({"pool": "enemies"}, "$it.broken") == 1.0


def test_target_predicates_do_not_advance_rng_in_condition_domain():
    """target_in_selected/target_lists_intersect 在条件（快照）域禁采样——
    旧未转发 allow_sample=False，random 规格下推进主 RNG（与 count_selected 分叉）。"""
    eng = _multi_engine()
    st = eng.state.actors["hero"]
    rng = eng.pipeline.rng
    funcs = eng._hooks._hook_functions(st, _roll_readonly=True)
    spec = {"pool": "enemies", "take": 1, "mode": "random"}
    for fn, args in (("target_in_selected", (spec, "e1")),
                     ("target_lists_intersect", (spec, {"pool": "enemies"}))):
        before = rng.getstate()
        funcs[fn](*args)
        assert rng.getstate() == before, f"{fn} 在条件域消耗了主随机流"