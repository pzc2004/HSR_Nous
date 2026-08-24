"""stage.yaml 编译器：关卡配置 → CompiledStage（初始阵容 + 波次）.

v0.3 支持 inline 敌人定义与 wave 敌人组；模板引用待 adapters。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from hsr_nous.sim.compile.build_compiler import _check_enum, _check_keys
from hsr_nous.sim.compile.compiled import CompiledStage
from hsr_nous.sim_schema.actor import Actor, StatBlock

#: stage 顶层合法键（enemy_level_overrides/environment_overrides 属 stage_template
#: 通道的覆盖槽——该通道未接入（NotImplementedError），inline 写了=静默吞，拒绝）
_STAGE_KEYS = frozenset({"stage_id", "stage_template", "enemies", "waves", "termination", "mode"})

#: inline 敌人合法键
_ENEMY_KEYS = frozenset({
    "enemy_template", "actor_id", "name", "level", "hp", "atk", "def", "spd",
    "max_toughness", "taunt", "weakness", "resistance",
})

#: wave 合法键
_WAVE_KEYS = frozenset({"wave_index", "enemies"})

#: termination 合法键
_TERMINATION_KEYS = frozenset({"mode", "max_action_value"})

#: 敌人模板 base_stats / actions 合法键（模板=生成物，错拼在此炸而不是静默取缺省）
_ENEMY_TPL_BASE_KEYS = frozenset({"hp", "atk", "def", "spd", "max_toughness", "effect_res"})
_ENEMY_TPL_ACTION_KEYS = frozenset({
    "action_id", "name", "action_type", "target_type", "damage_type",
    "scaling", "toughness_dmg", "energy_grant",
})

#: termination.mode 词表 = 10_termination.md 登记的四模式（spec 口径）；
#: 引擎 _should_terminate 现仅消费 fixed_av（kill_target 的死分支已删——全灭判停是
#: 模式无关的第一分支）；kill_target / survival / wipe 已登记未实现——
#: 写这三个值编译期炸"未实现"指路（曾编译通过但引擎不判停=静默吞）
TERMINATION_MODES = frozenset({"fixed_av", "kill_target", "survival", "wipe"})

#: 已实现的 termination.mode（引擎 _should_terminate 消费集）
TERMINATION_MODES_IMPLEMENTED = frozenset({"fixed_av"})


class StageCompiler:
    """stage.yaml → CompiledStage."""

    def _compile_enemy(self, spec: Dict[str, Any]) -> tuple[Actor, List[Any]]:
        """inline 敌人 / enemy_template 引用 → (Actor, actions)."""
        from hsr_nous.sim_schema.action import Action

        _check_keys(spec, _ENEMY_KEYS, where=f"enemy {spec.get('actor_id') or spec.get('enemy_template')!r}")
        if spec.get("enemy_template"):
            from hsr_nous.sim.compile.build_compiler import BuildCompiler
            tpl = BuildCompiler._load_template("enemies", str(spec["enemy_template"]))
            base = tpl.get("base_stats", {})
            _check_keys(base, _ENEMY_TPL_BASE_KEYS,
                        where=f"enemy 模板 {spec['enemy_template']} base_stats")
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
            actions = []
            for a in tpl.get("actions") or []:
                _check_keys(a, _ENEMY_TPL_ACTION_KEYS,
                            where=f"enemy 模板 {spec['enemy_template']} action {a.get('action_id')!r}")
                actions.append(Action(
                    action_id=a["action_id"], name=a.get("name", a["action_id"]),
                    action_type=a.get("action_type", "basic"),
                    target_type=a.get("target_type", "single"),
                    damage_type=a.get("damage_type") or None,
                    scaling=[{k: float(v) for k, v in s.items()} for s in a.get("scaling") or []],
                    toughness_dmg=int(a.get("toughness_dmg", 0)),
                    energy_grant=float(a.get("energy_grant", 0.0)),
                ))
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
        _check_keys(stage, _STAGE_KEYS, where="stage")
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
            _check_keys(w, _WAVE_KEYS, where=f"stage waves[{w.get('wave_index')!r}]")
            idx = int(w["wave_index"])
            wave_actors: List[Actor] = []
            for e in w.get("enemies", []):
                actor, acts = self._compile_enemy(e)
                wave_actors.append(actor)
                if acts:
                    enemy_actions[actor.actor_id] = acts
            waves[idx] = tuple(wave_actors)

        term = stage.get("termination") or {}
        _check_keys(term, _TERMINATION_KEYS, where="stage termination")
        _check_enum(term.get("mode"), TERMINATION_MODES, where="stage termination", field="mode")
        if term.get("mode") is not None and str(term["mode"]) not in TERMINATION_MODES_IMPLEMENTED:
            raise ValueError(
                f"stage termination 的 mode {term['mode']!r} 已登记但未实现（引擎 _should_terminate "
                f"仅消费 {sorted(TERMINATION_MODES_IMPLEMENTED)}；四模式登记见 10_termination.md）"
            )
        # 玩法模式 → 轮次配置（rulebook modes 节查表；stage.yaml 无 mode 字段则 cycle=None）
        cycle = None
        mode_key = stage.get("mode")
        if mode_key:
            from hsr_nous.sim_schema.encounter import Cycle
            from hsr_nous.sim_schema.rulebook import get_rulebook
            modes = get_rulebook().modes
            spec = modes.get(str(mode_key))
            if spec is None:
                # mode 拼错曾静默关闭轮次系统（cycle=None 零提示）——编译期炸
                raise ValueError(
                    f"stage 的 mode 非法值 {mode_key!r}（合法集合：{sorted(modes)}，"
                    f"见 rulebook.yaml modes 节）"
                )
            cycle = Cycle(
                first_cycle_av=int(spec["first_cycle_av"]),
                subsequent_cycle_av=int(spec["subsequent_cycle_av"]),
                reset_on_wave=bool(spec.get("reset_on_wave", False)),
            )
        return CompiledStage(
            stage_id=stage.get("stage_id", "stage"),
            enemies=tuple(enemies),
            waves=waves,
            termination_mode=term.get("mode", "fixed_av"),
            max_action_value=float(term.get("max_action_value", 450.0)),
            enemy_actions=enemy_actions,
            cycle=cycle,
        )
