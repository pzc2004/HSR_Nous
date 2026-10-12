"""编译产物顶层结构不可变钉（CompiledEncounter 族）.

契约（src/hsr_nous/sim/compile/compiled.py 模块 docstring）：frozen dataclass 只冻结
字段再赋值不够——顶层 dict 字段构造后包装为 MappingProxyType、list 字段收敛为 tuple，
顶层容器写入直接 TypeError/AttributeError；嵌套容器与实例本体不冻（纪律边界）。
deepcopy 链（debug checkpoint 的 copy.deepcopy(engine) 经共享 SummonDef/CompiledPolicy
实例到达 compiled 族）经各类 __deepcopy__ 解代理深拷后重挂代理，副本同守冻结。
"""
from __future__ import annotations

import copy
from types import MappingProxyType

import pytest

from hsr_nous.sim.compile.compiled import (
    CompiledEncounter, CompiledPolicy, CompiledStage, SummonDef,
)
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim_schema.actor import Actor, StatBlock


def _summon_def() -> SummonDef:
    return SummonDef(
        owner_id="hero",
        actor=Actor(actor_id="s1", name="测试假人", actor_type="summon", level=80,
                    stats=StatBlock(hp=1000.0, atk=100.0), summoner_id="hero"),
        resource_decls={"charge": {"max": 3}},
    )


def _compiled() -> CompiledEncounter:
    return CompiledEncounter(
        build_team=(),
        actions_by_actor={"hero": []},
        stage=CompiledStage(stage_id="s", enemies=(), waves={2: ()},
                            enemy_actions={"e1": []}),
        policy=CompiledPolicy(name="p", action_rules=(), target_rules=(),
                              parameters={"focus": "e1"}),
        modifiers_by_actor={"hero": []},
        state_configs_by_actor={},
        hooks=[object()],
        resource_decls_by_actor={"hero": {"charge": {"max": 3}}},
        summon_defs={"s1": _summon_def()},
        binding_params_by_actor={"hero": {"p": 1.0}},
        trigger_order={"on_x": ("hero",)},
        caveats=[{"text": "t", "level": "approx"}],
    )


# ---------------------------------------------------------------------------
# 顶层容器写入即炸（dict 字段 → MappingProxyType，list 字段 → tuple）
# ---------------------------------------------------------------------------

def test_actions_by_actor_write_raises():
    with pytest.raises(TypeError):
        _compiled().actions_by_actor["x"] = []


def test_hooks_append_raises():
    with pytest.raises(AttributeError):
        _compiled().hooks.append(object())


def test_stage_waves_write_raises():
    with pytest.raises(TypeError):
        _compiled().stage.waves[3] = ()


def test_caveats_append_raises():
    with pytest.raises(AttributeError):
        _compiled().caveats.append({})


def test_policy_parameters_write_raises():
    with pytest.raises(TypeError):
        _compiled().policy.parameters["y"] = 2


def test_summon_def_resource_decls_write_raises():
    with pytest.raises(TypeError):
        _summon_def().resource_decls["r2"] = {}


def test_remaining_dict_fields_are_readonly_views():
    c = _compiled()
    for view in (c.modifiers_by_actor, c.state_configs_by_actor,
                 c.resource_decls_by_actor, c.summon_defs,
                 c.binding_params_by_actor, c.trigger_order,
                 c.stage.enemy_actions):
        assert isinstance(view, MappingProxyType)
        with pytest.raises(TypeError):
            view["x"] = []


def test_list_fields_are_tuples():
    c = _compiled()
    assert isinstance(c.hooks, tuple) and len(c.hooks) == 1
    assert isinstance(c.caveats, tuple) and len(c.caveats) == 1


# ---------------------------------------------------------------------------
# 读兼容（Mapping/tuple 消费面不回归）+ 构造方手中原 dict 断活引用
# ---------------------------------------------------------------------------

def test_read_patterns_still_work():
    c = _compiled()
    assert c.actions_by_actor.get("hero") == []
    assert dict(c.resource_decls_by_actor)["hero"]["charge"]["max"] == 3
    assert sorted(c.trigger_order) == ["on_x"]
    assert list(c.hooks) and [dict(x) for x in c.caveats] == [
        {"text": "t", "level": "approx"}]
    assert {**c.stage.enemy_actions} == {"e1": []}
    assert len(c.policy.parameters) == 1


def test_wrapper_severs_constructor_dict_alias():
    actions = {"hero": []}
    c = CompiledEncounter(build_team=(), actions_by_actor=actions,
                          stage=CompiledStage(stage_id="s", enemies=()),
                          policy=CompiledPolicy(name="p", action_rules=(),
                                                target_rules=()))
    actions["sneaky"] = []   # 构造方事后改原 dict——编译产物视图不受影响
    assert "sneaky" not in c.actions_by_actor


# ---------------------------------------------------------------------------
# deepcopy 链（debug checkpoint）：引擎深拷不炸、compiled 深拷副本同守冻结
# ---------------------------------------------------------------------------

def test_deepcopy_engine_via_from_compiled():
    engine = CombatEngine.from_compiled(_compiled())
    engine2 = copy.deepcopy(engine)   # checkpoint 链：共享 SummonDef/CompiledPolicy 解代理深拷
    assert isinstance(engine2.actions_by_actor, dict)
    assert engine2.decision.policy.parameters["focus"] == "e1"
    assert engine2.summon_defs["s1"].resource_decls["charge"]["max"] == 3


def test_deepcopy_compiled_keeps_freeze():
    c = _compiled()
    c2 = copy.deepcopy(c)
    assert isinstance(c2.actions_by_actor, MappingProxyType)
    with pytest.raises(TypeError):
        c2.actions_by_actor["x"] = []
    with pytest.raises(TypeError):
        c2.summon_defs["s1"].resource_decls["r2"] = {}
    # 内容等值且内层容器独立（深拷语义）
    assert c2.binding_params_by_actor["hero"] == {"p": 1.0}
    assert c2.binding_params_by_actor["hero"] is not c.binding_params_by_actor["hero"]
