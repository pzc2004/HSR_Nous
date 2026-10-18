from __future__ import annotations

import math

import pytest

from hsr_nous.research_core.kernel import (
    build_claim,
    compare,
    confidence_interval,
    distribution,
    mean,
    paired_diff,
    quantile,
    validate_claim,
    variance,
)
from hsr_nous.research_protocol import PAIRED_V1
from hsr_nous.research_schema import Claim, EvidenceLink, MetricSpec
from hsr_nous.sim.montecarlo import summarize
from tests._research_builders import make_fingerprint


def test_mean_variance_quantile_hand_calculation():
    values = [1, 2, 3, 4]
    assert mean(values) == 2.5
    assert variance(values) == 1.25
    assert quantile(values, 0.25) == 1.75
    assert quantile(values, 0.5) == 2.5
    assert quantile(values, 0.75) == 3.25
    assert quantile([2], 0.95) == 2.0
    assert mean(["1.5", "2.5"]) == 2.0


@pytest.mark.parametrize("values", [[], [math.nan], [math.inf], [-math.inf]])
def test_numeric_inputs_reject_empty_and_non_finite(values):
    with pytest.raises(ValueError):
        mean(values)


def test_distribution_crosschecks_existing_montecarlo_statistics():
    values = [1, 2, 4, 8, 16]
    actual = distribution(values)
    expected = summarize(values)
    assert actual["n"] == expected.n
    assert actual["variance"] == 29.76
    for field in ("mean", "stdev", "minimum", "p5", "p50", "p95", "maximum"):
        assert math.isclose(actual[field], getattr(expected, field), abs_tol=1e-6)


def test_paired_diff_and_compare_validate_seed_cohorts():
    baseline = {seed: 100 + seed for seed in PAIRED_V1.dev_seeds}
    variant = {seed: 120 + seed for seed in PAIRED_V1.dev_seeds}
    assert paired_diff([1, 2, 3], [4, 6, 8]) == [3.0, 4.0, 5.0]
    result = compare(baseline, variant, protocol=PAIRED_V1, cohort="dev")
    assert result["n"] == 16
    assert result["effect"] == 20.0
    assert result["confidence_interval"]["lower"] == 20.0
    assert result["confidence_interval"]["upper"] == 20.0

    with pytest.raises(ValueError, match="seed"):
        compare(baseline, variant, protocol=PAIRED_V1, cohort="holdout")
    with pytest.raises(ValueError, match="seed"):
        compare({**baseline, 99: 1}, variant, protocol=PAIRED_V1, cohort="dev")
    with pytest.raises(ValueError, match="cohort"):
        compare(baseline, variant, protocol=PAIRED_V1, cohort="other")


def test_compare_keeps_exact_fraction_differences_until_final_rounding():
    from fractions import Fraction

    deltas = [Fraction(1, 10**7)] * 4 + [Fraction(6, 10**7)] * 12
    baseline = {seed: Fraction(100) for seed in PAIRED_V1.dev_seeds}
    variant = {
        seed: Fraction(100) + delta
        for seed, delta in zip(PAIRED_V1.dev_seeds, deltas)
    }
    result = compare(baseline, variant, protocol=PAIRED_V1, cohort="dev")
    assert result["paired_differences"] == [0.0] * 4 + [0.000001] * 12
    assert result["effect"] == 0.0
    assert result["confidence_interval"] == confidence_interval(
        deltas,
        resamples=PAIRED_V1.bootstrap_resamples,
        confidence=PAIRED_V1.confidence,
        seed=PAIRED_V1.bootstrap_seed,
    )


def test_constant_and_nontrivial_fixed_bootstrap_golden():
    constant = confidence_interval([3, 3, 3, 3], resamples=2000, confidence=0.95, seed=0)
    assert constant["lower"] == 3.0
    assert constant["upper"] == 3.0

    golden = confidence_interval(
        [1, -2, 3, 5, 0, 4, -1, 2], resamples=2000, confidence=0.95, seed=0
    )
    assert golden["lower"] == -0.125
    assert golden["upper"] == 3.125
    assert golden["resamples"] == 2000
    assert golden["seed"] == 0


def _comparison(effect=20.0):
    baseline = {seed: 100.0 for seed in PAIRED_V1.holdout_seeds}
    variant = {seed: 100.0 + effect for seed in PAIRED_V1.holdout_seeds}
    return compare(baseline, variant, protocol=PAIRED_V1, cohort="holdout"), baseline, variant


def _build(effect=20.0, **overrides):
    comparison, _, _ = _comparison(effect)
    values = {
        "trial_id": "a" * 64,
        "comparison_set_id": "b" * 64,
        "subject": "variant",
        "metric": MetricSpec(),
        "protocol": PAIRED_V1,
        "fingerprint": make_fingerprint(),
        "premises": (EvidenceLink(trial_id="a" * 64, artifact_hash="c" * 64),),
        "holdout": comparison,
        "valid_n": 16,
        "baseline_run_ids": tuple(f"baseline-{seed}" for seed in PAIRED_V1.holdout_seeds),
        "variant_run_ids": tuple(f"variant-{seed}" for seed in PAIRED_V1.holdout_seeds),
        "failed_run_ids": (),
        "truncated_run_ids": (),
    }
    values.update(overrides)
    return build_claim(**values)


def test_build_claim_status_and_pure_validation():
    accepted = _build()
    assert accepted.status == "accepted"
    assert accepted.statistical_metadata["effect"] == 20.0
    assert accepted.statistical_metadata["cohort"] == "holdout"
    assert accepted.scope["validation"] == "pending_real_validation"
    assert validate_claim(accepted, accepted) == ()

    payload = accepted.to_dict()
    payload["statistical_metadata"]["effect"] = 999.0
    forged = Claim.from_dict(payload)
    assert "statistical_metadata" in validate_claim(forged, accepted)

    failed = _build(failed_run_ids=("failed-run",), valid_n=15, holdout=None)
    assert failed.status == "inconclusive"
    assert "failed" in failed.failure_reason

    crossing = _build(effect=0.0)
    assert crossing.status == "inconclusive"
    assert "CI" in crossing.failure_reason

    rejected_view = _build(effect=-20.0)
    assert rejected_view.status == "accepted"
    assert rejected_view.statistical_metadata["effect"] == -20.0


def test_claim_id_ignores_status_and_failure_reason():
    accepted = _build()
    inconclusive = Claim.from_dict({
        **accepted.to_dict(),
        "status": "inconclusive",
        "failure_reason": "different status metadata",
    })
    assert inconclusive.claim_id == accepted.claim_id
