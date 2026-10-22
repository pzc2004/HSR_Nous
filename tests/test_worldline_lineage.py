"""世界线派生（lineage）测试家族（研究后端横向族，见 tests/README.md）。

覆盖：`WorldlineSpec.derived_from` 形状闸（闭集键 / 64 位小写 hex / note 类型 /
frozen）、`derive_child_spec` 继承与覆盖语义（含 failed 父代允许派生）、黄泉队
真实世界线派生 happy path（身份必变 / 执行不变 / 父链校验绿 / 父代字节不可变钉）、
读时父链校验（父缺失孤儿、换父断链、自环与父 payload 成环）。篡改手法沿用
`test_research_worldline`：改 payload → 重算哈希 → canonical 字节写回。
共享构造件 `tests/_worldline_builders.py`，不新增 YAML fixture。
"""
from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError

import pytest

from hsr_nous.research.core.artifacts import (
    ArtifactIntegrityError,
    ArtifactStore,
    _worldline_identity,
)
from hsr_nous.research.core.fingerprint import collect_worldline_fingerprint
from hsr_nous.research.core.worldline import WorldlineRunner, derive_child_spec
from hsr_nous.research.schema import (
    WorldlineArtifact,
    WorldlineSpec,
    canonical_bytes,
    content_hash,
)
from tests._worldline_builders import make_acheron_worldline_parts

TOTAL_DAMAGE = 13835.311721259002
_PARENT_ID = "a" * 64
_PARENT_HASH = "b" * 64


def _acheron_spec(**overrides) -> WorldlineSpec:
    build, stage, values = make_acheron_worldline_parts()
    params = {
        "build": build,
        "stage": stage,
        "random_values": tuple(values),
        "initial_sp": 5,
        "initial_energy_ratio": 1.0,
    }
    params.update(overrides)
    return WorldlineSpec(**params)


def _completed_parent() -> WorldlineArtifact:
    """内存态 completed 父代（不走模拟器，纯派生语义单元测试用）。"""
    return WorldlineArtifact(
        worldline_id=_PARENT_ID,
        spec=_acheron_spec(),
        fingerprint={"config_hash": "c"},
        status="completed",
        observed={"total_damage": 1.0},
        events=(),
        final_save={"state": {"total_damage": 1.0}},
        modifiers=(),
        caveats=(),
        failure_reasons=(),
    )


def _failed_parent() -> WorldlineArtifact:
    return WorldlineArtifact(
        worldline_id=_PARENT_ID,
        spec=_acheron_spec(),
        fingerprint={"config_hash": "c"},
        status="failed",
        observed={},
        events=(),
        final_save=None,
        modifiers=(),
        caveats=(),
        failure_reasons=("RuntimeError: scripted policy 未覆盖",),
    )


def _override_window_entry(
    ultimate_script: list[dict],
) -> list[dict]:
    """改一条 window 条目：给 skip 条目补显式 target。

    target 对 skip 条目是死字段（select_ultimate 的 skip 分支直接返回 None，
    target 不参与结算），执行逐决策不变；但 policy 原文变了——子代身份必变、
    轨迹必同，正好隔离验证 lineage 的身份语义。
    """
    overridden = [dict(entry) for entry in ultimate_script]
    overridden[0] = {**overridden[0], "target": "enemy1"}
    return overridden


