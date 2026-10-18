from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import hsr_nous.research_core.claims as claims_module
import hsr_nous.research_core.runner as runner_module
from hsr_nous.research_core.artifacts import ArtifactStore
from hsr_nous.research_core.claims import ClaimValidator
from hsr_nous.research_core.report import ReportComposer
from hsr_nous.research_core.runner import TrialRunner
from hsr_nous.research_schema import Claim, EvidenceLink
from tests._research_builders import make_demo_contract


def _edited(claim, edit):
    payload = claim.to_dict()
    edit(payload)
    return Claim.from_dict(payload)


def test_demo_claim_report_replay_forgeries_stale_and_drilldown(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    contract = make_demo_contract()
    artifact = TrialRunner(store).run(contract)
    validator = ClaimValidator(store)
    composer = ReportComposer(store)
    validated = validator.validate_trial(artifact.trial_id)
    assert validated.claim.status in {"accepted", "inconclusive"}
    report = composer.compose(validated)
    report_id = report["report_id"]
    assert store.read_report(artifact.trial_id, report_id) == report
    assert report["flags"] == {
        "source": "simulated",
        "world": "hypothetical",
        "validation": "pending_real_validation",
    }
    assert report["schema_version"] == "2"
    assert report["variant"]["comparison_kind"] == "mechanism"
    assert report["variant"]["world"] == "hypothetical"
    assert validated.claim.scope["comparison_kind"] == "mechanism"
    assert validated.claim.scope["world"] == "hypothetical"
    assert report["spec"]["trial_id"] == artifact.trial_id
    assert report["comparison_set"]["comparison_set_id"] == artifact.comparison_set.comparison_set_id
    assert report["fingerprint"] == artifact.fingerprint.to_dict()
    for role in ("baseline", "variant"):
        for cohort in ("dev", "holdout"):
            assert report["cohorts"][role][cohort]["n"] == 16
            assert report["cohorts"][role][cohort]["failed"] == 0
            assert report["cohorts"][role][cohort]["truncated"] == 0
    assert report["comparisons"]["holdout"]["n"] == 16
    assert report["effect"] == validated.claim.statistical_metadata["effect"]
    assert report["confidence_interval"] == validated.claim.statistical_metadata["confidence_interval"]
    assert report["derivation_steps"] == validated.claim.to_dict()["derivation_steps"]
    assert "simulated/hypothetical/pending_real_validation" in report["conclusion"]
    if validated.claim.status == "accepted":
        assert "mean total_damage" in report["conclusion"]
    else:
        assert "mean total_damage" not in report["conclusion"]

    replayed = validator.validate(validated.claim)
    replay_report = composer.compose(replayed)
    assert replay_report["report_id"] == report_id
    assert store.report_path(artifact.trial_id, report_id).read_bytes() == \
        store.report_path(artifact.trial_id, replay_report["report_id"]).read_bytes()

    premises = report["evidence"]["premises"]
    assert len(premises) == 67
    spec_resolution = store.resolve_evidence(EvidenceLink.from_dict(premises[0]))
    assert spec_resolution["status"] == "resolved"
    assert spec_resolution["kind"] == "spec"
    drilldown = report["evidence"]["drilldown"][0]
    run_link = drilldown["run"]
    assert store.resolve_evidence(EvidenceLink.from_dict(run_link))["kind"] == "run"
    event_link = drilldown["events"][0]
    assert store.resolve_evidence(EvidenceLink.from_dict(event_link))["kind"] == "event"
    modifier_link = drilldown["modifiers"][0]
    modifier = store.resolve_evidence(EvidenceLink.from_dict(modifier_link))
    assert modifier["status"] == "resolved"
    assert modifier["kind"] == "modifier"
    assert "name" in modifier["evidence"]["details"]
    unresolved = store.resolve_evidence(EvidenceLink(
        trial_id=artifact.trial_id,
        run_id=run_link["run_id"],
        modifier_id="0" * 64,
        artifact_hash=run_link["artifact_hash"],
    ))
    assert unresolved["status"] == "unresolved"
    assert "historical lifecycle" in unresolved["reason"]

    original_claim_path = store.claim_path(artifact.trial_id, validated.claim_record_id)
    original_claim_bytes = original_claim_path.read_bytes()
    edits = [
        lambda p: p["statistical_metadata"].update(effect=999.0),
        lambda p: p["statistical_metadata"]["confidence_interval"].update(upper=999.0),
        lambda p: p["statistical_metadata"].update(n=1),
        lambda p: p["derivation_steps"][0]["seeds"].__setitem__(0, 999),
        lambda p: p["scope"].update(cohort="dev"),
        lambda p: p.update(
            status="inconclusive" if validated.claim.status == "accepted" else "accepted"
        ),
        lambda p: p["premises"][0].update(artifact_hash="0" * 64),
    ]
    for edit in edits:
        rejected = validator.validate(_edited(validated.claim, edit))
        assert rejected.claim.status == "rejected"
        rejected_report = composer.compose(rejected)
        assert rejected_report["claim"]["status"] == "rejected"
        assert "effect" not in rejected_report
        assert "comparisons" not in rejected_report
        assert "mean total_damage" not in rejected_report["conclusion"]
    direct_forgery = _edited(
        validated.claim,
        lambda p: p["statistical_metadata"].update(effect=123456.0),
    )
    direct_report = composer.compose(replace(validated, claim=direct_forgery))
    assert direct_report["claim"]["status"] == "rejected"
    assert "effect" not in direct_report
    assert original_claim_path.read_bytes() == original_claim_bytes

    real_collect = claims_module.collect_research_fingerprint
    def stale_collect(*args, **kwargs):
        return replace(real_collect(*args, **kwargs), implementation_hash="stale-source")
    monkeypatch.setattr(claims_module, "collect_research_fingerprint", stale_collect)
    stale = validator.validate(validated.claim)
    assert stale.claim.status == "stale"
    assert stale.claim_record_id is None
    stale_report = composer.compose(stale)
    assert stale_report["claim"]["status"] == "stale"
    assert "effect" not in stale_report
    assert "comparisons" not in stale_report
    assert "actor_damage" not in stale_report
    assert "mean total_damage" not in stale_report["conclusion"]
    assert original_claim_path.read_bytes() == original_claim_bytes
    assert store.read_report(artifact.trial_id, report_id) == report


def test_real_failed_sample_deletion_is_rejected_and_report_has_no_direction(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    runner = TrialRunner(store)
    real_compile = runner_module.compile_encounter

    def fail_variant(*args, **kwargs):
        roots = kwargs.get("template_roots") or ()
        if roots and "variants" in Path(roots[0]).parts:
            raise RuntimeError("declared variant compile failure")
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(runner_module, "compile_encounter", fail_variant)
    artifact = runner.run(make_demo_contract())
    validator = ClaimValidator(store)
    inconclusive = validator.validate_trial(artifact.trial_id)
    assert inconclusive.claim.status == "inconclusive"
    assert "failed" in inconclusive.claim.failure_reason
    composer = ReportComposer(store)
    report = composer.compose(inconclusive)
    assert report["comparisons"]["holdout"] is None
    assert "mean total_damage" not in report["conclusion"]

    failed_run_id = next(
        run_id for run_id in artifact.run_ids
        if store.read_run(artifact.trial_id, run_id).status == "failed"
    )
    store.run_path(artifact.trial_id, failed_run_id).unlink()
    rejected = validator.validate(inconclusive.claim)
    assert rejected.claim.status == "rejected"
    rejected_report = composer.compose(rejected)
    assert rejected_report["claim"]["status"] == "rejected"
    assert "effect" not in rejected_report
    assert "comparisons" not in rejected_report
    assert "mean total_damage" not in rejected_report["conclusion"]


def _assert_64_configuration(artifact):
    assert len(artifact.run_ids) == 64
    comparison = artifact.comparison_set
    assert artifact.run_ids == (
        *comparison.baseline_dev,
        *comparison.baseline_holdout,
        *comparison.variant_dev,
        *comparison.variant_holdout,
    )


def _assert_canonical_configuration_report(report, claim):
    assert report["schema_version"] == "2"
    assert report["variant"]["comparison_kind"] == "configuration"
    assert report["variant"]["world"] == "canonical"
    assert report["variant"]["metadata"]["comparison_kind"] == "configuration"
    assert report["variant"]["metadata"]["world"] == "canonical"
    assert claim.scope["comparison_kind"] == "configuration"
    assert claim.scope["world"] == "canonical"
    assert report["flags"] == {
        "source": "simulated",
        "world": "canonical",
        "validation": "pending_real_validation",
    }
    assert report["conclusion"].startswith("simulated/canonical/pending_real_validation")
    assert "hypothetical" not in report["conclusion"]


def test_acheron_feet_configuration_real_64_and_attack_main_wins(tmp_path, monkeypatch):
    import json

    from tests._research_builders import make_acheron_feet_contract

    store = ArtifactStore(tmp_path / "artifacts")
    contract = make_acheron_feet_contract()
    real_compile = runner_module.compile_encounter
    effective_builds = []

    def capture_compile(build, stage, **kwargs):
        effective_builds.append(build)
        return real_compile(build, stage, **kwargs)

    monkeypatch.setattr(runner_module, "compile_encounter", capture_compile)
    artifact = TrialRunner(store).run(contract)
    assert artifact.status == "completed"
    _assert_64_configuration(artifact)
    assert effective_builds == [contract.experiment.build, contract.experiment.variant.build_override]
    assert effective_builds[0]["build"]["team"][0]["relics"]["feet"]["main"] == "spd"
    assert effective_builds[1]["build"]["team"][0]["relics"]["feet"]["main"] == "atk_pct"

    validated = ClaimValidator(store).validate_trial(artifact.trial_id)
    assert validated.claim.status == "accepted"
    assert validated.claim.statistical_metadata["effect"] > 0
    assert validated.claim.statistical_metadata["confidence_interval"]["lower"] > 0
    report = ReportComposer(store).compose(validated)
    _assert_canonical_configuration_report(report, validated.claim)
    _, metadata = store.read_variant(
        artifact.trial_id, report["variant"]["metadata"]["variant_id"]
    )
    assert metadata["documents"] == []
    build = json.loads((store.trial_dir(artifact.trial_id) / "variants" /
                        metadata["variant_id"] / "build.json").read_bytes())
    assert build["build"]["team"][0]["relics"]["feet"] == {
        "set_id": "101", "main": "atk_pct", "subs": {}
    }


def test_acheron_team_configuration_real_64_and_canonical_lineage(tmp_path, monkeypatch):
    from tests._research_builders import make_acheron_team_contract

    store = ArtifactStore(tmp_path / "artifacts")
    contract = make_acheron_team_contract()
    real_compile = runner_module.compile_encounter
    teams = []

    def capture_compile(build, stage, **kwargs):
        compiled = real_compile(build, stage, **kwargs)
        teams.append([actor.actor_id for actor in compiled.build_team])
        return compiled

    monkeypatch.setattr(runner_module, "compile_encounter", capture_compile)
    artifact = TrialRunner(store).run(contract)
    assert artifact.status == "completed"
    _assert_64_configuration(artifact)
    assert teams == [["1308", "1403", "1304"], ["1308", "1202", "1304"]]

    validated = ClaimValidator(store).validate_trial(artifact.trial_id)
    assert validated.claim.status in {"accepted", "inconclusive"}
    report = ReportComposer(store).compose(validated)
    _assert_canonical_configuration_report(report, validated.claim)
    records = [store.read_run(artifact.trial_id, run_id) for run_id in artifact.run_ids]
    by_key = {(record.arm_id, record.cohort, record.seed): record for record in records}
    for record in records:
        if record.arm_id == "variant":
            assert record.parent_run_id == by_key["baseline", record.cohort, record.seed].run_id
    run_link = report["evidence"]["drilldown"][0]["run"]
    assert store.resolve_evidence(EvidenceLink.from_dict(run_link))["kind"] == "run"


def test_acheron_cipher_whiteboard_four_person_actor_damage(tmp_path, monkeypatch):
    import json

    from tests._research_builders import make_acheron_cipher_contract

    contract = make_acheron_cipher_contract()
    for name in ("Acheron", "Jiaoqiu", "Tribbie", "Cipher", "Aventurine"):
        assert name in contract.question
    for actor_id in ("1308", "1218", "1403", "1406", "1304"):
        assert actor_id not in contract.question
    for member in contract.experiment.build["build"]["team"]:
        assert "relics" not in member and "light_cone_template" not in member

    store = ArtifactStore(tmp_path / "artifacts")
    real_compile = runner_module.compile_encounter
    teams = []

    def capture_compile(build, stage, **kwargs):
        compiled = real_compile(build, stage, **kwargs)
        teams.append([actor.actor_id for actor in compiled.build_team])
        return compiled

    monkeypatch.setattr(runner_module, "compile_encounter", capture_compile)
    artifact = TrialRunner(store).run(contract)
    assert artifact.status == "completed"
    _assert_64_configuration(artifact)
    assert teams == [
        ["1308", "1218", "1403", "1304"],
        ["1308", "1218", "1406", "1304"],
    ]

    validated = ClaimValidator(store).validate_trial(artifact.trial_id)
    assert validated.claim.status in {"accepted", "inconclusive"}
    report = ReportComposer(store).compose(validated)
    _assert_canonical_configuration_report(report, validated.claim)
    _, metadata = store.read_variant(
        artifact.trial_id, report["variant"]["metadata"]["variant_id"]
    )
    build = json.loads((store.trial_dir(artifact.trial_id) / "variants" /
                        metadata["variant_id"] / "build.json").read_bytes())
    assert [member["character_template"] for member in build["build"]["team"]] == \
        ["1308", "1218", "1406", "1304"]

    actor_damage = report["actor_damage"]
    expected_names = {
        "1308": "黄泉",
        "1218": "椒丘",
        "1304": "砂金",
        "1403": "缇宝",
        "1406": "赛飞儿",
    }
    for cohort in ("dev", "holdout"):
        baseline = actor_damage["baseline"][cohort]
        variant = actor_damage["variant"][cohort]
        for actor_id in ("1308", "1218", "1304"):
            for arm in (baseline, variant):
                assert arm[actor_id]["status"] == "present"
                assert arm[actor_id]["n"] == 16
                assert arm[actor_id]["distribution"] is not None
                assert arm[actor_id]["display_name"] == expected_names[actor_id]
        assert baseline["1403"]["status"] == "present"
        assert baseline["1403"]["n"] == 16
        assert baseline["1406"] == {
            "status": "absent",
            "display_name": "赛飞儿",
            "n": 0,
            "distribution": None,
        }
        assert variant["1406"]["status"] == "present"
        assert variant["1406"]["n"] == 16
        assert variant["1403"] == {
            "status": "absent",
            "display_name": "缇宝",
            "n": 0,
            "distribution": None,
        }
    assert "actor_damage" not in validated.claim.statistical_metadata
    assert report["effect"] == validated.claim.statistical_metadata["effect"]

    records = [store.read_run(artifact.trial_id, run_id) for run_id in artifact.run_ids]
    by_key = {(record.arm_id, record.cohort, record.seed): record for record in records}
    for record in records:
        if record.arm_id == "variant":
            assert record.parent_run_id == by_key["baseline", record.cohort, record.seed].run_id
    run_link = report["evidence"]["drilldown"][0]["run"]
    assert store.resolve_evidence(EvidenceLink.from_dict(run_link))["kind"] == "run"

    forged = _edited(
        validated.claim,
        lambda p: p["statistical_metadata"].update(effect=999.0),
    )
    rejected = ClaimValidator(store).validate(forged)
    rejected_report = ReportComposer(store).compose(rejected)
    assert rejected_report["claim"]["status"] == "rejected"
    assert "actor_damage" not in rejected_report
