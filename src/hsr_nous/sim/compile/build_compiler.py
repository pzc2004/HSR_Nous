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
from hsr_nous.sim_schema.effect_types import (
    EFFECT_EXPR_SLOTS,
    ENGINE_EFFECT_TYPES,
    HOOK_TARGET_SELECTORS,
)

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

# ---------------------------------------------------------------------------
# 编译期校验闸（错拼/未知键/非法枚举一律编译期炸——"LLM 写模板靠报错自愈"，静默吞=幻觉温床）
# ---------------------------------------------------------------------------

#: 糖键（04_modifier §4.12-4.14 设计预览，desugar 未接线——见 sugar.py 顶部注释）：
#: 写在 DSL 里必须炸得"认得"——报错指路"未落地"，而不是按普通未知键处理
_SUGAR_KEYS_UNWIRED = frozenset({
    "trigger_limit", "every_n", "accumulate", "tally",       # §4.12 计数器宏族
    "one_shot", "window",                                     # §4.13 攻击窗宏族
    "active_when", "scale_by", "scale_stat",                  # §4.14 门控/缩放
})

#: build.yaml team member 合法键（模板引用与 inline 共用；模板自带键不进本表——member 是作者面）
_MEMBER_KEYS = frozenset({
    "character_template", "actor_id", "name", "actor_type", "level", "eidolon",
    "skill_levels", "light_cone_template", "light_cone", "relics", "base_stats", "actions",
    "inline",  # 内联标记（inline: True，与 character_template: "inline" 同义——测试/独立场景）
})

#: base_stats 合法键（StatBlock 字段 + 三个 dict 槽；拼错如 atkk 在此炸）
_BASE_STATS_KEYS = frozenset({
    "hp", "atk", "def", "spd", "crit_rate", "crit_dmg", "break_effect",
    "effect_hit", "effect_res", "max_energy", "energy_regen", "taunt",
    "dmg_bonus", "weakness", "resistance",
})

#: action 合法键（= Action 字段的 YAML 映射；消费点见 _compile_inline_character）
_ACTION_KEYS = frozenset({
    "action_id", "name", "action_type", "target_type", "damage_type",
    "scaling", "energy_cost", "energy_gain", "energy_grant",
    "skill_point_cost", "skill_point_gain", "toughness_dmg",
    "scaling_blast", "toughness_dmg_blast", "instances",
    "resource_gain", "ult_cost_resource", "ult_cost_amount",
    "split", "act_now_targets", "apply_modifiers",
    "instances_from_resource", "instances_per_point", "instances_cap",
    "consume_all_resource", "cleanse_self", "level_key",
})

#: modifier dict 声明合法键（消费点：engine._modifier_from_spec / _attach_shield /
#: _execute_action 的 target 读取；词表按引擎实现冻结）
_MODIFIER_SPEC_KEYS = frozenset({
    "modifier_id", "name", "modifier_type", "duration", "stacks", "max_stack",
    "stack_mode", "dispellable", "stat_effects", "weakness_add", "grants_immune",
    "tick_anchor", "effect_scope", "hp_lock", "revive_percent", "moon_cocoon",
    "shield", "target",
})

#: hook 合法键（模板 hooks 块 / 秘技 hooks 共用）
_HOOK_KEYS = frozenset({"event", "condition", "effects"})

#: policy 合法键
_POLICY_KEYS = frozenset({"name", "action_rules", "target_rules", "parameters", "ult_timing"})
_POLICY_RULE_KEYS = frozenset({"condition", "action", "priority", "selector", "description"})

#: 各 effect_type 引擎消费的参数键（公共键 effect_type/target/name 之外；
#: 词表 = engine._run_hook_effect 逐分支实际读取的键，按代码现状冻结）
_EFFECT_PARAM_KEYS: Dict[str, frozenset] = {
    "cancel_event": frozenset(),
    "gain_resource": frozenset({"resource_id", "amount"}),
    "set_resource": frozenset({"resource_id", "amount"}),
    "gain_skill_point": frozenset({"amount"}),
    "gain_energy": frozenset({"amount", "err_exempt"}),
    "heal_self": frozenset({"ratio"}),
    "set_hp_to_percent": frozenset({"percent", "amount"}),
    "apply_modifier": frozenset({"modifier"}),
    "deal_damage": frozenset({"scaling_atk", "scaling_hp", "category", "damage_type"}),
    "trigger_action": frozenset({"action_id", "scaling_atk"}),
    "remove_modifier": frozenset({"modifier_id", "reason"}),
    "break_damage": frozenset({"element", "ratio"}),
    "grant_extra_turn": frozenset(),
    "delay_action": frozenset({"amount"}),
    "adjust_stacks": frozenset({"modifier_id", "delta"}),
}
_EFFECT_COMMON_KEYS = frozenset({"effect_type", "target", "name"})

