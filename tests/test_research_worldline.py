"""worldline-v1 单世界线证据链测试（家族：研究后端横向族，见 tests/README.md）。

覆盖：WorldlineSpec/WorldlineArtifact 契约闸（随机序列越界/非 scripted 拒/frozen/
status 与 schema_version 词表）、黄泉队全决策世界线验收（outcome/turn_count/随机
审计/total_damage 金样）、幂等重跑字节不变、失败世界线同样发布且可读、读时篡改
拒绝（observed 改值重哈希/spec 改随机序列/pretty-print/events 调换顺序）、身份
公式（随机序列入身份、git_commit 不入身份）。共享构造件
tests/_worldline_builders.py（真实黄泉队 scripted 世界线），不新增 YAML fixture。
"""
from __future__ import annotations

import json
import math
import os
import stat
from dataclasses import FrozenInstanceError

import pytest

from hsr_nous.research.core.artifacts import (
    ArtifactIntegrityError,
    ArtifactStore,
    _worldline_identity,
)
from hsr_nous.research.core.worldline import WorldlineRunner, verify_worldline
from hsr_nous.research.schema import (
    WorldlineArtifact,
    WorldlineSpec,
    canonical_bytes,
    content_hash,
)
from tests._worldline_builders import make_acheron_worldline_parts

TOTAL_DAMAGE = 13835.311721259002


def _acheron_spec(values=None) -> WorldlineSpec:
    build, stage, default_values = make_acheron_worldline_parts()
    return WorldlineSpec(
        build,
        stage,
        tuple(default_values if values is None else values),
        initial_sp=5,
        initial_energy_ratio=1.0,
    )


def _completed_artifact(**overrides) -> WorldlineArtifact:
    base = {
        "worldline_id": "0" * 64,
        "spec": _acheron_spec(),
        "fingerprint": {"config_hash": "c"},
        "status": "completed",
        "observed": {"total_damage": 1.0},
        "events": (),
        "final_save": {"state": {"total_damage": 1.0}},
        "modifiers": (),
        "caveats": (),
        "failure_reasons": (),
    }
    base.update(overrides)
    return WorldlineArtifact(**base)


class TestWorldlineSpecContract:
    @pytest.mark.parametrize(
        ("bad", "exc"),
        [
            (1.0, ValueError),
            (-0.001, ValueError),
            (math.nan, ValueError),
            (math.inf, ValueError),
            ("0.5", TypeError),
            (True, TypeError),
        ],
    )
    def test_random_values_out_of_range_rejected(self, bad, exc):
        build, stage, values = make_acheron_worldline_parts()
        with pytest.raises(exc):
            WorldlineSpec(build, stage, tuple(values[:-1]) + (bad,))

    def test_build_requires_build_key(self):
        _, stage, _ = make_acheron_worldline_parts()
        with pytest.raises(ValueError, match="build"):
            WorldlineSpec({"team": {}}, stage, (0.5,))

    def test_policy_mode_must_be_scripted(self):
        build, stage, values = make_acheron_worldline_parts()
        build["build"]["policy"]["mode"] = "rules"
        with pytest.raises(ValueError, match="scripted"):
            WorldlineSpec(build, stage, tuple(values))

    def test_from_dict_rejects_unknown_fields(self):
        spec = _acheron_spec()
        with pytest.raises(ValueError, match="unknown"):
            WorldlineSpec.from_dict({**spec.to_dict(), "extra": 1})

    def test_spec_is_frozen(self):
        spec = _acheron_spec()
        with pytest.raises(FrozenInstanceError):
            spec.initial_sp = 3

    def test_random_values_normalized_to_float(self):
        build, stage, _ = make_acheron_worldline_parts()
        spec = WorldlineSpec(build, stage, (0, 0.5))
        assert spec.random_values == (0.0, 0.5)
        assert all(isinstance(v, float) for v in spec.random_values)


class TestWorldlineArtifactContract:
    def test_status_vocabulary(self):
        with pytest.raises(ValueError, match="status"):
            _completed_artifact(status="weird")

    def test_schema_version_pinned(self):
        with pytest.raises(ValueError, match="schema_version"):
            _completed_artifact(schema_version="worldline-v2")

    def test_completed_requires_final_save_without_failure_reasons(self):
        with pytest.raises(ValueError, match="final_save"):
            _completed_artifact(final_save=None)
        with pytest.raises(ValueError, match="failure_reasons"):
            _completed_artifact(failure_reasons=("RuntimeError: x",))

    def test_failed_rejects_final_save_and_requires_reasons(self):
        with pytest.raises(ValueError, match="final_save"):
            _completed_artifact(status="failed", failure_reasons=("x",))
        with pytest.raises(ValueError, match="failure_reasons"):
            _completed_artifact(status="failed", final_save=None)


