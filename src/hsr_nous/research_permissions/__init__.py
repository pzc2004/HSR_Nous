"""Permission policy and the only external research claim gateway."""

from hsr_nous.research_permissions.gateway import ResearchGateway, open_research_gateway
from hsr_nous.research_permissions.policy import CapabilityPolicy, PermissionDeniedError

__all__ = [
    "CapabilityPolicy",
    "PermissionDeniedError",
    "ResearchGateway",
    "open_research_gateway",
]
