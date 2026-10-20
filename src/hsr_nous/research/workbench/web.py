"""Read-only FastAPI surface for the research workbench."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse

from hsr_nous.common import research_root
from hsr_nous.research.permissions import ArtifactError, ResearchGateway, open_research_gateway
from hsr_nous.research.schema import EvidenceLink, canonical_json

_STATIC = Path(__file__).parent / "web_static" / "index.html"


def create_app(
    root: Path | None = None,
    *,
    gateway: ResearchGateway | None = None,
) -> FastAPI:
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

    return app
