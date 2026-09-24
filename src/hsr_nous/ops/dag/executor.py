"""通用 DAG 执行器（生产运行时核心——零项目依赖，节点走注册注入）.

核心语义（designs/ANNOTATOR_DAG.md 立项）：

- **静态声明 + shape 纯函数扇出**：`shape(value) -> [Node]` 运行时追加新节点——闭环与
  条件分支统一为"追加新节点"（运行图 append-only）。DAG 无环性质保住，闭环为真：
  每次尝试都是一等节点，attempt 轨迹 = 运行图结构本身。shape 与 fn 分离——
  fn 干活（可缓存），shape 从值纯推子图（重放缓存命中时照跑，扇出图不丢）
- **重放**：节点输出（值 + inputs_hash × fn 源码指纹双键）落 runs 目录；
  输入哈希不变 → 命中缓存跳过 fn（shape 仍从缓存值重建子图）；变 → 自身与下游标脏重跑
- **服务注册表**：服务（llm_api/web_search/compile…）并发闸统一管控，节点只声明消费
- **fail-fast**：首个节点异常停调度，在跑节点收尾后抛 `DagError`（带失败节点 id 与轨迹）

节点契约：`fn(inputs) -> Any`（JSON 可序列化，大文本以字符串承载）；
`shape(value) -> [Node]` 可选、纯函数（构建 Node 对象，不许干活）。
`cache=False` 标记非幂等节点（永远重跑）。
"""

from __future__ import annotations

import hashlib
import inspect
import json
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, Tuple


class DagError(RuntimeError):
    """执行失败（fail-fast）：携带失败节点 id / 依赖错误与原始异常。"""


@dataclass(frozen=True)
class Node:
    """DAG 节点：node_id 图内唯一；deps 为依赖节点 id；fn(inputs) 返回 JSON 值。

    动态扇出经 `shape(value) -> [Node]`：**纯函数路由**（从值推子图，不干活）——
    与 fn 分离的原因：重放缓存命中时 fn 被跳过，shape 仍会从缓存值重建扇出图
    （闭环/条件分支在重放下同样成立，append-only 语义不丢）。
    service：服务注册表并发闸名（空 = 不限流）；kind：mechanical|llm|gate|router|human
    （审计/报告口径，执行器不解释）；cache=False 标记非幂等节点（永远重跑）。
    salt：节点声明的闭包值指纹（混入 fn 指纹——模块常量/锚文件内容改动经此传导缓存
    失效，源码指纹只覆盖函数体的兜底通道；打标提示词/锚范例族用）。
    """
    node_id: str
    fn: Callable[[Dict[str, Any]], Any]
    deps: Tuple[str, ...] = ()
    service: str = ""
    kind: str = "mechanical"
    cache: bool = True
    shape: Optional[Callable[[Any], Tuple["Node", ...]]] = None
    salt: str = ""


class ServiceRegistry:
    """服务并发闸注册表：未注册服务 = 不限流。"""

    def __init__(self, limits: Optional[Dict[str, int]] = None) -> None:
        self._sems: Dict[str, threading.Semaphore] = {}
        for name, limit in (limits or {}).items():
            if limit < 1:
                raise ValueError(f"服务 {name!r} 并发闸须 ≥1（得到 {limit}）")
            self._sems[name] = threading.Semaphore(limit)

    @contextmanager
    def acquire(self, name: str) -> Iterator[None]:
        sem = self._sems.get(name)
        if sem is None:
            yield
            return
        sem.acquire()
        try:
            yield
        finally:
            sem.release()