def test_acheron_worldline_end_to_end(tmp_path):
    spec = _acheron_spec()
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = WorldlineRunner(store=store).run(spec)

    assert artifact.status == "completed"
    observed = artifact.observed
    assert observed["outcome"] == "timeout"
    assert observed["turn_count"] == 16
    assert observed["random_consumed"] == 92
    assert observed["random_total"] == 92
    assert math.isclose(observed["total_damage"], TOTAL_DAMAGE, rel_tol=1e-9)

    ordinals = [event["ordinal"] for event in artifact.events]
    assert artifact.events and ordinals == list(range(len(ordinals)))
    assert artifact.modifiers
    assert artifact.final_save is not None and "state" in artifact.final_save
    assert artifact.caveats
    assert artifact.schema_version == "worldline-v1"

    spec_path = store.worldline_spec_path(artifact.worldline_id)
    worldline_path = store.worldline_path(artifact.worldline_id)
    assert spec_path.exists() and worldline_path.exists()
    if os.name == "posix":
        assert stat.S_IMODE(spec_path.stat().st_mode) == 0o444
        assert stat.S_IMODE(worldline_path.stat().st_mode) == 0o444

    reread = store.read_worldline(artifact.worldline_id)
    assert reread == artifact
    assert verify_worldline(store, artifact.worldline_id) == artifact


def test_rerun_skip_existing_is_byte_identical(tmp_path):
    spec = _acheron_spec()
    store = ArtifactStore(tmp_path / "artifacts")
    runner = WorldlineRunner(store=store)
    first = runner.run(spec)
    spec_path = store.worldline_spec_path(first.worldline_id)
    worldline_path = store.worldline_path(first.worldline_id)
    spec_bytes = spec_path.read_bytes()
    worldline_bytes = worldline_path.read_bytes()

    second = runner.run(spec, skip_existing=True)
    assert second == first
    assert spec_path.read_bytes() == spec_bytes
    assert worldline_path.read_bytes() == worldline_bytes


def test_failed_worldline_is_retained_and_readable(tmp_path):
    build, stage, values = make_acheron_worldline_parts()
    build["build"]["policy"]["script"][0]["turn"] = 999
    spec = WorldlineSpec(
        build, stage, tuple(values), initial_sp=5, initial_energy_ratio=1.0
    )
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = WorldlineRunner(store=store).run(spec)

    assert artifact.status == "failed"
    assert len(artifact.failure_reasons) == 1
    assert artifact.failure_reasons[0].startswith("RuntimeError")
    assert artifact.final_save is None
    assert artifact.observed == {}
    assert artifact.events == () and artifact.modifiers == ()
    assert store.worldline_path(artifact.worldline_id).exists()
    assert store.read_worldline(artifact.worldline_id) == artifact


def test_read_rejects_tampered_observed_total_damage(tmp_path):
    spec = _acheron_spec()
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = WorldlineRunner(store=store).run(spec)
    path = store.worldline_path(artifact.worldline_id)
    payload = json.loads(path.read_bytes())
    payload["observed"]["total_damage"] = 999.0
    payload["content_hash"] = content_hash({
        key: value for key, value in payload.items() if key != "content_hash"
    })
    path.chmod(0o644)
    path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="total_damage"):
        store.read_worldline(artifact.worldline_id)


def test_read_rejects_tampered_spec_random_values(tmp_path):
    spec = _acheron_spec()
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = WorldlineRunner(store=store).run(spec)
    spec_path = store.worldline_spec_path(artifact.worldline_id)
    payload = json.loads(spec_path.read_bytes())
    payload["spec"]["random_values"][0] = 0.5
    spec_path.chmod(0o644)
    spec_path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ArtifactIntegrityError):
        store.read_worldline(artifact.worldline_id)


def test_read_rejects_pretty_printed_worldline(tmp_path):
    spec = _acheron_spec()
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = WorldlineRunner(store=store).run(spec)
    path = store.worldline_path(artifact.worldline_id)
    path.chmod(0o644)
    path.write_text(json.dumps(json.loads(path.read_bytes()), indent=2), encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError):
        store.read_worldline(artifact.worldline_id)


def test_read_rejects_swapped_events(tmp_path):
    spec = _acheron_spec()
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = WorldlineRunner(store=store).run(spec)
    path = store.worldline_path(artifact.worldline_id)
    payload = json.loads(path.read_bytes())
    payload["events"][0], payload["events"][1] = payload["events"][1], payload["events"][0]
    payload["content_hash"] = content_hash({
        key: value for key, value in payload.items() if key != "content_hash"
    })
    path.chmod(0o644)
    path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ArtifactIntegrityError, match="ordinal"):
        store.read_worldline(artifact.worldline_id)


def test_worldline_id_binds_random_sequence(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    runner = WorldlineRunner(store=store)
    first = runner.run(_acheron_spec())
    second = runner.run(_acheron_spec(values=[0.98] * 92))
    assert first.worldline_id != second.worldline_id


def test_worldline_identity_ignores_git_commit():
    spec = _acheron_spec()
    fingerprint_a = {"git_commit": "a" * 40, "config_hash": "c"}
    fingerprint_b = {"git_commit": "b" * 40, "config_hash": "c"}
    assert _worldline_identity(spec, fingerprint_a) == _worldline_identity(
        spec, fingerprint_b
    )
    changed = {"git_commit": "a" * 40, "config_hash": "different"}
    assert _worldline_identity(spec, changed) != _worldline_identity(
        spec, fingerprint_a
    )
