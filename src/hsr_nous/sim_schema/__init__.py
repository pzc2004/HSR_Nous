"""仿真器数据模型（Schema）：战斗模拟器专用的输入格式定义."""

from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.encounter import Cycle, Encounter, TerminationConfig
from hsr_nous.sim_schema.policy import Policy, PolicyRule, TargetRule

__all__ = [
    "Actor",
    "StatBlock",
    "Action",
    "Cycle",
    "Encounter",
    "TerminationConfig",
    "Policy",
    "PolicyRule",
    "TargetRule",
]
