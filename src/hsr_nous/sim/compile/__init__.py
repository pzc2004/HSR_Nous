"""绑定编译层：DSL 模板（YAML）→ 不可变 CompiledEncounter.

编译器分层（design 02）：前端 parse → 绑定（符号解析+AST 预编译+糖 desugar）→ 产物。
v0.3 支持 inline 角色/敌人定义；模板引用待 adapters 生成后接入。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

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
    template_roots: Optional[Sequence[Union[str, Path]]] = None,
) -> CompiledEncounter:
    """build/stage 字典 → CompiledEncounter.

    template_roots：模板根注入（有序，先命中根生效——测试借此让人工 fixtures 根
    优先于 data/ 生成根）；None → 生产缺省 data/sim_templates
    （见 build_compiler.DEFAULT_TEMPLATE_ROOTS，行为与不注入的历史版本一致）。
    """
    expr = expr or ExprCompiler()
    team, actions, policy, modifiers, state_configs, hooks, resource_ids = BuildCompiler(expr).compile(
        build.get("build", build), template_roots=template_roots)
    compiled_stage = StageCompiler().compile(stage.get("stage", stage), template_roots=template_roots)
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


def compile_encounter_yaml(
    build_yaml: str,
    stage_yaml: str,
    *,
    template_roots: Optional[Sequence[Union[str, Path]]] = None,
) -> CompiledEncounter:
    """YAML 文本 → CompiledEncounter（template_roots 语义同 compile_encounter）。"""
    return compile_encounter(yaml.safe_load(build_yaml), yaml.safe_load(stage_yaml),
                             template_roots=template_roots)
