"""Permission policy and the only external research claim gateway."""

from hsr_nous.research_permissions.gateway import ResearchGateway
from hsr_nous.research_permissions.policy import CapabilityPolicy, PermissionDeniedError

__all__ = ["CapabilityPolicy", "PermissionDeniedError", "ResearchGateway"]
