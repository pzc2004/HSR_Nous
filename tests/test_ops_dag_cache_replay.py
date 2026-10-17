"""annotator 缓存重放：分段、cached 节点、服务映射与批量执行."""

from __future__ import annotations

import json

import pytest

from hsr_nous.ops.dag.cache_replay import (
    CachedRun,
    load_cached_runs,
    run_queue_cached,
)
from hsr_nous.ops.dag.simulation import SimTask


def _record(t, event, node, **extra):
    return json.dumps({"t": t, "event": event, "node": node, **extra})


def test_load_cached_runs_segments_and_cached_nodes(tmp_path):
    source = tmp_path / "light_cones" / "x" / "events.jsonl"
    source.parent.mkdir(parents=True)
    rows = [
        _record(0, "declared", "data_pull", kind="mechanical", deps=[]),
        _record(0, "declared", "evidence", kind="llm", deps=["data_pull"]),
        _record(0, "declared", "compile1", kind="gate", deps=["evidence", "data_pull"]),
        _record(0.001, "running", "data_pull"),
        _record(0.011, "done", "data_pull"),
        _record(0.020, "running", "evidence"),
        _record(0.030, "failed", "evidence", error="stop"),
        # 第二次运行：data_pull/evidence 命中缓存，只新鲜执行 compile1。
        _record(100, "declared", "data_pull", kind="mechanical", deps=[]),
        _record(100, "declared", "evidence", kind="llm", deps=["data_pull"]),
        _record(100, "declared", "compile1", kind="gate", deps=["evidence", "data_pull"]),
        _record(100.001, "cached", "data_pull"),
        _record(100.002, "cached", "evidence"),
        _record(100.003, "running", "compile1"),
        _record(100.008, "done", "compile1"),
    ]
    source.write_text("\n".join(rows) + "\n", encoding="utf-8")
    runs = load_cached_runs(tmp_path, duration_scale=0.1)
    assert len(runs) == 2

    first = {task.task_id: task for task in runs[0].tasks}
    assert set(first) == {"light_cones/x#0:data_pull", "light_cones/x#0:evidence"}
    assert first["light_cones/x#0:data_pull"].service == "game_data"
    assert first["light_cones/x#0:data_pull"].duration == pytest.approx(0.001)
    assert first["light_cones/x#0:evidence"].service == "llm_api"
    assert first["light_cones/x#0:evidence"].deps == ("light_cones/x#0:data_pull",)

    second = {task.task_id: task for task in runs[1].tasks}
    assert set(second) == {
        "light_cones/x#1:data_pull", "light_cones/x#1:evidence", "light_cones/x#1:compile1",
    }
    assert second["light_cones/x#1:data_pull"].service == "local"
    assert second["light_cones/x#1:data_pull"].duration == 1e-6
    assert second["light_cones/x#1:compile1"].service == "compile"
    assert second["light_cones/x#1:compile1"].duration == pytest.approx(0.0005)


def test_load_cached_runs_skips_incomplete_segment(tmp_path):
    source = tmp_path / "c" / "events.jsonl"
    source.parent.mkdir()
    source.write_text("\n".join([
        _record(0, "declared", "data_pull", kind="mechanical", deps=[]),
        _record(0.001, "running", "data_pull"),
    ]) + "\n", encoding="utf-8")
    assert load_cached_runs(tmp_path) == []


def test_queue_cached_production_backend():
    runs = [
        CachedRun("a", (
            SimTask("a:data", "game_data", 0.001),
            SimTask("a:llm", "llm_api", 0.001, deps=("a:data",)),
        ), 0.002),
        CachedRun("b", (
            SimTask("b:web", "web_search", 0.001),
            SimTask("b:compile", "compile", 0.001, deps=("b:web",)),
        ), 0.002),
    ]
    capacities = {"game_data": 1, "llm_api": 1, "web_search": 1, "compile": 1}
    queued = run_queue_cached(
        runs, capacities, batch_workers=2, entity_workers=1,
        sleep=lambda _duration: None)
    queued_by_id = {t.task_id: t for t in queued.traces}
    assert set(queued_by_id) == {"a:data", "a:llm", "b:web", "b:compile"}
    assert queued_by_id["a:data"].end <= queued_by_id["a:llm"].start
    assert queued_by_id["b:web"].end <= queued_by_id["b:compile"].start
