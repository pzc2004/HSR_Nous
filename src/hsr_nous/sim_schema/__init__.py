"""仿真器数据模型（Schema）：战斗模拟器专用的输入格式定义."""

from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.encounter import Cycle, Encounter, FormulaConfig, TerminationConfig, Wave
from hsr_nous.sim_schema.modifiers import Modifier
from hsr_nous.sim_schema.policy import Policy, PolicyRule, TargetRule, TimingRule
from hsr_nous.sim_schema.validator import (
    ValidationError,
    ValidationResult,
    validate_encounter,
    validate_modifier,
)

__all__ = [
    "Actor",
    "StatBlock",
    "Action",
    "Cycle",
    "Encounter",
    "FormulaConfig",
    "TerminationConfig",
    "Wave",
    "Modifier",
    "Policy",
    "PolicyRule",
    "TargetRule",
    "TimingRule",
    "ValidationError",
    "ValidationResult",
    "validate_encounter",
    "validate_modifier",
]
