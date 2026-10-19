"""ConfigAI 原始行为树的静态支持表（sim_schema 层，可供 adapters 与 sim 共用）."""
from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, Optional

#: 上游 MonsterTemplateConfig.Rank → ConfigAI CompareValue 数值枚举。
MONSTER_RANK_VALUES = {
    "Minion": 1,
    "MinionLv2": 2,
    "Elite": 3,
    "LittleBoss": 4,
    "BigBoss": 5,
}

#: 具名怪物集合目标别名（SummonIDList 与怪物名交叉核对）。
SPECIAL_TARGET_MONSTER_IDS = {
    "MMonster_W4_Claymore_01_LocalLegend_BlackSummon": frozenset({"4032052", "4032042"}),
    "MMonster_W4_Claymore_01_LocalLegend_WhiteSummon": frozenset({"4012033", "4012023"}),
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
    "RPG.GameCore.ByCheckCustomValueBool",
    "RPG.GameCore.ByAnd",
    "RPG.GameCore.ByAny",
    "RPG.GameCore.ByNot",
    "RPG.GameCore.ByTargetListAny",
    "RPG.GameCore.ByTargetAliveState",
    "RPG.GameCore.ByCompareHPRatio",
    "RPG.GameCore.ByRandomChance",
    "RPG.GameCore.SelectAISkillTarget",
    "RPG.GameCore.AIModifierNameSelector",
    "RPG.GameCore.AIComposeSelector",
    "RPG.GameCore.AITaskTargetTypeSelector",
    "RPG.GameCore.AIPropertySelector",
    "RPG.GameCore.AIMonsterIDSelector",
    "RPG.GameCore.AIMonsterRankSelector",
    "RPG.GameCore.AICustomStringTagSelector",
    "RPG.GameCore.AIComplexSkillAISelector",
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
    "RPG.GameCore.Retarget",
    "RPG.GameCore.SwitchCaseByDynamicValue",
})

_UNSUPPORTED_CONFIG_AI_TYPES = frozenset({
    "RPG.GameCore.ByCompareSkillUsageLimit",
})


def _signed_int32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def dynamic_value_hash(text: str) -> int:
    """上游 DynamicHashes 的 .NET Framework 字符串哈希（AISequence 三值实证）."""
    hash1 = hash2 = 5381
    for index in range(0, len(text), 2):
        hash1 = _signed_int32((hash1 << 5) + hash1) ^ ord(text[index])
        if index == len(text) - 1:
            break
        hash2 = _signed_int32((hash2 << 5) + hash2) ^ ord(text[index + 1])
    return _signed_int32(hash1 + _signed_int32(hash2 * 1566083941))


