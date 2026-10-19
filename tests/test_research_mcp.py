from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

from hsr_nous.common import repo_root
from hsr_nous.research_schema import canonical_json
from tests._research_builders import make_demo_contract


def _server_parameters(root: Path) -> StdioServerParameters:
    env = get_default_environment()
    env.update({
        "HOME": str(root),
        "HSR_NOUS_RESEARCH_ROOT": str(root),
        "PYTHONPATH": str(repo_root() / "src"),
    })
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "hsr_nous.research_permissions.mcp"],
        env=env,
        cwd=root,
    )


def _payload(result):
    assert not result.isError, result.content
    payload = result.structuredContent
    assert payload is not None
    if set(payload) == {"result"}:
        return payload["result"]
    return payload


def test_mcp_exposes_only_research_gateway_tools(tmp_path):
    async def scenario():
        async with stdio_client(_server_parameters(tmp_path)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                assert {tool.name for tool in result.tools} == {
                    "submit_claim",
                    "read_investigation",
                    "read_report",
                    "resolve_evidence",
                    "submit_candidate_set",
                    "read_candidate_set_report",
                }

    anyio.run(scenario)


def test_mcp_real_execution_report_evidence_and_forgery_rejection(tmp_path):
    contract = make_demo_contract()

    async def scenario():
        async with stdio_client(_server_parameters(tmp_path)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                submitted = _payload(await session.call_tool(
                    "submit_claim", {"contract_json": canonical_json(contract)}
                ))
                assert submitted["status"] == "accepted"
                execution = submitted["execution"]
                assert execution["status"] == "completed"
                assert execution["completed_runs"] == execution["total_runs"]
                report = submitted["report"]
                trial_id = submitted["claim"]["trial_id"]

                state = _payload(await session.call_tool(
                    "read_investigation",
                    {"investigation_id": execution["investigation_id"]},
                ))
                assert state["status"] == "completed"
                assert state["contract"] == contract.to_dict()

                stored = _payload(await session.call_tool(
                    "read_report",
                    {"trial_id": trial_id, "report_id": report["report_id"]},
                ))
                assert stored == report

                drilldown = report["evidence"]["drilldown"][0]
                run = _payload(await session.call_tool(
                    "resolve_evidence", {"link": drilldown["run"]}
                ))
                assert run["kind"] == "run"
                assert run["evidence"]["run_id"] == drilldown["run"]["run_id"]
                event = _payload(await session.call_tool(
                    "resolve_evidence", {"link": drilldown["events"][0]}
                ))
                assert event["kind"] == "event"
                assert event["evidence"]["event_id"] == drilldown["events"][0]["event_id"]

                forged = deepcopy(submitted["claim"])
                forged["statistical_metadata"]["effect"] = 999999.0
                rejected = _payload(await session.call_tool(
                    "submit_claim", {"claim_json": canonical_json(forged)}
                ))
                assert rejected["status"] == "rejected"
                assert rejected["error"]["code"] == "claim_derivation_mismatch"

                invalid = _payload(await session.call_tool(
                    "submit_claim", {"contract": {"unknown": True}}
                ))
                assert invalid["status"] == "rejected"
                assert invalid["error"]["code"] == "invalid_submission"

    anyio.run(scenario)
