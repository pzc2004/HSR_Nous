from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from hsr_nous.agents import cli
from hsr_nous.research.schema import canonical_json
from tests._research_builders import make_candidate_set
from tests.test_agents_dsh_live import _MessagesHandler, _contains_tool_result


def test_real_dsh_candidate_set_execution_and_host_revalidation(tmp_path):
    candidate_set = make_candidate_set((600.0, 550.0), top_k=1)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MessagesHandler)
    server.contract = candidate_set
    server.tool_name = "mcp__nous__submit_candidate_set"
    server.input_key = "candidate_set_json"
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = tmp_path / "research"
    try:
        result, report = cli.run_candidate_set(
            candidate_set,
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
    assert report["status"] == "accepted"
    assert report["selected"] == ["candidate-0"]
    assert len(report["candidates"]) == 2
    calls = [event for event in result.events if event.get("type") == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["tool"] == "mcp__nous__submit_candidate_set"
    assert calls[0]["input"] == {"candidate_set_json": canonical_json(candidate_set)}
    assert len(server.requests) == 2
    assert _contains_tool_result(server.requests[1]["messages"])
