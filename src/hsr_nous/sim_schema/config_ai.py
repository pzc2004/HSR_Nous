"""ConfigAI 原始行为树的静态支持表（sim_schema 层，可供 adapters 与 sim 共用）."""
from __future__ import annotations

from typing import Any, Dict

#: 上游 MonsterTemplateConfig.Rank → ConfigAI CompareValue 数值枚举。
MONSTER_RANK_VALUES = {
    "Minion": 1,
    "MinionLv2": 2,
    "Elite": 3,
    "LittleBoss": 4,
    "BigBoss": 5,
}

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
    "RPG.GameCore.SetDynamicValueByCopying",
    "RPG.GameCore.SetDynamicValueByCharacterCount",
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
    "RPG.GameCore.AIComposeSelector",
    "RPG.GameCore.AITaskTargetTypeSelector",
    "RPG.GameCore.AIPropertySelector",
    "RPG.GameCore.AIMonsterIDSelector",
    "RPG.GameCore.AIBehaviorFlagSelector",
    "RPG.GameCore.ByCompareTarget",
    "RPG.GameCore.ByCompareBP",
    "RPG.GameCore.ByContainBehaviorFlag",
    "RPG.GameCore.ByCompareMonsterID",
    "RPG.GameCore.ByCompareAliveEnemyNumber",
    "RPG.GameCore.ByCompareModifierValue",
    "RPG.GameCore.ByCompareCharacterNumber",
    "RPG.GameCore.ByCompareTargetCount",
    "RPG.GameCore.ByCompareMonsterRank",
    "RPG.GameCore.DebugLog",
    "RPG.GameCore.TargetAlias",
    "RPG.GameCore.TargetSequence",
    "RPG.GameCore.TargetFilter",
    "RPG.GameCore.TargetIndex",
    "RPG.GameCore.TargetSortByFormation",
    "RPG.GameCore.RemoveModifier",
    "RPG.GameCore.AddModifier",
    "RPG.GameCore.RandomConfig",
})

_UNSUPPORTED_CONFIG_AI_TYPES = frozenset({
    "RPG.GameCore.SwitchCaseByDynamicValue",
    "RPG.GameCore.Retarget",
    "RPG.GameCore.ByCheckCustomValueBool",
    "RPG.GameCore.ByCompareSkillUsageLimit",
})


def is_self_target_alias(alias: str) -> bool:
    """ConfigAI 目标别名是否指施放者自身（Caster/Self/带 _Self 后缀）."""
    return alias in {"Caster", "Self"} or alias.endswith("_Self")


def is_team_count_alias(spec: Any) -> bool:
    """计数目标规格：队伍别名，或别名/过滤/索引/编队排序组成的 TargetSequence."""
    if isinstance(spec, dict) and spec.get("$type") == "RPG.GameCore.TargetSequence":
        return all(
            item.get("$type") in {
                "RPG.GameCore.TargetFilter", "RPG.GameCore.TargetIndex",
                "RPG.GameCore.TargetSortByFormation",
            }
            or (item.get("$type") == "RPG.GameCore.TargetAlias"
                and is_team_count_alias(str(item.get("Alias", ""))))
            for item in spec.get("Sequence") or [])
    return spec in {"AllTeammate", "AllTeamMember", "AllDarkTeam", "AllEnemy"}


def used_config_skill_names(config: Dict[str, Any]) -> set[str]:
    """返回行为树全部 UseSkill 引用名；模板生成据此收编序列外的 ConfigAI 技能."""
    names: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("$type") == "RPG.GameCore.UseSkill" and value.get("SkillName"):
                names.add(str(value["SkillName"]))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(config)
    return names


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
            if node_type == "RPG.GameCore.AIComposeSelector" \
                    and (value.get("ComposeType") or "ByAnd") not in {"ByOr", "ByAnd"}:
                bad.add(f"compose:{value.get('ComposeType')}")
            if node_type == "RPG.GameCore.AITaskTargetTypeSelector":
                alias = str((value.get("TargetType") or {}).get("Alias", ""))
                if alias not in {"Caster", "AllTeammate", "AllTeamMember", "AllEnemy", "CasterSummonedMinions"}:
                    bad.add(f"target:{alias}")
            if node_type == "RPG.GameCore.SetDynamicValueByCopying":
                alias = str((value.get("FromTargetType") or {}).get("Alias", ""))
                if not is_self_target_alias(alias):
                    bad.add(f"target:{alias}")
            if node_type in {"RPG.GameCore.AddModifier", "RPG.GameCore.RemoveModifier"}:
                alias = str((value.get("TargetType") or {}).get("Alias", ""))
                if not is_self_target_alias(alias):
                    bad.add(f"target:{alias}")
            if node_type in {
                "RPG.GameCore.SetDynamicValueByCharacterCount",
                "RPG.GameCore.ByCompareCharacterNumber",
                "RPG.GameCore.ByCompareTargetCount",
            }:
                key = "ReadTargetType" if node_type.endswith("CharacterCount") else "TargetType"
                target_type = value.get(key) or {}
                spec = target_type.get("Alias") if target_type.get("$type") == "RPG.GameCore.TargetAlias" else target_type
                if not is_team_count_alias(spec):
                    bad.add("target:TargetSequence" if isinstance(spec, dict) else f"target:{spec}")
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
    return 1.0 if key.endswith("AIFlag") or key.endswith(("AICounter", "AICounter_01")) else 0.0


