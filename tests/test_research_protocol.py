from __future__ import annotations

import math
from dataclasses import replace

import pytest

from hsr_nous.research_protocol import (
    PAIRED_V1,
    ProtocolValidationError,
    resolve_protocol,
    validate_contract,
    validate_fingerprint,
)
from hsr_nous.research_schema import ExperimentArm
from tests._research_builders import (
    make_contract,
    make_fingerprint,
    make_patch,
    make_templates,
)


def _valid(contract=None):
    return validate_contract(contract or make_contract(), templates=make_templates())


def _with_variant(contract, **changes):
    variant = replace(contract.experiment.variant, **changes)
    return replace(contract, experiment=replace(contract.experiment, variant=variant))


def test_paired_v1_is_fully_fixed():
    resolved = resolve_protocol("paired-v1")
    assert resolved is PAIRED_V1
    assert resolved.mode == "roll"
    assert resolved.dev_seeds == tuple(range(16))
    assert resolved.holdout_seeds == tuple(range(16, 32))
    assert set(resolved.dev_seeds).isdisjoint(resolved.holdout_seeds)
    assert resolved.min_valid_n == 16
    assert resolved.bootstrap_resamples == 2000
    assert resolved.confidence == 0.95
    assert resolved.bootstrap_seed == 0
    assert resolved.required_runs == 64


def test_larger_budget_does_not_change_the_protocol():
    contract = replace(make_contract(), budget={"max_runs": 100})
    assert _valid(contract) == PAIRED_V1


def test_unknown_protocol_is_rejected():
    with pytest.raises(ProtocolValidationError, match="protocol_id"):
        _valid(make_contract(protocol_id="custom-v1"))


@pytest.mark.parametrize(
    "override",
    [
        {"seed": 7},
        {"seed0": 7},
        {"dev_seeds": tuple(range(16))},
        {"holdout_seeds": tuple(range(100, 116))},
        {"bootstrap_seed": 7},
        {"bootstrap_resamples": 20},
    ],
)
def test_caller_cannot_override_protocol_randomness(override):
    with pytest.raises(ProtocolValidationError, match="fixed"):
        validate_contract(make_contract(), templates=make_templates(), **override)


def test_resolved_protocol_rejects_missing_or_overlapping_cohorts():
    with pytest.raises(ValueError, match="dev_seeds"):
        replace(PAIRED_V1, dev_seeds=())
    with pytest.raises(ValueError, match="holdout_seeds"):
        replace(PAIRED_V1, holdout_seeds=())
    with pytest.raises(ValueError, match="disjoint"):
        replace(PAIRED_V1, holdout_seeds=PAIRED_V1.dev_seeds)


@pytest.mark.parametrize(
    "budget",
    [
        {"max_runs": 63},
        {"max_runs": True},
        {"max_runs": 64.0},
        {"max_runs": 64, "timeout": 10},
        {},
    ],
)
def test_budget_must_cover_exactly_the_supported_run_budget(budget):
    with pytest.raises(ProtocolValidationError, match="budget|max_runs"):
        _valid(replace(make_contract(), budget=budget))


def test_arm_worlds_and_single_baseline_variant_contract_are_enforced():
    contract = make_contract()
    with pytest.raises(ProtocolValidationError, match="canonical"):
        _valid(replace(contract, experiment=replace(
            contract.experiment,
            baseline=ExperimentArm("baseline", "hypothetical"),
        )))
    with pytest.raises(ProtocolValidationError, match="hypothetical"):
        _valid(_with_variant(contract, world="canonical"))
    with pytest.raises(ProtocolValidationError, match="canonical arm"):
        _valid(replace(contract, experiment=replace(
            contract.experiment,
            baseline=ExperimentArm("baseline", "canonical", (make_patch(),)),
        )))
    with pytest.raises(ProtocolValidationError, match="distinct"):
        _valid(_with_variant(contract, arm_id="baseline"))


def test_valid_patch_can_read_an_existing_list_number_without_adding_items():
    contract = _with_variant(
        make_contract(), patches=(make_patch(path=("values", 0), value=2.0),)
    )
    assert _valid(contract) == PAIRED_V1


@pytest.mark.parametrize(
    "patch",
    [
        make_patch(op="delete"),
        make_patch(path=("base_stats", "missing"), value=1.0),
        make_patch(path=("values", 1), value=2.0),
        make_patch(path=("id",), value=1203),
        make_patch(path=(), value=1.0),
        make_patch(value=True),
        make_patch(value="600"),
        make_patch(value=math.nan),
        make_patch(value=math.inf),
    ],
)
def test_invalid_patches_are_rejected(patch):
    with pytest.raises(ProtocolValidationError):
        _valid(_with_variant(make_contract(), patches=(patch,)))


def test_duplicate_patch_path_is_rejected():
    patch = make_patch()
    with pytest.raises(ProtocolValidationError, match="duplicate"):
        _valid(_with_variant(make_contract(), patches=(patch, patch)))


def test_non_finite_or_non_numeric_original_patch_value_is_rejected():
    for original in (math.nan, math.inf, True, "529.2"):
        templates = make_templates()
        templates["characters"]["1202"]["base_stats"]["atk"] = original
        with pytest.raises(ProtocolValidationError, match="original"):
            validate_contract(make_contract(), templates=templates)


