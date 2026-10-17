"""Runner 的集中队列执行后端：只搬运 node.fn，不侵入节点业务逻辑."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from hsr_nous.ops.dag.dispatcher import (
    DispatchEvent,
    SchedulingPolicy,
    ServiceDispatcher,
    ServiceRequest,
    ServiceSpec,
)


@dataclass(frozen=True)
class _NodeCall:
    node: Any
    inputs: Dict[str, Any]


def _execute_node(call: _NodeCall) -> Any:
    return call.node.fn(call.inputs)


class QueueBackend:
    """把节点执行统一交给 ServiceDispatcher；调用方持有并负责关闭.

    原 ``service=""`` 节点映射到 ``local``。Backend 只替换执行与排队，不解释依赖、
    缓存或动态扇出，也不要求把每个节点改写为独立服务 handler。
    默认策略为 FIFO；可用 ``policies`` 按服务注册结构优先级或 aging。
    """

    def __init__(self, capacities: Mapping[str, int], *, local_capacity: int = 1,
                 policies: Optional[Mapping[str, SchedulingPolicy]] = None) -> None:
        if local_capacity < 1:
            raise ValueError(f"local_capacity 须 ≥1（得到 {local_capacity}）")
        caps = dict(capacities)
        caps.setdefault("local", local_capacity)
        default_policy = SchedulingPolicy.fifo()
        selected = policies or {}
        self._dispatcher = ServiceDispatcher([
            ServiceSpec(name, capacity, _execute_node,
                        policy=selected.get(name, default_policy))
            for name, capacity in caps.items()
        ])

    def submit(self, node: Any, inputs: Dict[str, Any]) -> Future:
        """异步提交一个已就绪 DAG 节点."""
        return self._dispatcher.submit(ServiceRequest(
            service=node.service or "local",
            payload=_NodeCall(node=node, inputs=dict(inputs)),
            priority=getattr(node, "priority", 0.0),
            request_id=node.node_id,
        ))

    def shutdown(self) -> None:
        self._dispatcher.shutdown()

    def events(self) -> Tuple[DispatchEvent, ...]:
        return self._dispatcher.events()

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        return self._dispatcher.snapshot()

    def __enter__(self) -> "QueueBackend":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.shutdown()


__all__ = ["QueueBackend"]
