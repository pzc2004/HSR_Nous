from __future__ import annotations

from dataclasses import replace

import pytest

from hsr_nous.research.core import ArtifactIntegrityError, ArtifactStore, CandidateRunner
from hsr_nous.research.protocol import ProtocolValidationError, validate_candidate_set
from hsr_nous.research.schema import CandidateSet, canonical_bytes, content_hash
from tests._research_builders import make_acheron_candidate_set, make_candidate_set


def test_candidate_set_validation_rejects_inconsistent_plans():
    plan = make_candidate_set()
    with pytest.raises(ProtocolValidationError, match="duplicate contract_id"):
        validate_candidate_set(CandidateSet(
            question=plan.question,
            candidates=(plan.candidates[0], plan.candidates[0]),
            top_k=1,
        ))
    with pytest.raises(ProtocolValidationError, match="CandidateSet question"):
        validate_candidate_set(CandidateSet(
            question=plan.question,
            candidates=(plan.candidates[0], replace(
                plan.candidates[1], question="different question"
            )),
            top_k=1,
        ))
    with pytest.raises(ProtocolValidationError, match="share build"):
        validate_candidate_set(CandidateSet(
            question=plan.question,
            candidates=(plan.candidates[0], replace(
                plan.candidates[1],
                experiment=replace(plan.candidates[1].experiment, build={"different": True}),
            )),
            top_k=1,
        ))
    with pytest.raises(ProtocolValidationError, match="at most 16"):
        validate_candidate_set(make_candidate_set(tuple(range(17))))
    with pytest.raises(ValueError, match="top_k"):
        CandidateSet(question=plan.question, candidates=plan.candidates, top_k=0)


def test_candidate_set_full_execution_selection_and_determinism(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    runner = CandidateRunner(store)
    plan = make_candidate_set((600.0, 550.0, 500.0), top_k=2)

    report = runner.run(plan)
    assert report["schema_version"] == "candidate-v1"
    assert report["candidate_set_id"] == plan.candidate_set_id == content_hash(plan)
    assert report["status"] == "accepted"
    assert report["selected"] == ["candidate-0", "candidate-1"]
    assert [item["contract_id"] for item in report["dev_ranking"]] == [
        "candidate-0", "candidate-1", "candidate-2"
    ]
    assert report["selection"]["adjusted_confidence"] == pytest.approx(1 - 0.05 / 3)

    for candidate in report["candidates"]:
        assert candidate["trial_id"]
        assert candidate["report_id"]
        assert candidate["dev"] is not None
        assert candidate["holdout"] is not None
        assert candidate["holdout_adjusted"]["confidence_interval"]["confidence"] == \
            pytest.approx(1 - 0.05 / 3)
    assert not next(
        candidate for candidate in report["candidates"]
        if candidate["contract_id"] == "candidate-2"
    )["selected"]

    assert runner.validate(plan)["report_id"] == report["report_id"]
    assert runner.validate_report(plan, report["report_id"])["report_id"] == report["report_id"]
    assert runner.run(plan)["report_id"] == report["report_id"]


def test_candidate_set_no_winner_is_inconclusive(tmp_path):
    report = CandidateRunner(ArtifactStore(tmp_path / "artifacts")).run(
        make_candidate_set((529.2, 500.0), top_k=1)
    )
    assert report["status"] == "inconclusive"
    assert report["selected"] == []
    assert len(report["candidates"]) == 2


def test_candidate_set_failed_candidate_is_retained(tmp_path):
    plan = make_candidate_set((600.0, 550.0), top_k=1)
    broken = replace(
        plan.candidates[1],
        experiment=replace(
            plan.candidates[1].experiment,
            variant=replace(
                plan.candidates[1].experiment.variant,
                patches=(replace(
                    plan.candidates[1].experiment.variant.patches[0],
                    template_id="missing-template",
                ),),
            ),
        ),
    )
    report = CandidateRunner(ArtifactStore(tmp_path / "artifacts")).run(
        replace(plan, candidates=(plan.candidates[0], broken))
    )
    assert report["status"] == "accepted"
    failed = next(
        candidate for candidate in report["candidates"]
        if candidate["contract_id"] == broken.contract_id
    )
    assert failed["status"] == "failed"
    assert failed["error"]
    assert failed["selected"] is False
    assert len(report["candidates"]) == 2


def test_candidate_set_configuration_candidates(tmp_path):
    report = CandidateRunner(ArtifactStore(tmp_path / "artifacts")).run(
        make_acheron_candidate_set()
    )
    assert report["scope"]["comparison_kind"] == "configuration"
    assert len(report["candidates"]) == 3
    assert all(candidate["trial_id"] for candidate in report["candidates"])
    assert all(candidate["report_id"] for candidate in report["candidates"])


def test_candidate_report_forgery_is_rejected(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    runner = CandidateRunner(store)
    plan = make_candidate_set((600.0, 550.0))
    report = runner.run(plan)
    path = store.candidate_report_path(plan.candidate_set_id, report["report_id"])
    path.chmod(0o644)
    path.write_bytes(canonical_bytes({**report, "selected": ["forged"]}))
    with pytest.raises(ArtifactIntegrityError):
        runner.validate_report(plan, report["report_id"])