# --- 枚举词表（拼错编译期炸；历史案例：ult_timing "after_actoin" 终结技永远不开零提示） ---

#: action_type 合法值（03_actor.md §3.8 枚举表）
ACTION_TYPES = frozenset({"basic", "skill", "ultimate", "follow_up", "memosprite_skill", "assist"})

#: target_type 合法值（引擎 _resolve_targets 实现集——其余写法落入默认单体=静默错，冻结拒绝；
#: 文档示例里的 enemy_single/enemy_aoe 引擎未实现，不在词表）
TARGET_TYPES = frozenset({"single", "blast", "aoe", "bounce", "self", "ally_single", "ally_aoe"})

#: ult_timing 合法值（policy_api ULT_BEFORE_ACTION/ULT_AFTER_ACTION/ULT_NEVER）
ULT_TIMINGS = frozenset({"before_action", "after_action", "never"})

#: modifier 枚举字段（引擎 stack_mode/tick_anchor/effect_scope 实现集，state.py 注释同口径）
STACK_MODES = frozenset({"refresh", "independent", "replace", "set"})
TICK_ANCHORS = frozenset({"owner_turn_end", "owner_turn_start", "on_action"})
EFFECT_SCOPES = frozenset({"self", "team"})


def _check_keys(spec: Dict[str, Any], known: frozenset, *, where: str) -> None:
    """已知键集合 diff 校验：未知键（错拼）编译期炸，报错列出非法键+合法集合."""
    for k in spec:
        if k in _SUGAR_KEYS_UNWIRED and k not in known:
            raise ValueError(
                f"{where} 使用了糖键 {k!r}——04_modifier §4.12-4.14 设计预览，"
                f"desugar 未接线（sugar.py），落地前不可在模板中使用"
            )
        if k not in known:
            raise ValueError(f"{where} 含未知键 {k!r}（合法集合：{sorted(known)}）")


