"""Frozen, dependency-free data contracts for deterministic research."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, fields
from numbers import Real
from types import MappingProxyType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from hsr_nous.research.schema.canonical import _to_primitive, content_hash

CLAIM_STATUSES = frozenset({"accepted", "rejected", "inconclusive", "stale"})
EXECUTION_KINDS = frozenset({"initial", "cache_hit", "replay_check", "resume"})
CLAIM_SUBMISSION_STATUSES = frozenset({
    "accepted", "inconclusive", "rejected", "stale", "failed", "cancelled",
    "permission_denied",
})
EXECUTION_STATUSES = frozenset({
    "draft", "validated", "queued", "running", "validating", "completed",
    "failed", "cancel_requested", "cancelled",
})
ARTIFACT_STATUSES = frozenset({"partial", "complete"})
WORLDLINE_STATUSES = frozenset({"completed", "failed"})
WORLDLINE_SCHEMA_VERSION = "worldline-v1"
#: derived_from 内身份/内容哈希的闭合格式：完整 64 位小写十六进制 SHA-256
_DERIVED_FROM_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_DERIVED_FROM_KEYS = frozenset({"worldline_id", "content_hash", "note"})
METRIC_DIRECTIONS = {
    "total_damage": "higher_is_better",
    "action_value": "lower_is_better",
}


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


def _validate_candidate_path(path: Any, owner: str) -> None:
    if not isinstance(path, tuple) or not path:
        raise ValueError(f"{owner} path must be a non-empty tuple")
    for component in path:
        if isinstance(component, bool) or not isinstance(component, (str, int)):
            raise ValueError(f"{owner} path components must be strings or integers")


@dataclass(frozen=True)
class CandidateRule(_DataModel):
    path: tuple[str | int, ...]
    values: tuple[Any, ...]
    template_kind: str | None = None
    template_id: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_candidate_path(self.path, "CandidateRule")
        if not isinstance(self.values, tuple) or not self.values:
            raise ValueError("CandidateRule values must be a non-empty tuple")
        template_fields = (self.template_kind, self.template_id)
        if any(value is None for value in template_fields) and any(
            value is not None for value in template_fields
        ):
            raise ValueError("CandidateRule template_kind and template_id must be paired")
        if any(
            value is not None and (not isinstance(value, str) or not value)
            for value in template_fields
        ):
            raise ValueError("CandidateRule template fields must be non-empty strings")


@dataclass(frozen=True)
class CandidateSpace(_DataModel):
    base_contract: ResearchContract
    rules: tuple[CandidateRule, ...]
    max_candidates: int = 4

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.base_contract, ResearchContract):
            raise ValueError("CandidateSpace base_contract must be a ResearchContract")
        if not isinstance(self.rules, tuple) or not self.rules:
            raise ValueError("CandidateSpace requires at least one rule")
        if any(not isinstance(rule, CandidateRule) for rule in self.rules):
            raise ValueError("CandidateSpace rules must be CandidateRule instances")
        paths = [rule.path for rule in self.rules]
        if len(set(paths)) != len(paths):
            raise ValueError("CandidateSpace rule paths must be unique")
        if (isinstance(self.max_candidates, bool) or not isinstance(self.max_candidates, int)
                or not 2 <= self.max_candidates <= 16):
            raise ValueError("CandidateSpace max_candidates must be between 2 and 16")


@dataclass(frozen=True)
class CandidateEdit(_DataModel):
    path: tuple[str | int, ...]
    value: Any

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_candidate_path(self.path, "CandidateEdit")


@dataclass(frozen=True)
class CandidateProposal(_DataModel):
    path: tuple[str | int, ...] | None = None
    value: Any = None
    label: str | None = None
    edits: tuple[CandidateEdit, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.path is None and not self.edits:
            raise ValueError("CandidateProposal requires path/value or edits")
        if self.path is not None:
            _validate_candidate_path(self.path, "CandidateProposal")
            if self.edits:
                raise ValueError("CandidateProposal path/value and edits are mutually exclusive")
        if any(not isinstance(edit, CandidateEdit) for edit in self.edits):
            raise ValueError("CandidateProposal edits must be CandidateEdit instances")
        if self.label is not None and (not isinstance(self.label, str) or not self.label):
            raise ValueError("CandidateProposal label must be a non-empty string")


@dataclass(frozen=True)
class CandidateSet(_DataModel):
    question: str
    candidates: tuple[ResearchContract, ...]
    top_k: int = 1
    correction: str = "bonferroni"

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.question, str) or not self.question:
            raise ValueError("CandidateSet question must be non-empty")
        if len(self.candidates) < 2:
            raise ValueError("CandidateSet requires at least two candidates")
        if (isinstance(self.top_k, bool) or not isinstance(self.top_k, int)
                or not 1 <= self.top_k <= len(self.candidates)):
            raise ValueError("CandidateSet top_k must fit the candidate count")
        if self.correction != "bonferroni":
            raise ValueError("CandidateSet only supports bonferroni correction")

    @property
    def candidate_set_id(self) -> str:
        return content_hash(self)


@dataclass(frozen=True)
class CandidateTask(_DataModel):
    task_id: str
    candidate_set: CandidateSet
    investigation_ids: tuple[str, ...]
    status: str
    artifact_status: str
    attempt: int
    revision: int
    created_at: str
    updated_at: str
    report_id: str | None = None
    error: str | None = None
    history: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.task_id or not isinstance(self.candidate_set, CandidateSet):
            raise ValueError("CandidateTask requires an identity and CandidateSet")
        if len(self.investigation_ids) != len(self.candidate_set.candidates):
            raise ValueError("CandidateTask investigation IDs must match candidates")
        if self.status not in EXECUTION_STATUSES:
            raise ValueError(f"unsupported CandidateTask status: {self.status!r}")
        if self.artifact_status not in ARTIFACT_STATUSES:
            raise ValueError(f"unsupported artifact_status: {self.artifact_status!r}")
        if (isinstance(self.attempt, bool) or not isinstance(self.attempt, int)
                or self.attempt < 1):
            raise ValueError("CandidateTask attempt must be positive")
        if (isinstance(self.revision, bool) or not isinstance(self.revision, int)
                or self.revision < 1):
            raise ValueError("CandidateTask revision must be positive")


@dataclass(frozen=True)
class CandidateTaskEvent(_DataModel):
    event_id: str
    task_id: str
    kind: str
    status: str
    attempt: int
    created_at: str
    contract_id: str | None = None
    report_id: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.event_id or not self.task_id or not self.kind:
            raise ValueError("CandidateTaskEvent identities and kind must be non-empty")
        if self.status not in EXECUTION_STATUSES:
            raise ValueError(f"unsupported CandidateTaskEvent status: {self.status!r}")
        if (isinstance(self.attempt, bool) or not isinstance(self.attempt, int)
                or self.attempt < 1):
            raise ValueError("CandidateTaskEvent attempt must be positive")


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


@dataclass(frozen=True)
class ExecutionRecord(_DataModel):
    execution_id: str
    investigation_id: str
    kind: str
    attempt: int
    status: str
    artifact_status: str
    contract_hash: str
    completed_runs: int
    total_runs: int
    created_at: str
    parent_execution_id: str | None = None
    trial_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    history: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.kind not in EXECUTION_KINDS:
            raise ValueError(f"unsupported execution kind: {self.kind!r}")
        if self.status not in EXECUTION_STATUSES:
            raise ValueError(f"unsupported execution status: {self.status!r}")
        if self.artifact_status not in ARTIFACT_STATUSES:
            raise ValueError(f"unsupported artifact_status: {self.artifact_status!r}")


@dataclass(frozen=True)
class InvestigationState(_DataModel):
    investigation_id: str
    contract: ResearchContract
    status: str
    execution_ids: tuple[str, ...]
    completed_runs: int
    total_runs: int
    artifact_status: str
    next_action: str
    revision: int
    created_at: str
    updated_at: str
    active_execution_id: str | None = None
    trial_id: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status not in EXECUTION_STATUSES:
            raise ValueError(f"unsupported investigation status: {self.status!r}")
        if self.artifact_status not in ARTIFACT_STATUSES:
            raise ValueError(f"unsupported artifact_status: {self.artifact_status!r}")


@dataclass(frozen=True)
class ClaimSubmissionResult(_DataModel):
    status: str
    claim: Claim | None = None
    report: dict[str, Any] | None = None
    execution: ExecutionRecord | None = None
    error: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status not in CLAIM_SUBMISSION_STATUSES:
            raise ValueError(f"unsupported claim submission status: {self.status!r}")


@dataclass(frozen=True)
class WorldlineSpec(_DataModel):
    """单条脚本化世界线声明（worldline-v1 输入契约）。

    世界线 = 声明轨迹：build/stage 完全确定队伍与关卡，random_values 固定整条
    随机序列，initial_sp/initial_energy_ratio 固定开局资源。policy.mode 必须
    是 "scripted"——世界线不是策略搜索，是逐决策声明的确定性重放。
    """

    build: Mapping
    stage: Mapping
    random_values: tuple[float, ...]
    initial_sp: int | None = None
    initial_energy_ratio: float | None = None
    derived_from: Mapping | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.build, Mapping) or "build" not in self.build:
            raise ValueError("WorldlineSpec build 必须是含 'build' 键的 mapping")
        inner = self.build["build"]
        if not isinstance(inner, Mapping):
            raise ValueError("WorldlineSpec build['build'] 必须是 mapping")
        policy = inner.get("policy")
        if not isinstance(policy, Mapping) or policy.get("mode") != "scripted":
            raise ValueError(
                "世界线要求 build['build']['policy']['mode'] == 'scripted'"
                "（世界线是声明轨迹，非 scripted 策略拒收）"
            )
        if not isinstance(self.random_values, tuple):
            raise ValueError("WorldlineSpec random_values 必须是元组")
        normalized = []
        for index, value in enumerate(self.random_values):
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"随机脚本[{index}] 须为实数，实得 {value!r}")
            number = float(value)
            if not math.isfinite(number) or not 0.0 <= number < 1.0:
                raise ValueError(f"随机脚本[{index}] 须满足 0 <= value < 1，实得 {value!r}")
            normalized.append(number)
        # 归一化为 float：canonical JSON 里 0 与 0.0 字节不同，归一化保证身份稳定
        object.__setattr__(self, "random_values", tuple(normalized))
        _validate_derived_from(self.derived_from)

    @property
    def spec_hash(self) -> str:
        """声明内容的 canonical 内容哈希（发布与读时重算共用）。"""
        return content_hash(self)


def _validate_derived_from(derived_from: Mapping | None) -> None:
    """derived_from 形状闸：闭集键 + 两项 64 位小写 hex + 可选 str note。

    此处只验形状不验存在性/血缘——self-parent 与成环由 store 读侧拦截，
    父代是否真实存在同样属于读取期事实而非构造期事实。
    """
    if derived_from is None:
        return
    if not isinstance(derived_from, Mapping):
        raise ValueError("WorldlineSpec derived_from 必须是 mapping 或 None")
    unknown = set(derived_from) - _DERIVED_FROM_KEYS
    if unknown:
        raise ValueError(
            f"derived_from 只允许 worldline_id/content_hash/note 键，实得 {sorted(unknown)}"
        )
    for key in ("worldline_id", "content_hash"):
        value = derived_from.get(key)
        if not isinstance(value, str) or not _DERIVED_FROM_ID_RE.fullmatch(value):
            raise ValueError(
                f"derived_from.{key} 必须是 64 位小写十六进制 SHA-256，实得 {value!r}"
            )
    note = derived_from.get("note")
    if note is not None and not isinstance(note, str):
        raise TypeError(f"derived_from.note 必须是字符串，实得 {note!r}")


@dataclass(frozen=True)
class WorldlineArtifact(_DataModel):
    """单世界线执行证据（worldline-v1）。

    成功与失败都会发布并存留；读取时 store 重算身份、字节哈希与
    observed/final_save 交叉证据，篡改即拒。completed 要求保留 final_save
    且无 failure_reasons；failed 要求 final_save 为 None 且 failure_reasons
    非空。
    """

    worldline_id: str
    spec: WorldlineSpec
    fingerprint: Mapping
    status: str
    observed: Mapping
    events: tuple[Mapping, ...]
    final_save: Mapping | None
    modifiers: tuple[Mapping, ...]
    caveats: tuple[str, ...]
    failure_reasons: tuple[str, ...]
    schema_version: str = WORLDLINE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.schema_version != WORLDLINE_SCHEMA_VERSION:
            raise ValueError(f"unsupported worldline schema_version: {self.schema_version!r}")
        if self.status not in WORLDLINE_STATUSES:
            raise ValueError(f"unsupported WorldlineArtifact status: {self.status!r}")
        if self.status == "completed":
            if not isinstance(self.final_save, Mapping) or not self.final_save:
                raise ValueError("completed 世界线必须保留非空 final_save")
            if self.failure_reasons:
                raise ValueError("completed 世界线不得携带 failure_reasons")
        else:
            if self.final_save is not None:
                raise ValueError("failed 世界线不得保留 final_save")
            if not self.failure_reasons:
                raise ValueError("failed 世界线必须记录 failure_reasons")
