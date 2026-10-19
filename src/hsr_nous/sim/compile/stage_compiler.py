"""stage.yaml 编译器：关卡配置 → CompiledStage（初始阵容 + 波次）.

v0.4 支持 inline 敌人定义、wave 敌人组与 stage_template 引用；引用侧只允许
stage_id/enemy_level_overrides 覆盖，不与 inline waves/termination/mode 合并。
"""
from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from hsr_nous.sim.compile.build_compiler import (
    DEFAULT_TEMPLATE_ROOTS, PREFER_TARGETS, _check_enum, _check_keys,
    _check_resistance, _check_weakness)
from hsr_nous.sim.compile.compiled import CompiledEnemyPolicy, CompiledStage, SummonDef
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.config_ai import MONSTER_RANK_VALUES

#: stage 顶层合法键（environment_overrides 暂留词表但显式报未实现）
_STAGE_KEYS = frozenset({
    "stage_id", "stage_template", "name", "enemies", "waves", "termination", "mode",
    "enemy_level_overrides", "environment_overrides",
})

#: inline 敌人合法键
_ENEMY_KEYS = frozenset({
    "enemy_template", "actor_id", "name", "level", "hp", "atk", "def", "spd",
    "max_toughness", "toughness_bars", "taunt", "weakness", "resistance", "policy", "groups",
})

#: 敌人序列/冷却策略合法键（v1 不开放其他 AI 字段）
_ENEMY_POLICY_KEYS = frozenset({
    "sequence", "cooldown", "initial_cooldown", "skill_ids", "skill_phases", "monster_rank", "config",
})

#: wave 合法键
_WAVE_KEYS = frozenset({"wave_index", "enemies"})

#: termination 合法键
_TERMINATION_KEYS = frozenset({"mode", "max_action_value"})

#: 敌人模板 base_stats / actions 合法键（模板=生成物，错拼在此炸而不是静默取缺省）
_ENEMY_TPL_BASE_KEYS = frozenset({"hp", "atk", "def", "spd", "max_toughness", "toughness_bars", "effect_res"})
_ENEMY_TPL_ACTION_KEYS = frozenset({
    "action_id", "name", "action_type", "target_type", "damage_type",
    "scaling", "scaling_blast", "toughness_dmg", "toughness_dmg_blast",
    "energy_gain", "energy_grant", "instances", "instance_variants", "prefer_target", "split", "available_if",
    "resource_gain", "instances_from_resource", "instances_base", "instances_per_point",
    "instances_cap", "consume_all_resource",
})

#: termination.mode 词表 = 10_termination.md 登记的四模式（spec 口径）；
#: 引擎 _should_terminate 消费 fixed_av（AV 截断）、kill_target（对面全灭——与我方全灭
#: 同为模式无关通则分支）、survival / wipe（通则双分支 + AV 预算外框，2026-10-12 实装）
TERMINATION_MODES = frozenset({"fixed_av", "kill_target", "survival", "wipe"})

#: 已实现的 termination.mode（引擎 _should_terminate 消费集；词表新增未接线值时
#: 从本集移除——编译期炸"未实现"指路，不静默吞）
TERMINATION_MODES_IMPLEMENTED = frozenset({"fixed_av", "kill_target", "survival", "wipe"})


