"""结算管线：两层求值 → effect 原语执行 → 伤害公式（节点值树输出）.

v0.1 范围：两层求值 + deal_damage 全公式链 + heal + drain_hp + gain/consume(能量)。
每次结算输出 (value, 节点值树)——Evaluator 的显微镜，也是对拍的对齐粒度。

公式锚点：01_formula.md 十二乘区 + base_dmg_add 基数区（决策卡 #17）；
mechanics/02_damage_formula.md 镜像。

公式执行形态（B27 迁移）：公式链零 Python 算术——全部表达式来自 rulebook
（`sim_schema/rulebook.yaml`，01_formula 的可执行唯一来源），绑定期白名单
预编译，此处只带 context 求值（决策卡 A1：引擎零数值常数）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim.state import ActorState, BattleState
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor
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
        self._rb = get_rulebook()  # 公式簿（绑定期已预编译；此处只取句柄）

    def set_aura_provider(self, fn: Any) -> None:
        """注册光环提供者（engine 注入）：fn(ActorState) -> List[Modifier]（全队 scope=team 光环）."""
        self._aura_provider = fn

    # ------------------------------------------------------------------
    # rulebook 求值（热循环：预编译 AST + context）
    # ------------------------------------------------------------------

    def _zone(self, name: str, ctx: Dict[str, Any]) -> float:
        """乘区求值：rulebook 表达式 + 本结算 context."""
        return evaluate(self._rb.zones[name], context=ctx, rng=self.rng).value

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

    def effective_stats(self, actor_state: ActorState) -> Dict[str, Any]:
        """有效面板 = Layer 1（base + Σ modifier flat）→ Layer 2（转化 → 覆写）.

        防二次转化循环：转化读取的是 source 的 Layer 1，不读 effective。
        光环（scope=team）：provider 提供的全队光环 stat_effects 并入 Layer 1
        （pct 族按目标白值乘算，与 Layer 1.5 同口径）。
        """
        st = actor_state.actor.stats
        l1: Dict[str, Any] = {
            "hp": st.hp, "atk": st.atk, "def_": st.def_, "spd": st.spd,
            "crit_rate": st.crit_rate, "crit_dmg": st.crit_dmg,
            "def_pen": st.def_pen, "res_pen": st.res_pen,
            "vulnerability": st.vulnerability,
            "energy_regen": st.energy_regen,
            "break_effect": st.break_effect,
            "break_efficiency_boost": st.break_efficiency_boost,
            "weakness_break_efficiency_boost": st.weakness_break_efficiency_boost,
            "effect_hit": st.effect_hit, "effect_res": st.effect_res,
            "taunt": self._base_taunt(actor_state.actor),
            "heal_bonus": st.heal_bonus, "shield_bonus": st.shield_bonus,
            "dmg_bonus": dict(st.dmg_bonus),
        }
        # Layer 1：modifier flat 贡献（scoped 件跳过——它们的加成在命中域按条件计）
        # pct 族（atk_pct/def_pct/hp_pct/spd_pct）不进 l1 加算——它们的基数是**白值**（st.*），
        # 单独汇总后在 Layer 1.5 应用（游戏公式：面板 = 白值×(1+Σpct) + Σflat，flat 不吃百分比）
        pct_pool: Dict[str, float] = {}
        held = list(actor_state.modifiers.values())
        if self._aura_provider is not None:
            held = held + list(self._aura_provider(actor_state))
        for mod in held:
            if mod.hit_condition_expr is not None:
                continue
            for stat, val in mod.stat_effects.items():
                if stat in _PCT_BASE:
                    pct_pool[stat] = pct_pool.get(stat, 0.0) + val
                else:
                    self._add_eff(l1, stat, val)

        out = dict(l1)
        out["dmg_bonus"] = dict(l1["dmg_bonus"])
        # Layer 1.5：pct 族 = 白值 × (1+Σpct) + flat（l1 已含 flat，故 out = l1 + 白值×Σpct）
        for stat, pct in pct_pool.items():
            base_stat = _PCT_BASE[stat]
            out[base_stat] = out.get(base_stat, 0.0) + getattr(st, base_stat) * pct
        # Layer 2a：转化（scaling_effects：stat += source_L1 × ratio）
        for mod in actor_state.modifiers.values():
            for stat, (src, ratio) in mod.scaling_effects.items():
                if src in l1:
                    out[stat] = out.get(stat, 0.0) + l1[src] * ratio
        # Layer 2b：覆写（override_effects：stat = value）
        for mod in actor_state.modifiers.values():
            for stat, val in mod.override_effects.items():
                out[stat] = val
        # 嘲讽派生（mechanics 10）：taunt_eff = base × (1 + Σ aggro_boost 池)
        out["taunt_eff"] = out["taunt"] * (1.0 + out.get("aggro_boost", 0.0))
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
        if not action.scaling:
            return 0.0
        idx = min(max(level - 1, 0), len(action.scaling) - 1)
        s = action.scaling[idx]
        return (
            s.get("atk", 0.0) * se["atk"]
            + s.get("hp", 0.0) * se["hp"]
            + s.get("def_", s.get("def", 0.0)) * se["def_"]
        )

    def _dmg_boost_eff(self, action: Action, se: Dict[str, Any]) -> float:
        """增伤乘区：三个 dmg_bonus 桶的命中解析（引擎侧语义）+ rulebook 表达式求值."""
        b = se["dmg_bonus"]
        return self._zone("dmg_boost_multi", {
            "all_dmg_bonus": b.get("all", 0.0),
            "elemental_dmg_bonus": b.get(action.damage_type, 0.0) if action.damage_type else 0.0,
            "type_dmg_bonus": b.get(f"{action.action_type}_dmg_boost", 0.0),
        })

    def _scoped_boost(self, source: ActorState, action: Action) -> float:
        """hit_condition scoped 加成：条件命中才计入的增伤（§4.2 组合原语）."""
        total = 0.0
        ctx = {"action_type": action.action_type, "damage_type": action.damage_type}
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
                    if stat.startswith("dmg_") or stat == "all_dmg":
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
    ) -> SettleResult:
        """单次直伤结算（全公式链 + 节点值树；有效面板 + scoped 加成）.

        公式链 = rulebook 表达式求值（route["direct"] → damage / damage_expected）；
        本方法只做面板→context 的喂入与节点值树拼装，零公式算术。
        """
        src = self._as_state(source)
        tgt = self._as_state(target)
        se = self.effective_stats(src)
        te = self.effective_stats(tgt)

        ability = self._ability_multi_eff(action, se, skill_level)
        dmg_boost = self._dmg_boost_eff(action, se) + self._scoped_boost(src, action)
        ind_dmg_boost = self._zone("ind_dmg_boost_multi", {
            "ind_dmg_bonus": se["dmg_bonus"].get("ind_dmg_boost", 0.0)})
        def_multi = self._def_multi_eff(src.actor.level, se, te, tgt)
        res_multi = self._res_multi_eff(action, se, tgt)
        # 韧性状态喂入：broken 旗标为准（虚韧性条期间 toughness>0 仍是击破态——
        # 忘归人 122504；spec 表达式同口径，见 01_formula base_universal_multi）
        base_universal = self._zone("base_universal_multi", {
            "target_broken": 1.0 if (target_broken or tgt.broken) else 0.0})
        vuln = self._zone("vuln_multi", {"vulnerability": te["vulnerability"]})
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
    # 效果命中判定（§4.7：debuff/dot/control 施加前概率闸）
    # ------------------------------------------------------------------

    def hit_chance(
        self,
        source_eff: Dict[str, Any],
        target_eff: Dict[str, Any],
        base_chance: float,
        type_res: float = 0.0,
        effect_res_pen: float = 0.0,
    ) -> float:
        """命中概率：rulebook `ehr_multi` 表达式求值（01_formula dot_damage parameters 同式）.

        = min(1, base × (1+效果命中) × (1 − 目标效果抵抗 + 效果抵抗穿透) × (1 − 类型抵抗)).
        effect_res_pen：效果抵抗穿透（独立参数槽——modifier 面板经调用方 se.get("effect_res_pen") 喂入）.
        """
        return self._zone("ehr_multi", {
            "base_chance": base_chance,
            "effect_hit": source_eff.get("effect_hit", 0.0),
            "target_effect_res": target_eff.get("effect_res", 0.0),
            "effect_res_pen": effect_res_pen,
            "type_res": type_res,
        })

    def roll_debuff_apply(self, chance: float) -> bool:
        """debuff 施加判定：掷骰模式真判定；期望模式按 ≥0.5 生效（记录概率）."""
        if self.mode == MODE_EXPECTED:
            return chance >= 0.5
        return self.rng.random() < chance

    # ------------------------------------------------------------------
    # 其余原语（v0.1：heal / drain_hp / 能量 gain-consume）
    # ------------------------------------------------------------------

    def heal(self, source: Any, target: ActorState, amount: float = 0.0, *,
             atk_scaling: float = 0.0, hp_scaling: float = 0.0) -> SettleResult:
        """治疗结算：rulebook `heal` 公式唯一路径（mechanics 01 §1.3）.

        治疗量 = (atk_scaling×atk + hp_scaling×hp + flat_heal) × (1 + heal_bonus + incoming_heal)
        - atk/hp：施放者有效面板（治疗倍率按施放者属性缩放）
        - heal_bonus（Outgoing_Healing_Boost）：**施放者** effective_stats
        - incoming_heal（受治疗量变化——加成为正、降低为负，如萨姆领域）：**受疗者** effective_stats
        封顶 = 受疗者有效生命上限（与 engine heal_self/复活同口径）。
        事件（on_hp_increase）由调用方（引擎侧）发射——pipeline 纯结算不持 bus。
        """
        src = self._as_state(source)
        tgt = self._as_state(target)
        se = self.effective_stats(src)
        te = self.effective_stats(tgt)
        heal_bonus = se.get("heal_bonus", 0.0)
        incoming_heal = te.get("incoming_heal", 0.0)
        value = evaluate(self._rb.formulas["heal"], context={
            "atk_scaling": atk_scaling, "atk": se["atk"],
            "hp_scaling": hp_scaling, "hp": se["hp"],
            "flat_heal": amount,
            "heal_bonus": heal_bonus,
            "incoming_heal": incoming_heal,
        }, rng=self.rng).value
        old = tgt.current_hp
        tgt.current_hp = min(te["hp"], tgt.current_hp + value)
        return SettleResult(value=value, node={
            "formula": "heal", "amount": amount,
            "healBonusMulti": 1.0 + heal_bonus + incoming_heal,
            "actualAmount": tgt.current_hp - old,
        })

    def drain_hp(self, target: ActorState, amount: float, floor: int = 1) -> SettleResult:
        """烧血结算：保底 floor（耗不致死）.

        发射点约定：HP 下降事件 on_hp_decrease（reason='drain'，05_effects:509）由调用方
        （引擎侧）在调用处发射——pipeline 纯结算不持 bus；当前无引擎调用点
        （drain_hp effect 原语待收编，收编时在引擎调用处接线发射）。
        """
        actual = max(0.0, min(amount, target.current_hp - floor))
        target.current_hp -= actual
        return SettleResult(value=actual, node={
            "formula": "drain_hp", "amount": amount, "floor": floor, "actualAmount": actual,
        })

    def gain_energy(self, target: ActorState, amount: float, *, err_exempt: bool = False) -> SettleResult:
        """回能：amount × energy_regen（能量恢复效率直接乘算），钳到上限.

        err_exempt=True 为具名豁免（mechanics 05 §5.3 清单）：不乘 ERR，regenMulti 记 1.0。
        """
        st = target.actor.stats
        regen = 1.0 if err_exempt else st.energy_regen
        value = amount * regen
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

    def toughness_damage_amount(self, source: Optional[ActorState], base_toughness: float) -> float:
        """实际削韧量 = rulebook toughness_damage 公式求值（调用点在 engine._apply_toughness_damage）.

        spec 双池乘算：(1 + break_efficiency_boost) × (1 + weakness_break_efficiency_boost)
        （01_formula §1.5；池结构实测待确认——B19"削韧效率池结构"行在案）。
        fixed_toughness_dmg：引擎/模板尚无固定削韧概念，中性 0 喂入（不新造机制）。
        含光环辐射（effective_stats 统一生效面）；source=None 时双池取 0。
        """
        se = self.effective_stats(source) if source is not None else {}
        return evaluate(self._rb.formulas["toughness_damage"], context={
            "base_toughness": base_toughness,
            "break_efficiency_boost": se.get("break_efficiency_boost", 0.0),
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
        if not can_reduce or target.broken:
            return SettleResult(value=0.0, node={"formula": "toughness", "actualAmount": 0.0})
        old = target.toughness
        target.toughness = max(0.0, target.toughness - amount)
        return SettleResult(value=old - target.toughness, node={
            "formula": "toughness", "element": element, "actualAmount": old - target.toughness,
        })

    def break_damage(self, source: Actor, target: ActorState, element: str) -> SettleResult:
        """击破瞬间的击破伤害（route["break"] → break_damage 公式链求值）.

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
        vuln = self._zone("vuln_multi", {"vulnerability": te["vulnerability"]})
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

    def dot_tick(self, holder: ActorState, mod) -> SettleResult:
        """DOT 跳伤（A 类结算，持有者优先级按其自身回合开始）：快照口径 = 施加者 atk 快照 × dot_ratio，不暴击.

        v0.2 快照口径零乘区——防御/抗性/减伤等乘区不结算（dot 源面板在施加时快照）；
        rulebook `dot_damage` 式已入簿备镜，接线待办（乘区接入时本式退役）。
        """
        source_atk = mod.dot_source_atk
        def_multi = 1.0  # v0.2 简化：dot 源面板在施加时快照；此处按 holder 侧乘区
        value = source_atk * mod.dot_ratio
        holder.current_hp -= value
        return SettleResult(value=value, node={
            "formula": "dot", "element": mod.dot_element, "ratio": mod.dot_ratio, "actualAmount": value,
        })

    def bleed_tick(self, holder: ActorState, mod) -> SettleResult:
        """裂伤跳伤：rulebook `bleed_base_multi` 求值（01_formula §1.4）.

        裂伤式 = min（敌人类型系数×目标生命上限, 2×3767.5533×(0.5+最大韧性/40)）——
        min 结果整体替代通用框架的 level_base×effect_multiplier（cap 在基数层比较）；
        跳伤 = 基数 × mod.dot_ratio（击破裂伤 ratio=1.0，其他裂伤源经 ratio 缩放）。
        v0.2 简化口径：不乘 vuln/def/res（与 dot_tick 的快照简化同口径）。
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
        value = base * mod.dot_ratio
        holder.current_hp -= value
        return SettleResult(value=value, node={
            "formula": "bleed", "ratio": mod.dot_ratio, "bleedBaseMulti": base,
            "enemyType": rank, "actualAmount": value,
        })
