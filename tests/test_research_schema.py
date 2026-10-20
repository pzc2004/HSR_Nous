from __future__ import annotations

import hashlib
import json
import math
from dataclasses import FrozenInstanceError, dataclass, replace

import pytest

from hsr_nous.research.schema import (
    CLAIM_STATUSES,
    Claim,
    EvidenceLink,
    MetricSpec,
    ResearchContract,
    RunRecord,
    canonical_bytes,
    canonical_json,
    canonical_round,
    content_hash,
)
from tests._research_builders import make_contract


def test_canonical_json_sorts_keys_and_preserves_unicode():
    assert canonical_bytes({"b": 1, "a": "停云"}) == '{"a":"停云","b":1}'.encode()


def test_canonical_json_supports_nested_dataclasses_and_tuples():
    @dataclass(frozen=True)
    class Nested:
        values: tuple[int, ...]

    assert canonical_json({"outer": Nested((1, 2))}) == '{"outer":{"values":[1,2]}}'


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_numbers(value):
    with pytest.raises(ValueError, match="finite"):
        canonical_json({"nested": [value]})


def test_canonical_json_rejects_unknown_types_without_string_coercion():
    with pytest.raises(TypeError, match="unsupported"):
        canonical_json({"value": object()})


def test_content_hash_uses_canonical_bytes():
    assert content_hash({"b": 2, "a": 1}) == hashlib.sha256(b'{"a":1,"b":2}').hexdigest()


def test_canonical_round_is_separate_from_raw_storage():
    raw = {"values": [1.23456789, 2]}
    assert canonical_round(raw) == {"values": [1.234568, 2]}
    assert json.loads(canonical_json(raw)) == raw


def test_contract_round_trip_and_unknown_field_rejection():
    contract = make_contract()
    payload = contract.to_dict()
    assert ResearchContract.from_dict(payload) == contract

    payload["seed0"] = 99
    with pytest.raises(ValueError, match="unknown fields"):
        ResearchContract.from_dict(payload)


def test_contract_copies_and_recursively_freezes_nested_data():
    build = {"characters": [{"id": "1202"}], "policy": {"rules": ["basic"]}}
    budget = {"max_runs": 64}
    contract = make_contract(build=build, budget=budget)

    build["characters"][0]["id"] = "changed"
    build["policy"]["rules"].append("skill")
    budget["max_runs"] = 1
    assert contract.experiment.build["characters"][0]["id"] == "1202"
    assert contract.experiment.build["policy"]["rules"] == ("basic",)
    assert contract.budget == {"max_runs": 64}

    with pytest.raises(TypeError):
        contract.experiment.build["x"] = "forbidden"
    with pytest.raises(TypeError):
        contract.experiment.build["characters"][0]["id"] = "forbidden"
    with pytest.raises(TypeError):
        contract.budget["max_runs"] = 100

    payload = contract.to_dict()
    assert type(payload["experiment"]["build"]) is dict
    assert type(payload["experiment"]["build"]["characters"]) is list
    payload["experiment"]["build"]["characters"][0]["id"] = "also-changed"
    assert contract.experiment.build["characters"][0]["id"] == "1202"


def test_models_are_frozen():
    contract = make_contract()
    with pytest.raises(FrozenInstanceError):
        contract.contract_id = "changed"


def _claim(status: str = "accepted") -> Claim:
    return Claim(
        claim_id="claim-1",
        trial_id="trial-1",
        comparison_set_id="comparison-1",
        subject="variant",
        metric=MetricSpec(),
        relation="higher_than_baseline",
        status=status,
        premises=(
            EvidenceLink(trial_id="trial-1", artifact_hash="artifact-sha"),
        ),
        derivation_steps=({"operation": "paired_mean_difference"},),
        statistical_metadata={"holdout_n": 16},
        scope={"world": "hypothetical", "source": "simulated"},
    )


def test_claim_status_vocabulary():
    assert CLAIM_STATUSES == frozenset({"accepted", "rejected", "inconclusive", "stale"})
    for status in CLAIM_STATUSES:
        assert _claim(status).status == status
    with pytest.raises(ValueError, match="status"):
        _claim("negative")


def test_other_fixed_vocabularies():
    with pytest.raises(ValueError, match="source_type"):
        EvidenceLink(
            trial_id="trial-1", artifact_hash="sha", source_type="observed"
        )

    values = {
        "run_id": "run-1",
        "trial_id": "trial-1",
        "arm_id": "baseline",
        "cohort": "dev",
        "seed": 0,
        "status": "completed",
        "observed": {},
        "events": (),
        "final_save": {},
        "modifiers": (),
        "content_hash": "sha",
    }
    assert RunRecord(**values).kind == "recorded"
    with pytest.raises(ValueError, match="kind"):
        RunRecord(**values, kind="replayed")


def test_claim_round_trip():
    claim = replace(_claim(), status="inconclusive", failure_reason="CI contains zero")
    assert Claim.from_dict(claim.to_dict()) == claim


def test_trial_artifact_structured_caveats_round_trip():
    from hsr_nous.research.schema import ComparisonSet, TrialArtifact
    from tests._research_builders import make_fingerprint

    artifact = TrialArtifact(
        trial_id="trial-1",
        spec=make_contract(),
        resolved_protocol={"protocol_id": "paired-v1"},
        fingerprint=make_fingerprint(),
        comparison_set=ComparisonSet(
            comparison_set_id="comparison-1",
            baseline_dev=("baseline-dev-0",),
            baseline_holdout=("baseline-holdout-0",),
            variant_dev=("variant-dev-0",),
            variant_holdout=("variant-holdout-0",),
        ),
        run_ids=("baseline-dev-0", "variant-dev-0"),
        status="completed",
        caveats=({
            "actor": "1202",
            "text": "Approximate mechanic",
            "level": "warning",
            "source": "sim/compile",
        },),
    )

    payload = artifact.to_dict()
    assert type(payload["caveats"]) is list
    assert type(payload["caveats"][0]) is dict
    assert TrialArtifact.from_dict(payload) == artifact


def test_configuration_override_round_trip_and_recursive_freeze():
    from tests._research_builders import make_acheron_feet_contract, make_demo_contract

    contract = make_acheron_feet_contract()
    assert contract.experiment.comparison_kind == "configuration"
    assert ResearchContract.from_dict(contract.to_dict()) == contract
    with pytest.raises(TypeError):
        contract.experiment.variant.build_override["build"]["team"][0]["relics"]["feet"]["main"] = "spd"
    with pytest.raises(TypeError):
        contract.experiment.variant.build_override["new"] = "forbidden"

    mechanism = make_demo_contract()
    assert mechanism.experiment.comparison_kind == "mechanism"
    assert mechanism.experiment.variant.build_override is None
