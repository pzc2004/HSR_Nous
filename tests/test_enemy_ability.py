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
        if filename in {config, ability}:
            return b"{}", "etag"
        raise AssertionError(f"未预期下载 {filename}")

    monkeypatch.setattr("hsr_nous.pipeline.build.update.download_with_etag", fake_download)
    monkeypatch.setattr(enemy_update, "_remote_ability_file_index", lambda _timeout: {ability})
    assert enemy_update.run_update(data_dir=str(tmp_path)) == 0
    assert (tmp_path / config).is_file() and (tmp_path / ability).is_file()


def test_unknown_task_is_structured_unsupported():
    sources = {
        "character_config": {"SkillList": [{
            "Name": "Skill01", "SkillType": "Skill",
            "TargetInfo": {"TargetType": "Caster"}, "EntryAbility": "A",
        }]},
        "abilities": {"A": {"Name": "A", "OnStart": [{
            "$type": "RPG.GameCore.PredicateTaskList", "SuccessTaskList": [],
        }]}},
        "modifiers": {},
    }
    skills = [{"skill_id": "s1", "trigger_key": "Skill01", "param_list": []}]
    out = AbilityCompiler("fake", skills, sources).compile_skill("Skill01")
    assert not out["ok"]
    assert out["unsupported"][0]["node_type"] == "RPG.GameCore.PredicateTaskList"
    assert "未注册" in out["unsupported"][0]["reason"]


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
def test_pure_direct_skill_uses_ability_compiler(monkeypatch):
    from hsr_nous.adapters import template_generator as generator
    original = generator._enemy_convert_skill

    def legacy_guard(raw, *args, **kwargs):
        if str(raw.get("skill_id")) == "201301003":
            raise AssertionError("完整支持的纯直伤不应回落旧转换器")
        return original(raw, *args, **kwargs)

    monkeypatch.setattr(generator, "_enemy_convert_skill", legacy_guard)
    template = generator.generate_enemy_template("2013010")
    action = next(a for a in template["actions"] if a["action_id"] == "201301003")
    assert action["name"] == "Restraint"
    assert action["scaling"] == [{"atk": 3.0}]
    assert action["toughness_dmg"] == 10 and action["energy_grant"] == 10.0


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
def test_if_lesser_sting_missing_references_are_explicit():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ability_sources
    sources = get_enemy_ability_sources("8022021")
    assert "Monster_SW_Minion01_01_IF_Skill02_Phase01" in sources["missing_abilities"]
    assert "Monster_SW_Minion01_01_IF_SkillP01" in sources["missing_abilities"]
