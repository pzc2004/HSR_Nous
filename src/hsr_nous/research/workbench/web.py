"""研究台 FastAPI app：研究数据只读呈现 + 可选 ACP 聊天桥回环反代（唯一前端单页）。

研究 API（``/api/*``）只读，契约见 ``research/schema/docs/12_workbench.md``。
``chat_proxy`` 传入聊天桥子进程（``agents/chat_server``，workbench 不 import 其
任何代码——进程边界即模块边界）的回环 base URL 时，挂载 ``/chat/*`` 通用反代：
GET 且 Accept 含 ``text/event-stream`` 时流式逐 chunk 透传（不缓冲、客户端断开
即停读上游），其余方法透传 body/status。子进程不可达时反代 503，页面按
「聊天桥未启用」降级标注。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import APIRouter, Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from hsr_nous.common import research_root
from hsr_nous.research.permissions import ArtifactError, ResearchGateway, open_research_gateway
from hsr_nous.research.schema import EvidenceLink, canonical_json

_STATIC = Path(__file__).parent / "web_static" / "index.html"

# 不透传的逐跳首部（回环反代最小集；content-length 由 httpx 按实际 body 重算）
_HOP_BY_HOP = frozenset({
    "host", "connection", "content-length", "transfer-encoding",
    "keep-alive", "upgrade", "te", "trailer",
})
# prompt 结算可能很久：非 SSE 路径整体超时放宽，连接超时保持短，让「子进程已死」
# 快速变 503。SSE 路径读超时 None（不掐 idle 长连）——连接生死由断开检测管理。
_PROXY_TIMEOUT = httpx.Timeout(600.0, connect=5.0)
_SSE_TIMEOUT = httpx.Timeout(None, connect=5.0)


def _chat_proxy_router(base_url: str) -> APIRouter:
    """``/chat/*`` 反代到回环聊天桥：SSE 流式透传，其余方法整包透传。"""

    def _forward_headers(request: Request) -> dict[str, str]:
        return {
            name: value
            for name, value in request.headers.items()
            if name.lower() not in _HOP_BY_HOP
        }

    router = APIRouter()

    @router.api_route(
        "/chat/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def chat_proxy(path: str, request: Request) -> Response:
        target = f"/{path}"
        wants_sse = (
            request.method == "GET"
            and "text/event-stream" in request.headers.get("accept", "")
        )
        client = httpx.AsyncClient(
            base_url=base_url, timeout=_SSE_TIMEOUT if wants_sse else _PROXY_TIMEOUT
        )
        if wants_sse:
            async def stream() -> AsyncIterator[bytes]:
                try:
                    async with client.stream(
                        "GET", target,
                        params=request.query_params,
                        headers=_forward_headers(request),
                    ) as upstream:
                        async for chunk in upstream.aiter_raw():
                            if await request.is_disconnected():
                                break
                            yield chunk
                except httpx.HTTPError:
                    # 桥不可达/中途死掉：流安静结束——页面 EventSource 自动重连，
                    # 连接恢复前 chatStatus 已显示「事件流断开（自动重连中）」
                    pass
                finally:
                    await client.aclose()

            return StreamingResponse(stream(), media_type="text/event-stream")

        try:
            upstream = await client.request(
                request.method,
                target,
                params=request.query_params,
                content=await request.body(),
                headers=_forward_headers(request),
            )
        except httpx.HTTPError:
            await client.aclose()
            return JSONResponse({"detail": "聊天桥未启用或已退出"}, status_code=503)
        await client.aclose()
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers={
                "content-type": upstream.headers.get("content-type", "application/json")
            },
        )

    return router


def create_app(
    root: Path | None = None,
    *,
    gateway: ResearchGateway | None = None,
    chat_proxy: str | None = None,
) -> FastAPI:
    """``chat_proxy`` = 聊天桥子进程回环 base URL（如 ``http://127.0.0.1:54321``）。

    由 workbench cli spawn 并探活后传入；测试可指向外部 stub。None 表示无聊天
    （不挂反代，页面标注未启用）。
    """
    gateway = gateway or open_research_gateway(root or research_root())
    app = FastAPI(title="HSR_Nous · 研究台")

    def _read(call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return call(*args, **kwargs)
        except (ArtifactError, TypeError, ValueError, KeyError, FileNotFoundError) as error:
            raise HTTPException(404, str(error)) from error

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC, headers={"Cache-Control": "no-store"})

    @app.get("/api/tasks")
    def tasks(limit: int = 50) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise HTTPException(400, "limit must be between 1 and 100")
        return _read(gateway.list_candidate_tasks, limit)

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str) -> dict[str, Any]:
        return _read(gateway.read_candidate_task, task_id)

    @app.get("/api/tasks/{task_id}/events")
    def events(task_id: str, after_event_id: str = "") -> dict[str, Any]:
        return _read(
            gateway.wait_candidate_task,
            task_id,
            after_event_id=after_event_id,
            timeout_s=0,
        )

    @app.get("/api/tasks/{task_id}/report")
    def candidate_report(task_id: str) -> dict[str, Any]:
        task_view = _read(gateway.read_candidate_task, task_id)
        if task_view["report_id"] is None:
            raise HTTPException(404, "candidate report is not ready")
        return _read(
            gateway.read_candidate_set_report,
            task_view["candidate_set_id"],
            task_view["report_id"],
        )

    @app.get("/api/trials/{trial_id}/reports/{report_id}")
    def trial_report(trial_id: str, report_id: str) -> dict[str, Any]:
        return _read(gateway.read_report, trial_id, report_id)

    @app.post("/api/evidence")
    def evidence(link: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            parsed = EvidenceLink.from_dict(link)
        except (TypeError, ValueError, KeyError) as error:
            raise HTTPException(400, str(error)) from error
        return json.loads(canonical_json(_read(gateway.resolve_evidence, parsed)))

    if chat_proxy is not None:
        app.include_router(_chat_proxy_router(chat_proxy))

    return app
