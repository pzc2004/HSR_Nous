"""DeepSeek Search/Fetch provider with permission and evidence guards."""

from __future__ import annotations

import ipaddress
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from hsr_nous.research_schema import content_hash
from hsr_nous.research_web.models import (
    WebPermissionError,
    WebPolicy,
    WebProviderError,
    WebQueryRecord,
    WebResultSet,
    WebUsageLedger,
    result_id,
)
from hsr_nous.research_web.store import WebEvidenceStore

_OFFICIAL_DOMAINS = {"bbs.mihoyo.com", "www.miyoushe.com"}
_WIKI_DOMAINS = {"honkai-star-rail.fandom.com", "wiki.biligame.com"}
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}
_REDIRECT_STATUS = {301, 302, 303, 307, 308}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WebPermissionError("fetch requires an absolute HTTP/HTTPS URL")
    if parsed.username or parsed.password:
        raise WebPermissionError("fetch URL must not contain credentials")
    host = parsed.hostname.rstrip(".").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise WebPermissionError("fetch URL must use a hostname, not an IP literal")


def _allowed_host(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


class DeepSeekWebProvider:
    def __init__(
        self,
        store: WebEvidenceStore,
        policy: WebPolicy,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com",
        transport: httpx.BaseTransport | None = None,
        sleeper: Any = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.api_key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._sleeper = sleeper or time.sleep

    def _require(self, kind: str) -> None:
        enabled = self.policy.allow_web_search if kind == "search" else self.policy.allow_web_fetch
        if not enabled:
            raise WebPermissionError(f"web {kind} is disabled by policy")
        if not self.policy.allowed_web_domains:
            raise WebPermissionError("web access requires an allowed domain list")
        budget = self.policy.max_web_queries if kind == "search" else self.policy.max_web_fetch
        if budget <= 0:
            raise WebPermissionError(f"web {kind} budget must be positive")
        if not self.api_key:
            raise WebPermissionError("DEEPSEEK_API_KEY is required for web access")

    def _check_budget(self, investigation_id: str, kind: str) -> int:
        ledger = self.store.read_usage(investigation_id)
        used = ledger.search_count if kind == "search" else ledger.fetch_count
        budget = self.policy.max_web_queries if kind == "search" else self.policy.max_web_fetch
        if used >= budget:
            raise WebPermissionError(f"web {kind} budget exhausted: {used}/{budget}")
        return used + 1

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=15.0, follow_redirects=False)

    def _request_with_retries(
        self,
        client: httpx.Client,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        last_error = None
        for attempt in range(3):
            try:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                if response.status_code in _RETRY_STATUS and attempt < 2:
                    self._sleeper(0)
                    continue
                response.raise_for_status()
                return response
            except (httpx.HTTPError, OSError) as error:
                last_error = error
                if (isinstance(error, httpx.HTTPStatusError)
                        and error.response.status_code not in _RETRY_STATUS):
                    break
                if attempt < 2:
                    self._sleeper(0)
        raise WebProviderError(f"DeepSeek request failed: {last_error}")

    def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        with self._client() as client:
            return self._request_with_retries(client, f"{self.base_url}{path}", payload)

    @staticmethod
    def _source_type(host: str) -> str:
        if host in _OFFICIAL_DOMAINS:
            return "official_text"
        if host in _WIKI_DOMAINS:
            return "wiki"
        return "community"

    def _result(self, item: dict[str, Any]) -> dict[str, Any]:
        url = item.get("url", "")
        try:
            host = _host(url)
            allowed = _allowed_host(host, self.policy.allowed_web_domains)
            reason = None if allowed else "domain is not in the allowlist"
        except WebPermissionError as error:
            host = ""
            allowed = False
            reason = str(error)
        content = item.get("content") or ""
        return {
            "title": item.get("title", ""),
            "url": url,
            "snippet": item.get("snippet", ""),
            "summary": item.get("summary", ""),
            "content": content,
            "site_name": item.get("site_name"),
            "date": item.get("date"),
            "authority": item.get("authority"),
            "rerank_score": item.get("rerank_score"),
            "source_type": self._source_type(host) if host else "community",
            "allowed": allowed,
            "exclusion_reason": reason,
            "content_hash": content_hash(item),
        }

    def _write_result(
        self,
        *,
        investigation_id: str,
        kind: str,
        attempt: int,
        request: dict[str, Any],
        started: float,
        results: list[dict[str, Any]] | None,
        error: dict[str, Any] | None,
    ) -> WebResultSet | None:
        query_id = content_hash({
            "investigation_id": investigation_id,
            "kind": kind,
            "attempt": attempt,
            "request": request,
        })
        result_set_id = result_id(query_id, results) if results is not None else None
        status = "failed" if error else "completed"
        result = None
        if results is not None:
            result = WebResultSet(
                result_set_id=result_set_id,
                investigation_id=investigation_id,
                query_id=query_id,
                provider="deepseek",
                retrieved_at=_now(),
                results=tuple(results),
                content_hash=result_set_id,
            )
            self.store.write_result(result)
        record = WebQueryRecord(
            query_id=query_id,
            investigation_id=investigation_id,
            kind=kind,
            attempt=attempt,
            request=request,
            status=status,
            error=error,
            result_set_id=result_set_id,
            created_at=_now(),
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
        self.store.write_query(record)
        ledger = self.store.read_usage(investigation_id)
        history = (*ledger.history, {"query_id": query_id, "status": status, "error": error})
        if kind == "search":
            ledger = WebUsageLedger(
                search_count=ledger.search_count + 1,
                fetch_count=ledger.fetch_count,
                history=history,
            )
        else:
            ledger = WebUsageLedger(
                search_count=ledger.search_count,
                fetch_count=ledger.fetch_count + 1,
                history=history,
            )
        self.store.write_usage(investigation_id, ledger)
        return result

    def search(
        self,
        query: str,
        *,
        count: int = 10,
        need_content: bool = False,
        ori_question: str | None = None,
        investigation_id: str,
    ) -> WebResultSet:
        self._require("search")
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 128:
            raise WebPermissionError("query must contain 1 to 128 characters")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 50:
            raise WebPermissionError("count must be between 1 and 50")
        if ori_question is not None and (not isinstance(ori_question, str) or len(ori_question) > 128):
            raise WebPermissionError("ori_question must be at most 128 characters")
        if not isinstance(need_content, bool):
            raise WebPermissionError("need_content must be boolean")
        attempt = self._check_budget(investigation_id, "search")
        domains = " OR ".join(f"site:{domain}" for domain in self.policy.allowed_web_domains)
        request = {
            "query": f"{query} {domains}",
            "count": count,
            "need_content": need_content,
        }
        if ori_question is not None:
            request["ori_question"] = ori_question
        started = time.monotonic()
        try:
            response = self._post("/v1/tools/search", request)
            raw = response.json()
            results = [self._result(item) for item in raw.get("results", [])]
            result = self._write_result(
                investigation_id=investigation_id,
                kind="search",
                attempt=attempt,
                request=request,
                started=started,
                results=results,
                error=None,
            )
            assert result is not None
            return result
        except Exception as error:
            self._write_result(
                investigation_id=investigation_id,
                kind="search",
                attempt=attempt,
                request=request,
                started=started,
                results=None,
                error={"type": type(error).__name__, "message": str(error)},
            )
            raise

    def fetch(self, url: str, *, investigation_id: str) -> WebResultSet:
        self._require("fetch")
        if not isinstance(url, str) or not 1 <= len(url) <= 8192:
            raise WebPermissionError("fetch URL must contain 1 to 8192 characters")
        attempt = self._check_budget(investigation_id, "fetch")
        started = time.monotonic()
        current_url = url
        try:
            host = _host(current_url)
            if not _allowed_host(host, self.policy.allowed_web_domains):
                raise WebPermissionError(f"fetch host is not in the allowlist: {host}")
            with self._client() as client:
                for redirect_index in range(4):
                    response = self._request_with_retries(client, current_url)
                    if response.status_code in _REDIRECT_STATUS:
                        if redirect_index >= 3:
                            raise WebProviderError("too many fetch redirects")
                        location = response.headers.get("location")
                        if not location:
                            raise WebProviderError("redirect has no location")
                        current_url = urljoin(current_url, location)
                        host = _host(current_url)
                        if not _allowed_host(host, self.policy.allowed_web_domains):
                            raise WebPermissionError(f"redirect host is not in the allowlist: {host}")
                        continue
                    if response.status_code in _RETRY_STATUS:
                        raise WebProviderError(f"retryable DeepSeek status: {response.status_code}")
                    response.raise_for_status()
                    break
                else:
                    raise WebProviderError("fetch redirect limit exceeded")
            page = response.json()
            result_item = self._result({
                "title": page.get("title", ""),
                "url": current_url,
                "content": page.get("content", ""),
            })
            result = self._write_result(
                investigation_id=investigation_id,
                kind="fetch",
                attempt=attempt,
                request={"url": url},
                started=started,
                results=[result_item],
                error=None,
            )
            assert result is not None
            return result
        except Exception as error:
            self._write_result(
                investigation_id=investigation_id,
                kind="fetch",
                attempt=attempt,
                request={"url": url},
                started=started,
                results=None,
                error={"type": type(error).__name__, "message": str(error)},
            )
            raise
