"""Persistent candidate tasks, detached workers, and durable notifications."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable

from hsr_nous.common import repo_root
from hsr_nous.research.core.artifacts import ArtifactStore, make_investigation_id
from hsr_nous.research.core.candidates import CandidateRunner, _Evaluation
from hsr_nous.research.core.runner import RunCancelledError
from hsr_nous.research.protocol import resolve_protocol, validate_candidate_set
from hsr_nous.research.schema import (
    CandidateSet,
    CandidateTask,
    CandidateTaskEvent,
    canonical_bytes,
    canonical_json,
    content_hash,
)

_TERMINAL = {"completed", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class CandidateTaskStore:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store
        self.root = store._safe_path(store.root / "candidate_tasks")
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def identity(candidate_set: CandidateSet) -> str:
        return content_hash({
            "schema_version": "candidate-task-v1",
            "candidate_set_id": candidate_set.candidate_set_id,
        })

    def task_dir(self, task_id: str) -> Path:
        self.store._validate_id(task_id, "task_id")
        return self.store._safe_path(self.root / task_id)

    def task_path(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "task.json"

    def create(self, candidate_set: CandidateSet) -> CandidateTask:
        task_id = self.identity(candidate_set)
        if self.task_path(task_id).exists():
            return self.read(task_id)
        now = _now()
        task = CandidateTask(
            task_id=task_id,
            candidate_set=candidate_set,
            investigation_ids=tuple(
                make_investigation_id(contract) for contract in candidate_set.candidates
            ),
            status="queued",
            artifact_status="partial",
            attempt=1,
            revision=1,
            created_at=now,
            updated_at=now,
            history=({
                "at": now,
                "status": "queued",
                "attempt": 1,
                "note": "candidate task created",
            },),
        )
        self._write_new(task)
        return task

    def _write_new(self, task: CandidateTask) -> None:
        payload = task.to_dict()
        payload["artifact_hash"] = content_hash(task)
        self.store._publish_json(self.task_path(task.task_id), payload)

    def read(self, task_id: str) -> CandidateTask:
        payload = self.store._read_json(self.task_path(task_id))
        artifact_hash = payload.pop("artifact_hash", None)
        task = CandidateTask.from_dict(payload)
        if artifact_hash != content_hash(task) or task.task_id != task_id:
            raise ValueError("candidate task identity or content hash mismatch")
        if task_id != self.identity(task.candidate_set):
            raise ValueError("candidate task does not match its CandidateSet")
        return task

    def write(self, task: CandidateTask) -> CandidateTask:
        path = self.task_path(task.task_id)
        previous = self.read(task.task_id)
        if task.created_at != previous.created_at:
            raise ValueError("candidate task created_at cannot change")
        if task.revision < previous.revision:
            raise ValueError("candidate task revision cannot move backwards")
        if task.history[:len(previous.history)] != previous.history:
            raise ValueError("candidate task history cannot be rewritten")
        if canonical_json(task.candidate_set) != canonical_json(previous.candidate_set):
            raise ValueError("candidate task CandidateSet cannot change")
        payload = task.to_dict()
        payload["artifact_hash"] = content_hash(task)
        self.store._publish_json(path, payload, overwrite=True)
        return task

    def transition(
        self,
        task: CandidateTask,
        status: str,
        *,
        artifact_status: str | None = None,
        report_id: str | None = None,
        error: str | None = None,
        note: str,
    ) -> CandidateTask:
        with _locked(self.task_dir(task.task_id) / "control" / "state.lock"):
            current = self.read(task.task_id)
            if current.status in _TERMINAL:
                return current
            if current.status == "cancel_requested" and status == "running":
                return current
            now = _now()
            updated = replace(
                current,
                status=status,
                artifact_status=artifact_status or current.artifact_status,
                report_id=report_id,
                error=error,
                revision=current.revision + 1,
                updated_at=now,
                history=(*current.history, {
                    "at": now,
                    "status": status,
                    "attempt": current.attempt,
                    "note": note,
                }),
            )
            return self.write(updated)

    def emit(
        self,
        task: CandidateTask,
        kind: str,
        *,
        contract_id: str | None = None,
        report_id: str | None = None,
    ) -> CandidateTaskEvent:
        with _locked(self.task_dir(task.task_id) / "control" / "events.lock"):
            if kind in _TERMINAL:
                for existing in self.events(task.task_id):
                    if existing.attempt == task.attempt and existing.kind == kind:
                        return existing
            payload = {
                "task_id": task.task_id,
                "kind": kind,
                "status": task.status,
                "attempt": task.attempt,
                "created_at": _now(),
                "contract_id": contract_id,
                "report_id": report_id if report_id is not None else task.report_id,
            }
            event = CandidateTaskEvent(event_id=content_hash(payload), **payload)
            path = self.task_dir(task.task_id) / "events.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(fd, canonical_bytes(event) + b"\n")
                os.fsync(fd)
            finally:
                os.close(fd)
            return event

    def events(self, task_id: str, after_event_id: str = "") -> list[CandidateTaskEvent]:
        path = self.task_dir(task_id) / "events.jsonl"
        if not path.exists():
            return []
        raw = path.read_bytes()
        lines = raw.splitlines(keepends=True)
        events = []
        for line in lines:
            if not line.endswith(b"\n"):
                continue
            payload = json.loads(line)
            event = CandidateTaskEvent.from_dict(payload)
            identity = event.to_dict()
            identity.pop("event_id")
            if event.task_id != task_id or event.event_id != content_hash(identity):
                raise ValueError("candidate task event identity or content hash mismatch")
            events.append(event)
        if after_event_id:
            identities = [event.event_id for event in events]
            if after_event_id not in identities:
                raise ValueError("unknown candidate task event cursor")
            events = events[identities.index(after_event_id) + 1:]
        return events

    def _result_path(self, task: CandidateTask, contract) -> Path:
        return self.task_dir(task.task_id) / "results" / f"{content_hash(contract)}.json"

    def publish_result(self, task: CandidateTask, evaluation: _Evaluation) -> None:
        payload = {
            "contract_id": evaluation.contract.contract_id,
            "status": evaluation.status,
            "trial_id": evaluation.trial_id,
            "report_id": evaluation.report_id,
            "error": evaluation.error,
        }
        payload["result_hash"] = content_hash(payload)
        path = self._result_path(task, evaluation.contract)
        if path.exists():
            self._result(task, evaluation.contract)
        self.store._publish_json(path, payload, overwrite=True)

    def _result(self, task: CandidateTask, contract) -> dict[str, Any] | None:
        path = self._result_path(task, contract)
        if not path.exists():
            return None
        payload = self.store._read_json(path)
        result_hash = payload.pop("result_hash", None)
        if result_hash != content_hash(payload) or payload["contract_id"] != contract.contract_id:
            raise ValueError("candidate task result identity mismatch")
        return payload

    def view(self, task: CandidateTask) -> dict[str, Any]:
        candidates = []
        completed_runs = 0
        total_runs = 0
        for contract, investigation_id in zip(
            task.candidate_set.candidates, task.investigation_ids
        ):
            required = resolve_protocol(contract.protocol_id).required_runs
            status = "draft"
            completed = 0
            trial_id = None
            if self.store.investigation_path(investigation_id).exists():
                investigation = self.store.read_investigation(investigation_id)
                status = investigation.status
                completed = investigation.completed_runs
                trial_id = investigation.trial_id
            completed_runs += completed
            total_runs += required
            candidates.append({
                "contract_id": contract.contract_id,
                "investigation_id": investigation_id,
                "status": status,
                "completed_runs": completed,
                "total_runs": required,
                "trial_id": trial_id,
                "result": self._result(task, contract),
            })
        return json.loads(canonical_json({
            **task.to_dict(),
            "candidate_set_id": task.candidate_set.candidate_set_id,
            "completed_runs": completed_runs,
            "total_runs": total_runs,
            "candidates": candidates,
        }))

    def cancel_path(self, task: CandidateTask) -> Path:
        return self.task_dir(task.task_id) / "control" / f"cancel-{task.attempt}.json"

    def request_cancel(self, task: CandidateTask) -> None:
        self.store._publish_json(self.cancel_path(task), {
            "task_id": task.task_id,
            "attempt": task.attempt,
            "created_at": _now(),
        })

    def cancel_requested(self, task: CandidateTask) -> bool:
        return self.cancel_path(task).exists()

    def start_lock(self, task: CandidateTask) -> Path:
        return self.task_dir(task.task_id) / "control" / "start.lock"

    def execution_lock(self) -> Path:
        return self.root / "execution.lock"

    def worker_path(self, task: CandidateTask) -> Path:
        return self.task_dir(task.task_id) / "control" / f"worker-{task.attempt}.json"

    def write_worker(self, task: CandidateTask, **payload: Any) -> None:
        self.store._publish_json(self.worker_path(task), payload, overwrite=True)

    def read_worker(self, task: CandidateTask) -> dict[str, Any] | None:
        path = self.worker_path(task)
        return self.store._read_json(path) if path.exists() else None


class CandidateTaskManager:
    def __init__(
        self,
        store: ArtifactStore,
        *,
        runner: CandidateRunner | None = None,
        launcher: Callable[[CandidateTask, Path], int] | None = None,
    ) -> None:
        self.store = store
        self.tasks = CandidateTaskStore(store)
        self.runner = runner or CandidateRunner(store)
        self._launcher = launcher or self._spawn
        self._processes: dict[tuple[str, int], subprocess.Popen] = {}

    def _spawn(self, task: CandidateTask, log_path: Path) -> int:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.store.root.parent / "home"),
            "HSR_NOUS_RESEARCH_ROOT": str(self.store.root.parent),
            "PYTHONPATH": str(repo_root() / "src"),
            "PYTHONUNBUFFERED": "1",
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "hsr_nous.research.core.candidate_worker", task.task_id],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=repo_root(),
                env=env,
                start_new_session=True,
            )
        self._processes[(task.task_id, task.attempt)] = process
        return process.pid

    def _launch(self, task: CandidateTask) -> None:
        log_path = self.tasks.task_dir(task.task_id) / "worker.log"
        try:
            pid = self._launcher(task, log_path)
        except Exception as error:
            failed = self.tasks.transition(
                task, "failed", error=f"{type(error).__name__}: {error}",
                note="worker launch failed",
            )
            self.tasks.emit(failed, "failed")
            return
        self.tasks.write_worker(task, pid=pid, attempt=task.attempt, started_at=_now())

    def _alive(self, task: CandidateTask) -> bool:
        process = self._processes.get((task.task_id, task.attempt))
        if process is not None:
            return process.poll() is None
        worker = self.tasks.read_worker(task)
        if worker is None:
            return False
        try:
            os.kill(worker["pid"], 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _reconcile(self, task: CandidateTask) -> CandidateTask:
        if (task.status not in _TERMINAL and self.tasks.read_worker(task) is not None
                and not self._alive(task)):
            task = self.tasks.transition(
                task, "failed", error="worker exited before a terminal event",
                note="stale worker reconciled",
            )
            self.tasks.emit(task, "failed")
        return task

    def start(self, candidate_set: CandidateSet) -> dict[str, Any]:
        validate_candidate_set(candidate_set)
        task = self.tasks.create(candidate_set)
        with _locked(self.tasks.start_lock(task)):
            task = self.tasks.read(task.task_id)
            if task.status in _TERMINAL or self._alive(task):
                return self.tasks.view(task)
            self._launch(task)
        return self.read(task.task_id)

    def read(self, task_id: str) -> dict[str, Any]:
        task = self._reconcile(self.tasks.read(task_id))
        return self.tasks.view(task)

    def cancel(self, task_id: str) -> dict[str, Any]:
        task = self._reconcile(self.tasks.read(task_id))
        if task.status in _TERMINAL:
            return self.tasks.view(task)
        self.tasks.request_cancel(task)
        if task.status != "cancel_requested":
            task = self.tasks.transition(
                task, "cancel_requested", error="cancellation requested",
                note="candidate task cancellation requested",
            )
            if task.status == "cancel_requested":
                self.tasks.emit(task, "cancel_requested")
        return self.tasks.view(task)

    def resume(self, task_id: str) -> dict[str, Any]:
        task = self.tasks.read(task_id)
        with _locked(self.tasks.start_lock(task)):
            task = self.tasks.read(task_id)
            if task.status not in {"failed", "cancelled"} or task.artifact_status != "partial":
                raise ValueError("only failed/cancelled partial candidate tasks can resume")
            exit_deadline = time.monotonic() + 5
            while self._alive(task) and time.monotonic() < exit_deadline:
                time.sleep(0.01)
            if self._alive(task):
                raise ValueError("an active worker still owns this candidate task")
            self._recover_investigations(task)
            now = _now()
            task = replace(
                task,
                status="queued",
                attempt=task.attempt + 1,
                revision=task.revision + 1,
                updated_at=now,
                report_id=None,
                error=None,
                history=(*task.history, {
                    "at": now,
                    "status": "queued",
                    "attempt": task.attempt + 1,
                    "note": "candidate task resume queued",
                }),
            )
            self.tasks.write(task)
            self.tasks.emit(task, "queued")
            self._launch(task)
        return self.read(task_id)

    def _recover_investigations(self, task: CandidateTask) -> None:
        manager = self.runner._manager
        for investigation_id in task.investigation_ids:
            if not self.store.investigation_path(investigation_id).exists():
                continue
            investigation = self.store.read_investigation(investigation_id)
            if investigation.status in {"queued", "running", "cancel_requested", "validating"}:
                manager.recover(investigation_id)

    def run(self, task_id: str) -> dict[str, Any]:
        with _locked(self.tasks.execution_lock()):
            task = self.tasks.read(task_id)
            if task.status in _TERMINAL:
                return self.tasks.view(task)
            if self.tasks.cancel_requested(task):
                task = self.tasks.transition(
                    task, "cancelled", error="cancelled before execution",
                    note="candidate task cancelled",
                )
                self.tasks.emit(task, "cancelled")
                return self.tasks.view(task)
            task = self.tasks.transition(task, "running", note="candidate worker started")
            self.tasks.emit(task, "started")

            def observer(_completed: int, _total: int) -> None:
                if self.tasks.cancel_requested(task):
                    raise RunCancelledError("candidate task cancellation requested")

            def on_candidate(evaluation: _Evaluation) -> None:
                self.tasks.publish_result(task, evaluation)
                self.tasks.emit(
                    task, "candidate_finished",
                    contract_id=evaluation.contract.contract_id,
                    report_id=evaluation.report_id,
                )

            try:
                report = self.runner.run(
                    task.candidate_set,
                    observer=observer,
                    should_cancel=lambda: self.tasks.cancel_requested(task),
                    on_candidate=on_candidate,
                )
            except RunCancelledError as error:
                task = self.tasks.transition(
                    task, "cancelled", error=str(error), note="candidate task cancelled safely",
                )
                self.tasks.emit(task, "cancelled")
            except Exception as error:
                task = self.tasks.transition(
                    task, "failed", error=f"{type(error).__name__}: {error}",
                    note="candidate worker failed; retained evidence preserved",
                )
                self.tasks.emit(task, "failed")
            else:
                status = "completed" if report["status"] in {"accepted", "inconclusive"} else "failed"
                task = self.tasks.transition(
                    task,
                    status,
                    artifact_status="complete",
                    report_id=report["report_id"],
                    error=None if status == "completed" else "all candidates failed",
                    note="candidate report composed",
                )
                self.tasks.emit(task, status, report_id=report["report_id"])
            return self.tasks.view(task)

    def wait(
        self,
        task_id: str,
        *,
        after_event_id: str = "",
        timeout_s: float = 30,
    ) -> dict[str, Any]:
        if not 0 <= timeout_s <= 300:
            raise ValueError("timeout_s must be between 0 and 300")
        deadline = time.monotonic() + timeout_s
        while True:
            task = self._reconcile(self.tasks.read(task_id))
            events = self.tasks.events(task_id, after_event_id)
            if events or task.status in _TERMINAL or time.monotonic() >= deadline:
                return {
                    "task": self.tasks.view(task),
                    "events": [event.to_dict() for event in events],
                }
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))

    def wait_terminal(self, task_id: str, *, timeout_s: float | None = None) -> dict[str, Any]:
        deadline = None if timeout_s is None else time.monotonic() + timeout_s
        cursor = ""
        while True:
            remaining = None if deadline is None else max(0, deadline - time.monotonic())
            if remaining is not None and remaining <= 0:
                raise TimeoutError("candidate task did not reach a terminal state before timeout")
            result = self.wait(
                task_id,
                after_event_id=cursor,
                timeout_s=1 if remaining is None else min(1, remaining),
            )
            task = result["task"]
            if task["status"] in _TERMINAL:
                return task
            if result["events"]:
                cursor = result["events"][-1]["event_id"]
