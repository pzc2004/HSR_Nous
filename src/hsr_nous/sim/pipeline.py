"""结算管线：两层求值 → effect 原语执行 → 伤害公式（节点值树输出）.

现状范围（v0.1 起步，现已扩到全公式链）：两层求值（effective_stats/modifier_enabled）
+ 通用伤害结算 settle_damage（全类别：direct/true/击破/超击破/欢愉/DoT/裂伤——per-type 函数全删，只剩通用 settle + 通用原语）+ heal + gain/consume(能量) +
削韧/击破特攻 + 护盾值 + DoT 快照/当跳基数 + rulebook 常数访问族。
每次结算输出 (value, 节点值树)——Evaluator 的显微镜，也是对拍的对齐粒度。

公式锚点：01_formula.md 十二乘区 + base_dmg_add 基数区；
mechanics/02_damage_formula.md 镜像。

公式执行形态：公式链零 Python 算术——全部表达式来自 rulebook
（`sim_schema/rulebook.yaml`，01_formula 的可执行唯一来源），绑定期白名单
预编译，此处只带 context 求值（引擎零数值常数）。

通用结算形态：`settle_damage` 为全数据驱动并行新路径——
乘区取值声明在 rulebook zones 段（每乘区一次），类别结算规格在 route.<类别>.settle，
新路径零特定乘区/伤害类别知识（只剩通用 settle + 通用原语）；per-type 函数保留
作对拍基准，逐比特全等对拍见 tests/test_settle_parity.py。

统一 AST 形态（2026-10-11 裁决）：公式 = 大 AST，按名字**引用**乘区子 AST
（zone_refs——乘区在 rulebook 定义一次、处处引用，子树共享不做文本拷贝）；乘区
按引用点 AST 首遇序 **eager 求值一次**（exactly-once，含短路与三元未取分支），
zone_cache 承载值+子树 trace，大 AST 求值时引用回读（`expression.evaluate(
zone_refs=..., zone_cache=...)`，ZoneRef 节点值树）。
拆解/随机流顺序/子树复用三个白来项：拆解 = ZoneRef/zone_cache 子树 trace 结构自带；
随机流 = AST 首遇序结构确定（装配段 eager 序，遍历段零消耗）；复用 = 乘区子树经
zone_refs 共享 + 类别组合静态缓存（`_settle_composition`）。
"""
from __future__ import annotations

