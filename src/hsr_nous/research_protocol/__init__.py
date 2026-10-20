"""Fixed experiment protocols and contract validation."""

from hsr_nous.research_protocol.candidate_proposals import CandidateGenerator
from hsr_nous.research_protocol.profiles import (
    PAIRED_V1,
    PROTOCOL_PROFILES,
    ResolvedProtocol,
)
from hsr_nous.research_protocol.validation import (
    ProtocolValidationError,
    resolve_protocol,
    validate_candidate_set,
    validate_contract,
    validate_fingerprint,
    validate_patch_reference,
)

__all__ = [
    "CandidateGenerator",
    "PAIRED_V1",
    "PROTOCOL_PROFILES",
    "ProtocolValidationError",
    "ResolvedProtocol",
    "resolve_protocol",
    "validate_candidate_set",
    "validate_contract",
    "validate_fingerprint",
    "validate_patch_reference",
]
