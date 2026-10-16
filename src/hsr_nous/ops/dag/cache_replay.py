"""从 annotator 的 events.jsonl 重建批量 DAG，并用 mock handler 重放.

缓存只提供 DAG 形状与观测耗时，不会重放 LLM、网络或编译命令。``running → done``
可能含 executor/服务排队，因此缩放后的观测耗时是负载参数，不冒充纯服务执行时间；
需要脱离该污染比较策略时，应另用 ``simulation.py`` 做参数扫描。
"""

from __future__ import annotations

import json
import math
import queue
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from hsr_nous.ops.dag.benchmark import MockRunResult, _Recorder
from hsr_nous.ops.dag.dispatcher import (
    SchedulingPolicy,
    ServiceDispatcher,
    ServiceRequest,
    ServiceSpec,
)
from hsr_nous.ops.dag.executor import Node, Runner
from hsr_nous.ops.dag.queue_backend import QueueBackend
from hsr_nous.ops.dag.simulation import SimTask, _graph


@dataclass(frozen=True)
class CachedRun:
    """一个 events 文件分段对应的一次实体 DAG 执行."""

    run_id: str
    tasks: Tuple[SimTask, ...]
    observed_makespan: float


def _fallback_service(node: str, kind: str) -> str:
    if node in ("data_pull", "crosscheck"):
        return "game_data"
    if node == "community_search":
        return "web_search"
    if node == "community_fetch":
        return "web_fetch"
    if kind == "llm" or node in ("evidence", "draft") or node.startswith("revise"):
        return "llm_api"
    if node.startswith(("compile", "smoke", "golden")) or node == "oracle_report":
        return "compile"
    return "local"


def _segments(events: Sequence[Mapping]) -> List[List[Mapping]]:
    """同一文件可含失败重跑；每次重新 declared data_pull 即新分段."""
    segments: List[List[Mapping]] = []
    current: List[Mapping] = []
    for record in events:
        if record.get("event") == "declared" and record.get("node") == "data_pull" and current:
            segments.append(current)
            current = []
        current.append(record)
    if current:
        segments.append(current)
    return segments


def _parse_segment(source: Path, segment_index: int,
                   events: Sequence[Mapping], *, duration_scale: float,
                   min_duration: float) -> Optional[CachedRun]:
    declared = {r["node"]: r for r in events if r.get("event") == "declared"}
    starts = {r["node"]: float(r["t"]) for r in events if r.get("event") == "running"}
    ends = {r["node"]: float(r["t"]) for r in events
            if r.get("event") in ("done", "failed")}
    cached = {r["node"] for r in events if r.get("event") == "cached"}
    if not starts or any(node not in ends for node in starts):
        return None  # 纯缓存段无新工作；运行中崩溃的残缺段不臆造耗时

    run_id = f"{source.parent.parent.name}/{source.parent.name}#{segment_index}"
    nodes = set(starts) | cached
    tasks: List[SimTask] = []
    for node in sorted(nodes):
        if node not in declared:
            return None
        record = declared[node]
        deps = tuple(f"{run_id}:{dep}" for dep in record.get("deps", []))
        if any(dep.rsplit(":", 1)[1] not in nodes for dep in deps):
            return None
        if node in cached and node not in starts:
            duration, service = min_duration, "local"
        else:
            duration = max(min_duration, (ends[node] - starts[node]) * duration_scale)
            service = (record.get("service", "")
                       if "service" in record else _fallback_service(node, record.get("kind", "")))
            service = service or "local"
        tasks.append(SimTask(
            task_id=f"{run_id}:{node}", service=service, duration=duration,
            deps=deps, priority=0.0))
    observed_makespan = max(ends.values()) - min(starts.values())
    return CachedRun(run_id=run_id, tasks=tuple(tasks), observed_makespan=observed_makespan)


def load_cached_runs(runs_root: "str | Path", *, limit: Optional[int] = None,
                     duration_scale: float = 0.001,
                     min_duration: float = 1e-6) -> List[CachedRun]:
    """读取缓存并转成 mock DAG；limit 限制有效分段数而非扫描文件数."""
    root = Path(runs_root)
    if not root.is_dir():
        raise FileNotFoundError(f"缓存目录不存在：{root}")
    if limit is not None and limit < 1:
        raise ValueError("limit 须 ≥1")
    if not math.isfinite(duration_scale) or duration_scale <= 0:
        raise ValueError("duration_scale 须为有限正数")
    if not math.isfinite(min_duration) or min_duration <= 0:
        raise ValueError("min_duration 须为有限正数")

    runs: List[CachedRun] = []
    for source in sorted(root.rglob("events.jsonl")):
        events = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        for index, segment in enumerate(_segments(events)):
            run = _parse_segment(source, index, segment,
                                 duration_scale=duration_scale, min_duration=min_duration)
            if run is not None:
                runs.append(run)
                if limit is not None and len(runs) >= limit:
                    return runs
    return runs


