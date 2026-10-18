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
