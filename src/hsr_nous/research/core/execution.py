"""Minimal single-process investigation and execution lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from hsr_nous.research.core.artifacts import (
    ArtifactIntegrityError,
    ArtifactStore,
    make_execution_id,
    make_investigation_id,
    make_trial_id,
)
from hsr_nous.research.core.claims import ClaimValidator
from hsr_nous.research.core.fingerprint import collect_research_fingerprint
from hsr_nous.research.core.report import ReportComposer
from hsr_nous.research.core.runner import RunCancelledError, TrialRunner
from hsr_nous.research.protocol import resolve_protocol
from hsr_nous.research.schema import (
    ExecutionRecord,
    InvestigationState,
    ResearchContract,
    content_hash,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _duration_ms(started_at: str, finished_at: str) -> int:
    started = datetime.fromisoformat(started_at)
    finished = datetime.fromisoformat(finished_at)
    return max(0, int((finished - started).total_seconds() * 1000))


class ExecutionManager:
    def __init__(self, store: ArtifactStore, runner: TrialRunner | None = None) -> None:
        self.store = store
        self.runner = runner or TrialRunner(store)
        self.validator = ClaimValidator(store)
        self.composer = ReportComposer(store)

    def create_investigation(self, contract: ResearchContract) -> InvestigationState:
        investigation_id = make_investigation_id(contract)
        if self.store.investigation_path(investigation_id).exists():
            return self.store.read_investigation(investigation_id)
        now = _iso(_now())
        record = InvestigationState(
            investigation_id=investigation_id,
            contract=contract,
            status="draft",
            execution_ids=(),
            completed_runs=0,
            total_runs=resolve_protocol(contract.protocol_id).required_runs,
            artifact_status="partial",
            next_action="validate",
            revision=1,
            created_at=now,
            updated_at=now,
        )
        return self.store.write_investigation(record)

    def validate(self, investigation_id: str) -> InvestigationState:
        investigation = self.store.read_investigation(investigation_id)
        if investigation.trial_id is not None:
            return investigation
        if investigation.status not in {"draft", "failed"}:
            raise ValueError("only draft or failed investigations can be validated")
        try:
            prepared = self.runner.materializer.prepare(
                investigation.contract, hypothesis=investigation.contract.question
            )
            resolved = prepared.resolved_protocol
            fingerprint = collect_research_fingerprint(
                investigation.contract, resolved, prepared
            )
            trial_id = make_trial_id(investigation.contract, resolved, fingerprint)
        except Exception:
            failed = replace(
                investigation,
                status="failed",
                next_action="validate",
                revision=investigation.revision + 1,
                updated_at=_iso(_now()),
            )
            self.store.write_investigation(failed)
            raise
        validated = replace(
            investigation,
            status="validated",
            trial_id=trial_id,
            next_action="queue",
            revision=investigation.revision + 1,
            updated_at=_iso(_now()),
        )
        return self.store.write_investigation(validated)

    def _new_execution(
        self,
        investigation: InvestigationState,
        *,
        kind: str,
        parent_execution_id: str | None,
    ) -> tuple[ExecutionRecord, InvestigationState]:
        attempt = len(investigation.execution_ids) + 1
        execution_id = make_execution_id(
            investigation.investigation_id,
            content_hash(investigation.contract),
            kind,
            attempt,
        )
        now = _iso(_now())
        execution = ExecutionRecord(
            execution_id=execution_id,
            investigation_id=investigation.investigation_id,
            kind=kind,
            attempt=attempt,
            parent_execution_id=parent_execution_id,
            status="queued",
            artifact_status=investigation.artifact_status,
            trial_id=investigation.trial_id,
            contract_hash=content_hash(investigation.contract),
            completed_runs=investigation.completed_runs,
            total_runs=investigation.total_runs,
            created_at=now,
            history=({
                "at": now,
                "status": "queued",
                "completed_runs": investigation.completed_runs,
                "artifact_status": investigation.artifact_status,
                "note": f"{kind} execution queued",
            },),
        )
        self.store.write_execution(execution)
        queued = replace(
            investigation,
            status="queued",
            active_execution_id=execution_id,
            execution_ids=(*investigation.execution_ids, execution_id),
            next_action="execute",
            revision=investigation.revision + 1,
            updated_at=now,
        )
        self.store.write_investigation(queued)
        return execution, queued

    def queue(self, investigation_id: str) -> ExecutionRecord:
        investigation = self.store.read_investigation(investigation_id)
        if investigation.active_execution_id is not None:
            return self.store.read_execution(investigation.active_execution_id)
        if investigation.status != "validated":
            raise ValueError("only validated investigations can be queued")
        execution, _ = self._new_execution(
            investigation, kind="initial", parent_execution_id=None
        )
        return execution

    def _transition(
        self,
        execution: ExecutionRecord,
        investigation: InvestigationState,
        *,
        status: str,
        note: str,
        artifact_status: str | None = None,
        error: str | None = None,
        finished: bool = False,
    ) -> tuple[ExecutionRecord, InvestigationState]:
        now = _iso(_now())
        artifact_status = artifact_status or execution.artifact_status
        if finished:
            execution = replace(
                execution,
                finished_at=now,
                duration_ms=_duration_ms(
                    execution.started_at or execution.created_at, now
                ),
            )
        execution = replace(
            execution,
            status=status,
            artifact_status=artifact_status,
            error=error,
            history=(*execution.history, {
                "at": now,
                "status": status,
                "completed_runs": execution.completed_runs,
                "artifact_status": artifact_status,
                "note": note,
            }),
        )
        self.store.write_execution(execution)
        if status == "completed":
            next_action = "cache"
        elif status == "failed":
            next_action = "replay" if artifact_status == "complete" else "resume"
        elif status == "cancelled":
            next_action = "resume"
        elif status == "validating":
            next_action = "complete"
        else:
            next_action = "execute"
        active = None if status in {"completed", "failed", "cancelled"} else execution.execution_id
        investigation = replace(
            investigation,
            status=status,
            active_execution_id=active,
            completed_runs=execution.completed_runs,
            artifact_status=artifact_status,
            next_action=next_action,
            revision=investigation.revision + 1,
            updated_at=now,
        )
        self.store.write_investigation(investigation)
        return execution, investigation

    def execute(
        self,
        execution_id: str,
        *,
        observer: Callable[[int, int], None] | None = None,
    ) -> ExecutionRecord:
        execution = self.store.read_execution(execution_id)
        investigation = self.store.read_investigation(execution.investigation_id)
        if execution.status in {"completed", "failed", "cancelled"}:
            return execution
        if execution.status not in {"queued", "running", "cancel_requested"}:
            raise ValueError(f"cannot execute status {execution.status!r}")
        if execution.status == "queued":
            execution = replace(execution, started_at=_iso(_now()))
            execution, investigation = self._transition(
                execution,
                investigation,
                status="running",
                note="execution started",
            )

        def progress(completed: int, total: int) -> None:
            current = self.store.read_execution(execution_id)
            current_investigation = self.store.read_investigation(investigation.investigation_id)
            current = replace(current, completed_runs=completed)
            current_investigation = replace(
                current_investigation, completed_runs=completed
            )
            status = "cancel_requested" if current.status == "cancel_requested" else "running"
            current, current_investigation = self._transition(
                current,
                current_investigation,
                status=status,
                note=f"progress {completed}/{total}",
            )
            if observer is not None:
                observer(completed, total)
            if status == "cancel_requested":
                raise RunCancelledError("execution cancellation requested")

        try:
            self.runner.run(
                investigation.contract,
                progress=progress,
                skip_existing=execution.kind == "resume",
            )
            execution = self.store.read_execution(execution_id)
            investigation = self.store.read_investigation(investigation.investigation_id)
            if execution.completed_runs != execution.total_runs:
                raise ArtifactIntegrityError("cannot validate before all raw runs complete")
            execution, investigation = self._transition(
                execution,
                investigation,
                status="validating",
                artifact_status="complete",
                note="all raw runs retained; start validation",
            )
            validated = self.validator.validate_trial(execution.trial_id)
            report = self.composer.compose(validated)
            if validated.claim.status not in {"accepted", "inconclusive"}:
                raise ArtifactIntegrityError(
                    f"claim cannot complete validation: {validated.claim.status} — "
                    f"{validated.claim.failure_reason}"
                )
            if not report.get("report_id"):
                raise ArtifactIntegrityError("report publication did not return report_id")
            execution, investigation = self._transition(
                execution,
                investigation,
                status="completed",
                artifact_status="complete",
                note="validation and report completed",
                finished=True,
            )
        except RunCancelledError as error:
            execution = self.store.read_execution(execution_id)
            investigation = self.store.read_investigation(investigation.investigation_id)
            execution, investigation = self._transition(
                execution,
                investigation,
                status="cancelled",
                artifact_status="partial",
                error=str(error),
                note="execution cancelled safely",
                finished=True,
            )
        except Exception as error:
            execution = self.store.read_execution(execution_id)
            investigation = self.store.read_investigation(investigation.investigation_id)
            artifact_status = (
                "complete" if execution.completed_runs == execution.total_runs else "partial"
            )
            execution, investigation = self._transition(
                execution,
                investigation,
                status="failed",
                artifact_status=artifact_status,
                error=f"{type(error).__name__}: {error}",
                note="execution or validation failed; retained evidence preserved",
                finished=True,
            )
        return self.store.read_execution(execution_id)

    def cancel(self, execution_id: str) -> ExecutionRecord:
        execution = self.store.read_execution(execution_id)
        if execution.status != "running":
            raise ValueError("only running executions can be cancelled")
        investigation = self.store.read_investigation(execution.investigation_id)
        execution, _ = self._transition(
            execution,
            investigation,
            status="cancel_requested",
            note="cancellation requested; stop at next progress point",
        )
        return execution

    def recover(self, investigation_id: str) -> InvestigationState:
        investigation = self.store.read_investigation(investigation_id)
        if investigation.status not in {"queued", "running", "cancel_requested", "validating"}:
            return investigation
        if investigation.active_execution_id is None:
            raise ValueError("active investigation lacks an execution to recover")
        execution = self.store.read_execution(investigation.active_execution_id)
        artifact_status = (
            "complete" if execution.completed_runs == execution.total_runs else "partial"
        )
        self._transition(
            execution,
            investigation,
            status="failed",
            artifact_status=artifact_status,
            error="worker exited before execution completed",
            note="stale execution reconciled after worker exit",
            finished=True,
        )
        return self.store.read_investigation(investigation_id)

    def resume(
        self,
        investigation_id: str,
        *,
        observer: Callable[[int, int], None] | None = None,
    ) -> ExecutionRecord:
        investigation = self.store.read_investigation(investigation_id)
        if investigation.artifact_status != "partial" or investigation.status not in {
            "cancelled", "failed",
        }:
            raise ValueError("only cancelled/failed partial investigations can resume")
        parent = investigation.execution_ids[-1]
        execution, _ = self._new_execution(
            investigation, kind="resume", parent_execution_id=parent
        )
        return self.execute(execution.execution_id, observer=observer)

    def replay(self, investigation_id: str) -> ExecutionRecord:
        investigation = self.store.read_investigation(investigation_id)
        if investigation.artifact_status != "complete":
            raise ValueError("only complete investigations can replay")
        parent = investigation.execution_ids[-1]
        execution, _ = self._new_execution(
            investigation, kind="replay_check", parent_execution_id=parent
        )
        return self.execute(execution.execution_id)

    def cache(self, investigation_id: str) -> ExecutionRecord:
        investigation = self.store.read_investigation(investigation_id)
        if investigation.status != "completed" or investigation.artifact_status != "complete":
            raise ValueError("cache hit requires a completed investigation and report")
        self.store.read_result(investigation.trial_id)
        reports_root = self.store.trial_dir(investigation.trial_id) / "reports"
        valid_report = False
        for path in sorted(reports_root.glob("*.json")):
            try:
                self.store.read_report(investigation.trial_id, path.stem)
            except Exception:
                continue
            valid_report = True
            break
        if not valid_report:
            raise ValueError("cache hit requires at least one readable valid report")
        parent = investigation.execution_ids[-1]
        execution, investigation = self._new_execution(
            investigation, kind="cache_hit", parent_execution_id=parent
        )
        execution, _ = self._transition(
            execution,
            investigation,
            status="completed",
            artifact_status="complete",
            note="cache hit; read existing result without runner",
            finished=True,
        )
        return execution
