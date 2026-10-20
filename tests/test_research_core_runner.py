from __future__ import annotations

import json
from pathlib import Path

import pytest

import hsr_nous.research.core.runner as runner_module
from hsr_nous.research.core.artifacts import ArtifactIntegrityError, ArtifactStore
from hsr_nous.research.core.runner import TrialRunner
from hsr_nous.research.protocol import PAIRED_V1
from hsr_nous.research.schema import canonical_bytes, content_hash
from tests._research_builders import make_demo_contract


def _deterministic_files(store):
    return {
        path.relative_to(store.root): path.read_bytes()
        for path in store.root.rglob("*")
        if path.is_file() and path.name != "metadata.json"
    }


def _assert_64_members(artifact):
    assert len(artifact.run_ids) == 64
    comparison = artifact.comparison_set
    assert len(comparison.baseline_dev) == 16
    assert len(comparison.baseline_holdout) == 16
    assert len(comparison.variant_dev) == 16
    assert len(comparison.variant_holdout) == 16
    assert artifact.run_ids == (
        *comparison.baseline_dev,
        *comparison.baseline_holdout,
        *comparison.variant_dev,
        *comparison.variant_holdout,
    )


def test_demo_tingyun_formal_64_runs_and_idempotent_replay(tmp_path, monkeypatch):
    canonical_path = Path("data/library/characters/1202_停云.yaml")
    canonical_before = canonical_path.read_bytes()
    store = ArtifactStore(tmp_path / "research" / "artifacts")
    runner = TrialRunner(store)
    real_compile = runner_module.compile_encounter
    compile_calls = []

    def counted_compile(*args, **kwargs):
        compile_calls.append(kwargs.get("template_roots"))
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(runner_module, "compile_encounter", counted_compile)
    contract = make_demo_contract()
    artifact = runner.run(contract)
    assert len(compile_calls) == 2
    assert artifact.status == "completed"
    _assert_64_members(artifact)

    records = [store.read_run(artifact.trial_id, run_id) for run_id in artifact.run_ids]
    assert all(record.status == "completed" for record in records)
    assert all(not record.observed["truncated"] for record in records)
    assert all(record.events for record in records)
    assert all(record.final_save["save_version"] == 1 for record in records)
    assert sum(len(record.modifiers) for record in records) > 0
    assert all(
        "name" in modifier["details"]
        for record in records
        for modifier in record.modifiers
    )
    by_key = {(record.arm_id, record.cohort, record.seed): record for record in records}
    assert len(by_key) == 64
    for arm_id in ("baseline", "variant"):
        for cohort, seeds in (
            ("dev", PAIRED_V1.dev_seeds),
            ("holdout", PAIRED_V1.holdout_seeds),
        ):
            for seed in seeds:
                assert (arm_id, cohort, seed) in by_key
                assert len(by_key[arm_id, cohort, seed].run_id) == 64
    for record in records:
        if record.arm_id == "variant":
            parent = by_key["baseline", record.cohort, record.seed]
            assert record.parent_run_id == parent.run_id
        else:
            assert record.parent_run_id is None

    from hsr_nous.sim.engine import CombatEngine
    from hsr_nous.sim.montecarlo import RunRecorder, _RunRecorder, classify_outcome

    assert _RunRecorder is RunRecorder
    reference_compiled = real_compile(
        contract.experiment.build,
        contract.experiment.stage,
        template_roots=runner.materializer.template_roots,
    )
    reference_engine = CombatEngine.from_compiled(reference_compiled, mode="roll", seed=0)
    reference_engine.setup()
    reference_recorder = RunRecorder(reference_engine)
    reference_engine.run()
    reference = classify_outcome(
        reference_engine,
        seed=0,
        ult_casts=reference_recorder.ult_casts,
        energy_gained=reference_recorder.energy_gained,
        ally_actions=reference_recorder.ally_actions,
    )
    observed = by_key["baseline", "dev", 0].observed
    for field in ("ult_casts", "energy_gained", "energy_gain_per_action"):
        assert observed[field] == getattr(reference, field)
        assert observed[field] > 0
    assert store.read_result(artifact.trial_id) == artifact

    before = _deterministic_files(store)
    replayed = runner.run(contract)
    assert len(compile_calls) == 4
    assert replayed == artifact
    assert _deterministic_files(store) == before
    assert canonical_path.read_bytes() == canonical_before

    result_path = store.trial_dir(artifact.trial_id) / "result.json"
    payload = json.loads(result_path.read_bytes())
    result_hash = payload.pop("result_hash")
    assert result_hash == content_hash(payload)
    payload["run_ids"].append("f" * 64)
    payload["result_hash"] = content_hash(payload)
    result_path.chmod(0o644)
    result_path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ArtifactIntegrityError):
        store.read_result(artifact.trial_id)


def test_failed_variant_runs_are_retained_and_missing_run_is_not_silent(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    runner = TrialRunner(store)
    real_compile = runner_module.compile_encounter

    def fail_variant(*args, **kwargs):
        roots = kwargs.get("template_roots") or ()
        if roots and "variants" in Path(roots[0]).parts:
            raise RuntimeError("declared variant compile failure")
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(runner_module, "compile_encounter", fail_variant)
    contract = make_demo_contract()
    artifact = runner.run(contract)
    _assert_64_members(artifact)
    assert artifact.status == "failed"
    assert len(artifact.failure_reasons) == 32

    records = [store.read_run(artifact.trial_id, run_id) for run_id in artifact.run_ids]
    baseline = [record for record in records if record.arm_id == "baseline"]
    variant = [record for record in records if record.arm_id == "variant"]
    assert len(baseline) == 32 and all(record.status == "completed" for record in baseline)
    assert len(variant) == 32 and all(record.status == "failed" for record in variant)
    assert all("compile failure" in record.observed["error"]["message"] for record in variant)

    missing = store.run_path(artifact.trial_id, variant[0].run_id)
    missing.unlink()
    with pytest.raises(FileNotFoundError):
        store.read_result(artifact.trial_id)

    replayed = runner.run(contract)
    assert replayed == artifact
    assert store.read_result(artifact.trial_id) == artifact

    result_path = store.trial_dir(artifact.trial_id) / "result.json"
    payload = json.loads(result_path.read_bytes())
    payload.pop("result_hash")
    payload["failure_reasons"][0] = "reason does not match the failed run"
    payload["result_hash"] = content_hash(payload)
    result_path.chmod(0o644)
    result_path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="failure reasons"):
        store.read_result(artifact.trial_id)
