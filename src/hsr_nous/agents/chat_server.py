"""ACP 聊天桥：人在我们的页面聊天，DSH 退到幕后跑 ``--profile acp``。

架构::

    浏览器（vanilla JS 原型页）
        ↔ POST 下发 / SSE 推送（EventSource）
        ↔ 本 FastAPI app（一个 app 持一个 AcpClient）
        ↔ stdio 换行分隔 JSON-RPC
        ↔ dsh --profile acp（叠加研究/OpenAI 补丁，内含 nous MCP 网关）

推送选型注记（AUTORESEARCH_DESIGN §16 待决项的原型数据点）：项目未装
websockets 库而 sse-starlette 已在依赖里，SSE（EventSource）+ POST 下发
足以承载单向 update 流与取消语义；WS 升级留待多路复用/低延迟需求出现再说。

会话内事件流：AcpClient 的 ``session/update`` 通知原样 JSON 推给页面；
``session/prompt`` 结算后 app 本地合成一条 ``prompt_closed`` 事件
（含 ``stopReason`` 或错误文本），页面据此恢复输入框。
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from hsr_nous.agents.acp_client import AcpClient, AcpError

# prompt 结算后推给页面的本地事件名——不是 ACP 协议字段，页面据此关"在途"态
UPDATE_EVENT = "update"
CLOSED_EVENT = "prompt_closed"
# 每会话事件环形历史：SSE 晚订阅（页面刷新/POST /sessions 带首条 prompt 后
# 才连 events）时重放近期事件，原型级可靠度
HISTORY_LIMIT = 200


class CreateSessionRequest(BaseModel):
    cwd: Path | None = None
    prompt: str | None = None


class PromptRequest(BaseModel):
    text: str


def _page() -> str:
    """最小聊天原型页：消息流 + 工具调用可折叠渲染 + 输入 + 取消。"""
    return """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>HSR_Nous 研究聊天（ACP 桥原型）</title>
