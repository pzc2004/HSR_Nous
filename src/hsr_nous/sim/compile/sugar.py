"""糖 desugar 展开器：表面糖 → 核心原语（VM 只见展开产物）.

> **未接线（设计预览）**：本模块是 04_modifier.md §4.12-4.14 糖族的展开器原型，
> 编译链路**未接入**——`trigger_limit` 等糖键写在模板/hook/modifier dict 里会被
> 编译器按"已知但未落地"拒绝（build_compiler `_SUGAR_KEYS_UNWIRED`，编译期炸，
> 不是静默吞）。desugar 落地前请勿在模板中使用糖键。

纪律（22_syntax_reference.md §22.13）：
- 宏体纯数据变换（禁计算——计算只能出现在白名单表达式里）
- 展开深度上限 + 禁循环引用
- 先展开后过同一编译期校验（键 diff / effect_type 白名单 / 表达式白名单）
- VM 只见原语

v0.3 首糖：trigger_limit → 计数器三联件（资源声明 + 重置 hook + 消耗门控）。
"""
from __future__ import annotations

from typing import Any, Dict, List

MAX_EXPANSION_DEPTH = 8

# trigger_limit 的窗口档 → 重置事件（发射点）
_WINDOW_RESET_EVENT = {
    "per_turn": "on_turn_start",
    "per_wave": "on_wave_start",
    "per_action": "on_after_action",
    "per_attack": "on_after_action",
    "per_instance": "after_apply_modifier",
    "once_per_battle": None,          # 不重置
    "per_battle": None,
    "cooldown_turns": "on_turn_start",
    "per_target": None,               # 计数器按目标实例化，事件在参数里
}


class SugarError(ValueError):
    """糖展开错误（未知档/循环引用/深度超限）."""


def desugar_trigger_limit(spec: Dict[str, Any], *, owner_modifier_id: str, depth: int = 0) -> Dict[str, Any]:
    """trigger_limit 糖 → 计数器三联件（资源声明 + 重置 hook + 消耗门控）.

    返回引擎可直接注册的展开产物：
      resource: {resource_id, max}
      reset_hooks: [{event, effects:[gain_resource full]}]
      gate_condition: 表达式字符串（"$resource.x > 0"）
      consume_effect: {effect_type: consume_resource, amount: 1}
    """
    if depth > MAX_EXPANSION_DEPTH:
        raise SugarError(f"trigger_limit 展开深度超限（{depth} > {MAX_EXPANSION_DEPTH}）")

    count = 1
    window = "per_turn"
    reset_on: str | None = None
    for key, val in spec.items():
        if key == "count":
            count = int(val)
        elif key == "reset_on":
            reset_on = str(val)
        elif key in _WINDOW_RESET_EVENT:
            window = key
            if key in ("cooldown_turns", "per_battle"):
                count = int(val)
        else:
            raise SugarError(f"trigger_limit 未知窗口档：{key}")

    resource_id = f"_tl_{owner_modifier_id}"
    reset_event = reset_on or _WINDOW_RESET_EVENT[window]

    return {
        "resource": {"resource_id": resource_id, "max": float(count)},
        "reset_hooks": (
            [] if reset_event is None else [{
                "event": reset_event,
                "effects": [{
                    "effect_type": "gain_resource",
                    "resource_id": resource_id,
                    "amount": "full",
                }],
            }]
        ),
        "gate_condition": f"$resource.{resource_id} > 0",
        "consume_effect": {
            "effect_type": "consume_resource",
            "resource_id": resource_id,
            "amount": 1,
        },
        "window": window,
    }


# 糖注册表：新增糖在此登记（闭合关键字集，未登记 = validator error）
_SUGARS = {
    "trigger_limit": desugar_trigger_limit,
}


def desugar(name: str, spec: Dict[str, Any], *, depth: int = 0, **kwargs) -> Dict[str, Any]:
    """按名展开糖；未登记的糖名 = SugarError."""
    fn = _SUGARS.get(name)
    if fn is None:
        raise SugarError(f"未登记的糖：{name}（闭合关键字集，新增须决策卡）")
    return fn(spec, depth=depth, **kwargs)


def list_sugars() -> List[str]:
    return sorted(_SUGARS)