def _check_enum(value: Any, legal: frozenset, *, where: str, field: str) -> None:
    if value is not None and str(value) not in legal:
        raise ValueError(
            f"{where} 的 {field} 非法值 {value!r}（合法集合：{sorted(legal)}）"
        )


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
        aid_desc = f"team member {spec.get('actor_id') or spec.get('character_template')!r}"
        # inline 角色的 hooks: 块不接线——机制自包含 DSL 只走模板文件通道
        # （data/sim_templates/characters/<id>_*.yaml 的 hooks: 块，经 character_template 引用），
        # 不许静默吞：写了就炸并指路
        if "hooks" in spec:
            raise ValueError(
                f"{aid_desc}：inline 角色不支持 hooks: 块——机制 hook 请写进角色模板文件"
                f"（data/sim_templates/characters/，经 character_template 引用编译）"
            )
        _check_keys(spec, _MEMBER_KEYS, where=aid_desc)
        ref = spec.get("character_template")
        if ref is not None and not str(ref).startswith("inline"):
            tpl = self._load_character_template(str(ref))
            # 模板提供 actor_id/name/base_stats/actions；member 提供 level/eidolon/relics 覆盖
            spec = {**tpl, **{k: v for k, v in spec.items() if k in ("level", "eidolon", "relics", "skill_levels")}}

        base = spec.get("base_stats", {})
        _check_keys(base, _BASE_STATS_KEYS, where=f"{aid_desc} base_stats")
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
            skill_levels={**{"basic": 6, "skill": 10, "ultimate": 10, "talent": 10},
                          **{k: int(v) for k, v in (spec.get("skill_levels") or {}).items()}},
        )

        actions: List[Action] = []
        for a in spec.get("actions", []):
            a_desc = f"{aid_desc} action {a.get('action_id')!r}"
            _check_keys(a, _ACTION_KEYS, where=a_desc)
            _check_enum(a.get("action_type"), ACTION_TYPES, where=a_desc, field="action_type")
            _check_enum(a.get("target_type"), TARGET_TYPES, where=a_desc, field="target_type")
            for m in a.get("apply_modifiers") or []:
                self._validate_modifier_spec(m, f"{a_desc} apply_modifiers")
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
                energy_grant=float(a.get("energy_grant", 0.0)),
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
                level_key=str(a.get("level_key", "")),  # 倍率取档键（曾静默丢失——白厄模板族）
            ))
        return actor, actions

    # ------------------------------------------------------------------
    # modifier / hook 校验（编译期闸：未知键 + 枚举 + effect_type 白名单 + 表达式预编译）
    # ------------------------------------------------------------------

    def _validate_modifier_spec(self, spec: Dict[str, Any], where: str) -> None:
        """modifier dict 声明：未知键 diff + 枚举字段校验（stack_mode/tick_anchor/effect_scope）."""
        _check_keys(spec, _MODIFIER_SPEC_KEYS, where=where)
        _check_enum(spec.get("stack_mode"), STACK_MODES, where=where, field="stack_mode")
        _check_enum(spec.get("tick_anchor"), TICK_ANCHORS, where=where, field="tick_anchor")
        _check_enum(spec.get("effect_scope"), EFFECT_SCOPES, where=where, field="effect_scope")

    def _validate_effects(self, effects: List[Dict[str, Any]], source_desc: str) -> None:
        """hook effects 编译期闸（与引擎 _run_hook_effect 同读 effect_types 单一事实源）.

        三道：effect_type 白名单（未实现=编译期炸）→ 参数键 diff（错拼静默丢的防线）
        → 表达式槽预编译（B8 同口径：condition 早有闸，effects 数值槽补齐）。
        """
        for i, eff in enumerate(effects):
            e_desc = f"{source_desc} effects[{i}]"
            t = eff.get("effect_type")
            if t not in ENGINE_EFFECT_TYPES:
                raise ValueError(
                    f"{e_desc} 未知 effect_type {t!r}（已实现集合："
                    f"{sorted(ENGINE_EFFECT_TYPES)}，见 sim_schema/effect_types.py）"
                )
            _check_keys(eff, _EFFECT_COMMON_KEYS | _EFFECT_PARAM_KEYS[t], where=e_desc)
            sel = eff.get("target")
            if sel is not None and str(sel) not in HOOK_TARGET_SELECTORS \
                    and not str(sel).startswith("$event."):
                raise ValueError(
                    f"{e_desc} 未知 target 选择器 {sel!r}（合法集合："
                    f"{sorted(HOOK_TARGET_SELECTORS)} + '$event.<字段>'）"
                )
            if t == "apply_modifier":
                self._validate_modifier_spec(
                    dict(eff.get("modifier") or {}), f"{e_desc} modifier")
            for slot in EFFECT_EXPR_SLOTS:
                v = eff.get(slot)
                if isinstance(v, str):
                    try:
                        self.expr.compile(v, layer="effect")
                    except Exception as e:
                        raise ValueError(f"{e_desc} 的 {slot} 表达式非法：{e}") from e

    def _compile_hooks(self, items: List[Dict[str, Any]], source_desc: str,
                       owner_id: str, out: List[Any]) -> None:
        """模板/秘技 hooks 块 → CompiledHook 追加进 out.

        编译期闸：hook 键 diff → event 对总线契约表（bus.py DEFAULT_CONTRACT）
        → condition 白名单预编译 → effects 三道（_validate_effects）。
        """
        from hsr_nous.sim.bus import DEFAULT_CONTRACT
        from hsr_nous.sim.compile.compiled import CompiledHook

        for h in items:
            _check_keys(h, _HOOK_KEYS, where=f"{source_desc} 的 hook")
            event = str(h.get("event", ""))
            if event not in DEFAULT_CONTRACT:
                raise ValueError(
                    f"{source_desc} 的 hook 引用了未登记事件 {event!r}"
                    f"（契约表见 sim/bus.py DEFAULT_CONTRACT）"
                )
            effects = [dict(x) for x in h.get("effects") or []]
            self._validate_effects(effects, f"{source_desc} hook({event})")
            cond_src = h.get("condition")
            out.append(CompiledHook(
                owner_id=owner_id,
                event=event,
                condition_expr=self.expr.compile(cond_src, layer="effect") if cond_src else None,
                effects=tuple(effects),
            ))

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
        _check_keys(spec, _POLICY_KEYS, where="policy")
        _check_enum(spec.get("ult_timing"), ULT_TIMINGS, where="policy", field="ult_timing")

        def rules_of(items: List[Dict[str, Any]], with_selector: bool, kind: str) -> tuple[CompiledPolicyRule, ...]:
            out = []
            for r in items or []:
                _check_keys(r, _POLICY_RULE_KEYS, where=f"policy {kind}")
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
            action_rules=rules_of(spec.get("action_rules"), with_selector=False, kind="action_rules"),
            target_rules=rules_of(spec.get("target_rules"), with_selector=True, kind="target_rules"),
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
        from hsr_nous.sim.state import Modifier, StateConfig

        team: List[Actor] = []
        actions_by_actor: Dict[str, List[Action]] = {}
        modifiers_by_actor: Dict[str, List[Any]] = {}
        state_configs: Dict[str, tuple[Any, str]] = {}
        resource_ids_by_actor: Dict[str, List[str]] = {}
        hooks: List[Any] = []
        techniques_by_actor: Dict[str, List[Dict[str, Any]]] = {}
        tp_bonus = 0
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
                # 模板 techniques / team_modifiers 登记（战前秘技池与秘技表）
                if tpl.get("techniques"):
                    techniques_by_actor[actor.actor_id] = [dict(t) for t in tpl["techniques"]]
                tm = tpl.get("team_modifiers")
                if tm:
                    tp_bonus += int(tm.get("technique_point_initial_bonus", 0) or 0)
                # 模板 hooks 块 → CompiledHook（编译期闸全家：键 diff/事件契约/condition+effects 预编译）
                self._compile_hooks(tpl.get("hooks") or [], f"模板 {ref}", actor.actor_id, hooks)

                # 星魂激活：member.eidolon: N → 模板 eidolons E1..EN 生效
                from dataclasses import replace as _dc_replace
                eidolon_n = int(member.get("eidolon", 0) or 0)
                eidolons = tpl.get("eidolons") or {}
                for rank in range(1, min(max(eidolon_n, 0), 6) + 1):
                    e = eidolons.get(f"E{rank}")
                    if not e:
                        continue
                    se = e.get("stat_effects")
                    if se:
                        modifiers_by_actor.setdefault(actor.actor_id, []).append(Modifier(
                            modifier_id=f"EIDO_{actor.actor_id}_E{rank}",
                            name=str(e.get("name", f"E{rank}")), modifier_type="buff",
                            duration=0, dispellable=False,
                            stat_effects={k: float(v) for k, v in se.items()},
                        ))
                    slo = e.get("skill_level_overrides")
                    if slo:
                        for k, v in slo.items():
                            cap = 10 if k == "basic" else 15
                            actor.skill_levels[k] = min(cap, actor.skill_levels.get(k, 10) + int(v))
                    ov = e.get("overrides")
                    if ov and actor.actor_id in state_configs:
                        cfg, entry = state_configs[actor.actor_id]
                        state_configs[actor.actor_id] = (
                            _dc_replace(cfg, **{k: v for k, v in ov.items()}), entry)
                    self._compile_hooks(e.get("hooks") or [], f"模板 {ref} 星魂 E{rank}",
                                        actor.actor_id, hooks)
        policy = self._compile_policy(build.get("policy") or {})

        # 战前秘技：池校验（默认 5 + Σ bonus）→ 选中秘技 effects 注入 hooks 开头（装填预置先于一切 hook）
        pre_battle = build.get("pre_battle") or []
        if pre_battle:
            from hsr_nous.sim.compile.compiled import CompiledHook
            tp_pool = 5 + tp_bonus
            spent = 0
            pre_hooks: List[Any] = []
            for use in pre_battle:
                aid = str(use.get("actor_id", ""))
                tid = str(use.get("technique", ""))
                tdef = next((t for t in techniques_by_actor.get(aid, [])
                             if str(t.get("technique_id")) == tid), None)
                if tdef is None:
                    raise ValueError(f"pre_battle 引用不存在的秘技：{aid}/{tid}")
                spent += int(tdef.get("point_cost", 0))
                if spent > tp_pool:
                    raise ValueError(
                        f"秘技点超支：累计 {spent} > 池 {tp_pool}（默认 5 + 队伍加成 {tp_bonus}）"
                    )
                # 进战一次性 effects → on_battle_start hook（装填预置；effects 过同一编译期闸）
                one_shot = [dict(e) for e in tdef.get("effects") or []]
                self._validate_effects(one_shot, f"秘技 {aid}/{tid}")
                pre_hooks.append(CompiledHook(
                    owner_id=aid, event="on_battle_start", condition_expr=None,
                    effects=tuple(one_shot),
                ))
                # 常驻 hooks（如每波次伤害）→ 同模板 hooks 编译通道
                self._compile_hooks(tdef.get("hooks") or [], f"秘技 {aid}/{tid}", aid, pre_hooks)
            hooks = pre_hooks + hooks  # 装填预置先于模板 hooks

        return tuple(team), actions_by_actor, policy, modifiers_by_actor, state_configs, hooks, resource_ids_by_actor