class TestDerivedFromContract:
    def test_defaults_to_none(self):
        assert _acheron_spec().derived_from is None

    def test_valid_minimal_accepted(self):
        spec = _acheron_spec(
            derived_from={"worldline_id": _PARENT_ID, "content_hash": _PARENT_HASH}
        )
        assert spec.derived_from["worldline_id"] == _PARENT_ID

    def test_round_trip_via_dict(self):
        spec = _acheron_spec(
            derived_from={
                "worldline_id": _PARENT_ID,
                "content_hash": _PARENT_HASH,
                "note": "窗口微调",
            }
        )
        assert WorldlineSpec.from_dict(spec.to_dict()) == spec

    def test_missing_worldline_id_rejected(self):
        with pytest.raises(ValueError, match="worldline_id"):
            _acheron_spec(derived_from={"content_hash": _PARENT_HASH})

    def test_missing_content_hash_rejected(self):
        with pytest.raises(ValueError, match="content_hash"):
            _acheron_spec(derived_from={"worldline_id": _PARENT_ID})

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError, match="64 位小写十六进制"):
            _acheron_spec(
                derived_from={"worldline_id": "z" * 64, "content_hash": _PARENT_HASH}
            )

    def test_wrong_length_rejected(self):
        with pytest.raises(ValueError, match="64 位小写十六进制"):
            _acheron_spec(
                derived_from={"worldline_id": "a" * 63, "content_hash": _PARENT_HASH}
            )

    def test_uppercase_rejected(self):
        with pytest.raises(ValueError, match="64 位小写十六进制"):
            _acheron_spec(
                derived_from={"worldline_id": "A" * 64, "content_hash": _PARENT_HASH}
            )

    def test_non_string_note_rejected(self):
        with pytest.raises(TypeError, match="note"):
            _acheron_spec(
                derived_from={
                    "worldline_id": _PARENT_ID,
                    "content_hash": _PARENT_HASH,
                    "note": 123,
                }
            )

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match="只允许"):
            _acheron_spec(
                derived_from={
                    "worldline_id": _PARENT_ID,
                    "content_hash": _PARENT_HASH,
                    "lineage": "extra",
                }
            )

    def test_non_mapping_rejected(self):
        with pytest.raises(ValueError, match="mapping"):
            _acheron_spec(derived_from="not-a-mapping")

    def test_spec_is_frozen(self):
        spec = _acheron_spec(
            derived_from={"worldline_id": _PARENT_ID, "content_hash": _PARENT_HASH}
        )
        with pytest.raises(FrozenInstanceError):
            spec.derived_from = None


class TestDeriveChildSpec:
    def test_inherits_unspecified_fields(self):
        parent = _completed_parent()
        child_spec = derive_child_spec(parent)

        assert child_spec.initial_sp == 5
        assert child_spec.initial_energy_ratio == 1.0
        assert child_spec.random_values == parent.spec.random_values
        assert child_spec.stage == parent.spec.stage
        child_policy = child_spec.build["build"]["policy"]
        parent_policy = parent.spec.build["build"]["policy"]
        assert child_policy["script"] == parent_policy["script"]
        assert child_policy["ultimate_script"] == parent_policy["ultimate_script"]
        assert child_policy["mode"] == "scripted"
        assert child_policy["ult_timing"] == "scripted"

    def test_overrides_replace_named_fields(self):
        parent = _completed_parent()
        parent_policy = parent.spec.build["build"]["policy"]
        new_script = [dict(parent_policy["script"][0], turn=7)]
        new_ult = _override_window_entry(list(parent_policy["ultimate_script"]))

        child_spec = derive_child_spec(
            parent,
            script=new_script,
            ultimate_script=new_ult,
            random_values=[0.5, 0.25],
            initial_sp=3,
            initial_energy_ratio=0.0,
        )

        child_policy = child_spec.build["build"]["policy"]
        assert list(child_policy["script"]) == new_script
        assert list(child_policy["ultimate_script"]) == new_ult
        assert child_spec.random_values == (0.5, 0.25)
        assert child_spec.initial_sp == 3
        assert child_spec.initial_energy_ratio == 0.0
        # 覆盖不得回写父代（frozen + plain 拷贝双保险）
        assert parent.spec.initial_sp == 5
        assert list(parent_policy["script"]) != new_script

    def test_derived_from_binds_parent_identity_and_storage_hash(self):
        parent = _completed_parent()
        child_spec = derive_child_spec(parent, note="试跑")

        assert child_spec.derived_from is not None
        assert child_spec.derived_from["worldline_id"] == parent.worldline_id
        # 与 publish_worldline 的存储哈希同公式：content_hash(artifact.to_dict())
        assert child_spec.derived_from["content_hash"] == content_hash(parent.to_dict())
        assert child_spec.derived_from["note"] == "试跑"

    def test_note_omitted_when_none(self):
        parent = _completed_parent()
        assert derive_child_spec(parent).derived_from == {
            "worldline_id": parent.worldline_id,
            "content_hash": content_hash(parent.to_dict()),
        }

    def test_derive_from_failed_parent_allowed(self):
        parent = _failed_parent()
        child_spec = derive_child_spec(parent, note="修脚本错误再跑")
        assert child_spec.derived_from["worldline_id"] == parent.worldline_id
        assert child_spec.random_values == parent.spec.random_values


