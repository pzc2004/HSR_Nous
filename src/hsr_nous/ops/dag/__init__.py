"""通用 DAG 执行器（零项目依赖——节点走注册注入，生产 DAG 在 ops/ 兄弟模块定义）."""

from hsr_nous.ops.dag.dispatcher import (
    DispatchEvent,
    SchedulingPolicy,
    ServiceDispatcher,
    ServiceRequest,
    ServiceSpec,
)
from hsr_nous.ops.dag.executor import DagError, Node, Runner
from hsr_nous.ops.dag.queue_backend import QueueBackend
from hsr_nous.ops.dag.simulation import (
    ServiceMetrics,
    SimTask,
    SimTrace,
    SimulationResult,
    hlf_priorities,
    simulate,
    upward_ranks,
)

__all__ = [
    "DagError", "DispatchEvent", "Node", "QueueBackend", "Runner", "SchedulingPolicy",
    "ServiceDispatcher", "ServiceMetrics", "ServiceRequest", "ServiceSpec",
    "SimTask", "SimTrace", "SimulationResult", "hlf_priorities", "simulate", "upward_ranks",
]
