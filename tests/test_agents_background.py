from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer

from hsr_nous.agents import cli
from hsr_nous.agents.dsh import DshResult
from hsr_nous.research_permissions import open_research_gateway
from hsr_nous.research_schema import canonical_json
from tests._research_builders import make_candidate_proposals, make_candidate_space
from tests.test_agents_dsh_live import _MessagesHandler


def test_cli_background_proposals_return_task_without_waiting(tmp_path, monkeypatch, capsys):
    space = make_candidate_space(values=(600.0, 550.0, 500.0))
    proposals = make_candidate_proposals(space, values=(600.0, 550.0, 500.0))
    path = tmp_path / "space.json"
    path.write_text(canonical_json(space), encoding="utf-8")
    root = tmp_path / "research"

    def fake_run(task, *, root, dsh_bin, timeout_s, model_env, use_openai):
        task_view = open_research_gateway(root).start_candidate_proposals(space, proposals)
        return DshResult((
            {"type": "session", "sessionId": "background-session"},
            {
                "type": "tool_call",
                "callId": "background-call",
                "tool": "mcp__nous__start_candidate_proposals",
                "input": {
                    "candidate_space_json": canonical_json(space),
                    "candidate_proposals_json": canonical_json(proposals),
                },
            },
            {
                "type": "tool_result",
                "callId": "background-call",
                "status": "completed",
                "result": json.dumps({
                    "candidate_task_id": task_view["task_id"],
                    "candidate_set_id": task_view["candidate_set_id"],
                    "status": task_view["status"],
                }),
            },
            {"type": "final", "text": "background task accepted"},
        ), 0, "")

    monkeypatch.setattr(cli, "run_headless", fake_run)
    assert cli.main([
        str(path), "--candidate-proposals", "--background", "--research-root", str(root),
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert "candidate_set_report" not in output
    task = output["candidate_task"]
    assert task["total_runs"] == 192
    final = open_research_gateway(root)._candidate_tasks.wait_terminal(
        task["task_id"], timeout_s=120
    )
    assert final["status"] == "completed"


def test_real_dsh_background_proposals_and_completion_notification(tmp_path):
    space = make_candidate_space(values=(600.0, 550.0))
    proposals = make_candidate_proposals(space)
    tool_input = {
        "candidate_space_json": canonical_json(space),
        "candidate_proposals_json": canonical_json(proposals),
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MessagesHandler)
    server.contract = space
    server.tool_name = "mcp__nous__start_candidate_proposals"
    server.tool_input = tool_input
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = tmp_path / "research"
    try:
        result, task = cli.start_candidate_proposals(
            space,
            root=root,
            timeout_s=120,
            model_env={
                "HSR_NOUS_LLM_AGENTS_API_KEY": "test-placeholder",
                "HSR_NOUS_LLM_AGENTS_API_BASE": f"http://127.0.0.1:{server.server_port}",
            },
            use_openai=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.returncode == 0, result.stderr
    assert task["task_id"]
    gateway = open_research_gateway(root)
    final = gateway._candidate_tasks.wait_terminal(task["task_id"], timeout_s=120)
    assert final["status"] == "completed"
    report = gateway.validate_candidate_proposals_report(
        space, proposals, final["report_id"]
    )
    assert report["candidate_set_id"] == final["candidate_set_id"]
    calls = [event for event in result.events if event.get("type") == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["tool"] == "mcp__nous__start_candidate_proposals"
