"""ACP 聊天桥测试：假对端 AcpClient 注入 FastAPI app，TestClient 走 REST + SSE。"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import zstandard
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
            peer.notify_update(SESSION_ID, {
                "sessionUpdate": "usage_update", "used": 42, "size": 128})
            await peer.drain()
            await asyncio.sleep(0.05)
            peer.respond(message, {"stopReason": "end_turn"})
            await peer.drain()


async def resumable_handler(peer: Peer) -> None:
    """模拟带一个已落盘（可恢复）会话的对端：session/list 报 disk-1。"""

    while True:
        message = await peer.read()
        if message is None:
            return
        method = message.get("method")
        if method == "session/new":
            peer.respond(message, {"sessionId": SESSION_ID, "configOptions": []})
            await peer.drain()
        elif method == "session/list":
            peer.respond(message, {"sessions": [{"sessionId": "disk-1"}]})
            await peer.drain()
        elif method == "session/resume":
            assert message["params"]["sessionId"] == "disk-1"
            peer.respond(message, {"sessionId": "disk-1", "configOptions": []})
            await peer.drain()
        elif method == "session/prompt":
            peer.notify_update(SESSION_ID, {
                "sessionUpdate": "usage_update", "used": 42, "size": 128})
            await peer.drain()
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
            "agent_message_chunk", "tool_call", "tool_call_update", "usage_update",
            "prompt_closed",
        ], kinds
        assert events[0]["content"]["text"] == "你好"
        assert events[1]["title"] == "mcp__nous__read_report"
        assert events[-1]["stopReason"] == "end_turn"

        # cancel → 202 且假对端收到无 id 通知
        cancelled = client.post(f"/sessions/{sid}/cancel")
        assert cancelled.status_code == 202

        # list：活跃会话排前（带摘要标题与最近用量），落盘会话报可恢复
        listed = client.get("/sessions").json()
        assert listed["sessions"][0]["session_id"] == sid
        assert listed["sessions"][0]["status"] == "active"
        assert listed["sessions"][0]["usage"] == {"used": 42, "size": 128}
        assert len(listed["sessions"]) == 1

    cancel_notes = [m for m in peer.requests if m.get("method") == "session/cancel"]
    assert cancel_notes and "id" not in cancel_notes[0]


def test_resume_merges_persisted_session_into_active():
    holder: dict[str, Any] = {}
    ready = threading.Event()
    app = create_app(make_fake_client(resumable_handler, holder, ready), default_cwd="/tmp/ws")

    with TestClient(app) as client:
        assert ready.wait(timeout=5)

        # 建活跃会话（带首条 prompt）：列表应同时呈现活跃 + ACP 落盘的可恢复会话
        created = client.post("/sessions", json={"prompt": "开场问题"})
        assert created.status_code == 200
        sid = created.json()["session_id"]
        with client.stream("GET", f"/sessions/{sid}/events") as stream:
            _read_events(stream, lambda e: e["sessionUpdate"] == "prompt_closed")

        listed = client.get("/sessions").json()["sessions"]
        assert [(s["session_id"], s["status"]) for s in listed] == [
            (sid, "active"), ("disk-1", "resumable"),
        ]
        active = next(s for s in listed if s["session_id"] == sid)
        assert active["title"] == "开场问题"
        assert active["usage"] == {"used": 42, "size": 128}
        assert next(s for s in listed if s["session_id"] == "disk-1")["usage"] is None

        # 恢复落盘会话 → 纳入活跃记账、可正常下发 prompt（历史不回放，事件流从空开始）
        resumed = client.post("/sessions/disk-1/resume")
        assert resumed.status_code == 200
        accepted = client.post("/sessions/disk-1/prompt", json={"text": "继续"})
        assert accepted.status_code == 202
        with client.stream("GET", "/sessions/disk-1/events") as stream:
            events = _read_events(stream, lambda e: e["sessionUpdate"] == "prompt_closed")
        assert events[-1]["stopReason"] == "end_turn"

        # 重复 resume 活跃会话 → 409；最终两个会话都报活跃
        assert client.post("/sessions/disk-1/resume").status_code == 409
        statuses = {s["session_id"]: s["status"] for s in client.get("/sessions").json()["sessions"]}
        assert statuses == {sid: "active", "disk-1": "active"}


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


def test_healthz_and_prefix_router():
    """独立进程形态：/healthz 供 workbench 探活；prefix 让整组端点挂子路径。"""
    holder: dict[str, Any] = {}
    ready = threading.Event()
    app = create_app(
        make_fake_client(chatty_handler, holder, ready), default_cwd="/tmp/ws", prefix="/chat"
    )

    with TestClient(app) as client:
        assert ready.wait(timeout=5)
        assert client.get("/healthz").json() == {"ok": True}

        # 独立原型页路径基于前缀生成
        page = client.get("/")
        assert 'const BASE = "/chat";' in page.text

        created = client.post("/chat/sessions", json={})
        assert created.status_code == 200
        sid = created.json()["session_id"]
        listed = client.get("/chat/sessions").json()["sessions"]
        assert listed[0]["session_id"] == sid
        assert listed[0]["status"] == "active"
        # 无前缀路径不再存在
        assert client.post("/sessions", json={}).status_code == 404


def test_main_preflight_missing_model_config(monkeypatch, capsys):
    """独立进程入口：缺 HSR_NOUS_LLM_AGENTS_* 即打印中文错误并非零退出。"""
    from hsr_nous.agents import chat_server
    from hsr_nous.agents.dsh import MODEL_ENV_KEYS

    monkeypatch.setattr("hsr_nous.common.load_repo_env", lambda: None)  # 隔离仓库 .env
    for name in MODEL_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    assert chat_server.main(["--port", "0"]) == 1
    assert "缺少模型配置" in capsys.readouterr().err


def test_main_preflight_missing_dsh(monkeypatch, capsys):
    """独立进程入口：DSH 不可执行即打印中文错误并非零退出（workbench 依此降级）。"""
    from hsr_nous.agents import chat_server
    from hsr_nous.agents.dsh import MODEL_ENV_KEYS

    monkeypatch.setattr("hsr_nous.common.load_repo_env", lambda: None)
    for name in MODEL_ENV_KEYS:
        monkeypatch.setenv(name, "stub")
    monkeypatch.setattr("hsr_nous.agents.dsh._executable", lambda _bin: "/nonexistent/dsh")
    assert chat_server.main(["--port", "0"]) == 1
    assert "找不到 DSH" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 会话历史重建：DSH 落盘日志（zstd JSONL）→ GET /sessions/{id}/history
# ---------------------------------------------------------------------------

def _write_session_log(
    log_root: Path, session_id: str, events: list[Any],
    cwd_dir: str = "--root-HSR_Nous-workspace--",
) -> Path:
    """在 <log_root>/<cwd 变形>/<session_id>/session.v4.jsonl.zstd 造落盘日志。

    ``events`` 元素为 dict（JSON 序列化）或 str（原样写入一行，用于坏行容错）。
    """
    target = log_root / cwd_dir / session_id
    target.mkdir(parents=True)
    raw = "".join(
        (item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)) + "\n"
        for item in events
    )
    path = target / "session.v4.jsonl.zstd"
    path.write_bytes(zstandard.ZstdCompressor().compress(raw.encode("utf-8")))
    return path


def _user_event(seq: int, text: str) -> dict[str, Any]:
    # 真实落盘形状：扁平 content + source.kind=="user"（区别于 assistant 的
    # data.message 嵌套）；runtime-context 注入另见 _injected_context_event
    return {
        "type": "user/message", "seq": seq,
        "data": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
            "source": {"kind": "user"},
        },
    }


def _injected_context_event(seq: int) -> dict[str, Any]:
    """DSH 注入的 runtime-context 快照也记为 user/message，必须被过滤。"""
    return {
        "type": "user/message", "seq": seq,
        "data": {
            "role": "user",
            "content": [{"type": "text", "text": "Current runtime context. This snapshot…"}],
            "source": {"kind": "runtime-context", "form": "snapshot"},
        },
    }


def _assistant_event(seq: int, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "assistant/message", "seq": seq,
        "data": {"message": {"role": "assistant", "content": blocks}},
    }


def _history_app(tmp_path: Path, log_root: Path | None):
    holder: dict[str, Any] = {}
    ready = threading.Event()
    return create_app(
        make_fake_client(resumable_handler, holder, ready),
        default_cwd="/tmp/ws",
        session_log_root=log_root,
    ), ready


def test_history_rebuilt_from_session_log(tmp_path):
    """turns 按 seq 排序：user/assistant 的 text 块拼接，reasoning/工具行与坏行跳过。"""
    log_root = tmp_path / "dsh-home" / "sessions"
    _write_session_log(log_root, "disk-9", [
        {"type": "session", "sessionId": "disk-9"},  # 首行无 seq，跳过
        _user_event(1, "第一问"),
        _assistant_event(2, [
            {"type": "reasoning", "text": "内部思考不应出现"},
            {"type": "text", "text": "回答一"},
            {"type": "text", "text": "（续）"},
        ]),
        "{bad json line",  # 坏行容错
        _injected_context_event(2),  # runtime-context 注入：记为 user 但非真用户轮，必须过滤
        _user_event(3, "第二问"),
        _assistant_event(4, [
            {"type": "tool_use", "name": "mcp__nous__read_report"},
            {"type": "text", "text": "回答二"},
        ]),
    ])
    app, ready = _history_app(tmp_path, log_root)

    with TestClient(app) as client:
        assert ready.wait(timeout=5)
        response = client.get("/sessions/disk-9/history")
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "session-log"
        assert body["turns"] == [
            {"role": "user", "text": "第一问"},
            {"role": "assistant", "text": "回答一（续）"},
            {"role": "user", "text": "第二问"},
            {"role": "assistant", "text": "回答二"},
        ]


def test_history_not_found_when_no_log(tmp_path):
    """无落盘日志（或未传 session_log_root）→ 404，页面走「历史不回放」降级。"""
    app, ready = _history_app(tmp_path, tmp_path / "dsh-home" / "sessions")
    with TestClient(app) as client:
        assert ready.wait(timeout=5)
        response = client.get("/sessions/nope/history")
        assert response.status_code == 404
        assert response.json()["detail"] == "该会话无落盘日志"

    app_none, ready_none = _history_app(tmp_path, None)
    with TestClient(app_none) as client:
        assert ready_none.wait(timeout=5)
        assert client.get("/sessions/any/history").status_code == 404


def test_history_corrupt_log_returns_502(tmp_path):
    """文件损坏（非 zstd 内容）→ 502 清晰中文错误。"""
    log_root = tmp_path / "dsh-home" / "sessions"
    target = log_root / "--root-HSR_Nous-workspace--" / "disk-9"
    target.mkdir(parents=True)
    (target / "session.v4.jsonl.zstd").write_bytes(b"not a zstd stream at all")
    app, ready = _history_app(tmp_path, log_root)

    with TestClient(app) as client:
        assert ready.wait(timeout=5)
        response = client.get("/sessions/disk-9/history")
        assert response.status_code == 502
        assert "会话日志损坏" in response.json()["detail"]


# ---------------------------------------------------------------------------
# SSE 重连去重：桥侧 seq 单调 + events ?after= 重演过滤
# ---------------------------------------------------------------------------


def test_events_seq_monotonic_and_after_filter_skips_replay():
    """每事件带会话内单调 seq；?after=N 重放只补 seq>N 的新事件。"""
    holder: dict[str, Any] = {}
    ready = threading.Event()
    app = create_app(make_fake_client(chatty_handler, holder, ready), default_cwd="/tmp/ws")

    with TestClient(app) as client:
        assert ready.wait(timeout=5)
        sid = client.post("/sessions", json={}).json()["session_id"]

        client.post(f"/sessions/{sid}/prompt", json={"text": "第一轮"})
        with client.stream("GET", f"/sessions/{sid}/events") as stream:
            first = _read_events(stream, lambda e: e["sessionUpdate"] == "prompt_closed")
        seqs = [e["seq"] for e in first]
        assert all(isinstance(s, int) for s in seqs)
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "seq 应单调不重复"
        after = max(seqs)

        # 第二轮：带 after 订阅——重放跳过第一轮，只收新事件
        client.post(f"/sessions/{sid}/prompt", json={"text": "第二轮"})
        with client.stream("GET", f"/sessions/{sid}/events", params={"after": after}) as stream:
            second = _read_events(stream, lambda e: e["sessionUpdate"] == "prompt_closed")
        assert second, "after 过滤后仍应收到第二轮事件"
        assert all(e["seq"] > after for e in second)
        assert any(e["sessionUpdate"] == "agent_message_chunk" for e in second)


# ---------------------------------------------------------------------------
# 原生 token 流插件回推：POST /ingest/{sid} 合流
# ---------------------------------------------------------------------------


def test_ingest_delta_merges_into_event_stream():
    """delta 经 publish 合流（带 seq）；未知会话 202 丢弃；未知载荷 400。"""
    from hsr_nous.agents.chat_server import _LOOPBACK_HOSTS

    holder: dict[str, Any] = {}
    ready = threading.Event()
    app = create_app(make_fake_client(chatty_handler, holder, ready), default_cwd="/tmp/ws")

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert ready.wait(timeout=5)
        sid = client.post("/sessions", json={}).json()["session_id"]

        # 未知会话：202 丢弃（插件可能先于桥记账）
        ghost = client.post(
            "/ingest/ghost", json={"sessionUpdate": "agent_message_delta", "text": "x"}
        )
        assert ghost.status_code == 202 and ghost.json() == {"accepted": False}

        # 未知载荷类型：400（text 带上，让校验走到桥自己的类型闸）
        bad = client.post(
            f"/ingest/{sid}", json={"sessionUpdate": "mystery", "text": "x"}
        )
        assert bad.status_code == 400

        # 回环校验：正常合流应被接受（starlette 1.9 的 TestClient 默认 client 是
        # "testclient"，这里显式指定回环地址模拟插件/反代的真实来源）
        assert "127.0.0.1" in _LOOPBACK_HOSTS and "::1" in _LOOPBACK_HOSTS
        with client.stream("GET", f"/sessions/{sid}/events") as stream:
            accepted = client.post(
                f"/ingest/{sid}",
                json={"sessionUpdate": "agent_message_delta", "text": "tok"},
            )
            assert accepted.status_code == 202 and accepted.json() == {"accepted": True}
            deltas = _read_events(stream, lambda e: e["sessionUpdate"] == "agent_message_delta")
        assert deltas[0]["text"] == "tok"
        assert isinstance(deltas[0]["seq"], int), "ingest 事件同样带单调 seq"

    # 非回环来源：403（安全闸——ingest 只该来自本机插件/反代）。单独造 app：
    # 同一 fake client 不能进第二个 TestClient（lifespan 会重复 start）
    holder2: dict[str, Any] = {}
    ready2 = threading.Event()
    app2 = create_app(make_fake_client(chatty_handler, holder2, ready2), default_cwd="/tmp/ws")
    with TestClient(app2, client=("10.0.0.1", 40000)) as outsider:
        assert ready2.wait(timeout=5)
        denied = outsider.post(
            "/ingest/ghost", json={"sessionUpdate": "agent_message_delta", "text": "x"}
        )
        assert denied.status_code == 403
