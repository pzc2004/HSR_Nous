from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from hsr_nous.research_core.artifacts import (
    ArtifactConflictError,
    ArtifactIntegrityError,
    ArtifactPathError,
    ArtifactStore,
    make_event_id,
    make_modifier_id,
    make_run_id,
    make_trial_id,
)
from hsr_nous.research_core.fingerprint import (
    collect_research_fingerprint,
    implementation_hash,
)
from hsr_nous.research_core.variants import VariantMaterializer
from hsr_nous.research_protocol import resolve_protocol
from hsr_nous.research_schema import RunRecord, canonical_bytes, content_hash
from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from tests._research_builders import make_demo_contract, make_fingerprint


def _with_patch_value(contract, value):
    experiment = contract.experiment
    patch = replace(experiment.variant.patches[0], value=value)
    variant = replace(experiment.variant, patches=(patch,))
    return replace(contract, experiment=replace(experiment, variant=variant))


def _set_atk(document, value):
    document["base_stats"]["atk"] = value


def test_variant_uses_compiler_loader_and_preserves_canonical(tmp_path):
    contract = make_demo_contract()
    canonical_path = Path("data/library/characters/1202_停云.yaml")
    canonical_bytes_before = canonical_path.read_bytes()
    materializer = VariantMaterializer()
    prepared = materializer.prepare(contract, hypothesis="Raise declared ATK")
    again = materializer.prepare(contract, hypothesis="Raise declared ATK")
    changed = materializer.prepare(
        _with_patch_value(contract, 601.0), hypothesis="Raise declared ATK"
    )

    assert prepared.variant_id == again.variant_id
    assert prepared.variant_id != changed.variant_id
    assert len(prepared.variant_id) == 64
    document = prepared.documents[0]
    assert document["canonical"]["base_stats"]["atk"] == 529.2
    assert document["content"]["base_stats"]["atk"] == 600.0
    restored = json.loads(json.dumps(document["content"]))
    _set_atk(restored, 529.2)
    assert restored == document["canonical"]

    store = ArtifactStore(tmp_path / "artifacts")
    variant_root = store.publish_variant("0" * 64, prepared)
    written = yaml.safe_load(
        (variant_root / "characters" / "1202_variant.yaml").read_text(encoding="utf-8")
    )
    assert written["base_stats"]["atk"] == 600.0
    assert canonical_path.read_bytes() == canonical_bytes_before

    roots = materializer.template_roots
    assert BuildCompiler._load_template("characters", "1202", roots=roots) == \
        BuildCompiler.load_template("characters", "1202", roots=roots)
    baseline = compile_encounter(
        contract.experiment.build, contract.experiment.stage, template_roots=roots
    )
    variant = compile_encounter(
        contract.experiment.build,
        contract.experiment.stage,
        template_roots=(variant_root, *roots),
    )
    assert baseline.build_team[0].stats.atk == 529.2
    assert variant.build_team[0].stats.atk == 600.0
    assert canonical_path.read_bytes() == canonical_bytes_before


