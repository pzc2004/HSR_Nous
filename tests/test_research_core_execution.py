from __future__ import annotations

from dataclasses import replace

import pytest

from hsr_nous.research.core import ExecutionManager
from hsr_nous.research.core.artifacts import (
    ArtifactConflictError,
    ArtifactPathError,
    ArtifactStore,
)
from hsr_nous.research.schema import ExecutionRecord, InvestigationState, canonical_bytes, content_hash
from tests._research_builders import make_demo_contract


def _trial_files(store):
    return {
        path.relative_to(store.root): path.read_bytes()
        for path in (store.root / "trials").rglob("*")
        if path.is_file() and path.name != "metadata.json"
    }


def test_full_lifecycle_cache_and_replay(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    manager = ExecutionManager(store)
    investigation = manager.create_investigation(make_demo_contract())
    assert investigation.status == "draft"
    assert investigation.artifact_status == "partial"
    investigation = manager.validate(investigation.investigation_id)
    assert investigation.status == "validated"
    assert investigation.trial_id is not None

    execution = manager.queue(investigation.investigation_id)
    assert execution.kind == "initial"
    assert execution.parent_execution_id is None
    execution = manager.execute(execution.execution_id)
    assert execution.status == "completed"
    assert execution.artifact_status == "complete"
    assert execution.completed_runs == execution.total_runs == 64
    statuses = [entry["status"] for entry in execution.history]
    assert statuses[0] == "queued"
    assert "running" in statuses
    assert "validating" in statuses
    assert statuses[-1] == "completed"
    assert list((store.trial_dir(investigation.trial_id) / "reports").glob("*.json"))

    original_run = manager.runner.run
    def forbidden_run(*args, **kwargs):
        raise AssertionError("cache hit must not call TrialRunner.run")
    monkeypatch.setattr(manager.runner, "run", forbidden_run)
    cached = manager.cache(investigation.investigation_id)
    assert cached.kind == "cache_hit"
    assert cached.status == "completed"
    assert cached.parent_execution_id == execution.execution_id

    monkeypatch.setattr(manager.runner, "run", original_run)
    before = _trial_files(store)
    replayed = manager.replay(investigation.investigation_id)
    assert replayed.kind == "replay_check"
    assert replayed.status == "completed"
    assert replayed.parent_execution_id == cached.execution_id
    assert _trial_files(store) == before

    persisted = store.read_investigation(investigation.investigation_id)
    assert persisted.status == "completed"
    assert persisted.execution_ids == (
        execution.execution_id,
        cached.execution_id,
        replayed.execution_id,
    )
    assert persisted.revision > investigation.revision


def test_cancel_after_third_run_and_resume_only_missing(tmp_path, monkeypatch):
    from hsr_nous.sim.engine import CombatEngine

    store = ArtifactStore(tmp_path / "artifacts")
    manager = ExecutionManager(store)
    investigation = manager.create_investigation(make_demo_contract())
    investigation = manager.validate(investigation.investigation_id)
    queued = manager.queue(investigation.investigation_id)
    real_publish = store.publish_run
    published = 0

    def cancel_at_third(record):
        nonlocal published
        published += 1
        result = real_publish(record)
        if published == 3:
            manager.cancel(queued.execution_id)
        return result

    monkeypatch.setattr(store, "publish_run", cancel_at_third)
    cancelled = manager.execute(queued.execution_id)
    assert cancelled.status == "cancelled"
    assert cancelled.artifact_status == "partial"
    assert cancelled.completed_runs == 3
    assert published == 3
    assert not (store.trial_dir(investigation.trial_id) / "result.json").exists()
    # Read the retained runs directly from the frozen baseline dev prefix.
    from hsr_nous.research.core.artifacts import make_run_id
    from hsr_nous.research.protocol import PAIRED_V1
    first_three = {
        seed: store.run_path(
            investigation.trial_id, make_run_id(investigation.trial_id, "baseline", "dev", seed)
        ).read_bytes()
        for seed in PAIRED_V1.dev_seeds[:3]
    }

    real_from_compiled = CombatEngine.from_compiled
    engine_calls = 0
    def counted_from_compiled(cls, compiled, **kwargs):
        nonlocal engine_calls
        engine_calls += 1
        return real_from_compiled(compiled, **kwargs)
    monkeypatch.setattr(CombatEngine, "from_compiled", classmethod(counted_from_compiled))

    resumed = manager.resume(investigation.investigation_id)
    assert resumed.kind == "resume"
    assert resumed.parent_execution_id == cancelled.execution_id
    assert resumed.status == "completed"
    assert resumed.artifact_status == "complete"
    assert resumed.completed_runs == 64
    assert engine_calls == 61
    assert (store.trial_dir(investigation.trial_id) / "result.json").exists()
    for seed, original in first_three.items():
        run_id = make_run_id(investigation.trial_id, "baseline", "dev", seed)
        assert store.run_path(investigation.trial_id, run_id).read_bytes() == original


def test_validation_failure_preserves_raw_runs(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    manager = ExecutionManager(store)
    investigation = manager.create_investigation(make_demo_contract())
    investigation = manager.validate(investigation.investigation_id)
    queued = manager.queue(investigation.investigation_id)

    def fail_validation(trial_id):
        raise RuntimeError("declared validation failure")
    monkeypatch.setattr(manager.validator, "validate_trial", fail_validation)
    failed = manager.execute(queued.execution_id)
    assert failed.status == "failed"
    assert failed.artifact_status == "complete"
    assert failed.completed_runs == 64
    assert "declared validation failure" in failed.error
    assert len(list((store.trial_dir(investigation.trial_id) / "runs").glob("*.json"))) == 64
    assert store.read_investigation(investigation.investigation_id).next_action == "replay"


def test_execution_persistence_roundtrip_and_history_revision(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    manager = ExecutionManager(store)
    investigation = manager.create_investigation(make_demo_contract())
    assert InvestigationState.from_dict(investigation.to_dict()) == investigation
    assert store.read_investigation(investigation.investigation_id) == investigation

    execution = manager.queue(manager.validate(investigation.investigation_id).investigation_id)
    assert ExecutionRecord.from_dict(execution.to_dict()) == execution
    assert store.read_execution(execution.execution_id) == execution
    assert store.execution_path(execution.execution_id).read_bytes() == canonical_bytes({
        **execution.to_dict(), "artifact_hash": content_hash(execution)
    })

    entry = {
        "at": "2026-01-01T00:00:00+00:00",
        "status": "running",
        "completed_runs": 1,
        "artifact_status": "partial",
        "note": "manual progress",
    }
    updated = replace(execution, completed_runs=1, history=(*execution.history, entry))
    store.write_execution(updated)
    assert store.read_execution(execution.execution_id).history[:len(execution.history)] == \
        execution.history
    with pytest.raises(ArtifactConflictError):
        store.write_execution(execution)

    current = store.read_investigation(investigation.investigation_id)
    advanced = replace(
        current,
        completed_runs=1,
        revision=current.revision + 1,
    )
    store.write_investigation(advanced)
    assert store.read_investigation(investigation.investigation_id).revision == \
        current.revision + 1
    with pytest.raises(ArtifactConflictError):
        store.write_investigation(replace(advanced, revision=0))
    with pytest.raises(ArtifactPathError):
        store.execution_path("../escape")
    with pytest.raises(ValueError):
        replace(execution, kind="other")
    with pytest.raises(ValueError):
        replace(investigation, artifact_status="unknown")


def test_validate_failure_can_retry_and_succeed(tmp_path, monkeypatch):
    import hsr_nous.research.core.execution as execution_module

    store = ArtifactStore(tmp_path / "artifacts")
    manager = ExecutionManager(store)
    investigation = manager.create_investigation(make_demo_contract())
    real_collect = execution_module.collect_research_fingerprint
    calls = 0

    def flaky_collect(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient fingerprint failure")
        return real_collect(*args, **kwargs)

    monkeypatch.setattr(execution_module, "collect_research_fingerprint", flaky_collect)
    with pytest.raises(RuntimeError, match="transient"):
        manager.validate(investigation.investigation_id)
    failed = store.read_investigation(investigation.investigation_id)
    assert failed.status == "failed"
    assert failed.next_action == "validate"
    assert failed.trial_id is None

    validated = manager.validate(investigation.investigation_id)
    assert validated.status == "validated"
    assert validated.next_action == "queue"
    assert validated.trial_id is not None
    assert calls == 2


def test_cache_requires_a_readable_valid_report(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    manager = ExecutionManager(store)
    investigation = manager.create_investigation(make_demo_contract())
    investigation = manager.validate(investigation.investigation_id)
    execution = manager.queue(investigation.investigation_id)
    manager.execute(execution.execution_id)
    reports = list((store.trial_dir(investigation.trial_id) / "reports").glob("*.json"))
    assert reports
    for path in reports:
        path.unlink()

    with pytest.raises(ValueError, match="report"):
        manager.cache(investigation.investigation_id)
    assert store.read_investigation(investigation.investigation_id).execution_ids == (
        execution.execution_id,
    )
