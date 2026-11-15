"""ServiceDispatcher 的虚拟时间离散事件仿真（单服务单槽、非抢占）.

与真实运行时共用 :meth:`SchedulingPolicy.order_key`；任务只在 arrival 到达且全部
依赖完成后才进入 ready queue。每次时间推进都先完成在飞任务、再解锁就绪任务、
最后填满所有可用槽，因此工作守恒是可机械校验的不变量，而不是注释承诺。
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from hsr_nous.ops.dag.dispatcher import SchedulingPolicy


@dataclass(frozen=True)
class SimTask:
    task_id: str
    service: str
    duration: float
    deps: Tuple[str, ...] = ()
    arrival: float = 0.0
    priority: float = 0.0

    def __post_init__(self) -> None:
        if not self.task_id or not self.service:
            raise ValueError("task_id/service 不能为空")
        if not math.isfinite(self.duration) or self.duration <= 0:
            raise ValueError(f"任务 {self.task_id!r} duration 须为有限正数")
        if not math.isfinite(self.arrival) or self.arrival < 0:
            raise ValueError(f"任务 {self.task_id!r} arrival 须为有限非负数")
        if not math.isfinite(self.priority):
            raise ValueError(f"任务 {self.task_id!r} priority 须为有限数")


@dataclass(frozen=True)
class SimTrace:
    task_id: str
    service: str
    arrival: float
    ready_at: float
    start: float
    end: float
    wait: float


@dataclass(frozen=True)
class ServiceMetrics:
    capacity: int
    busy: float
    idle: float
    utilization: float


@dataclass(frozen=True)
class SimulationResult:
    traces: Tuple[SimTrace, ...]
    services: Dict[str, ServiceMetrics]
    makespan: float

    @property
    def throughput(self) -> float:
        return len(self.traces) / self.makespan if self.makespan > 0 else 0.0

    @property
    def waits(self) -> Tuple[float, ...]:
        return tuple(trace.wait for trace in self.traces)

    @property
    def start_order(self) -> Tuple[str, ...]:
        return tuple(trace.task_id for trace in self.traces)


def _graph(tasks: Iterable[SimTask]) -> Tuple[Dict[str, SimTask], Dict[str, List[str]]]:
    by_id: Dict[str, SimTask] = {}
    for task in tasks:
        if task.task_id in by_id:
            raise ValueError(f"任务 id 重复：{task.task_id!r}")
        by_id[task.task_id] = task
    dependents: Dict[str, List[str]] = {task_id: [] for task_id in by_id}
    for task in by_id.values():
        for dep in task.deps:
            if dep not in by_id:
                raise ValueError(f"任务 {task.task_id!r} 依赖未知任务 {dep!r}")
            dependents[dep].append(task.task_id)
    color: Dict[str, int] = {}

    def visit(task_id: str) -> None:
        if color.get(task_id) == 2:
            return
        if color.get(task_id) == 1:
            raise ValueError(f"任务图存在环（经过 {task_id!r}）")
        color[task_id] = 1
        for dep in by_id[task_id].deps:
            visit(dep)
        color[task_id] = 2

    for task_id in sorted(by_id):
        visit(task_id)
    return by_id, dependents


def _remaining_ranks(tasks: Iterable[SimTask],
                     weight: Callable[[SimTask], float]) -> Dict[str, float]:
    by_id, dependents = _graph(tasks)
    memo: Dict[str, float] = {}

    def rank(task_id: str) -> float:
        if task_id not in memo:
            task = by_id[task_id]
            memo[task_id] = weight(task) + max(
                (rank(child) for child in dependents[task_id]), default=0.0)
        return memo[task_id]

    for task_id in sorted(by_id):
        rank(task_id)
    return memo


def hlf_priorities(tasks: Iterable[SimTask]) -> Dict[str, float]:
    """Highest Level First：到终端的最长剩余链节点数（含当前节点）."""
    return _remaining_ranks(tasks, lambda _task: 1.0)


def upward_ranks(tasks: Iterable[SimTask]) -> Dict[str, float]:
    """HEFT upward-rank 的零通信成本形式：剩余最长预计执行成本."""
    return _remaining_ranks(tasks, lambda task: task.duration)


def simulate(tasks: Iterable[SimTask], capacities: Mapping[str, int], *,
             policy: Optional[SchedulingPolicy] = None,
             priorities: Optional[Mapping[str, float]] = None) -> SimulationResult:
    """运行确定性仿真；priorities 可覆盖各 SimTask 自带的基础优先级."""
    by_id, _dependents = _graph(tasks)
    policy = policy or SchedulingPolicy()
    priorities = priorities or {}
    unknown_priorities = set(priorities) - set(by_id)
    if unknown_priorities:
        raise ValueError(f"priorities 含未知任务：{sorted(unknown_priorities)}")
    for name, capacity in capacities.items():
        if capacity < 1:
            raise ValueError(f"服务 {name!r} 容量须 ≥1（得到 {capacity}）")
    missing = {task.service for task in by_id.values()} - set(capacities)
    if missing:
        raise KeyError(f"缺少服务容量定义：{sorted(missing)}")

    queues: Dict[str, List[Tuple[Tuple[float, int], str, float]]] = {
        name: [] for name in capacities}
    pending = set(by_id)
    queued: set[str] = set()
    finished: Dict[str, float] = {}
    running: List[Tuple[float, str]] = []
    active = {name: 0 for name in capacities}
    busy = {name: 0.0 for name in capacities}
    traces: List[SimTrace] = []
    now = 0.0
    sequence = 0

    while pending or running:
        while running and running[0][0] <= now:
            end, task_id = heapq.heappop(running)
            task = by_id[task_id]
            active[task.service] -= 1
            finished[task_id] = end

        # 同一时刻可重复解锁；只入队一次，ready_at 取到达与依赖完成的较晚者。
        for task_id in sorted(pending - queued):
            task = by_id[task_id]
            if task.arrival > now or any(dep not in finished for dep in task.deps):
                continue
            ready_at = max(
                task.arrival,
                max((finished[dep] for dep in task.deps), default=task.arrival),
            )
            priority = priorities.get(task_id, task.priority)
            key = policy.order_key(
                priority=priority, enqueued_at=ready_at, sequence=sequence)
            sequence += 1
            heapq.heappush(queues[task.service], (key, task_id, ready_at))
            queued.add(task_id)

        for service in sorted(capacities):
            queue = queues[service]
            while queue and active[service] < capacities[service]:
                _key, task_id, ready_at = heapq.heappop(queue)
                task = by_id[task_id]
                end = now + task.duration
                heapq.heappush(running, (end, task_id))
                active[service] += 1
                busy[service] += task.duration
                pending.remove(task_id)
                traces.append(SimTrace(
                    task_id=task_id, service=service, arrival=task.arrival,
                    ready_at=ready_at, start=now, end=end,
                    wait=max(0.0, now - ready_at)))
            if queue and active[service] < capacities[service]:
                raise AssertionError(f"工作守恒破坏：{service} 有空槽且 ready queue 非空")

        if not pending:
            break
        next_completion = running[0][0] if running else math.inf
        next_arrival = min(
            (by_id[task_id].arrival for task_id in pending
             if task_id not in queued and by_id[task_id].arrival > now),
            default=math.inf,
        )
        next_now = min(next_completion, next_arrival)
        if not math.isfinite(next_now) or next_now <= now:
            raise AssertionError("仿真无法推进：检查依赖环、容量或事件推进逻辑")
        now = next_now

    # 末尾在飞任务仍需全部结束，才能计算 makespan 与 busy/idle。
    while running:
        now = running[0][0]
        while running and running[0][0] <= now:
            end, task_id = heapq.heappop(running)
            active[by_id[task_id].service] -= 1
            finished[task_id] = end

    makespan = max(finished.values(), default=0.0)
    services = {
        name: ServiceMetrics(
            capacity=capacity,
            busy=busy[name],
            idle=capacity * makespan - busy[name],
            utilization=(busy[name] / (capacity * makespan)
                         if capacity * makespan > 0 else 0.0),
        )
        for name, capacity in capacities.items()
    }
    return SimulationResult(traces=tuple(traces), services=services, makespan=makespan)


__all__ = [
    "ServiceMetrics", "SimTask", "SimTrace", "SimulationResult",
    "hlf_priorities", "simulate", "upward_ranks",
]