def test_fingerprint_binds_config_variant_and_implementation(monkeypatch, tmp_path):
    import hsr_nous.research_core.fingerprint as fingerprint_module

    base = {
        "git_commit": "information-only",
        "rulebook_hash": "rulebook",
        "fixtures_hash": "fixtures",
        "data_hash": "data",
        "policy_hash": "policy",
    }
    monkeypatch.setattr(
        fingerprint_module, "collect_version_fingerprint", lambda policy_source: dict(base)
    )
    contract = make_demo_contract()
    materializer = VariantMaterializer()
    prepared = materializer.prepare(contract, hypothesis="Raise declared ATK")
    resolved = prepared.resolved_protocol
    fingerprint = collect_research_fingerprint(contract, resolved, prepared)
    assert fingerprint.config_hash and fingerprint.implementation_hash
    assert fingerprint.variant_hash == prepared.variant_hash
    assert fingerprint.protocol_id == "paired-v1"
    assert fingerprint.artifact_schema_version == "1"

    changed_build = dict(contract.experiment.build)
    changed_build["build"] = dict(changed_build["build"])
    changed_build["build"]["metadata"] = {"case": "different"}
    changed_contract = replace(
        contract, experiment=replace(contract.experiment, build=changed_build)
    )
    changed_fingerprint = collect_research_fingerprint(changed_contract, resolved, prepared)
    assert changed_fingerprint.config_hash != fingerprint.config_hash
    changed_variant = materializer.prepare(
        _with_patch_value(contract, 601.0), hypothesis="Raise declared ATK"
    )
    assert collect_research_fingerprint(
        contract, resolved, changed_variant
    ).variant_hash != fingerprint.variant_hash

    same_content_different_git = replace(fingerprint, git_commit="different-text")
    assert make_trial_id(contract, resolved, same_content_different_git) == make_trial_id(
        contract, resolved, fingerprint
    )

    root = tmp_path / "source-tree"
    for package in ("sim", "sim_schema", "research_schema", "research_protocol", "research_core"):
        directory = root / "src" / "hsr_nous" / package
        directory.mkdir(parents=True)
        (directory / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    first = implementation_hash(root)
    (root / "src" / "hsr_nous" / "research_core" / "module.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )
    assert implementation_hash(root) != first
    second = implementation_hash(root)
    (root / "uv.lock").write_text("version = 2\n", encoding="utf-8")
    assert implementation_hash(root) != second


def _run_record(trial_id, *, arm_id="baseline", cohort="dev", seed=0):
    run_id = make_run_id(trial_id, arm_id, cohort, seed)
    event_payload = {"event_type": "battle_start", "data": {}}
    event = {
        "event_id": make_event_id(run_id, 0, event_payload),
        "ordinal": 0,
        "payload": event_payload,
    }
    modifier = {
        "modifier_id": make_modifier_id(run_id, "1202", "TRACE"),
        "actor_id": "1202",
        "engine_modifier_id": "TRACE",
        "details": {"modifier_id": "TRACE", "name": "行迹", "duration": 0},
    }
    return RunRecord(
        run_id=run_id,
        trial_id=trial_id,
        arm_id=arm_id,
        cohort=cohort,
        seed=seed,
        status="completed",
        observed={"seed": seed, "total_damage": 100.0, "truncated": False},
        events=(event,),
        final_save={
            "save_version": 1,
            "state": {"total_damage": 100.0, "truncated": False, "actors": {}},
        },
        modifiers=(modifier,),
        content_hash="",
    )


def _published_spec(store):
    contract = make_demo_contract()
    resolved = resolve_protocol(contract.protocol_id)
    fingerprint = make_fingerprint()
    trial_id = store.publish_spec(contract, resolved, fingerprint)
    return contract, resolved, fingerprint, trial_id


def test_store_publish_is_canonical_idempotent_read_only_and_conflicting(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    _, _, _, trial_id = _published_spec(store)
    record = _run_record(trial_id)
    published = store.publish_run(record)
    path = store.run_path(trial_id, record.run_id)
    initial = path.read_bytes()
    assert initial == canonical_bytes(published)
    assert store.publish_run(record).content_hash == published.content_hash
    assert path.read_bytes() == initial
    assert store.read_run(trial_id, record.run_id) == published
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o444

    conflict = replace(
        record,
        observed={"seed": 0, "total_damage": 999.0, "truncated": False},
        final_save={
            "save_version": 1,
            "state": {"total_damage": 999.0, "truncated": False, "actors": {}},
        },
    )
    with pytest.raises(ArtifactConflictError):
        store.publish_run(conflict)
    assert path.read_bytes() == initial

    payload = json.loads(initial)
    payload["observed"]["total_damage"] = 999.0
    path.chmod(0o644)
    path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ArtifactIntegrityError):
        store.read_run(trial_id, record.run_id)


def test_store_atomic_replace_path_escape_and_metadata(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    _, _, _, trial_id = _published_spec(store)
    record = _run_record(trial_id)
    import hsr_nous.research_core.artifacts as artifacts_module

    real_replace = artifacts_module.os.replace
    calls = []
    monkeypatch.setattr(
        artifacts_module.os,
        "replace",
        lambda src, dst: (calls.append((src, dst)), real_replace(src, dst)),
    )
    store.publish_run(record)
    assert calls
    assert not list(store.root.rglob("*.tmp"))

    with pytest.raises(ArtifactPathError):
        store.run_path("../" + "0" * 64, "0" * 64)
    with pytest.raises(ArtifactPathError):
        store.run_path(trial_id, "../" + "0" * 64)

    symlink_trial = "a" * 64
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.root / "trials" / symlink_trial).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactPathError):
        store.run_path(symlink_trial, "b" * 64)

    spec_before = (store.trial_dir(trial_id) / "spec.json").read_bytes()
    store.write_metadata(trial_id, {"started_at": "2026-01-01T00:00:00+00:00"})
    store.write_metadata(trial_id, {"started_at": "2026-01-02T00:00:00+00:00"})
    assert store.read_metadata(trial_id)["started_at"].startswith("2026-01-02")
    assert (store.trial_dir(trial_id) / "spec.json").read_bytes() == spec_before


def test_store_rejects_noncanonical_read(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    _, _, _, trial_id = _published_spec(store)
    record = _run_record(trial_id)
    store.publish_run(record)
    path = store.run_path(trial_id, record.run_id)
    original = path.read_bytes()
    path.chmod(0o644)
    path.write_text(json.dumps(json.loads(original), indent=2), encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError):
        store.read_run(trial_id, record.run_id)


def test_variant_rejects_unsafe_patch_reference_before_any_loader(monkeypatch):
    from hsr_nous.research_protocol import ProtocolValidationError

    def forbidden_loader(*args, **kwargs):
        raise AssertionError("BuildCompiler loader must not be called")

    monkeypatch.setattr(BuildCompiler, "load_template", staticmethod(forbidden_loader))
    materializer = VariantMaterializer()
    for field, value, message in (
        ("template_id", "../1202", "template_id"),
        ("template_id", "*", "template_id"),
        ("template_kind", "../characters", "template_kind"),
    ):
        contract = make_demo_contract()
        experiment = contract.experiment
        patch = replace(experiment.variant.patches[0], **{field: value})
        contract = replace(
            contract,
            experiment=replace(
                experiment,
                variant=replace(experiment.variant, patches=(patch,)),
            ),
        )
        with pytest.raises(ProtocolValidationError, match=message):
            materializer.prepare(contract, hypothesis="unsafe reference")


def test_read_variant_verifies_yaml_content(tmp_path):
    contract = make_demo_contract()
    prepared = VariantMaterializer().prepare(contract, hypothesis="Raise declared ATK")
    store = ArtifactStore(tmp_path / "artifacts")
    published_root = store.publish_variant("0" * 64, prepared)
    root, metadata = store.read_variant("0" * 64, prepared.variant_id)
    assert root == published_root
    assert metadata["variant_id"] == prepared.variant_id
    assert metadata["documents"][0]["content_hash"] == prepared.documents[0]["content_hash"]

    yaml_path = root / "characters" / "1202_variant.yaml"
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    document["base_stats"]["atk"] = 601.0
    yaml_path.chmod(0o644)
    yaml_path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match="content hash"):
        store.read_variant("0" * 64, prepared.variant_id)


def test_read_variant_verifies_metadata_identity_and_document_paths(tmp_path):
    contract = make_demo_contract()
    prepared = VariantMaterializer().prepare(contract, hypothesis="Raise declared ATK")
    store = ArtifactStore(tmp_path / "artifacts")
    root = store.publish_variant("0" * 64, prepared)
    metadata_path = root / "variant.json"
    original = json.loads(metadata_path.read_bytes())
    metadata_path.chmod(0o644)

    payload = json.loads(json.dumps(original))
    payload["hypothesis"] = "tampered hypothesis"
    payload["metadata_hash"] = content_hash({
        key: value for key, value in payload.items() if key != "metadata_hash"
    })
    metadata_path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="variant_id"):
        store.read_variant("0" * 64, prepared.variant_id)

    payload = json.loads(json.dumps(original))
    payload["documents"][0]["path"] = "../outside.yaml"
    payload["metadata_hash"] = content_hash({
        key: value for key, value in payload.items() if key != "metadata_hash"
    })
    metadata_path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="path"):
        store.read_variant("0" * 64, prepared.variant_id)


