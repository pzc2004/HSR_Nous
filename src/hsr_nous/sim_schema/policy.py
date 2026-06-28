"""策略模型：可执行、可参数化、可搜索的战斗策略定义。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class PolicyRule:
    """单条策略规则：条件 -> 动作."""

    condition: str
    """条件表达式，如 "energy >= ULT_THRESHOLD"、"buff.stack >= 3"."""

    action: str
    """动作类型："ultimate" | "skill" | "basic" | "pass"."""

    priority: int = 0
    """规则优先级，数字大的优先匹配."""

    description: str = ""
    """人类可读描述，用于 LLM 生成和可解释输出."""


@dataclass
class TargetRule:
    """目标选择规则：条件 -> 目标选择器.

    selector 支持两种形式：
    1. 字符串：引用预注册的选择器，如 "lowest_hp"
    2. 字典：参数化选择器，如 {"type": "min", "key": "stats.hp"}
    """

    condition: str
    """条件表达式."""

    selector: Union[str, Dict[str, Any]]
    """目标选择器.

    字符串形式（预注册）：
        "primary_target" | "self" | "lowest_hp" | "lowest_hp_pct" |
        "highest_hp" | "highest_hp_pct" | "highest_atk" | "highest_spd" |
        "lowest_spd" | "broken" | "highest_break" | "random" |
        "all_enemies" | "all_allies" | "has_modifier"

    字典形式（参数化，内联定义）：
        {"type": "min", "key": "stats.hp"}
        {"type": "max", "key": "stats.atk"}
        {"type": "filter", "condition": "stats.hp < max_hp * 0.5"}
        {"type": "has_modifier", "modifier_id": "MOD_SHIELD"}
        {"type": "random"}
        {"type": "first", "condition": "actor_type == 'monster'"}
    """

    priority: int = 0


@dataclass
class TimingRule:
    """时机策略：在特定条件下延迟或提前行动."""

    condition: str
    """触发条件."""

    timing: str
    """时机指令：
    - "immediate"   立即行动（默认）
    - "delay"       延迟到特定条件满足
    - "advance"     提前行动（配合拉条）
    """

    delay_condition: Optional[str] = None
    """delay 时的等待条件."""


@dataclass
class Policy:
    """完整策略：技能选择 + 目标选择 + 时机 + 可调参数."""

    name: str = "default"
    """策略名称，用于标识和对比."""

    action_rules: List[PolicyRule] = field(default_factory=list)
    """技能选择规则列表，按 priority 降序匹配，第一条满足的被执行."""

    target_rules: List[TargetRule] = field(default_factory=list)
    """目标选择规则列表."""

    timing_rules: List[TimingRule] = field(default_factory=list)
    """时机策略规则列表."""

    parameters: Dict[str, Any] = field(default_factory=dict)
    """可调参数表，可在规则表达式中引用.

    例如：{"ULT_THRESHOLD": 120, "SKILL_PRIO": 0.8}
    """

    version: str = "1.0"
    """策略版本，用于兼容性和回溯."""

    def get_parameter(self, name: str, default: Any = None) -> Any:
        """获取参数值，支持嵌套访问（如 "buff.stack"）."""
        return self.parameters.get(name, default)
