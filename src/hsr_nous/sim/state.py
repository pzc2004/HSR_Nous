"""战斗全状态：可序列化的战场快照（纯净不变量的载体）.

设计约束：一切运行时状态都必须是纯数据（dataclass + 基本类型），
snapshot() 可逐字段比对——两局全等验证就靠它。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim_schema.actor import Actor


@dataclass
class Modifier:
    """挂在身上的状态件（buff/debuff/dot/control，v0.2 基础层）.

    duration：剩余时长（携带者回合 tick，0 = 永久）；stacks：层数。
    """

    modifier_id: str
    name: str
    modifier_type: str          # "buff" | "debuff" | "dot" | "control"
    debuff_kind: str = ""       # dot 类子类型（"dot"）/ 控制类（"control"）
    duration: int = 0
    stacks: int = 1
    source_id: str = ""         # 施加者 actor_id
    stat_effects: Dict[str, float] = field(default_factory=dict)  # stat → flat 值
    dot_element: str = ""       # dot 跳伤属性（dot 类用）
    dot_ratio: float = 0.0      # dot 跳伤 = 施加者 atk 快照 × dot_ratio（裂伤特判：× 目标 max_hp × 0.45 × ratio）
    dot_source_atk: float = 0.0  # dot 施加者攻击快照（跳伤基数）
    control_kind: str = ""      # "freeze"（跳过行动）/ "imprison"（禁锢：推条）/ "entangle"（纠缠：推条）

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
