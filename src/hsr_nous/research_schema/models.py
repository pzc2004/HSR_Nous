"""Frozen, dependency-free data contracts for deterministic research."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, fields
from types import MappingProxyType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from hsr_nous.research_schema.canonical import _to_primitive

CLAIM_STATUSES = frozenset({"accepted", "rejected", "inconclusive", "stale"})


def _snapshot(value: Any) -> Any:
    if isinstance(value, _DataModel):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({
            deepcopy(key): _snapshot(item) for key, item in value.items()
        })
    if isinstance(value, (list, tuple)):
        return tuple(_snapshot(item) for item in value)
    return deepcopy(value)


def _decode(value: Any, annotation: Any) -> Any:
    if annotation is Any:
        return _snapshot(value)
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        errors = []
        for option in get_args(annotation):
            try:
                return _decode(value, option)
            except (TypeError, ValueError) as exc:
                errors.append(str(exc))
        raise TypeError("value does not match " + str(annotation) + ": " + "; ".join(errors))
    if origin is dict:
        if not isinstance(value, Mapping):
            raise TypeError("expected an object")
        key_type, value_type = get_args(annotation)
        return {
            _decode(key, key_type): _decode(item, value_type)
            for key, item in value.items()
        }
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise TypeError("expected an array")
        args = get_args(annotation)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(item, args[0]) for item in value)
        if len(value) != len(args):
            raise TypeError("tuple length does not match its schema")
        return tuple(_decode(item, item_type) for item, item_type in zip(value, args))
    if isinstance(annotation, type) and issubclass(annotation, _DataModel):
        if not isinstance(value, Mapping):
            raise TypeError(f"expected an object for {annotation.__name__}")
        return annotation.from_dict(value)
    if annotation is type(None):
        if value is not None:
            raise TypeError("expected null")
        return None
    if annotation is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("expected a number")
        return float(value)
    if annotation is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("expected an integer")
        return value
    if annotation is str:
        if not isinstance(value, str):
            raise TypeError("expected a string")
        return value
    return deepcopy(value)


class _DataModel:
    def __post_init__(self) -> None:
        for field in fields(self):
            object.__setattr__(self, field.name, _snapshot(getattr(self, field.name)))

    def to_dict(self) -> dict[str, Any]:
        return _to_primitive(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]):
        if not isinstance(payload, Mapping):
            raise TypeError(f"expected an object for {cls.__name__}")
        model_fields = fields(cls)
        names = {field.name for field in model_fields}
        unknown = set(payload) - names
        if unknown:
            raise ValueError(f"unknown fields for {cls.__name__}: {sorted(unknown)}")
        hints = get_type_hints(cls)
        values = {
            field.name: _decode(payload[field.name], hints[field.name])
            for field in model_fields
            if field.name in payload
        }
        return cls(**values)


@dataclass(frozen=True)
class MechanismPatch(_DataModel):
    template_kind: str
    template_id: str
    path: tuple[str | int, ...]
    value: int | float
    op: str = "set_number"


@dataclass(frozen=True)
class ExperimentArm(_DataModel):
    arm_id: str
    world: str
    patches: tuple[MechanismPatch, ...] = ()
    build_override: dict[str, Any] | None = None


@dataclass(frozen=True)
class MetricSpec(_DataModel):
    metric_id: str = "total_damage"
    statistic: str = "paired_mean_difference"
    confidence: float = 0.95
    direction: str = "higher_is_better"


@dataclass(frozen=True)
class ExperimentSpec(_DataModel):
    spec_id: str
    build: dict[str, Any]
    stage: dict[str, Any]
    baseline: ExperimentArm
    variant: ExperimentArm
    metric: MetricSpec
    comparison_kind: str = "mechanism"


@dataclass(frozen=True)
class ResearchContract(_DataModel):
    contract_id: str
    question: str
    protocol_id: str
    experiment: ExperimentSpec
    budget: dict[str, Any]


@dataclass(frozen=True)
class VersionFingerprint(_DataModel):
    rulebook_hash: str | None
    fixtures_hash: str | None
    data_hash: str | None
    policy_hash: str | None
    implementation_hash: str | None
    config_hash: str | None
    protocol_id: str
    artifact_schema_version: str | None
    git_commit: str | None = None
    variant_hash: str | None = None


@dataclass(frozen=True)
class RunRecord(_DataModel):
    run_id: str
    trial_id: str
    arm_id: str
    cohort: str
    seed: int
    status: str
    observed: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    final_save: dict[str, Any]
    modifiers: tuple[dict[str, Any], ...]
    content_hash: str
    kind: str = "recorded"
    parent_run_id: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.kind != "recorded":
            raise ValueError("RunRecord kind must be 'recorded'")


@dataclass(frozen=True)
class ComparisonSet(_DataModel):
    comparison_set_id: str
    baseline_dev: tuple[str, ...]
    baseline_holdout: tuple[str, ...]
    variant_dev: tuple[str, ...]
    variant_holdout: tuple[str, ...]


@dataclass(frozen=True)
class TrialArtifact(_DataModel):
    trial_id: str
    spec: ResearchContract
    resolved_protocol: dict[str, Any]
    fingerprint: VersionFingerprint
    comparison_set: ComparisonSet
    run_ids: tuple[str, ...]
    status: str
    caveats: tuple[dict[str, Any], ...] = ()
    failure_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceLink(_DataModel):
    trial_id: str
    artifact_hash: str
    run_id: str | None = None
    event_id: str | None = None
    modifier_id: str | None = None
    source_type: str = "simulated"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.source_type != "simulated":
            raise ValueError("EvidenceLink source_type must be 'simulated'")


@dataclass(frozen=True)
class Claim(_DataModel):
    claim_id: str
    trial_id: str
    comparison_set_id: str
    subject: str
    metric: MetricSpec
    relation: str
    status: str
    premises: tuple[EvidenceLink, ...]
    derivation_steps: tuple[dict[str, Any], ...]
    statistical_metadata: dict[str, Any]
    scope: dict[str, Any]
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status not in CLAIM_STATUSES:
            raise ValueError(f"unsupported Claim status: {self.status!r}")
