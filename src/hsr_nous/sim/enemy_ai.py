"""ConfigAI 行为树解释器：只执行已登记节点，未知节点不得静默进入正式路径.

策略的 `config` 是上游原始 JSON（不是另一套手写 AI）。动态值、阶段与冷却状态都放进
既有 `_enemy_policy_state`，因此存档/恢复与 SequenceThree 共用同一条世界线。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.config_ai import unsupported_config_nodes  # noqa: F401  # 静态收编共用入口


def _fixed_number(value: Any) -> float:
    if isinstance(value, dict) and "FixedValue" in value:
        return float(value["FixedValue"].get("Value", 0))
    if isinstance(value, dict) and "Value" in value:
        return float(value["Value"])
    return float(value or 0)


def _dynamic_key(value: Any) -> str:
    if isinstance(value, dict) and "Value" in value:
        return str(value["Value"])
    return str(value)


def _compare(actual: float, expected: float, compare_type: str) -> bool:
    return {
        "Equal": actual == expected,
        "NotEqual": actual != expected,
        "Less": actual < expected,
        "LessEqual": actual <= expected,
        "Greater": actual > expected,
        "GreaterEqual": actual >= expected,
    }.get(compare_type, False)


class ConfigAIInterpreter:
    """一台敌方单位的 ConfigAI 执行器；每次敌方回合重新评分并执行任务."""

    def __init__(self, engine: Any, actor_state: Any) -> None:
        self.engine = engine
        self.actor_state = actor_state
        self.actor_id = actor_state.actor.actor_id
        self.policy = engine._enemy_policies[self.actor_id]
        self.runtime = engine._enemy_policy_state[self.actor_id]
        self.runtime.setdefault("dynamic_values", {})
        self.runtime.setdefault("current_phase", 1)
        self.actions = {
            action.action_id: action
            for action in engine.actions_by_actor.get(self.actor_id, [])
        }
        self.target_override: Optional[Any] = None

    def _dynamic(self, key: str) -> float:
        values = self.runtime["dynamic_values"]
        if key in values:
            return float(values[key])
        # 已读到的 AI 配置均以 AIFlag/首计数器 1 起步；其他动态键默认 0。
        return 1.0 if key == "AIFlag" or key.endswith("AICounter_01") else 0.0

    def _set_dynamic(self, key: str, value: float, *, add: bool = False) -> None:
        current = self._dynamic(key) if add else 0.0
        self.runtime["dynamic_values"][key] = current + float(value)

    def _cooldown_ready(self, action_id: str) -> bool:
        phases = self.policy.skill_phases.get(action_id, ())
        return (action_id in self.actions
                and self.runtime["cooldown_left"].get(action_id, 0) <= 0
                and (not phases or self.runtime["current_phase"] in phases))

    def _mark_executed(self, action_id: str) -> None:
        self.runtime["cooldown_left"][action_id] = self.policy.cooldown.get(action_id, 0)

    def _predicate(self, node: Dict[str, Any]) -> bool:
        node_type = node.get("$type")
        if node_type == "RPG.GameCore.ByCompareDynamicValue":
            return _compare(
                self._dynamic(_dynamic_key(node.get("DynamicKey"))),
                _fixed_number(node.get("CompareValue")),
                str(node.get("CompareType", "Equal")),
            )
        if node_type == "RPG.GameCore.ByCompareMonsterPhase":
            return _compare(
                float(self.runtime["current_phase"]), _fixed_number(node.get("CompareValue")),
                str(node.get("CompareType", "Equal")),
            )
        if node_type == "RPG.GameCore.ByIsContainModifier":
            name = _dynamic_key(node.get("ModifierName"))
            return any(mod.modifier_id == name or mod.name == name
                       for mod in self.actor_state.modifiers.values())
        if node_type == "RPG.GameCore.ByAnd":
            return all(self._predicate(child) for child in node.get("PredicateList") or [])
        if node_type == "RPG.GameCore.ByAny":
            return any(self._predicate(child) for child in node.get("PredicateList") or [])
        if node_type == "RPG.GameCore.ByNot":
            return not self._predicate(node.get("Predicate") or {})
        if node_type == "RPG.GameCore.ByTargetAliveState":
            return self.actor_state.alive == (str(node.get("CompareType", "Alive")) == "Alive")
        if node_type == "RPG.GameCore.ByCompareHPRatio":
            max_hp = max(1e-9, self.actor_state.max_hp)
            return _compare(
                self.actor_state.current_hp / max_hp, _fixed_number(node.get("CompareValue")),
                str(node.get("CompareType", "Equal")),
            )
        if node_type == "RPG.GameCore.ByRandomChance":
            return self.engine.pipeline.mechanic_chance(_fixed_number(node.get("CompareValue")))
        return False

    def _decision_score(self, decision: Dict[str, Any]) -> float:
        score = 1.0
        for axis in decision.get("ConsiderAxisList") or []:
            axis_type = axis.get("$type")
            if axis_type == "RPG.GameCore.ChoseSequencedSkillAxis":
                axis_score = _fixed_number(axis.get("CheckScore"))
            elif axis_type == "RPG.GameCore.CheckSkillUsabilityAxis":
                skill_name = str(axis.get("SkillName", ""))
                action_id = self.policy.skill_ids.get(skill_name, skill_name)
                axis_score = (_fixed_number(axis.get("CheckScore"))
                              if self._cooldown_ready(action_id) else 0.0)
            elif axis_type == "RPG.GameCore.CheckPredicateAxis":
                axis_score = (_fixed_number(axis.get("SuccessScore"))
                              if self._predicate(axis.get("Predicate") or {}) else 0.0)
            else:
                return 0.0
            score *= axis_score
            if score == 0:
                return 0.0
        return score * _fixed_number(decision.get("Weight", 1.0))

    def _choose(self, decisions: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for decision in decisions or []:
            node_type = decision.get("$type")
            if node_type == "RPG.GameCore.AIStepperDecisionGroupConfig":
                group_score = self._decision_score(decision)
                if group_score <= 0:
                    continue
                chosen = self._choose(decision.get("DecisionList") or [])
                if chosen is not None:
                    score = group_score * self._decision_score(chosen)
                    if score > best_score:
                        best, best_score = chosen, score
            elif node_type == "RPG.GameCore.AIDecisionConfig":
                score = self._decision_score(decision)
                if score > best_score:
                    best, best_score = decision, score
        return best

    def _select_modifier_target(self, modifier_name: str) -> Any:
        allies = self.engine._allies_alive()
        for target in allies:
            for modifier in target.modifiers.values():
                if modifier.modifier_id == modifier_name or modifier.name == modifier_name:
                    return target
        if modifier_name == "MCommon_DOT_Electric":
            for target in allies:
                if any(mod.dot_element == "thunder" for mod in target.modifiers.values()):
                    return target
        # 自定义目标标记尚无对应 modifier 时，回退到现有嘲讽/默认目标选择。
        return self.engine._pick_ally_target(self.actor_state)

    def _run_tasks(self, tasks: Iterable[Dict[str, Any]]) -> Optional[Action]:
        selected: Optional[Action] = None
        for task in tasks or []:
            task_type = task.get("$type")
            if task_type == "RPG.GameCore.DefineDynamicValue":
                self._set_dynamic(_dynamic_key(task.get("DynamicKey")),
                                  _fixed_number(task.get("ResetValue")))
            elif task_type == "RPG.GameCore.SetDynamicValue":
                self._set_dynamic(_dynamic_key(task.get("DynamicKey")),
                                  _fixed_number(task.get("ResetValue")))
            elif task_type == "RPG.GameCore.SetDynamicValueByAddValue":
                self._set_dynamic(_dynamic_key(task.get("DynamicKey")),
                                  _fixed_number(task.get("ResetValue")), add=True)
            elif task_type == "RPG.GameCore.PredicateTaskList":
                branch = "SuccessTaskList" if self._predicate(task.get("Predicate") or {}) else "FailedTaskList"
                selected = self._run_tasks(task.get(branch) or []) or selected
            elif task_type == "RPG.GameCore.SelectAISkillTarget":
                self.target_override = self._select_modifier_target(
                    _dynamic_key((task.get("Selector") or {}).get("ModifierName")))
            elif task_type == "RPG.GameCore.UseSkill":
                action_id = self.policy.skill_ids.get(str(task.get("SkillName", "")),
                                                      str(task.get("SkillName", "")))
                if self._cooldown_ready(action_id):
                    selected = self.actions[action_id]
                    self._mark_executed(action_id)
            elif task_type == "RPG.GameCore.UseSequencedSkill":
                selected = self.engine._select_enemy_policy_action(self.actor_state)
            elif task_type == "RPG.GameCore.DebugLog":
                continue
            else:
                return None
        return selected

    def choose_action(self) -> Optional[Action]:
        decision = self._choose(self.policy.config.get("DecisionList") or [])
        if decision is None:
            return None
        root = decision.get("RootTask") or {}
        if root.get("$type") != "RPG.GameCore.SequenceConfig":
            return None
        return self._run_tasks(root.get("TaskList") or [])