<style>
 body { font-family: system-ui, sans-serif; max-width: 52rem; margin: 1rem auto; padding: 0 1rem; }
 #stream { border: 1px solid #ccc; border-radius: .5rem; padding: .75rem; min-height: 20rem;
          max-height: 60vh; overflow-y: auto; white-space: pre-wrap; }
 .msg { margin: .4rem 0; }
 .thought { color: #888; font-style: italic; }
 .tool { margin: .3rem 0 .3rem 1rem; }
 .tool summary { cursor: pointer; color: #475; }
 .meta { color: #999; font-size: .8rem; }
 .error { color: #b00; }
 #composer { display: flex; gap: .5rem; margin-top: .75rem; }
 #text { flex: 1; padding: .4rem; }
 button { padding: .4rem .9rem; }
</style>
</head>
<body>
<h2>研究聊天 · ACP 桥原型</h2>
<div id="stream"></div>
<div id="composer">
  <input id="text" placeholder="输入消息…" autofocus>
  <button id="send">发送</button>
  <button id="cancel" disabled>取消</button>
</div>
<p class="meta">信任边界与 stock web 一致：仅 mcp__nous__* 白名单工具；Agent 文本不可信。
<div class="meta" id="status">初始化…</div></p>
<script>
let sid = null, es = null, pendingText = "", toolNodes = {}, msgNode = null;
const stream = document.getElementById("stream");
const statusEl = document.getElementById("status");
const textEl = document.getElementById("text");
const sendBtn = document.getElementById("send");
const cancelBtn = document.getElementById("cancel");

function el(cls, text) {
  const d = document.createElement("div");
  d.className = cls;
  if (text !== undefined) d.textContent = text;
  return d;
}
function setInFlight(on) {
  sendBtn.disabled = on; cancelBtn.disabled = !on; textEl.disabled = on;
  statusEl.textContent = on ? "Agent 运行中…" : "就绪（会话 " + sid + "）";
}
function render(update) {
  const kind = update.sessionUpdate;
  if (kind === "agent_message_chunk") {
    if (!msgNode) { msgNode = el("msg"); stream.appendChild(msgNode); }
    msgNode.textContent += update.content && update.content.text || "";
    stream.scrollTop = stream.scrollHeight;
  } else if (kind === "agent_thought_chunk") {
    stream.appendChild(el("thought", update.content && update.content.text || ""));
  } else if (kind === "tool_call") {
    const det = document.createElement("details");
    det.className = "tool";
    const title = (update.title || update.toolCallId || "tool") +
      (update.name ? " · " + update.name : "");
    const sum = document.createElement("summary");
    sum.textContent = "⚙ " + title + " [" + (update.status || "?") + "]";
    det.appendChild(sum);
    det.appendChild(el("meta", JSON.stringify(update.rawInput !== undefined ? update.rawInput : {})));
    stream.appendChild(det);
    toolNodes[update.toolCallId] = { det, sum, base: title };
  } else if (kind === "tool_call_update") {
    const t = toolNodes[update.toolCallId];
    if (t) {
      t.sum.textContent = "⚙ " + t.base + " [" + (update.status || "?") + "]";
      if (update.content) t.det.appendChild(el("meta", JSON.stringify(update.content).slice(0, 2000)));
    }
  } else if (kind === "usage_update") {
    statusEl.textContent = "Agent 运行中… 上下文 " + update.used + "/" + update.size;
  } else if (kind === "prompt_closed") {
    if (update.error) stream.appendChild(el("error", "错误：" + update.error));
    else stream.appendChild(el("meta", "— 本轮结束（" + (update.stopReason || "?") + "）—"));
    setInFlight(false);
  }
  stream.scrollTop = stream.scrollHeight;
}
async function createSession() {
  const resp = await fetch("/sessions", { method: "POST",
    headers: {"Content-Type": "application/json"}, body: "{}" });
  const data = await resp.json();
  sid = data.session_id;
  es = new EventSource("/sessions/" + sid + "/events");
  es.addEventListener("update", (e) => render(JSON.parse(e.data)));
  setInFlight(false);
}
async function send() {
  const text = textEl.value.trim();
  if (!text || !sid) return;
  textEl.value = "";
  stream.appendChild(el("msg", "你：" + text));
  msgNode = null;
  setInFlight(true);
  const resp = await fetch("/sessions/" + sid + "/prompt", { method: "POST",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify({text}) });
  if (resp.status !== 202) {
    stream.appendChild(el("error", "下发失败：" + resp.status));
    setInFlight(false);
  }
}
sendBtn.onclick = send;
textEl.onkeydown = (e) => { if (e.key === "Enter") send(); };
cancelBtn.onclick = async () => {
  await fetch("/sessions/" + sid + "/cancel", { method: "POST" });
};
createSession().catch((e) => { statusEl.textContent = "会话创建失败：" + e; });
</script>
</body>
</html>"""


async def _pin_openai_gateway_model(client: AcpClient, session_id: str) -> None:
    """建会话后把 model 配置项钉到 openai-gateway 组（.env 端点）。

    探针实证：dsh acp 会话的 model 默认值是目录首个路由（deepseek-official），
    ``agent-default-model`` 补丁不决定 ACP 配置项初值——须显式
    ``session/set_config_option`` 选中 ``["openai-gateway", <model>]``。
    须在首条 prompt 准入前完成（prompt 在准入时钉住路由）。
    """
    for option in client.last_config_options:
        if option.get("id") != "model" or option.get("type") != "select":
            continue
        for group in option.get("options") or []:
            choices = group.get("options") or []
            if group.get("group") == "openai-gateway" and choices:
                await client.set_config_option(session_id, "model", choices[0]["value"])
                return


def create_app(client: AcpClient, *, default_cwd: Path | None = None) -> FastAPI:
    """造聊天桥 app。``client`` 未启动——lifespan 里 start/aclose。"""
    default_cwd = default_cwd or Path.cwd()
    hub: dict[str, set[asyncio.Queue[dict[str, Any] | None]]] = {}
    history: dict[str, deque[dict[str, Any]]] = {}
    pumps: dict[str, asyncio.Task[None]] = {}
    prompts: dict[str, asyncio.Task[None]] = {}
    known: set[str] = set()

    def publish(session_id: str, event: dict[str, Any] | None) -> None:
        if event is not None:
            history.setdefault(session_id, deque(maxlen=HISTORY_LIMIT)).append(event)
        for queue in hub.get(session_id, ()):
            queue.put_nowait(event)

    def pump_updates(session_id: str) -> None:
        async def _run() -> None:
            try:
                async for update in client.updates(session_id):
                    publish(session_id, update)
            except AcpError:
                publish(session_id, None)

        pumps[session_id] = asyncio.create_task(_run(), name=f"acp-pump-{session_id}")

    def run_prompt(session_id: str, text: str) -> None:
        async def _run() -> None:
            try:
                result = await client.prompt(session_id, text)
                publish(session_id, {
                    "sessionUpdate": CLOSED_EVENT,
                    "stopReason": result.get("stopReason"),
                })
            except AcpError as error:
                publish(session_id, {
                    "sessionUpdate": CLOSED_EVENT,
                    "stopReason": "error",
                    "error": str(error),
                })
            finally:
                prompts.pop(session_id, None)

        prompts[session_id] = asyncio.create_task(_run(), name=f"acp-prompt-{session_id}")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await client.start()
        try:
            yield
        finally:
            for task in list(prompts.values()) + list(pumps.values()):
                task.cancel()
            await client.aclose()

    app = FastAPI(title="HSR_Nous ACP chat bridge", lifespan=lifespan)

    @app.post("/sessions")
    async def create_session(body: CreateSessionRequest) -> dict[str, Any]:
        cwd = body.cwd or default_cwd
        try:
            session_id = await client.new_session(cwd)
        except AcpError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        known.add(session_id)
        pump_updates(session_id)
        await _pin_openai_gateway_model(client, session_id)
        if body.prompt is not None and body.prompt.strip():
            run_prompt(session_id, body.prompt)
        return {"session_id": session_id}

    @app.post("/sessions/{sid}/prompt", status_code=202)
    async def post_prompt(sid: str, body: PromptRequest) -> None:
        if sid not in known:
            raise HTTPException(status_code=404, detail="未知会话")
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="prompt 文本不能为空")
        if sid in prompts:
            raise HTTPException(status_code=409, detail="该会话已有在途 prompt")
        run_prompt(sid, body.text)

    @app.post("/sessions/{sid}/cancel", status_code=202)
    async def post_cancel(sid: str) -> None:
        if sid not in known:
            raise HTTPException(status_code=404, detail="未知会话")
        try:
            await client.cancel(sid)
        except AcpError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/sessions")
    async def list_sessions() -> dict[str, Any]:
        try:
            persisted = await client.list_sessions()
        except AcpError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {
            "sessions": persisted,
            # session/list 只列已关闭会话；本桥把建过且未关闭的也报出来
            "active": sorted(known - {s.get("sessionId") for s in persisted}),
        }

    @app.get("/sessions/{sid}/events")
    async def events(sid: str, request: Request) -> EventSourceResponse:
        if sid not in known:
            raise HTTPException(status_code=404, detail="未知会话")

        async def stream() -> AsyncIterator[dict[str, Any]]:
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            hub.setdefault(sid, set()).add(queue)
            try:
                # 先重放近期事件（晚订阅不丢上下文），再转实时推送
                for item in list(history.get(sid, ())):
                    if await request.is_disconnected():
                        return
                    yield {"event": UPDATE_EVENT, "data": json.dumps(item, ensure_ascii=False)}
                while True:
                    if await request.is_disconnected():
                        break
                    item = await queue.get()
                    if item is None:
                        break
                    yield {"event": UPDATE_EVENT, "data": json.dumps(item, ensure_ascii=False)}
            finally:
                hub.get(sid, set()).discard(queue)

        return EventSourceResponse(stream())

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _page()

    return app
