"""Runner + QueueBackend 生产后端语义：缓存、扇出、容量、fail-fast 与共享所有权."""

from __future__ import annotations

import threading
import time

import pytest

from hsr_nous.ops.dag import DagError, Node, QueueBackend, Runner, SchedulingPolicy


def test_linear_chain_and_dynamic_fanout(tmp_path):
    def shape(value):
        return (Node("child", lambda inputs: inputs["gate"] + "C", deps=("gate",)),)

    with QueueBackend({}, local_capacity=2) as backend:
        runner = Runner(tmp_path, backend=backend)
        runner.add(Node("gate", lambda _inputs: "G", shape=shape))
        assert runner.run() == {"gate": "G", "child": "GC"}


def test_replay_cache_hit_and_dirty_subgraph(tmp_path):
    calls = {"a": 0, "b": 0}

    def a(_inputs):
        calls["a"] += 1
        return "A"

    def b(inputs):
        calls["b"] += 1
        return inputs["a"] + "B"

    def build(backend, fn=a):
        runner = Runner(tmp_path, backend=backend)
        runner.add(Node("a", fn), Node("b", b, deps=("a",)))
        return runner

    with QueueBackend({}, local_capacity=2) as backend:
        assert build(backend).run() == {"a": "A", "b": "AB"}
        assert build(backend).run() == {"a": "A", "b": "AB"}
        assert calls == {"a": 1, "b": 1}, "缓存命中零重跑"

        def a2(_inputs):
            calls["a"] += 1
            return "A2"

        assert build(backend, fn=a2).run() == {"a": "A2", "b": "A2B"}
        assert calls == {"a": 2, "b": 2}, "输入变则自身与下游重跑"


def test_service_capacity_and_independent_services(tmp_path):
    active = {"cur": 0, "max": 0}
    lock = threading.Lock()
    ended = {}

    def slow(inputs):
        with lock:
            active["cur"] += 1
            active["max"] = max(active["max"], active["cur"])
        time.sleep(0.03)
        with lock:
            active["cur"] -= 1
            ended["a"] = time.monotonic()
        return "A"

    def quick(inputs):
        ended["b"] = time.monotonic()
        return "B"

    with QueueBackend({"a": 1, "b": 1}) as backend:
        runner = Runner(tmp_path, backend=backend)
        runner.add(Node("a", slow, service="a"), Node("b", quick, service="b"))
        assert runner.run() == {"a": "A", "b": "B"}
    assert active["max"] == 1
    assert ended["b"] < ended["a"], "A 服务在跑不占 B 服务容量"


def test_fail_fast_drains_submitted_and_backend_reusable(tmp_path):
    finished = []

    def bad(_inputs):
        time.sleep(0.005)
        raise ValueError("炸了")

    def slow(_inputs):
        time.sleep(0.02)
        finished.append("slow")
        return "slow"

    with QueueBackend({}, local_capacity=2) as backend:
        runner = Runner(tmp_path / "bad", backend=backend)
        runner.add(Node("bad", bad), Node("slow", slow))
        with pytest.raises(DagError, match="'bad'"):
            runner.run()
        assert finished == ["slow"], "失败返回前已提交节点已收尾"

        runner2 = Runner(tmp_path / "good", backend=backend)
        runner2.add(Node("good", lambda _inputs: 42))
        assert runner2.run() == {"good": 42}, "Runner 不关闭共享 Backend，后续可复用"


def test_many_nodes_complete_through_callback_driver(tmp_path):
    with QueueBackend({"svc": 8}) as backend:
        runner = Runner(tmp_path, backend=backend)
        runner.add(*[Node(f"n{i:03d}", lambda _inputs, i=i: i, service="svc")
                     for i in range(500)])
        out = runner.run()
    assert len(out) == 500 and out["n499"] == 499


def test_default_annotator_llm_cap_is_only_technical_bound():
    from hsr_nous.ops.annotator.pipeline import _default_backend

    with _default_backend(3) as backend:
        snap = backend.snapshot()
    assert snap["llm_api"]["capacity"] == 3
    assert snap["local"]["capacity"] == 3
    assert snap["game_data"]["capacity"] == 4


def _policy_execution_order(policies):
    blocker_started = threading.Event()
    release = threading.Event()
    order = []

    def handler(inputs):
        label = inputs["label"]
        if label == "blocker":
            blocker_started.set()
            release.wait(2)
        else:
            order.append(label)
        return label

    with QueueBackend({"svc": 1}, policies=policies) as backend:
        try:
            backend.submit(Node("0_blocker", handler, service="svc"), {"label": "blocker"})
            assert blocker_started.wait(1)
            backend.submit(Node("a_low", handler, service="svc", priority=0), {"label": "low"})
            time.sleep(0.02)  # 给 aging 测试制造可测的排队间隔
            backend.submit(Node("z_high", handler, service="svc", priority=10), {"label": "high"})
            release.set()
        finally:
            release.set()
    return order


def test_default_policy_is_fifo_even_with_node_priority():
    assert _policy_execution_order(None) == ["low", "high"]


def test_structural_priority_policy_is_opt_in():
    assert _policy_execution_order({"svc": SchedulingPolicy()}) == ["high", "low"]


def test_aging_policy_is_opt_in():
    assert _policy_execution_order({"svc": SchedulingPolicy(aging_rate=1000)}) == ["low", "high"]
