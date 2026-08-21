"""能量资源三段式.

标准能量模型：阈值 = max_energy（或 action.energy_cost），激活 = 满即可大。
特殊充能（ult_cost_resource 非空）：自定义资源达量激活（白厄火种/遐蝶新蕊族），不走能量。
完整三段式（阈值≠上限/激活提供值/银行）按 §16 章后置。
"""
from __future__ import annotations

from typing import Optional

from hsr_nous.sim.state import ActorState
from hsr_nous.sim_schema.action import Action


def ult_threshold_of(action: Optional[Action], actor_max_energy: float) -> float:
    """终结技激活阈值：优先 action.energy_cost，缺省 = max_energy."""
    if action is not None and action.energy_cost > 0:
        return float(action.energy_cost)
    return float(actor_max_energy)


def ultimate_available(state: ActorState, ult_action: Optional[Action]) -> bool:
    """能量满即可大；特殊充能（ult_cost_resource 非空）走资源门槛不走能量."""
    if ult_action is None:
        return False
    if ult_action.ult_cost_resource:
        return state.resources.get(ult_action.ult_cost_resource, 0.0) >= ult_action.ult_cost_amount
    return state.current_energy >= ult_threshold_of(ult_action, state.actor.stats.max_energy)


def cast_cost(ult_action: Optional[Action], actor_max_energy: float) -> float:
    """开大能耗（v0.1 = 阈值全扣）."""
    return ult_threshold_of(ult_action, actor_max_energy)
