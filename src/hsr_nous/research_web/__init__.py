"""Optional external web evidence providers."""

from hsr_nous.research_web.models import (
    WebEvidenceError,
    WebPermissionError,
    WebProviderError,
    WebQueryRecord,
    WebResultSet,
    WebSearchProvider,
    WebUsageLedger,
)
from hsr_nous.research_web.provider import DeepSeekWebProvider
from hsr_nous.research_web.store import WebEvidenceStore

__all__ = [
    "DeepSeekWebProvider",
    "WebEvidenceError",
    "WebEvidenceStore",
    "WebPermissionError",
    "WebProviderError",
    "WebQueryRecord",
    "WebResultSet",
    "WebSearchProvider",
    "WebUsageLedger",
]
