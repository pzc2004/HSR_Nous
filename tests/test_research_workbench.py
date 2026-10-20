from __future__ import annotations

from fastapi.testclient import TestClient

from hsr_nous.research.core import ArtifactStore, CandidateTaskManager
from hsr_nous.research.permissions import open_research_gateway
from hsr_nous.research.workbench.web import create_app
from tests._research_builders import make_candidate_set


def test_workbench_read_only_task_report_and_evidence_chain(tmp_path):
    root = tmp_path / "research"
    manager = CandidateTaskManager(ArtifactStore(root / "artifacts"))
    plan = make_candidate_set((600.0, 550.0))
    started = manager.start(plan)
    final = manager.wait_terminal(started["task_id"], timeout_s=120)
    client = TestClient(create_app(gateway=open_research_gateway(root)))
    index = client.get("/")
    assert index.status_code == 200
    assert "HSR_Nous · 研究台" in index.text
    assert "伊德莉拉" not in index.text

    tasks = client.get("/api/tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == final["task_id"]
    assert tasks[0]["status"] == "completed"
    assert tasks[0]["completed_runs"] == 128

    task = client.get(f"/api/tasks/{final['task_id']}").json()
    assert task["candidate_set_id"] == final["candidate_set_id"]
    assert len(task["candidates"]) == 2
    assert all(candidate["result"]["report_id"] for candidate in task["candidates"])

    events = client.get(f"/api/tasks/{final['task_id']}/events").json()
    assert events["events"][-1]["kind"] == "completed"
    cursor = events["events"][-1]["event_id"]
    assert client.get(
        f"/api/tasks/{final['task_id']}/events", params={"after_event_id": cursor}
    ).json()["events"] == []

    report = client.get(f"/api/tasks/{final['task_id']}/report").json()
    assert report["schema_version"] == "candidate-v1"
    assert report["flags"]["validation"] == "pending_real_validation"
    assert len(report["dev_ranking"]) == 2
    candidate = report["candidates"][0]
    trial = client.get(f"/api/trials/{candidate['trial_id']}/reports/{candidate['report_id']}")
    assert trial.status_code == 200, trial.text
    trial_report = trial.json()
    assert trial_report["claim"]["status"] in {"accepted", "inconclusive"}
    assert trial_report["comparisons"]["holdout"]["effect"] is not None
    assert trial_report["cohorts"]["baseline"]["dev"]["n"] == 16

    drilldown = trial_report["evidence"]["drilldown"][0]
    run = client.post("/api/evidence", json=drilldown["run"])
    assert run.status_code == 200, run.text
    assert run.json()["kind"] == "run"
    event = client.post("/api/evidence", json=drilldown["events"][0])
    assert event.status_code == 200, event.text
    assert event.json()["kind"] == "event"
    if drilldown["modifiers"]:
        modifier = client.post("/api/evidence", json=drilldown["modifiers"][0])
        assert modifier.status_code == 200, modifier.text
        assert modifier.json()["kind"] == "modifier"

    assert client.get("/api/tasks", params={"limit": 0}).status_code == 400
    assert client.get("/api/tasks/not-a-task").status_code == 404
    assert client.post("/api/evidence", json={"unknown": True}).status_code == 400
