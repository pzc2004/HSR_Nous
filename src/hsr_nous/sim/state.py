"""战斗全状态：可序列化的战场快照（纯净不变量的载体）.

设计约束：一切运行时状态都必须是纯数据（dataclass + 基本类型），
snapshot() 可逐字段比对——两局全等验证就靠它。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim_schema.actor import Actor


@dataclass
class StateConfig:
    """形态配置（#20 糖化：形态 = 标记 modifier，本配置驱动合法性注入）.

    replaces_actions：形态下行动替换映射（如 basic → enhanced_basic）；
    locked_actions：形态下禁用的行动类型；
    exit_conditions：退出条件 [{trigger, value}]（on_action_count/on_resource_depleted）；
    stat_effects：形态内面板加成（并进标记 modifier——白厄"攻击力提高 X%"族）；
    final_action_id：倒计时最后一动强制施放的行动（白厄"最后的额外回合开始时立即发动最后一击"）；
    exit_remove_modifiers：退出形态时对**全体敌人**移除的 modifier_id 清单（境界植入件随形态解除）；
    banish_allies_on_enter：进入形态时其他队友离场且无法行动（白厄境界族；退出时回场）；
    countdown_spd_ratio：倒计时回合速度 = 基础速度 × 该比值（白厄"速度固定为基础速度的 60%"）；
    name：形态显示名（日志用中文官方名，如"卡厄斯兰那"；缺省回退 state 标识符）。
    """

    state: str
    replaces_actions: Dict[str, Any] = field(default_factory=dict)  # type→id 或 id 列表（多强化技能，140809/140811 族）
    locked_actions: List[str] = field(default_factory=list)
    exit_conditions: List[Dict[str, Any]] = field(default_factory=list)
    stat_effects: Dict[str, float] = field(default_factory=dict)
    final_action_id: str = ""
    exit_remove_modifiers: List[str] = field(default_factory=list)
    banish_allies_on_enter: bool = False
    countdown_spd_ratio: float = 1.0
    name: str = ""

    def marker_id(self) -> str:
        return f"STATE_{self.state}"


@dataclass
class Modifier:
    """挂在身上的状态件（buff/debuff/dot/control，v0.4 完整生命周期）.

    duration：剩余时长（携带者回合 tick，0 = 永久）；stacks：层数。
    stack_mode：refresh（重置时长+1层）| independent（每层独立计时，v0.4 视同 refresh 时长）
    | replace（新实例整换旧实例）| set（层数设为 stacks_value）。
    """

    modifier_id: str
    name: str
    modifier_type: str          # "buff" | "debuff" | "dot" | "control"
    debuff_kind: str = ""       # dot 类子类型（"dot"）/ 控制类（"control"）
    duration: int = 0
    stacks: int = 1
    max_stack: int = 99
    stack_mode: str = "refresh"
    stacks_value: float = 0.0   # stack_mode == "set" 时的目标层数
    dispellable: bool = True
    singleton_group: str = ""   # 同目标同组互斥（新挂替换旧挂）
    source_id: str = ""         # 施加者 actor_id
    stat_effects: Dict[str, float] = field(default_factory=dict)  # stat → flat 值（Layer 1）
    scaling_effects: Dict[str, tuple[str, float]] = field(default_factory=dict)  # stat → (source_stat, ratio)（Layer 2 转化）
    override_effects: Dict[str, float] = field(default_factory=dict)  # stat → 覆写值（Layer 2 覆写）
    hit_condition_expr: object = None   # 命中域条件（PreparedExpression，scoped 加成用）
    dot_element: str = ""       # dot 跳伤属性（dot 类用）
    dot_ratio: float = 0.0      # dot 跳伤 = 施加者 atk 快照 × dot_ratio（裂伤特判：× 目标 max_hp × 0.45 × ratio）
    dot_source_atk: float = 0.0  # dot 施加者攻击快照（跳伤基数）
    control_kind: str = ""      # "freeze"（跳过行动）/ "imprison"（禁锢：推条）/ "entangle"（纠缠：推条）
    weakness_add: List[str] = field(default_factory=list)  # 弱点植入（B25 stat 本体；判定走 pipeline.effective_weakness）

    def snapshot(self) -> Dict[str, Any]:
        return {
            "modifier_id": self.modifier_id,
            "type": self.modifier_type,
            "duration": self.duration,
            "stacks": self.stacks,
            "source_id": self.source_id,
        }


@dataclass
class ActorState:
    """单个参战单位的运行时状态."""

    actor: Actor
    current_hp: float
    current_energy: float = 0.0
    alive: bool = True
    banished: bool = False  # 放逐/离场（选择器统一排除；AV 冻结由 scheduler 处理）
    broken: bool = False    # 已击破（base_universal = 1.0，无韧性减伤）
    toughness: float = 0.0  # 当前韧性（敌人用；0 = 满条的初始值由引擎按 max_toughness 填）
    modifiers: Dict[str, Modifier] = field(default_factory=dict)  # modifier_id → 实例
    resources: Dict[str, float] = field(default_factory=dict)  # 自定义资源（trigger_limit 计数器等）
    state_config: Optional[StateConfig] = None  # 当前形态（None = 常态）

    def snapshot(self) -> Dict[str, Any]:
        return {
            "actor_id": self.actor.actor_id,
            "current_hp": round(self.current_hp, 4),
            "current_energy": round(self.current_energy, 4),
            "alive": self.alive,
            "banished": self.banished,
            "broken": self.broken,
            "toughness": round(self.toughness, 4),
            "modifiers": {k: self.modifiers[k].snapshot() for k in sorted(self.modifiers)},
            "resources": {k: round(v, 4) for k, v in sorted(self.resources.items())},
            "state": self.state_config.state if self.state_config else "normal",
        }


@dataclass
class BattleState:
    """整场战斗的运行时状态（纯数据）."""

    actors: Dict[str, ActorState] = field(default_factory=dict)  # actor_id → 状态
    clock: float = 0.0          # 全局时钟（绝对时刻）
    turn_count: int = 0         # 已完成的行动数
    cycle_av: float = 0.0       # 累计消耗 AV（轮次/终止判断）
    total_damage: float = 0.0
    damage_by_actor: Dict[str, float] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)  # 战斗日志（11_combat_log 格式）

    def snapshot(self) -> Dict[str, Any]:
        return {
            "clock": round(self.clock, 4),
            "turn_count": self.turn_count,
            "cycle_av": round(self.cycle_av, 4),
            "total_damage": round(self.total_damage, 4),
            "damage_by_actor": {k: round(v, 4) for k, v in sorted(self.damage_by_actor.items())},
            "actors": {k: self.actors[k].snapshot() for k in sorted(self.actors)},
        }
