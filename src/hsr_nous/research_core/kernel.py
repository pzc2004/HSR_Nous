"""Small, pure, rational-number statistics and claim derivation kernel."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import fields
from fractions import Fraction
from random import Random
from typing import Any

from hsr_nous.research_protocol import ResolvedProtocol
from hsr_nous.research_schema import (
    Claim,
    EvidenceLink,
    MetricSpec,
    VersionFingerprint,
    canonical_round,
    content_hash,
)


def _fraction(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric research sample")
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"sample must be a finite number, got {value!r}") from exc


def _fractions(values: Sequence[Any]) -> tuple[Fraction, ...]:
    result = tuple(_fraction(value) for value in values)
    if not result:
        raise ValueError("sample must not be empty")
    return result


def _rounded(value: Fraction) -> float:
    return canonical_round(float(value))


def _mean(values: tuple[Fraction, ...]) -> Fraction:
    return sum(values, Fraction(0)) / len(values)


def _variance(values: tuple[Fraction, ...]) -> Fraction:
    center = _mean(values)
    return sum(((value - center) ** 2 for value in values), Fraction(0)) / len(values)


def _quantile(values: tuple[Fraction, ...], q: Fraction) -> Fraction:
    if not 0 <= q <= 1:
        raise ValueError("quantile q must be between zero and one")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = int(position)
    fraction = position - lower
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def mean(values: Sequence[Any]) -> float:
    return _rounded(_mean(_fractions(values)))


def variance(values: Sequence[Any]) -> float:
    return _rounded(_variance(_fractions(values)))


def quantile(values: Sequence[Any], q: Any) -> float:
    return _rounded(_quantile(_fractions(values), _fraction(q)))


def distribution(values: Sequence[Any]) -> dict[str, Any]:
    samples = _fractions(values)
    var = _variance(samples)
    return {
        "n": len(samples),
        "mean": _rounded(_mean(samples)),
        "variance": _rounded(var),
        "stdev": canonical_round(math.sqrt(float(var))),
        "minimum": _rounded(min(samples)),
        "p5": _rounded(_quantile(samples, Fraction("0.05"))),
        "p50": _rounded(_quantile(samples, Fraction("0.5"))),
        "p95": _rounded(_quantile(samples, Fraction("0.95"))),
        "maximum": _rounded(max(samples)),
    }


def _paired_diff(
    baseline: Sequence[Any], variant: Sequence[Any]
) -> tuple[Fraction, ...]:
    if len(baseline) != len(variant):
        raise ValueError("paired samples must have the same length")
    base = _fractions(baseline)
    changed = _fractions(variant)
    return tuple(new - old for old, new in zip(base, changed))


def paired_diff(baseline: Sequence[Any], variant: Sequence[Any]) -> list[float]:
    return canonical_round([
        float(difference) for difference in _paired_diff(baseline, variant)
    ])


def confidence_interval(
    differences: Sequence[Any],
    *,
    resamples: int,
    confidence: float,
    seed: int,
) -> dict[str, Any]:
    samples = _fractions(differences)
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples <= 0:
        raise ValueError("bootstrap resamples must be a positive integer")
    confidence_fraction = _fraction(confidence)
    if not 0 < confidence_fraction < 1:
        raise ValueError("bootstrap confidence must be between zero and one")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("bootstrap seed must be an integer")

    rng = Random(seed)
    bootstrap_means = []
    for _ in range(resamples):
        indices = rng.choices(range(len(samples)), k=len(samples))
        bootstrap_means.append(_mean(tuple(samples[index] for index in indices)))
    ordered = tuple(sorted(bootstrap_means))
    tail = (1 - confidence_fraction) / 2
    return {
        "lower": _rounded(_quantile(ordered, tail)),
        "upper": _rounded(_quantile(ordered, 1 - tail)),
        "confidence": canonical_round(float(confidence_fraction)),
        "resamples": resamples,
        "seed": seed,
    }


def compare(
    baseline: Mapping[int, Any],
    variant: Mapping[int, Any],
    *,
    protocol: ResolvedProtocol,
    cohort: str,
    confidence: float | None = None,
) -> dict[str, Any]:
    if cohort not in {"dev", "holdout"}:
        raise ValueError(f"unsupported cohort: {cohort!r}")
    seeds = protocol.dev_seeds if cohort == "dev" else protocol.holdout_seeds
    expected = set(seeds)
    if set(baseline) != expected or set(variant) != expected:
        raise ValueError(f"{cohort} seed membership mismatch")
    base = [baseline[seed] for seed in seeds]
    changed = [variant[seed] for seed in seeds]
    exact_differences = _paired_diff(base, changed)
    display_differences = canonical_round([
        float(difference) for difference in exact_differences
    ])
    effect = _rounded(_mean(exact_differences))
    return canonical_round({
        "cohort": cohort,
        "protocol_id": protocol.protocol_id,
        "n": len(seeds),
        "seeds": seeds,
        "baseline": distribution(base),
        "variant": distribution(changed),
        "paired_differences": display_differences,
        "effect": effect,
        "confidence_interval": confidence_interval(
            exact_differences,
            resamples=protocol.bootstrap_resamples,
            confidence=protocol.confidence if confidence is None else confidence,
            seed=protocol.bootstrap_seed,
        ),
    })


def make_claim_id(
    subject: str,
    premises: tuple[EvidenceLink, ...],
    derivation_steps: tuple[dict[str, Any], ...],
) -> str:
    return content_hash({
        "subject": subject,
        "premises": premises,
        "derivation_steps": derivation_steps,
    })


def build_claim(
    *,
    trial_id: str,
    comparison_set_id: str,
    subject: str,
    metric: MetricSpec,
    protocol: ResolvedProtocol,
    fingerprint: VersionFingerprint,
    premises: tuple[EvidenceLink, ...],
    holdout: dict[str, Any] | None,
    valid_n: int,
    baseline_run_ids: tuple[str, ...],
    variant_run_ids: tuple[str, ...],
    failed_run_ids: tuple[str, ...] = (),
    truncated_run_ids: tuple[str, ...] = (),
    comparison_kind: str = "mechanism",
    world: str = "hypothetical",
) -> Claim:
    derivation = [{
        "operation": "extract_paired_samples",
        "cohort": "holdout",
        "seeds": protocol.holdout_seeds,
        "baseline_run_ids": baseline_run_ids,
        "variant_run_ids": variant_run_ids,
        "valid_n": valid_n,
        "failed_run_ids": failed_run_ids,
        "truncated_run_ids": truncated_run_ids,
    }]
    effect = None
    interval = None
    if holdout is not None:
        if holdout.get("cohort") != "holdout" or holdout.get("n") != valid_n:
            raise ValueError("holdout comparison metadata does not match valid samples")
        effect = holdout["effect"]
        interval = holdout["confidence_interval"]
        derivation.append({
            "operation": "paired_mean_difference",
            "direction": "variant - baseline",
            "paired_differences": holdout["paired_differences"],
            "effect": effect,
        })
        derivation.append({
            "operation": "paired_percentile_bootstrap",
            "resamples": protocol.bootstrap_resamples,
            "confidence": protocol.confidence,
            "seed": protocol.bootstrap_seed,
            "confidence_interval": interval,
        })

    reasons = []
    if failed_run_ids:
        reasons.append("holdout contains failed runs")
    if truncated_run_ids:
        reasons.append("holdout contains truncated runs")
    if valid_n < protocol.min_valid_n:
        reasons.append(
            f"holdout valid sample n={valid_n} is below min_valid_n={protocol.min_valid_n}"
        )
    if holdout is None:
        reasons.append("holdout comparison is unavailable")
    if not reasons:
        if interval["lower"] > 0 or interval["upper"] < 0:
            status = "accepted"
            failure_reason = None
        else:
            status = "inconclusive"
            failure_reason = "holdout CI contains 0"
    else:
        status = "inconclusive"
        failure_reason = "; ".join(reasons)

    derivation_steps = tuple(derivation)
    statistical_metadata = {
        "cohort": "holdout",
        "n": valid_n,
        "required_n": protocol.min_valid_n,
        "effect": effect,
        "confidence_interval": interval,
        "failed_run_ids": failed_run_ids,
        "truncated_run_ids": truncated_run_ids,
        "fingerprint": fingerprint.to_dict(),
    }
    return Claim(
        claim_id=make_claim_id(subject, premises, derivation_steps),
        trial_id=trial_id,
        comparison_set_id=comparison_set_id,
        subject=subject,
        metric=metric,
        relation="variant_minus_baseline",
        status=status,
        premises=premises,
        derivation_steps=derivation_steps,
        statistical_metadata=statistical_metadata,
        scope={
            "source": "simulated",
            "world": world,
            "validation": "pending_real_validation",
            "cohort": "holdout",
            "protocol_id": protocol.protocol_id,
            "comparison_kind": comparison_kind,
        },
        failure_reason=failure_reason,
    )


def validate_claim(claim: Claim, expected: Claim) -> tuple[str, ...]:
    """Return the fields whose pure structured derivation differs from the rebuilt claim."""
    return tuple(
        field.name
        for field in fields(Claim)
        if getattr(claim, field.name) != getattr(expected, field.name)
    )
