"""伤害/治疗/效果结算器.

实现崩铁标准直伤公式（期望形式，不模拟随机暴击）。
完整公式见 docs/mechanics/02_damage_formula.md。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


@dataclass
class DamageResult:
    """伤害结算结果（含乘区拆解，供解释与调试）."""

    damage: float
    is_crit: bool = False
    damage_type: Optional[str] = None
    breakdown: Dict[str, float] = field(default_factory=dict)


class DamageResolver:
    """伤害计算与结算（标准直伤，期望暴击形式）."""

    # 怪物对非弱点属性的基础抗性
    NON_WEAKNESS_RES = 0.20

    def _ability_multi(self, action: Action, source: Actor, level: int) -> float:
        """技能倍率乘区 = atk_scaling×ATK + hp_scaling×HP + def_scaling×DEF.

        scaling 按技能等级取值，索引越界时回退到最后一档。
        scaling 字典支持键：atk / hp / def_（或 def）。
        """
        if not action.scaling:
            return 0.0
        idx = min(max(level - 1, 0), len(action.scaling) - 1)
        s = action.scaling[idx]
        st = source.stats
        return (
            s.get("atk", 0.0) * st.atk
            + s.get("hp", 0.0) * st.hp
            + (s.get("def_", s.get("def", 0.0))) * st.def_
        )

    def _dmg_boost_multi(self, action: Action, source: Actor) -> float:
        """增伤乘区 = 1 + 通用增伤 + 属性增伤 + 技能类型增伤."""
        b = source.stats.dmg_bonus
        boost = b.get("all", 0.0)
        if action.damage_type:
            boost += b.get(action.damage_type, 0.0)
        # 技能类型增伤（如 basic_dmg_boost / skill_dmg_boost / ult_dmg_boost）
        type_key = f"{action.action_type}_dmg_boost"
        boost += b.get(type_key, 0.0)
        return 1.0 + boost

    def _def_multi(self, source: Actor, target: Actor) -> float:
        """防御乘区 = (攻击者等级×10+200) / (敌方防御×max(0,1-def_pen) + 攻击者等级×10+200).

        敌方防御缺省按 200 + 10×敌人等级 估算。
        """
        attacker_const = source.level * 10 + 200
        enemy_def = target.stats.def_ if target.stats.def_ > 0 else (200 + 10 * target.level)
        def_pen = source.stats.def_pen
        effective_def = enemy_def * max(0.0, 1.0 - def_pen)
        return attacker_const / (effective_def + attacker_const)

    def _res_multi(self, action: Action, source: Actor, target: Actor) -> float:
        """抗性乘区 = 1 - clamp(目标抗性 - 抗性穿透, -1.0, 0.9)."""
        dmg_type = action.damage_type
        if dmg_type and dmg_type in target.stats.weakness:
            base_res = 0.0
        elif dmg_type in target.stats.resistance:
            base_res = target.stats.resistance[dmg_type]
        else:
            base_res = self.NON_WEAKNESS_RES
        effective_res = _clamp(base_res - source.stats.res_pen, -1.0, 0.9)
        return 1.0 - effective_res

    @staticmethod
    def _crit_expected_multi(source: Actor) -> float:
        """暴击期望乘区 = CR×(1+CD) + (1-CR)，CR 上限 100%."""
        cr = min(1.0, source.stats.crit_rate)
        cd = source.stats.crit_dmg
        return cr * (1.0 + cd) + (1.0 - cr)

    def resolve(
        self,
        action: Action,
        source: Actor,
        target: Actor,
        *,
        skill_level: int = 1,
        target_broken: bool = False,
    ) -> DamageResult:
        """计算单次直伤（期望形式）.

        Args:
            action: 技能/行动（含倍率、属性、类型）
            source: 攻击者
            target: 受击者
            skill_level: 技能等级（索引倍率表）
            target_broken: 目标是否已击破（影响韧性减伤乘区）
        """
        ability = self._ability_multi(action, source, skill_level)
        dmg_boost = self._dmg_boost_multi(action, source)
        def_multi = self._def_multi(source, target)
        res_multi = self._res_multi(action, source, target)
        base_universal = 1.0 if target_broken else 0.9
        vuln = 1.0 + target.stats.vulnerability
        crit_expected = self._crit_expected_multi(source)

        damage = (
            ability
            * dmg_boost
            * def_multi
            * res_multi
            * base_universal
            * vuln
            * crit_expected
        )

        return DamageResult(
            damage=damage,
            is_crit=False,  # 期望形式不判定单次暴击
            damage_type=action.damage_type,
            breakdown={
                "abilityMulti": ability,
                "dmgBoostMulti": dmg_boost,
                "defMulti": def_multi,
                "resMulti": res_multi,
                "baseUniversalMulti": base_universal,
                "vulnMulti": vuln,
                "critExpectedMulti": crit_expected,
            },
        )
