"""Execution-independent validation for research contracts."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from hsr_nous.research.protocol.profiles import ResolvedProtocol, get_profile
from hsr_nous.research.schema import (
    CandidateSet,
    ExperimentArm,
    ExperimentSpec,
    MechanismPatch,
    MetricSpec,
    ResearchContract,
    VersionFingerprint,
    canonical_json,
)


class ProtocolValidationError(ValueError):
    """The caller requested an experiment outside the registered protocol."""


_TEMPLATE_KINDS = frozenset({"characters", "light_cones", "relics", "enemies"})
_TEMPLATE_ID_RE = re.compile(r"[A-Za-z0-9_-]+\Z")


def resolve_protocol(protocol_id: str) -> ResolvedProtocol:
    if not isinstance(protocol_id, str):
        raise ProtocolValidationError("protocol_id must name a registered profile")
    try:
        return get_profile(protocol_id)
    except KeyError as exc:
        raise ProtocolValidationError(f"unknown protocol_id: {protocol_id!r}") from exc


def _validate_budget(contract: ResearchContract, resolved: ResolvedProtocol) -> None:
    if not isinstance(contract.budget, Mapping) or set(contract.budget) != {"max_runs"}:
        raise ProtocolValidationError("budget must contain only max_runs")
    max_runs = contract.budget["max_runs"]
    if isinstance(max_runs, bool) or not isinstance(max_runs, int):
        raise ProtocolValidationError("budget max_runs must be an integer")
    if max_runs < resolved.required_runs:
        raise ProtocolValidationError(
            f"budget max_runs={max_runs} is below required_runs={resolved.required_runs}"
        )


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def _validate_metric(metric: MetricSpec, resolved: ResolvedProtocol) -> None:
    if not isinstance(metric, MetricSpec):
        raise ProtocolValidationError("metric must be a MetricSpec")
    expected = MetricSpec(confidence=resolved.confidence)
    for name in ("metric_id", "statistic", "confidence", "direction"):
        if getattr(metric, name) != getattr(expected, name):
            raise ProtocolValidationError(f"unsupported metric {name}: {getattr(metric, name)!r}")


def _template_for_patch(
    templates: Mapping[str, Mapping[str, Any]] | None,
    patch: MechanismPatch,
) -> Any:
    if templates is None:
        raise ProtocolValidationError("template data is required to validate patches")
    try:
        return templates[patch.template_kind][patch.template_id]
    except (KeyError, TypeError) as exc:
        raise ProtocolValidationError(
            f"template {patch.template_kind}/{patch.template_id} was not found"
        ) from exc


def _original_value(template: Any, patch: MechanismPatch) -> Any:
    current = template
    for component in patch.path:
        if isinstance(current, Mapping):
            if not isinstance(component, str) or component not in current:
                raise ProtocolValidationError(f"patch path does not exist: {patch.path!r}")
        elif isinstance(current, (list, tuple)):
            if (isinstance(component, bool) or not isinstance(component, int)
                    or not 0 <= component < len(current)):
                raise ProtocolValidationError(f"patch path does not exist: {patch.path!r}")
        else:
            raise ProtocolValidationError(f"patch path does not exist: {patch.path!r}")
        current = current[component]
    return current


def validate_patch_reference(patch: MechanismPatch) -> MechanismPatch:
    """Validate the loader-independent patch reference before any filesystem access."""
    if not isinstance(patch, MechanismPatch):
        raise ProtocolValidationError("patches must be MechanismPatch instances")
    if patch.op != "set_number":
        raise ProtocolValidationError(f"unsupported patch op: {patch.op!r}")
    if not isinstance(patch.template_kind, str) or not patch.template_kind:
        raise ProtocolValidationError("patch template_kind must be a non-empty string")
    if patch.template_kind not in _TEMPLATE_KINDS:
        raise ProtocolValidationError(f"unsupported patch template_kind: {patch.template_kind!r}")
    if not isinstance(patch.template_id, str) or not _TEMPLATE_ID_RE.fullmatch(patch.template_id):
        raise ProtocolValidationError("patch template_id must match [A-Za-z0-9_-]+")
    if not isinstance(patch.path, tuple) or not patch.path:
        raise ProtocolValidationError("patch path must be a non-empty tuple")
    for component in patch.path:
        if isinstance(component, bool) or not isinstance(component, (str, int)):
            raise ProtocolValidationError("patch path components must be strings or integers")
        if isinstance(component, str) and (
            component in {"id", "type"}
            or component.endswith("_id")
            or component.endswith("_type")
        ):
            raise ProtocolValidationError("patch cannot modify ID or type fields")
    if not _is_finite_number(patch.value):
        raise ProtocolValidationError("patch value must be a finite number and not bool")
    return patch


def _validate_patch(
    patch: MechanismPatch,
    templates: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    validate_patch_reference(patch)
    original = _original_value(_template_for_patch(templates, patch), patch)
    if not _is_finite_number(original):
        raise ProtocolValidationError(
            "original value at the patch path must be a finite number and not bool"
        )


def _validate_experiment(
    experiment: ExperimentSpec,
    resolved: ResolvedProtocol,
    templates: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    if not isinstance(experiment, ExperimentSpec):
        raise ProtocolValidationError("experiment must be an ExperimentSpec")
    if not isinstance(experiment.spec_id, str) or not experiment.spec_id:
        raise ProtocolValidationError("spec_id must be a non-empty string")
    baseline = experiment.baseline
    variant = experiment.variant
    if not isinstance(baseline, ExperimentArm) or not isinstance(variant, ExperimentArm):
        raise ProtocolValidationError("baseline and variant must be ExperimentArm instances")
    if any(not isinstance(arm.arm_id, str) or not arm.arm_id for arm in (baseline, variant)):
        raise ProtocolValidationError("baseline and variant arm_id must be non-empty strings")
    if baseline.arm_id == variant.arm_id:
        raise ProtocolValidationError("baseline and variant arm_id must be distinct")
    if experiment.comparison_kind not in {"mechanism", "configuration"}:
        raise ProtocolValidationError(
            f"unsupported comparison_kind: {experiment.comparison_kind!r}"
        )
    if baseline.world != "canonical":
        raise ProtocolValidationError("baseline world must be canonical")
    if baseline.patches:
        raise ProtocolValidationError("canonical arm cannot carry patches")
    if baseline.build_override is not None:
        raise ProtocolValidationError("baseline cannot carry build_override")

    if experiment.comparison_kind == "mechanism":
        if variant.world != "hypothetical":
            raise ProtocolValidationError("mechanism variant world must be hypothetical")
        if variant.build_override is not None:
            raise ProtocolValidationError("mechanism variant cannot carry build_override")
        if not variant.patches:
            raise ProtocolValidationError("variant.patches must not be empty")
        seen = set()
        for patch in variant.patches:
            _validate_patch(patch, templates)
            key = (patch.template_kind, patch.template_id, patch.path)
            if key in seen:
                raise ProtocolValidationError(f"duplicate patch path: {key!r}")
            seen.add(key)
    else:
        if variant.world != "canonical":
            raise ProtocolValidationError("configuration variant world must be canonical")
        if variant.patches:
            raise ProtocolValidationError("configuration variant cannot carry patches")
        override = variant.build_override
        if not isinstance(override, Mapping) or not override:
            raise ProtocolValidationError("configuration build_override must be non-empty")
        if canonical_json(override) == canonical_json(experiment.build):
            raise ProtocolValidationError("configuration build_override must differ from baseline")
    _validate_metric(experiment.metric, resolved)


def validate_contract(
    contract: ResearchContract,
    *,
    templates: Mapping[str, Mapping[str, Any]] | None = None,
    **overrides: Any,
) -> ResolvedProtocol:
    """Validate a contract and resolve its registered, caller-independent protocol."""
    if overrides:
        names = ", ".join(sorted(overrides))
        raise ProtocolValidationError(
            f"registered protocol parameters are fixed; overrides are not allowed: {names}"
        )
    if not isinstance(contract, ResearchContract):
        raise ProtocolValidationError("contract must be a ResearchContract")
    for name in ("contract_id", "question"):
        value = getattr(contract, name)
        if not isinstance(value, str) or not value:
            raise ProtocolValidationError(f"{name} must be a non-empty string")
    resolved = resolve_protocol(contract.protocol_id)
    _validate_budget(contract, resolved)
    _validate_experiment(contract.experiment, resolved, templates)
    return resolved


def validate_candidate_set(candidate_set: CandidateSet) -> None:
    if not isinstance(candidate_set, CandidateSet):
        raise ProtocolValidationError("candidate_set must be a CandidateSet")
    if len(candidate_set.candidates) > 16:
        raise ProtocolValidationError("CandidateSet supports at most 16 candidates")
    contract_ids = set()
    spec_ids = set()
    documents = set()
    total_runs = 0
    first = candidate_set.candidates[0]
    for contract in candidate_set.candidates:
        if not isinstance(contract, ResearchContract):
            raise ProtocolValidationError("candidates must be ResearchContract instances")
        if contract.question != candidate_set.question:
            raise ProtocolValidationError("all candidates must share the CandidateSet question")
        resolved = resolve_protocol(contract.protocol_id)
        _validate_budget(contract, resolved)
        if contract.contract_id in contract_ids:
            raise ProtocolValidationError(f"duplicate contract_id: {contract.contract_id!r}")
        if contract.experiment.spec_id in spec_ids:
            raise ProtocolValidationError(f"duplicate spec_id: {contract.experiment.spec_id!r}")
        document = canonical_json(contract)
        if document in documents:
            raise ProtocolValidationError("duplicate candidate contract content")
        contract_ids.add(contract.contract_id)
        spec_ids.add(contract.experiment.spec_id)
        documents.add(document)
        if contract.protocol_id != first.protocol_id:
            raise ProtocolValidationError("all candidates must share protocol_id")
        if canonical_json(contract.experiment.build) != canonical_json(first.experiment.build):
            raise ProtocolValidationError("all candidates must share build")
        if canonical_json(contract.experiment.stage) != canonical_json(first.experiment.stage):
            raise ProtocolValidationError("all candidates must share stage")
        if contract.experiment.baseline != first.experiment.baseline:
            raise ProtocolValidationError("all candidates must share baseline")
        if contract.experiment.metric != first.experiment.metric:
            raise ProtocolValidationError("all candidates must share metric")
        if contract.experiment.comparison_kind != first.experiment.comparison_kind:
            raise ProtocolValidationError("all candidates must share comparison_kind")
        if canonical_json(contract.budget) != canonical_json(first.budget):
            raise ProtocolValidationError("all candidates must share budget")
        total_runs += contract.budget["max_runs"]
    if total_runs > 1024:
        raise ProtocolValidationError("CandidateSet total run budget exceeds 1024")


def validate_fingerprint(
    fingerprint: VersionFingerprint | None,
    *,
    protocol_id: str,
) -> VersionFingerprint:
    """Reject execution identities missing required content bindings."""
    if not isinstance(fingerprint, VersionFingerprint):
        raise ProtocolValidationError("a complete fingerprint is required")
    required = (
        "rulebook_hash",
        "fixtures_hash",
        "data_hash",
        "implementation_hash",
        "config_hash",
        "protocol_id",
        "artifact_schema_version",
    )
    for name in required:
        value = getattr(fingerprint, name)
        if not isinstance(value, str) or not value:
            raise ProtocolValidationError(f"fingerprint {name} is required")
    if fingerprint.protocol_id != protocol_id:
        raise ProtocolValidationError(
            f"fingerprint protocol_id {fingerprint.protocol_id!r} does not match {protocol_id!r}"
        )
    return fingerprint
