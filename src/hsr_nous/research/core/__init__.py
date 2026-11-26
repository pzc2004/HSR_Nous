"""Deterministic research execution, evidence, statistics, and JSON reports."""

from hsr_nous.research.core.artifacts import (
    ArtifactConflictError,
    ArtifactError,
    ArtifactIntegrityError,
    ArtifactPathError,
    ArtifactStore,
    make_comparison_set,
    make_event_id,
    make_execution_id,
    make_investigation_id,
    make_modifier_id,
    make_run_id,
    make_trial_id,
    run_failure_reason,
)
from hsr_nous.research.core.candidates import CandidateRunner
from hsr_nous.research.core.tasks import CandidateTaskManager, CandidateTaskStore
from hsr_nous.research.core.claims import ClaimValidationResult, ClaimValidator
from hsr_nous.research.core.execution import ExecutionManager
from hsr_nous.research.core.fingerprint import (
    ARTIFACT_SCHEMA_VERSION,
    collect_research_fingerprint,
    collect_worldline_fingerprint,
    implementation_hash,
)
from hsr_nous.research.core.kernel import (
    build_claim,
    compare,
    confidence_interval,
    distribution,
    make_claim_id,
    mean,
    paired_diff,
    quantile,
    validate_claim,
    variance,
)
from hsr_nous.research.core.report import ReportComposer
from hsr_nous.research.core.runner import RunCancelledError, TrialRunner
from hsr_nous.research.core.variants import PreparedVariant, VariantMaterializer
from hsr_nous.research.core.worldline import (
    WorldlineRunner,
    derive_child_spec,
    verify_worldline,
)

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ArtifactConflictError",
    "ArtifactError",
    "ArtifactIntegrityError",
    "ArtifactPathError",
    "ArtifactStore",
    "CandidateRunner",
    "CandidateTaskManager",
    "CandidateTaskStore",
    "ClaimValidationResult",
    "ClaimValidator",
    "ExecutionManager",
    "PreparedVariant",
    "ReportComposer",
    "RunCancelledError",
    "TrialRunner",
    "VariantMaterializer",
    "WorldlineRunner",
    "build_claim",
    "collect_research_fingerprint",
    "collect_worldline_fingerprint",
    "compare",
    "confidence_interval",
    "distribution",
    "derive_child_spec",
    "implementation_hash",
    "make_claim_id",
    "make_comparison_set",
    "make_event_id",
    "make_execution_id",
    "make_investigation_id",
    "make_modifier_id",
    "make_run_id",
    "make_trial_id",
    "mean",
    "paired_diff",
    "quantile",
    "run_failure_reason",
    "validate_claim",
    "variance",
    "verify_worldline",
]
