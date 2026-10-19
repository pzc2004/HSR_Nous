from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

import hsr_nous.research_core.claims as claims_module
import hsr_nous.research_core.runner as runner_module
from hsr_nous.research_core import ArtifactStore
from hsr_nous.research_permissions import (
    CapabilityPolicy,
    PermissionDeniedError,
    ResearchGateway,
)
from hsr_nous.research_schema import Claim, ClaimSubmissionResult
from tests._research_builders import make_demo_contract


def _gateway(root: Path, **changes):
    policy = CapabilityPolicy(allowed_project_root=root, **changes)
    store = ArtifactStore(root / "artifacts")
    return ResearchGateway(store, policy)


def _accepted(root: Path):
    gateway = _gateway(root)
    result = gateway.submit_claim(contract=make_demo_contract())
    assert result.status == "accepted"
    return gateway, result


def _edited(claim: Claim, edit) -> Claim:
    payload = claim.to_dict()
    edit(payload)
    return Claim.from_dict(payload)


def test_default_policy_denies_custom_execution_and_is_immutable(tmp_path):
    gateway = _gateway(tmp_path)
    for kind in ("bash", "python", "docker"):
        with pytest.raises(PermissionDeniedError):
            gateway.execute_custom_code(kind, lambda: (_ for _ in ()).throw(
                AssertionError("payload must not execute")
            ))
    with pytest.raises(FrozenInstanceError):
        gateway._policy.allow_bash = True
    assert not gateway._policy.allow_web_search
    assert not gateway._policy.allow_web_fetch
    for name in ("publish_run", "publish_claim", "publish_report"):
        assert not hasattr(gateway, name)


def test_path_permissions_cover_secrets_repo_and_symlinks(tmp_path):
    gateway = _gateway(tmp_path)
    assert gateway.authorize_path(tmp_path / "out.json", "write_project") == \
        (tmp_path / "out.json").resolve()
    assert gateway.authorize_path(
        gateway._store.root / "trial.json", "read_artifacts"
    ) == (gateway._store.root / "trial.json").resolve()
    assert gateway.authorize_path(Path("pyproject.toml"), "read_repo") == \
        Path("pyproject.toml").resolve()

    for path in (
        tmp_path / ".env",
        tmp_path / ".git" / "config",
        tmp_path / "credentials.json",
        tmp_path / "docker.sock",
        tmp_path / "id_rsa",
        tmp_path / "secret.pem",
        Path("pyproject.toml"),
        tmp_path.parent / "outside.json",
    ):
        with pytest.raises(PermissionDeniedError):
            gateway.authorize_path(path, "write_project")

    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("x", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(outside)
    with pytest.raises(PermissionDeniedError):
        gateway.authorize_path(link, "write_project")


def test_submit_contract_returns_accepted_report_and_roundtrip(tmp_path):
    _, result = _accepted(tmp_path)
    assert result.claim.status == "accepted"
    assert result.report["claim"]["status"] == "accepted"
    assert result.execution.status == "completed"
    assert result.error is None
    assert ClaimSubmissionResult.from_dict(result.to_dict()) == result


def test_trial_revalidation_and_forged_claim_are_separated(tmp_path):
    gateway, accepted = _accepted(tmp_path)
    trial_id = accepted.claim.trial_id
    again = gateway.submit_claim(trial_id=trial_id)
    assert again.status == "accepted"
    assert again.report["report_id"] == accepted.report["report_id"]

    forged = _edited(
        accepted.claim,
        lambda payload: payload["statistical_metadata"].update(effect=999999.0),
    )
    rejected = gateway.submit_claim(claim=forged)
    assert rejected.status == "rejected"
    assert rejected.error["code"] == "claim_derivation_mismatch"
    assert "statistical_metadata" in rejected.error["fields"]
    assert rejected.report["claim"]["status"] == "rejected"
    assert "mean total_damage" not in rejected.report["conclusion"]

    invalid = gateway.submit_claim(contract=make_demo_contract(), trial_id=trial_id)
    assert invalid.status == "rejected"
    assert invalid.error["code"] == "invalid_submission"


def test_stale_is_returned_without_rewriting_accepted(tmp_path, monkeypatch):
    gateway, accepted = _accepted(tmp_path)
    real_collect = claims_module.collect_research_fingerprint

    def stale_collect(*args, **kwargs):
        return replace(real_collect(*args, **kwargs), implementation_hash="stale-source")

    monkeypatch.setattr(claims_module, "collect_research_fingerprint", stale_collect)
    stale = gateway.submit_claim(trial_id=accepted.claim.trial_id)
    assert stale.status == "stale"
    assert stale.claim.status == "stale"
    assert stale.report is None
    assert stale.error["code"] == "stale"
    assert "fingerprint" in stale.error["fields"]


def test_permission_denied_does_not_create_investigation(tmp_path):
    gateway = _gateway(tmp_path, allow_submit_claim=False)
    result = gateway.submit_claim(contract=make_demo_contract())
    assert result.status == "permission_denied"
    assert result.error["code"] == "permission_denied"
    assert "allow_submit_claim" in result.error["fields"]
    assert result.execution is None
    assert not list(gateway._store.root.rglob("*.json"))

    gateway = _gateway(tmp_path, allow_run_simulation=False)
    result = gateway.submit_claim(contract=make_demo_contract())
    assert result.status == "permission_denied"
    assert "allow_run_simulation" in result.error["fields"]
    assert not list(gateway._store.root.rglob("*.json"))


def test_inconclusive_has_a_structured_report(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    real_compile = runner_module.compile_encounter

    def fail_variant(*args, **kwargs):
        roots = kwargs.get("template_roots") or ()
        if roots and "variants" in Path(roots[0]).parts:
            raise RuntimeError("declared variant compile failure")
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(runner_module, "compile_encounter", fail_variant)
    result = gateway.submit_claim(contract=make_demo_contract())
    assert result.status == "inconclusive"
    assert result.report["claim"]["status"] == "inconclusive"
    assert result.report["comparisons"]["holdout"] is None
    assert "mean total_damage" not in result.report["conclusion"]
    assert result.execution.status == "completed"


def test_failed_and_cancelled_executions_keep_execution_evidence(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path / "failed")

    def fail_validation(trial_id):
        raise RuntimeError("declared validation failure")

    monkeypatch.setattr(gateway._validator, "validate_trial", fail_validation)
    failed = gateway.submit_claim(contract=make_demo_contract())
    assert failed.status == "failed"
    assert failed.execution.status == "failed"
    assert "declared validation failure" in failed.error["message"]

    gateway = _gateway(tmp_path / "cancelled")
    real_publish = gateway._store.publish_run
    real_queue = gateway._manager.queue
    queued_ids = []
    published = 0

    def tracked_queue(investigation_id):
        execution = real_queue(investigation_id)
        queued_ids.append(execution.execution_id)
        return execution

    def cancel_at_third(record):
        nonlocal published
        published += 1
        result = real_publish(record)
        if published == 3:
            gateway._manager.cancel(queued_ids[0])
        return result

    monkeypatch.setattr(gateway._manager, "queue", tracked_queue)

    monkeypatch.setattr(gateway._store, "publish_run", cancel_at_third)
    cancelled = gateway.submit_claim(contract=make_demo_contract())
    assert cancelled.status == "cancelled"
    assert cancelled.execution.status == "cancelled"
    assert cancelled.execution.completed_runs == 3
    assert cancelled.claim is None
