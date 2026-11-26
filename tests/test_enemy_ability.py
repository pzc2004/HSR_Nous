"""通用敌人 Ability 编译器：字节码、节点拒绝、真实样例对拍与行为."""
from __future__ import annotations

import copy
import pytest
import yaml

from hsr_nous.adapters.enemy_ability import AbilityCompiler, compile_dynamic_value
from hsr_nous.pipeline.enemies.update import _download_url
from tests._data_env import enemy_ability_available, enemy_data_available


def _dynamic(opcodes: str, *, hashes=(), fixed=()):
    return {"IsDynamic": True, "PostfixExpr": {
        "OpCodes": opcodes, "DynamicHashes": list(hashes),
        "FixedValues": [{"Value": value} for value in fixed],
    }}


def test_postfix_expression_decodes_slots_and_arithmetic():
    """真实 Felling/DoT 字节码形态：槽读取、乘法和加法，不靠技能 ID 特判."""
    scaled = _dynamic("AQAAAAQR", hashes=[-1841803274], fixed=[0.1])
    assert compile_dynamic_value(scaled, {-1841803274: 4.0}) == pytest.approx(0.4)
    dot = _dynamic("AQABAQQBAgQR", hashes=[10, 20, 30])
    symbols = {10: "$self.max_hp", 20: 0.05, 30: "max(1, $modifier.stacks)"}
    assert compile_dynamic_value(dot, symbols) == \
        "0.05 * $self.max_hp * max(1, $modifier.stacks)"
    added = _dynamic("AQABAQIR", hashes=[10, 20])
    assert compile_dynamic_value(added, {10: 0.1, 20: 0.08}) == pytest.approx(0.18)


def test_postfix_expression_decodes_numeric_equality():
    comparison = _dynamic("AQAAAAYR", hashes=[10], fixed=[4])
    assert compile_dynamic_value(comparison, {10: 4}) == 1.0
    assert compile_dynamic_value(comparison, {10: 3}) == 0.0
    assert compile_dynamic_value(comparison, {10: "dynamic_of($self.actor_id, 'Score')"}) == \
        "dynamic_of($self.actor_id, 'Score') == 4"


def test_postfix_expression_rejects_unknown_hash_and_opcode():
    with pytest.raises(ValueError, match="未知 DynamicHash"):
        compile_dynamic_value(_dynamic("AQAR", hashes=[123]), {})
    with pytest.raises(ValueError, match="未知 PostfixExpr opcode"):
        bad = _dynamic("AQAR", hashes=[123])
        bad["PostfixExpr"]["OpCodes"] = "Fw=="
        compile_dynamic_value(bad, {123: 1})


def test_postfix_expression_rejects_division_by_zero():
    with pytest.raises(ValueError, match="除数为 0"):
        compile_dynamic_value(_dynamic("AQAAAAUR", hashes=[10], fixed=[0]), {10: 4})


def test_config_download_url_uses_repository_root_not_excel_output():
    assert "/raw/main/Config/ConfigAbility/" in _download_url("Config/ConfigAbility/x.json")
    assert "/raw/main/ExcelOutput/MonsterConfig.json" in _download_url("MonsterConfig.json")


def test_ability_download_closure_uses_json_config_and_remote_index(tmp_path):
    import json
    from hsr_nous.pipeline.enemies.update import _ability_companions, _referenced_character_configs
    config = "Config/ConfigCharacter/Monster/Fake_Config.json"
    ability = "Config/ConfigAbility/Monster/Fake_Ability.json"
    (tmp_path / "MonsterTemplateConfig.json").write_text(json.dumps([
        {"MonsterTemplateID": 1, "JsonConfig": config},
        {"MonsterTemplateID": 2, "JsonConfig": "../escape.json"},
    ]), encoding="utf-8")
    configs = _referenced_character_configs(tmp_path)
    assert configs == [config]
    assert _ability_companions(configs, {ability}) == sorted([config, ability])
    assert _ability_companions(configs, set()) == [config]


def test_update_downloads_character_and_ability_configs(tmp_path, monkeypatch):
    import json
    from hsr_nous.pipeline.enemies import update as enemy_update
    config = "Config/ConfigCharacter/Monster/Fake_Config.json"
    ability = "Config/ConfigAbility/Monster/Fake_Ability.json"
    tables = {
        "MonsterConfig.json": [],
        "MonsterTemplateConfig.json": [{"MonsterTemplateID": 1, "JsonConfig": config}],
        "MonsterSkillConfig.json": [], "EliteGroup.json": [], "HardLevelGroup.json": [],
        "BattleTargetConfig.json": [],
    }

    def fake_download(url, *, timeout):
        filename = url.rsplit("/main/", 1)[1].removeprefix("ExcelOutput/")
        if filename in tables:
            return json.dumps(tables[filename]).encode(), "etag"
        if filename in {config, ability, *enemy_update.GLOBAL_MODIFIER_FILES,
                        *enemy_update.GLOBAL_TASK_LIST_FILES}:
            return b"{}", "etag"
        raise AssertionError(f"未预期下载 {filename}")

    monkeypatch.setattr("hsr_nous.pipeline.build.update.download_with_etag", fake_download)
    monkeypatch.setattr(enemy_update, "_remote_ability_file_index", lambda _timeout: {ability})
    assert enemy_update.run_update(data_dir=str(tmp_path)) == 0
    assert (tmp_path / config).is_file() and (tmp_path / ability).is_file()
    for filename in (*enemy_update.GLOBAL_MODIFIER_FILES,
                     *enemy_update.GLOBAL_TASK_LIST_FILES):
        assert (tmp_path / filename).is_file()


def test_global_modifier_index_reads_modifier_map(tmp_path):
    import json
    from hsr_nous.pipeline.enemies.loader import _ability_index
    filename = "Config/ConfigGlobalModifier/GlobalModifier_Common_Specific.json"
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ModifierMap": {
        "MCommon_DOT_Poison": {"MaxLayer": 5},
    }}), encoding="utf-8")
    index = _ability_index(str(tmp_path))
    source, definition = index["modifiers"]["MCommon_DOT_Poison"][0]
    assert source == filename and definition["MaxLayer"] == 5


def test_battle_target_param_loader(tmp_path):
    import json
    from hsr_nous.pipeline.enemies.loader import get_battle_target_param

    (tmp_path / "BattleTargetConfig.json").write_text(json.dumps([
        {"ID": 5001802, "TargetParam": 6},
        {"ID": 5001803},
    ]), encoding="utf-8")
    assert get_battle_target_param(5001802, tbgd_dir=str(tmp_path)) == 6
    assert get_battle_target_param(5001803, tbgd_dir=str(tmp_path)) is None
    assert get_battle_target_param(9999999, tbgd_dir=str(tmp_path)) is None


def test_battle_target_param_compiles_static_threshold():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByBattleTargetParam",
        "BattleTargetID": 5001802, "DynamicKey": "_BattleTarget_S1_2_Param",
    }, {
        "$type": "RPG.GameCore.SetDynamicValueByBattleTargetParam",
        "BattleTargetID": 5001803, "DynamicKey": "_BattleTarget_S1_3_Param",
    }]
    sources["battle_target_params"] = {5001802: 6, 5001803: 10}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [(effect["dynamic_key"], effect["amount"]) for effect in effects] == [
        ("_BattleTarget_S1_2_Param", 6), ("_BattleTarget_S1_3_Param", 10)]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"] == {
        "_BattleTarget_S1_2_Param": 6, "_BattleTarget_S1_3_Param": 10}

    sources["abilities"]["A"]["OnStart"].append({
        "$type": "RPG.GameCore.SetDynamicValueByBattleTargetParam",
        "BattleTargetID": 9999999, "DynamicKey": "Unknown",
    })
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("BattleTargetID/TargetParam" in issue["reason"]
               for issue in rejected["unsupported"])


def test_battle_target_progress_accumulates_on_level_blackboard():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.SetBattleTargetProgress",
        "BattleTargetID": {"IsDynamic": False, "FixedValue": {"Value": 5000703}},
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {
        "effect_type": "set_dynamic_value", "target": "$level",
        "dynamic_key": "_battle_target_progress:5000703",
        "amount": "dynamic_of($level, '_battle_target_progress:5000703') + (1)",
    }

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    for _ in range(6):
        eng._hooks._run_hook_effect(source, effect, {})
    values = eng._enemy_policy_state["$level"]["dynamic_values"]
    assert values["_battle_target_progress:5000703"] == 6
    assert "$level" not in eng.state.actors

    rejected = _task_skill({
        "$type": "RPG.GameCore.SetBattleTargetProgress",
        "BattleTargetID": {"IsDynamic": False, "FixedValue": {"Value": 0}},
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert not rejected["ok"]
    assert any("关卡目标 ID 需为正整数" in issue["reason"]
               for issue in rejected["unsupported"])


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实 GlobalModifier 数据缺失")
def test_builtin_behavior_flags_match_official_global_modifiers():
    from hsr_nous.pipeline.enemies.loader import _ability_index

    modifiers = _ability_index()["modifiers"]
    for name, expected in AbilityCompiler._BUILTIN_BEHAVIOR_FLAGS.items():
        _, definition = modifiers[name][0]
        assert set(definition.get("BehaviorFlagList") or []) == expected, name


def test_dynamic_ability_references_enter_source_closure():
    from hsr_nous.pipeline.enemies.loader import _config_refs
    tasks = [
        {"$type": "RPG.GameCore.AddStageAbilityByName",
         "StageAbilityName": {"Value": "Stage"}},
        {"$type": "RPG.GameCore.OwnerEntityAddAbility",
         "AbilityName": {"Value": "Owned"}},
        {"$type": "RPG.GameCore.TriggerParallelAbility", "ParallelAbilityList": [{
            "AbilityName": {"Value": "Parallel"},
        }]},
        {"$type": "RPG.GameCore.IncludeTaskListTemplate", "Name": "Shared"},
    ]
    assert set(_config_refs(tasks)) == {
        ("ability", "Stage"), ("ability", "Owned"), ("ability", "Parallel"),
        ("template", "Shared")}


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_real_stage_ability_enters_source_closure():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources
    sources = get_enemy_ability_sources("5012030")
    assert "Monster_W5_JK_00_PowerOut" in sources["abilities"]


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_instance_dynamic_values_join_custom_values():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources
    sources = get_enemy_ability_sources("2024016")
    assert sources["custom_values"]["HardLevel"] == {"Value": 1}


def test_global_template_index_reads_file_templates(tmp_path):
    import json
    from hsr_nous.pipeline.enemies.loader import _ability_index
    filename = "Config/ConfigAbility/Monster/Fake_Ability.json"
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"GlobalTemplates": [{
        "Name": "Shared", "TaskList": [{"$type": "RPG.GameCore.DebugLog"}],
    }]}), encoding="utf-8")
    index = _ability_index(str(tmp_path))
    source, definition = index["global_templates"]["Shared"][0]
    assert source == filename and definition["Name"] == "Shared"


def test_global_task_template_index_and_reference_closure(tmp_path):
    import json
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources

    config = "Config/ConfigCharacter/Monster/Fake_Config.json"
    ability = "Config/ConfigAbility/Monster/Fake_Ability.json"
    task_file = "Config/ConfigGlobalTaskListTemplate/GlobalTaskListTemplate.json"

    def write(filename, value):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    write("MonsterConfig.json", [{"MonsterID": 1, "MonsterTemplateID": 1}])
    write("MonsterTemplateConfig.json", [{
        "MonsterTemplateID": 1, "JsonConfig": config}])
    write(config, {"SkillList": [{"Name": "Skill01", "EntryAbility": "A"}]})
    write(ability, {"AbilityList": [{
        "Name": "A",
        "OnStart": [{"$type": "RPG.GameCore.IncludeTaskListTemplate", "Name": "Shared"}],
        "Modifiers": {"Mark": {"MaxLayer": 1}},
    }]})
    write(task_file, {"TaskListTemplate": [{
        "Name": "Shared",
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Mark"}}],
    }]})

    sources = get_enemy_ability_sources("1", tbgd_dir=str(tmp_path))
    assert sources["global_templates"]["Shared"]["Name"] == "Shared"
    assert sources["modifiers"]["Mark"]["MaxLayer"] == 1
    assert task_file in sources["source_files"]


def test_cross_file_target_alias_enters_source_closure(tmp_path):
    import json
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources

    config = "Config/ConfigCharacter/Monster/Fake_Config.json"
    ability = "Config/ConfigAbility/Monster/Fake_Ability.json"
    aliases = "Config/ConfigAbility/Monster/Fake_Aliases.json"

    def write(filename, value):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    write("MonsterConfig.json", [{"MonsterID": 1, "MonsterTemplateID": 1}])
    write("MonsterTemplateConfig.json", [{
        "MonsterTemplateID": 1, "JsonConfig": config}])
    write(config, {"SkillList": [{
        "Name": "Skill01", "SkillType": "Skill",
        "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
    }]})
    write(ability, {"AbilityList": [{
        "Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.ForceKill",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Shared"},
        }],
    }]})
    write(aliases, {"GlobalTargetAlias": {"Shared": {
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 405301}},
            }},
        ],
    }}})

    sources = get_enemy_ability_sources("1", tbgd_dir=str(tmp_path))
    assert sources["target_aliases"]["Shared"]["$type"] == "RPG.GameCore.TargetSequence"
    assert aliases in sources["source_files"]
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("1", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["target"] == {
        "pool": "enemies", "where": "monster_unique_id($it) == 405301"}


def test_suffixed_and_nested_target_aliases_enter_source_closure(tmp_path):
    import json
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources

    config = "Config/ConfigCharacter/Monster/Fake_Config.json"
    ability = "Config/ConfigAbility/Monster/Fake_Ability.json"
    aliases = "Config/ConfigAbility/Monster/Fake_Aliases.json"

    def write(filename, value):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    write("MonsterConfig.json", [{"MonsterID": 1, "MonsterTemplateID": 1}])
    write("MonsterTemplateConfig.json", [{
        "MonsterTemplateID": 1, "JsonConfig": config}])
    write(config, {"SkillList": [{
        "Name": "Skill01", "SkillType": "Skill",
        "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
    }]})
    write(ability, {"AbilityList": [{
        "Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.ForceKill",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Shared.Select1"},
        }],
    }]})
    write(aliases, {"GlobalTargetAlias": {
        "Shared": {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "Nested"}]},
        "Nested": {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"}]},
    }})

    sources = get_enemy_ability_sources("1", tbgd_dir=str(tmp_path))
    assert set(sources["target_aliases"]) == {"Shared", "Nested"}
    assert not sources["ambiguous"]


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_real_cross_file_target_alias_enters_source_closure():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources

    name = "MMonster_W4_Claymore_01_LocalLegend_BlackCurse_Target"
    sources = get_enemy_ability_sources("4032052")
    assert name in sources["target_aliases"]
    assert f"target_alias:{name}" not in sources["ambiguous"]


def test_local_modifier_scope_disambiguates_source_closure(tmp_path):
    import json
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources

    config_a = "Config/ConfigCharacter/Monster/Fake_A.json"
    config_b = "Config/ConfigCharacter/Monster/Fake_B.json"
    ability = "Config/ConfigAbility/Monster/Fake_Ability.json"

    def write(filename, value):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    add_marker = {"$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Mark"}}
    write("MonsterConfig.json", [
        {"MonsterID": 1, "MonsterTemplateID": 1},
        {"MonsterID": 2, "MonsterTemplateID": 2},
    ])
    write("MonsterTemplateConfig.json", [
        {"MonsterTemplateID": 1, "JsonConfig": config_a},
        {"MonsterTemplateID": 2, "JsonConfig": config_b},
    ])
    write(config_a, {"SkillList": [{"Name": "Skill01", "EntryAbility": "A"}]})
    write(config_b, {"SkillList": [
        {"Name": "Skill01", "EntryAbility": "A"},
        {"Name": "Skill02", "EntryAbility": "B"},
    ]})
    write(ability, {"AbilityList": [
        {"Name": "A", "OnStart": [add_marker], "Modifiers": {"Mark": {"MaxLayer": 2}}},
        {"Name": "B", "OnStart": [add_marker], "Modifiers": {"Mark": {"MaxLayer": 9}}},
    ]})

    sources = get_enemy_ability_sources("1", tbgd_dir=str(tmp_path))
    assert sources["modifiers"]["Mark"]["MaxLayer"] == 2
    assert "modifier:Mark" not in sources["ambiguous"]
    assert "Mark" not in sources["missing_modifiers"]

    ambiguous = get_enemy_ability_sources("2", tbgd_dir=str(tmp_path))
    assert "Mark" not in ambiguous["modifiers"]
    assert "modifier:Mark" in ambiguous["ambiguous"]


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_real_local_modifier_scope_resolves_enter_battle():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources

    name = "MMonster_XP_Minion04_02_P01_EnterBattle"
    sources = get_enemy_ability_sources("8002060")
    assert name in sources["modifiers"]
    assert f"modifier:{name}" not in sources["ambiguous"]


def test_unknown_task_is_structured_unsupported():
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "SuccessTaskList": [{"$type": "RPG.GameCore.DefineDynamicValue"}],
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]
    assert any(item["node_type"] == "RPG.GameCore.PredicateTaskList"
               for item in out["unsupported"])
    assert any("未注册" in item["reason"] for item in out["unsupported"])


def _predicate_skill(predicate):
    return [{
        "skill_id": "s1", "trigger_key": "Skill01", "param_list": [],
    }], {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.PredicateTaskList", "Predicate": predicate,
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.DefineDynamicValue",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "DynamicKey": {"Value": "PredicateResult"},
                "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
        }]}},
        "modifiers": {},
    }


@pytest.mark.parametrize(("alias", "namespace"), [
    ("Monster_W4_Nikadory_00_Self", "$self"),
    ("CasterSummoner", "summoner_of($self.actor_id)"),
    ("ParamEntity", "$it"),
])
def test_monster_phase_predicate_uses_resolved_target(alias, namespace):
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterPhase",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "CompareType": "GreaterEqual",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert f"dynamic_of({namespace}, 'current_phase') >= 2" in out["hooks"][0]["condition"]


def test_monster_phase_predicate_target_set_uses_count():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterPhase",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterLeftEntity"},
        "CompareType": "Equal",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "count_selected" in out["hooks"][0]["condition"]
    assert "dynamic_of($it, 'current_phase') == 2" in out["hooks"][0]["condition"]


def test_monster_self_alias_is_shared_by_modifier_predicate():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Monster_W4_Nikadory_00_Self"},
        "ModifierName": {"Value": "Mark"},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "has_modifier($self.actor_id, 'Mark')" in out["hooks"][0]["condition"]


def test_summoner_phase_predicate_reads_summoner_runtime():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterPhase",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummoner"},
        "CompareType": "Equal",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    boss = make_dummy("boss")
    part = make_dummy("part")
    part.summoner_id = "boss"
    eng = engine_vs_dummy(enemies=[boss, part])
    runtime = eng._enemy_policy_state.setdefault("boss", {"current_phase": 1})
    condition = out["hooks"][0]["condition"]
    payload = {"actor": "part", "action_id": "s1"}
    runtime["current_phase"] = 2
    assert eng._hooks._hook_amount(condition, eng.state.actors["part"], payload) == 1.0
    runtime["current_phase"] = 1
    assert eng._hooks._hook_amount(condition, eng.state.actors["part"], payload) == 0.0


def test_target_team_predicates_use_actor_type_vocabulary():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByTargetTeam",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Team": "TeamDark",
    })
    dark = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert dark["ok"] and "actor_type_of($self.actor_id) == 'monster'" in dark["hooks"][0]["condition"]

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByTargetTeam",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "Team": "TeamLight", "Inverse": True,
    })
    light = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert light["ok"] and "not (actor_type_of($event.target) == 'character'" in light["hooks"][0]["condition"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    assert eng._hooks._hook_amount(dark["hooks"][0]["condition"], source, {
        "actor": "source", "action_id": "s1"}) == 1.0
    assert eng._hooks._hook_amount(dark["hooks"][0]["condition"], hero, {
        "actor": "hero", "action_id": "s1"}) == 0.0
    assert eng._hooks._hook_amount(light["hooks"][0]["condition"], source, {
        "actor": "source", "action_id": "s1", "target": "source"}) == 1.0
    assert eng._hooks._hook_amount(light["hooks"][0]["condition"], source, {
        "actor": "source", "action_id": "s1", "target": "hero"}) == 0.0


def test_wave_and_alive_enemy_number_predicates_use_runtime_sides():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareWaveCount",
        "CompareType": "Equal", "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    wave = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert wave["ok"] and "wave_index() == 1" in wave["hooks"][0]["condition"]

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareAliveEnemyNumber",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "CompareType": "Greater", "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    alive = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert alive["ok"] and "side_size($self.actor_id" in alive["hooks"][0]["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")],
                          allies=[make_actor("a1"), make_actor("a2")])
    source = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1"}
    eng.current_wave = 1
    assert eng._hooks._hook_amount(wave["hooks"][0]["condition"], source, payload) == 1.0
    assert eng._hooks._hook_amount(alive["hooks"][0]["condition"], source, payload) == 1.0
    eng.state.actors["a2"].alive = False
    eng.current_wave = 2
    assert eng._hooks._hook_amount(wave["hooks"][0]["condition"], source, payload) == 0.0
    assert eng._hooks._hook_amount(alive["hooks"][0]["condition"], source, payload) == 0.0


@pytest.mark.parametrize(("alias", "pool"), [
    ("AllEnemy", "allies"), ("AllTeammate", "enemies"), ("Caster", "self"),
])
def test_target_list_any_uses_target_algebra(alias, pool):
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByTargetListAny",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "Predicate": {
            "$type": "RPG.GameCore.ByIsContainModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "Mark"},
        },
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert f'count_selected("{pool}"' in condition and "has_modifier($it, 'Mark')" in condition

    if alias == "AllEnemy":
        eng = engine_vs_dummy(enemies=[make_dummy("source")])
        source = eng.state.actors["source"]
        hero = eng.state.actors["hero"]
        payload = {"actor": "source", "action_id": "s1"}
        assert eng._hooks._hook_amount(condition, source, payload) == 0.0
        eng._apply_modifier(hero, Modifier(
            modifier_id="Mark", name="Mark", modifier_type="debuff"))
        assert eng._hooks._hook_amount(condition, source, payload) == 1.0


def test_param_entity_summoner_modifier_filter_reads_each_candidate_owner():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByTargetListAny",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "Predicate": {
            "$type": "RPG.GameCore.ByIsContainModifier",
            "TargetType": {
                "$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity.GetSummoner"},
            "ModifierName": {"Value": "Mark"},
        },
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "has_modifier(summoner_of($it), 'Mark')" in condition

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("servant"), make_dummy("other")])
    source = eng.state.actors["source"]
    eng.state.actors["servant"].actor.summoner_id = "source"
    payload = {"actor": "source", "action_id": "s1"}
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0
    eng._apply_modifier(source, Modifier(
        modifier_id="Mark", name="Mark", modifier_type="debuff"))
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    eng._remove_modifier(source, "Mark", "test")
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0


def test_teammate_predicate_compares_actor_sides():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsTeammate",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(condition, source, {
        "actor": "source", "action_id": "s1", "target": "source"}) == 1.0
    assert eng._hooks._hook_amount(condition, source, {
        "actor": "source", "action_id": "s1", "target": "hero"}) == 0.0

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsTeammate",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "Inverse": True,
    })
    inverse = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert inverse["ok"] and "not (" in inverse["hooks"][0]["condition"]


def test_avatar_base_type_stance_and_turn_team_predicates():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByAvatarBaseType", "BaseTypeList": ["Memory"],
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    })
    path = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert path["ok"] and "path_of($self.actor_id) == 'remembrance'" in path["hooks"][0]["condition"]

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByAvatarBaseType", "BaseTypeList": ["Knight", "Priest"],
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    })
    paths = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert paths["ok"] and "'preservation'" in paths["hooks"][0]["condition"]
    assert "'abundance'" in paths["hooks"][0]["condition"]

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareStance",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "CompareType": "Equal", "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    })
    stance = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert stance["ok"] and "toughness_of($self.actor_id) == 0" in stance["hooks"][0]["condition"]

    skills, sources = _predicate_skill({"$type": "RPG.GameCore.ByCompareTurnActionEntityTeamType",
                                       "Team": "TeamDark"})
    dark = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    skills, sources = _predicate_skill({"$type": "RPG.GameCore.ByCompareTurnActionEntityTeamType",
                                       "Team": "TeamLight"})
    light = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")

    memo = make_actor("memo")
    memo.actor_type = "summon"
    eng = engine_vs_dummy(enemies=[make_dummy("source")], allies=[memo])
    source = eng.state.actors["source"]
    source.actor.path = "remembrance"
    payload = {"actor": "source", "action_id": "s1"}
    assert eng._hooks._hook_amount(path["hooks"][0]["condition"], source, payload) == 1.0
    source.actor.path = "destruction"
    assert eng._hooks._hook_amount(path["hooks"][0]["condition"], source, payload) == 0.0
    source.toughness = 0
    assert eng._hooks._hook_amount(stance["hooks"][0]["condition"], source, payload) == 1.0
    source.toughness = 1
    assert eng._hooks._hook_amount(stance["hooks"][0]["condition"], source, payload) == 0.0
    eng._current_turn_actor_id = "source"
    assert eng._hooks._hook_amount(dark["hooks"][0]["condition"], source, payload) == 1.0
    eng._current_turn_actor_id = "memo"
    assert eng._hooks._hook_amount(dark["hooks"][0]["condition"], source, payload) == 0.0
    assert eng._hooks._hook_amount(light["hooks"][0]["condition"], source, payload) == 1.0


def test_current_skill_target_type_and_teammate_count_predicates():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCurrentSkillTargetType",
        "TargetType": "AllEnemy", "Inverse": True,
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and "not ($event.target_type == 'aoe')" in out["hooks"][0]["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("other")])
    source = eng.state.actors["source"]
    condition = out["hooks"][0]["condition"]
    assert eng._hooks._hook_amount(condition, source, {
        "actor": "source", "action_id": "s1", "target_type": "single"}) == 1.0
    assert eng._hooks._hook_amount(condition, source, {
        "actor": "source", "action_id": "s1", "target_type": "aoe"}) == 0.0

    compiled = {}
    for count_type in (None, "Count1", "Count2", "Count3"):
        predicate = {"$type": "RPG.GameCore.ByIsMatchTeammateCount", "TeamType": "TeamDark"}
        if count_type is not None:
            predicate["CountType"] = count_type
        skills, sources = _predicate_skill(predicate)
        compiled[count_type] = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
        assert compiled[count_type]["ok"] and not compiled[count_type]["unsupported"]
    payload = {"actor": "source", "action_id": "s1"}
    assert eng._hooks._hook_amount(compiled["Count2"]["hooks"][0]["condition"], source, payload) == 1.0
    assert eng._hooks._hook_amount(compiled["Count1"]["hooks"][0]["condition"], source, payload) == 0.0
    eng.state.actors["other"].alive = False
    assert eng._hooks._hook_amount(compiled["Count1"]["hooks"][0]["condition"], source, payload) == 1.0
    eng.state.actors["source"].alive = False
    assert eng._hooks._hook_amount(compiled[None]["hooks"][0]["condition"], source, payload) == 1.0


def test_behavior_flag_inverse_is_not_dropped():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Flag": "STAT_CTRL", "Inverse": True,
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "not controlled($self.actor_id)" in out["hooks"][0]["condition"]


def test_disable_action_behavior_flag_uses_prevent_action_state():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Flag": "DisableAction",
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "action_disabled($self.actor_id)" in out["hooks"][0]["condition"]


def test_taunt_behavior_flag_uses_control_kind():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Flag": "Taunt",
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "controlled($self.actor_id, 'taunt')" in out["hooks"][0]["condition"]


def test_dot_behavior_flag_uses_dot_count():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Flag": "STAT_DOT",
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "dot_count($self.actor_id) > 0" in out["hooks"][0]["condition"]


def test_electric_behavior_flag_uses_exact_dot_kind():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "Flag": "STAT_DOT_Electric",
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "dot_kind($event.target, 'shock')" in condition

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    payload = {"actor": "source", "action_id": "s1", "target": "hero"}
    hero.modifiers["BURN"] = Modifier(
        modifier_id="BURN", name="Burn", modifier_type="dot", dot_element="fire")
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0
    hero.modifiers["SHOCK"] = Modifier(
        modifier_id="SHOCK", name="Shock", modifier_type="dot", dot_element="thunder")
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0


@pytest.mark.parametrize("flag", ["Stealth", "MuteHitH"])
def test_raw_behavior_flag_reads_current_modifier_flags(flag):
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "Flag": flag,
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert f'has_behavior_flag($event.target, "{flag}")' in condition

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    payload = {"actor": "source", "action_id": "s1", "target": "hero"}
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0
    hero.modifiers["FLAG"] = Modifier(
        modifier_id="FLAG", name=flag, modifier_type="buff",
        behavior_flags=[flag])
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0


def test_stance_ratio_greater_zero_reads_current_toughness():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareStanceRatio",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "CompareType": "Greater",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "toughness_of($self.actor_id) > 0" in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1", "target": "hero"}
    source.toughness = 30.0
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    source.toughness = 0.0
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0

    rejected = dict(sources["abilities"]["A"]["OnStart"][0]["Predicate"])
    rejected["CompareType"] = "Less"
    skills, sources = _predicate_skill(rejected)
    assert not AbilityCompiler("fake", skills, sources).compile_skill("Skill01")["ok"]


def test_target_able_to_action_uses_action_disabled():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsTargetAbleToAction",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "not action_disabled($self.actor_id)" in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1", "target": "hero"}
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    source.modifiers["DISABLE"] = Modifier(
        modifier_id="DISABLE", name="Disable", modifier_type="debuff", prevent_action=True)
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0


def test_target_stance_weak_uses_attacker_element():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByTargetIsStanceWeak",
        "AttackerType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "Inverse": True,
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "not (has_weakness($event.target, element_of($self.actor_id)))" in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    source.actor.element = "fire"
    payload = {"actor": "source", "action_id": "s1", "target": "hero"}
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    hero.actor.stats.weakness = ["fire"]
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0


def test_target_lock_hp_predicate_reads_modifier_lock():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByTargetLockHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "Inverse": True,
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "not hp_locked($self.actor_id)" in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1", "target": "hero"}
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    source.modifiers["LOCK"] = Modifier(
        modifier_id="LOCK", name="Lock", modifier_type="buff", hp_lock=True)
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0


@pytest.mark.parametrize(("flag", "kind"), [
    ("STAT_CTRL_Stun", "stun"),
    ("STAT_Entangle", "entangle"),
])
def test_control_behavior_flags_use_exact_control_kind(flag, kind):
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "Flag": flag,
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert f"controlled($event.target, '{kind}')" in condition

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    payload = {"actor": "source", "action_id": "s1", "target": "hero"}
    eng._apply_modifier(hero, Modifier(
        modifier_id="idle", name="Idle", modifier_type="debuff", prevent_action=True))
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0
    eng._apply_modifier(hero, Modifier(
        modifier_id=kind, name=kind, modifier_type="debuff",
        debuff_kind="control", control_kind=kind))
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0


def test_common_stun_modifier_preserves_control_and_disable_action():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "ModifierName": {"Value": "MCommon_CTRL_Stun"},
        "LifeTime": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["control_kind"] == "stun"
    assert effect["modifier"]["debuff_kind"] == "control"
    assert effect["modifier"]["prevent_action"] is True

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    stunned = eng.state.actors["hero"].modifiers["MCommon_CTRL_Stun"]
    assert stunned.prevent_action and stunned.control_kind == "stun"


def test_immune_debuff_modifier_and_predicate_share_full_immunity():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "Flag": "ImmuneDebuff",
    })
    predicate_out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert predicate_out["ok"] and not predicate_out["unsupported"]
    condition = predicate_out["hooks"][0]["condition"]
    assert "immune_debuff($event.target)" in condition

    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "ModifierName": {"Value": "Immune"},
    }]
    sources["modifiers"] = {"Immune": {"BehaviorFlagList": ["ImmuneDebuff"]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["grants_immune"] == ["debuff", "dot", "control"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    payload = {"actor": "source", "action_id": "s1", "target": "hero"}
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    for incoming in (
        Modifier(modifier_id="debuff", name="debuff", modifier_type="debuff"),
        Modifier(modifier_id="dot", name="dot", modifier_type="dot"),
        Modifier(modifier_id="control", name="control", modifier_type="debuff",
                 debuff_kind="control", control_kind="stun"),
    ):
        assert eng._apply_modifier(hero, incoming) is False

    eng._remove_modifier(hero, "Immune", "test")
    eng._apply_modifier(hero, Modifier(
        modifier_id="control_only", name="control only", modifier_type="buff",
        grants_immune=["control"]))
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0


def test_stack_status_resistance_uses_control_type_res_zone():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "ModifierName": {"Value": "ControlResist"},
    }]
    sources["modifiers"] = {"ControlResist": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackStatusResistance",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "BehaviorFlag": "STAT_CTRL",
            "Resistance": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["stat_effects"] == {"control_type_res": 1.0}

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, effect, {})
    stats = eng.pipeline.effective_stats(hero)
    assert stats["control_type_res"] == 1.0 and stats["effect_res"] == 0.0
    assert eng._apply_modifier(hero, Modifier(
        modifier_id="control", name="control", modifier_type="debuff",
        debuff_kind="control", control_kind="stun"), apply_chance=1.0) is False
    assert eng._apply_modifier(hero, Modifier(
        modifier_id="ordinary", name="ordinary", modifier_type="debuff"),
        apply_chance=1.0) is True

    sources["modifiers"]["ControlResist"]["_CallbackList"][0]["CallbackConfig"][0].update({
        "BehaviorFlag": "Taunt",
        "Resistance": {"IsDynamic": False, "FixedValue": {"Value": -1}},
    })
    taunt = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert taunt["ok"] and not taunt["unsupported"]
    assert taunt["hooks"][0]["effects"][0]["modifier"]["stat_effects"] == {
        "control_type_res": -1.0,
    }


@pytest.mark.parametrize(("alias", "expected"), [
    ("AbilityTargetAdjoinEntity", 'count_selected("allies", "is_adjacent($it, $event.target)")'),
    ("ParamEntityAdjoinEntity", 'count_selected("allies", "is_adjacent($it, $event.target)")'),
    ("AbilityTargetAndAdjoinEntity",
     'count_selected("allies", "($it.actor_id == $event.target or is_adjacent($it, $event.target))")'),
    ("CasterAdjoinEntity", 'count_selected("enemies", "is_adjacent($it, $self.actor_id)")'),
])
def test_adjacent_target_counts_use_target_algebra(alias, expected):
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareCharacterNumber",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "CompareType": "Equal",
        "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert f"{expected} == 2" in out["hooks"][0]["condition"]


def test_param_entity_adjoins_use_event_target_in_real_enemy():
    real = _real_compiler("2005010").compile_enemy()
    assert not any("ParamEntityAdjoinEntity" in issue["path"]
                   for issue in real["unsupported"])
    assert any(isinstance(effect.get("target"), dict)
               and effect["target"].get("where") == "is_adjacent($it, $event.target)"
               for hook in real["hooks"] for effect in hook.get("effects", []))


@pytest.mark.parametrize(("alias", "expected"), [
    ("AllLightTeam.RemoveServant", 'count_selected("allies", "not $it.summoner_id")'),
    ("CasterSummonedMinions", 'count_selected("enemies", "$it.summoner_id == $self.actor_id")'),
    ("ModifierOwnerSummonedMinions", 'count_selected("enemies", "$it.summoner_id == $self.actor_id")'),
])
def test_composite_target_counts_use_target_algebra(alias, expected):
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareCharacterNumber",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "CompareType": "Equal",
        "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert f"{expected} == 2" in out["hooks"][0]["condition"]


def test_remove_servant_modifier_target_uses_summoner_filter():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam.RemoveServant"},
        "ModifierName": {"Value": "WMonster_TY_Elite01_00_Skill07_Mark"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["target"] == {
        "pool": "allies", "where": "not $it.summoner_id"}


def test_param_entity_actual_owner_uses_summoner_or_event_target():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    for enemy_id in ("2004013", "3021020"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("ParamEntityActualOwner" in issue["reason"] for issue in real["unsupported"])

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    target = compiler._hook_target(
        "ParamEntityActualOwner", _Context(mode="event", skill=skills[0], event="on_hp_decrease"))
    assert target == {"pool": "all", "where": (
        "$it.actor_id == (summoner_of($event.target) or $event.target)")}

    eng = engine_vs_dummy(enemies=[make_dummy("owner"), make_dummy("servant"), make_dummy("other")])
    eng.state.actors["servant"].actor.summoner_id = "owner"
    for actor_id in ("owner", "servant", "other"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    effect = {"effect_type": "remove_modifier", "target": target,
              "filter": "1 == 1", "reason": "test"}
    eng._hooks._run_hook_effect(eng.state.actors["owner"], effect, {"target": "servant"})
    assert "mark" not in eng.state.actors["owner"].modifiers
    assert "mark" in eng.state.actors["servant"].modifiers
    eng._hooks._run_hook_effect(eng.state.actors["owner"], effect, {"target": "other"})
    assert "mark" not in eng.state.actors["other"].modifiers


def test_param_entity2_target_spec_matches_event_role():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    for enemy_id in ("4064012", "5024010"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["reason"] == "目标别名未注册：ParamEntity2"
                       for issue in real["unsupported"])

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    on_kill = compiler._target_spec(
        {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity2"},
        _Context(mode="event", skill=skills[0], event="on_kill"), "kill")
    assert on_kill == {"pool": "$event.source"}
    on_stack = compiler._target_spec(
        {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity2"},
        _Context(mode="event", skill=skills[0], event="after_apply_modifier"), "stack")
    assert on_stack == {"pool": "$event.target"}

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    for actor_id in ("hero", "source"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    effect = {"effect_type": "remove_modifier", "target": on_kill,
              "filter": "1 == 1", "reason": "test"}
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {
        "source": "source", "target": "hero"})
    assert "mark" not in eng.state.actors["source"].modifiers
    assert "mark" in eng.state.actors["hero"].modifiers


def test_get_servant_and_summoner_suffixes_share_target_algebra():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    for enemy_id in ("4012060", "8034012"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["reason"].endswith(("ModifierOwnerEntity.GetServant",
                       "ModifierOwnerEntity.GetSummoner", "Caster.GetServant"))
                       for issue in real["unsupported"])

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_hp_decrease")
    def target(alias):
        return compiler._target_spec(
            {"$type": "RPG.GameCore.TargetAlias", "Alias": alias}, ctx, alias)
    servant = target("ModifierOwnerEntity.GetServant")
    summoner = target("ModifierOwnerEntity.GetSummoner")
    assert target("Caster.GetServant") == servant
    assert servant == {"pool": "all", "where": "$it.summoner_id == $self.actor_id"}
    assert summoner == {"pool": "all", "where": "$it.actor_id == summoner_of($self.actor_id)"}
    difference = target("AllLightTeam - AllLightTeam.GetServant")
    assert difference["where"].startswith("not (target_in_selected")

    eng = engine_vs_dummy(enemies=[make_dummy("owner"), make_dummy("servant"), make_dummy("other")])
    eng.state.actors["servant"].actor.summoner_id = "owner"
    for actor_id in ("owner", "servant", "other"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    for holder_id, target_spec in (("owner", servant), ("servant", summoner)):
        eng._hooks._run_hook_effect(eng.state.actors[holder_id], {
            "effect_type": "remove_modifier", "target": target_spec,
            "filter": "1 == 1", "reason": "test"}, {})
    assert "mark" not in eng.state.actors["servant"].modifiers
    assert "mark" not in eng.state.actors["owner"].modifiers
    assert "mark" in eng.state.actors["other"].modifiers


def test_avatar_next_turn_owner_skips_summons_in_preview():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    real = _real_compiler("3025010").compile_enemy()
    assert not any(issue["reason"] == "目标别名未注册：AvatarNextTurnOwnerEntity"
                   for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    target = compiler._hook_target("AvatarNextTurnOwnerEntity", _Context(
        mode="event", skill=skills[0], event="on_action"))
    assert target == {"pool": "allies",
                      "where": "is_top_action_delay_target($it, 'light', 1)"}

    summon = make_actor("summon", spd=1000)
    summon.actor_type = "summon"
    summon.summoner_id = "hero"
    eng = engine_vs_dummy(allies=[summon], enemies=[make_dummy("source")])
    for actor_id in ("hero", "summon"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    eng._hooks._run_hook_effect(eng.state.actors["source"], {
        "effect_type": "remove_modifier", "target": target,
        "filter": "1 == 1", "reason": "test"}, {})
    assert "mark" not in eng.state.actors["hero"].modifiers
    assert "mark" in eng.state.actors["summon"].modifiers


def test_with_servant_remove_unselectable_suffix_order():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    real = _real_compiler("4023011").compile_enemy()
    assert not any("WithServant.RemoveUnselectable" in issue["reason"]
                   for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    alias = "ModifierOwnerEntity.WithServant.RemoveUnselectable"
    target = compiler._target_spec(
        {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        _Context(mode="event", skill=skills[0], event="on_action"), "target")
    assert target == {"concat": [{"pool": "self", "include_summons": True}],
                      "where": "$it.enemy_targetable and $it.ally_targetable"}

    selectable = make_dummy("selectable")
    blocked = make_dummy("blocked")
    eng = engine_vs_dummy(enemies=[make_dummy("owner"), selectable, blocked])
    for actor_id in ("selectable", "blocked"):
        eng.state.actors[actor_id].actor.summoner_id = "owner"
        eng.state.actors[actor_id].actor.actor_type = "summon"
    blocked.summon_flags["enemy_targetable"] = False
    for actor_id in ("owner", "selectable", "blocked"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    eng._hooks._run_hook_effect(eng.state.actors["owner"], {
        "effect_type": "remove_modifier", "target": target,
        "filter": "1 == 1", "reason": "test"}, {})
    assert "mark" not in eng.state.actors["owner"].modifiers
    assert "mark" not in eng.state.actors["selectable"].modifiers
    assert "mark" in eng.state.actors["blocked"].modifiers


def test_param_entity_with_summoner_target():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    real = _real_compiler("4063010").compile_enemy()
    assert not any(issue["reason"].endswith("ParamEntity.WithSummoner")
                   for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    target = compiler._hook_target("ParamEntity.WithSummoner", ctx)
    assert target == {"concat": [{"pool": "$event.target"}, {
        "pool": "all", "where": "$it.actor_id == summoner_of($event.target)"}]}

    eng = engine_vs_dummy(enemies=[make_dummy("owner"), make_dummy("servant"), make_dummy("other")])
    eng.state.actors["servant"].actor.summoner_id = "owner"
    for actor_id in ("owner", "servant", "other"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    eng._hooks._run_hook_effect(eng.state.actors["owner"], {
        "effect_type": "remove_modifier", "target": target,
        "filter": "1 == 1", "reason": "test"}, {"target": "servant"})
    assert "mark" not in eng.state.actors["owner"].modifiers
    assert "mark" not in eng.state.actors["servant"].modifiers
    assert "mark" in eng.state.actors["other"].modifiers


def test_get_battle_event_targets_creator_owned_pseudo_entity():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    real = _real_compiler("3014020").compile_enemy()
    assert not any(issue["reason"].endswith("ModifierOwnerEntity.GetBattleEvent")
                   for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    target = compiler._hook_target("ModifierOwnerEntity.GetBattleEvent", _Context(
        mode="event", skill=skills[0], event="after_apply_modifier"))
    assert target == {"pool": "battle_events", "where": "$it.summoner_id == $self.actor_id"}

    eng = engine_vs_dummy(enemies=[make_dummy("owner"), make_dummy("other")])
    for actor_id, event_id in (("owner", 60001), ("other", 60002)):
        eng._hooks._run_hook_effect(eng.state.actors[actor_id], {
            "effect_type": "create_battle_event", "event_id": event_id, "team": ""}, {})
    eng._hooks._run_hook_effect(eng.state.actors["owner"], {
        "effect_type": "apply_modifier", "target": target,
        "modifier": {"modifier_id": "mark", "name": "mark", "modifier_type": "debuff",
                     "duration": 0}}, {})
    first = eng.battle_events[60001]["actor_state"]
    second = eng.battle_events[60002]["actor_state"]
    assert "mark" in first.modifiers
    assert "mark" not in second.modifiers


def test_level_and_team_entities_work_as_hook_targets():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    real = _real_compiler("5012030").compile_enemy()
    assert not any(issue["reason"].endswith("LevelEntity") for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_action")
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    for alias, ref in (("LevelEntity", "$level"),
                       ("LightTeamEntity", "$light_team"), ("DarkTeamEntity", "$dark_team")):
        target = compiler._target_spec(
            {"$type": "RPG.GameCore.TargetAlias", "Alias": alias}, ctx, alias)
        assert target == {"pool": ref}
        eng._hooks._run_hook_effect(eng.state.actors["source"], {
            "effect_type": "apply_modifier", "target": target,
            "modifier": {"modifier_id": f"mark_{ref}", "name": "mark",
                         "modifier_type": "buff", "duration": 0}}, {})
        state = eng._pseudo_entity_state(ref)
        assert state is not None and f"mark_{ref}" in state.modifiers


def test_param_entity_attack_target_list_uses_hit_targets():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    real = _real_compiler("8033020").compile_enemy()
    assert not any(issue["reason"].endswith("ParamEntityAttackTargetList")
                   for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    target = compiler._target_spec(
        {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntityAttackTargetList"},
        _Context(mode="event", skill=skills[0], event="on_action_end"), "target")
    assert target == {"pool": "$event.hit_targets"}

    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    for actor_id in ("hero", "ally"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    eng._hooks._run_hook_effect(eng.state.actors["source"], {
        "effect_type": "remove_modifier", "target": target,
        "filter": "1 == 1", "reason": "test"}, {"hit_targets": ["hero"]})
    assert "mark" not in eng.state.actors["hero"].modifiers
    assert "mark" in eng.state.actors["ally"].modifiers


def test_energy_gain_accepts_unique_bound_battle_event():
    from tests._builders import engine_vs_dummy, make_dummy

    real = _real_compiler("4015011").compile_enemy()
    assert not any("unique:HealBattleEvent" in issue["reason"] for issue in real["unsupported"])
    out = _task_skill({
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "unique:HealBattleEvent"},
        "FixedAddValue": {"IsDynamic": False, "FixedValue": {"Value": 5}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "gain_energy"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, {
        "effect_type": "create_battle_event", "event_id": 60001, "team": ""}, {})
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_target", "dynamic_key": "HealBattleEvent",
        "scope": "unique_name", "target": {"pool": "battle_events",
            "where": "$it.actor_id == '$battle_event:60001'"}}, {})
    eng._hooks._run_hook_effect(source, effect, {})
    event = eng.battle_events[60001]["actor_state"]
    assert event.current_energy == pytest.approx(5.0)


def test_lose_hp_caster_summoner_uses_target_algebra():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.LoseHPByRatio",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummoner"},
        "SourceType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummoner"},
        "RatioType": "MaxHP", "Ratio": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
        "Floor": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == {"pool": "all",
                                "where": "$it.actor_id == summoner_of($self.actor_id)"}

    eng = engine_vs_dummy(enemies=[make_dummy("owner", hp=1000), make_dummy("servant", hp=1000)])
    eng.state.actors["servant"].actor.summoner_id = "owner"
    eng._hooks._run_hook_effect(eng.state.actors["servant"], effect, {})
    assert eng.state.actors["owner"].current_hp == pytest.approx(750.0)
    assert eng.state.actors["servant"].current_hp == pytest.approx(1000.0)


def test_trailblazer_alias_uses_character_identity_set():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    real = _real_compiler("4035010").compile_enemy()
    assert not any(issue["reason"].endswith("Trailblazer") for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    target = compiler._hook_target("Trailblazer", _Context(
        mode="event", skill=skills[0], event="before_action"))
    assert target["pool"] == "allies"
    assert "'8001'" in target["where"] and "'8010'" in target["where"]

    eng = engine_vs_dummy(allies=[make_actor("8001")], enemies=[make_dummy("source")])
    for actor_id in ("hero", "8001"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    eng._hooks._run_hook_effect(eng.state.actors["source"], {
        "effect_type": "remove_modifier", "target": target,
        "filter": "1 == 1", "reason": "test"}, {})
    assert "mark" in eng.state.actors["hero"].modifiers
    assert "mark" not in eng.state.actors["8001"].modifiers


def test_modifier_owner_skill_target_list_uses_action_targets():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    real = _real_compiler("4035010").compile_enemy()
    assert not any(issue["reason"].endswith("ModifierOwnerSkillTargetEntityList")
                   for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    target = compiler._target_spec(
        {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerSkillTargetEntityList"},
        _Context(mode="event", skill=skills[0], event="on_action"), "target")
    assert target == {"pool": "$event.targets"}

    eng = engine_vs_dummy(allies=[make_actor("8001"), make_actor("8002")],
                          enemies=[make_dummy("source")])
    for actor_id in ("hero", "8001", "8002"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    eng._hooks._run_hook_effect(eng.state.actors["source"], {
        "effect_type": "remove_modifier", "target": target,
        "filter": "1 == 1", "reason": "test"}, {"targets": ["hero", "8001"]})
    assert "mark" not in eng.state.actors["hero"].modifiers
    assert "mark" not in eng.state.actors["8001"].modifiers
    assert "mark" in eng.state.actors["8002"].modifiers


def test_alias_difference_excludes_servant_subset():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    alias = "AllLightTeam - AllLightTeam.GetServant"
    real = _real_compiler("4035010").compile_enemy()
    assert not any(issue["reason"].endswith(alias) for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    target = compiler._target_spec(
        {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        _Context(mode="event", skill=skills[0], event="before_action"), "target")
    assert target["concat"][0]["pool"] == "allies"
    assert "not (target_in_selected" in target["where"]

    summon = make_actor("summon")
    summon.actor_type = "summon"
    summon.summoner_id = "hero"
    eng = engine_vs_dummy(allies=[make_actor("friend"), summon], enemies=[make_dummy("source")])
    for actor_id in ("hero", "friend", "summon"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    eng._hooks._run_hook_effect(eng.state.actors["source"], {
        "effect_type": "remove_modifier", "target": target,
        "filter": "1 == 1", "reason": "test"}, {})
    assert "mark" not in eng.state.actors["hero"].modifiers
    assert "mark" not in eng.state.actors["friend"].modifiers
    assert "mark" in eng.state.actors["summon"].modifiers


def test_energy_gain_accepts_concat_target_algebra():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    real = _real_compiler("8034012").compile_enemy()
    assert not any(issue["reason"] == "未注册玩家侧能量目标：ParamEntity"
                   for issue in real["unsupported"])
    out = _task_skill({
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": "AllLightTeam - AllLightTeam.GetServant"},
        "FixedAddValue": {"IsDynamic": False, "FixedValue": {"Value": 10}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "gain_energy"

    summon = make_actor("summon")
    summon.actor_type = "summon"
    summon.summoner_id = "hero"
    eng = engine_vs_dummy(allies=[summon], enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert eng.state.actors["hero"].current_energy == pytest.approx(10.0)
    assert summon is not None and eng.state.actors["summon"].current_energy == pytest.approx(0.0)


def test_remove_battle_event_and_servant_suffixes_compose():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    alias = "AllLightTeamWithAllLightTeamUnselectable.RemoveBattleEvent.RemoveServant"
    real = _real_compiler("8034012").compile_enemy()
    assert not any(issue["reason"].endswith(alias) for issue in real["unsupported"])
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    target = compiler._target_spec(
        {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        _Context(mode="event", skill=skills[0], event="on_action"), "target")
    assert target["pool"] == "allies" and target["include_unselectable"]
    assert "actor_type_of($it) != 'battle_event'" in target["where"]
    assert "not $it.summoner_id" in target["where"]

    summon = make_actor("summon")
    summon.actor_type = "summon"
    summon.summoner_id = "hero"
    eng = engine_vs_dummy(allies=[summon], enemies=[make_dummy("source")])
    for actor_id in ("hero", "summon"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="mark", name="mark", modifier_type="debuff"))
    eng._hooks._run_hook_effect(eng.state.actors["source"], {
        "effect_type": "remove_modifier", "target": target,
        "filter": "1 == 1", "reason": "test"}, {})
    assert "mark" not in eng.state.actors["hero"].modifiers
    assert "mark" in eng.state.actors["summon"].modifiers


@pytest.mark.parametrize(("formula", "alias", "target", "ratio", "amount"), [
    ("HealByTargetMaxHP", "AllLightTeam", "all_allies", 0, "0.25 * $target.max_hp"),
    ("HealByHealerMaxHP", "AllTeamMember", "all_enemies", 0.25, 0),
])
def test_heal_hp_uses_existing_heal_effect(formula, alias, target, ratio, amount):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.HealHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "FormulaType": formula,
        "HealPercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "heal", "target": target, "ratio": ratio, "amount": amount,
    }]


def test_heal_hp_modify_value_is_percentage_alias():
    out = _task_skill({
        "$type": "RPG.GameCore.HealHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "FormulaType": "HealByHealerMaxHP",
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
    })
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "heal", "target": "self", "ratio": 0.25, "amount": 0}]

    rejected = _task_skill({
        "$type": "RPG.GameCore.HealHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "FormulaType": "HealByHealerMaxHP",
        "HealPercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
    })
    assert not rejected["ok"]


def test_heal_hp_base_value_uses_flat_amount():
    out = _task_skill({
        "$type": "RPG.GameCore.HealHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "FormulaType": "HealByBaseValue",
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 375.0}},
    })
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "heal", "target": "self", "ratio": 0, "amount": 375.0}]


def test_heal_hp_default_formula_uses_healer_attack():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.HealHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "HealerTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "HealPercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {
        "effect_type": "heal", "target": "self", "ratio": 0, "amount": "0.25 * $self.atk"}

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=200)])
    source = eng.state.actors["source"]
    source.current_hp = 50
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.current_hp == 100

    rejected = _task_skill({
        "$type": "RPG.GameCore.HealHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "HealerTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "HealPercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
    })
    assert not rejected["ok"]
    assert any("AllEnemy" in issue["reason"] for issue in rejected["unsupported"])


def test_heal_hp_rejects_unmodelled_lost_hp_formula():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.HealHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "FormulaType": "HealByTargetLostHP",
        "HealPercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]
    assert any("HealByTargetLostHP" in item["reason"] for item in out["unsupported"])


@pytest.mark.parametrize(("value", "effect_type"), [
    (0.5, "delay_action"), (-0.5, "advance_action"),
])
def test_modify_action_delay_uses_sign_to_select_effect(value, effect_type):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifyActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "AddNormalizedValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": effect_type, "target": "$event.target", "amount": 50.0,
    }]


def test_modify_action_delay_dynamic_sign_runs_both_directions():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.ModifyActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "AddNormalizedValue": _dynamic("AQAR", hashes=[dynamic_value_hash("_MaxStance")]),
    })
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [effect["effect_type"] for effect in effects] == ["delay_action", "advance_action"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    runtime = eng._enemy_policy_state.setdefault("source", {
        "current_phase": 1, "dynamic_values": {"_MaxStance": 0.25}})
    handle = eng.scheduler.handle_of("source")
    initial = eng.scheduler._remaining[handle]
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert eng.scheduler._remaining[handle] == initial * 1.25
    runtime["dynamic_values"]["_MaxStance"] = -0.25
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert eng.scheduler._remaining[handle] == initial


def test_modify_action_delay_change_delay_version_is_preview_metadata():
    task = {
        "$type": "RPG.GameCore.ModifyActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "AddNormalizedValue": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
    }
    plain = _task_skill(task)
    versioned = _task_skill({**task, "ChangeDelayVersion": True})
    assert plain["ok"] and versioned["ok"]
    assert not plain["unsupported"] and not versioned["unsupported"]
    assert versioned["hooks"] == plain["hooks"]


def test_modify_action_delay_rejects_absolute_value_form():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifyActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "AddValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]
    assert any("AddValue" in item["reason"] for item in out["unsupported"])


@pytest.mark.parametrize(("field", "value", "amount", "fixed"), [
    ("AddValue", 20.0, 20.0, False),
    ("FixedAddValue", 20.0, 20.0, True),
    ("AddMaxSPRatio", 0.5, "0.5 * $target.max_energy", False),
    ("FixedAddMaxSPRatio", 0.5, "0.5 * $target.max_energy", True),
])
def test_modify_sp_positive_energy_forms(field, value, amount, fixed):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        field: {"IsDynamic": False, "FixedValue": {"Value": value}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    expected = {"effect_type": "gain_energy", "target": "all_allies", "amount": amount}
    if fixed:
        expected["err_exempt"] = True
    assert out["hooks"][0]["effects"] == [expected]


@pytest.mark.parametrize(("field", "value", "amount"), [
    ("AddValue", -20.0, 20.0),
    ("FixedAddValue", -20.0, 20.0),
    ("AddMaxSPRatio", -0.2, "0.2 * $target.max_energy"),
    ("FixedAddMaxSPRatio", -0.2, "0.2 * $target.max_energy"),
])
def test_modify_sp_negative_energy_forms(field, value, amount):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias",
            "Alias": "AllLightTeamOnlyAddSPOnceForServant",
        },
        field: {"IsDynamic": False, "FixedValue": {"Value": value}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "consume_energy",
        "target": {"pool": "allies", "where": "not $it.summoner_id"}, "amount": amount,
    }]


def test_modify_sp_set_value_writes_energy_without_gain_pipeline():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "BattleEvent_60030"},
        "SetValue": {"IsDynamic": False, "FixedValue": {"Value": 4}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {
        "effect_type": "set_energy", "target": {"pool": "unique:$battle_event:60030"},
        "amount": 4,
    }
    BuildCompiler()._validate_effects([effect], "模板 X")

    create = _task_skill({
        "$type": "RPG.GameCore.CreateBattleEvent",
        "EventID": {"IsDynamic": False, "FixedValue": {"Value": 60030}},
    })
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, create["hooks"][0]["effects"][0], {})
    gained = []
    eng.bus.subscribe("on_gain_energy", lambda et, payload, ctx: gained.append(payload))
    eng._hooks._run_hook_effect(source, effect, {})
    event_state = eng.battle_events[60030]["actor_state"]
    assert event_state.current_energy == 4.0
    assert event_state.actor.stats.max_energy == 0
    assert gained == []

    ignore_block = _task_skill({
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "SetValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        "IgnoreBlock": True,
    })
    assert ignore_block["ok"] and not ignore_block["unsupported"]


def test_modify_sp_retarget_enemy_targets_consumes_energy():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "TauntOrRandomEnemy"},
        "ByRandom": True,
        "TaskList": [{
            "$type": "RPG.GameCore.ModifySPNew",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "FixedAddValue": {"IsDynamic": False, "FixedValue": {"Value": -5}},
        }],
    })
    assert out["ok"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "consume_energy"
    assert effect["target"]["pool"] == "enemy_targets"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    hero.current_energy = 20.0
    eng._hooks._run_hook_effect(source, effect, {})
    assert hero.current_energy == 15.0


def test_modify_sp_battle_event_gain_ignores_character_cap():
    from tests._builders import engine_vs_dummy, make_dummy

    create = _task_skill({
        "$type": "RPG.GameCore.CreateBattleEvent",
        "EventID": {"IsDynamic": False, "FixedValue": {"Value": 60001}},
    })
    out = _task_skill({
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllUnselectable"},
        "ByRandom": True,
        "TaskList": [{
            "$type": "RPG.GameCore.ModifySPNew",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "FixedAddValue": {"IsDynamic": False, "FixedValue": {"Value": 100}},
        }],
    })
    assert out["ok"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "gain_energy"
    assert effect["target"]["pool"] == "unselectable"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, create["hooks"][0]["effects"][0], {})
    eng._hooks._run_hook_effect(source, effect, {})
    event_state = eng.battle_events[60001]["actor_state"]
    assert event_state.actor.stats.max_energy == 0
    assert event_state.current_energy == 100.0


def test_modify_sp_modifier_owner_targets_self():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "FixedAddValue": {"IsDynamic": False, "FixedValue": {"Value": -5}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "consume_energy", "target": "self", "amount": 5}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    source.current_energy = 20.0
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.current_energy == 15.0


def test_modify_current_skill_delay_cost_sets_normalized_av():
    out = _task_skill({
        "$type": "RPG.GameCore.ModifyCurrentSkillDelayCost",
        "NormalizedValue": {"IsDynamic": False, "FixedValue": {"Value": 0.01}},
        "ModifyFunction": "Set",
    })
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0] == {
        "effect_type": "set_action_delay", "target": "self", "amount": 1.0}

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifyCurrentSkillDelayCost",
        "NormalizedValue": _dynamic("AQAR", hashes=[123]),
    }]
    sources["character_config"]["DynamicValues"] = {"Floats": {
        "123": {"ReadInfo": {"Type": "SkillParam", "TriggerKey": "Skill01", "Index": 0}},
    }}
    skills[0]["param_list"] = [0.5]
    dynamic = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert dynamic["ok"] and not dynamic["unsupported"]
    assert dynamic["hooks"][0]["effects"][0]["amount"] == 50.0

    rejected = _task_skill({
        "$type": "RPG.GameCore.ModifyCurrentSkillDelayCost",
        "NormalizedValue": {"IsDynamic": False, "FixedValue": {"Value": -1}},
    })
    assert not rejected["ok"]
    assert any("非负" in u["reason"] for u in rejected["unsupported"])


def test_modify_sp_set_value_form():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        "SetValue": {"IsDynamic": False, "FixedValue": {"Value": 20}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "set_energy", "target": "all_allies", "amount": 20,
    }]


@pytest.mark.parametrize("value", [2, -1])
def test_modify_team_boost_point_adds_integer_skill_points(value):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifyTeamBoostPoint", "ModifyFunction": "Add",
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{"effect_type": "gain_skill_point", "amount": value}]


@pytest.mark.parametrize(("function", "value"), [("Add", 1.5), ("Set", 1.5)])
def test_modify_team_boost_point_rejects_fraction(function, value):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifyTeamBoostPoint", "ModifyFunction": function,
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]


def test_modify_team_boost_point_set_writes_current_sp():
    from tests._builders import engine_vs_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.ModifyTeamBoostPoint", "ModifyFunction": "Set",
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "set_skill_point", "amount": 0}

    eng = engine_vs_dummy(initial_sp=4)
    changes = []
    eng.bus.subscribe("on_skill_point_change", lambda et, payload, ctx: changes.append(payload))
    eng._hooks._run_hook_effect(eng.state.actors["e1"], effect, {})
    assert eng.state.skill_points == 0
    assert [(item["before"], item["after"]) for item in changes] == [(4, 0)]


def test_modify_team_boost_point_max_sets_sp_cap_on_stack():
    from tests._builders import engine_vs_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "BPMax"},
    }]
    sources["modifiers"] = {"BPMax": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.ModifyTeamBoostPointMax", "ModifyFunction": "Set",
            "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 999}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "set_sp_max")
    assert effect["amount"] == 999

    eng = engine_vs_dummy()
    eng._hooks._run_hook_effect(eng.state.actors["e1"], effect, {})
    assert eng.state.sp_max_override == 999
    eng._adjust_skill_points(1000)
    assert eng.state.skill_points == 999

    for function, value in (("Add", 2), ("Set", -1), ("Set", 1.5)):
        rejected = _task_skill({
            "$type": "RPG.GameCore.ModifyTeamBoostPointMax", "ModifyFunction": function,
            "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
        })
        assert not rejected["ok"]


def test_all_unselectable_alias_uses_dedicated_pool():
    out = _task_skill({
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllUnselectable"},
        "ModifierName": {"Value": "Mark"},
    })
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["target"] == {"pool": "unselectable"}


def test_all_teams_with_unselectable_includes_both_sides():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias",
            "Alias": "AllLightTeamWithAllDarkTeamWithAllUnSelectable"},
        "ModifierName": {"Value": "Mark"},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == {"pool": "all", "include_unselectable": True}

    eng = engine_vs_dummy(
        enemies=[make_dummy("source"), make_dummy("hidden_enemy")],
        allies=[make_actor("hero"), make_actor("hidden_ally")])
    eng.state.actors["hidden_enemy"].actor.summon_flags["enemy_targetable"] = False
    eng.state.actors["hidden_ally"].actor.summon_flags.update({
        "enemy_targetable": False, "ally_targetable": False})
    picked = eng._hooks._hook_target_states(
        effect["target"], eng.state.actors["source"], {})
    assert {s.actor.actor_id for s in picked} == {
        "source", "hidden_enemy", "hero", "hidden_ally"}


def test_gridfight_all_backend_selects_enemy_side_with_unselectable():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "GridFight_AllBackEnd"},
        "ModifierName": {"Value": "Mark"},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == {"pool": "enemies", "include_unselectable": True}
    eng = engine_vs_dummy(
        enemies=[make_dummy("source"), make_dummy("hidden")], allies=[make_actor("hero")])
    eng.state.actors["hidden"].actor.summon_flags["enemy_targetable"] = False
    picked = eng._hooks._hook_target_states(effect["target"], eng.state.actors["source"], {})
    assert {s.actor.actor_id for s in picked} == {"source", "hidden"}

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareCharacterNumber",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "GridFight_AllBackEnd"},
        "CompareType": "Greater",
        "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    })
    counted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert counted["ok"] and not counted["unsupported"]
    condition = counted["hooks"][0]["condition"]
    assert 'count_selected("enemies", "true", 1) > 0' in condition
    assert eng._hooks._hook_amount(condition, eng.state.actors["source"], {
        "actor": "source", "action_id": "s1"}) == 1.0


def test_variate_max_monster_phase_reads_character_config():
    skills, sources = _predicate_skill({})
    sources["character_config"]["MaxMonsterPhase"] = 3
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByVariateType",
        "DynamicKey": "PhaseCap", "VariateType": "MaxMonsterPhase",
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "PhaseCap", "amount": 3,
    }]


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_variate_max_monster_phase_derives_from_closed_phase_writes():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetMonsterPhase", "PhaseNum": 3,
    }, {
        "$type": "RPG.GameCore.SetDynamicValueByVariateType",
        "DynamicKey": "PhaseCap", "VariateType": "MaxMonsterPhase",
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    assert any(effect.get("dynamic_key") == "PhaseCap" and effect.get("amount") == 3
               for hook in out["hooks"] for effect in hook["effects"])

    sources["abilities"]["A"]["OnStart"][0] = {
        "$type": "RPG.GameCore.SetMonsterPhase", "SetMode": "Inc"}
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("闭包显式阶段写入" in issue["reason"] for issue in rejected["unsupported"])

    real = _real_compiler("8024013").compile_enemy()
    assert not any("MaxMonsterPhase" in issue["reason"] for issue in real["unsupported"])


@pytest.mark.parametrize("event", ["on_hp_decrease", "on_hp_increase"])
def test_variate_param_value_reads_hp_change_amount(event):
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event=event)
    compiler._compile_variate({
        "$type": "RPG.GameCore.SetDynamicValueByVariateType",
        "DynamicKey": "_HPChangeValue", "VariateType": "ParamValue",
    }, ctx, "P", ())
    assert not ctx.unsupported
    assert ctx.effects == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "_HPChangeValue",
        "amount": "-$event.amount" if event == "on_hp_decrease" else "$event.amount",
    }]


@pytest.mark.parametrize("event", ["on_hp_decrease", "on_hp_increase"])
def test_hp_change_param_value_predicate_uses_event_amount(event):
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event=event)
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareParamValue",
        "CompareType": "Greater",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }, ctx, "P")
    expected = "-$event.amount > 0" if event == "on_hp_decrease" else "$event.amount > 0"
    assert expression == expected
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(expression, source, {"amount": 2.0}) == (event == "on_hp_increase")
    assert not eng._hooks._hook_amount(expression, source, {"amount": 0.0})

    other = _Context(mode="event", skill=skills[0], event="on_action")
    assert compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareParamValue",
        "CompareType": "Greater",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }, other, "P") is None
    assert any("HP/战技点/能量变化事件" in issue["reason"] for issue in other.unsupported)


def test_bp_change_writes_raw_delta_and_scopes_consumer():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _real_compiler("3024020").compile_skill("Skill04")
    assert not any(item["node_type"] in {"OnListenBpChange", "RPG.GameCore.SetDynamicValueByBPChange"}
                   for item in out["unsupported"])
    hook = next(hook for hook in out["hooks"] if hook["event"] == "on_skill_point_change"
                and any(effect.get("dynamic_key") == "MDF_CurrentBPChange"
                        for effect in hook.get("effects", [])))
    assert hook["effects"][0]["amount"] == "$event.after - $event.before"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    for before, after, expected_total in ((4, 1, -3), (1, 3, -3)):
        payload = {"before": before, "after": after, "consumer": "source"}
        for effect in hook["effects"]:
            eng._hooks._run_hook_effect(source, effect, payload)
        assert eng._hooks._hook_amount(
            "dynamic_of($self.actor_id, 'MDF_CurrentBPChange')", source, {}) == after - before
        assert eng._hooks._hook_amount(
            "dynamic_of($self.actor_id, 'MDF_BPChange')", source, {}) == expected_total

    nikadory = _real_compiler("4014013").compile_enemy()
    assert not any(item["node_type"] in {
        "OnListenBpChange", "RPG.GameCore.ByCompareParamValue",
        "RPG.GameCore.SetDynamicValueByVariateType"} for item in nikadory["unsupported"])
    brave = next(hook for hook in nikadory["hooks"]
                 if hook["event"] == "on_skill_point_change"
                 and "target_lists_intersect" in hook.get("condition", ""))
    assert "$event.consumer" in brave["condition"]
    assert "$event.after - $event.before < 0" in brave["condition"]


@pytest.mark.parametrize(("raw_type", "action_type"), [
    ("BPSkill", "skill"), ("ElationDamage", "elation_damage"), ("Pursued", "follow_up"),
])
def test_attack_type_maps_bp_skill_and_elation_damage(raw_type, action_type):
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByAttackType", "AttackTypes": [raw_type],
    }, ctx, "P")
    assert expression == f"($event.action_type == '{action_type}')"
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(expression, source, {"action_type": action_type})
    assert not eng._hooks._hook_amount(expression, source, {"action_type": "basic"})

    rejected_ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    assert not compiler._predicate_expr({
        "$type": "RPG.GameCore.ByAttackType", "AttackTypes": ["UnknownType"],
    }, rejected_ctx, "P")
    assert any("UnknownType" in issue["reason"] for issue in rejected_ctx.unsupported)


def test_attack_type_maze_is_not_a_battle_hit():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByAttackType", "AttackTypes": ["Maze", "Normal"],
    }, ctx, "P")
    assert expression == "(1 == 0 or $event.action_type == 'basic')"
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(expression, source, {"action_type": "basic"})
    assert not eng._hooks._hook_amount(expression, source, {"action_type": "dot"})


def test_split_damage_predicate_reads_real_hit_payload():
    from dataclasses import replace
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByIsSplitDamage", "Inverse": True,
    }, ctx, "P")
    assert expression == "not ($event.split != '')" and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("left"), make_dummy("right")])
    source = eng.state.actors["hero"]
    assert eng._hooks._hook_amount(expression, source, {"split": ""})
    assert not eng._hooks._hook_amount(expression, source, {"split": "even"})

    events = []
    eng.bus.subscribe("after_being_hit", lambda _t, payload, _c: events.append(payload))
    action = replace(basic_action("split", target_type="aoe"), split="even")
    eng._execute_action(source, action)
    assert [payload["split"] for payload in events] == ["even", "even"]


def test_indirect_damage_predicate_reads_explicit_attack_flag():
    from dataclasses import replace
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="before_take_damage")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByIsIndirectDamage"}, ctx, "P")
    assert expression == "$event.is_indirect" and not ctx.unsupported
    inverse = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByIsIndirectDamage", "Inverse": True}, ctx, "P")
    assert inverse == "not $event.is_indirect"

    eng = engine_vs_dummy(enemies=[make_dummy("enemy")])
    source = eng.state.actors["hero"]
    assert eng._hooks._hook_amount(expression, source, {"is_indirect": True})
    assert not eng._hooks._hook_amount(expression, source, {"is_indirect": False})
    before_events = []
    events = []
    eng.bus.subscribe_waterfall(
        "before_take_damage", lambda _t, payload, _c: before_events.append(dict(payload)))
    eng.bus.subscribe("after_being_hit", lambda _t, payload, _c: events.append(dict(payload)))
    eng._execute_action(source, replace(basic_action("b"), is_indirect=True))
    eng._execute_action(source, basic_action("b"))
    eng._hooks._run_hook_effect(source, {
        "effect_type": "deal_damage", "target": "$event.target", "damage_type": "fire",
        "action_type": "follow_up", "scaling_atk": 1.0, "toughness_dmg": 0,
        "is_indirect": True,
    }, {"target": "enemy"})
    assert [payload["is_indirect"] for payload in before_events] == [True, False, True]
    assert [payload["is_indirect"] for payload in events] == [True, False, True]


def test_damage_tag_predicate_reads_explicit_numeric_tags():
    from dataclasses import replace
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareDamageTag",
        "DamageTagList": [{"EnumIndex": 3, "Value": 45}], "Inverse": True,
    }, ctx, "P")
    assert expression == "not (45 in $event.damage_tags)" and not ctx.unsupported
    rejected_ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    assert compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareDamageTag",
        "DamageTagList": [{"EnumIndex": 3, "Value": 40}, {"EnumIndex": 3, "Value": 45}],
    }, rejected_ctx, "P") is None
    assert any("单个" in issue["reason"] for issue in rejected_ctx.unsupported)

    eng = engine_vs_dummy(enemies=[make_dummy("enemy")])
    source = eng.state.actors["hero"]
    before_events, events = [], []
    eng.bus.subscribe_waterfall(
        "before_take_damage", lambda _t, payload, _c: before_events.append(dict(payload)))
    eng.bus.subscribe("after_being_hit", lambda _t, payload, _c: events.append(dict(payload)))
    eng._execute_action(source, replace(basic_action("b"), damage_tags=[45]))
    eng._execute_action(source, basic_action("b"))
    eng._hooks._run_hook_effect(source, {
        "effect_type": "deal_damage", "target": "$event.target", "damage_type": "fire",
        "action_type": "follow_up", "scaling_atk": 1.0, "toughness_dmg": 0,
        "damage_tags": [40],
    }, {"target": "enemy"})
    assert [payload["damage_tags"] for payload in before_events] == [[45], [], [40]]
    assert [payload["damage_tags"] for payload in events] == [[45], [], [40]]

    for enemy_id in ("4052010", "5012110"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.ByCompareDamageTag"
                       for issue in real["unsupported"])


def test_damage_custom_name_predicate_and_event_payload():
    from dataclasses import replace
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareDamageCustomName",
        "CustomName": {"Value": "Peacock_UseColor"},
    }, ctx, "P")
    assert expression == '$event.damage_custom_name == "Peacock_UseColor"'
    assert not ctx.unsupported
    real = _real_compiler("5013030").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.ByCompareDamageCustomName"
                   for issue in real["unsupported"])
    produced = _task_skill({
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "AttackProperty": {
            "DamageType": {"DamageType": "Fire"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 1.0}},
            "CustomName": {"Value": "Peacock_UseColor"},
        },
    })
    assert produced["action"]["damage_custom_name"] == "Peacock_UseColor"

    eng = engine_vs_dummy(enemies=[make_dummy("enemy")])
    source = eng.state.actors["hero"]
    before_events, events = [], []
    eng.bus.subscribe_waterfall(
        "before_take_damage", lambda _t, payload, _c: before_events.append(dict(payload)))
    eng.bus.subscribe("after_being_hit", lambda _t, payload, _c: events.append(dict(payload)))
    eng._execute_action(source, replace(
        basic_action("b"), damage_custom_name="Peacock_UseColor"))
    eng._execute_action(source, basic_action("b"))
    eng._hooks._run_hook_effect(source, {
        "effect_type": "deal_damage", "target": "$event.target", "damage_type": "fire",
        "action_type": "follow_up", "scaling_atk": 1.0, "toughness_dmg": 0,
        "damage_custom_name": "Hook_Custom",
    }, {"target": "enemy"})
    expected = ["Peacock_UseColor", "", "Hook_Custom"]
    assert [payload["damage_custom_name"] for payload in before_events] == expected
    assert [payload["damage_custom_name"] for payload in events] == expected


def test_block_damage_predicate_reads_triggered_barrier_after_consumption():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByIsTriggeredBlockDamage",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    }, ctx, "P")
    assert expression == "$event.block_damage_triggered" and not ctx.unsupported

    eng = engine_vs_dummy(enemies=[make_dummy("enemy")])
    enemy = eng.state.actors["enemy"]
    assert eng._hooks._hook_amount(expression, enemy, {"block_damage_triggered": True})
    assert not eng._hooks._hook_amount(expression, enemy, {"block_damage_triggered": False})
    enemy.modifiers["BARRIER"] = Modifier(
        modifier_id="BARRIER", name="Barrier", modifier_type="buff", block_damage=True)
    events = []
    eng.bus.subscribe("after_being_hit", lambda _t, payload, _c: events.append(dict(payload)))
    old_hp = enemy.current_hp
    eng._execute_action(eng.state.actors["hero"], basic_action("b"))
    assert enemy.current_hp == old_hp and "BARRIER" not in enemy.modifiers
    eng._execute_action(eng.state.actors["hero"], basic_action("b"))
    assert enemy.current_hp < old_hp
    assert [payload["block_damage_triggered"] for payload in events] == [True, False]
    assert events[0]["amount"] == 0 and events[1]["amount"] > 0

    hook_eng = engine_vs_dummy(enemies=[make_dummy("enemy")])
    hook_enemy = hook_eng.state.actors["enemy"]
    hook_enemy.modifiers["BARRIER"] = Modifier(
        modifier_id="BARRIER", name="Barrier", modifier_type="buff", block_damage=True)
    hook_events = []
    hook_eng.bus.subscribe("after_being_hit", lambda _t, payload, _c: hook_events.append(dict(payload)))
    hook_eng._hooks._run_hook_effect(hook_eng.state.actors["hero"], {
        "effect_type": "deal_damage", "target": "$event.target", "damage_type": "fire",
        "action_type": "follow_up", "scaling_atk": 1.0, "toughness_dmg": 0,
    }, {"target": "enemy"})
    assert [payload["block_damage_triggered"] for payload in hook_events] == [True]
    assert hook_events[0]["amount"] == 0


def test_attack_type_true_damage_reads_damage_type():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByAttackType", "AttackTypes": ["TrueDamage"],
    }, ctx, "P")
    assert expression == "($event.damage_type == 'true')" and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(expression, source, {"damage_type": "true"})
    assert not eng._hooks._hook_amount(expression, source, {"damage_type": "fire"})


def test_dynamic_monster_id_comparison_normalizes_numeric_value():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("2004010", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_action")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareMonsterID",
        "TargetMonsterID": _dynamic("AQAR", hashes=[dynamic_value_hash("_MaxStance")]),
    }, ctx, "P")
    assert expression == "monster_id_equals($self.actor_id, dynamic_of($self.actor_id, '_MaxStance'))"
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("2004010")])
    source = eng.state.actors["2004010"]
    runtime = eng._enemy_policy_state.setdefault("2004010", {
        "current_phase": 1, "dynamic_values": {"_MaxStance": 2004010}})
    assert eng._hooks._hook_amount(expression, source, {})
    runtime["dynamic_values"]["_MaxStance"] = 2004011
    assert not eng._hooks._hook_amount(expression, source, {})


def test_unselectable_predicate_supports_event_target():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByIsTargetUnselectable",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    }, ctx, "P")
    assert expression == "target_unselectable($event.target)" and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"target": "hero"}
    assert not eng._hooks._hook_amount(expression, source, payload)
    eng.state.actors["hero"].actor.summon_flags["enemy_targetable"] = False
    assert eng._hooks._hook_amount(expression, source, payload)

    dark = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByIsTargetUnselectable",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "SourceEntity": {"$type": "RPG.GameCore.TargetAlias", "Alias": "DarkTeamEntity"},
    }, ctx, "P2")
    flags = eng.state.actors["hero"].actor.summon_flags
    flags["enemy_targetable"] = True
    flags["ally_targetable"] = False
    assert not eng._hooks._hook_amount(dark, source, payload)
    flags["enemy_targetable"] = False
    assert eng._hooks._hook_amount(dark, source, payload)


def test_compare_stance_count_reads_declared_and_added_bars():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_action")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareStanceCount", "CompareType": "Equal",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 3}},
    }, ctx, "P")
    assert expression == "stance_count_of($self.actor_id) == 3" and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    source.actor.stats.toughness_bars = [30, 40]
    assert eng._hooks._hook_amount(expression, source, {})
    source.added_bars.append(20)
    assert not eng._hooks._hook_amount(expression, source, {})


def test_get_creator_after_hit_covers_summon_and_battle_event():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByTargetEntityType", "EntityTypeMask": "Avatar",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity.GetCreator"},
    }, ctx, "P")
    assert expression and not ctx.unsupported
    servant = make_actor("servant")
    servant.actor_type = "summon"
    servant.summoner_id = "hero"
    eng = engine_vs_dummy(allies=[servant], enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(expression, source, {"target": "servant"})
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(hero, {"effect_type": "create_battle_event", "event_id": 1}, {})
    assert eng._hooks._hook_amount(expression, source, {"target": "$battle_event:1"})
    target = compiler._hook_target("ParamEntity.GetCreator", ctx)
    assert eng._hooks._hook_target_states(target, source, {"target": "$battle_event:1"}) == [hero]


@pytest.mark.parametrize("event", ["on_hp_decrease", "on_hp_increase"])
def test_change_value_stores_hp_event_amount(event):
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event=event)
    compiler._compile_change_value({
        "$type": "RPG.GameCore.SetDynamicValueByChangeValue",
        "DynamicKey": "HPChange",
    }, ctx, "P", ())
    expected = "-$event.amount" if event == "on_hp_decrease" else "$event.amount"
    assert ctx.effects == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "HPChange", "amount": expected}]
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, ctx.effects[0], {"amount": 12.0})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["HPChange"] == (
        -12.0 if event == "on_hp_decrease" else 12.0)

    rejected = _Context(mode="event", skill=skills[0], event="on_hp_increase")
    compiler._compile_change_value({
        "$type": "RPG.GameCore.SetDynamicValueByChangeValue", "DynamicKey": "HPChange",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LevelEntity"},
    }, rejected, "P", ())
    assert any("写入自身" in issue["reason"] for issue in rejected.unsupported)


def test_active_modifier_compiles_hp_change_listener():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "HPListener"},
    }]
    sources["modifiers"]["HPListener"] = {"_CallbackList": [{
        "Event": "OnHPChange", "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValueByChangeValue", "DynamicKey": "HPChange"}],
    }]}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    listeners = [hook for hook in out["hooks"]
                 if hook["event"] in {"on_hp_decrease", "on_hp_increase"}]
    assert [hook["event"] for hook in listeners] == ["on_hp_decrease", "on_hp_increase"]
    assert listeners[0]["effects"][0]["amount"] == "-$event.amount"
    assert listeners[1]["effects"][0]["amount"] == "$event.amount"


def test_hp_ratio_dynamic_uses_hp_of():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByHPRatio", "DynamicKey": "CurrentHPRatio",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "CurrentHPRatio",
        "amount": "hp_of($self.actor_id) / max_hp_of($self.actor_id)",
    }]


def test_hp_ratio_dynamic_reads_each_retarget_entity():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_action",
                   retarget={"pool": "enemies"})
    compiler._compile_hp_ratio_dynamic({
        "$type": "RPG.GameCore.SetDynamicValueByHPRatio", "DynamicKey": "CurrentHPRatio",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    }, ctx, "P", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    assert effect["amount"] == "hp_of($target) / max_hp_of($target)"
    assert effect["amount_target"] == {"pool": "enemies"}
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("partner", hp=200)])
    source, partner = eng.state.actors["source"], eng.state.actors["partner"]
    partner.current_hp = 50
    eng._enemy_policy_state.setdefault("source", {"current_phase": 1, "dynamic_values": {}})
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["CurrentHPRatio"] == 0.25

    compiler._compile_formation_index({
        "$type": "RPG.GameCore.SetDynamicValueByFormationIndex", "DynamicKey": "IndexTarget",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    }, ctx, "P2", ())
    eng._hooks._run_hook_effect(source, ctx.effects[1], {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["IndexTarget"] == 2


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_hp_ratio_dynamic_reads_named_target_algebra():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["target_aliases"] = {"Boss": {
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "BattleAllEntity"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByIsContainModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "Mark"},
            }},
        ],
    }}
    sources["modifiers"] = {"Mark": {}}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByHPRatio", "DynamicKey": "CurrentHPRatio",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Boss"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount"] == "hp_of($target) / max_hp_of($target)"
    assert effect["amount_target"] == {
        "pool": "all_with_battle_events", "where": "has_modifier($it, 'Mark')"}

    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("partner", hp=200)])
    source, partner = eng.state.actors["source"], eng.state.actors["partner"]
    partner.current_hp = 50
    partner.modifiers["Mark"] = Modifier(
        modifier_id="Mark", name="Mark", modifier_type="buff")
    eng._enemy_policy_state.setdefault("source", {"current_phase": 1, "dynamic_values": {}})
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["CurrentHPRatio"] == 0.25

    for enemy_id in ("4033021", "4033022"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("HP 比例动态键/读取目标未注册" in issue["reason"]
                       for issue in real["unsupported"])


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_skill_max_hit_split_count_reads_actual_action_instances():
    from dataclasses import replace
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    compiler = AbilityCompiler("fake", [], {})
    ctx = _Context(mode="event", skill={"skill_id": "s1"}, event="after_being_hit")
    compiler._compile_skill_max_hit_split_count({
        "$type": "RPG.GameCore.SetDynamicValueBySkillMaxHitSplitCount",
        "DynamicKey": "MDF_SkillMaxHit",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity2"},
    }, ctx, "test", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    assert effect["amount"] == "$event.max_hit_split_count"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    events = []
    eng.bus.subscribe("after_being_hit",
                      lambda _event, payload, _ctx: events.append(dict(payload)))
    eng._execute_action(source, replace(basic_action(), instances=3),
                        forced_target=eng.state.actors["hero"])
    assert len(events) == 3
    assert {event["max_hit_split_count"] for event in events} == {3}
    eng._enemy_policy_state.setdefault("source", {"current_phase": 1, "dynamic_values": {}})
    eng._hooks._run_hook_effect(source, effect, events[0])
    assert eng._enemy_policy_state["source"]["dynamic_values"]["MDF_SkillMaxHit"] == 3

    for enemy_id in ("2004010", "2004011", "2004012", "2004013", "2004014", "2004015"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.SetDynamicValueBySkillMaxHitSplitCount"
                       for issue in real["unsupported"])


def test_variate_wave_and_character_id_in_engine():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByVariateType",
        "DynamicKey": "Wave", "VariateType": "CurWaveIndex",
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and out["hooks"][0]["effects"] == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "Wave", "amount": "wave_index()",
    }]
    eng = engine_vs_dummy(enemies=[make_dummy("12345")])
    eng.current_wave = 3
    st = eng.state.actors["12345"]
    eng._hooks._run_hook_effect(st, out["hooks"][0]["effects"][0], {})
    assert eng._enemy_policy_state["12345"]["dynamic_values"]["Wave"] == 3

    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByVariateType",
        "DynamicKey": "CharacterID", "VariateType": "TargetCharacterID",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "WriteTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LevelEntity"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and out["hooks"][0]["effects"] == [{
        "effect_type": "set_dynamic_value", "target": "$level",
        "dynamic_key": "CharacterID", "amount": "character_id($self.actor_id)",
    }]
    eng._hooks._run_hook_effect(st, out["hooks"][0]["effects"][0], {})
    assert eng._enemy_policy_state["$level"]["dynamic_values"]["CharacterID"] == 12345


def test_variate_character_id_param_entity_uses_amount_target():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValueByVariateType",
            "DynamicKey": "TargetID", "VariateType": "TargetCharacterID",
            "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "WriteTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount_target"] == {"pool": "allies"}
    assert effect["target"] == "self" and effect["amount"] == "character_id($target)"
    eng = engine_vs_dummy(hero=make_actor("12345"), enemies=[make_dummy("source")])
    st = eng.state.actors["source"]
    eng._hooks._run_hook_effect(st, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["TargetID"] == 12345


def test_attach_entity_unselectable_in_engine():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{"$type": "RPG.GameCore.AttachEntityUnselectable"}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and out["hooks"][0]["effects"] == [{
        "effect_type": "set_targetable", "target": "self",
        "enemy_targetable": False, "ally_targetable": False,
    }]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, out["hooks"][0]["effects"][0], {})
    assert not source.actor.summon_flags["enemy_targetable"]
    assert source not in eng._hostile_target_pool(hero.actor)
    eng._hooks._run_hook_effect(hero, out["hooks"][0]["effects"][0], {})
    assert not hero.actor.summon_flags["ally_targetable"]
    assert eng._pick_ally_target(source) is None


def test_unselectable_start_and_end_emit_only_on_real_transition():
    from tests._builders import engine_vs_dummy, make_dummy

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    starts, ends = [], []
    eng.bus.subscribe("on_unselectable_start", lambda _t, payload, _c: starts.append(dict(payload)))
    eng.bus.subscribe("on_unselectable_end", lambda _t, payload, _c: ends.append(dict(payload)))
    for effect in (
            {"effect_type": "set_targetable", "target": "self", "enemy_targetable": False},
            {"effect_type": "set_targetable", "target": "self", "enemy_targetable": False},
            {"effect_type": "set_targetable", "target": "self", "enemy_targetable": True},
            {"effect_type": "set_targetable", "target": "self", "ally_targetable": False},
            {"effect_type": "set_targetable", "target": "self", "ally_targetable": True}):
        eng._hooks._run_hook_effect(source, effect, {})
    assert len(starts) == 2 and len(ends) == 2
    assert starts[0] == {"target": "source", "source": "source",
                         "enemy_targetable": False, "ally_targetable": True}
    assert starts[1] == {"target": "source", "source": "source",
                         "enemy_targetable": True, "ally_targetable": False}
    assert ends[0]["enemy_targetable"] and ends[0]["ally_targetable"]
    assert ends[1]["enemy_targetable"] and ends[1]["ally_targetable"]
    real = _real_compiler("3003030").compile_enemy()
    assert not any(issue["node_type"] == "OnUnselectableStart"
                   for issue in real["unsupported"])
    end_real = _real_compiler("4014010").compile_enemy()
    assert not any(issue["node_type"] == "OnUnselectableEnd"
                   for issue in end_real["unsupported"])


def test_stack_custom_unselectable_filters_matching_source():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "WhiteMonst"},
    }]

    def task(team):
        return {
            "$type": "RPG.GameCore.StackCustomUnselectable",
            "TeamTypes": team, "EntityTypes": "All",
            "Condition": {
                "$type": "RPG.GameCore.ByIsContainModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "BlackCurse"},
            },
        }

    sources["modifiers"]["WhiteMonst"] = {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [task("TeamLight"), task("TeamNeutral")],
    }]}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    apply = out["hooks"][0]["effects"][0]
    assert apply["modifier"]["custom_unselectable"] == {
        "BlackCurse": ["light", "neutral"]}

    eng = engine_vs_dummy(
        enemies=[make_dummy("white")], allies=[make_actor("ally")])
    white = eng.state.actors["white"]
    hero = eng.state.actors["hero"]
    ally = eng.state.actors["ally"]
    eng._hooks._run_hook_effect(white, apply, {})
    hero.modifiers["BlackCurse"] = Modifier(
        modifier_id="BlackCurse", name="Black Curse", modifier_type="debuff")
    assert eng._hostile_target_pool(hero.actor) == []
    assert eng._hostile_target_pool(ally.actor) == [white]


def test_set_modifier_value_layer_and_lifetime():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetModifierValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Bullet"}, "ModifyFunction": "Add",
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and out["hooks"][0]["effects"] == [{
        "effect_type": "adjust_stacks", "target": "self", "modifier_id": "Bullet", "delta": 1.0,
    }]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    st = eng.state.actors["source"]
    st.modifiers["Bullet"] = Modifier(
        modifier_id="Bullet", name="Bullet", modifier_type="buff", duration=1, max_stack=3)
    eng._hooks._run_hook_effect(st, out["hooks"][0]["effects"][0], {})
    assert st.modifiers["Bullet"].stacks == 2

    reset_task = sources["abilities"]["A"]["OnStart"][0]
    reset_task.pop("ModifyFunction")
    reset_task["Value"] = {"IsDynamic": False, "FixedValue": {"Value": 0}}
    reset = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert reset["ok"] and reset["hooks"][0]["effects"] == [{
        "effect_type": "adjust_stacks", "target": "self", "modifier_id": "Bullet",
        "delta": "(0) - stacks($self.actor_id, 'Bullet')",
    }]

    reset_task.update({
        "ValueType": "LifeTime", "Value": {"IsDynamic": False, "FixedValue": {"Value": 2}}})
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and out["hooks"][0]["effects"] == [{
        "effect_type": "adjust_duration", "target": "self", "modifier_id": "Bullet",
        "delta": "(2) - modifier_duration($self.actor_id, 'Bullet')",
    }]
    eng._hooks._run_hook_effect(st, out["hooks"][0]["effects"][0], {})
    assert st.modifiers["Bullet"].duration == 2


def _servant_retarget(alias, *, with_definition=False):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "MCommon_Servant"},
        }],
    }]
    if with_definition:
        sources["modifiers"]["MCommon_Servant"] = {"_CallbackList": [{
            "Event": "OnCreate", "CallbackConfig": [{
                "$type": "RPG.GameCore.OwnerEntityAddAbility",
                "AbilityName": {"Value": "Common_Servant_Forcekill"},
            }],
        }]}
    return AbilityCompiler("fake", skills, sources).compile_skill("Skill01")


def test_servant_marker_uses_retarget_context():
    out = _servant_retarget("CasterSummonedMinions", with_definition=True)
    assert out["ok"] and not out["unsupported"]


def test_servant_marker_is_not_skipped_for_unproven_target():
    out = _servant_retarget("Caster")
    assert not out["ok"]
    assert any("MCommon_Servant" in issue["reason"] for issue in out["unsupported"])


@pytest.mark.parametrize(("flag", "expected_filter"), [
    ("STAT_CTRL", "$mod.kind == 'control'"),
    ("STAT_DOT", "$mod.kind == 'dot'"),
    ("DisableAction", "$mod.prevent_action"),
])
def test_remove_behavior_flag_uses_mod_filter(flag, expected_filter):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.RemoveModifierByBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        "ModifierBehaviorFlags": [flag],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "remove_modifier", "target": "all_allies",
        "filter": expected_filter, "reason": "dispel",
    }]


def test_remove_behavior_flag_matches_raw_modifier_flags():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.RemoveModifierByBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierBehaviorFlags": ["Deathrattle"],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["filter"] == "'Deathrattle' in $mod.behavior_flags"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._apply_modifier(source, Modifier(
        modifier_id="flagged", name="亡语", modifier_type="buff",
        behavior_flags=["Deathrattle"]))
    eng._apply_modifier(source, Modifier(
        modifier_id="ordinary", name="普通", modifier_type="buff"))
    eng._hooks._run_hook_effect(source, effect, {})
    assert "flagged" not in source.modifiers and "ordinary" in source.modifiers

    sources["abilities"]["A"]["OnStart"][0]["ModifierBehaviorFlags"] = [
        "AttackSign", "TeamAction"]
    combined = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert combined["ok"] and not combined["unsupported"]
    assert " or " in combined["hooks"][0]["effects"][0]["filter"]


def test_dispel_status_defaults_clear_all_including_dead():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DispelStatus",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "OnlyAlive": False, "IsSilentDispel": True,
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["filter"] == "1 == 1" and "max_count" not in effect
    BuildCompiler()._validate_effects([effect], "模板 X")

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._apply_modifier(source, Modifier(
        modifier_id="buff", name="buff", modifier_type="buff"))
    eng._apply_modifier(source, Modifier(
        modifier_id="debuff", name="debuff", modifier_type="debuff"))
    source.alive = False
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.modifiers == {}

    sources["abilities"]["A"]["OnStart"][0].update({
        "BuffType": "Buff", "Order": "LastAdded",
        "Numbers": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        "OnlyAlive": True,
    })
    buff_only = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert buff_only["ok"] and not buff_only["unsupported"]
    effect = buff_only["hooks"][0]["effects"][0]
    assert effect["filter"] == "$mod.kind == 'buff'" and effect["max_count"] == 1
    eng._apply_modifier(source, Modifier(
        modifier_id="buff", name="buff", modifier_type="buff"))
    eng._apply_modifier(source, Modifier(
        modifier_id="debuff", name="debuff", modifier_type="debuff"))
    eng._hooks._run_hook_effect(source, effect, {})
    assert "buff" not in source.modifiers and "debuff" in source.modifiers

    sources["abilities"]["A"]["OnStart"][0].pop("BuffType")
    sources["abilities"]["A"]["OnStart"][0]["BehaviorFlags"] = ["STAT_CTRL"]
    control = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert control["ok"] and control["hooks"][0]["effects"][0]["filter"] == "$mod.kind == 'control'"


def test_dispel_status_all_teammates_include_dead_targets():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DispelStatus",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "OnlyAlive": False,
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == {"pool": "enemies", "include_dead": True}

    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("other")])
    for actor_id in ("source", "other"):
        eng._apply_modifier(eng.state.actors[actor_id], Modifier(
            modifier_id="buff", name="buff", modifier_type="buff"))
    eng.state.actors["other"].alive = False
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert eng.state.actors["source"].modifiers == {}
    assert eng.state.actors["other"].modifiers == {}


def test_dispel_status_multiple_flags_and_first_added_order():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DispelStatus",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "BehaviorFlags": ["STAT_CTRL", "DisableAction", "Break"],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert "$mod.kind == 'control'" in effect["filter"]
    assert "$mod.prevent_action" in effect["filter"]
    assert "'Break' in $mod.behavior_flags" in effect["filter"]
    assert " or " in effect["filter"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._apply_modifier(source, Modifier(
        modifier_id="control", name="control", modifier_type="debuff",
        debuff_kind="control", behavior_flags=["STAT_CTRL"]))
    eng._apply_modifier(source, Modifier(
        modifier_id="break", name="break", modifier_type="debuff",
        behavior_flags=["Break", "DisableAction"], prevent_action=True))
    eng._apply_modifier(source, Modifier(
        modifier_id="ordinary", name="ordinary", modifier_type="debuff"))
    eng._apply_modifier(source, Modifier(
        modifier_id="buff", name="buff", modifier_type="buff"))
    eng._hooks._run_hook_effect(source, effect, {})
    assert set(source.modifiers) == {"ordinary", "buff"}

    sources["abilities"]["A"]["OnStart"][0].update({
        "BuffType": "Buff", "Order": "FirstAdded",
        "Numbers": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    sources["abilities"]["A"]["OnStart"][0].pop("BehaviorFlags")
    oldest = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert oldest["ok"] and not oldest["unsupported"]
    effect = oldest["hooks"][0]["effects"][0]
    assert effect["order"] == "oldest" and effect["max_count"] == 1
    source.modifiers.clear()
    eng._apply_modifier(source, Modifier(
        modifier_id="first", name="first", modifier_type="buff"))
    eng._apply_modifier(source, Modifier(
        modifier_id="second", name="second", modifier_type="buff"))
    eng._hooks._run_hook_effect(source, effect, {})
    assert "first" not in source.modifiers and "second" in source.modifiers


def test_target_count_uses_number_and_alive_flag():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    predicate = {
        "$type": "RPG.GameCore.ByCompareTargetCount",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        "AliveOnly": True, "Number": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        "CompareType": "NotEqual",
    }
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "count($team.actor_id) != 1" in out["hooks"][0]["condition"]

    predicate["AliveOnly"] = False
    skills, sources = _predicate_skill(predicate)
    included = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert included["ok"] and not included["unsupported"]
    condition = included["hooks"][0]["condition"]
    assert '\\"include_dead\\": true' in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")], allies=[make_actor("ally")])
    source = eng.state.actors["source"]
    eng.state.actors["hero"].alive = False
    payload = {"actor": "source", "action_id": "s1"}
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    alive_condition = out["hooks"][0]["condition"]
    assert eng._hooks._hook_amount(alive_condition, source, payload) == 0.0
    eng.state.actors["hero"].alive = True
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    assert eng._hooks._hook_amount(alive_condition, source, payload) == 1.0


def test_target_count_event_list_honors_alive_flag():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    predicate = {
        "$type": "RPG.GameCore.ByCompareTargetCount",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntityList"},
        "AliveOnly": False, "Number": {"IsDynamic": False, "FixedValue": {"Value": 2}},
        "CompareType": "Equal",
    }
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert '\\"include_dead\\": true' in condition and "$event.targets" in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")], allies=[make_actor("ally")])
    source = eng.state.actors["source"]
    eng.state.actors["hero"].alive = False
    payload = {"actor": "source", "action_id": "s1", "targets": ["hero", "ally"]}
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0

    predicate["AliveOnly"] = True
    predicate["Number"]["FixedValue"]["Value"] = 1
    skills, sources = _predicate_skill(predicate)
    alive = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert alive["ok"] and not alive["unsupported"]
    assert eng._hooks._hook_amount(alive["hooks"][0]["condition"], source, payload) == 1.0


def test_unselectable_dark_team_alias_uses_full_enemy_pool():
    predicate = {
        "$type": "RPG.GameCore.ByCompareCharacterNumber",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias",
            "Alias": "AllDarkTeamWithAllDarkTeamUnselectable",
        },
        "CompareType": "GreaterEqual",
        "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "enemies_alive() >= 1" in out["hooks"][0]["condition"]

    predicate["Predicate"] = {
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "Flag": "Break",
    }
    filtered = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert filtered["ok"] and not filtered["unsupported"]
    assert 'count_selected("enemies", "broken_of($it)") >= 1' in filtered["hooks"][0]["condition"]


def test_light_team_ignore_servant_excludes_summons():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareCharacterNumber",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeamIgnoreServant"},
        "CompareType": "Equal",
        "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert 'count_selected("allies", "actor_type_of($it) != \'summon\'") == 2' in out["hooks"][0]["condition"]


def test_character_count_preserves_target_predicate():
    """Cocolia `_NotBreakCount` 同形：人数写入必须保留未击破过滤."""
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByCharacterCount",
        "DynamicKey": "_NotBreakCount",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "Predicate": {
            "$type": "RPG.GameCore.ByContainBehaviorFlag",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "Flag": "Break", "Inverse": True,
        },
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount"] == 'count_selected("enemies", "not broken_of($it)")'


def test_stance_count_dynamic_value_reads_all_bars():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByStanceCount",
        "DynamicKey": "_StanceCount",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount"] == "stance_count_of($self.actor_id)"

    from tests._builders import engine_vs_dummy, make_dummy
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    source.actor.stats.toughness_bars = [30, 40]
    source.added_bars.append(20)
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["_StanceCount"] == 4


def test_attack_damage_type_switch_supports_guarded_mechanism_branches():
    skills, sources = _predicate_skill({})
    switch = {
        "$type": "RPG.GameCore.SwitchCaseByAttackDamageType",
        "Source": {"SourceType": "ReadTargetType", "ReadTargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}},
        "CaseTaskList": [{
            "Case": "Physical", "TaskList": [{
                "$type": "RPG.GameCore.TriggerEffect", "EffectPath": "break_physical",
            }],
        }, {
            "Case": "Fire", "TaskList": [{
                "$type": "RPG.GameCore.PredicateTaskList",
                "SuccessTaskList": [{"$type": "RPG.GameCore.TriggerEffect"}],
                "FailedTaskList": [{"$type": "RPG.GameCore.TriggerEffect"}],
            }],
        }],
    }
    sources["abilities"]["A"]["OnStart"] = [switch]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]

    switch["CaseTaskList"][0]["TaskList"].append({
        "$type": "RPG.GameCore.DefineDynamicValue",
        "DynamicKey": {"Value": "MechanicalBranch"},
        "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    compiled = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert compiled["ok"] and not compiled["unsupported"]
    effect = next(effect for hook in compiled["hooks"] for effect in hook["effects"]
                  if effect.get("dynamic_key") == "MechanicalBranch")
    assert effect["condition"] == "$event.damage_type == 'physical'"


def test_real_break_effect_damage_type_switch_is_presentation_only():
    out = _real_compiler("8012210").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.SwitchCaseByAttackDamageType"
                   for item in out["unsupported"])


def test_reset_teammate_attack_perform_is_presentation_cleanup():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ResetTeammateAttackPerform",
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"] and not out["hooks"]

    real = _real_compiler("2004010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ResetTeammateAttackPerform"
                   for item in real["unsupported"])


def test_boss_hp_stance_heal_change_is_presentation_only():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetBossHPStanceChangeType", "ChangeType": "Heal",
        "ChangeTime": {"IsDynamic": False, "FixedValue": {"Value": 3}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"] and not out["hooks"]

    sources["abilities"]["A"]["OnStart"][0]["ChangeType"] = "Damage"
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]

    real = _real_compiler("4035011").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.SetBossHPStanceChangeType"
                   for item in real["unsupported"])


def test_missing_monster_skill_row_allows_self_contained_ability():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DefineDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "DynamicKey": {"Value": "KnownSkill"},
        "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]
    sources["character_config"]["SkillList"].append({
        "Name": "Skill02", "SkillType": "Skill",
        "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "Empty",
    })
    sources["abilities"]["Empty"] = {
        "Name": "Empty", "TargetInfo": {"TargetType": "Caster"}, "OnStart": [],
    }
    out = AbilityCompiler("fake", skills, sources).compile_enemy()
    assert out["ok"] and not out["unsupported"]

    sources["abilities"]["Empty"]["OnStart"] = [{
        "$type": "RPG.GameCore.DefineDynamicValue", "DynamicKey": {"Value": "Mechanism"},
    }]
    self_contained = AbilityCompiler("fake", skills, sources).compile_enemy()
    assert self_contained["ok"]
    assert any(action["action_id"] == "fake:Skill02"
               for action in self_contained["actions"])

    sources["abilities"]["Empty"]["OnStart"] = [{
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "AttackProperty": {
            "DamageType": {"DamageType": "Physical"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 1.5}},
        },
    }]
    rejected = AbilityCompiler("fake", skills, sources).compile_enemy()
    assert not rejected["ok"]
    assert any(item["owner"] == "Skill02" and "StanceValue" in item["reason"]
               for item in rejected["unsupported"])


def test_orphan_tbgd_rows_require_execution_references():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DefineDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "DynamicKey": {"Value": "KnownSkill"},
        "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]
    sources["abilities"]["A"]["DynamicValues"] = {"Floats": {"1": {
        "ReadInfo": {"Type": "SkillParam", "TriggerKey": "PassiveSkill99", "Index": 0},
    }}}
    skills.extend([
        {"skill_id": "p99", "trigger_key": "SkillP99", "param_list": []},
        {"skill_id": "ps99", "trigger_key": "PassiveSkill99", "param_list": [0.25]},
    ])
    out = AbilityCompiler("fake", skills, sources).compile_enemy()
    assert out["ok"] and not out["unsupported"]

    skills.append({"skill_id": "s99", "trigger_key": "Skill99", "param_list": []})
    sources["config_ai"] = {"DecisionList": [{"RootTask": {"TaskList": [{"SkillName": "Skill99"}]}}]}
    rejected = AbilityCompiler("fake", skills, sources).compile_enemy()
    assert any(item["owner"] == "Skill99" and item["node_type"] == "SkillList"
               for item in rejected["unsupported"])


def test_real_orphan_tbgd_rows_follow_execution_references():
    for enemy_id, trigger in (("1002015", "SkillP01"), ("2024016", "SkillP02"),
                              ("1004023", "Skill12")):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["owner"] == trigger and item["node_type"] == "SkillList"
                       for item in out["unsupported"])
    active = _real_compiler("1004023").compile_enemy()
    assert any(item["owner"] == "Skill13" and item["node_type"] == "SkillList"
               for item in active["unsupported"])


def test_real_missing_skill_rows_compile_from_ability():
    for enemy_id, trigger in (("3003030", "Skill02"), ("4034010", "ChangePhase"),
                              ("1002040", "Skill02")):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["owner"] == trigger
                       and item["node_type"] == "MonsterSkillConfig"
                       for item in out["unsupported"])


@pytest.mark.parametrize("event", ["before_take_damage", "after_being_hit"])
@pytest.mark.parametrize("alias", ["Caster", "ModifierOwnerEntity"])
def test_damage_data_dynamic_value_reads_event_amount(event, alias):
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy
    compiler = AbilityCompiler("fake", [], {"character_config": {}})
    ctx = _Context(mode="event", skill={"skill_id": "s1"}, event=event)
    compiler._compile_damage_data_value({
        "$type": "RPG.GameCore.SetDynamicValueByDamageDataProperty",
        "DynamicKey": "MDF_HitDamage",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
    }, ctx, "P", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    assert effect["amount"] == "$event.amount"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {"amount": 37.5})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["MDF_HitDamage"] == 37.5


def test_real_damage_data_dynamic_values_compile():
    for enemy_id in ("4012052", "5012110"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.SetDynamicValueByDamageDataProperty"
                       for item in out["unsupported"])


def test_wait_for_only_skips_synchronous_animation_barriers():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.WaitFor",
        "Predicate": {"$type": "RPG.GameCore.ByDieAnimFinished"},
    }, {
        "$type": "RPG.GameCore.WaitFor",
        "Predicate": {"$type": "RPG.GameCore.ByHaveInsertUltraWait"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"] and not out["hooks"]

    sources["abilities"]["A"]["OnStart"][0]["Predicate"] = {
        "$type": "RPG.GameCore.ByCompareHP",
    }
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any(item["node_type"] == "RPG.GameCore.WaitFor"
               for item in rejected["unsupported"])

    for enemy_id in ("2004020", "3025010"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.WaitFor"
                       for item in real["unsupported"])


def test_skill_presentation_barriers_and_emotion_are_ignored():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.WaitAbilityStartTimeStamp",
        "WaitTime": {"IsDynamic": False, "FixedValue": {"Value": 0.6}},
    }, {"$type": "RPG.GameCore.WaitSkillPerformAbilityFinish"}, {
        "$type": "RPG.GameCore.EnableEmotion", "Enable": True,
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"] and not out["hooks"]

    for enemy_id in ("5014014", "8012040", "4034020"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] in {
            "RPG.GameCore.WaitAbilityStartTimeStamp",
            "RPG.GameCore.WaitSkillPerformAbilityFinish", "RPG.GameCore.EnableEmotion",
        } for item in real["unsupported"])


def test_target_sort_by_action_order_uses_eta_not_gauge_ratio():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    compiler = AbilityCompiler("fake", [], {"character_config": {}})
    ctx = _Context(mode="action", skill={"skill_id": "s1"})
    spec = compiler._target_spec({
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam.RemoveServant"},
            {"$type": "RPG.GameCore.TargetSortByActionOrder"},
            {"$type": "RPG.GameCore.TargetTake", "Count": {
                "IsDynamic": False, "FixedValue": {"Value": 4}}},
        ],
    }, ctx, "P")
    assert not ctx.unsupported
    eng = engine_vs_dummy(allies=[make_actor("hero", spd=100), make_actor("ally", spd=200)],
                          enemies=[make_dummy("source")])
    eng.scheduler._remaining[eng.scheduler.handle_of("hero")] = 5000
    eng.scheduler._remaining[eng.scheduler.handle_of("ally")] = 7500
    selected = eng._hooks._hook_target_states(spec, eng.state.actors["source"], {})
    assert [state.actor.actor_id for state in selected] == ["ally", "hero"]

    real = _real_compiler("8034010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.TargetSortByActionOrder"
                   for item in real["unsupported"])


def test_set_target_team_location_moves_formation_order():
    expected = {"KeepOnFirst": "first", "KeepOnLast": "last",
                "BeforeCaster": "before_owner", "AfterCaster": "after"}
    for location, position in expected.items():
        out = _task_skill({
            "$type": "RPG.GameCore.SetTargetTeamLocation",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "Location": location,
            "CustomCaster": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        })
        assert out["ok"] and not out["unsupported"]
        effect = out["hooks"][0]["effects"][0]
        assert effect["position"] == position

    from tests._builders import engine_vs_dummy, make_dummy
    eng = engine_vs_dummy(enemies=[make_dummy("other"), make_dummy("source"), make_dummy("third")])
    eng.state.actors["third"].actor.summoner_id = "other"
    effect["reference"] = {"pool": "enemies", "where": "$it.actor_id == 'other'"}
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert list(eng.state.actors) == ["hero", "other", "source", "third"]

    row = _task_skill({
        "$type": "RPG.GameCore.SetTargetTeamLocation",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Row": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert row["ok"] and not row["unsupported"]
    row_effect = row["hooks"][0]["effects"][0]
    assert row_effect["dynamic_key"] == "_FormationRow" and row_effect["amount"] == 1
    eng._hooks._run_hook_effect(eng.state.actors["source"], row_effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["_FormationRow"] == 1
    for enemy_id in ("4023010", "4035010"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.SetTargetTeamLocation"
                       for item in real["unsupported"])


def test_switch_battle_area_is_scene_presentation():
    out = _task_skill({
        "$type": "RPG.GameCore.SwitchBattleArea",
        "UnifiedId": {"IsDynamic": False, "FixedValue": {"Value": 2043102}},
        "WaitFinish": True,
    })
    assert out["ok"] and not out["unsupported"] and not out["hooks"]
    for enemy_id in ("4015010", "4035010", "8015030"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.SwitchBattleArea"
                       for item in real["unsupported"])


def test_switch_case_without_break_compiles_each_predicate():
    skills, sources = _predicate_skill({})
    rows = []
    for value in (1, 2):
        rows.append({
            "Predicate": {"$type": "RPG.GameCore.ByCompareDynamicValue",
                          "DynamicKey": {"Value": "Flag"}, "CompareType": "Equal",
                          "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": value}}},
            "SuccessTaskList": [{"$type": "RPG.GameCore.DefineDynamicValue",
                                 "DynamicKey": {"Value": f"Case{value}"},
                                 "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
        })
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SwitchCase", "WithBreak": False,
        "TaskList": rows, "DefaultTask": [{"$type": "RPG.GameCore.DebugLog"}],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert sum(len(hook["effects"]) for hook in out["hooks"]) == 2

    sources["abilities"]["A"]["OnStart"][0]["WithBreak"] = True
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    for enemy_id in ("3025010", "5013030"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.SwitchCase"
                       for item in real["unsupported"])


def test_loop_target_list_absorbs_go_next_marker():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.LoopTargetList", "TaskList": [
            {"$type": "RPG.GameCore.GoNextTargetInList"},
            {"$type": "RPG.GameCore.DefineDynamicValue", "DynamicKey": {"Value": "Visited"},
             "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}}},
        ],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert len(out["hooks"][0]["effects"]) == 1
    real = _real_compiler("1013010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.GoNextTargetInList"
                   for item in real["unsupported"])


def test_insert_battle_perform_is_story_presentation():
    out = _task_skill({
        "$type": "RPG.GameCore.InsertBattlePerform",
        "BattlePerformPath": "Story/BattlePerformance/20332052/BattlePerform2033205204.json",
    })
    assert out["ok"] and not out["unsupported"] and not out["hooks"]
    real = _real_compiler("3025013").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.InsertBattlePerform"
                   for item in real["unsupported"])


def test_entity_action_state_predicate_uses_action_disabled():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsEntityActionState",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "not action_disabled($self.actor_id)" in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1"}
    assert eng._hooks._hook_amount(condition, source, payload) == 1
    eng._apply_modifier(source, Modifier(
        modifier_id="idle", name="Idle", modifier_type="debuff", prevent_action=True))
    assert eng._hooks._hook_amount(condition, source, payload) == 0
    real = _real_compiler("8034010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ByIsEntityActionState"
                   for item in real["unsupported"])


def test_special_action_state_reads_modifier_behavior_flag():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Flag": "SpecialActionState",
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1"}
    assert eng._hooks._hook_amount(condition, source, payload) == 0
    eng._apply_modifier(source, Modifier(
        modifier_id="special", name="Special", modifier_type="buff",
        behavior_flags=["SpecialActionState"]))
    assert eng._hooks._hook_amount(condition, source, payload) == 1
    real = _real_compiler("8034010").compile_enemy()
    assert not any("SpecialActionState" in item["reason"] for item in real["unsupported"])


def test_set_action_delay_legacy_value_uses_normalized_ratio():
    from tests._builders import engine_vs_dummy, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.SetActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "set_action_delay", "target": "self", "amount": 25}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert eng.scheduler._remaining[eng.scheduler.handle_of("source")] == 2500
    real = _real_compiler("4035011").compile_enemy()
    assert not any("裸 Value" in item["reason"] for item in real["unsupported"])


def test_dynamic_write_to_unique_name_uses_actor_runtime():
    skills, sources = _predicate_skill({})
    fetch = {"$type": "RPG.GameCore.TargetFetchUniqueNameEntity", "UniqueName": "BossUnique"}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetTargetUniqueName",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "UniqueName": {"RawString": "BossUnique"},
    }, {
        "$type": "RPG.GameCore.SetDynamicValue", "TargetType": fetch,
        "DynamicKey": {"Value": "Flag"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][-1]["target"] == {"pool": "unique:BossUnique"}

    sources["abilities"]["A"]["OnStart"].pop(0)
    without_registration = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert without_registration["ok"]

    sources["abilities"]["A"]["OnStart"][0]["TargetType"] = {
        "$type": "RPG.GameCore.TargetAlias", "Alias": "UnknownBare"}
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]

    real = _real_compiler("8034010").compile_enemy()
    path = ("Skill01:Monster_W3_Aventurine_00_Skill01_Phase01/OnStart/0:"
            "Monster_W3_Aventurine_00_Skill01_Phase02/OnStart/11/TaskList/1/"
            "_CallbackList/0/OnDestroy/1/SuccessTaskList/0")
    assert not any(item["path"] == path for item in real["unsupported"])


def test_dynamic_values_support_allied_targets_and_persist():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.SetDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        "DynamicKey": {"Value": "SharedFlag"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 2.5}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    eng = engine_vs_dummy(allies=[make_actor("hero"), make_actor("ally")],
                          enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    for actor_id in ("hero", "ally"):
        assert eng._enemy_policy_state[actor_id]["dynamic_values"]["SharedFlag"] == 2.5
        assert eng._hooks._hook_amount(
            f"dynamic_of('{actor_id}', 'SharedFlag')", eng.state.actors["source"], {}) == 2.5


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_obfuscated_property_value_normalizes_to_standard_reader():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _real_compiler("3024030").compile_enemy()
    assert not any(issue["node_type"] == "BIEFKHPDHPI" for issue in out["unsupported"])
    effects = {}

    def walk(value):
        if isinstance(value, dict):
            if value.get("effect_type") == "set_dynamic_value" \
                    and value.get("dynamic_key") in {"MDF_MaxHP_DownScale", "MDF_CurrentHP_DownScale"}:
                effects.setdefault(value["dynamic_key"], value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(out)
    assert effects["MDF_MaxHP_DownScale"]["amount"] == "max_hp_of($self.actor_id)"
    assert effects["MDF_CurrentHP_DownScale"]["amount"] == "hp_of($self.actor_id)"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    for effect in effects.values():
        eng._hooks._run_hook_effect(source, effect, {})
    values = eng._enemy_policy_state["source"]["dynamic_values"]
    assert values["MDF_MaxHP_DownScale"] == pytest.approx(
        eng.pipeline.effective_stats(source)["hp"])
    assert values["MDF_CurrentHP_DownScale"] == pytest.approx(source.current_hp)


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_obfuscated_control_skill_mapping_is_ui_only():
    out = _real_compiler("5014030").compile_enemy()
    assert not any(issue["node_type"] == "DGAOCHGKJKJ" for issue in out["unsupported"])


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_abort_modifier_phase_perform_is_presentation_only():
    out = _real_compiler("1012040").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.AbortModifierPhasePerform"
                   for issue in out["unsupported"])


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_obfuscated_textmap_prompt_is_presentation_only():
    out = _real_compiler("1003014").compile_enemy()
    assert not any(issue["node_type"] == "BENHFIGIMGL" for issue in out["unsupported"])


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
@pytest.mark.parametrize(("enemy_id", "node_type"), [
    ("4015011", "RPG.GameCore.MuteEntitySound"),
    ("4035010", "RPG.GameCore.SetLayerWeight"),
])
def test_audio_and_animation_layer_nodes_are_presentation_only(enemy_id, node_type):
    out = _real_compiler(enemy_id).compile_enemy()
    assert not any(issue["node_type"] == node_type for issue in out["unsupported"])


def test_reset_action_delay_with_skip_turn_uses_end_current_turn():
    out = _task_skill({
        "$type": "RPG.GameCore.ResetActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "SkipTargetTurn": True,
    })
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "end_current_turn", "target": "self"}]

    rejected = _task_skill({
        "$type": "RPG.GameCore.ResetActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    })
    assert not rejected["ok"]


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_battle_event_qte_ui_does_not_duplicate_real_event():
    out = _real_compiler("4015021").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.CreateBattleEventQTEUI"
                   for issue in out["unsupported"])

    def effects(value):
        if isinstance(value, dict):
            if value.get("effect_type") == "create_battle_event":
                yield value
            for child in value.values():
                yield from effects(child)
        elif isinstance(value, list):
            for child in value:
                yield from effects(child)

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.CreateBattleEvent",
        "EventID": {"IsDynamic": False, "FixedValue": {"Value": 60027}},
    }, {
        "$type": "RPG.GameCore.CreateBattleEventQTEUI",
        "EventID": {"IsDynamic": False, "FixedValue": {"Value": 60027}},
    }]
    synthetic = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    created = list(effects(synthetic))
    assert len(created) == 1 and created[0]["event_id"] == 60027


def test_character_leave_stage_vanish_uses_leave_battle():
    out = _task_skill({
        "$type": "RPG.GameCore.CharacterLeaveStage",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "AliveOnly": False,
        "ReasonKey": "Vanish",
    })
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "leave_battle", "target": "self", "reason": "vanish"}]

    rejected = _task_skill({
        "$type": "RPG.GameCore.CharacterLeaveStage",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "AliveOnly": True,
        "ReasonKey": "Vanish",
    })
    assert not rejected["ok"]


def test_negative_hp_property_reads_negative_hp_magnitude():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy
    compiler = AbilityCompiler("fake", [], {"character_config": {}})
    ctx = _Context(mode="event", skill={"skill_id": "s1"}, event="on_hp_decrease")
    compiler._compile_property_value({
        "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "NegativeHP",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "Value": "NegativeHP",
    }, ctx, "P", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    assert effect["amount"] == "max(0, -hp_of($self.actor_id))"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    source.current_hp = -125
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["NegativeHP"] == 125
    source.current_hp = 50
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["NegativeHP"] == 0
    real = _real_compiler("4033011").compile_enemy()
    assert not any("NegativeHP" in item["reason"] for item in real["unsupported"])


def test_special_sp_flows_from_config_to_runtime_and_predicates():
    from hsr_nous.pipeline.enemies.loader import calc_enemy_stats
    from tests._builders import engine_vs_dummy, make_dummy
    stats = calc_enemy_stats("8034010", 80)
    assert stats["max_special_sp"] == stats["initial_special_sp"] == 0

    dummy = make_dummy("source")
    dummy.stats.max_special_sp = 5
    dummy.initial_special_sp = 2
    eng = engine_vs_dummy(enemies=[dummy])
    source = eng.state.actors["source"]
    assert source.special_sp == 2 and source.snapshot()["special_sp"] == 2

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareAbilityProperty", "Property": "MaxSpecialSP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "CompareType": "Greater",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "max_special_sp_of($self.actor_id) > 0" in condition
    assert eng._hooks._hook_amount(condition, source, {"actor": "source", "action_id": "s1"}) == 1

    real = _real_compiler("8034010").compile_enemy()
    assert not any("MaxSpecialSP" in item["reason"] for item in real["unsupported"])


def test_modify_special_sp_refills_from_each_target_state():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.ModifySpecialSP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "FixedAddValue": _dynamic("AQABAQMR", hashes=[
            dynamic_value_hash("MaxSpecialSP"), dynamic_value_hash("CurrentSpecialSP")]),
        "IgnoreBlock": True,
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "modify_special_sp"
    assert "max_special_sp_of($target)" in effect["amount"]
    assert "special_sp_of($target)" in effect["amount"]
    hero = make_actor("hero")
    hero.stats.max_special_sp = 5
    hero.initial_special_sp = 2
    eng = engine_vs_dummy(allies=[hero], enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {"target": "hero"})
    assert eng.state.actors["hero"].special_sp == 5

    real = _real_compiler("8034010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ModifySpecialSP"
                   for item in real["unsupported"])


def test_modify_sp_ignore_block_uses_existing_energy_channels():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    for field, value in (("FixedAddValue", 2), ("SetValue", 7)):
        out = _task_skill({
            "$type": "RPG.GameCore.ModifySPNew",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            field: {"IsDynamic": False, "FixedValue": {"Value": value}},
            "IgnoreBlock": True,
        })
        assert out["ok"] and not out["unsupported"]
        effect = out["hooks"][0]["effects"][0]
        eng = engine_vs_dummy(enemies=[make_dummy("source")])
        source = eng.state.actors["source"]
        source.actor.stats.max_energy = 20
        eng._hooks._run_hook_effect(source, effect, {})
        assert source.current_energy == (2 if field == "FixedAddValue" else 7)

    real = _real_compiler("4044010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ModifySPNew"
                   and "IgnoreBlock" in item["reason"] for item in real["unsupported"])


def test_team_formation_row_predicate_uses_single_row_zero():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareTeamFormationRowIndex",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "CompareType": "Equal", "Inverse": True,
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "not" in condition and "_FormationRow" in condition
    from tests._builders import engine_vs_dummy, make_dummy
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    assert eng._hooks._hook_amount(condition, eng.state.actors["source"],
                                   {"actor": "source", "action_id": "s1"}) == 1
    for enemy_id in ("4012052", "4022011"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.ByCompareTeamFormationRowIndex"
                       for item in real["unsupported"])


def test_servant_attack_type_reads_event_source_identity():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy
    compiler = AbilityCompiler("fake", [], {"character_config": {}})
    ctx = _Context(mode="event", skill={"skill_id": "s1"}, event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByAttackType", "AttackTypes": ["Servant"],
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    }, ctx, "P")
    assert expression and not ctx.unsupported
    minion = make_dummy("minion")
    minion.summoner_id = "owner"
    eng = engine_vs_dummy(enemies=[make_dummy("source"), minion])
    assert eng._hooks._hook_amount(expression, eng.state.actors["source"], {"source": "minion"}) == 1
    assert eng._hooks._hook_amount(expression, eng.state.actors["source"], {"source": "source"}) == 0
    real = _real_compiler("3002020").compile_enemy()
    assert not any("Servant" in item["reason"] for item in real["unsupported"])


def test_on_kill_param_entity2_is_living_killer():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy
    compiler = AbilityCompiler("fake", [], {"character_config": {}})
    ctx = _Context(mode="event", skill={"skill_id": "s1"}, event="on_kill")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByAnd", "PredicateList": [{
            "$type": "RPG.GameCore.ByIsTargetValid",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity2"},
        }, {
            "$type": "RPG.GameCore.ByTargetTeam", "Team": "TeamDark", "Inverse": True,
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity2"},
        }],
    }, ctx, "P")
    assert expression and expression.count("$event.source") >= 2 and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(expression, source, {"source": "hero", "target": "source"}) == 1
    eng.state.actors["hero"].alive = False
    assert eng._hooks._hook_amount(expression, source, {"source": "hero", "target": "source"}) == 0
    real = _real_compiler("4023011").compile_enemy()
    assert not any("ParamEntity2" in item["reason"] for item in real["unsupported"])


def test_behavior_flags_default_to_or_and_support_frozen_effect():
    from hsr_nous.adapters.enemy_ability import _Context
    compiler = AbilityCompiler("fake", [], {"character_config": {}})
    predicate = {"$type": "RPG.GameCore.ByContainBehaviorFlag",
                 "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                 "Flags": ["STAT_CTRL_Frozen", "STAT_CTRL_Frozen_Effect"], "Inverse": True}
    ctx = _Context(mode="action", skill={"skill_id": "s1"})
    expression = compiler._predicate_expr(predicate, ctx, "P")
    assert expression and " or " in expression and "Frozen_Effect" in expression
    predicate["ContainType"] = "And"
    joined = compiler._predicate_expr(predicate, ctx, "P")
    assert joined and " and " in joined
    real = _real_compiler("5023020").compile_enemy()
    assert not any("多旗标" in item["reason"] or "Frozen_Effect" in item["reason"]
                   for item in real["unsupported"])


def test_summon_keep_first_last_aliases():
    for location, position in (("KeepOnFirst", "first"), ("KeepOnLast", "last")):
        out = _task_skill({
            "$type": "RPG.GameCore.SummonMonster",
            "SummonMonsterDataList": [{"MonsterID": 2022072, "LocationType": location}],
        })
        assert out["ok"] and not out["unsupported"]
        effect = out["hooks"][0]["effects"][0]
        assert effect["position"] == position
    for enemy_id in ("4035010", "4035011"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("LocationType=KeepOn" in item["reason"]
                       for item in real["unsupported"])


def test_stance_break_resistance_negates_toughness_taken():
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Resistance"},
    }]
    sources["modifiers"]["Resistance"] = {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty", "Property": "StanceBreakResistance",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }]}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["stat_effects"]["toughness_taken"] == -1
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng.pipeline.toughness_damage_amount(None, 30, target=source) == 0
    real = _real_compiler("1013012").compile_enemy()
    assert not any("StanceBreakResistance" in item["reason"] for item in real["unsupported"])


def test_monster_hp_total_seg_is_display_configuration():
    out = _task_skill({
        "$type": "RPG.GameCore.SetMonsterHPTotalSeg",
        "TotalSeg": {"IsDynamic": False, "FixedValue": {"Value": 3}},
    })
    assert out["ok"] and not out["unsupported"] and not out["hooks"]
    real = _real_compiler("3012030").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.SetMonsterHPTotalSeg"
                   for item in real["unsupported"])


def test_dynamic_loop_executes_nested_dynamic_writes():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValueByAddValue", "Key": {"Value": "Total"},
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "AddValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "loop_effects"
    BuildCompiler()._validate_effects([effect], "模板 X")
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 3, "Total": 0}}
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Total"] == 3
    eng._enemy_policy_state["source"]["dynamic_values"]["LoopCount"] = -1
    with pytest.raises(ValueError, match="非负"):
        eng._hooks._run_hook_effect(source, effect, {})

    looped_modifier = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Mark"},
        }],
    }, modifiers={"Mark": {"BehaviorFlagList": ["Mark"]}})
    assert looped_modifier["ok"] and not looped_modifier["unsupported"]
    looped_effect = looped_modifier["hooks"][0]["effects"][0]
    assert looped_effect["effects"][0]["effect_type"] == "apply_modifier"
    applied = []
    eng.bus.subscribe("after_apply_modifier", lambda _t, payload, _c: applied.append(payload))
    eng._enemy_policy_state["source"]["dynamic_values"]["LoopCount"] = 3
    eng._hooks._run_hook_effect(source, looped_effect, {})
    assert len(applied) == 3 and "Mark" in source.modifiers

    retargeted = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.Retarget",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
            "TaskList": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "Mark"},
            }],
        }],
    }, modifiers={"Mark": {"BehaviorFlagList": ["Mark"]}})
    assert retargeted["ok"] and not retargeted["unsupported"]
    eng._enemy_policy_state["source"]["dynamic_values"]["LoopCount"] = 2
    eng._hooks._run_hook_effect(source, retargeted["hooks"][0]["effects"][0], {})
    assert len(applied) == 5
    assert all(payload["target"] == "hero" for payload in applied[3:])
    real = _real_compiler("3002050").compile_enemy()
    assert not any("循环次数" in item["reason"] for item in real["unsupported"])


def test_dynamic_loop_executes_direct_damage_each_iteration():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.DamageByAttackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            "AttackProperty": {
                "DamageType": {"DamageType": "Physical"},
                "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.01}},
                "StanceValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
            },
        }],
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "loop_effects"
    assert [nested["effect_type"] for nested in effect["effects"]] == ["deal_damage"]
    BuildCompiler()._validate_effects([effect], "模板 X")

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 3}}
    hits = []
    eng.bus.subscribe("after_being_hit", lambda _t, payload, _c: hits.append(payload))
    eng._hooks._run_hook_effect(source, effect, {})
    assert len(hits) == 3

    real = _real_compiler("4034010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.LoopExecuteTaskList"
                   and "动态次数循环仅支持" in item["reason"]
                   for item in real["unsupported"])


def test_dynamic_loop_preserves_mixed_damage_write_order():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    increment = {
        "$type": "RPG.GameCore.SetDynamicValueByAddValue", "Key": {"Value": "Total"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "AddValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }
    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [increment, {
            "$type": "RPG.GameCore.DamageByAttackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            "AttackProperty": {
                "DamageType": {"DamageType": "Physical"},
                "DamagePercentage": _dynamic("AQAR", hashes=[dynamic_value_hash("Total")]),
                "StanceValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
            },
        }, increment],
    })
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert [nested["effect_type"] for nested in effect["effects"]] == [
        "set_dynamic_value", "deal_damage", "set_dynamic_value"]

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=10)])
    source = eng.state.actors["source"]
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 2, "Total": 0}}
    hits = []
    eng.bus.subscribe("after_being_hit", lambda _t, payload, _c: hits.append(payload))
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Total"] == 4
    assert len(hits) == 2 and hits[0]["amount"] < hits[1]["amount"]

    real = _real_compiler("3003020").compile_enemy()
    assert not any(item["owner"] == "Skill01"
                   and item["node_type"] == "RPG.GameCore.LoopExecuteTaskList"
                   for item in real["unsupported"])


def test_dynamic_loop_retargets_unmarked_target_each_iteration():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.Retarget",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
            "Predicate": {
                "$type": "RPG.GameCore.ByIsContainModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "Mark"}, "Inverse": True,
            },
            "MaxNumber": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            "TaskList": [{
                "$type": "RPG.GameCore.DamageByAttackProperty",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "AttackProperty": {
                    "DamageType": {"DamageType": "Imaginary"},
                    "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.01}},
                    "StanceValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
                },
            }, {
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "Mark"},
            }],
        }],
    }, modifiers={"Mark": {"BehaviorFlagList": ["Mark"]}})
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 2}}
    hit_targets = []
    eng.bus.subscribe("after_being_hit",
                      lambda _t, payload, _c: hit_targets.append(payload["target"]))
    eng._hooks._run_hook_effect(source, effect, {})
    assert len(hit_targets) == 2 and len(set(hit_targets)) == 2

    real = _real_compiler("3025010").compile_enemy()
    assert not any(item["owner"] == "Skill02"
                   and item["node_type"] == "RPG.GameCore.LoopExecuteTaskList"
                   for item in real["unsupported"])


def test_dynamic_loop_remove_modifier_uses_normal_removal_chain():
    from hsr_nous.sim.state import Modifier
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.RemoveModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Mark"},
        }],
    }, modifiers={"Mark": {"BehaviorFlagList": ["Mark"]}})
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effects"][0]["effect_type"] == "remove_modifier"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    source.modifiers["Mark"] = Modifier(
        modifier_id="Mark", name="Mark", modifier_type="debuff")
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 2}}
    removed = []
    eng.bus.subscribe("after_remove_modifier", lambda _t, payload, _c: removed.append(payload))
    eng._hooks._run_hook_effect(source, effect, {})
    assert "Mark" not in source.modifiers and len(removed) == 1

    real = _real_compiler("1023011").compile_enemy()
    assert not any(item["owner"] == "Skill08"
                   and item["node_type"] == "RPG.GameCore.LoopExecuteTaskList"
                   for item in real["unsupported"])


def test_dynamic_loop_preserves_modifier_lifecycle_hooks():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Pool"},
        }],
    }]
    sources["modifiers"] = {"Pool": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "Property": "RallyHP",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    loop = next(effect for hook in out["hooks"] for effect in hook["effects"]
                if effect["effect_type"] == "loop_effects")
    stack_hooks = [hook for hook in out["hooks"]
                   if hook["event"] == "after_apply_modifier" and "Pool" in hook["condition"]]
    assert len(stack_hooks) == 1

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hook = stack_hooks[0]
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event=hook["event"],
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=tuple(hook["effects"]))]
    eng._hooks._subscribe_compiled_hooks()
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 2}}
    eng._hooks._run_hook_effect(source, loop, {})
    assert source.resources["rally_hp"] == 2

    real = _real_compiler("1004010").compile_enemy()
    assert any(hook["event"] == "after_apply_modifier"
               and "IceValueShow" in hook["condition"] for hook in real["hooks"])


def test_dynamic_loop_expands_local_template_without_dropping_side_channels():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    loop = {
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{"$type": "RPG.GameCore.IncludeTaskListTemplate", "Name": "Hit"}],
    }
    sources["abilities"]["A"]["OnStart"] = [loop]
    sources["abilities"]["A"]["TaskListTemplate"] = [{
        "Name": "Hit",
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValueByAddValue", "Key": {"Value": "Total"},
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "AddValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }, {
            "$type": "RPG.GameCore.DamageByAttackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            "AttackProperty": {
                "DamageType": {"DamageType": "Physical"},
                "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.01}},
                "StanceValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
            },
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert [nested["effect_type"] for nested in effect["effects"]] == [
        "set_dynamic_value", "deal_damage"]

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 2, "Total": 0}}
    hits = []
    eng.bus.subscribe("after_being_hit", lambda _t, payload, _c: hits.append(payload))
    eng._hooks._run_hook_effect(source, effect, {})
    assert len(hits) == 2
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Total"] == 2

    sources["abilities"]["A"]["TaskListTemplate"][0]["TaskList"] = [{
        "$type": "RPG.GameCore.SummonMonster",
        "SummonMonsterDataList": [{
            "MonsterID": {"IsDynamic": False, "FixedValue": {"Value": 1001}},
        }],
    }]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("动态次数循环含未收编机制任务" in issue["reason"]
               for issue in rejected["unsupported"])

    for enemy_id in ("4023020", "4023021"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.LoopExecuteTaskList"
                       for item in real["unsupported"])


def test_dynamic_loop_lose_hp_then_force_kill_reads_current_hp_each_iteration():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "CurrentHP",
            "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "Value": "CurrentHP",
        }, {
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareDynamicValue", "DynamicKey": {"Value": "CurrentHP"},
                "CompareType": "LessEqual",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 500}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.ForceKill",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            }],
            "FailedTaskList": [{
                "$type": "RPG.GameCore.LoseHPByRatio",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
                "RatioType": "MaxHP",
                "Ratio": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
            }],
        }],
    })
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    loop = next(effect for hook in out["hooks"] for effect in hook["effects"]
                if effect["effect_type"] == "loop_effects")
    eng = engine_vs_dummy(enemies=[make_dummy("source", hp=1000)])
    source = eng.state.actors["source"]
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 3}}
    eng._hooks._run_hook_effect(source, loop, {})
    assert not source.alive
    assert source.current_hp == 0

    real = _real_compiler("2024020").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.LoopExecuteTaskList"
                   for item in real["unsupported"])


def test_dynamic_loop_switch_case_selects_branch_each_iteration():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    def increment(value):
        return {
            "$type": "RPG.GameCore.SetDynamicValueByAddValue", "Key": {"Value": "Total"},
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "AddValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
        }

    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Mode"},
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 2}},
        }, {
            "$type": "RPG.GameCore.SwitchCaseByDynamicValue",
            "Switch": _dynamic("AQAR", hashes=[dynamic_value_hash("Mode")]),
            "CaseTaskList": [
                {"Case": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                 "TaskList": [increment(1)]},
                {"Case": {"IsDynamic": False, "FixedValue": {"Value": 2}},
                 "TaskList": [increment(10)]},
            ],
        }],
    })
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    loop = next(effect for hook in out["hooks"] for effect in hook["effects"]
                if effect["effect_type"] == "loop_effects")
    assert len(loop["effects"]) == 3
    assert all("Mode" in effect.get("condition", "") for effect in loop["effects"][1:])

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 2, "Mode": 2, "Total": 0}}
    eng._hooks._run_hook_effect(source, loop, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Total"] == 20

    real = _real_compiler("4053020").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.LoopExecuteTaskList"
                   for item in real["unsupported"])


def test_dynamic_loop_binds_random_independently_per_iteration():
    from hsr_nous.sim.frame import ExecutionFrame
    from hsr_nous.sim.pipeline import MODE_ROLL
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByRandomChance",
                "Chance": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Outcome"},
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
            "FailedTaskList": [{
                "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Outcome"},
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "Value": {"IsDynamic": False, "FixedValue": {"Value": 0}},
            }],
        }],
    })
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    loop = next(effect for hook in out["hooks"] for effect in hook["effects"]
                if effect["effect_type"] == "loop_effects")

    class SequenceRng:
        def __init__(self):
            self.values = iter([0.2, 0.8])
            self.calls = 0

        def random(self):
            self.calls += 1
            return next(self.values)

    eng = engine_vs_dummy(enemies=[make_dummy("source")], mode=MODE_ROLL)
    source = eng.state.actors["source"]
    rng = SequenceRng()
    eng.pipeline.rng = rng
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 2}}
    frame = ExecutionFrame("test", "source")
    eng._frame_stack.append(frame)
    eng._hooks._run_hook_effect(source, loop, {})
    eng._frame_stack.pop()
    eng._commit_frame(frame)
    assert rng.calls == 2
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Outcome"] == 0
    assert [value for value in frame.rolls.values()] == [0.2, 0.8]
    assert all("@loop:" in key for key in frame.rolls)

    real = _real_compiler("3013010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.LoopExecuteTaskList"
                   for item in real["unsupported"])


def test_dynamic_loop_add_to_formation_without_summon_spec_is_noop():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.AddEntityToTeamFormation",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        }],
    })
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    loop = next(effect for hook in out["hooks"] for effect in hook["effects"]
                if effect["effect_type"] == "loop_effects")
    assert loop["effects"] == []
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._enemy_policy_state["source"] = {"dynamic_values": {"LoopCount": 2}}
    before = source.current_hp
    eng._hooks._run_hook_effect(source, loop, {})
    assert source.current_hp == before

    real = _real_compiler("2024021").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.LoopExecuteTaskList"
                   for item in real["unsupported"])


def test_dynamic_loop_preserves_predicate_conditions():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")]),
        "TaskList": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {"$type": "RPG.GameCore.ByCompareDynamicValue",
                          "DynamicKey": {"Value": "Enabled"}, "CompareType": "Equal",
                          "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}}},
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.SetDynamicValueByAddValue", "Key": {"Value": "Total"},
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "AddValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
        }],
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    nested = effect["effects"][0]
    assert "Enabled" in nested["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    values = eng._enemy_policy_state.setdefault("source", {"dynamic_values": {}})["dynamic_values"]
    values.update({"LoopCount": 2, "Total": 0, "Enabled": 1})
    eng._hooks._run_hook_effect(source, effect, {})
    assert values["Total"] == 2
    values.update({"Total": 0, "Enabled": 0})
    eng._hooks._run_hook_effect(source, effect, {})
    assert values["Total"] == 0


def test_turn_owner_has_action_in_turn_uses_frame_and_phase():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.frame import ExecutionFrame
    from tests._builders import engine_vs_dummy, make_dummy
    compiler = AbilityCompiler("fake", [], {"character_config": {}})
    ctx = _Context(mode="event", skill={"skill_id": "s1"}, event="on_turn_end")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByTurnOwnerHasActionInTurn",
    }, ctx, "P")
    assert expression == "turn_owner_has_action_in_turn()" and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._current_turn_actor_id = "hero"
    assert eng._hooks._hook_amount(expression, source, {}) == 0
    eng._frame_stack.append(ExecutionFrame("a", "hero"))
    assert eng._hooks._hook_amount(expression, source, {}) == 1
    eng._frame_stack.pop()
    eng._turn_owner_action_phase_end = True
    assert eng._hooks._hook_amount(expression, source, {}) == 1
    real = _real_compiler("4035010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ByTurnOwnerHasActionInTurn"
                   for item in real["unsupported"])


def test_delay_cumulate_eliminates_only_unreferenced_write():
    skills, sources = _predicate_skill({})
    node = {"$type": "RPG.GameCore.SetDynamicValueByDelayCumulate", "DynamicKey": "UnusedDelay"}
    sources["abilities"]["A"]["OnStart"] = [node]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"] and not out["hooks"]

    sources["abilities"]["A"]["OnStart"].append({
        "$type": "RPG.GameCore.PredicateTaskList",
        "Predicate": {"$type": "RPG.GameCore.ByCompareDynamicValue",
                      "DynamicKey": {"Value": "UnusedDelay"}, "CompareType": "Equal",
                      "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}}},
    })
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    real = _real_compiler("4044010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.SetDynamicValueByDelayCumulate"
                   for item in real["unsupported"])


def test_part_entity_character_count_uses_configured_monster_id():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy
    enemy_id = "8015012"
    skills = get_enemy_skills(enemy_id)
    compiler = AbilityCompiler(enemy_id, skills, get_enemy_ability_sources(enemy_id))
    ctx = _Context(mode="event", skill=skills[0], event="on_turn_end")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareCharacterNumber",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "PartEntity1"},
        "CompareType": "Equal", "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }, ctx, "P")
    assert "8012146" in expression and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    assert eng._hooks._hook_amount(expression, eng.state.actors["source"], {})
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("8012146")])
    assert not eng._hooks._hook_amount(expression, eng.state.actors["source"], {})


def test_set_dynamic_value_defaults_to_caster():
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.SetDynamicValue", "ContextScope": "TargetEntity",
            "DynamicKey": {"Value": "BattleEventFlag"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "BattleEventFlag", "amount": 1,
    }]


def test_modifier_lifetime_uses_explicit_modifier_name():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareModifierValue",
        "ModifierName": "MMonster_W2_Mecha03_00_Overdrive_On",
        "ValueType": "LifeTime", "CompareType": "Equal",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert ("modifier_duration($self.actor_id, 'MMonster_W2_Mecha03_00_Overdrive_On') == 1"
            in out["hooks"][0]["condition"])


def test_monster_phase_compare_accepts_dynamic_threshold():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterPhase",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "CompareType": "NotEqual",
        "CompareValue": _dynamic("AQAR", hashes=[dynamic_value_hash("MaxPhase")]),
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "dynamic_of($self, 'current_phase') != dynamic_of($self.actor_id, 'MaxPhase')" \
        in out["hooks"][0]["condition"]


def test_modifier_value_compare_accepts_dynamic_threshold():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareModifierValue",
        "ModifierName": "Mark", "ValueType": "Layer", "CompareType": "Equal",
        "CompareValue": _dynamic("AQAR", hashes=[123]),
    })
    sources["character_config"]["DynamicValues"] = {"Floats": {
        "123": {"ReadInfo": {"Type": "SkillParam", "TriggerKey": "Skill01", "Index": 0}},
    }}
    skills[0]["param_list"] = [3]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "stacks($self.actor_id, 'Mark') == 3" in out["hooks"][0]["condition"]


def test_retarget_without_max_number_takes_all_candidates():
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.Retarget",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            "TaskList": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "WMonster_TY_Elite01_00_Skill07_Mark"},
            }],
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["target"] == {"pool": "allies"}


@pytest.mark.parametrize("alias", [
    "TauntOrRandomEnemy", "TauntOrRandomEnemyWithoutServant",
    "TauntOrRandomEnemy.RemoveServant",
])
def test_taunt_or_random_enemy_uses_dedicated_target_mode(alias):
    skills, sources = _predicate_skill({})
    marker = {
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "ModifierName": {"Value": "WMonster_TY_Elite01_00_Skill07_Mark"},
    }
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "ByRandom": True,
        "MaxNumber": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        "TaskList": [marker],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    expected = {"pool": "enemy_targets", "take": 1, "mode": "taunt_or_random"}
    if alias != "TauntOrRandomEnemy":
        expected["where"] = "not $it.summoner_id"
    assert out["hooks"][0]["effects"][0]["target"] == expected

    direct_marker = dict(marker)
    direct_marker["TargetType"] = {"$type": "RPG.GameCore.TargetAlias", "Alias": alias}
    sources["abilities"]["A"]["OnStart"] = [direct_marker]
    direct = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert direct["ok"] and not direct["unsupported"]
    assert direct["hooks"][0]["effects"][0]["target"] == expected


def test_set_dynamic_entity_param_separates_owner_and_selected_target():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicEntityParam",
        "DynamicKey": "ProjectileFirstTarget",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ParamTargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "TauntOrRandomEnemy"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "set_dynamic_target")
    assert effect == {
        "effect_type": "set_dynamic_target", "dynamic_key": "ProjectileFirstTarget",
        "owner": "self",
        "target": {"pool": "enemy_targets", "take": 1, "mode": "taunt_or_random"},
    }
    BuildCompiler()._validate_effects([effect], "动态目标绑定测试")

    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    ally = eng.state.actors["ally"]
    eng._apply_modifier(source, Modifier(
        modifier_id="TAUNT", name="嘲讽", modifier_type="debuff",
        source_id="ally", forced_taunt=True, duration=2))
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_targets"]["ProjectileFirstTarget"] == "ally"
    assert "ProjectileFirstTarget" not in eng._enemy_policy_state.get(
        "ally", {}).get("dynamic_targets", {})


def test_target_concat_preserves_child_target_specs():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetConcat", "Targets": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        ]},
        "TaskList": [{
            "$type": "RPG.GameCore.ResetStance",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ConstantValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["target"] == {
        "concat": [{"pool": "enemies"}, {"pool": "self"}]}


def test_target_alias_concat_allows_missing_spaces():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.SetActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": "AllDarkTeam+AllLightTeam"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == {"concat": [{"pool": "enemies"}, {"pool": "allies"}]}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    picked = eng._hooks._hook_target_states(effect["target"], eng.state.actors["source"], {})
    assert {st.actor.actor_id for st in picked} == {"source", "hero"}
    real = _real_compiler("8015030").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.SetActionDelay"
                   for item in real["unsupported"])


def test_retarget_list_uses_same_target_algebra():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.RetargetList",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "MaxNumber": {"IsDynamic": False, "FixedValue": {"Value": 2}},
        "TaskList": [{
            "$type": "RPG.GameCore.ResetStance",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntityList"},
            "ConstantValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "reset_stance", "target": {"pool": "allies", "take": 2},
        "mode": "set", "amount": 0.5,
    }]


def test_remodifier_filters_existing_modifier_and_uses_failed_tasks():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Remodifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "ModifierName": "Mark",
        "MaxNumber": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        "TaskList": [{
            "$type": "RPG.GameCore.ResetStance",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ConstantValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        }],
        "FailedTaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Fallback"},
        }],
    }]
    sources["modifiers"] = {"Fallback": {"BehaviorFlagList": ["RemoveWhenCasterDead"]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[0]["target"] == {
        "pool": "allies", "where": "has_modifier($it, 'Mark')", "take": 1}
    assert effects[1]["condition"].startswith("count_selected")
    assert effects[1]["target"] == "self"


def test_remodifier_supports_self_limbo_and_event_caster_filter():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["modifiers"] = {"Mark": {}}
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_kill",
                   retarget={"pool": "allies", "where": "$it.actor_id == 'hero'"})
    compiler._compile_remodifier({
        "$type": "RPG.GameCore.Remodifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "IncludeLimbo": True,
        "CasterFilter": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "ModifierName": "Mark",
        "TaskList": [{
            "$type": "RPG.GameCore.RemoveModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "ParamModifier"},
        }],
    }, ctx, "P", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    assert effect["target"]["pool"] == "self"
    assert "target_in_selected" in effect["target"]["where"]
    assert "modifier_source" in effect["target"]["where"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    source.modifiers["Mark"] = Modifier(
        modifier_id="Mark", name="Mark", modifier_type="buff", source_id="hero")
    eng._hooks._run_hook_effect(source, effect, {"target": "hero"})
    assert "Mark" not in source.modifiers
    for enemy_id in ("4032020", "2034011"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] in {"RPG.GameCore.Remodifier", "RPG.GameCore.TargetAlias"}
                       for item in real["unsupported"])
    turn_ctx = _Context(mode="event", skill=skills[0], event="on_turn_start")
    assert compiler._hook_target("ParamEntity", turn_ctx) == "$event.actor"
    picked = eng._hooks._hook_target_states("$event.actor", source, {"actor": "hero"})
    assert [st.actor.actor_id for st in picked] == ["hero"]


def test_retarget_empty_candidates_run_failed_tasks_in_engine():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "Predicate": {
            "$type": "RPG.GameCore.ByIsContainModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "Mark"},
        },
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "Selected"},
        }],
        "FailedTaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Fallback"},
        }],
    }]
    sources["modifiers"] = {
        "Mark": {},
        "Selected": {"BehaviorFlagList": ["RemoveWhenCasterDead"]},
        "Fallback": {"BehaviorFlagList": ["RemoveWhenCasterDead"]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[0]["target"] == {
        "pool": "allies", "where": "has_modifier($it, 'Mark')"}
    assert effects[1]["target"] == "self"
    assert effects[1]["condition"] == (
        'count_selected("allies", "has_modifier($it, \'Mark\')") == 0')

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert "Fallback" in source.modifiers and "Selected" not in hero.modifiers

    source.modifiers.clear()
    hero.modifiers["Mark"] = Modifier(modifier_id="Mark", name="Mark", modifier_type="buff")
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert "Selected" in hero.modifiers and "Fallback" not in source.modifiers


@pytest.mark.parametrize("alias", ["AbilityTargetEntity", "AbilityTargetAdjoinEntity"])
def test_retarget_empty_fallback_supports_event_context(alias):
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "ByRandom": True,
        "FailedTaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Fallback"},
        }],
    }]
    sources["modifiers"] = {"Fallback": {"BehaviorFlagList": ["RemoveWhenCasterDead"]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["effects"][0]["condition"]
    assert condition.startswith("count_selected(") and "$event.target" in condition
    assert '"take"' not in condition and '"mode"' not in condition

    eng = engine_vs_dummy(enemies=[make_dummy("source")], allies=[make_actor("ally")])
    source = eng.state.actors["source"]
    for effect in out["hooks"][0]["effects"]:
        eng._hooks._run_hook_effect(source, effect, {"target": "hero"})
    assert "Fallback" not in source.modifiers
    for effect in out["hooks"][0]["effects"]:
        eng._hooks._run_hook_effect(source, effect, {})
    assert "Fallback" in source.modifiers


def test_retarget_empty_fallback_supports_concat():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetConcat", "Targets": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        ]},
        "ByRandom": True,
        "FailedTaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Fallback"},
        }],
    }]
    sources["modifiers"] = {"Fallback": {"BehaviorFlagList": ["RemoveWhenCasterDead"]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["effects"][0]["condition"]
    assert "concat" in condition and '"mode"' not in condition

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    for effect in out["hooks"][0]["effects"]:
        eng._hooks._run_hook_effect(source, effect, {"target": "hero"})
    assert "Fallback" not in source.modifiers
    for effect in out["hooks"][0]["effects"]:
        eng._hooks._run_hook_effect(source, effect, {})
    assert "Fallback" in source.modifiers


def test_target_sequence_concat_applies_outer_filter():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetConcat", "Targets": [
                {"$type": "RPG.GameCore.TargetAlias",
                 "Alias": "AllLightTeamWithAllLightTeamUnselectable"},
                {"$type": "RPG.GameCore.TargetAlias",
                 "Alias": "AllDarkTeamWithAllDarkTeamUnselectable"},
            ]},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByIsContainModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "Mark"},
            }},
        ]},
        "ModifierName": {"Value": "Mark"},
    }]
    sources["modifiers"] = {"Mark": {}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"]["where"] == "has_modifier($it, 'Mark')"

    eng = engine_vs_dummy(
        enemies=[make_dummy("source"), make_dummy("partner")], allies=[make_actor("ally")])
    source = eng.state.actors["source"]
    for actor_id in ("hero", "partner"):
        eng.state.actors[actor_id].modifiers["Mark"] = Modifier(
            modifier_id="Mark", name="Mark", modifier_type="debuff")
    eng._hooks._run_hook_effect(source, effect, {})
    assert "Mark" not in eng.state.actors["hero"].modifiers
    assert "Mark" not in eng.state.actors["partner"].modifiers
    assert "Mark" not in eng.state.actors["ally"].modifiers


def test_with_servant_appends_only_selected_targets_summons():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim.state import ActorState, Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    sources = get_enemy_ability_sources("4013016")
    compiler = AbilityCompiler("4013016", get_enemy_skills("4013016"), sources)
    ctx = __import__("hsr_nous.adapters.enemy_ability", fromlist=["_Context"])._Context(
        mode="event", skill={"skill_id": "s1"}, event="after_being_hit")
    spec = compiler._hook_target(
        "MMonster_W4_Claymore_01_LocalLegend_WhiteCurse_Target.WithServant", ctx)
    assert spec["include_summons"] is True

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    ally = make_actor("ally")
    eng.state.actors["ally"] = ActorState(actor=ally, current_hp=ally.stats.hp)
    hero.modifiers["MMonster_W4_Claymore_01_LocalLegend_WhiteCurse"] = Modifier(
        modifier_id="MMonster_W4_Claymore_01_LocalLegend_WhiteCurse",
        name="White Curse", modifier_type="debuff")
    for actor_id, summoner_id in (("hero_servant", "hero"), ("ally_servant", "ally")):
        actor = make_actor(actor_id)
        actor.actor_type = "summon"
        actor.summoner_id = summoner_id
        eng.state.actors[actor_id] = ActorState(actor=actor, current_hp=actor.stats.hp)
    picked = eng._hooks._hook_target_states(spec, source, {})
    assert {state.actor.actor_id for state in picked} == {"hero", "hero_servant"}


def test_teammate_minus_modifier_excludes_holder():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    spec = compiler._hook_target("AllTeammate - MMonster_W4_Manta_00_LocalLegend", None)
    assert spec == {
        "pool": "enemies", "where": "not has_modifier($it, 'MMonster_W4_Manta_00_LocalLegend')"}
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("partner")])
    source = eng.state.actors["source"]
    partner = eng.state.actors["partner"]
    partner.modifiers["MMonster_W4_Manta_00_LocalLegend"] = Modifier(
        modifier_id="MMonster_W4_Manta_00_LocalLegend", name="Manta", modifier_type="buff")
    assert eng._hooks._hook_target_states(spec, source, {}) == [source]


def test_part_entity_aliases_resolve_shared_body_config():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    expected = {
        "8015010": (8012140, 8013141, 8012142),
        "8015011": (8012143, 8013144, 8012145),
        "8015012": (8012146, 8013145, 8012147),
        "8013141": (8012140, 8013141, 8012142),
        "8013144": (8012143, 8013144, 8012145),
        "8013145": (8012146, 8013145, 8012147),
    }
    for enemy_id, monster_ids in expected.items():
        compiler = AbilityCompiler(enemy_id, get_enemy_skills(enemy_id),
                                   get_enemy_ability_sources(enemy_id))
        for index, monster_id in enumerate(monster_ids, start=1):
            spec = compiler._hook_target(f"PartEntity{index}", None)
            assert spec == {"pool": "enemies", "where": f"monster_id($it) == '{monster_id}'"}

    eng = engine_vs_dummy(enemies=[make_dummy("8012140__8015010_part1")])
    spec = {"pool": "enemies", "where": "monster_id($it) == '8012140'"}
    source = eng.state.actors["8012140__8015010_part1"]
    assert eng._hooks._hook_target_states(spec, source, {}) == [source]


def test_target_index_defaults_to_strict_and_selects_zero_based():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="action", skill=skills[0])
    raw = {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
        {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        {"$type": "RPG.GameCore.TargetSortByFormation"},
        {"$type": "RPG.GameCore.TargetIndex",
         "IndexValue": {"IsDynamic": False, "FixedValue": {"Value": 1}}},
    ]}
    spec = compiler._target_spec(raw, ctx, "target")
    assert spec["index"] == 1 and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")], allies=[make_actor("ally")])
    selected = eng._hooks._hook_target_states(spec, eng.state.actors["source"], {})
    assert [state.actor.actor_id for state in selected] == ["ally"]

    raw["Sequence"][-1]["IndexType"] = "First"
    assert compiler._target_spec(raw, ctx, "target") is None
    assert any("仅支持 IndexStrict" in issue["reason"] for issue in ctx.unsupported)


def test_target_sequence_caster_left_right_aliases():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="action", skill=skills[0])
    eng = engine_vs_dummy(enemies=[
        make_dummy("left"), make_dummy("source"), make_dummy("right")])
    source = eng.state.actors["source"]
    for alias, delta, expected in (("CasterLeftEntity", -1, "left"),
                                   ("CasterRightEntity", 1, "right")):
        spec = compiler._target_spec({
            "$type": "RPG.GameCore.TargetAlias", "Alias": alias}, ctx, "target")
        assert spec == {"pool": "enemies",
                        "where": f"position_delta($it, $self.actor_id) == {delta}"}
        selected = eng._hooks._hook_target_states(spec, source, {})
        assert [state.actor.actor_id for state in selected] == [expected]


def test_modifier_owner_skill_target_list_uses_any_target():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="before_action")
    character = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareCharacterID", "TargetCharacterID": {
            "IsDynamic": False, "FixedValue": {"Value": 1413}},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": "ModifierOwnerSkillTargetEntityList"},
    }, ctx, "P")
    modifier = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByIsContainModifier", "ModifierName": {"Value": "Mark"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": "ModifierOwnerSkillTargetEntityList"},
    }, ctx, "P")
    assert "character_id($it) == '1413'" in character
    assert "has_modifier($it, 'Mark')" in modifier
    assert character.startswith("count_selected(") and modifier.startswith("count_selected(")
    assert not ctx.unsupported

    eng = engine_vs_dummy(enemies=[make_dummy("source")], allies=[make_actor("1413")])
    source, ally = eng.state.actors["source"], eng.state.actors["1413"]
    payload = {"targets": ["hero", "1413"]}
    assert eng._hooks._hook_amount(character, source, payload)
    assert not eng._hooks._hook_amount(character, source, {"targets": ["hero"]})
    assert not eng._hooks._hook_amount(modifier, source, payload)
    eng._apply_modifier_spec(ally, {
        "modifier_id": "Mark", "modifier_type": "buff", "duration": 0,
        "max_stack": 1}, source)
    assert eng._hooks._hook_amount(modifier, source, payload)


def test_select_n_hook_alias_uses_real_closed_over_target_alias():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    enemy_id = "4012033"
    skills = get_enemy_skills(enemy_id)
    compiler = AbilityCompiler(enemy_id, skills, get_enemy_ability_sources(enemy_id))
    ctx = _Context(mode="event", skill=skills[0], event="before_action")
    base = "MMonster_W4_Claymore_01_LocalLegend_WhiteCurse_Target"
    first = compiler._hook_target(f"{base}.Select1", ctx)
    second = compiler._hook_target(f"{base}.Select2", ctx)
    assert first["index"] == 0 and second["index"] == 1
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")], allies=[make_actor("ally")])
    source = eng.state.actors["source"]
    for target in (eng.state.actors["hero"], eng.state.actors["ally"]):
        eng._apply_modifier_spec(target, {
            "modifier_id": "MMonster_W4_Claymore_01_LocalLegend_WhiteCurse",
            "modifier_type": "debuff", "duration": 0, "max_stack": 1}, source)
    assert eng._hooks._hook_target_states(first, source, {}) == [eng.state.actors["hero"]]
    assert eng._hooks._hook_target_states(second, source, {}) == [eng.state.actors["ally"]]
    out = compiler.compile_skill("Skill01")
    binding = next(effect for hook in out["hooks"] for effect in hook.get("effects", [])
                   if effect.get("effect_type") == "set_dynamic_target"
                   and isinstance(effect.get("target"), dict)
                   and effect["target"].get("index") == 0)
    assert binding["owner"] == "self"
    eng._hooks._run_hook_effect(source, binding, {})
    assert eng._enemy_policy_state["source"]["dynamic_targets"][binding["dynamic_key"]] == "hero"


def test_target_query_light_avatar_alive_only():
    from dataclasses import replace
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="action", skill=skills[0])
    raw = {"$type": "RPG.GameCore.TargetQuery", "TeamTypeMask": "TeamLight",
           "EntityTypeMask": "Avatar", "AliveStateMask": "Mask_AliveOnly"}
    spec = compiler._target_spec(raw, ctx, "target")
    assert spec == {"pool": "allies",
                    "where": "actor_type_of($it) == 'character' and actor_alive($it)"}
    pet = replace(make_actor("pet"), actor_type="summon", summoner_id="hero")
    eng = engine_vs_dummy(enemies=[make_dummy("source")], allies=[pet, make_actor("ally")])
    source = eng.state.actors["source"]
    assert [state.actor.actor_id for state in eng._hooks._hook_target_states(spec, source, {})] == [
        "hero", "ally"]
    eng.state.actors["ally"].alive = False
    assert [state.actor.actor_id for state in eng._hooks._hook_target_states(spec, source, {})] == ["hero"]

    raw["AliveStateMask"] = "Bit_Deathrattle"
    assert compiler._target_spec(raw, ctx, "target") is None
    assert any("仅支持 TeamLight/Avatar" in issue["reason"] for issue in ctx.unsupported)


def test_target_sort_monster_rank_uses_rank_host():
    import types
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="action", skill=skills[0])
    spec = compiler._target_spec({"$type": "RPG.GameCore.TargetSequence", "Sequence": [
        {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
        {"$type": "RPG.GameCore.TargetSortMonsterRank", "HighestFirst": True},
    ]}, ctx, "target")
    assert spec["order_by"] == "-monster_rank($it)" and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[
        make_dummy("minion"), make_dummy("boss"), make_dummy("elite")])
    for actor_id, rank in (("minion", "Minion"), ("boss", "BigBoss"), ("elite", "Elite")):
        eng._enemy_policies[actor_id] = types.SimpleNamespace(monster_rank=rank)
    selected = eng._hooks._hook_target_states(spec, eng.state.actors["minion"], {})
    assert [state.actor.actor_id for state in selected] == ["boss", "elite", "minion"]


def test_score_lowest_servant_sorts_after_pre_shuffle():
    import random
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim.pipeline import MODE_ROLL
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    compiler = AbilityCompiler("8034012", get_enemy_skills("8034012"),
                               get_enemy_ability_sources("8034012"))
    ctx = __import__("hsr_nous.adapters.enemy_ability", fromlist=["_Context"])._Context(
        mode="event", skill={"skill_id": "s1"}, event="on_action")
    spec = compiler._hook_target("Monster_W3_Aventurine_00_IF_ScoreLowest_Servant", ctx)
    assert spec["pre_shuffle"] is True and spec["take"] == 1
    assert spec["order_by"] == "stacks($it.actor_id, 'MMonster_W3_Aventurine_00_IF_Score_Dark')"

    eng = engine_vs_dummy(enemies=[make_dummy("high"), make_dummy("low"), make_dummy("charged")],
                          mode=MODE_ROLL, seed=7)
    eng.pipeline.rng = random.Random(7)
    for actor_id, score in (("high", 5), ("low", 1), ("charged", 0)):
        state = eng.state.actors[actor_id]
        state.modifiers["MMonster_W3_Aventurine_00_IF_Score_Dark"] = Modifier(
            modifier_id="MMonster_W3_Aventurine_00_IF_Score_Dark",
            name="Score", modifier_type="debuff", stacks=score)
    eng.state.actors["charged"].modifiers["MMonster_W3_Aventurine_00_IF_Skill11_Charge"] = Modifier(
        modifier_id="MMonster_W3_Aventurine_00_IF_Skill11_Charge",
        name="Charge", modifier_type="buff")
    picked = eng._hooks._hook_target_states(spec, eng.state.actors["hero"], {})
    assert [state.actor.actor_id for state in picked] == ["low"]


def test_param_entity_servant_summoner_and_concat_targets():
    from hsr_nous.sim.state import ActorState
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = __import__("hsr_nous.adapters.enemy_ability", fromlist=["_Context"])._Context(
        mode="event", skill=skills[0], event="after_being_hit")
    spec = compiler._hook_target(
        "ParamEntity + ParamEntity.GetServant + ParamEntity.GetSummoner", ctx)
    assert spec == {"concat": [
        {"pool": "$event.target"},
        {"pool": "all", "where": "$it.summoner_id == $event.target"},
        {"pool": "all", "where": "$it.actor_id == summoner_of($event.target)"},
    ]}

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    hero.actor.summoner_id = "master"
    for actor_id, summoner_id in (("servant", "hero"), ("master", "")):
        actor = make_actor(actor_id)
        actor.summoner_id = summoner_id
        eng.state.actors[actor_id] = ActorState(actor=actor, current_hp=actor.stats.hp)
    picked = eng._hooks._hook_target_states(spec, source, {"target": "hero"})
    assert [state.actor.actor_id for state in picked] == ["hero", "servant", "master"]


def test_shuffle_aliases_use_full_permutation_in_roll_mode():
    import random
    from hsr_nous.sim.pipeline import MODE_ROLL
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = __import__("hsr_nous.adapters.enemy_ability", fromlist=["_Context"])._Context(
        mode="event", skill=skills[0], event="on_action")
    spec = compiler._hook_target("AllEnemy.RemoveServant.Shuffle", ctx)
    assert spec == {"pool": "allies", "where": "not $it.summoner_id", "mode": "shuffle"}
    event_spec = compiler._target_spec(
        {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntityList.Shuffle"}, ctx, "P")
    assert event_spec == {"pool": "$event.targets", "mode": "shuffle"}

    eng = engine_vs_dummy(
        enemies=[make_dummy("source")], allies=[make_actor("ally")], mode=MODE_ROLL, seed=17)
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    ally = eng.state.actors["ally"]
    eng.pipeline.rng = random.Random(17)
    picked = eng._hooks._hook_target_states(spec, source, {})
    assert [state.actor.actor_id for state in picked] == [
        state.actor.actor_id for state in random.Random(17).sample([hero, ally], 2)]


@pytest.mark.parametrize(("alias", "pool", "where"), [
    ("AbilityTargetAdjoinEntity", "allies", "is_adjacent($it, $event.target)"),
    ("AbilityTargetAndAdjoinEntity", "allies",
     "($it.actor_id == $event.target or is_adjacent($it, $event.target))"),
    ("CasterAdjoinEntity", "enemies", "is_adjacent($it, $self.actor_id)"),
])
def test_retarget_adjacent_aliases_use_target_algebra(alias, pool, where):
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.Retarget",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
            "ByRandom": True,
            "TaskList": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "WMonster_TY_Elite01_00_Skill07_Mark"},
            }],
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["target"] == {
        "pool": pool, "where": where, "take": 1, "mode": "random"}

    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "ModifierName": {"Value": "WMonster_TY_Elite01_00_Skill07_Mark"},
    }]
    direct = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert direct["ok"] and not direct["unsupported"]
    assert direct["hooks"][0]["effects"][0]["target"] == {"pool": pool, "where": where}


def test_trigger_ability_binds_caller_dynamic_values():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {"TargetType": "AllEnemy"}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.TriggerAbility", "AbilityName": {"Value": "B"},
        "DynamicValues": {"Ratio": {"IsDynamic": False, "FixedValue": {"Value": 0.375}}},
    }]
    sources["abilities"]["B"] = {"Name": "B", "OnStart": [{
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "AttackProperty": {"DamageType": "Fire", "DamagePercentage": _dynamic(
            "AQAR", hashes=[dynamic_value_hash("Ratio")])},
    }]}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["scaling"] == [{"atk": 0.375}]


def test_abort_disable_action_gates_triggered_ability():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.TriggerAbility", "AbilityName": {"Value": "B"},
        "AbortBehaviorFlags": ["DisableAction"],
    }]
    sources["abilities"]["B"] = {"Name": "B", "OnStart": [{
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Mark"},
    }]}
    sources["modifiers"] = {"Mark": {}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "not action_disabled($self.actor_id)" in out["hooks"][0]["condition"]


def test_custom_modifier_event_preserves_target_and_marker_errors():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "ModifierName": {"Value": "MCommon_SkillTarget"},
    }, {
        "$type": "RPG.GameCore.TriggerModifierCustomEvent",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "EventType": {"EnumIndex": 4, "Value": 6},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]
    reasons = {issue["reason"] for issue in out["unsupported"]}
    assert "modifier 定义缺失：MCommon_SkillTarget" in reasons
    assert "自定义事件目标或数值未注册" in reasons


def test_custom_modifier_events_trigger_only_matching_dot_element():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    effects = []
    for event_value, element in ((3, "thunder"), (4, "wind")):
        out = _task_skill({
            "$type": "RPG.GameCore.TriggerModifierCustomEvent",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "EventType": {"EnumIndex": 4, "Value": event_value},
            "DynamicKey": "DOT_TriggerRatio",
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 0.75}},
        })
        assert out["ok"] and not out["unsupported"]
        effect = out["hooks"][0]["effects"][0]
        assert effect == {"effect_type": "trigger_dot", "target": "self",
                          "ratio": 0.75, "dot_element": element}
        effects.append(effect)

    eng = engine_vs_dummy(enemies=[make_dummy("enemy")])
    hero = eng.state.actors["hero"]
    for modifier_id, element in (("shock", "thunder"), ("poison", "wind")):
        hero.modifiers[modifier_id] = Modifier(
            modifier_id=modifier_id, name=modifier_id, modifier_type="dot", debuff_kind="dot",
            duration=2, source_id="enemy", dot_element=element,
            dot_ratio=1.0, dot_source_atk=1000.0)
    triggered = []
    eng.bus.subscribe("on_dot_retrigger", lambda _et, payload, _ctx: triggered.append(
        payload["modifier_id"]))
    for effect in effects:
        eng._hooks._run_hook_effect(hero, effect, {})
    assert triggered == ["shock", "poison"]
    assert set(hero.modifiers) == {"shock", "poison"}

    for enemy_id in ("2004010", "8024010", "8003051"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.TriggerModifierCustomEvent"
                       for item in real["unsupported"])


def test_bare_modifier_predicate_is_ignored_only_in_presentation_branch():
    skills, sources = _predicate_skill({})
    predicate = {
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "ModifierName": {"Value": "VisualMark"},
    }
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "FailedTaskList": [predicate, {
            "$type": "RPG.GameCore.TriggerEffect",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "EffectPath": "Effects/VisualOnly",
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]

    sources["abilities"]["A"]["OnStart"][0]["FailedTaskList"].append({
        "$type": "RPG.GameCore.SetDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "DynamicKey": {"Value": "MustKeepCondition"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]


def test_include_local_template_and_presentation_nodes():
    presentation = [
        "ShowBattleUI", "HideLevelStage", "SetSimulationSpeedEnable", "TriggerSound", "DebugLog",
        "SetMonsterEnergyBarState", "SetTeamRootOffset", "ScaleCharacterModel",
        "SetAttachmentVisibility", "ChangeTargetModifierEffectState", "SetEntityPosition",
        "SetEntityFollowAttachPoint", "ClearEntityFollowAttachPoint", "HideEntityForCurrentCamera",
        "WaitTimelineFinish", "WaitAnimEvent", "ShowBattleAlert", "HideEffectByCharacterType",
        "SetCharacterPartsVisibility", "AudioSetRTPCValueByRatio",
        "SetTriggeredFormationAssetAutoCenter", "TriggerEnergyBarEffect", "PlayMonsterHPBarTween",
        "ResetBattleBGMToStage", "SetBattleBGMState", "GetGapSecondsForSyncWithBgm",
        "RemoveChallengeBossInfoPanelState", "AddChallengeBossInfoPanelState",
        "CharacterReactionAnimConfig", "HideCharacterFilteredEffect", "LevelAudioState",
        "LevelAudioSwitch", "ModifierDetachEffect", "PlayScreenTransfer", "RefreshChangePhaseUI",
        "ReleaseCharacterHUDVisibleControl", "SetAttachEffectTimeSlow",
        "SetCharacterEffectMaterialBlock", "SetCharacterScaleFollow", "SetLocalOffsetAsMoveTarget",
        "SetTargetDamageTextVisible", "ShowBossInfoBar", "StackStatusDesc", "ToggleUITop",
        "TargetTimeSlow", "ClearTargetTimeSlow", "RemoveGlobalTimeSlow",
        "ChangeCharacterConfigParamClientOnly", "UpdateMonsterFootIKMode",
        "ChangeMonsterHeadIcon", "SetCharacterVisibilityFollow",
        "SetMonsterHitCountEnergyBarState", "SetBattleItemProgressInfo",
        "WriteCustomValueToStatistic", "WaitParallelTimeStamp",
    ]
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {
            "Name": "A",
            "OnStart": [{"$type": f"RPG.GameCore.{name}"} for name in presentation] + [{
                "$type": "RPG.GameCore.IncludeTaskListTemplate", "Name": "Hit",
            }],
            "TaskListTemplate": [{
                "Name": "Hit", "TaskList": [{
                    "$type": "RPG.GameCore.RemoveModifier",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                    "ModifierName": {"Value": "Mark"},
                }],
            }],
        }},
        "modifiers": {"Mark": {}},
    }
    sources["abilities"]["A"]["OnStart"].insert(-1, {"$type": "PBEMMHIOJBO"})
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "remove_modifier", "target": "self", "modifier_id": "Mark",
    }]

    sources["abilities"]["A"]["TaskListTemplate"][0]["TaskList"] = [{
        "$type": "RPG.GameCore.IncludeTaskListTemplate", "Name": "Hit",
    }]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("循环引用" in item["reason"] for item in rejected["unsupported"])


@pytest.mark.parametrize("include_type", [
    "RPG.GameCore.IncludeTaskListTemplate", "RPG.GameCore.IncludeGlobalTaskListTemplate",
])
def test_global_template_dynamic_values_expand_in_caller_context(include_type):
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": include_type, "Name": "Shared",
        "DynamicValues": {
            "Ratio": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        },
    }]
    sources["global_templates"] = {"Shared": {
        "Name": "Shared", "TaskList": [{
            "$type": "RPG.GameCore.ResetStance",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ConstantValue": _dynamic("AQAR", hashes=[dynamic_value_hash("Ratio")]),
        }],
    }}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "reset_stance", "target": "self", "mode": "set", "amount": 0.5,
    }]

    sources["global_templates"]["Shared"]["TaskList"][0]["TargetType"] = {
        "$type": "RPG.GameCore.TargetAlias", "Alias": "TemplateParamEntityList"}
    sources["abilities"]["A"]["OnStart"][0]["ParamTarget"] = {
        "$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"}
    targeted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert targeted["ok"] and not targeted["unsupported"]
    assert targeted["hooks"][0]["effects"] == [{
        "effect_type": "reset_stance", "target": {"pool": "allies"},
        "mode": "set", "amount": 0.5,
    }]

    sources["abilities"]["A"]["OnStart"][0]["ParamTarget"] = {
        "$type": "RPG.GameCore.TargetFetchUniqueNameEntity", "UniqueName": "BE_Test"}
    unique = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert unique["ok"] and not unique["unsupported"]
    assert unique["hooks"][0]["effects"][0]["target"] == {"pool": "unique:BE_Test"}


@pytest.mark.parametrize("include_type", [
    "RPG.GameCore.IncludeTaskListTemplate", "RPG.GameCore.IncludeGlobalTaskListTemplate",
])
def test_template_switch_reads_caller_dynamic_values(include_type):
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": include_type, "Name": "Shared",
        "DynamicValues": {"Choice": {"IsDynamic": False, "FixedValue": {"Value": 2}}},
    }]
    sources["global_templates"] = {"Shared": {
        "Name": "Shared", "TaskList": [{
            "$type": "RPG.GameCore.SwitchCaseByDynamicValue",
            "Switch": _dynamic("AQAR", hashes=[dynamic_value_hash("Choice")]),
            "CaseTaskList": [{
                "Case": {"IsDynamic": False, "FixedValue": {"Value": value}},
                "TaskList": [{
                    "$type": "RPG.GameCore.RemoveModifier",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                    "ModifierName": {"Value": f"Mark{value}"},
                }],
            } for value in (1, 2)],
        }],
    }}
    sources["modifiers"] = {"Mark1": {}, "Mark2": {}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "remove_modifier", "target": "self", "modifier_id": "Mark2"}]

    sources["abilities"]["A"]["OnStart"][0]["DynamicValues"]["Choice"] = _dynamic(
        "AQAR", hashes=[dynamic_value_hash("CurrentSummonIndex")])
    dynamic = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert dynamic["ok"] and not dynamic["unsupported"], dynamic["unsupported"]
    conditions = [effect.get("condition", "") for hook in dynamic["hooks"]
                  for effect in hook["effects"] if effect["effect_type"] == "remove_modifier"]
    assert any("(dynamic_of($self.actor_id, 'CurrentSummonIndex')) == 2" in condition
               for condition in conditions), conditions

    sources["abilities"]["A"]["OnStart"][0]["DynamicValues"]["Choice"] = {
        "IsDynamic": False, "FixedValue": {"Value": 2}}
    sources["custom_values"] = {"Choice": 1}
    sources["abilities"]["A"]["OnStart"].insert(0, {
        "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Choice"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}})
    mutable = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert mutable["ok"] and not mutable["unsupported"]
    removes = [effect for hook in mutable["hooks"] for effect in hook["effects"]
               if effect["effect_type"] == "remove_modifier"]
    assert any("dynamic_of($self, 'Choice') == 2" in effect["condition"]
               for effect in removes)


def test_unique_name_binds_fetches_and_checks_alive_target():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetTargetUniqueName",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "UniqueName": {"RawString": "SelectTarget"},
    }, {
        "$type": "RPG.GameCore.TurnInsertAction",
        "TargetType": {"$type": "RPG.GameCore.TargetFetchUniqueNameEntity",
                       "UniqueName": "SelectTarget"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    bind, insert = out["hooks"][0]["effects"]
    assert bind == {"effect_type": "set_dynamic_target", "dynamic_key": "SelectTarget",
                    "target": "$event.target", "scope": "unique_name"}
    assert insert == {"effect_type": "grant_extra_turn",
                      "target": {"pool": "unique:SelectTarget"}}

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsTargetValid",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": "MMonster_W4_Claymore_01_BattleEvent_SelectTarget"},
        "AliveOnly": True, "Inverse": True,
    })
    predicate = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert predicate["ok"] and not predicate["unsupported"]
    condition = predicate["hooks"][0]["condition"]
    assert 'not actor_alive(unique_target("SelectTarget"))' in condition

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    payload = {"actor": "source", "action_id": "s1", "target": "hero"}

    def evaluate(text):
        return eng._expr.evaluate(
            eng._expr.compile(text, layer="effect"), eng._hooks._hook_ctx(source, payload),
            functions=eng._hooks._hook_functions(source))

    assert evaluate('unique_target("Missing")') == ""
    eng._hooks._run_hook_effect(source, bind, payload)
    assert eng._enemy_policy_state["$level"]["dynamic_targets"]["SelectTarget"] == "hero"
    assert evaluate('unique_target("SelectTarget")') == "hero"
    assert eng._hooks._hook_target_states(insert["target"], source, payload) == [hero]
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0
    hero.alive = False
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0

    eng._hooks._run_hook_effect(source, bind, {**payload, "target": "source"})
    assert evaluate('unique_target("SelectTarget")') == "source"


def test_parallel_templates_inline_only_zero_delays():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.TriggerParallelTaskListTemplate",
        "Templates": [
            {"Name": "A", "BaseDelay": {"IsDynamic": False, "FixedValue": {"Value": 0}},
             "DelayInterval": {"IsDynamic": False, "FixedValue": {"Value": 0}}},
            {"Name": "B", "BaseDelay": {"IsDynamic": False, "FixedValue": {"Value": 0}},
             "DelayInterval": {"IsDynamic": False, "FixedValue": {"Value": 0}}},
        ],
    }]
    sources["global_templates"] = {
        "A": {"Name": "A", "TaskList": [{
            "$type": "RPG.GameCore.ResetStance",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ConstantValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
        }]},
        "B": {"Name": "B", "TaskList": [{
            "$type": "RPG.GameCore.ResetStance",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ConstantValue": {"IsDynamic": False, "FixedValue": {"Value": 0.2}},
        }]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [effect["amount"] for effect in effects] == [0.1, 0.2]


def test_monster_template_and_custom_value_bool_predicates():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterTemplateID",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "TargetMonsterTemplateID": {"IsDynamic": False, "FixedValue": {"Value": 2013010}},
    })
    sources["monster_template_id"] = "2013010"
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and "1 == 1" in out["hooks"][0]["condition"]

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCheckCustomValueBool",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Key": {"Hash": dynamic_value_hash("Elite")}, "Inverse": True,
    })
    sources["custom_value_tags"] = ["Elite"]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and "not (in_group($self.actor_id, 'Elite'))" in out["hooks"][0]["condition"]


def test_ability_property_hp_speed_and_target_sequence():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareAbilityProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Property": "CurrentHP", "CompareType": "LessEqual",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and "hp_of($self.actor_id) <= 0" in out["hooks"][0]["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    st = eng.state.actors["source"]
    st.current_hp = 0
    assert eng._hooks._hook_amount(out["hooks"][0]["condition"], st, {
        "actor": "source", "action_id": "s1"}) == 1.0
    st.current_hp = 1
    assert eng._hooks._hook_amount(out["hooks"][0]["condition"], st, {
        "actor": "source", "action_id": "s1"}) == 0.0

    sources["abilities"]["A"]["OnStart"][0]["Predicate"]["Property"] = "BaseSpeed"
    sources["abilities"]["A"]["OnStart"][0]["Predicate"]["CompareType"] = "Equal"
    speed = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert speed["ok"] and "base_stat_of($self.actor_id, 'spd') == 0" in speed["hooks"][0]["condition"]

    sources["abilities"]["A"]["OnStart"][0]["Predicate"].update({
        "TargetType": {"$type": "RPG.GameCore.TargetSequence", "Sequence": [{
            "$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeamMember"}]},
        "Property": "CurrentHP", "CompareType": "LessEqual",
    })
    sequence = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert sequence["ok"] and "count_selected" in sequence["hooks"][0]["condition"]
    assert "hp_of($it) <= 0" in sequence["hooks"][0]["condition"]


def test_hp_predicate_reads_runtime_hp_and_summoner():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "CompareType": "LessEqual", "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "hp_of($self.actor_id) <= 0" in condition

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1"}
    source.current_hp = 0.0
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    source.current_hp = 1.0
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummoner"},
        "CompareType": "Greater", "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    })
    summoner = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert summoner["ok"] and not summoner["unsupported"]
    assert "hp_of(summoner_of($self.actor_id)) > 0" in summoner["hooks"][0]["condition"]


def test_alive_predicate_uses_actor_alive_and_accepts_alive_or_limbo():
    from tests._builders import engine_vs_dummy, make_dummy

    predicate = {
        "$type": "RPG.GameCore.ByTargetAliveState",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "AliveStateMask": "Mask_AliveOnly", "Inverse": True,
    }
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "not actor_alive($self.actor_id)" in condition

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1"}
    source.alive = False
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    source.alive = True
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0

    predicate["AliveStateMask"] = "Mask_AliveOrLimbo"
    skills, sources = _predicate_skill(predicate)
    accepted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert accepted["ok"] and not accepted["unsupported"]
    limbo_condition = accepted["hooks"][0]["condition"]
    source.current_hp = 0
    source.alive = True
    assert eng._hooks._hook_amount(limbo_condition, source, payload) == 0.0
    source.alive = False
    assert eng._hooks._hook_amount(limbo_condition, source, payload) == 1.0

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCasterAliveOrLimbo", "AliveStateMask": "Mask_AliveOnly"})
    caster = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert caster["ok"] and not caster["unsupported"]
    assert "actor_alive($self.actor_id)" in caster["hooks"][0]["condition"]


def test_top_action_delay_target_uses_scheduler_preview():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByIsTopActionDelayTarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "CompareTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
    }, ctx, "P")
    assert expression == "is_top_action_delay_target($event.target, 'light')"
    assert not ctx.unsupported
    eng = engine_vs_dummy(allies=[make_actor("ally", spd=50)], enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(expression, source, {"target": "hero"})
    assert not eng._hooks._hook_amount(expression, source, {"target": "ally"})


@pytest.mark.parametrize(("target_alias", "alive_only", "expected"), [
    ("Caster", True, "actor_alive($self.actor_id)"),
    ("DamageAttackerEntity", None, "not actor_alive($event.source)"),
])
def test_valid_target_predicate_uses_actor_alive(target_alias, alive_only, expected):
    from tests._builders import engine_vs_dummy, make_dummy

    predicate = {
        "$type": "RPG.GameCore.ByIsTargetValid",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": target_alias},
        "Inverse": target_alias == "DamageAttackerEntity",
    }
    if alive_only is not None:
        predicate["AliveOnly"] = alive_only
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert expected in out["hooks"][0]["condition"]

    if target_alias == "DamageAttackerEntity":
        eng = engine_vs_dummy(enemies=[make_dummy("source")])
        hero = eng.state.actors["hero"]
        payload = {"actor": "source", "action_id": "s1", "source": "hero"}
        hero.alive = True
        assert eng._hooks._hook_amount(out["hooks"][0]["condition"],
                                       eng.state.actors["source"], payload) == 0.0
        hero.alive = False
        assert eng._hooks._hook_amount(out["hooks"][0]["condition"],
                                       eng.state.actors["source"], payload) == 1.0

    predicate["AliveOnly"] = False
    skills, sources = _predicate_skill(predicate)
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("AliveOnly=true" in issue["reason"] for issue in rejected["unsupported"])


def test_summon_relation_filters_actual_summons():
    from tests._builders import engine_vs_dummy, make_dummy

    relation = {
        "$type": "RPG.GameCore.ByHasSummonRelation",
        "SummonerType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ServantType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    }
    mark = "WMonster_TY_Elite01_00_Skill07_Mark"
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "Predicate": relation,
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": mark},
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"]["where"] == "summoner_of($it) == $self.actor_id"

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("servant"), make_dummy("other"),
    ])
    source = eng.state.actors["source"]
    servant = eng.state.actors["servant"]
    servant.actor.summoner_id = "source"
    eng._hooks._run_hook_effect(source, effect, {})
    assert mark in servant.modifiers
    assert mark not in source.modifiers
    assert mark not in eng.state.actors["other"].modifiers

    relation["Inverse"] = True
    inverse = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert inverse["ok"] and not inverse["unsupported"]
    assert "not (summoner_of($it) == $self.actor_id)" in inverse["hooks"][0]["effects"][0]["target"]["where"]


def test_entity_type_filters_servant_and_avatar():
    from tests._builders import engine_vs_dummy, make_dummy

    predicate = {
        "$type": "RPG.GameCore.ByTargetEntityType",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "EntityTypeMask": "Servant",
    }
    mark = "WMonster_TY_Elite01_00_Skill07_Mark"
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "Predicate": predicate,
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": mark},
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"]["where"] == "actor_type_of($it) == 'summon' or summoner_of($it) != ''"

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("servant"), make_dummy("other"),
    ])
    source = eng.state.actors["source"]
    servant = eng.state.actors["servant"]
    servant.actor.summoner_id = "source"
    eng._hooks._run_hook_effect(source, effect, {})
    assert mark in servant.modifiers
    assert mark not in source.modifiers
    assert mark not in eng.state.actors["other"].modifiers

    predicate["EntityTypeMask"] = "Avatar"
    avatar = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert avatar["ok"] and not avatar["unsupported"]
    assert avatar["hooks"][0]["effects"][0]["target"]["where"] == \
        "actor_type_of($it) == 'character'"

    predicate["EntityTypeMask"] = "Servant"
    predicate["Inverse"] = True
    inverse = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert inverse["ok"] and not inverse["unsupported"]
    assert "not (actor_type_of($it) == 'summon' or summoner_of($it) != '')" in \
        inverse["hooks"][0]["effects"][0]["target"]["where"]


def test_monster_rank_predicate_uses_config_ai_rank_mapping():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterRank",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "CompareType": "LessEqual", "CompareValue": 2,
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "monster_rank($it) <= 2" in out["hooks"][0]["condition"]


def test_monster_id_predicate_reads_each_target():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterID",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "TargetMonsterID": {"IsDynamic": False, "FixedValue": {"Value": 2004023}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "monster_id($it) == '2004023'" in out["hooks"][0]["condition"]


def test_monster_template_predicate_reads_param_entity_and_summoner():
    from tests._builders import engine_vs_dummy, make_dummy

    for alias, namespace in (("ParamEntity", "$it"),
                             ("CasterSummoner", "summoner_of($self.actor_id)")):
        skills, sources = _predicate_skill({
            "$type": "RPG.GameCore.ByCompareMonsterTemplateID",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
            "TargetMonsterTemplateID": {"IsDynamic": False, "FixedValue": {"Value": 4014014}},
        })
        out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
        assert out["ok"] and not out["unsupported"]
        assert f"monster_id({namespace}) == '4014014'" in out["hooks"][0]["condition"]

    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("4014014")])
    source = eng.state.actors["source"]
    source.actor.summoner_id = "4014014"
    assert eng._hooks._hook_amount(
        "monster_id(summoner_of($self.actor_id)) == '4014014'", source, {})
    source.actor.summoner_id = "missing"
    assert not eng._hooks._hook_amount(
        "monster_id(summoner_of($self.actor_id)) == '4014014'", source, {})


def test_battle_event_entity_predicate_reuses_actor_type():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsBattleEventEntity", "Inverse": True,
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "not (actor_type_of($it) == 'battle_event')" in out["hooks"][0]["condition"]


def test_behavior_flag_plural_single_and_explicit_and():
    for predicate, expected in (
        ({"Flags": ["Break"]}, "broken_of($self.actor_id)"),
        ({"Flags": ["STAT_CTRL_Frozen", "DisableAction"], "ContainType": "And"},
         "(controlled($self.actor_id, 'freeze') and action_disabled($self.actor_id))"),
    ):
        skills, sources = _predicate_skill({
            "$type": "RPG.GameCore.ByContainBehaviorFlag",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            **predicate,
        })
        out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
        assert out["ok"] and not out["unsupported"]
        assert expected in out["hooks"][0]["condition"]

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Flags": ["STAT_CTRL_Frozen", "STAT_CTRL_Frozen_Effect"],
    })
    accepted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert accepted["ok"] and not accepted["unsupported"]
    assert " or " in accepted["hooks"][0]["condition"]


def test_character_id_predicate_reads_each_target():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareCharacterID",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "TargetCharacterID": {"IsDynamic": False, "FixedValue": {"Value": 1220}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "character_id($it) == '1220'" in out["hooks"][0]["condition"]


def test_camera_numeric_suffix_and_stack_properties():
    from hsr_nous.adapters.enemy_ability import _is_camera_ability

    assert _is_camera_ability("Monster_Skill04_Camera02")
    assert _is_camera_ability("Boss_Cocolia_RL_Weapon_DeathSetCamera")
    assert _is_camera_ability("Boss_Cocolia_RL_Weapon_MuteHitFly")
    assert not _is_camera_ability("Boss_Cocolia_RL_Weapon_DeathEffect")
    assert not _is_camera_ability("Monster_Skill04_Camera02_Phase")
    real = _real_compiler("1002015").compile_enemy()
    assert not any(item["owner"].endswith(("DeathSetCamera", "MuteHitFly"))
                   for item in real["unsupported"])
    assert any(item["owner"].endswith("DeathEffect") for item in real["unsupported"])
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Buff"},
            "DynamicValues": {"MDF_PropertyValue": {
                "IsDynamic": False, "FixedValue": {"Value": 0.2}}},
        }, {
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {"$type": "RPG.GameCore.ByIsContainModifier",
                          "ModifierName": {"Value": "Buff"}},
        }]}},
        "modifiers": {"Buff": {"_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.2}},
            }, {
                "$type": "RPG.GameCore.StackProperty", "Property": "DefenceAddedRatio",
                "PropertyValue": _dynamic("AAAOAQAEEQ==", hashes=[2128130574], fixed=[1]),
            }, {
                "$type": "RPG.GameCore.StackProperty", "Property": "AllDamageReduce",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
            }, {
                "$type": "RPG.GameCore.StackProperty", "Property": "HPAddedRatio",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.2}},
            }, {
                "$type": "RPG.GameCore.StackProperty", "Property": "SPRatioBase",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.3}},
            }, {
                "$type": "RPG.GameCore.StackProperty", "Property": "CriticalDamageBase",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.4}},
            }, {
                "$type": "RPG.GameCore.StackProperty", "Property": "AttackDelta",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 50}},
            }, {
                "$type": "RPG.GameCore.StackProperty", "Property": "HPDelta",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 1000}},
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["modifier"]["stat_effects"] == {
        "atk_pct": 0.2, "def_pct": -0.2, "dmg_dmg_reduction": 0.1,
        "hp_pct": 0.2, "energy_regen": 0.3, "crit_dmg": 0.4,
        "atk": 50, "hp": 1000}


def test_property_dynamic_value_write_then_read_compiles_live():
    """写后读（#26 期 2/3）：同技能 SetByProperty 后再 ByCompareDynamicValue——
    旧"旧事件快照"拒因退役，改翻单 hook + effect 级活读条件。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "Owner_ATK",
            "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "Value": "BaseAttack",
        }, {
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareDynamicValue",
                "DynamicKey": {"Value": "Owner_ATK"}, "CompareType": "GreaterEqual",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1000}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "ModifierName": {"Value": "Buff"},
            }],
        }]}},
        "modifiers": {"Buff": {"_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[0] == {
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "Owner_ATK",
        "amount": "base_stat_of($self.actor_id, 'atk')",
    }
    # 写后读分支：Buff 施加效果带 effect 级活读条件（执行时读帧覆盖层，非快照）。
    assert effects[1]["effect_type"] == "apply_modifier"
    assert "dynamic_of($self, 'Owner_ATK') >= 1000" in effects[1]["condition"]

    sources["abilities"]["A"]["OnStart"] = sources["abilities"]["A"]["OnStart"][:1]
    accepted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert accepted["ok"] and not accepted["unsupported"]
    assert accepted["hooks"][0]["effects"][0] == {
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "Owner_ATK",
        "amount": "base_stat_of($self.actor_id, 'atk')",
    }


def test_property_dynamic_param_entity_reads_each_target():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    task = {
        "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "_MaxHP",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "Value": "MaxHP",
    }
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        "TaskList": [task],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "_MaxHP",
        "amount": "max_hp_of($target)", "amount_target": {"pool": "allies"},
    }

    eng = engine_vs_dummy(allies=[make_actor("ally", hp=6000)], enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    runtime = eng._enemy_policy_state["source"]
    assert runtime["dynamic_values"]["_MaxHP"] == 6000.0

    runtime["dynamic_values"].clear()
    empty = {**effect, "amount_target": {"pool": "allies", "where": "0"}}
    eng._hooks._run_hook_effect(source, empty, {})
    assert "_MaxHP" not in runtime["dynamic_values"]

    sources["abilities"]["A"]["OnStart"] = [task]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("ParamEntity" in issue["reason"] for issue in rejected["unsupported"])


def test_retarget_predicate_reads_values_written_by_previous_effect():
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "X"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }, {
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "Predicate": {
            "$type": "RPG.GameCore.ByCompareDynamicValue", "DynamicKey": {"Value": "X"},
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "CompareType": "Equal",
            "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        },
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "DynamicKey": {"Value": "Seen"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[1]["target"]["where"] == "dynamic_of($it, 'X') == 1"
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("partner")])
    for effect in effects:
        eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Seen"] == 1
    assert "Seen" not in eng._enemy_policy_state.get("partner", {}).get("dynamic_values", {})


@pytest.mark.parametrize(("event", "expected"), [
    ("on_turn_end", "$event.actor"),
    ("toughness_recovered", "$event.target"),
    ("before_take_damage", "$event.target"),
])
def test_param_entity_maps_turn_end_and_toughness_recovery(event, expected):
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event=event)
    assert compiler._hook_target("ParamEntity", ctx) == expected
    assert not ctx.unsupported


@pytest.mark.parametrize("event", ["on_hp_decrease", "on_hp_increase"])
def test_property_param_entity_reads_hp_event_target(event):
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event=event)
    compiler._compile_property_value({
        "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "_TargetMaxHP",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "Value": "MaxHP",
    }, ctx, "property", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    assert effect["amount"] == "max_hp_of($event.target)"
    assert "amount_target" not in effect

    eng = engine_vs_dummy(allies=[make_actor("ally", hp=6000)],
                          enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {"target": "ally"})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["_TargetMaxHP"] == 6000.0


def test_property_global_alias_reads_selected_target_stats():
    from tests._builders import engine_vs_dummy, make_dummy
    from hsr_nous.adapters.enemy_ability import _Context

    alias = "Monster_W4_Hearse_00_Self"
    skills, sources = _predicate_skill({})
    sources["target_aliases"] = {alias: {
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 405301}},
            }},
        ],
    }}
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_hp_decrease")
    compiler._compile_property_value({
        "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "_TargetMaxHP",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "Value": "MaxHP",
    }, ctx, "property", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    assert effect["amount"] == "max_hp_of($target)"
    assert effect["amount_target"] == {
        "pool": "enemies", "where": "monster_unique_id($it) == 405301"}

    eng = engine_vs_dummy(enemies=[
        make_dummy("4053010", hp=7000), make_dummy("4053020", hp=6000),
        make_dummy("4053030", hp=5000)])
    eng._hooks._run_hook_effect(eng.state.actors["4053030"], effect, {})
    assert eng._enemy_policy_state["4053030"]["dynamic_values"]["_TargetMaxHP"] == 7000.0


def test_target_list_intersects_uses_entity_identity_and_alive_flags():
    from tests._builders import engine_vs_dummy, make_dummy

    predicate = {
        "$type": "RPG.GameCore.ByTargetListIntersects",
        "FirstTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummonedMinions"},
        "SecondTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    }
    expr = _pred_expr(predicate, event="on_hp_decrease")
    assert expr.startswith("target_lists_intersect(")
    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("summon"), make_dummy("partner")])
    summon = eng.state.actors["summon"]
    summon.actor.summoner_id = "source"
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(expr, source, {"target": "summon"}) == 1.0
    assert eng._hooks._hook_amount(expr, source, {"target": "partner"}) == 0.0

    summon.alive = False
    assert eng._hooks._hook_amount(expr, source, {"target": "summon"}) == 0.0
    include_dead = _pred_expr({
        **predicate,
        "FirstTargetAliveOnly": False, "SecondTargetAliveOnly": False,
    }, event="on_hp_decrease")
    assert eng._hooks._hook_amount(include_dead, source, {"target": "summon"}) == 1.0


def test_property_energy_readers_follow_selected_actor():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    tasks = [{
        "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": key,
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "Value": value,
    } for key, value in (("_CurrentSP", "CurrentSP"), ("_MaxSP", "MaxSP"))]
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        "TaskList": tasks,
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [effect["amount"] for effect in effects] == [
        "energy_of($target)", "max_energy_of($target)"]

    eng = engine_vs_dummy(allies=[make_actor("ally", max_energy=160)],
                          enemies=[make_dummy("source")])
    ally = eng.state.actors["ally"]
    ally.current_energy = 37.5
    for effect in effects:
        eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"] == {
        "_CurrentSP": 37.5, "_MaxSP": 160.0}


def test_property_shield_reads_team_remaining_value():
    from tests._builders import engine_vs_dummy, make_dummy
    from hsr_nous.sim.state import ShieldInstance

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByProperty",
        "DynamicKey": key,
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "Value": "Shield",
    } for key, alias in (("_DarkShield", "DarkTeamEntity"),
                         ("_LightShield", "LightTeamEntity"))]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [effect["amount"] for effect in effects] == [
        "shield_of($dark_team)", "shield_of($light_team)"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    dark = eng._team_entity_state("TeamDark")
    light = eng._team_entity_state("TeamLight")
    dark.shields.extend([
        ShieldInstance(shield_id="d1", name="甲", remaining=100, modifier_id="m1"),
        ShieldInstance(shield_id="d2", name="乙", remaining=50, modifier_id="m2"),
    ])
    light.shields.append(ShieldInstance(shield_id="l1", name="丙", remaining=80))
    for effect in effects:
        eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"] == {
        "_DarkShield": 150.0, "_LightShield": 80.0}


def test_property_action_delay_reads_normalized_scheduler_distance():
    from tests._builders import engine_vs_dummy, make_dummy

    task = {
        "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "_Delay",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "Value": "ActionDelay",
    }
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "TaskList": [task],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount"] == "action_delay_of($target)"
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("partner")])
    source, partner = eng.state.actors["source"], eng.state.actors["partner"]
    eng.scheduler.set_action_delay(partner.actor, 0.5)
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["_Delay"] == 0.5


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_parallel_ability_independent_damage_and_index_targets():
    import copy
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    skills, sources = _predicate_skill({})
    sources["abilities"]["B"] = {
        "Name": "B", "TargetInfo": {"TargetType": "AbilityTargetEntity"},
        "OnStart": [{
            "$type": "RPG.GameCore.DamageByAttackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
            "AttackProperty": {"DamageType": "Fire", "DamagePercentage": {
                "IsDynamic": False, "FixedValue": {"Value": 0.5}}},
        }],
    }
    task = {
        "$type": "RPG.GameCore.TriggerParallelAbility", "ParallelAbilityList": [
            {"TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
             "AbilityInherentTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
             "AbilityName": {"Value": "B"}},
            {"TargetType": {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
                {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
                {"$type": "RPG.GameCore.TargetIndex", "IndexType": "IndexStrict",
                 "IndexValue": {"IsDynamic": False, "FixedValue": {"Value": 1}}},
            ]}, "AbilityName": {"Value": "B"}},
        ],
    }
    sources["abilities"]["A"]["OnStart"] = [task]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]
               if effect.get("effect_type") == "deal_damage"]
    assert len(effects) == 2
    assert effects[0]["target"] == {"pool": "allies"}
    assert effects[1]["target"] == {"pool": "allies", "index": 1}

    delayed = copy.deepcopy(task)
    delayed["ParallelAbilityList"][0]["Delay"] = {"IsDynamic": False, "FixedValue": {"Value": 1}}
    sources["abilities"]["A"]["OnStart"] = [delayed]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert any("非零并行 Delay" in issue["reason"] for issue in rejected["unsupported"])

    sources["abilities"]["B"]["OnStart"].append({
        "$type": "RPG.GameCore.SetDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "DynamicKey": {"Value": "Marked"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}})
    sources["abilities"]["A"]["OnStart"] = [task]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert any("无状态副作用" in issue["reason"] for issue in rejected["unsupported"])

    single = copy.deepcopy(task)
    single["ParallelAbilityList"] = single["ParallelAbilityList"][:1]
    sources["abilities"]["B"]["OnStart"][0]["AttackProperty"]["DamagePercentage"] = _dynamic(
        "AQAR", hashes=[dynamic_value_hash("_MaxStance")])
    sources["abilities"]["A"]["OnStart"] = [single]
    accepted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert accepted["ok"] and not accepted["unsupported"]
    assert any(effect["effect_type"] == "set_dynamic_value"
               for hook in accepted["hooks"] for effect in hook["effects"])
    assert any(effect.get("scaling_atk") == "dynamic_of($self.actor_id, '_MaxStance')"
               for hook in accepted["hooks"] for effect in hook["effects"])


def test_owner_add_ability_only_ignores_presentation_ability():
    skills, sources = _predicate_skill({})
    sources["abilities"]["Pure"] = {
        "Name": "Pure", "OnStart": [{"$type": "RPG.GameCore.TriggerEffect"}],
        "Modifiers": {},
    }
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.OwnerEntityAddAbility", "AbilityName": {"Value": "Pure"}}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    sources["abilities"]["Pure"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "X"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}]
    accepted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert accepted["ok"] and not accepted["unsupported"]
    effects = [effect for hook in accepted["hooks"] for effect in hook["effects"]]
    assert any(effect.get("dynamic_key") == "_ability_enabled:Pure" for effect in effects)
    assert not any(effect.get("dynamic_key") == "X" for effect in effects)
    from tests._builders import engine_vs_dummy, make_dummy
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    gate = "dynamic_of($self.actor_id, '_ability_enabled:Pure') > 0"
    assert not eng._hooks._hook_amount(gate, source, {})
    registration = next(effect for effect in effects
                        if effect.get("dynamic_key") == "_ability_enabled:Pure")
    eng._hooks._run_hook_effect(source, registration, {})
    assert eng._hooks._hook_amount(gate, source, {}) == 1.0

    sources["abilities"]["A"]["OnStart"].append({
        "$type": "RPG.GameCore.TurnInsertAbility", "AbilityName": {"Value": "Pure"}})
    triggered = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert triggered["ok"] and not triggered["unsupported"]
    assert any("_ability_enabled:Pure" in str(hook.get("condition"))
               for hook in triggered["hooks"])

    sources["character_config"]["AbilityList"] = ["Pure"]
    initial = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert initial["ok"] and not initial["unsupported"]
    assert not any("_ability_enabled:Pure" in str(effect) for hook in initial["hooks"]
                   for effect in hook["effects"])
    assert not any("_ability_enabled:Pure" in str(hook.get("condition"))
                   for hook in initial["hooks"])


def test_stage_add_ability_registers_level_gate_without_running():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["Stage"] = {
        "Name": "Stage", "OnStart": [{
            "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "X"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }], "Modifiers": {},
    }
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddStageAbilityByName", "StageAbilityName": {"Value": "Stage"},
        "CanReplace": False, "DynamicValues": {},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    registration = next(effect for effect in effects
                        if effect.get("dynamic_key") == "_stage_ability_enabled:Stage")
    assert registration["target"] == "$level"
    assert not any(effect.get("dynamic_key") == "X" for effect in effects)
    sources["abilities"]["A"]["OnStart"].append({
        "$type": "RPG.GameCore.TurnInsertAbility", "AbilityName": {"Value": "Stage"}})
    triggered = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert any("dynamic_of($level" in str(hook.get("condition"))
               and "_stage_ability_enabled:Stage" in str(hook.get("condition"))
               for hook in triggered["hooks"])

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    gate = "dynamic_of($level, '_stage_ability_enabled:Stage') > 0"
    assert not eng._hooks._hook_amount(gate, source, {})
    eng._hooks._run_hook_effect(source, registration, {})
    assert eng._hooks._hook_amount(gate, source, {}) == 1.0

    sources["abilities"]["A"]["OnStart"][0]["CanReplace"] = True
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("替换语义" in issue["reason"] for issue in rejected["unsupported"])
    real = _real_compiler("1004013").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.AddStageAbilityByName"
                   for issue in real["unsupported"])
    camera = _task_skill({
        "$type": "RPG.GameCore.AddStageAbilityByName",
        "StageAbilityName": {"Value": "Missing_Camera"},
    })
    assert camera["ok"] and not camera["unsupported"]
    real_camera = _real_compiler("4015010").compile_enemy()
    assert not any("Rognarok_Camera" in issue["reason"]
                   for issue in real_camera["unsupported"])


def test_stage_ability_static_params_bind_to_trigger_and_parallel():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddStageAbilityByName",
        "StageAbilityName": {"Value": "StageB"}, "CanReplace": False,
        "DynamicValues": {"Ratio": {"IsDynamic": False, "FixedValue": {"Value": 1.5}}},
    }, {
        "$type": "RPG.GameCore.TriggerAbility", "AbilityName": {"Value": "StageB"},
    }]
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {"TargetType": "AllEnemy"}
    sources["abilities"]["StageB"] = {
        "Name": "StageB", "OnStart": [{
            "$type": "RPG.GameCore.DamageByAttackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            "AttackProperty": {
                "DamageType": {"DamageType": "Fire"},
                "DamagePercentage": _dynamic("AQAR", hashes=[dynamic_value_hash("Ratio")]),
                "StanceValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
            },
        }], "Modifiers": {},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    assert out["action"]["scaling"] == [{"atk": 1.5}]

    sources["abilities"]["A"]["OnStart"][1] = {
        "$type": "RPG.GameCore.TriggerParallelAbility",
        "ParallelAbilityList": [{
            "AbilityName": {"Value": "StageB"},
            "AbilityInherentTargetType": {
                "$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            "Delay": {"IsDynamic": False, "FixedValue": {"Value": 0}},
        }],
    }
    parallel = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert parallel["ok"] and not parallel["unsupported"], parallel["unsupported"]
    damage = next(effect for hook in parallel["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "deal_damage")
    assert damage["scaling_atk"] == 1.5

    for enemy_id in ("3004010", "8012040", "5014010"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.AddStageAbilityByName"
                       for item in real["unsupported"]), (enemy_id, real["unsupported"])
    sources["abilities"]["A"]["OnStart"].insert(0, {
        "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Ratio"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    sources["abilities"]["A"]["OnStart"][1]["DynamicValues"]["Ratio"] = _dynamic(
        "AQAR", hashes=[dynamic_value_hash("Ratio")])
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert any("仅支持静态持久参数" in item["reason"]
               for item in rejected["unsupported"])


def test_elation_be_target_resolves_created_battle_events():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Elation_BE"},
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "Mark"},
        }],
    }, modifiers={"Mark": {"BehaviorFlagList": ["Mark"]}})
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    spec = out["hooks"][0]["effects"][0]["target"]
    assert [child["pool"] for child in spec["concat"]] == [
        "unique:$battle_event:70001", "unique:$battle_event:70002"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    pool = {"concat": spec["concat"]}
    assert eng._hooks._hook_target_states(pool, source, {}) == []
    for index, event_id in enumerate((70001, 70002), 1):
        eng._hooks._run_hook_effect(source, {
            "effect_type": "create_battle_event", "event_id": event_id, "team": "neutral"}, {})
        targets = eng._hooks._hook_target_states(pool, source, {})
        assert len(targets) == index
        assert targets[-1].actor.actor_type == "battle_event"

    real = _real_compiler("5014010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.TargetAlias"
                   and "Elation_BE" in item["reason"] for item in real["unsupported"])


def test_target_query_deathrattle_selects_only_dead_actors():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetQuery", "AliveStateMask": "Bit_Deathrattle"},
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "Mark"},
        }],
    }, modifiers={"Mark": {"BehaviorFlagList": ["Mark"]}})
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    spec = out["hooks"][0]["effects"][0]["target"]
    assert spec["include_dead"] is True

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    assert eng._hooks._hook_target_states(spec, source, {}) == []
    hero.current_hp = 0
    eng._check_death(hero)
    assert [target.actor.actor_id for target in eng._hooks._hook_target_states(spec, source, {})] == ["hero"]

    real = _real_compiler("8012040").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.TargetQuery"
                   for item in real["unsupported"])


def test_fake_avatar_attack_flag_is_false_in_current_entity_model():
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    predicate = {"$type": "RPG.GameCore.ByContainsParamFlag", "Flag": "IsFakeAvatarAttack"}
    assert compiler._predicate_expr(predicate, ctx, "P") == "1 == 0"
    assert not ctx.unsupported
    assert compiler._predicate_expr({
        "$type": "RPG.GameCore.ByNot", "Predicate": predicate}, ctx, "P") == "not (1 == 0)"
    assert not ctx.unsupported

    real = _real_compiler("1003010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ByContainsParamFlag"
                   for item in real["unsupported"])


def test_set_action_delay_near_target_places_actor_after_reference():
    import math
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.SetActionDelayNearTarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "NearTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        "NearType": "After", "IsInit": True,
    })
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "set_action_delay" and "amount" not in effect

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source, hero = eng.state.actors["source"], eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, effect, {})
    source_delay = eng.scheduler._remaining[eng.scheduler.handle_of(source.actor.actor_id)]
    hero_delay = eng.scheduler._remaining[eng.scheduler.handle_of(hero.actor.actor_id)]
    assert source_delay == math.nextafter(hero_delay, math.inf)

    for enemy_id in ("3025010", "4013016", "4035010"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "RPG.GameCore.SetActionDelayNearTarget"
                       for item in real["unsupported"])


def test_control_skill_disable_reads_charm_flag():
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_charm_action")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByIsControlSkillDisable",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    }, ctx, "P")
    assert expression == "has_behavior_flag($self.actor_id, 'Charm')"
    assert not ctx.unsupported

    real = _real_compiler("2004010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ByIsControlSkillDisable"
                   for item in real["unsupported"])


def test_special_avatar_types_are_false_in_current_entity_model():
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    for special_type in ("TYPE_TRIAL", "TYPE_MISSION", "TYPE_PLOT"):
        ctx = _Context(mode="event", skill=skills[0], event="on_enter_battle")
        expression = compiler._predicate_expr({
            "$type": "RPG.GameCore.ByCompareSpecialAvatarType",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "CompareType": special_type,
        }, ctx, "P")
        assert expression == "1 == 0"
        assert not ctx.unsupported

    real = _real_compiler("4034020").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ByCompareSpecialAvatarType"
                   for item in real["unsupported"])


def test_character_fly_is_false_in_current_entity_model():
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_enter_battle")
    predicate = {"$type": "RPG.GameCore.ByCheckCharacterFly",
                 "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"}}
    assert compiler._predicate_expr(predicate, ctx, "P") == "1 == 0"
    assert not ctx.unsupported
    assert compiler._predicate_expr({
        "$type": "RPG.GameCore.ByNot", "Predicate": predicate}, ctx, "P") == "not (1 == 0)"

    real = _real_compiler("2022010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ByCheckCharacterFly"
                   for item in real["unsupported"])


def test_auto_ultra_skill_toggles_ultimate_action_lock():
    from hsr_nous.sim.resources import ultimate_available
    from hsr_nous.sim_schema.action import Action
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AutoUseUltraSkill",
        "Target": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "WaitCutinFinished": False, "Enable": False,
        "BindUltraSkillNames": ["Skill3_AsatPramad_00"],
    }, {
        "$type": "RPG.GameCore.AutoUseUltraSkill",
        "Target": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "WaitCutinFinished": False,
        "BindUltraSkillNames": ["Skill3_AsatPramad_00"],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [effect["effect_type"] for effect in effects] == ["apply_modifier", "remove_modifier"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    source.current_energy = 100
    ult = Action(action_id="ult", name="Ult", action_type="ultimate", target_type="single")
    eng._hooks._run_hook_effect(source, effects[0], {})
    assert not ultimate_available(source, ult)
    eng._hooks._run_hook_effect(source, effects[1], {})
    assert ultimate_available(source, ult)

    real = _real_compiler("8015030").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.AutoUseUltraSkill"
                   for item in real["unsupported"])


def test_native_dynamic_damage_scaling_runs_at_action_time():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import basic_action, engine_vs_dummy, make_dummy
    from dataclasses import replace

    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {"TargetType": "EnemySelect"}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "AttackProperty": {"DamageType": "Fire", "DamagePercentage": _dynamic(
            "AQAR", hashes=[dynamic_value_hash("_MaxStance")])},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["scaling"] == [{"atk": "dynamic_of($self.actor_id, '_MaxStance')"}]
    action = BuildCompiler()._compile_action_list([out["action"]], "dynamic")[0]

    def run(dynamic: bool) -> float:
        eng = engine_vs_dummy(enemies=[make_dummy("source", atk=100)],
                              actions={"source": [basic_action("placeholder")]})
        runtime = eng._enemy_policy_state.setdefault("source", {
            "current_phase": 1, "dynamic_values": {}})
        runtime["dynamic_values"]["_MaxStance"] = 2
        actual = action if dynamic else replace(action, scaling=[{"atk": 2.0}])
        eng._execute_action(eng.state.actors["source"], actual,
                            forced_target=eng.state.actors["hero"])
        return eng.state.actors["hero"].current_hp

    assert run(True) == run(False)


def test_native_dynamic_stance_value_runs_at_action_time():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy
    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {"TargetType": "EnemySelect"}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "AttackProperty": {"DamageType": "Fire", "DamagePercentage": {
            "IsDynamic": False, "FixedValue": {"Value": 0.5}},
            "StanceValue": _dynamic("AQAR", hashes=[dynamic_value_hash("_MaxStance")])},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["toughness_dmg"] == "dynamic_of($self.actor_id, '_MaxStance')"
    action = BuildCompiler()._compile_action_list([out["action"]], "stance")[0]
    eng = engine_vs_dummy()
    eng._enemy_policy_state.setdefault("hero", {
        "current_phase": 1, "dynamic_values": {"_MaxStance": 20}})
    target = eng.state.actors["e1"]
    initial = target.toughness
    eng._execute_action(eng.state.actors["hero"], action, forced_target=target)
    assert target.toughness == initial - 20


def test_repeated_identical_blast_segments_compile_as_multi_instance():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {
        "TargetType": "EnemySelect", "SubTargetType": "TargetAdjoinEntity"}
    sources["abilities"]["A"]["OnStart"] = []
    for _ in range(2):
        for alias in ("AbilityTargetEntity", "AbilityTargetAdjoinEntity"):
            sources["abilities"]["A"]["OnStart"].append({
                "$type": "RPG.GameCore.DamageByAttackProperty",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
                "AttackProperty": {"DamageType": "Fire", "DamagePercentage": {
                    "IsDynamic": False, "FixedValue": {"Value": 0.5}}},
            })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["instances"] == 2 and "scaling_blast" not in out["action"]
    action = BuildCompiler()._compile_action_list([out["action"]], "blast")[0]
    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    hits = []
    eng.bus.subscribe("after_being_hit", lambda event, payload, ctx: hits.append(payload))
    eng._execute_action(eng.state.actors["source"], action,
                        forced_target=eng.state.actors["hero"])
    assert [(hit["seg_index"], hit["target"]) for hit in hits] == [
        (0, "hero"), (0, "ally"), (1, "hero"), (1, "ally")]


def test_blast_instance_variants_override_each_segment():
    import math
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {
        "TargetType": "EnemySelect", "SubTargetType": "TargetAdjoinEntity"}
    sources["abilities"]["A"]["OnStart"] = []
    for blast_ratio in (0.25, 0.75):
        for alias, ratio in (("AbilityTargetEntity", 0.5),
                             ("AbilityTargetAdjoinEntity", blast_ratio)):
            sources["abilities"]["A"]["OnStart"].append({
                "$type": "RPG.GameCore.DamageByAttackProperty",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
                "AttackProperty": {"DamageType": "Fire", "DamagePercentage": {
                    "IsDynamic": False, "FixedValue": {"Value": ratio}}},
            })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert [variant["scaling_blast"][0]["atk"]
            for variant in out["action"]["instance_variants"]] == [0.25, 0.75]
    action = BuildCompiler()._compile_action_list([out["action"]], "blast_variants")[0]
    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    hits = []
    eng.bus.subscribe("after_being_hit", lambda event, payload, ctx: hits.append(payload))
    eng._execute_action(eng.state.actors["source"], action,
                        forced_target=eng.state.actors["hero"])
    adjacent = [hit["amount"] for hit in hits if hit["target"] == "ally"]
    assert math.isclose(adjacent[1], adjacent[0] * 3, rel_tol=1e-9)


def test_friendly_max_hp_damage_compiles_and_runs():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {"TargetType": "AllTeamMember"}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "AttackProperty": {"DamageType": "Fire", "FormulaType": "ByMaxHP",
                           "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.5}}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["scaling"] == [{"hp": 0.5}]
    action = BuildCompiler()._compile_action_list([out["action"]], "friendly_hp")[0]
    eng = engine_vs_dummy(enemies=[make_dummy("source", hp=100), make_dummy("partner", hp=200)])
    eng._execute_action(eng.state.actors["source"], action,
                        forced_target=eng.state.actors["source"])
    source_loss = 100 - eng.state.actors["source"].current_hp
    assert source_loss > 0
    assert eng.state.actors["partner"].current_hp == 200 - source_loss


def test_multi_segment_elements_use_instance_variants():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {"TargetType": "EnemySelect"}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "AttackProperty": {"DamageType": element, "DamagePercentage": {
            "IsDynamic": False, "FixedValue": {"Value": 0.5}}},
    } for element in ("Fire", "Thunder")]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert [variant.get("damage_type", out["action"]["damage_type"])
            for variant in out["action"]["instance_variants"]] == ["fire", "thunder"]
    action = BuildCompiler()._compile_action_list([out["action"]], "elements")[0]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    hits = []
    eng.bus.subscribe("after_being_hit", lambda event, payload, ctx: hits.append(payload))
    eng._execute_action(eng.state.actors["source"], action,
                        forced_target=eng.state.actors["hero"])
    assert [hit["damage_type"] for hit in hits] == ["fire", "thunder"]


def test_dynamic_apply_chance_uses_runtime_value():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Mark"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Chance": _dynamic("AQAR", hashes=[dynamic_value_hash("_MaxStance")]),
    }, modifiers={"Mark": {
        "BehaviorFlagList": ["RemoveWhenCasterDead"], "_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": -0.1}},
            }],
        }],
    }})
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["apply_chance"] == "dynamic_of($self.actor_id, '_MaxStance')"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    runtime = eng._enemy_policy_state.setdefault("source", {
        "current_phase": 1, "dynamic_values": {}})
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert "Mark" not in source.modifiers
    runtime["dynamic_values"]["_MaxStance"] = 1
    eng._hooks._run_hook_effect(source, effect, {})
    assert "Mark" in source.modifiers


def test_dynamic_modifier_duration_and_max_stack_bake_on_apply():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy
    raw = _dynamic("AQAR", hashes=[dynamic_value_hash("_MaxStance")])
    out = _task_skill({
        "$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Mark"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "LifeTime": raw, "MaxLayer": raw,
    }, modifiers={"Mark": {"BehaviorFlagList": ["RemoveWhenCasterDead"]}})
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["duration"] == "dynamic_of($self.actor_id, '_MaxStance')"
    assert effect["modifier"]["max_stack"] == "dynamic_of($self.actor_id, '_MaxStance')"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    runtime = eng._enemy_policy_state.setdefault("source", {
        "current_phase": 1, "dynamic_values": {"_MaxStance": 3}})
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.modifiers["Mark"].duration == 3
    assert source.modifiers["Mark"].max_stack == 3


def test_dynamic_energy_delta_splits_gain_and_consume():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "FixedAddValue": _dynamic("AQAR", hashes=[dynamic_value_hash("_MaxStance")]),
    })
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [effect["effect_type"] for effect in effects] == ["gain_energy", "consume_energy"]
    assert all(effect["amount"] == "abs(dynamic_of($self.actor_id, '_MaxStance'))"
               for effect in effects)
    eng = engine_vs_dummy(enemies=[make_dummy("source", max_energy=100)])
    source = eng.state.actors["source"]
    source.current_energy = 10
    runtime = eng._enemy_policy_state.setdefault("source", {
        "current_phase": 1, "dynamic_values": {"_MaxStance": 2}})
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert source.current_energy == 12
    runtime["dynamic_values"]["_MaxStance"] = -3
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert source.current_energy == 9


def test_dynamic_set_skill_point_uses_runtime_max_bp():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.ModifyTeamBoostPoint", "ModifyFunction": "Set",
        "ModifyValue": _dynamic("AQAR", hashes=[dynamic_value_hash("_MaxStance")]),
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "set_skill_point",
                      "amount": "dynamic_of($self.actor_id, '_MaxStance')"}
    eng = engine_vs_dummy(initial_sp=2)
    eng.state.sp_max_override = 6
    source = eng.state.actors["e1"]
    eng._enemy_policy_state.setdefault("e1", {
        "current_phase": 1, "dynamic_values": {"_MaxStance": 6}})
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng.state.skill_points == 6


def test_remove_modifier_by_multiple_behavior_flags_uses_union():
    from tests._builders import engine_vs_dummy, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.RemoveModifierByBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierBehaviorFlags": ["AttackSign", "TeamAction"],
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["filter"] == "('AttackSign' in $mod.behavior_flags or 'TeamAction' in $mod.behavior_flags)"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    for modifier_id, flags in (("Attack", ["AttackSign"]), ("Team", ["TeamAction"]),
                               ("Other", ["Other"])):
        eng._apply_modifier_spec(source, {
            "modifier_id": modifier_id, "modifier_type": "debuff", "duration": 0,
            "behavior_flags": flags}, source)
    eng._hooks._run_hook_effect(source, effect, {})
    assert set(source.modifiers) == {"Other"}


def test_mixed_behavior_flag_types_are_preserved_deterministically():
    out = _task_skill({
        "$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Mark"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }, modifiers={"Mark": {"BehaviorFlagList": ["RemoveWhenCasterDead", 148]}})
    assert out["ok"] and not out["unsupported"]
    modifier = out["hooks"][0]["effects"][0]["modifier"]
    assert modifier["behavior_flags"] == [148, "RemoveWhenCasterDead"]


def test_dot_snapshot_property_attack_uses_caster_snapshot():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    sources = get_enemy_ability_sources("1002050")
    import copy
    definition = copy.deepcopy(sources["modifiers"]["MCommon_DOT_Tear"])
    attack_reader = next(
        task for callback in definition["_CallbackList"] if callback["Event"] == "OnPhase1"
        for task in callback["CallbackConfig"]
        if task.get("$type") == "RPG.GameCore.SetDynamicValueByProperty"
        and task.get("Value") == "Attack")
    definition["_CallbackList"] = [{"Event": "OnPhase1", "CallbackConfig": [
        attack_reader,
        {"$type": "RPG.GameCore.DamageByAttackProperty", "AttackProperty": {
            "DamageType": "Physical", "DamagePercentage": _dynamic(
                "AQAR", hashes=[-561841936])}},
    ]}]
    skills = get_enemy_skills("1002050")
    compiler = AbilityCompiler("1002050", skills, sources)
    from hsr_nous.adapters.enemy_ability import _Context
    skill = next(item for item in skills if item["trigger_key"] == "Skill02")
    ctx = _Context(mode="action", skill=skill)
    add_task = next(
        task for ability in sources["abilities"].values()
        for task in ability.get("OnStart") or []
        if task.get("$type") == "RPG.GameCore.AddModifier"
        and (task.get("ModifierName") or {}).get("Value") == "MCommon_DOT_Tear")
    out = compiler._compile_dot("MCommon_DOT_Tear", add_task, definition, ctx, "tear")
    assert not ctx.unsupported
    assert out is not None and "$snapshot.atk" in out["dot_ratio_expr"]


def test_dot_conditional_damage_uses_snapshot_max_hp_cap():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim_schema.expression import evaluate, parse

    enemy_id = "3002030"
    name = "Monster_W2_Beast01_03_Bleed"
    sources = get_enemy_ability_sources(enemy_id)
    skills = get_enemy_skills(enemy_id)
    compiler = AbilityCompiler(enemy_id, skills, sources)
    skill = next(item for item in skills if item["trigger_key"] == "Skill02")
    add_task = next(
        task for ability in sources["abilities"].values() for task in ability.get("OnStart") or []
        if task.get("$type") == "RPG.GameCore.AddModifier"
        and (task.get("ModifierName") or {}).get("Value") == name)
    ctx = _Context(mode="action", skill=skill)
    out = compiler._compile_dot(name, add_task, sources["modifiers"][name], ctx, "bleed")
    assert not ctx.unsupported
    assert out is not None and "$snapshot.max_hp" in out["dot_ratio_expr"]
    prepared = parse(out["dot_ratio_expr"], layer="effect")
    for snapshot_hp, expected in ((100000.0, 500.0), (2.0, 200.0)):
        result = evaluate(prepared, context={
            "self": {"max_hp": 10000.0}, "snapshot": {"max_hp": snapshot_hp},
            "modifier": {"stacks": 2},
        })
        assert result.value == pytest.approx(expected)


def test_dot_on_create_snapshot_property_reads_event_source():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    enemy_id = "1002050"
    out = AbilityCompiler(
        enemy_id, get_enemy_skills(enemy_id), get_enemy_ability_sources(enemy_id),
    ).compile_skill("Skill02")
    assert not any("MDF_CasterAttack" in issue["reason"] for issue in out["unsupported"])
    spec = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("modifier_id") == "ENEMY_100205001_BLEED")
    effect = next(effect for effect in spec["on_apply"]
                  if effect.get("dynamic_key") == "MDF_CasterAttack")
    assert effect["amount"] == "stat_of($event.source, 'atk')"

    eng = engine_vs_dummy(enemies=[make_dummy(enemy_id, atk=321.0)])
    eng._hooks._run_hook_effect(eng.state.actors["hero"], effect, {"source": enemy_id})
    values = eng._enemy_policy_state["hero"]["dynamic_values"]
    assert values["MDF_CasterAttack"] == pytest.approx(321.0)


def test_compare_ability_action_delay_uses_scheduler_value():
    from tests._builders import engine_vs_dummy, make_dummy

    predicate = {
        "$type": "RPG.GameCore.ByCompareAbilityProperty", "Property": "ActionDelay",
        "CompareType": "Greater", "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0.4}},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    }
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "action_delay_of($self.actor_id) > 0.4" in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng.scheduler.set_action_delay(source.actor, 0.5)
    assert eng._expr.evaluate(eng._expr.compile(condition, layer="effect"),
                              eng._hooks._hook_ctx(source, {"actor": "source", "action_id": "s1"}),
                              functions=eng._hooks._hook_functions(source))


def test_compare_ability_property_accepts_dynamic_compare_value():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    predicate = {
        "$type": "RPG.GameCore.ByCompareAbilityProperty", "Property": "ActionDelay",
        "CompareType": "LessEqual",
        "CompareValue": _dynamic("AQAR", hashes=[dynamic_value_hash("CurrentActionDelay")]),
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    }
    compiler = AbilityCompiler("fake", [], {})
    ctx = _Context(mode="event", skill={}, event="on_turn_end", value_symbols={
        dynamic_value_hash("CurrentActionDelay"):
            "dynamic_of($self.actor_id, 'CurrentActionDelay')",
    })
    expression = compiler._predicate_expr(predicate, ctx, "test")
    assert expression == (
        "action_delay_of($self.actor_id) <= dynamic_of($self.actor_id, 'CurrentActionDelay')")
    assert not ctx.unsupported


def test_onstage_then_onstack_preserves_current_modifier_name():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Mark"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }]
    sources["modifiers"]["Mark"] = {"_CallbackList": [
        {"Event": "OnStage", "CallbackConfig": [{
            "$type": "RPG.GameCore.SetEffectAnimatorTrigger", "TriggerName": "Stage",
        }]},
        {"Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.PredicateTaskList", "Predicate": {
                "$type": "RPG.GameCore.ByCompareModifierValue", "ValueType": "Layer",
                "CompareType": "Equal", "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Seen"},
                "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
        }]},
    ]}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "stacks($self.actor_id, 'Mark') == 1" in str(out["hooks"])


def test_modifier_max_layer_read_and_get_summoner_target():
    from dataclasses import replace
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareModifierValue", "ValueType": "MaxLayer",
        "ModifierName": "Mark", "CompareType": "Equal",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 3}},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "modifier_max_stacks($self.actor_id, 'Mark') == 3" in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._apply_modifier_spec(source, {
        "modifier_id": "Mark", "modifier_type": "buff", "max_stack": 3}, source)
    assert eng._expr.evaluate(eng._expr.compile(condition, layer="effect"),
                              eng._hooks._hook_ctx(source, {"actor": "source", "action_id": "s1"}),
                              functions=eng._hooks._hook_functions(source))

    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByModifierValue", "DynamicKey": "MaxLayers",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity.GetSummoner"},
        "ModifierName": "Mark", "ValueType": "MaxLayer", "Multiplier": 1,
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert "modifier_max_stacks(summoner_of($self.actor_id), 'Mark')" in effect["amount"]
    eng = engine_vs_dummy(allies=[make_actor("owner")],
                          enemies=[replace(make_dummy("source"), summoner_id="owner")])
    owner = eng.state.actors["owner"]
    eng._apply_modifier_spec(owner, {
        "modifier_id": "Mark", "modifier_type": "buff", "max_stack": 3}, owner)
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["MaxLayers"] == 3.0


def test_listen_escape_and_action_end_use_existing_events():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    for event_name, engine_event in [("OnListenCharacterEscape", "actor_exit"),
                                     ("OnListenActionEnd", "on_action_end")]:
        skills, sources = _predicate_skill({})
        sources["abilities"]["A"]["OnStart"] = [{
            "$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Listener"},
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        }]
        sources["modifiers"]["Listener"] = {"_CallbackList": [{
            "Event": event_name, "CallbackConfig": [{
                "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Seen"},
                "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
        }]}
        out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
        assert out["ok"] and not out["unsupported"]
        hook = next(item for item in out["hooks"] if item["event"] == engine_event)
        eng = engine_vs_dummy(enemies=[make_dummy("listener"), make_dummy("other")])
        listener, other = eng.state.actors["listener"], eng.state.actors["other"]
        eng._compiled_hooks = [CompiledHook(
            owner_id="listener", event=engine_event,
            condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
            effects=hook["effects"])]
        eng._hooks._subscribe_compiled_hooks()
        if event_name == "OnListenCharacterEscape":
            eng.leave_actor("other", reason="flee")
        else:
            eng._execute_action(listener, basic_action())
        assert eng._enemy_policy_state["listener"]["dynamic_values"]["Seen"] == 1.0


@pytest.mark.parametrize("event_name", ["OnLimboWaitHeal", "OnBeingLimbo", "OnListenCharacterLimbo"])
def test_limbo_wait_heal_triggers_on_negative_hp_survival(event_name):
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Mark"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }]
    sources["modifiers"]["Mark"] = {"_CallbackList": [
        {"Event": "OnStack", "CallbackConfig": [{"$type": "RPG.GameCore.EnableNegativeHP"}]},
        {"Event": event_name, "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Limbo"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }]},
    ]}
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"]
    hook = next(item for item in out["hooks"] if item["event"] == "on_hp_decrease")
    assert "hp_of($event.target) <= 0" in hook["condition"]
    assert ("has_modifier($self.actor_id, 'Mark')" in hook["condition"]) == (
        event_name != "OnListenCharacterLimbo")

    eng = engine_vs_dummy(enemies=[make_dummy("source", hp=1)])
    source, hero = eng.state.actors["source"], eng.state.actors["hero"]
    mount = next(item for item in out["hooks"] if item["event"] == "on_battle_start")
    for effect in mount["effects"]:
        eng._hooks._run_hook_effect(source, effect, {})
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event="on_hp_decrease",
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    eng._execute_action(hero, basic_action(scaling=1.0), forced_target=source)
    assert source.alive and source.current_hp < 0
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Limbo"] == 1.0


def test_modifier_dynamic_values_read_applied_stacks_and_lifetime():
    from tests._builders import engine_vs_dummy, make_dummy

    name = "Monster_W1_Svarog_00_RL_AttackUp"
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": name},
        "LayerAddWhenStack": {"IsDynamic": False, "FixedValue": {"Value": 3}},
    }]
    sources["modifiers"] = {name: {
        "MaxLayer": 9,
        "_CallbackList": [{"Event": "OnCreate", "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValueByModifierValue",
            "ModifierName": name, "ValueType": "Layer",
            "Multiplier": {"IsDynamic": False, "FixedValue": {"Value": 2}},
            "DynamicKey": "AttackUpLayer",
        }]}],
    }}
    out = AbilityCompiler("1014011", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["on_apply"] == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "AttackUpLayer", "amount": f"2.0 * stacks($self.actor_id, '{name}')",
    }]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.modifiers[name].stacks == 3
    assert eng._enemy_policy_state["source"]["dynamic_values"]["AttackUpLayer"] == 6.0

    direct_task = dict(sources["modifiers"][name]["_CallbackList"][0]["CallbackConfig"][0])
    direct_task["Multiplier"] = {"IsDynamic": False, "FixedValue": {"Value": 1}}
    sources["abilities"]["A"]["OnStart"] = [direct_task]
    direct = AbilityCompiler("1014011", skills, sources).compile_skill("Skill01")
    assert direct["ok"] and not direct["unsupported"]
    direct_effect = direct["hooks"][0]["effects"][0]
    assert direct_effect["amount"] == f"stacks($self.actor_id, '{name}')"
    eng._hooks._run_hook_effect(source, direct_effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["AttackUpLayer"] == 3.0

    source.modifiers[name].duration = 5
    lifetime_task = dict(direct_task)
    lifetime_task["ValueType"] = "LifeTime"
    lifetime_task["ReadTargetType"] = {
        "$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity",
    }
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "TaskList": [lifetime_task],
    }]
    lifetime = AbilityCompiler("8003011", skills, sources).compile_skill("Skill01")
    assert lifetime["ok"] and not lifetime["unsupported"]
    lifetime_effect = lifetime["hooks"][0]["effects"][0]
    assert lifetime_effect["amount"] == f"modifier_duration($target, '{name}')"
    assert lifetime_effect["amount_target"] == {"pool": "enemies"}
    eng._hooks._run_hook_effect(source, lifetime_effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["AttackUpLayer"] == 5.0

    sources["abilities"]["A"]["OnStart"] = [direct_task]
    sources["modifiers"][name]["BehaviorFlagList"] = ["STAT_DOT"]
    rejected = AbilityCompiler("1014011", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("跨技能 DoT 数值读取未能绑定来源技能" in issue["reason"]
               for issue in rejected["unsupported"])


def test_layer_add_when_stack_evaluates_dynamic_stacks_on_apply():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DefineDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "DynamicKey": {"Value": "CurrentLayers"},
        "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 3}},
    }, {
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "StackingBuff"},
        "LayerAddWhenStack": _dynamic(
            "AQAR", hashes=[dynamic_value_hash("CurrentLayers")]),
    }]
    sources["modifiers"] = {"StackingBuff": {
        "MaxLayer": 9,
        "_CallbackList": [{"Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
        }]}],
    }}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    apply = next(effect for effect in effects if effect["effect_type"] == "apply_modifier")
    assert apply["modifier"]["stacks"] == "dynamic_of($self.actor_id, 'CurrentLayers')"
    BuildCompiler()._validate_effects([apply], "动态层数测试")
    eng = engine_vs_dummy()
    for effect in effects:
        eng._hooks._run_hook_effect(eng.state.actors["e1"], effect, {})
    assert eng.state.actors["e1"].modifiers["StackingBuff"].stacks == 3


def test_default_layer_add_reserved_hash():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "StackingBuff"},
    }]
    sources["modifiers"] = {"StackingBuff": {
        "MaxLayer": 5,
        "LayerAddWhenStack": _dynamic("AQAR", hashes=[-797864550]),
        "_CallbackList": [{"Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
        }]}],
    }}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    modifier = out["hooks"][0]["effects"][0]["modifier"]
    assert modifier["stacks"] == 1 and modifier["max_stack"] == 5

    sources["modifiers"]["StackingBuff"]["LayerAddWhenStack"] = _dynamic("AQAR", hashes=[-1])
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("未知 DynamicHash：-1" in issue["reason"] for issue in rejected["unsupported"])


def test_onstack_dynamic_value_feeds_resistance_delta():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "IceBuff"},
        "DynamicValues": {"MDF_IceResistanceRatio_PerLayer": {
            "IsDynamic": False, "FixedValue": {"Value": 0.05}}},
    }]
    sources["modifiers"] = {"IceBuff": {
        "MaxLayer": 4, "LayerAddWhenStack": 2,
        "_CallbackList": [{"Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValueByModifierValue",
            "ValueType": "Layer", "DynamicKey": "ModifierLayers",
        }, {
            "$type": "RPG.GameCore.SetDynamicValue",
            "DynamicKey": {"Value": "MDF_IceResistanceRatio"},
            "Value": _dynamic("AQABAQQR", hashes=[
                dynamic_value_hash("MDF_IceResistanceRatio_PerLayer"),
                dynamic_value_hash("ModifierLayers")]),
        }, {
            "$type": "RPG.GameCore.StackProperty", "Property": "IceResistanceDelta",
            "PropertyValue": _dynamic("AQAR", hashes=[
                dynamic_value_hash("MDF_IceResistanceRatio")]),
        }]}],
    }}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["stat_exprs"]["res_ice"] == "0.05 * max(1, $modifier.stacks)"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.modifiers["IceBuff"].stacks == 2
    assert eng.pipeline.effective_stats(source)["res_ice"] == pytest.approx(0.1)


def test_dot_onstack_modifier_layers_feed_damage_value():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Burn"},
    }]
    sources["modifiers"] = {"Burn": {
        "BehaviorFlagList": ["STAT_DOT", "STAT_DOT_Fire"], "LayerAddWhenStack": 2,
        "_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.SetDynamicValueByModifierValue",
                "ValueType": "Layer", "DynamicKey": "ModifierLayers",
            }],
        }, {
            "Event": "OnPhase1", "CallbackConfig": [{
                "$type": "RPG.GameCore.DamageByAttackProperty",
                "AttackProperty": {"DamageType": "Fire", "DamageValue": _dynamic(
                    "AQAR", hashes=[dynamic_value_hash("ModifierLayers")])},
            }],
        }],
    }}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    spec = out["hooks"][0]["effects"][0]["modifier"]
    assert spec["dot_ratio_expr"] == "max(1, $modifier.stacks)"


@pytest.mark.parametrize(("alias", "expected"), [
    ("LevelEntity", "$level"),
    ("CasterSummoner", "summoner_of($self.actor_id)"),
    ("CasterSummonedMinions", {
        "pool": "enemies", "where": "$it.summoner_id == $self.actor_id"}),
])
def test_dynamic_write_preserves_enemy_side_target(alias, expected):
    from tests._builders import engine_vs_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DefineDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "DynamicKey": {"Value": "Seen"},
        "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == expected

    if alias == "LevelEntity":
        eng = engine_vs_dummy()
        source = eng.state.actors["e1"]
        eng._hooks._run_hook_effect(source, effect, {})
        assert eng._enemy_policy_state["$level"]["dynamic_values"]["Seen"] == 1
        assert "Seen" not in eng._enemy_policy_state.get("e1", {}).get("dynamic_values", {})


def test_set_dynamic_value_enemy_pool_and_battle_event():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["target_aliases"] = {"EnemyPool": {
        "$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"}}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
        "DynamicKey": {"Value": "TeamFlag"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }, {
        "$type": "RPG.GameCore.SetDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "EnemyPool"},
        "DynamicKey": {"Value": "PoolFlag"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }, {
        "$type": "RPG.GameCore.SetDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "BattleEvent_20034"},
        "DynamicKey": {"Value": "_SelectTimes"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    team_effect, pool_effect, event_effect = out["hooks"][0]["effects"]
    assert team_effect["target"] == "all_enemies"
    assert pool_effect["target"] == {"pool": "enemies"}
    assert event_effect["target"] == {"pool": "unique:$battle_event:20034"}

    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("partner")])
    source = eng.state.actors["source"]
    for effect in (team_effect, pool_effect):
        eng._hooks._run_hook_effect(source, effect, {})
    for actor_id in ("source", "partner"):
        values = eng._enemy_policy_state[actor_id]["dynamic_values"]
        assert values["TeamFlag"] == 1 and values["PoolFlag"] == 1
    eng._hooks._run_hook_effect(source, {
        "effect_type": "create_battle_event", "event_id": 20034, "team": "TeamNeutral"}, {})
    eng._hooks._run_hook_effect(source, event_effect, {})
    assert eng._hooks._hook_amount(
        "dynamic_of(unique_target('$battle_event:20034'), '_SelectTimes')", source, {}) == 1


def test_property_value_reads_modifier_owner_summoner_action_delay():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByProperty",
        "DynamicKey": "_ActionDelaySummoner",
        "ReadTargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerSummoner"},
        "Value": "ActionDelay",
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["amount"] == \
        "action_delay_of(summoner_of($self.actor_id))"


def test_self_dynamic_value_reads_runtime_value():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValue",
        "DynamicKey": {"Value": "X"},
        "Value": {"IsDynamic": True, "PostfixExpr": {
            "OpCodes": "AQAR", "FixedValues": [], "DynamicHashes": [dynamic_value_hash("X")],
        }},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount"] == "dynamic_of($self.actor_id, 'X')"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    runtime = eng._enemy_policy_state.setdefault("source", {
        "seq_idx": 0, "cooldown_left": {}, "current_phase": 1, "dynamic_values": {},
    })
    runtime["dynamic_values"]["X"] = 4.0
    eng._hooks._run_hook_effect(source, effect, {})
    assert runtime["dynamic_values"]["X"] == 4.0


def test_modifier_value_default_count_is_presence_not_layers():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    name = "MMonster_SW_Boss_01_IF_SwarmArmor"
    out = _task_skill({
        "$type": "RPG.GameCore.SetDynamicValueByModifierValue",
        "ModifierName": name,
        "Multiplier": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        "DynamicKey": "ArmorCount",
    }, modifiers={name: {"MaxLayer": 9}})
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount"] == f"has_modifier($self.actor_id, '{name}')"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["ArmorCount"] == 0.0
    eng._apply_modifier(source, Modifier(
        modifier_id=name, name=name, modifier_type="buff", stacks=3))
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["ArmorCount"] == 1.0


def test_modifier_value_event_summoner_and_global_alias_targets():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    from hsr_nous.adapters.enemy_ability import _Context

    name = "Marker"
    alias = "Monster_W4_Nikadory_00_Self"
    skills, sources = _predicate_skill({})
    sources["target_aliases"] = {alias: {
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 405301}},
            }},
        ],
    }}
    sources["modifiers"] = {name: {}}
    compiler = AbilityCompiler("fake", skills, sources)
    for alias_name, event, key in (("ParamEntity", "after_being_hit", "event_count"),
                                   (alias, "on_action", "named_count"),
                                   ("ParamEntitySummoner", "actor_enter", "owner_count")):
        ctx = _Context(mode="event", skill=skills[0], event=event)
        compiler._compile_modifier_value({
            "$type": "RPG.GameCore.SetDynamicValueByModifierValue",
            "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias_name},
            "ModifierName": name, "ValueType": "Layer",
            "Multiplier": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            "DynamicKey": key,
        }, ctx, "modifier_value", ())
        assert not ctx.unsupported
        if alias_name == "ParamEntity":
            event_effect = ctx.effects[0]
        elif alias_name == alias:
            named_effect = ctx.effects[0]
        else:
            owner_effect = ctx.effects[0]

    assert event_effect["amount"] == f"stacks($event.target, '{name}')"
    assert "amount_target" not in event_effect
    assert named_effect["amount"] == f"stacks($target, '{name}')"
    assert named_effect["amount_target"] == {
        "pool": "enemies", "where": "monster_unique_id($it) == 405301"}
    assert owner_effect["amount"] == f"stacks(summoner_of($event.actor), '{name}')"

    eng = engine_vs_dummy(allies=[make_actor("hero")], enemies=[
        make_dummy("4053010"), make_dummy("owner"), make_dummy("source")])
    eng.state.actors["source"].actor.summoner_id = "owner"
    eng._apply_modifier(eng.state.actors["hero"], Modifier(
        modifier_id=name, name=name, modifier_type="buff", stacks=3))
    eng._apply_modifier(eng.state.actors["4053010"], Modifier(
        modifier_id=name, name=name, modifier_type="buff", stacks=4))
    eng._apply_modifier(eng.state.actors["owner"], Modifier(
        modifier_id=name, name=name, modifier_type="buff", stacks=5))
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, event_effect, {"target": "hero"})
    eng._hooks._run_hook_effect(source, named_effect, {})
    eng._hooks._run_hook_effect(source, owner_effect, {"actor": "source"})
    values = eng._enemy_policy_state["source"]["dynamic_values"]
    assert values == {"event_count": 3.0, "named_count": 4.0, "owner_count": 5.0}


def test_dynamic_add_twice_and_write_read_compiles_live():
    def add_task(key, value):
        return {
            "$type": "RPG.GameCore.SetDynamicValueByAddValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "Key": {"Value": key},
            "AddValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
        }

    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.DefineDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "X"},
            "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }, add_task("X", 1), add_task("X", 1), {
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareDynamicValue",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
                "DynamicKey": {"Value": "X"}, "CompareType": "Equal",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "ModifierName": {"Value": "Buff"},
            }],
        }]}},
        "modifiers": {"Buff": {"_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    assert effects[3]["effect_type"] == "apply_modifier"
    assert effects[3]["condition"] == "dynamic_of($event.target, 'X') == 1"

    sources["abilities"]["A"]["OnStart"] = sources["abilities"]["A"]["OnStart"][:3]
    accepted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert accepted["ok"] and not accepted["unsupported"]
    amounts = [effect["amount"] for hook in accepted["hooks"] for effect in hook["effects"]
               if effect["effect_type"] == "set_dynamic_value"]
    assert amounts == [1, "dynamic_of($self, 'X') + (1)", "dynamic_of($self, 'X') + (1)"]


def test_dynamic_add_level_entity_uses_level_dynamic_values():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByAddValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LevelEntity"},
        "Key": {"Value": "X"},
        "AddValue": {"IsDynamic": False, "FixedValue": {"Value": 5}},
        "Min": {"IsDynamic": False, "FixedValue": {"Value": 0}},
        "Max": {"IsDynamic": False, "FixedValue": {"Value": 10}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {
        "effect_type": "set_dynamic_value", "target": "$level", "dynamic_key": "X",
        "amount": "min(max(dynamic_of($level, 'X') + (5), (0)), (10))"}

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    runtime = eng._enemy_policy_state.setdefault("$level", {
        "seq_idx": 0, "cooldown_left": {}, "current_phase": 1, "dynamic_values": {}})
    runtime["dynamic_values"]["X"] = 3.0
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert runtime["dynamic_values"]["X"] == 8.0
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert runtime["dynamic_values"]["X"] == 10.0


def test_dynamic_add_summoner_and_target_algebra():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByAddValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummoner"},
        "Key": {"Value": "X"},
        "AddValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == {
        "pool": "all", "where": "$it.actor_id == summoner_of($self.actor_id)"}
    assert effect["amount"] == "dynamic_of($target, 'X') + (2)"

    sources["target_aliases"] = {"Group": {
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 405301}},
            }},
        ],
    }}
    sources["abilities"]["A"]["OnStart"][0]["TargetType"]["Alias"] = "Group"
    sources["abilities"]["A"]["OnStart"][0]["Key"]["Value"] = "Y"
    sources["abilities"]["A"]["OnStart"][0]["AddValue"]["FixedValue"]["Value"] = 4
    selected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert selected["ok"] and not selected["unsupported"]
    selected_effect = selected["hooks"][0]["effects"][0]
    assert selected_effect["amount"] == "dynamic_of($target, 'Y') + (4)"

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("owner"),
        make_dummy("4053010"), make_dummy("4053020")])
    eng.state.actors["source"].actor.summoner_id = "owner"
    for actor_id in ("owner", "4053010"):
        eng._enemy_policy_state[actor_id] = {
            "seq_idx": 0, "cooldown_left": {}, "current_phase": 1,
            "dynamic_values": {"X": 3.0, "Y": 1.0}}
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    eng._hooks._run_hook_effect(source, selected_effect, {})
    assert eng._enemy_policy_state["owner"]["dynamic_values"]["X"] == 5.0
    assert eng._enemy_policy_state["4053010"]["dynamic_values"]["Y"] == 5.0


def test_conditional_and_unconditional_writes_keep_task_order():
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.DefineDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "X"},
            "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
        }, {
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "TargetMonsterID": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "X",
                "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "Value": "BaseAttack",
            }],
        }, {
            "$type": "RPG.GameCore.DefineDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "X"},
            "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("1", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    amounts = [effect["amount"] for hook in out["hooks"] for effect in hook["effects"]
               if effect["effect_type"] == "set_dynamic_value"]
    assert amounts == [0, "base_stat_of($self.actor_id, 'atk')", 2]


def test_abort_behavior_flag_survives_identical_branch_merge():
    damage = {
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "AttackProperty": {
            "DamageType": {"DamageType": "Fire"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 2.0}},
            "SPHitRatio": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        },
    }
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "AllEnemy"}, "EntryAbility": "A",
        }]},
        "abilities": {
            "A": {"Name": "A", "OnStart": [{
                "$type": "RPG.GameCore.TriggerAbility", "AbilityName": {"Value": "B"},
                "AbortBehaviorFlags": ["Break"],
            }]},
            "B": {"Name": "B", "OnStart": [{
                "$type": "RPG.GameCore.PredicateTaskList",
                "Predicate": {
                    "$type": "RPG.GameCore.ByCompareMonsterID",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                    "TargetMonsterID": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                },
                "SuccessTaskList": [damage], "FailedTaskList": [damage],
            }]},
        },
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "damage_type": "Fire",
               "sp_hit_base": 10, "param_list": [2.0]}]
    out = AbilityCompiler("1", skills, sources).compile_skill("Skill01")
    # 原始恒等分支只结算一次，但外层 Ability 的中止条件不能随合并丢失。
    assert out["ok"], out["unsupported"]
    conditional = [h for h in out["hooks"]
                   if any(e["effect_type"] == "deal_damage" for e in h["effects"])]
    assert len(conditional) == 1
    assert "not broken_of($self.actor_id)" in conditional[0]["condition"]


def test_conditional_damage_preserves_target_sequence():
    damage = {
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByIsContainModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "Mark"},
            }},
        ]},
        "AttackProperty": {
            "DamageType": {"DamageType": "Fire"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 2.0}},
            "SPHitRatio": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        },
    }
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "AllEnemy"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "TargetMonsterID": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            },
            "SuccessTaskList": [damage],
        }]}},
        "modifiers": {"Mark": {}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "damage_type": "Fire",
               "sp_hit_base": 10, "param_list": [2.0]}]
    out = AbilityCompiler("1", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "deal_damage")
    assert effect["target"] == {"pool": "allies", "where": "has_modifier($it, 'Mark')"}


def test_skill_param_switch_selects_static_case():
    def remove(name):
        return {
            "$type": "RPG.GameCore.RemoveModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": name},
        }

    sources = {
        "character_config": {
            "SkillList": [{
                "Name": "Skill01", "SkillType": "Skill",
                "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
            }],
            "DynamicValues": {"Floats": {"7": {"ReadInfo": {
                "Type": "SkillParam", "TriggerKey": "Skill01", "Index": 0,
            }}}},
        },
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.SwitchCaseByDynamicValue",
            "Switch": _dynamic("AQAR", hashes=[7]),
            "CaseTaskList": [
                {"Case": {"IsDynamic": False, "FixedValue": {"Value": 0}},
                 "TaskList": [remove("A")]},
                {"Case": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                 "TaskList": [remove("B")]},
            ],
            "DefaultTaskList": [remove("C")],
        }]}},
        "modifiers": {"A": {}, "B": {}, "C": {}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": [1]}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "remove_modifier", "target": "self", "modifier_id": "B",
    }]

    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    # 可变 CustomValue（生成期被 config_ai 写）→ 活读翻译：各 Case 效果带
    # dynamic_of 等值守卫，Default 带全不等守卫（#26 期 2/3）。
    sources["custom_values"] = {"X": 0}
    sources["abilities"]["A"]["OnStart"][0]["Switch"] = _dynamic(
        "AQAR", hashes=[dynamic_value_hash("X")])
    sources["config_ai"] = {
        "$type": "RPG.GameCore.SetDynamicValueByHPRatio", "DynamicKey": {"Value": "X"},
    }
    translated = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert translated["ok"] and not translated["unsupported"], translated["unsupported"]
    effects = translated["hooks"][0]["effects"]
    assert [effect["modifier_id"] for effect in effects] == ["A", "B", "C"]
    assert effects[0]["condition"] == "dynamic_of($self, 'X') == 0"
    assert effects[1]["condition"] == "dynamic_of($self, 'X') == 1"
    assert effects[2]["condition"] == (
        "dynamic_of($self, 'X') != 0 and dynamic_of($self, 'X') != 1")

    sources["custom_values"] = {"U1zRkAF7AV": 0}
    sources["abilities"]["A"]["OnStart"][0]["Switch"] = _dynamic(
        "AQAR", hashes=[dynamic_value_hash("U1zRkAF7AV")])
    sources["config_ai"] = {
        "$type": "RPG.GameCore.SetDynamicValueByCopying",
        "FromDynamicKey": {"Value": "A5zSTRyo3j"}, "ToDynamicKey": {"Value": "Other"},
    }
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("哈希命名空间冲突" in item["reason"] for item in rejected["unsupported"])


def test_projectile_direct_hit_and_supported_hit_tasks():
    damage = {
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ProjectileHitEntity"},
        "AttackProperty": {
            "DamageType": {"DamageType": "Physical"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 1.5}},
            "SPHitRatio": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        },
    }
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "EnemySelect"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.FireProjectile",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
            "OnProjectileHit": [damage],
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "damage_type": "Physical",
               "sp_hit_base": 10, "param_list": [1.5]}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["scaling"] == [{"atk": 1.5}]

    projectile = sources["abilities"]["A"]["OnStart"][0]
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
        "TaskList": [projectile],
    }]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("Retarget 内投射物" in item["reason"] for item in rejected["unsupported"])

    sources["abilities"]["A"]["OnStart"] = [projectile]
    sources["abilities"]["A"]["OnStart"][0]["OnProjectileHit"].append({
        "$type": "RPG.GameCore.DefineDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "DynamicKey": {"Value": "X"},
        "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    accepted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert accepted["ok"] and not accepted["unsupported"]
    assert any(effect["effect_type"] == "set_dynamic_value"
               for hook in accepted["hooks"] for effect in hook["effects"])


def test_new_fire_projectile_reuses_hit_compiler():
    damage = {
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ProjectileHitEntity"},
        "AttackProperty": {
            "DamageType": {"DamageType": "Quantum"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 1.5}},
            "SPHitRatio": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        },
    }
    task = {
        "$type": "RPG.GameCore.NewFireProjectile",
        "MaxNumber": 1,
        "NewProjectile": {"$type": "RPG.GameCore.LinearProjectileData"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "OnProjectileHit": [damage],
    }
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "EnemySelect"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [task]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "damage_type": "Quantum",
               "sp_hit_base": 10, "param_list": [1.5]}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["scaling"] == [{"atk": 1.5}]

    task["OnProjectileHit"] = [{
        "$type": "RPG.GameCore.RemoveEffect", "EffectPath": "Effects/Ball",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }]
    presentation = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not any(issue["node_type"] == "RPG.GameCore.NewFireProjectile"
                   for issue in presentation["unsupported"])
    task["OnProjectileHit"] = []
    empty = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not any(issue["node_type"] == "RPG.GameCore.NewFireProjectile"
                   for issue in empty["unsupported"])


def test_new_fire_projectile_allows_single_retarget_only():
    damage = {
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ProjectileHitEntity"},
        "AttackProperty": {
            "DamageType": {"DamageType": "Quantum"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 1.5}},
            "SPHitRatio": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        },
    }
    projectile = {
        "$type": "RPG.GameCore.NewFireProjectile",
        "NewProjectile": {"$type": "RPG.GameCore.ParabolaProjectileData"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "OnProjectileHit": [damage],
    }
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "EnemySelect"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.Retarget",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            "ByRandom": True,
            "MaxNumber": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            "TaskList": [projectile],
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "damage_type": "Quantum",
               "sp_hit_base": 10, "param_list": [1.5]}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "deal_damage")
    assert effect["target"]["pool"] == "allies" and effect["target"]["take"] == 1

    del sources["abilities"]["A"]["OnStart"][0]["ByRandom"]
    del sources["abilities"]["A"]["OnStart"][0]["MaxNumber"]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("Retarget 内投射物主目标未证明" in issue["reason"]
               for issue in rejected["unsupported"])


def test_fire_projectile_caster_targets_self():
    damage = {
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ProjectileHitEntity"},
        "AttackProperty": {
            "DamageType": {"DamageType": "Fire"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 1.0}},
            "SPHitRatio": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        },
    }
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "EnemySelect"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.FireProjectile",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "OnProjectileHit": [damage],
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "damage_type": "Fire",
               "sp_hit_base": 10, "param_list": [1.0]}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "deal_damage")
    assert effect["target"] == {"pool": "self"}


def test_exit_break_and_default_reset_stance_pair():
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [
            {"$type": "RPG.GameCore.ExitBreakState",
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}},
            {"$type": "RPG.GameCore.ResetStance",
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}},
        ]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "restore_toughness", "target": "self",
    }]

    sources["abilities"]["A"]["OnStart"] = [sources["abilities"]["A"]["OnStart"][1]]
    independent = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert independent["ok"] and not independent["unsupported"]
    assert independent["hooks"][0]["effects"] == [{
        "effect_type": "reset_stance", "target": "self",
    }]

    sources["abilities"]["A"]["OnStart"][0]["ConstantValue"] = {
        "IsDynamic": False, "FixedValue": {"Value": 2}}
    custom = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert custom["ok"] and custom["hooks"][0]["effects"] == [{
        "effect_type": "reset_stance", "target": "self", "mode": "set", "amount": 2.0,
    }]

    reset_task = sources["abilities"]["A"]["OnStart"][0]
    del reset_task["ConstantValue"]
    reset_task["AddValue"] = {"IsDynamic": False, "FixedValue": {"Value": 30}}
    added = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert added["ok"] and added["hooks"][0]["effects"] == [{
        "effect_type": "reset_stance", "target": "self", "mode": "add", "amount": 30.0,
    }]

    reset_task["ForbidWhenEmpty"] = True
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("ForbidWhenEmpty=true" in item["reason"] for item in rejected["unsupported"])


def test_independent_exit_break_and_reset_stance_in_engine():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ExitBreakState",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and out["hooks"][0]["effects"] == [{
        "effect_type": "exit_break_state", "target": "self"}]

    eng = engine_vs_dummy(enemies=[make_dummy("source", max_toughness=120)])
    st = eng.state.actors["source"]
    st.broken = True
    st.bar_index = 1
    st.toughness = 0
    eng._hooks._run_hook_effect(st, out["hooks"][0]["effects"][0], {})
    assert not st.broken and st.bar_index == 1 and st.toughness == 0

    st.broken = True
    eng._hooks._run_hook_effect(st, {"effect_type": "reset_stance", "target": "self"}, {})
    assert st.broken and st.bar_index == 0 and st.toughness == 120

    st.toughness = 80
    eng._hooks._run_hook_effect(st, {
        "effect_type": "reset_stance", "target": "self", "mode": "set", "amount": 60}, {})
    assert st.broken and st.toughness == 60
    eng._hooks._run_hook_effect(st, {
        "effect_type": "reset_stance", "target": "self", "mode": "add", "amount": 50}, {})
    assert st.toughness == 110
    eng._hooks._run_hook_effect(st, {
        "effect_type": "reset_stance", "target": "self", "mode": "add", "amount": 200}, {})
    assert st.toughness == 120


def test_on_stack_reset_stance_uses_add_modifier_inline_symbols():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Buff"},
        "DynamicValues": {
            "Ratio": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        },
    }]
    sources["modifiers"] = {"Buff": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
        }, {
            "$type": "RPG.GameCore.SetDynamicValueByProperty",
            "DynamicKey": "_MaxStance",
            "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "Value": "MaxStance",
        }, {
            "$type": "RPG.GameCore.ResetStance",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "AddValue": _dynamic("AQABAQQR", hashes=[
                dynamic_value_hash("_MaxStance"), dynamic_value_hash("Ratio")]),
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    resets = [effect for hook in out["hooks"] for effect in hook["effects"]
              if effect["effect_type"] == "reset_stance"]
    assert len(resets) == 1
    assert resets[0]["mode"] == "add" and resets[0]["target"] == "self"
    assert "_MaxStance" in resets[0]["amount"] and "0.5" in resets[0]["amount"]


def test_stance_vulnerable_toggles_toughness_lock():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [
        {"$type": "RPG.GameCore.SetMonsterStanceVulnerable", "IsVulnerable": False},
        {"$type": "RPG.GameCore.SetMonsterStanceVulnerable"},
    ]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[0]["effect_type"] == "apply_modifier"
    assert effects[0]["modifier"]["toughness_lock"] is True
    assert effects[1] == {
        "effect_type": "remove_modifier", "target": "self",
        "modifier_id": "ENEMY_s1_TOUGHNESS_LOCK", "reason": "stance_vulnerable",
    }
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    st = eng.state.actors["source"]
    for effect in effects[:1]:
        eng._hooks._run_hook_effect(st, effect, {})
    assert "ENEMY_s1_TOUGHNESS_LOCK" in st.modifiers
    eng._hooks._run_hook_effect(st, effects[1], {})
    assert "ENEMY_s1_TOUGHNESS_LOCK" not in st.modifiers


def test_lock_stance_zero_ratio_blocks_toughness_damage():
    from tests._builders import engine_vs_dummy, make_dummy

    task = {
        "$type": "RPG.GameCore.LockStance",
        "StanceValueRatio": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == "self"
    assert effect["modifier"]["toughness_lock"] is True

    eng = engine_vs_dummy(enemies=[make_dummy("source", max_toughness=120)])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    eng._hooks._run_hook_effect(source, {
        "effect_type": "reduce_toughness", "target": "self", "amount": 30}, {})
    assert source.toughness == 120


def test_on_stack_lock_stance_marks_containing_modifier():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Lock"},
    }]
    sources["modifiers"]["Lock"] = {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.LockStance",
            "StanceValueRatio": {"IsDynamic": False, "FixedValue": {"Value": 0}},
        }],
    }]}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    apply = out["hooks"][0]["effects"][0]
    assert apply["modifier"]["toughness_lock"] is True
    assert "on_apply" not in apply["modifier"]

    sources["modifiers"]["Lock"]["_CallbackList"][0]["CallbackConfig"][0][
        "StanceValueRatio"]["FixedValue"]["Value"] = 1
    restored = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert restored["ok"] and not restored["unsupported"]
    assert any(effect["effect_type"] == "reset_stance"
               for hook in restored["hooks"] for effect in hook["effects"])


@pytest.mark.skipif(not (enemy_data_available() and enemy_ability_available()),
                    reason="真实敌人 Ability 数据缺失")
def test_lock_stance_full_ratio_restores_without_exiting_break():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.LockStance",
        "StanceValueRatio": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [effect["effect_type"] for effect in effects] == [
        "reset_stance", "apply_modifier"]

    eng = engine_vs_dummy(enemies=[make_dummy("source", max_toughness=120)])
    source = eng.state.actors["source"]
    source.toughness = 30
    source.broken = True
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert source.toughness == 120 and source.broken
    eng._hooks._run_hook_effect(source, {
        "effect_type": "reduce_toughness", "target": "self", "amount": 30}, {})
    assert source.toughness == 120

    rejected = _task_skill({
        "$type": "RPG.GameCore.LockStance",
        "StanceValueRatio": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
    })
    assert not rejected["ok"]
    real = _real_compiler("4034013").compile_enemy()
    assert not any("非零比例" in issue["reason"] or "满值恢复" in issue["reason"]
                   for issue in real["unsupported"])


def test_init_shield_flat_and_hp_ratio_in_engine():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.InitShield",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ShieldValue": {"IsDynamic": False, "FixedValue": {"Value": 500}},
        "FormulaType": "ShieldByCasterMaxHP",
        "ShieldPercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["shield"] == {"flat": 500.0, "scaling": {"hp": 0.1}}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(hero, effect, {})
    assert hero.shields[0].remaining == pytest.approx(1000.0)


def test_on_create_init_shield_uses_inline_dynamic_value():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Buff"},
        "DynamicValues": {
            "MDF_ShowValue": {"IsDynamic": False, "FixedValue": {"Value": 500}},
        },
    }]
    sources["modifiers"] = {"Buff": {"_CallbackList": [{
        "Event": "OnCreate", "CallbackConfig": [{
            "$type": "RPG.GameCore.InitShield",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "ShieldValue": _dynamic("AQAR", hashes=[dynamic_value_hash("MDF_ShowValue")]),
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    apply = out["hooks"][0]["effects"][0]
    shield_effect = apply["modifier"]["on_apply"][0]
    assert shield_effect["modifier"]["shield"]["flat"] == 500.0


def test_event_retarget_damage_does_not_leak_action_assembly_records():
    from tests._builders import engine_vs_dummy, make_dummy

    damage = {
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "AttackProperty": {
            "DamageType": {"DamageType": "Fire"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
            "SPHitRatio": {"IsDynamic": False, "FixedValue": {"Value": 0}},
        },
    }
    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Listener"},
        }]}},
        "modifiers": {"Listener": {"_CallbackList": [{
            "Event": "OnAfterHit",
            "CallbackConfig": [{
                "$type": "RPG.GameCore.Retarget",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
                "TaskList": [damage],
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "deal_damage")
    assert effect["target"] == {"pool": "allies"}
    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    before = hero.current_hp
    eng._hooks._run_hook_effect(source, effect, {"source": "source", "target": "hero"})
    assert hero.current_hp < before

    real = _real_compiler("1002030").compile_enemy()
    assert not any("回调伤害/召唤/分段效果" in item["reason"]
                   for item in real["unsupported"])


def test_before_being_lose_hp_rewrites_drain_amount():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Listener"},
        }]}},
        "modifiers": {"Listener": {"_CallbackList": [{
            "Event": "OnBeforeBeingLoseHP",
            "CallbackConfig": [{
                "$type": "RPG.GameCore.ModifyLoseHPData",
                "ConstFinalDamage": {"IsDynamic": False, "FixedValue": {"Value": 12.5}},
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    hook = next(h for h in out["hooks"] if h["event"] == "before_drain")
    assert hook["condition"] == "$event.target == $self.actor_id"
    assert hook["effects"] == [{"effect_type": "modify_amount", "amount": 12.5}]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._compiled_hooks = [CompiledHook(
        owner_id="hero", event="before_drain",
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    before = hero.current_hp
    eng._hooks._run_hook_effect(source, {
        "effect_type": "drain_hp", "target": {"pool": "allies"},
        "amount": 100, "drain_ratio": 0.0}, {})
    assert hero.current_hp == before - 12.5
    real = _real_compiler("3012030").compile_enemy()
    assert not any(item["node_type"] in {"OnBeforeBeingLoseHP", "RPG.GameCore.ModifyLoseHPData"}
                   for item in real["unsupported"])


def test_modify_damage_data_rewrites_before_take_damage_amount():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Listener"},
        }]}},
        "modifiers": {"Listener": {"_CallbackList": [{
            "Event": "OnBeforeBeingHitAll",
            "CallbackConfig": [{
                "$type": "RPG.GameCore.ModifyDamageData",
                "AttackData_ConstFinalDamage": {
                    "IsDynamic": False, "FixedValue": {"Value": 12.5}},
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    hook = next(h for h in out["hooks"] if h["event"] == "before_take_damage")
    assert hook["effects"] == [{"effect_type": "modify_amount", "amount": 12.5}]

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._compiled_hooks = [CompiledHook(
        owner_id="hero", event="before_take_damage",
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    before = hero.current_hp
    eng._hooks._run_hook_effect(source, {
        "effect_type": "deal_damage", "target": "$event.target",
        "damage_type": "fire", "action_type": "follow_up", "scaling_atk": 1.0,
        "toughness_dmg": 0}, {"target": "hero", "source": "source"})
    assert hero.current_hp == before - 12.5
    real = _real_compiler("3012030").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ModifyDamageData"
                   for item in real["unsupported"])


def test_final_damage_max_caps_hook_damage_before_hp_deduction():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="before_take_damage")
    compiler._compile_modify_damage_data({
        "$type": "RPG.GameCore.ModifyDamageData",
        "AttackData_FinalDamageMax": {"IsDynamic": False, "FixedValue": {"Value": 12.5}},
    }, ctx, "P", ())
    assert not ctx.unsupported
    assert ctx.effects[0]["amount"] == "min($event.amount, (12.5))"

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._compiled_hooks = [CompiledHook(
        owner_id="hero", event="before_take_damage", condition_expr=None,
        effects=ctx.effects)]
    eng._hooks._subscribe_compiled_hooks()
    before = hero.current_hp
    eng._hooks._run_hook_effect(source, {
        "effect_type": "deal_damage", "target": "$event.target",
        "damage_type": "fire", "action_type": "follow_up", "scaling_atk": 1.0,
        "toughness_dmg": 0}, {"target": "hero", "source": "source"})
    assert hero.current_hp == before - 12.5
    real = _real_compiler("1005011").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ModifyDamageData"
                   for item in real["unsupported"])


def test_change_config_param_resilience_is_presentation():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ChangeCharacterConfigParam",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "HudOffset": {"X": 0, "Y": 1, "Z": 0}, "Resilience": "D",
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert all(not hook.get("effects") for hook in out["hooks"])
    for task in (
        {"$type": "RPG.GameCore.SetResilience"},
        {"$type": "RPG.GameCore.SetResilience", "DoReset": False},
        {"$type": "RPG.GameCore.SetResilience", "Resilience": "D"},
    ):
        out = _task_skill(task)
        assert out["ok"] and not out["unsupported"]
        assert all(not hook.get("effects") for hook in out["hooks"])


def test_damage_metadata_does_not_reject_fully_compiled_utility_skill():
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill02", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "AllEnemy"}, "EntryAbility": "Empty",
        }]},
        "abilities": {"Empty": {"Name": "Empty", "OnStart": [
            {"$type": "RPG.GameCore.SkillPerformFinish"},
        ]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s2", "trigger_key": "Skill02",
               "damage_type": "Quantum", "param_list": [2.5]}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill02")
    assert out["ok"] and not out["unsupported"] and out["action"] is not None

    sources["abilities"]["Empty"]["OnStart"].append({
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "AttackProperty": {"AttackType": "Normal", "DamageType": "Quantum",
                           "DamagePercentage": _dynamic("AQAR", hashes=[999999])},
    })
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill02")
    assert not rejected["ok"]
    assert any(item["path"].endswith("/DamagePercentage") for item in rejected["unsupported"])


def test_compile_enemy_missing_config_and_referenced_trigger_are_explicit():
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    missing = AbilityCompiler("fake", skills, {"character_config": None}).compile_enemy()
    assert not missing["ok"]
    assert missing["unsupported"][0]["node_type"] == "CharacterConfig"
    orphan_sources = {"character_config": {"SkillList": []}, "abilities": {}, "modifiers": {}}
    orphan = AbilityCompiler("fake", skills, orphan_sources).compile_enemy()
    assert not orphan["ok"] and not orphan["unsupported"]
    orphan_sources["config_ai"] = {"RootTask": {"SkillName": "Skill01"}}
    referenced = AbilityCompiler("fake", skills, orphan_sources).compile_enemy()
    assert referenced["unsupported"][0]["node_type"] == "SkillList"


_need_ability = pytest.mark.skipif(
    not (enemy_data_available() and enemy_ability_available()),
    reason="真实 Ability 样例数据缺失（tbgd/Fandom + CharacterConfig/Ability）")


def _semantic(enemy_id: str, name: str):
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics
    return {s["name"]: s for s in get_enemy_mechanics(name)["skills"]}


@_need_ability
def test_soldier_projectile_is_presentation():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "1002030", get_enemy_skills("1002030"), get_enemy_ability_sources("1002030"),
    ).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["target_type"] == "blast"
    assert out["action"]["damage_type"] == "physical"
    assert out["action"]["scaling"] == [{"atk": 1.3}]
    assert out["action"]["scaling_blast"] == [{"atk": 1.0}]


@_need_ability
def test_svarog_attach_points_are_presentation_only():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "1012040", get_enemy_skills("1012040"), get_enemy_ability_sources("1012040"),
    ).compile_skill("Skill03")
    presentation = {
        "RPG.GameCore.SetEntityFollowAttachPoint",
        "RPG.GameCore.ClearEntityFollowAttachPoint",
        "RPG.GameCore.HideEntityForCurrentCamera",
    }
    assert not any(issue["node_type"] in presentation for issue in out["unsupported"])


@_need_ability
def test_real_cocolia_adjacent_retarget_and_disable_action():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "1004011", get_enemy_skills("1004011"), get_enemy_ability_sources("1004011"),
    ).compile_skill("Skill07")
    # 重复插入能力的循环引用另案拒绝；本测试钉已直译的相邻目标与中止旗标。
    assert not any("DisableAction" in issue["reason"] for issue in out["unsupported"])
    assert any("not action_disabled($self.actor_id)" in hook["condition"]
               for hook in out["hooks"])
    assert any(
        isinstance(effect.get("target"), dict)
        and effect["target"].get("where") == "is_adjacent($it, $event.target)"
        and effect["target"].get("take") == 1
        for hook in out["hooks"] for effect in hook["effects"]
    )


@_need_ability
@pytest.mark.parametrize(("enemy_id", "trigger", "expected"), [
    ("1002040", "Skill01", -0.5), ("4033010", "Skill06", -0.3),
])
def test_real_defence_down_and_unary_negative_compile(enemy_id, trigger, expected):
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        enemy_id, get_enemy_skills(enemy_id), get_enemy_ability_sources(enemy_id),
    ).compile_skill(trigger)
    assert out["ok"] and not out["unsupported"]
    values = [
        (effect["modifier"].get("stat_effects") or {}).get("def_pct")
        for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
    ]
    assert any(value == pytest.approx(expected) for value in values)


@_need_ability
def test_real_custom_values_resolve_dynamic_symbols():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "4014010", get_enemy_skills("4014010"), get_enemy_ability_sources("4014010"),
    ).compile_skill("Skill02")
    assert not any("964279853" in issue["reason"] for issue in out["unsupported"])
    shield = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("name") == "MMonster_Heaven_StoneShield"
    )
    assert shield["stacks"] == shield["max_stack"] == 7


@_need_ability
def test_real_visual_callbacks_preserve_modifier():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "8003030", get_enemy_skills("8003030"), get_enemy_ability_sources("8003030"),
    ).compile_skill("Skill04")
    assert not out["ok"]
    assert {item["node_type"] for item in out["unsupported"]} == {
        "RPG.GameCore.CreateTeamFormationSnapshot", "RPG.GameCore.RestoreTeamFormationSnapshot"}
    assert any(
        effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("name") == "Monster_XP_Elite02_00_Edict02"
        for hook in out["hooks"] for effect in hook["effects"]
    )


@_need_ability
@pytest.mark.parametrize(("enemy_id", "trigger"), [
    ("5013010", "Skill04"), ("2023021", "Skill02"),
])
def test_real_remaining_presentation_nodes_compile(enemy_id, trigger):
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        enemy_id, get_enemy_skills(enemy_id), get_enemy_ability_sources(enemy_id),
    ).compile_skill(trigger)
    assert out["ok"] and not out["unsupported"]


@pytest.mark.parametrize("node_type", [
    "RPG.GameCore.AutoMappingAttachPoint",
    "RPG.GameCore.ChangeCharacterModel",
    "RPG.GameCore.ChangeCharacterUIDisplay",
    "RPG.GameCore.DisableCharacterVO",
    "RPG.GameCore.GlobalTimeSlow",
    "RPG.GameCore.ModifierOverrideOnHitEffect",
    "RPG.GameCore.OverrideEntityModifierPhaseCamera",
    "RPG.GameCore.ResetCharacterCustomTeamFormation",
    "RPG.GameCore.SetCameraRootFollow",
    "RPG.GameCore.SetEntityForceVisible",
    "RPG.GameCore.SetFaceDirectionLocked",
    "RPG.GameCore.ShowActionBarEffect",
    "RPG.GameCore.ShowBattleEventButton",
    "RPG.GameCore.StartEffectAim",
    "RPG.GameCore.StopTimeline",
    "RPG.GameCore.TutorialTaskUnlock",
    "RPG.GameCore.VCameraNoiseChange",
    "RPG.GameCore.TriggerAutoLayoutTransferPerform",
    "RPG.GameCore.SwitchOverrideController",
    "RPG.GameCore.CharacterChangeModel",
    "RPG.GameCore.DecoupleParentTransform",
    "RPG.GameCore.SetActionBarRightDownMiniIcon",
    "RPG.GameCore.LevelAudioTrigger",
    "RPG.GameCore.SetModifierEffectVisible",
    "RPG.GameCore.SetColliderCenterFollowAttachPoint",
    "RPG.GameCore.AvatarIntensityEffect",
    "RPG.GameCore.SetCharacterVisibleInViewMode",
    "RPG.GameCore.ShowBattleTalkBGUI",
    "RPG.GameCore.ToggleHitCountUITop",
    "RPG.GameCore.TriggerModelShake",
    "RPG.GameCore.ChangeAnimEventConfig",
    "RPG.GameCore.FrameCaptureIfNeed",
    "RPG.GameCore.LockAnimatorSpeed",
    "RPG.GameCore.SetCharacterAtlasFaceEmotion",
    "RPG.GameCore.ForbidBattleConditionOnStart",
    "RPG.GameCore.SetSignedAngleByTarget",
    "RPG.GameCore.AlignTargetToTeamCenter",
    "RPG.GameCore.SetCharacterFormation",
    "RPG.GameCore.SetCharacterCustomTeamFormation",
])
def test_additional_presentation_nodes_are_ignored(node_type):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{"$type": node_type}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]


@_need_ability
def test_real_fire_prowler_servant_hp_ratio_in_engine():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        "4034010", get_enemy_skills("4034010"), get_enemy_ability_sources("4034010"),
    ).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]
               if effect.get("effect_type") == "set_dynamic_value"
               and effect.get("dynamic_key") == "CurrentHPRatio"]
    assert effects == [{
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "CurrentHPRatio",
        "amount": "hp_of($self.actor_id) / max_hp_of($self.actor_id)",
    }]

    eng = engine_vs_dummy(enemies=[make_dummy("4034010", hp=4000)])
    enemy = eng.state.actors["4034010"]
    enemy.current_hp = 2000.0
    for effect in effects:
        eng._hooks._run_hook_effect(enemy, effect, {})
    runtime = eng._enemy_policy_state["4034010"]["dynamic_values"]
    assert runtime["CurrentHPRatio"] == pytest.approx(0.5)


@_need_ability
@pytest.mark.parametrize(("enemy_id", "trigger", "target", "target_id", "expected_filter", "modifier_kwargs"), [
    ("3003010", "Skill03", "self", "3003010", "$mod.kind == 'control'",
     {"modifier_type": "debuff", "debuff_kind": "control", "control_kind": "freeze"}),
    ("3003050", "Skill05", "all_allies", "hero", "$mod.kind == 'dot'",
     {"modifier_type": "dot"}),
    ("3025010", "Skill042", "all_enemies", "3025010", "$mod.prevent_action",
     {"modifier_type": "debuff", "prevent_action": True}),
])
def test_real_remove_behavior_flag_in_engine(
        enemy_id, trigger, target, target_id, expected_filter, modifier_kwargs):
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        enemy_id, get_enemy_skills(enemy_id), get_enemy_ability_sources(enemy_id),
    ).compile_skill(trigger)
    assert not any("未注册行为旗标摘除" in issue["reason"] for issue in out["unsupported"])
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]
               if effect.get("filter") == expected_filter]
    assert effects == [{
        "effect_type": "remove_modifier", "target": target,
        "filter": expected_filter, "reason": "dispel",
    }]

    eng = engine_vs_dummy(enemies=[make_dummy(enemy_id)])
    source = eng.state.actors[enemy_id]
    target_state = eng.state.actors[target_id]
    target_state.modifiers["marked"] = Modifier(
        modifier_id="marked", name="marked", **modifier_kwargs)
    target_state.modifiers["atk_up"] = Modifier(
        modifier_id="atk_up", name="atk_up", modifier_type="buff")
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert "marked" not in target_state.modifiers and "atk_up" in target_state.modifiers


@_need_ability
def test_real_dot_predicate_filters_retarget_in_engine():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    real_sources = get_enemy_ability_sources("3003050")
    retarget = dict(real_sources["abilities"][
        "Monster_W3_Figure_01_Skill05_Phase02"]["OnStart"][4])
    assert retarget["$type"] == "RPG.GameCore.Retarget"
    assert retarget["Predicate"]["Flag"] == "STAT_DOT"
    retarget["TaskList"] = [{
        "$type": "RPG.GameCore.RemoveModifierByBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "ModifierBehaviorFlags": ["STAT_DOT"],
    }]
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [retarget]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == {
        "pool": "allies", "where": "dot_count($it) > 0", "mode": "random", "take": 1,
    }

    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    ally = eng.state.actors["ally"]
    hero.modifiers["dot"] = Modifier(modifier_id="dot", name="dot", modifier_type="dot")
    hero.modifiers["atk_up"] = Modifier(
        modifier_id="atk_up", name="atk_up", modifier_type="buff")
    ally.modifiers["debuff"] = Modifier(
        modifier_id="debuff", name="debuff", modifier_type="debuff")
    eng._hooks._run_hook_effect(source, effect, {})
    assert "dot" not in hero.modifiers and "atk_up" in hero.modifiers
    assert "debuff" in ally.modifiers


@_need_ability
def test_real_dot_trigger_and_purge_chain_in_engine():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = AbilityCompiler(
        "3003050", get_enemy_skills("3003050"), get_enemy_ability_sources("3003050"),
    ).compile_skill("Skill05")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["target_type"] == "aoe"
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    trigger = next(effect for effect in effects if effect["effect_type"] == "trigger_dot")
    assert trigger == {
        "effect_type": "trigger_dot", "ratio": 1.25,
        "target": {"pool": "allies", "where": "dot_count($it) > 0", "mode": "random", "take": 1},
    }

    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("3003050")])
    source = eng.state.actors["3003050"]
    hero = eng.state.actors["hero"]
    ally = eng.state.actors["ally"]
    hero.modifiers["dot"] = Modifier(
        modifier_id="dot", name="dot", modifier_type="dot", debuff_kind="dot",
        duration=2, source_id="3003050", dot_element="thunder",
        dot_ratio=1.0, dot_source_atk=1000.0)
    ally.modifiers["debuff"] = Modifier(
        modifier_id="debuff", name="debuff", modifier_type="debuff")
    events = []
    eng.bus.subscribe("on_dot_retrigger", lambda _et, payload, _ctx: events.append(
        ("trigger", payload["modifier_id"])))
    eng.bus.subscribe("after_remove_modifier", lambda _et, payload, _ctx: events.append(
        ("remove", payload["modifier_id"])) if payload["modifier_id"] == "dot" else None)
    hp_before = hero.current_hp
    ally_hp_before = ally.current_hp
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert hp_before - hero.current_hp == pytest.approx(1.25 * 1000 * 0.5 * 0.8 * 0.9)
    assert eng.state.damage_by_actor["3003050"] == pytest.approx(450.0)
    assert "dot" not in hero.modifiers
    assert ally.current_hp == ally_hp_before and "debuff" in ally.modifiers
    assert events == [("trigger", "dot"), ("remove", "dot")]


@_need_ability
@pytest.mark.parametrize(("enemy_id", "trigger", "modifier_name", "stat", "expected"), [
    ("4052010", "Skill01", "MMonster_W4_Manta_00_Virus_Transfer", "dmg_dmg_reduction", 0.7),
    ("5012100", "Skill03", "MMonster_W5_Magical_00_DeathRattle_Sun", "crit_dmg", 0.25),
    ("3001010", "Skill01", "MCommon_StatusResistanceDown", "effect_res", -0.2),
])
def test_real_stack_property_mappings(enemy_id, trigger, modifier_name, stat, expected):
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        enemy_id, get_enemy_skills(enemy_id), get_enemy_ability_sources(enemy_id),
    ).compile_skill(trigger)
    expected_unsupported = {
        "DynamicValue", "RPG.GameCore.SetDynamicValue",
        "RPG.GameCore.PredicateTaskList", "ModifierDOT",
    } if enemy_id == "4052010" else set()
    assert out["ok"] == (not expected_unsupported)
    assert {item["node_type"] for item in out["unsupported"]} == expected_unsupported
    modifier = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("name") == modifier_name
    )
    assert modifier["stat_effects"][stat] == pytest.approx(expected)


@_need_ability
def test_monster_damage_taken_ratio_reuses_vulnerability():
    out = _real_compiler("8015010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.StackProperty"
                   and "Monster_DamageTakenRatio" in item["reason"]
                   for item in out["unsupported"])
    modifier = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("name") == "MMonster_AML_Boss_00_DamageTakenUp")
    assert modifier["stat_effects"]["vulnerability"] == pytest.approx(9.0)


@_need_ability
def test_element_taken_ratio_uses_scoped_vulnerability_only_for_that_element():
    from hsr_nous.sim.state import Modifier
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    out = _real_compiler("2004023").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.StackProperty"
                   and "IceTakenRatio" in item["reason"] for item in out["unsupported"])
    spec = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("name") == "MMonster_W2_Yanqing_00_Common_IceDamageTakenUp")
    assert spec["hit_condition"] == "$event.damage_type == 'ice'"
    assert set(spec["hit_stat_exprs"]) == {"vulnerability"}

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    hero.modifiers[spec["modifier_id"]] = Modifier(
        modifier_id=spec["modifier_id"], name=spec["name"], modifier_type="debuff",
        hit_condition_expr=eng._expr.compile(spec["hit_condition"], layer="effect"),
        hit_stat_exprs={"vulnerability": eng._expr.compile(
            spec["hit_stat_exprs"]["vulnerability"], layer="effect")})
    ice = eng.pipeline.settle_damage(
        "direct", source, hero, action=basic_action("hit", damage_type="ice"), element="ice")
    fire = eng.pipeline.settle_damage(
        "direct", source, hero, action=basic_action("hit", damage_type="fire"), element="fire")
    assert ice.node["vulnMulti"] == pytest.approx(1.02)
    assert fire.node["vulnMulti"] == pytest.approx(1.0)


@_need_ability
def test_level_final_damage_added_ratio_uses_final_damage_bucket():
    from hsr_nous.sim.state import Modifier
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    out = _real_compiler("8015020").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.StackProperty"
                   and "Level_FinalDamageAddedRatio" in item["reason"]
                   for item in out["unsupported"])
    spec = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("name") == "Monster_W2_Huanlong_00_JingYuan_DamageUp")
    assert spec["stat_effects"]["dmg_final_dmg_boost"] == pytest.approx(2.0)

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    source.modifiers[spec["modifier_id"]] = Modifier(
        modifier_id=spec["modifier_id"], name=spec["name"], modifier_type="buff",
        stat_effects=dict(spec["stat_effects"]))
    result = eng.pipeline.settle_damage(
        "direct", source, eng.state.actors["hero"], action=basic_action("hit"))
    assert result.node["finalDmgMulti"] == pytest.approx(3.0)


@_need_ability
def test_before_take_damage_reads_modifier_layers_from_event_target():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    out = _real_compiler("2004013").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.SetDynamicValueByModifierValue"
                   for issue in out["unsupported"])
    effect = next(
        effect for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("dynamic_key") == "MDF_OriginLayer"
        and effect.get("amount") == "stacks($event.target, 'Monster_Company_Coin_Avater')")

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    eng._apply_modifier(eng.state.actors["hero"], Modifier(
        modifier_id="Monster_Company_Coin_Avater", name="coin", modifier_type="debuff",
        stacks=3, max_stack=5))
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {"target": "hero"})
    values = eng._enemy_policy_state["source"]["dynamic_values"]
    assert values["MDF_OriginLayer"] == pytest.approx(3.0)


@_need_ability
def test_before_hit_all_zero_defence_uses_scoped_def_pen():
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    out = _real_compiler("3025010").compile_skill("Skill10")
    assert not any("OnBeforeHitAll" in issue["path"] for issue in out["unsupported"])
    name = "MMonster_W3_Sunday_00_Skill10_AttackIgnoreDEF"
    spec = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("modifier_id") == name)
    assert spec["hit_stat_exprs"]["def_pen"] == pytest.approx(1.0)
    assert "hit_condition" not in spec

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    eng._apply_modifier_spec(source, spec, source)
    result = eng.pipeline.settle_damage(
        "direct", source, eng.state.actors["hero"], action=basic_action("hit"))
    assert result.node["defMulti"] == pytest.approx(1.0)

    import copy
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    bad_sources = copy.deepcopy(get_enemy_ability_sources("3025010"))
    definition = bad_sources["modifiers"][name]
    callback = next(callback for callback in definition["_CallbackList"]
                    if callback["Event"] == "OnBeforeHitAll")
    change = next(task for task in callback["CallbackConfig"]
                  if task.get("$type") == "RPG.GameCore.ModifyDamageData")
    change["Defender_DefenceDelta"]["PostfixExpr"]["FixedValues"][0]["Value"] = 1
    bad = AbilityCompiler("3025010", get_enemy_skills("3025010"), bad_sources).compile_skill("Skill10")
    assert any(issue["node_type"] == "RPG.GameCore.ModifyDamageData"
               and "OnBeforeHitAll" in issue["path"] for issue in bad["unsupported"])


@_need_ability
def test_before_hit_attacker_added_ratio_uses_scoped_all_dmg():
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    out = _real_compiler("3025015").compile_enemy()
    result = out["skill_results"]["Monster_W3_Sunday_00_SkillP03"]
    assert not any("OnBeforeHitAll" in issue["path"] for issue in result["unsupported"])
    name = "MMonster_W3_Sunday_00_MainStory380_Mar7thAllDamageTypeAddedRatio"
    spec = next(
        effect["modifier"] for hook in result["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("modifier_id") == name)
    assert spec["hit_condition"] == "($event.action_type == 'ultimate')"
    assert spec["hit_stat_exprs"]["all_dmg"] == pytest.approx(2.0)

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    eng._apply_modifier_spec(source, spec, source)
    hero = eng.state.actors["hero"]
    ultimate = eng.pipeline.settle_damage(
        "direct", source, hero, action=basic_action("hit", action_type="ultimate"))
    basic = eng.pipeline.settle_damage(
        "direct", source, hero, action=basic_action("hit", action_type="basic"))
    assert ultimate.node["dmgBoostMulti"] == pytest.approx(3.0)
    assert basic.node["dmgBoostMulti"] == pytest.approx(1.0)


@_need_ability
def test_before_hit_defender_taken_ratio_uses_scoped_vulnerability():
    import copy
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim.state import Modifier
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    enemy_id = "8034012"
    name = "MMonster_W3_Aventurine_00_IF_Score_Light"
    out = _real_compiler(enemy_id).compile_enemy()
    result = out["skill_results"]["Monster_W3_Aventurine_00_Passive01"]
    assert not any("OnBeforeHitAll" in issue["path"] for issue in result["unsupported"])
    spec = next(
        effect["modifier"] for hook in result["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("modifier_id") == name
        and effect["modifier"].get("hit_stat_exprs"))
    assert spec["hit_stat_exprs"]["vulnerability"] == (
        "0.01 * dynamic_of($self.actor_id, 'MDF_EntityScore')")

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "MDF_EntityScore", "amount": 4.0}, {})
    eng._apply_modifier_spec(source, spec, source)
    hero = eng.state.actors["hero"]
    hit = eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))
    assert hit.node["vulnMulti"] == pytest.approx(1.04)
    self_hit = eng.pipeline.settle_damage("direct", source, source, action=basic_action("hit"))
    assert self_hit.node["vulnMulti"] == pytest.approx(1.04)
    eng._apply_modifier(hero, Modifier(
        modifier_id="MMonster_W3_Aventurine_00_IF_Defence", name="defence",
        modifier_type="buff"))
    defended = eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))
    assert defended.node["vulnMulti"] == pytest.approx(1.0)

    bad_sources = copy.deepcopy(get_enemy_ability_sources(enemy_id))
    definition = bad_sources["modifiers"][name]
    definition["_CallbackList"].append({"Event": "OnCreate", "CallbackConfig": [{
        "$type": "RPG.GameCore.SetDynamicValue",
        "DynamicKey": {"Value": "ExternalRead"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "Value": {"IsDynamic": True, "PostfixExpr": {
            "OpCodes": "AQAR", "FixedValues": [],
            "DynamicHashes": [dynamic_value_hash("MDF_AllDamageAddedRatio")]}},
    }]})
    bad = AbilityCompiler(enemy_id, get_enemy_skills(enemy_id), bad_sources).compile_enemy()
    assert any(issue["node_type"] == "RPG.GameCore.ModifyDamageData"
               and "OnBeforeHitAll" in issue["path"] for issue in bad["unsupported"])


@_need_ability
def test_before_being_hit_taken_ratio_uses_scoped_vulnerability():
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    out = _real_compiler("4012060").compile_enemy()

    def modifiers(value):
        if isinstance(value, dict):
            if value.get("modifier_id") == "Monster_W4_HearsePart_00_Soul" \
                    and value.get("hit_stat_exprs"):
                yield value
            for child in value.values():
                yield from modifiers(child)
        elif isinstance(value, list):
            for child in value:
                yield from modifiers(child)

    spec = next(modifiers(out))
    assert spec["hit_stat_exprs"]["vulnerability"] == pytest.approx(1.0)
    assert "target_lists_intersect" in spec["hit_condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._apply_modifier_spec(hero, spec, source)
    hit = eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))
    assert hit.node["vulnMulti"] == pytest.approx(2.0)


@_need_ability
def test_before_being_hit_monster_taken_ratio_switch_uses_live_world_level():
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    out = _real_compiler("3025015").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ModifyDamageData"
                   for item in out["unsupported"])
    spec = next(
        effect["modifier"] for result in out["skill_results"].values()
        for hook in result.get("hooks", []) for effect in hook.get("effects", [])
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("modifier_id")
        == "MMonster_W3_Sunday_00_MainStory380_DamageTakenRatio")
    assert "actor_type_of($event.target) == 'character'" in spec["hit_condition"]
    assert "dynamic_of($self, 'MDF_WorldLevel') == 2" in spec["hit_stat_exprs"]["vulnerability"]

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._apply_modifier_spec(source, spec, source)
    for world_level, expected in ((0, 1.2), (2, 1.4), (99, 6.0)):
        eng._hooks._run_hook_effect(source, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": "MDF_WorldLevel", "amount": world_level}, {})
        hit = eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))
        assert hit.node["vulnMulti"] == pytest.approx(expected)
    enemy_hit = eng.pipeline.settle_damage("direct", source, source, action=basic_action("hit"))
    assert enemy_hit.node["vulnMulti"] == pytest.approx(1.0)


@_need_ability
def test_force_stance_break_ratio_opens_conditional_toughness_gate():
    import copy
    from dataclasses import replace
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    out = _real_compiler("8012146").compile_skill("Skill02")
    assert not any(item["node_type"] == "RPG.GameCore.ModifyDamageData"
                   for item in out["unsupported"])
    spec = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and "force_stance_break" in effect["modifier"].get("hit_stat_exprs", {}))
    assert spec["hit_stat_exprs"]["force_stance_break"] == 1
    assert "not (has_weakness($event.target, element_of($self.actor_id)))" in spec["hit_condition"]

    source_actor = replace(make_dummy("source"), element="imaginary")
    eng = engine_vs_dummy(enemies=[
        source_actor, make_dummy("target", weakness=("fire",))])
    source = eng.state.actors["source"]
    target = eng.state.actors["target"]
    action = basic_action("hit", damage_type="imaginary", toughness_dmg=30)
    initial = target.toughness
    eng._apply_toughness_damage(source.actor, action, target)
    assert target.toughness == initial
    eng._apply_modifier_spec(source, spec, source)
    eng._apply_toughness_damage(source.actor, action, target)
    assert target.toughness == initial
    eng._apply_modifier_spec(target, {
        "modifier_id": "MMonster_AML_Boss_00_Part2_IF_SkillP01_Weakness_Part3",
        "modifier_type": "debuff", "duration": 0}, source)
    eng._apply_toughness_damage(source.actor, action, target)
    assert target.toughness == pytest.approx(initial - 45.0)

    bad_sources = copy.deepcopy(get_enemy_ability_sources("8012146"))
    definition = bad_sources["modifiers"]["MMonster_AML_Boss_00_IF_Enhance_Imaginary"]
    callback = next(callback for callback in definition["_CallbackList"]
                    if callback["Event"] == "OnBeforeHit")
    change = callback["CallbackConfig"][0]["SuccessTaskList"][0]
    change["Attacker_ForceStanceBreakRatio"]["FixedValue"]["Value"] = 0.5
    bad = AbilityCompiler("8012146", get_enemy_skills("8012146"), bad_sources).compile_skill("Skill02")
    assert any("仅支持静态值 1" in item["reason"] for item in bad["unsupported"])


@_need_ability
def test_before_hit_all_damage_reduce_uses_multiplicative_scoped_reduction():
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    out = _real_compiler("8003040").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ModifyDamageData"
                   for item in out["unsupported"])
    spec = next(
        effect["modifier"] for result in out["skill_results"].values()
        for hook in result.get("hooks", []) for effect in hook.get("effects", [])
        if effect.get("effect_type") == "apply_modifier"
        and "dmg_dmg_reduction" in effect["modifier"].get("hit_stat_exprs", {}))
    assert spec["hit_stat_exprs"]["dmg_dmg_reduction"] == pytest.approx(0.1)

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._apply_modifier_spec(source, spec, source)
    hit = eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))
    assert hit.node["dmgRedMulti"] == pytest.approx(0.9)
    other_action = eng.pipeline.settle_damage(
        "direct", source, hero, action=basic_action("hit", action_type="additional"))
    assert other_action.node["dmgRedMulti"] == pytest.approx(1.0)

    eng._apply_modifier_spec(hero, {
        "modifier_id": "HIT_REDUCTION", "modifier_type": "buff", "duration": 0,
        "hit_stat_exprs": {"dmg_dmg_reduction": 0.2}}, source)
    eng._apply_modifier_spec(hero, {
        "modifier_id": "PANEL_REDUCTION", "modifier_type": "buff", "duration": 0,
        "stat_effects": {"dmg_dmg_reduction": 0.3}}, source)
    combined = eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))
    assert combined.node["dmgRedMulti"] == pytest.approx(0.7 * 0.9 * 0.8)


@_need_ability
def test_fixed_critical_chance_overrides_scoped_crit_rate():
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    out = _real_compiler("3024030").compile_skill("Skill04")
    assert not any(item["node_type"] == "RPG.GameCore.ModifyDamageData"
                   for item in out["unsupported"])
    spec = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and "fixed_crit_rate" in effect["modifier"].get("hit_stat_exprs", {}))
    assert spec["hit_stat_exprs"]["fixed_crit_rate"] == 0
    assert spec["hit_condition"] == "dynamic_of($self, 'MDF_TargetAttackFlag') == 2"

    eng = engine_vs_dummy(enemies=[make_dummy(
        "source", atk=1000, crit_rate=0.8, crit_dmg=1.0)])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._apply_modifier_spec(source, spec, source)
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "MDF_TargetAttackFlag", "amount": 1}, {})
    normal = eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))
    assert normal.node["critMulti"] == pytest.approx(1.8)
    eng._apply_modifier_spec(source, {
        "modifier_id": "HIT_CRIT_RATE", "modifier_type": "buff", "duration": 0,
        "hit_stat_exprs": {"crit_rate": 0.5}}, source)
    boosted = eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))
    assert boosted.node["critMulti"] == pytest.approx(2.0)
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "MDF_TargetAttackFlag", "amount": 2}, {})
    fixed = eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))
    assert fixed.node["critMulti"] == pytest.approx(1.0)

    eng._apply_modifier_spec(source, {
        "modifier_id": "CONFLICTING_FIXED_CRIT", "modifier_type": "buff", "duration": 0,
        "hit_stat_exprs": {"fixed_crit_rate": 0.5}}, source)
    with pytest.raises(ValueError, match="scoped_override 存在冲突值"):
        eng.pipeline.settle_damage("direct", source, hero, action=basic_action("hit"))


@_need_ability
def test_switch_case_hit_ratios_preserve_live_damage_predicates():
    from dataclasses import replace
    from tests._builders import basic_action, engine_vs_dummy, make_actor, make_dummy

    out = _real_compiler("5013030").compile_enemy()
    assert not any(item["reason"] == "CustomValue 哈希缺失或冲突"
                   for item in out["unsupported"])
    assert not any(item["node_type"] == "RPG.GameCore.ModifyDamageData"
                   for item in out["unsupported"])
    spec = next(
        effect["modifier"] for result in out["skill_results"].values()
        for hook in result.get("hooks", []) for effect in hook.get("effects", [])
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("modifier_id") == "MMonster_W5_Peacock_00_SkillP01_Colorful"
        and effect["modifier"].get("hit_stat_exprs"))
    assert "not (element_of($event.target) == 'fire')" in spec["hit_stat_exprs"]["all_dmg"]

    eng = engine_vs_dummy(hero=replace(make_actor("hero"), element="ice"),
                          enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._apply_modifier_spec(source, spec, source)
    action = replace(basic_action("hit", action_type="follow_up", damage_type="fire"),
                     damage_custom_name="Peacock_UseColor")
    different = eng.pipeline.settle_damage("direct", source, hero, action=action)
    assert different.node["dmgBoostMulti"] == pytest.approx(1.5)
    hero.actor = replace(hero.actor, element="fire")
    same = eng.pipeline.settle_damage("direct", source, hero, action=action)
    assert same.node["dmgBoostMulti"] == pytest.approx(1.0)
    wrong_name = eng.pipeline.settle_damage(
        "direct", source, hero, action=replace(action, damage_custom_name="Other"))
    assert wrong_name.node["dmgBoostMulti"] == pytest.approx(1.0)


@_need_ability
def test_before_being_heal_taken_ratio_uses_target_scoped_incoming_heal():
    from dataclasses import replace
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = _real_compiler("3024020").compile_enemy()
    assert not any(issue["node_type"] == "OnBeforeBeingHeal" for issue in out["unsupported"])

    def modifiers(value):
        if isinstance(value, dict):
            if value.get("modifier_id") == "Monster_W3_Sam_00_BurningBP" \
                    and value.get("hit_stat_exprs"):
                yield value
            for child in value.values():
                yield from modifiers(child)
        elif isinstance(value, list):
            for child in value:
                yield from modifiers(child)

    spec = next(modifiers(out))
    assert spec["hit_stat_exprs"]["incoming_heal"] == pytest.approx(-0.9)
    servant_actor = replace(make_actor("servant"), actor_type="summon", summoner_id="hero")
    eng = engine_vs_dummy(allies=[servant_actor], enemies=[make_dummy("source")])
    hero = eng.state.actors["hero"]
    servant = eng.state.actors["servant"]
    eng._apply_modifier_spec(servant, spec, hero)
    reduced = eng.pipeline.heal(hero, servant, amount=1000)
    normal = eng.pipeline.heal(hero, hero, amount=1000)
    assert reduced.value == pytest.approx(100.0)
    assert normal.value == pytest.approx(1000.0)


@_need_ability
def test_active_modifier_on_end_break_reaches_lifecycle_compiler():
    out = _real_compiler("3025010").compile_enemy()
    name = "MMonster_W3_Sunday_00_Skill042_Part_ChargeEffect_Controller"
    assert not any(item["node_type"] == "Modifier" and item["reason"].endswith(name)
                   for item in out["unsupported"])
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Controller"},
    }]
    sources["modifiers"] = {
        "Controller": {"_CallbackList": [{
            "Event": "OnEndBreak",
            "CallbackConfig": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
                "ModifierName": {"Value": "Child"},
            }],
        }]},
        "Child": {"BehaviorFlagList": ["RemoveWhenCasterDead"]},
    }
    synthetic = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert synthetic["ok"] and not synthetic["unsupported"]
    assert any(effect.get("effect_type") == "apply_modifier"
               and effect["modifier"].get("name") == "Child"
               for hook in synthetic["hooks"] if hook["event"] == "toughness_recovered"
               for effect in hook["effects"])


@_need_ability
def test_active_modifiers_accept_on_listen_turn_begin():
    for enemy_id, name in (("2033010", "MCommon_FearListener"),
                           ("4014020", "Monster_W4_Hearse_00_Action")):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(item["node_type"] == "Modifier" and item["reason"].endswith(name)
                       for item in out["unsupported"])
        assert any(hook["event"] == "on_turn_start" for hook in out["hooks"])


@pytest.mark.parametrize("unknown_event", ["OnUnknownEvent", "OnCustomEvent"])
def test_mixed_modifier_callbacks_report_unknown_event_instead_of_skipping(unknown_event):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Controller"},
    }]
    sources["modifiers"] = {"Controller": {"_CallbackList": [{
        "Event": "OnEndBreak",
        "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValue",
            "DynamicKey": {"Value": "Known"}, "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }, {
        "Event": unknown_event,
        "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValue",
            "DynamicKey": {"Value": "MustNotHide"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    if unknown_event == "OnCustomEvent":
        assert out["ok"] and not out["unsupported"]
        assert any(hook["event"] == "modifier_custom_event" for hook in out["hooks"])
    else:
        assert not out["ok"]
        assert any(item["node_type"] == unknown_event for item in out["unsupported"])


@_need_ability
@pytest.mark.parametrize(("enemy_id", "trigger", "key", "stat", "expected"), [
    ("2005010", "Skill03", "CurrentSpeed", "spd", 150.0),
    ("3025010", "Skill10", "Skill10Attack", "atk", 3000.0),
])
def test_real_current_property_dynamic_values(enemy_id, trigger, key, stat, expected):
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        enemy_id, get_enemy_skills(enemy_id), get_enemy_ability_sources(enemy_id),
    ).compile_skill(trigger)
    assert not any(key in issue["reason"] and "属性动态键" in issue["reason"]
                   for issue in out["unsupported"])
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]
               if effect.get("dynamic_key") == key]
    assert effects == [{
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": key,
        "amount": f"stat_of($self.actor_id, '{stat}')",
    }]

    eng = engine_vs_dummy(enemies=[make_dummy(enemy_id, atk=2000, spd=100)])
    source = eng.state.actors[enemy_id]
    eng._apply_modifier(source, Modifier(
        modifier_id="boost", name="boost", modifier_type="buff",
        stat_effects={f"{stat}_pct": 0.5}))
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state[enemy_id]["dynamic_values"][key] == pytest.approx(expected)


@_need_ability
def test_real_summoner_max_hp_dynamic_value():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = AbilityCompiler(
        "8012204", get_enemy_skills("8012204"), get_enemy_ability_sources("8012204"),
    ).compile_skill("PassiveSkill03")
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]
               if effect.get("dynamic_key") == "SummonerMaxHPValue"]
    assert effects == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "SummonerMaxHPValue",
        "amount": "max_hp_of(summoner_of($self.actor_id))",
    }]

    summoner = make_actor("summoner", hp=7000)
    lotus = make_dummy("8012204")
    lotus.summoner_id = "summoner"
    eng = engine_vs_dummy(allies=[summoner], enemies=[lotus])
    source = eng.state.actors["8012204"]
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    runtime = eng._enemy_policy_state["8012204"]["dynamic_values"]
    assert runtime["SummonerMaxHPValue"] == pytest.approx(7000.0)


@_need_ability
def test_real_stance_dynamic_values():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        "4034013", get_enemy_skills("4034013"), get_enemy_ability_sources("4034013"),
    ).compile_skill("Skill08")
    on_apply = next(
        effect["modifier"]["on_apply"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and any(item.get("dynamic_key") == "_CurrentStance"
                for item in effect["modifier"].get("on_apply", []))
    )
    assert on_apply[:3] == [{
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "_StanceCount",
        "amount": "stance_count_of($self.actor_id)",
    }, {
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "_CurrentStance",
        "amount": "toughness_of($self.actor_id)",
    }, {
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "_MaxStance",
        "amount": "base_stat_of($self.actor_id, 'max_toughness')",
    }]

    eng = engine_vs_dummy(enemies=[make_dummy("4034013", max_toughness=120)])
    source = eng.state.actors["4034013"]
    source.toughness = 45.0
    for effect in on_apply[:3]:
        eng._hooks._run_hook_effect(source, effect, {})
    runtime = eng._enemy_policy_state["4034013"]["dynamic_values"]
    assert runtime["_StanceCount"] == pytest.approx(1.0)
    assert runtime["_CurrentStance"] == pytest.approx(45.0)
    assert runtime["_MaxStance"] == pytest.approx(120.0)


@_need_ability
def test_real_param_entity_max_hp_dynamic_value():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        "4012070", get_enemy_skills("4012070"), get_enemy_ability_sources("4012070"),
    ).compile_skill("Skill02")
    assert not any("_MaxHP / ParamEntity / MaxHP" in issue["reason"]
                   for issue in out["unsupported"])
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]
               if effect.get("dynamic_key") == "_MaxHP"]
    assert effects[0] == {
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "_MaxHP",
        "amount": "max_hp_of($target)", "amount_target": {"pool": "$event.target"},
    }

    eng = engine_vs_dummy(enemies=[make_dummy("4012070")])
    source = eng.state.actors["4012070"]
    eng._hooks._run_hook_effect(source, effects[0], {"target": "hero"})
    runtime = eng._enemy_policy_state["4012070"]["dynamic_values"]
    assert runtime["_MaxHP"] == pytest.approx(5000.0)


@_need_ability
def test_real_taunt_effect_and_source_exit_lifecycle():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    skills = get_enemy_skills("1013010")
    sources = dict(get_enemy_ability_sources("1013010"))
    sources["character_config"] = dict(sources["character_config"])
    task = sources["abilities"]["WMonster_W1_Mecha_02_Skill04_Phase02"]["OnStart"][8]["TaskList"][2]
    assert task["ModifierName"]["Value"] == "MCommon_CTRL_Taunt"
    sources["character_config"]["SkillList"] = [{
        "Name": "Skill04", "SkillType": "Skill",
        "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
    }]
    sources["abilities"] = {"A": {"Name": "A", "OnStart": [task]}}
    out = AbilityCompiler("1013010", skills, sources).compile_skill("Skill04")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    spec = effect["modifier"]
    assert spec["control_kind"] == "taunt" and spec["forced_taunt"]
    assert spec["remove_on_source_death"] and spec["remove_on_source_exit"]

    def apply_taunt():
        eng = engine_vs_dummy(enemies=[make_dummy("1013010")])
        source = eng.state.actors["1013010"]
        eng._hooks._run_hook_effect(source, effect, {"target": "hero"})
        return eng, source, eng.state.actors["hero"]

    eng, source, hero = apply_taunt()
    assert hero.modifiers[spec["modifier_id"]].forced_taunt
    assert eng._pick_ally_target(source) is hero
    assert eng._hooks._hook_functions(source)["controlled"]("hero", "taunt") == 1.0
    eng.leave_actor("1013010")
    assert spec["modifier_id"] not in hero.modifiers

    eng, source, hero = apply_taunt()
    source.current_hp = 0.0
    eng._check_death(source)
    assert spec["modifier_id"] not in hero.modifiers

    eng, source, hero = apply_taunt()
    eng.leave_actor("1013010", reason="banish")
    assert spec["modifier_id"] in hero.modifiers


@_need_ability
def test_real_freeze_control_and_turn_start_pursued_damage():
    import types
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    skills = get_enemy_skills("1004025")
    sources = dict(get_enemy_ability_sources("1004025"))
    sources["character_config"] = dict(sources["character_config"])
    task = sources["abilities"]["Monster_W1_Gepard_00_IF_03_Skill04_Phase02"]["OnStart"][7]["SuccessTaskList"][0]
    assert task["ModifierName"]["Value"] == "MCommon_CTRL_Frozen"
    sources["character_config"]["SkillList"] = [{
        "Name": "Skill04", "SkillType": "Skill",
        "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
    }]
    sources["abilities"] = {"A": {"Name": "A", "OnStart": [task]}}
    out = AbilityCompiler("1004025", skills, sources).compile_skill("Skill04")
    assert out["ok"] and not out["unsupported"]
    apply_effect = out["hooks"][0]["effects"][0]
    spec = apply_effect["modifier"]
    assert spec["modifier_type"] == "control" and spec["control_kind"] == "freeze"
    assert spec["prevent_action"]
    turn_hook = next(hook for hook in out["hooks"] if hook["event"] == "on_turn_start")
    assert turn_hook["effects"] == [{
        "effect_type": "deal_damage", "target": "$event.actor", "damage_type": "ice",
        "action_type": "follow_up", "scaling_atk": 1.0,
    }]

    eng = engine_vs_dummy(enemies=[make_dummy("1004025", atk=1000, crit_rate=0.0)])
    source = eng.state.actors["1004025"]
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, {**apply_effect, "apply_chance": 1.0}, {"target": "hero"})
    assert hero.modifiers["MCommon_CTRL_Frozen"].prevent_action
    eng._compiled_hooks = [types.SimpleNamespace(
        event="on_turn_start", owner_id="1004025",
        condition_expr=eng._expr.compile(turn_hook["condition"]),
        effects=turn_hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    hp_before = hero.current_hp
    eng.bus.emit("on_turn_start", {"actor": "hero"}, eng.state)
    assert hp_before - hero.current_hp == pytest.approx(360.0)

    bad_task = dict(task)
    bad_task["DynamicValues"] = {}
    bad_sources = dict(sources)
    bad_sources["abilities"] = {"A": {"Name": "A", "OnStart": [bad_task]}}
    rejected = AbilityCompiler("1004025", skills, bad_sources).compile_skill("Skill04")
    assert not rejected["ok"]
    assert any("冻结追击倍率未注册" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_projectile_damage_freeze_and_pursued_damage():
    import types
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        "1004010", get_enemy_skills("1004010"), get_enemy_ability_sources("1004010"),
    ).compile_skill("Skill04")
    assert not any(issue["node_type"] == "RPG.GameCore.FireProjectile"
                   for issue in out["unsupported"])
    assert out["action"]["scaling"] == [{"atk": 1.5}]
    assert out["action"]["toughness_dmg"] == 10
    apply_effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                        if effect.get("effect_type") == "apply_modifier")
    assert apply_effect["modifier"]["duration"] == 2
    turn_hook = next(hook for hook in out["hooks"] if hook["event"] == "on_turn_start")
    assert turn_hook["effects"][0]["scaling_atk"] == 1.5

    eng = engine_vs_dummy(enemies=[make_dummy("1004010", atk=1000, crit_rate=0.0)])
    source = eng.state.actors["1004010"]
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, apply_effect, {"target": "hero"})
    assert hero.modifiers["MCommon_CTRL_Frozen"].prevent_action
    eng._compiled_hooks = [types.SimpleNamespace(
        event="on_turn_start", owner_id="1004010",
        condition_expr=eng._expr.compile(turn_hook["condition"]),
        effects=turn_hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    hp_before = hero.current_hp
    eng.bus.emit("on_turn_start", {"actor": "hero"}, eng.state)
    assert hp_before - hero.current_hp == pytest.approx(540.0)


@_need_ability
def test_real_wave_projectile_expands_to_action_instances():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim_schema.action import Action
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        "101401008", get_enemy_skills("101401008"), get_enemy_ability_sources("101401008"),
    ).compile_skill("Skill04")
    assert not any(issue["node_type"] in {"RPG.GameCore.FireWaveProjectile", "DamageMissing"}
                   for issue in out["unsupported"])
    assert out["action"]["damage_type"] == "physical"
    assert out["action"]["instances"] == 12
    assert out["action"]["scaling"] == [{"atk": 0.2}]
    assert out["action"]["toughness_dmg"] == 2

    eng = engine_vs_dummy(enemies=[make_dummy("101401008", atk=1000, crit_rate=0.0)])
    source = eng.state.actors["101401008"]
    hero = eng.state.actors["hero"]
    hp_before = hero.current_hp
    eng._execute_action(source, Action(**out["action"]), forced_target=hero)
    assert hp_before - hero.current_hp == pytest.approx(864.0)
    assert eng.state.damage_by_actor["101401008"] == pytest.approx(864.0)


@_need_ability
def test_real_all_team_member_speed_buff_targets_monsters():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim_schema.action import Action
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        "1004032", get_enemy_skills("1004032"), get_enemy_ability_sources("1004032"),
    ).compile_skill("Skill05")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["target_type"] == "ally_aoe"
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect.get("effect_type") == "apply_modifier")
    assert effect["modifier"]["modifier_type"] == "buff"
    assert effect["modifier"]["stat_effects"]["spd"] == 50.0

    eng = engine_vs_dummy(enemies=[make_dummy("1004032", spd=100), make_dummy("minion", spd=80)])
    source = eng.state.actors["1004032"]
    _primary, targets = eng._resolve_targets(source, Action(**out["action"]))
    assert {state.actor.actor_id for state in targets} == {"1004032", "minion"}
    eng._hooks._run_hook_effect(source, effect, {})
    for actor_id, base_spd in [("1004032", 100), ("minion", 80)]:
        target = eng.state.actors[actor_id]
        assert target.modifiers["MCommon_SpeedUp"].modifier_type == "buff"
        assert eng.pipeline.effective_stats(target)["spd"] == pytest.approx(base_spd + 50)
    assert eng.pipeline.effective_stats(eng.state.actors["hero"])["spd"] == pytest.approx(200)


@_need_ability
def test_real_vulnerability_modifier_remains_debuff():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "2002010", get_enemy_skills("2002010"), get_enemy_ability_sources("2002010"),
    ).compile_skill("Skill01")
    spec = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("modifier_id") == "MCommon_AllDamageTypeTakenRatio"
    )
    assert spec["modifier_type"] == "debuff"
    assert spec["stat_effects"]["vulnerability"] == 0.25


@_need_ability
def test_real_common_poison_modifier_from_global_config():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    sources = get_enemy_ability_sources("2022010")
    assert sources["modifiers"]["MCommon_DOT_Poison"]["MaxLayer"] == 5
    out = AbilityCompiler("2022010", get_enemy_skills("2022010"), sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = next(
        effect for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("modifier_id") == "ENEMY_202201001_POISON"
    )
    spec = effect["modifier"]
    assert spec["dot_element"] == "wind"
    assert spec["dot_ratio_expr"] == "0.5 * max(1, $modifier.stacks)"
    assert spec["duration"] == 3 and spec["stacks"] == 2 and spec["max_stack"] == 5

    eng = engine_vs_dummy(enemies=[make_dummy("2022010")])
    source = eng.state.actors["2022010"]
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, effect, {"target": "hero"})
    modifier = hero.modifiers["ENEMY_202201001_POISON"]
    assert modifier.stacks == 2 and modifier.max_stack == 5
    assert eng.pipeline.dot_tick_base(hero, modifier) == pytest.approx(1.0)


@_need_ability
def test_dot_visual_only_conditional_is_ignored():
    out = _real_compiler("4014036").compile_skill("Skill01")
    assert not any(issue["reason"] == "DoT 条件分支仅支持双分支对同一持有者键赋值"
                   for issue in out["unsupported"])


@_need_ability
def test_real_dot_current_hp_ratio_expression():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim.state import Modifier
    from hsr_nous.sim_schema.expression import parse
    from tests._builders import engine_vs_dummy

    out = AbilityCompiler(
        "4014030", get_enemy_skills("4014030"), get_enemy_ability_sources("4014030"),
    ).compile_skill("Skill02")
    assert not any("未注册 DoT 属性" in issue["reason"] or "DOT/DamageValue" in issue["path"]
                   for issue in out["unsupported"])
    spec = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("modifier_type") == "dot"
    )
    assert spec["modifier_id"] == "Monster_W4_Pollux_00_ThirstBlood"
    assert spec["dot_ratio_expr"] == "0.6 * (1 + ($self.hp / $self.max_hp))"

    eng = engine_vs_dummy()
    holder = eng.state.actors["hero"]
    modifier = Modifier(
        modifier_id=spec["modifier_id"], name=spec["name"], modifier_type="dot",
        dot_element=spec["dot_element"],
        dot_ratio_expr=parse(spec["dot_ratio_expr"], layer="effect"))
    holder.current_hp = 2500.0
    assert eng.pipeline.dot_tick_base(holder, modifier) == pytest.approx(0.9)
    holder.current_hp = 5000.0
    assert eng.pipeline.dot_tick_base(holder, modifier) == pytest.approx(1.2)


@_need_ability
@pytest.mark.parametrize(("enemy_id", "element"), [
    ("5013040", "quantum"), ("5013050", "fire"),
    ("5013060", "imaginary"), ("5013070", "physical"),
])
def test_readonly_custom_value_switch_selects_variant(enemy_id, element):
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        enemy_id, get_enemy_skills(enemy_id), get_enemy_ability_sources(enemy_id),
    ).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["damage_type"] == element
    assert out["action"]["scaling"] == [{"atk": 4.0}]
    assert out["action"]["toughness_dmg"] == 10


@_need_ability
def test_identical_conditional_damage_is_deduplicated():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "2034010", get_enemy_skills("2034010"), get_enemy_ability_sources("2034010"),
    ).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["damage_type"] == "thunder"
    assert out["action"]["scaling"] == [{"atk": 2.0}]
    assert out["action"]["toughness_dmg"] == 10
    assert "instances" not in out["action"]


@_need_ability
def test_real_conditional_followup_damage_uses_dynamic_count():
    import types
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        "1023021", get_enemy_skills("1023021"), get_enemy_ability_sources("1023021"),
    ).compile_skill("Skill11")
    assert not any(issue["node_type"] == "ConditionalDamage" for issue in out["unsupported"])
    assert out["action"]["scaling"] == [{"atk": 1.0}]
    damage_effects = [effect for hook in out["hooks"] for effect in hook["effects"]
                      if effect.get("effect_type") == "deal_damage"]
    assert [effect["scaling_atk"] for effect in damage_effects] == [1.0, 1.0, 2.0]

    eng = engine_vs_dummy(enemies=[make_dummy("1023021", atk=1000, crit_rate=0.0)])
    runtime = eng._enemy_policy_state.setdefault("1023021", {
        "seq_idx": 0, "cooldown_left": {}, "current_phase": 1, "dynamic_values": {},
    })
    runtime["dynamic_values"]["SummonMonsterEatCount"] = 3.0
    eng._compiled_hooks = [types.SimpleNamespace(
        event="on_action", owner_id="1023021",
        condition_expr=eng._expr.compile(hook["condition"]), effects=hook["effects"])
        for hook in out["hooks"] if hook["event"] == "on_action"]
    eng._hooks._subscribe_compiled_hooks()
    hero = eng.state.actors["hero"]
    hp_before = hero.current_hp
    eng.bus.emit("on_action", {
        "actor": "1023021", "action_id": "102302111", "actor_type": "monster",
    }, eng.state)
    assert hp_before - hero.current_hp == pytest.approx(720.0)
    assert eng.state.damage_by_actor["1023021"] == pytest.approx(720.0)


@_need_ability
def test_different_conditional_damage_stays_unsupported():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "3024020", get_enemy_skills("3024020"), get_enemy_ability_sources("3024020"),
    ).compile_skill("Skill02")
    # 决策卡 #33：条件主伤收编——ConditionalDamage 拒因清零
    assert not any(item["node_type"] == "ConditionalDamage" for item in out["unsupported"]), (
        f"条件主伤拒因应清零：{[i['reason'] for i in out['unsupported']]}")


@_need_ability
@pytest.mark.parametrize(("enemy_id", "key", "expected"), [
    ("2013010", "W2_Mecha03_00_SummonID", 2012010),
    ("201301002", "W2_Mecha03_00_SummonID", 202202003),
    ("1005012", "Monster_W1_CocoliaP2_00_SummonMonsterID01", 1002017),
])
def test_custom_value_summon_ids(enemy_id, key, expected):
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    real_sources = get_enemy_ability_sources(enemy_id)
    assert real_sources["custom_values"][key] == expected
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.SummonMonster", "SummonMonsterDataList": [{
                "MonsterIDFromCustomValue": {"Hash": dynamic_value_hash(key)},
            }],
        }]}},
        "modifiers": {}, "custom_values": real_sources["custom_values"],
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler(enemy_id, skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert [spec["enemy_template"] for spec in out["summons"]] == [str(expected)]


def test_summon_id_list_reserved_dynamic_hashes():
    skills, sources = _predicate_skill({})
    sources["summon_ids"] = [3003031, 3003041, 3003051]
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SummonMonster",
        "SummonMonsterDataList": [{
            "MonsterID": _dynamic("AQAR", hashes=[1509106746 + index]),
            "LocationType": location,
        } for index, location in enumerate(("First", "Last", "BeforeCaster"))],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert [spec["enemy_template"] for spec in out["summons"]] == [
        "3003031", "3003041", "3003051"]

    sources["summon_ids"] = [3003031]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    reasons = [issue["reason"] for issue in rejected["unsupported"]]
    assert "未知 DynamicHash：1509106747" in reasons
    assert "未知 DynamicHash：1509106748" in reasons
    assert "未知 DynamicHash：1509106746" not in reasons


def test_last_die_summon_uses_death_target_position():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.compile.compiled import SummonDef
    from tests._builders import engine_vs_dummy, make_dummy

    task = {
        "$type": "RPG.GameCore.SummonMonster",
        "SummonMonsterDataList": [{"MonsterID": 2022072, "LocationType": "LastDie"}],
    }
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_kill")
    compiler._compile_summon_monster(task, ctx, "summon", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    summon_id = effect["summon_id"]
    assert effect == {
        "effect_type": "summon", "summon_id": summon_id,
        "position": "last_die", "summon_group": "fake:summon",
    }
    assert any("LastDie" in issue["reason"] for issue in _task_skill(task)["unsupported"])

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("left"), make_dummy("dead"), make_dummy("right")])
    eng.state.actors["dead"].alive = False
    eng.summon_defs = {
        summon_id: SummonDef(owner_id="source", actor=make_dummy(summon_id), inheritance="none"),
        "other": SummonDef(owner_id="source", actor=make_dummy("other"), inheritance="none"),
    }
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {"target": "dead"})
    assert list(eng.state.actors) == ["hero", "source", "left", summon_id, "dead", "right"]
    assert [state.actor.actor_id for state in eng._enemies_alive()] == [
        "source", "left", summon_id, "right"]
    with pytest.raises(ValueError, match="last_die"):
        eng._hooks._run_hook_effect(eng.state.actors["source"], {
            "effect_type": "summon", "summon_id": "other", "position": "last_die"}, {})


def test_formation_record_summon_uses_recorded_position_and_clear():
    from hsr_nous.sim.compile.compiled import SummonDef
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.RecordEntityFormationIndex",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
    }, {
        "$type": "RPG.GameCore.SummonMonster",
        "SummonMonsterDataList": [{"MonsterID": 2022072, "LocationType": "FormationRecord"}],
    }, {
        "$type": "RPG.GameCore.ClearRecordEntityFormation", "Team": "TeamDark",
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    assert [effect["effect_type"] for effect in effects] == [
        "record_formation_index", "summon", "set_dynamic_value"]

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("left"), make_dummy("right")])
    source = eng.state.actors["source"]
    summon_id = out["summons"][0]["summon_id"]
    eng.summon_defs = {
        summon_id: SummonDef(owner_id="source", actor=make_dummy(summon_id), inheritance="none"),
    }
    payload = {"target": "left"}
    eng._hooks._run_hook_effect(source, effects[0], payload)
    level = eng._enemy_policy_state["$level"]["dynamic_values"]
    assert level["_FormationRecord:dark"] == 2.0
    eng._hooks._run_hook_effect(source, effects[1], payload)
    assert list(eng.state.actors) == ["hero", "source", summon_id, "left", "right"]
    eng._hooks._run_hook_effect(source, effects[2], payload)
    assert level["_FormationRecord:dark"] == 0.0


def test_last_summon_group_targets_latest_group_and_survives_save_load():
    from hsr_nous.sim.compile.compiled import SummonDef
    from tests._builders import engine_vs_dummy, make_dummy

    reduced = _task_skill({
        "$type": "RPG.GameCore.ReduceStanceRatio",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LastSummonMonsters"},
        "ReduceValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
    })
    assert reduced["ok"] and not reduced["unsupported"]
    reduce_effect = reduced["hooks"][0]["effects"][0]
    assert reduce_effect["target"] == {"pool": "last_summons"}
    phased = _task_skill({
        "$type": "RPG.GameCore.SetMonsterPhase",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LastSummonMonsters"},
        "PhaseNum": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    assert phased["ok"] and not phased["unsupported"]
    assert phased["hooks"][0]["effects"][0]["target"] == {"pool": "last_summons"}
    from hsr_nous.adapters.enemy_ability import _Context
    compiler = AbilityCompiler("fake", [], {})
    ctx = _Context(mode="event", skill={}, event="on_turn_end")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareMonsterRank",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LastSummonMonsters"},
        "CompareType": "GreaterEqual",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 3}},
    }, ctx, "P")
    assert expression is not None and not ctx.unsupported
    assert 'count_selected("last_summons"' in expression

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng.summon_defs = {
        sid: SummonDef(owner_id="source", actor=make_dummy(sid), inheritance="none")
        for sid in ("s1", "s2", "s3")
    }
    for sid in ("s1", "s2"):
        eng._hooks._run_hook_effect(source, {
            "effect_type": "summon", "summon_id": sid,
            "summon_group": "g1", "position": "last"}, {})
    selected = eng._hooks._hook_target_states({"pool": "last_summons"}, source, {})
    assert [state.actor.actor_id for state in selected] == ["s1", "s2"]
    eng._hooks._run_hook_effect(source, reduce_effect, {})
    assert eng.state.actors["s1"].toughness == pytest.approx(4999.5)
    assert eng.state.actors["s2"].toughness == pytest.approx(4999.5)

    eng._hooks._run_hook_effect(source, {
        "effect_type": "summon", "summon_id": "s3",
        "summon_group": "g2", "position": "last"}, {})
    selected = eng._hooks._hook_target_states({"pool": "last_summons"}, source, {})
    assert [state.actor.actor_id for state in selected] == ["s3"]

    from hsr_nous.sim.save_load import _decode
    from hsr_nous.sim.state import BattleState
    restored = _decode(BattleState, eng.save_state()["state"], eng._expr)
    assert restored.last_summon_group == "g2"
    assert restored.last_summon_ids == ["s3"]


def test_dynamic_summon_selects_only_registered_candidate():
    from hsr_nous.sim.compile.compiled import SummonDef
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    key = "_SummonChoice"
    skills, sources = _predicate_skill({})
    sources["summon_ids"] = [2022071, 2022072]
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValue",
        "DynamicKey": {"Value": key},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }, {
        "$type": "RPG.GameCore.SummonMonster",
        "SummonMonsterDataList": [{
            "MonsterID": _dynamic("AQAR", hashes=[dynamic_value_hash(key)]),
            "LocationType": "Last",
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert [spec["enemy_template"] for spec in out["summons"]] == ["2022071", "2022072"]
    effect = out["hooks"][0]["effects"][-1]
    assert effect["summon_id_source"] == "dynamic_of($self.actor_id, '_SummonChoice')"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng.summon_defs = {
        spec["summon_id"]: SummonDef(
            owner_id="source", actor=make_dummy(spec["summon_id"]), inheritance="none")
        for spec in out["summons"]
    }
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": key, "amount": 2022072}, {})
    eng._hooks._run_hook_effect(source, effect, {})
    assert out["summons"][1]["summon_id"] in eng.state.actors
    assert out["summons"][0]["summon_id"] not in eng.state.actors

    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": key, "amount": 999}, {})
    with pytest.raises(ValueError, match="候选闭集"):
        eng._hooks._run_hook_effect(source, effect, {})

    sources["summon_ids"] = []
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("候选闭集" in issue["reason"] for issue in rejected["unsupported"])


def test_mapped_callback_registers_summon_declaration():
    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Death"},
        }]}},
        "modifiers": {"Death": {"_CallbackList": [{
            "Event": "OnDeathrattle",
            "CallbackConfig": [{
                "$type": "RPG.GameCore.SummonMonster",
                "SummonMonsterDataList": [{"MonsterID": 2022072, "LocationType": "Last"}],
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    assert len(out["summons"]) == 1
    summon_id = out["summons"][0]["summon_id"]
    effect = next(effect for hook in out["hooks"] if hook["event"] == "on_kill"
                  for effect in hook["effects"] if effect["effect_type"] == "summon")
    assert effect == {
        "effect_type": "summon", "summon_id": summon_id, "position": "last",
        "summon_group": "fake:P/OnStart/0/_CallbackList/0/OnDeathrattle/0",
    }


@_need_ability
def test_real_modifier_flags_map_to_existing_lifecycle_fields():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources

    real = get_enemy_ability_sources("2013010")

    def compile_modifier(name, dynamic_values=None):
        sources = {
            "character_config": {"SkillList": [{
                "Name": "Skill01", "SkillType": "Skill",
                "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
            }]},
            "abilities": {"A": {"Name": "A", "OnStart": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "ModifierName": {"Value": name}, "DynamicValues": dynamic_values or {},
            }, {
                "$type": "RPG.GameCore.PredicateTaskList",
                "Predicate": {"$type": "RPG.GameCore.ByIsContainModifier",
                              "ModifierName": {"Value": name}},
            }]}},
            "modifiers": {name: real["modifiers"][name]},
        }
        skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
        out = AbilityCompiler("2013010", skills, sources).compile_skill("Skill01")
        return out

    overdrive_result = compile_modifier(
        "MMonster_W2_Mecha03_00_Overdrive_On",
        {"MDF_SpeedAddedValue": {"IsDynamic": False, "FixedValue": {"Value": 30}}},
    )
    assert overdrive_result["ok"] and not overdrive_result["unsupported"]
    overdrive = overdrive_result["hooks"][0]["effects"][0]["modifier"]
    assert overdrive["toughness_lock"] and overdrive["stat_effects"] == {"spd": 30}
    assert [(effect["dynamic_key"], effect["amount"]) for effect in overdrive["on_apply"]] == [
        ("W2_Mecha03_00_Overdrive_State", 2), ("W2_Mecha03_00_AICounter", 2),
    ]
    assert [(effect["dynamic_key"], effect["amount"]) for effect in overdrive["on_remove"]] == [
        ("W2_Mecha03_00_Overdrive_State", 0), ("W2_Mecha03_00_AICounter", 1),
    ]
    sign_result = compile_modifier("Monster_W2_Mecha03_00_Sign")
    assert sign_result["ok"] and not sign_result["unsupported"]
    sign = sign_result["hooks"][0]["effects"][0]["modifier"]
    assert sign["lock_on"] and sign["remove_on_source_death"]


def test_attack_sign_with_onstack_callback_preserves_lock_on():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "ModifierName": {"Value": "ChargeTarget"},
    }, modifiers={"ChargeTarget": {
        "BehaviorFlagList": ["AttackSign"],
        "_CallbackList": [{"Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicEntityParam",
            "DynamicKey": "ChargeTarget_DynamicTarget",
            "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "ParamTargetType": {"$type": "RPG.GameCore.TargetFetchUniqueNameEntity",
                                "UniqueName": "W4_Serpent_01"},
        }]}],
    }})
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["lock_on"] and effect["modifier"]["modifier_type"] == "debuff"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {"target": "hero"})
    assert eng.state.actors["hero"].modifiers["ENEMY_s1_LOCK_ON"].lock_on


def test_before_actor_exit_self_force_kill_is_noop():
    from hsr_nous.adapters.enemy_ability import _Context

    compiler = AbilityCompiler("fake", [], {})
    ctx = _Context(mode="event", skill={"skill_id": "s1"}, event="before_actor_exit")
    compiler._compile_force_kill({
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }, ctx, "probe", ())
    assert not ctx.effects and not ctx.unsupported


def test_force_kill_preserves_target_sequence():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.ForceKill",
        "TargetType": {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByIsContainModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "Mark"},
            }},
        ]},
    }, modifiers={"Mark": {}})
    assert out["ok"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "set_hp_to_percent"
    assert effect["target"] == {"pool": "allies", "where": "has_modifier($it, 'Mark')"}
    eng = engine_vs_dummy(enemies=[make_dummy("source")], allies=[make_actor("ally")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    hero.modifiers["Mark"] = Modifier(modifier_id="Mark", name="Mark", modifier_type="debuff")
    eng._hooks._run_hook_effect(source, effect, {})
    assert not hero.alive and eng.state.actors["ally"].alive


@_need_ability
def test_conditional_on_destroy_preserves_dynamic_guard():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources

    real = get_enemy_ability_sources("1012041")
    name = "Monster_W1_SvarogPart_00_RL_CountDown"
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": name},
        }]}},
        "modifiers": {name: real["modifiers"][name]},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("1012041", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["modifier"]["on_remove"] == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "PartDecisionFlag", "amount": 2,
        "condition": "dynamic_of($self, 'PartDecisionFlag') == 1",
    }]


@_need_ability
def test_on_create_loop_stays_in_lifecycle_slot():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "3003032", get_enemy_skills("3003032"), get_enemy_ability_sources("3003032"),
    ).compile_skill("Skill04")
    assert not any(issue["node_type"] == "OnCreate" for issue in out["unsupported"])
    charge = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"]["modifier_id"] == "Monster_W3_Figure_02_RLElite_ChargeLayer")
    assert len(charge["on_apply"]) == 7
    assert all(effect["effect_type"] == "apply_modifier" for effect in charge["on_apply"])


@_need_ability
@pytest.mark.parametrize(("trigger", "semantic_name"), [
    ("Skill09", "Disintegration Order"), ("Skill11", "Dismantle"),
])
def test_direwolf_dot_matches_frozen_legacy_baseline(trigger, semantic_name):
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    semantics = _semantic("1013020", "Automaton Direwolf")[semantic_name]
    skills = get_enemy_skills("1013020")
    compiler = AbilityCompiler("1013020", skills, get_enemy_ability_sources("1013020"),
                               semantics={trigger: semantics})
    out = compiler.compile_skill(trigger)
    skill_id = "101302003" if trigger == "Skill09" else "101302004"
    assert out["ok"] and not out["unsupported"]
    assert out["action"] == {
        "action_id": skill_id, "name": semantic_name, "action_type": "skill",
        "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 2.5}],
        "toughness_dmg": 10, "energy_gain": 0, "energy_grant": 10.0,
    }
    assert out["hooks"] == [{
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{skill_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "$event.target", "apply_chance": 1.0,
            "modifier": {
                "modifier_id": f"ENEMY_{skill_id}_BLEED", "name": "Bleed",
                "modifier_type": "dot", "dot_element": "physical",
                "dot_ratio_expr": "0.05 * $self.max_hp * max(1, $modifier.stacks)",
                "dot_base_chance": 1.0, "stacks": 1, "duration": 2, "max_stack": 10,
                "stack_mode": "refresh", "dispellable": True,
                "behavior_flags": ["STAT_DOT", "STAT_DOT_Bleed"],
                "dynamic_values": {"Modifier_Bleed_DamagePercentage": 0.05, "MDF_MaxLayer": 10.0},
            },
        }],
    }]


@_need_ability
@pytest.mark.parametrize(("enemy_id", "skill_id", "name", "ratio", "toughness", "energy"), [
    ("2013010", "201301003", "Restraint", 3.0, 10, 10.0),
    ("3002040", "300204003", "Wake-Up Punch", 2.5, 10, 10.0),
    ("4022010", "402201001", "Pierce the Night Sky", 2.0, 5, 5.0),
])
def test_pure_direct_skill_matches_legacy_semantic_guard(
        enemy_id, skill_id, name, ratio, toughness, energy):
    from hsr_nous.adapters import template_generator as generator

    template = generator.generate_enemy_template(enemy_id)
    action = next(a for a in template["actions"] if a["action_id"] == skill_id)
    assert action["name"] == name
    assert action["scaling"] == [{"atk": ratio}]
    assert action["toughness_dmg"] == toughness and action["energy_grant"] == energy


@_need_ability
def test_wake_up_alarm_compiles_immediate_action_and_shared_removals():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    semantics = _semantic("3002040", "Dreamjolt Troupe's Winder Goon")["Wake-Up Alarm"]
    out = AbilityCompiler("3002040", get_enemy_skills("3002040"),
                          get_enemy_ability_sources("3002040"),
                          semantics={"Skill02": semantics}).compile_skill("Skill02")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[0] == {
        "effect_type": "immediate_action",
        "target": {"pool": "enemies", "where": "$it.actor_id != $self.actor_id"},
    }
    assert [effect["modifier_id"] for effect in effects[1:]] == [
        "MMonster_W3_Clock_00_Skill01_Charge",
        "MMonster_W3_Clock_00_Skill01_Charge_Effect",
    ]


def test_camera_only_predicate_and_source_limited_removal():
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill02", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "SuccessTaskList": [{"$type": "RPG.GameCore.TriggerAbility",
                                 "AbilityName": {"Value": "Demo_Camera_Special"}}],
            "FailedTaskList": [{"$type": "RPG.GameCore.TriggerAbility",
                                "AbilityName": {"Value": "Demo_Camera"}}],
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s2", "trigger_key": "Skill02", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill02")
    assert out["ok"] and not out["unsupported"]

    sources["abilities"]["A"]["OnStart"].append({
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Shared"}, "OnlyRemoveCasterAdded": True,
    })
    sources["modifiers"]["Shared"] = {"BehaviorFlagList": []}
    accepted = AbilityCompiler("fake", skills, sources).compile_skill("Skill02")
    assert accepted["ok"]
    assert accepted["hooks"][0]["effects"][-1]["filter"] == "$mod.source == $self.actor_id"


@_need_ability
def test_real_xuanlu_branch_heal_hp_in_engine():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        "2022090", get_enemy_skills("2022090"), get_enemy_ability_sources("2022090"),
    ).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    assert effects == [{"effect_type": "heal", "target": "all_enemies", "ratio": 0.25, "amount": 0}]

    eng = engine_vs_dummy(enemies=[make_dummy("2022090", hp=4000, max_toughness=120)])
    enemy = eng.state.actors["2022090"]
    enemy.current_hp = 1000.0
    for effect in effects:
        eng._hooks._run_hook_effect(enemy, effect, {})
    assert enemy.current_hp == pytest.approx(2000.0)


@_need_ability
def test_real_if_xuanlu_heals_only_own_summons():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "2024016", get_enemy_skills("2024016"), get_enemy_ability_sources("2024016"),
    ).compile_skill("Skill09")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    assert len(effects) == 1
    assert effects[0]["target"] == {
        "pool": "enemies", "where": "$it.summoner_id == $self.actor_id"}
    assert effects[0]["ratio"] == pytest.approx(0.015)


@_need_ability
def test_real_shadewalker_modify_action_delay_compiles():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        "1022010", get_enemy_skills("1022010"), get_enemy_ability_sources("1022010"),
    ).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    delays = [effect for hook in out["hooks"] for effect in hook["effects"]
              if effect["effect_type"] == "delay_action"]
    assert delays == [{"effect_type": "delay_action", "target": "$event.target", "amount": 50.0}]


@_need_ability
def test_real_bananadvisor_advance_action_in_engine():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_dummy

    out = AbilityCompiler(
        "3002041", get_enemy_skills("3002041"), get_enemy_ability_sources("3002041"),
    ).compile_skill("Skill02")
    assert out["ok"] and not out["unsupported"]
    advances = [effect for hook in out["hooks"] for effect in hook["effects"]
                if effect["effect_type"] == "advance_action"]
    assert advances == [{"effect_type": "advance_action", "target": "all_enemies", "amount": 50.0}]

    eng = engine_vs_dummy(enemies=[make_dummy("3002041"), make_dummy("partner")])
    for effect in advances:
        eng._hooks._run_hook_effect(eng.state.actors["3002041"], effect, {})
    for actor_id in ("3002041", "partner"):
        handle = eng.scheduler.handle_of(actor_id)
        assert eng.scheduler._remaining[handle] == pytest.approx(5000.0)


@_need_ability
def test_real_modify_action_delay_honours_except_this_unit():
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_ability_sources, get_enemy_skills, get_monster_meta,
    )

    enemy_id = "2034010"
    semantic = _semantic(enemy_id, get_monster_meta(enemy_id)["en"])["Barrenness of Earth Gouged"]
    out = AbilityCompiler(
        enemy_id, get_enemy_skills(enemy_id), get_enemy_ability_sources(enemy_id),
        semantics={"Skill04": semantic},
    ).compile_skill("Skill04")
    assert out["ok"] and not out["unsupported"]
    delays = [effect for hook in out["hooks"] for effect in hook["effects"]
              if effect["effect_type"] == "delay_action"]
    assert [(effect["target"], effect["amount"]) for effect in delays] == [
        ("all_allies", 20.0),
        ({"pool": "enemies", "where": "$it.actor_id != $self.actor_id"}, 30.0),
    ]


@_need_ability
def test_real_domescreen_modify_sp_energy_forms():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    compiler = AbilityCompiler(
        "3002010", get_enemy_skills("3002010"), get_enemy_ability_sources("3002010"),
    )
    restored = compiler.compile_skill("Skill01")
    consumed = compiler.compile_skill("Skill02")
    assert restored["ok"] and not restored["unsupported"]
    assert consumed["ok"] and not consumed["unsupported"]
    assert restored["hooks"][0]["effects"] == [{
        "effect_type": "gain_energy", "target": "$event.target",
        "amount": "0.5 * $target.max_energy",
    }]
    assert consumed["hooks"][0]["effects"] == [{
        "effect_type": "consume_energy",
        "target": {"pool": "allies", "where": "not $it.summoner_id"},
        "amount": "0.2 * $target.max_energy",
    }]


@_need_ability
def test_real_fortune_seller_energy_dedupes_memosprite():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = AbilityCompiler(
        "3002020", get_enemy_skills("3002020"), get_enemy_ability_sources("3002020"),
    ).compile_skill("Skill02")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]
               if effect["effect_type"] == "gain_energy"]
    assert effects == [{
        "effect_type": "gain_energy",
        "target": {"pool": "allies", "where": "not $it.summoner_id"}, "amount": 20.0,
    }]

    memo = make_actor("memo", max_energy=100)
    memo.actor_type = "summon"
    memo.summoner_id = "hero"
    eng = engine_vs_dummy(
        hero=make_actor("hero", max_energy=100, energy_regen=1.2),
        allies=[memo], enemies=[make_dummy("3002020")],
    )
    for effect in effects:
        eng._hooks._run_hook_effect(eng.state.actors["3002020"], effect, {})
    assert eng.state.actors["hero"].current_energy == pytest.approx(24.0)
    assert eng.state.actors["memo"].current_energy == 0.0


@_need_ability
def test_real_fortune_seller_skill_points_and_energy():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    compiler = AbilityCompiler(
        "3002020", get_enemy_skills("3002020"), get_enemy_ability_sources("3002020"),
    )
    basic = compiler.compile_skill("Skill01")
    combo = compiler.compile_skill("Skill03")
    assert basic["ok"] and not basic["unsupported"]
    assert basic["hooks"][0]["effects"] == [{"effect_type": "gain_skill_point", "amount": 2}]
    assert combo["ok"] and not combo["unsupported"]
    effects = [effect for hook in combo["hooks"] for effect in hook["effects"]]
    assert [effect for effect in effects if effect["effect_type"] == "gain_skill_point"] == [{
        "effect_type": "gain_skill_point", "amount": 2,
    }]
    assert [effect for effect in effects if effect["effect_type"] == "gain_energy"] == [{
        "effect_type": "gain_energy",
        "target": {"pool": "allies", "where": "not $it.summoner_id"}, "amount": 20.0,
    }]

    eng = engine_vs_dummy(
        hero=make_actor("hero", max_energy=100, energy_regen=1.2),
        enemies=[make_dummy("3002020")], initial_sp=3,
    )
    for effect in effects:
        eng._hooks._run_hook_effect(eng.state.actors["3002020"], effect, {})
    assert eng.state.skill_points == 5
    assert eng.state.actors["hero"].current_energy == pytest.approx(24.0)


@_need_ability
def test_direwolf_compiled_dot_stacks_in_engine(tmp_path):
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    from hsr_nous.sim import CombatEngine, MODE_EXPECTED
    from hsr_nous.sim.compile import compile_encounter
    semantics = _semantic("1013020", "Automaton Direwolf")["Disintegration Order"]
    compiler = AbilityCompiler("1013020", get_enemy_skills("1013020"),
                               get_enemy_ability_sources("1013020"),
                               semantics={"Skill09": semantics})
    converted = compiler.compile_skill("Skill09")
    template = generate_enemy_template("1013020")
    template.update({
        "actions": [converted["action"]], "hooks": converted["hooks"],
        "policy": {"sequence": ["101302003"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1013020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 100000, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1013020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hero = engine.state.actors["hero"]
    enemy = engine.state.actors["1013020"]
    engine._enemy_turn(enemy)
    modifier = hero.modifiers["ENEMY_101302003_BLEED"]
    assert modifier.stacks == 1
    assert engine.pipeline.dot_tick_base(hero, modifier) == pytest.approx(5000.0)
    engine._enemy_turn(enemy)
    assert modifier.stacks == 2
    assert engine.pipeline.dot_tick_base(hero, modifier) == pytest.approx(10000.0)


@_need_ability
def test_lesser_sting_deathrattle_compiles_complete_chain():
    """被动通道：on_kill 亡语钩保留，缺省全清与分支效果均已收编。"""
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    compiler = AbilityCompiler("8022020", get_enemy_skills("8022020"),
                               get_enemy_ability_sources("8022020"))
    out = compiler.compile_passive("Monster_SW_Minion01_01_Passive01", "802202004")
    assert out["ok"] and not out["unsupported"]
    kill_hooks = [hook for hook in out["hooks"] if hook["event"] == "on_kill"]
    assert kill_hooks, f"亡语钩应保留：{[h['event'] for h in out['hooks']]}"
    damage = next(effect for effect in kill_hooks[0]["effects"]
                  if effect["effect_type"] == "deal_damage")
    assert damage["scaling_hp"] == pytest.approx(0.6)
    assert damage["toughness_dmg"] == pytest.approx(30.0)
    unsupported = {item["node_type"] for item in out["unsupported"]}
    assert "RPG.GameCore.PredicateTaskList" not in unsupported
    assert "RPG.GameCore.DispelStatus" not in unsupported
    assert any(effect["effect_type"] == "remove_modifier" and effect["filter"] == "1 == 1"
               for effect in kill_hooks[0]["effects"])
    assert any(effect["effect_type"] == "apply_modifier"
               for hook in kill_hooks for effect in hook["effects"])


@_need_ability
def test_if_lesser_sting_references_resolve():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources
    sources = get_enemy_ability_sources("8022021")
    for name in ("Monster_SW_Minion01_01_IF_Skill02_Phase01",
                 "Monster_SW_Minion01_01_IF_SkillP01"):
        assert name in sources["abilities"]
        assert name not in sources["missing_abilities"]
    assert not sources["ambiguous"]


# ---------------------------------------------------------------------------
# 执行帧感知翻译（#26 期 2/3）：真实样例编译产物结构钉 + 引擎级行为钉
# ---------------------------------------------------------------------------

def _real_compiler(enemy_id: str) -> AbilityCompiler:
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    return AbilityCompiler(enemy_id, get_enemy_skills(enemy_id),
                           get_enemy_ability_sources(enemy_id), level=80)


def _effects_with(hooks, effect_type):
    return [effect for hook in hooks for effect in hook.get("effects", [])
            if effect.get("effect_type") == effect_type]


@_need_ability
def test_real_sw_boss_probability_branch_compiles_bind_roll():
    """真实 SW_Boss_00（8024010）ByRandomChance(0.5) 召唤分支——
    单 hook + bind_roll 在前 + Success/Failed 互补 roll 守卫（effect 级）。"""
    result = _real_compiler("8024010").compile_enemy()
    hooks = [hook for hook in result["hooks"]
             if any(effect.get("effect_type") == "bind_roll"
                    for effect in hook.get("effects", []))]
    assert hooks, "应编译出概率分支 hook"
    hook = hooks[0]
    effects = hook["effects"]
    assert effects[0]["effect_type"] == "bind_roll"
    key = effects[0]["roll_key"]
    assert key and "'" not in key
    guards = [effect.get("condition", "") for effect in effects[1:]]
    assert any(f"roll('{key}') < 0.5" in guard for guard in guards), guards
    assert any(f"roll('{key}') >= 0.5" in guard for guard in guards), guards
    # bind 无条件（守卫在分支效果上），且任何 effect 不丢 hook 级基础条件
    assert "condition" not in effects[0]


@_need_ability
def test_real_sw_boss_write_then_read_guard_is_effect_level():
    """真实 SW_Boss_00 写后读（Skill02_Phase02 Loop 分支：Set 后再 ByCompare）编译为
    effect 级活读——旧"旧事件快照"拒因位置（Skill02First 键）现为 dynamic_of 守卫."""
    result = _real_compiler("8024010").compile_enemy()
    conditioned = [effect for effect in _effects_with(result["hooks"], "set_dynamic_value")
                   if "Skill02First" in str(effect.get("condition", ""))]
    assert conditioned, "写后读守卫应落在效果级 condition"
    assert all(effect["condition"] == "dynamic_of($self, 'Skill02First') == 1"
               for effect in conditioned)


@_need_ability
def test_real_sw_boss_skill02_phase02_no_write_read_rejection():
    """旧拒因"同一技能写入后读取动态值会命中旧事件快照"在真实敌人上退役."""
    result = _real_compiler("8024010").compile_enemy()
    assert not any("旧事件快照" in item["reason"] for item in result["unsupported"])


@_need_ability
def test_real_cocolia_if_02_switch_live_guards():
    """真实 CocoliaP1_00_IF_02（1004014）SwitchCaseByDynamicValue(SummonCount)——
    活读翻译：Case 效果带 dynamic_of 等值守卫。"""
    result = _real_compiler("1004014").compile_enemy()
    assert not any("运行时 Switch 尚未注册" in item["reason"]
                   for item in result["unsupported"])
    guarded = [effect for hook in result["hooks"]
               for effect in hook.get("effects", [])
               if "dynamic_of($self, 'SummonCount') ==" in str(effect.get("condition", ""))]
    assert guarded, "Switch 活读守卫应出现在效果级 condition"


@_need_ability
def test_switch_by_attack_damage_type_guards_real_effects():
    from tests._builders import engine_vs_dummy, make_dummy

    real = _real_compiler("5013030").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.SwitchCaseByAttackDamageType"
                   for item in real["unsupported"])
    assert any("$event.damage_type == 'fire'" in str(effect.get("condition", ""))
               for hook in real["hooks"] for effect in hook.get("effects", []))

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Listener"},
    }]
    def write(value):
        return [{
            "$type": "RPG.GameCore.DefineDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "DynamicKey": {"Value": "Color"},
            "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
        }]
    sources["modifiers"] = {"Listener": {"_CallbackList": [{
        "Event": "OnAfterBeingHitAll",
        "CallbackConfig": [{
            "$type": "RPG.GameCore.SwitchCaseByAttackDamageType",
            "Source": {"SourceType": "ReadTargetType", "ReadTargetType": {
                "$type": "RPG.GameCore.TargetAlias", "Alias": "DamageAttackerEntity"}},
            "CaseTaskList": [
                {"Case": "Fire", "TaskList": write(1)},
                {"Case": "Ice", "TaskList": write(2)},
            ],
            "DefaultTaskList": write(3),
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    spec = next(effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
                if effect.get("effect_type") == "apply_modifier")
    listener = next(hook for hook in out["hooks"] if hook["event"] == "after_being_hit"
                    and any(effect.get("dynamic_key") == "Color"
                            for effect in hook.get("effects", [])))
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._apply_modifier_spec(source, spec, source)
    for damage_type, expected in (("fire", 1), ("ice", 2), ("wind", 3)):
        payload = {"source": "hero", "target": "source", "damage_type": damage_type}
        for effect in listener["effects"]:
            eng._hooks._run_hook_effect(source, effect, payload)
        assert eng._hooks._hook_amount(
            "dynamic_of($self.actor_id, 'Color')", source, {}) == expected


@_need_ability
def test_reference_modifier_definition_is_loaded_and_compiled_with_slot_id():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    real_sources = get_enemy_ability_sources("5013030")
    assert "MMonster_W5_Peacock_00_SkillP01_Color_Red" in real_sources["modifiers"]
    real = AbilityCompiler("5013030", get_enemy_skills("5013030"),
                           real_sources, level=80).compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.AddModifier"
                   and "Color_Slot" in item["reason"] for item in real["unsupported"])

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Slot"},
        "ReferenceModifierName": "Reference",
    }]
    sources["modifiers"] = {"Reference": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "Property": "AttackAddedRatio",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.2}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    spec = next(effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
                if effect.get("effect_type") == "apply_modifier")
    assert spec["modifier_id"] == "Slot"
    assert spec["stat_effects"]["atk_pct"] == pytest.approx(0.2)


@_need_ability
def test_real_cocolia_add_clamp_expression_compiles():
    """真实 Cocolia IF_02 的 AddValue 钳制编译产物——同敌 Boss_Cocolia_BattleScore1
    回调（AddValue=1, Min=0, Max=5）落在编译产物里：min/max 内联组合、读旧值走
    dynamic_of（帧覆盖层优先=帧内累积）。卡 #26 点名样例 MinionCount(-1/0/4) 所在
    modifier 回调因同技能其他拒因（LastSummonMonsters 目标别名）未达编译，其形状由
    test_add_clamp_minion_count_shape 单元件钉。"""
    result = _real_compiler("1004014").compile_enemy()
    amounts = [effect.get("amount") for effect in
               _effects_with(result["hooks"], "set_dynamic_value")]
    clamped = [amount for amount in amounts
               if isinstance(amount, str) and amount.startswith("min(max(")]
    assert clamped, f"钳制表达式未编译出：{amounts}"
    assert any("dynamic_of($self, 'FrozenScore') + (1)" in amount
               and amount.endswith("), (0)), (5))") for amount in clamped), clamped


def test_add_clamp_minion_count_shape():
    """卡 #26 点名样例形状钉：Cocolia MinionCount AddValue=-1, Min=0, Max=4
    （真实节点取自 Monster_W1_CocoliaP1_00_IF_02_Ability.json，此处经最小件复现其
    完整字段）——钳制内联表达式逐字钉。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.SetDynamicValueByAddValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "Key": {"Value": "MinionCount"},
            "AddValue": {"IsDynamic": False, "FixedValue": {"Value": -1}},
            "Min": {"IsDynamic": False, "FixedValue": {"Value": 0}},
            "Max": {"IsDynamic": False, "FixedValue": {"Value": 4}},
            "ContextScope": "TargetEntity",
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    (effect,) = _effects_with(out["hooks"], "set_dynamic_value")
    assert effect["dynamic_key"] == "MinionCount"
    assert effect["amount"] == "min(max(dynamic_of($self, 'MinionCount') + (-1), (0)), (4))"


def test_random_config_presentation_only_consumes_nothing():
    """真实 SW_Boss_01 RandomConfig 壳（0.333/0.333/0.334，选项全表现）——
    纯表现权重掷不消耗随机流、不产 bind_roll。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.RandomConfig",
            "OddsList": [
                {"IsDynamic": False, "FixedValue": {"Value": 0.333}},
                {"IsDynamic": False, "FixedValue": {"Value": 0.333}},
                {"IsDynamic": False, "FixedValue": {"Value": 0.334}},
            ],
            "TaskList": [
                [{"$type": "RPG.GameCore.TriggerEffect", "EffectPath": "fx/1"}],
                [{"$type": "RPG.GameCore.TriggerEffect", "EffectPath": "fx/2"}],
                [{"$type": "RPG.GameCore.TriggerEffect", "EffectPath": "fx/3"}],
            ],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert not _effects_with(out["hooks"], "bind_roll")


def test_random_config_weighted_translation_structure():
    """加权掷翻译结构（真实壳+机制替换件：语料中普通 RandomConfig 选项全为表现，
    机制内容按真实 OddsList 壳替换）——bind scale=Σ权重，守卫为累计权重区间。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.RandomConfig",
            "OddsList": [
                {"IsDynamic": False, "FixedValue": {"Value": 0.333}},
                {"IsDynamic": False, "FixedValue": {"Value": 0.333}},
                {"IsDynamic": False, "FixedValue": {"Value": 0.334}},
            ],
            "TaskList": [
                [{"$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "P"},
                  "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
                [{"$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "P"},
                  "Value": {"IsDynamic": False, "FixedValue": {"Value": 2}}}],
                [{"$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "P"},
                  "Value": {"IsDynamic": False, "FixedValue": {"Value": 3}}}],
            ],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effects = out["hooks"][0]["effects"]
    binds = [effect for effect in effects if effect["effect_type"] == "bind_roll"]
    assert len(binds) == 1 and binds[0]["scale"] == pytest.approx(1.0)
    key = binds[0]["roll_key"]
    guards = [effect.get("condition", "") for effect in effects
              if effect["effect_type"] == "set_dynamic_value"]
    assert guards[0] == f"roll('{key}') <= 0.333"
    assert guards[1] == f"roll('{key}') > 0.333 and roll('{key}') <= 0.666"
    assert guards[2] == f"roll('{key}') > 0.666 and roll('{key}') <= 1.0"


def test_random_config_dynamic_weights_use_live_expressions():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    hashed = dynamic_value_hash("Chance")
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Chance"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
        }, {
            "$type": "RPG.GameCore.RandomConfig",
            "OddsList": [
                _dynamic("AQAR", hashes=[hashed]),
                _dynamic("AAABAAMR", hashes=[hashed], fixed=[1]),
            ],
            "TaskList": [
                [{"$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "A"},
                  "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
                [{"$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "B"},
                  "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
            ],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effects = out["hooks"][0]["effects"]
    bind = next(effect for effect in effects if effect["effect_type"] == "bind_roll")
    assert "dynamic_of($self.actor_id, 'Chance')" in bind["scale"]
    assert "1 - dynamic_of($self.actor_id, 'Chance')" in bind["scale"]
    guards = [effect.get("condition", "") for effect in effects
              if effect["effect_type"] == "set_dynamic_value" and effect["dynamic_key"] in {"A", "B"}]
    assert "dynamic_of($self.actor_id, 'Chance')" in guards[0]
    assert "1 - dynamic_of($self.actor_id, 'Chance')" in guards[1]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "Chance", "amount": 0.25}, {})
    assert eng._hooks._hook_amount(bind["scale"], source, {}) == pytest.approx(1.0)

    real = _real_compiler("3012010").compile_skill("Skill01")
    assert not any("权重" in issue["reason"] for issue in real["unsupported"])


def test_random_unique_single_draw_without_mask_is_plain_weighted():
    task = {
        "$type": "RPG.GameCore.RandomConfig",
        "OddsList": [{"IsDynamic": False, "FixedValue": {"Value": 1.0}}],
        "TaskList": [[{
            "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "P"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }]],
    }
    plain = _task_skill(task)
    unique = _task_skill({**task, "RandomUnique": True})
    assert plain["ok"] and unique["ok"]
    assert not plain["unsupported"] and not unique["unsupported"]
    assert unique["hooks"] == plain["hooks"]
    real = _real_compiler("2034014").compile_enemy()
    assert not any(issue["reason"] == "战斗级随机记忆字段尚未注册：['RandomUnique']"
                   for issue in real["unsupported"])


def test_random_config_memory_fields_stay_unsupported():
    """真实 AML Boss IF RandomConfig 壳（RandomUnique + RandomMaskKey）——
    战斗级记忆显式 unsupported，禁止猜测。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.RandomConfig",
            "OddsList": [{"IsDynamic": False, "FixedValue": {"Value": 1.0}}],
            "RandomUnique": True,
            "RandomMaskKey": {"Value": "Mask"},
            "TaskList": [[{
                "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "P"},
                "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}]],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]
    assert any("战斗级随机记忆" in item["reason"] for item in out["unsupported"])
    assert not _effects_with(out["hooks"], "bind_roll")


def test_dynamic_copying_self_alias_translates():
    """SetDynamicValueByCopying 自身与关卡源分别读 $self/$level；
    ParamModifier 的动态 modifier 引用仍拒绝。"""
    def copying(from_alias, from_key="Src", to_key="Dst", modifier=None):
        node = {
            "$type": "RPG.GameCore.SetDynamicValueByCopying",
            "FromTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": from_alias},
            "FromDynamicKey": {"Value": from_key},
            "ToDynamicKey": {"Value": to_key},
        }
        if modifier:
            node["FromModifierName"] = {"Value": modifier}
        return node

    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [
            copying("Caster"), copying("Caster", "Src2", "Dst2"),
            copying("LevelEntity"),
        ]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    copies = _effects_with(out["hooks"], "set_dynamic_value")
    assert [(effect["dynamic_key"], effect["amount"]) for effect in copies] == [
        ("Dst", "dynamic_of($self, 'Src')"),
        ("Dst2", "dynamic_of($self, 'Src2')"),
        ("Dst", "dynamic_of($level, 'Src')"),
    ]
    assert out["ok"] and not out["unsupported"]

    sources["abilities"]["A"]["OnStart"] = [copying("Caster", modifier="ParamModifier")]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert any("ParamModifier" in item["reason"] for item in rejected["unsupported"])


def test_dynamic_copying_reads_named_modifier_instance_values():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Mark"},
        "DynamicValues": {"Value": {"IsDynamic": False, "FixedValue": {"Value": 2.5}}},
    }, {
        "$type": "RPG.GameCore.SetDynamicValueByCopying",
        "FromTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "FromModifierName": {"Value": "Mark"},
        "FromDynamicKey": {"Value": "Value"},
        "ToTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ToDynamicKey": {"Value": "Copied"},
    }]
    sources["modifiers"] = {"Mark": {"BehaviorFlagList": ["KeepOnDeathrattle"]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    copy_effect = next(effect for effect in effects
                       if effect.get("dynamic_key") == "Copied")
    assert copy_effect["amount"] == "modifier_dynamic_of($self, 'Mark', 'Value')"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "Value", "amount": 99.0}, {})
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert source.modifiers["Mark"].dynamic_values == {"Value": 2.5}
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Value"] == 99.0
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Copied"] == 2.5

    eng._apply_modifier_spec(source, {
        "modifier_id": "Mark", "modifier_type": "buff", "duration": 0,
        "max_stack": 1, "dynamic_values": {"Value": 7.0}}, source)
    assert source.modifiers["Mark"].dynamic_values["Value"] == 2.5
    eng._apply_modifier_spec(source, {
        "modifier_id": "Mark", "modifier_type": "buff", "duration": 0,
        "max_stack": 1, "stack_mode": "replace", "dynamic_values": {"Value": 7.0}}, source)
    eng._hooks._run_hook_effect(source, copy_effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Copied"] == 7.0

    eng._remove_modifier(source, "Mark", "test")
    eng._hooks._run_hook_effect(source, copy_effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Copied"] == 0.0


def test_set_modifier_dynamic_value_supports_set_add_and_missing_instance():
    from tests._builders import engine_vs_dummy, make_dummy

    def copying(key):
        return {
            "$type": "RPG.GameCore.SetDynamicValueByCopying",
            "FromTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "FromModifierName": {"Value": "Mark"},
            "FromDynamicKey": {"Value": "Value"},
            "ToDynamicKey": {"Value": key},
        }

    def writing(value, mode=None):
        task = {
            "$type": "RPG.GameCore.SetModifierDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Mark"},
            "DynamicKey": {"Value": "Value"},
            "NewValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
        }
        if mode is not None:
            task["ModifyFunction"] = mode
        return task

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Mark"},
        "DynamicValues": {"Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}},
    }, writing(2, "Add"), copying("AfterAdd"), writing(5), copying("AfterSet")]
    sources["modifiers"] = {"Mark": {"BehaviorFlagList": ["KeepOnDeathrattle"]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    writes = [effect for effect in effects
              if effect["effect_type"] == "set_modifier_dynamic_value"]
    assert [effect["mode"] for effect in writes] == ["add", "set"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "Value", "amount": 99.0}, {})
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    dynamic = eng._enemy_policy_state["source"]["dynamic_values"]
    assert source.modifiers["Mark"].dynamic_values["Value"] == 5.0
    assert dynamic["Value"] == 99.0
    assert dynamic["AfterAdd"] == 3.0 and dynamic["AfterSet"] == 5.0

    eng._remove_modifier(source, "Mark", "test")
    for effect in [*writes, next(effect for effect in effects
                                if effect.get("dynamic_key") == "AfterSet")]:
        eng._hooks._run_hook_effect(source, effect, {})
    assert dynamic["AfterSet"] == 0.0

    one_more = writing(1)
    one_more["ModifierName"] = {"Value": "OneMorePerTurn"}
    one_more["DynamicKey"] = {"Value": "OneMoreCount"}
    sources["abilities"]["A"]["OnStart"] = [one_more]
    built_in = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert built_in["ok"] and not built_in["unsupported"]
    built_in_effects = [effect for hook in built_in["hooks"] for effect in hook["effects"]]
    assert built_in_effects == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "OneMoreCount", "amount": 1}]

    one_more["ModifyFunction"] = "Add"
    sources["abilities"]["A"]["OnStart"] = [one_more]
    added = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert added["ok"] and not added["unsupported"]
    add_effect = added["hooks"][0]["effects"][0]
    assert add_effect == {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "OneMoreCount",
        "amount": "dynamic_of($self.actor_id, 'OneMoreCount') + 1"}
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "OneMoreCount", "amount": 2}, {})
    eng._hooks._run_hook_effect(source, add_effect, {})
    assert dynamic["OneMoreCount"] == 3.0


def test_set_modifier_dynamic_value_defaults_caster_and_rejects_cross_skill_bleed():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Mark"},
    }, {
        "$type": "RPG.GameCore.SetModifierDynamicValue",
        "ModifierName": {"Value": "Mark"},
        "DynamicKey": {"Value": "Value"},
        "NewValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]
    sources["modifiers"] = {"Mark": {"BehaviorFlagList": ["KeepOnDeathrattle"]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    write = next(effect for hook in out["hooks"] for effect in hook["effects"]
                 if effect["effect_type"] == "set_modifier_dynamic_value")
    assert write["target"] == "self"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    for hook in out["hooks"]:
        for effect in hook["effects"]:
            eng._hooks._run_hook_effect(source, effect, {})
    assert source.modifiers["Mark"].dynamic_values["Value"] == 1.0

    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetModifierDynamicValue",
        "ModifierName": {"Value": "Monster_W2_Beast01_03_Bleed"},
        "DynamicKey": {"Value": "Modifier_Bleed_DamagePercentage"},
        "NewValue": {"IsDynamic": False, "FixedValue": {"Value": 0.01}},
    }]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("跨技能 Bleed" in issue["reason"] for issue in rejected["unsupported"])


def test_param_modifier_reads_remodifier_selected_instance():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Remodifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummoner"},
        "CasterFilter": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": "Mark",
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValueByCopying",
            "FromTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "FromModifierName": {"Value": "ParamModifier"},
            "FromDynamicKey": {"Value": "Value"},
            "ToDynamicKey": {"Value": "Copied"},
        }],
    }]
    sources["modifiers"] = {"Mark": {"BehaviorFlagList": ["KeepOnDeathrattle"]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect.get("dynamic_key") == "Copied")
    assert effect["amount"] == "modifier_dynamic_of($target, 'Mark', 'Value')"
    assert "has_modifier($it, 'Mark', $self.actor_id)" in effect["amount_target"]["where"]

    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("owner")])
    source, owner = eng.state.actors["source"], eng.state.actors["owner"]
    source.actor.summoner_id = "owner"
    eng._apply_modifier_spec(owner, {
        "modifier_id": "Mark", "modifier_type": "buff", "duration": 0,
        "max_stack": 1, "dynamic_values": {"Value": 3.0}}, source)
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Copied"] == 3.0


def test_param_modifier_reads_current_modifier_event():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Listener"},
    }]
    sources["modifiers"] = {
        "Listener": {"BehaviorFlagList": ["KeepOnDeathrattle"], "_CallbackList": [{
            "Event": "OnModifierAdd", "CallbackConfig": [{
                "$type": "RPG.GameCore.PredicateTaskList",
                "Predicate": {"$type": "RPG.GameCore.ByCheckModifierCallBackName",
                              "ModifierName": "Mark"},
                "SuccessTaskList": [{
                    "$type": "RPG.GameCore.SetDynamicValueByCopying",
                    "FromTargetType": {"$type": "RPG.GameCore.TargetAlias",
                                       "Alias": "ModifierOwnerEntity"},
                    "FromModifierName": {"Value": "ParamModifier"},
                    "FromDynamicKey": {"Value": "Value"},
                    "ToTargetType": {"$type": "RPG.GameCore.TargetAlias",
                                     "Alias": "ModifierOwnerEntity"},
                    "ToDynamicKey": {"Value": "Copied"},
                }],
            }]}, {
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
            }],
        }]},
        "Mark": {"BehaviorFlagList": ["KeepOnDeathrattle"]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    listener = next(hook for hook in out["hooks"] if hook["event"] == "after_apply_modifier")
    effect = listener["effects"][0]
    assert effect["amount"] == "modifier_dynamic_of($self, $event.modifier_id, 'Value')"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    mount = next(effect for hook in out["hooks"] for effect in hook["effects"]
                 if effect["effect_type"] == "apply_modifier")
    eng._hooks._run_hook_effect(source, mount, {})
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event="after_apply_modifier",
        condition_expr=eng._expr.compile(listener["condition"], layer="effect"),
        effects=listener["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    eng._apply_modifier_spec(source, {
        "modifier_id": "Mark", "modifier_type": "buff", "duration": 0,
        "max_stack": 1, "dynamic_values": {"Value": 4.0}}, source)
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Copied"] == 4.0


def test_dynamic_copying_to_level_entity():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.SetDynamicValueByCopying",
        "FromTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "FromDynamicKey": {"Value": "7023RoleID"},
        "ToTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LevelEntity"},
        "ToDynamicKey": {"Value": "7023RoleID"},
        "TargetContextScope": "TargetEntity",
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {
        "effect_type": "set_dynamic_value", "target": "$level",
        "dynamic_key": "7023RoleID", "amount": "dynamic_of($self, '7023RoleID')"}

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "7023RoleID", "amount": 7}, {})
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["$level"]["dynamic_values"]["7023RoleID"] == 7.0
    assert eng._enemy_policy_state["source"]["dynamic_values"]["7023RoleID"] == 7.0


def test_dynamic_copying_summoner_and_event_target():
    from tests._builders import engine_vs_dummy, make_dummy
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_hp_decrease")
    for from_alias, to_key in (("CasterSummoner", "Y"), ("ParamEntity", "Z")):
        compiler._compile_dynamic_copying({
            "$type": "RPG.GameCore.SetDynamicValueByCopying",
            "FromTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": from_alias},
            "FromDynamicKey": {"Value": "X"},
            "ToDynamicKey": {"Value": to_key},
        }, ctx, "copy", ())
    assert not ctx.unsupported
    summoner_effect, event_effect = ctx.effects
    assert summoner_effect["amount"] == "dynamic_of($target, 'X')"
    assert summoner_effect["amount_target"] == {
        "pool": "all", "where": "$it.actor_id == summoner_of($self.actor_id)"}
    assert event_effect["amount"] == "dynamic_of($event.target, 'X')"
    assert "amount_target" not in event_effect

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("owner"), make_dummy("4053010")])
    eng.state.actors["source"].actor.summoner_id = "owner"
    eng._enemy_policy_state["owner"] = {
        "seq_idx": 0, "cooldown_left": {}, "current_phase": 1,
        "dynamic_values": {"X": 7.0}}
    eng._enemy_policy_state["4053010"] = {
        "seq_idx": 0, "cooldown_left": {}, "current_phase": 1,
        "dynamic_values": {"X": 11.0}}
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, summoner_effect, {})
    eng._hooks._run_hook_effect(source, event_effect, {"target": "4053010"})
    runtime = eng._enemy_policy_state["source"]["dynamic_values"]
    assert runtime["Y"] == 7.0 and runtime["Z"] == 11.0


def test_event_mode_probability_branch_compiles_with_event_frame():
    """帧外事件由 HookRuntime 建帧，事件域概率分支不再拒绝。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "Modifiers": {"M": {
            "BehaviorFlagList": ["Deathrattle"],
            "_CallbackList": [{
                "Event": "OnDeathrattle",
                "CallbackConfig": [{
                    "$type": "RPG.GameCore.PredicateTaskList",
                    "Predicate": {"$type": "RPG.GameCore.ByRandomChance",
                                  "Chance": {"IsDynamic": False, "FixedValue": {"Value": 0.5}}},
                    "SuccessTaskList": [{
                        "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "X"},
                        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
                }],
            }],
        }}}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"]
    assert _effects_with(out["hooks"], "bind_roll")


def test_nested_random_chance_uses_lazy_effect_roll():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"][0]["Predicate"] = {
        "$type": "RPG.GameCore.ByAnd", "PredicateList": [{
            "$type": "RPG.GameCore.ByCompareHPRatio",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "CompareType": "Greater",
            "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        }, {
            "$type": "RPG.GameCore.ByRandomChance",
            "Chance": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
        }],
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert not _effects_with(out["hooks"], "bind_roll")
    effect = out["hooks"][0]["effects"][0]
    key = "RSkill01_A_OnStart_0_Predicate_PredicateList_1_ByRandomChance"
    assert effect["condition"] == (
        f"((hp_of($self.actor_id) / max_hp_of($self.actor_id)) > 0.5 "
        f"and roll('{key}') < 0.25)")


@_need_ability
def test_real_nested_random_chance_preserves_integer_toughness():
    out = _real_compiler("5012090").compile_skill("Skill02")
    assert out["action"]["toughness_dmg"] == 30
    assert not any(item["node_type"] == "RPG.GameCore.ByRandomChance"
                   for item in out["unsupported"])


def test_nested_random_chance_supports_event_domain():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"][0]["Predicate"] = {
        "$type": "RPG.GameCore.ByNot", "Predicate": {
            "$type": "RPG.GameCore.ByRandomChance",
            "Chance": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        },
    }
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"]


def test_frame_out_event_hook_gets_commit_scoped_frame():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy
    eng = engine_vs_dummy(mode="expected")
    eng._compiled_hooks = [CompiledHook(
        owner_id="e1", event="on_turn_end", condition_expr=None, effects=(
            {"effect_type": "set_dynamic_value", "target": "self",
             "dynamic_key": "EventWrite", "amount": 1},
            {"effect_type": "gain_resource", "resource_id": "lo", "amount": 1,
             "condition": "roll('EventRoll') < 0.5"},
            {"effect_type": "gain_resource", "resource_id": "hi", "amount": 1,
             "condition": "roll('EventRoll') >= 0.5"},
        ))]
    eng._hooks._subscribe_compiled_hooks()
    assert eng.current_frame is None
    eng.bus.emit("on_turn_end", {"actor": "hero", "kind": "normal"}, eng.state)
    st = eng.state.actors["e1"]
    assert st.resources["lo"] == 1 and "hi" not in st.resources
    assert eng._enemy_policy_state["e1"]["dynamic_values"]["EventWrite"] == 1
    assert eng.current_frame is None


def test_effect_roll_without_bind_is_lazy_and_frame_scoped():
    import random as _random
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy

    eng = engine_vs_dummy(mode="roll", seed=23)
    eng._compiled_hooks = [CompiledHook(
        owner_id="e1", event="on_action", condition_expr=None, effects=(
            {"effect_type": "gain_resource", "resource_id": "short", "amount": 1,
             "condition": "0 > 1 and roll('Nested') < 1"},
            {"effect_type": "gain_resource", "resource_id": "after", "amount": "roll('After')"},
        ))]
    eng._hooks._subscribe_compiled_hooks()
    eng._execute_action(eng.state.actors["hero"], eng.actions_by_actor["hero"][0],
                        _action_broadcast={
                            "actor": "hero", "action_type": "basic", "action_id": "b",
                            "target_type": "single", "actor_type": "character"})
    assert "short" not in eng.state.actors["e1"].resources
    seq = _random.Random(23)
    seq.random()
    after = seq.random()
    assert eng.state.actors["e1"].resources["after"] == pytest.approx(after)
    assert eng.pipeline.rng.getstate() == seq.getstate()


def test_probability_branch_engine_level_roll_and_expected():
    """引擎级：编译产物形态（bind_roll + 互补守卫）在 roll/expected 两模式下行为钉——
    roll 模式同 seed 同分支（0.5 守卫两侧互斥、恰好一边生效）；
    expected 模式绑 0.5 下邻浮点，< 0.5 分支恒生效、>= 0.5 分支恒不生效。"""
    import random as _random
    from hsr_nous.sim.compile.compiled import CompiledHook
    from hsr_nous.sim_schema.expression import parse
    from tests._builders import engine_vs_dummy

    def build(mode, seed):
        eng = engine_vs_dummy(mode=mode, seed=seed)
        effects = (
            {"effect_type": "bind_roll", "roll_key": "K"},
            {"effect_type": "gain_resource", "resource_id": "lo", "amount": 1,
             "condition": "roll('K') < 0.5"},
            {"effect_type": "gain_resource", "resource_id": "hi", "amount": 1,
             "condition": "roll('K') >= 0.5"},
        )
        eng._compiled_hooks = [CompiledHook(
            owner_id="e1", event="on_action", condition_expr=None, effects=effects)]
        eng._hooks._subscribe_compiled_hooks()
        eng._execute_action(eng.state.actors["hero"], eng.actions_by_actor["hero"][0],
                            _action_broadcast={
                                "actor": "hero", "action_type": "basic", "action_id": "b",
                                "target_type": "single", "actor_type": "character"})
        return eng

    # 行动结算（首段直伤暴击判定）先消耗主流一次，on_action 的 bind 取第二抽。
    seq = _random.Random(11)
    seq.random()
    first_draw = seq.random()
    eng = build("roll", 11)
    st = eng.state.actors["e1"]
    expected_lo, expected_hi = (1.0, 0.0) if first_draw < 0.5 else (0.0, 1.0)
    assert st.resources.get("lo", 0.0) == expected_lo, "守卫两侧互斥且恰好一边生效"
    assert st.resources.get("hi", 0.0) == expected_hi

    eng_exp = build("expected", 11)
    st_exp = eng_exp.state.actors["e1"]
    assert st_exp.resources.get("lo", 0.0) == 1.0, "expected 绑 0.5 下邻浮点，< 0.5 恒真"
    assert st_exp.resources.get("hi", 0.0) == 0.0


def test_probability_branch_zero_cost_after_bind_engine_level():
    """引擎级：bind 后同键读取零消耗——带守卫的两次读取只消耗主流一次."""
    import random as _random
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy

    def build(amount):
        eng = engine_vs_dummy(mode="roll", seed=23)
        effects = (
            {"effect_type": "bind_roll", "roll_key": "K"},
            {"effect_type": "gain_resource", "resource_id": "d", "amount": amount},
        )
        eng._compiled_hooks = [CompiledHook(
            owner_id="e1", event="on_action", condition_expr=None, effects=effects)]
        eng._hooks._subscribe_compiled_hooks()
        eng._execute_action(eng.state.actors["hero"], eng.actions_by_actor["hero"][0],
                            _action_broadcast={
                                "actor": "hero", "action_type": "basic", "action_id": "b",
                                "target_type": "single", "actor_type": "character"})
        return eng

    single = build("roll('K')")
    double = build("roll('K') + roll('K')")
    seq = _random.Random(23)
    seq.random()   # 暴击判定先消耗一流
    first = seq.random()
    assert single.state.actors["e1"].resources["d"] == pytest.approx(first)
    assert double.state.actors["e1"].resources["d"] == pytest.approx(2 * first)
    assert single.pipeline.rng.getstate() == double.pipeline.rng.getstate()


# ---------------------------------------------------------------------------
# 被动事件族（14_policy.md 被动事件族节）：真实样例结构钉 + 引擎级挂载行为钉
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("source_event", "engine_event"), [
    ("OnPhase1", "on_turn_start"),
    ("OnPhase2", "on_turn_end"),
])
def test_non_dot_phase_callbacks_use_owner_turn_events(source_event, engine_event):
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Periodic"},
    }]
    sources["modifiers"] = {"Periodic": {"_CallbackList": [{
        "Event": source_event,
        "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "Seen"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"]
    hook = next(h for h in out["hooks"] if h["event"] == engine_event)
    assert hook["condition"] == "$event.actor == $self.actor_id"
    mount = next(e for h in out["hooks"] for e in h["effects"]
                 if e["effect_type"] == "apply_modifier")
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("other")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, mount, {})
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event=engine_event,
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    eng.bus.emit(engine_event, {"actor": "other", "kind": "normal"}, eng.state)
    assert "Seen" not in eng._enemy_policy_state.get("source", {}).get("dynamic_values", {})
    eng.bus.emit(engine_event, {"actor": "source", "kind": "normal"}, eng.state)
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Seen"] == 1


def test_listen_character_die_without_deathrattle_flag_is_global():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Listener"},
    }]
    sources["modifiers"] = {"Listener": {"_CallbackList": [{
        "Event": "OnListenCharacterDie",
        "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "Seen"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"]
    hook = next(h for h in out["hooks"] if h["event"] == "on_kill")
    assert hook["condition"] == "true"
    mount = next(e for h in out["hooks"] for e in h["effects"]
                 if e["effect_type"] == "apply_modifier")
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("other")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, mount, {})
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event="on_kill",
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    eng.bus.emit("on_kill", {"source": "source", "target": "other"}, eng.state)
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Seen"] == 1


def test_before_action_fires_after_target_resolution_before_effects():
    from dataclasses import replace
    from tests._builders import basic_action, engine_vs_dummy

    eng = engine_vs_dummy()
    events = []
    initial_sp = eng.state.skill_points
    observed_sp = {}
    eng.bus.subscribe("before_action", lambda _et, _payload, _ctx: observed_sp.update(
        before=eng.state.skill_points))
    for event_name in ("before_action", "on_become_target", "on_action"):
        eng.bus.subscribe(event_name, lambda et, payload, _ctx: events.append((et, payload)))
    action = replace(basic_action(), skill_point_cost=1)
    eng._execute_action(eng.state.actors["hero"], action, _action_broadcast={
        "actor": "hero", "action_type": "basic", "action_id": "b",
        "target_type": "single", "actor_type": "character",
    })
    assert [name for name, _payload in events] == [
        "before_action", "on_become_target", "on_action"]
    payload = events[0][1]
    assert payload["actor"] == "hero" and payload["actor_type"] == "character"
    assert payload["action_id"] == "b" and payload["action_type"] == "basic"
    assert payload["target"] == "e1" and payload["targets"] == ["e1"]
    assert payload["target_type"] == "single" and payload["insert"] is False
    assert observed_sp["before"] == initial_sp
    assert eng.state.skill_points < initial_sp


@pytest.mark.parametrize(("expected", "inverse", "accepted"), [
    ("A", False, True), ("B", False, False), ("B", True, True),
])
def test_compare_param_string_uses_current_ability(expected, inverse, accepted):
    predicate = {"$type": "RPG.GameCore.ByCompareParamString",
                 "CompareValue": {"Value": expected}}
    if inverse:
        predicate["Inverse"] = True
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    expected_guard = "1 == 1" if accepted else "1 == 0"
    assert any(effect.get("dynamic_key") == "PredicateResult" and expected_guard in hook["condition"]
               for hook in out["hooks"] for effect in hook.get("effects", []))
    if accepted:
        sources["abilities"]["Passive"] = {
            "Name": "Passive", "OnStart": sources["abilities"]["A"]["OnStart"]}
        passive = AbilityCompiler("fake", skills, sources).compile_passive("Passive", "p")
        assert passive["ok"] and not passive["unsupported"]


def test_before_action_current_skill_predicates():
    name = _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillName", "SkillName": "Skill01"},
                      event="before_action")
    skill_type = _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType", "SkillType": "Skill"},
                            event="before_action")
    elation = _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType", "SkillType": "Elation"},
                         event="before_action")
    assert name == "$event.action_id == 's1'"
    assert skill_type == "$event.action_type == 'skill'"
    assert elation == "$event.action_type == 'elation_skill'"


def test_current_turn_state_reads_execution_frame_insert_and_action_type():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import basic_action, engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="before_action")
    expressions = {}
    for state in ("InsertAbilityActionPhase", "InsertUltraSkillExecuting"):
        expressions[state] = compiler._predicate_expr({
            "$type": "RPG.GameCore.ByCurrentTurnState", "TurnStates": [state]}, ctx, state)
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    seen = []
    eng.bus.subscribe("before_action", lambda event, payload, ctx: seen.append((
        eng._hooks._hook_amount(expressions["InsertAbilityActionPhase"], source, payload),
        eng._hooks._hook_amount(expressions["InsertUltraSkillExecuting"], source, payload))))
    for action_type, insert in (("basic", False), ("basic", True), ("ultimate", True)):
        eng._execute_action(source, basic_action(
            "b", action_type=action_type), _insert=insert,
            forced_target=eng.state.actors["hero"])
    assert seen == [(0, 0), (1, 0), (0, 1)]


def test_current_turn_state_tracks_modifier_phase1_begin():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_turn_start")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCurrentTurnState",
        "TurnStates": ["ModifierPhase1Begin"]}, ctx, "phase1")
    assert expression == "(current_turn_state('ModifierPhase1Begin'))"
    assert not ctx.unsupported

    eng = engine_vs_dummy()
    hero = eng.state.actors["hero"]
    seen = []
    for event in ("on_turn_start", "before_action", "on_turn_end"):
        eng.bus.subscribe(event, lambda et, payload, bus_ctx: seen.append(
            (et, eng._hooks._hook_amount(expression, hero, payload))))
    eng._run_turn(hero, "normal")
    assert seen == [("on_turn_start", 1.0), ("before_action", 0.0), ("on_turn_end", 0.0)]
    assert eng._hooks._hook_amount(expression, hero, {}) == 0.0


def test_after_attack_reads_dynamic_value_written_by_after_hit():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Controller"},
    }]
    sources["modifiers"] = {"Controller": {"_CallbackList": [{
        "Event": "OnAfterHit",
        "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "Counter"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }, {
        "Event": "OnAfterAttack",
        "CallbackConfig": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareDynamicValue",
                "DynamicKey": {"Value": "Counter"},
                "CompareType": "GreaterEqual",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.SetDynamicValue",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "DynamicKey": {"Value": "Passive"},
                "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"]
    mount = next(e for h in out["hooks"] for e in h["effects"]
                 if e["effect_type"] == "apply_modifier")
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("other")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, mount, {})
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event=h["event"],
        condition_expr=eng._expr.compile(h["condition"], layer="effect"),
        effects=h["effects"])
        for h in out["hooks"] if h["event"] in {"after_being_hit", "on_action_end"}]
    eng._hooks._subscribe_compiled_hooks()
    eng.bus.emit("after_being_hit", {
        "source": "source", "target": "hero", "action_id": "s1"}, eng.state)
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Counter"] == 1
    eng.bus.emit("on_action_end", {"actor": "other", "action_id": "x"}, eng.state)
    assert "Passive" not in eng._enemy_policy_state["source"]["dynamic_values"]
    eng.bus.emit("on_action_end", {"actor": "source", "action_id": "s1"}, eng.state)
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Passive"] == 1


def test_compare_modifier_value_defaults_to_count():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareModifierValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "ModifierName": "Mark", "CompareType": "Equal",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }, ctx, "P")
    assert expression == "has_modifier($self.actor_id, 'Mark') == 1"
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert not eng._hooks._hook_amount(expression, source, {})
    eng._apply_modifier_spec(source, {
        "modifier_id": "Mark", "modifier_type": "buff", "duration": 0,
        "max_stack": 3}, source)
    assert eng._hooks._hook_amount(expression, source, {})


def test_modifier_dynamic_hash_rebinds_to_current_instance():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Mark"},
        "DynamicValues": {"Value": {"IsDynamic": False, "FixedValue": {"Value": 2.5}}},
    }]
    sources["modifiers"] = {"Mark": {"BehaviorFlagList": ["KeepOnDeathrattle"]}}
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_apply_modifier",
                   current_modifier="Mark")
    value = compiler._value({
        "IsDynamic": True, "PostfixExpr": {"OpCodes": "AQAR", "FixedValues": [],
                                         "DynamicHashes": [dynamic_value_hash("Value")]}},
        ctx, "P")
    assert value == "modifier_dynamic_of($self.actor_id, 'Mark', 'Value')"
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._apply_modifier_spec(source, {
        "modifier_id": "Mark", "modifier_type": "buff", "duration": 0,
        "max_stack": 1, "dynamic_values": {"Value": 2.5}}, source)
    assert eng._hooks._hook_amount(value, source, {}) == 2.5


def test_modifier_callback_layer_compares_current_event_modifier():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_apply_modifier")
    expression = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCheckModifierCallBackModifierValue",
        "ValueType": "Layer", "CompareType": "Equal",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }, ctx, "P")
    assert expression == "stacks($event.target, $event.modifier_id) == 0"
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"target": "source", "modifier_id": "Mark"}
    assert eng._hooks._hook_amount(expression, source, payload)
    eng._apply_modifier_spec(source, {
        "modifier_id": "Mark", "modifier_type": "buff", "stacks": 2,
        "duration": 0, "max_stack": 5}, source)
    assert not eng._hooks._hook_amount(expression, source, payload)

    rejected_ctx = _Context(mode="event", skill=skills[0], event="on_action")
    assert compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCheckModifierCallBackModifierValue",
        "ValueType": "Layer", "CompareType": "Equal",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }, rejected_ctx, "P") is None
    assert any("添加事件" in issue["reason"] for issue in rejected_ctx.unsupported)


def test_on_modifier_on_stack_uses_after_apply_event_and_target():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [
        {"$type": "RPG.GameCore.AddModifier", "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
         "ModifierName": {"Value": "Listener"}},
        {"$type": "RPG.GameCore.AddModifier", "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
         "ModifierName": {"Value": "Triggered"}},
    ]
    sources["modifiers"] = {
        "Listener": {"_CallbackList": [{
            "Event": "OnModifierOnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.PredicateTaskList", "Predicate": {
                    "$type": "RPG.GameCore.ByAnd", "PredicateList": [
                        {"$type": "RPG.GameCore.ByCheckModifierCallBackName",
                         "ModifierName": "Triggered"},
                        {"$type": "RPG.GameCore.ByCompareCurrentModifierStatusType",
                         "TargetStatusType": "Buff"},
                        {"$type": "RPG.GameCore.ByTargetTeam", "Team": "TeamDark",
                         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity2"}},
                    ]},
                "SuccessTaskList": [{
                    "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Seen"},
                    "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                }],
            }],
        }]},
        "Triggered": {"BehaviorFlagList": ["ImmuneDebuff"]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"]
    hook = next(item for item in out["hooks"] if item["event"] == "after_apply_modifier")
    assert "$event.modifier_id == 'Triggered'" in hook["condition"]
    assert "$event.modifier_type == 'buff'" in hook["condition"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event="after_apply_modifier",
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    eng._apply_modifier_spec(source, {
        "modifier_id": "Triggered", "modifier_type": "buff"}, source)
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Seen"] == 1.0


def _real_passive(enemy_id: str, ability_name: str, skill_id: str) -> dict:
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    return AbilityCompiler(enemy_id, get_enemy_skills(enemy_id),
                           get_enemy_ability_sources(enemy_id), level=80
                           ).compile_passive(ability_name, skill_id)


@_need_ability
def test_real_kafka_passive_mounts_and_maps_dispel_callback():
    """真实 Kafka（2004010）Passive01：OnStart 挂载 → on_battle_start + actor_enter
    双触发钩；OnListenModifierDispel → after_remove_modifier + reason=='dispel' 窄化。"""
    out = _real_passive("2004010", "Monster_W2_Kafka_00_Passive01",
                        "2004010_Monster_W2_Kafka_00_Passive01")
    events = [hook["event"] for hook in out["hooks"]]
    assert "on_battle_start" in events and "actor_enter" in events
    mount = next(h for h in out["hooks"] if h["event"] == "on_battle_start")
    assert any(effect["effect_type"] == "apply_modifier" for effect in mount["effects"])
    wave = next(h for h in out["hooks"] if h["event"] == "actor_enter")
    assert wave["condition"] == "$event.actor == $self.actor_id and $event.wave_index >= 1"
    assert out["ok"] and not out["unsupported"]


@_need_ability
def test_real_kafka_bgm_level_entity_blackboard_supported():
    """LevelEntity 已收编（决策卡 #31 关卡黑板）——Kafka BGM 被动不再因关卡目标被拒."""
    out = _real_passive("2004010", "Monster_W2_Kafka_00_PassiveSkill_BGM",
                        "2004010_Monster_W2_Kafka_00_PassiveSkill_BGM")
    assert not any("LevelEntity" in item["reason"] for item in out["unsupported"]), (
        f"LevelEntity 相关拒因应清零：{[i['reason'] for i in out['unsupported']]}")


@_need_ability
def test_real_aml_break_passive_on_break_mapping():
    """真实 AML 小怪（8012010，Monster_AML_Minion02_00_Passive01）：OnBeingBreak →
    on_break + $event.target 持有者窄化（Monster_Common_* 共享被动维持 deferred，
    不收进本断言）。"""
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    compiler = AbilityCompiler("8012010", get_enemy_skills("8012010"),
                               get_enemy_ability_sources("8012010"), level=80)
    result = compiler.compile_enemy()
    break_hooks = [h for h in result["hooks"] if h.get("event") == "on_break"]
    assert break_hooks, "OnBeingBreak 应映射出 on_break 钩"
    conditioned = [h for h in break_hooks
                   if "$event.target == $self.actor_id" in str(h.get("condition", ""))]
    assert conditioned, f"击破回调应持有者窄化：{[h.get('condition') for h in break_hooks]}"
    effects = [e for h in conditioned for e in h.get("effects", [])]
    assert any(e.get("effect_type") == "remove_modifier" for e in effects), \
        f"击破回调效果应编译出：{[e.get('effect_type') for e in effects]}"


@pytest.mark.parametrize(("event", "engine_event", "condition"), [
    ("OnListenModifierAdd", "after_apply_modifier", "$event.target == $self.actor_id"),
    ("OnShieldChange", "shield_changed", "$event.target == $self.actor_id"),
    ("OnListenShieldChange", "shield_changed", "true"),
    ("OnListenEndBreak", "toughness_recovered", "true"),
    ("OnListenAfterAction", "on_action_end", "true"),
    ("OnListenAfterSkillUse", "on_action", "$event.action_type == 'skill'"),
    ("OnAfterSkillUse", "on_action",
     "$event.actor == $self.actor_id and $event.action_type == 'skill'"),
    ("OnAllowAction", "on_turn_start", "not action_disabled($event.actor)"),
    ("OnListenAllowAction", "on_turn_start", "not action_disabled($event.actor)"),
    ("OnDepartedStart", "before_actor_exit", "$event.actor == $self.actor_id"),
    ("OnBeforeEscape", "before_actor_exit",
     "$event.actor == $self.actor_id and $event.reason == 'flee'"),
    ("OnListenDepartedStart", "before_actor_exit", "true"),
    ("OnDepartedEnd", "actor_exit", "$event.actor == $self.actor_id"),
    ("OnListenDepartedEnd", "actor_exit", "true"),
    ("OnListenTurnPhase1Begin", "on_turn_start", "true"),
    ("OnListenTurnPhase2Begin", "on_turn_end", "true"),
    ("OnListenBeforeTurnPhase1End", "on_turn_end", "true"),
    ("OnListenInsertAbilityStart", "on_action", "$event.insert"),
    ("OnInsertAbilityStart", "on_action", "$event.insert and $event.actor == $self.actor_id"),
    ("OnInsertActionStart", "before_action", "$event.insert and $event.actor == $self.actor_id"),
    ("OnBeforeInsertActionPrepare", "before_action", "$event.insert and $event.actor == $self.actor_id"),
    ("OnListenInsertActionStart", "before_action", "$event.insert"),
    ("OnListenInsertAbilityFinish", "on_action_end", "$event.insert"),
    ("OnInsertAbilityFinish", "on_action_end", "$event.insert"),
    ("OnListenInsertActionFinish", "on_action_end", "$event.insert"),
    ("OnListenElationTimeStart", "aha_instant_start", "true"),
    ("OnListenBattleEventCreate", "battle_event_create", "true"),
    ("OnMonsterPhaseChanged", "monster_phase_changed", "$event.actor == $self.actor_id"),
    ("OnAfterHitAll", "after_being_hit", "$event.target == $self.actor_id"),
    ("OnListenAfterBeingHitAll", "after_being_hit", "true"),
    ("OnAfterBeingAttackedAdv", "after_being_hit", "$event.target == $self.actor_id"),
    ("OnAfterHit", "after_being_hit", "$event.source == $self.actor_id"),
    ("OnAfterAttack", "on_action_end", "$event.actor == $self.actor_id"),
    ("OnAfterAttackEnd", "on_action_end", "$event.actor == $self.actor_id"),
    ("OnAfterAction", "on_action_end", "$event.actor == $self.actor_id"),
    ("OnBeingStanceCountDown", "on_stance_countdown", "$event.target == $self.actor_id"),
    ("OnUltraSkillPrepare", "on_ultimate_prepare", "$event.source == $self.actor_id"),
    ("OnBeforeUltraSkillPrepare", "on_ultimate_prepare", "$event.source == $self.actor_id"),
    ("OnListenUltraSkillPrepare", "on_ultimate_prepare", "true"),
    ("OnListenAfterAttack", "on_action_end", "true"),
    ("OnListenAfterAttackEnd", "on_action_end", "true"),
    ("OnListenCharmMakeDamage", "after_being_hit", "true"),
    ("OnBeforeAttack", "before_action", "$event.actor == $self.actor_id"),
    ("OnListenBeforeAttack", "before_action", "true"),
    ("OnHPOverflow", "on_hp_increase", "$event.excess > 0"),
    ("OnListenRevive", "on_revive", "true"),
    ("OnBeingRevived", "on_revive", "$event.target == $self.actor_id"),
    ("OnListenBeforeAction", "before_action", "true"),
    ("OnActionPhaseBegin", "before_action", "$event.actor == $self.actor_id"),
    ("OnCharmAction", "on_action", "$event.actor == $self.actor_id"),
    ("OnListenActionPhaseBegin", "before_action", "true"),
    ("OnBeforeSkillUse", "before_action",
     "$event.actor == $self.actor_id and $event.action_type == 'skill'"),
    ("OnListenBeforeSkillUse", "before_action", "$event.action_type == 'skill'"),
    ("OnBeforeHit", "before_take_damage", "$event.target == $self.actor_id"),
    ("OnTriggerBreak", "on_break", "$event.target == $self.actor_id"),
    ("OnBeforeBeingBreak", "on_break", "$event.target == $self.actor_id"),
    ("OnStanceReset", "toughness_recovered", "$event.target == $self.actor_id"),
    ("OnDeathrattle", "on_kill", "$event.target == $self.actor_id"),
    ("OnTriggerDeath", "on_kill", "$event.target == $self.actor_id"),
    ("OnTriggerDeathrattle", "on_kill", "$event.target == $self.actor_id"),
    ("OnDispel", "after_remove_modifier",
     "$event.target == $self.actor_id and $event.reason == 'dispel'"),
    ("OnBeforeAction", "before_action", "$event.actor == $self.actor_id"),
    ("OnBeingStanceDamage", "on_toughness_damage", "$event.target == $self.actor_id"),
])
def test_listen_event_aliases_reuse_existing_hooks(event, engine_event, condition):
    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Listener"},
        }]}},
        "modifiers": {"Listener": {"_CallbackList": [{
            "Event": event,
            "CallbackConfig": [{
                "$type": "RPG.GameCore.DefineDynamicValue",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "DynamicKey": {"Value": "Seen"},
                "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    hook = next(h for h in out["hooks"] if h["event"] == engine_event)
    assert hook["condition"] == condition
    if event == "OnAfterAttackEnd":
        real = _real_compiler("4062020").compile_enemy()
        assert not any(item["node_type"] == event for item in real["unsupported"])
    if event == "OnStanceReset":
        real = _real_compiler("3003010").compile_enemy()
        assert not any(item["node_type"] == event for item in real["unsupported"])
    real_id = {"OnActionPhaseBegin": "4014010",
               "OnListenActionPhaseBegin": "3025011",
               "OnDepartedStart": "2033022", "OnDepartedEnd": "2033022",
               "OnListenDepartedStart": "8034010",
               "OnListenDepartedEnd": "4035010",
               "OnBeforeBeingBreak": "3013010",
               "OnListenCharmMakeDamage": "2004010"}.get(event)
    if real_id:
        real = _real_compiler(real_id).compile_enemy()
        assert not any(item["node_type"] == event for item in real["unsupported"])


def test_actor_exit_hook_runs_after_owner_leaves():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event="actor_exit",
        condition_expr=eng._expr.compile("$event.actor == $self.actor_id", layer="effect"),
        effects=[{"effect_type": "set_dynamic_value", "target": "self",
                  "dynamic_key": "DepartedEnd", "amount": 1}],
    )]
    eng._hooks._subscribe_compiled_hooks()
    assert eng.leave_actor("source")
    assert not source.alive
    assert eng._enemy_policy_state["source"]["dynamic_values"]["DepartedEnd"] == 1


def test_charm_make_damage_reads_hit_source_for_property_values():
    from tests._builders import engine_vs_dummy, make_dummy

    real = _real_compiler("2004010").compile_enemy()
    assert not any(item["node_type"] == "OnListenCharmMakeDamage"
                   for item in real["unsupported"])
    from hsr_nous.adapters.enemy_ability import _Context
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="after_being_hit")
    compiler._compile_property_value({
        "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "ATK_Avatar",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity2"},
        "Value": "Attack",
    }, ctx, "P", ())
    effect = ctx.effects[0]
    assert effect["amount"] == "stat_of($event.source, 'atk')"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    hero.actor.stats.atk = 321.0
    assert eng._hooks._hook_amount(effect["amount"], source, {
        "source": "hero", "target": "source"}) == 321.0


def test_on_revive_maps_target_and_source_parameters():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_revive")
    assert compiler._hook_target("ParamEntity", ctx) == "$event.target"
    expr = compiler._predicate_expr({
        "$type": "RPG.GameCore.ByCompareTarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity2"},
        "CompareType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Inverse": True,
    }, ctx, "P")
    assert expr == "not ($event.source == $self.actor_id)" and not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    payload = {"target": "hero", "source": "hero"}
    assert eng._hooks._hook_amount(expr, source, payload) == 1.0
    assert [st.actor.actor_id for st in eng._hooks._hook_target_states(
        "$event.target", source, payload)] == ["hero"]
    real = _real_compiler("4015020").compile_enemy()
    assert not any(item["node_type"] in {"OnListenRevive", "RPG.GameCore.ByCompareTarget"}
                   for item in real["unsupported"])


@pytest.mark.parametrize(("event", "condition"), [
    ("OnHPChange", "$event.target == $self.actor_id"),
    ("OnListenHPChange", "true"),
])
def test_hp_change_registers_both_directions_without_double_run(event, condition):
    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Listener"},
        }]}},
        "modifiers": {"Listener": {"_CallbackList": [{
            "Event": event,
            "CallbackConfig": [{
                "$type": "RPG.GameCore.DefineDynamicValue",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "DynamicKey": {"Value": "Seen"},
                "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"], out["unsupported"]
    hooks = {h["event"]: h["condition"] for h in out["hooks"]
             if h["event"] in {"on_hp_decrease", "on_hp_increase"}}
    assert hooks == {"on_hp_decrease": condition, "on_hp_increase": condition}


def test_ability_modifier_deathrattle_is_not_duplicated():
    callback = {
        "Event": "OnDeathrattle",
        "CallbackConfig": [{
            "$type": "RPG.GameCore.DefineDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "Seen"},
            "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }
    modifier = {"_CallbackList": [callback]}
    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {
            "Name": "P",
            "OnStart": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "ModifierName": {"Value": "Listener"},
            }],
            "Modifiers": {"Listener": modifier},
        }},
        "modifiers": {"Listener": modifier},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    assert sum(h["event"] == "on_kill" for h in out["hooks"]) == 1


def test_empty_ai_shell_passive_compiles_to_nothing():
    """空被动（无 OnAdd/OnStart/回调机制内容的 AI 控制壳）——空翻译 ok=True 零钩。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Passive01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P"}},   # 无 OnAdd/OnStart/Modifiers
    }
    skills = [{"skill_id": "s1", "trigger_key": "Passive01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"] and not out["hooks"]


def test_unmapped_event_rejected_with_reason_and_presentation_ignored():
    """无载体事件两态钉：机制内容显式拒（理由写清）；纯表现回调安全忽略。"""
    def passive_with(callback_event, callback_tasks):
        return {
            "character_config": {"SkillList": [{
                "Name": "Passive01", "SkillType": "Passive",
                "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
            }]},
            "abilities": {"P": {"Name": "P", "OnAdd": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "ModifierName": {"Value": "M"},
            }]}},
            "modifiers": {"M": {
                "BehaviorFlagList": [],
                "LifeTime": 99, "Stacking": "Refresh",
                "_CallbackList": [{"Event": callback_event, "CallbackConfig": callback_tasks}],
            }},
        }

    skills = [{"skill_id": "s1", "trigger_key": "Passive01", "param_list": []}]
    sources = passive_with("OnUnknownEvent", [{
        "$type": "RPG.GameCore.DefineDynamicValue", "DynamicKey": {"Value": "X"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}])
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert not out["ok"]
    assert any("未注册" in item["reason"] for item in out["unsupported"])

    sources = passive_with("OnCustomEvent", [{
        "$type": "RPG.GameCore.MakeCharacterHUDVisible",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}}])
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]


def test_wave_mount_condition_disjoint_from_battle_start():
    """双触发互斥钉：初始阵容 on_battle_start 挂载、波次 actor_enter 补挂——
    同一 actor 实例两触发集不相交（初始 actor_enter 在订阅前发射收不到）。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Passive01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P", "OnAdd": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Buff"},
        }]}},
        "modifiers": {"Buff": {"_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}}}],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Passive01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    assert [h["event"] for h in out["hooks"]] == ["on_battle_start", "actor_enter"]
    assert out["hooks"][0]["condition"] == "true"
    assert "wave_index >= 1" in out["hooks"][1]["condition"]


def test_passive_mount_engine_level_applies_modifier_at_battle_start():
    """引擎级：编译产物挂载钩在 setup() 的 on_battle_start 生效——modifier 进战斗态。"""
    import types
    from hsr_nous.sim.engine import CombatEngine
    from hsr_nous.sim_schema.actor import Actor, StatBlock
    from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Passive01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P", "OnAdd": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Buff"},
        }, {
            "$type": "RPG.GameCore.DefineDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "X"},
            "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 7}},
        }]}},
        "modifiers": {"Buff": {"_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}}}],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Passive01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    enemy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, atk=1000, spd=100, max_toughness=9999,
                                  weakness=["fire"]))
    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(hp=5000, atk=2000, spd=200, max_energy=100))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, enemy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=50))
    eng = CombatEngine(enc, actions_by_actor={}, mode="expected",
                       initial_energy_ratio=0.0)
    eng._compiled_hooks = [types.SimpleNamespace(
        event=h["event"],
        owner_id="e1",
        condition_expr=(eng._expr.compile(h["condition"], layer="effect")
                        if h.get("condition") and h["condition"] != "true" else None),
        effects=tuple(dict(e) for e in h["effects"]),
    ) for h in out["hooks"]]
    eng.setup()
    st = eng.state.actors["e1"]
    assert "Buff" in st.modifiers, f"on_battle_start 挂载应施加 Buff：{list(st.modifiers)}"
    assert st.modifiers["Buff"].stat_effects.get("atk_pct") == 0.5
    from hsr_nous.sim.enemy_ai import config_ai_dynamic_value
    assert config_ai_dynamic_value(eng, "e1", "X") == 7.0, "DefineDynamicValue 初始化应落地"


def test_dispel_callback_maps_to_after_remove_modifier():
    """OnListenModifierDispel 映射结构钉：after_remove_modifier + reason=='dispel'
    窄化 + 回调任务编译进钩。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Passive01", "SkillType": "Passive",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "P",
        }]},
        "abilities": {"P": {"Name": "P", "OnAdd": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Buff"},
        }]}},
        "modifiers": {"Buff": {
            "LifeTime": 99, "Stacking": "Refresh",
            "_CallbackList": [{
                "Event": "OnListenModifierDispel",
                "CallbackConfig": [{
                    "$type": "RPG.GameCore.SetDynamicValueByAddValue",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                    "Key": {"Value": "DisPelCount"},
                    "AddValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                }],
            }],
        }},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Passive01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    dispel = [h for h in out["hooks"] if h["event"] == "after_remove_modifier"]
    assert len(dispel) == 1
    assert dispel[0]["condition"] == (
        "$event.target == $self.actor_id and $event.reason == 'dispel'")
    assert dispel[0]["effects"][0]["effect_type"] == "set_dynamic_value"


# ---------------------------------------------------------------------------
# 任务节点长尾族（14_policy.md 任务节点长尾节）：真实节点形状钉 + 引擎级落点钉
# ---------------------------------------------------------------------------

def _task_skill(task, *, config_extra=None, modifiers=None):
    """最小主动技能外壳：EntryAbility A 的 OnStart = [task]。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [task]}},
        "modifiers": modifiers or {},
    }
    if config_extra:
        sources["character_config"].update(config_extra)
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    return AbilityCompiler("fake", skills, sources).compile_skill("Skill01")


@_need_ability
def test_dynamic_max_bp_reads_runtime_skill_point_cap():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.SetDynamicValueByMaxBP", "DynamicKey": "MaxBP"})
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "MaxBP", "amount": "max_skill_points()"}

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    eng.state.sp_max_override = 7
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["MaxBP"] == 7

    real = _real_compiler("3024020").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.SetDynamicValueByMaxBP"
                   for issue in real["unsupported"])
    rejected = _task_skill({
        "$type": "RPG.GameCore.SetDynamicValueByMaxBP", "DynamicKey": "MaxBP",
        "TargetType": {"Alias": "Caster"}})
    assert not rejected["ok"]
    assert any("仅含 DynamicKey" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_simulate_speed_up_presentation_only_branches_are_ignored():
    def heal_display(seconds):
        return {"$type": "RPG.GameCore.SetBossHPStanceChangeType",
                "ChangeType": "Heal",
                "ChangeTime": {"IsDynamic": False, "FixedValue": {"Value": seconds}}}

    out = _task_skill({
        "$type": "RPG.GameCore.PredicateTaskList",
        "Predicate": {"$type": "RPG.GameCore.BySimulateSpeedUp", "Inverse": True},
        "SuccessTaskList": [heal_display(3)],
        "FailedTaskList": [heal_display(1.5)],
    })
    assert out["ok"] and not out["unsupported"]
    assert not _effects_with(out["hooks"], "set_dynamic_value")

    real = _real_compiler("4035010").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.BySimulateSpeedUp"
                   for issue in real["unsupported"])

    rejected = _task_skill({
        "$type": "RPG.GameCore.PredicateTaskList",
        "Predicate": {"$type": "RPG.GameCore.BySimulateSpeedUp"},
        "SuccessTaskList": [{
            "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "X"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
        "FailedTaskList": [heal_display(1.5)],
    })
    assert not rejected["ok"]
    assert any(issue["node_type"] == "RPG.GameCore.BySimulateSpeedUp"
               for issue in rejected["unsupported"])


@_need_ability
def test_on_stack_skips_unique_effect_predicate_for_presentation_branches():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "VisualModifier"},
    }]
    predicate = {
        "$type": "RPG.GameCore.PredicateTaskList",
        "Predicate": {
            "$type": "RPG.GameCore.ByAnd", "PredicateList": [{
                "$type": "RPG.GameCore.ByHaveUniqueNameEffect",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                               "Alias": "ModifierOwnerEntity"},
                "EffectUniqueName": {"Value": "Loop"},
                "IncludeUnprepared": True, "IncludeFadeOut": True,
            }],
        },
        "SuccessTaskList": [{
            "$type": "RPG.GameCore.TriggerEffect", "EffectPath": "Loop.prefab",
            "UniqueEffectName": "Loop",
        }],
        "FailedTaskList": [],
    }
    sources["modifiers"] = {"VisualModifier": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [predicate]}]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]

    real = _real_compiler("8033020").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.ByHaveUniqueNameEffect"
                   for issue in real["unsupported"])

    predicate["SuccessTaskList"] = [{
        "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "X"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any(issue["node_type"] == "RPG.GameCore.ByHaveUniqueNameEffect"
               for issue in rejected["unsupported"])


@_need_ability
def test_mission_talk_finish_only_waits_are_presentation():
    task = {
        "$type": "RPG.GameCore.PredicateTaskList",
        "Predicate": {"$type": "RPG.GameCore.ByBattleMissionTalkFinish"},
        "SuccessTaskList": [{
            "$type": "RPG.GameCore.WaitSecond",
            "WaitTime": {"IsDynamic": False, "FixedValue": {"Value": 4}}}],
        "FailedTaskList": [
            {"$type": "RPG.GameCore.WaitMissionTalkFinish"},
            {"$type": "RPG.GameCore.WaitSecond",
             "WaitTime": {"IsDynamic": False, "FixedValue": {"Value": 0.5}}}],
    }
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    real = _real_compiler("4035011").compile_enemy()
    assert not any(issue["node_type"] in {
        "RPG.GameCore.ByBattleMissionTalkFinish", "RPG.GameCore.WaitMissionTalkFinish"}
        for issue in real["unsupported"])

    task["SuccessTaskList"] = [{
        "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "X"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}]
    rejected = _task_skill(task)
    assert not rejected["ok"]
    assert any(issue["node_type"] == "RPG.GameCore.ByBattleMissionTalkFinish"
               for issue in rejected["unsupported"])


@_need_ability
def test_fire_prowler_template_switch_uses_dynamic_expression():
    real = _real_compiler("4034013").compile_enemy()
    assert not any(issue["reason"] == "运行时 Switch 尚未注册"
                   for issue in real["unsupported"])


@_need_ability
def test_deathrattle_preserves_modifier_for_local_template():
    template = {
        "Name": "Local",
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Seen"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
    }
    modifier = {
        "_CallbackList": [{
            "Event": "OnListenCharacterDie",
            "CallbackConfig": [{
                "$type": "RPG.GameCore.IncludeTaskListTemplate", "Name": "Local"}],
        }],
        "TaskListTemplate": [template],
    }
    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive", "EntryAbility": "P"}]},
        "abilities": {"P": {"Name": "P", "Modifiers": {"Listener": modifier}}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"] == [{
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "Seen", "amount": 1}]

    for enemy_id in ("1002030", "1004031"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("OnDieOrEscape" in issue["reason"] for issue in real["unsupported"])


@_need_ability
def test_character_count_excludes_servants_and_change_targets():
    from dataclasses import replace
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.SetDynamicValueByCharacterCount",
        "DynamicKey": "_CharacterCount",
        "ReadTargetType": {
            "$type": "RPG.GameCore.TargetAlias",
            "Alias": "AllLightTeamIgnoreServant.RemoveCharacterChangeTarget"},
        "AliveOnly": True,
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    servant_actor = replace(make_actor("servant"), actor_type="summon", summoner_id="hero")
    eng = engine_vs_dummy(allies=[servant_actor], enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["_CharacterCount"] == 1

    real = _real_compiler("4053011").compile_enemy()
    assert not any("RemoveCharacterChangeTarget" in issue["reason"]
                   for issue in real["unsupported"])


@_need_ability
def test_monster_rank_score_override_is_presentation():
    out = _task_skill({
        "$type": "RPG.GameCore.OverrideMonsterRankScore",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "IsRevert": True,
    })
    assert out["ok"] and not out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])
    for enemy_id in ("5013090", "8003060"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.OverrideMonsterRankScore"
                       for issue in real["unsupported"])


@_need_ability
def test_avatar_change_camera_dither_reset_is_presentation():
    name = "MAvatar_AvatarChange_W2_Test_ResetCameraDither"
    out = _task_skill({
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": name},
    })
    assert out["ok"] and not out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])
    for enemy_id in ("2035012", "4053011"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("ResetCameraDither" in issue["reason"]
                       for issue in real["unsupported"])


@_need_ability
def test_ap_show_hint_add_and_remove_are_presentation():
    name = "Monster_APShow_OneMore"
    out = _task_skill({
        "$type": "RPG.GameCore.SequenceConfig",
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": name},
        }, {
            "$type": "RPG.GameCore.RemoveModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": name},
        }],
    })
    assert out["ok"] and not out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])
    for enemy_id in ("1013022", "4014020"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("Monster_APShow_" in issue["reason"]
                       for issue in real["unsupported"])


@_need_ability
def test_trigger_break_reuses_complete_break_chain_without_reentry():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.TriggerBreak",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "IgnoreMuteBreak": True,
    })
    assert out["ok"] and not out["unsupported"]
    effect = dict(out["hooks"][0]["effects"][0], damage_type="$event.element")
    eng = engine_vs_dummy(enemies=[make_dummy("source", max_toughness=100)])
    source = eng.state.actors["source"]
    source.toughness = 0
    events = []
    eng.bus.subscribe("on_break", lambda _event, payload, _ctx: events.append(dict(payload)))
    eng._apply_modifier_spec(source, {
        "modifier_id": "MuteBreak", "modifier_type": "buff", "duration": 0,
        "behavior_flags": ["MuteBreak"]}, source)
    eng._hooks._run_hook_effect(
        source, dict(effect, ignore_mute_break=False), {"element": "fire"})
    assert not events and not source.broken
    source.modifiers.pop("MuteBreak")
    eng._hooks._run_hook_effect(source, effect, {"element": "fire"})
    assert source.broken and source.bars_exhausted
    assert events[0]["element"] == "fire"
    eng._hooks._run_hook_effect(source, effect, {"element": "fire"})
    assert len(events) == 1

    rejected = _task_skill({
        "$type": "RPG.GameCore.TriggerBreak", "IgnoreMuteBreak": False,
        "UnknownField": True})
    assert not rejected["ok"]
    for enemy_id in ("3004021", "3004022", "8003060"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.TriggerBreak"
                       for issue in real["unsupported"])


@_need_ability
def test_projectile_adjacent_hit_uses_blast_scaling():
    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {
        "TargetType": "EnemySelect", "SubTargetType": "TargetAdjoinEntity"}
    hits = []
    for alias, ratio in (("AbilityTargetEntity", 1.2),
                         ("AbilityTargetAdjoinEntity", 0.6)):
        hits.append({
            "$type": "RPG.GameCore.DamageByAttackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
            "AttackProperty": {"DamageType": "Physical", "DamagePercentage": {
                "IsDynamic": False, "FixedValue": {"Value": ratio}}},
        })
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.FireProjectile",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "OnProjectileHit": hits,
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["scaling"] == [{"atk": 1.2}]
    assert out["action"]["scaling_blast"] == [{"atk": 0.6}]

    for enemy_id in ("1002030", "4014013"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("其他命中任务尚未注册" in issue["reason"]
                       for issue in real["unsupported"])


@_need_ability
def test_projectile_equivalent_left_right_hits_coalesce_to_blast():
    def compile_pair(right_ratio=0.6):
        skills, sources = _predicate_skill({})
        sources["character_config"]["SkillList"][0]["TargetInfo"] = {
            "TargetType": "EnemySelect", "SubTargetType": "TargetAdjoinEntity"}
        hits = []
        for alias, ratio in (("AbilityTargetEntity", 1.2),
                             ("AbilityTargetLeftEntity", 0.6),
                             ("AbilityTargetRightEntity", right_ratio)):
            hits.append({
                "$type": "RPG.GameCore.DamageByAttackProperty",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
                "AttackProperty": {"DamageType": "Physical", "DamagePercentage": {
                    "IsDynamic": False, "FixedValue": {"Value": ratio}}},
                "HitEffect": f"Effects/{alias}",
            })
        sources["abilities"]["A"]["OnStart"] = [{
            "$type": "RPG.GameCore.FireProjectile",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
            "OnProjectileHit": hits,
        }]
        return AbilityCompiler("fake", skills, sources).compile_skill("Skill01")

    out = compile_pair()
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["scaling"] == [{"atk": 1.2}]
    assert out["action"]["scaling_blast"] == [{"atk": 0.6}]
    rejected = compile_pair(right_ratio=0.7)
    assert not rejected["ok"]
    assert sum("其他命中任务尚未注册" in issue["reason"]
               for issue in rejected["unsupported"]) == 2

    for enemy_id in ("2033010", "2033011"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("其他命中任务尚未注册" in issue["reason"]
                       for issue in real["unsupported"])


@_need_ability
def test_wait_custom_string_is_synchronous_presentation_barrier():
    out = _task_skill({
        "$type": "RPG.GameCore.WaitCustomString",
        "CustomString": {"Value": "SkillFinish"},
    })
    assert out["ok"] and not out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    for enemy_id in ("5013090", "5014010", "5014012", "5014014", "5014015"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.WaitCustomString"
                       for issue in real["unsupported"])


@_need_ability
def test_on_sp_change_reads_actual_energy_delta_and_ratio():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    modifier = {"_CallbackList": [{
        "Event": "OnSPChange",
        "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValueByChangeValue",
            "DynamicKey": "Delta", "ValueType": "RawDelta",
        }, {
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareSPRatio",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                               "Alias": "ModifierOwnerEntity"},
                "CompareType": "GreaterEqual",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Full"},
                "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
            "FailedTaskList": [],
        }],
    }]}
    sources = {
        "character_config": {"SkillList": [{
            "Name": "SkillP01", "SkillType": "Passive", "EntryAbility": "P"}]},
        "abilities": {"P": {"Name": "P", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            "ModifierName": {"Value": "Listener"},
        }]}},
        "modifiers": {"Listener": modifier},
    }
    skills = [{"skill_id": "s1", "trigger_key": "SkillP01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_passive("P", "s1")
    assert out["ok"] and not out["unsupported"]
    mount = next(hook for hook in out["hooks"] if hook["event"] == "on_battle_start")
    energy_hooks = [hook for hook in out["hooks"] if hook["event"] == "on_energy_change"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source, hero = eng.state.actors["source"], eng.state.actors["hero"]
    for effect in mount["effects"]:
        eng._hooks._run_hook_effect(source, effect, {})
    eng._compiled_hooks = [CompiledHook(
        owner_id="hero", event="on_energy_change",
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=hook["effects"]) for hook in energy_hooks]
    eng._hooks._subscribe_compiled_hooks()
    events = []
    eng.bus.subscribe("on_energy_change",
                      lambda _event, payload, _ctx: events.append(dict(payload)))

    eng._grant_energy(hero, 100, source="source", action_id=None, reason="effect")
    values = eng._enemy_policy_state["hero"]["dynamic_values"]
    assert values["Delta"] == 100 and values.get("Full") == 1
    eng._hooks._run_hook_effect(hero, {
        "effect_type": "consume_energy", "target": "self", "amount": 40}, {})
    assert values["Delta"] == -40
    eng._hooks._run_hook_effect(hero, {
        "effect_type": "set_energy", "target": "self", "amount": 100}, {})
    assert values["Delta"] == 40
    assert [(event["before"], event["after"]) for event in events] == [
        (0, 100), (100, 60), (60, 100)]

    real = _real_compiler("4035011").compile_enemy()
    assert not any(issue["node_type"] in {
        "OnSPChange", "RPG.GameCore.ByCompareSPRatio",
        "RPG.GameCore.SetDynamicValueByChangeValue", "RPG.GameCore.ByCompareParamValue"}
        for issue in real["unsupported"])


@_need_ability
def test_abort_monster_change_phase_uses_behavior_flag():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.TriggerAbility", "AbilityName": {"Value": "B"},
        "AbortBehaviorFlags": ["STAT_MonsterChangePhase"],
    }]
    sources["abilities"]["B"] = {"Name": "B", "OnStart": [{
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Mark"},
    }]}
    sources["modifiers"] = {"Mark": {}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    expression = "not has_behavior_flag($self.actor_id, 'STAT_MonsterChangePhase')"
    assert expression in out["hooks"][0]["condition"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(expression, source, {}) == 1
    eng._apply_modifier_spec(source, {
        "modifier_id": "ChangingPhase", "modifier_type": "buff", "duration": 0,
        "behavior_flags": ["STAT_MonsterChangePhase"]}, source)
    assert eng._hooks._hook_amount(expression, source, {}) == 0

    real = _real_compiler("2004020").compile_enemy()
    assert not any("STAT_MonsterChangePhase" in issue["reason"]
                   for issue in real["unsupported"])


@_need_ability
def test_real_damage_stance_translates_reduce_toughness():
    """真实 AML Boss IF DamageStance 节点形状：Force=true → reduce_toughness，
    目标=DefenderTargetType(Caster→self)、量走表达式通道（帧覆盖层活读）。"""
    task = {
        "$type": "RPG.GameCore.DamageStance",
        "StanceDamageType": {"DamageType": "Imaginary"},
        "DefenderTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "StanceValue": {"IsDynamic": False, "FixedValue": {"Value": 50}},
        "ForceStanceDamage": True, "IgnoreMuteBreak": True,
    }
    out = _task_skill(task, modifiers=None)
    effects = [e for h in out["hooks"] for e in h.get("effects", [])]
    reduces = [e for e in effects if e.get("effect_type") == "reduce_toughness"]
    assert reduces, f"DamageStance 应翻 reduce_toughness：{[e.get('effect_type') for e in effects]}"
    assert reduces[0]["target"] == "self" and reduces[0]["amount"] == 50
    # 动态量走 SkillParam 符号（真实 AML 节点动态槽形态在案）
    dyn_sources = {
        "character_config": {
            "SkillList": [{
                "Name": "Skill01", "SkillType": "Skill",
                "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
            }],
            "DynamicValues": {"Floats": {"1316389464": {"ReadInfo": {
                "Type": "SkillParam", "TriggerKey": "Skill01", "Index": 0}}}},
        },
        "abilities": {"A": {"Name": "A", "OnStart": [dict(
            task, StanceValue={"IsDynamic": True, "PostfixExpr": {
                "OpCodes": "AQAR", "FixedValues": [],
                "DynamicHashes": [1316389464]}})]}},
        "modifiers": {},
    }
    dyn = AbilityCompiler(
        "fake", [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": [50]}],
        dyn_sources).compile_skill("Skill01")
    dyn_reduces = [e for h in dyn["hooks"] for e in h.get("effects", [])
                   if e.get("effect_type") == "reduce_toughness"]
    assert dyn_reduces and dyn_reduces[0]["amount"] == 50

    task["ForceStanceDamage"] = False
    rejected = _task_skill(task)
    assert any("ForceStanceDamage=false" in i["reason"] for i in rejected["unsupported"])


def test_reduce_stance_ratio_uses_max_toughness_and_targets_last_summons():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.ReduceStanceRatio",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "ReduceValue": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["effect_type"] == "reduce_toughness" and effect["target"] == "self"
    eng = engine_vs_dummy(enemies=[make_dummy("source", max_toughness=120)])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.toughness == 90

    last_summons = _task_skill({
        "$type": "RPG.GameCore.ReduceStanceRatio",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LastSummonMonsters"},
        "ReduceValue": {"IsDynamic": False, "FixedValue": {"Value": 0.99}},
    })
    assert last_summons["ok"] and not last_summons["unsupported"]
    assert last_summons["hooks"][0]["effects"][0]["target"] == {"pool": "last_summons"}


def test_damage_stance_engine_level_reduces_toughness():
    """引擎级：reduce_toughness 效果实际削韧（假人韧性 9999 → 结算后扣量）。"""
    import types
    from tests._builders import engine_vs_dummy
    eng = engine_vs_dummy(mode="expected")
    eng._compiled_hooks = [types.SimpleNamespace(
        event="on_action", owner_id="e1", condition_expr=None,
        effects=({"effect_type": "reduce_toughness", "target": "self", "amount": 100},))]
    eng._hooks._subscribe_compiled_hooks()
    e1 = eng.state.actors["e1"]
    eng._execute_action(eng.state.actors["hero"], eng.actions_by_actor["hero"][0],
                        _action_broadcast={"actor": "hero", "action_type": "basic",
                                           "action_id": "b", "target_type": "single",
                                           "actor_type": "character"})
    assert e1.toughness == pytest.approx(9999 - 100), f"削韧未落地：{e1.toughness}"


def test_set_stance_count_empty_form_is_noop():
    out = _task_skill({
        "$type": "RPG.GameCore.SetStanceCount",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    })
    assert out["ok"] and not out["unsupported"]
    assert all(not hook.get("effects") for hook in out["hooks"])
    for task in (
        {"$type": "RPG.GameCore.SetStanceCount", "IsReset": True},
        {"$type": "RPG.GameCore.SetStanceCount", "AddCustomValue": {
            "IsDynamic": False, "FixedValue": {"Value": 1}}},
    ):
        rejected = _task_skill(task)
        assert not rejected["ok"]
        assert any("韧性条数重置/增减" in issue["reason"] for issue in rejected["unsupported"])

    for enemy_id in ("1004011", "3025010"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.SetStanceCount"
                       for issue in real["unsupported"])


def test_trigger_stance_countdown_emits_event_without_changing_toughness():
    from hsr_nous.adapters.enemy_ability import _PASSIVE_EVENT_MAP
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.TriggerStanceCountDown", "IgnoreMuteBreak": True,
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {
        "effect_type": "trigger_stance_countdown", "target": "all_enemies",
        "ignore_mute_break": True,
    }
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("partner")])
    before = {actor_id: state.toughness for actor_id, state in eng.state.actors.items()}
    events = []
    eng.bus.subscribe("on_stance_countdown", lambda _t, payload, _c: events.append(dict(payload)))
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert [payload["target"] for payload in events] == ["source", "partner"]
    assert all(payload["source"] == "source" and payload["ignore_mute_break"]
               for payload in events)
    assert {actor_id: state.toughness for actor_id, state in eng.state.actors.items()} == before
    assert not any(state.broken for state in eng.state.actors.values())
    assert _PASSIVE_EVENT_MAP["OnBeingStanceCountDown"] == (
        "hook", "on_stance_countdown", "$event.target == $self.actor_id")
    real_listener = _real_compiler("4015010").compile_enemy()
    assert not any("OnBeingStanceCountDown" in issue["path"]
                   for issue in real_listener["unsupported"])

    for enemy_id in ("1004024", "4015011"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.TriggerStanceCountDown"
                       for issue in real["unsupported"])


def test_show_ui_hint_dialog_is_presentation_only():
    out = _task_skill({
        "$type": "RPG.GameCore.ShowUI", "Name": "Ui.Battle.BattleCommonHintDialog",
        "Param": {"Value": "BattleMessage_Test"},
    })
    assert out["ok"] and not out["unsupported"]
    assert all(not hook.get("effects") for hook in out["hooks"])
    real = _real_compiler("2034014").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.ShowUI"
                   for issue in real["unsupported"])


def test_ultimate_prepare_precedes_cost_and_actual_fire():
    from hsr_nous.sim_schema.action import Action
    from tests._builders import engine_vs_dummy

    ult = Action(
        action_id="ult", name="终结技", action_type="ultimate", target_type="single",
        damage_type="fire", scaling=[{"atk": 1.0}], energy_cost=30)
    eng = engine_vs_dummy(actions={"hero": [ult]})
    hero = eng.state.actors["hero"]
    hero.current_energy = 30
    events = []
    eng.bus.subscribe("on_ultimate_prepare", lambda _t, payload, _c: events.append(
        ("prepare", {**payload, "energy": hero.current_energy})))
    eng.bus.subscribe("on_ultimate", lambda _t, payload, _c: events.append(
        ("fire", dict(payload))))
    assert eng._fire_ultimate(hero, ult)
    assert [name for name, _payload in events] == ["prepare", "fire"]
    assert events[0][1] == {"source": "hero", "action": "ult", "energy": 30}
    assert hero.current_energy == 5
    real = _real_compiler("4012050").compile_enemy()
    assert not any("UltraSkillPrepare" in issue["path"] for issue in real["unsupported"])
    alias = _real_compiler("4033021").compile_enemy()
    assert not any(issue["node_type"] == "OnBeforeUltraSkillPrepare"
                   for issue in alias["unsupported"])
    assert any(hook["event"] == "on_ultimate_prepare"
               and "BlackMonst" in str(hook) for hook in alias["hooks"])


def test_weakness_grant_and_lock_family():
    """AddWeakness/任务位 StackWeakness/ClearWeakness 翻译形态钉
    （真实节点形状：Yanqing IF 弱点植入/Cocolia IF 韧性锁）。"""
    add_weakness = {
        "$type": "RPG.GameCore.AddWeakness",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "DamageType": "Wind",
    }
    out = _task_skill(add_weakness)
    effects = [e for h in out["hooks"] for e in h.get("effects", [])]
    (grant,) = [e for e in effects if e.get("effect_type") == "apply_modifier"]
    mod = grant["modifier"]
    assert mod["weakness_add"] == ["wind"] and mod["dispellable"] is False
    assert mod["modifier_id"] == "ENEMY_s1_WEAKNESS_WIND"

    stack_lock = {
        "$type": "RPG.GameCore.StackWeakness",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "OPType": "Protected",
        "WeakList": ["Physical", "Fire", "Ice", "Thunder", "Wind", "Quantum", "Imaginary"],
    }
    out = _task_skill(stack_lock)
    effects = [e for h in out["hooks"] for e in h.get("effects", [])]
    (lock,) = [e for e in effects if e.get("effect_type") == "apply_modifier"]
    assert lock["modifier"]["toughness_lock"] is True
    lock_id = lock["modifier"]["modifier_id"]

    clear_lock = {
        "$type": "RPG.GameCore.ClearWeakness",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "OPType": "Protected",
        "WeakList": ["Physical", "Fire", "Ice", "Thunder", "Wind", "Quantum", "Imaginary"],
    }
    out = _task_skill(clear_lock)
    effects = [e for h in out["hooks"] for e in h.get("effects", [])]
    (clear,) = [e for e in effects if e.get("effect_type") == "remove_modifier"]
    assert clear["modifier_id"] == lock_id, "清除必须与锁同件配对命名"
    default_clear = dict(clear_lock)
    default_clear.pop("OPType")
    default_out = _task_skill(default_clear)
    assert default_out["ok"] and not default_out["unsupported"]
    assert default_out["hooks"] == out["hooks"]


def test_partial_weakness_protection_attach_and_clear():
    from dataclasses import replace
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    protected = {
        "$type": "RPG.GameCore.StackWeakness",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "OPType": "Protected", "WeakList": ["Fire", "Wind"],
    }
    out = _task_skill(protected)
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [effect["modifier"]["protected_weakness"] for effect in effects] == [["fire"], ["wind"]]
    eng = engine_vs_dummy(enemies=[make_dummy("source", weakness=("fire", "wind"))])
    source, hero = eng.state.actors["source"], eng.state.actors["hero"]
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    eng._apply_toughness_damage(hero.actor, basic_action(toughness_dmg=30), source)
    assert source.toughness == source.actor.stats.max_toughness
    clear = {**protected, "$type": "RPG.GameCore.ClearWeakness", "WeakList": ["Wind"]}
    clear_out = _task_skill(clear)
    assert clear_out["ok"] and not clear_out["unsupported"]
    eng._hooks._run_hook_effect(source, clear_out["hooks"][0]["effects"][0], {})
    assert source.modifiers["ENEMY_s1_PROTECTED_FIRE"].protected_weakness == ["fire"]
    assert source.modifiers["ENEMY_s1_PROTECTED_WIND"].protected_weakness == []
    eng._apply_toughness_damage(
        hero.actor, basic_action(damage_type="wind", toughness_dmg=30), source)
    assert source.toughness == source.actor.stats.max_toughness - 30
    eng._apply_toughness_damage(hero.actor, replace(
        basic_action(toughness_dmg=30), toughness_scope="all"), source)
    assert source.toughness == source.actor.stats.max_toughness - 60

    attached = {**protected, "OPType": "Attach", "WeakList": ["Ice", "Quantum"]}
    attach_out = _task_skill(attached)
    assert attach_out["ok"] and not attach_out["unsupported"]
    assert [effect["modifier"]["weakness_add"]
            for effect in attach_out["hooks"][0]["effects"]] == [["ice"], ["quantum"]]


def test_weakness_override_empty_and_secret_visibility():
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    secret = {
        "$type": "RPG.GameCore.StackWeakness",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "WeakList": ["Wind"], "SecretList": ["Wind"],
    }
    out = _task_skill(secret)
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["weakness_override"] == ["wind"]
    assert effect["modifier"]["secret_weakness"] == ["wind"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source, hero = eng.state.actors["source"], eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng.pipeline.effective_weakness(source) == {"wind"}
    eng._apply_toughness_damage(
        hero.actor, basic_action(damage_type="wind", toughness_dmg=30), source)
    assert source.toughness == source.actor.stats.max_toughness - 30

    reveal = _task_skill({
        "$type": "RPG.GameCore.ClearWeakness", "OPType": "Secret",
        "WeakList": ["Wind"],
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    })
    assert reveal["ok"] and not reveal["unsupported"]
    eng._hooks._run_hook_effect(source, reveal["hooks"][0]["effects"][0], {})
    modifier = source.modifiers["ENEMY_s1_WEAKNESS_OVERRIDE"]
    assert modifier.secret_weakness == []
    assert eng.pipeline.effective_weakness(source) == {"wind"}

    empty = _task_skill({**secret, "WeakList": [], "SecretList": []})
    assert empty["ok"] and not empty["unsupported"]
    empty_effect = empty["hooks"][0]["effects"][0]
    assert empty_effect["modifier"]["weakness_override"] == []
    eng._hooks._run_hook_effect(source, empty_effect, {})
    assert eng.pipeline.effective_weakness(source) == set()
    attach = _task_skill({**secret, "OPType": "Attach", "WeakList": ["Ice"], "SecretList": []})
    eng._hooks._run_hook_effect(source, attach["hooks"][0]["effects"][0], {})
    assert eng.pipeline.effective_weakness(source) == {"ice"}
    clear_attach = _task_skill({
        "$type": "RPG.GameCore.ClearWeakness", "OPType": "Attach", "WeakList": ["Ice"],
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    })
    assert clear_attach["ok"] and not clear_attach["unsupported"]
    eng._hooks._run_hook_effect(source, clear_attach["hooks"][0]["effects"][0], {})
    assert eng.pipeline.effective_weakness(source) == set()


def test_modifier_partial_weakness_protection_survives_definition_lifecycle():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier", "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Protection"},
    }]
    sources["modifiers"]["Protection"] = {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackWeakness", "OPType": "Protected",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "WeakList": ["Fire", "Ice"],
        }],
    }]}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["protected_weakness"] == ["fire", "ice"]

    sources["modifiers"]["Protection"]["_CallbackList"][0]["CallbackConfig"][0] = {
        "$type": "RPG.GameCore.StackWeakness", "WeakList": ["Fire"],
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    }
    overridden = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert overridden["ok"] and not overridden["unsupported"]
    assert overridden["hooks"][0]["effects"][0]["modifier"]["weakness_override"] == ["fire"]

    all_type = _task_skill({
        "$type": "RPG.GameCore.StackWeakness", "OPType": "Protected",
        "WeakList": ["AllType"],
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    })
    assert all_type["ok"] and not all_type["unsupported"]
    assert all_type["hooks"][0]["effects"][0]["modifier"]["toughness_lock"] is True


def test_stacking_prolong_and_replace_keep_duration():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [
        {"$type": "RPG.GameCore.AddModifier", "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
         "ModifierName": {"Value": "Parasitism"}},
        {"$type": "RPG.GameCore.AddModifier", "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
         "ModifierName": {"Value": "Flesh"}},
    ]
    sources["modifiers"] = {
        "Parasitism": {"Stacking": "ReplaceButKeepLifeTime",
                       "BehaviorFlagList": ["RemoveWhenCasterDead"]},
        "Flesh": {"Stacking": "Prolong", "BehaviorFlagList": ["RemoveWhenCasterDead"]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[0]["modifier"]["stack_mode"] == "replace_keep_duration"
    assert effects[1]["modifier"]["stack_mode"] == "refresh"


def test_retain_global_latest_unique_uses_global_singleton_group():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [
        {"$type": "RPG.GameCore.AddModifier", "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
         "ModifierName": {"Value": "Screen01_Effect"}},
        {"$type": "RPG.GameCore.AddModifier", "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
         "ModifierName": {"Value": "Screen02_Effect"}},
    ]
    sources["modifiers"] = {
        "Screen01_Effect": {"Stacking": "RetainGlobalLatestUnique",
                            "BehaviorFlagList": ["KeepOnDeathrattle"]},
        "Screen02_Effect": {"Stacking": "RetainGlobalLatestUnique",
                            "BehaviorFlagList": ["KeepOnDeathrattle"]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[0]["modifier"]["singleton_group"] == "global:Screen01_Effect"
    assert effects[1]["modifier"]["singleton_group"] == "global:Screen02_Effect"


def test_merge_stacking_uses_refresh_merge_semantics():
    from tests._builders import engine_vs_dummy, make_dummy
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "MergeStats"},
    }]
    sources["modifiers"]["MergeStats"] = {
        "LifeTime": 2, "MaxLayer": 3, "Stacking": "Merge",
        "_CallbackList": [{"Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
        }, {
            "$type": "RPG.GameCore.StackProperty", "Property": "DirtyHPRatio",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
        }, {
            "$type": "RPG.GameCore.StackProperty", "Property": "DirtyHPDelta",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 500}},
        }]}],
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["stack_mode"] == "refresh"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    source.modifiers["MergeStats"].duration = 1
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.modifiers["MergeStats"].stacks == 2
    assert source.modifiers["MergeStats"].duration == 2
    stats = eng.pipeline.effective_stats(source)
    assert stats["recoverable_hp_reduction"] == pytest.approx(0.25)
    assert stats["recoverable_hp_delta"] == pytest.approx(500)
    source.actor.stats.hp = 10000
    source.current_hp = 0
    eng.pipeline.heal(source, source, amount=10000)
    assert source.current_hp == pytest.approx(7000)

    real = _real_compiler("4015011").compile_enemy()
    assert not any(item["reason"] == "未注册叠加语义：Merge"
                   for item in real["unsupported"])


def test_onstack_property_overrides_and_shared_stats():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier", "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Stats"},
    }]
    sources["modifiers"]["Stats"] = {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [
            {"$type": "RPG.GameCore.StackProperty", "Property": "BaseSpeed",
             "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0}},
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}},
            {"$type": "RPG.GameCore.StackProperty", "Property": "CriticalChanceBase",
             "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.8}},
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}},
            {"$type": "RPG.GameCore.StackProperty", "Property": "MaxStance",
             "PropertyValue": _dynamic("AQAR", hashes=[dynamic_value_hash("_MaxStance")]),
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}},
            {"$type": "RPG.GameCore.StackProperty", "Property": "AllDamageTypeResistance",
             "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.2}},
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}},
            {"$type": "RPG.GameCore.StackProperty", "Property": "AllDamageTypePenetrate",
             "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.15}},
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}},
            {"$type": "RPG.GameCore.StackProperty", "Property": "BreakDamageAddedRatioBase",
             "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.3}},
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}},
            {"$type": "RPG.GameCore.StackProperty", "Property": "StanceBreakAddedRatio",
             "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}},
            {"$type": "RPG.GameCore.StackProperty", "Property": "StanceBreakTakenRatio",
             "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}},
        ],
    }]}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["override_effects"] == {"spd": 0, "crit_rate": 0.8}
    assert effect["modifier"]["override_exprs"] == {
        "max_toughness": "dynamic_of($self.actor_id, '_MaxStance')"}
    assert effect["modifier"]["stat_effects"]["res_fire"] == 0.2
    assert effect["modifier"]["stat_effects"]["res_pen"] == 0.15
    assert effect["modifier"]["stat_effects"]["break_effect"] == 0.3
    assert effect["modifier"]["stat_effects"]["break_efficiency_boost"] == 0.5
    assert effect["modifier"]["stat_effects"]["toughness_taken"] == 0.25
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    runtime = eng._enemy_policy_state.setdefault("source", {
        "current_phase": 1, "dynamic_values": {}})
    runtime["dynamic_values"]["_MaxStance"] = 200
    eng._hooks._run_hook_effect(source, effect, {})
    stats = eng.pipeline.effective_stats(source)
    assert stats["spd"] == 0 and stats["crit_rate"] == 0.8
    assert stats["res_fire"] == 0.2 and stats["res_quantum"] == 0.2
    assert stats["res_pen"] == 0.15 and stats["break_effect"] == 0.3
    assert stats["break_efficiency_boost"] == 0.5 and stats["max_toughness"] == 200
    assert stats["toughness_taken"] == 0.25
    assert eng.pipeline.toughness_damage_amount(None, 40, target=source) == 50
    assert eng.scheduler.spd_of(eng.scheduler.handle_of("source")) == 0
    eng._hooks._run_hook_effect(source, {"effect_type": "reset_stance", "target": "self"}, {})
    assert source.toughness == 200

    real = _real_compiler("5014014").compile_enemy()
    assert not any(issue["reason"] == "未注册属性：AllDamageTypePenetrate"
                   for issue in real["unsupported"])
    real_huanlong = _real_compiler("8015022").compile_enemy()
    assert not any(issue["reason"] == "未注册属性：BreakDamageAddedRatioBase"
                   for issue in real_huanlong["unsupported"])


def test_weakness_engine_level_effective_weakness():
    """引擎级：弱点植入 modifier 进有效弱点并集（pipeline weakness_add 消费点在案）。"""
    import types
    from tests._builders import engine_vs_dummy
    eng = engine_vs_dummy(mode="expected")
    eng._compiled_hooks = [types.SimpleNamespace(
        event="on_action", owner_id="e1", condition_expr=None,
        effects=({"effect_type": "apply_modifier", "target": "self", "modifier": {
            "modifier_id": "ENEMY_T_WEAKNESS_WIND", "name": "w", "modifier_type": "debuff",
            "duration": 0, "dispellable": False, "weakness_add": ["wind"]}},))]
    eng._hooks._subscribe_compiled_hooks()
    e1 = eng.state.actors["e1"]
    eng._execute_action(eng.state.actors["hero"], eng.actions_by_actor["hero"][0],
                        _action_broadcast={"actor": "hero", "action_type": "basic",
                                           "action_id": "b", "target_type": "single",
                                           "actor_type": "character"})
    weakness = eng.pipeline.effective_weakness(e1) if hasattr(
        eng.pipeline, "effective_weakness") else None
    if weakness is None:
        # 消费点内联于弱点判定——直接用结算路径验证（风弱命中变化）
        from hsr_nous.sim_schema.expression import parse
        from hsr_nous.sim.enemy_ai import config_ai_dynamic_value
        assert "ENEMY_T_WEAKNESS_WIND" in e1.modifiers
    else:
        assert "wind" in weakness


def test_perform_delay_execute_presentation_ignored_mechanism_rejected():
    """PerformDelayExecute 两态：纯表现内容忽略；机制内容显式拒（时机未收编）。"""
    presentation = {
        "$type": "RPG.GameCore.PerformDelayExecute",
        "PerformTaskList": [{
            "$type": "RPG.GameCore.SetCharacterPartsVisibility",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntityList"},
            "AttachPoint": "Body", "ShowPartList": [1, 3], "SyncEffect": True}],
    }
    out = _task_skill(presentation)
    assert out["ok"] and not out["unsupported"]
    mechanism = {
        "$type": "RPG.GameCore.PerformDelayExecute",
        "PerformTaskList": [{
            "$type": "RPG.GameCore.DefineDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "X"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
    }
    rejected = _task_skill(mechanism)
    assert any("Perform 时点" in i["reason"] for i in rejected["unsupported"])


def test_battle_play_video_checks_callback_tasks():
    presentation = {
        "$type": "RPG.GameCore.BattlePlayVideo", "VideoID": 1,
        "OnBeginPlay": [{"$type": "RPG.GameCore.SetBattleBGMState"}],
    }
    out = _task_skill(presentation)
    assert out["ok"] and not out["unsupported"]
    rejected = _task_skill({**presentation, "OnBeginPlay": [{
        "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "X"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}]})
    assert any("视频播放回调" in issue["reason"] for issue in rejected["unsupported"])


def test_add_buff_perform_only_accepts_presentation_tasks():
    presentation = {
        "$type": "RPG.GameCore.AddBuffPerform", "TaskList": [{
            "$type": "RPG.GameCore.TriggerEffect", "EffectPath": "Effects/Buff.prefab"}],
        "AddPerformTime": {"IsDynamic": False, "FixedValue": {"Value": 0.75}},
    }
    out = _task_skill(presentation)
    assert out["ok"] and not out["unsupported"]
    mechanism = {**presentation, "TaskList": [{
        "$type": "RPG.GameCore.DefineDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "DynamicKey": {"Value": "X"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}]}
    rejected = _task_skill(mechanism)
    assert any("含机制任务" in issue["reason"] for issue in rejected["unsupported"])


def test_lose_hp_by_current_hp_respects_floor():
    from tests._builders import engine_vs_dummy, make_dummy
    out = _task_skill({
        "$type": "RPG.GameCore.LoseHPByRatio", "RatioType": "CurrentHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Ratio": {"IsDynamic": False, "FixedValue": {"Value": 0.8}},
        "Floor": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount"] == "0.8 * $self.hp" and effect["floor"] == 1
    eng = engine_vs_dummy(enemies=[make_dummy("source", hp=100)])
    source = eng.state.actors["source"]
    source.current_hp = 10
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.current_hp == 2
    source.current_hp = 1
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.current_hp == 1


def test_lose_hp_absolute_resolves_literal_monster_target():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.pipeline.enemies.loader import get_monster_id_by_config_alias
    from tests._builders import engine_vs_dummy, make_dummy
    assert get_monster_id_by_config_alias("Monster_W4_IronTombCore_00") == "4035010"
    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_hp_decrease")
    compiler._compile_lose_hp_absolute({
        "$type": "RPG.GameCore.LoseHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Monster_W4_IronTombCore_00"},
        "DamageValue": {"IsDynamic": False, "FixedValue": {"Value": 12}},
    }, ctx, "P", ())
    assert not ctx.unsupported
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("4035010")])
    source, boss = eng.state.actors["source"], eng.state.actors["4035010"]
    boss.current_hp = 100
    eng._hooks._run_hook_effect(source, ctx.effects[0], {})
    assert boss.current_hp == 88 and source.current_hp == source.actor.stats.hp

    combo = compiler._hook_target(
        "Monster_W4_IronTombCorePart_00 + Monster_W4_IronTombCorePart_01", ctx)
    assert len(combo["concat"]) == 2
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("4032060"),
                                   make_dummy("4032070")])
    selected = eng._hooks._hook_target_states(combo, eng.state.actors["source"], {})
    assert {state.actor.actor_id for state in selected} == {"4032060", "4032070"}

    rejected = _Context(mode="event", skill=skills[0], event="on_hp_decrease")
    compiler._compile_lose_hp_absolute({
        "$type": "RPG.GameCore.LoseHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "DamageValue": {"IsDynamic": False, "FixedValue": {"Value": 12}},
    }, rejected, "P", ())
    assert any("回流" in issue["reason"] for issue in rejected.unsupported)


def test_set_hp_modify_ratio_sets_target_max_hp_percent():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.SetHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifyRatio": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        "ShowText": False,
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "set_hp_to_percent", "target": "self", "percent": 0.5}
    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    source.current_hp = 100.0
    eng._hooks._run_hook_effect(source, effect, {})
    assert source.current_hp == source.actor.stats.hp * 0.5

    absolute = _task_skill({
        "$type": "RPG.GameCore.SetHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert absolute["ok"] and not absolute["unsupported"]
    absolute_effect = absolute["hooks"][0]["effects"][0]
    assert absolute_effect["effect_type"] == "set_hp_to_percent"
    assert "$target.max_hp" in absolute_effect["percent"]
    eng._hooks._run_hook_effect(source, absolute_effect, {})
    assert source.current_hp == 1.0

    absolute_effect = {**absolute_effect, "target": {"pool": "allies"}}
    eng._hooks._run_hook_effect(source, absolute_effect, {})
    assert eng.state.actors["hero"].current_hp == 1.0
    assert eng.state.actors["ally"].current_hp == 1.0
    real = _real_compiler("1004025").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.SetHP" for item in real["unsupported"])


@_need_ability
def test_set_hp_source_type_uses_actual_modifier_caster():
    from hsr_nous.adapters.enemy_ability import _Context
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    task = {
        "$type": "RPG.GameCore.SetHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        "ShowText": False,
        "SourceType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }
    compiler = AbilityCompiler("fake", [], {"modifiers": {"Mark": {}}})
    ctx = _Context(mode="event", skill={"skill_id": "s1"},
                   event="on_revive", current_modifier="Mark")
    compiler._compile_set_hp(task, ctx, "test", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    assert effect == {
        "effect_type": "set_hp_to_percent", "target": "self",
        "percent": "1 / $target.max_hp", "source": "modifier:Mark",
    }

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    hero, source = eng.state.actors["hero"], eng.state.actors["source"]
    hero.modifiers["Mark"] = Modifier(
        modifier_id="Mark", name="Mark", modifier_type="debuff", source_id="source")
    hp_events, kill_events = [], []
    eng.bus.subscribe("on_hp_decrease",
                      lambda _event, payload, _ctx: hp_events.append(dict(payload)))
    eng.bus.subscribe("on_kill", lambda _event, payload, _ctx: kill_events.append(dict(payload)))
    eng._hooks._run_hook_effect(hero, effect, {})
    assert hero.current_hp == 1
    assert hp_events[-1]["source"] == source.actor.actor_id
    eng._hooks._run_hook_effect(hero, dict(effect, percent=0), {})
    assert kill_events[-1]["source"] == source.actor.actor_id

    rejected = _task_skill(task)
    assert not rejected["ok"]
    assert any("SourceType" in issue["reason"] for issue in rejected["unsupported"])
    for enemy_id in ("4015011", "4015020", "4015021"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.SetHP"
                       for issue in real["unsupported"])


def test_phase_custom_event_trigger_and_flagged_listener():
    from types import SimpleNamespace
    from tests._builders import engine_vs_dummy, make_dummy

    begin_out = _task_skill({
        "$type": "RPG.GameCore.TriggerModifierCustomEvent",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "BattleAllEntity.GetAliveOrLimbo"},
        "IncludeLimbo": True,
        "EventType": {"EnumIndex": 4, "Value": 13},
        "OverrideParamEntity": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    })
    end_out = _task_skill({
        "$type": "RPG.GameCore.TriggerModifierCustomEvent",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "BattleAllEntity.GetAliveOrLimbo"},
        "EventType": {"EnumIndex": 4, "Value": 8},
    })
    assert begin_out["ok"] and end_out["ok"]
    begin = begin_out["hooks"][0]["effects"][0]
    end = end_out["hooks"][0]["effects"][0]
    assert begin == {
        "effect_type": "emit_phase_custom_event",
        "phase_event": "monster_phase_change_begin", "include_limbo": True,
        "param_entity": "self",
    }
    assert end == {
        "effect_type": "emit_phase_custom_event",
        "phase_event": "monster_phase_change_end", "include_limbo": False,
    }

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Controller"},
    }]
    sources["modifiers"] = {"Controller": {
        "BehaviorFlagList": ["CustomEvent_MonsterChangePhaseTrigger"],
        "_CallbackList": [{
            "Event": "OnCustomEvent",
            "CallbackConfig": [{
                "$type": "RPG.GameCore.SetDynamicValue",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "DynamicKey": {"Value": "PhaseEnd"},
                "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
        }],
    }}
    listener = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert listener["ok"] and not listener["unsupported"]
    phase_hook = next(h for h in listener["hooks"]
                      if h["event"] == "monster_phase_change_end")
    assert phase_hook["condition"] == "$self.actor_id in $event.targets"
    mount = next(e for h in listener["hooks"] for e in h["effects"]
                 if e["effect_type"] == "apply_modifier")

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("limbo"), make_dummy("dead")])
    source = eng.state.actors["source"]
    eng.state.actors["limbo"].current_hp = -1.0
    eng.state.actors["dead"].alive = False
    eng._hooks._run_hook_effect(source, mount, {})
    assert "Controller" in source.modifiers
    compiled = SimpleNamespace(
        condition_expr=eng._expr.compile(phase_hook["condition"], layer="effect"),
        owner_id="source", event="monster_phase_change_end")

    def on_end(_event, payload, _ctx):
        if eng._hooks._hook_condition_ok(compiled, source, payload):
            for effect in phase_hook["effects"]:
                eng._hooks._run_hook_effect(source, effect, payload)

    emitted = {"begin": [], "end": []}
    eng.bus.subscribe("monster_phase_change_begin",
                      lambda _et, p, _c: emitted["begin"].append(p))
    eng.bus.subscribe("monster_phase_change_end", on_end)
    eng.bus.subscribe("monster_phase_change_end",
                      lambda _et, p, _c: emitted["end"].append(p))
    eng._hooks._run_hook_effect(source, begin, {})
    assert set(emitted["begin"][0]["targets"]) == {"hero", "source", "limbo"}
    assert "PhaseEnd" not in eng._enemy_policy_state.get("source", {}).get("dynamic_values", {})
    eng._hooks._run_hook_effect(source, end, {})
    assert set(emitted["end"][0]["targets"]) == {"hero", "source"}
    assert emitted["end"][0]["param_entity"] == "source"
    assert eng._enemy_policy_state["source"]["dynamic_values"]["PhaseEnd"] == 1


def test_global_dynamic_offset_is_presentation_only():
    out = _task_skill({
        "$type": "RPG.GameCore.AddGlobalDynamicOffset",
        "ConfigName": {"Value": "W3_Sunday_00_P3"},
    })
    assert out["ok"] and not out["unsupported"]
    assert all(not hook["effects"] for hook in out["hooks"])


def test_effect_animator_parameter_is_presentation_only():
    out = _task_skill({
        "$type": "RPG.GameCore.SetEffectAnimatorParameter",
        "UniqueEffectName": {"RawString": "OverdriveEffect"},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ParameterName": "State", "ParameterType": "Int",
        "IntValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert out["ok"] and not out["unsupported"]
    assert all(not hook["effects"] for hook in out["hooks"])


def test_lock_target_hp_and_unlock_target_hp_pair():
    from tests._builders import engine_vs_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.LockTargetHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Threshold": {"IsDynamic": False, "FixedValue": {"Value": 0.001}},
    }, {
        "$type": "RPG.GameCore.UnlockTargetHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    lock = next(effect for effect in effects if effect["effect_type"] == "apply_modifier")
    unlock = next(effect for effect in effects if effect["effect_type"] == "remove_modifier")
    assert lock["modifier"]["hp_lock"]
    assert unlock["modifier_id"] == lock["modifier"]["modifier_id"]

    eng = engine_vs_dummy()
    source = eng.state.actors["e1"]
    eng._hooks._run_hook_effect(source, lock, {})
    source.current_hp = 0
    eng._check_death(source, "hero", action_id="hit")
    assert source.alive and source.current_hp == 1
    eng._hooks._run_hook_effect(source, unlock, {})
    source.current_hp = 0
    eng._check_death(source, "hero", action_id="hit")
    assert not source.alive


def test_unregistered_task_reasons_specific_not_generic():
    """_UNREGISTERED_TASK_REASONS 逐型理由钉：LockHP/CreateBattleEvent 不再只报
    '未注册任务节点'。"""
    lockhp = {"$type": "RPG.GameCore.LockHP",
              "Threshold": {"IsDynamic": False, "FixedValue": {"Value": 0.01}}}
    create = {"$type": "RPG.GameCore.CreateBattleEvent",
              "EventID": {"IsDynamic": False, "FixedValue": {"Value": 20001}},
              "PropertyFromTarget": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}}
    out = _task_skill(create)
    assert out["ok"], out["unsupported"]
    assert any(e["effect_type"] == "create_battle_event" and e.get("event_id") == 20001
               for h in out["hooks"] for e in h["effects"])
    # LockHP 已收编（决策卡 #43）——锁血 modifier 编译通过
    out = _task_skill(lockhp)
    assert out["ok"], out["unsupported"]


def test_modifier_owner_caster_filter_uses_hook_owner_not_event_source():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    expr = _pred_expr({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "ModifierName": {"Value": "Mark"},
        "CasterFilter": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    }, event="after_remove_modifier")
    assert expr == "has_modifier($event.target, 'Mark', $self.actor_id)"

    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("other")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    payload = {"source": "other", "target": "hero", "modifier_id": "Parent"}
    hero.modifiers["Mark"] = Modifier(
        modifier_id="Mark", name="Mark", modifier_type="debuff", source_id="source")
    assert eng._hooks._hook_amount(expr, source, payload) == 1.0
    hero.modifiers["Mark"].source_id = "other"
    assert eng._hooks._hook_amount(expr, source, payload) == 0.0


def test_get_creator_reads_summoner_in_character_and_modifier_contexts():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    entering = _pred_expr({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity.GetCreator"},
        "ModifierName": {"Value": "Curse"},
    }, event="actor_enter")
    assert entering == "has_modifier(summoner_of($event.actor), 'Curse')"
    owner = _pred_expr({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity.GetCreator"},
        "ModifierName": {"Value": "Curse"},
    }, event="after_apply_modifier")
    assert owner == "has_modifier(summoner_of($self.actor_id), 'Curse')"

    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("creator")])
    source = eng.state.actors["source"]
    creator = eng.state.actors["creator"]
    source.actor.summoner_id = "creator"
    payload = {"actor": "source", "target": "source", "modifier_id": "Curse"}
    assert eng._hooks._hook_amount(entering, source, payload) == 0.0
    assert eng._hooks._hook_amount(owner, source, payload) == 0.0
    eng._apply_modifier(creator, Modifier(
        modifier_id="Curse", name="Curse", modifier_type="debuff"))
    assert eng._hooks._hook_amount(entering, source, payload) == 1.0
    assert eng._hooks._hook_amount(owner, source, payload) == 1.0


def test_create_battle_event_materializes_unique_modifier_target():
    from tests._builders import engine_vs_dummy, make_dummy

    create = {
        "$type": "RPG.GameCore.CreateBattleEvent",
        "EventID": {"IsDynamic": False, "FixedValue": {"Value": 20034}},
        "Team": "TeamNeutral",
        "OnBattleEventCreate": [{
            "$type": "RPG.GameCore.SetTargetUniqueName",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "UniqueName": {"RawString": "SelectTarget"},
        }, {
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "Marker"},
        }],
    }
    out = _task_skill(create, modifiers={
        "Marker": {"BehaviorFlagList": ["RemoveWhenCasterDead"]},
    })
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    reserved = "unique:$battle_event:20034"
    assert effects[0]["effect_type"] == "create_battle_event"
    assert effects[1]["target"] == {"pool": reserved}
    assert effects[2]["target"] == {"pool": reserved}

    direct = _pred_expr({
        "$type": "RPG.GameCore.ByCompareBattleEventID",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "TargetBattleEventID": {"IsDynamic": False, "FixedValue": {"Value": 20034}},
    }, event="battle_event_create")
    assert direct == "$event.event_id == 20034"
    creator = _pred_expr({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity.GetCreator"},
        "ModifierName": {"Value": "Marker"},
    }, event="battle_event_create")
    assert creator == "has_modifier($event.source, 'Marker')"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    emitted = []
    eng.bus.subscribe("battle_event_create", lambda et, p, c: emitted.append(p))
    for effect in effects:
        eng._hooks._run_hook_effect(source, effect, {})
    assert emitted == [{
        "actor": "$battle_event:20034", "event_id": 20034,
        "source": "source", "team": "TeamNeutral",
    }]
    state = eng.battle_events[20034]["actor_state"]
    assert state.alive and "Marker" in state.modifiers
    assert state.actor.actor_id not in eng.state.actors
    assert eng._hooks._hook_target_states(
        {"pool": "unique:SelectTarget"}, source, {}) == [state]
    assert eng._hooks._hook_amount(
        'actor_alive(unique_target("SelectTarget"))', source, {}) == 1.0


def test_numeric_battle_event_alias_reads_energy_and_uses_death_chain():
    from tests._builders import engine_vs_dummy, make_dummy

    alias = {"$type": "RPG.GameCore.TargetAlias", "Alias": "BattleEvent_60048"}
    read = _task_skill({
        "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "_CurrentBPSP",
        "ReadTargetType": alias, "Value": "CurrentSP",
    })
    assert read["ok"] and not read["unsupported"]
    read_effect = read["hooks"][0]["effects"][0]
    assert read_effect["amount"] == "energy_of(unique_target('$battle_event:60048'))"

    kill = _task_skill({"$type": "RPG.GameCore.SetDieImmediately", "TargetType": alias})
    assert kill["ok"] and not kill["unsupported"]
    assert kill["hooks"][0]["effects"][0]["target"] == {"pool": "unique:$battle_event:60048"}

    create = _task_skill({
        "$type": "RPG.GameCore.CreateBattleEvent",
        "EventID": {"IsDynamic": False, "FixedValue": {"Value": 60048}},
    })
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, create["hooks"][0]["effects"][0], {})
    event_state = eng.battle_events[60048]["actor_state"]
    event_state.current_energy = 18.0
    eng._hooks._run_hook_effect(source, read_effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["_CurrentBPSP"] == 18.0
    eng._hooks._run_hook_effect(source, kill["hooks"][0]["effects"][0], {})
    assert not event_state.alive

    default = _task_skill({"$type": "RPG.GameCore.SetDieImmediately"})
    assert default["ok"] and not default["unsupported"]
    assert default["hooks"][0]["effects"][0]["target"] == "self"


def test_team_battle_event_aliases_compose_and_exclude():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    base = "AllLightTeamWithAllUnselectableLightTeam"
    plus = _task_skill({
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": f"{base} + BattleEvent_60048"},
        "ModifierName": {"Value": "Marker"},
    }, modifiers={"Marker": {"BehaviorFlagList": ["RemoveWhenCasterDead"]}})
    minus = _task_skill({
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": f"{base} - BattleEvent_60048"},
        "ModifierName": {"Value": "Marker"},
    }, modifiers={"Marker": {"BehaviorFlagList": ["RemoveWhenCasterDead"]}})
    assert plus["ok"] and not plus["unsupported"]
    assert minus["ok"] and not minus["unsupported"]
    plus_target = plus["hooks"][0]["effects"][0]["target"]
    minus_target = minus["hooks"][0]["effects"][0]["target"]
    assert plus_target == {"concat": [
        {"pool": "allies", "include_unselectable": True},
        {"pool": "unique:$battle_event:60048"},
    ]}
    assert minus_target == {
        "pool": "allies", "include_unselectable": True,
        "where": "$it.actor_id != unique_target('$battle_event:60048')",
    }

    create = _task_skill({
        "$type": "RPG.GameCore.CreateBattleEvent",
        "EventID": {"IsDynamic": False, "FixedValue": {"Value": 60048}},
    })
    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    ally = eng.state.actors["ally"]
    ally.actor.summon_flags["ally_targetable"] = False
    eng._hooks._run_hook_effect(source, create["hooks"][0]["effects"][0], {})
    event_state = eng.battle_events[60048]["actor_state"]
    picked_plus = eng._hooks._hook_target_states(plus_target, source, {})
    picked_minus = eng._hooks._hook_target_states(minus_target, source, {})
    assert [state.actor.actor_id for state in picked_plus] == [
        "hero", "ally", "$battle_event:60048"]
    assert [state.actor.actor_id for state in picked_minus] == ["hero", "ally"]


def test_team_target_alias_variants_use_registered_target_algebra():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    expected = {
        "TauntOrAggroEnemy": {"pool": "enemy_targets", "take": 1, "mode": "taunt_or_aggro"},
        "AllEnemy.RemoveServant": {"pool": "allies", "where": "not $it.summoner_id"},
        "AllLightAvatar": {"pool": "allies", "where": "actor_type_of($it) == 'character'"},
        "AllLightTeam - ModifierOwnerEntity": {
            "pool": "allies", "where": "$it.actor_id != $self.actor_id"},
        "AllDarkTeam - ModifierOwnerEntity": {
            "pool": "enemies", "where": "$it.actor_id != $self.actor_id"},
        "AllDarkTeamUnselectable": {
            "pool": "enemies", "include_unselectable": True,
            "where": "not ($it.enemy_targetable and $it.ally_targetable)"},
        "AllEnemy.GetServant": {"pool": "allies", "where": "$it.summoner_id"},
        "ServantEntityList": {
            "pool": "all", "include_unselectable": True,
            "where": "actor_type_of($it) == 'summon'"},
        "AllLightTeamOnlyAddSPOnceForServant": {
            "pool": "allies", "where": "not $it.summoner_id"},
        "AllLightTeam.SortByHP.Reverse": {"pool": "allies", "order_by": "-$it.hp"},
        "AbilityTargetEntity.GetSummoner": {
            "pool": "all", "where": "$it.actor_id == summoner_of($event.target)"},
        "Monster_Svarog_00_Unselectable": {
            "pool": "enemies", "include_unselectable": True,
            "where": "in_group($it, 'W1_SvarogPart')"},
        "Monster_Svarog_00_RL_Unselectable": {
            "pool": "enemies", "include_unselectable": True,
            "where": "in_group($it, 'W1_SvarogPart') and in_group($it, 'RL')"},
        "ModifierOwnerEntityAllTeammate": {
            "pool": "enemies", "where": "$it.actor_id != $self.actor_id"},
        "ModifierOwnerEntityAdjoinEntity": {
            "pool": "enemies", "where": "is_adjacent($it, $self.actor_id)"},
        "ProjectileHitEntityAdjoinEntity": {
            "pool": "allies", "where": "is_adjacent($it, $event.target)"},
        "AllTeammate.RemoveUnselectable": {
            "pool": "enemies", "where": "$it.enemy_targetable and $it.ally_targetable"},
        "AllDarkTeam + AllLightTeam": {"pool": "all"},
        "AllTeammateWithUnselectable": {"pool": "enemies", "include_unselectable": True},
        "LeftToRightDarkTeamTarget": {"pool": "enemies", "order_by": "formation"},
        "RightToLeftDarkTeamTarget": {"pool": "enemies", "order_by": "-formation"},
    }
    for alias, target in expected.items():
        out = _task_skill({
            "$type": "RPG.GameCore.ForceKill",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        })
        assert out["ok"] and not out["unsupported"], (alias, out["unsupported"])
        assert out["hooks"][0]["effects"][0]["target"] == target

    nested = _task_skill({
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy.RemoveServant"},
        "TaskList": [{
            "$type": "RPG.GameCore.ForceKill",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        }],
    })
    assert nested["ok"] and not nested["unsupported"]
    assert nested["hooks"][0]["effects"][0]["target"] == expected["AllEnemy.RemoveServant"]

    for alias, direction in (("AbilityTargetLeftEntity", -1), ("AbilityTargetRightEntity", 1)):
        positioned = _task_skill({
            "$type": "RPG.GameCore.Retarget",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
            "TaskList": [{
                "$type": "RPG.GameCore.ForceKill",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            }],
        })
        assert positioned["ok"] and not positioned["unsupported"]
        assert positioned["hooks"][0]["effects"][0]["target"] == {
            "pool": "allies", "where": f"position_delta($it, $event.target) == {direction}"}

    summon = make_actor("summon")
    summon.actor_type = "summon"
    summon.summoner_id = "ally"
    ally = make_actor("ally", hp=7000)
    eng = engine_vs_dummy(allies=[ally, summon],
                          enemies=[make_dummy("source"), make_dummy("partner")])
    source = eng.state.actors["source"]
    source.actor.groups = ["W1_SvarogPart"]
    eng.state.actors["partner"].actor.groups = ["W1_SvarogPart", "RL"]
    eng.state.actors["partner"].actor.summon_flags["enemy_targetable"] = False
    picked = {
        alias: [state.actor.actor_id for state in eng._hooks._hook_target_states(
            expected[alias], eng.state.actors["ally"]
            if alias == "AllLightTeam - ModifierOwnerEntity" else source,
            {"target": "summon"} if alias == "AbilityTargetEntity.GetSummoner"
            else {"target": "ally"} if alias == "ProjectileHitEntityAdjoinEntity" else {})]
        for alias in expected
    }
    assert picked["TauntOrAggroEnemy"] == ["hero"]
    assert picked["AllEnemy.RemoveServant"] == ["hero", "ally"]
    assert picked["AllLightAvatar"] == ["hero", "ally"]
    assert picked["AllLightTeam - ModifierOwnerEntity"] == ["hero", "summon"]
    assert picked["AllDarkTeam - ModifierOwnerEntity"] == ["partner"]
    assert picked["AllDarkTeamUnselectable"] == ["partner"]
    assert picked["AllEnemy.GetServant"] == ["summon"]
    assert picked["ServantEntityList"] == ["summon"]
    assert picked["AllLightTeamOnlyAddSPOnceForServant"] == ["hero", "ally"]
    assert picked["AllLightTeam.SortByHP.Reverse"] == ["ally", "hero", "summon"]
    assert picked["Monster_Svarog_00_Unselectable"] == ["source", "partner"]
    assert picked["Monster_Svarog_00_RL_Unselectable"] == ["partner"]
    assert picked["ModifierOwnerEntityAllTeammate"] == ["partner"]
    assert picked["ModifierOwnerEntityAdjoinEntity"] == ["partner"]
    assert picked["ProjectileHitEntityAdjoinEntity"] == ["hero", "summon"]
    assert picked["AllTeammate.RemoveUnselectable"] == ["source"]
    assert picked["LeftToRightDarkTeamTarget"] == ["source", "partner"]
    assert picked["RightToLeftDarkTeamTarget"] == ["partner", "source"]
    assert picked["AllTeammateWithUnselectable"] == ["source", "partner"]
    assert picked["AllDarkTeam + AllLightTeam"] == [
        "hero", "ally", "summon", "source", "partner"]
    summoner = eng._hooks._hook_target_states(
        expected["AbilityTargetEntity.GetSummoner"], source, {"target": "summon"})
    assert [state.actor.actor_id for state in summoner] == ["ally"]
    for alias, expected_ids in (("AbilityTargetLeftEntity", ["hero"]),
                                ("AbilityTargetRightEntity", ["summon"])):
        direction = -1 if alias == "AbilityTargetLeftEntity" else 1
        target = {"pool": "allies",
                  "where": f"position_delta($it, $event.target) == {direction}"}
        positioned = eng._hooks._hook_target_states(target, source, {"target": "ally"})
        assert [state.actor.actor_id for state in positioned] == expected_ids


def test_global_target_alias_expands_for_plain_hook_targets():
    from tests._builders import engine_vs_dummy, make_dummy

    alias = "MMonster_W4_Manta_00_LocalLegend"
    skills, sources = _predicate_skill({})
    sources["target_aliases"] = {alias: {
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 405301}},
            }},
        ],
    }}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ForceKill",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    target = out["hooks"][0]["effects"][0]["target"]
    assert target == {"pool": "enemies", "where": "monster_unique_id($it) == 405301"}

    eng = engine_vs_dummy(enemies=[make_dummy("4053010"), make_dummy("4053020")])
    picked = eng._hooks._hook_target_states(target, eng.state.actors["hero"], {})
    assert [state.actor.actor_id for state in picked] == ["4053010"]

    sources["target_aliases"] = {
        "Loop": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Loop"}}
    sources["abilities"]["A"]["OnStart"][0]["TargetType"]["Alias"] = "Loop"
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("循环引用" in issue["reason"] for issue in rejected["unsupported"])


def test_plus_target_aliases_compile_as_concat_in_both_channels():
    from tests._builders import engine_vs_dummy, make_dummy

    def unique_alias(unique_id):
        return {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": unique_id}},
            }},
        ]}

    black = "MMonster_Black"
    white = "MMonster_White"
    joined = f"{black} + {white}"
    skills, sources = _predicate_skill({})
    sources["target_aliases"] = {black: unique_alias(405301), white: unique_alias(405302)}
    expected = {"concat": [
        {"pool": "enemies", "where": "monster_unique_id($it) == 405301"},
        {"pool": "enemies", "where": "monster_unique_id($it) == 405302"},
    ]}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ForceKill",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": joined},
    }]
    direct = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert direct["ok"] and not direct["unsupported"]
    assert direct["hooks"][0]["effects"][0]["target"] == expected

    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": joined},
        "TaskList": [{
            "$type": "RPG.GameCore.ForceKill",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        }],
    }]
    nested = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert nested["ok"] and not nested["unsupported"]
    assert nested["hooks"][0]["effects"][0]["target"] == expected

    eng = engine_vs_dummy(enemies=[
        make_dummy("4053010"), make_dummy("4053020"), make_dummy("4053030")])
    picked = eng._hooks._hook_target_states(expected, eng.state.actors["hero"], {})
    assert [state.actor.actor_id for state in picked] == ["4053010", "4053020"]


def test_attack_target_list_uses_action_end_hit_targets():
    from tests._builders import basic_action, engine_vs_dummy, make_actor, make_dummy
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_action_end")
    compiler._compile_force_kill({
        "$type": "RPG.GameCore.ForceKill",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AttackTargetList"},
    }, ctx, "attack_targets", ())
    assert not ctx.unsupported
    assert ctx.effects[0]["target"] == "$event.hit_targets"

    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    emitted = []
    eng.bus.subscribe("on_action_end", lambda et, payload, ctx: emitted.append(payload))
    action = basic_action("aoe", target_type="aoe", scaling=0.01)
    action.instances = 2
    eng._execute_action(eng.state.actors["source"], action)
    assert emitted[-1]["hit_targets"] == ["hero", "ally"]
    picked = eng._hooks._hook_target_states(
        "$event.hit_targets", eng.state.actors["source"], emitted[-1])
    assert [state.actor.actor_id for state in picked] == ["hero", "ally"]


def test_skill_target_list_uses_action_targets_and_direct_action_targeting():
    from tests._builders import basic_action, engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {"TargetType": "EnemySelect"}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "SkillTargetEntityList"},
        "AttackProperty": {
            "DamageType": "Physical",
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        },
    }]
    direct = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert direct["ok"] and not direct["unsupported"]
    assert direct["action"]["target_type"] == "single"
    assert direct["action"]["scaling"] == [{"atk": 0.5}]

    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "SkillTargetEntityList"},
        "TaskList": [{
            "$type": "RPG.GameCore.ForceKill",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        }],
    }]
    nested = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert nested["ok"] and not nested["unsupported"]
    assert nested["hooks"][0]["effects"][0]["target"] == {"pool": "$event.targets"}

    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    emitted = []
    eng.bus.subscribe("on_action", lambda et, payload, ctx: emitted.append(payload))
    action = basic_action("aoe", target_type="aoe", scaling=0.01)
    eng._execute_action(eng.state.actors["source"], action, _action_broadcast={
        "actor": "source", "action_type": "basic", "action_id": "aoe",
        "target_type": "aoe", "actor_type": "monster", "insert": False,
    })
    assert emitted[-1]["targets"] == ["hero", "ally"]
    picked = eng._hooks._hook_target_states(
        "$event.targets", eng.state.actors["source"], emitted[-1])
    assert [state.actor.actor_id for state in picked] == ["hero", "ally"]


def test_destroy_battle_character_uses_death_chain_and_unique_target():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.DestroyBattleCharacter",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "set_hp_to_percent", "target": "self", "percent": 0.0}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert not source.alive

    unique = _task_skill({
        "$type": "RPG.GameCore.DestroyBattleCharacter", "CharacterUniqueName": "RageEnd",
    })
    assert unique["ok"] and not unique["unsupported"]
    assert unique["hooks"][0]["effects"][0]["target"] == {"pool": "unique:RageEnd"}


def test_monster_view_phase_form_sets_current_phase():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.SetMonsterViewPhase",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "PhaseType": "Form", "PhaseNum": 2,
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "set_dynamic_value", "target": "self",
                      "dynamic_key": "current_phase", "amount": 2}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["current_phase"] == 2

    rejected = _task_skill({"$type": "RPG.GameCore.SetMonsterViewPhase", "PhaseType": "Other"})
    assert not rejected["ok"]


def test_set_monster_phase_without_mode_sets_explicit_or_initial_phase():
    from tests._builders import engine_vs_dummy, make_dummy

    initial = _task_skill({"$type": "RPG.GameCore.SetMonsterPhase"})
    assert initial["ok"] and not initial["unsupported"]
    effect = initial["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "set_dynamic_value", "target": "self",
                      "dynamic_key": "current_phase", "amount": 1}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, {
        **effect, "amount": 3}, {})
    assert eng._enemy_policy_state["source"]["current_phase"] == 3
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["current_phase"] == 1

    explicit = _task_skill({"$type": "RPG.GameCore.SetMonsterPhase", "PhaseNum": 2})
    assert explicit["ok"] and not explicit["unsupported"]
    assert explicit["hooks"][0]["effects"][0]["amount"] == 2
    last_summons = _task_skill({
        "$type": "RPG.GameCore.SetMonsterPhase", "PhaseNum": 2,
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LastSummonMonsters"},
    })
    assert last_summons["ok"] and not last_summons["unsupported"]
    assert last_summons["hooks"][0]["effects"][0]["target"] == {"pool": "last_summons"}


def test_set_monster_phase_inc_updates_each_selected_target_once():
    from tests._builders import engine_vs_dummy, make_dummy
    from hsr_nous.adapters.enemy_ability import _Context

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = _Context(mode="event", skill=skills[0], event="on_hp_decrease")
    compiler._compile_monster_phase({
        "$type": "RPG.GameCore.SetMonsterPhase", "SetMode": "Inc",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    }, ctx, "phase", ())
    assert not ctx.unsupported
    event_effect = ctx.effects[0]
    assert event_effect == {
        "effect_type": "set_dynamic_value", "target": "$event.target",
        "dynamic_key": "current_phase", "amount": "dynamic_of($target, 'current_phase') + 1"}

    sources["target_aliases"] = {"Group": {
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"}],
    }}
    compiler.target_aliases = sources["target_aliases"]
    group_ctx = _Context(mode="event", skill=skills[0], event="on_hp_decrease")
    compiler._compile_monster_phase({
        "$type": "RPG.GameCore.SetMonsterPhase", "SetMode": "Inc",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Group"},
    }, group_ctx, "group", ())
    assert not group_ctx.unsupported
    group_effect = group_ctx.effects[0]
    assert group_effect["target"] == {"pool": "enemies"}
    assert "amount_target" not in group_effect

    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("partner")])
    for actor_id in ("source", "partner"):
        eng._enemy_policy_state.setdefault(actor_id, {
            "seq_idx": 0, "cooldown_left": {}, "current_phase": 1, "dynamic_values": {}})
    eng._enemy_policy_state["partner"]["current_phase"] = 3
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, event_effect, {"target": "partner"})
    assert eng._enemy_policy_state["source"]["current_phase"] == 1
    assert eng._enemy_policy_state["partner"]["current_phase"] == 4
    eng._hooks._run_hook_effect(source, group_effect, {})
    assert eng._enemy_policy_state["source"]["current_phase"] == 2
    assert eng._enemy_policy_state["partner"]["current_phase"] == 5


def test_set_action_delay_normalized_value_sets_remaining_distance():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.SetActionDelay",
        "NormalizedValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "set_action_delay", "target": "self", "amount": 50.0}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    handle = eng.scheduler.handle_of("source")
    assert eng.scheduler._remaining[handle] == 5000.0
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng.scheduler._remaining[handle] == 5000.0

    legacy = _task_skill({
        "$type": "RPG.GameCore.SetActionDelay",
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    })
    assert legacy["ok"]
    assert legacy["hooks"][0]["effects"][0]["amount"] == 100


def test_set_action_delay_preserves_target_sequence():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["custom_value_tags"] = ["Elite"]
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCheckCustomValueBool",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "Key": {"Value": "Elite"},
            }},
        ]},
        "NormalizedValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == {"pool": "enemies", "where": "in_group($it, 'Elite')"}
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("partner")])
    eng.state.actors["source"].actor.groups.append("Elite")
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert eng.scheduler._remaining[eng.scheduler.handle_of("source")] == 5000.0
    assert eng.scheduler._remaining[eng.scheduler.handle_of("partner")] == 10000.0


def test_set_action_delay_target_compute_minus_excludes_event_target():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({})
    compiler = AbilityCompiler("fake", skills, sources)
    task = {
        "$type": "RPG.GameCore.SetActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetCompute", "ComputeType": "Minus",
                       "Targets": [
                           {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
                           {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                       ]},
        "NormalizedValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
    }
    ctx = _Context(mode="event", skill=skills[0], event="after_remove_modifier")
    compiler._compile_action_delay(task, ctx, "test", ())
    assert not ctx.unsupported
    effect = ctx.effects[0]
    assert "not target_in_selected(" in effect["target"]["where"]
    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {"target": "hero"})
    assert eng.scheduler._remaining[eng.scheduler.handle_of("ally")] == 5000.0
    assert eng.scheduler._remaining[eng.scheduler.handle_of("hero")] == 10000.0

    rejected_ctx = _Context(mode="event", skill=skills[0], event="after_remove_modifier")
    compiler._compile_action_delay({**task, "TargetType": {
        "$type": "RPG.GameCore.TargetCompute", "ComputeType": "Add", "Targets": []}},
        rejected_ctx, "test", ())
    assert any("TargetCompute(Minus)" in issue["reason"] for issue in rejected_ctx.unsupported)


def test_active_before_skill_use_listener_uses_before_action():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Listener"},
    }]
    sources["modifiers"] = {"Listener": {"_CallbackList": [{
        "Event": "OnBeforeSkillUse", "CallbackConfig": [{
            "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Seen"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    hook = next(hook for hook in out["hooks"] if hook["event"] == "before_action")
    assert "$event.actor == $self.actor_id" in hook["condition"]
    assert "$event.action_type == 'skill'" in hook["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event="before_action",
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    eng.bus.emit("before_action", {"actor": "source", "action_type": "skill"}, eng.state)
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Seen"] == 1.0
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "Seen", "amount": 0}, {})
    eng.bus.emit("before_action", {"actor": "source", "action_type": "basic"}, eng.state)
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Seen"] == 0.0


def test_active_modifier_remove_listener_retargets_and_checks_death_source():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "AimTarget"},
    }, modifiers={"AimTarget": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "AimTarget"},
        }],
    }, {
        "Event": "OnListenModifierRemove", "CallbackConfig": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {"$type": "RPG.GameCore.ByAnd", "PredicateList": [
                {"$type": "RPG.GameCore.ByCheckModifierCallBackName", "ModifierName": "AimTarget"},
                {"$type": "RPG.GameCore.ByCheckModifierDeathSource",
                 "DeathSource": "CasterDead", "Inverse": True},
            ]},
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.Retarget", "ByRandom": True, "MaxNumber": 1,
                "TargetType": {"$type": "RPG.GameCore.TargetCompute", "ComputeType": "Minus",
                               "Targets": [
                                   {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
                                   {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                               ]},
                "TaskList": [{
                    "$type": "RPG.GameCore.AddModifier",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                    "ModifierName": {"Value": "AimTarget"},
                }],
            }],
        }],
    }]}})
    assert out["ok"] and not out["unsupported"]
    listener = next(hook for hook in out["hooks"] if hook["event"] == "after_remove_modifier")
    assert "source_death" in listener["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    apply_effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                        if effect["effect_type"] == "apply_modifier")
    eng._hooks._run_hook_effect(source, apply_effect, {})
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event="after_remove_modifier",
        condition_expr=eng._expr.compile(listener["condition"], layer="effect"),
        effects=listener["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    eng._remove_modifier(source, "AimTarget", "test")
    assert "AimTarget" in eng.state.actors["hero"].modifiers


def test_remodifier_caster_filter_uses_modifier_source():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.Remodifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
        "CasterFilter": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": "Mark", "MaxNumber": 1,
        "TaskList": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "Mark"},
        }],
    }, modifiers={"Mark": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
        }]}
    ]}})
    assert out["ok"] and not out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "apply_modifier")
    assert "$self.actor_id" in effect["target"]["where"]
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("other"), make_dummy("third")])
    source, other, third = (eng.state.actors[key] for key in ("source", "other", "third"))
    eng._apply_modifier_spec(other, {"modifier_id": "Mark", "modifier_type": "buff"}, source)
    eng._apply_modifier_spec(third, {"modifier_id": "Mark", "modifier_type": "buff"}, other)
    selected = eng._hooks._hook_target_states(effect["target"], source, {})
    assert [state.actor.actor_id for state in selected] == ["other"]


def test_modifier_default_caster_and_event_param_entity():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({"$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Mark"}},
                      modifiers={"Mark": {"BehaviorFlagList": ["ImmuneDebuff"]}})
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["target"] == "self"

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier", "ModifierName": {"Value": "Listener"},
    }]
    sources["modifiers"] = {
        "Listener": {"_CallbackList": [{
            "Event": "OnListenCharacterCreate", "CallbackConfig": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "ModifierName": {"Value": "Mark"},
            }],
        }]},
        "Mark": {"BehaviorFlagList": ["ImmuneDebuff"]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"]
    hook = next(item for item in out["hooks"]
                if item["event"] == "actor_enter"
                and any(effect.get("target") == "$event.actor" for effect in item["effects"]))
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("newcomer")])
    targets = eng._hooks._hook_target_states(
        "$event.actor", eng.state.actors["source"], {"actor": "newcomer"})
    assert [target.actor.actor_id for target in targets] == ["newcomer"]
    assert hook["effects"][0]["target"] == "$event.actor"


def test_global_target_alias_expands_monster_phase_predicate():
    from tests._builders import engine_vs_dummy, make_dummy

    predicate = {
        "$type": "RPG.GameCore.ByCompareMonsterPhase",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Core"},
        "CompareType": "Equal", "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    }
    skills, sources = _predicate_skill(predicate)
    sources["target_aliases"] = {"Core": {
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "BattleAllEntity"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 403501}},
            }},
        ],
    }}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "count_selected(\"all_with_battle_events\"" in condition
    assert "dynamic_of($it, 'current_phase') == 2" in condition

    eng = engine_vs_dummy(enemies=[make_dummy("4035010")])
    source = eng.state.actors["4035010"]
    eng._hooks._run_hook_effect(source, {
        "effect_type": "set_dynamic_value", "target": "self",
        "dynamic_key": "current_phase", "amount": 2}, {})
    assert eng._expr.evaluate(eng._expr.compile(condition, layer="effect"),
                              eng._hooks._hook_ctx(source, {"actor": "4035010", "action_id": "s1"}),
                              functions=eng._hooks._hook_functions(source))


def test_stage_id_predicate_uses_runtime_encounter_id():
    from tests._builders import engine_vs_dummy, make_dummy

    predicate = {"$type": "RPG.GameCore.ByCompareStageID", "CompareType": "GreaterEqual",
                 "StageID": {"IsDynamic": False, "FixedValue": {"Value": 4260100}}}
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "stage_id() >= 4260100" in condition
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng.encounter.encounter_id = 4260120
    payload = {"actor": "source", "action_id": "s1"}
    assert eng._expr.evaluate(eng._expr.compile(condition, layer="effect"),
                              eng._hooks._hook_ctx(source, payload),
                              functions=eng._hooks._hook_functions(source))
    eng.encounter.encounter_id = 426011
    assert not eng._expr.evaluate(eng._expr.compile(condition, layer="effect"),
                                  eng._hooks._hook_ctx(source, payload),
                                  functions=eng._hooks._hook_functions(source))


@pytest.mark.parametrize(("mask", "expected"), [
    ("Avatar", "actor_type_of($self.actor_id) == 'character'"),
    ("Servant", "actor_type_of($self.actor_id) == 'summon' or summoner_of($self.actor_id) != ''"),
    ("Monster", "actor_type_of($self.actor_id) == 'monster' or actor_type_of($self.actor_id) == 'enemy'"),
    ("BattleEvent", "actor_type_of($self.actor_id) == 'battle_event'"),
])
def test_target_entity_type_masks(mask, expected):
    predicate = {"$type": "RPG.GameCore.ByTargetEntityType",
                 "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                 "EntityTypeMask": mask}
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert expected in out["hooks"][0]["condition"]


def test_target_entity_alive_only_and_battle_event_pool():
    from tests._builders import engine_vs_dummy, make_dummy

    predicate = {"$type": "RPG.GameCore.ByTargetEntityType",
                 "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                 "EntityTypeMask": "Avatar", "AliveStateMask": "Mask_AliveOnly"}
    skills, sources = _predicate_skill(predicate)
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "actor_alive($self.actor_id)" in out["hooks"][0]["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, {
        "effect_type": "create_battle_event", "event_id": 20034, "team": "TeamNeutral"}, {})
    events = eng._hooks._hook_target_states({"pool": "battle_events"}, source, {})
    assert len(events) == 1 and events[0].actor.actor_type == "battle_event"


def test_hp_ratio_summoner_projectile_and_skill_target():
    from dataclasses import replace
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    for alias, expected in [
        ("ModifierOwnerSummoner", "hp_of(summoner_of($self.actor_id))"),
        ("ProjectileHitEntity", "hp_of($event.target)"),
        ("TurnActionEntitySkillTarget", "hp_of($event.target)"),
    ]:
        predicate = {"$type": "RPG.GameCore.ByCompareHPRatio",
                     "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
                     "CompareType": "LessEqual",
                     "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0.6}}}
        skills, sources = _predicate_skill(predicate)
        out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
        assert out["ok"] and not out["unsupported"]
        assert expected in out["hooks"][0]["condition"]
        assert "max_hp_of(" in out["hooks"][0]["condition"]

    predicate = {"$type": "RPG.GameCore.ByCompareHPRatio",
                 "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerSummoner"},
                 "CompareType": "LessEqual",
                 "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0.6}}}
    skills, sources = _predicate_skill(predicate)
    condition = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")["hooks"][0]["condition"]
    eng = engine_vs_dummy(allies=[make_actor("owner")],
                          enemies=[replace(make_dummy("source"), summoner_id="owner")])
    source, owner = eng.state.actors["source"], eng.state.actors["owner"]
    owner.current_hp = 2500.0
    assert eng._expr.evaluate(eng._expr.compile(condition, layer="effect"),
                              eng._hooks._hook_ctx(source, {"actor": "source", "action_id": "s1"}),
                              functions=eng._hooks._hook_functions(source))


def test_hp_ratio_compare_value_accepts_skill_param_dynamic_hash():
    predicate = {
        "$type": "RPG.GameCore.ByCompareHPRatio",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "CompareType": "LessEqual",
        "CompareValue": _dynamic("AQAR", hashes=[123]),
    }
    skills, sources = _predicate_skill(predicate)
    sources["character_config"]["DynamicValues"] = {"Floats": {
        "123": {"ReadInfo": {"Type": "SkillParam", "TriggerKey": "Skill01", "Index": 0}},
    }}
    skills[0]["param_list"] = [0.6]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "(hp_of($self.actor_id) / max_hp_of($self.actor_id)) <= 0.6" in \
        out["hooks"][0]["condition"]


def test_global_template_dynamic_keys_resolve_runtime_reads():
    predicate = {
        "$type": "RPG.GameCore.ByCompareHPRatio",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "CompareType": "LessEqual",
        "CompareValue": _dynamic("AQABAQIR", hashes=[-1031795115, 907832512]),
    }
    skills, sources = _predicate_skill(predicate)
    sources["global_templates"] = {"Shared": {"TaskList": [{
        "$type": "RPG.GameCore.SetDynamicValue",
        "DynamicKey": {"Value": "MDF_NextLockHpRatio"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]}}
    sources["character_config"]["DynamicValues"] = {"Floats": {
        "907832512": {"ReadInfo": {
            "Type": "SkillParam", "TriggerKey": "Skill01", "Index": 0}},
    }}
    skills[0]["param_list"] = [0.2]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "dynamic_of($self.actor_id, 'MDF_NextLockHpRatio') + 0.2" in condition


@pytest.mark.parametrize(("enemy_id", "target_id", "success_unknown"), [
    ("4014030", 4014032, True),
])
def test_static_boolean_short_circuit_skips_unreachable_dynamic_branch(
        enemy_id, target_id, success_unknown):
    combine = "RPG.GameCore.ByAnd" if success_unknown else "RPG.GameCore.ByAny"
    unknown_hp = {
        "$type": "RPG.GameCore.SetHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifyRatio": _dynamic("AQAR", hashes=[999]),
    }
    known_hp = {
        "$type": "RPG.GameCore.SetHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifyRatio": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
    }
    task = {
        "$type": "RPG.GameCore.PredicateTaskList",
        "Predicate": {
            "$type": combine,
            "PredicateList": [{
                "$type": "RPG.GameCore.ByCompareMonsterID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "TargetMonsterID": {"IsDynamic": False, "FixedValue": {"Value": target_id}},
            }, {
                "$type": "RPG.GameCore.ByCompareDynamicValue",
                "DynamicKey": {"Value": "_WorldLevel"},
                "CompareType": "Less",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 6}},
            }],
        },
        "SuccessTaskList": [unknown_hp if success_unknown else known_hp],
        "FailedTaskList": [known_hp if success_unknown else unknown_hp],
    }
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [task]
    out = AbilityCompiler(enemy_id, skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["hooks"][0]["effects"][0]["percent"] == 0.5


def test_nested_boolean_phase_write_after_read_uses_live_branch():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetMonsterPhase", "PhaseNum": 2,
    }, {
        "$type": "RPG.GameCore.PredicateTaskList",
        "Predicate": {
            "$type": "RPG.GameCore.ByAnd",
            "PredicateList": [{
                "$type": "RPG.GameCore.ByNot",
                "Predicate": {
                    "$type": "RPG.GameCore.ByCompareMonsterPhase",
                    "CompareType": "Equal",
                    "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                },
            }, {
                "$type": "RPG.GameCore.ByCompareMonsterPhase",
                "CompareType": "Equal",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
            }],
        },
        "SuccessTaskList": [{
            "$type": "RPG.GameCore.SetHP",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifyRatio": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        }],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]


def test_onstack_phase_write_after_read_uses_live_branch():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetMonsterPhase", "PhaseNum": 2,
    }, {
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Buff"},
    }]
    sources["modifiers"] = {"Buff": {"_CallbackList": [{
        "Event": "OnStack",
        "CallbackConfig": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterPhase",
                "CompareType": "Equal",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.StackProperty",
                "TargetType": {
                    "$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
                "Property": "AttackAddedRatio",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.2}},
            }],
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]


def test_compare_target_turn_owner_and_alias_membership():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    for alias, other, expected in [
        ("CurrentTurnOwnerEntity", "Caster", "turn_owner_of() == $self.actor_id"),
        ("Caster", "CurrentTurnOwnerEntity", "$self.actor_id == turn_owner_of()"),
        ("ModifierOwnerEntity", "ModifierOwnerEntity", "$self.actor_id == $self.actor_id"),
    ]:
        predicate = {"$type": "RPG.GameCore.ByCompareTarget",
                     "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
                     "CompareType": {"$type": "RPG.GameCore.TargetAlias", "Alias": other}}
        skills, sources = _predicate_skill(predicate)
        out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
        assert out["ok"] and not out["unsupported"]
        assert expected in out["hooks"][0]["condition"]

    predicate = {"$type": "RPG.GameCore.ByCompareTarget",
                 "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                 "CompareType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}}
    compiler = AbilityCompiler("fake", [], {})
    expr = compiler._predicate_expr(predicate, _Context(
        mode="event", skill={}, event="after_apply_modifier"), "test")
    assert expr == "$event.target == $self.actor_id"

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareTarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "CompareType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Core"},
    })
    sources["target_aliases"] = {"Core": {
        "$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "BattleAllEntity"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 403501}},
            }},
        ],
    }}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "target_in_selected(" in condition and "$self.actor_id))" in condition

    effect = _task_skill({
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CurrentTurnOwnerEntity"},
        "ModifierName": {"Value": "Mark"},
    })["hooks"][0]["effects"][0]
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    eng._current_turn_actor_id = "source"
    selected = eng._hooks._hook_target_states(effect["target"], eng.state.actors["source"], {})
    assert [target.actor.actor_id for target in selected] == ["source"]


def test_compare_target_collection_event_unique_and_select():
    from dataclasses import replace
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    def compiled(predicate, event):
        compiler = AbilityCompiler("fake", [], {})
        ctx = _Context(mode="event", skill={}, event=event)
        expression = compiler._predicate_expr(predicate, ctx, "test")
        assert expression is not None and not ctx.unsupported
        return expression

    minion = replace(make_dummy("minion"), summoner_id="source")
    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("other"), make_dummy("third"), minion])
    source = eng.state.actors["source"]

    def evaluate(expression, owner=source, payload=None):
        payload = payload or {}
        return eng._hooks._hook_amount(expression, owner, payload)

    summons = compiled({
        "$type": "RPG.GameCore.ByCompareTarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": "ModifierOwnerSummonedMinions"},
        "CompareType": {"$type": "RPG.GameCore.TargetAlias",
                        "Alias": "CurrentTurnOwnerEntity"},
    }, "on_turn_end")
    eng._current_turn_actor_id = "minion"
    assert evaluate(summons) == 1.0
    eng._current_turn_actor_id = "other"
    assert evaluate(summons) == 0.0

    listener = compiled({
        "$type": "RPG.GameCore.ByCompareTarget", "Inverse": True,
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "CompareType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    }, "on_action")
    assert evaluate(listener, payload={"actor": "hero"}) == 1.0
    assert evaluate(listener, payload={"actor": "source"}) == 0.0

    unique = compiled({
        "$type": "RPG.GameCore.ByCompareTarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "CompareType": {"$type": "RPG.GameCore.TargetFetchUniqueNameEntity",
                        "UniqueName": "W5_Vtuber_00_Virtual"},
    }, "on_action")
    eng._enemy_policy_state.setdefault("$level", {}).setdefault(
        "dynamic_targets", {})["W5_Vtuber_00_Virtual"] = "source"
    assert evaluate(unique, payload={"actor": "source"}) == 1.0
    assert evaluate(unique, payload={"actor": "hero"}) == 0.0

    select_third = compiled({
        "$type": "RPG.GameCore.ByCompareTarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "CompareType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam.Select3"},
    }, "on_turn_end")
    assert evaluate(select_third, eng.state.actors["third"]) == 1.0
    assert evaluate(select_third, source) == 0.0


def test_inclusive_team_targets_reach_unselectable_modifiers():
    from dataclasses import replace
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": "AllLightTeamWithAllLightTeamUnselectable"},
        "ModifierName": {"Value": "Mark"},
    })
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == {"pool": "allies", "include_unselectable": True}
    friend = replace(make_actor("friend"), summon_flags={"ally_targetable": False})
    eng = engine_vs_dummy(allies=[friend], enemies=[make_dummy("source")])
    source, hero = eng.state.actors["source"], eng.state.actors["hero"]
    for target in (hero, eng.state.actors["friend"]):
        eng._apply_modifier_spec(target, {
            "modifier_id": "Mark", "modifier_type": "debuff"}, source)
    assert eng._hooks._hook_target_states({"pool": "allies"}, hero, {}) == [hero]
    inclusive = eng._hooks._hook_target_states(effect["target"], hero, {})
    assert [target.actor.actor_id for target in inclusive] == ["hero", "friend"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert all("Mark" not in target.modifiers for target in inclusive)

    remove_servant = _task_skill({
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                       "Alias": "AllLightTeamWithAllLightTeamUnselectable.RemoveServant"},
        "ModifierName": {"Value": "Mark"},
    })
    assert remove_servant["ok"] and not remove_servant["unsupported"]
    assert remove_servant["hooks"][0]["effects"][0]["target"]["where"] == "not $it.summoner_id"

    with_servant = _task_skill({
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity.WithServant"},
        "ModifierName": {"Value": "Mark"},
    })
    assert with_servant["ok"] and not with_servant["unsupported"]
    target_spec = with_servant["hooks"][0]["effects"][0]["target"]
    servant = replace(make_actor("servant"), actor_type="servant", summoner_id="hero")
    eng = engine_vs_dummy(allies=[servant], enemies=[make_dummy("source")])
    selected = eng._hooks._hook_target_states(
        target_spec, eng.state.actors["source"], {"target": "hero"})
    assert [target.actor.actor_id for target in selected] == ["hero", "servant"]


def test_monster_phase_changed_emits_only_outer_frame_commit():
    from hsr_nous.sim.frame import ExecutionFrame
    from tests._builders import engine_vs_dummy, make_dummy

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    emitted = []
    eng.bus.subscribe("monster_phase_changed", lambda et, p, c: emitted.append(p))
    parent = ExecutionFrame("parent", "source")
    child = ExecutionFrame("child", "source")
    eng._frame_stack.extend([parent, child])
    effect = {"effect_type": "set_dynamic_value", "target": "self",
              "dynamic_key": "current_phase", "amount": 2}
    eng._hooks._run_hook_effect(source, effect, {})
    assert emitted == []
    eng._frame_stack.pop()
    eng._commit_frame(child)
    assert emitted == []
    eng._frame_stack.pop()
    eng._commit_frame(parent)
    assert emitted == [{"actor": "source", "from_phase": 1, "to_phase": 2}]
    assert eng._enemy_policy_state["source"]["current_phase"] == 2
    assert "current_phase" not in eng._enemy_policy_state["source"]["dynamic_values"]

    same = ExecutionFrame("same", "source")
    eng._frame_stack.append(same)
    eng._hooks._run_hook_effect(source, effect, {})
    eng._frame_stack.pop()
    eng._commit_frame(same)
    assert len(emitted) == 1

    rolled_back = ExecutionFrame("rolled_back", "source")
    eng._frame_stack.append(rolled_back)
    eng._hooks._run_hook_effect(source, {**effect, "amount": 3}, {})
    eng._frame_stack.pop()
    assert len(emitted) == 1
    assert eng._enemy_policy_state["source"]["current_phase"] == 2

    cancelled = ExecutionFrame("cancelled", "source")
    eng._frame_stack.append(cancelled)
    eng._hooks._run_hook_effect(source, {**effect, "amount": 3}, {})
    eng._hooks._run_hook_effect(source, effect, {})
    eng._frame_stack.pop()
    eng._commit_frame(cancelled)
    assert len(emitted) == 1
    assert eng._enemy_policy_state["source"]["current_phase"] == 2


def _lock_delay_task(*, locked=True, change_type=None, reason="Mask_TurnBasedAdvance"):
    task = {
        "$type": "RPG.GameCore.LockActionDelayChange",
        "LockTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "IsLock": locked,
        "WhitelistSourceEntity": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "WhitelistChangeReason": reason,
    }
    if change_type is not None:
        task["WhitelistChangeType"] = change_type
    return task


def test_lock_action_delay_preserves_source_whitelist_and_unlock():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill(_lock_delay_task())
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "lock_action_delay", "target": "self",
                      "lock_id": "fake:s1", "locked": True, "whitelist_source": "self"}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source, hero = eng.state.actors["source"], eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, effect, {})
    handle = eng.scheduler.handle_of("source")
    for actor, effect_type, expected in [
        (hero, "advance_action", 10000.0),
        (hero, "delay_action", 10000.0),
        (source, "advance_action", 7500.0),
        (source, "delay_action", 10000.0),
    ]:
        eng._hooks._run_hook_effect(actor, {
            "effect_type": effect_type,
            "target": "self" if actor is source else "all_enemies", "amount": 25}, {})
        assert eng.scheduler._remaining[handle] == expected

    eng._hooks._run_hook_effect(source, {**effect, "locked": False}, {})
    assert not source.action_delay_locks
    eng._hooks._run_hook_effect(hero, {
        "effect_type": "advance_action", "target": "all_enemies", "amount": 25}, {})
    assert eng.scheduler._remaining[handle] == 7500.0


def test_lock_target_action_delay_reuses_modifier_lock():
    from tests._builders import engine_vs_dummy, make_dummy
    task = {"$type": "RPG.GameCore.LockTargetActionDelay",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}}
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect == {"effect_type": "lock_action_delay", "target": "self",
                      "lock_id": "fake:s1", "locked": True}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source, hero = eng.state.actors["source"], eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, effect, {})
    eng._hooks._run_hook_effect(hero, {
        "effect_type": "advance_action", "target": "all_enemies", "amount": 25}, {})
    assert eng.scheduler._remaining[eng.scheduler.handle_of("source")] == 10000
    eng._hooks._run_hook_effect(source, {**effect, "locked": False}, {})
    assert not source.action_delay_locks

    real = _real_compiler("3014020").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.LockTargetActionDelay"
                   for item in real["unsupported"])


@_need_ability
def test_lock_target_action_delay_accepts_registered_target_pools():
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    task = {"$type": "RPG.GameCore.LockTargetActionDelay",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"}}
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["target"] == "all_allies"
    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], effect, {})
    assert eng.state.actors["hero"].action_delay_locks
    assert eng.state.actors["ally"].action_delay_locks

    rejected = _task_skill({**task, "WhitelistSourceEntity": {
        "$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"}})
    assert not rejected["ok"]
    for enemy_id in ("4015011", "4015020", "4015021"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.LockTargetActionDelay"
                       for issue in real["unsupported"])


def test_lock_action_delay_direction_and_numeric_reason_boundaries():
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill(_lock_delay_task(change_type="Bit_Decrease"))
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["whitelist_change_type"] == "decrease"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, effect, {})
    handle = eng.scheduler.handle_of("source")
    eng._hooks._run_hook_effect(source, {
        "effect_type": "advance_action", "target": "self", "amount": 25}, {})
    assert eng.scheduler._remaining[handle] == 7500.0
    eng._hooks._run_hook_effect(source, {
        "effect_type": "delay_action", "target": "self", "amount": 25}, {})
    assert eng.scheduler._remaining[handle] == 7500.0

    rejected = _task_skill(_lock_delay_task(reason=17))
    assert not rejected["ok"]
    assert any("17" in issue["reason"] for issue in rejected["unsupported"])


def test_presentation_bulk_ignored_task_nodes():
    """表现类长尾 IGNORED 零成本钉：客户端串/编队/预载/相机/HUD 照过。"""
    tasks = [
        {"$type": "RPG.GameCore.TriggerCustomString",
         "CustomString": {"Value": "Level_SpecialWin"}},
        {"$type": "RPG.GameCore.ModifyDefaultTeamFormation",
         "FormationWidthMin": {"IsDynamic": False, "FixedValue": {"Value": 12}},
         "TeamCenter": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
         "ExtraConfig": []},
        {"$type": "RPG.GameCore.RemoveEntityFromTeamFormation",
         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"}},
        {"$type": "RPG.GameCore.PreloadBattleEventByID",
         "EventID": {"IsDynamic": False, "FixedValue": {"Value": 1}}},
        {"$type": "RPG.GameCore.BlockCameraDitherUpdate", "BlockTime": 1},
        {"$type": "RPG.GameCore.SetEntityForbidCameraDither",
         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}},
        {"$type": "RPG.GameCore.SetMonsterHUDVisibleType",
         "ChildPanelVisibleType": "OnlySpecialMark",
         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}},
        {"$type": "RPG.GameCore.SetControlSkillMapping",
         "ControlSkillType": "ControlSkill11", "SkillTriggerKey": "Skill11_Painter_00",
         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}},
        {"$type": "RPG.GameCore.ShowBattleConditionUI"},
        {"$type": "RPG.GameCore.HeadLookAt",
         "PerformerType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
         "DoRootRotate": True},
        {"$type": "RPG.GameCore.SetCustomLocationConfig",
         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
         "LocationConfig": {"Width": 2.5}, "RefreshImmediately": False},
    ]
    out = _task_skill(tasks[0])
    for task in tasks[1:]:
        out2 = _task_skill(task)
        assert out2["ok"] and not out2["unsupported"]
    assert out["ok"] and not out["unsupported"]
    real = _real_compiler("2035012").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.SetEntityForbidCameraDither"
                   for item in real["unsupported"])


def test_onstack_screen_attachment_is_presentation_only():
    def screen(name):
        return {
            "$type": "LHOKPKHEBIK",
            "ECNKCCNJNPJ": {"RawString": name},
            "BLEOLOJJFDA": {"$type": "RPG.GameCore.TargetAlias",
                            "Alias": "Monster_W5_VtuberPart01_00"},
            "FCGFFNKCLNJ": "Screen",
            "HILNFHCPEAD": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "MPFLMHPNOOB": {"X": 0, "Y": -0.25, "Z": 1.5},
            "HAIBFNMDPKE": {"X": 0, "Y": -0.15, "Z": 0},
        }

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Screen01"},
    }, {
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Screen02"},
    }]
    sources["modifiers"] = {
        "Screen01": {"_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [screen("Screen01")],
        }]},
        "Screen02": {"_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.PredicateTaskList",
                "Predicate": {
                    "$type": "RPG.GameCore.ByCompareTarget",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                    "CompareType": {"$type": "RPG.GameCore.TargetFetchUniqueNameEntity",
                                    "UniqueName": "W5_Vtuber_00_Virtual"},
                },
                "SuccessTaskList": [screen("Screen02")],
                "FailedTaskList": [screen("Screen02")],
            }],
        }]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    for effect in (effect for hook in out["hooks"] for effect in hook["effects"]):
        assert effect.get("effect_type") == "apply_modifier"


def test_achievement_only_retarget_modifier_is_visual():
    out = _task_skill({
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "AchievementOnly"},
    }, modifiers={"AchievementOnly": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.Retarget",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
            "FailedTaskList": [{"$type": "RPG.GameCore.SetBattleAchievement", "AchievementID": 30164}],
        }],
    }]}})
    assert out["ok"] and not out["unsupported"] and not out["hooks"]
    compiler = AbilityCompiler("fake", [], {})
    assert not compiler._visual_modifier({"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.DamageByAttackProperty", "AttackProperty": {},
        }],
    }]})


# ---------------------------------------------------------------------------
# 谓词长尾族（14_policy.md 任务节点长尾节）：语境门控翻译 + 逐型拒因钉
# ---------------------------------------------------------------------------

def _pred_expr(predicate, *, event="on_action", extra_skills=()):
    """最小件：on_action 系 hook 的条件谓词编译（_predicate_expr 直测通道）。"""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A"}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []},
              *extra_skills]
    compiler = AbilityCompiler("fake", skills, sources)
    ctx = __import__("hsr_nous.adapters.enemy_ability", fromlist=["_Context"])._Context(
        mode="event", skill=skills[0], event=event)
    return compiler._predicate_expr(predicate, ctx, "P")


def test_in_elation_time_predicate_tracks_aha_turn():
    from tests._builders import basic_action, engine_vs_dummy, make_actor, make_dummy

    assert _pred_expr({"$type": "RPG.GameCore.ByIsInElationTime"}) == "in_elation_time()"
    hero = make_actor("hero")
    hero.path = "elation"
    hero.elation_number = 1
    eng = engine_vs_dummy(
        hero=hero, enemies=[make_dummy("source")],
        actions={"hero": [basic_action(action_type="elation_skill")]})
    seen = []
    eng.bus.subscribe("on_action", lambda et, payload, ctx: seen.append(
        eng._hooks._hook_functions(hero)["in_elation_time"]()))
    eng._run_aha_turn(extra_pool=20)
    assert seen == [1.0]
    assert eng._hooks._hook_functions(hero)["in_elation_time"]() == 0.0


def test_turn_owner_action_phase_end_tracks_turn_boundary():
    from tests._builders import engine_vs_dummy, make_dummy

    assert _pred_expr({
        "$type": "RPG.GameCore.ByTurnOwnerActionPhaseEnd", "Inverse": True}) == \
        "not turn_owner_action_phase_end()"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_functions(source)["turn_owner_action_phase_end"]() == 0.0
    seen = []
    eng.bus.subscribe("on_turn_end", lambda et, payload, ctx: seen.append(
        eng._hooks._hook_functions(source)["turn_owner_action_phase_end"]()))
    eng._run_turn(source, "normal")
    assert seen == [1.0]
    assert eng._hooks._hook_functions(source)["turn_owner_action_phase_end"]() == 1.0
    started = []
    eng.bus.subscribe("on_turn_start", lambda et, payload, ctx: started.append(
        eng._hooks._hook_functions(source)["turn_owner_action_phase_end"]()))
    eng._run_turn(source, "normal")
    assert started == [0.0]


def test_predicate_current_skill_name_and_type_action_context():
    """ByCurrentSkillName/Type 在带 action_type 的行动与伤害事件上翻译，其余语境显式拒。"""
    expr = _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillName",
                             "SkillName": "Skill01"})
    assert expr == "$event.action_id == 's1'"
    expr = _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType",
                             "SkillType": "Ultra"})
    assert expr == "$event.action_type == 'ultimate'"
    for event in ("on_action_end", "before_take_damage", "after_being_hit", "on_hp_decrease"):
        assert _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillName",
                           "SkillName": "Skill01"}, event=event) == "$event.action_id == 's1'"
        assert _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType",
                           "SkillType": "Ultra"}, event=event) == "$event.action_type == 'ultimate'"
    assert _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType",
                       "SkillType": "Servant"}, event="on_action_end") == (
        "actor_type_of($event.actor) == 'summon'")
    assert _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType"}) == (
        "$event.action_type == 'basic'")
    assert _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType", "SkillType": 0}) == (
        "$event.action_type == 'basic'")
    assert _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType", "SkillType": 3},
                      event="on_hp_decrease") == "actor_type_of($event.source) == 'summon'"
    servant_hit = _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType",
                              "SkillType": "Servant"}, event="on_hp_decrease")
    assert servant_hit == "actor_type_of($event.source) == 'summon'"
    from tests._builders import engine_vs_dummy, make_dummy
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert eng._hooks._hook_amount(servant_hit, source, {"source": "source"}) == 0.0
    source.actor.actor_type = "summon"
    assert eng._hooks._hook_amount(servant_hit, source, {"source": "source"}) == 1.0

    bad = _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillName",
                            "SkillName": "Skill01"}, event="on_battle_start")
    assert bad is None
    bad = _pred_expr({"$type": "RPG.GameCore.ByCurrentSkillType",
                            "SkillType": "Mystery"})
    assert bad is None


@_need_ability
def test_empty_task_config_is_placeholder_but_fields_still_reject():
    out = _task_skill({"$type": "RPG.GameCore.TaskConfig"})
    assert out["ok"] and not out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    rejected = _task_skill({"$type": "RPG.GameCore.TaskConfig", "Unknown": 1})
    assert not rejected["ok"]
    assert any(issue["node_type"] == "RPG.GameCore.TaskConfig"
               for issue in rejected["unsupported"])
    for enemy_id in ("1023020", "1023021"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.TaskConfig"
                       for issue in real["unsupported"])


@_need_ability
def test_character_config_inherits_parent_dynamic_values():
    from hsr_nous.pipeline.enemies.loader import get_enemy_character_config

    config = get_enemy_character_config("4033023") or {}
    floats = ((config.get("DynamicValues") or {}).get("Floats") or {})
    assert "-1089063255" in floats, "变体 Config 应继承父级 DynamicValues.Floats"


@_need_ability
def test_conditional_stack_weak_resistance_compiles():
    for enemy_id in ("3022011", "3025013"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.StackWeakResistance"
                       for issue in real["unsupported"]), (enemy_id, real["unsupported"])


@_need_ability
def test_show_target_hp_bar_is_presentation_only_but_fields_still_reject():
    task = {"$type": "RPG.GameCore.ShowTargetHPBar",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}}
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    rejected = _task_skill({**task, "Unknown": 1})
    assert not rejected["ok"]
    assert any(issue["node_type"] == "RPG.GameCore.ShowTargetHPBar"
               for issue in rejected["unsupported"])


@_need_ability
def test_empty_apply_operation_is_placeholder_but_fields_still_reject():
    out = _task_skill({"$type": "RPG.GameCore.ApplyOperation"})
    assert out["ok"] and not out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    rejected = _task_skill({"$type": "RPG.GameCore.ApplyOperation", "Unknown": 1})
    assert not rejected["ok"]
    assert any(issue["node_type"] == "RPG.GameCore.ApplyOperation"
               for issue in rejected["unsupported"])
    for enemy_id in ("1005010", "1005011"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.ApplyOperation"
                       for issue in real["unsupported"])


@_need_ability
def test_modifier_custom_event_connects_trigger_and_target_listener():
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["modifiers"]["Listener"] = {"_CallbackList": [{
        "Event": "OnCustomEvent", "CallbackConfig": [{
            "$type": "RPG.GameCore.DefineDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "DynamicKey": {"Value": "Seen"},
            "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }]}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Listener"},
    }, {
        "$type": "RPG.GameCore.TriggerModifierCustomEvent",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "EventType": {"EnumIndex": 4, "Value": 42},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    listener = next(hook for hook in out["hooks"] if hook["event"] == "modifier_custom_event")
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event="modifier_custom_event",
        condition_expr=eng._expr.compile(listener["condition"], layer="effect"),
        effects=listener["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    eng._enemy_policy_state.setdefault("source", {"current_phase": 1, "dynamic_values": {}})
    for hook in out["hooks"]:
        if hook["event"] == "on_action":
            for effect in hook["effects"]:
                eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Seen"] == 1

    rejected = _task_skill({
        "$type": "RPG.GameCore.TriggerModifierCustomEvent",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "EventType": {"Value": 42}, "IncludeLimbo": True,
    })
    assert not rejected["ok"]
    for enemy_id in ("2024021", "8022030", "8022031"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("未注册 modifier 自定义事件" in issue["reason"]
                       for issue in real["unsupported"])
    real = _real_compiler("2023031").compile_enemy()
    assert not any("非 DoT/怪物阶段自定义事件未注册" in issue["reason"]
                   for issue in real["unsupported"])


@_need_ability
def test_before_hit_failed_branch_uses_inverse_hit_condition():
    skills, sources = _predicate_skill({})
    branch = {
        "$type": "RPG.GameCore.PredicateTaskList",
        "Predicate": {
            "$type": "RPG.GameCore.ByCompareHPRatio",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "CompareType": "LessEqual",
            "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
        },
        "SuccessTaskList": [],
        "FailedTaskList": [{
            "$type": "RPG.GameCore.ModifyDamageData",
            "Attacker_AllDamageTypeAddedRatio": {
                "IsDynamic": False, "FixedValue": {"Value": 0.2}},
        }],
    }
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Scoped"},
    }]
    sources["modifiers"] = {"Scoped": {"_CallbackList": [{
        "Event": "OnBeforeHitAll", "CallbackConfig": [branch]}]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    spec = out["hooks"][0]["effects"][0]["modifier"]
    assert spec["hit_stat_exprs"]["all_dmg"] == 0.2
    assert spec["hit_condition"].startswith("not ")

    branch["SuccessTaskList"] = [dict(branch["FailedTaskList"][0])]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]

    for enemy_id in ("4033020", "4033024"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("仅支持 AttackData_ConstFinalDamage" in issue["reason"]
                       and "/OnStart/5/_CallbackList/4/" in issue["path"]
                       for issue in real["unsupported"])


def test_before_hit_mixed_callback_preserves_regular_and_scoped_branches():
    from hsr_nous.sim.state import Modifier
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    hp_gate = {
        "$type": "RPG.GameCore.ByCompareHPRatio",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "CompareType": "LessEqual",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
    }
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Scoped"},
    }]
    sources["modifiers"] = {
        "Marker": {},
        "Scoped": {"_CallbackList": [{
            "Event": "OnBeforeBeingHitAll",
            "CallbackConfig": [{
                "$type": "RPG.GameCore.PredicateTaskList", "Predicate": hp_gate,
                "SuccessTaskList": [{
                    "$type": "RPG.GameCore.AddModifier",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                                   "Alias": "ModifierOwnerEntity"},
                    "ModifierName": {"Value": "Marker"},
                }],
                "FailedTaskList": [],
            }, {
                "$type": "RPG.GameCore.PredicateTaskList",
                "Predicate": {
                    "$type": "RPG.GameCore.ByIsContainModifier",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                                   "Alias": "ModifierOwnerEntity"},
                    "ModifierName": {"Value": "Marker"},
                },
                "SuccessTaskList": [],
                "FailedTaskList": [{
                    "$type": "RPG.GameCore.ModifyDamageData",
                    "Defender_AllDamageReduce": {
                        "IsDynamic": False, "FixedValue": {"Value": 0.2}},
                }],
            }],
        }]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    scoped = out["hooks"][0]["effects"][0]["modifier"]
    assert scoped["hit_stat_exprs"]["dmg_dmg_reduction"] == 0.2
    assert "not " in scoped["hit_condition"] and "Marker" in scoped["hit_condition"]
    marker_effects = [(hook, effect) for hook in out["hooks"] for effect in hook.get("effects", [])
                      if effect.get("effect_type") == "apply_modifier"
                      and effect.get("modifier", {}).get("modifier_id") == "Marker"]
    assert len(marker_effects) == 1
    assert "0.5" in marker_effects[0][0]["condition"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    hero = eng.state.actors["hero"]
    source = eng.state.actors["source"]
    eng._apply_modifier_spec(source, scoped, source)
    hit = eng.pipeline.settle_damage("direct", hero, source, action=basic_action("hit"))
    assert hit.node["dmgRedMulti"] == pytest.approx(0.8)
    eng._apply_modifier(source, Modifier(
        modifier_id="Marker", name="Marker", modifier_type="buff"))
    blocked = eng.pipeline.settle_damage("direct", hero, source, action=basic_action("hit"))
    assert blocked.node["dmgRedMulti"] == pytest.approx(1.0)


@_need_ability
def test_before_hit_modifier_layer_assignment_is_inlined():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Scoped"},
    }]
    sources["modifiers"] = {"Scoped": {"_CallbackList": [{
        "Event": "OnBeforeHitAll", "CallbackConfig": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareHPRatio",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
                "CompareType": "LessEqual",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.SetDynamicValueByModifierValue",
                "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias",
                                   "Alias": "ModifierOwnerEntity"},
                "ValueType": "Layer",
                "Multiplier": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                "DynamicKey": "MDF_Layer",
            }, {
                "$type": "RPG.GameCore.ModifyDamageData",
                "Defender_AllDamageReduce": _dynamic(
                    "AQAR", hashes=[dynamic_value_hash("MDF_Layer")]),
            }],
            "FailedTaskList": [],
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    spec = out["hooks"][0]["effects"][0]["modifier"]
    assert "stacks($self.actor_id, 'Scoped')" in spec["hit_stat_exprs"]["dmg_dmg_reduction"]

    for enemy_id in ("3004021", "3004022"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any("仅支持 AttackData_ConstFinalDamage" in issue["reason"]
                       for issue in real["unsupported"])


@_need_ability
def test_obfuscated_attack_data_reuses_damage_compiler():
    skills, sources = _predicate_skill({})
    sources["character_config"]["SkillList"][0]["TargetInfo"] = {"TargetType": "EnemySelect"}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "MEDEPLMJCIC",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"},
        "AttackProperty": {"DamageType": "Physical", "DamagePercentage": {
            "IsDynamic": False, "FixedValue": {"Value": 1.2}}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert out["action"]["damage_type"] == "physical"
    assert out["action"]["scaling"] == [{"atk": 1.2}]

    real = _real_compiler("5012092").compile_enemy()
    assert not any(issue["node_type"] == "MEDEPLMJCIC"
                   for issue in real["unsupported"])


@_need_ability
def test_obfuscated_origin_root_attach_point_is_presentation_only():
    task = {"$type": "OPBLGCPAKKI", "HPLBJMDGFGJ": "Origin", "MPBNJEOANHL": "Root"}
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    rejected = _task_skill({**task, "TargetType": {"Alias": "Caster"}})
    assert not rejected["ok"]
    for enemy_id in ("8015030", "8015040", "8015050"):
        real = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "OPBLGCPAKKI"
                       for issue in real["unsupported"])


@_need_ability
def test_current_skill_name_list_checks_each_bound_action_id():
    expr = _pred_expr({
        "$type": "RPG.GameCore.ByCurrentSkillName",
        "SkillNameList": ["Skill01", "Skill02"],
    }, extra_skills=({"skill_id": "s2", "trigger_key": "Skill02", "param_list": []},))
    assert expr == "($event.action_id == 's1' or $event.action_id == 's2')"
    assert _pred_expr({
        "$type": "RPG.GameCore.ByCurrentSkillName", "SkillNameList": ["Unknown"],
    }) is None
    real = _real_compiler("4033010").compile_enemy()
    assert not any(issue["node_type"] == "RPG.GameCore.ByCurrentSkillName"
                   for issue in real["unsupported"])


def test_damage_defender_modifier_predicate_reads_hit_target():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    expr = _pred_expr({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "DamageDefenderEntity"},
        "ModifierName": {"Value": "MCommon_DOT_Burn"},
    }, event="after_being_hit")
    assert expr == "has_modifier($event.target, 'MCommon_DOT_Burn')"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    payload = {"source": "source", "target": "hero", "action_id": "s1"}
    assert eng._hooks._hook_amount(expr, source, payload) == 0.0
    hero.modifiers["MCommon_DOT_Burn"] = Modifier(
        modifier_id="MCommon_DOT_Burn", name="Burn", modifier_type="dot", dot_element="fire")
    assert eng._hooks._hook_amount(expr, source, payload) == 1.0


def test_predicate_damage_and_weakness_contextual():
    """ByIsDamageType（伤害事件语境）/ByHasStanceWeak（has_weakness 宿主）翻译钉。"""
    expr = _pred_expr(
        {"$type": "RPG.GameCore.ByIsDamageType",
         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
         "DamageTypeList": ["Fire"]}, event="after_being_hit")
    assert expr == "($event.damage_type == 'fire')"
    expr = _pred_expr(
        {"$type": "RPG.GameCore.ByHasStanceWeak",
         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
         "WeakType": {"DamageType": "Thunder"}})
    assert expr == "has_weakness($self.actor_id, 'thunder')"


def test_predicate_unique_id_static_self_branch():
    """ByCompareMonsterUniqueID 自身静态支（ByCompareMonsterID 静态求值先例同口径）。"""
    expr = _pred_expr(
        {"$type": "RPG.GameCore.ByCompareMonsterUniqueID",
         "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
         "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 12345}}})
    assert expr == "1 == 0"   # fake enemy_id 非 12345
    expr = _pred_expr(
        {"$type": "RPG.GameCore.ByCompareMonsterUniqueID",
         "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 12345}}})
    assert expr == "1 == 0"


def test_modifier_callback_name_uses_event_modifier_id():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Listener"},
    }]
    sources["modifiers"] = {"Listener": {"_CallbackList": [{
        "Event": "OnCreate", "CallbackConfig": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCheckModifierCallBackName",
                "ModifierName": "Watched",
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.SetDynamicValue",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "DynamicKey": {"Value": "Seen"},
                "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }],
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]["modifier"]["on_apply"][0]
    assert effect["condition"] == "$event.modifier_id == 'Watched'"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    st = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1", "target": "source", "modifier_id": "Watched"}
    assert eng._hooks._hook_amount(effect["condition"], st, payload) == 1.0
    payload["modifier_id"] = "Other"
    assert eng._hooks._hook_amount(effect["condition"], st, payload) == 0.0

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCheckModifierCallBackName", "ModifierName": "Watched"})
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("缺少 modifier 回调语境" in issue["reason"] for issue in rejected["unsupported"])


def test_modifier_callback_behavior_flag_uses_event_payload():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    predicate = {
        "$type": "RPG.GameCore.ByCheckModifierCallBackBehaviorFlag",
        "Flag": "DisableAction",
    }
    expr = _pred_expr(predicate, event="after_apply_modifier")
    assert expr == '"DisableAction" in $event.behavior_flags'
    assert _pred_expr({**predicate, "Inverse": True},
                      event="after_remove_modifier") == 'not ("DisableAction" in $event.behavior_flags)'
    assert _pred_expr(predicate, event="on_action") is None

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Watched"},
    }]
    sources["modifiers"] = {"Watched": {
        "BehaviorFlagList": ["STAT_CTRL", "DisableAction"],
    }}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    modifier = out["hooks"][0]["effects"][0]["modifier"]
    assert modifier["behavior_flags"] == ["DisableAction", "STAT_CTRL"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    st = eng.state.actors["source"]
    events = {}
    eng.bus.subscribe("after_apply_modifier", lambda et, p, c: events.setdefault("apply", p))
    eng.bus.subscribe("after_remove_modifier", lambda et, p, c: events.setdefault("remove", p))
    eng._apply_modifier(st, Modifier(
        modifier_id="Watched", name="Watched", modifier_type="buff",
        behavior_flags=["DisableAction", "STAT_CTRL"]))
    eng._remove_modifier(st, "Watched", "test")
    assert events["apply"]["behavior_flags"] == ["DisableAction", "STAT_CTRL"]
    assert events["remove"]["behavior_flags"] == ["DisableAction", "STAT_CTRL"]
    assert eng._hooks._hook_amount(expr, st, events["apply"]) == 1.0
    assert eng._hooks._hook_amount(expr, st, {**events["apply"], "behavior_flags": []}) == 0.0


def test_predicate_unregistered_reasons_specific():
    """谓词逐型拒因钉：未知站位类型有独立拒因。"""
    for pred, needle in (
        ({"$type": "RPG.GameCore.ByIsTeamLocationIndexType",
          "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
          "TeamType": "TeamDark", "Type": "Unknown"}, "词表外"),
    ):
        expr = _pred_expr(pred)
        assert expr is None
        # 拒因经 compiler._issue 落 ctx.unsupported——重编译取回
        sources = {
            "character_config": {"SkillList": [{
                "Name": "Skill01", "SkillType": "Skill",
                "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
            }]},
            "abilities": {"A": {"Name": "A", "OnStart": [{
                "$type": "RPG.GameCore.PredicateTaskList", "Predicate": pred,
                "SuccessTaskList": [{
                    "$type": "RPG.GameCore.DefineDynamicValue",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                    "DynamicKey": {"Value": "X"},
                    "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}],
            }]}},
            "modifiers": {},
        }
        skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
        out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
        assert any(needle in i["reason"] for i in out["unsupported"]), \
            f"{needle} 拒因未落：{[i['reason'] for i in out['unsupported']]}"


def test_dynamic_key_hash_table_lookup_and_exclusions():
    """全语料动态键哈希反查表（pipeline 生成物，scripts/mine_dynamic_key_table.py）：
    全局/跨文件写入键回收为 dynamic_of 活读；MDF_ 内联参数族与不可反解哈希保持显式未知。"""
    from hsr_nous.pipeline.enemies.dynamic_key_table import (DYNAMIC_KEY_HASH_TABLE,
                                                             lookup_dynamic_key_name)

    def build(hashes):
        tasks = [{
            "$type": "RPG.GameCore.SetDynamicValueByAddValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "Key": {"Value": f"Sink{index}"},
            "AddValue": {"IsDynamic": True, "PostfixExpr": {
                "OpCodes": "AQAAAAIR", "FixedValues": [{"Value": 1}],
                "DynamicHashes": [hashed]}},
        } for index, hashed in enumerate(hashes)]
        sources = {
            "character_config": {"SkillList": [{
                "Name": "Skill01", "SkillType": "Skill",
                "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
            }]},
            "abilities": {"A": {"Name": "A", "OnStart": tasks}},
            "modifiers": {},
        }
        skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
        return AbilityCompiler("fake", skills, sources).compile_skill("Skill01")

    assert len(DYNAMIC_KEY_HASH_TABLE) >= 1000, "语料表规模异常（tbgd 缺失？）"
    assert lookup_dynamic_key_name(-1368562990) == "OneMoreCount"
    out = build([1912601768, 768008000])   # _Layer / CurrentSummonIndex
    by_key = {e.get("dynamic_key"): str(e.get("amount"))
              for h in out["hooks"] for e in h.get("effects", [])}
    assert "dynamic_of($self.actor_id, '_Layer')" in by_key["Sink0"]
    assert "dynamic_of($self.actor_id, 'CurrentSummonIndex')" in by_key["Sink1"]
    rejected = build([2128130574, 1227332892])   # MDF_PropertyValue / MaxOneMoreCount 读哈希
    unknown = [i["reason"] for i in rejected["unsupported"] if "未知 DynamicHash" in i["reason"]]
    assert any("2128130574" in r for r in unknown), "内联参数族应保持未知（静默 0 比显式未知更坏）"
    # 决策卡 #27：MaxOneMoreCount 转为运行时供给键收编（默认 1 + 待实测），不再未知
    assert not any("1227332892" in r for r in unknown), "MaxOneMoreCount 已注册（决策卡 #27）"
    resolved = {e.get("dynamic_key"): str(e.get("amount"))
                for h in rejected["hooks"] for e in h.get("effects", [])}
    assert any("dynamic_of($self.actor_id, 'MaxOneMoreCount')" in v for v in resolved.values())


@_need_ability
def test_one_more_per_turn_family_extra_turn_quota(tmp_path):
    """OneMorePerTurn 族运行钉（决策卡 #27）：每回合 1+1 动、额度重置只认普通回合.

    编译产物形态取自本族真实编译输出（modifier on_apply/on_remove + 三条生命周期钩）。
    计数：普通回合开始 3 次、额外回合开始恰好 3 次（每普通回合一次再动）、
    普通回合结束 OneMoreCount 重置为 1。若重置误含额外回合则无限续杯——
    行动数安全阀 >20 直接判负，防挂死。
    """
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim import CombatEngine, MODE_EXPECTED
    from hsr_nous.sim.compile import compile_encounter

    max_expr = "dynamic_of($self.actor_id, 'MaxOneMoreCount')"
    count_expr = "dynamic_of($self.actor_id, 'OneMoreCount')"
    one_more_modifier = {
        "modifier_id": "OneMorePerTurn", "name": "OneMorePerTurn", "modifier_type": "buff",
        "duration": 0, "max_stack": 1, "stacks": 1, "stack_mode": "refresh", "dispellable": True,
        "on_apply": [{"effect_type": "set_dynamic_value", "target": "self",
                      "dynamic_key": "OneMoreCount", "amount": max_expr}],
        "on_remove": [{"effect_type": "set_dynamic_value", "target": "self",
                       "dynamic_key": "OneMoreCount", "amount": 0}],
    }
    hooks = [
        {"event": "on_battle_start", "condition": "true",
         "effects": [{"effect_type": "apply_modifier", "target": "self",
                      "modifier": one_more_modifier}]},
        {"event": "on_turn_start",
         "condition": f"$event.actor == $self.actor_id and $event.kind == 'normal' and {count_expr} > 0",
         "effects": [{"effect_type": "grant_extra_turn", "target": "self"}]},
        {"event": "on_action_end", "condition": "$event.actor == $self.actor_id",
         "effects": [{"effect_type": "set_dynamic_value", "target": "self",
                      "dynamic_key": "OneMoreCount", "amount": f"{count_expr} - 1"}]},
        {"event": "on_turn_end",
         "condition": "$event.actor == $self.actor_id",
         "effects": [{"effect_type": "set_dynamic_value", "target": "self",
                      "dynamic_key": "OneMoreCount", "amount": max_expr}]},
    ]
    template = generate_enemy_template("1013020")
    template.update({
        "actions": [{"action_id": "bite", "name": "测试咬击", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        "hooks": hooks,
        "policy": {"sequence": ["bite"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1013020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 100000, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1013020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 350},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    events = []
    engine.bus.subscribe("on_turn_start",
                         lambda et, payload, ctx: events.append((et, (payload.get("kind"), payload.get("actor")))))
    engine.bus.subscribe("on_action_end",
                         lambda et, payload, ctx: events.append((et, (None, payload.get("actor")))))
    engine.setup()
    engine.run()
    enemy_normal = sum(1 for et, (k, a) in events if et == "on_turn_start"
                       and k == "normal" and a == "1013020")
    extras = sum(1 for et, (k, a) in events if et == "on_turn_start" and k == "normal_extra")
    actions = [a for et, a in events if et == "on_action_end" and a[1] == "1013020"]
    assert enemy_normal >= 2, "至少两个普通回合才谈得上周而复始"
    assert extras in (enemy_normal, enemy_normal - 1), (
        f"N,E 交替再动（末回合的再动可能未轮到）：{events}")
    assert len(actions) == enemy_normal + extras, (
        f"行动数 = 普通回合 + 再动：{len(actions)} vs {enemy_normal}+{extras}")


def test_team_location_predicate_compile_forms():
    """站位谓词含缺省/Left 与 Max/Right 同义形，未知类型仍拒绝。"""
    def _compile(ptype, inverse=False):
        skills, sources = _predicate_skill({
            "$type": "RPG.GameCore.ByIsTeamLocationIndexType",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "TeamType": "TeamDark", **({"Type": ptype} if ptype else {}),
            **({"Inverse": True} if inverse else {}),
        })
        return AbilityCompiler("fake", skills, sources).compile_skill("Skill01")

    out = _compile("Left")
    assert out["ok"] and "position_of($it, 'dark') == 1" in out["hooks"][0]["condition"]
    out = _compile("Right")
    assert out["ok"] and "position_of($it, 'dark') == side_size($it, 'dark')" in out["hooks"][0]["condition"]
    out = _compile("Medium")
    cond = out["hooks"][0]["condition"]
    assert out["ok"] and "position_of($it, 'dark') > 1" in cond and "position_of($it, 'dark') < side_size($it, 'dark')" in cond
    out = _compile("Pos2")
    assert out["ok"] and "position_of($it, 'dark') == 2" in out["hooks"][0]["condition"]
    out = _compile("Left", inverse=True)
    assert out["ok"] and "not (position_of($it, 'dark') == 1)" in out["hooks"][0]["condition"]
    for ptype, position in (("Max", "side_size($it, 'dark')"), (None, "1")):
        out = _compile(ptype)
        assert out["ok"] and f"position_of($it, 'dark') == {position}" in out["hooks"][0]["condition"]
    out = _compile("Unknown")
    assert not out["ok"] and any("词表外" in i["reason"] for i in out["unsupported"])
    real = _real_compiler("2004021").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.ByIsTeamLocationIndexType"
                   for item in real["unsupported"])


def test_position_of_and_side_size_runtime():
    """站位运行时语义：同侧存活列表序（与 blast 相邻同口径）+ 死亡重排 + 跨侧归零。"""
    from tests._builders import engine_vs_dummy, make_actor, make_dummy
    eng = engine_vs_dummy(allies=[make_actor("ally")],
                          enemies=[make_dummy("e1"), make_dummy("e2"), make_dummy("e3")])
    eng.setup()
    st = eng.state.actors["e1"]

    def ok(cond):
        expr = eng._expr.compile(cond)
        return bool(eng._expr.evaluate(expr, eng._hooks._hook_ctx(st, {}),
                                       functions=eng._hooks._hook_functions(st, _roll_readonly=True)))

    assert ok("position_of('e1', 'dark') == 1")
    assert ok("position_of('e2', 'dark') == 2")
    assert ok("position_of('e3', 'dark') == 3")
    assert ok("side_size('e1', 'dark') == 3")
    assert ok("side_size('e1', 'light') == 2")   # hero + ally
    assert ok("position_of('hero', 'light') == 1")
    assert ok("position_of('ally', 'light') == 2")
    assert ok("position_of('hero', 'dark') == 0"), "跨侧归零"
    # 右端点 = 存活数；Medium = 非端点；死亡后存活序重排
    assert ok("position_of('e3', 'dark') == side_size('e3', 'dark')")
    assert ok("position_of('e2', 'dark') > 1 and position_of('e2', 'dark') < side_size('e2', 'dark')")
    eng.state.actors["e2"].alive = False
    assert ok("position_of('e3', 'dark') == 2"), "e2 阵亡后 e3 前移"
    assert ok("side_size('e1', 'dark') == 2")
    assert ok("position_of('e2', 'dark') == 0"), "阵亡者不占位"


def test_monster_unique_id_predicate_compile_and_runtime():
    """UniqueID 谓词（决策卡 #30）：ParamEntity 逐候选 + 自身静态支按 id//10 求值."""
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 401402}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and "monster_unique_id($it) == 401402" in out["hooks"][0]["condition"]

    # 自身静态支：编译器 enemy_id=4014010，UniqueID=401401 应命中（旧实现直比全 id 恒假）
    skills2, sources2 = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterUniqueID",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "TargetMonsterUniqueID": {"IsDynamic": False, "FixedValue": {"Value": 401401}},
    })
    out2 = AbilityCompiler("4014010", skills2, sources2).compile_skill("Skill01")
    assert out2["ok"] and "1 == 1" in out2["hooks"][0]["condition"]

    # 运行时：怪物 UniqueID = 模板 id // 10，跨实例后缀归一化
    from tests._builders import engine_vs_dummy, make_dummy
    eng = engine_vs_dummy(enemies=[make_dummy("4014010"), make_dummy("4014020")])
    eng.setup()
    st = eng.state.actors["4014010"]

    def uid_of(aid):
        expr = eng._expr.compile(f"monster_unique_id('{aid}')")
        return eng._expr.evaluate(expr, eng._hooks._hook_ctx(st, {}),
                                  functions=eng._hooks._hook_functions(st, _roll_readonly=True))
    assert uid_of("4014010") == 401401
    assert uid_of("4014020") == 401402
    assert uid_of("hero") == 0.0, "非数值 id 安全缺省"


def test_level_entity_blackboard():
    """关卡黑板（决策卡 #31）：LevelEntity 动态值读写 + modifier 判定 + 不占站位."""
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LevelEntity"},
        "DynamicKey": {"Value": "SoldierCount01"},
        "CompareType": "GreaterEqual",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    assert "dynamic_of($level, 'SoldierCount01') >= 2" in out["hooks"][0]["condition"]

    from tests._builders import engine_vs_dummy, make_dummy
    eng = engine_vs_dummy(enemies=[make_dummy("e1"), make_dummy("e2")])
    eng.setup()
    st = eng.state.actors["e1"]

    def evaluate(cond):
        expr = eng._expr.compile(cond)
        return eng._expr.evaluate(expr, eng._hooks._hook_ctx(st, {}),
                                  functions=eng._hooks._hook_functions(st, _roll_readonly=True))
    assert evaluate("dynamic_of($level, 'SoldierCount01') == 0")
    eng._hooks._run_hook_effect(st, {"effect_type": "set_dynamic_value", "target": "$level",
                                     "dynamic_key": "SoldierCount01", "amount": 2}, {})
    assert evaluate("dynamic_of($level, 'SoldierCount01') == 2"), "关卡黑板写入后读得出"
    assert "$level" not in eng.state.actors, "关卡黑板不占 actors/站位"
    assert evaluate("side_size($level, 'dark') == 2"), "关卡黑板不影响人数统计"
    assert not evaluate("has_modifier($level, '某标记')")
    eng._hooks._run_hook_effect(st, {"effect_type": "apply_modifier", "target": "$level",
                                     "modifier": {"modifier_id": "WeatherPhase01Flag",
                                                  "name": "天气一阶段", "modifier_type": "buff",
                                                  "duration": 0, "max_stack": 1}}, {})
    assert evaluate("has_modifier($level, 'WeatherPhase01Flag')"), "关卡级 modifier 可挂可查"


def test_on_stack_behavior_compiles_runtime_hook():
    """OnStack 行为任务（决策卡 #32）：叠层触发型行为编译为 on_stack 运行时钩."""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Buff"},
        }]}},
        "modifiers": {
            "Buff": {"_CallbackList": [{
                "Event": "OnStack", "CallbackConfig": [{
                    "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                    "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.2}},
                }, {
                    "$type": "RPG.GameCore.SetDynamicValue",
                    "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                    "DynamicKey": {"Value": "StackCounter"},
                    "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                }],
            }]},
        },
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    hooks = [h for h in out["hooks"] if h["event"] == "after_apply_modifier"]
    assert hooks, "叠层行为应编译出 after_apply_modifier 钩"
    assert "$event.modifier_id" in hooks[0]["condition"]
    effects = [e for h in hooks for e in h["effects"]]
    assert any(e["effect_type"] == "set_dynamic_value"
               and e.get("dynamic_key") == "StackCounter" for e in effects), effects


def test_on_stack_attach_skill_type_disable_tracks_modifier_lifecycle():
    from hsr_nous.sim.resources import ultimate_available
    from tests._builders import basic_action, engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Buff"},
    }]
    sources["modifiers"] = {"Buff": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.AttachSkillTypeDisable", "Types": ["Ultra", "Normal", "Skill"],
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["locked_action_types"] == ["basic", "skill", "ultimate"]

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(hero, effect, {})
    ultimate = basic_action("ultimate", action_type="ultimate")
    hero.current_energy = hero.actor.stats.max_energy
    assert not eng._available_if_ok(hero, ultimate)
    assert not ultimate_available(hero, ultimate)
    assert not eng._available_if_ok(hero, basic_action("basic", action_type="basic"))
    assert not eng._available_if_ok(hero, basic_action("skill", action_type="skill"))
    eng._remove_modifier(hero, "Buff", "test")
    assert eng._available_if_ok(hero, ultimate)
    assert ultimate_available(hero, ultimate)


def test_on_stack_weak_resistance_maps_element_panel():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Buff"},
    }]
    sources["modifiers"] = {"Buff": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackWeakResistance",
            "StackResistanceList": [
                {"DamageType": "Fire", "Value": {"IsDynamic": False, "FixedValue": {"Value": 0.1}}},
                {"DamageType": "Ice", "Value": {"IsDynamic": False, "FixedValue": {"Value": 0.2}}},
            ],
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["stat_effects"] == {"res_fire": 0.1, "res_ice": 0.2}
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(hero, effect, {})
    stats = eng.pipeline.effective_stats(hero)
    assert stats["res_fire"] == pytest.approx(0.1)
    assert stats["res_ice"] == pytest.approx(0.2)


def test_on_stack_enable_negative_hp_tracks_parent_lifecycle():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Buff"},
    }]
    sources["modifiers"] = {"Buff": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{"$type": "RPG.GameCore.EnableNegativeHP"}],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["modifier"]["allow_negative_hp"] is True
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(hero, effect, {})
    hero.current_hp = -100
    eng._check_death(hero)
    assert hero.alive and hero.current_hp == -100
    eng._remove_modifier(hero, "Buff", "test")
    eng._check_death(hero)
    assert not hero.alive


def test_always_idle_on_and_off():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [
        {"$type": "RPG.GameCore.SetCharacterAlwaysIdleState", "On": True},
        {"$type": "RPG.GameCore.SetCharacterAlwaysIdleState", "On": False},
    ]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[0]["modifier"]["prevent_action"] is True
    assert effects[1]["effect_type"] == "remove_modifier"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    st = eng.state.actors["source"]
    eng._hooks._run_hook_effect(st, effects[0], {})
    assert st.modifiers["ALWAYS_IDLE"].prevent_action is True
    eng._hooks._run_hook_effect(st, effects[1], {})
    assert "ALWAYS_IDLE" not in st.modifiers


def test_entity_action_state_false_and_true():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [
        {"$type": "RPG.GameCore.SetEntityActionState", "UniqueName": "DollBoss", "ActionState": False},
        {"$type": "RPG.GameCore.SetEntityActionState", "UniqueName": "DollBoss", "ActionState": True},
    ]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert effects[0]["modifier"]["prevent_action"] is True
    assert effects[1]["effect_type"] == "remove_modifier"
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    st = eng.state.actors["source"]
    eng._hooks._run_hook_effect(st, effects[0], {})
    assert st.modifiers["ENTITY_ACTION_DollBoss"].prevent_action is True
    eng._hooks._run_hook_effect(st, effects[1], {})
    assert "ENTITY_ACTION_DollBoss" not in st.modifiers


def test_after_apply_modifier_fires_on_every_apply():
    """after_apply_modifier 运行时钉（叠层行为合并载体）：首挂与刷新各发一次."""
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy
    eng = engine_vs_dummy()
    eng.setup()
    st = eng.state.actors["e1"]
    seen = []
    eng.bus.subscribe("after_apply_modifier",
                      lambda et, p, c: seen.append(p["modifier_id"]))
    mod = Modifier(modifier_id="Buff", name="Buff", modifier_type="buff",
                   duration=3, max_stack=3, stacks=1)
    eng._apply_modifier(st, mod)
    eng._apply_modifier(st, mod)   # refresh 叠层同发
    assert seen == ["Buff", "Buff"], seen


def test_neighbor_predicates_and_position_delta():
    """左右邻目标别名 + position_delta/neighbor_of（决策卡 #35）：多族谓词的共同载体."""
    # 编译：ByIsContainModifier 的 CasterLeft/RightEntity 目标
    for alias, offset in (("CasterLeftEntity", -1), ("CasterRightEntity", 1)):
        skills, sources = _predicate_skill({
            "$type": "RPG.GameCore.ByIsContainModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
            "ModifierName": {"Value": "Buff"},
        })
        out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
        assert out["ok"], out["unsupported"]
        assert f"position_delta($it, $self.actor_id) == {offset}" in out["hooks"][0]["condition"]

    # 运行时：e1/e2/e3 三怪,e2 的左邻=e1、右邻=e3;position_delta 同侧站位差
    from tests._builders import engine_vs_dummy, make_dummy
    eng = engine_vs_dummy(enemies=[make_dummy("e1"), make_dummy("e2"), make_dummy("e3")])
    eng.setup()
    st = eng.state.actors["e2"]

    def ev(cond):
        expr = eng._expr.compile(cond)
        return eng._expr.evaluate(expr, eng._hooks._hook_ctx(st, {}),
                                  functions=eng._hooks._hook_functions(st, _roll_readonly=True))
    assert ev("neighbor_of('e2', -1) == 'e1'")
    assert ev("neighbor_of('e2', 1) == 'e3'")
    assert ev("neighbor_of('e1', -1) == ''"), "最左无左邻"
    assert ev("position_delta('e3', 'e2') == 1")
    assert ev("position_delta('e1', 'e2') == -1")
    assert ev("position_delta('hero', 'e2') == 0"), "跨侧归零"
    # 死亡后邻居重排:e1 阵亡,e2 左邻变""
    eng.state.actors["e1"].alive = False
    assert ev("neighbor_of('e2', -1) == ''")


@pytest.mark.parametrize(("alias", "expected", "wrong"), [
    ("AbilityTargetLeftEntity", "left", "right"),
    ("AbilityTargetRightEntity", "right", "left"),
])
def test_ability_target_side_modifier_predicate(alias, expected, wrong):
    from types import SimpleNamespace
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "ModifierName": {"Value": "Mark"},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    condition = out["hooks"][0]["condition"]
    assert "position_delta($it, $event.target)" in condition
    assert "has_modifier($it, 'Mark')" in condition

    eng = engine_vs_dummy(
        enemies=[make_dummy("source")],
        allies=[make_actor("left"), make_actor("mid"), make_actor("right")])
    source = eng.state.actors["source"]
    payload = {"actor": "source", "action_id": "s1", "target": "mid"}
    hook = SimpleNamespace(
        condition_expr=eng._expr.compile(condition, layer="effect"),
        owner_id="source", event="on_action")
    eng._apply_modifier(eng.state.actors[wrong], Modifier(
        modifier_id="Mark", name="Mark", modifier_type="debuff"))
    assert eng._hooks._hook_amount(condition, source, payload) == 0.0
    assert not eng._hooks._hook_condition_ok(hook, source, payload)
    eng._apply_modifier(eng.state.actors[expected], Modifier(
        modifier_id="Mark", name="Mark", modifier_type="debuff"))
    assert eng._hooks._hook_amount(condition, source, payload) == 1.0
    assert eng._hooks._hook_condition_ok(hook, source, payload)


def test_pool_modifier_predicates_evaluate_per_candidate_in_engine():
    from hsr_nous.sim.state import Modifier
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterLeftEntity"},
        "ModifierName": {"Value": "Buff"},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and "count_selected" in out["hooks"][0]["condition"]
    eng = engine_vs_dummy(enemies=[make_dummy("e1"), make_dummy("e2")])
    st = eng.state.actors["e2"]
    payload = {"actor": "e2", "action_id": "s1"}
    condition = out["hooks"][0]["condition"]
    assert eng._hooks._hook_amount(condition, st, payload) == 0.0
    eng.state.actors["e1"].modifiers["Buff"] = Modifier(
        modifier_id="Buff", name="Buff", modifier_type="buff")
    assert eng._hooks._hook_amount(condition, st, payload) == 1.0
    sources["abilities"]["A"]["OnStart"][0]["Predicate"]["Inverse"] = True
    inverted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert eng._hooks._hook_amount(inverted["hooks"][0]["condition"], st, payload) == 0.0
    del eng.state.actors["e1"].modifiers["Buff"]
    assert eng._hooks._hook_amount(inverted["hooks"][0]["condition"], st, payload) == 1.0

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummonedMinions"},
        "ModifierName": {"Value": "Buff"},
    })
    summons = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    boss = make_dummy("boss")
    minion = make_dummy("minion")
    minion.summoner_id = "boss"
    eng = engine_vs_dummy(enemies=[boss, minion])
    st = eng.state.actors["boss"]
    payload = {"actor": "boss", "action_id": "s1"}
    condition = summons["hooks"][0]["condition"]
    assert eng._hooks._hook_amount(condition, st, payload) == 0.0
    eng.state.actors["minion"].modifiers["Buff"] = Modifier(
        modifier_id="Buff", name="Buff", modifier_type="buff")
    assert eng._hooks._hook_amount(condition, st, payload) == 1.0


def test_recursive_modifier_lifecycle_is_not_unrolled():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Buff"},
    }]
    sources["modifiers"] = {"Buff": {"_CallbackList": [{
        "Event": "OnCreate", "CallbackConfig": [{
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByIsContainModifier",
                "TargetType": {
                    "$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummonedMinions"},
                "ModifierName": {"Value": "Buff"},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                "ModifierName": {"Value": "Buff"},
            }],
        }],
    }, {
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]


def test_frozen_behavior_flag_predicate():
    """STAT_CTRL_Frozen 旗标谓词 → controlled(target, 'freeze')（决策卡 #35）."""
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByContainBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "Flag": "STAT_CTRL_Frozen",
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and "controlled($it, 'freeze')" in out["hooks"][0]["condition"]


def test_on_stack_conditional_property_compiles_expression():
    """OnStack 条件属性分支（决策卡 #36）：谓词可翻则属性改条件表达式."""
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.AddModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "ModifierName": {"Value": "Buff"},
        }]}},
        "modifiers": {"Buff": {"_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.PredicateTaskList",
                "Predicate": {"$type": "RPG.GameCore.ByCompareDynamicValue",
                              "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                              "DynamicKey": {"Value": "Flag"},
                              "CompareType": "Greater",
                              "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 0}}},
                "SuccessTaskList": [{
                    "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                    "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
                }, {
                    "$type": "RPG.GameCore.SetMonsterEnergyBarState",
                }],
                "FailedTaskList": [{
                    "$type": "RPG.GameCore.StackProperty", "Property": "AttackAddedRatio",
                    "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 0.1}},
                }],
            }],
        }]}},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    effects = [e for h in out["hooks"] for e in h["effects"]]
    mod = next(e["modifier"] for e in effects if e["effect_type"] == "apply_modifier")
    expr = mod["stat_exprs"]["atk_pct"]
    assert "dynamic_of" in expr and "?" in expr, f"属性应编译为条件表达式：{expr}"
    assert "0.5" in expr and "0.1" in expr

    callback = sources["modifiers"]["Buff"]["_CallbackList"][0]["CallbackConfig"]
    for node_type in (
            "RPG.GameCore.DebugLog",
            "RPG.GameCore.ClearEntityFloatMessage",
            "RPG.GameCore.HideMonsterSkillInViewMode",
            "RPG.GameCore.HideSkillDisplayInfo",
            "RPG.GameCore.RefreshWeaknessUI",
            "RPG.GameCore.SaveModelWhenDead",
            "RPG.GameCore.SetIronTombInfinityHPUI",
            "RPG.GameCore.SetMonsterPhasePointPrefab",
            "RPG.GameCore.TriggerAnimStateOnModifierCustomEvent"):
        callback.append({"$type": node_type})
    assert AbilityCompiler("fake", skills, sources).compile_skill("Skill01")["ok"]
    callback.append({"$type": "RPG.GameCore.SwitchOverrideController"})
    assert AbilityCompiler("fake", skills, sources).compile_skill("Skill01")["ok"]
    callback.append({"$type": "RPG.GameCore.WaitFor"})
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any(issue["node_type"] == "RPG.GameCore.WaitFor"
               for issue in rejected["unsupported"])


def test_light_team_entity_modifier_shared_shield_and_restore():
    import json
    from hsr_nous.sim.save_load import _restore_engine_fields, _save_engine_fields
    from tests._builders import engine_vs_dummy, make_actor, make_dummy

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LightTeamEntity"},
        "ModifierName": {"Value": "TeamShield"},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "has_modifier($light_team, 'TeamShield')" in out["hooks"][0]["condition"]

    eng = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    effect = {
        "effect_type": "apply_modifier", "target": "$light_team",
        "modifier": {
            "modifier_id": "TeamShield", "name": "队伍盾", "modifier_type": "buff",
            "duration": 0, "max_stack": 1, "shield": {"flat": 100.0},
        },
    }
    eng._hooks._run_hook_effect(source, effect, {})
    team = eng._light_team_state_obj
    assert team is not None and team.modifiers["TeamShield"].shield_spec == {"flat": 100.0}
    assert team.shields[0].remaining == 100.0
    assert "$light_team" not in eng.state.actors
    assert eng._hooks._hook_target_states("$light_team", source, {}) == [team]
    assert eng._hooks._hook_functions(source)["has_modifier"]("$light_team", "TeamShield")
    assert not eng._hooks._hook_functions(source)["has_modifier"]("$dark_team", "TeamShield")

    saved = json.loads(json.dumps(_save_engine_fields(eng)))
    restored = engine_vs_dummy(allies=[make_actor("ally")], enemies=[make_dummy("source")])
    _restore_engine_fields(restored, saved)
    restored_team = restored._light_team_state_obj
    assert restored_team is not None and restored_team.shields[0].remaining == 100.0
    assert "TeamShield" in restored_team.modifiers
    assert restored._dark_team_state_obj is None or \
        "TeamShield" not in restored._dark_team_state_obj.modifiers

    hero = restored.state.actors["hero"]
    ally = restored.state.actors["ally"]
    assert restored._absorb_with_shields(hero, 60.0, "source") == 0.0
    assert restored_team.shields[0].remaining == 40.0
    assert restored._absorb_with_shields(ally, 50.0, "source") == 10.0
    assert not restored_team.shields and "TeamShield" not in restored_team.modifiers


def test_modify_shield_max_and_current_respect_modifier_ids():
    import json
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from hsr_nous.sim.save_load import _restore_engine_fields, _save_engine_fields
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LightTeamEntity"},
        "ModifierName": {"Value": "TeamShield"},
    }]
    sources["modifiers"] = {"TeamShield": {"_CallbackList": [{
        "Event": "OnCreate", "CallbackConfig": [{
            "$type": "RPG.GameCore.InitShield",
            "TargetType": {
                "$type": "RPG.GameCore.TargetAlias", "Alias": "LightTeamEntity"},
            "ShieldValue": {"IsDynamic": False, "FixedValue": {"Value": 100}},
        }],
    }, {
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.ModifyShieldMax",
            "TargetType": {
                "$type": "RPG.GameCore.TargetAlias", "Alias": "LightTeamEntity"},
            "ShieldModifiers": ["TeamShield"], "ModifyOp": "Set",
            "FormulaValue": {"IsDynamic": False, "FixedValue": {"Value": 200}},
        }, {
            "$type": "RPG.GameCore.ModifyShield",
            "TargetType": {
                "$type": "RPG.GameCore.TargetAlias", "Alias": "LightTeamEntity"},
            "ShieldModifiers": ["TeamShield"], "ModifyOp": "Set",
            "FormulaValue": {"IsDynamic": False, "FixedValue": {"Value": 150}},
        }, {
            "$type": "RPG.GameCore.ModifyShield",
            "TargetType": {
                "$type": "RPG.GameCore.TargetAlias", "Alias": "LightTeamEntity"},
            "ShieldModifiers": ["TeamShield"],
            "FormulaValue": {"IsDynamic": False, "FixedValue": {"Value": 50}},
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    base_apply = next(effect for effect in effects if effect["effect_type"] == "apply_modifier"
                      and effect["modifier"]["modifier_id"] == "TeamShield")
    maximum = next(effect for effect in effects if effect["effect_type"] == "modify_shield"
                   and effect["max"])
    current = next(effect for effect in effects if effect["effect_type"] == "modify_shield"
                   and not effect["max"] and effect["mode"] == "set")
    addition = next(effect for effect in effects if effect["effect_type"] == "modify_shield"
                    and not effect["max"] and effect["mode"] == "add")
    assert maximum["amount"] == 200 and current["amount"] == 150
    assert addition["amount"] == 50 and not addition["allow_expand_max"]
    BuildCompiler()._validate_effects([base_apply, maximum, current, addition], "队伍盾值测试")

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    eng._hooks._run_hook_effect(eng.state.actors["source"], base_apply, {})
    team = eng._light_team_state_obj
    assert team is not None and "TeamShield" in team.modifiers
    assert team.shields[0].modifier_id == "TeamShield"
    assert team.shields[0].remaining == 100
    eng._apply_modifier_spec(team, {
        "modifier_id": "OtherShield", "name": "其他盾", "modifier_type": "buff",
        "duration": 0, "shield": {"flat": 30},
    }, eng.state.actors["source"])
    eng._hooks._run_hook_effect(eng.state.actors["source"], maximum, {})
    eng._hooks._run_hook_effect(eng.state.actors["source"], current, {})
    eng._hooks._run_hook_effect(eng.state.actors["source"], addition, {})
    shield = next(item for item in team.shields if item.modifier_id == "TeamShield")
    other = next(item for item in team.shields if item.modifier_id == "OtherShield")
    assert shield.max_value == 200 and shield.remaining == 200
    assert other.max_value == 0 and other.remaining == 30

    saved = json.loads(json.dumps(_save_engine_fields(eng)))
    restored = engine_vs_dummy(enemies=[make_dummy("source")])
    _restore_engine_fields(restored, saved)
    recovered = next(item for item in restored._light_team_state_obj.shields
                     if item.modifier_id == "TeamShield")
    assert recovered.max_value == 200 and recovered.remaining == 200

    rejected = _task_skill({
        "$type": "RPG.GameCore.ModifyShieldMax", "ModifyOp": "Add",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "LightTeamEntity"},
        "ShieldModifiers": ["TeamShield"],
        "FormulaValue": {"IsDynamic": False, "FixedValue": {"Value": 50}},
    })
    assert not rejected["ok"]


def test_currentshield_modifier_value_reads_team_shield():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.SetDynamicValueByModifierValue",
        "ReadTargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "LightTeamEntity"},
        "ModifierName": "TeamShield", "ValueType": "CurrentShield",
        "Multiplier": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        "DynamicKey": "CurShield",
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount"] == "shield_of($light_team, 'TeamShield')"

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    team = eng._team_entity_state("TeamLight")
    eng._apply_modifier_spec(team, {
        "modifier_id": "TeamShield", "name": "队伍盾", "modifier_type": "buff",
        "duration": 0, "shield": {"flat": 100},
    }, source)
    eng._hooks._run_hook_effect(team, effect, {})
    assert eng._enemy_policy_state["$light_team"]["dynamic_values"]["CurShield"] == 100.0
    eng._hooks._run_hook_effect(team, {
        "effect_type": "modify_shield", "target": "$light_team", "max": False,
        "mode": "add", "modifier_ids": ["TeamShield"], "amount": 50,
    }, {})
    eng._hooks._run_hook_effect(team, effect, {})
    assert eng._enemy_policy_state["$light_team"]["dynamic_values"]["CurShield"] == 150.0


def test_nested_modifier_max_layer_reads_current_parent_max_stack():
    from hsr_nous.sim.state import Modifier
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy

    max_hash = dynamic_value_hash("MDF_MaxLayer")
    ratio_hash = dynamic_value_hash("Ratio")
    layer_hash = dynamic_value_hash("MDF_Layer")
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Parent"},
        "MaxLayer": {"IsDynamic": False, "FixedValue": {"Value": 6}},
        "DynamicValues": {"Ratio": {"IsDynamic": False, "FixedValue": {"Value": 0.5}}},
    }]
    sources["modifiers"] = {
        "Parent": {
            "MaxLayer": 1,
            "DynamicValues": {"Floats": {str(max_hash): {"ReadInfo": {"Type": "None"}}}},
            "_CallbackList": [{"Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.SetDynamicValueByModifierValue",
                "ValueType": "Layer", "DynamicKey": "MDF_Layer",
                "Multiplier": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            }, {
                "$type": "RPG.GameCore.AddModifier",
                "TargetType": {
                    "$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
                "ModifierName": {"Value": "BlackBlood"},
                "DynamicValues": {"MDF_DirtyHPRatio": _dynamic(
                    "AQABAQUBAgQR", hashes=[ratio_hash, max_hash, layer_hash])},
            }]}],
        },
        "BlackBlood": {"_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.StackProperty",
                "TargetType": {
                    "$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
                "Property": "DirtyHPRatio",
                "PropertyValue": _dynamic(
                    "AQAR", hashes=[dynamic_value_hash("MDF_DirtyHPRatio")]),
            }],
        }]},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    nested = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "apply_modifier"
                  and effect["modifier"]["modifier_id"] == "BlackBlood")
    expression = nested["modifier"]["stat_exprs"]["recoverable_hp_reduction"]
    assert "modifier_max_stacks($self.actor_id, 'Parent')" in expression
    assert "(0.5 / modifier_max_stacks($self.actor_id, 'Parent')) * max(1, $modifier.stacks)" \
        in expression

    eng = engine_vs_dummy()
    source = eng.state.actors["e1"]
    source.modifiers["Parent"] = Modifier(
        modifier_id="Parent", name="Parent", modifier_type="buff", max_stack=6, stacks=1)
    eng._apply_modifier_spec(source, nested["modifier"], source)
    eng._cond_aura_present = True
    assert eng.pipeline.effective_stats(source)["recoverable_hp_reduction"] == \
        pytest.approx(0.5 / 6)


def test_dirty_hp_ratio_maps_to_recoverable_hp_reduction_and_reads_back():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash
    from tests._builders import engine_vs_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "BlackBlood"},
        "DynamicValues": {
            "MDF_DirtyHPRatio": {"IsDynamic": False, "FixedValue": {"Value": 0.3}}},
    }, {
        "$type": "RPG.GameCore.SetDynamicValueByProperty",
        "DynamicKey": "CurrentDirtyHPRatio",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Value": "DirtyHPRatio",
    }]
    sources["modifiers"] = {"BlackBlood": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty",
            "TargetType": {
                "$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "Property": "DirtyHPRatio",
            "PropertyValue": _dynamic(
                "AQAR", hashes=[dynamic_value_hash("MDF_DirtyHPRatio")]),
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    apply = next(effect for effect in effects if effect["effect_type"] == "apply_modifier")
    readback = next(effect for effect in effects if effect["effect_type"] == "set_dynamic_value")
    assert apply["modifier"]["stat_effects"]["recoverable_hp_reduction"] == pytest.approx(0.3)
    assert readback["amount"] == "stat_of($self.actor_id, 'recoverable_hp_reduction')"

    eng = engine_vs_dummy()
    source = eng.state.actors["e1"]
    hero = eng.state.actors["hero"]
    eng._hooks._run_hook_effect(source, apply, {})
    eng._hooks._run_hook_effect(source, readback, {})
    assert eng.pipeline.effective_stats(source)["recoverable_hp_reduction"] == pytest.approx(0.3)
    assert eng._enemy_policy_state["e1"]["dynamic_values"]["CurrentDirtyHPRatio"] == \
        pytest.approx(0.3)

    eng._hooks._run_hook_effect(hero, apply, {})
    max_hp = eng.pipeline.effective_stats(hero)["hp"]
    hero.current_hp = max_hp
    assert eng.pipeline.heal(source, hero, amount=1000).node["actualAmount"] == 0.0
    hero.current_hp = max_hp * 0.65
    healed = eng.pipeline.heal(source, hero, amount=max_hp)
    assert healed.node["actualAmount"] == pytest.approx(max_hp * 0.05)
    assert hero.current_hp == pytest.approx(max_hp * 0.7)


def test_turn_insert_action_and_escape_and_remove_shield():
    """插入行动/逃逸/移除护盾三处理器（决策卡 #38）."""
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [
            {"$type": "RPG.GameCore.TurnInsertAction",
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}},
            {"$type": "RPG.GameCore.RemoveShield",
             "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}},
            {"$type": "RPG.GameCore.EscapeFromBattle"},
        ]}},
        "modifiers": {},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    effects = [e for h in out["hooks"] for e in h["effects"]]
    assert any(e["effect_type"] == "grant_extra_turn" for e in effects)
    assert any(e["effect_type"] == "remove_shield" for e in effects)
    assert any(e["effect_type"] == "leave_battle" and e.get("reason") == "flee" for e in effects)

    # 运行时：remove_shield 清空护盾
    from tests._builders import engine_vs_dummy
    from hsr_nous.sim.state import ShieldInstance
    eng = engine_vs_dummy()
    eng.setup()
    st = eng.state.actors["e1"]
    st.shields.append(ShieldInstance(shield_id="s", name="测试盾", remaining=100))
    eng._hooks._run_hook_effect(st, {"effect_type": "remove_shield", "target": "self"}, {})
    assert not st.shields, "护盾应被移除"


def test_modify_action_delay_preserves_battle_event_sequence():
    out = _task_skill({
        "$type": "RPG.GameCore.ModifyActionDelay",
        "TargetType": {"$type": "RPG.GameCore.TargetSequence", "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "BattleEventEntityList"},
            {"$type": "RPG.GameCore.TargetFilter", "Predicate": {
                "$type": "RPG.GameCore.ByCompareBattleEventID",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
                "TargetBattleEventID": {"IsDynamic": False, "FixedValue": {"Value": 20005}},
            }},
        ]},
        "AddNormalizedValue": {"IsDynamic": False, "FixedValue": {"Value": -1}},
    })
    assert out["ok"], out["unsupported"]
    assert out["hooks"][0]["effects"][0] == {
        "effect_type": "advance_action",
        "target": {"pool": "battle_events", "where": "battle_event_exists(20005)"},
        "amount": 100.0,
    }


def test_sequence_config_compiles_children_in_order():
    out = _task_skill({
        "$type": "RPG.GameCore.SequenceConfig",
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "First"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }, {
            "$type": "RPG.GameCore.SetDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "DynamicKey": {"Value": "Second"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 2}},
        }],
    })
    assert out["ok"], out["unsupported"]
    assert [effect["dynamic_key"] for hook in out["hooks"] for effect in hook["effects"]] == [
        "First", "Second"]


def test_loop_execute_and_add_formation_and_entity_param():
    """循环展开/编队加装/动态目标绑定（决策卡 #39）."""
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [
            {"$type": "RPG.GameCore.LoopExecuteTaskListWithInterval",
             "MaxLoopCount": {"IsDynamic": False, "FixedValue": {"Value": 2}},
             "TaskList": [{"$type": "RPG.GameCore.DefineDynamicValue",
                           "DynamicKey": {"Value": "X"},
                           "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}}}]},
            {"$type": "RPG.GameCore.SetDynamicEntityParam",
             "DynamicKey": "MTest_DynamicTarget",
             "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
             "ParamTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}},
        ]}},
        "modifiers": {},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"], out["unsupported"]
    effects = [e for h in out["hooks"] for e in h["effects"]]
    assert sum(1 for e in effects if e["effect_type"] == "set_dynamic_value") == 2, "循环展开两次"
    assert any(e["effect_type"] == "set_dynamic_target" for e in effects)

    # 运行时：动态目标绑定写入
    from tests._builders import engine_vs_dummy
    eng = engine_vs_dummy()
    eng.setup()
    st = eng.state.actors["e1"]
    eng._hooks._run_hook_effect(st, {"effect_type": "set_dynamic_target",
                                     "dynamic_key": "MTest", "target": "self"}, {})
    assert eng._enemy_policy_state["e1"]["dynamic_targets"]["MTest"] == "e1"


def test_loop_execute_expands_static_skill_param_and_supports_live_write_count():
    from hsr_nous.sim_schema.config_ai import dynamic_value_hash

    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": [3]}]
    loop = {
        "$type": "RPG.GameCore.LoopExecuteTaskList",
        "MaxLoopCount": _dynamic("AQAR", hashes=[123]),
        "TaskList": [{
            "$type": "RPG.GameCore.SetDynamicValue",
            "DynamicKey": {"Value": "LoopHit"},
            "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }],
    }
    sources = {
        "character_config": {
            "SkillList": [{
                "Name": "Skill01", "SkillType": "Skill",
                "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
            }],
            "DynamicValues": {"Floats": {
                "123": {"ReadInfo": {
                    "Type": "SkillParam", "TriggerKey": "Skill01", "Index": 0}},
            }},
        },
        "abilities": {"A": {"Name": "A", "OnStart": [loop]}},
        "modifiers": {"Mark": {}},
    }
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    assert sum(effect["effect_type"] == "set_dynamic_value" for effect in effects) == 3

    for invalid in (0, -1, 1.5):
        loop["MaxLoopCount"] = {"IsDynamic": False, "FixedValue": {"Value": invalid}}
        rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
        assert not rejected["ok"]
        assert any("循环次数必须是确定的正整数" in issue["reason"]
                   for issue in rejected["unsupported"])

    loop["MaxLoopCount"] = _dynamic("AQAR", hashes=[dynamic_value_hash("LoopCount")])
    live = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert live["ok"] and not live["unsupported"]
    assert any(effect["effect_type"] == "loop_effects"
               for hook in live["hooks"] for effect in hook["effects"])

    loop["TaskList"] = [{
        "$type": "RPG.GameCore.SummonMonster",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }]
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("动态次数循环含未收编机制任务" in issue["reason"]
               for issue in rejected["unsupported"])


def test_current_turn_action_entity_uses_turn_owner_namespace():
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareCharacterID",
        "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "CurrentTurnActionEntity"},
        "TargetCharacterID": {"IsDynamic": False, "FixedValue": {"Value": 1207}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"]
    assert "character_id(turn_owner_of()) == '1207'" in out["hooks"][0]["condition"]


def test_character_damage_type_and_turn_owner_predicates():
    """伤害属性判定 + 全语境回合归属者（决策卡 #40）."""
    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCharacterDamageType",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "DamageType": "Fire",
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and "element_of($it) == 'fire'" in out["hooks"][0]["condition"]
    inverse_skills, inverse_sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCharacterDamageType",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "DamageType": "Fire", "Inverse": True,
    })
    inverse = AbilityCompiler("fake", inverse_skills, inverse_sources).compile_skill("Skill01")
    assert inverse["ok"] and "not (element_of($it) == 'fire')" in inverse["hooks"][0]["condition"]

    skills2, sources2 = _predicate_skill({
        "$type": "RPG.GameCore.ByIsTurnOwnerEntity",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    })
    out2 = AbilityCompiler("fake", skills2, sources2).compile_skill("Skill01")
    assert out2["ok"] and "turn_owner_of() == $self.actor_id" in out2["hooks"][0]["condition"]


def test_turn_action_entity_matches_turn_owner_in_event_context():
    from hsr_nous.adapters.enemy_ability import _Context
    from tests._builders import engine_vs_dummy, make_dummy

    for event, alias, expected in (
            ("on_action", "Caster", "turn_owner_of() == $self.actor_id"),
            ("on_kill", "ParamEntity", "turn_owner_of() == $event.target"),
            ("after_apply_modifier", "ParamEntity", "turn_owner_of() == $event.target")):
        predicate = {"$type": "RPG.GameCore.ByIsTurnActionEntity",
                     "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias}}
        compiler = AbilityCompiler("fake", [], {})
        ctx = _Context(mode="event", skill={}, event=event)
        assert compiler._predicate_expr(predicate, ctx, "test") == expected
        assert not ctx.unsupported

    predicate = {"$type": "RPG.GameCore.ByIsTurnActionEntity",
                 "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"}}
    compiler = AbilityCompiler("fake", [], {})
    expression = compiler._predicate_expr(
        predicate, _Context(mode="event", skill={}, event="on_kill"), "test")
    eng = engine_vs_dummy(enemies=[make_dummy("source"), make_dummy("other")])
    source = eng.state.actors["source"]
    eng._current_turn_actor_id = "source"
    assert eng._hooks._hook_amount(expression, source, {"target": "source"}) == 1.0
    assert eng._hooks._hook_amount(expression, source, {"target": "other"}) == 0.0



def test_non_dot_modifier_direct_dot_damage_uses_dot_route_and_tags():
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from hsr_nous.sim.compile.compiled import CompiledHook
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Periodic"},
    }]
    damage = {
        "$type": "RPG.GameCore.DamageByAttackProperty",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "AttackProperty": {
            "AttackType": "DOT", "DamageType": {"DamageType": "Fire"},
            "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.25}},
            "DamageTag": [{"EnumIndex": 3, "Value": 32}],
        },
    }
    sources["modifiers"] = {"Periodic": {"_CallbackList": [{
        "Event": "OnPhase1", "CallbackConfig": [damage],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    hook = next(h for h in out["hooks"] if h["event"] == "on_turn_start")
    effect = next(e for e in hook["effects"] if e["effect_type"] == "deal_damage")
    assert effect["action_type"] == "dot" and effect["damage_tags"] == [32]
    assert effect["scaling_atk"] == 0.25 and effect["toughness_dmg"] == 0
    BuildCompiler()._validate_effects([effect], "直接 DOT 测试")

    eng = engine_vs_dummy(enemies=[make_dummy("source", atk=1000)])
    source = eng.state.actors["source"]
    mount = next(e for h in out["hooks"] for e in h["effects"]
                 if e["effect_type"] == "apply_modifier")
    eng._hooks._run_hook_effect(source, mount, {})
    eng._compiled_hooks = [CompiledHook(
        owner_id="source", event="on_turn_start",
        condition_expr=eng._expr.compile(hook["condition"], layer="effect"),
        effects=hook["effects"])]
    eng._hooks._subscribe_compiled_hooks()
    hits = []
    eng.bus.subscribe("after_being_hit", lambda _event, payload, _ctx: hits.append(payload))
    eng.bus.emit("on_turn_start", {"actor": "source", "kind": "normal"}, eng.state)
    assert len(hits) == 1
    assert hits[0]["action_type"] == "dot" and hits[0]["damage_tags"] == [32]
    assert hits[0]["source"] == hits[0]["target"] == "source"
    assert hits[0]["amount"] > 0

    damage["AttackProperty"]["DamageTag"] = [{"EnumIndex": 2, "Value": 32}]
    rejected = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert not rejected["ok"]
    assert any("整数 DamageTag" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_non_dot_modifier_direct_dot_damage_compiles():
    for enemy_id in ("5014030", "5014031", "5014032"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.DamageByAttackProperty"
                       and issue["reason"] == "DoT 伤害须由 modifier 定义编译"
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])



def test_obfuscated_control_skill_mapping_is_strictly_ui_only():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Controller"},
    }]
    mapping = {
        "$type": "MOPOKJECALI", "GFNJJEFJKPD": "ControlSkill03",
        "IPOJMHGKIEH": "Skill3_AsatPramad_00",
    }
    sources["modifiers"] = {"Controller": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [mapping],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    assert not any(effect["effect_type"] != "apply_modifier"
                   for hook in out["hooks"] for effect in hook["effects"])

    mapping["Unexpected"] = True
    rejected = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert not rejected["ok"]
    assert any("控制按钮映射" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_obfuscated_control_skill_mapping_compiles():
    for enemy_id in ("8015030", "8015040"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "MOPOKJECALI"
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])



def test_non_dot_on_stage_consumption_matches_actual_expansion():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "StageController"},
    }]
    tasks = [{
        "$type": "RPG.GameCore.DefineDynamicValue",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "DynamicKey": {"Value": "StageSeen"},
        "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]
    sources["modifiers"] = {"StageController": {"_CallbackList": [{
        "Event": "OnStage", "CallbackConfig": tasks,
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    writes = [effect for hook in out["hooks"] if hook["event"] == "on_battle_start"
              for effect in hook["effects"]
              if effect["effect_type"] == "set_dynamic_value"
              and effect.get("dynamic_key") == "StageSeen"]
    assert len(writes) == 1 and writes[0]["amount"] == 1

    tasks.append({"$type": "Unknown.OnStageTask"})
    rejected = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert not rejected["ok"]
    assert any(issue["node_type"] == "Unknown.OnStageTask"
               for issue in rejected["unsupported"])


@_need_ability
def test_real_non_dot_on_stage_consumption_compiles():
    for enemy_id in ("2013010", "2013011", "2013012", "2013013"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any("OnStage 回调任务未被定义编译消费" in issue["reason"]
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])



def test_obfuscated_hp_bar_visibility_is_strictly_presentation_only():
    task = {
        "$type": "DNBOLDHOBML", "GNDCCBNILML": True,
        "HILNFHCPEAD": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
    }
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    task["Unexpected"] = 1
    rejected = _task_skill(task)
    assert not rejected["ok"]
    assert any("血条显隐" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_obfuscated_hp_bar_visibility_compiles():
    out = _real_compiler("4015012").compile_enemy()
    assert not any(issue["node_type"] == "DNBOLDHOBML"
                   for issue in out["unsupported"]), out["unsupported"]



def test_dot_onstack_define_dynamic_value_requires_no_reader():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Burn"},
    }]
    sources["modifiers"] = {"Burn": {
        "BehaviorFlagList": ["STAT_DOT"],
        "_CallbackList": [{
            "Event": "OnStack", "CallbackConfig": [{
                "$type": "RPG.GameCore.DefineDynamicValue",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
                "DynamicKey": {"Value": "PresentationOnly"},
            }],
        }, {
            "Event": "OnPhase1", "CallbackConfig": [{
                "$type": "RPG.GameCore.DamageByAttackProperty",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
                "AttackProperty": {
                    "AttackType": "DOT", "DamageType": {"DamageType": "Fire"},
                    "DamagePercentage": {"IsDynamic": False, "FixedValue": {"Value": 0.2}},
                },
            }],
        }],
    }}
    out = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert out["ok"] and not out["unsupported"], out["unsupported"]

    phase = next(callback for callback in sources["modifiers"]["Burn"]["_CallbackList"]
                 if callback["Event"] == "OnPhase1")
    phase["CallbackConfig"].insert(0, {
        "$type": "RPG.GameCore.PredicateTaskList",
        "Predicate": {
            "$type": "RPG.GameCore.ByCompareDynamicValue",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "DynamicKey": {"Value": "PresentationOnly"},
            "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        },
        "SuccessTaskList": [], "FailedTaskList": [],
    })
    rejected = AbilityCompiler("fake", skills, sources).compile_passive("A", "s1")
    assert not rejected["ok"]
    assert any("DoT 定义的 OnStack 仅支持层数读取" in issue["reason"]
               for issue in rejected["unsupported"])


@_need_ability
def test_real_dot_onstack_dead_write_compiles():
    from hsr_nous.adapters.enemy_ability import _Context

    for enemy_id in ("4023013", "8003020", "8003021", "8003022"):
        compiler = _real_compiler(enemy_id)
        name = "MMonster_XP_Elite01_00_Burn"
        definition = compiler.modifiers[name]
        callback = next(cb for cb in definition["_CallbackList"] if cb["Event"] == "OnStack")
        ctx = _Context(mode="event", skill=next(iter(compiler.skills.values())),
                       event="after_apply_modifier", current_modifier=name)
        compiler._check_definition_consumed(
            name, definition, callback["CallbackConfig"], "OnStack", ctx, "real")
        assert not ctx.unsupported, (enemy_id, ctx.unsupported)



def test_self_dynamic_write_dead_store_skips_unknown_value_only_without_readers():
    for node_type in ("RPG.GameCore.SetDynamicValue", "RPG.GameCore.DefineDynamicValue"):
        for explicit_target in (False, True):
            skills, sources = _predicate_skill({})
            task = {
                "$type": node_type, "DynamicKey": {"Value": "Unused"},
                "ResetValue" if node_type.endswith("DefineDynamicValue") else "Value": {
                    "IsDynamic": True,
                    "PostfixExpr": {"OpCodes": "AQAR", "FixedValues": [],
                                    "DynamicHashes": [123456789]},
                },
            }
            if explicit_target:
                task["TargetType"] = {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}
            sources["abilities"]["A"]["OnStart"] = [task]
            out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
            assert out["ok"] and not out["unsupported"], (node_type, out["unsupported"])
            assert not any(hook.get("effects") for hook in out["hooks"])

            sources["config_ai"] = {
                "$type": "RPG.GameCore.ByCompareDynamicValue",
                "DynamicKey": {"Value": "Unused"},
            }
            rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
            assert not rejected["ok"]
            assert any("动态键/值/自指目标未注册" in issue["reason"]
                       for issue in rejected["unsupported"])


@_need_ability
def test_real_self_dynamic_dead_writes_compile():
    from hsr_nous.adapters.enemy_ability import _Context

    cases = [
        ("5014030", "RPG.GameCore.DefineDynamicValue", "Inferno_Skill02_Bonus_SPRatio"),
        ("3022010", "RPG.GameCore.DefineDynamicValue", "AssistSkill02_DamagePercentage"),
        ("8015030", "RPG.GameCore.DefineDynamicValue", "AsatPramad_Skill3_DamagePercentageDark"),
        ("4032041", "RPG.GameCore.SetDynamicValue", "MDF_NegativeBlood"),
    ]
    for enemy_id, node_type, key in cases:
        compiler = _real_compiler(enemy_id)

        def find(value):
            if isinstance(value, dict):
                raw_key = value.get("DynamicKey") or value.get("Key") or {}
                actual = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
                if value.get("$type") == node_type and actual == key:
                    return value
                for child in value.values():
                    found = find(child)
                    if found is not None:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = find(child)
                    if found is not None:
                        return found
            return None

        task = find(compiler.sources)
        assert task is not None, (enemy_id, key)
        ctx = _Context(mode="event", skill=next(iter(compiler.skills.values())), event="on_apply")
        compiler._compile_define_dynamic(task, ctx, "real", ())
        assert not ctx.unsupported, (enemy_id, ctx.unsupported)



def test_faterin_monster_preview_precalculation_is_non_combat():
    add = {
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Modifier_FateRin_MonsterPreview_PreCal"},
        "DynamicValues": {"#CL_PreShowValue": {
            "IsDynamic": False, "FixedValue": {"Value": 0}}},
    }
    out = _task_skill(add)
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByIsContainModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Modifier_FateRin_MonsterPreview_PreCal"},
    })
    sources["abilities"]["A"]["OnStart"].append(add)
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("modifier 定义缺失" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_faterin_monster_preview_precalculation_compiles():
    for enemy_id in ("4012074", "4012075"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any("Modifier_FateRin_MonsterPreview_PreCal" in issue["reason"]
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])



def test_obfuscated_empty_disable_list_has_no_effect_and_nonempty_rejects():
    task = {
        "$type": "OHONOHOIOJA", "ACJEBIJEHOK": [],
        "HILNFHCPEAD": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
    }
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    task["ACJEBIJEHOK"] = ["Ultra"]
    rejected = _task_skill(task)
    assert not rejected["ok"]
    assert any("显式空列表" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_obfuscated_empty_disable_list_compiles():
    for enemy_id in ("4012074", "4012075"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "OHONOHOIOJA"
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])


def test_obfuscated_auto_bp_preferences_have_no_effect_and_reject_unknown_fields():
    preferences = ["BPSkillPriority", "AdvancedBPReserve", "BPHealingSkill", "IgnoreBPFail"]
    setting = {
        "$type": "AIGHNCCAJPL", "OELMOCMDEJI": "Controller",
        "CHLBKIKJFLC": {key: {"IsDynamic": False, "FixedValue": {"Value": 0}}
                        for key in preferences},
    }
    removing = {
        "$type": "AGPCKNGHOAH", "OELMOCMDEJI": "Controller",
        "DPBLGLBPFGK": preferences,
    }
    for task in (setting, removing):
        out = _task_skill(task)
        assert out["ok"] and not out["unsupported"], out["unsupported"]
        assert not any(hook.get("effects") for hook in out["hooks"])

    setting["CHLBKIKJFLC"]["UnknownPreference"] = {
        "IsDynamic": False, "FixedValue": {"Value": 1}}
    rejected = _task_skill(setting)
    assert not rejected["ok"]
    assert any("自动战斗 BP 偏好" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_obfuscated_auto_bp_preferences_compile():
    out = _real_compiler("5014030").compile_enemy()
    assert not any(issue["node_type"] in {"AIGHNCCAJPL", "AGPCKNGHOAH"}
                   for issue in out["unsupported"]), out["unsupported"]


def test_dispel_other_after_same_target_clear_all_is_redundant():
    skills, sources = _predicate_skill({})
    target = {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"}
    clear_all = {"$type": "RPG.GameCore.DispelStatus", "TargetType": target}
    other = {"$type": "RPG.GameCore.DispelStatus", "TargetType": target, "BuffType": "Other"}
    sources["abilities"]["A"]["OnStart"] = [clear_all, other]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook["effects"]]
    assert len(effects) == 1 and effects[0]["filter"] == "1 == 1"

    for tasks in ([other], [{**clear_all, "TargetType": {
            "$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}}, other],
            [{**clear_all, "Numbers": {"IsDynamic": False, "FixedValue": {"Value": 1}}}, other]):
        sources["abilities"]["A"]["OnStart"] = tasks
        rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
        assert not rejected["ok"]
        assert any("驱散类型/顺序未注册" in issue["reason"]
                   for issue in rejected["unsupported"])


@_need_ability
def test_real_dispel_other_after_clear_all_compiles():
    for enemy_id in ("3004011", "3004013"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.DispelStatus"
                       and issue["reason"] == "驱散类型/顺序未注册"
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])


def test_empty_monster_phase_override_is_presentation_only():
    task = {"$type": "RPG.GameCore.ApplyMonsterPhaseOverrideConfig"}
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    assert not any(hook.get("effects") for hook in out["hooks"])

    task["PhaseMaxHPRatio"] = {"IsDynamic": False, "FixedValue": {"Value": 1}}
    rejected = _task_skill(task)
    assert not rejected["ok"]
    assert any("仅支持无参数" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_empty_monster_phase_override_compiles():
    for enemy_id in ("8015020", "8015021", "8015022"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.ApplyMonsterPhaseOverrideConfig"
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])


def test_predicate_identical_raw_branches_compile_once_without_predicate():
    skills, sources = _predicate_skill({})
    shared = [{
        "$type": "RPG.GameCore.SetDynamicValue", "DynamicKey": {"Value": "Seen"},
        "Value": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    }]
    predicate = {"$type": "RPG.GameCore.ByCompareStageType", "CurrentStageType": "Unknown"}
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.PredicateTaskList", "Predicate": predicate,
        "SuccessTaskList": shared, "FailedTaskList": copy.deepcopy(shared),
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effects = [effect for hook in out["hooks"] for effect in hook.get("effects", [])]
    assert len(effects) == 1 and effects[0]["dynamic_key"] == "Seen"

    sources["abilities"]["A"]["OnStart"][0]["FailedTaskList"][0]["Value"]["FixedValue"]["Value"] = 2
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any(issue["node_type"] == "RPG.GameCore.ByCompareStageType"
               for issue in rejected["unsupported"])


@_need_ability
def test_real_predicate_identical_stage_branches_compile():
    fragments = {
        "4033020": ("/OnCreate/1/Predicate", "/OnAfterBeingHitAll/0/SuccessTaskList/0/Predicate"),
        "4033024": ("/OnCreate/1/Predicate", "/OnAfterBeingHitAll/0/SuccessTaskList/0/Predicate"),
        "4014030": ("/OnCreate/3/FailedTaskList/0/Predicate",),
        "4014031": ("/OnCreate/3/FailedTaskList/0/Predicate",),
        "4014032": ("/OnCreate/3/FailedTaskList/0/Predicate",),
        "4014035": ("/OnCreate/3/FailedTaskList/0/Predicate",),
    }
    for enemy_id, paths in fragments.items():
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.ByCompareStageType"
                       and any(fragment in issue["path"] for fragment in paths)
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])


def test_obfuscated_punchline_add_and_set_use_team_resource():
    from tests._builders import engine_vs_dummy, make_dummy

    add = {
        "$type": "JDOLDFECMPL", "FKCKKFALPBK": "EGFCFCBHJJP",
        "AJHHCOHFIFA": {"IsDynamic": False, "FixedValue": {"Value": 5}},
    }
    out = _task_skill(add)
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    add_effect = out["hooks"][0]["effects"][0]
    assert add_effect == {"effect_type": "gain_resource", "resource_id": "punchline",
                          "amount": 5.0}

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    eng._hooks._run_hook_effect(source, add_effect, {})
    assert eng.state.punchline == 5.0
    assert "punchline" not in source.resources

    set_task = {
        "$type": "JDOLDFECMPL", "FKCKKFALPBK": "DADCFBHGLOH",
        "AJHHCOHFIFA": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }
    out = _task_skill(set_task)
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    set_effect = out["hooks"][0]["effects"][0]
    assert set_effect == {"effect_type": "set_resource", "resource_id": "punchline",
                          "amount": 0.0}
    eng._hooks._run_hook_effect(source, set_effect, {})
    assert eng.state.punchline == 0.0
    assert "punchline" not in source.resources

    for task in ({**add, "FKCKKFALPBK": "Unknown"},
                 {**add, "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"}}):
        rejected = _task_skill(task)
        assert not rejected["ok"]
        assert any("笑点" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_obfuscated_punchline_tasks_compile():
    for enemy_id in ("5012010", "5012020", "5012090"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "JDOLDFECMPL"
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])


def test_remodifier_buff_mask_filters_actual_modifier_kind():
    from tests._builders import engine_vs_dummy, make_dummy

    task = {
        "$type": "RPG.GameCore.Remodifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
        "CasterFilter": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "StatusTypeMask": "Buff", "ModifierName": "Mark", "MaxNumber": 1,
        "TaskList": [{
            "$type": "RPG.GameCore.RemoveModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "ParamModifier"},
        }],
    }
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "remove_modifier")
    assert "modifier_kind($it, 'Mark') == 'buff'" in effect["target"]["where"]
    assert "$self.actor_id" in effect["target"]["where"]

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("buff"), make_dummy("debuff")])
    source, buff, debuff = (eng.state.actors[key] for key in ("source", "buff", "debuff"))
    eng._apply_modifier_spec(buff, {"modifier_id": "Mark", "modifier_type": "buff"}, source)
    eng._apply_modifier_spec(debuff, {"modifier_id": "Mark", "modifier_type": "debuff"}, source)
    selected = eng._hooks._hook_target_states(effect["target"], source, {})
    assert [state.actor.actor_id for state in selected] == ["buff"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert "Mark" not in buff.modifiers and "Mark" in debuff.modifiers
    assert eng._hooks._hook_functions(source)["modifier_kind"]("missing", "Mark") == ""

    for field, value in (("StatusTypeMask", "Debuff"),
                         ("PredicateFilter", {"$type": "RPG.GameCore.ByRandomChance"})):
        rejected = _task_skill({**task, field: value})
        assert not rejected["ok"]
        assert any("Remodifier" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_remodifier_buff_mask_compiles():
    for enemy_id in ("4012020", "4012021"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.Remodifier"
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])


def test_remodifier_predicate_filter_reads_selected_instance_dynamic_value():
    from tests._builders import engine_vs_dummy, make_dummy

    task = {
        "$type": "RPG.GameCore.Remodifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
        "CasterFilter": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": "Mark", "MaxNumber": 1,
        "PredicateFilter": {
            "$type": "RPG.GameCore.ByCompareModifierCallBackDynamicValue",
            "DynamicKey": "Trigger", "CompareType": "Equal",
            "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        },
        "TaskList": [{
            "$type": "RPG.GameCore.RemoveModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "ParamModifier"},
        }],
    }
    out = _task_skill(task)
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effect = next(effect for hook in out["hooks"] for effect in hook["effects"]
                  if effect["effect_type"] == "remove_modifier")
    assert "modifier_dynamic_of($it, 'Mark', 'Trigger') == 1" in effect["target"]["where"]
    assert "$self.actor_id" in effect["target"]["where"]

    eng = engine_vs_dummy(enemies=[
        make_dummy("source"), make_dummy("ready"), make_dummy("waiting")])
    source, ready, waiting = (eng.state.actors[key] for key in ("source", "ready", "waiting"))
    for target, trigger in ((ready, 1), (waiting, 0)):
        eng._apply_modifier_spec(target, {
            "modifier_id": "Mark", "modifier_type": "buff",
            "dynamic_values": {"Trigger": trigger}}, source)
    selected = eng._hooks._hook_target_states(effect["target"], source, {})
    assert [state.actor.actor_id for state in selected] == ["ready"]
    eng._hooks._run_hook_effect(source, effect, {})
    assert "Mark" not in ready.modifiers and "Mark" in waiting.modifiers

    rejected = _task_skill({**task, "PredicateFilter": {
        "$type": "RPG.GameCore.ByRandomChance", "Chance": {
            "IsDynamic": False, "FixedValue": {"Value": 1}}}})
    assert not rejected["ok"]
    assert any("Remodifier" in issue["reason"] for issue in rejected["unsupported"])


@_need_ability
def test_real_remodifier_dynamic_predicate_compiles():
    for enemy_id in ("4052010", "4052012", "4052020", "4053010",
                     "4053012", "4053014", "4053020"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.Remodifier"
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])


def test_rally_hp_stack_and_property_read_use_actor_resource():
    from tests._builders import engine_vs_dummy, make_dummy

    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    for value in (7, -2):
        out = _task_skill({
            "$type": "RPG.GameCore.StackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
            "Property": "RallyHP",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
        })
        assert out["ok"] and not out["unsupported"], out["unsupported"]
        effect = out["hooks"][0]["effects"][0]
        assert effect["effect_type"] == "gain_resource"
        assert effect["resource_id"] == "rally_hp"
        eng._hooks._run_hook_effect(source, effect, {})
    assert source.resources["rally_hp"] == 5.0

    out = _task_skill({
        "$type": "RPG.GameCore.SetDynamicValueByProperty", "DynamicKey": "Balance",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Value": "RallyHP",
    })
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effect = out["hooks"][0]["effects"][0]
    assert effect["amount"] == "resource_of($self.actor_id, 'rally_hp')"
    eng._hooks._run_hook_effect(source, effect, {})
    assert eng._enemy_policy_state["source"]["dynamic_values"]["Balance"] == 5.0


def test_rally_hp_onstack_writes_only_when_stack_hook_runs():
    from tests._builders import engine_vs_dummy, make_dummy

    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "Pool"},
    }]
    sources["modifiers"] = {"Pool": {"_CallbackList": [{
        "Event": "OnStack", "CallbackConfig": [{
            "$type": "RPG.GameCore.StackProperty",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
            "Property": "RallyHP",
            "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 3}},
        }, {
            "$type": "RPG.GameCore.PredicateTaskList",
            "Predicate": {
                "$type": "RPG.GameCore.ByCompareDynamicValue",
                "DynamicKey": {"Value": "Enabled"}, "CompareType": "Equal",
                "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
            },
            "SuccessTaskList": [{
                "$type": "RPG.GameCore.StackProperty",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
                "Property": "RallyHP",
                "PropertyValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
            }],
            "FailedTaskList": [],
        }],
    }]}}
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    hook = next(hook for hook in out["hooks"] if hook["event"] == "after_apply_modifier"
                and any(effect.get("resource_id") == "rally_hp"
                        for effect in hook["effects"]))
    effect = next(effect for effect in hook["effects"]
                  if effect.get("resource_id") == "rally_hp")
    conditional = next(h for h in out["hooks"] if h["event"] == "after_apply_modifier"
                       and "Enabled" in h["condition"])
    assert any(effect.get("resource_id") == "rally_hp" and effect.get("amount") == 2.0
               for effect in conditional["effects"])
    eng = engine_vs_dummy(enemies=[make_dummy("source")])
    source = eng.state.actors["source"]
    assert source.resources.get("rally_hp", 0.0) == 0.0
    for expected in (3.0, 6.0):
        eng._hooks._run_hook_effect(source, effect, {})
        assert source.resources["rally_hp"] == expected


@_need_ability
def test_real_rally_hp_basic_read_write_compiles():
    for enemy_id in ("3024030", "4032010", "4032020"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] in {
            "RPG.GameCore.StackProperty", "RPG.GameCore.SetDynamicValueByProperty"}
            and "RallyHP" in issue["reason"]
            for issue in out["unsupported"]), (enemy_id, out["unsupported"])


def test_heal_rally_hp_consumes_only_actual_healing():
    import types
    from hsr_nous.sim.compile.build_compiler import BuildCompiler
    from tests._builders import engine_vs_dummy, make_dummy

    out = _task_skill({
        "$type": "RPG.GameCore.HealHP",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "HealerTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ModifierOwnerEntity"},
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": 1.0}},
        "IsHealRallyHP": True,
    })
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    effects = out["hooks"][0]["effects"]
    assert [effect["effect_type"] for effect in effects] == ["heal", "gain_resource"]
    assert effects[1]["resource_id"] == "rally_hp"
    assert effects[1]["amount"] == "-$last.actual_amount"
    assert effects[1]["target"] == effects[0]["target"]
    BuildCompiler()._validate_effects(effects, "模板 X")

    eng = engine_vs_dummy(enemies=[make_dummy("source", hp=1000, atk=1000)])
    source = eng.state.actors["source"]
    source.current_hp = 700
    source.resources["rally_hp"] = 500
    eng._hooks._run_hook_effects(source, types.SimpleNamespace(effects=effects), {})
    assert source.current_hp == 1000
    assert source.resources["rally_hp"] == 200

    real = _real_compiler("4032010").compile_enemy()
    assert not any(item["node_type"] == "RPG.GameCore.HealHP"
                   and "RallyHP" in item["reason"] for item in real["unsupported"])


def test_part_entity_zero_targets_main_body_from_part_or_main():
    from tests._builders import engine_vs_dummy, make_dummy

    compiler = AbilityCompiler("fake", [], {"character_config": {}})
    target = compiler._hook_target("PartEntity0")
    assert isinstance(target, dict) and "summoner_of($self.actor_id)" in target["where"]

    eng = engine_vs_dummy(enemies=[
        make_dummy("main"), make_dummy("part"), make_dummy("other")])
    main, part = eng.state.actors["main"], eng.state.actors["part"]
    part.actor.summoner_id = "main"
    for source in (part, main):
        selected = eng._hooks._hook_target_states(target, source, {})
        assert [state.actor.actor_id for state in selected] == ["main"]

    skills, sources = _predicate_skill({
        "$type": "RPG.GameCore.ByCompareMonsterPhase",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "PartEntity0"},
        "CompareType": "Equal", "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert out["ok"] and not out["unsupported"], out["unsupported"]
    assert "current_phase" in out["hooks"][0]["condition"]


@_need_ability
def test_real_part_entity_zero_compiles():
    for enemy_id in ("8013141", "8013144", "8013145", "8015012"):
        out = _real_compiler(enemy_id).compile_enemy()
        assert not any(issue["node_type"] == "RPG.GameCore.ByCompareMonsterPhase"
                       and "PartEntity0" in issue["reason"]
                       for issue in out["unsupported"]), (enemy_id, out["unsupported"])
