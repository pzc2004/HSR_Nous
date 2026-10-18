"""Deterministic research execution, evidence, statistics, and JSON reports."""

from hsr_nous.research_core.artifacts import (
    ArtifactConflictError,
    ArtifactError,
    ArtifactIntegrityError,
    ArtifactPathError,
    ArtifactStore,
    make_comparison_set,
    make_event_id,
    make_modifier_id,
    make_run_id,
    make_trial_id,
    run_failure_reason,
)
from hsr_nous.research_core.claims import ClaimValidationResult, ClaimValidator
from hsr_nous.research_core.fingerprint import (
    ARTIFACT_SCHEMA_VERSION,
    collect_research_fingerprint,
    implementation_hash,
)
from hsr_nous.research_core.kernel import (
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
from hsr_nous.research_core.report import ReportComposer
from hsr_nous.research_core.runner import TrialRunner
from hsr_nous.research_core.variants import PreparedVariant, VariantMaterializer

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ArtifactConflictError",
    "ArtifactError",
    "ArtifactIntegrityError",
    "ArtifactPathError",
    "ArtifactStore",
    "ClaimValidationResult",
    "ClaimValidator",
    "PreparedVariant",
    "ReportComposer",
    "TrialRunner",
    "VariantMaterializer",
    "build_claim",
    "collect_research_fingerprint",
    "compare",
    "confidence_interval",
    "distribution",
    "implementation_hash",
    "make_claim_id",
    "make_comparison_set",
    "make_event_id",
    "make_modifier_id",
    "make_run_id",
    "make_trial_id",
    "mean",
    "paired_diff",
    "quantile",
    "run_failure_reason",
    "validate_claim",
    "variance",
]