def _initial_predicate(
    node: Dict[str, Any], monster_id: str, monster_rank: str, enemy_count: int = 4,
) -> bool:
    """初始谓词与运行时同口径处理 Inverse（含递归子谓词）."""
    result = _initial_predicate_raw(node, monster_id, monster_rank, enemy_count)
    return not result if node.get("Inverse", False) else result


def _initial_predicate_raw(
    node: Dict[str, Any], monster_id: str, monster_rank: str, enemy_count: int,
) -> bool:
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
    if node_type == "RPG.GameCore.ByContainBehaviorFlag":
        return False  # 初始未击破、无 DoT、无控制、无禁行动
    if node_type == "RPG.GameCore.ByAnd":
        return all(_initial_predicate(child, monster_id, monster_rank, enemy_count)
                   for child in node.get("PredicateList") or [])
    if node_type == "RPG.GameCore.ByAny":
        return any(_initial_predicate(child, monster_id, monster_rank, enemy_count)
                   for child in node.get("PredicateList") or [])
    if node_type == "RPG.GameCore.ByNot":
        return not _initial_predicate(node.get("Predicate") or {}, monster_id, monster_rank, enemy_count)
    if node_type == "RPG.GameCore.ByTargetAliveState":
        return str(node.get("CompareType", "Alive")) == "Alive"
    if node_type == "RPG.GameCore.ByCompareHPRatio":
        return _compare(
            1.0, _fixed_number(node.get("CompareValue")),
            str(node.get("CompareType", "Equal")))
    if node_type == "RPG.GameCore.ByRandomChance":
        return True
    if node_type == "RPG.GameCore.ByCompareMonsterID":
        actual = monster_id.split("__", 1)[0]
        return actual == str(int(_fixed_number(node.get("TargetMonsterID"))))
    if node_type == "RPG.GameCore.ByCompareTarget":
        actual_alias = str((node.get("TargetType") or {}).get("Alias", ""))
        compare_alias = str((node.get("CompareType") or {}).get("Alias", ""))
        if actual_alias not in {"ParamEntity", "Caster"} or compare_alias not in {"ParamEntity", "Caster"}:
            return False
        return actual_alias == compare_alias
    if node_type == "RPG.GameCore.ByCompareBP":
        return _compare(
            3.0, _fixed_number(node.get("CompareValue")),
            str(node.get("CompareType", "Equal")))
    if node_type == "RPG.GameCore.ByCompareAliveEnemyNumber":
        return _compare(
            4.0, _fixed_number(node.get("CompareValue")),
            str(node.get("CompareType", "Equal")))
    if node_type == "RPG.GameCore.ByCompareMonsterRank":
        return _compare(
            float(MONSTER_RANK_VALUES.get(monster_rank, 0)),
            _fixed_number(node.get("CompareValue")),
            str(node.get("CompareType", "Equal")))
    if node_type in {"RPG.GameCore.ByCompareCharacterNumber", "RPG.GameCore.ByCompareTargetCount"}:
        nested = node.get("Predicate")
        if nested and nested.get("$type") == "RPG.GameCore.ByIsContainModifier":
            actual = 0.0  # 初始无 modifier，嵌套过滤后的候选数恒为 0
        elif nested:
            return False  # 其他嵌套过滤不在静态初始状态臆造候选
        else:
            alias = str((node.get("TargetType") or {}).get("Alias", ""))
            actual = 4.0 if alias in {"AllEnemy", "AllDarkTeam"} else float(enemy_count)
        expected_key = "CompareNumber" if node_type.endswith("CharacterNumber") else "Number"
        return _compare(
            actual, _fixed_number(node.get(expected_key)),
            str(node.get("CompareType", "Equal")))
    if node_type == "RPG.GameCore.ByCompareModifierValue":
        return _compare(
            0.0, _fixed_number(node.get("CompareValue")),
            str(node.get("CompareType", "Equal")))
    return False


def _initial_decision_score(
    decision: Dict[str, Any], available_skill_ids: set[str], monster_id: str, monster_rank: str,
    enemy_count: int = 4,
) -> float:
    if not decision.get("ConsiderAxisList"):
        return _fixed_number(decision.get("Weight", 1.0))
    score = 0.0
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
                          if _initial_predicate(
                              axis.get("Predicate") or {}, monster_id, monster_rank, enemy_count)
                          else 0.0)
        else:
            return 0.0
        score += axis_score
        if score == 0:
            return 0.0
    return score * _fixed_number(decision.get("Weight", 1.0))


def has_initial_decision(
    config: Dict[str, Any], available_skill_ids: set[str], monster_id: str = "",
    monster_rank: str = "",
) -> bool:
    """默认动态值/阶段 1 下是否存在可执行决策；怪物侧数量按 1/4 两档核查."""

    def walk(decisions: Any, enemy_count: int) -> bool:
        for decision in decisions or []:
            node_type = decision.get("$type")
            if node_type == "RPG.GameCore.AIStepperDecisionGroupConfig":
                if (_initial_decision_score(
                        decision, available_skill_ids, monster_id, monster_rank, enemy_count) > 0
                        and walk(decision.get("DecisionList"), enemy_count)):
                    return True
            elif node_type == "RPG.GameCore.AIDecisionConfig":
                if _initial_decision_score(
                        decision, available_skill_ids, monster_id, monster_rank, enemy_count) > 0:
                    return True
        return False

    return any(walk(config.get("DecisionList") or [], count) for count in (1, 4))
