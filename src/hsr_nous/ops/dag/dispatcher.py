"""集中式单槽服务调度器：注册 handler、就绪排队、结构优先级与 aging.

DAG/调用方只提交已经就绪的请求；本模块不解释依赖图。每个请求属于一个服务、
只占该服务一个并发槽且不可抢占。服务容量用足时，工作线程数严格等于各服务
容量之和，不依赖 ``asyncio.to_thread`` 或默认线程池的硬件派生上限。

优先级只在同一服务的 ready queue 内排序。``aging_rate`` 是优先级/秒的加速率；
同一服务内所有请求同速 aging，因此 ``base - rate * enqueued_at`` 已足够确定任意
时刻的相对顺序（共同的 ``rate * now`` 项不影响比较），无需每次派发重排整队。
"""

from __future__ import annotations

import heapq
import math
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class SchedulingPolicy:
    """服务级排队策略；结构优先级由每个请求携带."""

    use_structural_priority: bool = True
    aging_rate: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.aging_rate) or self.aging_rate < 0:
            raise ValueError(f"aging_rate 须为有限非负数（得到 {self.aging_rate}）")

    @classmethod
    def fifo(cls) -> "SchedulingPolicy":
        """纯 FIFO：忽略结构优先级且不做 aging."""
        return cls(use_structural_priority=False)

    def order_key(self, *, priority: float, enqueued_at: float,
                  sequence: int) -> Tuple[float, int]:
        """返回最小堆键；数值越小越先派发，入队序号保证稳定 tie-break."""
        base = priority if self.use_structural_priority else 0.0
        aged_rank = base - self.aging_rate * enqueued_at
        return (-aged_rank, sequence)


@dataclass(frozen=True)
class ServiceRequest:
    """一次单槽服务调用；priority 越大，基础优先级越高."""

    service: str
    payload: Any
    priority: float = 0.0
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.service:
            raise ValueError("service 不能为空")
        if not self.request_id:
            raise ValueError("request_id 不能为空")
        if not math.isfinite(self.priority):
            raise ValueError(f"priority 须为有限数（得到 {self.priority}）")


@dataclass(frozen=True)
class ServiceSpec:
    """服务注册项：执行逻辑、容量与排队策略同属一个注册点."""

    name: str
    capacity: int
    handler: Callable[[Any], Any]
    policy: SchedulingPolicy = field(default_factory=SchedulingPolicy)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("服务名不能为空")
        if self.capacity < 1:
            raise ValueError(f"服务 {self.name!r} 容量须 ≥1（得到 {self.capacity}）")
        if not callable(self.handler):
            raise TypeError(f"服务 {self.name!r} handler 不可调用")


@dataclass(frozen=True)
class DispatchEvent:
    """调度观测事件；时间来自 Dispatcher 注入的单调时钟."""

    kind: str
    service: str
    request_id: str
    at: float
    queue_wait: Optional[float] = None
    error: str = ""


@dataclass
class _RequestState:
    request: ServiceRequest
    future: Future
    enqueued_at: float


@dataclass
class _ServiceState:
    spec: ServiceSpec
    queue: List[Tuple[Tuple[float, int], _RequestState]] = field(default_factory=list)
    inflight: int = 0
    submitted: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0


