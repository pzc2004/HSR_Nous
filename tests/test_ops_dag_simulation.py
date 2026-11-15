"""ServiceDispatcher 离散事件仿真：HLF 理论锚、upward-rank、aging 与不变量."""

from __future__ import annotations

import random

import pytest

from hsr_nous.ops.dag import (
    SchedulingPolicy,
    SimTask,
    hlf_priorities,
    simulate,
    upward_ranks,
)


def _chain_forest():
    tasks = []
    for i in range(100):
        a, b = f"a{i:03d}", f"b{i:03d}"
        tasks.append(SimTask(a, "llm", 1))
        tasks.append(SimTask(b, "llm", 1, deps=(a,)))
    return tasks


def test_hlf_chain_forest_matches_work_lower_bound():
    tasks = _chain_forest()
    result = simulate(tasks, {"llm": 90}, priorities=hlf_priorities(tasks))
    assert result.makespan == 3, "200 个单位任务 / 90 槽的总工作量下界"

    waves = [{t.task_id for t in result.traces if t.start == start} for start in (0, 1, 2)]
    assert len(waves[0]) == 90 and all(t.startswith("a") for t in waves[0])
    assert len(waves[1]) == 90
    assert sum(t.startswith("a") for t in waves[1]) == 10
    assert sum(t.startswith("b") for t in waves[1]) == 80
    assert len(waves[2]) == 20 and all(t.startswith("b") for t in waves[2])

    by_id = {t.task_id: t for t in result.traces}
    for task in tasks:
        trace = by_id[task.task_id]
        for dep in task.deps:
            assert by_id[dep].end <= trace.start
    metrics = result.services["llm"]
    assert metrics.busy == 200
    assert metrics.idle == 70
    assert metrics.utilization == pytest.approx(200 / 270)


def test_chain_forest_baseline_and_reverse_priority_comparison():
    """同一负载同时跑基线与反向优先级：不预设所有策略都必须有差异."""
    tasks = _chain_forest()
    fifo = simulate(tasks, {"llm": 90}, policy=SchedulingPolicy.fifo())
    hlf = simulate(tasks, {"llm": 90}, priorities=hlf_priorities(tasks))
    assert fifo.makespan == hlf.makespan == 3, "此提交顺序下 FIFO 也恰好最优"

    # 人为让后继优先：第二阶段抢跑会把剩余第一阶段拖到尾部，作为反面对照。
    reverse = {t.task_id: (0.0 if t.task_id.startswith("a") else 1.0) for t in tasks}
    successor_first = simulate(tasks, {"llm": 90}, priorities=reverse)
    assert successor_first.makespan == 4
    assert hlf.makespan < successor_first.makespan


def test_upward_rank_uses_remaining_weighted_cost():
    tasks = [
        SimTask("a", "llm", 5, deps=()),
        SimTask("c", "llm", 4, deps=("a",)),
        SimTask("d", "llm", 2),
    ]
    ranks = upward_ranks(tasks)
    assert ranks == {"a": 9, "c": 4, "d": 2}
    result = simulate(tasks, {"llm": 1}, priorities=ranks)
    assert result.start_order == ("a", "c", "d")
    assert result.makespan == 11


def test_aging_prevents_bounded_starvation_scenario():
    tasks = [
        SimTask("blocker", "llm", 5, priority=100),
        SimTask("low", "llm", 1, priority=0),
    ]
    tasks += [SimTask(f"high{i}", "llm", 1, arrival=i, priority=1) for i in range(1, 5)]

    plain = simulate(tasks, {"llm": 1})
    aged = simulate(tasks, {"llm": 1}, policy=SchedulingPolicy(aging_rate=1))
    assert plain.start_order[1:6] == ("high1", "high2", "high3", "high4", "low")
    assert aged.start_order[1] == "low", "久等任务的 aging 抵消新到任务的结构优先级"
    assert aged.makespan == plain.makespan == 10


def test_multi_service_and_dynamic_arrival():
    tasks = [
        SimTask("a1", "llm", 2),
        SimTask("a2", "web", 1),
        SimTask("b", "llm", 1, deps=("a1", "a2")),
        SimTask("c", "web", 1, arrival=1),
    ]
    result = simulate(tasks, {"llm": 1, "web": 1})
    traces = {t.task_id: t for t in result.traces}
    assert traces["a1"].start == traces["a2"].start == 0
    assert traces["c"].start == 1
    assert traces["b"].start == 2
    assert result.makespan == 3
    assert result.services["llm"].busy == 3
    assert result.services["web"].busy == 2


def _random_dag(seed=7, count=40):
    rng = random.Random(seed)
    tasks = []
    services = ("llm", "web", "compile")
    for i in range(count):
        task_id = f"n{i:02d}"
        previous = [t.task_id for t in tasks]
        deps = tuple(sorted(rng.sample(previous, min(len(previous), rng.randint(0, 2))))) \
            if previous and rng.random() < 0.35 else ()
        tasks.append(SimTask(
            task_id, services[i % len(services)], rng.uniform(0.2, 2.0),
            deps=deps, arrival=rng.uniform(0, 5)))
    return tasks


def _assert_valid_simulation(tasks, capacities, result):
    assert len(result.traces) == len(tasks)
    by_id = {t.task_id: t for t in result.traces}
    for task in tasks:
        trace = by_id[task.task_id]
        assert trace.start >= task.arrival
        assert trace.ready_at >= task.arrival
        assert trace.start >= trace.ready_at
        assert trace.end - trace.start == pytest.approx(task.duration)
        assert trace.wait == pytest.approx(trace.start - trace.ready_at)
        for dep in task.deps:
            assert by_id[dep].end <= trace.start + 1e-9

    for service, capacity in capacities.items():
        events = []
        service_busy = 0.0
        for task in tasks:
            if task.service != service:
                continue
            trace = by_id[task.task_id]
            service_busy += task.duration
            events.append((trace.start, 1))
            events.append((trace.end, -1))
        active = max_active = 0
        for _time, delta in sorted(events, key=lambda event: (event[0], event[1])):
            active += delta
            max_active = max(max_active, active)
        assert max_active <= capacity
        assert result.services[service].busy == pytest.approx(service_busy)
        assert result.services[service].idle == pytest.approx(
            capacity * result.makespan - service_busy)


def test_random_dag_invariants_for_baseline_and_hlf():
    tasks = _random_dag()
    capacities = {"llm": 3, "web": 2, "compile": 1}
    baseline = simulate(tasks, capacities, policy=SchedulingPolicy.fifo())
    hlf = simulate(tasks, capacities, priorities=hlf_priorities(tasks))
    _assert_valid_simulation(tasks, capacities, baseline)
    _assert_valid_simulation(tasks, capacities, hlf)
    assert baseline.makespan > 0 and hlf.makespan > 0


def test_invalid_graph_and_capacity_are_rejected():
    with pytest.raises(ValueError, match="依赖未知"):
        simulate([SimTask("a", "svc", 1, deps=("ghost",))], {"svc": 1})
    with pytest.raises(ValueError, match="存在环"):
        simulate([
            SimTask("a", "svc", 1, deps=("b",)),
            SimTask("b", "svc", 1, deps=("a",)),
        ], {"svc": 1})
    with pytest.raises(KeyError, match="缺少服务容量"):
        simulate([SimTask("a", "svc", 1)], {})
