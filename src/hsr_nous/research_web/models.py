"""External web evidence contracts and provider protocol."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from hsr_nous.research_schema import content_hash


class WebPermissionError(PermissionError):
    pass


class WebProviderError(RuntimeError):
    pass


class WebEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebPolicy(Protocol):
    allow_web_search: bool
    allow_web_fetch: bool
    allowed_web_domains: tuple[str, ...]
    max_web_queries: int
    max_web_fetch: int


@dataclass(frozen=True)
class WebQueryRecord:
    query_id: str
    investigation_id: str
    kind: str
    attempt: int
    request: dict[str, Any]
    status: str
    error: dict[str, Any] | None
    result_set_id: str | None
    created_at: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WebQueryRecord":
        return cls(**payload)


@dataclass(frozen=True)
class WebResultSet:
    result_set_id: str
    investigation_id: str
    query_id: str
    provider: str
    retrieved_at: str
    results: tuple[dict[str, Any], ...]
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WebResultSet":
        payload = dict(payload)
        payload["results"] = tuple(payload["results"])
        return cls(**payload)


@dataclass(frozen=True)
class WebUsageLedger:
    search_count: int = 0
    fetch_count: int = 0
    history: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WebUsageLedger":
        payload = dict(payload)
        payload["history"] = tuple(payload["history"])
        return cls(**payload)


class WebSearchProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        count: int = 10,
        need_content: bool = False,
        ori_question: str | None = None,
        investigation_id: str,
    ) -> WebResultSet:
        ...

    def fetch(self, url: str, *, investigation_id: str) -> WebResultSet:
        ...


def result_id(query_id: str, results: Any) -> str:
    return content_hash({"query_id": query_id, "results": results})
