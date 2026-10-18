from __future__ import annotations

from dataclasses import asdict, replace

import pytest

import hsr_nous.research_core.claims as claims_module
from hsr_nous.research_core.artifacts import (
    ArtifactStore,
    make_comparison_set,
    make_event_id,
    make_modifier_id,
    make_run_id,
    run_failure_reason,
)
from hsr_nous.research_core.claims import ClaimValidator
from hsr_nous.research_core.fingerprint import collect_research_fingerprint
from hsr_nous.research_core.variants import VariantMaterializer
from hsr_nous.research_schema import Claim, RunRecord, TrialArtifact
from tests._research_builders import make_demo_contract


def _make_trial(store, *, effect=20.0, failed_seed=None, truncated_seed=None):
    contract = make_demo_contract()
    prepared = VariantMaterializer().prepare(contract, hypothesis=contract.question)
    resolved = prepared.resolved_protocol
    fingerprint = collect_research_fingerprint(contract, resolved, prepared)
    trial_id = store.publish_spec(contract, resolved, fingerprint)
    store.publish_variant(trial_id, prepared)
    records = []
    for arm in (contract.experiment.baseline, contract.experiment.variant):
        for cohort, seeds in (("dev", resolved.dev_seeds), ("holdout", resolved.holdout_seeds)):
            for seed in seeds:
                run_id = make_run_id(trial_id, arm.arm_id, cohort, seed)
                failed = seed == failed_seed and arm.arm_id == "variant" and cohort == "holdout"
                truncated = seed == truncated_seed and arm.arm_id == "variant" and cohort == "holdout"
                damage = 100.0 + seed + (effect if arm.arm_id == "variant" else 0.0)
                observed = {
                    "seed": seed,
                    "total_damage": damage,
                    "truncated": truncated,
                }
                status = "failed" if failed else "completed"
                if failed:
                    observed = {"error": {"type": "RuntimeError", "message": "retained failure"}}
                final_save = {} if failed else {
                    "save_version": 1,
                    "state": {
                        "total_damage": damage,
                        "truncated": truncated,
                        "actors": {},
                    },
                }
                event_payload = {"event_type": "battle_start", "data": {}}
                modifier_id = "TRACE"
                record = RunRecord(
                    run_id=run_id,
                    trial_id=trial_id,
                    arm_id=arm.arm_id,
                    cohort=cohort,
                    seed=seed,
                    status=status,
                    observed=observed,
                    events=({
                        "event_id": make_event_id(run_id, 0, event_payload),
                        "ordinal": 0,
                        "payload": event_payload,
                    },),
                    final_save=final_save,
                    modifiers=({
                        "modifier_id": make_modifier_id(run_id, "1202", modifier_id),
                        "actor_id": "1202",
                        "engine_modifier_id": modifier_id,
                        "details": {"modifier_id": modifier_id, "name": "行迹"},
                    },),
                    content_hash="",
                    parent_run_id=(
                        make_run_id(trial_id, "baseline", cohort, seed)
                        if arm.arm_id == "variant" else None
                    ),
                )
                records.append(store.publish_run(record))
    failed = [record for record in records if record.status == "failed"]
    artifact = TrialArtifact(
        trial_id=trial_id,
        spec=contract,
        resolved_protocol=asdict(resolved),
        fingerprint=fingerprint,
        comparison_set=make_comparison_set(trial_id, contract, resolved),
        run_ids=tuple(record.run_id for record in records),
        status="failed" if failed else "completed",
        failure_reasons=tuple(run_failure_reason(record) for record in failed),
    )
    store.publish_result(artifact)
    return trial_id


def _edited(claim, edit):
    payload = claim.to_dict()
    edit(payload)
    return Claim.from_dict(payload)


def test_validator_rebuilds_accepted_claim_and_is_idempotent(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    trial_id = _make_trial(store)
    validator = ClaimValidator(store)
    result = validator.validate_trial(trial_id)
    assert result.claim.status == "accepted"
    assert result.claim.statistical_metadata["effect"] == 20.0
    assert result.claim.statistical_metadata["confidence_interval"]["lower"] == 20.0
    assert store.read_claim(trial_id, result.claim_record_id) == result.claim
    assert validator.validate(result.claim).claim == result.claim


def test_validator_rejects_handwritten_numbers_cohorts_status_and_evidence(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    trial_id = _make_trial(store)
    validator = ClaimValidator(store)
    accepted = validator.validate_trial(trial_id).claim
    accepted_record = store.claim_path(trial_id, validator.validate(accepted).claim_record_id)
    original_bytes = accepted_record.read_bytes()

    edits = []
    def add(name, edit):
        edits.append((name, edit))

    add("mean", lambda p: p["statistical_metadata"].update(effect=999.0))
    add("ci", lambda p: p["statistical_metadata"]["confidence_interval"].update(lower=-1.0))
    add("n", lambda p: p["statistical_metadata"].update(n=1))
    add("seed", lambda p: p["derivation_steps"][0]["seeds"].__setitem__(0, 999))
    add("holdout", lambda p: p["scope"].update(cohort="dev"))
    add("status", lambda p: p.update(status="inconclusive"))
    add("comparison", lambda p: p.update(comparison_set_id="0" * 64))
    add("hash", lambda p: p["premises"][0].update(artifact_hash="0" * 64))
    add("claim_id", lambda p: p.update(claim_id="f" * 64))

    for name, edit in edits:
        rejected = validator.validate(_edited(accepted, edit))
        assert rejected.claim.status == "rejected", name
        assert rejected.claim_record_id is not None
        assert store.read_claim(trial_id, rejected.claim_record_id).status == "rejected"
        assert accepted_record.read_bytes() == original_bytes


def test_failed_or_truncated_holdout_is_inconclusive_then_missing_run_is_rejected(tmp_path):
    failed_store = ArtifactStore(tmp_path / "failed")
    failed_trial = _make_trial(failed_store, failed_seed=16)
    validator = ClaimValidator(failed_store)
    inconclusive = validator.validate_trial(failed_trial)
    assert inconclusive.claim.status == "inconclusive"
    assert "failed" in inconclusive.claim.failure_reason

    failed_run_id = next(
        run_id for run_id in inconclusive.trial.run_ids
        if failed_store.read_run(failed_trial, run_id).status == "failed"
    )
    failed_store.run_path(failed_trial, failed_run_id).unlink()
    rejected = validator.validate(inconclusive.claim)
    assert rejected.claim.status == "rejected"

    truncated_store = ArtifactStore(tmp_path / "truncated")
    truncated_trial = _make_trial(truncated_store, truncated_seed=16)
    truncated = ClaimValidator(truncated_store).validate_trial(truncated_trial)
    assert truncated.claim.status == "inconclusive"
    assert "truncated" in truncated.claim.failure_reason


def test_current_fingerprint_mismatch_is_stale_without_rewriting_history(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    trial_id = _make_trial(store)
    validator = ClaimValidator(store)
    accepted = validator.validate_trial(trial_id)
    claim_path = store.claim_path(trial_id, accepted.claim_record_id)
    original = claim_path.read_bytes()
    real_collect = claims_module.collect_research_fingerprint

    def stale_collect(*args, **kwargs):
        return replace(real_collect(*args, **kwargs), implementation_hash="new-implementation")

    monkeypatch.setattr(claims_module, "collect_research_fingerprint", stale_collect)
    stale = validator.validate(accepted.claim)
    assert stale.claim.status == "stale"
    assert stale.claim_record_id is None
    assert claim_path.read_bytes() == original
    assert store.read_claim(trial_id, accepted.claim_record_id).status == "accepted"