def resolve_config_custom_values(
    config: Dict[str, Any], custom_values: Dict[str, Any],
    custom_value_tags: Iterable[str] = (),
) -> Dict[str, Any]:
    """归一化可证明的 CustomValues 读取与 CustomValueTags 谓词，其他节点原样保留."""
    resolved = copy.deepcopy(config)
    by_hash: Dict[int, float] = {}
    for name, raw_value in custom_values.items():
        hashed = dynamic_value_hash(str(name))
        value = float(raw_value or 0)
        if hashed in by_hash and by_hash[hashed] != value:
            raise ValueError(f"ConfigAI CustomValues 哈希冲突：{name!r} / {hashed}")
        by_hash[hashed] = value
    tag_by_hash: Dict[int, str] = {}
    for tag in custom_value_tags:
        hashed = dynamic_value_hash(str(tag))
        if hashed in tag_by_hash and tag_by_hash[hashed] != tag:
            raise ValueError(f"ConfigAI CustomValueTags 哈希冲突：{tag!r} / {hashed}")
        tag_by_hash[hashed] = str(tag)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            node_type = value.get("$type")
            if node_type == "RPG.GameCore.SwitchCaseByDynamicValue":
                switch = value.get("Switch") or {}
                expr = switch.get("PostfixExpr") or {}
                hashes = expr.get("DynamicHashes") or []
                if (switch.get("IsDynamic") and expr.get("OpCodes") == "AQAR"
                        and not expr.get("FixedValues") and len(hashes) == 1
                        and int(hashes[0]) in by_hash):
                    value["Switch"] = {
                        "IsDynamic": False,
                        "FixedValue": {"Value": by_hash[int(hashes[0])]},
                    }
            elif node_type == "RPG.GameCore.ByCheckCustomValueBool":
                key = value.get("Key") or {}
                if "Hash" in key and int(key["Hash"]) in tag_by_hash:
                    value["Key"] = {"Value": tag_by_hash[int(key["Hash"])]}
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(resolved)
    return resolved


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
    return spec in {
        "AllTeammate", "AllTeamMember", "AllDarkTeam", "AllEnemy", "AllLightTeam",
        "AllLightTeam.RemoveServant", "TauntOrAggroEnemy.RemoveServant",
        "AllDarkTeam - Caster", "Monster_W4_Griffin_00_LocalLegend_Partner",
        "Monster_Svarog_00_Unselectable", "Monster_Svarog_00_RL_Unselectable",
        "MMonster_W4_Claymore_01_LocalLegend_BlackSummon",
        "MMonster_W4_Claymore_01_LocalLegend_WhiteSummon", "CasterSummonedMinions",
    }


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
            if node_type == "RPG.GameCore.SwitchCaseByDynamicValue":
                if (value.get("Switch") or {}).get("IsDynamic") is not False:
                    bad.add("switch:DynamicValue")
                for case in value.get("CaseTaskList") or []:
                    if (case.get("Case") or {}).get("IsDynamic") is not False:
                        bad.add("switch:DynamicCase")
            if node_type == "RPG.GameCore.ByCheckCustomValueBool" \
                    and not (value.get("Key") or {}).get("Value"):
                bad.add("custom_bool:Key")
            if node_type == "RPG.GameCore.AITaskTargetTypeSelector":
                target_type = value.get("TargetType") or {}
                if target_type.get("$type") == "RPG.GameCore.TargetSequence":
                    if not is_team_count_alias(target_type):
                        bad.add("target:TargetSequence")
                else:
                    alias = str(target_type.get("Alias", ""))
                    if alias not in {
                            "Caster", "AllTeammate", "AllTeamMember", "AllEnemy",
                            "AllEnemyIgnoreServant", "CasterSummonedMinions", "CasterSummoner",
                            "Monster_W4_Griffin_00_LocalLegend_Partner",
                            "Monster_W4_Claymore_01_Skill02_Target"}:
                        bad.add(f"target:{alias}")
            if node_type == "RPG.GameCore.ByTargetListAny":
                target_type = value.get("TargetType") or {}
                spec = (target_type.get("Alias")
                        if target_type.get("$type") == "RPG.GameCore.TargetAlias" else target_type)
                if not is_team_count_alias(spec):
                    bad.add("target:TargetSequence" if isinstance(spec, dict) else f"target:{spec}")
            if node_type == "RPG.GameCore.AIMonsterRankSelector" \
                    and value.get("PropertyStrategy") != "Max":
                bad.add("rank:PropertyStrategy")
            if node_type == "RPG.GameCore.Retarget":
                target_type = value.get("TargetType") or {}
                spec = (target_type.get("Alias")
                        if target_type.get("$type") == "RPG.GameCore.TargetAlias" else target_type)
                if not is_team_count_alias(spec):
                    bad.add("target:TargetSequence" if isinstance(spec, dict) else f"target:{spec}")
                if _fixed_number(value.get("MaxNumber") or 1) != 1.0:
                    bad.add("retarget:MaxNumber")
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


#: 经 ConfigCharacter.CustomValues 或 PassiveSkillInitiate 对账的初始动态值，键=(AIName, 怪物 ID)。
#: 怪物 ID 空串 = 同 AIName 的公共默认；具体 ID 优先，避免共享 AI 名时串用初值。
CONFIG_AI_INITIAL_DYNAMIC_VALUES = {
    ("Monster_W1_Bronya_00_RL", ""): {"Bronya_AICounter_Act1": 1.0},
    ("Monster_XP_Elite01_00", ""): {"Phase_Flag": 1.0},
    ("Monster_RO_015", "1004030"): {"Bronya_AICounter_Act2": 2.0},
    ("Monster_RO_015", "100403002"): {"Bronya_AICounter_Act2": 2.0},
    ("Monster_W1_Mecha01_00", "3002010"): {"FlopSide": -1.0, "AIFlag": 0.0},
    ("Monster_W1_Mecha01_00", "3002011"): {"FlopSide": -1.0, "AIFlag": 0.0},
    ("Monster_W1_Mecha01_00", "3002021"): {"FlopSide": -1.0, "AIFlag": 0.0},
    ("Monster_W3_Clock_00", "3002041"): {"FlopSide": -1.0, "AIFlag": 1.0},
    ("Monster_W2_Yanqing_00", "200402005"): {
        "W2_Yanqing_00_AICounter": 1.0, "W2_Yanqing_00_AIPhase": 1.0,
        "W2_Yanqing_00_MaxPhaseNum": 1.0,
    },
}