def test_derived_child_runs_and_chain_verifies(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    runner = WorldlineRunner(store=store)
    parent = runner.run(_acheron_spec())
    parent_worldline_bytes = store.worldline_path(parent.worldline_id).read_bytes()
    parent_spec_bytes = store.worldline_spec_path(parent.worldline_id).read_bytes()

    parent_ult = list(parent.spec.build["build"]["policy"]["ultimate_script"])
    note = "skip 条目补显式 target（死字段）——身份必变、轨迹不变"
    child_spec = derive_child_spec(
        parent, ultimate_script=_override_window_entry(parent_ult), note=note
    )

    # 继承未覆盖字段、覆盖生效（内存断言见 TestDeriveChildSpec，这里盯链上行为）
    assert child_spec.initial_sp == 5
    child_ult = child_spec.build["build"]["policy"]["ultimate_script"]
    assert child_ult[0] == {**dict(parent_ult[0]), "target": "enemy1"}
    assert list(child_ult[1:]) == [dict(e) for e in parent_ult[1:]]

    child = runner.run(child_spec)
    assert child.worldline_id != parent.worldline_id
    assert child.status == "completed"
    assert child.observed["turn_count"] == 16
    assert child.observed["random_consumed"] == 92
    # 死字段覆盖：执行与父代逐值一致
    assert math.isclose(child.observed["total_damage"], TOTAL_DAMAGE, rel_tol=1e-9)
    assert math.isclose(
        child.observed["total_damage"], parent.observed["total_damage"], rel_tol=1e-9
    )
    # 父链校验绿 + 父代重读仍绿
    assert store.read_worldline(child.worldline_id) == child
    assert store.read_worldline(parent.worldline_id) == parent
    # 不可变钉：子代发布不得触碰父代文件字节
    assert store.worldline_path(parent.worldline_id).read_bytes() == parent_worldline_bytes
    assert store.worldline_spec_path(parent.worldline_id).read_bytes() == parent_spec_bytes


def test_read_rejects_orphan_child_after_parent_deleted(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    runner = WorldlineRunner(store=store)
    parent = runner.run(_acheron_spec())
    child = runner.run(derive_child_spec(parent, note="派生"))

    store.worldline_path(parent.worldline_id).unlink()
    with pytest.raises(ArtifactIntegrityError, match="孤儿派生"):
        store.read_worldline(child.worldline_id)


def test_read_rejects_replaced_parent_hash(tmp_path):
    """换父断链：derived_from.content_hash 记录与父代实际内容不符。

    发布宽松（artifact 落盘），读取严格（run 末尾的 read_worldline 拦截）。
    """
    store = ArtifactStore(tmp_path / "artifacts")
    runner = WorldlineRunner(store=store)
    parent = runner.run(_acheron_spec())

    child_spec = derive_child_spec(parent)
    lying_spec = WorldlineSpec.from_dict(
        {
            **child_spec.to_dict(),
            "derived_from": {**child_spec.derived_from, "content_hash": "f" * 64},
        }
    )
    with pytest.raises(ArtifactIntegrityError, match="换父"):
        runner.run(lying_spec)
    lying_id = _worldline_identity(
        lying_spec, collect_worldline_fingerprint(lying_spec)
    )
    assert store.worldline_path(lying_id).exists()
    with pytest.raises(ArtifactIntegrityError, match="换父"):
        store.read_worldline(lying_id)


def test_read_rejects_self_parent_entry(tmp_path):
    """自环：子代 derived_from.worldline_id 改指自己。

    derived_from 入身份哈希——含自环的 spec 重算身份必然偏离已发布
    worldline_id，在 read_worldline_spec 的身份重算处即拒（walk 的
    visited 防环对入口 artifact 是纵深防御，见下测）。
    """
    store = ArtifactStore(tmp_path / "artifacts")
    runner = WorldlineRunner(store=store)
    child = runner.run(derive_child_spec(runner.run(_acheron_spec()), note="x"))

    spec_path = store.worldline_spec_path(child.worldline_id)
    spec_payload = json.loads(spec_path.read_bytes())
    spec_payload["spec"]["derived_from"]["worldline_id"] = child.worldline_id
    spec_payload["spec_hash"] = content_hash(
        {key: value for key, value in spec_payload.items() if key != "spec_hash"}
    )
    spec_path.chmod(0o644)
    spec_path.write_bytes(canonical_bytes(spec_payload))

    worldline_path = store.worldline_path(child.worldline_id)
    worldline_payload = json.loads(worldline_path.read_bytes())
    worldline_payload["spec"]["derived_from"]["worldline_id"] = child.worldline_id
    worldline_payload["content_hash"] = content_hash(
        {key: value for key, value in worldline_payload.items() if key != "content_hash"}
    )
    worldline_path.chmod(0o644)
    worldline_path.write_bytes(canonical_bytes(worldline_payload))

    with pytest.raises(ArtifactIntegrityError, match="worldline_id"):
        store.read_worldline(child.worldline_id)


def test_walk_rejects_cycle_in_parent_payload(tmp_path):
    """父 payload 自环：walk 上溯时 visited 真正拦截的一环。

    内容寻址 + 身份绑定使"身份合法的互环"在密码学上不可构造（环上任意节点
    的 id 固定其内容，闭环即成哈希不动点）；visited 防环拦的是手工 craft 的
    父 payload——父只被轻量读取（不重建身份），其 spec 里自指的 derived_from
    在第二跳即命中 visited。这里手工把真实父代的 derived_from 改指自己
    （两份文件重算哈希写盘），再派生一个链环对账合法的子代。
    """
    store = ArtifactStore(tmp_path / "artifacts")
    runner = WorldlineRunner(store=store)
    parent = runner.run(_acheron_spec())

    worldline_path = store.worldline_path(parent.worldline_id)
    worldline_payload = json.loads(worldline_path.read_bytes())
    worldline_payload["spec"]["derived_from"] = {
        "worldline_id": parent.worldline_id,
        "content_hash": "0" * 64,
    }
    worldline_payload["content_hash"] = content_hash(
        {key: value for key, value in worldline_payload.items() if key != "content_hash"}
    )
    worldline_path.chmod(0o644)
    worldline_path.write_bytes(canonical_bytes(worldline_payload))

    spec_path = store.worldline_spec_path(parent.worldline_id)
    spec_payload = json.loads(spec_path.read_bytes())
    spec_payload["spec"]["derived_from"] = {
        "worldline_id": parent.worldline_id,
        "content_hash": "0" * 64,
    }
    spec_payload["spec_hash"] = content_hash(
        {key: value for key, value in spec_payload.items() if key != "spec_hash"}
    )
    spec_path.chmod(0o644)
    spec_path.write_bytes(canonical_bytes(spec_payload))

    # 子代的链环记录与改后的父 payload 一致——第一跳对账通过，第二跳成环
    loop_spec = _acheron_spec(
        derived_from={
            "worldline_id": parent.worldline_id,
            "content_hash": worldline_payload["content_hash"],
        }
    )
    with pytest.raises(ArtifactIntegrityError, match="成环"):
        runner.run(loop_spec)
    loop_id = _worldline_identity(loop_spec, collect_worldline_fingerprint(loop_spec))
    assert store.worldline_path(loop_id).exists()
    with pytest.raises(ArtifactIntegrityError, match="成环"):
        store.read_worldline(loop_id)


def test_derive_from_failed_parent_fixes_script(tmp_path):
    build, stage, values = make_acheron_worldline_parts()
    build["build"]["policy"]["script"][0]["turn"] = 999
    store = ArtifactStore(tmp_path / "artifacts")
    runner = WorldlineRunner(store=store)
    parent = runner.run(
        WorldlineSpec(
            build, stage, tuple(values), initial_sp=5, initial_energy_ratio=1.0
        )
    )
    assert parent.status == "failed"

    fixed_script = [dict(entry) for entry in
                    parent.spec.build["build"]["policy"]["script"]]
    fixed_script[0]["turn"] = 3
    child_spec = derive_child_spec(parent, script=fixed_script, note="修复 script 窗口后重跑")
    child = runner.run(child_spec)

    assert child.status == "completed"
    assert child.worldline_id != parent.worldline_id
    assert child.spec.derived_from["worldline_id"] == parent.worldline_id
    assert math.isclose(child.observed["total_damage"], TOTAL_DAMAGE, rel_tol=1e-9)
    assert store.read_worldline(child.worldline_id) == child
