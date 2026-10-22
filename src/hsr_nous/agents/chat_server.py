"""ACP 聊天桥：人在我们的页面聊天，DSH 退到幕后跑 ``--profile acp``。

架构::

    浏览器（研究台单页的聊天视图，workbench ``web_static/index.html``）
        ↔ POST 下发 / SSE 推送（EventSource）
        ↔ workbench:8001（唯一对外；``/chat/*`` 流式反代到回环上的本进程）
        ↔ 本进程（``python -m hsr_nous.agents.chat_server``，独立部署单元：
           ``create_app`` 持一个 AcpClient，由 workbench 代管生命周期）
        ↔ stdio 换行分隔 JSON-RPC
        ↔ dsh --profile acp（叠加研究/OpenAI 补丁，内含 nous MCP 网关）

workbench **不 import 本模块**——它是 spawn 出来的第二个本地服务（第一个先例是
sim.web 的本地服务与孤儿看护复用），workbench 只做回环反代（SSE 透传 + POST
透传），进程边界即模块边界。缺 ``HSR_NOUS_LLM_AGENTS_*`` 模型配置或 DSH 可执行
文件时，``main()`` 启动前置校验即打印中文错误并非零退出，workbench 依此降级为
无聊天。日常入口是研究台；``hsr-research-chat --serve`` / ``python -m
hsr_nous.agents.chat_server`` 仅开发调试。

推送选型注记（AUTORESEARCH_DESIGN §16 待决项的原型数据点）：项目未装
websockets 库而 sse-starlette 已在依赖里，SSE（EventSource）+ POST 下发
足以承载单向 update 流与取消语义；WS 升级留待多路复用/低延迟需求出现再说。

会话内事件流：AcpClient 的 ``session/update`` 通知原样 JSON 推给页面；
``session/prompt`` 结算后本地合成一条 ``prompt_closed`` 事件
（含 ``stopReason`` 或错误文本），页面据此恢复输入框。

会话列表语义（聊天视图左栏的数据源）：``GET /sessions`` 合并两侧——
活跃 = 本桥记账的未关闭会话（带首条用户消息摘要与最近上下文用量），
可恢复 = ACP ``session/list`` 的落盘会话（桥无其历史）；
``POST /sessions/{id}/resume`` 恢复后不重回放，页面标注「历史不回放」。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, Sequence

from fastapi import APIRouter, FastAPI, HTTPException, Request
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
# 会话列表摘要标题的字符上限（首条用户消息截断）
TITLE_LIMIT = 30


class CreateSessionRequest(BaseModel):
    cwd: Path | None = None
    prompt: str | None = None


class PromptRequest(BaseModel):
    text: str


def _page(base: str) -> str:
    """最小聊天原型页：消息流 + 工具调用可折叠渲染 + 输入 + 取消。

    ``base`` 为路由前缀（无前缀时 ""），页面 fetch/EventSource 路径全部基于它生成，
    保证挂在 ``/chat`` 等前缀下仍可用。仅供 ``create_app`` 独立模式（开发调试）
    使用；生产入口是研究台单页（workbench 反代）。
    """
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
const BASE = "__BASE__";
let sid = null, es = null, pendingText = "", toolNodes = {}, msgNode = null;
let thoughtDet = null, thoughtCount = 0;
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
    // 思考过程默认折叠成一张卡片（摘要行显示段数），展开才见全文——
    // 每轮一张，send() 里随 msgNode 一起重置
    if (!thoughtDet) {
      thoughtDet = document.createElement("details");
      thoughtDet.className = "tool";
      const sum = document.createElement("summary");
      thoughtDet.appendChild(sum);
      thoughtDet._sum = sum;
      thoughtCount = 0;
      stream.appendChild(thoughtDet);
    }
    thoughtCount += 1;
    thoughtDet._sum.textContent = "💭 思考过程（" + thoughtCount + " 段，点击展开）";
    thoughtDet.appendChild(el("thought", update.content && update.content.text || ""));
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
  const resp = await fetch(BASE + "/sessions", { method: "POST",
    headers: {"Content-Type": "application/json"}, body: "{}" });
  const data = await resp.json();
  sid = data.session_id;
  es = new EventSource(BASE + "/sessions/" + sid + "/events");
  es.addEventListener("update", (e) => render(JSON.parse(e.data)));
  setInFlight(false);
}
async function send() {
  const text = textEl.value.trim();
  if (!text || !sid) return;
  textEl.value = "";
  stream.appendChild(el("msg", "你：" + text));
  msgNode = null;
  thoughtDet = null;
  setInFlight(true);
  const resp = await fetch(BASE + "/sessions/" + sid + "/prompt", { method: "POST",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify({text}) });
  if (resp.status !== 202) {
    stream.appendChild(el("error", "下发失败：" + resp.status));
    setInFlight(false);
  }
}
sendBtn.onclick = send;
textEl.onkeydown = (e) => { if (e.key === "Enter") send(); };
cancelBtn.onclick = async () => {
  await fetch(BASE + "/sessions/" + sid + "/cancel", { method: "POST" });
};
createSession().catch((e) => { statusEl.textContent = "会话创建失败：" + e; });
</script>
</body>
</html>""".replace("__BASE__", base)


