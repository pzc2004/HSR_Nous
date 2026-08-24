"""绑定编译层：DSL 模板（YAML）→ 不可变 CompiledEncounter.

编译器分层（design 02）：前端 parse → 绑定（符号解析+AST 预编译+糖 desugar）→ 产物。
v0.3 支持 inline 角色/敌人定义；模板引用待 adapters 生成后接入。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import yaml

from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.compile.compiled import CompiledEncounter, CompiledStage
from hsr_nous.sim.compile.expr_compiler import ExprCompiler
from hsr_nous.sim.compile.stage_compiler import StageCompiler
from hsr_nous.sim.compile.sugar import desugar, list_sugars

__all__ = [
    "compile_encounter",
    "compile_encounter_yaml",
    "CompiledEncounter",
    "CompiledStage",
    "ExprCompiler",
    "desugar",
    "list_sugars",
]


def compile_encounter(
    build: Dict[str, Any],
    stage: Dict[str, Any],
    *,
    expr: Optional[ExprCompiler] = None,
) -> CompiledEncounter:
    """build/stage 字典 → CompiledEncounter."""
    expr = expr or ExprCompiler()
    team, actions, policy, modifiers, state_configs, hooks, resource_ids = BuildCompiler(expr).compile(build.get("build", build))
    compiled_stage = StageCompiler().compile(stage.get("stage", stage))
    # 敌人模板自带的行动表并入（build 侧同名键优先——我方/敌方 id 不冲突，直接合并）
    actions = {**compiled_stage.enemy_actions, **actions}
    return CompiledEncounter(
        build_team=team,
        actions_by_actor=actions,
        stage=compiled_stage,
        policy=policy,
        modifiers_by_actor=modifiers,
        state_configs_by_actor=state_configs,
        hooks=hooks,
        resource_ids_by_actor=resource_ids,
        expr=expr,
    )


def compile_encounter_yaml(build_yaml: str, stage_yaml: str) -> CompiledEncounter:
    """YAML 文本 → CompiledEncounter."""
    return compile_encounter(yaml.safe_load(build_yaml), yaml.safe_load(stage_yaml))
