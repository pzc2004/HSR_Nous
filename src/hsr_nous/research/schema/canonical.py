"""Canonical JSON and content hashing for research artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any


def _to_primitive(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_primitive(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            result[key] = _to_primitive(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_to_primitive(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON numbers must be finite")
        return value
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize supported data without coercion or non-finite numbers."""
    return json.dumps(
        _to_primitive(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _round_primitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _round_primitive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_primitive(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def canonical_round(value: Any) -> Any:
    """Return JSON-shaped kernel output with every float rounded to six places."""
    return _round_primitive(_to_primitive(value))
