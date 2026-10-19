"""Permission-checked external entry point for research submissions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hsr_nous.common import repo_root, research_root
from hsr_nous.research_core import (
    ArtifactStore,
    ClaimValidator,
    ExecutionManager,
    ReportComposer,
    TrialRunner,
)
from hsr_nous.research_core.kernel import validate_claim
from hsr_nous.research_permissions.policy import CapabilityPolicy, PermissionDeniedError
from hsr_nous.research_schema import (
    Claim,
    ClaimSubmissionResult,
    EvidenceLink,
    InvestigationState,
    ResearchContract,
)
from hsr_nous.research_web import DeepSeekWebProvider, WebEvidenceStore, WebSearchProvider


def open_research_gateway(
    root: Path | None = None,
    *,
    policy: CapabilityPolicy | None = None,
) -> ResearchGateway:
    if root is None:
        root = policy.allowed_project_root if policy is not None else research_root()
    project_root = Path(root).resolve()
    if policy is None:
        policy = CapabilityPolicy(allowed_project_root=project_root)
    return ResearchGateway(ArtifactStore(project_root / "artifacts"), policy)


def _error(
    code: str,
    message: str,
    *,
    fields: dict[str, str] | None = None,
    evidence: Any = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "fields": fields or {},
        "evidence": evidence if evidence is not None else {},
    }


class ResearchGateway:
    def __init__(
        self,
        store: ArtifactStore,
        policy: CapabilityPolicy,
        *,
        runner: TrialRunner | None = None,
        validator: ClaimValidator | None = None,
        composer: ReportComposer | None = None,
        execution_manager: ExecutionManager | None = None,
        web_provider: WebSearchProvider | None = None,
    ) -> None:
        self._store = store
        self._policy = policy
        self._manager = execution_manager or ExecutionManager(store, runner)
        self._runner = runner or self._manager.runner
        self._validator = validator or self._manager.validator
        self._composer = composer or self._manager.composer
        if web_provider is None and (policy.allow_web_search or policy.allow_web_fetch):
            web_provider = DeepSeekWebProvider(WebEvidenceStore(self._store.root), policy=self._policy)
        self._web_provider = web_provider
        root = policy.allowed_project_root.resolve()
        repository = repo_root().resolve()
        if self._within(root, repository):
            raise PermissionDeniedError("allowed_project_root must be outside the repository")

    @staticmethod
    def _within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    def _require(self, *capabilities: str) -> None:
        missing = [name for name in capabilities if not getattr(self._policy, name)]
        if missing:
            raise PermissionDeniedError("disabled capabilities: " + ", ".join(missing))

    def authorize_path(self, path: Path, capability: str) -> Path:
        resolved = Path(path).resolve()
        name = resolved.name.lower()
        parts = {part.lower() for part in resolved.parts}
        if ".git" in parts or name == ".env" or name.startswith(".env."):
            raise PermissionDeniedError("access to .git and .env is forbidden")
        if (name == "docker.sock" or "credential" in name or "secret" in name
                or "token" in name or name == "id_rsa" or name.endswith((".pem", ".key"))):
            raise PermissionDeniedError("access to credentials and Docker socket is forbidden")

        if capability == "write_project":
            self._require("allow_write_project")
            root = self._policy.allowed_project_root.resolve()
            if self._within(resolved, repo_root().resolve()) or not self._within(resolved, root):
                raise PermissionDeniedError("project write escapes allowed_project_root")
        elif capability == "read_artifacts":
            self._require("allow_read_artifacts")
            root = self._store.root.resolve()
            if not self._within(resolved, root):
                raise PermissionDeniedError("artifact read escapes artifact root")
        elif capability == "read_repo":
            self._require("allow_read_repo")
            if not self._within(resolved, repo_root().resolve()):
                raise PermissionDeniedError("repository read escapes repository root")
        else:
            raise PermissionDeniedError(f"unknown path capability: {capability}")
        return resolved

    def execute_custom_code(self, kind: str, payload: Any) -> None:
        del kind, payload
        raise PermissionDeniedError("custom Bash/Python/Docker execution is disabled")

    def create_investigation(self, contract: ResearchContract):
        self._require("allow_write_project")
        return self._manager.create_investigation(contract)

    def validate(self, investigation_id: str):
        self._require("allow_read_repo", "allow_write_project")
        return self._manager.validate(investigation_id)

    def queue(self, investigation_id: str):
        self._require("allow_write_project")
        return self._manager.queue(investigation_id)

    def execute(self, execution_id: str):
        self._require("allow_run_simulation", "allow_write_project")
        return self._manager.execute(execution_id)

    def cancel(self, execution_id: str):
        self._require("allow_write_project")
        return self._manager.cancel(execution_id)

    def resume(self, investigation_id: str):
        self._require("allow_run_simulation", "allow_write_project")
        return self._manager.resume(investigation_id)

    def replay(self, investigation_id: str):
        self._require("allow_run_simulation", "allow_write_project")
        return self._manager.replay(investigation_id)

    def cache(self, investigation_id: str):
        self._require("allow_read_artifacts")
        return self._manager.cache(investigation_id)

    def read_investigation(self, investigation_id: str) -> InvestigationState:
        self._require("allow_read_artifacts")
        return self._store.read_investigation(investigation_id)

    def read_report(self, trial_id: str, report_id: str) -> dict[str, Any]:
        self._require("allow_read_artifacts")
        return self._store.read_report(trial_id, report_id)

    def resolve_evidence(self, link: EvidenceLink) -> dict[str, Any]:
        self._require("allow_read_artifacts")
        return self._store.resolve_evidence(link)

    def search_web(self, query: str, **kwargs):
        self._require("allow_web_search")
        if self._web_provider is None:
            raise PermissionDeniedError("web search provider is not configured")
        return self._web_provider.search(query, **kwargs)

    def fetch_web(self, url: str, *, investigation_id: str):
        self._require("allow_web_fetch")
        if self._web_provider is None:
            raise PermissionDeniedError("web fetch provider is not configured")
        return self._web_provider.fetch(url, investigation_id=investigation_id)

    def _permission_result(self, missing: list[str]) -> ClaimSubmissionResult:
        return ClaimSubmissionResult(
            status="permission_denied",
            error=_error(
                "permission_denied",
                "disabled capabilities: " + ", ".join(missing),
                fields={name: "disabled by policy" for name in missing},
            ),
        )

    def _missing_submit_capabilities(self, contract, trial_id, claim) -> list[str]:
        missing = []
        if not self._policy.allow_submit_claim:
            missing.append("allow_submit_claim")
        if contract is not None:
            for name in ("allow_run_simulation", "allow_write_project", "allow_read_repo"):
                if not getattr(self._policy, name):
                    missing.append(name)
        else:
            if not self._policy.allow_read_artifacts:
                missing.append("allow_read_artifacts")
        return missing

    def _rejected_result(
        self,
        claim: Claim | None,
        *,
        code: str,
        message: str,
        fields: dict[str, str],
        execution: Any = None,
    ) -> ClaimSubmissionResult:
        if claim is None:
            return ClaimSubmissionResult(
                status="rejected",
                execution=execution,
                error=_error(code, message, fields=fields),
            )
        validated = self._validator.validate(claim)
        report = self._composer.compose(validated)
        claim = validated.claim
        evidence = claim.to_dict()["premises"]
        return ClaimSubmissionResult(
            status="rejected",
            claim=claim,
            report=report,
            execution=execution,
            error=_error(code, message, fields=fields, evidence=evidence),
        )

    def submit_claim(
        self,
        *,
        contract: ResearchContract | None = None,
        trial_id: str | None = None,
        claim: Claim | None = None,
    ) -> ClaimSubmissionResult:
        missing = self._missing_submit_capabilities(contract, trial_id, claim)
        if missing:
            return self._permission_result(missing)
        inputs = [contract is not None, trial_id is not None, claim is not None]
        if sum(inputs) != 1:
            return ClaimSubmissionResult(
                status="rejected",
                error=_error(
                    "invalid_submission",
                    "exactly one of contract, trial_id, or claim is required",
                    fields={"input": "exactly one input is allowed"},
                ),
            )
        try:
            if contract is not None:
                return self._submit_contract(contract)
            if trial_id is not None:
                return self._submit_trial(trial_id)
            return self._submit_claim_object(claim)
        except Exception as error:
            if claim is not None:
                return self._rejected_result(
                    claim,
                    code="evidence_invalid",
                    message=f"{type(error).__name__}: {error}",
                    fields={"evidence": "failed to reload or independently validate evidence"},
                )
            return ClaimSubmissionResult(
                status="rejected",
                error=_error(
                    "evidence_invalid",
                    f"{type(error).__name__}: {error}",
                    fields={"trial_id": trial_id or "unknown"},
                ),
            )

    def _submit_contract(self, contract: ResearchContract) -> ClaimSubmissionResult:
        investigation = self._manager.create_investigation(contract)
        try:
            investigation = self._manager.validate(investigation.investigation_id)
            execution = self._manager.queue(investigation.investigation_id)
            execution = self._manager.execute(execution.execution_id)
        except Exception as error:
            return ClaimSubmissionResult(
                status="failed",
                error=_error(
                    "execution_validation_failed",
                    f"{type(error).__name__}: {error}",
                    fields={"stage": "create_or_validate"},
                ),
            )
        if execution.status in {"failed", "cancelled"}:
            return ClaimSubmissionResult(
                status=execution.status,
                execution=execution,
                error=_error(
                    f"execution_{execution.status}",
                    execution.error or execution.status,
                    fields={"execution_id": execution.execution_id},
                    evidence={"execution_id": execution.execution_id},
                ),
            )
        validated = self._validator.validate_trial(execution.trial_id)
        if validated.claim.status == "stale":
            return ClaimSubmissionResult(
                status="stale",
                claim=validated.claim,
                execution=execution,
                error=_error(
                    "stale",
                    validated.claim.failure_reason or "current fingerprint differs",
                    fields={"fingerprint": "current fingerprint differs from claim premises"},
                    evidence=validated.claim.to_dict()["premises"],
                ),
            )
        report = self._composer.compose(validated)
        if validated.claim.status == "accepted":
            return ClaimSubmissionResult(
                status="accepted",
                claim=validated.claim,
                report=report,
                execution=execution,
            )
        if validated.claim.status == "rejected":
            return self._rejected_result(
                validated.claim,
                code="claim_derivation_mismatch",
                message=validated.claim.failure_reason or "claim validation rejected",
                fields={"claim": "independent recomputation rejected the claim"},
                execution=execution,
            )
        return ClaimSubmissionResult(
            status=validated.claim.status,
            claim=validated.claim,
            report=report,
            execution=execution,
            error=_error(
                validated.claim.status,
                validated.claim.failure_reason or "validation inconclusive",
                fields={"holdout": "no accepted directional conclusion"},
                evidence=validated.claim.to_dict()["premises"],
            ),
        )

    def _submit_trial(self, trial_id: str) -> ClaimSubmissionResult:
        validated = self._validator.validate_trial(trial_id)
        if validated.claim.status == "stale":
            return ClaimSubmissionResult(
                status="stale",
                claim=validated.claim,
                error=_error(
                    "stale",
                    validated.claim.failure_reason or "current fingerprint differs",
                    fields={"fingerprint": "current fingerprint differs from claim premises"},
                    evidence=validated.claim.to_dict()["premises"],
                ),
            )
        report = self._composer.compose(validated)
        if validated.claim.status == "accepted":
            return ClaimSubmissionResult(
                status="accepted", claim=validated.claim, report=report
            )
        if validated.claim.status == "rejected":
            return self._rejected_result(
                validated.claim,
                code="claim_derivation_mismatch",
                message=validated.claim.failure_reason or "claim validation rejected",
                fields={"claim": "independent recomputation rejected the claim"},
            )
        return ClaimSubmissionResult(
            status=validated.claim.status,
            claim=validated.claim,
            error=_error(
                validated.claim.status,
                validated.claim.failure_reason or "validation inconclusive",
                fields={"holdout": "no accepted directional conclusion"},
                evidence=validated.claim.to_dict()["premises"],
            ),
        )

    def _submit_claim_object(self, claim: Claim) -> ClaimSubmissionResult:
        validated = self._validator.validate(claim)
        if validated.claim.status == "stale":
            return ClaimSubmissionResult(
                status="stale",
                claim=validated.claim,
                error=_error(
                    "stale",
                    validated.claim.failure_reason or "current fingerprint differs",
                    fields={"fingerprint": "current fingerprint differs from claim premises"},
                    evidence=validated.claim.to_dict()["premises"],
                ),
            )
        if validated.claim.status == "rejected":
            expected = self._validator.validate_trial(claim.trial_id)
            fields = {
                field: "does not match independently recomputed value"
                for field in validate_claim(claim, expected.claim)
            }
            return self._rejected_result(
                validated.claim,
                code="claim_derivation_mismatch",
                message=validated.claim.failure_reason or "claim derivation mismatch",
                fields=fields or {"claim": "independent recomputation rejected the claim"},
            )
        report = self._composer.compose(validated)
        if validated.claim.status == "accepted":
            return ClaimSubmissionResult(
                status="accepted", claim=validated.claim, report=report
            )
        return ClaimSubmissionResult(
            status=validated.claim.status,
            claim=validated.claim,
            error=_error(
                validated.claim.status,
                validated.claim.failure_reason or "validation inconclusive",
                fields={"holdout": "no accepted directional conclusion"},
                evidence=validated.claim.to_dict()["premises"],
            ),
        )
