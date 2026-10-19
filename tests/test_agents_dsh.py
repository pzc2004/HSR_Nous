from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

from hsr_nous.agents import cli
from hsr_nous.agents.dsh import DshError, DshResult, DshTimeoutError, run_headless
from hsr_nous.common import repo_root
from hsr_nous.research_permissions import open_research_gateway
from hsr_nous.research_schema import canonical_json
from tests._research_builders import make_demo_contract


def _fake_dsh(root: Path, body: str) -> Path:
    path = root / "fake-dsh"
    path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body), encoding="utf-8")
    path.chmod(0o755)
    return path


def test_headless_uses_isolated_environment_and_json_transport(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-a-real-credential")
    fake = _fake_dsh(tmp_path, """
        import json, os, sys
        task = sys.stdin.read()
        record = {
            "argv": sys.argv[1:], "task": task, "cwd": os.getcwd(),
            "home": os.environ.get("HOME"), "dsh_home": os.environ.get("DSH_HOME"),
            "permission": os.environ.get("DSH_PERMISSION_MODE"),
            "telemetry": os.environ.get("DSH_TELEMETRY_DISABLED"),
            "tools_mode": os.environ.get("DSH_TOOLS_MODE"),
            "has_api_key": "DEEPSEEK_API_KEY" in os.environ,
        }
        with open(os.path.join(os.environ["HSR_NOUS_RESEARCH_ROOT"], "invocation.json"), "w") as stream:
            json.dump(record, stream)
        print(json.dumps({"type": "session", "sessionId": "isolated-session"}))
        print(json.dumps({"type": "final", "text": "untrusted text"}))
    """)
    root = tmp_path / "research"
    result = run_headless("task through stdin", root=root, dsh_bin=fake)
    record = json.loads((root / "invocation.json").read_text(encoding="utf-8"))
    assert result.session_id == "isolated-session"
    assert result.final_text == "untrusted text"
    assert result.returncode == 0
    assert record["argv"] == [
        "--profile", "headless", "--patch",
        str(repo_root() / "src" / "hsr_nous" / "agents" / "dsh_profile" / "research.cordis.yml"),
        "--json",
    ]
    assert record["task"] == "task through stdin"
    assert record["cwd"] == str(root)
    assert record["home"] == str(root / "home")
    assert record["dsh_home"] == str(root / "dsh-home")
    assert record["permission"] == "read-only"
    assert record["telemetry"] == "1"
    assert record["tools_mode"] == "native"
    assert not record["has_api_key"]


def test_headless_timeout_stops_process_group(tmp_path):
    fake = _fake_dsh(tmp_path, """
        import time
        time.sleep(30)
    """)
    with pytest.raises(DshTimeoutError):
        run_headless("timeout", root=tmp_path / "research", dsh_bin=fake, timeout_s=0.05)


def test_headless_rejects_malformed_output_and_preserves_failure_status(tmp_path):
    malformed = _fake_dsh(tmp_path, "print('not-json')")
    with pytest.raises(DshError, match="malformed JSON"):
        run_headless("bad output", root=tmp_path / "research", dsh_bin=malformed)

    failed = _fake_dsh(tmp_path, """
        import json, sys
        print(json.dumps({"type": "error", "message": "declared failure"}))
        sys.exit(1)
    """)
    result = run_headless("failure", root=tmp_path / "research", dsh_bin=failed)
    assert result.returncode == 1
    assert result.events[0]["type"] == "error"


def test_headless_rejects_repository_as_workspace(tmp_path):
    for root in (repo_root(), repo_root().parent):
        with pytest.raises(DshError, match="disjoint"):
            run_headless("unsafe", root=root, dsh_bin=tmp_path / "unused")


def test_dsh_policy_guard_allows_only_research_tools(tmp_path):
    node = shutil.which("node")
    assert node is not None
    plugin = repo_root() / "src" / "hsr_nous" / "agents" / "dsh_profile" / "research_policy.mjs"
    script = """
        import { pathToFileURL } from 'node:url'
        const plugin = await import(pathToFileURL(process.argv[1]))
        let guard
        plugin.apply({ tools: { guard(fn) { guard = fn } } })
        const names = [
          'mcp__nous__submit_claim', 'mcp__nous__read_investigation',
          'mcp__nous__read_report', 'mcp__nous__resolve_evidence',
          'bash', 'run_code', 'web_search', 'mcp__other__submit_claim',
        ]
        console.log(JSON.stringify(Object.fromEntries(
          names.map((name) => [name, guard({ name }) ?? null])
        )))
    """
    result = subprocess.run(
        [node, "--input-type=module", "--eval", script, str(plugin)],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)},
    )
    decisions = json.loads(result.stdout)
    for name in (
        "mcp__nous__submit_claim",
        "mcp__nous__read_investigation",
        "mcp__nous__read_report",
        "mcp__nous__resolve_evidence",
    ):
        assert decisions[name] is None
    for name in ("bash", "run_code", "web_search", "mcp__other__submit_claim"):
        assert "outside the research capability allowlist" in decisions[name]


def test_cli_returns_host_verified_report_not_agent_text(tmp_path, monkeypatch, capsys):
    contract = make_demo_contract()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract.to_dict()), encoding="utf-8")

    def fake_run(task, *, root, dsh_bin, timeout_s, model_env):
        submission = open_research_gateway(root).submit_claim(contract=contract)
        assert submission.status == "accepted"
        return DshResult((
            {"type": "session", "sessionId": "fake-session"},
            {
                "type": "tool_call",
                "callId": "fake-call",
                "tool": "mcp__nous__submit_claim",
                "input": {"contract_json": canonical_json(contract)},
            },
            {"type": "tool_result", "callId": "fake-call", "status": "completed"},
            {"type": "final", "text": "untrusted: effect is 999999"},
        ), 0, "")

    monkeypatch.setattr(cli, "run_headless", fake_run)
    root = tmp_path / "research"
    assert cli.main([str(contract_path), "--research-root", str(root)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["session_id"] == "fake-session"
    assert output["untrusted_agent_text"] == "untrusted: effect is 999999"
    assert output["investigation"]["status"] == "completed"
    assert output["submission"]["status"] == "accepted"
    assert output["submission"]["claim"]["statistical_metadata"]["effect"] != 999999


def test_cli_rejects_natural_language_only_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_headless", lambda *args, **kwargs: DshResult((
        {"type": "final", "text": "accepted without an experiment"},
    ), 0, ""))
    with pytest.raises(DshError, match="did not complete"):
        cli.run_contract(make_demo_contract(), root=tmp_path / "research")


def test_cli_rejects_wrong_or_unsuccessful_submission_receipt():
    contract = make_demo_contract()
    wrong_call = DshResult(({
        "type": "tool_call",
        "callId": "wrong",
        "tool": "mcp__nous__submit_claim",
        "input": {"contract_json": "{}"},
    },), 0, "")
    with pytest.raises(DshError, match="expected contract"):
        cli._require_expected_submission(wrong_call, contract)

    missing_result = DshResult(({
        "type": "tool_call",
        "callId": "missing",
        "tool": "mcp__nous__submit_claim",
        "input": {"contract_json": canonical_json(contract)},
    },), 0, "")
    with pytest.raises(DshError, match="successful tool result"):
        cli._require_expected_submission(missing_result, contract)
