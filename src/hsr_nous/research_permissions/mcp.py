"""Stdio MCP transport for the permission-checked research gateway."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from hsr_nous.research_permissions import ResearchGateway, open_research_gateway
from hsr_nous.research_protocol import ProtocolValidationError
from hsr_nous.research_schema import (
    CandidateProposal,
    CandidateSet,
    CandidateSpace,
    Claim,
    EvidenceLink,
    ResearchContract,
    canonical_json,
)


def _invalid_input(error: Exception) -> dict[str, Any]:
    return {
        "status": "rejected",
        "error": {
            "code": "invalid_submission",
            "message": f"{type(error).__name__}: {error}",
            "fields": {"input": "failed strict schema validation"},
            "evidence": {},
        },
    }


def _task_response(task: dict[str, Any]) -> dict[str, Any]:
    return json.loads(canonical_json({
        "candidate_task_id": task["task_id"],
        "candidate_set_id": task["candidate_set_id"],
        "status": task["status"],
        "task": task,
    }))


def _wait_response(result: dict[str, Any]) -> dict[str, Any]:
    response = _task_response(result["task"])
    response["events"] = result["events"]
    return json.loads(canonical_json(response))


def build_server(gateway: ResearchGateway | None = None) -> FastMCP:
    gateway = gateway or open_research_gateway()
    server = FastMCP(
        "nous",
        instructions=(
            "Use submit_claim for simulator-backed claims. Never present natural-language "
            "text or caller-provided statistics as verified evidence. Read reports and "
            "resolve their evidence links through the provided tools."
        ),
    )

    @server.tool()
    def submit_claim(
        contract: dict[str, Any] | None = None,
        contract_json: str = "",
        trial_id: str | None = None,
        claim: dict[str, Any] | None = None,
        claim_json: str = "",
    ) -> dict[str, Any]:
        """Execute or revalidate evidence and return the independent claim result."""
        try:
            inputs = (contract, contract_json or None, trial_id, claim, claim_json or None)
            if sum(value is not None for value in inputs) != 1:
                raise ValueError("exactly one submission input is required")
            parsed_contract = ResearchContract.from_dict(
                json.loads(contract_json) if contract_json else contract
            ) if contract is not None or contract_json else None
            parsed_claim = Claim.from_dict(
                json.loads(claim_json) if claim_json else claim
            ) if claim is not None or claim_json else None
        except (TypeError, ValueError, KeyError) as error:
            return _invalid_input(error)
        return gateway.submit_claim(
            contract=parsed_contract,
            trial_id=trial_id,
            claim=parsed_claim,
        ).to_dict()

    @server.tool()
    def read_investigation(investigation_id: str) -> dict[str, Any]:
        """Read the persisted lifecycle state for one investigation."""
        return gateway.read_investigation(investigation_id).to_dict()

    @server.tool()
    def read_report(trial_id: str, report_id: str) -> dict[str, Any]:
        """Read and integrity-check one stored report."""
        return gateway.read_report(trial_id, report_id)

    @server.tool()
    def resolve_evidence(link: dict[str, Any]) -> dict[str, Any]:
        """Resolve a claim evidence link to its original run, event, or modifier."""
        try:
            parsed_link = EvidenceLink.from_dict(link)
        except (TypeError, ValueError, KeyError) as error:
            return _invalid_input(error)
        result = gateway.resolve_evidence(parsed_link)
        return json.loads(canonical_json(result))

    @server.tool()
    def submit_candidate_set(
        candidate_set: dict[str, Any] | None = None,
        candidate_set_json: str = "",
    ) -> dict[str, Any]:
        """Execute and independently validate a bounded candidate set."""
        try:
            if (candidate_set is None) == (not candidate_set_json):
                raise ValueError("exactly one candidate_set or candidate_set_json is required")
            parsed = CandidateSet.from_dict(
                json.loads(candidate_set_json) if candidate_set_json else candidate_set
            )
        except (TypeError, ValueError, KeyError) as error:
            return _invalid_input(error)
        result = gateway.submit_candidate_set(parsed)
        return json.loads(canonical_json({
            "candidate_report_id": result["report_id"],
            "candidate_set_id": result["candidate_set_id"],
            "report_id": result["report_id"],
            "status": result["status"],
            "report": result,
        }))

    @server.tool()
    def submit_candidate_proposals(
        candidate_space_json: str = "",
        candidate_proposals_json: str = "",
    ) -> dict[str, Any]:
        """Generate and execute a bounded candidate set from allowed proposals."""
        try:
            if not candidate_space_json or not candidate_proposals_json:
                raise ValueError("candidate_space_json and candidate_proposals_json are required")
            raw_proposals = json.loads(candidate_proposals_json)
            if not isinstance(raw_proposals, list):
                raise TypeError("candidate_proposals_json must contain an array")
            space = CandidateSpace.from_dict(json.loads(candidate_space_json))
            proposals = tuple(CandidateProposal.from_dict(item) for item in raw_proposals)
        except (TypeError, ValueError, KeyError) as error:
            return _invalid_input(error)
        try:
            result = gateway.submit_candidate_proposals(space, proposals)
        except ProtocolValidationError as error:
            return _invalid_input(error)
        return json.loads(canonical_json({
            "candidate_report_id": result["report_id"],
            "candidate_set_id": result["candidate_set_id"],
            "report_id": result["report_id"],
            "status": result["status"],
            "report": result,
        }))

    @server.tool()
    def start_candidate_set(
        candidate_set: dict[str, Any] | None = None,
        candidate_set_json: str = "",
    ) -> dict[str, Any]:
        """Start a detached candidate task and return its identity immediately."""
        try:
            if (candidate_set is None) == (not candidate_set_json):
                raise ValueError("exactly one candidate_set or candidate_set_json is required")
            parsed = CandidateSet.from_dict(
                json.loads(candidate_set_json) if candidate_set_json else candidate_set
            )
            task = gateway.start_candidate_set(parsed)
        except (TypeError, ValueError, KeyError) as error:
            return _invalid_input(error)
        return _task_response(task)

    @server.tool()
    def start_candidate_proposals(
        candidate_space_json: str = "",
        candidate_proposals_json: str = "",
    ) -> dict[str, Any]:
        """Start a detached candidate task from allowed proposals."""
        try:
            if not candidate_space_json or not candidate_proposals_json:
                raise ValueError("candidate_space_json and candidate_proposals_json are required")
            raw_proposals = json.loads(candidate_proposals_json)
            if not isinstance(raw_proposals, list):
                raise TypeError("candidate_proposals_json must contain an array")
            space = CandidateSpace.from_dict(json.loads(candidate_space_json))
            proposals = tuple(CandidateProposal.from_dict(item) for item in raw_proposals)
            task = gateway.start_candidate_proposals(space, proposals)
        except (TypeError, ValueError, KeyError) as error:
            return _invalid_input(error)
        return _task_response(task)

    @server.tool()
    def read_candidate_task(task_id: str) -> dict[str, Any]:
        """Read current progress and any completed candidate result references."""
        return _task_response(gateway.read_candidate_task(task_id))

    @server.tool()
    def wait_candidate_task(
        task_id: str,
        after_event_id: str = "",
        timeout_s: float = 30,
    ) -> dict[str, Any]:
        """Wait for durable task events without client-side polling."""
        try:
            result = gateway.wait_candidate_task(
                task_id, after_event_id=after_event_id, timeout_s=timeout_s
            )
        except (TypeError, ValueError) as error:
            return _invalid_input(error)
        return _wait_response(result)

    @server.tool()
    def cancel_candidate_task(task_id: str) -> dict[str, Any]:
        """Request cooperative cancellation at the next safe progress point."""
        return _task_response(gateway.cancel_candidate_task(task_id))

    @server.tool()
    def resume_candidate_task(task_id: str) -> dict[str, Any]:
        """Resume a cancelled or failed partial task without repeating finished work."""
        try:
            task = gateway.resume_candidate_task(task_id)
        except (TypeError, ValueError) as error:
            return _invalid_input(error)
        return _task_response(task)

    @server.tool()
    def read_candidate_set_report(candidate_set_id: str, report_id: str) -> dict[str, Any]:
        """Read and integrity-check one candidate-set report."""
        return json.loads(canonical_json(
            gateway.read_candidate_set_report(candidate_set_id, report_id)
        ))

    return server


def main() -> int:
    build_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
