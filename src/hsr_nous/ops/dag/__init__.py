"""通用 DAG 执行器（零项目依赖——节点走注册注入，生产 DAG 在 ops/ 兄弟模块定义）."""

from hsr_nous.ops.dag.executor import DagError, Node, Runner, ServiceRegistry

__all__ = ["DagError", "Node", "Runner", "ServiceRegistry"]
