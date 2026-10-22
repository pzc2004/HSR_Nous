"""ACP 聊天桥测试：假对端 AcpClient 注入 FastAPI app，TestClient 走 REST + SSE。"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from hsr_nous.agents.acp_client import AcpClient
from hsr_nous.agents.chat_server import create_app
from tests._acp_fake import Handler, Peer, _PipeTransport

SESSION_ID = "srv-sid-1"


def make_fake_client(
    handler: Handler, holder: dict[str, Any], ready: threading.Event
) -> AcpClient:
    """造注入假对端的 AcpClient：spawn 在 app 事件循环里同时起 handler 任务。

    ``holder["peer"]`` 拿到假对端句柄（断言收到的帧），``ready`` 在管道就绪时 set。
    """

    client_sock, server_sock = socket.socketpair()

    async def spawn() -> _PipeTransport:
        reader, writer = await asyncio.open_connection(sock=client_sock)
        server_reader, server_writer = await asyncio.open_connection(sock=server_sock)
        peer = Peer(server_reader, server_writer)
        holder["peer"] = peer
        ready.set()

        async def run() -> None:
            try:
                await handler(peer)
            finally:
                await peer.aclose()

        asyncio.create_task(run(), name="acp-fake-peer")
        return _PipeTransport(reader, writer)

    return AcpClient(argv=["fake"], env={}, cwd="/", spawn=spawn)


def _read_events(stream, stop: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
    """从 TestClient SSE 流里收事件，直到 stop(event) 为真（或流断）。"""
    events: list[dict[str, Any]] = []
    for line in stream.iter_lines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[len("data: "):])
        events.append(event)
        if stop(event):
            break
    return events


# ---------------------------------------------------------------------------
# 假对端 handler：交错推 update 再结算（验桥在 prompt 在途期间持续泵）
# ---------------------------------------------------------------------------


async def chatty_handler(peer: Peer) -> None:
    while True:
        message = await peer.read()
        if message is None:
            return
        method = message.get("method")
        if method == "session/new":
            peer.respond(message, {
                "sessionId": SESSION_ID,
                "configOptions": [{
                    "id": "model", "type": "select", "currentValue": "deepseek",
                    "options": [
                        {"group": "deepseek-official", "name": "DS",
                         "options": [{"value": "ds", "name": "ds"}]},
                        {"group": "openai-gateway", "name": "GW",
                         "options": [{"value": '["openai-gateway","m"]', "name": "m"}]},
                    ],
                }],
            })
            await peer.drain()
        elif method == "session/set_config_option":
            peer.respond(message, {"configOptions": []})
            await peer.drain()
        elif method == "session/list":
            peer.respond(message, {"sessions": []})
            await peer.drain()
        elif method == "session/prompt":
            assert message["params"]["sessionId"] == SESSION_ID
            peer.notify_update(SESSION_ID, {
                "sessionUpdate": "agent_message_chunk", "messageId": "m1",
                "content": {"type": "text", "text": "你好"}})
            peer.notify_update(SESSION_ID, {
                "sessionUpdate": "tool_call", "toolCallId": "t1",
                "title": "mcp__nous__read_report", "status": "in_progress",
                "rawInput": {"trial_id": "x"}})
            peer.notify_update(SESSION_ID, {
                "sessionUpdate": "tool_call_update", "toolCallId": "t1",
                "status": "completed"})
            await peer.drain()
            await asyncio.sleep(0.05)
            peer.respond(message, {"stopReason": "end_turn"})
            await peer.drain()


def test_create_prompt_sse_and_cancel_roundtrip():
    holder: dict[str, Any] = {}
    ready = threading.Event()
    app = create_app(make_fake_client(chatty_handler, holder, ready), default_cwd="/tmp/ws")

    with TestClient(app) as client:
        assert ready.wait(timeout=5), "假对端管道未就绪"
        peer = holder["peer"]

        created = client.post("/sessions", json={})
        assert created.status_code == 200
        sid = created.json()["session_id"]
        assert sid == SESSION_ID

        # 建会话后桥应把 model 配置项钉到 openai-gateway 组（.env 端点）
        pin = [m for m in peer.requests if m.get("method") == "session/set_config_option"]
        assert pin and pin[0]["params"]["value"] == '["openai-gateway","m"]'

        # prompt 下发 → 202，随后后台任务跑 prompt
        accepted = client.post(f"/sessions/{sid}/prompt", json={"text": "读报告"})
        assert accepted.status_code == 202

        # SSE：应依次收到交错 update 与本地合成的 prompt_closed
        with client.stream("GET", f"/sessions/{sid}/events") as stream:
            events = _read_events(stream, lambda e: e["sessionUpdate"] == "prompt_closed")
        kinds = [e["sessionUpdate"] for e in events]
        assert kinds == [
            "agent_message_chunk", "tool_call", "tool_call_update", "prompt_closed",
        ], kinds
        assert events[0]["content"]["text"] == "你好"
        assert events[1]["title"] == "mcp__nous__read_report"
        assert events[-1]["stopReason"] == "end_turn"

        # cancel → 202 且假对端收到无 id 通知
        cancelled = client.post(f"/sessions/{sid}/cancel")
        assert cancelled.status_code == 202

        # list：活动会话应出现在 active 里（session/list 只列已关闭的）
        listed = client.get("/sessions").json()
        assert listed["sessions"] == []
        assert listed["active"] == [sid]

    cancel_notes = [m for m in peer.requests if m.get("method") == "session/cancel"]
    assert cancel_notes and "id" not in cancel_notes[0]


def test_create_session_with_initial_prompt_streams_updates():
    holder: dict[str, Any] = {}
    ready = threading.Event()
    app = create_app(make_fake_client(chatty_handler, holder, ready), default_cwd="/tmp/ws")

    with TestClient(app) as client:
        assert ready.wait(timeout=5)
        created = client.post("/sessions", json={"prompt": "直接开始"})
        assert created.status_code == 200
        sid = created.json()["session_id"]

        with client.stream("GET", f"/sessions/{sid}/events") as stream:
            events = _read_events(stream, lambda e: e["sessionUpdate"] == "prompt_closed")
        assert events[-1]["sessionUpdate"] == "prompt_closed"
        assert any(e["sessionUpdate"] == "agent_message_chunk" for e in events)

        peer = holder["peer"]
        prompts = [m for m in peer.requests if m.get("method") == "session/prompt"]
        assert len(prompts) == 1 and prompts[0]["params"]["prompt"] == [
            {"type": "text", "text": "直接开始"},
        ]


def test_unknown_session_and_empty_prompt_rejected():
    holder: dict[str, Any] = {}
    ready = threading.Event()
    app = create_app(make_fake_client(chatty_handler, holder, ready), default_cwd="/tmp/ws")

    with TestClient(app) as client:
        assert ready.wait(timeout=5)
        assert client.post("/sessions/ghost/prompt", json={"text": "hi"}).status_code == 404
        assert client.post("/sessions/ghost/cancel").status_code == 404
        assert client.get("/sessions/ghost/events").status_code == 404

        created = client.post("/sessions", json={})
        sid = created.json()["session_id"]
        assert client.post(f"/sessions/{sid}/prompt", json={"text": "  "}).status_code == 400


def test_index_page_served():
    holder: dict[str, Any] = {}
    ready = threading.Event()
    app = create_app(make_fake_client(chatty_handler, holder, ready), default_cwd="/tmp/ws")

    with TestClient(app) as client:
        assert ready.wait(timeout=5)
        page = client.get("/")
        assert page.status_code == 200
        assert "ACP 桥原型" in page.text
        assert "EventSource" in page.text