async def _pin_openai_gateway_model(client: AcpClient, session_id: str) -> None:
    """建/恢复会话后把 model 配置项钉到 openai-gateway 组（.env 端点）。

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


def _title_of(entry: dict[str, Any]) -> str | None:
    """会话列表摘要标题：首条用户消息截断；无消息（如恢复的会话）返回 None。"""
    first = entry.get("first_prompt")
    if not first:
        return None
    return first[:TITLE_LIMIT] + ("…" if len(first) > TITLE_LIMIT else "")


def create_chat_router(
    client: AcpClient, *, default_cwd: Path | None = None, prefix: str = "/"
) -> APIRouter:
    """造聊天路由组：独立 app 直接挂；workbench 场景由本进程的 app 对外、经反代访问。

    ``prefix`` 让整组端点可挂在子路径下（如 workbench 反代 ``/chat/*`` 到本进程
    根路径时无需前缀；开发调试想直接把本进程挂到 ``/chat`` 下时用 ``prefix="/chat"``）。
    ``client`` 由调用方持有但未启动——起停经 ``chat_lifespan`` 组合进宿主 app
    的 lifespan（一个 app 持一个 AcpClient = 一个 dsh 子进程，内含多会话）。
    """
    default_cwd = default_cwd or Path.cwd()
    hub: dict[str, set[asyncio.Queue[dict[str, Any] | None]]] = {}
    history: dict[str, deque[dict[str, Any]]] = {}
    pumps: dict[str, asyncio.Task[None]] = {}
    prompts: dict[str, asyncio.Task[None]] = {}
    known: set[str] = set()
    # 桥侧会话记账：首条用户消息（列表摘要标题）/ 最近上下文用量 / 创建时间
    meta: dict[str, dict[str, Any]] = {}

    def publish(session_id: str, event: dict[str, Any] | None) -> None:
        if event is not None:
            history.setdefault(session_id, deque(maxlen=HISTORY_LIMIT)).append(event)
            if event.get("sessionUpdate") == "usage_update":
                entry = meta.get(session_id)
                if entry is not None:
                    entry["usage"] = {"used": event.get("used"), "size": event.get("size")}
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

    def remember(session_id: str) -> None:
        known.add(session_id)
        meta[session_id] = {"created_at": time.time(), "first_prompt": None, "usage": None}

    router = APIRouter(prefix=prefix if prefix not in ("", "/") else "")

    @router.post("/sessions")
    async def create_session(body: CreateSessionRequest) -> dict[str, Any]:
        cwd = body.cwd or default_cwd
        try:
            session_id = await client.new_session(cwd)
        except AcpError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        remember(session_id)
        pump_updates(session_id)
        await _pin_openai_gateway_model(client, session_id)
        if body.prompt is not None and body.prompt.strip():
            meta[session_id]["first_prompt"] = body.prompt.strip()
            run_prompt(session_id, body.prompt)
        return {"session_id": session_id}

    @router.post("/sessions/{sid}/prompt", status_code=202)
    async def post_prompt(sid: str, body: PromptRequest) -> None:
        if sid not in known:
            raise HTTPException(status_code=404, detail="未知会话")
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="prompt 文本不能为空")
        if sid in prompts:
            raise HTTPException(status_code=409, detail="该会话已有在途 prompt")
        entry = meta.setdefault(
            sid, {"created_at": time.time(), "first_prompt": None, "usage": None}
        )
        if entry["first_prompt"] is None:
            entry["first_prompt"] = body.text.strip()
        run_prompt(sid, body.text)

    @router.post("/sessions/{sid}/cancel", status_code=202)
    async def post_cancel(sid: str) -> None:
        if sid not in known:
            raise HTTPException(status_code=404, detail="未知会话")
        try:
            await client.cancel(sid)
        except AcpError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/sessions/{sid}/resume")
    async def resume_session(sid: str) -> dict[str, Any]:
        """恢复 ACP 落盘会话：纳入活跃记账并起 update 泵；历史不回放。"""
        if sid in known:
            raise HTTPException(status_code=409, detail="会话已在活跃列表中")
        try:
            await client.resume_session(sid, default_cwd)
        except AcpError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        remember(sid)
        pump_updates(sid)
        await _pin_openai_gateway_model(client, sid)
        return {"session_id": sid}

    @router.get("/sessions")
    async def list_sessions() -> dict[str, Any]:
        """合并会话列表：活跃 = 桥记账（含摘要标题与最近用量），可恢复 = ACP session/list。"""
        try:
            persisted = await client.list_sessions()
        except AcpError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        sessions: list[dict[str, Any]] = []
        for sid in sorted(known, key=lambda s: -float(meta.get(s, {}).get("created_at") or 0)):
            entry = meta.get(sid, {})
            sessions.append({
                "session_id": sid,
                "status": "active",
                "title": _title_of(entry),
                "usage": entry.get("usage"),
                "created_at": entry.get("created_at"),
            })
        for item in persisted:
            sid = item.get("sessionId")
            if not isinstance(sid, str) or sid in known:
                continue  # 活跃优先；session/list 只列已落盘（可恢复）会话
            sessions.append({
                "session_id": sid,
                "status": "resumable",
                "title": None,
                "usage": None,
                "created_at": None,
            })
        return {"sessions": sessions}

    @router.get("/sessions/{sid}/events")
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

    return router


def chat_lifespan(client: AcpClient) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """宿主 app lifespan 片段：启动并收尸 ACP 客户端（与 workbench lifespan 组合）。

    ``aclose`` 会向全部订阅者扇入 ``None`` 哨兵、使在途 pending 快速失败，
    pump/prompt 后台任务随之自行收场，无需宿主再逐任务取消。
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        await client.start()
        try:
            yield
        finally:
            await client.aclose()

    return _lifespan


def create_app(
    client: AcpClient, *, default_cwd: Path | None = None, prefix: str = "/"
) -> FastAPI:
    """独立成 app：自带 lifespan 与内嵌聊天原型页。

    日常由 workbench spawn 本进程（回环随机端口）并经 ``/chat/*`` 反代访问；
    ``--serve`` / ``python -m hsr_nous.agents.chat_server`` 独立模式仅开发调试。
    ``GET /healthz`` 供 workbench 启动探活。
    """
    app = FastAPI(title="HSR_Nous ACP chat bridge", lifespan=chat_lifespan(client))
    app.include_router(create_chat_router(client, default_cwd=default_cwd, prefix=prefix))

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _page(prefix.rstrip("/"))

    return app


def main(argv: Sequence[str] | None = None) -> int:
    """聊天桥独立进程入口：前置校验（模型配置 + DSH）→ uvicorn 起 ``create_app``。

    缺 ``HSR_NOUS_LLM_AGENTS_*`` 三项或 DSH 可执行文件时打印中文错误并非零退出
    ——workbench 代管本进程时依此把聊天降级为未启用。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认回环）")
    parser.add_argument("--research-root", type=Path, help="研究根（默认 HSR_NOUS_RESEARCH_ROOT 或 ~/HSR_Nous）")
    parser.add_argument("--dsh-bin", type=Path, help="DSH 可执行文件（默认 external/dsh 或 PATH）")
    args = parser.parse_args(argv)

    import uvicorn

    from hsr_nous.agents.acp_client import AcpClient
    from hsr_nous.agents.dsh import MODEL_ENV_KEYS, _executable, _prepare_root
    from hsr_nous.common import load_repo_env, research_root

    load_repo_env()  # 仓库根 .env → 环境变量（不覆盖已有）；DSH 启动时也会自行读取
    missing = sorted(name for name in MODEL_ENV_KEYS if not os.environ.get(name))
    if missing:
        print(f"缺少模型配置 {missing}——先按 .env.example 填写 HSR_NOUS_LLM_AGENTS_* 三项", file=sys.stderr)
        return 1
    exe = _executable(args.dsh_bin)
    if not Path(exe).is_file() and shutil.which(exe) is None:
        print(f"找不到 DSH 可执行文件（{exe}）——先跑 scripts/setup_agent_env.sh", file=sys.stderr)
        return 1

    root = _prepare_root(args.research_root or research_root())
    client = AcpClient.dsh(root=root, dsh_bin=args.dsh_bin)
    app = create_app(client, default_cwd=root / "workspace")
    print(f"研究根: {root}", file=sys.stderr)
    print(
        f"ACP 聊天桥: http://{args.host}:{args.port}"
        "（研究台经 /chat 反代访问；独立模式仅开发调试，Ctrl-C 停止）",
        file=sys.stderr,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
