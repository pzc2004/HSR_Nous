"""stage.yaml 编译器：关卡配置 → CompiledStage（初始阵容 + 波次）.

v0.3 支持 inline 敌人定义与 wave 敌人组；模板引用待 adapters。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from hsr_nous.sim.compile.compiled import CompiledStage
from hsr_nous.sim_schema.actor import Actor, StatBlock


class StageCompiler:
    """stage.yaml → CompiledStage."""

    def _compile_enemy(self, spec: Dict[str, Any]) -> Actor:
        stats = StatBlock(
            hp=float(spec.get("hp", 0.0)),
            atk=float(spec.get("atk", 0.0)),
            def_=float(spec.get("def", 0.0)),
            spd=float(spec.get("spd", 100.0)),
            max_toughness=float(spec.get("max_toughness", 0.0)),
            taunt=float(spec.get("taunt", 100.0)),
        )
        stats.weakness = list(spec.get("weakness") or [])
        stats.resistance = {k: float(v) for k, v in (spec.get("resistance") or {}).items()}
        return Actor(
            actor_id=spec["actor_id"],
            name=spec.get("name", spec["actor_id"]),
            actor_type="monster",
            level=int(spec.get("level", 80)),
            stats=stats,
        )

    def compile(self, stage: Dict[str, Any]) -> CompiledStage:
        if stage.get("stage_template"):
            raise NotImplementedError("stage_template 引用待 adapters 生成后接入（v0.3 仅支持 inline）")

        enemies = tuple(self._compile_enemy(e) for e in stage.get("enemies", []))
        waves: Dict[int, tuple[Actor, ...]] = {}
        for w in stage.get("waves", []):
            idx = int(w["wave_index"])
            waves[idx] = tuple(self._compile_enemy(e) for e in w.get("enemies", []))

        term = stage.get("termination") or {}
        return CompiledStage(
            stage_id=stage.get("stage_id", "stage"),
            enemies=enemies,
            waves=waves,
            termination_mode=term.get("mode", "fixed_av"),
            max_action_value=float(term.get("max_action_value", 450.0)),
        )
