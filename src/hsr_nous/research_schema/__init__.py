"""Pure data contracts for deterministic research."""

from hsr_nous.research_schema.canonical import (
    canonical_bytes,
    canonical_json,
    canonical_round,
    content_hash,
)
from hsr_nous.research_schema.models import (
    CLAIM_STATUSES,
    Claim,
    ComparisonSet,
    EvidenceLink,
    ExperimentArm,
    ExperimentSpec,
    MechanismPatch,
    MetricSpec,
    ResearchContract,
    RunRecord,
    TrialArtifact,
    VersionFingerprint,
)

__all__ = [
    "CLAIM_STATUSES",
    "Claim",
    "ComparisonSet",
    "EvidenceLink",
    "ExperimentArm",
    "ExperimentSpec",
    "MechanismPatch",
    "MetricSpec",
    "ResearchContract",
    "RunRecord",
    "TrialArtifact",
    "VersionFingerprint",
    "canonical_bytes",
    "canonical_json",
    "canonical_round",
    "content_hash",
]
