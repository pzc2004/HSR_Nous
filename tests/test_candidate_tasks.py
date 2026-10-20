from __future__ import annotations

import os
import signal
import time

import pytest

from hsr_nous.research.core import ArtifactStore, CandidateRunner, CandidateTaskManager
from hsr_nous.research.permissions import open_research_gateway
from hsr_nous.research.permissions.policy import CapabilityPolicy, PermissionDeniedError
from tests._research_builders import make_candidate_set


def _wait_for_progress(manager, task_id, minimum, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = manager.read(task_id)
        if task["completed_runs"] >= minimum:
            return task
        time.sleep(0.02)
    raise AssertionError("candidate task did not reach the expected progress")


def test_candidate_task_background_completion_events_and_dedup(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    manager = CandidateTaskManager(store)
    plan = make_candidate_set((600.0, 550.0))

    started = manager.start(plan)
    assert started["status"] in {"queued", "running"}
    assert started["total_runs"] == 128
    assert manager.start(plan)["task_id"] == started["task_id"]
    assert manager.start(plan)["attempt"] == 1

    final = manager.wait_terminal(started["task_id"], timeout_s=120)
    assert final["status"] == "completed"
    assert final["artifact_status"] == "complete"
    assert final["completed_runs"] == 128
    assert final["report_id"]
    assert all(candidate["result"]["report_id"] for candidate in final["candidates"])
    assert CandidateRunner(store).validate_report(plan, final["report_id"])

    events = manager.tasks.events(final["task_id"])
    completed = [event for event in events if event.kind == "completed"]
    assert len(completed) == 1
    waited = manager.wait(final["task_id"], after_event_id="", timeout_s=0)
    assert waited["events"][-1]["kind"] == "completed"
    assert manager.wait(
        final["task_id"], after_event_id=completed[0].event_id, timeout_s=0
    )["events"] == []
    assert CandidateTaskManager(store).read(final["task_id"])["report_id"] == final["report_id"]


def test_candidate_task_cancel_resume_preserves_partial_evidence(tmp_path):
    manager = CandidateTaskManager(ArtifactStore(tmp_path / "artifacts"))
    plan = make_candidate_set((600.0, 550.0, 500.0))
    started = manager.start(plan)
    task_id = started["task_id"]
    _wait_for_progress(manager, task_id, 2)

    requested = manager.cancel(task_id)
    assert requested["status"] == "cancel_requested"
    cancelled = manager.wait_terminal(task_id, timeout_s=30)
    assert cancelled["status"] == "cancelled"
    assert cancelled["artifact_status"] == "partial"
    assert cancelled["completed_runs"] < 192
    assert cancelled["report_id"] is None

    resumed = manager.resume(task_id)
    assert resumed["attempt"] == 2
    final = manager.wait_terminal(task_id, timeout_s=120)
    assert final["status"] == "completed"
    assert final["completed_runs"] == 192
    assert final["report_id"]
    kinds = [event.kind for event in manager.tasks.events(task_id)]
    assert "cancel_requested" in kinds and "cancelled" in kinds and "completed" in kinds


def test_candidate_task_recovers_after_worker_crash(tmp_path):
    manager = CandidateTaskManager(ArtifactStore(tmp_path / "artifacts"))
    plan = make_candidate_set((600.0, 550.0, 500.0))
    started = manager.start(plan)
    task_id = started["task_id"]
    _wait_for_progress(manager, task_id, 2)
    task = manager.tasks.read(task_id)
    worker = manager.tasks.read_worker(task)
    assert worker and worker["pid"] != os.getpid()
    os.kill(worker["pid"], signal.SIGKILL)

    failed = manager.wait_terminal(task_id, timeout_s=30)
    assert failed["status"] == "failed"
    assert failed["artifact_status"] == "partial"
    assert failed["completed_runs"] < 192

    manager.resume(task_id)
    final = manager.wait_terminal(task_id, timeout_s=120)
    assert final["status"] == "completed"
    assert final["completed_runs"] == 192
    assert final["report_id"]


def test_candidate_task_event_rejects_cross_task_copy(tmp_path):
    manager = CandidateTaskManager(ArtifactStore(tmp_path / "artifacts"))
    first = manager.tasks.create(make_candidate_set((600.0, 550.0)))
    second = manager.tasks.create(make_candidate_set((600.0, 500.0)))
    manager.tasks.emit(first, "queued")
    source = manager.tasks.task_dir(first.task_id) / "events.jsonl"
    target = manager.tasks.task_dir(second.task_id) / "events.jsonl"
    target.write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="identity"):
        manager.tasks.events(second.task_id)


def test_candidate_task_resume_requires_submit_permission(tmp_path):
    policy = CapabilityPolicy(allowed_project_root=tmp_path, allow_submit_claim=False)
    gateway = open_research_gateway(tmp_path, policy=policy)
    with pytest.raises(PermissionDeniedError):
        gateway.resume_candidate_task("0" * 64)