def _prepare(runs: Sequence[CachedRun], capacities: Mapping[str, int],
             batch_workers: int, entity_workers: int) -> Tuple[Dict[str, SimTask], Dict[str, int]]:
    if batch_workers < 1 or entity_workers < 1:
        raise ValueError("batch_workers/entity_workers 须 ≥1")
    by_id, _dependents = _graph(task for run in runs for task in run.tasks)
    caps = dict(capacities)
    # 生产 local 未注册=名义不限流，但实际宽度受外层×单实体 worker 限制；两边显式同帽。
    caps.setdefault("local", batch_workers * entity_workers)
    for name, capacity in caps.items():
        if capacity < 1:
            raise ValueError(f"服务 {name!r} 容量须 ≥1（得到 {capacity}）")
    missing = {task.service for task in by_id.values()} - set(caps)
    if missing:
        raise KeyError(f"缺少服务容量定义：{sorted(missing)}")
    return by_id, caps


def run_queue_cached(runs: Sequence[CachedRun], capacities: Mapping[str, int], *,
                     batch_workers: int = 4, entity_workers: int = 2,
                     sleep: Callable[[float], None] = time.sleep) -> MockRunResult:
    """多实体 Runner + 外层 worker + 批级共享 QueueBackend."""
    by_id, caps = _prepare(runs, capacities, batch_workers, entity_workers)
    if not by_id:
        return MockRunResult((), 0.0)
    recorder = _Recorder(sleep)
    shared_backend = QueueBackend(caps)
    try:
        with tempfile.TemporaryDirectory(prefix="hsr-nous-cache-runner-") as root:
            def run_one(pair: "tuple[int, CachedRun]") -> None:
                index, cached = pair
                runner = Runner(Path(root) / str(index),
                                max_workers=entity_workers, backend=shared_backend)
                for task in cached.tasks:
                    def fn(_inputs, task=task):
                        return recorder.execute(task)
                    runner.add(Node(task.task_id, fn, deps=task.deps,
                                    service=task.service, cache=False))
                runner.run()

            recorder.begin()
            with ThreadPoolExecutor(max_workers=batch_workers) as pool:
                list(pool.map(run_one, enumerate(runs)))
    finally:
        shared_backend.shutdown()
    return recorder.result(by_id)


def run_dispatcher_cached(runs: Sequence[CachedRun], capacities: Mapping[str, int], *,
                          batch_workers: int = 4, entity_workers: int = 2,
                          policies: Optional[Mapping[str, SchedulingPolicy]] = None,
                          priorities: Optional[Mapping[str, float]] = None,
                          sleep: Callable[[float], None] = time.sleep) -> MockRunResult:
    """新路：多实体 ready-list 驱动 + 批级共享 ServiceDispatcher."""
    by_id, caps = _prepare(runs, capacities, batch_workers, entity_workers)
    if not by_id:
        return MockRunResult((), 0.0)
    policies = policies or {}
    priorities = priorities or {}
    unknown_policies = set(policies) - set(caps)
    unknown_priorities = set(priorities) - set(by_id)
    if unknown_policies:
        raise ValueError(f"policies 含未知服务：{sorted(unknown_policies)}")
    if unknown_priorities:
        raise ValueError(f"priorities 含未知任务：{sorted(unknown_priorities)}")

    recorder = _Recorder(sleep)
    specs = [ServiceSpec(name, capacity, recorder.execute,
                         policy=policies.get(name, SchedulingPolicy()))
             for name, capacity in caps.items()]
    dispatcher = ServiceDispatcher(specs)

    def run_one(cached: CachedRun) -> None:
        pending = {task.task_id for task in cached.tasks}
        running = 0
        completed: "queue.Queue[Tuple[str, Future]]" = queue.Queue()
        outputs: Dict[str, str] = {}
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

    try:
        recorder.begin()
        with ThreadPoolExecutor(max_workers=batch_workers) as pool:
            list(pool.map(run_one, runs))
    finally:
        dispatcher.shutdown()
    return recorder.result(by_id)


__all__ = [
    "CachedRun", "load_cached_runs", "run_dispatcher_cached", "run_queue_cached",
]