import ast
import random
import types
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from hsr_nous.sim.state import BREAK_DOT_ID_PREFIX, ActorState
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.expression import EvalOutcome, PreparedExpression, evaluate
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
        # hit_condition 命中域宿主函数提供者（engine 注入）：fn(source ActorState) ->
        # 函数表（hooks._hook_functions 同集——debuff_count($event.target) 族命中域判定）；
        # 未注入时 hit_condition 只读 $event 标量字段（函数调用求值失败按不计入）
        self._hit_functions: Optional[Any] = None
        # 命中域 `$self` 命名空间工厂（engine 注入）：fn(source ActorState) -> NS
        # （hooks._HookSelfNS 同型——面板惰性 + variable_bindings 参数读取；
        # 04_modifier §hit_condition「$self 绑定携带者」的兑现，hit_stat_exprs 叠影参数族取数源）
        self._hit_self_ns: Optional[Any] = None
        # actor 反查（engine 注入）：fn(actor_id) -> Optional[ActorState]——DoT 跳伤时刻
        # 按 mod.source_id 反查施加者（跳伤攻击侧 scoped 求值源）
        self._actor_lookup: Optional[Any] = None
        self._rb = get_rulebook()  # 公式簿（绑定期已预编译；此处只取句柄）
        self._comp_cache: Dict[tuple, Any] = {}  # 统一 AST 类别组合静态缓存（_settle_composition）

    def set_aura_provider(self, fn: Any) -> None:
        """注册光环提供者（engine 注入）：fn(ActorState) -> List[Modifier]（全队 scope=team 光环）."""
        self._aura_provider = fn

    def set_condition_runtime(self, runtime_fn: Any, warn_fn: Any) -> None:
        """注册条件光环运行时（engine 注入）：enable_if/stat_exprs 的语境工厂 + 告警槽."""
        self._cond_runtime = runtime_fn
        self._cond_warn = warn_fn

    def set_hit_functions(self, fn: Any, self_ns_fn: Any = None) -> None:
        """注册 hit_condition 命中域宿主函数提供者（engine 注入）：fn(ActorState) -> 函数表；
        self_ns_fn（可选）= 命中域 `$self` 命名空间工厂（fn(ActorState) -> NS）."""
        self._hit_functions = fn
        self._hit_self_ns = self_ns_fn

    def set_actor_lookup(self, fn: Any) -> None:
        """注册 actor 反查（engine 注入）：fn(actor_id) -> Optional[ActorState]."""
        self._actor_lookup = fn

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

    def effective_stats(self, actor_state: ActorState, *, _skip_cond: bool = False,
                        _skip_aura: bool = False) -> Dict[str, Any]:
        """有效面板 = Layer 1（base + Σ modifier flat）→ Layer 2（转化 → 覆写）.

        防二次转化循环：转化读取的是 source 的 Layer 1，不读 effective。
        光环（scope=team）：provider 提供的全队光环 stat_effects 并入 Layer 1
        （pct 族按目标白值乘算，与 Layer 1.5 同口径）。
        条件光环（04_modifier §4.16）：enable_if/stat_exprs 件先按**无条件件面板**
        求门控与档位，通过的才并入（重估时机=面板读取即重估，懒求值零 stale）；
        `_skip_cond=True` = 无条件件面板通道——条件域一切面板读取走此（构造防环）。
        `_skip_aura=True` = 不并光环（德谬歌镜像忆师 HP_P% 专用——忆师池经镜像进忆灵，
        光环直辐射忆灵，两侧不双计，2026-09-23）。
        """
        held = list(actor_state.modifiers.values())
        if self._aura_provider is not None and not _skip_aura:
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
            "elation": st.elation,   # 欢愉度（21_elation §21.1，elation_multi=1+elation）
            "break_efficiency_boost": st.break_efficiency_boost,
            "weakness_break_efficiency_boost": st.weakness_break_efficiency_boost,
            "effect_hit": st.effect_hit, "effect_res": st.effect_res,
            "taunt": self._base_taunt(actor_state.actor),
            "heal_bonus": st.heal_bonus, "shield_bonus": st.shield_bonus,
            "dmg_bonus": dict(st.dmg_bonus),
            # max_toughness（云火昭「各自韧性上限×比例」族 $target.max_toughness
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
            if mod.hit_condition_expr is not None or mod.hit_stat_exprs:
                continue   # 命中域件（hit_condition/hit_stat_exprs 携带者）面板不读——值只经命中域计入
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
        # pct 加成池暴露（2026-09-23——德谬歌活镜像昔涟 HP_P% 首实例；stat_of 直读，
        # 与 optimizer 面板 HP_P 同位；不影响合成值，仅增量键）
        out.update(pct_pool)
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
    # scoped 命中域聚合与元素抗性解析（通用原语——settle/治疗/削韧共用）
    # ------------------------------------------------------------------

    def _scoped_boost(self, source: ActorState, event_ctx: Dict[str, Any],
                      accept: Any, *, target: Optional[ActorState] = None) -> float:
        """hit_condition scoped 加成：命中域条件命中才计入（04_modifier §hit_condition 组合原语）.

        命中域 `$event` 命名空间按结算类型由调用方注入（伤害：action_type/damage_type/
        target_broken/target_controlled/target_control_kinds/target_hp_ratio；治疗：
        target_hp_ratio）；`accept(stat)` 判定该结算类型计入哪些 stat（伤害 = dmg_*/all_dmg；
        治疗 = heal_bonus）。
        `target`：本次命中目标 ActorState——注入 `$event.target`（攻击者对带 debuff 的
        目标增伤/穿透/暴击族——按目标状态判定的 scoped 件，宿主函数 debuff_count 等
        经 has_modifier 同通道解析，117 2pc/116 4pc/21001 族）；调用方 payload dict
        不含此键（统一在此并入，非各结算点自报字段）。
        命中域可用宿主函数 = engine 注入的 _hit_functions（hooks._hook_functions 同集，
        $self 绑定携带者）；未注入/求值失败均静默不计。
        `hit_stat_exprs`（2026-09-23 落地）：命中域表达式值槽——条件通过时逐 stat
        现场求值计入当次命中（per-hit 按目标状态/层数伸缩值，静态 stat_effects 是
        烘焙定值）；携带件与 hit_condition 件同纪律面板不读（_compute 同闸）。
        只扫携带者自身持有件（scope=team 光环不辐射——全队族双件各挂）；求值失败静默不计。
        """
        total = 0.0
        if target is not None:
            event_ctx = {**event_ctx, "target": target}
        ctx = {"event": types.SimpleNamespace(**event_ctx)}
        if self._hit_self_ns is not None:
            ctx["self"] = self._hit_self_ns(source)   # $self=携带者（04_modifier §hit_condition）
        functions = self._hit_functions(source) if self._hit_functions is not None else None
        for mod in source.modifiers.values():
            if mod.hit_condition_expr is None and not mod.hit_stat_exprs:
                continue
            ok = True
            if mod.hit_condition_expr is not None:
                ok = False
                try:
                    ok = bool(self.expr_evaluate(mod.hit_condition_expr, ctx, functions=functions))
                except Exception:
                    ok = False
            if ok:
                for stat, val in mod.stat_effects.items():
                    if accept(stat):
                        total += val
                # 命中域表达式值（hit_stat_exprs——按目标状态伸缩的 per-hit 值槽，
                # 与 hit_condition 同语境现场求值；失败静默不计，B8 同口径）
                for stat, expr in mod.hit_stat_exprs.items():
                    if not accept(stat):
                        continue
                    try:
                        total += float(self.expr_evaluate(expr, ctx, functions=functions))
                    except Exception:
                        continue
        return total

    def expr_evaluate(self, prepared: Any, ctx: Dict[str, Any], *,
                      functions: Optional[Any] = None) -> Any:
        """白名单表达式求值（经 expression.py；未接编译器时退化为 False）."""
        if self._expr is None:
            return False
        return self._expr.evaluate(prepared, ctx, self.rng, functions=functions)

    def effective_weakness(self, target: ActorState) -> set:
        """有效弱点 = 面板弱点 ∪ 挂身 modifier 的 weakness_add（弱点植入 debuff 族）."""
        w = set(target.actor.stats.weakness)
        for m in target.modifiers.values():
            w |= set(m.weakness_add)
        return w

    def _base_res(self, dmg_type: Optional[str], target: ActorState) -> float:
        """基础抗性 + `res_<element>` 修饰：弱点 0 / 面板抗性 / 非弱点默认后同位加算."""
        if dmg_type and dmg_type in self.effective_weakness(target):
            base = 0.0
        elif dmg_type in target.actor.stats.resistance:
            base = target.actor.stats.resistance[dmg_type]
        else:
            base = self._rb.constants["non_weakness_res"]
        if not dmg_type:
            return base
        return base + float(self.effective_stats(target).get(f"res_{dmg_type}", 0.0))

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
        - heal_bonus（Outgoing_Healing_Boost）：**治疗源** effective_stats，外加命中域条件件
          （hit_condition）现场并入——治疗命中域 `$event.target_hp_ratio` = 受疗者当前 HP /
          有效生命上限（治疗前；04_modifier §hit_condition 治疗命中域，1409 阴云莞尔族）。
          **召唤物施放的治疗，治疗源 = 主人**（2026-09-21 裁决：召唤物无 OHB 属性，
          「治疗量提高」主体为召唤者——面板 heal_bonus 与命中域 scoped 件都读主人
          effective_stats，不取主人+召唤物并集（主人面板已含一切加成）；主人查不到
          （未注入反查/裸件直调）回退施放者自身面板。灵砂 1222 浮元族，R-LS1 收官）
        - incoming_heal（受治疗量变化——加成为正、降低为负，如萨姆领域）：**受疗者** effective_stats
        封顶 = 受疗者有效生命上限（与 engine heal_self/复活同口径）。
        事件（on_hp_increase）由调用方（引擎侧）发射——pipeline 纯结算不持 bus。
        """
        src = self._as_state(source)
        tgt = self._as_state(target)
        se = self.effective_stats(src)
        te = self.effective_stats(tgt)
        # 治疗源解析：召唤物（summoner_id 反指主人）治疗归主人面板——见上 heal_bonus 条
        hb_src = src
        if src.actor.summoner_id and self._actor_lookup is not None:
            hb_src = self._actor_lookup(str(src.actor.summoner_id)) or src
        hse = se if hb_src is src else self.effective_stats(hb_src)
        heal_bonus = hse.get("heal_bonus", 0.0) + self._scoped_boost(
            hb_src, {"target_hp_ratio": tgt.current_hp / te["hp"] if te["hp"] > 0 else 0.0},
            lambda s: s == "heal_bonus", target=tgt)
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
    # 属性击破效果表已入 rulebook.break_effects（引擎零数值常数）
    # ------------------------------------------------------------------

    def toughness_damage_amount(self, source: Optional[ActorState], base_toughness: float,
                                *, action_type: str = "", damage_type: str = "") -> float:
        """实际削韧量 = rulebook toughness_damage 公式求值（调用点在 engine._apply_toughness_damage）.

        spec 双池乘算：(1 + break_efficiency_boost) × (1 + weakness_break_efficiency_boost)
        （01_formula §1.5；池结构实测待确认）。
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

    def _elation_ability_multi(self, action: Action, skill_level: int) -> float:
        """欢愉技纯倍率取档（scaling 行键 `elation`——比例量纲不基于角色属性，
        mechanics 02 §2.14 abilityMultiplier 口径；取档索引与 _scaling_row 同式）."""
        if not action.scaling:
            return 0.0
        idx = min(max(skill_level - 1, 0), len(action.scaling) - 1)
        return float(action.scaling[idx].get("elation", 0.0))

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

    def aha_speed(self, spds: List[float]) -> float:
        """阿哈时刻速度（rulebook constants.aha_speed_base/aha_speed_weights——21_elation
        §21.4：基础值 + Σ权重×欢愉角色有效速度降序前 4；spds 已由调用方降序截前 4）."""
        c = self._rb.constants
        return float(c["aha_speed_base"]) + sum(
            w * v for w, v in zip(c["aha_speed_weights"], spds))

    def aha_start_punchline(self) -> float:
        """进战每欢愉角色阿哈笑点（rulebook constants.aha_start_punchline，mechanics 08 §8.2）."""
        return float(self._rb.constants["aha_start_punchline"])

    def aha_start_banger(self) -> float:
        """进战好活当赏点数（rulebook constants.aha_start_banger，mechanics 08 §8.1）."""
        return float(self._rb.constants["aha_start_banger"])

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
    # DoT 跳伤（已收官：route["dot"]/route["bleed"] 全乘区链 + 快照切分，
    # mechanics 02 §2.12；v0.2 简化式 dot_snapshot/bleed_tick 已退役）
    # ------------------------------------------------------------------

    def dot_snapshot_context(self, source: Any, target: Any, element: str, ratio: Optional[float],
                             *, base_chance: float = 1.0) -> Dict[str, float]:
        """DoT 施加时刻攻击侧快照包（mechanics 02 §2.12 快照切分落地）.

        施加时由引擎算好存 `modifier.dot_snapshot_ctx`；跳伤时攻击侧乘区全读本包，
        目标侧乘区取现值。槽位（消费端各取所需——常规 DoT 不读 be_multi，裂伤只读
        be_multi/final_dmg_multi）：
        - ability_multiplier：ability_base 求值（atk_scaling=dot_ratio × 施加者有效 atk；
          hp/def 缩放 DoT 实例未到，两槽中性 0 喂入；叠层 DoT 的层数乘算在跳伤侧——
          快照只存每层倍率基数）。ratio=None（dot_ratio_expr 跳伤时求值件）不烤此槽——
          基数由跳伤时刻表达式给出，快照只留攻击侧乘区
        - dmg_boost_multi：施加者增伤面板合成（all + 元素 + `dot_dmg_boost` 桶——
          「持续伤害提高」池，21008 猎物视线首实例）
        - ind_dmg_boost_multi / final_dmg_multi / weaken_multi：施加者对应桶快照
          （虚弱读攻击侧——mechanics 07「降低造成伤害的 debuff」口径）
        - ehr_multi：施加时刻命中区（base_chance=dot_base_chance 常规 DoT——期望值建模层，
          01_formula dot_damage 注；type_res 无实例源中性 0，与 hit_chance 同口径）
        - be_multi：施加者击破特攻区（裂伤专用——cap 外乘区，01_formula §1.4 裂伤特例）
        - source_level / def_pen / res_pen：防御/抗性乘区内的攻击侧输入（随攻击侧快照）
        """
        src = self._as_state(source)
        tgt = self._as_state(target)
        se = self.effective_stats(src)
        te = self.effective_stats(tgt)
        b = se["dmg_bonus"]
        ctx = {
            "source_level": float(src.actor.level),
            "def_pen": float(se["def_pen"]),
            "res_pen": float(se["res_pen"]),
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
                "base_chance": float(base_chance),
                "effect_hit": se.get("effect_hit", 0.0),
                "target_effect_res": te.get("effect_res", 0.0),
                "effect_res_pen": se.get("effect_res_pen", 0.0),
                "type_res": 0.0}),
            "be_multi": self._zone("be_multi", {"break_effect": se["break_effect"]}),
        }
        if ratio is not None:
            ctx["ability_multiplier"] = self._zone("ability_base", {
                "atk_scaling": float(ratio), "hp_scaling": 0.0, "def_scaling": 0.0,
                "atk": se["atk"], "hp": 0.0, "def_": 0.0, "base_dmg_add": 0.0})
        return ctx

    def _dot_source_state(self, mod: Any) -> Optional[ActorState]:
        """DoT 施加者反查（跳伤时刻攻击侧 scoped 求值源）：engine 注入的 actor 反查；
        未注入/查无/无 source_id → None（scoped 不计——裸件直调路径中性兜底）."""
        if self._actor_lookup is None or not getattr(mod, "source_id", ""):
            return None
        return self._actor_lookup(str(mod.source_id))

    def _dot_tick_expr_ctx(self, holder: ActorState, mod: Any) -> Dict[str, Any]:
        """dot_ratio 跳伤时求值语境（闭合键表，编译闸 _check_dot_tick_expr 同集镜像）.

        与通道「跳伤时读目标侧现值」的快照切分语义同构：
        - `self`：持有者（挂 modifier 的敌方）**跳伤时刻现值**——基础字段（hp=当前/
          energy/max_energy/state/actor_id/summoner_id）+ 有效面板（max_hp/atk/def_/
          spd/... 同 _HookSelfNS 面板通道，effective_stats 全键）+ weakness/resistance/
          toughness_bars/summon_flags（actor.stats 直读，_SELF_NS_FIELDS 白名单全量背书）
        - `snapshot`：施加者攻击侧快照包（dot_snapshot_ctx 全键 + atk=dot_source_atk）——
          施加时刻存件，跳伤时只读（施加者可能已离场，读现值无意义）
        - `modifier`：modifier 自身实例（stacks/duration/max_stack/modifier_id/dot_element）
        """
        te = self.effective_stats(holder)
        st = holder.actor.stats
        self_ns: Dict[str, Any] = dict(te)
        self_ns.update({
            "hp": holder.current_hp, "max_hp": te["hp"],
            "energy": holder.current_energy, "max_energy": float(st.max_energy),
            "state": holder.state_config.state if holder.state_config else "",
            "actor_id": holder.actor.actor_id, "summoner_id": holder.actor.summoner_id,
            "weakness": list(st.weakness), "resistance": dict(st.resistance),
            "toughness_bars": list(st.toughness_bars),
            "summon_flags": dict(holder.actor.summon_flags),
        })
        snapshot_ns: Dict[str, Any] = dict(mod.dot_snapshot_ctx or {})
        snapshot_ns["atk"] = float(mod.dot_source_atk)
        modifier_ns = {
            "stacks": int(mod.stacks), "duration": int(mod.duration),
            "max_stack": int(mod.max_stack), "modifier_id": mod.modifier_id,
            "dot_element": mod.dot_element,
        }
        return {"self": self_ns, "snapshot": snapshot_ns, "modifier": modifier_ns}

    def _bleed_base_multi(self, holder: ActorState) -> tuple:
        """击破裂伤基数区（bleed_base_multi zone 求值 + rank 档回传——dot_tick_base 裂伤档用）.

        min（敌人类型系数×目标生命上限, 2×3767.5533×(0.5+最大韧性/40)）；敌类型系数
        （rulebook break_effects.physical.bleed_coeff：elite 7% / normal 16%）——
        sim_schema Actor 无 rank/elite 字段，按现有最贴近的 actor_type 喂入，
        怪物（monster/enemy）一律精英档（rank 字段落地后接真实档位）。
        target_hp 取裸面板生命上限（spec 未写 effective 口径，按代码现状冻结）。
        """
        coeff_table = self._rb.break_effects["physical"].get("bleed_coeff", {})
        rank = "elite" if holder.actor.actor_type in ("monster", "enemy") else "normal"
        return self._zone("bleed_base_multi", {
            "enemy_type_coeff": coeff_table.get(rank, 0.0),
            "target_hp": holder.actor.stats.hp,
            "max_toughness": holder.actor.stats.max_toughness,
        }), rank

    def dot_tick_base(self, holder: ActorState, mod) -> float:
        """DoT 当跳基数（跳伤/引爆读数唯一事实源——dot_tick 与 dot_value 宿主函数共用）.

        基数两态（互斥）：静态 dot_ratio（float）走施加时快照 ability_multiplier ×跳伤
        时刻 max(1, stacks) 现值；dot_ratio_expr（跳伤时求值件）以持有者为语境现场求值，
        表达式值即当跳基数——不再 ×快照 atk/×stacks（层数语义由表达式自含，如奥迹
        base+inc×(stacks−1)、海瑟音裂伤 min(20%maxHP, 25%快照atk)）。
        击破裂伤（physical + BREAK_DOT_ID_PREFIX，走 bleed 链）：基数 = bleed_base_multi
        × dot_ratio（min 比较层见 _bleed_base_multi，01_formula §1.4——BE/防御等乘区
        不在基数层，属跳伤公式链）。
        空 ctx = 裸件兜底（手建 modifier 直调路径）：攻击侧全中性、倍率基数走
        dot_source_atk × dot_ratio（ability_base 求值）。
        """
        snap = mod.dot_snapshot_ctx or {}
        if getattr(mod, "dot_ratio_expr", None) is not None:
            # 跳伤时求值（持有者现值+施加者快照+自身层数语境）：表达式值即当跳基数
            return float(evaluate(mod.dot_ratio_expr,
                                  context=self._dot_tick_expr_ctx(holder, mod),
                                  rng=self.rng, trace=False).value)
        if mod.dot_element == "physical" and str(mod.modifier_id).startswith(BREAK_DOT_ID_PREFIX):
            base, _rank = self._bleed_base_multi(holder)
            return base * float(mod.dot_ratio)
        if "ability_multiplier" in snap:
            ability = float(snap["ability_multiplier"])
        else:
            ability = self._zone("ability_base", {
                "atk_scaling": mod.dot_ratio, "hp_scaling": 0.0, "def_scaling": 0.0,
                "atk": mod.dot_source_atk, "hp": 0.0, "def_": 0.0, "base_dmg_add": 0.0})
        # 叠层 DoT（桑博 1108 风化族——dot_ratio 为**每层**倍率）：跳伤基数 ×跳伤时刻层数现值
        #（快照只存每层倍率基数，层数不进施加时刻快照——层数在施加与跳伤间可变，E4 追加层族）。
        # 非叠层件 stacks 恒 1（击破裂伤/单档灼烧触电族）——×1 无观察差。
        return ability * max(1, int(getattr(mod, "stacks", 1)))

    # ------------------------------------------------------------------
    # 通用伤害结算（全数据驱动 settle——**唯一结算路径**，per-type
    # 函数已全删；数值行为逐比特不变，逐类别公式预期验收见
    # tests/test_settle_parity.py）
    #
    # 统一 AST 形态（2026-10-11 裁决）：route[category] 按当前 mode 取公式
    # → `_settle_composition` 静态分析（缓存：乘区/绑定分派 inline/const/ctx 三形态，
    # inline 乘区进 zone_refs 引用表）→ 共享 ctx 装配（formula_idents 序——取值/
    # scoped/绑定消费与旧两阶段路径同序）→ **公式大 AST 一次求值**（evaluate 带
    # zone_refs：乘区名就地求被引用子 AST——乘区在 rulebook 定义一次、子树共享），
    # ZoneRef 节点值树给乘区拆解（node 装配不再逐区手动调用）。随机流消耗序 =
    # AST 遍历序（结构确定——判定区 crit_multi 随遍历掷骰，装配阶段零随机消费）。
    # 声明词汇与语义地板的边界：表达式求值器 / 面板·桶读取器 /
    # scoped 聚合器（_scoped_boost 复用）/ 快照存取 / 目标防御解析 / 元素抗性解析
    # （_base_res 复用）/ 击破旗标 / 判定区 trace 读取 / dot_tick_base / bleed rank
    # 推导 / 事件总线 = 通用原语（谁声明都能用）；「是什么」归 rulebook 数据，
    # 「怎么跑」归本段引擎。
    # ------------------------------------------------------------------

    def settle_damage(
        self,
        category: str,
        source: Any,
        target: Any,
        *,
        action: Optional[Action] = None,
        skill_level: int = 1,
        modifier: Any = None,
        element: str = "",
        params: Optional[Dict[str, Any]] = None,
        shared: Optional[Dict[Any, Any]] = None,
    ) -> SettleResult:
        """通用伤害结算（唯一结算路径——route[category].settle + zones 取值声明驱动）.

        category：伤害类别（route 键——direct/break/super_break/elation/dot/bleed/true）。
        action/skill_level：direct 技能倍率取档（ability_base 合成）；element：本击属性
        （break/super_break/elation）；modifier：DoT 跳伤件（dot/bleed，此时 target=holder）；
        params：调用方参数槽——fixed_value/true_dmg_rate（true）、ability_multiplier/
        punchline_source（elation）、effective_toughness（super_break）、base_override/
        target_broken（direct）——各槽是否消费由类别声明决定。
        shared：AoE 攻击侧共享缓存（**opt-in 安全契约**——仅当调用方保证循环内无事件
        发射/状态改写影响攻击侧面板时传入；引擎默认不传，证据见 _SettleCtx 共享层注释）。
        """
        if self._rb.route[category].get("settle") is None:
            raise ValueError(
                f"通用 settle：route[{category!r}] 无 settle 声明"
                f"（新伤害类别 = rulebook 加 route/settle 数据，引擎零改动）")
        return _SettleCtx(self, category, source, target, action=action,
                          skill_level=skill_level, modifier=modifier,
                          element=element, params=params, shared=shared).run()

    def _settle_composition(self, category: str) -> "_SettleComposition":
        """类别组合静态分析（缓存）：公式引用的每个标识符分派三种取值形态——

        - inline：乘区进统一 AST（zone_refs 按名引用子 AST，随公式遍历序求值——
          目标侧乘区/判定区（随机源）/scoped_post 之外的全体默认形态）；
        - const：攻击侧纯件（无 scoped、无随机源、输入全攻击侧/常量/快照——
          AoE 可共享，单独求值一次 ctx 绑定；shared 缓存的承载层）；
        - ctx：快照直读（by_type.read）/ scoped_post 激活（求值后加总——保浮点
          结合序必须单独求值）/ 绑定（参数/常量/引擎原语）。
        另有同名输入冲突降级闸：两个 inline 乘区声明同名输入但取值声明不同 →
        双方降级 ctx（共享 ctx 容不下两个值——现状数据无实例，闸防未来漂移）。
        """
        key = (category, self.mode)
        cached = self._comp_cache.get(key)
        if cached is not None:
            return cached
        rb = self._rb
        formula_key = rb.route[category][self.mode]
        formula = rb.formulas[formula_key]
        idents = rb.formula_idents[formula_key]
        spec = rb.route[category]["settle"]
        scoped_set = frozenset(spec.get("scoped", ()))
        dot_family = spec.get("family") == "dot"
        binds: Dict[str, Any] = {}
        kinds: Dict[str, str] = {}
        merged_inputs: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for ident in idents:
            if ident in rb.zone_decls:
                decl = rb.zone_decls[ident]
                merged_inputs[ident] = _merged_input_decls(category, decl)
                by = (decl.get("by_type") or {}).get(category) or {}
                if "read" in by:
                    kinds[ident] = "ctx"
                elif decl.get("scoped_post") and ident in scoped_set:
                    kinds[ident] = "ctx"
                elif _zone_const_eligible(merged_inputs[ident], decl, ident, scoped_set,
                                          rb.zones[ident]):
                    kinds[ident] = "const"
                else:
                    kinds[ident] = "inline"
            elif ident in (spec.get("bind") or {}):
                kinds[ident] = "ctx"
                binds[ident] = spec["bind"][ident]
            else:
                raise ValueError(
                    f"通用 settle：公式 {formula_key!r} 标识符 {ident!r} 无取值声明"
                    f"（类别 {category!r}——zones 段加声明或 settle.bind 加绑定）")
        # 同名输入冲突降级闸
        owner: Dict[str, tuple] = {}
        demote: set = set()
        for ident in idents:
            if kinds[ident] != "inline":
                continue
            for in_name, in_decl in merged_inputs[ident].items():
                sig = repr(sorted(in_decl.items()))
                if in_name in owner and owner[in_name][1] != sig:
                    demote.add(ident)
                    demote.add(owner[in_name][0])
                else:
                    owner.setdefault(in_name, (ident, sig))
        for ident in demote:
            kinds[ident] = "ctx"
        zone_refs = {i: rb.zones[i] for i in idents if kinds[i] == "inline"}
        comp = _SettleComposition(
            category=category, formula_key=formula_key, formula=formula, idents=idents,
            kinds=kinds, zone_refs=zone_refs, merged_inputs=merged_inputs, binds=binds,
            scoped_active={i: i in scoped_set for i in idents})
        self._comp_cache[key] = comp
        return comp