class Runner:
    """一张运行图：静态节点经 add() 声明，动态节点经 FanOut 运行时追加。"""

    def __init__(self, runs_dir: "str | Path", services: Optional[ServiceRegistry] = None,
                 max_workers: int = 4) -> None:
        self._runs_dir = Path(runs_dir)
        self._services = services or ServiceRegistry()
        if max_workers < 1:
            raise ValueError(f"max_workers 须 ≥1（得到 {max_workers}）")
        self._max_workers = max_workers
        self._nodes: Dict[str, Node] = {}
        self._outputs: Dict[str, Any] = {}
        # 状态流（DAG 可视化取数：web 实时渲染运行图——declared/running/cached/done/failed）
        self._status: Dict[str, str] = {}
        self._errors: Dict[str, str] = {}
        self._events_path = self._runs_dir / "events.jsonl"

    # -- 状态流（前端实时渲染数据源；runs 目录即状态机的一部分） --

    def _emit(self, event: str, node_id: str, **extra: Any) -> None:
        self._status[node_id] = event
        if event == "failed":
            self._errors[node_id] = str(extra.get("error", ""))
        rec = {"t": round(__import__("time").time(), 3), "event": event, "node": node_id, **extra}
        try:
            self._runs_dir.mkdir(parents=True, exist_ok=True)
            with self._events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass  # 状态流尽力而为——写不动不拖死执行

    def graph_state(self) -> Dict[str, Any]:
        """运行图快照（结构驱动渲染的唯一数据源）：nodes（含 deps/kind/service/status/
        error/value 预览）+ edges（dep → node）。动态扇出节点与静态节点同权在册。
        """
        nodes = []
        for nid, n in self._nodes.items():
            value = self._outputs.get(nid)
            preview = json.dumps(value, ensure_ascii=False, default=str)[:200] \
                if nid in self._outputs else ""
            nodes.append({
                "id": nid, "kind": n.kind, "service": n.service, "deps": list(n.deps),
                "status": self._status.get(nid, "pending"),
                "error": self._errors.get(nid, ""), "value_preview": preview,
                "cache": n.cache,
            })
        edges = [[d, nid] for nid, n in self._nodes.items() for d in n.deps]
        return {"nodes": nodes, "edges": edges}

    # -- 图声明 --

    def add(self, *nodes: Node) -> None:
        """声明节点（乱序可——依赖存在性推迟到 run() 校验；重复 id 立即炸）。."""
        for n in nodes:
            if n.node_id in self._nodes:
                raise DagError(
                    f"节点 id 重复：{n.node_id!r}（扇出新节点须唯一 id——attempt 轨迹靠它区分）")
            self._nodes[n.node_id] = n
            self._emit("declared", n.node_id, kind=n.kind, service=n.service, deps=list(n.deps))

    @property
    def outputs(self) -> Dict[str, Any]:
        return dict(self._outputs)

    # -- 重放 --

    @staticmethod
    def _fn_fingerprint(node: Node) -> str:
        """fn 源码 + salt 双料指纹（闭源/动态构造回落 repr）——节点代码改了缓存必须失效；
        工厂闭包共享源码（make_gate(1)/(2) 同指纹）靠输入哈希区分；
        salt=闭包值变更的兜底通道（打标提示词/锚范例内容族——模块常量改=指纹变=缓存失效）。
        """
        try:
            src = inspect.getsource(node.fn)
        except (OSError, TypeError):
            src = repr(node.fn)
        return hashlib.sha256((src + "\0" + node.salt).encode()).hexdigest()[:12]

    def _inputs_hash(self, node: Node) -> str:
        payload = {d: self._outputs[d] for d in node.deps}
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def _cache_path(self, node: Node) -> Path:
        return self._runs_dir / f"{node.node_id}.json"

    def _cached(self, node: Node, ih: str) -> "tuple[bool, Any]":
        if not node.cache:
            return False, None
        p = self._cache_path(node)
        if not p.exists():
            return False, None
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False, None
        if rec.get("inputs_hash") != ih or rec.get("fn_hash") != self._fn_fingerprint(node):
            return False, None
        return True, rec.get("value")

    def _store(self, node: Node, ih: str, value: Any) -> None:
        if not node.cache:
            return
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path(node).write_text(
            json.dumps({"inputs_hash": ih, "fn_hash": self._fn_fingerprint(node),
                        "value": value}, ensure_ascii=False, indent=2),
            encoding="utf-8")

    # -- 执行 --

    def _invoke(self, node: Node, inputs: Dict[str, Any]) -> Any:
        with self._services.acquire(node.service):
            return node.fn(inputs)

    def run(self) -> Dict[str, Any]:
        # 依赖存在性总校验（声明乱序可；扇出图在运行中动态长，故只能此时查）
        for n in list(self._nodes.values()):
            for d in n.deps:
                if d not in self._nodes:
                    raise DagError(f"节点 {n.node_id!r} 依赖未注册节点 {d!r}")
        pending = set(self._nodes)
        running: Dict[Future, "tuple[Node, str]"] = {}

        def _resolve(node: Node, value: Any, pending: set) -> None:
            """落值 + 纯函数扇出（缓存命中与新鲜执行同路——shape 从值重建子图）。"""
            self._outputs[node.node_id] = value
            if node.shape is None:
                return
            children = tuple(node.shape(value) or ())
            if children:
                self.add(*children)
                pending.update(n.node_id for n in children if n.node_id not in self._outputs)

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            while pending or running:
                progress = False   # 本趟是否有节点被解决（缓存命中也算推进——命中间接满足他人依赖）
                for nid in sorted(pending):
                    node = self._nodes[nid]
                    if not all(d in self._outputs for d in node.deps):
                        continue
                    pending.discard(nid)
                    progress = True
                    ih = self._inputs_hash(node)
                    hit, value = self._cached(node, ih)
                    if hit:
                        self._emit("cached", node.node_id)
                        _resolve(node, value, pending)
                        continue
                    inputs = {d: self._outputs[d] for d in node.deps}
                    self._emit("running", node.node_id)
                    running[pool.submit(self._invoke, node, inputs)] = (node, ih)
                if not running:
                    if pending:
                        if not progress:
                            raise DagError(f"存在不可满足依赖（环？）：{sorted(pending)}")
                        continue   # 缓存命中刚满足了新依赖——重扫就绪集
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for fut in done:
                    node, ih = running.pop(fut)
                    try:
                        value = fut.result()
                    except Exception as e:  # noqa: BLE001 —— 原样上抛带节点 id
                        self._emit("failed", node.node_id, error=str(e))
                        raise DagError(f"节点 {node.node_id!r} 失败：{e}") from e
                    self._store(node, ih, value)
                    self._emit("done", node.node_id)
                    _resolve(node, value, pending)
        return dict(self._outputs)
