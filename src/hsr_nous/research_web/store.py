"""Canonical, append-only external web evidence storage."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from hsr_nous.research_schema import canonical_bytes, content_hash
from hsr_nous.research_web.models import (
    WebEvidenceError,
    WebQueryRecord,
    WebResultSet,
    WebUsageLedger,
)

_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMPONENT_RE = re.compile(r"[A-Za-z0-9_-]+\Z")


class WebEvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root) / "web"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _id(value: str, label: str) -> str:
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            raise WebEvidenceError(f"{label} must be a full SHA-256 ID")
        return value

    def _safe(self, path: Path) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as exc:
            raise WebEvidenceError(f"web evidence path escapes root: {path}") from exc
        return resolved

    def _investigation_dir(self, investigation_id: str) -> Path:
        if not isinstance(investigation_id, str) or not _COMPONENT_RE.fullmatch(investigation_id):
            raise WebEvidenceError("unsafe investigation_id")
        return self._safe(self.root / investigation_id)

    @staticmethod
    def _publish(path: Path, payload: Any, *, overwrite: bool = False) -> None:
        data = canonical_bytes(payload)
        if path.exists() and not overwrite:
            if path.read_bytes() == data:
                path.chmod(0o444)
                return
            raise WebEvidenceError(f"artifact already exists with different bytes: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o444)
            if path.exists() and not overwrite:
                if path.read_bytes() == data:
                    temporary.unlink()
                    return
                raise WebEvidenceError(f"artifact already exists with different bytes: {path}")
            os.replace(temporary, path)
            path.chmod(0o444)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _read(self, path: Path) -> Any:
        raw = self._safe(path).read_bytes()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WebEvidenceError(f"invalid web artifact JSON: {path}") from exc
        if raw != canonical_bytes(payload):
            raise WebEvidenceError(f"web artifact is not canonical: {path}")
        artifact_hash = payload.pop("artifact_hash", None)
        if artifact_hash != content_hash(payload):
            raise WebEvidenceError("web artifact content hash mismatch")
        return payload

    def write_query(self, record: WebQueryRecord) -> None:
        path = self._safe(
            self._investigation_dir(record.investigation_id) / "queries" / f"{record.query_id}.json"
        )
        payload = record.to_dict()
        payload["artifact_hash"] = content_hash(record)
        self._publish(path, payload)

    def read_query(self, investigation_id: str, query_id: str) -> WebQueryRecord:
        payload = self._read(
            self._investigation_dir(investigation_id) / "queries" / f"{query_id}.json"
        )
        record = WebQueryRecord.from_dict(payload)
        if record.query_id != query_id or record.investigation_id != investigation_id:
            raise WebEvidenceError("query identity does not match its path")
        return record

    def write_result(self, result: WebResultSet) -> None:
        path = self._safe(
            self._investigation_dir(result.investigation_id) / "results" / f"{result.result_set_id}.json"
        )
        payload = result.to_dict()
        payload["artifact_hash"] = content_hash(result)
        self._publish(path, payload)

    def read_result(self, investigation_id: str, result_set_id: str) -> WebResultSet:
        payload = self._read(
            self._investigation_dir(investigation_id) / "results" / f"{result_set_id}.json"
        )
        result = WebResultSet.from_dict(payload)
        if result.result_set_id != result_set_id or result.investigation_id != investigation_id:
            raise WebEvidenceError("result_set identity does not match its path")
        if result.content_hash != content_hash({
            "query_id": result.query_id,
            "results": result.results,
        }):
            raise WebEvidenceError("result set content hash mismatch")
        return result

    def read_usage(self, investigation_id: str) -> WebUsageLedger:
        path = self._investigation_dir(investigation_id) / "usage.json"
        if not path.exists():
            return WebUsageLedger()
        payload = self._read(path)
        return WebUsageLedger.from_dict(payload)

    def write_usage(self, investigation_id: str, ledger: WebUsageLedger) -> None:
        previous = self.read_usage(investigation_id)
        if (ledger.search_count < previous.search_count
                or ledger.fetch_count < previous.fetch_count
                or ledger.history[:len(previous.history)] != previous.history):
            raise WebEvidenceError("web usage history cannot move backwards")
        payload = ledger.to_dict()
        payload["artifact_hash"] = content_hash(ledger)
        path = self._investigation_dir(investigation_id) / "usage.json"
        if path.exists():
            path.chmod(0o644)
        self._publish(path, payload, overwrite=True)
