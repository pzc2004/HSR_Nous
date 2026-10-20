"""Permission policy and the only external research claim gateway."""

from hsr_nous.research.core import ArtifactError
from hsr_nous.research.permissions.gateway import ResearchGateway, open_research_gateway
from hsr_nous.research.permissions.policy import CapabilityPolicy, PermissionDeniedError

__all__ = [
    "ArtifactError",
    "CapabilityPolicy",
    "PermissionDeniedError",
    "ResearchGateway",
    "open_research_gateway",
]
