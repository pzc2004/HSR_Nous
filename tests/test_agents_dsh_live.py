from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hsr_nous.agents import cli
from hsr_nous.research.permissions import open_research_gateway
from hsr_nous.research.schema import EvidenceLink, canonical_json
from tests._research_builders import make_demo_contract


def _contains_tool_result(value):
    if isinstance(value, dict):
        return value.get("type") == "tool_result" or any(
            _contains_tool_result(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_tool_result(item) for item in value)
    return False


def _sse(events):
    return "".join(
        f"event: {event}\ndata: {json.dumps(data)}\n\n" for event, data in events
    ).encode()


def _message_start(model, message_id):
    return "message_start", {
        "type": "message_start",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 1},
        },
    }


def _tool_response(
    model, contract, *, tool_name="mcp__nous__submit_claim", input_key="contract_json",
    tool_input=None,
):
    if tool_input is None:
        tool_input = {input_key: canonical_json(contract)}
    return _sse([
        _message_start(model, "msg_tool"),
        ("content_block_start", {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_research",
                "name": tool_name,
                "input": {},
            },
        }),
        ("content_block_delta", {
            "type": "content_block_delta",
            "index": 0,
            "delta": {
                "type": "input_json_delta",
                "partial_json": json.dumps(tool_input),
            },
        }),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 20},
        }),
        ("message_stop", {"type": "message_stop"}),
    ])


def _text_response(model):
    return _sse([
        _message_start(model, "msg_final"),
        ("content_block_start", {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        }),
        ("content_block_delta", {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Use the host-verified report."},
        }),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 10},
        }),
        ("message_stop", {"type": "message_stop"}),
    ])


class _MessagesHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        if self.path != "/v1/messages":
            self.send_error(404)
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(payload)
        if self.headers.get("x-api-key") != "test-placeholder":
            self.send_error(401)
            return
        if _contains_tool_result(payload["messages"]):
            body = _text_response(payload["model"])
        else:
            body = _tool_response(
                payload["model"],
                self.server.contract,
                tool_name=getattr(self.server, "tool_name", "mcp__nous__submit_claim"),
                input_key=getattr(self.server, "input_key", "contract_json"),
                tool_input=getattr(self.server, "tool_input", None),
            )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_real_dsh_mcp_and_simulator_with_isolated_model_gateway(tmp_path):
    contract = make_demo_contract()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MessagesHandler)
    server.contract = contract
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = tmp_path / "research"
    try:
        result, investigation, submission = cli.run_contract(
            contract,
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
    assert investigation.status == "completed"
    assert submission.status == "accepted"
    assert result.final_text == "Use the host-verified report."
    calls = [event for event in result.events if event.get("type") == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["tool"] == "mcp__nous__submit_claim"
    assert calls[0]["input"] == {"contract_json": canonical_json(contract)}
    assert len(server.requests) == 2
    assert _contains_tool_result(server.requests[1]["messages"])

    report = submission.report
    link = report["evidence"]["drilldown"][0]["events"][0]
    resolved = open_research_gateway(root).resolve_evidence(
        EvidenceLink.from_dict(link)
    )
    assert resolved["kind"] == "event"