@pytest.mark.parametrize(
    ("observed_changes", "state_changes", "message"),
    [
        ({"total_damage": 101.0}, {}, "total_damage"),
        ({"seed": 1}, {}, "seed"),
        ({"truncated": True}, {}, "truncated"),
        ({}, {"total_damage": 101.0}, "total_damage"),
    ],
)
def test_run_observed_final_save_mismatch_is_rejected_on_publish(
    tmp_path, observed_changes, state_changes, message
):
    store = ArtifactStore(tmp_path / "artifacts")
    record = _run_record("0" * 64)
    observed = {**record.observed, **observed_changes}
    state = {**record.final_save["state"], **state_changes}
    invalid = replace(
        record,
        observed=observed,
        final_save={**record.final_save, "state": state},
    )
    with pytest.raises(ArtifactIntegrityError, match=message):
        store.publish_run(invalid)


def test_run_observed_final_save_mismatch_is_rejected_on_read(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    record = _run_record("0" * 64)
    store.publish_run(record)
    path = store.run_path("0" * 64, record.run_id)
    payload = json.loads(path.read_bytes())
    payload["observed"]["total_damage"] = 999.0
    payload["content_hash"] = content_hash({
        key: value for key, value in payload.items() if key != "content_hash"
    })
    path.chmod(0o644)
    path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="total_damage"):
        store.read_run("0" * 64, record.run_id)


def test_report_publish_and_read_enforce_trial_ownership(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    _, _, _, trial_id = _published_spec(store)
    report = {"spec": {"trial_id": trial_id}, "claim": {"status": "accepted"}}
    report_id = store.publish_report(trial_id, report)
    assert store.read_report(trial_id, report_id)["report_id"] == report_id

    other_trial = "1" * 64
    with pytest.raises(ArtifactIntegrityError, match="trial"):
        store.publish_report(other_trial, report)
    misplaced = store.report_path(other_trial, report_id)
    misplaced.parent.mkdir(parents=True, exist_ok=True)
    misplaced.write_bytes(canonical_bytes({**report, "report_id": report_id}))
    with pytest.raises(ArtifactIntegrityError, match="trial"):
        store.read_report(other_trial, report_id)


def test_event_and_modifier_evidence_links_require_run_id(tmp_path):
    from hsr_nous.research_schema import EvidenceLink

    store = ArtifactStore(tmp_path / "artifacts")
    for field in ("event_id", "modifier_id"):
        link = EvidenceLink(
            trial_id="0" * 64,
            artifact_hash="2" * 64,
            **{field: "1" * 64},
        )
        with pytest.raises(ArtifactIntegrityError, match="run_id"):
            store.resolve_evidence(link)
