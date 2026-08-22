"""结算管线：两层求值 → effect 原语执行 → 伤害公式（节点值树输出）.

v0.1 范围：两层求值 + deal_damage 全公式链 + heal + drain_hp + gain/consume(能量)。
每次结算输出 (value, 节点值树)——Evaluator 的显微镜，也是对拍的对齐粒度。

公式锚点：01_formula.md 十二乘区 + base_dmg_add 基数区（决策卡 #17）；
mechanics/02_damage_formula.md 镜像。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim.state import ActorState, BattleState
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor

# 怪物对非弱点属性的基础抗性
NON_WEAKNESS_RES = 0.20

# 随机模式
MODE_EXPECTED = "expected"  # 期望值模式（不掷骰，对拍校准用）
MODE_ROLL = "roll"          # 掷骰模式（方差研究主力；种子进配置）

# pct 族 stat → 白值字段（modifier "atk_pct: 0.12" = 白值攻击 ×12%；flat 不吃百分比，游戏公式口径）
_PCT_BASE = {"atk_pct": "atk", "def_pct": "def_", "hp_pct": "hp", "spd_pct": "spd"}


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


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

    def set_aura_provider(self, fn: Any) -> None:
        """注册光环提供者（engine 注入）：fn(ActorState) -> List[Modifier]（全队 scope=team 光环）."""
        self._aura_provider = fn

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
            "effect_hit": st.effect_hit, "effect_res": st.effect_res,
            "taunt": st.taunt,
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
        return out

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
        b = se["dmg_bonus"]
        boost = b.get("all", 0.0)
        if action.damage_type:
            boost += b.get(action.damage_type, 0.0)
        boost += b.get(f"{action.action_type}_dmg_boost", 0.0)
        return 1.0 + boost

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
        attacker_const = source_level * 10 + 200
        # 覆写优先：有 modifier 把 def_ 覆写为 0 时按字面（真·零防）
        has_def_override = any("def_" in m.override_effects for m in tgt_state.modifiers.values())
        if te["def_"] > 0 or has_def_override:
            enemy_def = te["def_"]
        else:
            enemy_def = 200 + 10 * 80  # 白板假人的等级估算（旧 golden 基准）
        return attacker_const / (enemy_def * max(0.0, 1.0 - se["def_pen"]) + attacker_const)

    def effective_weakness(self, target: ActorState) -> set:
        """有效弱点 = 面板弱点 ∪ 挂身 modifier 的 weakness_add（弱点植入 debuff 族）."""
        w = set(target.actor.stats.weakness)
        for m in target.modifiers.values():
            w |= set(m.weakness_add)
        return w

    def _res_multi_eff(self, action: Action, se: Dict[str, Any], target: ActorState) -> float:
        dmg_type = action.damage_type
        if dmg_type and dmg_type in self.effective_weakness(target):
            base_res = 0.0
        elif dmg_type in target.actor.stats.resistance:
            base_res = target.actor.stats.resistance[dmg_type]
        else:
            base_res = NON_WEAKNESS_RES
        return 1.0 - _clamp(base_res - se["res_pen"], -1.0, 0.9)

    def _res_multi_for_eff(self, dmg_type: str, se: Dict[str, Any], target: ActorState) -> float:
        if dmg_type in self.effective_weakness(target):
            base_res = 0.0
        elif dmg_type in target.actor.stats.resistance:
            base_res = target.actor.stats.resistance[dmg_type]
        else:
            base_res = NON_WEAKNESS_RES
        return 1.0 - _clamp(base_res - se["res_pen"], -1.0, 0.9)

    def _crit_eff(self, se: Dict[str, Any]) -> tuple[float, bool]:
        cr = min(1.0, se["crit_rate"])
        cd = se["crit_dmg"]
        if self.mode == MODE_EXPECTED:
            return cr * (1.0 + cd) + (1.0 - cr), False
        is_crit = self.rng.random() < cr
        return (1.0 + cd) if is_crit else 1.0, is_crit

    def deal_damage(
        self,
        action: Action,
        source: Any,
        target: Any,
        *,
        skill_level: int = 1,
        target_broken: bool = False,
    ) -> SettleResult:
        """单次直伤结算（全公式链 + 节点值树；有效面板 + scoped 加成）."""
        src = self._as_state(source)
        tgt = self._as_state(target)
        se = self.effective_stats(src)
        te = self.effective_stats(tgt)

        ability = self._ability_multi_eff(action, se, skill_level)
        dmg_boost = self._dmg_boost_eff(action, se) + self._scoped_boost(src, action)
        ind_dmg_boost = 1.0 + se["dmg_bonus"].get("ind_dmg_boost", 0.0)
        def_multi = self._def_multi_eff(src.actor.level, se, te, tgt)
        res_multi = self._res_multi_eff(action, se, tgt)
        base_universal = 1.0 if (target_broken or tgt.broken) else 0.9
        vuln = 1.0 + te["vulnerability"]
        ind_vuln = 1.0 + te["dmg_bonus"].get("ind_vulnerability", 0.0)
        final_dmg = 1.0 + se["dmg_bonus"].get("final_dmg_boost", 0.0)
        crit_multi, is_crit = self._crit_eff(se)
        weaken = 1.0 - te["dmg_bonus"].get("weaken", 0.0)
        dmg_red = 1.0 - te["dmg_bonus"].get("dmg_reduction", 0.0)

        value = (
            ability * dmg_boost * ind_dmg_boost * def_multi * res_multi
            * base_universal * vuln * ind_vuln * final_dmg * crit_multi
            * weaken * dmg_red
        )
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
    ) -> float:
        """命中概率 = min(1, base × (1+效果命中) × (1-目标效果抵抗+穿透) × (1-类型抵抗))."""
        return min(1.0, base_chance * (1 + source_eff.get("effect_hit", 0.0)) * (1 - target_eff.get("effect_res", 0.0)) * (1 - type_res))

    def roll_debuff_apply(self, chance: float) -> bool:
        """debuff 施加判定：掷骰模式真判定；期望模式按 ≥0.5 生效（记录概率）."""
        if self.mode == MODE_EXPECTED:
            return chance >= 0.5
        return self.rng.random() < chance

    # ------------------------------------------------------------------
    # 其余原语（v0.1：heal / drain_hp / 能量 gain-consume）
    # ------------------------------------------------------------------

    def heal(self, source: Actor, target: ActorState, amount: float) -> SettleResult:
        """治疗结算：amount × (1 + heal_bonus)；不写防御/抗性乘区."""
        st = target.actor.stats
        bonus = 1.0 + source.stats.dmg_bonus.get("heal_bonus", 0.0)
        value = amount * bonus
        old = target.current_hp
        target.current_hp = min(st.hp, target.current_hp + value)
        return SettleResult(value=value, node={
            "formula": "heal", "amount": amount, "healBonusMulti": bonus,
            "actualAmount": target.current_hp - old,
        })

    def drain_hp(self, target: ActorState, amount: float, floor: int = 1) -> SettleResult:
        """烧血结算：保底 floor（耗不致死）."""
        actual = max(0.0, min(amount, target.current_hp - floor))
        target.current_hp -= actual
        return SettleResult(value=actual, node={
            "formula": "drain_hp", "amount": amount, "floor": floor, "actualAmount": actual,
        })

    def gain_energy(self, target: ActorState, amount: float) -> SettleResult:
        """回能：amount × energy_regen（能量恢复效率直接乘算），钳到上限."""
        st = target.actor.stats
        value = amount * st.energy_regen
        old = target.current_energy
        target.current_energy = min(st.max_energy, target.current_energy + value)
        return SettleResult(value=value, node={
            "formula": "gain_energy", "amount": amount, "regenMulti": st.energy_regen,
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
    # ------------------------------------------------------------------

    # 属性击破效果表（效果与附加伤害倍率；推条 25% 全属性通用，量子/虚数另注）
    BREAK_EFFECTS: Dict[str, Dict[str, Any]] = {
        "physical":  {"dot_ratio": None, "control": "",       "delay": 0.25, "scaling": 2.0},  # 裂伤按目标 max_hp 比例跳伤（dot_ratio=None 特判）
        "fire":      {"dot_ratio": 1.0,  "control": "",       "delay": 0.25, "scaling": 1.0},  # 灼烧 = 1.0×atk
        "ice":       {"dot_ratio": 0.0,  "control": "freeze", "delay": 0.25, "scaling": 1.0},  # 冻结：跳过行动 + 附加伤害
        "thunder":   {"dot_ratio": 2.0,  "control": "",       "delay": 0.25, "scaling": 1.0},  # 触电 = 2.0×atk
        "wind":      {"dot_ratio": 1.5,  "control": "",       "delay": 0.25, "scaling": 1.5},  # 风化 = 1.5×atk
        "quantum":   {"dot_ratio": 0.6,  "control": "entangle", "delay": 0.45, "scaling": 0.6},  # 纠缠：额外延后
        "imaginary": {"dot_ratio": 0.0,  "control": "imprison", "delay": 0.55, "scaling": 0.5},  # 禁锢：额外延后 + 减速（v0.2 减速未建模，延后代替）
    }

    LEVEL_BREAK_BASE = 3767.5533  # 等级 80 基础击破伤害常数（含等级系数）

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
        """击破瞬间的击破伤害：breakBaseMulti × (1+BE) × 防御 × 抗性 × 易伤 × 最终 × 减伤（不暴击、已击破 base_universal=1.0）."""
        eff = self.BREAK_EFFECTS.get(element, self.BREAK_EFFECTS["fire"])
        se = self.effective_stats(self._as_state(source))
        te = self.effective_stats(target)
        base = self.LEVEL_BREAK_BASE * eff["scaling"] * (0.5 + target.actor.stats.max_toughness / 40)
        be_multi = 1.0 + se["break_effect"]
        def_multi = self._def_multi_eff(source.level, se, te, target)
        res_multi = self._res_multi_for_eff(element, se, target)
        vuln = 1.0 + te["vulnerability"]
        value = base * be_multi * def_multi * res_multi * vuln
        target.current_hp -= value
        return SettleResult(value=value, node={
            "formula": "break_damage", "breakBaseMulti": base, "beMulti": be_multi,
            "defMulti": def_multi, "resMulti": res_multi, "vulnMulti": vuln,
        })

    def _res_multi_for(self, dmg_type: str, source: Actor, target: Actor) -> float:
        """按指定属性的抗性乘区（击破伤害用；击破不吃属性增伤但吃抗性）."""
        if dmg_type in target.stats.weakness:
            base_res = 0.0
        elif dmg_type in target.stats.resistance:
            base_res = target.stats.resistance[dmg_type]
        else:
            base_res = NON_WEAKNESS_RES
        return 1.0 - _clamp(base_res - source.stats.res_pen, -1.0, 0.9)

    def break_effect_of(self, element: str) -> Dict[str, Any]:
        return self.BREAK_EFFECTS.get(element, self.BREAK_EFFECTS["fire"])

    def dot_tick(self, holder: ActorState, mod) -> SettleResult:
        """DOT 跳伤（A 类结算，持有者优先级按其自身回合开始）：攻击方 atk × dot_ratio × 防御/抗性/减伤；不暴击."""
        source_atk = mod.dot_source_atk
        def_multi = 1.0  # v0.2 简化：dot 源面板在施加时快照；此处按 holder 侧乘区
        value = source_atk * mod.dot_ratio
        holder.current_hp -= value
        return SettleResult(value=value, node={
            "formula": "dot", "element": mod.dot_element, "ratio": mod.dot_ratio, "actualAmount": value,
        })

    def bleed_tick(self, holder: ActorState, mod) -> SettleResult:
        """裂伤跳伤：按目标 max_hp 比例（物理击破特判）."""
        value = holder.actor.stats.hp * 0.45 * mod.dot_ratio
        holder.current_hp -= value
        return SettleResult(value=value, node={
            "formula": "bleed", "ratio": mod.dot_ratio, "actualAmount": value,
        })
