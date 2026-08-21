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


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


@dataclass
class SettleResult:
    """结算结果：值 + 节点值树（每次结算的对拍对齐粒度）."""

    value: float
    node: Dict[str, Any] = field(default_factory=dict)


class SettlementPipeline:
    """结算管线（v0.1：直伤闭环）."""

    def __init__(self, mode: str = MODE_ROLL, seed: Optional[int] = None) -> None:
        assert mode in (MODE_EXPECTED, MODE_ROLL)
        self.mode = mode
        # 掷骰为默认模式（真暴击判定）；随机性种子化——缺省固定种子 0 保证可复现
        self.rng = random.Random(seed if seed is not None else 0)

    # ------------------------------------------------------------------
    # 两层属性求值（v0.1：effective = base + flat；转化/覆写后置）
    # ------------------------------------------------------------------

    def effective_stats(self, actor: Actor) -> Dict[str, float]:
        """两层求值的有效面板（v0.1 简式：base ± flat_bonus）.

        完整两层模型（§4.10：Layer 2 转化/覆写读 source Layer 1）后置 v0.2；
        v0.1 白板场景 = StatBlock 原值。
        """
        st = actor.stats
        return {
            "hp": st.hp, "atk": st.atk, "def": st.def_, "spd": st.spd,
            "crit_rate": st.crit_rate, "crit_dmg": st.crit_dmg,
            "def_pen": st.def_pen, "res_pen": st.res_pen,
            "vulnerability": st.vulnerability,
            "energy_regen": st.energy_regen,
        }

    # ------------------------------------------------------------------
    # 伤害公式（十二乘区 + base_dmg_add）
    # ------------------------------------------------------------------

    def _ability_multi(self, action: Action, source: Actor, level: int) -> float:
        """技能倍率乘区 = atk×倍率 + hp×倍率 + def×倍率（+ Σbase_dmg_add 后置）."""
        if not action.scaling:
            return 0.0
        idx = min(max(level - 1, 0), len(action.scaling) - 1)
        s = action.scaling[idx]
        st = source.stats
        return (
            s.get("atk", 0.0) * st.atk
            + s.get("hp", 0.0) * st.hp
            + s.get("def_", s.get("def", 0.0)) * st.def_
        )

    def _dmg_boost_multi(self, action: Action, source: Actor) -> float:
        """增伤乘区 = 1 + 通用增伤 + 属性增伤 + 类别增伤（action_type + tags 命中各档求和）."""
        b = source.stats.dmg_bonus
        boost = b.get("all", 0.0)
        if action.damage_type:
            boost += b.get(action.damage_type, 0.0)
        boost += b.get(f"{action.action_type}_dmg_boost", 0.0)
        return 1.0 + boost

    def _def_multi(self, source: Actor, target: Actor) -> float:
        """防御乘区 = (攻击方等级×10+200) / (目标防御×max(0,1-def_pen) + 攻击方等级×10+200)."""
        attacker_const = source.level * 10 + 200
        enemy_def = target.stats.def_ if target.stats.def_ > 0 else (200 + 10 * target.level)
        def_pen = source.stats.def_pen
        return attacker_const / (enemy_def * max(0.0, 1.0 - def_pen) + attacker_const)

    def _res_multi(self, action: Action, source: Actor, target: Actor) -> float:
        """抗性乘区 = 1 - clamp(有效抗性, -1.0, 0.9)；有效抗性 = 目标抗性 - res_pen."""
        dmg_type = action.damage_type
        if dmg_type and dmg_type in target.stats.weakness:
            base_res = 0.0
        elif dmg_type in target.stats.resistance:
            base_res = target.stats.resistance[dmg_type]
        else:
            base_res = NON_WEAKNESS_RES
        return 1.0 - _clamp(base_res - source.stats.res_pen, -1.0, 0.9)

    def _crit_multi(self, source: Actor) -> tuple[float, bool]:
        """暴击乘区：掷骰模式 = 真判定（1+CD 或 1）；期望模式 = CR×(1+CD)+(1-CR)."""
        cr = min(1.0, source.stats.crit_rate)
        cd = source.stats.crit_dmg
        if self.mode == MODE_EXPECTED:
            return cr * (1.0 + cd) + (1.0 - cr), False
        is_crit = self.rng.random() < cr
        return (1.0 + cd) if is_crit else 1.0, is_crit

    def deal_damage(
        self,
        action: Action,
        source: Actor,
        target: Actor,
        *,
        skill_level: int = 1,
        target_broken: bool = False,
    ) -> SettleResult:
        """单次直伤结算（全公式链 + 节点值树）."""
        ability = self._ability_multi(action, source, skill_level)
        dmg_boost = self._dmg_boost_multi(action, source)
        ind_dmg_boost = 1.0 + source.stats.dmg_bonus.get("ind_dmg_boost", 0.0)
        def_multi = self._def_multi(source, target)
        res_multi = self._res_multi(action, source, target)
        base_universal = 1.0 if target_broken else 0.9
        vuln = 1.0 + target.stats.vulnerability
        ind_vuln = 1.0 + target.stats.dmg_bonus.get("ind_vulnerability", 0.0)
        final_dmg = 1.0 + source.stats.dmg_bonus.get("final_dmg_boost", 0.0)
        crit_multi, is_crit = self._crit_multi(source)
        weaken = 1.0 - target.stats.dmg_bonus.get("weaken", 0.0)
        dmg_red = 1.0 - target.stats.dmg_bonus.get("dmg_reduction", 0.0)

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
