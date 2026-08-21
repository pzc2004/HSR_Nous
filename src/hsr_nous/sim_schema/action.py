"""技能/行动定义：普攻、战技、终结技、天赋等."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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

    # 扩散副目标（Blast：主目标 + 相邻；数值锚点 docs/mechanics/04_break_system.md 基线 10/20/10）
    scaling_blast: Optional[List[Dict[str, float]]] = None  # 相邻目标倍率表（按等级）；None=与主目标相同
    toughness_dmg_blast: Optional[int] = None  # 相邻目标削韧；None=主目标一半

    # 多段（决策卡 #19 instances 的引擎层表达）：scaling/toughness_dmg 均为**每段**数值
    instances: int = 1  # 段数；>1 时逐段结算，段间目标死亡则后续段落空（鞭尸损失）

    # 自定义资源（火种/毁伤/新蕊族，决策卡 #19 资源族）
    resource_gain: Dict[str, float] = field(default_factory=dict)  # 释放后获得的自定义资源 {resource_id: amount}
    ult_cost_resource: str = ""    # 非空=特殊充能：该资源 ≥ ult_cost_amount 时终结技可激活（不走能量）
    ult_cost_amount: float = 0.0

    # 分配轴（05_effects §split）："even"=总伤按结算时存活目标数均分（逐目标各自跑公式）
    split: str = ""

    # 立即行动效果（拉条族）：非空时施放后使指定目标立即行动（"all_enemies"=敌方全体，白厄 140809 族）
    act_now_targets: str = ""

    # 施放后挂身 modifier（dict 声明→引擎物化；v1 仅 self 目标：buff 类技能通道）
    apply_modifiers: List[Dict[str, Any]] = field(default_factory=list)

    # 资源驱动段数（毁伤族，白厄 140811）：非空时段数 = 该资源当前值 × instances_per_point（消耗前读）
    instances_from_resource: str = ""
    instances_per_point: float = 1.0  # 每 1 点资源对应几段（140811：每毁伤 4 段）
    instances_cap: int = 0            # 段数上限（140811：总倍率上限换算 26 段；0=无上限）
    consume_all_resource: str = ""    # 非空时施放后消耗该资源全部当前值（段数已先读）

    # 净化（解除自身所有可驱散负面，140811 族）
    cleanse_self: bool = False