class ServiceDispatcher:
    """多服务集中调度器；注册完成后提交请求，关闭时排空.

    - ``submit`` 只入队并立即返回 Future，真正的容量等待不占用调用方线程；
    - 每服务独立 ready queue/inflight，完成一个立即补一个；
    - 首次 submit 启动调度线程和容量精确匹配的工作池，此后不再接受新服务注册；
    - ``join`` 等当前已提交请求全部到终态，``shutdown`` 拒绝新请求并排干后关闭。
    """

    def __init__(self, services: Iterable[ServiceSpec] = (), *,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._condition = threading.Condition()
        self._services: Dict[str, _ServiceState] = {}
        self._events: List[DispatchEvent] = []
        self._sequence = 0
        self._outstanding = 0
        self._started = False
        self._shutdown_requested = False
        self._executor: Optional[ThreadPoolExecutor] = None
        self._scheduler: Optional[threading.Thread] = None
        for spec in services:
            self.register(spec)

    def register(self, spec: ServiceSpec) -> None:
        """注册服务；为避免运行中改变总工作池容量，首次 submit 后禁止再注册."""
        with self._condition:
            if self._started or self._shutdown_requested:
                raise RuntimeError("Dispatcher 已启动或关闭，不能再注册服务")
            if spec.name in self._services:
                raise ValueError(f"服务 {spec.name!r} 重复注册")
            self._services[spec.name] = _ServiceState(spec=spec)

    def submit(self, request: ServiceRequest) -> Future:
        """异步提交就绪请求；未知服务或关闭后提交立即报错."""
        with self._condition:
            if self._shutdown_requested:
                raise RuntimeError("Dispatcher 已关闭，拒绝新请求")
            state = self._services.get(request.service)
            if state is None:
                raise KeyError(f"未注册服务 {request.service!r}")
            if not self._started:
                self._start_locked()
            enqueued_at = self._clock()
            future: Future = Future()
            req_state = _RequestState(request=request, future=future, enqueued_at=enqueued_at)
            key = state.spec.policy.order_key(
                priority=request.priority, enqueued_at=enqueued_at, sequence=self._sequence)
            self._sequence += 1
            heapq.heappush(state.queue, (key, req_state))
            state.submitted += 1
            self._outstanding += 1
            self._events.append(DispatchEvent(
                "submitted", request.service, request.request_id, enqueued_at))
            self._condition.notify_all()
            return future

    def join(self, timeout: Optional[float] = None) -> bool:
        """等待当前请求全部完成/失败/取消；timeout 到期返回 False."""
        with self._condition:
            return self._condition.wait_for(lambda: self._outstanding == 0, timeout)

    def shutdown(self) -> None:
        """拒绝新请求，排空已提交请求并关闭线程；重复调用安全."""
        with self._condition:
            self._shutdown_requested = True
            self._condition.notify_all()
        self.join()
        with self._condition:
            scheduler = self._scheduler
            executor = self._executor
            self._condition.notify_all()
        if scheduler is not None and scheduler is not threading.current_thread():
            scheduler.join()
        if executor is not None:
            executor.shutdown(wait=True)

    def events(self) -> Tuple[DispatchEvent, ...]:
        """观测事件快照（append-only 原序）."""
        with self._condition:
            return tuple(self._events)

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        """每服务容量、队列与终态计数快照."""
        with self._condition:
            return {
                name: {
                    "capacity": state.spec.capacity,
                    "queued": len(state.queue),
                    "inflight": state.inflight,
                    "submitted": state.submitted,
                    "succeeded": state.succeeded,
                    "failed": state.failed,
                    "cancelled": state.cancelled,
                }
                for name, state in self._services.items()
            }

    def _start_locked(self) -> None:
        total_capacity = sum(state.spec.capacity for state in self._services.values())
        self._executor = ThreadPoolExecutor(
            max_workers=total_capacity, thread_name_prefix="hsr-nous-service")
        self._scheduler = threading.Thread(
            target=self._schedule_loop, name="hsr-nous-dispatch", daemon=True)
        self._started = True
        self._scheduler.start()

    def _schedule_loop(self) -> None:
        with self._condition:
            while True:
                if self._dispatch_locked():
                    continue
                if self._shutdown_requested and self._outstanding == 0:
                    return
                self._condition.wait()

    def _dispatch_locked(self) -> bool:
        """填满所有服务的可用槽；调用方必须持有 condition 锁."""
        assert self._executor is not None
        progressed = False
        for name in sorted(self._services):
            state = self._services[name]
            while state.queue and state.inflight < state.spec.capacity:
                _key, req_state = heapq.heappop(state.queue)
                if not req_state.future.set_running_or_notify_cancel():
                    state.cancelled += 1
                    self._outstanding -= 1
                    self._events.append(DispatchEvent(
                        "cancelled", name, req_state.request.request_id, self._clock()))
                    progressed = True
                    continue
                started_at = self._clock()
                state.inflight += 1
                self._events.append(DispatchEvent(
                    "started", name, req_state.request.request_id, started_at,
                    queue_wait=max(0.0, started_at - req_state.enqueued_at)))
                self._executor.submit(self._execute, name, req_state)
                progressed = True
        self._condition.notify_all()
        return progressed

    def _execute(self, service: str, req_state: _RequestState) -> None:
        request = req_state.request
        error: Optional[BaseException] = None
        result: Any = None
        try:
            result = self._services[service].spec.handler(request.payload)
        except BaseException as exc:  # 工作线程异常也必须落 Future 并释放容量
            error = exc
        with self._condition:
            state = self._services[service]
            state.inflight -= 1
            self._outstanding -= 1
            finished_at = self._clock()
            if error is None:
                state.succeeded += 1
                req_state.future.set_result(result)
                self._events.append(DispatchEvent(
                    "succeeded", service, request.request_id, finished_at))
            else:
                state.failed += 1
                req_state.future.set_exception(error)
                self._events.append(DispatchEvent(
                    "failed", service, request.request_id, finished_at,
                    error=f"{type(error).__name__}: {error}"))
            self._condition.notify_all()

    def __enter__(self) -> "ServiceDispatcher":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.shutdown()


__all__ = [
    "DispatchEvent", "SchedulingPolicy", "ServiceDispatcher", "ServiceRequest", "ServiceSpec",
]
