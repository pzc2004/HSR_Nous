"""stage.yaml 编译器：关卡配置 → CompiledStage（初始阵容 + 波次）.

v0.3 支持 inline 敌人定义与 wave 敌人组；模板引用待 adapters。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from hsr_nous.sim.compile.compiled import CompiledStage
from hsr_nous.sim_schema.actor import Actor, StatBlock


class StageCompiler:
    """stage.yaml → CompiledStage."""

    def _compile_enemy(self, spec: Dict[str, Any]) -> tuple[Actor, List[Any]]:
        """inline 敌人 / enemy_template 引用 → (Actor, actions)."""
        from hsr_nous.sim_schema.action import Action

        if spec.get("enemy_template"):
            from hsr_nous.sim.compile.build_compiler import BuildCompiler
            tpl = BuildCompiler._load_template("enemies", str(spec["enemy_template"]))
            base = tpl.get("base_stats", {})
            stats = StatBlock(
                hp=float(base.get("hp", 0.0)), atk=float(base.get("atk", 0.0)),
                def_=float(base.get("def", 0.0)), spd=float(base.get("spd", 100.0)),
                max_toughness=float(base.get("max_toughness", 0.0)),
                effect_res=float(base.get("effect_res", 0.0)),
                taunt=float(spec.get("taunt", 100.0)),
            )
            stats.weakness = list(tpl.get("weakness") or [])
            actor = Actor(
                actor_id=tpl["enemy_id"], name=tpl.get("name", tpl["enemy_id"]),
                actor_type="monster", level=int(spec.get("level", tpl.get("level", 80))),
                stats=stats,
            )
            actions = [
                Action(
                    action_id=a["action_id"], name=a.get("name", a["action_id"]),
                    action_type=a.get("action_type", "basic"),
                    target_type=a.get("target_type", "single"),
                    damage_type=a.get("damage_type") or None,
                    scaling=[{k: float(v) for k, v in s.items()} for s in a.get("scaling") or []],
                    toughness_dmg=int(a.get("toughness_dmg", 0)),
                    energy_grant=float(a.get("energy_grant", 0.0)),
                )
                for a in tpl.get("actions") or []
            ]
            return actor, actions

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
        ), []

    def compile(self, stage: Dict[str, Any]) -> CompiledStage:
        if stage.get("stage_template"):
            raise NotImplementedError("stage_template 引用待 adapters 生成后接入（v0.3 仅支持 inline）")

        enemy_actions: Dict[str, List[Any]] = {}
        enemies: List[Actor] = []
        for e in stage.get("enemies", []):
            actor, acts = self._compile_enemy(e)
            enemies.append(actor)
            if acts:
                enemy_actions[actor.actor_id] = acts
        waves: Dict[int, tuple[Actor, ...]] = {}
        for w in stage.get("waves", []):
            idx = int(w["wave_index"])
            wave_actors: List[Actor] = []
            for e in w.get("enemies", []):
                actor, acts = self._compile_enemy(e)
                wave_actors.append(actor)
                if acts:
                    enemy_actions[actor.actor_id] = acts
            waves[idx] = tuple(wave_actors)

        term = stage.get("termination") or {}
        return CompiledStage(
            stage_id=stage.get("stage_id", "stage"),
            enemies=tuple(enemies),
            waves=waves,
            termination_mode=term.get("mode", "fixed_av"),
            max_action_value=float(term.get("max_action_value", 450.0)),
            enemy_actions=enemy_actions,
        )
