"""DAG 可视化：执行器状态流 + web 图重建（零硬编码——结构全从事件流来）."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from hsr_nous.ops.annotator.web import _graph_from_events, create_app
from hsr_nous.ops.dag import Node, Runner


def _run_small_dag(tmp_path):
    r = Runner(tmp_path / "run1")
    r.add(Node("a", lambda i: "A"),
          Node("b", lambda i: i["a"] + "B", deps=("a",), kind="gate"))
    r.run()
    return r


def test_executor_emits_state_flow(tmp_path):
    r = _run_small_dag(tmp_path)
    events = [json.loads(x) for x in (tmp_path / "run1" / "events.jsonl")
              .read_text(encoding="utf-8").splitlines()]
    kinds = [(e["event"], e["node"]) for e in events]
    assert ("declared", "a") in kinds and ("running", "a") in kinds and ("done", "b") in kinds
    st = r.graph_state()
    assert {n["id"] for n in st["nodes"]} == {"a", "b"}
    assert st["edges"] == [["a", "b"]], "依赖结构入状态流"
    assert all(n["status"] == "done" for n in st["nodes"])


def test_graph_from_events_rebuilds_structure_and_status(tmp_path):
    _run_small_dag(tmp_path)
    g = _graph_from_events(tmp_path / "run1")
    assert g["edges"] == [["a", "b"]]
    assert {n["id"] for n in g["nodes"]} == {"a", "b"}
    b = next(n for n in g["nodes"] if n["id"] == "b")
    assert b["kind"] == "gate" and b["status"] == "done"
    assert b["value_preview"], "值预览从缓存记录补"


def test_web_endpoints(tmp_path):
    _run_small_dag(tmp_path)
    c = TestClient(create_app(tmp_path))
    runs = c.get("/api/runs").json()["runs"]
    assert runs and runs[0]["cid"] == "run1"
    g = c.get("/api/graph/run1").json()
    assert {n["id"] for n in g["nodes"]} == {"a", "b"} and g["edges"] == [["a", "b"]]
    assert c.get("/api/graph/ghost").json()["nodes"] == []
    assert "DAG" in c.get("/").text, "单页可达"