def config_ai_initial_values(config: Dict[str, Any], monster_id: str = "") -> Dict[str, float]:
    """按 ConfigAI.AIName 与实例 ID 查初始值；关卡实例后缀不参与匹配."""
    ai_name = str(config.get("AIName", ""))
    base_id = str(monster_id).split("__", 1)[0]
    return CONFIG_AI_INITIAL_DYNAMIC_VALUES.get(
        (ai_name, base_id), CONFIG_AI_INITIAL_DYNAMIC_VALUES.get((ai_name, ""), {}))


def _initial_dynamic(key: str, initial_values: Optional[Dict[str, float]] = None) -> float:
    # 与 ConfigAIInterpreter 当前缺省口径一致；只用于拒绝初始即不可执行的配置。
    if initial_values and key in initial_values:
        return float(initial_values[key])
    return 1.0 if key.endswith("AIFlag") or key.endswith(("AICounter", "AICounter_01")) else 0.0


def _initial_predicate(
    node: Dict[str, Any], monster_id: str, monster_rank: str, enemy_count: int = 4,
    initial_values: Optional[Dict[str, float]] = None,
) -> bool:
    """初始谓词与运行时同口径处理 Inverse（含递归子谓词）."""
    result = _initial_predicate_raw(node, monster_id, monster_rank, enemy_count, initial_values)
    return not result if node.get("Inverse", False) else result


def _initial_predicate_raw(
    node: Dict[str, Any], monster_id: str, monster_rank: str, enemy_count: int,
    initial_values: Optional[Dict[str, float]],
) -> bool:
    node_type = node.get("$type")
    if node_type == "RPG.GameCore.ByCompareDynamicValue":
        key = _dynamic_key(node.get("DynamicKey"))
        return _compare(
            _initial_dynamic(key, initial_values), _fixed_number(node.get("CompareValue")),
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
        return all(_initial_predicate(child, monster_id, monster_rank, enemy_count, initial_values)
                   for child in node.get("PredicateList") or [])
    if node_type == "RPG.GameCore.ByAny":
        return any(_initial_predicate(child, monster_id, monster_rank, enemy_count, initial_values)
                   for child in node.get("PredicateList") or [])
    if node_type == "RPG.GameCore.ByNot":
        return not _initial_predicate(
            node.get("Predicate") or {}, monster_id, monster_rank, enemy_count, initial_values)
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
            if alias in {
                    "CasterSummonedMinions", "Monster_Svarog_00_Unselectable",
                    "Monster_Svarog_00_RL_Unselectable",
                    "MMonster_W4_Claymore_01_LocalLegend_BlackSummon",
                    "MMonster_W4_Claymore_01_LocalLegend_WhiteSummon"}:
                actual = 0.0  # 初始决策评估不虚构布场召唤物或特定目标
            elif alias in {"AllDarkTeam - Caster", "Monster_W4_Griffin_00_LocalLegend_Partner"}:
                actual = max(0.0, float(enemy_count) - 1.0)
            else:
                actual = (4.0 if alias in {
                    "AllEnemy", "AllLightTeam", "AllLightTeam.RemoveServant",
                    "TauntOrAggroEnemy.RemoveServant"} else float(enemy_count))
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
    enemy_count: int = 4, initial_values: Optional[Dict[str, float]] = None,
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
                              axis.get("Predicate") or {}, monster_id, monster_rank, enemy_count,
                              initial_values)
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
    initial_values = config_ai_initial_values(config, monster_id)

    def walk(decisions: Any, enemy_count: int) -> bool:
        for decision in decisions or []:
            node_type = decision.get("$type")
            if node_type == "RPG.GameCore.AIStepperDecisionGroupConfig":
                if (_initial_decision_score(
                        decision, available_skill_ids, monster_id, monster_rank, enemy_count,
                        initial_values) > 0
                        and walk(decision.get("DecisionList"), enemy_count)):
                    return True
            elif node_type == "RPG.GameCore.AIDecisionConfig":
                if _initial_decision_score(
                        decision, available_skill_ids, monster_id, monster_rank, enemy_count,
                        initial_values) > 0:
                    return True
        return False

    return any(walk(config.get("DecisionList") or [], count) for count in (1, 4))