def test_patch_requires_template_evidence():
    with pytest.raises(ProtocolValidationError, match="template"):
        validate_contract(make_contract())
    with pytest.raises(ProtocolValidationError, match="template"):
        validate_contract(make_contract(), templates={})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("metric_id", "dps"),
        ("statistic", "mean_difference"),
        ("confidence", 0.9),
        ("direction", "lower_is_better"),
    ],
)
def test_only_the_paired_total_damage_metric_is_supported(field, value):
    contract = make_contract()
    metric = replace(contract.experiment.metric, **{field: value})
    with pytest.raises(ProtocolValidationError, match="metric"):
        _valid(make_contract(metric=metric))


def test_required_fingerprint_fields_and_protocol_binding():
    fingerprint = make_fingerprint(git_commit=None, variant_hash=None)
    assert validate_fingerprint(fingerprint, protocol_id="paired-v1") is fingerprint

    with pytest.raises(ProtocolValidationError, match="fingerprint"):
        validate_fingerprint(None, protocol_id="paired-v1")
    with pytest.raises(ProtocolValidationError, match="protocol_id"):
        validate_fingerprint(fingerprint, protocol_id="other")

    for field in (
        "rulebook_hash",
        "fixtures_hash",
        "data_hash",
        "implementation_hash",
        "config_hash",
        "artifact_schema_version",
    ):
        with pytest.raises(ProtocolValidationError, match=field):
            validate_fingerprint(
                replace(fingerprint, **{field: None}), protocol_id="paired-v1"
            )


@pytest.mark.parametrize("field", ["dev_seeds", "holdout_seeds"])
def test_resolved_protocol_rejects_duplicate_seeds_within_a_cohort(field):
    seeds = getattr(PAIRED_V1, field)
    duplicated = (seeds[0], *seeds[:-1])
    with pytest.raises(ValueError, match=rf"{field}.*duplicate"):
        replace(PAIRED_V1, **{field: duplicated})


@pytest.mark.parametrize("field", ["contract_id", "question", "spec_id"])
@pytest.mark.parametrize("value", ["", None])
def test_contract_identity_fields_must_be_non_empty_strings(field, value):
    contract = make_contract()
    if field == "spec_id":
        contract = replace(
            contract,
            experiment=replace(contract.experiment, **{field: value}),
        )
    else:
        contract = replace(contract, **{field: value})
    with pytest.raises(ProtocolValidationError, match=field):
        _valid(contract)


def test_variant_must_declare_at_least_one_patch():
    with pytest.raises(ProtocolValidationError, match="variant.patches"):
        _valid(_with_variant(make_contract(), patches=()))


def test_patch_template_kind_is_a_closed_vocabulary():
    with pytest.raises(ProtocolValidationError, match="template_kind"):
        _valid(_with_variant(
            make_contract(), patches=(make_patch(template_kind="weapons"),)
        ))

    for kind in ("characters", "light_cones", "relics", "enemies"):
        patch = make_patch(
            template_kind=kind,
            template_id="entity",
            path=("value",),
            value=2.0,
        )
        contract = _with_variant(make_contract(), patches=(patch,))
        templates = {kind: {"entity": {"value": 1.0}}}
        assert validate_contract(contract, templates=templates) == PAIRED_V1


def test_patch_reference_validation_is_public_and_does_not_need_templates():
    from hsr_nous.research_protocol import validate_patch_reference

    assert validate_patch_reference(make_patch()) == make_patch()
    for template_id in ("../1202", "*", "with/slash", "with space"):
        with pytest.raises(ProtocolValidationError, match="template_id"):
            validate_patch_reference(make_patch(template_id=template_id))


def test_protocol_doc_matches_paired_v1():
    from pathlib import Path

    text = (
        Path(__file__).parent.parent
        / "src/hsr_nous/research_schema/docs/02_protocol.md"
    ).read_text(encoding="utf-8")
    dev = PAIRED_V1.dev_seeds
    holdout = PAIRED_V1.holdout_seeds
    assert f"dev seed 为 `{dev[0]}..{dev[-1]}`" in text
    assert f"holdout seed 为 `{holdout[0]}..{holdout[-1]}`" in text
    assert f"`min_valid_n={PAIRED_V1.min_valid_n}`" in text
    assert f"`required_runs={PAIRED_V1.required_runs}`" in text
    assert f"| `bootstrap_resamples` | {PAIRED_V1.bootstrap_resamples} |" in text
    assert f"| `confidence` | {PAIRED_V1.confidence} |" in text
    assert f"| `bootstrap_seed` | {PAIRED_V1.bootstrap_seed} |" in text


def test_configuration_contract_combinations():
    from tests._research_builders import make_acheron_feet_contract, make_demo_contract

    contract = make_acheron_feet_contract()
    assert validate_contract(contract) == PAIRED_V1

    with pytest.raises(ProtocolValidationError, match="comparison_kind"):
        _valid(replace(
            contract,
            experiment=replace(contract.experiment, comparison_kind="other"),
        ))
    with pytest.raises(ProtocolValidationError, match="canonical"):
        _valid(_with_variant(contract, world="hypothetical"))
    with pytest.raises(ProtocolValidationError, match="patches"):
        _valid(_with_variant(contract, patches=(make_patch(),)))
    with pytest.raises(ProtocolValidationError, match="non-empty"):
        _valid(_with_variant(contract, build_override={}))
    with pytest.raises(ProtocolValidationError, match="differ"):
        _valid(_with_variant(contract, build_override=contract.experiment.build))
    with pytest.raises(ProtocolValidationError, match="baseline"):
        _valid(replace(
            contract,
            experiment=replace(
                contract.experiment,
                baseline=ExperimentArm(
                    "baseline", "canonical", build_override={"changed": True}
                ),
            ),
        ))
    with pytest.raises(ProtocolValidationError, match="build_override"):
        _valid(_with_variant(make_demo_contract(), build_override={"changed": True}))
