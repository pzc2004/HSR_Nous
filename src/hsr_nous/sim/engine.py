"""战斗引擎：回合制战斗核心循环 + 策略解释器."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim.selectors import get_selector, resolve_parametric_selector
from hsr_nous.sim_schema.actor import Actor
from hsr_nous.sim_schema.encounter import Encounter
from hsr_nous.sim_schema.policy import Policy, PolicyRule, TargetRule


@dataclass
class BattleState:
    actors: List[Actor] = field(default_factory=list)
    turn_count: int = 0
    action_history: List[str] = field(default_factory=list)
    total_damage: float = 0.0
    max_turns: int = 50


class PolicyInterpreter:
    """策略解释器：根据当前状态选择行动."""

    def __init__(self, policy: Policy) -> None:
        self.policy = policy

    def _eval_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """求值条件表达式.

        TODO: 实现安全的表达式引擎（支持基本运算符、变量访问）
        目前先用简单字符串替换 + eval 做占位。
        """
        if condition == "true":
            return True
        # 占位：未来实现完整表达式解析
        try:
            # 将上下文变量注入表达式
            expr = condition
            for key, val in context.items():
                if isinstance(val, (int, float, bool)):
                    expr = expr.replace(key, str(val))
            return bool(eval(expr, {"__builtins__": {}}, {}))
        except Exception:
            return False

    def select_action(self, actor: Actor, context: Dict[str, Any]) -> Optional[str]:
        """根据策略选择技能（ultimate/skill/basic/pass）."""
        if not self.policy.action_rules:
            return "basic"

        # 按 priority 降序排序
        rules = sorted(
            self.policy.action_rules,
            key=lambda r: r.priority,
            reverse=True,
        )

        # 注入策略参数到上下文
        eval_context = dict(context)
        eval_context.update(self.policy.parameters)

        for rule in rules:
            if self._eval_condition(rule.condition, eval_context):
                return rule.action

        return "basic"  # 默认普攻

    def select_target(
        self,
        actor: Actor,
        action: str,
        candidates: List[Actor],
        context: Dict[str, Any],
    ) -> Optional[Actor]:
        """根据策略选择目标."""
        if not self.policy.target_rules:
            return candidates[0] if candidates else None

        rules = sorted(
            self.policy.target_rules,
            key=lambda r: r.priority,
            reverse=True,
        )

        eval_context = dict(context)
        eval_context["action_type"] = action
        eval_context.update(self.policy.parameters)

        for rule in rules:
            if self._eval_condition(rule.condition, eval_context):
                selector = rule.selector

                # 1. 字符串选择器：走注册表
                if isinstance(selector, str):
                    selector_fn = get_selector(selector)
                    if selector_fn is not None:
                        return selector_fn(actor, candidates, eval_context)
                    return candidates[0] if candidates else None

                # 2. 字典选择器：参数化解析，不需要预注册
                if isinstance(selector, dict):
                    return resolve_parametric_selector(
                        actor, candidates, eval_context, selector
                    )

                # 未知类型回退
                return candidates[0] if candidates else None

        return candidates[0] if candidates else None


class CombatEngine:
    """回合制战斗模拟器核心."""

    def __init__(
        self,
        encounter: Encounter,
        policy: Optional[Policy] = None,
        seed: int = 42,
    ) -> None:
        self.encounter = encounter
        self.policy = policy
        self.interpreter = PolicyInterpreter(policy) if policy else None
        self.seed = seed
        self.state = BattleState()

    def run(self) -> BattleState:
        """运行完整战斗仿真.

        TODO: 实现行动序、伤害结算、增益/减益管理
        当前为骨架，仅演示策略解释器集成。
        """
        self.state.actors = list(self.encounter.actors)

        for turn in range(self.state.max_turns):
            self.state.turn_count = turn

            # TODO: 按行动值排序选择当前行动角色
            for actor in self.state.actors:
                if actor.actor_type == "character" and self.interpreter:
                    context = {
                        "energy": getattr(actor, "energy", 0),
                        "skill_points": 3,  # TODO: 从 globals 读取
                        "hp": actor.stats.hp,
                        "max_hp": actor.stats.hp,  # TODO: 需要 max_hp 字段
                    }
                    action = self.interpreter.select_action(actor, context)
                    self.state.action_history.append(
                        f"T{turn}: {actor.name} uses {action}"
                    )

        return self.state
