from __future__ import annotations

import anyio
from mcp import ClientSession
from mcp.client.stdio import stdio_client

from hsr_nous.research.schema import canonical_json
from tests._research_builders import make_candidate_set
from tests.test_research_mcp import _payload, _server_parameters


def test_mcp_candidate_set_execution_and_report_read(tmp_path):
    plan = make_candidate_set((600.0, 550.0), top_k=1)

    async def scenario():
        async with stdio_client(_server_parameters(tmp_path)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name for tool in (await session.list_tools()).tools}
                assert {"submit_candidate_set", "read_candidate_set_report"} <= tools

                submitted = _payload(await session.call_tool(
                    "submit_candidate_set", {"candidate_set_json": canonical_json(plan)}
                ))
                assert submitted["status"] == "accepted"
                assert submitted["candidate_set_id"] == plan.candidate_set_id
                assert submitted["report"]["selected"] == ["candidate-0"]
                assert len(submitted["report"]["candidates"]) == 2
                report_id = submitted["candidate_report_id"]
                assert submitted["report_id"] == report_id

                stored = _payload(await session.call_tool(
                    "read_candidate_set_report",
                    {"candidate_set_id": plan.candidate_set_id, "report_id": report_id},
                ))
                assert stored["report_id"] == report_id
                assert stored["candidate_set_id"] == plan.candidate_set_id

                repeated = _payload(await session.call_tool(
                    "submit_candidate_set", {"candidate_set": plan.to_dict()}
                ))
                assert repeated["report_id"] == report_id

                invalid = _payload(await session.call_tool(
                    "submit_candidate_set", {"candidate_set": {"question": "x", "candidates": []}}
                ))
                assert invalid["status"] == "rejected"
                assert invalid["error"]["code"] == "invalid_submission"

    anyio.run(scenario)
