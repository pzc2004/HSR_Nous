"""战斗引擎：回合制战斗核心循环 + 策略解释器."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim.resolver import DamageResolver
from hsr_nous.sim.selectors import get_selector, resolve_parametric_selector
from hsr_nous.sim.timeline import Timeline
from hsr_nous.sim_schema.action import Action
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

    # 运行时状态
    damage_by_actor: Dict[str, float] = field(default_factory=dict)
    current_hp: Dict[str, float] = field(default_factory=dict)
    total_av: float = 0.0  # 累计行动值（轮次/终止判断用）


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
    """回合制战斗模拟器核心.

    Phase 1：行动值驱动的主循环 + 标准直伤结算。
    敌人回合暂不结算对我方伤害（生存机制属 Phase 3）。
    """

    # monster 类型 actor_type 取值
    MONSTER_TYPES = {"monster", "enemy"}

    def __init__(
        self,
        encounter: Encounter,
        policy: Optional[Policy] = None,
        actions_by_actor: Optional[Dict[str, List[Action]]] = None,
        seed: int = 42,
    ) -> None:
        self.encounter = encounter
        self.policy = policy
        self.interpreter = PolicyInterpreter(policy) if policy else None
        self.actions_by_actor = actions_by_actor or {}
        self.seed = seed
        self.state = BattleState()
        self.resolver = DamageResolver()

    def _is_monster(self, actor: Actor) -> bool:
        return actor.actor_type in self.MONSTER_TYPES

    def _is_alive(self, actor: Actor) -> bool:
        return self.state.current_hp.get(actor.actor_id, 0.0) > 0.0

    def _resolve_action_obj(self, actor: Actor, action_type: str) -> Optional[Action]:
        """根据策略选定的行动类型，取该角色对应的 Action 对象."""
        actions = self.actions_by_actor.get(actor.actor_id, [])
        for act in actions:
            if act.action_type == action_type:
                return act
        # 回退：返回第一个可用行动
        return actions[0] if actions else None

    def _select_action_type(self, actor: Actor) -> str:
        """通过策略解释器选择行动类型，无策略时默认普攻."""
        if not self.interpreter:
            return "basic"
        context = {
            "energy": actor.stats.energy,
            "max_energy": actor.stats.max_energy,
            "hp": self.state.current_hp.get(actor.actor_id, actor.stats.hp),
            "max_hp": actor.stats.hp,
        }
        return self.interpreter.select_action(actor, context) or "basic"

    def _enemies_alive(self) -> List[Actor]:
        return [a for a in self.state.actors if self._is_monster(a) and self._is_alive(a)]

    def _should_terminate(self) -> bool:
        term = self.encounter.termination
        if self.state.total_av >= term.max_action_value and term.mode == "fixed_av":
            return True
        if term.mode == "kill_target":
            if not self._enemies_alive():
                return True
        # 兜底：无存活敌人则结束
        if not self._enemies_alive():
            return True
        return False

    def run(self) -> BattleState:
        """运行战斗仿真（Phase 1：行动值循环 + 直伤结算）."""
        self.state.actors = list(self.encounter.actors)
        # 初始化 HP
        for a in self.state.actors:
            self.state.current_hp[a.actor_id] = a.stats.hp
            self.state.damage_by_actor.setdefault(a.actor_id, 0.0)

        timeline = Timeline(self.state.actors)

        for turn in range(self.state.max_turns):
            if self._should_terminate():
                break

            actor, _ = timeline.next_actor()
            self.state.total_av = timeline.total_elapsed_av
            self.state.turn_count = turn

            if not self._is_alive(actor):
                continue  # 已阵亡单位跳过回合

            if self._is_monster(actor):
                # Phase 1：敌人回合占位（不结算对我方伤害）
                self.state.action_history.append(
                    f"AV{self.state.total_av:.1f}: [敌] {actor.name} 行动"
                )
                continue

            # 我方角色行动
            action_type = self._select_action_type(actor)
            action = self._resolve_action_obj(actor, action_type)
            if action is None:
                self.state.action_history.append(
                    f"AV{self.state.total_av:.1f}: {actor.name} 无可用行动"
                )
                continue

            target = self._choose_target(actor, action)
            if target is None:
                continue

            result = self.resolver.resolve(action, actor, target)
            self.state.total_damage += result.damage
            self.state.damage_by_actor[actor.actor_id] += result.damage
            self.state.current_hp[target.actor_id] -= result.damage
            self.state.action_history.append(
                f"AV{self.state.total_av:.1f}: {actor.name} 对 {target.name} "
                f"使用 {action.name} 造成 {result.damage:,.0f} 伤害"
            )

        return self.state

    def _choose_target(self, actor: Actor, action: Action) -> Optional[Actor]:
        """选择行动目标：优先用策略，缺省取首个存活敌人."""
        enemies = self._enemies_alive()
        if not enemies:
            return None
        if self.interpreter:
            context = {"action_type": action.action_type}
            chosen = self.interpreter.select_target(actor, action.action_type, enemies, context)
            if chosen is not None:
                return chosen
        return enemies[0]
