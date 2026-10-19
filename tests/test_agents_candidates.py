from __future__ import annotations

import json

import pytest

from hsr_nous.agents import cli
from hsr_nous.agents.dsh import DshError, DshResult
from hsr_nous.research_permissions import open_research_gateway
from hsr_nous.research_schema import canonical_json
from tests._research_builders import make_candidate_set


def _fake_result(candidate_set, report, *, status="completed"):
    return DshResult((
        {"type": "session", "sessionId": "candidate-session"},
        {
            "type": "tool_call",
            "callId": "candidate-call",
            "tool": "mcp__nous__submit_candidate_set",
            "input": {"candidate_set_json": canonical_json(candidate_set)},
        },
        {
            "type": "tool_result",
            "callId": "candidate-call",
            "status": status,
            "result": json.dumps({
                "candidate_set_id": candidate_set.candidate_set_id,
                "report_id": report["report_id"],
            }),
        },
        {"type": "final", "text": "untrusted: every candidate is excellent"},
    ), 0, "")


def test_cli_candidate_set_returns_host_verified_report(tmp_path, monkeypatch, capsys):
    candidate_set = make_candidate_set((600.0, 550.0), top_k=1)
    contract_path = tmp_path / "candidate-set.json"
    contract_path.write_text(canonical_json(candidate_set), encoding="utf-8")

    def fake_run(task, *, root, dsh_bin, timeout_s, model_env, use_openai):
        report = open_research_gateway(root).submit_candidate_set(candidate_set)
        return _fake_result(candidate_set, report)

    monkeypatch.setattr(cli, "run_headless", fake_run)
    root = tmp_path / "research"
    assert cli.main([str(contract_path), "--candidate-set", "--research-root", str(root)]) == 0
    output = json.loads(capsys.readouterr().out)
    report = output["candidate_set_report"]
    assert report["status"] == "accepted"
    assert report["selected"] == ["candidate-0"]
    assert len(report["dev_ranking"]) == 2
    assert output["untrusted_agent_text"] == "untrusted: every candidate is excellent"
    assert report["candidates"][0]["dev"]["effect"] != 999999


def test_cli_candidate_set_rejects_natural_language_only(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_headless", lambda *args, **kwargs: DshResult((
        {"type": "final", "text": "accepted without candidate execution"},
    ), 0, ""))
    with pytest.raises(DshError, match="exactly once"):
        cli.run_candidate_set(make_candidate_set(), root=tmp_path / "research")


def test_cli_candidate_set_rejects_existing_report(tmp_path, monkeypatch):
    candidate_set = make_candidate_set()
    gateway = open_research_gateway(tmp_path / "research")
    gateway.submit_candidate_set(candidate_set)
    with pytest.raises(DshError, match="already has a report"):
        cli.run_candidate_set(candidate_set, root=tmp_path / "research")


def test_candidate_submission_rejects_unsuccessful_tool_result():
    candidate_set = make_candidate_set()
    result = _fake_result(candidate_set, {"report_id": "0" * 64}, status="error")
    with pytest.raises(DshError, match="successful tool result"):
        cli._require_candidate_submission(result, candidate_set)
