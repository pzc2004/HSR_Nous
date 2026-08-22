"""Rulebook 加载器健全性：预编译产物结构完整、路由闭合、消费面齐备."""
from __future__ import annotations

import ast as _ast

from hsr_nous.sim_schema.rulebook import get_rulebook


def test_rulebook_loads_precompiled():
    rb = get_rulebook()
    # 公式族 + 削韧公式齐备（欢愉表达式入簿备镜，但路由不接）
    for key in ("damage", "damage_expected", "true_damage", "break_damage",
                "super_break_damage", "dot_damage", "elation_damage", "heal",
                "shield", "toughness_damage"):
        assert key in rb.formulas, f"formula {key} 缺失"
    assert rb.zones and rb.break_effects


def test_route_closed_and_mode_complete():
    """route 表：每个伤害类别两种模式都指向已定义的公式键（新类别 = 加一行即生效）."""
    rb = get_rulebook()
    for category, by_mode in rb.route.items():
        assert set(by_mode) == {"roll", "expected"}, f"{category} 模式不全"
        for mode, key in by_mode.items():
            assert key in rb.formulas, f"route[{category}][{mode}] → 未定义公式 {key!r}"
    # 欢愉未实装：表达式在簿但不得有路由（实例垫底纪律）
    assert not any("elation" in key for by_mode in rb.route.values() for key in by_mode.values())


def test_consumed_zones_defined():
    """引擎消费的公式（direct/break 两路由）引用的乘区名全部在 zones 有定义."""
    rb = get_rulebook()
    consumed = {rb.route[c][m] for c in ("direct", "break") for m in ("roll", "expected")}
    for key in consumed:
        names = {n.id for n in _ast.walk(rb.formulas[key].tree) if isinstance(n, _ast.Name)}
        for name in names:
            assert name in rb.zones or name == "ability_multiplier", (
                f"公式 {key} 引用未定义乘区 {name!r}")


def test_constants_present():
    rb = get_rulebook()
    assert rb.constants["non_weakness_res"] == 0.20
    assert rb.constants["default_target_def"] == 1000.0
