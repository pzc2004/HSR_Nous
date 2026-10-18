"""Research contract tests' shared pure-Python builders."""

from __future__ import annotations

from typing import Any

from hsr_nous.research_schema import (
    ExperimentArm,
    ExperimentSpec,
    MechanismPatch,
    MetricSpec,
    ResearchContract,
    VersionFingerprint,
)


def make_patch(**changes: Any) -> MechanismPatch:
    values: dict[str, Any] = {
        "template_kind": "characters",
        "template_id": "1202",
        "path": ("base_stats", "atk"),
        "value": 600.0,
    }
    values.update(changes)
    return MechanismPatch(**values)


def make_contract(
    *,
    protocol_id: str = "paired-v1",
    budget: dict[str, Any] | None = None,
    baseline: ExperimentArm | None = None,
    variant: ExperimentArm | None = None,
    metric: MetricSpec | None = None,
    build: dict[str, Any] | None = None,
    stage: dict[str, Any] | None = None,
) -> ResearchContract:
    if build is None:
        build = {"characters": [{"id": "1202"}], "policy": {"name": "fixed"}}
    if stage is None:
        stage = {"enemies": [{"id": "1001"}], "waves": [1]}
    if baseline is None:
        baseline = ExperimentArm(arm_id="baseline", world="canonical")
    if variant is None:
        variant = ExperimentArm(
            arm_id="variant", world="hypothetical", patches=(make_patch(),)
        )
    return ResearchContract(
        contract_id="contract-1",
        question="Does the declared ATK change increase simulated total damage?",
        protocol_id=protocol_id,
        experiment=ExperimentSpec(
            spec_id="experiment-1",
            build=build,
            stage=stage,
            baseline=baseline,
            variant=variant,
            metric=metric or MetricSpec(),
        ),
        budget=dict(budget) if budget is not None else {"max_runs": 64},
    )


def make_templates() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "characters": {
            "1202": {
                "id": "1202",
                "type": "character",
                "base_stats": {"atk": 529.2},
                "values": [1.0],
            }
        }
    }


def make_fingerprint(**changes: Any) -> VersionFingerprint:
    values: dict[str, Any] = {
        "rulebook_hash": "rulebook-sha",
        "fixtures_hash": "fixtures-sha",
        "data_hash": "data-sha",
        "policy_hash": "policy-sha",
        "implementation_hash": "implementation-sha",
        "config_hash": "config-sha",
        "variant_hash": "variant-sha",
        "protocol_id": "paired-v1",
        "artifact_schema_version": "1",
        "git_commit": None,
    }
    values.update(changes)
    return VersionFingerprint(**values)
