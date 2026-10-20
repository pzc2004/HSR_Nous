"""JSON-only rendering of independently validated research claims."""

from __future__ import annotations

from typing import Any

from hsr_nous.research.core.artifacts import ArtifactStore
from hsr_nous.research.core.claims import ClaimValidationResult, ClaimValidator
from hsr_nous.research.schema import Claim, EvidenceLink, ResearchContract


def _claim_view(claim: Claim) -> dict[str, Any]:
    if claim.status in {"accepted", "inconclusive"}:
        return claim.to_dict()
    operation = "stale_check" if claim.status == "stale" else "validation_rejected"
    return {
        "claim_id": claim.claim_id,
        "trial_id": claim.trial_id,
        "comparison_set_id": claim.comparison_set_id,
        "subject": claim.subject,
        "metric": claim.metric,
        "relation": claim.relation,
        "status": claim.status,
        "premises": claim.premises,
        "derivation_steps": ({
            "operation": operation,
            "reason": claim.failure_reason,
        },),
        "scope": claim.scope,
        "failure_reason": claim.failure_reason,
    }


def _drilldown(result: ClaimValidationResult) -> list[dict[str, Any]]:
    if result.trial is None:
        return []
    baseline = result.trial.spec.experiment.baseline.arm_id
    variant = result.trial.spec.experiment.variant.arm_id
    entries = []
    seen = set()
    for record in result.records:
        if record.arm_id in seen:
            continue
        seen.add(record.arm_id)
        entries.append({
            "arm_id": record.arm_id,
            "run": EvidenceLink(
                trial_id=record.trial_id,
                run_id=record.run_id,
                artifact_hash=record.content_hash,
            ),
            "events": tuple(
                EvidenceLink(
                    trial_id=record.trial_id,
                    run_id=record.run_id,
                    event_id=event["event_id"],
                    artifact_hash=record.content_hash,
                )
                for event in record.events
            ),
            "modifiers": tuple(
                EvidenceLink(
                    trial_id=record.trial_id,
                    run_id=record.run_id,
                    modifier_id=modifier["modifier_id"],
                    artifact_hash=record.content_hash,
                )
                for modifier in record.modifiers
            ),
        })
        if seen == {baseline, variant}:
            break
    return entries


def _conclusion(claim: Claim) -> str:
    prefix = (
        f"{claim.scope['source']}/{claim.scope['world']}/"
        f"{claim.scope['validation']}"
    )
    if claim.status == "accepted":
        metadata = claim.statistical_metadata
        interval = metadata["confidence_interval"]
        confidence = claim.metric.confidence * 100
        return (
            f"{prefix}: holdout variant - baseline mean total_damage = "
            f"{metadata['effect']:.6f}; {confidence:.0f}% CI "
            f"[{interval['lower']:.6f}, {interval['upper']:.6f}]; "
            f"n={metadata['n']}."
        )
    return f"{prefix}: {claim.status} — {claim.failure_reason}"


class ReportComposer:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store
        self._validator = ClaimValidator(store)

    def compose(self, validated: ClaimValidationResult) -> dict[str, Any]:
        """Revalidate, then render and publish; no caller-supplied metrics are trusted."""
        if not isinstance(validated, ClaimValidationResult):
            raise TypeError("ReportComposer requires a ClaimValidationResult")
        validated = self._validator.validate(validated.claim)
        claim = validated.claim
        contract = ResearchContract.from_dict(validated.spec["contract"])
        trial = validated.trial
        report = {
            "schema_version": "2",
            "spec": validated.spec,
            "canonical": {
                "arm_id": contract.experiment.baseline.arm_id,
                "world": "canonical",
            },
            "variant": {
                "arm_id": contract.experiment.variant.arm_id,
                "world": contract.experiment.variant.world,
                "comparison_kind": contract.experiment.comparison_kind,
                "metadata": validated.variant_metadata,
            },
            "flags": {
                "source": claim.scope["source"],
                "world": claim.scope["world"],
                "validation": claim.scope["validation"],
            },
            "comparison_set": trial.comparison_set if trial is not None else None,
            "fingerprint": validated.spec["fingerprint"],
            "claim": _claim_view(claim),
            "evidence": {
                "claim_record_id": validated.claim_record_id,
                "comparison_set_id": claim.comparison_set_id,
                "premises": claim.premises,
                "drilldown": _drilldown(validated),
            },
            "caveats": trial.caveats if trial is not None else (),
            "failure_reasons": trial.failure_reasons if trial is not None else (),
            "validation_reason": claim.failure_reason,
            "conclusion": _conclusion(claim),
        }
        if claim.status in {"accepted", "inconclusive"}:
            report.update({
                "cohorts": validated.summaries,
                "comparisons": validated.comparisons,
                "effect": claim.statistical_metadata["effect"],
                "confidence_interval": claim.statistical_metadata["confidence_interval"],
                "actor_damage": validated.actor_damage,
                "derivation_steps": claim.derivation_steps,
            })
        report_id = self.store.publish_report(claim.trial_id, report)
        return self.store.read_report(claim.trial_id, report_id)
