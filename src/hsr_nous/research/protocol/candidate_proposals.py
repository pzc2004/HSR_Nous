"""Deterministically materialize bounded candidate sets from agent proposals."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from hsr_nous.research.protocol.validation import (
    ProtocolValidationError,
    validate_candidate_set,
    validate_patch_reference,
)
from hsr_nous.research.schema import (
    CandidateEdit,
    CandidateProposal,
    CandidateRule,
    CandidateSet,
    CandidateSpace,
    ExperimentArm,
    MechanismPatch,
    canonical_json,
)

_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and (not isinstance(value, float) or math.isfinite(value))
    )


def _json_value(value: Any) -> Any:
    try:
        return json.loads(canonical_json(value))
    except (TypeError, ValueError) as error:
        raise ProtocolValidationError(f"proposal values must be finite JSON: {error}") from error


def _rule_value(rule: CandidateRule, value: Any, *, mechanism: bool) -> Any:
    if mechanism:
        if not _finite_number(value):
            raise ProtocolValidationError("mechanism proposal value must be a finite number")
        normalized = float(value)
        try:
            allowed = {canonical_json(float(item)) for item in rule.values}
        except (TypeError, ValueError) as error:
            raise ProtocolValidationError(
                "mechanism rule values must all be finite numbers"
            ) from error
        if any(not _finite_number(item) for item in rule.values):
            raise ProtocolValidationError("mechanism rule values must all be finite numbers")
        if canonical_json(normalized) not in allowed:
            raise ProtocolValidationError("proposal value is outside the rule value domain")
        return normalized

    normalized = _json_value(value)
    try:
        allowed = {canonical_json(item) for item in rule.values}
    except (TypeError, ValueError) as error:
        raise ProtocolValidationError("configuration rule values must be finite JSON") from error
    if canonical_json(normalized) not in allowed:
        raise ProtocolValidationError("proposal value is outside the rule value domain")
    return normalized


def _location(document: Any, path: tuple[str | int, ...]) -> tuple[Any, str | int]:
    current = document
    for index, component in enumerate(path):
        if isinstance(current, Mapping):
            if not isinstance(component, str) or component not in current:
                raise ProtocolValidationError(f"configuration path does not exist: {path!r}")
        elif isinstance(current, list):
            if (isinstance(component, bool) or not isinstance(component, int)
                    or not 0 <= component < len(current)):
                raise ProtocolValidationError(f"configuration path does not exist: {path!r}")
        else:
            raise ProtocolValidationError(f"configuration path does not exist: {path!r}")
        if index == len(path) - 1:
            return current, component
        current = current[component]
    raise ProtocolValidationError("configuration path must not be empty")


def _compatible(original: Any, value: Any) -> bool:
    if original is None:
        return value is None
    if isinstance(original, bool):
        return isinstance(value, bool)
    if isinstance(original, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(original, float):
        return _finite_number(value)
    if isinstance(original, str):
        return isinstance(value, str)
    if isinstance(original, dict):
        return isinstance(value, dict)
    if isinstance(original, list):
        return isinstance(value, list)
    return False


def _proposal_edits(proposal: CandidateProposal) -> tuple[CandidateEdit, ...]:
    if proposal.edits:
        return proposal.edits
    return (CandidateEdit(path=proposal.path, value=proposal.value),)


def _apply_configuration_edit(
    baseline: dict[str, Any],
    override: dict[str, Any],
    path: tuple[str | int, ...],
    value: Any,
) -> dict[str, Any]:
    original_parent, original_key = _location(_json_value(baseline), path)
    original = original_parent[original_key]
    if not _compatible(original, value):
        raise ProtocolValidationError(
            f"configuration proposal type does not match the baseline at {path!r}"
        )
    normalized = float(value) if isinstance(original, float) else value
    if canonical_json(normalized) == canonical_json(original):
        raise ProtocolValidationError("configuration proposal must not be a no-op")
    parent, key = _location(override, path)
    parent[key] = normalized
    return override


class CandidateGenerator:
    @staticmethod
    def build_candidate_set(
        space: CandidateSpace,
        proposals: Sequence[CandidateProposal],
    ) -> CandidateSet:
        if not isinstance(space, CandidateSpace):
            raise ProtocolValidationError("space must be a CandidateSpace")
        if not isinstance(proposals, (list, tuple)) or any(
            not isinstance(proposal, CandidateProposal) for proposal in proposals
        ):
            raise ProtocolValidationError("proposals must be a sequence of CandidateProposal")
        if not 2 <= len(proposals) <= space.max_candidates:
            raise ProtocolValidationError(
                f"proposal count must be between 2 and {space.max_candidates}"
            )

        base = space.base_contract
        experiment = base.experiment
        mechanism = experiment.comparison_kind == "mechanism"
        if not mechanism and experiment.comparison_kind != "configuration":
            raise ProtocolValidationError(
                f"unsupported comparison_kind: {experiment.comparison_kind!r}"
            )
        rules = {rule.path: rule for rule in space.rules}
        for rule in rules.values():
            if mechanism and (rule.template_kind is None or rule.template_id is None):
                raise ProtocolValidationError("mechanism rules require template identity")
            if not mechanism and (rule.template_kind is not None or rule.template_id is not None):
                raise ProtocolValidationError("configuration rules cannot carry template identity")
            if mechanism:
                validate_patch_reference(MechanismPatch(
                    template_kind=rule.template_kind,
                    template_id=rule.template_id,
                    path=rule.path,
                    value=0.0,
                ))
                if any(not _finite_number(value) for value in rule.values):
                    raise ProtocolValidationError(
                        "mechanism rule values must all be finite numbers"
                    )
            else:
                _json_value(rule.values)

        seen = set()
        labels = set()
        candidates = []
        for index, proposal in enumerate(proposals):
            edits = _proposal_edits(proposal)
            resolved_edits = []
            paths = set()
            for edit in edits:
                if edit.path in paths:
                    raise ProtocolValidationError(
                        f"duplicate edit path within one candidate: {edit.path!r}"
                    )
                paths.add(edit.path)
                rule = rules.get(edit.path)
                if rule is None:
                    raise ProtocolValidationError(f"proposal path is not allowed: {edit.path!r}")
                value = _rule_value(rule, edit.value, mechanism=mechanism)
                resolved_edits.append((edit.path, value, rule))
            identity = tuple(
                (path, canonical_json(value)) for path, value, _rule in resolved_edits
            )
            if identity in seen:
                raise ProtocolValidationError("duplicate proposal edits")
            seen.add(identity)
            label = proposal.label or f"candidate-{index}"
            if not _LABEL_RE.fullmatch(label):
                raise ProtocolValidationError(f"invalid candidate label: {label!r}")
            if label in labels:
                raise ProtocolValidationError(f"duplicate candidate label: {label!r}")
            labels.add(label)

            if mechanism:
                variant = ExperimentArm(
                    arm_id=experiment.variant.arm_id,
                    world="hypothetical",
                    patches=tuple(
                        MechanismPatch(
                            template_kind=rule.template_kind,
                            template_id=rule.template_id,
                            path=path,
                            value=value,
                        )
                        for path, value, rule in resolved_edits
                    ),
                )
            else:
                override = _json_value(experiment.build)
                for path, value, _rule in resolved_edits:
                    override = _apply_configuration_edit(
                        experiment.build, override, path, value
                    )
                variant = ExperimentArm(
                    arm_id=experiment.variant.arm_id,
                    world="canonical",
                    build_override=override,
                )
            candidates.append(replace(
                base,
                contract_id=label,
                experiment=replace(experiment, spec_id=label, variant=variant),
            ))

        try:
            candidate_set = CandidateSet(question=base.question, candidates=tuple(candidates))
        except ValueError as error:
            raise ProtocolValidationError(str(error)) from error
        validate_candidate_set(candidate_set)
        return candidate_set
