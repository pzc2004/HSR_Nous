from __future__ import annotations

from dataclasses import replace
import json

import pytest

from hsr_nous.agents import cli
from hsr_nous.agents.dsh import DshError, DshResult
from hsr_nous.research_permissions import open_research_gateway
from hsr_nous.research_protocol import ProtocolValidationError
from hsr_nous.research_schema import canonical_json
from tests._research_builders import make_candidate_proposals, make_candidate_space


def _fake_result(space, proposals, report, *, status="completed"):
    return DshResult((
        {"type": "session", "sessionId": "proposal-session"},
        {
            "type": "tool_call",
            "callId": "proposal-call",
            "tool": "mcp__nous__submit_candidate_proposals",
            "input": {
                "candidate_space_json": canonical_json(space),
                "candidate_proposals_json": canonical_json(proposals),
            },
        },
        {
            "type": "tool_result",
            "callId": "proposal-call",
            "status": status,
            "result": json.dumps({
                "candidate_report_id": report["report_id"],
                "candidate_set_id": report["candidate_set_id"],
                "report_id": report["report_id"],
            }),
        },
        {"type": "final", "text": "untrusted: all proposals are optimal"},
    ), 0, "")


def test_cli_candidate_proposals_return_host_verified_report(tmp_path, monkeypatch, capsys):
    space = make_candidate_space(values=(600.0, 550.0))
    proposals = make_candidate_proposals(space, labels=("high", "low"))
    space_path = tmp_path / "candidate-space.json"
    space_path.write_text(canonical_json(space), encoding="utf-8")

    def fake_run(task, *, root, dsh_bin, timeout_s, model_env, use_openai):
        assert space.base_contract.question in task
        assert canonical_json(space) in task
        assert canonical_json(proposals) not in task
        report = open_research_gateway(root).submit_candidate_proposals(space, proposals)
        return _fake_result(space, proposals, report)

    monkeypatch.setattr(cli, "run_headless", fake_run)
    root = tmp_path / "research"
    assert cli.main([
        str(space_path), "--candidate-proposals", "--research-root", str(root),
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    report = output["candidate_set_report"]
    assert report["status"] == "accepted"
    assert report["selected"] == ["high"]
    assert len(report["candidates"]) == 2
    assert output["untrusted_agent_text"] == "untrusted: all proposals are optimal"


def test_candidate_proposals_reject_natural_language_only(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_headless", lambda *args, **kwargs: DshResult((
        {"type": "final", "text": "accepted without candidate execution"},
    ), 0, ""))
    with pytest.raises(DshError, match="exactly once"):
        cli.run_candidate_proposals(make_candidate_space(), root=tmp_path / "research")


def test_candidate_proposals_reject_tampered_space(tmp_path, monkeypatch):
    space = make_candidate_space()
    changed = replace(space, max_candidates=3)
    proposals = make_candidate_proposals(space)

    def fake_run(*args, **kwargs):
        return _fake_result(
            changed, proposals, {"candidate_set_id": "0" * 64, "report_id": "1" * 64}
        )

    monkeypatch.setattr(cli, "run_headless", fake_run)
    with pytest.raises(DshError, match="changed the expected candidate space"):
        cli.run_candidate_proposals(space, root=tmp_path / "research")


def test_candidate_proposals_reject_extra_submission():
    space = make_candidate_space()
    proposals = make_candidate_proposals(space)
    result = _fake_result(
        space, proposals, {"candidate_set_id": "0" * 64, "report_id": "1" * 64}
    )
    events = result.events + ({
        "type": "tool_call",
        "callId": "other-call",
        "tool": "mcp__nous__submit_claim",
        "input": {},
    },)
    with pytest.raises(DshError, match="without other submissions"):
        cli._require_candidate_proposal_submission(
            DshResult(events, 0, ""), space
        )


def test_candidate_proposals_reject_wrong_set_identity(tmp_path, monkeypatch):
    space = make_candidate_space(values=(600.0, 550.0))
    proposals = make_candidate_proposals(space)

    def fake_run(_task, *, root, **kwargs):
        report = open_research_gateway(root).submit_candidate_proposals(space, proposals)
        forged = {**report, "candidate_set_id": "0" * 64}
        return _fake_result(space, proposals, forged)

    monkeypatch.setattr(cli, "run_headless", fake_run)
    with pytest.raises(DshError, match="candidate set identity mismatch"):
        cli.run_candidate_proposals(space, root=tmp_path / "research")


def test_candidate_proposals_reject_unsuccessful_tool_result():
    space = make_candidate_space()
    proposals = make_candidate_proposals(space)
    result = _fake_result(
        space,
        proposals,
        {"candidate_set_id": "0" * 64, "report_id": "1" * 64},
        status="error",
    )
    with pytest.raises(DshError, match="successful tool result"):
        cli._require_candidate_proposal_submission(result, space)


def test_candidate_proposals_reject_invalid_generated_candidates(tmp_path, monkeypatch):
    space = make_candidate_space()
    proposals = make_candidate_proposals(space, values=(600, 600.0))

    def fake_run(*args, **kwargs):
        return _fake_result(
            space, proposals, {"candidate_set_id": "0" * 64, "report_id": "1" * 64}
        )

    monkeypatch.setattr(cli, "run_headless", fake_run)
    with pytest.raises(ProtocolValidationError, match="duplicate proposal"):
        cli.run_candidate_proposals(space, root=tmp_path / "research")


def test_candidate_proposal_task_uses_backend_generated_labels():
    task = cli._candidate_proposal_task(make_candidate_space())
    assert "Omit label" in task


def test_candidate_proposal_rejection_preserves_structured_error():
    space = make_candidate_space()
    proposals = make_candidate_proposals(space)
    result = DshResult((
        {
            "type": "tool_call",
            "callId": "proposal-call",
            "tool": "mcp__nous__submit_candidate_proposals",
            "input": {
                "candidate_space_json": canonical_json(space),
                "candidate_proposals_json": canonical_json(proposals),
            },
        },
        {
            "type": "tool_result",
            "callId": "proposal-call",
            "status": "completed",
            "result": json.dumps({
                "status": "rejected",
                "error": {"code": "invalid_submission", "message": "invalid candidate label"},
            }),
        },
    ), 0, "")
    with pytest.raises(DshError, match="invalid candidate label"):
        cli._require_candidate_proposal_submission(result, space)
