"""ACP v1 客户端测试：进程内假对端单测（确定性）+ 真 dsh --profile acp hermetic live 测试。"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from hsr_nous.agents.acp_client import (
    AcpClient,
    AcpConnectionError,
    AcpProtocolError,
    AcpTimeoutError,
)
from hsr_nous.common import repo_root
from tests._acp_fake import open_client_with_peer

SESSION_ID = "11111111-2222-3333-4444-555555555555"


def _update(update_id: str, **extra: object) -> dict:
    base = {"sessionUpdate": update_id}
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# 假对端单测（无 DSH、无网络）
# ---------------------------------------------------------------------------


def test_handshake_and_session_lifecycle():
    async def scenario() -> None:
        authenticated: list[str] = []

        async def handler(peer):
            while True:
                # 自定义 initialize 应答（advertise authMethods），绕开自动应答
                message = await peer.read_raw()
                if message is None:
                    return
                method = message.get("method")
                if method == "initialize":
                    assert message["params"]["protocolVersion"] == 1
                    peer.respond(message, {
                        "protocolVersion": 1,
                        "agentInfo": {"name": "fake-acp", "version": "0.0.1"},
                        "agentCapabilities": {"sessionCapabilities": {"close": {}, "list": {}, "resume": {}}},
                        "authMethods": [{"id": "fake-method", "name": "Fake"}],
                    })
                    await peer.drain()
                elif method == "authenticate":
                    authenticated.append(message["params"]["methodId"])
                    peer.respond(message, {})
                    await peer.drain()
                elif method == "session/new":
                    assert message["params"]["mcpServers"] == []
                    peer.respond(message, {
                        "sessionId": SESSION_ID,
                        "configOptions": [{"id": "model", "type": "select", "currentValue": "x", "options": []}],
                    })
                    await peer.drain()
                elif method == "session/list":
                    peer.respond(message, {"sessions": [{"sessionId": SESSION_ID, "cwd": "/tmp"}]})
                    await peer.drain()
                elif method == "session/resume":
                    assert message["params"]["sessionId"] == SESSION_ID
                    peer.respond(message, {"configOptions": []})
                    await peer.drain()
                elif method == "session/close":
                    peer.respond(message, {})
                    await peer.drain()
                elif method == "session/set_config_option":
                    assert message["params"] == {
                        "sessionId": SESSION_ID, "configId": "reasoning_effort", "value": "off",
                    }
                    peer.respond(message, {"configOptions": [{"id": "reasoning_effort", "currentValue": "off"}]})
                    await peer.drain()

        client, peer, task = await open_client_with_peer(handler)
        await client.start()
        assert authenticated == ["fake-method"], "authMethods 非空时应以首个 methodId 认证"
        assert client.server_info is not None

        sid = await client.new_session("/tmp/ws")
        assert sid == SESSION_ID
        assert client.last_config_options[0]["id"] == "model"
        assert (await client.list_sessions())[0]["sessionId"] == SESSION_ID
        await client.resume_session(sid, "/tmp/ws")
        options = await client.set_config_option(sid, "reasoning_effort", "off")
        assert options[0]["currentValue"] == "off"
        await client.close_session(sid)

        methods = [m["method"] for m in peer.requests if "method" in m]
        assert methods == [
            "initialize", "authenticate", "session/new", "session/list",
            "session/resume", "session/set_config_option", "session/close",
        ]
        await client.aclose()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())


def test_prompt_pumps_interleaved_updates_until_settlement():
    async def scenario() -> None:
        async def handler(peer):
            while True:
                message = await peer.read()
                if message is None:
                    return
                if message.get("method") == "session/new":
                    peer.respond(message, {"sessionId": SESSION_ID, "configOptions": []})
                    await peer.drain()
                elif message.get("method") == "session/prompt":
                    assert message["params"] == {
                        "sessionId": SESSION_ID,
                        "prompt": [{"type": "text", "text": "你好"}],
                    }
                    # 模拟 settlement 语义：响应前先排干 update
                    for text in ("你好", "，世界"):
                        peer.notify_update(SESSION_ID, _update(
                            "agent_message_chunk", messageId="m1",
                            content={"type": "text", "text": text}))
                    peer.notify_update(SESSION_ID, _update("usage_update", used=42, size=100))
                    await peer.drain()
                    await asyncio.sleep(0.05)  # 给客户端读循环派发时间
                    peer.respond(message, {"stopReason": "end_turn"})
                    await peer.drain()

        client, _, task = await open_client_with_peer(handler)
        await client.start()
        sid = await client.new_session("/tmp/ws")
        received: list[dict] = []

        async def collect() -> None:
            async for update in client.updates(sid):
                received.append(update)

        collector = asyncio.create_task(collect())
        result = await asyncio.wait_for(client.prompt(sid, "你好"), timeout=5)
        assert result == {"stopReason": "end_turn"}
        await asyncio.sleep(0.1)  # 让最后一帧派发进队列
        assert [u["sessionUpdate"] for u in received] == [
            "agent_message_chunk", "agent_message_chunk", "usage_update",
        ]
        assert received[0]["content"] == {"type": "text", "text": "你好"}
        await client.aclose()
        await asyncio.wait_for(collector, timeout=5)
        assert received  # 连接关闭后迭代结束
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())


def test_cancel_is_notification_without_id():
    async def scenario() -> None:
        async def handler(peer):
            while True:
                message = await peer.read()
                if message is None:
                    return
                if message.get("method") == "session/new":
                    peer.respond(message, {"sessionId": SESSION_ID, "configOptions": []})
                    await peer.drain()
                elif message.get("method") == "session/cancel":
                    assert "id" not in message, "cancel 是通知，不带 id"
                    assert message["params"] == {"sessionId": SESSION_ID}
                    return  # 通知无需响应；handler 结束即关管道

        client, peer, task = await open_client_with_peer(handler)
        await client.start()
        await client.cancel(SESSION_ID)
        await asyncio.wait_for(task, timeout=5)
        assert [m["method"] for m in peer.requests] == ["initialize", "session/cancel"]
        await client.aclose()

    asyncio.run(scenario())


def test_jsonrpc_error_mapped_to_chinese_exception():
    async def scenario() -> None:
        async def handler(peer):
            while True:
                message = await peer.read()
                if message is None:
                    return
                if message.get("method") == "session/new":
                    peer.respond_error(message, -32602, "Invalid params: cwd must be an absolute path")
                    await peer.drain()

        client, _, task = await open_client_with_peer(handler)
        await client.start()
        with pytest.raises(AcpProtocolError, match=r"code=-32602.*cwd must be an absolute"):
            await client.new_session("relative/path")
        await client.aclose()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())


def test_malformed_frame_fails_with_protocol_error():
    async def scenario() -> None:
        async def handler(peer):
            while True:
                message = await peer.read()
                if message is None:
                    return
                if message.get("method") == "session/new":
                    peer._writer.write(b"this-is-not-json\n")
                    await peer.drain()
                    # 保持管道开着，让客户端自己判错
                    await asyncio.sleep(5)

        client, _, task = await open_client_with_peer(handler)
        await client.start()
        with pytest.raises(AcpProtocolError, match="损坏"):
            await asyncio.wait_for(client.new_session("/tmp/ws"), timeout=5)
        await client.aclose()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_request_timeout_raises():
    async def scenario() -> None:
        async def handler(peer):
            while True:
                message = await peer.read()
                if message is None:
                    return
                if message.get("method") == "session/new":
                    pass  # 故意不回

        client, _, task = await open_client_with_peer(handler)
        await client.start()
        with pytest.raises(AcpTimeoutError, match="超时"):
            await client.new_session("/tmp/ws", timeout_s=0.1)
        await client.aclose()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_aclose_terminates_subscribers_and_fails_pending():
    async def scenario() -> None:
        started = asyncio.Event()

        async def handler(peer):
            while True:
                message = await peer.read()
                if message is None:
                    return
                if message.get("method") == "session/new":
                    peer.respond(message, {"sessionId": SESSION_ID, "configOptions": []})
                    await peer.drain()
                elif message.get("method") == "session/prompt":
                    started.set()
                    pass  # 永远不回——pending 与订阅者都应被 aclose 清场

        client, _, task = await open_client_with_peer(handler)
        await client.start()
        sid = await client.new_session("/tmp/ws")
        seen: list[str] = []

        async def collect() -> None:
            async for _ in client.updates(sid):
                seen.append("x")

        collector = asyncio.create_task(collect())
        prompt_task = asyncio.create_task(client.prompt(sid, "挂着"))
        await started.wait()
        await client.aclose()
        with pytest.raises(AcpConnectionError, match="已关闭"):
            await prompt_task
        await asyncio.wait_for(collector, timeout=5)
        assert seen == [], "关闭哨兵直接结束迭代，不产出事件"
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 真 ACP hermetic live 测试：真 dsh --profile acp + 两补丁 + 回环 OpenAI mock
# ---------------------------------------------------------------------------


def _sse_chunk(payload: dict) -> bytes:
    return b"data: " + json.dumps(payload).encode() + b"\n\n"


class _CompletionsHandler(BaseHTTPRequestHandler):
    """回环 OpenAI 兼容 mock。门控在 nous MCP 工具注册完成上：

    - 工具清单未见 mcp__nous__*（注册是异步的，探针实证约数秒）→ 回纯文本收轮；
    - 已见 → 回 mcp__nous__ 工具调用；下一轮（带 tool result）→ 最终文本。
    """

    protocol_version = "HTTP/1.1"

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(body)
        messages = body["messages"]
        tool_names = [t["function"]["name"] for t in body.get("tools", [])]
        has_nous = any(name.startswith("mcp__nous__") for name in tool_names)
        has_tool_turn = any(m.get("role") == "tool" for m in messages)
        if has_nous and not has_tool_turn:
            chunks = [
                {"id": "c1", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant", "tool_calls": [{"index": 0, "id": "call_live", "type": "function", "function": {"name": "mcp__nous__read_candidate_task", "arguments": ""}}]}, "finish_reason": None}]},
                {"id": "c1", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\"task_id\": \"warmup\"}"}}]}, "finish_reason": None}]},
                {"id": "c1", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
            ]
        else:
            text = "final answer after tool" if has_tool_turn else "tools not ready yet"
            chunks = [
                {"id": "c1", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
                {"id": "c1", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]},
                {"id": "c1", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]
        payload = b"".join(_sse_chunk(c) for c in chunks) + b"data: [DONE]\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.mark.skipif(
    not (repo_root() / "external/dsh/node_modules/.bin/dsh").is_file(),
    reason="DSH 未安装（先跑 scripts/setup_agent_env.sh）",
)
def test_real_dsh_acp_prompt_with_loopback_model(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CompletionsHandler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = AcpClient.dsh(
            root=tmp_path / "research",
            model_env={
                "HSR_NOUS_LLM_AGENTS_API_KEY": "test-placeholder",
                "HSR_NOUS_LLM_AGENTS_MODEL": "test-model",
                "HSR_NOUS_LLM_AGENTS_API_BASE": f"http://127.0.0.1:{server.server_port}",
            },
        )
        updates: list[dict] = []
        final_text = asyncio.run(_drive_live_prompt(client, updates))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert final_text == "final answer after tool"
    kinds = [u["sessionUpdate"] for u in updates]
    assert "agent_message_chunk" in kinds
    assert "tool_call" in kinds and "tool_call_update" in kinds
    tool_calls = [u for u in updates if u["sessionUpdate"] == "tool_call"]
    assert tool_calls[0]["title"] == "mcp__nous__read_candidate_task"
    # 工具清单含 mcp__nous__*（模型视角的 offer 来自 nous MCP 网关）
    last_tools = [t["function"]["name"] for t in server.requests[-1].get("tools", [])]
    assert "mcp__nous__read_candidate_task" in last_tools
    assert "mcp__nous__submit_claim" in last_tools


async def _drive_live_prompt(client: AcpClient, updates: list[dict]) -> str:
    """initialize → new → 轮询 prompt 直到 mock 见到 nous 工具并完成一轮工具调用。"""
    await client.start(timeout_s=60)
    try:
        sid = await client.new_session("/tmp")
        # dsh acp 会话默认模型是 deepseek-official 路由；显式钉到 openai-gateway
        # （.env 端点）再发 prompt——与 chat_server 建会话行为一致。
        for option in client.last_config_options:
            if option.get("id") != "model":
                continue
            for group in option.get("options") or []:
                choices = group.get("options") or []
                if group.get("group") == "openai-gateway" and choices:
                    await client.set_config_option(sid, "model", choices[0]["value"])
        collector = asyncio.create_task(_collect(client, sid, updates))
        try:
            final_text = ""
            for attempt in range(10):
                result = await client.prompt(sid, "请开始", timeout_s=180)
                assert result.get("stopReason") == "end_turn"
                final_text = "".join(
                    u.get("content", {}).get("text", "")
                    for u in updates
                    if u["sessionUpdate"] == "agent_message_chunk"
                )
                if final_text == "final answer after tool":
                    break
                updates.clear()
                if attempt < 9:
                    # nous MCP 工具注册是异步的（探针实证数秒），轮询间隔等待
                    await asyncio.sleep(3)
            else:
                raise AssertionError("mock 始终未见 mcp__nous__ 工具注册完成")
            return final_text
        finally:
            collector.cancel()
            await asyncio.gather(collector, return_exceptions=True)
            await client.close_session(sid)
    finally:
        await client.aclose()


async def _collect(client: AcpClient, sid: str, updates: list[dict]) -> None:
    async for update in client.updates(sid):
        updates.append(update)
