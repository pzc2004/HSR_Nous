"""逐事件对拍器：第一分歧、数值容差与缺/多/顺序错误分类."""
from __future__ import annotations

import json

from hsr_nous.sim.trace_compare import compare_traces


def _action(seq: int, action_id: str = "a") -> dict:
    return {"seq": seq, "event_type": "action", "actor_id": "enemy",
            "action_id": action_id, "target_ids": ["hero"]}


def _damage(seq: int, amount: float) -> dict:
    return {"seq": seq, "event_type": "damage", "source_id": "enemy",
            "target_id": "hero", "damage": amount, "timestamp": 33.3333}


def test_identical_traces_match_and_report_is_json_serializable():
    expected = [_action(0), _damage(1, 100.0)]
    report = compare_traces(expected, expected)
    assert report == {"match": True, "first_divergence": None, "compared_events": 2}
    json.dumps(report)


def test_damage_and_av_use_independent_explicit_tolerances():
    expected = [_damage(0, 1000.0)]
    actual = [_damage(0, 1004.0)]
    assert not compare_traces(expected, actual)["match"]
    assert compare_traces(
        expected, actual,
        tolerance={"damage": {"relative": 0.005, "absolute": 0.0},
                   "av": {"relative": 0.0, "absolute": 0.001}},
    )["match"]


def test_action_order_never_hidden_by_damage_tolerance():
    expected = [_action(0, "a"), _action(1, "b")]
    actual = [_action(0, "b"), _action(1, "a")]
    report = compare_traces(
        expected, actual, tolerance={"damage": {"relative": 1.0, "absolute": 1e9}})
    diff = report["first_divergence"]
    assert diff["kind"] == "field_mismatch" and diff["field"] == "action_id"
    assert diff["seq"] == 0


def test_missing_middle_event_is_distinguished_from_order_error():
    expected = [_action(0), {"seq": 9, "event_type": "break", "target_id": "hero"},
                _action(2, "b")]
    actual = [_action(0), _action(2, "b")]
    # 列表位置发生位移；一步前视识别 expected 中缺失的 break。
    diff = compare_traces(expected, actual)["first_divergence"]
    assert diff["kind"] == "missing_event" and diff["seq"] == 9
    assert diff["actual"] == "<missing>"


def test_extra_middle_event_is_distinguished_from_order_error():
    expected = [_action(0), _action(2, "b")]
    actual = [_action(0), {"seq": 8, "event_type": "break", "target_id": "hero"},
              _action(2, "b")]
    diff = compare_traces(expected, actual)["first_divergence"]
    assert diff["kind"] == "extra_event" and diff["expected"] == "<missing>"


def test_first_field_divergence_reports_expected_actual_and_stops():
    expected = [_damage(0, 100.0), _action(1, "b")]
    actual = [_damage(0, 101.0), _action(1, "wrong")]
    report = compare_traces(expected, actual)
    assert report["compared_events"] == 0
    assert report["first_divergence"] == {
        "seq": 0, "kind": "field_mismatch", "event_type": "damage",
        "field": "damage", "expected": 100.0, "actual": 101.0,
    }


def test_missing_and_extra_tail_events_have_distinct_kinds():
    missing = compare_traces([_action(0), _action(1)], [_action(0)])
    assert missing["first_divergence"]["kind"] == "missing_event"
    extra = compare_traces([_action(0)], [_action(0), _action(1)])
    assert extra["first_divergence"]["kind"] == "extra_event"
