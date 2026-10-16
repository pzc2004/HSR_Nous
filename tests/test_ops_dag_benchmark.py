"""ServiceDispatcher mock 执行：无外部调用、依赖、容量与优先级可验."""

from __future__ import annotations

import pytest

from hsr_nous.ops.dag.benchmark import run_dispatcher_mock
from hsr_nous.ops.dag.simulation import SimTask


def _assert_complete_and_ordered(tasks, result):
    assert {trace.task_id for trace in result.traces} == {task.task_id for task in tasks}
    traces = {trace.task_id: trace for trace in result.traces}
    for task in tasks:
        trace = traces[task.task_id]
        assert trace.end >= trace.start >= trace.ready_at >= 0
        assert trace.wait == pytest.approx(trace.start - trace.ready_at)
        for dep in task.deps:
            assert traces[dep].end <= trace.start + 1e-9


def test_dispatcher_mock_runs_dag_without_external_calls():
    tasks = [
        SimTask("root", "llm", 0.001),
        SimTask("a", "web", 0.001, deps=("root",)),
        SimTask("b", "llm", 0.001, deps=("root",)),
        SimTask("join", "compile", 0.001, deps=("a", "b")),
    ]
    result = run_dispatcher_mock(
        tasks, {"llm": 2, "web": 1, "compile": 1}, sleep=lambda _duration: None)
    _assert_complete_and_ordered(tasks, result)
    assert result.makespan >= 0


def test_dispatcher_mock_applies_structural_priority():
    tasks = [
        SimTask("0_blocker", "svc", 0.05),
        SimTask("a_low", "svc", 0.001),
        SimTask("z_high", "svc", 0.001),
    ]
    result = run_dispatcher_mock(
        tasks, {"svc": 1},
        priorities={"0_blocker": 100.0, "a_low": 0.0, "z_high": 10.0})
    assert result.start_order == ("0_blocker", "z_high", "a_low")


def test_mock_preserves_service_capacity():
    tasks = [SimTask(f"n{i}", "svc", 0.02) for i in range(6)]
    result = run_dispatcher_mock(tasks, {"svc": 2})
    events = []
    for trace in result.traces:
        events.append((trace.start, 1))
        events.append((trace.end, -1))
    active = max_active = 0
    for _time, delta in sorted(events, key=lambda event: (event[0], event[1])):
        active += delta
        max_active = max(max_active, active)
    assert max_active <= 2


def test_mock_rejects_dynamic_arrival_and_missing_capacity():
    arriving = [SimTask("a", "svc", 0.001, arrival=1)]
    with pytest.raises(ValueError, match="arrival=0"):
        run_dispatcher_mock(arriving, {"svc": 1})
    with pytest.raises(KeyError, match="缺少服务容量"):
        run_dispatcher_mock([SimTask("a", "svc", 0.001)], {})