_SETTLE_OMIT = object()  # node_extra 读取哨兵——该键不落入 node（ratioExpr 条件键族）


def _settle_accept(sd: Dict[str, Any]) -> Any:
    """scoped 声明 → accept 判定（通用原语）：{stats: [...]} 精确集 或 {prefix, extras} 前缀+补集."""
    stats = sd.get("stats")
    if stats is not None:
        keep = frozenset(stats)
        return lambda s: s in keep
    prefix = sd.get("prefix", "")
    extras = frozenset(sd.get("extras", ()))
    return lambda s: s.startswith(prefix) or s in extras


@dataclass(frozen=True)
class _SettleComposition:
    """类别组合（_settle_composition 静态分析产物——统一 AST 求值的结构层）."""

    category: str
    formula_key: str
    formula: PreparedExpression                    # 公式大 AST（rulebook 共享对象）
    idents: List[str]                              # 公式引用的标识符（装配序）
    kinds: Dict[str, str]                          # ident → "inline" | "const" | "ctx"
    zone_refs: Mapping[str, PreparedExpression]    # inline 乘区引用表（子 AST 共享）
    merged_inputs: Dict[str, Dict[str, Dict[str, Any]]]  # 乘区名 → by_type 合并后输入声明
    binds: Dict[str, Any]                          # 绑定声明（公式引用的非乘区标识符）
    scoped_active: Dict[str, bool]                 # 乘区 scoped 激活力（类别名单）


