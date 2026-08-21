"""build.yaml 编译器：配装配置 → 队伍 Actor + CompiledPolicy.

v0.3 支持两种角色定义：
- `inline:` 内联（测试/独立场景用）：直接给基础面板与技能
- `character_template: "<id>"`：引用 data/sim_templates 模板（adapters 后置，暂抛 NotImplementedError）

遗器词条计算：主词条满级 + 副词条按 roll 数 × base（pipeline relic affix 数据）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from hsr_nous.sim.compile.compiled import CompiledPolicy, CompiledPolicyRule
from hsr_nous.sim.compile.expr_compiler import ExprCompiler
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock

# 主词条 id → StatBlock 字段与满级值（v0.3 常用子集；全表在 pipeline relic affix 数据）
_MAIN_AFFIX: Dict[str, tuple[str, float]] = {
    "hp": ("hp", 705.6), "atk": ("atk", 352.8),
    "hp_pct": ("hp_pct", 0.432), "atk_pct": ("atk_pct", 0.432), "def_pct": ("def_pct", 0.54),
    "spd": ("spd", 25.032), "crit_rate": ("crit_rate", 0.324), "crit_dmg": ("crit_dmg", 0.648),
    "effect_hit": ("effect_hit", 0.432), "effect_res": ("effect_res", 0.432),
    "break_effect": ("break_effect", 0.648), "energy_regen": ("energy_regen", 0.194),
    "heal_bonus": ("heal_bonus", 0.345),
    "ice_dmg": ("dmg_ice", 0.388), "fire_dmg": ("dmg_fire", 0.388),
    "thunder_dmg": ("dmg_thunder", 0.388), "wind_dmg": ("dmg_wind", 0.388),
    "physical_dmg": ("dmg_physical", 0.388), "quantum_dmg": ("dmg_quantum", 0.388),
    "imaginary_dmg": ("dmg_imaginary", 0.388),
}

# 副词条 id → (字段, 每 roll 值)（5★ 遗器基础值；step 见 pipeline 数据）
_SUB_AFFIX: Dict[str, tuple[str, float]] = {
    "hp": ("hp", 42.34), "atk": ("atk", 21.17), "def_": ("def_", 21.17),
    "hp_pct": ("hp_pct", 0.0432), "atk_pct": ("atk_pct", 0.0432), "def_pct": ("def_pct", 0.054),
    "spd": ("spd", 2.6), "crit_rate": ("crit_rate", 0.0324), "crit_dmg": ("crit_dmg", 0.0648),
    "effect_hit": ("effect_hit", 0.0432), "effect_res": ("effect_res", 0.0432),
    "break_effect": ("break_effect", 0.0648),
}

_DMG_KEYS = {"dmg_physical", "dmg_fire", "dmg_ice", "dmg_thunder", "dmg_wind", "dmg_quantum", "dmg_imaginary"}


class BuildCompiler:
    """build.yaml → (team actors, actions_by_actor, CompiledPolicy)."""

    def __init__(self, expr: Optional[ExprCompiler] = None) -> None:
        self.expr = expr or ExprCompiler()

    @staticmethod
    def _load_template(kind: str, ref: str) -> Dict[str, Any]:
        """加载 data/sim_templates/<kind>/<id>_*.yaml 模板（kind=characters/light_cones/relics/enemies）.

        同 id 多文件时按文件名排序取第一个——人工全机制版用英文小写命名（如
        `1408_phainon.yaml`），稳定排在生成器的中文名文件之前（排序确定性）。
        """
        import glob

        import yaml
        hits = sorted(glob.glob(f"data/sim_templates/{kind}/{ref}_*.yaml")) or glob.glob(
            f"data/sim_templates/{kind}/{ref}.yaml")
        if not hits:
            raise FileNotFoundError(
                f"模板 {kind}/{ref} 不存在：先跑 adapters/template_generator 生成"
            )
        with open(hits[0], encoding="utf-8") as f:
            return yaml.safe_load(f)

    @classmethod
    def _load_character_template(cls, ref: str) -> Dict[str, Any]:
        return cls._load_template("characters", ref)

    # ------------------------------------------------------------------
    # 角色（inline）
    # ------------------------------------------------------------------

    def _compile_inline_character(self, spec: Dict[str, Any]) -> tuple[Actor, List[Action]]:
        """内联角色定义 / 模板引用 → Actor + 技能列表."""
        ref = spec.get("character_template")
        if ref is not None and not str(ref).startswith("inline"):
            tpl = self._load_character_template(str(ref))
            # 模板提供 actor_id/name/base_stats/actions；member 提供 level/eidolon/relics 覆盖
            spec = {**tpl, **{k: v for k, v in spec.items() if k in ("level", "eidolon", "relics")}}

        base = spec.get("base_stats", {})
        stats = StatBlock(
            hp=float(base.get("hp", 0.0)),
            atk=float(base.get("atk", 0.0)),
            def_=float(base.get("def", 0.0)),
            spd=float(base.get("spd", 100.0)),
            crit_rate=float(base.get("crit_rate", 0.05)),
            crit_dmg=float(base.get("crit_dmg", 0.5)),
            break_effect=float(base.get("break_effect", 0.0)),
            effect_hit=float(base.get("effect_hit", 0.0)),
            effect_res=float(base.get("effect_res", 0.0)),
            max_energy=float(base.get("max_energy", 100.0)),
            energy_regen=float(base.get("energy_regen", 1.0)),
            taunt=float(base.get("taunt", 100.0)),
        )
        for k, v in (base.get("dmg_bonus") or {}).items():
            stats.dmg_bonus[k] = float(v)
        stats.weakness = list(base.get("weakness") or [])
        stats.resistance = {k: float(v) for k, v in (base.get("resistance") or {}).items()}

        actor = Actor(
            actor_id=spec["actor_id"],
            name=spec.get("name", spec["actor_id"]),
            actor_type=spec.get("actor_type", "character"),
            level=int(spec.get("level", 80)),
            stats=stats,
        )

        actions: List[Action] = []
        for a in spec.get("actions", []):
            scaling = a.get("scaling") or []
            actions.append(Action(
                action_id=a["action_id"],
                name=a.get("name", a["action_id"]),
                action_type=a["action_type"],
                target_type=a.get("target_type", "single"),
                damage_type=a.get("damage_type"),
                scaling=[{k: float(v) for k, v in s.items()} for s in scaling],
                energy_cost=int(a.get("energy_cost", 0)),
                energy_gain=(int(v) if (v := a.get("energy_gain")) is not None else None),
                skill_point_cost=int(a.get("skill_point_cost", 0)),
                skill_point_gain=int(a.get("skill_point_gain", 0)),
                toughness_dmg=int(a.get("toughness_dmg", 0)),
                scaling_blast=([{k: float(v) for k, v in s.items()} for s in sb]
                               if (sb := a.get("scaling_blast")) else None),
                toughness_dmg_blast=(int(v) if (v := a.get("toughness_dmg_blast")) is not None else None),
                instances=int(a.get("instances", 1)),
                resource_gain={k: float(v) for k, v in (a.get("resource_gain") or {}).items()},
                ult_cost_resource=str(a.get("ult_cost_resource", "")),
                ult_cost_amount=float(a.get("ult_cost_amount", 0.0)),
                split=str(a.get("split", "")),
                act_now_targets=str(a.get("act_now_targets", "")),
                apply_modifiers=[dict(m) for m in a.get("apply_modifiers") or []],
                instances_from_resource=str(a.get("instances_from_resource", "")),
                instances_per_point=float(a.get("instances_per_point", 1.0)),
                instances_cap=int(a.get("instances_cap", 0)),
                consume_all_resource=str(a.get("consume_all_resource", "")),
                cleanse_self=bool(a.get("cleanse_self", False)),
            ))
        return actor, actions

    # ------------------------------------------------------------------
    # 遗器词条计算
    # ------------------------------------------------------------------

    def apply_relics(self, stats: StatBlock, relics: Dict[str, Dict[str, Any]]) -> None:
        """把遗器主/副词条累进面板（满级主词条 + roll 数 × 副词条基础值）.

        百分比词条按**基础值**（白值）乘算——hp_pct/atk_pct/def_pct = base × pct，
        其余为固定值累加（游戏公式：最终 = 白值 × (1+pct) + 固定值）。
        """
        base_hp, base_atk, base_def = stats.hp, stats.atk, stats.def_
        for _slot, relic in (relics or {}).items():
            main = relic.get("main")
            if main in _MAIN_AFFIX:
                field, val = _MAIN_AFFIX[main]
                self._add_stat(stats, field, val, base_hp, base_atk, base_def)
            for sub_id, rolls in (relic.get("subs") or {}).items():
                if sub_id in _SUB_AFFIX:
                    field, per = _SUB_AFFIX[sub_id]
                    self._add_stat(stats, field, per * float(rolls), base_hp, base_atk, base_def)

    @staticmethod
    def _add_stat(stats: StatBlock, field: str, val: float, base_hp: float, base_atk: float, base_def: float) -> None:
        if field.startswith("dmg_"):
            element = field.removeprefix("dmg_")
            stats.dmg_bonus[element] = stats.dmg_bonus.get(element, 0.0) + val
        elif field == "hp_pct":
            stats.hp += base_hp * val
        elif field == "atk_pct":
            stats.atk += base_atk * val
        elif field == "def_pct":
            stats.def_ += base_def * val
        elif field == "def_":
            stats.def_ += val
        else:
            setattr(stats, field, getattr(stats, field) + val)

    # ------------------------------------------------------------------
    # 策略
    # ------------------------------------------------------------------

    def _compile_policy(self, spec: Dict[str, Any]) -> CompiledPolicy:
        def rules_of(items: List[Dict[str, Any]], with_selector: bool) -> tuple[CompiledPolicyRule, ...]:
            out = []
            for r in items or []:
                out.append(CompiledPolicyRule(
                    action=r.get("action", ""),
                    priority=int(r.get("priority", 0)),
                    condition_expr=self.expr.try_compile(r.get("condition", "true")),
                    selector=(r.get("selector") if with_selector else None),
                    description=r.get("description", ""),
                ))
            return tuple(sorted(out, key=lambda r: -r.priority))

        return CompiledPolicy(
            name=spec.get("name", "default"),
            action_rules=rules_of(spec.get("action_rules"), with_selector=False),
            target_rules=rules_of(spec.get("target_rules"), with_selector=True),
            parameters=dict(spec.get("parameters") or {}),
            ult_timing=spec.get("ult_timing", "after_action"),
        )

    # ------------------------------------------------------------------
    # 光锥/遗器套装归并（编译期并进所属 actor 三桶，00_overview 数据流）
    # ------------------------------------------------------------------

    def _merge_light_cone(self, stats: StatBlock, spec: Dict[str, Any]) -> None:
        """light_cone_template 引用 → 白值三围归并进面板.

        机制 effects 未生成（notes 态）不结算；白值并入后 pct 族基数口径自动正确
        （游戏公式：白值 = 角色 + 光锥，mechanics 01 §1.2）。
        """
        ref = spec.get("light_cone_template")
        if not ref:
            return
        tpl = self._load_template("light_cones", str(ref))
        base = tpl.get("base_stats", {})
        stats.hp += float(base.get("hp", 0.0))
        stats.atk += float(base.get("atk", 0.0))
        stats.def_ += float(base.get("def", 0.0))

    def _merge_relic_sets(self, spec: Dict[str, Any]) -> List[Any]:
        """relics 部件的 set_id 聚合计数（15 章形状）→ 满 2/4 件触发套装效果转初始 Modifier."""
        from collections import Counter

        from hsr_nous.sim.state import Modifier

        counts: Counter = Counter(
            str(r.get("set_id")) for r in (spec.get("relics") or {}).values()
            if isinstance(r, dict) and r.get("set_id")
        )
        mods: List[Any] = []
        for set_id, n in counts.items():
            tpl = self._load_template("relics", set_id)
            for need, key in ((2, "set_2pc"), (4, "set_4pc")):
                if n < need or key not in tpl:
                    continue
                eff = (tpl[key] or {}).get("stat_effects")
                if eff:
                    mods.append(Modifier(
                        modifier_id=f"RELIC_{tpl['relic_set_id']}_{need}PC",
                        name=f"{tpl['name']} {need}pc",
                        modifier_type="buff", duration=0, dispellable=False,
                        stat_effects={k: float(v) for k, v in eff.items()},
                    ))
        return mods

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def compile(self, build: Dict[str, Any]) -> tuple[tuple[Actor, ...], Dict[str, List[Action]], CompiledPolicy, Dict[str, List[Any]], Dict[str, tuple[Any, str]], List[Any]]:
        """build.yaml 的 build 段 → (team, actions, policy, modifiers, state_configs, hooks).

        state_configs: {actor_id: (StateConfig, entry_action_id)}——模板 state_config 块；
        hooks: 模板 hooks 块的 CompiledHook 列表（机制自包含 DSL 的编译产物）.
        """
        from hsr_nous.sim.state import StateConfig

        team: List[Actor] = []
        actions_by_actor: Dict[str, List[Action]] = {}
        modifiers_by_actor: Dict[str, List[Any]] = {}
        state_configs: Dict[str, tuple[Any, str]] = {}
        resource_ids_by_actor: Dict[str, List[str]] = {}
        hooks: List[Any] = []
        for member in build.get("team", []):
            actor, actions = self._compile_inline_character(member)
            self._merge_light_cone(actor.stats, member)
            if member.get("relics"):
                self.apply_relics(actor.stats, member["relics"])
            team.append(actor)
            actions_by_actor[actor.actor_id] = actions
            mods = self._merge_relic_sets(member)
            if mods:
                modifiers_by_actor[actor.actor_id] = mods
            # 模板 state_config 块 → 引擎形态注册件
            ref = member.get("character_template")
            if ref is not None and not str(ref).startswith("inline"):
                tpl = self._load_character_template(str(ref))
                # 行迹 pct（trace_stat_effects）→ 初始 modifier（与遗器套装同通道；pct 白值口径由引擎结算）
                tse = tpl.get("trace_stat_effects")
                if tse:
                    from hsr_nous.sim.state import Modifier
                    modifiers_by_actor.setdefault(actor.actor_id, []).append(Modifier(
                        modifier_id=f"TRACE_{actor.actor_id}", name="行迹", modifier_type="buff",
                        duration=0, dispellable=False,
                        stat_effects={k: float(v) for k, v in tse.items()},
                    ))
                sc = tpl.get("state_config")
                # 模板 custom_resources 声明的资源键登记（setup 初始化缺省 0）
                cr = tpl.get("custom_resources")
                if cr:
                    resource_ids_by_actor[actor.actor_id] = [str(k) for k in cr.keys()]
                if sc:
                    state_configs[actor.actor_id] = (StateConfig(
                        state=sc["state"],
                        replaces_actions={k: ([str(x) for x in v] if isinstance(v, list) else str(v))
                                          for k, v in (sc.get("replaces_actions") or {}).items()},
                        locked_actions=[str(x) for x in sc.get("locked_actions") or []],
                        exit_conditions=[dict(c) for c in sc.get("exit_conditions") or []],
                        stat_effects={k: float(v) for k, v in (sc.get("stat_effects") or {}).items()},
                        final_action_id=str(sc.get("final_action_id", "")),
                        exit_remove_modifiers=[str(x) for x in sc.get("exit_remove_modifiers") or []],
                        banish_allies_on_enter=bool(sc.get("banish_allies_on_enter", False)),
                        countdown_spd_ratio=float(sc.get("countdown_spd_ratio", 1.0)),
                        name=str(sc.get("name", "")),
                        grants_immune=[str(x) for x in sc.get("grants_immune") or []],
                    ), str(sc.get("entry_action_id", "")))
                # 模板 hooks 块 → CompiledHook（condition 过白名单编译期校验；event 名对总线契约表）
                from hsr_nous.sim.bus import DEFAULT_CONTRACT
                from hsr_nous.sim.compile.compiled import CompiledHook
                for h in tpl.get("hooks") or []:
                    event = str(h.get("event", ""))
                    if event not in DEFAULT_CONTRACT:
                        raise ValueError(
                            f"模板 {ref} 的 hook 引用了未登记事件 {event!r}"
                            f"（契约表见 sim/bus.py DEFAULT_CONTRACT）"
                        )
                    cond_src = h.get("condition")
                    cond_expr = self.expr.compile(cond_src, layer="effect") if cond_src else None
                    hooks.append(CompiledHook(
                        owner_id=actor.actor_id,
                        event=event,
                        condition_expr=cond_expr,
                        effects=tuple(dict(e) for e in h.get("effects") or []),
                    ))
        policy = self._compile_policy(build.get("policy") or {})
        return tuple(team), actions_by_actor, policy, modifiers_by_actor, state_configs, hooks, resource_ids_by_actor