def _parse_enemy_actions(items: Any, *, where: str) -> List[Any]:
    """敌人行动表（模板件与 inline 件同一形状/同一键闸）→ Action 列表."""
    from hsr_nous.sim_schema.action import Action

    actions: List[Any] = []
    seen_action_ids: set[str] = set()
    for a in items or []:
        _check_keys(a, _ENEMY_TPL_ACTION_KEYS, where=f"{where} action {a.get('action_id')!r}")
        if a.get("prefer_target"):
            _check_enum(a["prefer_target"], PREFER_TARGETS,
                        where=f"{where} action {a.get('action_id')!r}", field="prefer_target")
        action_id = str(a["action_id"])
        if action_id in seen_action_ids:
            raise ValueError(f"{where} action_id {action_id!r} 重复")
        seen_action_ids.add(action_id)
        actions.append(Action(
            action_id=action_id, name=a.get("name", action_id),
            action_type=a.get("action_type", "basic"),
            target_type=a.get("target_type", "single"),
            damage_type=a.get("damage_type") or None,
            scaling=[{k: float(v) for k, v in s.items()} for s in a.get("scaling") or []],
            scaling_blast=([{k: float(v) for k, v in s.items()}
                            for s in a.get("scaling_blast") or []] or None),
            toughness_dmg=int(a.get("toughness_dmg", 0)),
            toughness_dmg_blast=(int(a["toughness_dmg_blast"])
                                 if "toughness_dmg_blast" in a else None),
            energy_gain=int(a["energy_gain"]) if "energy_gain" in a else None,
            energy_grant=float(a.get("energy_grant", 0.0)),
            instances=int(a.get("instances", 1)),
            instance_variants=([None if iv is None else dict(iv)
                                for iv in a["instance_variants"]]
                               if a.get("instance_variants") is not None else None),
            prefer_target=str(a.get("prefer_target", "")),
            split=str(a.get("split", "")),
            available_if=str(a.get("available_if", "")),
            resource_gain={k: float(v) for k, v in (a.get("resource_gain") or {}).items()},
            instances_from_resource=str(a.get("instances_from_resource", "")),
            instances_base=int(a.get("instances_base", 0)),
            instances_per_point=float(a.get("instances_per_point", 1.0)),
            instances_cap=int(a.get("instances_cap", 0)),
            consume_all_resource=str(a.get("consume_all_resource", "")),
        ))
    return actions


def _apply_level_overrides(stage: Dict[str, Any], overrides: Any) -> None:
    """enemy_level_overrides：仅允许覆盖模板中实际出现的 enemy_template id."""
    if not isinstance(overrides, dict):
        raise ValueError("enemy_level_overrides 必须是 {enemy_id: level} 映射")
    enemy_specs = list(stage.get("enemies", [])) + [
        e for wave in stage.get("waves", []) for e in wave.get("enemies", [])]
    allowed = {str(e.get("enemy_template")) for e in enemy_specs if e.get("enemy_template")}
    for enemy_id, level in overrides.items():
        if enemy_id not in allowed:
            raise ValueError(f"enemy_level_overrides 的 {enemy_id!r} 不在 stage 模板怪物清单中")
        if isinstance(level, bool) or not isinstance(level, int) or not (1 <= level <= 120):
            raise ValueError(f"enemy_level_overrides[{enemy_id!r}]={level!r} 越界（合法 1-120 整数）")
    for spec in enemy_specs:
        enemy_id = spec.get("enemy_template")
        if enemy_id in overrides:
            spec["level"] = overrides[enemy_id]


