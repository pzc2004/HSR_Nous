from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

from hsr_nous.agents.chat_server import create_app as create_chat_app
from hsr_nous.research.core import ArtifactStore, CandidateTaskManager
from hsr_nous.research.permissions import open_research_gateway
from hsr_nous.research.workbench.web import create_app
from tests._research_builders import make_candidate_set
from tests.test_chat_server import (
    _read_events,
    chatty_handler,
    make_fake_client,
    resumable_handler,
)


def test_workbench_read_only_task_report_and_evidence_chain(tmp_path):
    root = tmp_path / "research"
    manager = CandidateTaskManager(ArtifactStore(root / "artifacts"))
    plan = make_candidate_set((600.0, 550.0))
    started = manager.start(plan)
    final = manager.wait_terminal(started["task_id"], timeout_s=120)
    client = TestClient(create_app(gateway=open_research_gateway(root)))
    index = client.get("/")
    assert index.status_code == 200
    assert "HSR_Nous · 研究台" in index.text
    assert "伊德莉拉" not in index.text

    tasks = client.get("/api/tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == final["task_id"]
    assert tasks[0]["status"] == "completed"
    assert tasks[0]["completed_runs"] == 128

    task = client.get(f"/api/tasks/{final['task_id']}").json()
    assert task["candidate_set_id"] == final["candidate_set_id"]
    assert len(task["candidates"]) == 2
    assert all(candidate["result"]["report_id"] for candidate in task["candidates"])

    events = client.get(f"/api/tasks/{final['task_id']}/events").json()
    assert events["events"][-1]["kind"] == "completed"
    cursor = events["events"][-1]["event_id"]
    assert client.get(
        f"/api/tasks/{final['task_id']}/events", params={"after_event_id": cursor}
    ).json()["events"] == []

    report = client.get(f"/api/tasks/{final['task_id']}/report").json()
    assert report["schema_version"] == "candidate-v1"
    assert report["flags"]["validation"] == "pending_real_validation"
    assert len(report["dev_ranking"]) == 2
    candidate = report["candidates"][0]
    trial = client.get(f"/api/trials/{candidate['trial_id']}/reports/{candidate['report_id']}")
    assert trial.status_code == 200, trial.text
    trial_report = trial.json()
    assert trial_report["claim"]["status"] in {"accepted", "inconclusive"}
    assert trial_report["comparisons"]["holdout"]["effect"] is not None
    assert trial_report["cohorts"]["baseline"]["dev"]["n"] == 16

    drilldown = trial_report["evidence"]["drilldown"][0]
    run = client.post("/api/evidence", json=drilldown["run"])
    assert run.status_code == 200, run.text
    assert run.json()["kind"] == "run"
    event = client.post("/api/evidence", json=drilldown["events"][0])
    assert event.status_code == 200, event.text
    assert event.json()["kind"] == "event"
    if drilldown["modifiers"]:
        modifier = client.post("/api/evidence", json=drilldown["modifiers"][0])
        assert modifier.status_code == 200, modifier.text
        assert modifier.json()["kind"] == "modifier"

    assert client.get("/api/tasks", params={"limit": 0}).status_code == 400
    assert client.get("/api/tasks/not-a-task").status_code == 404
    assert client.post("/api/evidence", json={"unknown": True}).status_code == 400


# ---------------------------------------------------------------------------
# 聊天视图：workbench 经 /chat/* 回环反代到 chat 桥子进程（不 import agents）
# ---------------------------------------------------------------------------


def _boot_chat_stub(app: Any) -> tuple[uvicorn.Server, threading.Thread, str]:
    """回环随机端口起真 uvicorn（chat app + 假 ACP 对端），返回 (server, thread, base)。"""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            pytest.fail("聊天桥 stub 启动失败")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, thread, f"http://127.0.0.1:{port}"


@pytest.fixture()
def chat_server_factory():
    """造回环聊天桥 stub（真 uvicorn + 进程内假 ACP 对端），测试结束统一收尸。"""
    booted: list[tuple[uvicorn.Server, threading.Thread]] = []

    def factory(handler: Any, holder: dict[str, Any], ready: threading.Event, cwd: Path) -> str:
        app = create_chat_app(make_fake_client(handler, holder, ready), default_cwd=cwd)
        server, thread, base = _boot_chat_stub(app)
        assert ready.wait(timeout=5), "假对端管道未就绪"
        booted.append((server, thread))
        return base

    yield factory
    for server, thread in booted:
        server.should_exit = True
        thread.join(timeout=10)


def test_workbench_page_has_chat_view_and_proxies_chat_routes(tmp_path, chat_server_factory):
    """单前端合并：workbench 只做 /chat/* 反代，聊天语义全在桥子进程侧。"""
    holder: dict[str, Any] = {}
    ready = threading.Event()
    base = chat_server_factory(chatty_handler, holder, ready, tmp_path / "ws")
    root = tmp_path / "research"
    manager = CandidateTaskManager(ArtifactStore(root / "artifacts"))
    started = manager.start(make_candidate_set((600.0, 550.0)))
    final = manager.wait_terminal(started["task_id"], timeout_s=120)
    client = TestClient(create_app(gateway=open_research_gateway(root), chat_proxy=base))

    page = client.get("/")
    assert page.status_code == 200
    assert "研究数据只读" in page.text
    assert "chatView" in page.text and "sessionList" in page.text  # 聊天视图入口

    # 研究只读 API 不受聊天反代影响
    tasks = client.get("/api/tasks").json()
    assert len(tasks) == 1 and tasks[0]["task_id"] == final["task_id"]

    # /chat/* 透传：建会话 → 列表记账 → prompt → SSE 流式透传收到事件
    created = client.post("/chat/sessions", json={})
    assert created.status_code == 200
    sid = created.json()["session_id"]
    listed = client.get("/chat/sessions").json()["sessions"]
    assert listed[0]["session_id"] == sid
    assert listed[0]["status"] == "active"

    accepted = client.post(f"/chat/sessions/{sid}/prompt", json={"text": "读报告"})
    assert accepted.status_code == 202
    with client.stream(
        "GET", f"/chat/sessions/{sid}/events", headers={"Accept": "text/event-stream"}
    ) as stream:
        events = _read_events(stream, lambda e: e["sessionUpdate"] == "prompt_closed")
    assert events[0]["content"]["text"] == "你好"
    assert events[-1]["stopReason"] == "end_turn"

    # resume/cancel 前缀路径同样透传（活跃会话重复 resume → 409 原样透传）
    assert client.post(f"/chat/sessions/{sid}/resume").status_code == 409
    assert client.post(f"/chat/sessions/{sid}/cancel").status_code == 202


def test_workbench_proxy_merges_resumable_sessions_and_resumes(tmp_path, chat_server_factory):
    """反代不篡改桥语义：落盘会话出现在列表（resumable），resume 后纳入活跃。"""
    holder: dict[str, Any] = {}
    ready = threading.Event()
    base = chat_server_factory(resumable_handler, holder, ready, tmp_path / "ws")
    client = TestClient(create_app(gateway=open_research_gateway(tmp_path / "research"), chat_proxy=base))

    created = client.post("/chat/sessions", json={"prompt": "开场问题"})
    assert created.status_code == 200
    sid = created.json()["session_id"]
    with client.stream(
        "GET", f"/chat/sessions/{sid}/events", headers={"Accept": "text/event-stream"}
    ) as stream:
        _read_events(stream, lambda e: e["sessionUpdate"] == "prompt_closed")

    listed = client.get("/chat/sessions").json()["sessions"]
    assert [(s["session_id"], s["status"]) for s in listed] == [
        (sid, "active"), ("disk-1", "resumable"),
    ]
    assert next(s for s in listed if s["session_id"] == sid)["title"] == "开场问题"

    resumed = client.post("/chat/sessions/disk-1/resume")
    assert resumed.status_code == 200
    assert client.post("/chat/sessions/disk-1/prompt", json={"text": "继续"}).status_code == 202
    statuses = {s["session_id"]: s["status"] for s in client.get("/chat/sessions").json()["sessions"]}
    assert statuses == {sid: "active", "disk-1": "active"}


def test_workbench_chat_proxy_bridge_down_returns_503(tmp_path):
    """桥子进程不可达（运行期死掉/未 spawn 成功）：普通请求 503，SSE 安静结束。"""
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    finally:
        sock.close()
    client = TestClient(create_app(
        gateway=open_research_gateway(tmp_path / "research"),
        chat_proxy=f"http://127.0.0.1:{port}",
    ))
    response = client.get("/chat/sessions")
    assert response.status_code == 503
    assert "聊天桥" in response.json()["detail"]
    with client.stream(
        "GET", "/chat/sessions/ghost/events", headers={"Accept": "text/event-stream"}
    ) as stream:
        assert stream.status_code == 200
        assert b"data:" not in stream.read()


def test_workbench_without_chat_proxy_has_no_chat_routes(tmp_path):
    """未注入 chat_proxy（spawn 失败的降级形态）：页面标注，聊天路由 404。"""
    root = tmp_path / "research"
    client = TestClient(create_app(gateway=open_research_gateway(root)))
    page = client.get("/")
    assert page.status_code == 200
    assert "chatView" in page.text
    assert client.get("/chat/sessions").status_code == 404
    assert client.post("/chat/sessions", json={}).status_code == 404
