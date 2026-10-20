from __future__ import annotations

import anyio
from mcp import ClientSession
from mcp.client.stdio import stdio_client

from hsr_nous.research_schema import canonical_json
from tests._research_builders import make_candidate_proposals, make_candidate_space
from tests.test_research_mcp import _payload, _server_parameters


async def _wait_terminal(session, task_id):
    cursor = ""
    for _ in range(300):
        waited = _payload(await session.call_tool(
            "wait_candidate_task",
            {"task_id": task_id, "after_event_id": cursor, "timeout_s": 1},
        ))
        if waited["events"]:
            cursor = waited["events"][-1]["event_id"]
        if waited["task"]["status"] in {"completed", "failed", "cancelled"}:
            return waited
    raise AssertionError("candidate task did not finish")


def test_mcp_candidate_task_start_query_cancel_resume_and_notify(tmp_path):
    space = make_candidate_space(values=(600.0, 550.0, 500.0))
    proposals = make_candidate_proposals(space, values=(600.0, 550.0, 500.0))

    async def scenario():
        async with stdio_client(_server_parameters(tmp_path)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                started = _payload(await session.call_tool(
                    "start_candidate_proposals",
                    {
                        "candidate_space_json": canonical_json(space),
                        "candidate_proposals_json": canonical_json(proposals),
                    },
                ))
                task_id = started["candidate_task_id"]
                assert started["status"] in {"queued", "running", "cancel_requested"}
                queried = _payload(await session.call_tool(
                    "read_candidate_task", {"task_id": task_id}
                ))
                assert queried["task"]["total_runs"] == 192

                cancelled_request = _payload(await session.call_tool(
                    "cancel_candidate_task", {"task_id": task_id}
                ))
                assert cancelled_request["status"] in {"cancel_requested", "cancelled"}
                cancelled = await _wait_terminal(session, task_id)
                assert cancelled["task"]["status"] == "cancelled"
                assert cancelled["task"]["report_id"] is None

                resumed = _payload(await session.call_tool(
                    "resume_candidate_task", {"task_id": task_id}
                ))
                assert resumed["task"]["attempt"] == 2
                completed = await _wait_terminal(session, task_id)
                assert completed["task"]["status"] == "completed"
                assert completed["task"]["completed_runs"] == 192
                assert any(event["kind"] == "completed" for event in completed["events"])

                duplicate = _payload(await session.call_tool(
                    "start_candidate_proposals",
                    {
                        "candidate_space_json": canonical_json(space),
                        "candidate_proposals_json": canonical_json(proposals),
                    },
                ))
                assert duplicate["candidate_task_id"] == task_id
                assert duplicate["task"]["attempt"] == 2
                report = _payload(await session.call_tool(
                    "read_candidate_set_report",
                    {
                        "candidate_set_id": completed["task"]["candidate_set_id"],
                        "report_id": completed["task"]["report_id"],
                    },
                ))
                assert report["report_id"] == completed["task"]["report_id"]

    anyio.run(scenario)