def _parse_enemy_policy(value: Any, *, where: str) -> Optional[CompiledEnemyPolicy]:
    """模板 policy 块 → CompiledEnemyPolicy；空序列不做表序兜底."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{where} policy 必须是 mapping")
    _check_keys(value, _ENEMY_POLICY_KEYS, where=where)
    raw_sequence = value.get("sequence")
    if raw_sequence is None:
        raw_sequence = []
    elif not raw_sequence and not value.get("config"):
        raise ValueError(f"{where} policy.sequence 不能为空（空序列语义未知）")
    if not isinstance(raw_sequence, (list, tuple)):
        raise ValueError(f"{where} policy.sequence 必须是数组")
    sequence: List[str] = []
    for item in raw_sequence:
        if isinstance(item, bool) or not isinstance(item, (str, int)) or not str(item):
            raise ValueError(f"{where} policy.sequence 含非法技能 id {item!r}")
        sequence.append(str(item))
    skill_ids = value.get("skill_ids") or {}
    if not isinstance(skill_ids, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in skill_ids.items()):
        raise ValueError(f"{where} skill_ids 必须是 {{SkillTriggerKey: action_id}} 字符串映射")
    config = value.get("config") or {}
    if not isinstance(config, dict):
        raise ValueError(f"{where} config 必须是 mapping")

    def _cooldowns(raw: Any, name: str) -> Dict[str, int]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError(f"{where} {name} 必须是 mapping")
        out: Dict[str, int] = {}
        for action_id, cooldown_value in raw.items():
            if (isinstance(cooldown_value, bool) or not isinstance(cooldown_value, int)
                    or cooldown_value < 0):
                raise ValueError(
                    f"{where} {name}[{action_id!r}]={cooldown_value!r} 必须是非负整数")
            out[str(action_id)] = cooldown_value
        return out

    raw_phases = value.get("skill_phases") or {}
    if not isinstance(raw_phases, dict):
        raise ValueError(f"{where} skill_phases 必须是 mapping")
    skill_phases: Dict[str, tuple[int, ...]] = {}
    for action_id, phase_list in raw_phases.items():
        if not isinstance(phase_list, (list, tuple)) or not phase_list:
            raise ValueError(f"{where} skill_phases[{action_id!r}] 必须是非空阶段数组")
        if any(isinstance(phase, bool) or not isinstance(phase, int) or phase <= 0
               for phase in phase_list):
            raise ValueError(f"{where} skill_phases[{action_id!r}] 含非法阶段号")
        skill_phases[str(action_id)] = tuple(phase_list)

    monster_rank = str(value.get("monster_rank") or "")
    if monster_rank not in set(MONSTER_RANK_VALUES) | {""}:
        raise ValueError(f"{where} monster_rank={monster_rank!r} 非法")

    return CompiledEnemyPolicy(
        sequence=tuple(sequence),
        cooldown=_cooldowns(value.get("cooldown"), "cooldown"),
        initial_cooldown=_cooldowns(value.get("initial_cooldown"), "initial_cooldown"),
        skill_ids=dict(skill_ids),
        skill_phases=skill_phases,
        monster_rank=monster_rank,
        config=config,
    )


class StageCompiler:
    """stage.yaml → CompiledStage."""

    def _compile_enemy(
        self, spec: Dict[str, Any], *, roots: Sequence[Union[str, Path]], hook_compiler: Any = None,
    ) -> tuple[Actor, List[Any], Optional[CompiledEnemyPolicy], List[Any], List[Any], Dict[str, Any]]:
        """inline 敌人 / enemy_template 引用 → (Actor, actions, policy, hooks, summons, resources)."""
        from hsr_nous.sim_schema.action import Action

        _check_keys(spec, _ENEMY_KEYS, where=f"enemy {spec.get('actor_id') or spec.get('enemy_template')!r}")
        e_desc = f"enemy {spec.get('actor_id') or spec.get('enemy_template')!r}"
        level = int(spec.get("level", 80))
        if not (1 <= level <= 120):
            raise ValueError(f"{e_desc} level {level} 越界（合法 1-120，13_validator §13.3）")
        if float(spec.get("spd", 100.0)) <= 0:
            raise ValueError(f"{e_desc} spd 必须 > 0，实得 {spec.get('spd')!r}（13_validator §13.3）")
        if spec.get("enemy_template"):
            from hsr_nous.sim.compile.build_compiler import BuildCompiler
            tpl = BuildCompiler._load_template("enemies", str(spec["enemy_template"]), roots=roots)
            level = int(spec.get("level", tpl.get("level", 80)))
            if not (1 <= level <= 120):
                raise ValueError(
                    f"{e_desc} level {level} 越界（合法 1-120，13_validator §13.3）")
            base = tpl.get("base_stats", {})
            _check_keys(base, _ENEMY_TPL_BASE_KEYS,
                        where=f"enemy 模板 {spec['enemy_template']} base_stats")
            stats = StatBlock(
                hp=float(base.get("hp", 0.0)), atk=float(base.get("atk", 0.0)),
                def_=float(base.get("def", 0.0)), spd=float(base.get("spd", 100.0)),
                max_toughness=float(base.get("max_toughness", 0.0)),
                toughness_bars=[float(x) for x in (base.get("toughness_bars") or [])],
                effect_res=float(base.get("effect_res", 0.0)),
                taunt=float(spec.get("taunt", 100.0)),
            )
            # 引用侧 weakness 可覆盖（召唤物候选弱点池→入场时为空、机制再揭示真实弱点）；
            # 未写时完整继承模板，既有敌人行为不变。
            stats.weakness = list(spec["weakness"] if "weakness" in spec else (tpl.get("weakness") or []))
            _check_weakness(stats.weakness, where=f"enemy 模板 {spec['enemy_template']}")
            stats.resistance = {k: float(v) for k, v in (tpl.get("resistance") or {}).items()}
            actor = Actor(
                # actor_id/name 引用侧可覆盖：同模板多放（一波同型怪/多个沙包）靠它去重——
                # 不覆盖则多份引用同 id，compile() 重复闸炸（引擎按 id 键控只剩一只=静默吞）
                actor_id=str(spec.get("actor_id") or tpl["enemy_id"]),
                name=spec.get("name") or tpl.get("name", tpl["enemy_id"]),
                actor_type="monster", level=level,
                stats=stats,
            )
            actor.groups = list(tpl.get("groups") or [])
            actions = _parse_enemy_actions(
                tpl.get("actions"), where=f"enemy 模板 {spec['enemy_template']}")
            policy = _parse_enemy_policy(
                tpl.get("policy"), where=f"enemy 模板 {spec['enemy_template']} policy")
            enemy_hooks: List[Any] = []
            compiler = hook_compiler or BuildCompiler()
            if tpl.get("hooks"):
                compiler._compile_hooks(
                    tpl["hooks"], f"enemy 模板 {spec['enemy_template']}", actor.actor_id,
                    enemy_hooks)
            resource_decls = compiler._parse_resource_decls(
                tpl.get("custom_resources") or {},
                f"enemy 模板 {spec['enemy_template']}", actor.actor_id, enemy_hooks)
            return (actor, actions, policy, enemy_hooks, list(tpl.get("summons") or []),
                    resource_decls)

        stats = StatBlock(
            hp=float(spec.get("hp", 0.0)),
            atk=float(spec.get("atk", 0.0)),
            def_=float(spec.get("def", 0.0)),
            spd=float(spec.get("spd", 100.0)),
            max_toughness=float(spec.get("max_toughness", 0.0)),
            toughness_bars=[float(x) for x in (spec.get("toughness_bars") or [])],
            taunt=float(spec.get("taunt", 100.0)),
        )
        stats.weakness = list(spec.get("weakness") or [])
        _check_weakness(stats.weakness, where=f"inline enemy {spec.get('actor_id')!r}")
        stats.resistance = {k: float(v) for k, v in (spec.get("resistance") or {}).items()}
        _check_resistance(stats.resistance, where=f"inline enemy {spec.get('actor_id')!r}")
        actor = Actor(
            actor_id=spec["actor_id"],
            name=spec.get("name", spec["actor_id"]),
            actor_type="monster",
            level=level,
            stats=stats,
        )
        actor.groups = list(spec.get("groups") or [])
        policy = _parse_enemy_policy(spec.get("policy"), where=f"{e_desc} policy")
        return actor, [], policy, [], [], {}

    def compile(self, stage: Dict[str, Any], *,
                template_roots: Optional[Sequence[Union[str, Path]]] = None,
                hook_compiler: Any = None) -> CompiledStage:
        _check_keys(stage, _STAGE_KEYS, where="stage")
        roots = (tuple(str(r) for r in template_roots)
                 if template_roots is not None else DEFAULT_TEMPLATE_ROOTS)
        if "stage_template" in stage:
            ref = stage["stage_template"]
            if not isinstance(ref, str) or not ref or "/" in ref or "\\" in ref:
                raise ValueError(f"stage_template 引用必须是单个模板 id（得到 {ref!r}）")
            if any(key in stage for key in ("enemies", "waves", "termination", "mode")):
                raise ValueError(
                    "stage_template 不得与 inline enemies/waves/termination/mode 同写——"
                    "不做两套输入合并")
            unsupported = set(stage) - {
                "stage_template", "stage_id", "enemy_level_overrides", "environment_overrides",
            }
            if unsupported:
                raise ValueError(
                    f"stage_template 引用侧只允许 stage_id/enemy_level_overrides 覆盖，"
                    f"得到多余键 {sorted(unsupported)}")
            from hsr_nous.sim.compile.build_compiler import BuildCompiler

            tpl = BuildCompiler._load_template("stages", ref, roots=roots)
            if tpl.get("stage_template"):
                raise ValueError(f"stage 模板 {ref!r} 不得嵌套 stage_template")
            if "enemy_level_overrides" in tpl or "environment_overrides" in tpl:
                raise ValueError(f"stage 模板 {ref!r} 不得包含覆盖槽")
            _check_keys(tpl, _STAGE_KEYS, where=f"stage 模板 {ref}")
            stage_id_override = stage.get("stage_id")
            level_overrides = stage.get("enemy_level_overrides")
            stage = copy.deepcopy(tpl)
            if stage_id_override is not None:
                stage["stage_id"] = stage_id_override
            if level_overrides is not None:
                _apply_level_overrides(stage, level_overrides)
        elif "enemy_level_overrides" in stage:
            raise ValueError("enemy_level_overrides 仅可与 stage_template 同写")
        if "environment_overrides" in stage:
            raise NotImplementedError("environment_overrides 尚未实现，禁止静默接受")
        waves_spec = stage.get("waves", [])
        if len(waves_spec) > 10:
            raise ValueError(f"stage 波次数 {len(waves_spec)} 超上限 10（13_validator §13.3）")
        enemy_actions: Dict[str, List[Any]] = {}
        enemy_policies: Dict[str, CompiledEnemyPolicy] = {}
        enemy_hooks: List[Any] = []
        enemy_summon_defs: Dict[str, SummonDef] = {}
        enemy_resource_decls: Dict[str, Dict[str, Any]] = {}
        enemies: List[Actor] = []
        seen_ids: Dict[str, str] = {}  # actor_id 终值 → 首次出现位置（重复即炸闸）

        def _no_dup(actor: Actor, where: str) -> None:
            """重复 actor_id 编译期炸（enemies + waves 全查，终值口径——inline actor_id /
            模板 enemy_id 回退 / 引用侧覆盖后同判）：引擎 state.actors[id] 与 scheduler
            按 id 键控，同 id 两单位互相覆盖只剩一只=静默吞（曾钉为预期行为，2026-10-12
            改闸）；同模板多放合法路径 = 引用侧 actor_id 覆盖去重（web 表单层同口径——
            battles「同一敌人不可复选」）。"""
            first = seen_ids.get(actor.actor_id)
            if first is not None:
                raise ValueError(
                    f"{where} 的 actor_id {actor.actor_id!r} 重复（与 {first} 撞）——同 id "
                    f"单位引擎按 id 键控只剩一只；同模板多放请用引用侧 actor_id 覆盖去重")
            seen_ids[actor.actor_id] = where

        def _namespace_summons(owner: Actor, hooks: List[Any], specs: List[Any]):
            """召唤物 ID 加召唤者实例后缀；hook 与定义同步改写，跨波同型怪不撞名."""
            mapping = {
                str(spec["summon_id"]): f"{spec['summon_id']}__{owner.actor_id}"
                for spec in specs
            }
            namespaced_hooks = []
            for hook in hooks:
                effects = tuple(
                    {**eff, "summon_id": mapping[str(eff["summon_id"])]}
                    if eff.get("summon_id") in mapping else eff
                    for eff in hook.effects)
                namespaced_hooks.append(replace(hook, effects=effects))
            namespaced_specs = [
                {**spec, "summon_id": mapping[str(spec["summon_id"])]}
                for spec in specs
            ]
            return namespaced_hooks, namespaced_specs

        def _compile_summons(owner: Actor, specs: List[Any], where: str) -> None:
            for summon_spec in specs:
                compile_spec = dict(summon_spec)
                compile_spec["actor_id"] = compile_spec.pop("summon_id")
                summoned, acts, policy, hooks, _nested_summon_specs, resources = self._compile_enemy(
                    compile_spec, roots=roots, hook_compiler=hook_compiler)
                _no_dup(summoned, where)
                summoned.summoner_id = owner.actor_id
                enemy_summon_defs[summoned.actor_id] = SummonDef(
                    owner_id=owner.actor_id, actor=summoned,
                    inheritance="none", control="auto")
                if acts:
                    enemy_actions[summoned.actor_id] = acts
                if policy is not None:
                    enemy_policies[summoned.actor_id] = policy
                if resources:
                    enemy_resource_decls[summoned.actor_id] = resources
                enemy_hooks.extend(hooks)

        for i, e in enumerate(stage.get("enemies", [])):
            actor, acts, policy, hooks, summon_specs, resources = self._compile_enemy(
                e, roots=roots, hook_compiler=hook_compiler)
            _no_dup(actor, f"stage enemies[{i}]")
            hooks, summon_specs = _namespace_summons(actor, hooks, summon_specs)
            enemies.append(actor)
            if acts:
                enemy_actions[actor.actor_id] = acts
            if policy is not None:
                enemy_policies[actor.actor_id] = policy
            if resources:
                enemy_resource_decls[actor.actor_id] = resources
            enemy_hooks.extend(hooks)
            _compile_summons(actor, summon_specs, f"stage enemies[{i}] summons")
        if len(enemies) > 10:
            raise ValueError(f"stage 首波敌人数 {len(enemies)} 超上限 10（13_validator §13.3）")
        waves: Dict[int, tuple[Actor, ...]] = {}
        for w in waves_spec:
            _check_keys(w, _WAVE_KEYS, where=f"stage waves[{w.get('wave_index')!r}]")
            idx = int(w["wave_index"])
            wave_actors: List[Actor] = []
            for i, e in enumerate(w.get("enemies", [])):
                actor, acts, policy, hooks, summon_specs, resources = self._compile_enemy(
                    e, roots=roots, hook_compiler=hook_compiler)
                _no_dup(actor, f"stage waves[{idx}] enemies[{i}]")
                hooks, summon_specs = _namespace_summons(actor, hooks, summon_specs)
                wave_actors.append(actor)
                if acts:
                    enemy_actions[actor.actor_id] = acts
                if policy is not None:
                    enemy_policies[actor.actor_id] = policy
                if resources:
                    enemy_resource_decls[actor.actor_id] = resources
                enemy_hooks.extend(hooks)
                _compile_summons(actor, summon_specs, f"stage waves[{idx}] enemies[{i}] summons")
            if len(wave_actors) > 10:
                raise ValueError(f"stage waves[{idx}] 敌人数超上限 10（13_validator §13.3）")
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
            enemy_policies=enemy_policies,
            enemy_hooks=tuple(enemy_hooks),
            enemy_summon_defs=enemy_summon_defs,
            enemy_resource_decls=enemy_resource_decls,
            cycle=cycle,
        )
