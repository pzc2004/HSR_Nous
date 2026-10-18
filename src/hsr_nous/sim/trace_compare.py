"""真实战斗 trace 对拍：按稳定 seq 找第一处分歧，不用数值容差掩盖顺序错误.

比较器只依赖事件字典，不绑定 StructuredLogger 或某一客户端记录格式。调用方负责把
expected/actual 规范化为同一事件词表；缺省容差为全 0，任何放宽都必须由 golden case
显式声明。本模块不产生 expected，也不把自洽模拟结果当作真实客户端证据。
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence

_DAMAGE_FIELDS = frozenset({"damage", "heal", "target_hp_before", "target_hp_after"})
_AV_FIELDS = frozenset({"timestamp", "action_value", "cycle_av"})
_MISSING = object()


def _tolerance(tolerance: Mapping[str, Any], family: str) -> tuple[float, float]:
    spec = tolerance.get(family) or {}
    return float(spec.get("relative", 0.0)), float(spec.get("absolute", 0.0))


def _number_equal(expected: float, actual: float, *, relative: float, absolute: float) -> bool:
    if not math.isfinite(expected) or not math.isfinite(actual):
        return expected == actual
    return abs(expected - actual) <= absolute + relative * max(abs(expected), abs(actual))


def _signature(event: Mapping[str, Any]) -> tuple:
    """用于缺失/额外事件的一步前视识别；顺序本身仍严格由 seq 比较."""
    return tuple(sorted((k, repr(v)) for k, v in event.items() if k != "seq"))


def _difference(seq: Any, kind: str, field: str, expected: Any, actual: Any,
                event_type: Any = None) -> Dict[str, Any]:
    return {
        "seq": seq,
        "kind": kind,
        "event_type": event_type,
        "field": field,
        "expected": "<missing>" if expected is _MISSING else expected,
        "actual": "<missing>" if actual is _MISSING else actual,
    }


def compare_traces(
    expected: Sequence[Mapping[str, Any]],
    actual: Sequence[Mapping[str, Any]],
    *,
    tolerance: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """比较规范化事件序列，返回可 JSON 序列化的报告.

    - 顺序按列表位置（事件可携带 seq 作为报告标识），不得用容差放行；
    - damage/heal/HP 数值使用 ``tolerance['damage']``；
    - timestamp/action_value/cycle_av 使用 ``tolerance['av']``；
    - 中间缺项/多项用一步前视区分，无法安全识别时标 order_error；
    - 只报告第一处分歧，调用方可据此修复后重跑，避免被下游连带差异淹没。
    """
    tolerance = tolerance or {}
    for i in range(min(len(expected), len(actual))):
        exp = expected[i]
        act = actual[i]
        seq = exp.get("seq", act.get("seq", i))
        exp_type = exp.get("event_type")
        act_type = act.get("event_type")
        if exp_type != act_type:
            kind = "order_error"
            shown_exp: Any = exp_type
            shown_act: Any = act_type
            if i + 1 < len(expected) and _signature(act) == _signature(expected[i + 1]):
                kind, shown_act = "missing_event", _MISSING
            elif i + 1 < len(actual) and _signature(expected[i]) == _signature(actual[i + 1]):
                kind, shown_exp = "extra_event", _MISSING
            return {
                "match": False,
                "first_divergence": _difference(
                    seq, kind, "event_type", shown_exp, shown_act, exp_type),
                "compared_events": i,
            }
        for field in sorted((set(exp) | set(act)) - {"seq", "event_type"}):
            left = exp.get(field, _MISSING)
            right = act.get(field, _MISSING)
            equal = left == right
            if left is not _MISSING and right is not _MISSING:
                if field in _DAMAGE_FIELDS:
                    family = "damage"
                elif field in _AV_FIELDS:
                    family = "av"
                else:
                    family = ""
                if family and isinstance(left, (int, float)) and isinstance(right, (int, float)) \
                        and not isinstance(left, bool) and not isinstance(right, bool):
                    relative, absolute = _tolerance(tolerance, family)
                    equal = _number_equal(
                        float(left), float(right), relative=relative, absolute=absolute)
            if not equal:
                return {
                    "match": False,
                    "first_divergence": _difference(
                        seq, "field_mismatch", field, left, right, exp_type),
                    "compared_events": i,
                }

    if len(expected) != len(actual):
        i = min(len(expected), len(actual))
        missing_from_actual = len(expected) > len(actual)
        event = expected[i] if missing_from_actual else actual[i]
        return {
            "match": False,
            "first_divergence": _difference(
                event.get("seq", i),
                "missing_event" if missing_from_actual else "extra_event",
                "event_type",
                event.get("event_type") if missing_from_actual else _MISSING,
                _MISSING if missing_from_actual else event.get("event_type"),
                event.get("event_type"),
            ),
            "compared_events": i,
        }
    return {"match": True, "first_divergence": None, "compared_events": len(expected)}
