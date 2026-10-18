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
    comparison_kind: str = "mechanism",
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
            comparison_kind=comparison_kind,
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
        "artifact_schema_version": "2",
        "git_commit": None,
    }
    values.update(changes)
    return VersionFingerprint(**values)


def make_demo_contract() -> ResearchContract:
    """Build the formal Tingyun contract from the tracked, read-only battle YAML."""
    import yaml

    from hsr_nous.common import repo_data_dir

    path = repo_data_dir() / "battles" / "demo_停云白板.yaml"
    record = yaml.safe_load(path.read_text(encoding="utf-8"))
    build = yaml.safe_load(record["build_yaml"])
    stage = yaml.safe_load(record["stage_yaml"])
    return make_contract(build=build, stage=stage)


def _demo_parts(name: str):
    import yaml

    from hsr_nous.common import repo_data_dir

    path = repo_data_dir() / "battles" / f"{name}.yaml"
    record = yaml.safe_load(path.read_text(encoding="utf-8"))
    return yaml.safe_load(record["build_yaml"]), yaml.safe_load(record["stage_yaml"])


def make_acheron_feet_contract() -> ResearchContract:
    from copy import deepcopy
    from dataclasses import replace

    build, stage = _demo_parts("demo_黄泉队")
    baseline_build = deepcopy(build)
    override = deepcopy(build)
    baseline_build["build"]["team"][0]["relics"] = {
        "feet": {"set_id": "101", "main": "spd", "subs": {}}
    }
    override["build"]["team"][0]["relics"] = {
        "feet": {"set_id": "101", "main": "atk_pct", "subs": {}}
    }
    contract = make_contract(
        build=baseline_build,
        stage=stage,
        comparison_kind="configuration",
        variant=ExperimentArm(
            arm_id="variant", world="canonical", build_override=override
        ),
    )
    return replace(contract, question="Acheron feet main stat: atk_pct vs spd")


def make_acheron_team_contract() -> ResearchContract:
    from copy import deepcopy
    from dataclasses import replace

    build, stage = _demo_parts("demo_黄泉队")
    override = deepcopy(build)
    override["build"]["team"][1]["character_template"] = "1202"
    contract = make_contract(
        build=build,
        stage=stage,
        comparison_kind="configuration",
        variant=ExperimentArm(
            arm_id="variant", world="canonical", build_override=override
        ),
    )
    return replace(contract, question="Replace Tribbie with Tingyun")


def make_acheron_cipher_contract() -> ResearchContract:
    from copy import deepcopy
    from dataclasses import replace

    build, stage = _demo_parts("demo_黄泉队")
    baseline_build = deepcopy(build)
    baseline_build["build"]["team"] = [
        {"character_template": "1308", "level": 80},
        {"character_template": "1218", "level": 80},
        {"character_template": "1403", "level": 80},
        {"character_template": "1304", "level": 80},
    ]
    override = deepcopy(baseline_build)
    override["build"]["team"][2]["character_template"] = "1406"
    contract = make_contract(
        build=baseline_build,
        stage=stage,
        comparison_kind="configuration",
        variant=ExperimentArm(
            arm_id="variant", world="canonical", build_override=override
        ),
    )
    return replace(
        contract,
        question=(
            "Whiteboard four-person mechanism comparison: "
            "Acheron + Jiaoqiu + Tribbie + Aventurine versus "
            "Acheron + Jiaoqiu + Cipher + Aventurine"
        ),
    )
