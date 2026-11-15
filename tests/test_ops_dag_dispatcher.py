"""ServiceDispatcher 真实线程运行时语义钉：容量、优先级、aging、终态与观测."""

from __future__ import annotations

import threading

import pytest

from hsr_nous.ops.dag import (
    SchedulingPolicy,
    ServiceDispatcher,
    ServiceRequest,
    ServiceSpec,
)


def test_submit_future_events_and_snapshot():
    d = ServiceDispatcher([ServiceSpec("echo", 1, lambda payload: payload * 2)])
    future = d.submit(ServiceRequest("echo", 21, request_id="r1"))
    assert future.result(timeout=2) == 42
    with pytest.raises(RuntimeError, match="不能再注册"):
        d.register(ServiceSpec("late", 1, lambda payload: payload))
    d.shutdown()

    assert d.join(0), "关闭后当前请求均已到终态"
    events = d.events()
    assert [e.kind for e in events] == ["submitted", "started", "succeeded"]
    assert events[1].queue_wait is not None and events[1].queue_wait >= 0
    assert d.snapshot()["echo"] == {
        "capacity": 1, "queued": 0, "inflight": 0, "submitted": 1,
        "succeeded": 1, "failed": 0, "cancelled": 0,
    }
    with pytest.raises(RuntimeError, match="拒绝新请求"):
        d.submit(ServiceRequest("echo", 1))


def test_capacity_is_not_bounded_by_default_executor():
    """8 个容量必须真能提供 8 个工人，不受 CPU 核数派生的默认池上限影响."""
    capacity = 8
    active = {"cur": 0, "max": 0}
    lock = threading.Lock()
    all_started = threading.Event()
    release = threading.Event()

    def handler(payload):
        with lock:
            active["cur"] += 1
            active["max"] = max(active["max"], active["cur"])
            if active["cur"] == capacity:
                all_started.set()
        release.wait(5)
        with lock:
            active["cur"] -= 1
        return payload

    d = ServiceDispatcher([ServiceSpec("svc", capacity, handler)])
    futures = []
    try:
        futures = [d.submit(ServiceRequest("svc", i)) for i in range(capacity)]
        assert all_started.wait(3), "有空槽且有 ready 请求，必须全部派发（工作守恒）"
        assert active["max"] == capacity
        assert d.snapshot()["svc"]["inflight"] == capacity
    finally:
        release.set()
        d.shutdown()
    assert [f.result(timeout=0) for f in futures] == list(range(capacity))
    assert active["max"] == capacity


def test_services_have_independent_capacity():
    a_started = threading.Event()
    release_a = threading.Event()

    def slow_a(payload):
        a_started.set()
        release_a.wait(5)
        return payload

    d = ServiceDispatcher([
        ServiceSpec("a", 1, slow_a),
        ServiceSpec("b", 1, lambda payload: f"B:{payload}"),
    ])
    try:
        fa = d.submit(ServiceRequest("a", 1))
        assert a_started.wait(2)
        fb = d.submit(ServiceRequest("b", 2))
        assert fb.result(timeout=2) == "B:2", "A 服务堵死不占 B 服务容量"
        release_a.set()
        assert fa.result(timeout=2) == 1
    finally:
        release_a.set()
        d.shutdown()


def test_structural_priority_and_stable_fifo():
    for priorities, expected in [
        ((0.0, 10.0), ["high", "low"]),
        ((0.0, 0.0), ["low", "high"]),  # 同优先级按提交顺序
    ]:
        blocker_started = threading.Event()
        release = threading.Event()
        order = []

        def handler(payload):
            if payload == "blocker":
                blocker_started.set()
                release.wait(5)
            else:
                order.append(payload)
            return payload

        d = ServiceDispatcher([ServiceSpec("svc", 1, handler)])
        try:
            d.submit(ServiceRequest("svc", "blocker"))
            assert blocker_started.wait(2)
            d.submit(ServiceRequest("svc", "low", priority=priorities[0]))
            d.submit(ServiceRequest("svc", "high", priority=priorities[1]))
            release.set()
            assert d.join(3)
        finally:
            release.set()
            d.shutdown()
        assert order == expected


@pytest.mark.parametrize("aging_rate,expected", [
    (0.0, ["new_high", "old_low"]),
    (1.0, ["old_low", "new_high"]),
])
def test_aging_lets_old_request_overtake_newer_priority(aging_rate, expected):
    now = [0.0]
    blocker_started = threading.Event()
    release = threading.Event()
    order = []

    def handler(payload):
        if payload == "blocker":
            blocker_started.set()
            release.wait(5)
        else:
            order.append(payload)
        return payload

    spec = ServiceSpec(
        "svc", 1, handler, policy=SchedulingPolicy(aging_rate=aging_rate))
    d = ServiceDispatcher([spec], clock=lambda: now[0])
    try:
        d.submit(ServiceRequest("svc", "blocker"))
        assert blocker_started.wait(2)
        d.submit(ServiceRequest("svc", "old_low", priority=0.0))
        now[0] = 10.0
        d.submit(ServiceRequest("svc", "new_high", priority=5.0))
        release.set()
        assert d.join(3)
    finally:
        release.set()
        d.shutdown()
    assert order == expected


def test_handler_error_releases_capacity_and_preserves_future():
    def handler(payload):
        if payload == "bad":
            raise ValueError("炸了")
        return payload

    with ServiceDispatcher([ServiceSpec("svc", 1, handler)]) as d:
        bad = d.submit(ServiceRequest("svc", "bad"))
        good = d.submit(ServiceRequest("svc", "good"))
        with pytest.raises(ValueError, match="炸了"):
            bad.result(timeout=2)
        assert good.result(timeout=2) == "good"
        assert d.join(1)

    snap = d.snapshot()["svc"]
    assert snap["failed"] == snap["succeeded"] == 1
    assert snap["inflight"] == snap["queued"] == 0
    kinds = [e.kind for e in d.events()]
    assert kinds.count("failed") == kinds.count("succeeded") == 1
    assert kinds[-1] == "succeeded"


def test_queued_cancellation_is_terminal_and_never_executes():
    blocker_started = threading.Event()
    release = threading.Event()
    calls = []

    def handler(payload):
        calls.append(payload)
        if payload == "blocker":
            blocker_started.set()
            release.wait(5)
        return payload

    d = ServiceDispatcher([ServiceSpec("svc", 1, handler)])
    try:
        blocker = d.submit(ServiceRequest("svc", "blocker"))
        assert blocker_started.wait(2)
        cancelled = d.submit(ServiceRequest("svc", "cancel-me"))
        assert cancelled.cancel()
        release.set()
        assert blocker.result(timeout=2) == "blocker"
        assert d.join(2)
    finally:
        release.set()
        d.shutdown()
    assert calls == ["blocker"]
    assert cancelled.cancelled()
    assert d.snapshot()["svc"]["cancelled"] == 1
