"""结算管线：两层求值 → effect 原语执行 → 伤害公式（节点值树输出）.

v0.1 范围：两层求值 + deal_damage 全公式链 + heal + gain/consume(能量)。
每次结算输出 (value, 节点值树)——Evaluator 的显微镜，也是对拍的对齐粒度。

公式锚点：01_formula.md 十二乘区 + base_dmg_add 基数区（决策卡 #17）；
mechanics/02_damage_formula.md 镜像。

公式执行形态（B27 迁移）：公式链零 Python 算术——全部表达式来自 rulebook
（`sim_schema/rulebook.yaml`，01_formula 的可执行唯一来源），绑定期白名单
预编译，此处只带 context 求值（决策卡 A1：引擎零数值常数）。
"""
from __future__ import annotations

import random
import types
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim.state import ActorState
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.expression import EvalOutcome, evaluate
from hsr_nous.sim_schema.rulebook import get_rulebook

# 随机模式
MODE_EXPECTED = "expected"  # 期望值模式（不掷骰，对拍校准用）
MODE_ROLL = "roll"          # 掷骰模式（方差研究主力；种子进配置）

# pct 族 stat → 白值字段（modifier "atk_pct: 0.12" = 白值攻击 ×12%；flat 不吃百分比，游戏公式口径）
_PCT_BASE = {"atk_pct": "atk", "def_pct": "def_", "hp_pct": "hp", "spd_pct": "spd"}


@dataclass
class SettleResult:
    """结算结果：值 + 节点值树（每次结算的对拍对齐粒度）."""

    value: float
    node: Dict[str, Any] = field(default_factory=dict)


