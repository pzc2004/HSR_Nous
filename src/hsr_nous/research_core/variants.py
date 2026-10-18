"""Validated in-memory mechanism and configuration variants before publication."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from hsr_nous.research_protocol import (
    ResolvedProtocol,
    validate_contract,
    validate_patch_reference,
)
from hsr_nous.research_schema import MechanismPatch, ResearchContract, content_hash
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim_schema.templates import RUNTIME_TEMPLATE_ROOTS


@dataclass(frozen=True)
class PreparedVariant:
    resolved_protocol: ResolvedProtocol
    comparison_kind: str
    world: str
    effective_build: dict[str, Any]
    variant_id: str
    parent_base_hash: str
    variant_hash: str
    hypothesis: str
    patches: tuple[MechanismPatch, ...]
    documents: tuple[dict[str, Any], ...]


class VariantMaterializer:
    """Load through BuildCompiler, validate, then patch copies in memory."""

    def __init__(
        self,
        template_roots: Sequence[str | Path] = RUNTIME_TEMPLATE_ROOTS,
    ) -> None:
        self._template_roots = tuple(str(root) for root in template_roots)

    @property
    def template_roots(self) -> tuple[str, ...]:
        return self._template_roots

    @staticmethod
    def _apply_patch(document: dict[str, Any], patch: MechanismPatch) -> None:
        current = document
        for component in patch.path[:-1]:
            current = current[component]
        current[patch.path[-1]] = patch.value

    def prepare(self, contract: ResearchContract, *, hypothesis: str) -> PreparedVariant:
        if not isinstance(hypothesis, str) or not hypothesis:
            raise ValueError("hypothesis must be a non-empty string")
        experiment = contract.experiment
        arm = experiment.variant
        comparison_kind = experiment.comparison_kind

        def variant_id(parent_hash: str, variant_hash: str) -> str:
            return content_hash({
                "comparison_kind": comparison_kind,
                "world": arm.world,
                "parent_base_hash": parent_hash,
                "variant_hash": variant_hash,
                "patches": arm.patches,
                "hypothesis": hypothesis,
            })

        if comparison_kind == "configuration":
            resolved = validate_contract(contract)
            parent_base_hash = content_hash(experiment.build)
            variant_hash = content_hash(arm.build_override)
            return PreparedVariant(
                resolved_protocol=resolved,
                comparison_kind=comparison_kind,
                world=arm.world,
                effective_build=arm.build_override,
                variant_id=variant_id(parent_base_hash, variant_hash),
                parent_base_hash=parent_base_hash,
                variant_hash=variant_hash,
                hypothesis=hypothesis,
                patches=(),
                documents=(),
            )

        for patch in arm.patches:
            validate_patch_reference(patch)
        keys = []
        for patch in arm.patches:
            key = (patch.template_kind, patch.template_id)
            if key not in keys:
                keys.append(key)
        canonical = {
            key: BuildCompiler.load_template(*key, roots=self._template_roots)
            for key in keys
        }
        templates: dict[str, dict[str, Any]] = {}
        for (kind, template_id), document in canonical.items():
            templates.setdefault(kind, {})[template_id] = document
        resolved = validate_contract(contract, templates=templates)

        modified = {key: deepcopy(document) for key, document in canonical.items()}
        for patch in arm.patches:
            self._apply_patch(modified[(patch.template_kind, patch.template_id)], patch)
        parent_identity = []
        variant_identity = []
        documents = []
        for kind, template_id in keys:
            key = (kind, template_id)
            parent_hash = content_hash(canonical[key])
            variant_hash = content_hash(modified[key])
            parent_identity.append({
                "template_kind": kind,
                "template_id": template_id,
                "content_hash": parent_hash,
            })
            variant_identity.append({
                "template_kind": kind,
                "template_id": template_id,
                "content_hash": variant_hash,
            })
            documents.append({
                "template_kind": kind,
                "template_id": template_id,
                "parent_base_hash": parent_hash,
                "content_hash": variant_hash,
                "canonical": canonical[key],
                "content": modified[key],
            })
        parent_base_hash = content_hash(parent_identity)
        variant_hash = content_hash(variant_identity)
        return PreparedVariant(
            resolved_protocol=resolved,
            comparison_kind=comparison_kind,
            world=arm.world,
            effective_build=experiment.build,
            variant_id=variant_id(parent_base_hash, variant_hash),
            parent_base_hash=parent_base_hash,
            variant_hash=variant_hash,
            hypothesis=hypothesis,
            patches=arm.patches,
            documents=tuple(documents),
        )