def _merged_input_decls(category: str, decl: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """乘区 inputs 声明的 by_type 合并（静态）：类别变体覆写基声明，by_type 键剥除."""
    out: Dict[str, Dict[str, Any]] = {}
    for in_name, in_decl0 in (decl.get("inputs") or {}).items():
        in_decl = {k: v for k, v in in_decl0.items() if k != "by_type"}
        override = (in_decl0.get("by_type") or {}).get(category)
        if override:
            in_decl.update(override)
        out[in_name] = in_decl
    return out


# const（攻击侧纯件）资格的输入源黑名单——目标侧/逐调用参数/结算输出
_CONST_BLOCK_FROM = frozenset({"target", "target_raw", "bleed_coeff", "parameter", "value"})


def _zone_const_eligible(merged_inputs: Dict[str, Dict[str, Any]], decl: Mapping[str, Any],
                         name: str, scoped_set: frozenset,
                         zone_expr: PreparedExpression) -> bool:
    """const 资格（AoE 共享候选）：无 scoped 激活、无 scoped_post、无随机源、
    输入全攻击侧/常量/快照/行动层静态源（目标侧输入/解析原语/target 族一律出局）."""
    if name in scoped_set or decl.get("scoped_post"):
        return False
    for in_decl in merged_inputs.values():
        if in_decl.get("scoped"):
            return False
        if "resolve" in in_decl:   # target_def / base_res = 目标侧解析
            return False
        if in_decl.get("from") in _CONST_BLOCK_FROM:
            return False
        if in_decl.get("from") == "broken_state" and in_decl.get("mode", "live") != "const":
            return False
    for node in ast.walk(zone_expr.tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("random", "chance")):
            return False
    return True


class _SettleCtx:
    """一次通用伤害结算的解析上下文（内部件——非 schema、不进 snapshot）.

    职责：按 route.<类别>.settle 规格与 zones 取值声明，把公式引用的每个标识符解析成值。
    取值声明字段语义见 rulebook.yaml 卷头「乘区取值声明」节；本类只实现通用源读取与
    具名解析原语，零特定乘区/伤害类别知识（类别差全部来自声明数据）。
    """

    def __init__(self, pipe: SettlementPipeline, category: str, source: Any, target: Any, *,
                 action: Optional[Action], skill_level: int, modifier: Any,
                 element: str, params: Optional[Dict[str, Any]],
                 shared: Optional[Dict[Any, Any]] = None) -> None:
        self.pipe = pipe
        self.category = category
        self.spec: Dict[str, Any] = pipe._rb.route[category]["settle"]
        self.src = pipe._as_state(source)
        self.tgt = pipe._as_state(target)
        self.action = action
        self.skill_level = skill_level
        self.mod = modifier
        self.element = element
        self.params = dict(params or {})
        # AoE 攻击侧共享缓存（opt-in）：键 ("se", id(src)) = 攻击侧有效面板；
        # 键 ("zc", category, ident, id(src), id(action), skill_level, element) = const 乘区值。
        # **安全契约**：仅当调用方保证共享窗口内无事件发射/状态改写影响攻击侧面板
        # （cond/光环可经宿主函数读任意战斗状态）时传入——引擎 AoE 目标循环在目标间
        # 发射 before_take_damage waterfall / on_hp_decrease / after_being_hit（hook 可改
        # 任意 actor 状态），故引擎默认**不传**（确定性优先于共享收益）。
        self.shared = shared
        # DoT 族（route.<类别>.settle.family: dot）：attacker_side 读取改走施加时刻快照包、
        # scoped 攻击侧携带者改走施加者反查（跳伤时刻现场值），target=持有者
        self.dot_family = self.spec.get("family") == "dot"
        self.is_crit = False
        self.value = 0.0
        self.node: Dict[str, Any] = {"formula": self.spec["node_formula"]}
        self.ctx: Dict[str, Any] = {}
        self._se: Optional[Dict[str, Any]] = None
        self._te: Optional[Dict[str, Any]] = None
        self._event: Optional[Dict[str, Any]] = None

    @property
    def se(self) -> Dict[str, Any]:
        """攻击侧有效面板（懒求值——true 族无目标侧读取，不算多余面板；shared 注入时经其记忆）."""
        if self.shared is not None:
            key = ("se", id(self.src))
            if key not in self.shared:
                self.shared[key] = self.pipe.effective_stats(self.src)
            return self.shared[key]
        if self._se is None:
            self._se = self.pipe.effective_stats(self.src)
        return self._se

    @property
    def te(self) -> Dict[str, Any]:
        if self._te is None:
            self._te = self.pipe.effective_stats(self.tgt)
        return self._te

    @property
    def event(self) -> Dict[str, Any]:
        if self._event is None:
            self._event = self._build_event()
        return self._event

    # ---- 主流程（统一 AST 求值——2026-10-11 裁决，A/B 逐比特对拍后翻转上线） ----

    def run(self) -> SettleResult:
        """统一 AST 主流程：组合静态分析 → 共享 ctx 装配（idents 序）→ 大 AST 一次求值.

        与旧两阶段路径（逐区 _zone 再喂 _formula）逐比特全等的论据：
        - inline 乘区子 AST 以同一份输入值、同一求值器求值——表达式树共享自 rulebook
          （定义一次、处处引用），ev 同序同短路语义 → 各区值逐比特同"逐区 _zone"；
        - 随机流：inline 乘区在装配段按 idents 序（= AST 首遇序）eager 求值一次
          （含未取分支——旧路径 eager 语义冻结），判定区掷骰位置与旧路径逐比特同位；
          大 AST 求值段引用回读 zone_cache，自身零随机消耗；
        - node：zone_cache 子树 trace 给 inline 区值（拆解结构自带），ctx 给直读/
          绑定/单独求值区值，键集与 node_drop/is_crit/extras 走同一份类别声明。
        """
        skipped = self._gate()
        if skipped is not None:
            return skipped
        comp = self.pipe._settle_composition(self.category)
        ctx, zone_cache = self._assemble_unified(comp)
        outcome = evaluate(comp.formula, context=ctx, rng=self.pipe.rng,
                           zone_refs=comp.zone_refs, zone_cache=zone_cache, trace=True)
        self.value = outcome.value
        zvals = zone_cache
        # isCrit：roll_check 判定区（必为 inline——随机源出 const 集）的子树 trace 读取
        for name, (zval, sub) in zvals.items():
            decl = self.pipe._rb.zone_decls.get(name) or {}
            if decl.get("roll_check"):
                self.is_crit = (bool(sub["children"][0]["value"])
                                if sub.get("kind") == "IfExp" else zval != 1.0)
        if self.spec.get("hp_deduct"):
            self.tgt.current_hp -= self.value
        # node 装配（拆解白来项——inline 区值出自 ZoneRef 节点值树，其余出自装配 ctx）
        rb = self.pipe._rb
        for ident in comp.idents:
            val = zvals[ident][0] if comp.kinds[ident] == "inline" else ctx[ident]
            key = (rb.zone_decls[ident].get("node") if ident in rb.zone_decls
                   else (comp.binds.get(ident) or {}).get("node"))
            if key and ident not in self.spec.get("node_drop", ()):
                self.node[key] = val
        for extra in self.spec.get("node_extra", ()):
            val = self._read(extra)
            if val is not _SETTLE_OMIT:
                self.node[extra["node"]] = val
        is_crit = self.spec.get("is_crit")
        if is_crit == "crit":
            self.node["isCrit"] = self.is_crit
        elif is_crit == "literal_false":
            self.node["isCrit"] = False
        return SettleResult(value=self.value, node=self.node)

    def _assemble_unified(self, comp: _SettleComposition) -> tuple:
        """共享 ctx 装配 + inline 乘区 eager 求值（公式 idents 序 = AST 首遇序）.

        返回 (ctx, zone_cache)：ctx = 乘区输入/直读/绑定值；zone_cache = inline 乘区
        的 exactly-once 求值缓存（值 + 子树 trace）——公式引用的每个 inline 乘区
        在此**全表求值一次**（含短路与三元未取分支：zone 级 eager 语义冻结，随机流
        消耗序 = 引用点首遇序），大 AST 求值时引用只回读缓存。
        """
        ctx: Dict[str, Any] = {}
        zone_cache: Dict[str, tuple] = {}
        for ident in comp.idents:
            kind = comp.kinds[ident]
            if kind == "inline":
                # inline 乘区：装配输入后**就地按 AST 首遇序求值一次**（带子树 trace——
                # 拆解/roll_check 读取源；随机流消耗序 = 本循环序）
                for in_name, in_decl in comp.merged_inputs[ident].items():
                    val = self._read(in_decl)
                    sd = in_decl.get("scoped")
                    if sd and comp.scoped_active[ident]:
                        val = val + self._scoped_total(sd)
                    if in_decl.get("wrap") == "list":
                        val = [val]
                    ctx[in_name] = val
                outcome = evaluate(comp.zone_refs[ident], context=ctx,
                                   rng=self.pipe.rng, trace=True)
                zone_cache[ident] = (outcome.value, outcome.trace)
            elif ident in comp.binds:
                ctx[ident] = self._bind_only(comp.binds[ident])
            else:
                ctx[ident] = self._zone_value_alone(ident, comp)
        return ctx, zone_cache

    def _zone_value_alone(self, name: str, comp: _SettleComposition) -> float:
        """非 inline 乘区单独求值：by_type 直读 / const（shared 记忆）/ scoped_post（结合序）."""
        rb = self.pipe._rb
        decl = rb.zone_decls[name]
        by = (decl.get("by_type") or {}).get(self.category) or {}
        if "read" in by:
            rd = dict(by["read"])
            rd.setdefault("key", name)   # snapshot 直读键缺省 = 乘区名
            value = float(self._read(rd))
        elif comp.kinds[name] == "const" and self.shared is not None:
            key = ("zc", self.category, name, id(self.src),
                   id(self.action), self.skill_level, self.element)
            if key not in self.shared:
                self.shared[key] = self._zone_eval(name, comp)
            value = self.shared[key]
        else:
            value = self._zone_eval(name, comp)
        post = decl.get("scoped_post")
        if post and comp.scoped_active[name]:
            value = value + self._scoped_total(post)
        return value

    def _zone_eval(self, name: str, comp: _SettleComposition) -> float:
        """乘区表达式独立求值（const/scoped_post/bind 合成通道）：inputs 声明凑小 ctx（+scoped 激活）."""
        merged = (comp.merged_inputs.get(name)
                  or _merged_input_decls(self.category, self.pipe._rb.zone_decls[name]))
        active = name in self.spec.get("scoped", ())
        zctx: Dict[str, Any] = {}
        for in_name, in_decl in merged.items():
            val = self._read(in_decl)
            sd = in_decl.get("scoped")
            if sd and active:
                val = val + self._scoped_total(sd)
            if in_decl.get("wrap") == "list":
                val = [val]
            zctx[in_name] = val
        return self.pipe._zone(name, zctx)

    def _bind_only(self, bd: Dict[str, Any]) -> Any:
        """非乘区标识符绑定取值（zone 合成/参数/常量/原语；node 记录归 run 末尾统一装配）."""
        if "zone" in bd:
            override = bd.get("override_param")
            if override is not None and self.params.get(override) is not None:
                return float(self.params[override])
            return self._zone_eval(bd["zone"],
                                   self.pipe._settle_composition(self.category))
        return self._read(bd)

    def _gate(self) -> Optional[SettleResult]:
        """前置跳过闸（super_break 无转换源/无削韧、elation 零倍率）：闸上下文按声明取值，
        绑定期预编译表达式判定，命中 = 返回跳过态 SettleResult（0.0 + 模板 node），
        在任何乘区求值**之前**（elation 跳过不得消耗暴击掷骰——随机流逐比特对齐）."""
        g = self.spec.get("gate")
        if not g:
            return None
        gctx = {name: self._read(d) for name, d in g["ctx"].items()}
        hit = evaluate(self.pipe._rb.settle_gates[self.category],
                       context=gctx, rng=self.pipe.rng, trace=False).value
        if not hit:
            return None
        node = {"formula": self.spec["node_formula"]}
        for k, v in g["node"].items():
            node[k] = gctx[v] if isinstance(v, str) else v
        return SettleResult(value=0.0, node=node)

    def _read(self, d: Dict[str, Any]) -> Any:
        # 输入级覆写（2026-10-11——bind 级 override_param 同构下放到输入级：声明
        # override_param 的输入在 params 携键时改读参数（大吉大利择优族 elation
        # 输入覆写首实例——rulebook elation_multi override_param: elation））
        ov = d.get("override_param")
        if ov is not None and self.params.get(ov) is not None:
            return float(self.params[ov])
        kind = d.get("from")
        if kind in ("attacker", "target"):
            panel = self.se if kind == "attacker" else self.te
            if "resolve" in d:
                return self._resolve(d["resolve"])
            if "bucket" in d:
                return panel["dmg_bonus"].get(d["bucket"], 0.0)
            if d.get("bucket_element"):
                el = self.event.get("damage_type")
                return panel["dmg_bonus"].get(el, 0.0) if el else 0.0
            if d.get("bucket_action_type"):
                at = self.event.get("action_type") or ""
                return panel["dmg_bonus"].get(f"{at}_dmg_boost", 0.0)
            return float(panel.get(d["stat"], 0.0) or 0.0)
        if kind == "attacker_side":
            # 攻击侧输入：直伤族=现场面板；DoT 族=施加时刻快照包（裸件兜底=持有者档/中性 0）
            key = d["key"]
            if self.dot_family:
                snap = getattr(self.mod, "dot_snapshot_ctx", None) or {}
                if key == "level":
                    return int(snap.get("source_level", self.tgt.actor.level))
                return float(snap.get(key, 0.0))
            if key == "level":
                return self.src.actor.level
            return float(self.se.get(key, 0.0) or 0.0)
        if kind == "snapshot":
            snap = getattr(self.mod, "dot_snapshot_ctx", None) or {}
            return float(snap.get(d["key"], d.get("default", 1.0)))
        if kind == "parameter":
            val = self.params.get(d["key"], d.get("default"))
            return float(val) if d.get("coerce") == "float" else val
        if kind == "constant":
            return float(self.pipe._rb.constants[d["key"]])
        if kind == "literal":
            return d["value"]
        if kind == "modifier":
            return getattr(self.mod, d["field"])
        if kind == "action_scaling":
            row = self._scaling_row()
            key = d["key"]
            if key == "def_":
                return row.get("def_", row.get("def", 0.0))
            return row.get(key, 0.0)
        if kind == "break_effect_table":
            return self.pipe.break_effect_of(self.element)[d["key"]]
        if kind == "bleed_coeff":
            table = self.pipe._rb.break_effects["physical"].get("bleed_coeff", {})
            return table.get(self._bleed_rank(), 0.0)
        if kind == "target_raw":
            return getattr(self.tgt.actor.stats, d["key"])
        if kind == "broken_state":
            mode = d.get("mode", "live")
            if mode == "const":
                return 1.0
            if mode == "or_param":
                return 1.0 if (self.params.get("target_broken") or self.tgt.broken) else 0.0
            return 1.0 if self.tgt.broken else 0.0
        if kind == "value":
            return self.value
        if kind == "bleed_rank":
            return self._bleed_rank()
        if kind == "dot_tick_base":
            return self.pipe.dot_tick_base(self.tgt, self.mod)
        if kind == "dot_ratio_expr_source":
            expr = getattr(self.mod, "dot_ratio_expr", None)
            return _SETTLE_OMIT if expr is None else expr.source
        raise ValueError(f"通用 settle：未知取值源 {kind!r}（声明 {d!r}）")

    def _scaling_row(self) -> Dict[str, float]:
        """行动倍率表按级取档（索引式 min(max(level-1,0),len-1)；空表 = 全 0 行）."""
        scaling = self.action.scaling if self.action is not None else []
        if not scaling:
            return {}
        return scaling[min(max(self.skill_level - 1, 0), len(scaling) - 1)]

    def _resolve(self, name: str) -> float:
        """具名解析原语：target_def（覆写优先/白板兜底）/ base_res（弱点→面板抗性→非弱点默认）."""
        if name == "target_def":
            has_override = any("def_" in m.override_effects
                               for m in self.tgt.modifiers.values())
            if self.te["def_"] > 0 or has_override:
                return self.te["def_"]
            return self.pipe._rb.constants["default_target_def"]
        if name == "base_res":
            return self.pipe._base_res(self.event.get("damage_type"), self.tgt)
        raise ValueError(f"通用 settle：未知解析原语 {name!r}")

    def _bleed_rank(self) -> str:
        """裂伤敌类型档（引擎原语——Actor 无 rank 字段，按 actor_type 最贴近喂入）."""
        return "elite" if self.tgt.actor.actor_type in ("monster", "enemy") else "normal"

    # ---- scoped 聚合（通用原语——_scoped_boost 复用；携带侧声明驱动） ----

    def _scoped_total(self, sd: Dict[str, Any]) -> float:
        carrier = self.tgt if sd.get("from") == "target" else self._scoped_attacker()
        if carrier is None:
            return 0.0   # DoT 族施加者反查未命中（裸件直调路径）——scoped 不计
        return self.pipe._scoped_boost(carrier, self.event, _settle_accept(sd), target=self.tgt)

    def _scoped_attacker(self) -> Optional[ActorState]:
        if self.dot_family:
            return self.pipe._dot_source_state(self.mod)
        return self.src

    # ---- 命中域 payload（event ctx——字段清单声明驱动，字段计算是通用原语） ----

    def _build_event(self) -> Dict[str, Any]:
        ev = self.spec.get("event") or {}
        return {f: self._event_field(f, ev.get(f)) for f in ev.get("fields", ())}

    def _event_field(self, field: str, token: Any) -> Any:
        if field == "action_type":
            return self.action.action_type if token == "action" else token
        if field == "decl_action_type":
            # 行动声明类别（elation 路由专有——本路由 action_type 喂路由 id
            # "elation_damage"（承伤 scoped 按类别判定，04_modifier §hit_condition），
            # 行动域隔离（「强化普攻期间」族）改读本字段：行动层=行动真型、hook 段=
            # 伪行动类别声明槽（pseudo action 建制流入）；无 action 直调兜底 None）
            return self.action.action_type if self.action is not None else None
        if field == "damage_type":
            if token == "action":
                return self.action.damage_type
            if token == "element":
                return self.element
            if token == "dot_element":
                return self.mod.dot_element
            return token
        if field == "target_broken":
            return True if token == "const" else self.tgt.broken
        if field == "target_controlled":
            return any(m.control_kind for m in self.tgt.modifiers.values())
        if field == "target_control_kinds":
            return [m.control_kind for m in self.tgt.modifiers.values() if m.control_kind]
        if field == "target_hp_ratio":
            return (self.tgt.current_hp / self.te["hp"]) if self.te.get("hp") else 0.0
        raise ValueError(f"通用 settle：未知 event 字段 {field!r}")
