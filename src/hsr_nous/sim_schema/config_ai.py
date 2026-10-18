"""ConfigAI 原始行为树的静态支持表（sim_schema 层，可供 adapters 与 sim 共用）."""
from __future__ import annotations

from typing import Any, Dict

# 执行器已实现的节点；静态收编与运行时共用，防止“支持表漂移”.
SUPPORTED_CONFIG_AI_TYPES = frozenset({
    "RPG.GameCore.AIVariableBool",
    "RPG.GameCore.AIVariableString",
    "RPG.GameCore.AIDecisionConfig",
    "RPG.GameCore.AIStepperDecisionGroupConfig",
    "RPG.GameCore.SequenceConfig",
    "RPG.GameCore.UseSkill",
    "RPG.GameCore.UseSequencedSkill",
    "RPG.GameCore.ChoseSequencedSkillAxis",
    "RPG.GameCore.CheckSkillUsabilityAxis",
    "RPG.GameCore.CheckPredicateAxis",
    "RPG.GameCore.DefineDynamicValue",
    "RPG.GameCore.SetDynamicValue",
    "RPG.GameCore.SetDynamicValueByAddValue",
    "RPG.GameCore.PredicateTaskList",
    "RPG.GameCore.ByCompareDynamicValue",
    "RPG.GameCore.ByCompareMonsterPhase",
    "RPG.GameCore.ByIsContainModifier",
    "RPG.GameCore.ByAnd",
    "RPG.GameCore.ByAny",
    "RPG.GameCore.ByNot",
    "RPG.GameCore.ByTargetAliveState",
    "RPG.GameCore.ByCompareHPRatio",
    "RPG.GameCore.ByRandomChance",
    "RPG.GameCore.SelectAISkillTarget",
    "RPG.GameCore.AIModifierNameSelector",
    "RPG.GameCore.DebugLog",
    "RPG.GameCore.TargetAlias",
})

_UNSUPPORTED_CONFIG_AI_TYPES = frozenset({
    "RPG.GameCore.SwitchCaseByDynamicValue",
    "RPG.GameCore.RandomConfig",
    "RPG.GameCore.Retarget",
    "RPG.GameCore.AddModifier",
    "RPG.GameCore.RemoveModifier",
    "RPG.GameCore.SetDynamicValueByCopying",
    "RPG.GameCore.SetDynamicValueByCharacterCount",
    "RPG.GameCore.ByCompareCharacterNumber",
    "RPG.GameCore.ByContainBehaviorFlag",
    "RPG.GameCore.ByCheckCustomValueBool",
    "RPG.GameCore.ByCompareTargetCount",
    "RPG.GameCore.ByCompareMonsterID",
    "RPG.GameCore.ByCompareMonsterRank",
    "RPG.GameCore.ByCompareSkillUsageLimit",
    "RPG.GameCore.ByCompareBP",
    "RPG.GameCore.ByCompareTarget",
    "RPG.GameCore.ByCompareAliveEnemyNumber",
    "RPG.GameCore.ByCompareModifierValue",
})


def unsupported_config_nodes(config: Dict[str, Any], available_skill_ids: set[str]) -> set[str]:
    """返回行为树中未支持的节点/技能；空集才允许写入 CompiledEnemyPolicy.config."""
    bad: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            node_type = value.get("$type")
            if node_type in _UNSUPPORTED_CONFIG_AI_TYPES:
                bad.add(node_type)
            elif node_type and node_type not in SUPPORTED_CONFIG_AI_TYPES:
                bad.add(node_type)
            if node_type == "RPG.GameCore.UseSkill":
                skill_name = str(value.get("SkillName", ""))
                if skill_name not in available_skill_ids:
                    bad.add(f"skill:{skill_name}")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(config)
    return bad


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


def _initial_dynamic(key: str) -> float:
    # 与 ConfigAIInterpreter 当前缺省口径一致；只用于拒绝初始即不可执行的配置。
    return 1.0 if key == "AIFlag" or key.endswith("AICounter_01") else 0.0


def _initial_predicate(node: Dict[str, Any]) -> bool:
    node_type = node.get("$type")
    if node_type == "RPG.GameCore.ByCompareDynamicValue":
        key = _dynamic_key(node.get("DynamicKey"))
        return _compare(
            _initial_dynamic(key), _fixed_number(node.get("CompareValue")),
            str(node.get("CompareType", "Equal")))
    if node_type == "RPG.GameCore.ByCompareMonsterPhase":
        return _compare(
            1.0, _fixed_number(node.get("CompareValue")),
            str(node.get("CompareType", "Equal")))
    if node_type == "RPG.GameCore.ByIsContainModifier":
        return False
    if node_type == "RPG.GameCore.ByAnd":
        return all(_initial_predicate(child) for child in node.get("PredicateList") or [])
    if node_type == "RPG.GameCore.ByAny":
        return any(_initial_predicate(child) for child in node.get("PredicateList") or [])
    if node_type == "RPG.GameCore.ByNot":
        return not _initial_predicate(node.get("Predicate") or {})
    if node_type == "RPG.GameCore.ByTargetAliveState":
        return str(node.get("CompareType", "Alive")) == "Alive"
    if node_type == "RPG.GameCore.ByCompareHPRatio":
        return _compare(
            1.0, _fixed_number(node.get("CompareValue")),
            str(node.get("CompareType", "Equal")))
    if node_type == "RPG.GameCore.ByRandomChance":
        return True
    return False


def _initial_decision_score(decision: Dict[str, Any], available_skill_ids: set[str]) -> float:
    score = 1.0
    for axis in decision.get("ConsiderAxisList") or []:
        axis_type = axis.get("$type")
        if axis_type == "RPG.GameCore.ChoseSequencedSkillAxis":
            axis_score = _fixed_number(axis.get("CheckScore"))
        elif axis_type == "RPG.GameCore.CheckSkillUsabilityAxis":
            skill_name = str(axis.get("SkillName", ""))
            axis_score = (_fixed_number(axis.get("CheckScore"))
                          if skill_name in available_skill_ids else 0.0)
        elif axis_type == "RPG.GameCore.CheckPredicateAxis":
            axis_score = (_fixed_number(axis.get("SuccessScore"))
                          if _initial_predicate(axis.get("Predicate") or {}) else 0.0)
        else:
            return 0.0
        score *= axis_score
        if score == 0:
            return 0.0
    return score * _fixed_number(decision.get("Weight", 1.0))


def has_initial_decision(config: Dict[str, Any], available_skill_ids: set[str]) -> bool:
    """默认动态值/阶段 1 下是否存在可执行决策；无则只能保留原始序列候选."""

    def walk(decisions: Any) -> bool:
        for decision in decisions or []:
            node_type = decision.get("$type")
            if node_type == "RPG.GameCore.AIStepperDecisionGroupConfig":
                if (_initial_decision_score(decision, available_skill_ids) > 0
                        and walk(decision.get("DecisionList"))):
                    return True
            elif node_type == "RPG.GameCore.AIDecisionConfig":
                if _initial_decision_score(decision, available_skill_ids) > 0:
                    return True
        return False

    return walk(config.get("DecisionList") or [])
