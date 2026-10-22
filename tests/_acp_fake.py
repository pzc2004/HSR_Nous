"""ACP 假对端：进程内双向管道（socketpair），回预设 JSON-RPC 序列。

AcpClient 通过 ``spawn`` 注入拿到管道一端；handler 协程拿到另一端，
按测试脚本回响应/推通知。确定性、无 DSH、无网络。
"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Awaitable, Callable
from typing import Any

from hsr_nous.agents.acp_client import AcpClient, _Transport

Handler = Callable[["Peer"], Awaitable[None]]


class Peer:
    """假 ACP 服务器侧句柄：读客户端帧、回响应、推通知。"""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self.requests: list[dict[str, Any]] = []
        """收到的全部客户端请求/通知（测试断言用）。"""

    async def read(self) -> dict[str, Any] | None:
        """读下一帧；客户端断开后返回 None。

        ``initialize`` 由假对端自动应答（探针实测形状的精简版：
        ``{"protocolVersion": 1}``），handler 只处理之后的业务帧；
        要测 initialize 本身的用 ``read_raw``。
        """
        while True:
            message = await self.read_raw()
            if message is None:
                return None
            if message.get("method") == "initialize":
                self.respond(message, {"protocolVersion": 1})
                await self.drain()
                continue
            return message

    async def read_raw(self) -> dict[str, Any] | None:
        """读下一帧原文（不做 initialize 自动应答）。"""
        raw = await self._reader.readline()
        if not raw:
            return None
        message = json.loads(raw.decode("utf-8"))
        self.requests.append(message)
        return message

    def send(self, message: dict[str, Any]) -> None:
        """发一帧（响应或通知）。"""
        self._writer.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))

    async def drain(self) -> None:
        await self._writer.drain()

    async def send_flush(self, message: dict[str, Any]) -> None:
        self.send(message)
        await self._writer.drain()

    def respond(self, request: dict[str, Any], result: dict[str, Any]) -> None:
        assert "id" in request
        self.send({"jsonrpc": "2.0", "id": request["id"], "result": result})

    def respond_error(self, request: dict[str, Any], code: int, message: str) -> None:
        assert "id" in request
        self.send({"jsonrpc": "2.0", "id": request["id"],
                     "error": {"code": code, "message": message}})

    def notify_update(self, session_id: str, update: dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "method": "session/update",
                   "params": {"sessionId": session_id, "update": update}})

    async def aclose(self) -> None:
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


class _PipeTransport(_Transport):
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer

    def write(self, data: bytes) -> None:
        self._writer.write(data)

    async def drain(self) -> None:
        await self._writer.drain()

    async def readline(self) -> bytes:
        return await self._reader.readline()

    async def aclose(self) -> None:
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


async def open_client_with_peer(handler: Handler) -> tuple[AcpClient, Peer, asyncio.Task[None]]:
    """在 running loop 里造一对 (AcpClient, Peer) + handler 任务。

    测试随后 ``await client.start()`` 触发握手；peer 可直接断言收到的帧。
    handler 正常返回或客户端断开即结束。
    """
    client_sock, server_sock = socket.socketpair()
    server_reader, server_writer = await asyncio.open_connection(sock=server_sock)
    peer = Peer(server_reader, server_writer)

    async def spawn() -> _Transport:
        client_reader, client_writer = await asyncio.open_connection(sock=client_sock)
        return _PipeTransport(client_reader, client_writer)

    async def run() -> None:
        try:
            await handler(peer)
        finally:
            await peer.aclose()

    task = asyncio.create_task(run(), name="acp-fake-peer")
    client = AcpClient(argv=["fake"], env={}, cwd="/", spawn=spawn)
    return client, peer, task