class SettlementPipeline:
    """结算管线（v0.1：直伤闭环）."""

    def __init__(self, mode: str = MODE_ROLL, seed: Optional[int] = None, expr: Any = None) -> None:
        assert mode in (MODE_EXPECTED, MODE_ROLL)
        self.mode = mode
        # 掷骰为默认模式（真暴击判定）；随机性种子化——缺省固定种子 0 保证可复现
        self.rng = random.Random(seed if seed is not None else 0)
        self._expr = expr  # ExprCompiler（scoped hit_condition 求值用；None 时 scoped 加成不生效）
        self._aura_provider: Optional[Any] = None  # 光环提供者（engine 注入：fn(ActorState) -> List[Modifier]，scope=team 光环辐射）
        # 条件光环运行时（04_modifier §4.16，engine 注入）：
        # fn(target_state, mod, panel_of) -> (ctx, functions)——enable_if/stat_exprs 求值语境
        # （panel_of = 无条件件面板读取，条件域防环钉）；未注入时条件件一律不生效
        self._cond_runtime: Optional[Any] = None
        self._cond_warn: Optional[Any] = None  # fn(str)——求值失败 ⚠ 留痕（B8 同口径）
        self._rb = get_rulebook()  # 公式簿（绑定期已预编译；此处只取句柄）

    def set_aura_provider(self, fn: Any) -> None:
        """注册光环提供者（engine 注入）：fn(ActorState) -> List[Modifier]（全队 scope=team 光环）."""
        self._aura_provider = fn

    def set_condition_runtime(self, runtime_fn: Any, warn_fn: Any) -> None:
        """注册条件光环运行时（engine 注入）：enable_if/stat_exprs 的语境工厂 + 告警槽."""
        self._cond_runtime = runtime_fn
        self._cond_warn = warn_fn

    # ------------------------------------------------------------------
    # rulebook 求值（热循环：预编译 AST + context）
    # ------------------------------------------------------------------

    def _zone(self, name: str, ctx: Dict[str, Any]) -> float:
        """乘区求值：rulebook 表达式 + 本结算 context（trace=False 快路径：不建节点值树）."""
        return evaluate(self._rb.zones[name], context=ctx, rng=self.rng, trace=False).value

    def _zone_outcome(self, name: str, ctx: Dict[str, Any]) -> EvalOutcome:
        """带节点值树的乘区求值（暴击判定等需要读 trace 中间值时用）."""
        return evaluate(self._rb.zones[name], context=ctx, rng=self.rng)

    def _formula(self, category: str, ctx: Dict[str, Any]) -> float:
        """顶层公式求值：伤害类别经 route 表映射到本模式的公式键."""
        key = self._rb.route[category][self.mode]
        return evaluate(self._rb.formulas[key], context=ctx, rng=self.rng).value

    # ------------------------------------------------------------------
    # 两层属性求值（§4.10：Layer 1 白值+flat → Layer 2 转化/覆写）
    # ------------------------------------------------------------------

    def effective_stats(self, actor_state: ActorState, *, _skip_cond: bool = False) -> Dict[str, Any]:
        """有效面板 = Layer 1（base + Σ modifier flat）→ Layer 2（转化 → 覆写）.

        防二次转化循环：转化读取的是 source 的 Layer 1，不读 effective。
        光环（scope=team）：provider 提供的全队光环 stat_effects 并入 Layer 1
        （pct 族按目标白值乘算，与 Layer 1.5 同口径）。
        条件光环（04_modifier §4.16）：enable_if/stat_exprs 件先按**无条件件面板**
        求门控与档位，通过的才并入（重估时机=面板读取即重估，懒求值零 stale）；
        `_skip_cond=True` = 无条件件面板通道——条件域一切面板读取走此（构造防环）。
        """
        held = list(actor_state.modifiers.values())
        if self._aura_provider is not None:
            held = held + list(self._aura_provider(actor_state))
        cond_ids = {id(m) for m in held if m.enable_if_expr is not None or m.stat_exprs}
        if _skip_cond or not cond_ids or self._cond_runtime is None:
            if _skip_cond and cond_ids:
                held = [m for m in held if id(m) not in cond_ids]
            return self._compute(actor_state, held, ())

        panel_cache: Dict[int, Dict[str, Any]] = {}

        def panel_of(st: ActorState) -> Dict[str, Any]:
            # 无条件件面板（同批求值共享缓存——条件件彼此不可互观察，04_modifier §4.16）
            if id(st) not in panel_cache:
                panel_cache[id(st)] = self.effective_stats(st, _skip_cond=True)
            return panel_cache[id(st)]

        active = [m for m in held if id(m) not in cond_ids]
        extra: List[tuple] = []
        for m in (m for m in held if id(m) in cond_ids):
            try:
                ctx, functions = self._cond_runtime(actor_state, m, panel_of)
                ok = True
                if m.enable_if_expr is not None:
                    ok = bool(evaluate(m.enable_if_expr, context=ctx,
                                       functions=functions, trace=False).value)
                if not ok:
                    continue
                active.append(m)
                for stat, expr in m.stat_exprs.items():
                    val = float(evaluate(expr, context=ctx, functions=functions,
                                         trace=False).value)
                    extra.append((stat, val))
            except Exception as e:
                # B8 同口径：求值失败按不生效 + ⚠ 留痕（编译期预编译闸已拦语法错）
                if self._cond_warn is not None:
                    self._cond_warn(f"⚠ 条件光环 {m.modifier_id} 求值失败按不生效处理：{e!r}")
        return self._compute(actor_state, active, extra)

    def modifier_enabled(self, actor_state: ActorState, m: Any) -> bool:
        """条件件启用判定（enable_if 现场求值）——stat 贡献外的即时判定通道复用
        （grants_immune 族：条件免疫随 enable_if 开关，未启用=不在场，青镞冷却闩
        首实例）；无 enable_if / 无 cond 运行时 = 恒启用；求值失败按不生效（B8 同口径）.
        """
        if m.enable_if_expr is None or self._cond_runtime is None:
            return True
        try:
            ctx, functions = self._cond_runtime(
                actor_state, m, lambda st: self.effective_stats(st, _skip_cond=True))
            return bool(evaluate(m.enable_if_expr, context=ctx,
                                 functions=functions, trace=False).value)
        except Exception:
            return False

    def _compute(self, actor_state: ActorState, held: List[Any],
                 extra: List[tuple]) -> Dict[str, Any]:
        """面板求值本体：held = 生效 modifier 列表（含光环件）；extra = stat_exprs 现场求值产物."""
        st = actor_state.actor.stats
        l1: Dict[str, Any] = {
            "hp": st.hp, "atk": st.atk, "def_": st.def_, "spd": st.spd,
            "crit_rate": st.crit_rate, "crit_dmg": st.crit_dmg,
            "def_pen": st.def_pen, "res_pen": st.res_pen,
            "vulnerability": st.vulnerability,
            "energy_regen": st.energy_regen,
            "break_effect": st.break_effect,
            "elation": st.elation,   # 欢愉度（B40——21_elation §21.1，elation_multi=1+elation）
            "break_efficiency_boost": st.break_efficiency_boost,
            "weakness_break_efficiency_boost": st.weakness_break_efficiency_boost,
            "effect_hit": st.effect_hit, "effect_res": st.effect_res,
            "taunt": self._base_taunt(actor_state.actor),
            "heal_bonus": st.heal_bonus, "shield_bonus": st.shield_bonus,
            "dmg_bonus": dict(st.dmg_bonus),
            # max_toughness（B38 补口——云火昭「各自韧性上限×比例」族 $target.max_toughness
            # 消费端；编译白名单 _SELF_NS_FIELDS 早已放行，此前无消费端未暴露 L1 缺键）
            "max_toughness": st.max_toughness,
        }
        # Layer 1：modifier flat 贡献（scoped 件跳过——它们的加成在命中域按条件计）
        # pct 族（atk_pct/def_pct/hp_pct/spd_pct）不进 l1 加算——它们的基数是**白值**（st.*），
        # 单独汇总后在 Layer 1.5 应用（游戏公式：面板 = 白值×(1+Σpct) + Σflat，flat 不吃百分比）
        pct_pool: Dict[str, float] = {}

        def _fold(stat: str, val: float) -> None:
            if stat in _PCT_BASE:
                pct_pool[stat] = pct_pool.get(stat, 0.0) + val
            else:
                self._add_eff(l1, stat, val)

        for mod in held:
            if mod.hit_condition_expr is not None:
                continue
            for stat, val in mod.stat_effects.items():
                _fold(stat, val)
        for stat, val in extra:
            _fold(stat, val)

        out = dict(l1)
        out["dmg_bonus"] = dict(l1["dmg_bonus"])
        # Layer 1.5：pct 族 = 白值 × (1+Σpct) + flat（l1 已含 flat，故 out = l1 + 白值×Σpct——
        # 合成式唯一来源 rulebook zones.stat_with_pct，01_formula §1.12 镜像，逐比特同旧 Python 拼接）
        for stat, pct in pct_pool.items():
            base_stat = _PCT_BASE[stat]
            out[base_stat] = self._zone("stat_with_pct", {
                "l1": out.get(base_stat, 0.0), "base": getattr(st, base_stat), "pct": pct})
        # Layer 2a/2b（转化/覆写）只扫**自身持有**的生效件——scope=team 光环的
        # scaling/override 不辐射（与旧口径逐比特一致；flat 才走光环辐射）
        own_ids = {id(m) for m in actor_state.modifiers.values()}
        # Layer 2a：转化（scaling_effects：stat += source_L1 × ratio）
        for mod in held:
            if id(mod) not in own_ids:
                continue
            for stat, (src, ratio) in mod.scaling_effects.items():
                if src in l1:
                    out[stat] = out.get(stat, 0.0) + l1[src] * ratio
        # Layer 2b：覆写（override_effects：stat = value）
        for mod in held:
            if id(mod) not in own_ids:
                continue
            for stat, val in mod.override_effects.items():
                out[stat] = val
        # 嘲讽派生（mechanics 10）：taunt_eff = base × (1 + Σ aggro_boost 池)（rulebook zones 求值）
        out["taunt_eff"] = self._zone("taunt_eff", {
            "taunt": out["taunt"], "aggro_boost": out.get("aggro_boost", 0.0)})
        return out

    def _base_taunt(self, actor: Any) -> float:
        """基础嘲讽解析：显式 stats.taunt > 0 优先；忆灵查 memosprite_base（按名）；
        否则按命途查 path_base；兜底 100（mechanics 10_taunt_system.md，rulebook taunt 节）."""
        st = actor.stats
        if st.taunt > 0:
            return st.taunt
        tables = self._rb.taunt
        if actor.summoner_id:
            memo = tables.get("memosprite_base", {})
            if actor.name in memo:
                return float(memo[actor.name])
        path_base = tables.get("path_base", {})
        if actor.path and actor.path in path_base:
            return float(path_base[actor.path])
        return 100.0

    @staticmethod
    def _add_eff(eff: Dict[str, Any], stat: str, val: float) -> None:
        if stat.startswith("dmg_"):
            element = stat.removeprefix("dmg_")
            if element == "dmg_reduction":
                # 减伤堆叠乘算（rulebook zones.dmg_red_multi 注释口径：dmg_reduction
                # 已预计算为乘积结果 ∏(1-x_i)——多件按 1-∏(1-x_i) 折叠进桶，
                # 曾按加算堆叠（克拉拉天赋+终结技 0.35 vs 乘算 0.325，1107 过堂钓出）
                cur = eff["dmg_bonus"].get(element, 0.0)
                eff["dmg_bonus"][element] = 1.0 - (1.0 - cur) * (1.0 - val)
            else:
                eff["dmg_bonus"][element] = eff["dmg_bonus"].get(element, 0.0) + val
        elif stat == "all_dmg":
            eff["dmg_bonus"]["all"] = eff["dmg_bonus"].get("all", 0.0) + val
        else:
            eff[stat] = eff.get(stat, 0.0) + val

    def _as_state(self, x: Any) -> ActorState:
        """兼容入口：Actor → 裸 ActorState（无 modifier）."""
        if isinstance(x, ActorState):
            return x
        return ActorState(actor=x, current_hp=x.stats.hp, current_energy=0.0)

    # ------------------------------------------------------------------
    # 伤害公式（十二乘区 + base_dmg_add；有效面板驱动）
    # ------------------------------------------------------------------

    def _ability_multi_eff(self, action: Action, se: Dict[str, Any], level: int) -> float:
        """技能基数区：rulebook zones.ability_base 求值（倍率×基础属性求和；逐比特同旧 Python 拼接）."""
        if not action.scaling:
            return 0.0
        idx = min(max(level - 1, 0), len(action.scaling) - 1)
        s = action.scaling[idx]
        return self._zone("ability_base", {
            "atk_scaling": s.get("atk", 0.0),
            "hp_scaling": s.get("hp", 0.0),
            "def_scaling": s.get("def_", s.get("def", 0.0)),
            "atk": se["atk"], "hp": se["hp"], "def_": se["def_"],
        })

    def _dmg_boost_eff(self, action: Action, se: Dict[str, Any]) -> float:
        """增伤乘区：三个 dmg_bonus 桶的命中解析（引擎侧语义）+ rulebook 表达式求值."""
        b = se["dmg_bonus"]
        return self._zone("dmg_boost_multi", {
            "all_dmg_bonus": b.get("all", 0.0),
            "elemental_dmg_bonus": b.get(action.damage_type, 0.0) if action.damage_type else 0.0,
            "type_dmg_bonus": b.get(f"{action.action_type}_dmg_boost", 0.0),
        })

    def _scoped_boost(self, source: ActorState, event_ctx: Dict[str, Any],
                      accept: Any) -> float:
        """hit_condition scoped 加成：命中域条件命中才计入（04_modifier §hit_condition 组合原语）.

        命中域 `$event` 命名空间按结算类型由调用方注入（伤害：action_type/damage_type/
        target_broken/target_controlled；治疗：target_hp_ratio）；`accept(stat)` 判定该
        结算类型计入哪些 stat（伤害 = dmg_*/all_dmg；治疗 = heal_bonus）。
        只扫携带者自身持有件（scope=team 光环不辐射——全队族双件各挂）；求值失败静默不计。
        """
        total = 0.0
        ctx = {"event": types.SimpleNamespace(**event_ctx)}
        for mod in source.modifiers.values():
            if mod.hit_condition_expr is None:
                continue
            ok = False
            try:
                ok = bool(self.expr_evaluate(mod.hit_condition_expr, ctx))
            except Exception:
                ok = False
            if ok:
                for stat, val in mod.stat_effects.items():
                    if accept(stat):
                        total += val
        return total

    def expr_evaluate(self, prepared: Any, ctx: Dict[str, Any]) -> Any:
        """白名单表达式求值（经 expression.py；未接编译器时退化为 False）."""
        if self._expr is None:
            return False
        return self._expr.evaluate(prepared, ctx, self.rng)

    def _def_multi_eff(self, source_level: int, se: Dict[str, Any], te: Dict[str, Any], tgt_state: ActorState) -> float:
        """防御乘区：目标防御解析（覆写优先/白板兜底）+ rulebook 表达式求值."""
        # 覆写优先：有 modifier 把 def_ 覆写为 0 时按字面（真·零防）
        has_def_override = any("def_" in m.override_effects for m in tgt_state.modifiers.values())
        if te["def_"] > 0 or has_def_override:
            enemy_def = te["def_"]
        else:
            enemy_def = self._rb.constants["default_target_def"]  # 白板假人的防御兜底（旧 golden 基准）
        return self._zone("def_multi", {
            "attacker_level": source_level,
            "target_def": enemy_def,
            "def_pen": se["def_pen"],
        })

    def effective_weakness(self, target: ActorState) -> set:
        """有效弱点 = 面板弱点 ∪ 挂身 modifier 的 weakness_add（弱点植入 debuff 族）."""
        w = set(target.actor.stats.weakness)
        for m in target.modifiers.values():
            w |= set(m.weakness_add)
        return w

    def _base_res(self, dmg_type: Optional[str], target: ActorState) -> float:
        """基础抗性解析（引擎侧语义）：弱点 0 / 面板抗性 / 非弱点默认抗性."""
        if dmg_type and dmg_type in self.effective_weakness(target):
            return 0.0
        if dmg_type in target.actor.stats.resistance:
            return target.actor.stats.resistance[dmg_type]
        return self._rb.constants["non_weakness_res"]

    def _res_multi_eff(self, action: Action, se: Dict[str, Any], target: ActorState) -> float:
        return self._zone("res_multi", {
            "target_res": self._base_res(action.damage_type, target),
            "res_pen": se["res_pen"],
        })

    def _res_multi_for_eff(self, dmg_type: str, se: Dict[str, Any], target: ActorState) -> float:
        return self._zone("res_multi", {
            "target_res": self._base_res(dmg_type, target),
            "res_pen": se["res_pen"],
        })

    def _crit_eff(self, se: Dict[str, Any]) -> tuple[float, bool]:
        """暴击乘区：期望模式走 crit_expected_multi；掷骰模式走 crit_multi（isCrit 读判定 trace）."""
        ctx = {"crit_rate": se["crit_rate"], "crit_dmg": se["crit_dmg"]}
        if self.mode == MODE_EXPECTED:
            return self._zone("crit_expected_multi", ctx), False
        outcome = self._zone_outcome("crit_multi", ctx)
        # isCrit = 三元判定条件（Compare 节点）的求值结果，与掷骰同源
        trace = outcome.trace
        is_crit = bool(trace["children"][0]["value"]) if trace.get("kind") == "IfExp" else outcome.value != 1.0
        return outcome.value, is_crit

    def deal_damage(
        self,
        action: Action,
        source: Any,
        target: Any,
        *,
        skill_level: int = 1,
        target_broken: bool = False,
        base_override: Optional[float] = None,
    ) -> SettleResult:
        """单次直伤结算（全公式链 + 节点值树；有效面板 + scoped 加成）.

        公式链 = rulebook 表达式求值（route["direct"] → damage / damage_expected）；
        本方法只做面板→context 的喂入与节点值树拼装，零公式算术。
        base_override：非 None 时 ability_multiplier 直写本值（基数区不走倍率×面板——
        hook deal_damage `amount` 通道：tally×比例族"资源值即基数"，01_formula §1.1
        ability_multiplier source 注"由 effect 的 amount 表达式喂入"）。
        """
        src = self._as_state(source)
        tgt = self._as_state(target)
        se = self.effective_stats(src)
        te = self.effective_stats(tgt)

        ability = (float(base_override) if base_override is not None
                   else self._ability_multi_eff(action, se, skill_level))
        dmg_boost = self._dmg_boost_eff(action, se) + self._scoped_boost(
            src,
            {"action_type": action.action_type, "damage_type": action.damage_type,
             "target_broken": tgt.broken,
             "target_controlled": any(m.control_kind for m in tgt.modifiers.values())},
            lambda s: s.startswith("dmg_") or s == "all_dmg")
        ind_dmg_boost = self._zone("ind_dmg_boost_multi", {
            "ind_dmg_bonus": se["dmg_bonus"].get("ind_dmg_boost", 0.0)})
        def_multi = self._def_multi_eff(src.actor.level, se, te, tgt)
        # 抗性区 scoped 补口（2026-09-14 承伤三区通用化②）：hit_condition 件的 res_pen
        # 同命中域计入——类型限定穿透（飞霄 1220 E6「终结技伤害全抗性穿透」首实例）；
        # 携带者=攻击侧。击破结算同形不补（击破 action_type 非 ultimate 自然出集）
        res_multi = self._zone("res_multi", {
            "target_res": self._base_res(action.damage_type, tgt),
            "res_pen": se["res_pen"] + self._scoped_boost(
                src,
                {"action_type": action.action_type, "damage_type": action.damage_type,
                 "target_broken": tgt.broken,
                 "target_controlled": any(m.control_kind for m in tgt.modifiers.values())},
                lambda s: s == "res_pen")})
        # 韧性状态喂入：broken 旗标为准（虚韧性条期间 toughness>0 仍是击破态——
        # 忘归人 122504；spec 表达式同口径，见 01_formula base_universal_multi）
        base_universal = self._zone("base_universal_multi", {
            "target_broken": 1.0 if (target_broken or tgt.broken) else 0.0})
        # 承伤区 scoped 补口（2026-09-14）：hit_condition 件的 vulnerability/ind_vulnerability
        # 同命中域计入——旧缺口：scoped_boost 只服务增伤区/治疗区，类型限定承伤（椒丘 1218
        # 结界「终结技伤害易伤」首实例）永不被读；携带者=目标侧（承伤件挂敌方）。
        # 击破结算同形不补：击破 action_type 非 ultimate 族，命中域自然出集
        scoped_vuln = self._scoped_boost(
            tgt,
            {"action_type": action.action_type, "damage_type": action.damage_type,
             "target_broken": tgt.broken,
             "target_controlled": any(m.control_kind for m in tgt.modifiers.values())},
            lambda s: s in ("vulnerability", "ind_vulnerability"))
        vuln = self._zone("vuln_multi", {"vulnerability": te["vulnerability"] + scoped_vuln})
        ind_vuln = self._zone("ind_vuln_multi", {
            "ind_vulnerability": te["dmg_bonus"].get("ind_vulnerability", 0.0)})
        final_dmg = self._zone("final_dmg_multi", {
            "final_dmg_bonus": se["dmg_bonus"].get("final_dmg_boost", 0.0)})
        crit_multi, is_crit = self._crit_eff(se)
        weaken = self._zone("weaken_multi", {"weaken": te["dmg_bonus"].get("weaken", 0.0)})
        dmg_red = self._zone("dmg_red_multi", {
            "dmg_reduction": te["dmg_bonus"].get("dmg_reduction", 0.0)})

        value = self._formula("direct", {
            "ability_multiplier": ability,
            "dmg_boost_multi": dmg_boost,
            "ind_dmg_boost_multi": ind_dmg_boost,
            "def_multi": def_multi,
            "res_multi": res_multi,
            "base_universal_multi": base_universal,
            "vuln_multi": vuln,
            "ind_vuln_multi": ind_vuln,
            "final_dmg_multi": final_dmg,
            # 两种模式的公式各引用其一，同值并喂无害
            "crit_multi": crit_multi,
            "crit_expected_multi": crit_multi,
            "weaken_multi": weaken,
            "dmg_red_multi": dmg_red,
        })
        return SettleResult(
            value=value,
            node={
                "formula": "damage",
                "abilityMulti": ability,
                "dmgBoostMulti": dmg_boost,
                "indDmgBoostMulti": ind_dmg_boost,
                "defMulti": def_multi,
                "resMulti": res_multi,
                "baseUniversalMulti": base_universal,
                "vulnMulti": vuln,
                "indVulnMulti": ind_vuln,
                "finalDmgMulti": final_dmg,
                "critMulti": crit_multi,
                "isCrit": is_crit,
                "weakenMulti": weaken,
                "dmgRedMulti": dmg_red,
            },
        )

    # ------------------------------------------------------------------
    # 真实伤害（rulebook true_damage 式——route["true"]；01_formula §1.3 / mechanics 02 §2.8）
    # ------------------------------------------------------------------

    def deal_true_damage(
        self,
        source: Any,
        target: Any,
        *,
        fixed_value: float,
        true_dmg_rate: float = 1.0,
    ) -> SettleResult:
        """真实伤害结算：fixed_value × true_dmg_rate × true_dmg_multi.

        常规乘区（防御/抗性/增伤/暴击/易伤/减伤/虚弱）全不命中；护盾吸收层由调用方同走
        （mechanics 02 §2.8"会被护盾抵挡"）。true_dmg_modifier 走 dmg_bonus 桶
        "true_dmg_boost"（词表登记——现无实例源，中性 0）；hit 级修正无通道，中性 0。
        """
        src = self._as_state(source)
        se = self.effective_stats(src)
        multi = self._zone("true_dmg_multi", {
            "true_dmg_modifier": se["dmg_bonus"].get("true_dmg_boost", 0.0),
            "hit_true_dmg_modifier": 0.0,
        })
        value = self._formula("true", {
            "fixed_value": float(fixed_value),
            "true_dmg_rate": float(true_dmg_rate),
            "true_dmg_multi": multi,
        })
        return SettleResult(
            value=value,
            node={
                "formula": "true_damage",
                "fixedValue": float(fixed_value),
                "trueDmgRate": float(true_dmg_rate),
                "trueDmgMulti": multi,
                "isCrit": False,
            },
        )

    # ------------------------------------------------------------------
    # 效果命中判定（§4.7：debuff/dot/control 施加前概率闸）
    # ------------------------------------------------------------------

    def hit_chance(
        self,
        source_eff: Dict[str, Any],
        target_eff: Dict[str, Any],
        base_chance: float,
        effect_res_pen: float = 0.0,
    ) -> float:
        """命中概率：rulebook `ehr_multi` 表达式求值（01_formula dot_damage parameters 同式）.

        = min(1, base × (1+效果命中) × (1 − 目标效果抵抗 + 效果抵抗穿透) × (1 − 类型抵抗)).
        effect_res_pen：效果抵抗穿透（独立参数槽——modifier 面板经调用方 se.get("effect_res_pen") 喂入）.
        类型抵抗（type_res）：公式乘区保留，无实例源——中性 0 喂入（不新造机制）。
        """
        return self._zone("ehr_multi", {
            "base_chance": base_chance,
            "effect_hit": source_eff.get("effect_hit", 0.0),
            "target_effect_res": target_eff.get("effect_res", 0.0),
            "effect_res_pen": effect_res_pen,
            "type_res": 0.0,
        })

    def roll_debuff_apply(self, chance: float) -> bool:
        """debuff 施加判定：掷骰模式真判定；期望模式按 ≥0.5 生效（记录概率）."""
        if self.mode == MODE_EXPECTED:
            return chance >= 0.5
        return self.rng.random() < chance

    def mechanic_chance(self, p: float) -> bool:
        """机制概率判定（可变概率变量通道 v1——银狼 LV.999 Top Loot Box 族）：

        概率载体 = 自定义资源（0-1 小数），本方法只裁判——roll 模式 zagreus 真掷
        （同 seed 复现）、expected 模式按 ≥0.5 生效（与 roll_debuff_apply 同一期望口径，
        两通道不许出现两种期望语义）。
        """
        if self.mode == MODE_EXPECTED:
            return float(p) >= 0.5
        return self.rng.random() < float(p)

    # ------------------------------------------------------------------
    # 其余原语（v0.1：heal / 能量 gain-consume）
    # ------------------------------------------------------------------

    def heal(self, source: Any, target: ActorState, amount: float = 0.0, *,
             atk_scaling: float = 0.0, hp_scaling: float = 0.0) -> SettleResult:
        """治疗结算：rulebook `heal` 公式唯一路径（mechanics 01 §1.3）.

        治疗量 = (atk_scaling×atk + hp_scaling×hp + flat_heal) × (1 + heal_bonus + incoming_heal)
        - atk/hp：施放者有效面板（治疗倍率按施放者属性缩放）
        - heal_bonus（Outgoing_Healing_Boost）：**施放者** effective_stats，外加命中域条件件
          （hit_condition）现场并入——治疗命中域 `$event.target_hp_ratio` = 受疗者当前 HP /
          有效生命上限（治疗前；04_modifier §hit_condition 治疗命中域，1409 阴云莞尔族）
        - incoming_heal（受治疗量变化——加成为正、降低为负，如萨姆领域）：**受疗者** effective_stats
        封顶 = 受疗者有效生命上限（与 engine heal_self/复活同口径）。
        事件（on_hp_increase）由调用方（引擎侧）发射——pipeline 纯结算不持 bus。
        """
        src = self._as_state(source)
        tgt = self._as_state(target)
        se = self.effective_stats(src)
        te = self.effective_stats(tgt)
        heal_bonus = se.get("heal_bonus", 0.0) + self._scoped_boost(
            src, {"target_hp_ratio": tgt.current_hp / te["hp"] if te["hp"] > 0 else 0.0},
            lambda s: s == "heal_bonus")
        incoming_heal = te.get("incoming_heal", 0.0)
        outcome = evaluate(self._rb.formulas["heal"], context={
            "atk_scaling": atk_scaling, "atk": se["atk"],
            "hp_scaling": hp_scaling, "hp": se["hp"],
            "flat_heal": amount,
            "heal_bonus": heal_bonus,
            "incoming_heal": incoming_heal,
        }, rng=self.rng)
        value = outcome.value
        # healBonusMulti 从公式 trace 中间节点取（(基数) * (1+加成) 根节点的右子树）——展示层不抄公式
        heal_multi = outcome.trace["children"][1]["value"]
        old = tgt.current_hp
        # 封顶 = 受疗者有效生命上限；**超上限目标治疗不压血**（忆灵/召唤物 HP 继承口径
        # 可超 effective 上限——min 下钳会把 HP 压回上限=治疗变扣血：actual 取 max(0, …)，
        # 超出部分全计溢出 excess；昔涟 1415 德谬歌/小伊卡组 e2e 钓出）
        new = min(te["hp"], old + value)
        actual = max(0.0, new - old)
        tgt.current_hp = max(old, new)
        return SettleResult(value=value, node={
            "formula": "heal", "amount": amount,
            "healBonusMulti": heal_multi,
            "actualAmount": actual,
        })

    def gain_energy(self, target: ActorState, amount: float, *, err_exempt: bool = False) -> SettleResult:
        """回能：rulebook `gain_energy` 公式求值（amount × energy_regen），钳到上限.

        energy_regen 读**有效面板**——modifier ERR buff（stat_effects.energy_regen）经
        effective_stats 生效（旧读裸面板时该键是死键，buff 完全不生效）。
        err_exempt=True 为具名豁免（mechanics 05 §5.3 清单）：不乘 ERR，regenMulti 记 1.0。
        """
        st = target.actor.stats
        regen = 1.0 if err_exempt else float(self.effective_stats(target)["energy_regen"])
        value = evaluate(self._rb.formulas["gain_energy"], context={
            "amount": amount, "energy_regen": regen,
        }, rng=self.rng).value
        old = target.current_energy
        target.current_energy = min(st.max_energy, target.current_energy + value)
        return SettleResult(value=value, node={
            "formula": "gain_energy", "amount": amount, "regenMulti": regen,
            "actualAmount": target.current_energy - old,
        })

    def consume_energy(self, target: ActorState, amount: float) -> SettleResult:
        """耗能（终结技等）：不低于 0."""
        actual = min(amount, target.current_energy)
        target.current_energy -= actual
        return SettleResult(value=actual, node={
            "formula": "consume_energy", "amount": amount, "actualAmount": actual,
        })

    # ------------------------------------------------------------------
    # 削韧与击破（v0.2，锚点：mechanics/04_break_system.md + 02 §击破伤害）
    # 属性击破效果表已入 rulebook.break_effects（决策卡 A1：引擎零数值常数）
    # ------------------------------------------------------------------

    def toughness_damage_amount(self, source: Optional[ActorState], base_toughness: float,
                                *, action_type: str = "", damage_type: str = "") -> float:
        """实际削韧量 = rulebook toughness_damage 公式求值（调用点在 engine._apply_toughness_damage）.

        spec 双池乘算：(1 + break_efficiency_boost) × (1 + weakness_break_efficiency_boost)
        （01_formula §1.5；池结构实测待确认——B19"削韧效率池结构"行在案）。
        fixed_toughness_dmg：引擎/模板尚无固定削韧概念，中性 0 喂入（不新造机制）。
        含光环辐射（effective_stats 统一生效面）；source=None 时双池取 0。
        action_type/damage_type：hit_condition 命中域注入（2026-09-14 承伤三区通用化③
        ——类型限定削韧效率（飞霄 1220 E4「天赋追加攻击削韧效率+100%」首实例）；
        scoped 值并入 break_efficiency_boost 池，weakness_break 池的 scoped 待实例）。
        """
        se = self.effective_stats(source) if source is not None else {}
        scoped_eff = 0.0
        if source is not None and action_type:
            scoped_eff = self._scoped_boost(
                source,
                {"action_type": action_type, "damage_type": damage_type,
                 "target_broken": False, "target_controlled": False},
                lambda s: s == "break_efficiency_boost")
        return evaluate(self._rb.formulas["toughness_damage"], context={
            "base_toughness": base_toughness,
            "break_efficiency_boost": se.get("break_efficiency_boost", 0.0) + scoped_eff,
            "weakness_break_efficiency_boost": se.get("weakness_break_efficiency_boost", 0.0),
            "fixed_toughness_dmg": 0.0,  # 固定削韧：无实例，中性喂入
        }, rng=self.rng).value

    def toughness_damage(
        self,
        target: ActorState,
        amount: float,
        element: str,
        can_reduce: bool = True,
    ) -> SettleResult:
        """削韧结算：toughness_scope 闸（own_element 默认）在外层判定；本方法只记账."""
        if not can_reduce or target.bars_exhausted:
            return SettleResult(value=0.0, node={"formula": "toughness", "actualAmount": 0.0})
        old = target.toughness
        target.toughness = max(0.0, target.toughness - amount)
        return SettleResult(value=old - target.toughness, node={
            "formula": "toughness", "element": element, "actualAmount": old - target.toughness,
        })

    def break_damage(self, source: Any, target: ActorState, element: str) -> SettleResult:
        """击破瞬间的击破伤害（route["break"] → break_damage 公式链求值）.

        source：ActorState（活体，主路径——攻击方 modifier/光环口径全保留）或裸 Actor
        （兼容入口，_as_state 包无 modifier 裸壳——旧测试直调专用，引擎主路径勿用）。

        行为口径：break_dmg_boost 池已接真实面板——dmg_bonus 桶键 `break_dmg_boost`
        （modifier stat `dmg_break_dmg_boost` 经 _add_eff 自动入桶，池内多源加算；
        击破/超击破共池——spec：01_formula 击破式/超击破式 + mechanics §2.11）；
        final_dmg / dmg_red 两区仍按中性喂入（未实装，与旧 golden 锚一致；
        击破 finalDmgMulti 存疑待实测见 B19）；已击破 base_universal=1.0；不暴击。

        纯结算：本方法**不扣血**（与 deal_damage 同口径）——扣血由调用方（引擎）
        按返回值执行；调用方扣血量可带 ratio（hook 击破追加族），故扣血必须在引擎层。
        引擎主路径/hook 均绕盾直扣（B19 冻结口径，注记见 engine._trigger_break）。
        """
        eff = self.break_effect_of(element)
        src_state = self._as_state(source)
        se = self.effective_stats(src_state)
        te = self.effective_stats(target)
        base = self._zone("break_base_multi", {
            "elemental_break_scaling": eff["scaling"],
            "max_toughness": target.actor.stats.max_toughness,
            "special_scaling": 1.0,  # 特殊倍率槽（当前无实例，中性喂入）
        })
        be_multi = self._zone("be_multi", {"break_effect": se["break_effect"]})
        # 击破伤害提高池（已实装）：dmg_bonus 桶键直读，多源在 effective_stats 层加算收敛
        break_boost = self._zone("break_dmg_boost_multi", {
            "break_dmg_boost": se["dmg_bonus"].get("break_dmg_boost", 0.0)})
        def_multi = self._def_multi_eff(src_state.actor.level, se, te, target)
        res_multi = self._res_multi_for_eff(element, se, target)
        # 击破承伤 scoped（2026-09-14 承伤三区通用化·击破侧）：hit_condition 件的
        # vulnerability 同命中域计入——「受到的击破伤害提高」类型限定（灵砂 1222 BEFOG
        # 首实例；action_type 喂 "break" 自定义标识——hit_condition 表达式按字面值匹配；
        # ind_vulnerability 无击破乘区不纳入）
        vuln = self._zone("vuln_multi", {"vulnerability": te["vulnerability"] + self._scoped_boost(
            target,
            {"action_type": "break", "damage_type": element,
             "target_broken": True,
             "target_controlled": any(m.control_kind for m in target.modifiers.values())},
            lambda s: s == "vulnerability")})
        value = self._formula("break", {
            "break_base_multi": base,
            "be_multi": be_multi,
            "break_dmg_boost_multi": break_boost,
            "base_universal_multi": self._zone("base_universal_multi", {"target_broken": 1.0}),  # 击破瞬间恒已击破 → 1.0
            "def_multi": def_multi,
            "res_multi": res_multi,
            "vuln_multi": vuln,
            "final_dmg_multi": self._zone("final_dmg_multi", {"final_dmg_bonus": 0.0}),  # 未实装乘区，中性喂入
            "dmg_red_multi": self._zone("dmg_red_multi", {"dmg_reduction": 0.0}),  # 未实装乘区，中性喂入
        })
        return SettleResult(value=value, node={
            "formula": "break_damage", "breakBaseMulti": base, "beMulti": be_multi,
            "breakDmgBoostMulti": break_boost,
            "defMulti": def_multi, "resMulti": res_multi, "vulnMulti": vuln,
        })

    def super_break_damage(self, source: Any, target: ActorState, *,
                           effective_toughness: float, damage_type: str = "physical",
                           action_type: str = "") -> SettleResult:
        """超击破伤害结算（route["super_break"] → super_break_damage 公式链求值；B38）.

        触发口径（mechanics 04 §4.4 + 01_formula §1.3/§2.11）：目标已处弱点击破状态
        （broken）且攻击方转换倍率池 > 0（无源 = 0 不造成超击破）且本击有**名义**
        有效削韧值（已击破目标不再产生实际削韧，超击破按"该攻击若可削应削多少"结算——
        effective_toughness 由调用方经 toughness_damage_amount 同口径算出）。

        池读取（攻击方 effective_stats，开放命名空间顶层键）：
        - 转换倍率池 `super_break_modifier`：同谐主伴舞/忘归人天赋（122504 #1）/流萤
          β模组（11310102）经 modifier stat_effects 入池，多源加算；
        - 超击破增伤池 `super_break_dmg_boost`：忘归人 E4/乱破族（仅超击破生效）；
        - 击破增伤池共用 `break_dmg_boost`（击破/超击破共池已实装口径同 break_damage）。
        不吃攻击/增伤/双暴/虚弱；吃防御/抗性/易伤（含 hit_condition 击破承伤 scoped——
        action_type 喂 "super_break"，B38 预留命名）/减伤/韧性减伤/最终伤害（后两者
        未实装按中性喂入，与 break_damage 同口径）。纯结算**不扣血**（调用方扣血）。
        """
        src_state = self._as_state(source)
        se = self.effective_stats(src_state)
        te = self.effective_stats(target)
        conversion = float(se.get("super_break_modifier", 0.0) or 0.0)
        if conversion <= 0.0 or effective_toughness <= 0.0:
            return SettleResult(value=0.0, node={
                "formula": "super_break_damage", "superBreakConversionMulti": conversion,
                "effectiveToughness": effective_toughness, "skipped": True})
        base = self._zone("super_break_base_multi", {"effective_toughness": effective_toughness})
        be_multi = self._zone("be_multi", {"break_effect": se["break_effect"]})
        break_boost = self._zone("break_dmg_boost_multi", {
            "break_dmg_boost": se["dmg_bonus"].get("break_dmg_boost", 0.0)})
        sb_boost = self._zone("super_break_dmg_boost_multi", {
            "super_break_dmg_boost": float(se.get("super_break_dmg_boost", 0.0) or 0.0)})
        def_multi = self._def_multi_eff(src_state.actor.level, se, te, target)
        res_multi = self._res_multi_for_eff(damage_type, se, target)
        vuln = self._zone("vuln_multi", {"vulnerability": te["vulnerability"] + self._scoped_boost(
            target,
            {"action_type": "super_break", "damage_type": damage_type,
             "target_broken": True,
             "target_controlled": any(m.control_kind for m in target.modifiers.values())},
            lambda s: s == "vulnerability")})
        value = self._formula("super_break", {
            "super_break_base_multi": base,
            "be_multi": be_multi,
            "super_break_conversion_multi": conversion,
            "break_dmg_boost_multi": break_boost,
            "super_break_dmg_boost_multi": sb_boost,
            "base_universal_multi": self._zone("base_universal_multi", {"target_broken": 1.0}),  # 触发前提恒已击破 → 1.0
            "def_multi": def_multi,
            "res_multi": res_multi,
            "vuln_multi": vuln,
            "final_dmg_multi": self._zone("final_dmg_multi", {"final_dmg_bonus": 0.0}),  # 未实装，中性喂入
            "dmg_red_multi": self._zone("dmg_red_multi", {"dmg_reduction": 0.0}),        # 未实装，中性喂入
        })
        return SettleResult(value=value, node={
            "formula": "super_break_damage", "superBreakBaseMulti": base, "beMulti": be_multi,
            "superBreakConversionMulti": conversion, "breakDmgBoostMulti": break_boost,
            "superBreakDmgBoostMulti": sb_boost,
            "defMulti": def_multi, "resMulti": res_multi, "vulnMulti": vuln,
        })

    def _elation_ability_multi(self, action: Action, skill_level: int) -> float:
        """欢愉技纯倍率取档（scaling 行键 `elation`——比例量纲不基于角色属性，
        mechanics 02 §2.14 abilityMultiplier 口径；取档索引与 _ability_multi_eff 同式）."""
        if not action.scaling:
            return 0.0
        idx = min(max(skill_level - 1, 0), len(action.scaling) - 1)
        return float(action.scaling[idx].get("elation", 0.0))

    def elation_damage(self, source: Any, target: ActorState, *,
                       ability_multiplier: float, punchline_source: float,
                       damage_type: str, action_type: str = "elation_skill") -> SettleResult:
        """欢愉伤害结算（route["elation"] → elation_damage 公式链求值；B40 P2a）.

        口径（mechanics 02 §2.14 + 01_formula 欢愉式——rulebook 已在册只消费，零公式算术）：
        - 基础伤害 = 等级系数 7535.107 × 纯倍率 ability_multiplier（比例量纲，不基于角色属性）
        - `elation_multi` = 1 + 攻击方有效面板 `elation`（欢愉度，B40 P1b 面板键）
        - `punchline_source` 定槽（21_elation §21.2）：施放欢愉技=阿哈笑点池实时值、
          其他欢愉伤害=持有者好活当赏合并值——来源判定在调用方（action 层喂池 /
          hook deal_damage `punchline_source` 表达式槽），本路由只消费参数
        - 可暴击（`_crit_eff` 双模）；不吃通用增伤/独立增伤/独立易伤/weaken（不喂入）；
          防御/抗性/易伤/减伤/韧性减伤正常生效——易伤=通用池+承伤 scoped「受到的欢愉
          伤害提高」（action_type 喂 "elation_damage" 路由标识，与 break/super_break 同族；
          02 §2.14 vulnMulti「欢愉易伤+全类型易伤」口径，欢愉易伤经 hit_condition 命中）
        - `orig_elation_dmg_multi` 无实例中性 1.0（勿填 fandom 值——归 final_dmg_multi 槽）；
          `final_dmg_multi` 读攻击方 final_dmg_boost 池（「为原伤害的 X%」族——爻光 E4
          欢愉技 150% 落点）；`elation_dmg_boost`/`merrymake` 读攻击方开放命名空间键
          （无实例默认 0——行迹「欢愉度强化」映射 elation 面板不归本池）
        纯结算**不扣血**（调用方扣血——与 deal_damage/super_break_damage 同口径）。
        """
        src_state = self._as_state(source)
        se = self.effective_stats(src_state)
        te = self.effective_stats(target)
        if ability_multiplier <= 0.0:
            return SettleResult(value=0.0, node={
                "formula": "elation_damage", "abilityMulti": ability_multiplier, "skipped": True})
        el_boost = self._zone("elation_dmg_boost_multi", {
            "elation_dmg_boost": float(se.get("elation_dmg_boost", 0.0) or 0.0)})
        el_multi = self._zone("elation_multi", {"elation": float(se.get("elation", 0.0) or 0.0)})
        pl_multi = self._zone("punchline_multi", {"punchline_source": float(punchline_source)})
        mm_multi = self._zone("merrymake_multi", {
            "merrymake": float(se.get("merrymake", 0.0) or 0.0)})
        crit_multi, is_crit = self._crit_eff(se)
        def_multi = self._def_multi_eff(src_state.actor.level, se, te, target)
        res_multi = self._res_multi_for_eff(damage_type, se, target)
        vuln = self._zone("vuln_multi", {"vulnerability": te["vulnerability"] + self._scoped_boost(
            target,
            {"action_type": "elation_damage", "damage_type": damage_type,
             "target_broken": target.broken,
             "target_controlled": any(m.control_kind for m in target.modifiers.values())},
            lambda s: s == "vulnerability")})
        final_dmg = self._zone("final_dmg_multi", {
            "final_dmg_bonus": se["dmg_bonus"].get("final_dmg_boost", 0.0)})
        dmg_red = self._zone("dmg_red_multi", {
            "dmg_reduction": te["dmg_bonus"].get("dmg_reduction", 0.0)})
        value = self._formula("elation", {
            "elation_level_multiplier": float(self._rb.constants["elation_level_multiplier"]),
            "ability_multiplier": ability_multiplier,
            "orig_elation_dmg_multi": 1.0,   # 无实例中性喂入（勿填 fandom 值——02 §2.14 定槽）
            "elation_dmg_boost_multi": el_boost,
            "crit_multi": crit_multi,
            "elation_multi": el_multi,
            "punchline_multi": pl_multi,
            "merrymake_multi": mm_multi,
            "def_multi": def_multi,
            "res_multi": res_multi,
            "vuln_multi": vuln,
            "dmg_red_multi": dmg_red,
            "base_universal_multi": self._zone("base_universal_multi", {
                "target_broken": 1.0 if target.broken else 0.0}),
            "final_dmg_multi": final_dmg,
        })
        return SettleResult(value=value, node={
            "formula": "elation_damage", "abilityMulti": ability_multiplier,
            "elationLevelMultiplier": float(self._rb.constants["elation_level_multiplier"]),
            "elationDmgBoostMulti": el_boost, "elationMulti": el_multi,
            "punchlineMulti": pl_multi, "merrymakeMulti": mm_multi,
            "critMulti": crit_multi, "isCrit": is_crit,
            "defMulti": def_multi, "resMulti": res_multi, "vulnMulti": vuln,
            "baseUniversalMulti": 1.0 if target.broken else 0.9,
            "finalDmgMulti": final_dmg, "dmgRedMulti": dmg_red,
            "punchlineSource": float(punchline_source),
        })

    def break_effect_of(self, element: str) -> Dict[str, Any]:
        table = self._rb.break_effects
        return table.get(element, table["fire"])

    def energy_gain_default(self, action_type: str) -> float:
        """行动默认回能查表（rulebook energy 节，mechanics 05 §5.1；Action 显式 energy_gain 优先——调用方保证）."""
        return float(self._rb.energy.get(action_type, 0))

    def freeze_advance(self) -> float:
        """冻结解冻后的行动提前比例（rulebook constants.freeze_advance，mechanics 03 §3.5）."""
        return float(self._rb.constants["freeze_advance"])

    def sp_max_default(self) -> int:
        """战技点默认上限（rulebook constants.sp_max_default，mechanics 06 §6.1：默认 5）."""
        return int(self._rb.constants["sp_max_default"])

    def initial_sp_default(self) -> int:
        """开局战技点（rulebook constants.initial_sp，mechanics 06 §6.2：初始 3 点）."""
        return int(self._rb.constants["initial_sp"])

    def initial_energy_ratio_default(self) -> float:
        """开局能量占上限比例（rulebook constants.initial_energy_ratio：默认 0.5）."""
        return float(self._rb.constants["initial_energy_ratio"])

    def blast_toughness_ratio(self) -> float:
        """扩散副目标默认削韧比例（rulebook constants.blast_toughness_ratio，04_break_system 基线 10/20/10）."""
        return float(self._rb.constants["blast_toughness_ratio"])

    def shield_value(self, source: Optional[ActorState], shield_spec: Dict[str, Any]) -> float:
        """护盾值：rulebook `shield` 公式唯一路径（mechanics 01 §1.3）.

        scaling 槽位 = def/hp/atk 三缩放族（公式槽）；shield_bonus 读施加者**有效面板**。
        公式外槽位报错指路（不静默吞——旧逐键循环曾照单全收）。
        """
        se = self.effective_stats(source) if source is not None else {}
        scaling = shield_spec.get("scaling") or {}
        unknown = set(scaling) - {"def", "def_", "hp", "atk"}
        if unknown:
            raise ValueError(
                f"护盾 scaling 含公式外槽位 {sorted(unknown)}（rulebook shield 公式仅 def/hp/atk 三缩放槽）")
        return evaluate(self._rb.formulas["shield"], context={
            "def_scaling": float(scaling.get("def", scaling.get("def_", 0.0))),
            "defense": float(se.get("def_", 0.0)),  # 表达式内 bare def 经预处理改写为 defense
            "hp_scaling": float(scaling.get("hp", 0.0)),
            "hp": float(se.get("hp", 0.0)),
            "atk_scaling": float(scaling.get("atk", 0.0)),
            "atk": float(se.get("atk", 0.0)),
            "flat_shield": float(shield_spec.get("flat", 0.0)),
            "shield_bonus": float(se.get("shield_bonus", 0.0)),
        }, rng=self.rng).value

    # ------------------------------------------------------------------
    # DoT 跳伤（B27#3 收官：route["dot"]/route["bleed"] 全乘区链 + 快照切分，
    # mechanics 02 §2.12；v0.2 简化式 dot_snapshot/bleed_tick 已退役）
    # ------------------------------------------------------------------

    def dot_snapshot_context(self, source: Any, target: Any, element: str, ratio: float) -> Dict[str, float]:
        """DoT 施加时刻攻击侧快照包（mechanics 02 §2.12 快照切分落地）.

        施加时由引擎算好存 `modifier.dot_snapshot_ctx`；跳伤时攻击侧乘区全读本包，
        目标侧乘区取现值。槽位（消费端各取所需——常规 DoT 不读 be_multi，裂伤只读
        be_multi/final_dmg_multi）：
        - ability_multiplier：ability_base 求值（atk_scaling=dot_ratio × 施加者有效 atk；
          hp/def 缩放 DoT 实例未到，两槽中性 0 喂入）
        - dmg_boost_multi：施加者增伤面板合成（all + 元素 + `dot_dmg_boost` 桶——
          「持续伤害提高」池，21008 猎物视线首实例）
        - ind_dmg_boost_multi / final_dmg_multi / weaken_multi：施加者对应桶快照
          （虚弱读攻击侧——mechanics 07「降低造成伤害的 debuff」口径）
        - ehr_multi：施加时刻命中区（base_chance=1.0 常规 DoT——期望值建模层，01_formula
          dot_damage 注；type_res 无实例源中性 0，与 hit_chance 同口径）
        - be_multi：施加者击破特攻区（裂伤专用——cap 外乘区，01_formula §1.4 裂伤特例）
        - source_level / def_pen / res_pen：防御/抗性乘区内的攻击侧输入（随攻击侧快照）
        """
        src = self._as_state(source)
        tgt = self._as_state(target)
        se = self.effective_stats(src)
        te = self.effective_stats(tgt)
        b = se["dmg_bonus"]
        return {
            "source_level": float(src.actor.level),
            "def_pen": float(se["def_pen"]),
            "res_pen": float(se["res_pen"]),
            "ability_multiplier": self._zone("ability_base", {
                "atk_scaling": float(ratio), "hp_scaling": 0.0, "def_scaling": 0.0,
                "atk": se["atk"], "hp": 0.0, "def_": 0.0}),
            "dmg_boost_multi": self._zone("dmg_boost_multi", {
                "all_dmg_bonus": b.get("all", 0.0),
                "elemental_dmg_bonus": b.get(element, 0.0) if element else 0.0,
                "type_dmg_bonus": b.get("dot_dmg_boost", 0.0)}),
            "ind_dmg_boost_multi": self._zone("ind_dmg_boost_multi", {
                "ind_dmg_bonus": b.get("ind_dmg_boost", 0.0)}),
            "final_dmg_multi": self._zone("final_dmg_multi", {
                "final_dmg_bonus": b.get("final_dmg_boost", 0.0)}),
            "weaken_multi": self._zone("weaken_multi", {"weaken": b.get("weaken", 0.0)}),
            "ehr_multi": self._zone("ehr_multi", {
                "base_chance": 1.0,
                "effect_hit": se.get("effect_hit", 0.0),
                "target_effect_res": te.get("effect_res", 0.0),
                "effect_res_pen": se.get("effect_res_pen", 0.0),
                "type_res": 0.0}),
            "be_multi": self._zone("be_multi", {"break_effect": se["break_effect"]}),
        }

    def _dot_target_side(self, holder: ActorState, snap: Dict[str, float], element: str,
                         *, scoped_accept: Any) -> Dict[str, Any]:
        """DoT 跳伤目标侧链（跳伤时刻现值）：防御/抗性/韧性减伤/易伤（含承伤 scoped）/减伤.

        防御/抗性区内的攻击侧输入（attacker_level/def_pen/res_pen）读快照包（空件中性 0，
        attacker_level 兜底持有者等级——裸件直调路径）；承伤 scoped = hit_condition 件的
        「受到的持续伤害提高」族（action_type 喂 "dot" 路由 id，与 break/super_break/elation
        族同构——携带者=目标侧，04_modifier §hit_condition）。
        """
        te = self.effective_stats(holder)
        attacker_level = int(snap.get("source_level", holder.actor.level))
        def_multi = self._def_multi_eff(
            attacker_level, {"def_pen": float(snap.get("def_pen", 0.0))}, te, holder)
        res_multi = self._res_multi_for_eff(
            element, {"res_pen": float(snap.get("res_pen", 0.0))}, holder)
        base_universal = self._zone("base_universal_multi", {
            "target_broken": 1.0 if holder.broken else 0.0})
        vuln = self._zone("vuln_multi", {"vulnerability": te["vulnerability"] + self._scoped_boost(
            holder,
            {"action_type": "dot", "damage_type": element,
             "target_broken": holder.broken,
             "target_controlled": any(m.control_kind for m in holder.modifiers.values())},
            scoped_accept)})
        dmg_red = self._zone("dmg_red_multi", {
            "dmg_reduction": te["dmg_bonus"].get("dmg_reduction", 0.0)})
        return {"te": te, "def_multi": def_multi, "res_multi": res_multi,
                "base_universal_multi": base_universal, "vuln_multi": vuln,
                "dmg_red_multi": dmg_red}

    def dot_tick(self, holder: ActorState, mod) -> SettleResult:
        """DOT 跳伤（A 类结算，持有者优先级按其自身回合开始）：rulebook `dot_damage` 公式链
        （route["dot"]），不暴击.

        快照切分（mechanics 02 §2.12，B27#3 收官）：攻击侧乘区读 `mod.dot_snapshot_ctx`
        （施加时刻引擎算好存件——dot_snapshot_context）；目标侧乘区跳伤时刻现值
        （_dot_target_side；独立易伤常规 DoT 生效——读目标面板桶）。空 ctx = 裸件兜底
        （手建 modifier 直调路径）：攻击侧全中性、倍率基数走 dot_source_atk × dot_ratio
        （ability_base 求值）。
        """
        snap = mod.dot_snapshot_ctx or {}
        if "ability_multiplier" in snap:
            ability = float(snap["ability_multiplier"])
        else:
            ability = self._zone("ability_base", {
                "atk_scaling": mod.dot_ratio, "hp_scaling": 0.0, "def_scaling": 0.0,
                "atk": mod.dot_source_atk, "hp": 0.0, "def_": 0.0})
        side = self._dot_target_side(holder, snap, mod.dot_element,
                                     scoped_accept=lambda s: s in ("vulnerability", "ind_vulnerability"))
        # 独立易伤（常规 DoT 生效——02 §2.12 常规列）：目标面板桶现值
        ind_vuln = self._zone("ind_vuln_multi", {
            "ind_vulnerability": side["te"]["dmg_bonus"].get("ind_vulnerability", 0.0)})
        value = self._formula("dot", {
            "ability_multiplier": ability,
            "dmg_boost_multi": float(snap.get("dmg_boost_multi", 1.0)),
            "ind_dmg_boost_multi": float(snap.get("ind_dmg_boost_multi", 1.0)),
            "def_multi": side["def_multi"],
            "res_multi": side["res_multi"],
            "base_universal_multi": side["base_universal_multi"],
            "vuln_multi": side["vuln_multi"],
            "ind_vuln_multi": ind_vuln,
            "final_dmg_multi": float(snap.get("final_dmg_multi", 1.0)),
            "weaken_multi": float(snap.get("weaken_multi", 1.0)),
            "dmg_red_multi": side["dmg_red_multi"],
            "ehr_multi": float(snap.get("ehr_multi", 1.0)),
        })
        holder.current_hp -= value
        return SettleResult(value=value, node={
            "formula": "dot", "element": mod.dot_element, "ratio": mod.dot_ratio,
            "abilityMulti": ability,
            "dmgBoostMulti": float(snap.get("dmg_boost_multi", 1.0)),
            "indDmgBoostMulti": float(snap.get("ind_dmg_boost_multi", 1.0)),
            "defMulti": side["def_multi"], "resMulti": side["res_multi"],
            "baseUniversalMulti": side["base_universal_multi"],
            "vulnMulti": side["vuln_multi"], "indVulnMulti": ind_vuln,
            "finalDmgMulti": float(snap.get("final_dmg_multi", 1.0)),
            "weakenMulti": float(snap.get("weaken_multi", 1.0)),
            "dmgRedMulti": side["dmg_red_multi"],
            "ehrMulti": float(snap.get("ehr_multi", 1.0)),
            "isCrit": False, "actualAmount": value,
        })

    def bleed_tick(self, holder: ActorState, mod) -> SettleResult:
        """裂伤跳伤：rulebook `bleed_dot_damage` 公式链（route["bleed"]，B27#3 收官）.

        裂伤式 = min（敌人类型系数×目标生命上限, 2×3767.5533×(0.5+最大韧性/40)）——
        min 结果整体替代通用框架的 level_base×effect_multiplier（cap 在基数层比较）；
        其后照常乘 (1+BE)×易伤×防御×抗性×减伤×最终伤害×韧性减伤（01_formula §1.4 裂伤特例
        + mechanics 02 §2.12 击破列：BE/最终伤害按施加者快照——dot_snapshot_ctx，其余目标侧
        跳伤现值；独立易伤/虚弱/攻击力/增伤/独立增伤不喂——击破 DOT 列）。
        击破裂伤 ratio=1.0（rulebook break_effects.physical.bleed_ratio），其他裂伤源经 ratio 缩放。
        敌类型系数（rulebook break_effects.physical.bleed_coeff：elite 7% / normal 16%）：
        sim_schema Actor 无 rank/elite 字段——按现有最贴近的 actor_type 喂入，
        怪物（monster/enemy）一律精英档（深渊环境最贴近；rank 字段落地后接真实档位）。
        target_hp 取裸面板生命上限（spec 未写 effective 口径，按代码现状冻结）。
        """
        coeff_table = self._rb.break_effects["physical"].get("bleed_coeff", {})
        rank = "elite" if holder.actor.actor_type in ("monster", "enemy") else "normal"
        base = self._zone("bleed_base_multi", {
            "enemy_type_coeff": coeff_table.get(rank, 0.0),
            "target_hp": holder.actor.stats.hp,
            "max_toughness": holder.actor.stats.max_toughness,
        })
        snap = mod.dot_snapshot_ctx or {}
        side = self._dot_target_side(holder, snap, "physical",
                                     scoped_accept=lambda s: s == "vulnerability")
        value = self._formula("bleed", {
            "bleed_base_multi": base,
            "dot_ratio": mod.dot_ratio,
            "be_multi": float(snap.get("be_multi", 1.0)),
            "def_multi": side["def_multi"],
            "res_multi": side["res_multi"],
            "base_universal_multi": side["base_universal_multi"],
            "vuln_multi": side["vuln_multi"],
            "final_dmg_multi": float(snap.get("final_dmg_multi", 1.0)),
            "dmg_red_multi": side["dmg_red_multi"],
        })
        holder.current_hp -= value
        return SettleResult(value=value, node={
            "formula": "bleed", "ratio": mod.dot_ratio, "bleedBaseMulti": base,
            "beMulti": float(snap.get("be_multi", 1.0)),
            "defMulti": side["def_multi"], "resMulti": side["res_multi"],
            "baseUniversalMulti": side["base_universal_multi"],
            "vulnMulti": side["vuln_multi"],
            "finalDmgMulti": float(snap.get("final_dmg_multi", 1.0)),
            "dmgRedMulti": side["dmg_red_multi"],
            "enemyType": rank, "actualAmount": value,
        })
