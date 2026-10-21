"""通用敌人 Ability 编译器：字节码、节点拒绝、真实样例对拍与行为."""
from __future__ import annotations

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
    }

    def fake_download(url, *, timeout):
        filename = url.rsplit("/main/", 1)[1].removeprefix("ExcelOutput/")
        if filename in tables:
            return json.dumps(tables[filename]).encode(), "etag"
        if filename in {config, ability, *enemy_update.GLOBAL_MODIFIER_FILES}:
            return b"{}", "etag"
        raise AssertionError(f"未预期下载 {filename}")

    monkeypatch.setattr("hsr_nous.pipeline.build.update.download_with_etag", fake_download)
    monkeypatch.setattr(enemy_update, "_remote_ability_file_index", lambda _timeout: {ability})
    assert enemy_update.run_update(data_dir=str(tmp_path)) == 0
    assert (tmp_path / config).is_file() and (tmp_path / ability).is_file()
    for filename in enemy_update.GLOBAL_MODIFIER_FILES:
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


@pytest.mark.parametrize(("alias", "expected"), [
    ("AbilityTargetAdjoinEntity", 'count_selected("allies", "is_adjacent($it, $event.target)")'),
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


@pytest.mark.parametrize(("alias", "expected"), [
    ("AllLightTeam.RemoveServant", 'count_selected("allies", "not $it.summoner_id")'),
    ("CasterSummonedMinions", 'count_selected("enemies", "$it.summoner_id == $self.actor_id")'),
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
        "effect_type": "consume_energy", "target": "all_allies", "amount": amount,
    }]


def test_modify_sp_rejects_set_value_form():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifySPNew",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        "SetValue": {"IsDynamic": False, "FixedValue": {"Value": 20}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]
    assert any("设值" in item["reason"] for item in out["unsupported"])


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


@pytest.mark.parametrize(("function", "value"), [("Set", 2), ("Add", 1.5)])
def test_modify_team_boost_point_rejects_set_and_fraction(function, value):
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.ModifyTeamBoostPoint", "ModifyFunction": function,
        "ModifyValue": {"IsDynamic": False, "FixedValue": {"Value": value}},
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]


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


def test_remove_behavior_flag_rejects_other_flags():
    skills, sources = _predicate_skill({})
    sources["abilities"]["A"]["OnStart"] = [{
        "$type": "RPG.GameCore.RemoveModifierByBehaviorFlag",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierBehaviorFlags": ["Deathrattle"],
    }]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]


def test_target_count_uses_number_and_alive_only():
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
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("AliveOnly" in item["reason"] for item in rejected["unsupported"])


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


def test_custom_modifier_event_rejects_unknown_type_and_keeps_marker():
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
    assert "未注册 modifier 自定义事件" in reasons


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
        "WaitParallelTimeStamp",
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


def test_alive_predicate_uses_actor_alive_and_rejects_limbo():
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
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("Mask_AliveOrLimbo" in issue["reason"] for issue in rejected["unsupported"])


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
        "not (actor_type_of($it) == 'summon' or summoner_of($it) != '')"

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
    assert not _is_camera_ability("Monster_Skill04_Camera02_Phase")
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


def test_property_dynamic_value_write_then_read_is_explicitly_rejected():
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
    assert not out["ok"]
    assert any("旧事件快照" in item["reason"] for item in out["unsupported"])

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


def test_dynamic_add_twice_and_write_read_rejected():
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
    assert not out["ok"]
    assert any("旧事件快照" in item["reason"] for item in out["unsupported"])

    sources["abilities"]["A"]["OnStart"] = sources["abilities"]["A"]["OnStart"][:3]
    accepted = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert accepted["ok"] and not accepted["unsupported"]
    amounts = [effect["amount"] for hook in accepted["hooks"] for effect in hook["effects"]
               if effect["effect_type"] == "set_dynamic_value"]
    assert amounts == [1, "dynamic_of($self, 'X') + 1", "dynamic_of($self, 'X') + 1"]


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


def test_abort_behavior_flag_prevents_conditional_damage_dedup():
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
    assert not out["ok"]
    assert any(item["node_type"] == "ConditionalDamage" for item in out["unsupported"])


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

    sources["custom_values"] = {"X": 0}
    sources["abilities"]["A"]["OnStart"][0]["Switch"] = _dynamic(
        "AQAR", hashes=[dynamic_value_hash("X")])
    sources["config_ai"] = {
        "$type": "RPG.GameCore.SetDynamicValueByHPRatio", "DynamicKey": {"Value": "X"},
    }
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("可变 CustomValue" in item["reason"] for item in rejected["unsupported"])

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
    rejected = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not rejected["ok"]
    assert any("默认 ResetStance" in item["reason"] for item in rejected["unsupported"])


