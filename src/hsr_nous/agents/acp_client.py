"""ACP v1 客户端：驱动后台 ``dsh --profile acp`` 子进程的 asyncio 桥。

线协议（实测 dsh 0.2.1-rc.2 探针确认，2026-10-22）：

- stdio 上传输**换行分隔的 JSON-RPC 帧**，stdout 纯协议流；请求/响应按 ``id``
  配对，无 ``id`` 的帧是服务器→客户端通知（``session/update`` 等）。
- ``initialize`` 协商 ACP v1（``protocolVersion: 1``），响应含
  ``agentCapabilities`` / ``authMethods``；dsh 的 ``authMethods`` 恒为空数组，
  ``authenticate`` 无需调用（探针实证：即使 authenticate 报参数错，
  ``session/new`` 照常成功）。为兼容其他 ACP 服务端，本客户端在
  ``authMethods`` 非空时仍以首个 methodId 发起 ``authenticate``。
- ``session/new`` 返回 ``{"sessionId": str, "configOptions": [...]}``——
  配置选项是透明 select/boolean 选择器（model / reasoning_effort），
  原样透传不解读。
- ``session/list`` **只列已关闭（可恢复）的持久会话**；活动会话不出现
  （探针实证：new 之后 list 为空，close 之后才列出）。
- ``session/prompt`` 的 settlement 要等全部 ``session/update`` 排干；
  在途期间服务器持续推通知，客户端必须边收通知边等响应——本客户端用
  独立读循环任务天然满足。
- 协议错误形态：JSON-RPC error（如 -32601 未知方法、-32602 参数错、
  -32603 turn 失败）按 ``code + message`` 映射为 ``AcpProtocolError``。

进程模型：一个 ``AcpClient`` = 一个 dsh 子进程（``start_new_session``，
独立进程组），内含多会话；``aclose()`` 关管道后按 SIGTERM→SIGKILL
语义收尸（与 ``dsh._stop`` 一致）。
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from hsr_nous.agents.dsh import _environment, _executable, _prepare_root
from hsr_nous.common import repo_root

# ACP v1 协议版本（@agentclientprotocol/sdk PROTOCOL_VERSION=1；实测 dsh
# initialize 响应 protocolVersion=1）
ACP_PROTOCOL_VERSION = 1

CLIENT_NAME = "hsr-nous-acp-bridge"
CLIENT_VERSION = "0.1.0"


class AcpError(RuntimeError):
    """ACP 客户端错误基类。"""


class AcpProtocolError(AcpError):
    """协议错误：JSON-RPC error 响应、未知方法、帧损坏或形状不符。"""


class AcpConnectionError(AcpError):
    """连接错误：子进程退出、管道断开或客户端已关闭。"""


class AcpTimeoutError(AcpError):
    """等待响应超时。"""


def encode_frame(message: Mapping[str, Any]) -> bytes:
    """把一条 JSON-RPC 消息编码为一帧（单行 JSON + ``\\n``）。"""
    return (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def decode_frame(line: str | bytes) -> dict[str, Any]:
    """解码一帧；帧损坏或不是 JSON-RPC 消息时抛 ``AcpProtocolError``。"""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    line = line.strip()
    if not line:
        raise AcpProtocolError("ACP 对端发送了空帧")
    try:
        message = json.loads(line)
    except json.JSONDecodeError as error:
        raise AcpProtocolError(f"ACP 对端发送了损坏的 JSON 帧: {line[:200]!r}") from error
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise AcpProtocolError(f"ACP 对端发送了非 JSON-RPC 2.0 帧: {line[:200]!r}")
    return message


def _error_text(error: Mapping[str, Any]) -> str:
    """把 JSON-RPC error 对象转成中文报错文本。"""
    code = error.get("code")
    message = error.get("message")
    data = error.get("data")
    text = f"ACP 协议错误（code={code}）: {message}"
    if data is not None:
        text += f"；数据: {json.dumps(data, ensure_ascii=False)[:300]}"
    return text


class AcpClient:
    """一个 ``dsh --profile acp`` 子进程上的多会话 ACP v1 客户端。

    用法::

        client = AcpClient.dsh(root=research_root_path)
        await client.start()                      # spawn + 读循环 + initialize 握手
        sid = await client.new_session(cwd)       # session/new
        async for update in client.updates(sid):  # session/update 通知流
            ...
        result = await client.prompt(sid, "你好")  # session/prompt（在途持续泵 update）
        await client.aclose()                     # 关连接 + 收尸进程组

    线程模型：单个读循环任务按行读帧——响应按 ``id`` 配对到 pending future，
    通知按 ``params.sessionId`` 扇入该会话的订阅队列；因此 ``prompt()`` 在途
    期间 ``updates()`` 照常出流（ACP settlement 语义要求的"持续泵"）。
    """

    def __init__(
        self,
        *,
        argv: list[str],
        env: Mapping[str, str],
        cwd: Path | str,
        spawn: Callable[[], Awaitable["_Transport"]] | None = None,
    ) -> None:
        """一般用 ``AcpClient.dsh(...)`` 构造；``spawn`` 仅供测试注入进程内假对端。"""
        self._argv = argv
        self._env = dict(env)
        self._cwd = str(cwd)
        self._spawn = spawn or self._spawn_subprocess
        self._transport: _Transport | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any] | None]]] = {}
        self._closed = False
        # 读循环/关闭造成的致命错误（连接或协议级）：后续请求快速失败
        self._connection_error: AcpError | None = None
        self.server_info: dict[str, Any] | None = None
        # initialize 响应原文（agentInfo / agentCapabilities / authMethods）
        self.last_config_options: list[dict[str, Any]] = []
        # 最近一次 new/resume/set_config_option 响应里的配置选项状态

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------

    @classmethod
    def dsh(
        cls,
        *,
        root: Path | None = None,
        dsh_bin: str | Path | None = None,
        model_env: Mapping[str, str] | None = None,
        workspace: str = "workspace",
        spawn: Callable[[], Awaitable["_Transport"]] | None = None,
    ) -> AcpClient:
        """组装真 dsh --profile acp 客户端（叠加研究/ OpenAI 两补丁）。

        进程组装复用 ``dsh.py`` 的 ``_prepare_root`` / ``_environment`` /
        ``_executable``（隔离 HOME/DSH_HOME=研究根下、只读沙箱、telemetry off）。
        会话工作目录默认是研究根下 ``workspace/`` 并自动创建。
        """
        research = _prepare_root(root)
        session_cwd = research / workspace
        session_cwd.mkdir(parents=True, exist_ok=True)
        profile_dir = Path(__file__).parent / "dsh_profile"
        argv = [
            _executable(dsh_bin),
            "--profile", "acp",
            "--patch", str(profile_dir / "research.cordis.yml"),
            "--patch", str(profile_dir / "openai.cordis.yml"),
        ]
        # cwd=源码仓库：与 interactive.py 一致，DSH 自行读取仓库根 .env 的
        # HSR_NOUS_LLM_AGENTS_*（_environment 不透传这些键，见 dsh.py）。
        return cls(
            argv=argv,
            env=_environment(research, model_env),
            cwd=repo_root(),
            spawn=spawn,
        )

    async def _spawn_subprocess(self) -> "_Transport":
        """spawn dsh 子进程（独立进程组，killpg 收尸语义与 dsh._stop 一致）。"""
        try:
            process = await asyncio.create_subprocess_exec(
                *self._argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,  # 诊断走 web 日志会污染 stdout 纯协议流约定之外的通道；原型期直接丢弃
                cwd=self._cwd,
                env=self._env,
                start_new_session=True,
            )
        except OSError as error:
            raise AcpConnectionError(f"无法启动 ACP 对端进程: {error}") from error
        assert process.stdin is not None and process.stdout is not None
        return _SubprocessTransport(process)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self, timeout_s: float = 30.0) -> None:
        """spawn 进程、起读循环、完成 initialize（+ 需要时的 authenticate）握手。"""
        if self._transport is not None:
            raise AcpError("ACP 客户端已启动")
        self._transport = await self._spawn()
        self._reader_task = asyncio.create_task(self._read_loop(), name="acp-reader")
        try:
            init = await self._request(
                "initialize",
                {
                    "protocolVersion": ACP_PROTOCOL_VERSION,
                    "clientCapabilities": {
                        "fs": {"readTextFile": False, "writeTextFile": False},
                        "terminal": False,
                    },
                    "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
                },
                timeout_s=timeout_s,
            )
        except AcpError:
            await self.aclose()
            raise
        version = init.get("protocolVersion")
        if version != ACP_PROTOCOL_VERSION:
            await self.aclose()
            raise AcpProtocolError(
                f"ACP 对端协议版本不兼容: 协商得 {version!r}，本客户端只支持 v{ACP_PROTOCOL_VERSION}"
            )
        self.server_info = init
        # dsh acp 的 authMethods 恒为空（无需认证）；非空时按协议用首个
        # methodId 认证，兼容其他 ACP 服务端。
        auth_methods = init.get("authMethods") or []
        if auth_methods:
            await self._request(
                "authenticate", {"methodId": auth_methods[0].get("id")}, timeout_s=timeout_s
            )

    async def aclose(self) -> None:
        """关连接并收尸子进程（幂等）。SIGTERM → 5s 后 SIGKILL。"""
        if self._closed:
            return
        self._closed = True
        error = AcpConnectionError("ACP 客户端已关闭")
        self._fail_all(error)
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None
        transport, self._transport = self._transport, None
        if transport is not None:
            await transport.aclose()

    # ------------------------------------------------------------------
    # 会话操作（形状以实测 dsh acp 响应为准）
    # ------------------------------------------------------------------

    async def new_session(self, cwd: Path | str, timeout_s: float = 60.0) -> str:
        """``session/new`` → 新会话 id（响应里的 configOptions 见 ``last_config_options``）。"""
        result = await self._request(
            "session/new", {"cwd": str(cwd), "mcpServers": []}, timeout_s=timeout_s
        )
        self.last_config_options = result.get("configOptions") or []
        session_id = result.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise AcpProtocolError(f"ACP 对端 session/new 响应缺少 sessionId: {result!r}")
        return session_id

    async def list_sessions(self, timeout_s: float = 30.0) -> list[dict[str, Any]]:
        """``session/list`` → 已关闭（可恢复）会话摘要列表；活动会话不出现。"""
        result = await self._request("session/list", {}, timeout_s=timeout_s)
        sessions = result.get("sessions")
        if not isinstance(sessions, list):
            raise AcpProtocolError(f"ACP 对端 session/list 响应形状不符: {result!r}")
        return sessions

    async def resume_session(self, session_id: str, cwd: Path | str, timeout_s: float = 60.0) -> dict[str, Any]:
        """``session/resume`` → 恢复已关闭会话（不重放历史）。"""
        result = await self._request(
            "session/resume",
            {"sessionId": session_id, "cwd": str(cwd)},
            timeout_s=timeout_s,
        )
        self.last_config_options = result.get("configOptions") or []
        return result

    async def close_session(self, session_id: str, timeout_s: float = 60.0) -> None:
        """``session/close`` → 静息取消、排干 update、落盘持久状态。"""
        await self._request("session/close", {"sessionId": session_id}, timeout_s=timeout_s)

    async def set_config_option(
        self, session_id: str, config_id: str, value: Any, timeout_s: float = 30.0
    ) -> list[dict[str, Any]]:
        """``session/set_config_option`` → 完整配置选项状态（透传 select/boolean 值）。"""
        result = await self._request(
            "session/set_config_option",
            {"sessionId": session_id, "configId": config_id, "value": value},
            timeout_s=timeout_s,
        )
        options = result.get("configOptions")
        if not isinstance(options, list):
            raise AcpProtocolError(f"ACP 对端 set_config_option 响应形状不符: {result!r}")
        self.last_config_options = options
        return options

    async def prompt(self, session_id: str, text: str, timeout_s: float = 900.0) -> dict[str, Any]:
        """``session/prompt`` → ``{"stopReason": ...}``。

        prompt 在途期间读循环持续把 ``session/update`` 扇入订阅队列，
        调用方应并发消费 ``updates(session_id)`` 直到出现本地合成的
        ``prompt_closed`` 事件（见 chat_server）。
        """
        if not text.strip():
            raise ValueError("prompt 文本不能为空")
        return await self._request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": text}],
            },
            timeout_s=timeout_s,
        )

    async def cancel(self, session_id: str) -> None:
        """``session/cancel`` 通知（无响应）：取消在途 prompt 的会话活动。"""
        await self._notify("session/cancel", {"sessionId": session_id})

    # ------------------------------------------------------------------
    # update 订阅
    # ------------------------------------------------------------------

    def updates(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """订阅该会话的 ``session/update`` 通知流（async iterator）。

        每个调用注册一个独立队列，通知扇入全部订阅者；连接断开或
        ``aclose()`` 后以 ``None`` 哨兵结束迭代。事件是通知的 ``params.update``
        原样 dict（探针实测形状如 ``{"sessionUpdate": "agent_message_chunk",
        "messageId": ..., "content": {"type": "text", "text": ...}}``）。
        """

        async def _iterate() -> AsyncIterator[dict[str, Any]]:
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            self._subscribers.setdefault(session_id, set()).add(queue)
            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        return
                    yield item
            finally:
                self._subscribers.get(session_id, set()).discard(queue)

        return _iterate()

    # ------------------------------------------------------------------
    # 内部：帧收发与读循环
    # ------------------------------------------------------------------

    def _alloc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def _send(self, message: Mapping[str, Any]) -> None:
        if self._closed or self._transport is None:
            raise AcpConnectionError("ACP 客户端未连接或已关闭")
        async with self._write_lock:
            self._transport.write(encode_frame(message))
            await self._transport.drain()

    async def _request(
        self, method: str, params: Mapping[str, Any], timeout_s: float
    ) -> dict[str, Any]:
        """发请求并按 id 等响应；JSON-RPC error 映射为 ``AcpProtocolError``。"""
        if self._connection_error is not None:
            raise self._connection_error
        request_id = self._alloc_id()
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            message = await asyncio.wait_for(future, timeout=timeout_s)
        except (asyncio.TimeoutError, TimeoutError) as error:
            raise AcpTimeoutError(
                f"等待 ACP 对端 {method} 响应超时（{timeout_s:g}s）"
            ) from error
        finally:
            self._pending.pop(request_id, None)
        if "error" in message:
            raise AcpProtocolError(_error_text(message["error"]))
        result = message.get("result")
        if not isinstance(result, dict):
            raise AcpProtocolError(f"ACP 对端 {method} 响应缺少 result: {message!r}")
        return result

    async def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        """发通知（无 id，不等响应）。"""
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _read_loop(self) -> None:
        """单行读帧循环：响应配对 pending，通知扇入订阅，服务器→客户端请求自动应答。"""
        assert self._transport is not None
        try:
            while True:
                raw = await self._transport.readline()
                if not raw:
                    raise AcpConnectionError("ACP 对端关闭了连接（stdout EOF）")
                message = decode_frame(raw)
                self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except AcpError as error:
            self._fail_all(error)
        except Exception as error:  # noqa: BLE001 — 读循环不允许泄漏未捕获异常
            self._fail_all(AcpConnectionError(f"ACP 读循环异常: {error!r}"))

    def _dispatch(self, message: dict[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            future = self._pending.get(message["id"])
            if future is None or future.done():
                # 未知 id 的响应：协议层对不上账，按连接级错误处理
                self._fail_all(AcpProtocolError(f"ACP 对端响应 id 无匹配请求: {message!r}"))
                return
            future.set_result(message)
            return
        if "id" in message and "method" in message:
            # 服务器→客户端请求（如 session/request_permission）：读循环里
            #  fire-and-forget 自动应答，避免阻塞后续帧。
            asyncio.ensure_future(self._answer_server_request(message))
            return
        if "method" in message:
            self._handle_notification(message)
            return
        self._fail_all(AcpProtocolError(f"ACP 对端发送了无法识别的帧: {message!r}"))

    def _handle_notification(self, message: dict[str, Any]) -> None:
        params = message.get("params")
        if message.get("method") != "session/update" or not isinstance(params, dict):
            return  # 未知通知忽略（原型只消费 session/update）
        session_id = params.get("sessionId")
        update = params.get("update")
        if not isinstance(session_id, str) or not isinstance(update, dict):
            return
        for queue in self._subscribers.get(session_id, ()):
            queue.put_nowait(update)

    async def _answer_server_request(self, message: dict[str, Any]) -> None:
        """自动应答服务器→客户端请求：permission 选首个 allow 选项（工具白名单
        guard 在研究 profile 内仍是最终裁决，此处只是不误伤），其余回 method-not-found。"""
        method = message["method"]
        request_id = message["id"]
        if method == "session/request_permission":
            params = message.get("params") or {}
            options = params.get("options") or []
            option_id = None
            for option in options:
                if option.get("kind") in ("allow_once", "always_allow"):
                    option_id = option.get("optionId")
                    break
            if option_id is None and options:
                option_id = options[0].get("optionId")
            result: dict[str, Any] = {"outcome": {"outcome": "selected", "optionId": option_id}}
            if option_id is None:
                result = {"outcome": {"outcome": "cancelled"}}
        else:
            result = {"code": -32601, "message": f"客户端不支持的服务器请求: {method}"}
        frame: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "result": result}
        if method != "session/request_permission":
            frame = {"jsonrpc": "2.0", "id": request_id, "error": result}
        try:
            await self._send(frame)
        except AcpError:
            pass

    def _fail_all(self, error: AcpError) -> None:
        """把错误广播给全部 pending 请求与订阅者（订阅者收 None 哨兵）。

        首个致命错误记入 ``_connection_error`` 使后续请求快速失败；
        pending 与订阅者按原错误类型/哨兵收场。
        """
        if self._connection_error is None:
            self._connection_error = error
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()
        for subscribers in self._subscribers.values():
            for queue in subscribers:
                queue.put_nowait(None)
        self._subscribers.clear()


class _Transport:
    """AcpClient 传输抽象：真子进程或测试注入的进程内管道都实现这四个方法。"""

    def write(self, data: bytes) -> None:
        raise NotImplementedError

    async def drain(self) -> None:
        raise NotImplementedError

    async def readline(self) -> bytes:
        raise NotImplementedError

    async def aclose(self) -> None:
        raise NotImplementedError


class _SubprocessTransport(_Transport):
    """真 dsh 子进程传输（killpg 收尸语义与 dsh._stop 一致）。"""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        assert process.stdin is not None and process.stdout is not None
        self._stdin = process.stdin
        self._stdout = process.stdout

    def write(self, data: bytes) -> None:
        self._stdin.write(data)

    async def drain(self) -> None:
        await self._stdin.drain()

    async def readline(self) -> bytes:
        return await self._stdout.readline()

    async def aclose(self) -> None:
        try:
            self._stdin.close()
        except Exception:  # noqa: BLE001
            pass
        process = self._process
        if process.returncode is None:
            self._signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            self._signal(signal.SIGKILL)
            await process.wait()

    def _signal(self, sig: int) -> None:
        try:
            if os.name == "posix":
                os.killpg(self._process.pid, sig)
            elif sig == signal.SIGTERM:
                self._process.terminate()
            else:
                self._process.kill()
        except ProcessLookupError:
            pass
