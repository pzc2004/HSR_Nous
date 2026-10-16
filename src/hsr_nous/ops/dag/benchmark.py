"""ServiceDispatcher 的静态 DAG mock 执行与 trace 记录.

本模块只跑静态 DAG（所有 arrival=0）：实验性 ready-list 驱动把节点交给
``ServiceDispatcher``。mock handler 只按任务 duration 等待并返回 id，不访问 LLM、
网络或文件数据。墙钟结果受机器负载影响；策略结论以 ``simulation.py`` 为准。
"""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Mapping, Optional, Tuple

from hsr_nous.ops.dag.dispatcher import (
    SchedulingPolicy,
    ServiceDispatcher,
    ServiceRequest,
    ServiceSpec,
)
from hsr_nous.ops.dag.simulation import SimTask, _graph


@dataclass(frozen=True)
class MockTrace:
    task_id: str
    service: str
    ready_at: float
    start: float
    end: float
    wait: float


@dataclass(frozen=True)
class MockRunResult:
    """一次 mock 执行的实测 trace；时间均以本次 run 开始为零点."""

    traces: Tuple[MockTrace, ...]
    makespan: float

    @property
    def start_order(self) -> Tuple[str, ...]:
        return tuple(trace.task_id for trace in self.traces)

    @property
    def waits(self) -> Tuple[float, ...]:
        return tuple(trace.wait for trace in self.traces)


class _Recorder:
    def __init__(self, sleep: Callable[[float], None]) -> None:
        self._sleep = sleep
        self._origin = 0.0
        self._lock = threading.Lock()
        self.starts: Dict[str, float] = {}
        self.ends: Dict[str, float] = {}

    def begin(self) -> None:
        self._origin = time.monotonic()

    def _now(self) -> float:
        return time.monotonic() - self._origin

    def execute(self, task: SimTask) -> str:
        start = self._now()
        with self._lock:
            self.starts[task.task_id] = start
        self._sleep(task.duration)
        end = self._now()
        with self._lock:
            self.ends[task.task_id] = end
        return task.task_id

    def result(self, tasks: Mapping[str, SimTask]) -> MockRunResult:
        if not tasks:
            return MockRunResult((), 0.0)
        if set(self.starts) != set(tasks) or set(self.ends) != set(tasks):
            raise AssertionError("mock 执行 trace 不完整")
        traces = []
        for task_id, task in tasks.items():
            start, end = self.starts[task_id], self.ends[task_id]
            ready_at = max((self.ends[dep] for dep in task.deps), default=0.0)
            if start + 1e-9 < ready_at:
                raise AssertionError(f"任务 {task_id!r} 在依赖完成前启动")
            traces.append(MockTrace(
                task_id=task_id, service=task.service, ready_at=ready_at,
                start=start, end=end, wait=max(0.0, start - ready_at)))
        traces.sort(key=lambda trace: (trace.start, trace.task_id))
        return MockRunResult(tuple(traces), max(self.ends.values()))


def _validated(tasks: Iterable[SimTask], capacities: Mapping[str, int]) -> Dict[str, SimTask]:
    by_id, _dependents = _graph(tasks)
    if any(task.arrival != 0 for task in by_id.values()):
        raise ValueError("真实线程 mock 对拍只支持 arrival=0；动态到达请用 simulation")
    for name, capacity in capacities.items():
        if capacity < 1:
            raise ValueError(f"服务 {name!r} 容量须 ≥1（得到 {capacity}）")
    missing = {task.service for task in by_id.values()} - set(capacities)
    if missing:
        raise KeyError(f"缺少服务容量定义：{sorted(missing)}")
    return by_id


def run_dispatcher_mock(tasks: Iterable[SimTask], capacities: Mapping[str, int], *,
                        policies: Optional[Mapping[str, SchedulingPolicy]] = None,
                        priorities: Optional[Mapping[str, float]] = None,
                        sleep: Callable[[float], None] = time.sleep) -> MockRunResult:
    """实验 ready-list 驱动 + ServiceDispatcher."""
    by_id = _validated(tasks, capacities)
    if not by_id:
        return MockRunResult((), 0.0)
    policies = policies or {}
    priorities = priorities or {}
    unknown_policies = set(policies) - set(capacities)
    unknown_priorities = set(priorities) - set(by_id)
    if unknown_policies:
        raise ValueError(f"policies 含未知服务：{sorted(unknown_policies)}")
    if unknown_priorities:
        raise ValueError(f"priorities 含未知任务：{sorted(unknown_priorities)}")

    recorder = _Recorder(sleep)
    specs = [
        ServiceSpec(name, capacity, recorder.execute,
                    policy=policies.get(name, SchedulingPolicy()))
        for name, capacity in capacities.items()
    ]
    dispatcher = ServiceDispatcher(specs)
    pending = set(by_id)
    running = 0
    # 完成回调队列：避免反复 wait(FIRST_COMPLETED) 在剩余 Future 集上重复注册回调；
    # 一万节点实测该测量器开销曾淹没被测调度器（数倍至一个数量级）。
    completed: "queue.Queue[Tuple[str, Future]]" = queue.Queue()
    outputs: Dict[str, str] = {}
    try:
        recorder.begin()
        while pending or running:
            for task_id in sorted(pending):
                task = by_id[task_id]
                if not all(dep in outputs for dep in task.deps):
                    continue
                future = dispatcher.submit(ServiceRequest(
                    service=task.service, payload=task,
                    priority=priorities.get(task_id, task.priority), request_id=task_id))
                running += 1
                future.add_done_callback(
                    lambda fut, task_id=task_id: completed.put((task_id, fut)))
                pending.remove(task_id)
            if not running:
                if pending:
                    raise AssertionError(f"存在不可满足依赖：{sorted(pending)}")
                break
            task_id, future = completed.get()
            while True:
                running -= 1
                outputs[task_id] = future.result()
                try:
                    task_id, future = completed.get_nowait()
                except queue.Empty:
                    break
    finally:
        dispatcher.shutdown()
    return recorder.result(by_id)


__all__ = ["MockRunResult", "MockTrace", "run_dispatcher_mock"]