def test_empty_damage_ability_is_not_full_coverage():
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
    assert not out["ok"] and out["action"] is None
    assert out["unsupported"][0]["node_type"] == "DamageMissing"


def test_compile_enemy_missing_config_and_trigger_are_explicit():
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    missing = AbilityCompiler("fake", skills, {"character_config": None}).compile_enemy()
    assert not missing["ok"]
    assert missing["unsupported"][0]["node_type"] == "CharacterConfig"
    no_trigger = AbilityCompiler(
        "fake", skills, {"character_config": {"SkillList": []}, "abilities": {}, "modifiers": {}},
    ).compile_enemy()
    assert not no_trigger["ok"]
    assert no_trigger["unsupported"][0]["node_type"] == "SkillList"


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
    assert out["ok"] and not out["unsupported"]
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
])
def test_real_stack_property_mappings(enemy_id, trigger, modifier_name, stat, expected):
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills

    out = AbilityCompiler(
        enemy_id, get_enemy_skills(enemy_id), get_enemy_ability_sources(enemy_id),
    ).compile_skill(trigger)
    assert out["ok"] and not out["unsupported"]
    modifier = next(
        effect["modifier"] for hook in out["hooks"] for effect in hook["effects"]
        if effect.get("effect_type") == "apply_modifier"
        and effect["modifier"].get("name") == modifier_name
    )
    assert modifier["stat_effects"][stat] == pytest.approx(expected)


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
    assert on_apply[:2] == [{
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "_CurrentStance",
        "amount": "toughness_of($self.actor_id)",
    }, {
        "effect_type": "set_dynamic_value", "target": "self", "dynamic_key": "_MaxStance",
        "amount": "base_stat_of($self.actor_id, 'max_toughness')",
    }]

    eng = engine_vs_dummy(enemies=[make_dummy("4034013", max_toughness=120)])
    source = eng.state.actors["4034013"]
    source.toughness = 45.0
    for effect in on_apply[:2]:
        eng._hooks._run_hook_effect(source, effect, {})
    runtime = eng._enemy_policy_state["4034013"]["dynamic_values"]
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
    assert not out["ok"]
    assert any(item["node_type"] == "ConditionalDamage" for item in out["unsupported"])


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


def test_before_actor_exit_self_force_kill_is_noop():
    from hsr_nous.adapters.enemy_ability import _Context

    compiler = AbilityCompiler("fake", [], {})
    ctx = _Context(mode="event", skill={"skill_id": "s1"}, event="before_actor_exit")
    compiler._compile_force_kill({
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
    }, ctx, "probe", ())
    assert not ctx.effects and not ctx.unsupported


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
    assert not any(hook["event"] == "after_being_hit" for hook in out["hooks"])


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
        "effect_type": "consume_energy", "target": "all_allies",
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
def test_lesser_sting_deathrattle_keeps_unproven_branch_unsupported():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources, get_enemy_skills
    compiler = AbilityCompiler("8022020", get_enemy_skills("8022020"),
                               get_enemy_ability_sources("8022020"))
    out = compiler.compile_passive("Monster_SW_Minion01_01_Passive01", "802202004")
    assert not out["ok"]
    damage = out["hooks"][0]["effects"][0]
    assert damage["scaling_hp"] == pytest.approx(0.6)
    assert damage["toughness_dmg"] == pytest.approx(30.0)
    unsupported = {item["node_type"] for item in out["unsupported"]}
    assert "RPG.GameCore.PredicateTaskList" in unsupported
    assert all(effect["effect_type"] != "apply_modifier" for effect in out["hooks"][0]["effects"])


@_need_ability
def test_if_lesser_sting_references_resolve():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources
    sources = get_enemy_ability_sources("8022021")
    for name in ("Monster_SW_Minion01_01_IF_Skill02_Phase01",
                 "Monster_SW_Minion01_01_IF_SkillP01"):
        assert name in sources["abilities"]
        assert name not in sources["missing_abilities"]
    assert not sources["ambiguous"]
