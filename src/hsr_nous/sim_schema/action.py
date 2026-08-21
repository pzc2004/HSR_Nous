"""技能/行动定义：普攻、战技、终结技、天赋等."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Action:
    """技能/行动."""

    action_id: str
    name: str
    action_type: str  # "basic", "skill", "ultimate", "talent", "follow_up", "elation_damage"
    target_type: str  # "single", "blast", "aoe", "self", "ally_single", "ally_aoe"
    damage_type: Optional[str] = None  # "physical", "fire", "ice", "thunder", "wind", "quantum", "imaginary"

    # 技能倍率（按等级）
    scaling: List[Dict[str, float]] = field(default_factory=list)

    # 能量
    energy_cost: int = 0      # 终结技能量消耗
    energy_gain: Optional[int] = None  # 释放后获得的能量；None=按 action_type 默认（普攻20/战技30），显式 0=不回能

    # 战技点
    skill_point_cost: int = 0  # 战技点消耗（普攻=-1回复，战技=1消耗）
    skill_point_gain: int = 0  # 战技点获取（普攻默认+1）

    # 削韧值（击破系统核心参数）
    toughness_dmg: int = 0     # 削韧值（普攻10, 战技20, 终结技30）
