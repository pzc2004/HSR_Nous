"""mock 执行的 trace 记录与负载校验工具（供缓存重放复用）."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Mapping, Tuple

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


__all__ = ["MockRunResult", "MockTrace"]
