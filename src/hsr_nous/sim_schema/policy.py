"""策略模型：可执行、可参数化、可搜索的战斗策略定义。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Union


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
    1. 字符串：预注册选择器（合法集合 = `sim_schema/effect_types.py`
       `POLICY_TARGET_SELECTORS` 单一事实源，如 "lowest_hp"）
    2. 字典：参数化选择器（type 合法集合 = 同文件 `POLICY_SELECTOR_DICT_TYPES`），
       如 {"type": "min", "key": "stats.hp"}
    """

    condition: str
    """条件表达式."""

    selector: Union[str, Dict[str, Any]]
    """目标选择器（词表见 effect_types；编译期未知选择器即炸）.

    字典形式（参数化，内联定义）示例：
        {"type": "min", "key": "stats.hp"}
        {"type": "max", "key": "stats.atk"}
        {"type": "filter", "condition": "stats.hp < max_hp * 0.5"}
        {"type": "has_modifier", "modifier_id": "MOD_SHIELD"}
        {"type": "random"}
        {"type": "first", "condition": "actor_type == 'monster'"}
    """

    priority: int = 0


@dataclass
class Policy:
    """完整策略：技能选择 + 目标选择 + 可调参数."""

    name: str = "default"
    """策略名称，用于标识和对比."""

    action_rules: List[PolicyRule] = field(default_factory=list)
    """技能选择规则列表，按 priority 降序匹配，第一条满足的被执行."""

    target_rules: List[TargetRule] = field(default_factory=list)
    """目标选择规则列表."""

    parameters: Dict[str, Any] = field(default_factory=dict)
    """可调参数表，可在规则表达式中引用.

    例如：{"ULT_THRESHOLD": 120, "SKILL_PRIO": 0.8}
    """

    version: str = "1.0"
    """策略版本，用于兼容性和回溯."""
