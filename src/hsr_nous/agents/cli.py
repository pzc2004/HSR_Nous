"""Run one contract through DSH and return only host-verified research results."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
from typing import Sequence

from hsr_nous.agents.dsh import MODEL_ENV_KEYS, DshError, DshResult, run_headless
from hsr_nous.research_permissions import open_research_gateway
from hsr_nous.research_schema import (
    CandidateSet,
    ClaimSubmissionResult,
    InvestigationState,
    ResearchContract,
    canonical_json,
)


def _task(contract: ResearchContract) -> str:
    payload = canonical_json(contract)
    return (
        "Execute exactly one controlled research experiment. "
        "Call mcp__nous__submit_claim exactly once with contract_json set to the exact "
        "JSON string below, preserving every character. Do not change its builds, stage, "
        "arms, metric, protocol, budget, or seeds. Afterwards report only the returned "
        "status and report_id; never invent statistics. If the tool fails, report its "
        "structured error instead.\n\n"
        f"contract_json:\n{payload}"
    )


def _require_expected_submission(result: DshResult, contract: ResearchContract) -> None:
    calls = [
        event for event in result.events
        if event.get("type") == "tool_call"
        and event.get("tool") == "mcp__nous__submit_claim"
    ]
    expected_input = {"contract_json": canonical_json(contract)}
    if len(calls) != 1 or calls[0].get("input") != expected_input:
        raise DshError("DSH did not submit the expected contract exactly once")
    call_id = calls[0].get("callId")
    if not isinstance(call_id, str):
        raise DshError("DSH submission lacks a valid call identity")
    if not any(
        event.get("type") == "tool_result"
        and event.get("callId") == call_id
        and event.get("status") == "completed"
        for event in result.events
    ):
        raise DshError("DSH submission did not return a successful tool result")


def run_contract(
    contract: ResearchContract,
    *,
    root: Path | None = None,
    dsh_bin: str | Path | None = None,
    timeout_s: float = 900,
    model_env: Mapping[str, str] | None = None,
    use_openai: bool | None = None,
) -> tuple[DshResult, InvestigationState, ClaimSubmissionResult]:
    gateway = open_research_gateway(root)
    investigation = gateway.create_investigation(contract)
    if investigation.status == "completed":
        raise DshError("contract already completed; a cache read is not a new agent run")
    result = run_headless(
        _task(contract),
        root=root,
        dsh_bin=dsh_bin,
        timeout_s=timeout_s,
        model_env=model_env,
        use_openai=use_openai,
    )
    if result.returncode != 0:
        raise DshError(f"DSH failed with exit code {result.returncode}")
    investigation = gateway.read_investigation(investigation.investigation_id)
    if investigation.status != "completed" or investigation.trial_id is None:
        raise DshError("DSH did not complete the expected investigation")
    _require_expected_submission(result, contract)
    submission = gateway.submit_claim(trial_id=investigation.trial_id)
    if submission.status not in {"accepted", "inconclusive"} or submission.report is None:
        raise DshError(f"trusted report is unavailable: {submission.status}")
    return result, investigation, submission


def _candidate_task(candidate_set: CandidateSet) -> str:
    payload = canonical_json(candidate_set)
    return (
        "Execute exactly one bounded candidate-set experiment. "
        "Call mcp__nous__submit_candidate_set exactly once with candidate_set_json set to the "
        "exact JSON string below, preserving every character. Do not change the candidates, "
        "baseline, build, stage, metric, protocol, budget, or seeds. Afterwards report only "
        "the returned status and report_id; never invent statistics or a winner. If the tool "
        "fails, report its structured error instead.\n\n"
        f"candidate_set_json:\n{payload}"
    )


def _require_candidate_submission(result: DshResult, candidate_set: CandidateSet) -> str:
    calls = [
        event for event in result.events
        if event.get("type") == "tool_call"
        and event.get("tool") == "mcp__nous__submit_candidate_set"
    ]
    expected_input = {"candidate_set_json": canonical_json(candidate_set)}
    if len(calls) != 1 or calls[0].get("input") != expected_input:
        raise DshError("DSH did not submit the expected candidate set exactly once")
    call_id = calls[0].get("callId")
    if not isinstance(call_id, str):
        raise DshError("DSH candidate submission lacks a valid call identity")
    for event in result.events:
        if (event.get("type") != "tool_result" or event.get("callId") != call_id
                or event.get("status") != "completed"):
            continue
        text = event.get("result")
        if not isinstance(text, str):
            raise DshError("candidate report result is not text")
        set_match = re.search(r'"candidate_set_id"\s*:\s*"([0-9a-f]{64})"', text)
        report_match = re.search(r'"(?:candidate_report_id|report_id)"\s*:\s*"([0-9a-f]{64})"', text)
        if not set_match or set_match.group(1) != candidate_set.candidate_set_id:
            raise DshError("candidate set identity mismatch in tool result")
        if not report_match:
            raise DshError("candidate report result lacks report_id")
        return report_match.group(1)
    raise DshError("DSH candidate submission did not return a successful tool result")


def run_candidate_set(
    candidate_set: CandidateSet,
    *,
    root: Path | None = None,
    dsh_bin: str | Path | None = None,
    timeout_s: float = 900,
    model_env: Mapping[str, str] | None = None,
    use_openai: bool | None = None,
) -> tuple[DshResult, dict]:
    gateway = open_research_gateway(root)
    if gateway.candidate_set_report_exists(candidate_set.candidate_set_id):
        raise DshError("candidate set already has a report; a cache read is not a new agent run")
    result = run_headless(
        _candidate_task(candidate_set),
        root=root,
        dsh_bin=dsh_bin,
        timeout_s=timeout_s,
        model_env=model_env,
        use_openai=use_openai,
    )
    if result.returncode != 0:
        raise DshError(f"DSH failed with exit code {result.returncode}")
    report_id = _require_candidate_submission(result, candidate_set)
    report = gateway.validate_candidate_set_report(candidate_set, report_id)
    if report["status"] not in {"accepted", "inconclusive"}:
        raise DshError(f"trusted candidate report is unavailable: {report['status']}")
    return result, report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="ResearchContract or CandidateSet JSON file")
    parser.add_argument("--candidate-set", action="store_true", help="input is a CandidateSet")
    parser.add_argument("--research-root", type=Path)
    parser.add_argument("--dsh-bin", type=Path)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument(
        "--allow-model-env",
        action="store_true",
        help="explicitly pass the HSR_NOUS_LLM_AGENTS_* settings to DSH",
    )
    args = parser.parse_args(argv)
    model_env = {
        name: os.environ[name] for name in MODEL_ENV_KEYS if name in os.environ
    } if args.allow_model_env else None
    try:
        if args.candidate_set:
            candidate_set = CandidateSet.from_dict(
                json.loads(args.contract.read_text(encoding="utf-8"))
            )
            result, candidate_report = run_candidate_set(
                candidate_set,
                root=args.research_root,
                dsh_bin=args.dsh_bin,
                timeout_s=args.timeout,
                model_env=model_env,
            )
            output = {
                "session_id": result.session_id,
                "untrusted_agent_text": result.final_text,
                "candidate_set_report": candidate_report,
            }
        else:
            contract = ResearchContract.from_dict(
                json.loads(args.contract.read_text(encoding="utf-8"))
            )
            result, investigation, submission = run_contract(
                contract,
                root=args.research_root,
                dsh_bin=args.dsh_bin,
                timeout_s=args.timeout,
                model_env=model_env,
            )
            output = {
                "session_id": result.session_id,
                "untrusted_agent_text": result.final_text,
                "investigation": investigation.to_dict(),
                "submission": submission.to_dict(),
            }
    except (OSError, ValueError, DshError) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
