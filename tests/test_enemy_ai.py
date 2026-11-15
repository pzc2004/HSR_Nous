"""ConfigAI 行为树解释器：动态值、阶段分支与静态收编闸."""
from __future__ import annotations

from hsr_nous.sim.compile.compiled import CompiledEnemyPolicy
from hsr_nous.sim.enemy_ai import ConfigAIInterpreter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.config_ai import (
    dynamic_value_hash, resolve_config_custom_values, unsupported_config_nodes)
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _engine(config, skill_ids, allies=None, enemy_id="enemy", stage_id="t"):
    heroes = allies or [Actor(actor_id="hero", name="测试员", stats=StatBlock(hp=1e9, spd=50))]
    enemy = Actor(actor_id=enemy_id, name="假人", actor_type="monster",
                  stats=StatBlock(hp=1e9, atk=0, spd=100))
    actions = [Action(action_id=action_id, name=action_id, action_type="skill",
                      target_type="single", damage_type="physical",
                      scaling=[{"atk": 0.0}], energy_gain=0)
               for action_id in set(skill_ids.values())]
    policy = CompiledEnemyPolicy(config=config, skill_ids=skill_ids)
    encounter = Encounter(
        encounter_id=stage_id, name=stage_id, actors=[*heroes, enemy],
        termination=TerminationConfig(mode="fixed_av", max_action_value=1000),
    )
    engine = CombatEngine(
        encounter, actions_by_actor={enemy_id: actions}, enemy_policies={enemy_id: policy},
        initial_energy_ratio=0.0, mode=MODE_EXPECTED,
    )
    engine.setup()
    return engine


def _axis(skill, flag):
    return {
        "$type": "RPG.GameCore.CheckPredicateAxis",
        "Predicate": {
            "$type": "RPG.GameCore.ByCompareDynamicValue",
            "DynamicKey": {"Value": "AIFlag"},
            "ContextScope": "TargetEntity",
            "CompareType": "Equal",
            "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": flag}},
        },
        "SuccessScore": {"Value": 0.5},
    }


def _decision(skill, flag, next_flag):
    return {
        "$type": "RPG.GameCore.AIDecisionConfig",
        "DecisionName": f"use_{skill}",
        "RootTask": {
            "$type": "RPG.GameCore.SequenceConfig",
            "TaskList": [
                {"$type": "RPG.GameCore.DefineDynamicValue",
                 "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
                 "DynamicKey": {"Value": "AIFlag"},
                 "ResetValue": {"IsDynamic": False, "FixedValue": {"Value": next_flag}},
                 "ContextScope": "TargetEntity"},
                {"$type": "RPG.GameCore.UseSkill", "SkillName": skill},
            ],
        },
        "ScoreEvaluatorType": "DefaultDSE",
        "Weight": {"Value": 0.5},
        "ConsiderAxisList": [_axis(skill, flag)],
    }


def test_dynamic_decision_flow_updates_aiflag():
    config = {"DecisionList": [_decision("Skill01", 1, 2), _decision("Skill02", 2, 3)]}
    engine = _engine(config, {"Skill01": "a", "Skill02": "b"})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert [interpreter.choose_action().action_id for _ in range(2)] == ["a", "b"]
    assert interpreter.choose_action() is None
    assert engine._enemy_policy_state["enemy"]["dynamic_values"]["AIFlag"] == 3


def test_set_and_add_dynamic_value_read_upstream_fields():
    config = {"DecisionList": [{
        "$type": "RPG.GameCore.AIDecisionConfig",
        "RootTask": {"$type": "RPG.GameCore.SequenceConfig", "TaskList": [
            {"$type": "RPG.GameCore.SetDynamicValue",
             "DynamicKey": {"Value": "AIFlag"},
             "Value": {"IsDynamic": False, "FixedValue": {"Value": 2}}},
            {"$type": "RPG.GameCore.SetDynamicValueByAddValue",
             "Key": {"Value": "AIFlag"},
             "AddValue": {"IsDynamic": False, "FixedValue": {"Value": 3}}},
            {"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill01"},
        ]},
    }]}
    engine = _engine(config, {"Skill01": "a"})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter.choose_action().action_id == "a"
    assert engine._enemy_policy_state["enemy"]["dynamic_values"]["AIFlag"] == 5


def test_random_config_expected_uses_first_branch():
    config = {"DecisionList": [{
        "$type": "RPG.GameCore.AIDecisionConfig",
        "RootTask": {"$type": "RPG.GameCore.SequenceConfig", "TaskList": [{
            "$type": "RPG.GameCore.RandomConfig",
            "OddsList": [
                {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
                {"IsDynamic": False, "FixedValue": {"Value": 0.5}},
            ],
            "TaskList": [
                [{"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill01"}],
                [{"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill02"}],
            ],
        }]},
    }]}
    assert not unsupported_config_nodes(config, {"Skill01", "Skill02"})
    engine = _engine(config, {"Skill01": "a", "Skill02": "b"})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter.choose_action().action_id == "a"


def test_remove_modifier_task_only_targets_caster():
    decision = _decision("Skill01", 1, 2)
    decision["RootTask"]["TaskList"].insert(1, {
        "$type": "RPG.GameCore.RemoveModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "OneMore"},
    })
    config = {"DecisionList": [decision]}
    assert not unsupported_config_nodes(config, {"Skill01"})
    engine = _engine(config, {"Skill01": "a"})
    enemy = engine.state.actors["enemy"]
    enemy.modifiers["OneMore"] = Modifier(
        modifier_id="OneMore", name="OneMore", modifier_type="buff", duration=1)
    interpreter = ConfigAIInterpreter(engine, enemy)
    assert interpreter.choose_action().action_id == "a"
    assert "OneMore" not in enemy.modifiers
    bad = unsupported_config_nodes({
        "DecisionList": [{"RootTask": {"TaskList": [{
            "$type": "RPG.GameCore.RemoveModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            "ModifierName": {"Value": "OneMore"},
        }]}}]
    }, {"Skill01"})
    assert "target:AllEnemy" in bad


def test_add_modifier_task_only_targets_caster():
    decision = _decision("Skill01", 1, 2)
    decision["RootTask"]["TaskList"].insert(1, {
        "$type": "RPG.GameCore.AddModifier",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "ModifierName": {"Value": "OneMore"},
    })
    config = {"DecisionList": [decision]}
    assert not unsupported_config_nodes(config, {"Skill01"})
    engine = _engine(config, {"Skill01": "a"})
    enemy = engine.state.actors["enemy"]
    interpreter = ConfigAIInterpreter(engine, enemy)
    assert interpreter.choose_action().action_id == "a"
    assert enemy.modifiers["OneMore"].modifier_type == "buff"


def test_inverse_predicate_matches_static_initial_gate():
    from hsr_nous.sim_schema.config_ai import has_initial_decision

    decision = _decision("Skill01", 2, 3)
    decision["ConsiderAxisList"][0]["Predicate"]["Inverse"] = True
    config = {"DecisionList": [decision]}
    assert has_initial_decision(config, {"Skill01"})
    engine = _engine(config, {"Skill01": "a"})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter.choose_action().action_id == "a"


def test_by_random_chance_reads_chance_field_with_comparevalue_fallback():
    # 真实语料 109 例全用 Chance 字段（旧代码只读 CompareValue→None 潜伏偏差，
    # 与编译器 _compile_probability_guards 同口径：Chance 优先、CompareValue 回落）
    def _fixed(value):
        return {"IsDynamic": False, "FixedValue": {"Value": value}}

    def _random_axis(node):
        return {"$type": "RPG.GameCore.CheckPredicateAxis",
                "Predicate": node, "SuccessScore": {"Value": 0.5}}

    def _choose(node):
        decision = _decision("Skill01", 2, 3)
        decision["ConsiderAxisList"] = [_random_axis(node)]
        engine = _engine({"DecisionList": [decision]}, {"Skill01": "a"})
        interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
        return interpreter.choose_action()

    assert _choose({"$type": "RPG.GameCore.ByRandomChance",
                    "Chance": _fixed(1.0)}).action_id == "a"
    assert _choose({"$type": "RPG.GameCore.ByRandomChance",
                    "CompareValue": _fixed(1.0)}).action_id == "a"
    # Chance 优先于 CompareValue（两字段同在时）
    assert _choose({"$type": "RPG.GameCore.ByRandomChance",
                    "Chance": _fixed(1.0), "CompareValue": _fixed(0.0)}).action_id == "a"
    # Chance=0 期望模式永不通过（门控失败→选不出）
    assert _choose({"$type": "RPG.GameCore.ByRandomChance",
                    "Chance": _fixed(0.0)}) is None


def test_config_ai_initial_values_are_scoped_by_ai_name():
    from hsr_nous.sim_schema.config_ai import has_initial_decision

    for ai_name, key, expected in (
            ("Monster_W1_Bronya_00_RL", "Bronya_AICounter_Act1", True),
            ("Monster_W1_Bronya_00_RL", "Other_AICounter_Act1", False),
            ("Monster_XP_Elite01_00", "Phase_Flag", True),
            ("Monster_XP_Elite01_00", "Bronya_AICounter_Act1", False)):
        decision = _decision("Skill01", 1, 2)
        decision["ConsiderAxisList"][0]["Predicate"]["DynamicKey"]["Value"] = key
        config = {"AIName": ai_name, "DecisionList": [decision]}
        assert has_initial_decision(config, {"Skill01"}) is expected
        engine = _engine(config, {"Skill01": "a"})
        interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
        assert (interpreter.choose_action() is not None) is expected


def test_cocolia_complete_initial_custom_value_executes_decision():
    """RL ConfigCharacter 的 DecisionFlag=1 同时通过静态闸并驱动真实行为树."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    for enemy_id, expected_action in (("1004011", "100401104"), ("1004012", "100401204")):
        policy = generate_enemy_template(enemy_id)["policy"]
        engine = _engine(policy["config"], policy["skill_ids"], enemy_id=enemy_id)
        interpreter = ConfigAIInterpreter(engine, engine.state.actors[enemy_id])
        assert interpreter.choose_action().action_id == expected_action
        assert engine._enemy_policy_state[enemy_id]["dynamic_values"]["DecisionFlag"] == 2


def test_stepper_group_requires_current_phase():
    decision = _decision("Skill01", 1, 2)
    decision["ConsiderAxisList"] = [{
        "$type": "RPG.GameCore.CheckPredicateAxis",
        "Predicate": {"$type": "RPG.GameCore.ByCompareMonsterPhase",
                      "CompareType": "Equal",
                      "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}}},
        "SuccessScore": {"Value": 1},
    }]
    config = {"DecisionList": [{
        "$type": "RPG.GameCore.AIStepperDecisionGroupConfig",
        "DecisionGroupName": "phase1",
        "DecisionList": [decision],
        "ScoreEvaluatorType": "DefaultDSE",
    }]}
    engine = _engine(config, {"Skill01": "a"})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter.choose_action().action_id == "a"
    engine._enemy_policy_state["enemy"]["current_phase"] = 2
    assert interpreter.choose_action() is None


def test_static_gate_rejects_unknown_nodes_and_missing_skills():
    config = {"DecisionList": [{
        "$type": "RPG.GameCore.AIDecisionConfig",
        "RootTask": {"$type": "RPG.GameCore.SequenceConfig", "TaskList": [
            {"$type": "RPG.GameCore.ByCompareSkillUsageLimit"},
            {"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill02"},
        ]},
    }]}
    bad = unsupported_config_nodes(config, {"Skill01"})
    assert "usage:ActionDelay" in bad
    assert "skill:Skill02" in bad


def test_skill_usage_limit_uses_fixed_delay_on_existing_cooldown_axis():
    predicate = {
        "$type": "RPG.GameCore.ByCompareSkillUsageLimit",
        "IDFromTriggerKey": "Skill02",
        "ActionDelay": {"IsDynamic": False, "FixedValue": {"Value": 12}},
    }
    config = {"DecisionList": [{
        "$type": "RPG.GameCore.AIDecisionConfig",
        "RootTask": {"$type": "RPG.GameCore.SequenceConfig", "TaskList": [{
            "$type": "RPG.GameCore.PredicateTaskList", "Predicate": predicate,
            "SuccessTaskList": [{"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill02"}],
            "FailedTaskList": [{"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill01"}],
        }]},
    }]}
    assert not unsupported_config_nodes(config, {"Skill01", "Skill02"})
    engine = _engine(config, {"Skill01": "a", "Skill02": "b"})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    seen = [interpreter.choose_action().action_id]
    engine._tick_enemy_policy_cooldown("enemy")
    assert engine._enemy_policy_state["enemy"]["cooldown_left"]["b"] == 11
    for _ in range(11):
        seen.append(interpreter.choose_action().action_id)
        engine._tick_enemy_policy_cooldown("enemy")
    seen.append(interpreter.choose_action().action_id)
    assert seen == ["b", *(["a"] * 11), "b"]

    predicate["ActionDelay"] = {"IsDynamic": True, "PostfixExpr": {"DynamicHashes": [1]}}
    assert "usage:ActionDelay" in unsupported_config_nodes(config, {"Skill01", "Skill02"})


def test_harpy_local_legend_global_delay_uses_stage_evidence():
    """4022011 的 _GlobalDelay：426007 为 6，其余关卡为 12."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.enemy_ai import config_ai_dynamic_value

    template = generate_enemy_template("4022011")
    assert [a["action_id"] for a in template["actions"]] == ["402201101", "402201102"]
    policy = template["policy"]
    assert not unsupported_config_nodes(
        policy["config"], set(policy["skill_ids"]), monster_id="4022011")
    for stage_id, expected in (("t", 12.0), ("426007", 6.0)):
        engine = _engine(policy["config"], policy["skill_ids"],
                         enemy_id="4022011", stage_id=stage_id)
        interpreter = ConfigAIInterpreter(engine, engine.state.actors["4022011"])
        assert config_ai_dynamic_value(engine, "4022011", "_GlobalDelay") == expected
        assert interpreter.choose_action().action_id == "402201102"
        assert interpreter.runtime["cooldown_left"]["402201102"] == expected


def test_switch_case_fixed_value_and_dynamic_gate():
    def make_config(value):
        return {"DecisionList": [{
            "$type": "RPG.GameCore.AIDecisionConfig",
            "RootTask": {"$type": "RPG.GameCore.SequenceConfig", "TaskList": [{
                "$type": "RPG.GameCore.SwitchCaseByDynamicValue",
                "Switch": {"IsDynamic": False, "FixedValue": {"Value": value}},
                "CaseTaskList": [
                    {"Case": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                     "TaskList": [{"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill01"}]},
                    {"Case": {"IsDynamic": False, "FixedValue": {"Value": 2}},
                     "TaskList": [{"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill02"}]},
                ],
                "DefaultTaskList": [{"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill03"}],
            }]},
        }]}

    skill_ids = {"Skill01": "a", "Skill02": "b", "Skill03": "c"}
    for value, expected in ((2, "b"), (0, "c")):
        config = make_config(value)
        assert not unsupported_config_nodes(config, set(skill_ids))
        engine = _engine(config, skill_ids)
        interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
        assert interpreter.choose_action().action_id == expected
    config = make_config(1)
    config["DecisionList"][0]["RootTask"]["TaskList"][0]["Switch"]["IsDynamic"] = True
    assert "switch:DynamicValue" in unsupported_config_nodes(config, set(skill_ids))


def test_mascot_custom_values_resolve_real_switches():
    from hsr_nous.pipeline.enemies.loader import get_enemy_ai, get_enemy_ai_config, get_enemy_detail

    assert [dynamic_value_hash(f"AISequence_{index}") for index in (1, 2, 3)] == [
        -1346384835, 1382498520, -183585421]
    detail = get_enemy_detail("4012050")
    custom_values = {
        str(item["BFLIFKBEOPJ"]): item.get("MNDFOPKBHKP", 0)
        for item in detail["CustomValues"]
    }
    config = resolve_config_custom_values(
        get_enemy_ai_config(get_enemy_ai("4012050")["ai_path"]), custom_values)
    switches = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("$type") == "RPG.GameCore.SwitchCaseByDynamicValue":
                switches.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(config)
    assert [switch["Switch"]["FixedValue"]["Value"] for switch in switches] == [1, 2, 3, 2, 2]
    skill_ids = {"Skill01": "a", "Skill02": "b", "Skill03": "c"}
    assert not unsupported_config_nodes(config, set(skill_ids))
    engine = _engine(config, skill_ids)
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    first_switch = config["DecisionList"][1]["DecisionList"][0]["RootTask"]["TaskList"][1]
    assert interpreter._run_tasks([first_switch]).action_id == "a"
    assert interpreter.runtime["dynamic_values"]["Sequence_i"] == 2


def test_custom_value_bool_resolves_real_tag_and_evaluates():
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_ai, get_enemy_ai_config, list_custom_value_tags)

    raw_config = get_enemy_ai_config(get_enemy_ai("4052020")["ai_path"])
    assert "custom_bool:Key" in unsupported_config_nodes(raw_config, {"Skill01", "Skill02"})
    config = resolve_config_custom_values(raw_config, {}, list_custom_value_tags())
    predicates = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("$type") == "RPG.GameCore.ByCheckCustomValueBool":
                predicates.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(config)
    assert dynamic_value_hash("SW_Minion01_03") == 1223239280
    assert len(predicates) == 1 and predicates[0]["Key"] == {"Value": "SW_Minion01_03"}
    assert not unsupported_config_nodes(config, {"Skill01", "Skill02"})
    engine = _engine(config, {"Skill01": "a", "Skill02": "b"})
    enemy = engine.state.actors["enemy"]
    interpreter = ConfigAIInterpreter(engine, enemy)
    enemy.actor.groups = ["SW_Minion01_03"]
    assert interpreter._predicate(predicates[0], enemy)
    enemy.actor.groups = []
    assert not interpreter._predicate(predicates[0], enemy)


def _selector_config(modifier_name):
    decision = _decision("Skill01", 1, 2)
    decision["RootTask"]["TaskList"].insert(0, {
        "$type": "RPG.GameCore.SelectAISkillTarget", "SkillName": "Skill01",
        "Selector": {"$type": "RPG.GameCore.AIModifierNameSelector",
                     "ModifierName": modifier_name},
    })
    return {"DecisionList": [decision]}


def test_modifier_selector_prefers_shocked_target():
    h1 = Actor(actor_id="h1", name="高嘲讽", stats=StatBlock(hp=1e9, spd=50, taunt=500))
    h2 = Actor(actor_id="h2", name="触电者", stats=StatBlock(hp=1e9, spd=50, taunt=100))
    engine = _engine(_selector_config("MCommon_DOT_Electric"), {"Skill01": "a"}, [h1, h2])
    engine.state.actors["h2"].modifiers["TEST_SHOCK"] = Modifier(
        modifier_id="TEST_SHOCK", name="Shock", modifier_type="dot",
        dot_element="thunder", dot_ratio=1.0, dot_source_atk=0.0,
    )
    engine._enemy_turn(engine.state.actors["enemy"])
    assert engine._last_target_id == "h2"


def test_modifier_selector_and_predicate_recognize_frozen_target():
    h1 = Actor(actor_id="h1", name="高嘲讽", stats=StatBlock(hp=1e9, spd=50, taunt=500))
    h2 = Actor(actor_id="h2", name="冻结者", stats=StatBlock(hp=1e9, spd=50, taunt=100))
    engine = _engine(_selector_config("MCommon_CTRL_Frozen"), {"Skill01": "a"}, [h1, h2])
    frozen = engine.state.actors["h2"]
    frozen.modifiers["TEST_FREEZE"] = Modifier(
        modifier_id="TEST_FREEZE", name="Freeze", modifier_type="debuff",
        debuff_kind="control", control_kind="freeze", prevent_action=True,
    )
    engine._enemy_turn(engine.state.actors["enemy"])
    assert engine._last_target_id == "h2"
    predicate = {"$type": "RPG.GameCore.ByIsContainModifier",
                 "ModifierName": "MCommon_CTRL_Frozen"}
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter._predicate(predicate, frozen)
    assert not interpreter._predicate(predicate, engine.state.actors["h1"])


def test_monster_id_selector_and_inverse():
    engine = _engine({}, {})
    enemy = engine.state.actors["enemy"]
    enemy.actor.actor_id = "1002020"
    engine._enemy_policies["1002020"] = engine._enemy_policies["enemy"]
    engine._enemy_policy_state["1002020"] = engine._enemy_policy_state["enemy"]
    interpreter = ConfigAIInterpreter(engine, enemy)
    selected = interpreter._select_target({
        "$type": "RPG.GameCore.AIMonsterIDSelector", "MonsterIDList": [1002020],
    })
    assert selected is enemy
    inverse = interpreter._select_target({
        "$type": "RPG.GameCore.AIMonsterIDSelector", "MonsterIDList": [1002020],
        "InverseResultFlag": True,
    })
    assert inverse.actor.actor_id == "hero"
    assert not unsupported_config_nodes({
        "$type": "RPG.GameCore.SelectAISkillTarget",
        "Selector": {"$type": "RPG.GameCore.AIMonsterIDSelector", "MonsterIDList": [1002020]},
    }, {"Skill01"})


def test_compose_by_and_intersects_task_and_modifier_selectors():
    decision = _decision("Skill01", 1, 2)
    decision["RootTask"]["TaskList"].insert(0, {
        "$type": "RPG.GameCore.SelectAISkillTarget", "SkillName": "Skill01",
        "Selector": {
            "$type": "RPG.GameCore.AIComposeSelector",
            "SelectorList": [
                {"$type": "RPG.GameCore.AITaskTargetTypeSelector",
                 "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"}},
                {"$type": "RPG.GameCore.AIModifierNameSelector", "ModifierName": "MARK"},
            ],
        },
    })
    config = {"DecisionList": [decision]}
    assert not unsupported_config_nodes(config, {"Skill01"})
    h1 = Actor(actor_id="h1", name="高嘲讽无标记", stats=StatBlock(hp=1e9, spd=50, taunt=500))
    h2 = Actor(actor_id="h2", name="低嘲讽有标记", stats=StatBlock(hp=1e9, spd=50, taunt=100))
    engine = _engine(config, {"Skill01": "a"}, [h1, h2])
    engine.state.actors["h2"].modifiers["MARK"] = Modifier(
        modifier_id="MARK", name="MARK", modifier_type="debuff")
    engine._enemy_turn(engine.state.actors["enemy"])
    assert engine._last_target_id == "h2"


def test_behavior_flag_predicate_and_selector():
    h1 = Actor(actor_id="h1", name="普通", stats=StatBlock(hp=1e9, spd=50))
    h2 = Actor(actor_id="h2", name="击破", stats=StatBlock(hp=1e9, spd=50))
    h3 = Actor(actor_id="h3", name="控制", stats=StatBlock(hp=1e9, spd=50))
    engine = _engine({}, {}, [h1, h2, h3])
    engine.state.actors["h2"].broken = True
    engine.state.actors["h3"].modifiers["CTRL"] = Modifier(
        modifier_id="CTRL", name="Freeze", modifier_type="debuff",
        debuff_kind="control", control_kind="freeze", prevent_action=True)
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter._predicate({"$type": "RPG.GameCore.ByContainBehaviorFlag", "Flag": "Break"},
                                  engine.state.actors["h2"])
    assert interpreter._predicate({"$type": "RPG.GameCore.ByContainBehaviorFlag", "Flag": "STAT_CTRL"},
                                  engine.state.actors["h3"])
    assert interpreter._predicate({"$type": "RPG.GameCore.ByContainBehaviorFlag", "Flag": "DisableAction"},
                                  engine.state.actors["h3"])
    chosen = interpreter._select_target({
        "$type": "RPG.GameCore.AIBehaviorFlagSelector",
        "BehaviorFlag": "Break", "InverseResultFlag": True,
    })
    assert chosen.actor.actor_id == "h1"


def test_target_sequence_filters_candidates():
    h1 = Actor(actor_id="h1", name="普通", stats=StatBlock(hp=1e9, spd=50))
    h2 = Actor(actor_id="h2", name="触电", stats=StatBlock(hp=1e9, spd=50))
    engine = _engine({}, {}, [h1, h2])
    engine.state.actors["h2"].modifiers["SHOCK"] = Modifier(
        modifier_id="SHOCK", name="Shock", modifier_type="dot",
        dot_element="thunder", dot_ratio=1.0, dot_source_atk=0.0)
    sequence = {
        "$type": "RPG.GameCore.TargetSequence",
        "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            {"$type": "RPG.GameCore.TargetFilter",
             "Predicate": {"$type": "RPG.GameCore.ByIsContainModifier",
                           "ModifierName": "SHOCK"}},
        ],
    }
    assert not unsupported_config_nodes(sequence, set())
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter._team_count(sequence) == 1
    assert interpreter._select_target(sequence).actor.actor_id == "h2"


def test_target_sort_and_index():
    h1 = Actor(actor_id="h1", name="一", stats=StatBlock(hp=1e9, spd=50))
    h2 = Actor(actor_id="h2", name="二", stats=StatBlock(hp=1e9, spd=50))
    h3 = Actor(actor_id="h3", name="三", stats=StatBlock(hp=1e9, spd=50))
    engine = _engine({}, {}, [h1, h2, h3])
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    sequence = {
        "$type": "RPG.GameCore.TargetSequence",
        "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            {"$type": "RPG.GameCore.TargetSortByFormation", "HighestFirst": True},
            {"$type": "RPG.GameCore.TargetIndex", "IndexType": "IndexStrict",
             "IndexValue": {"IsDynamic": False, "FixedValue": {"Value": 1}}},
        ],
    }
    assert not unsupported_config_nodes(sequence, set())
    assert interpreter._select_target(sequence).actor.actor_id == "h2"
    first = {
        "$type": "RPG.GameCore.TargetSequence",
        "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemy"},
            {"$type": "RPG.GameCore.TargetIndex", "IndexType": "IndexStrict",
             "IndexValue": {"IsDynamic": False, "FixedValue": {"Value": 0}}},
        ],
    }
    assert interpreter._select_target(first).actor.actor_id == "h1"


def test_compare_target_uses_entity_identity_and_inverse():
    engine = _engine({}, {})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    node = {
        "$type": "RPG.GameCore.ByCompareTarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
        "CompareType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "Inverse": True,
    }
    assert interpreter._predicate(node, engine.state.actors["hero"])
    assert not interpreter._predicate(node, engine.state.actors["enemy"])


def test_stat_dot_and_compare_bp():
    engine = _engine({}, {})
    engine.state.actors["hero"].modifiers["SHOCK"] = Modifier(
        modifier_id="SHOCK", name="Shock", modifier_type="dot",
        dot_element="thunder", dot_ratio=1.0, dot_source_atk=0.0)
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter._predicate(
        {"$type": "RPG.GameCore.ByContainBehaviorFlag", "Flag": "STAT_DOT"},
        engine.state.actors["hero"])
    assert not interpreter._predicate(
        {"$type": "RPG.GameCore.ByContainBehaviorFlag", "Flag": "STAT_DOT"},
        engine.state.actors["enemy"])
    engine.state.skill_points = 2
    assert interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareBP", "CompareType": "LessEqual",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    engine.state.skill_points = 3
    assert not interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareBP", "CompareType": "LessEqual",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })


def test_property_selector_hp_ratio_and_value():
    h1 = Actor(actor_id="h1", name="高比例", stats=StatBlock(hp=100, spd=50))
    h2 = Actor(actor_id="h2", name="低比例", stats=StatBlock(hp=100, spd=50))
    h3 = Actor(actor_id="h3", name="中比例", stats=StatBlock(hp=100, spd=50))
    engine = _engine({}, {}, [h1, h2, h3])
    engine.state.actors["h1"].current_hp = 90
    engine.state.actors["h2"].current_hp = 20
    engine.state.actors["h3"].current_hp = 50
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter._select_target({
        "$type": "RPG.GameCore.AIPropertySelector",
        "PropertyStrategy": "MaxRatio", "Property": "CurrentHP",
    }).actor.actor_id == "h1"
    assert interpreter._select_target({
        "$type": "RPG.GameCore.AIPropertySelector",
        "PropertyStrategy": "MinRatio", "Property": "CurrentHP",
    }).actor.actor_id == "h2"
    assert interpreter._select_target({
        "$type": "RPG.GameCore.AIPropertySelector",
        "PropertyStrategy": "Min", "Property": "CurrentHP",
    }).actor.actor_id == "h2"


def test_modifier_selector_without_marker_falls_back_to_default_target():
    h1 = Actor(actor_id="h1", name="高嘲讽", stats=StatBlock(hp=1e9, spd=50, taunt=500))
    h2 = Actor(actor_id="h2", name="低嘲讽", stats=StatBlock(hp=1e9, spd=50, taunt=100))
    engine = _engine(
        _selector_config("MMonster_AML_Minion03_00_Target"), {"Skill01": "a"}, [h1, h2])
    engine._enemy_turn(engine.state.actors["enemy"])
    assert engine._last_target_id == "h1"


def test_baryon_config_ai_uses_skill_and_default_target():
    from hsr_nous.sim.compile import compile_encounter
    h1 = Actor(actor_id="h1", name="高嘲讽", stats=StatBlock(hp=1e9, spd=50, taunt=500))
    h2 = Actor(actor_id="h2", name="低嘲讽", stats=StatBlock(hp=1e9, spd=50, taunt=100))
    build = {"build": {
        "team": [{
            "actor_id": h.actor_id, "name": h.name, "inline": True,
            "base_stats": {"hp": 1e9, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100, "taunt": h.stats.taunt},
            "actions": [{"action_id": f"{h.actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        } for h in (h1, h2)],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {"enemies": [{"enemy_template": "8011010", "level": 80}],
                       "termination": {"mode": "fixed_av", "max_action_value": 1000}}}
    compiled = compile_encounter(build, stage, template_roots=["data/sim_templates"])
    assert compiled.stage.enemy_policies["8011010"].config
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "8011010":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    for _ in range(10):
        engine.step()
        if seen:
            break
    assert seen == ["801101001"]
    assert engine._last_target_id == "h1"


def test_config_only_ai_without_sequence_executes(tmp_path):
    """Silvermane Soldier：AISkillSequence 为空，但可执行 ConfigAI 独立驱动行动."""
    import yaml
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.compile import compile_encounter

    template = generate_enemy_template("1002041")
    assert template["policy"]["sequence"] == []
    assert template["policy"]["config"]["AIName"] == "Monster_W1_CWSoldier_02"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1002041.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e9, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {"enemies": [{"enemy_template": "1002041", "level": 80}],
                       "termination": {"mode": "fixed_av", "max_action_value": 1000}}}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    assert compiled.stage.enemy_policies["1002041"].sequence == ()
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1002041":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(10):
        engine.step()
        if seen:
            break
    assert seen == ["100204101"]


def test_monster_id_alive_count_and_modifier_value_predicates():
    engine = _engine({}, {})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    interpreter.actor_id = "3012030__stage"
    assert interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareMonsterID",
        "TargetMonsterID": {"IsDynamic": False, "FixedValue": {"Value": 3012030}},
    })
    assert not interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareMonsterID",
        "TargetMonsterID": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareAliveEnemyNumber",
        "CompareType": "GreaterEqual",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert not interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareAliveEnemyNumber",
        "CompareType": "Greater",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    engine.state.actors["enemy"].modifiers["OneMore"] = Modifier(
        modifier_id="OneMore", name="OneMore", modifier_type="buff", duration=2)
    assert interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareModifierValue",
        "ModifierName": "OneMore", "ValueType": "LifeTime",
        "CompareType": "GreaterEqual",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })
    assert not interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareModifierValue",
        "ModifierName": "OneMore", "ValueType": "LifeTime",
        "CompareType": "Greater",
        "CompareValue": {"IsDynamic": False, "FixedValue": {"Value": 2}},
    })


def test_set_dynamic_value_by_copying_only_from_self():
    engine = _engine({}, {})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    interpreter._set_dynamic("AIFlag", 7)
    task = {
        "$type": "RPG.GameCore.SetDynamicValueByCopying",
        "FromTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Caster"},
        "FromDynamicKey": {"Value": "AIFlag"},
        "ToDynamicKey": {"Value": "Copied"},
    }
    assert interpreter._run_tasks([task]) is None
    assert engine._enemy_policy_state["enemy"]["dynamic_values"]["Copied"] == 7
    assert not unsupported_config_nodes(task, set())
    task["FromTargetType"]["Alias"] = "Other"
    assert "target:Other" in unsupported_config_nodes(task, set())


def test_team_count_predicates_and_dynamic_write():
    engine = _engine({}, {})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareCharacterNumber",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "CompareType": "GreaterEqual",
        "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert not interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareCharacterNumber",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        "CompareType": "Greater",
        "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareTargetCount",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
        "CompareType": "LessEqual",
        "Number": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    assert not interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareTargetCount",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
        "CompareType": "Less",
        "Number": {"IsDynamic": False, "FixedValue": {"Value": 1}},
    })
    interpreter._run_tasks([{
        "$type": "RPG.GameCore.SetDynamicValueByCharacterCount",
        "DynamicKey": "DarkTeamCount",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllDarkTeam"},
        "AliveOnly": True,
    }])
    assert engine._enemy_policy_state["enemy"]["dynamic_values"]["DarkTeamCount"] == 1
    assert "target:Other" in unsupported_config_nodes({
        "$type": "RPG.GameCore.SetDynamicValueByCharacterCount",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Other"},
    }, set())


def test_caster_summoned_minions_count_and_static_gate():
    from hsr_nous.sim.state import ActorState
    from hsr_nous.sim_schema.config_ai import has_initial_decision

    engine = _engine({}, {})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    alias = "CasterSummonedMinions"
    predicate = {
        "$type": "RPG.GameCore.ByCompareTargetCount",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "CompareType": "Greater", "Number": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }
    config = {"DecisionList": [{
        "$type": "RPG.GameCore.AIDecisionConfig",
        "RootTask": {"$type": "RPG.GameCore.SequenceConfig", "TaskList": [
            {"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill01"},
        ]},
        "ConsiderAxisList": [{
            "$type": "RPG.GameCore.CheckPredicateAxis",
            "Predicate": predicate, "SuccessScore": {"Value": 1},
        }],
    }]}
    assert interpreter._team_count(alias) == 0
    assert not unsupported_config_nodes(config, {"Skill01"})
    assert not has_initial_decision(config, {"Skill01"})

    for actor_id, owner_id in (("minion_a", "enemy"), ("minion_b", "enemy"),
                               ("minion_other", "other")):
        actor = Actor(actor_id=actor_id, name=actor_id, actor_type="monster",
                      stats=StatBlock(hp=100, spd=10), summoner_id=owner_id)
        engine.state.actors[actor_id] = ActorState(actor=actor, current_hp=100)
    assert interpreter._team_count(alias) == 2
    assert interpreter._predicate(predicate)
    task = {
        "$type": "RPG.GameCore.SetDynamicValueByCharacterCount",
        "DynamicKey": "MinionCount",
        "ReadTargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
    }
    assert not unsupported_config_nodes(task, set())
    interpreter._run_tasks([task])
    assert engine._enemy_policy_state["enemy"]["dynamic_values"]["MinionCount"] == 2


def test_light_team_and_ignore_servant_aliases():
    from hsr_nous.sim.state import ActorState

    engine = _engine({}, {})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    for actor_id, actor_type, owner_id in (("enemy_pet", "monster", "enemy"),
                                           ("hero_pet", "memosprite", "hero")):
        actor = Actor(actor_id=actor_id, name=actor_id, actor_type=actor_type,
                      stats=StatBlock(hp=100, spd=10), summoner_id=owner_id)
        engine.state.actors[actor_id] = ActorState(actor=actor, current_hp=100)

    assert interpreter._team_count("AllLightTeam") == 2
    assert interpreter._team_count("AllLightTeam.RemoveServant") == 1
    assert [st.actor.actor_id for st in interpreter._team_members("AllLightTeam")] == [
        "hero", "hero_pet"]
    assert [st.actor.actor_id for st in interpreter._team_members("AllLightTeam.RemoveServant")] == [
        "hero"]
    assert [st.actor.actor_id for st in interpreter._team_members("AllDarkTeam")] == [
        "enemy", "enemy_pet"]
    assert [st.actor.actor_id for st in interpreter._team_members("AllDarkTeam - Caster")] == [
        "enemy_pet"]
    for alias in ("AllLightTeam", "AllLightTeam.RemoveServant", "AllDarkTeam - Caster"):
        assert not unsupported_config_nodes({
            "$type": "RPG.GameCore.ByCompareCharacterNumber",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
            "CompareType": "Greater",
            "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 0}},
        }, set())
    selector = {
        "$type": "RPG.GameCore.AITaskTargetTypeSelector",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllEnemyIgnoreServant"},
    }
    assert not unsupported_config_nodes(selector, set())
    assert [st.actor.actor_id for st in interpreter._select_target_candidates(selector)] == ["hero"]
    assert interpreter._select_target(selector).actor.actor_id == "hero"


def test_svarog_unselectable_aliases_use_custom_tags():
    from hsr_nous.sim.state import ActorState

    engine = _engine({}, {})
    enemy = engine.state.actors["enemy"]
    enemy.actor.groups = ["W1_SvarogPart"]
    rl_actor = Actor(actor_id="rl", name="rl", actor_type="monster",
                     stats=StatBlock(hp=100, spd=10))
    rl_actor.groups = ["W1_SvarogPart", "RL"]
    rl = ActorState(actor=rl_actor, current_hp=100)
    engine.state.actors["rl"] = rl
    interpreter = ConfigAIInterpreter(engine, enemy)

    for alias, expected in (("Monster_Svarog_00_Unselectable", [enemy]),
                            ("Monster_Svarog_00_RL_Unselectable", [rl])):
        assert interpreter._team_members(alias) == expected
        assert not unsupported_config_nodes({
            "$type": "RPG.GameCore.ByCompareCharacterNumber",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
            "CompareType": "Less", "CompareNumber": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        }, set())


def test_retarget_filters_candidate_and_runs_branch():
    from hsr_nous.sim.state import ActorState

    retarget = {
        "$type": "RPG.GameCore.Retarget",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
        "Predicate": {
            "$type": "RPG.GameCore.ByIsContainModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "Sign"},
        },
        "ByRandom": True,
        "MaxNumber": {"IsDynamic": False, "FixedValue": {"Value": 1}},
        "TaskList": [{"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill01"}],
        "FailedTaskList": [{"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill02"}],
    }
    config = {"DecisionList": [{
        "$type": "RPG.GameCore.AIDecisionConfig",
        "RootTask": {"$type": "RPG.GameCore.SequenceConfig", "TaskList": [retarget]},
    }]}
    assert not unsupported_config_nodes(config, {"Skill01", "Skill02"})
    engine = _engine(config, {"Skill01": "a", "Skill02": "b"})
    marked_actor = Actor(actor_id="marked_hero", name="marked_hero", actor_type="character",
                         stats=StatBlock(hp=100, spd=10))
    marked = ActorState(actor=marked_actor, current_hp=100)
    marked.modifiers["Sign"] = Modifier(
        modifier_id="Sign", name="Sign", modifier_type="debuff", duration=0)
    engine.state.actors["marked_hero"] = marked

    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter.choose_action().action_id == "a"
    assert interpreter.target_override is marked

    marked.modifiers.clear()
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter.choose_action().action_id == "b"
    assert interpreter.target_override is None

    bad = dict(retarget)
    bad["MaxNumber"] = {"IsDynamic": False, "FixedValue": {"Value": 2}}
    assert "retarget:MaxNumber" in unsupported_config_nodes(bad, set())


def test_monster_rank_predicate_uses_upstream_rank():
    engine = _engine({}, {})
    engine._enemy_policies["enemy"] = CompiledEnemyPolicy(monster_rank="BigBoss")
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareMonsterRank",
        "CompareType": "Equal", "CompareValue": 5,
    })
    assert not interpreter._predicate({
        "$type": "RPG.GameCore.ByCompareMonsterRank",
        "CompareType": "Equal", "CompareValue": 4,
    })


def test_monster_rank_selector_keeps_highest_rank():
    from hsr_nous.sim.state import ActorState

    engine = _engine({}, {})
    engine._enemy_policies["enemy"] = CompiledEnemyPolicy(monster_rank="Minion")
    for actor_id in ("elite", "elite2"):
        actor = Actor(actor_id=actor_id, name=actor_id, actor_type="monster",
                      stats=StatBlock(hp=100, spd=10))
        engine.state.actors[actor_id] = ActorState(actor=actor, current_hp=100)
        engine._enemy_policies[actor_id] = CompiledEnemyPolicy(monster_rank="BigBoss")
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    selector = {"$type": "RPG.GameCore.AIMonsterRankSelector", "PropertyStrategy": "Max"}
    assert not unsupported_config_nodes(selector, set())
    assert [st.actor.actor_id for st in interpreter._select_target_candidates(selector)] == [
        "elite", "elite2"]
    compose = {
        "$type": "RPG.GameCore.AIComposeSelector",
        "SelectorList": [{
            "$type": "RPG.GameCore.AITaskTargetTypeSelector",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllTeammate"},
        }, selector],
    }
    assert not unsupported_config_nodes(compose, set())
    assert [st.actor.actor_id for st in interpreter._select_target_candidates(compose)] == [
        "elite", "elite2"]
    assert "rank:PropertyStrategy" in unsupported_config_nodes(
        {"$type": "RPG.GameCore.AIMonsterRankSelector", "PropertyStrategy": "Min"}, set())


def test_caster_summoner_targets_living_owner():
    from hsr_nous.sim.state import ActorState

    engine = _engine({}, {})
    pet_actor = Actor(actor_id="pet", name="pet", actor_type="monster",
                      stats=StatBlock(hp=100, spd=10), summoner_id="enemy")
    pet = ActorState(actor=pet_actor, current_hp=100)
    engine.state.actors["pet"] = pet
    engine._enemy_policies["pet"] = CompiledEnemyPolicy()
    engine._enemy_policy_state["pet"] = {}
    interpreter = ConfigAIInterpreter(engine, pet)
    selector = {
        "$type": "RPG.GameCore.AITaskTargetTypeSelector",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "CasterSummoner"},
    }
    assert not unsupported_config_nodes(selector, set())
    assert interpreter._select_target_candidates(selector) == [engine.state.actors["enemy"]]
    assert interpreter._select_target(selector) is engine.state.actors["enemy"]

    engine.state.actors["enemy"].alive = False
    assert interpreter._select_target_candidates(selector) == []


def test_complex_skill_selector_self_reference_uses_action_targeting():
    selector = {
        "$type": "RPG.GameCore.AIComplexSkillAISelector", "UseSourceInSkillConfig": "Skill03"}
    task = {
        "$type": "RPG.GameCore.SelectAISkillTarget", "SkillName": "Skill03", "Selector": selector,
    }
    config = {"DecisionList": [{
        "$type": "RPG.GameCore.AIDecisionConfig",
        "RootTask": {"$type": "RPG.GameCore.SequenceConfig", "TaskList": [
            task, {"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill03"},
        ]},
    }]}
    assert not unsupported_config_nodes(config, {"Skill03"})
    engine = _engine(config, {"Skill03": "a"})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter.choose_action().action_id == "a"
    assert interpreter.target_override is None

    selector["UseSourceInSkillConfig"] = "Skill04"
    engine = _engine(config, {"Skill03": "a"})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    assert interpreter.choose_action() is None


def test_local_legend_partner_excludes_caster():
    from hsr_nous.sim.state import ActorState

    engine = _engine({}, {})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    alias = "Monster_W4_Griffin_00_LocalLegend_Partner"
    assert interpreter._team_count(alias) == 0
    assert interpreter._select_target_candidates({
        "$type": "RPG.GameCore.AITaskTargetTypeSelector",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
    }) == []

    partner_actor = Actor(actor_id="partner", name="partner", actor_type="monster",
                          stats=StatBlock(hp=100, spd=10))
    partner = ActorState(actor=partner_actor, current_hp=100)
    engine.state.actors["partner"] = partner
    assert interpreter._team_count(alias) == 1
    selector = {
        "$type": "RPG.GameCore.AITaskTargetTypeSelector",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
    }
    assert not unsupported_config_nodes(selector, set())
    assert interpreter._select_target_candidates(selector) == [partner]
    assert not unsupported_config_nodes({
        "$type": "RPG.GameCore.ByCompareTargetCount",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
        "CompareType": "Greater", "Number": {"IsDynamic": False, "FixedValue": {"Value": 0}},
    }, set())


def test_claymore_black_white_summon_aliases_use_monster_ids():
    from hsr_nous.sim.state import ActorState

    engine = _engine({}, {})
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    black = "MMonster_W4_Claymore_01_LocalLegend_BlackSummon"
    white = "MMonster_W4_Claymore_01_LocalLegend_WhiteSummon"
    assert interpreter._team_count(black) == 0 and interpreter._team_count(white) == 0
    for alias in (black, white):
        assert not unsupported_config_nodes({
            "$type": "RPG.GameCore.ByCompareTargetCount",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": alias},
            "CompareType": "Equal", "Number": {"IsDynamic": False, "FixedValue": {"Value": 0}},
        }, set())

    for actor_id in ("4032052", "4032042", "4012033", "4012023", "4032053"):
        actor = Actor(actor_id=actor_id, name=actor_id, actor_type="monster",
                      stats=StatBlock(hp=100, spd=10))
        engine.state.actors[actor_id] = ActorState(actor=actor, current_hp=100)
    assert interpreter._team_count(black) == 2
    assert interpreter._team_count(white) == 2


def test_claymore_skill02_target_prefers_most_buffs():
    from hsr_nous.sim.state import ActorState

    engine = _engine({}, {})
    for actor_id, actor_type, owner_id in (("h2", "character", ""),
                                           ("hero_pet", "memosprite", "hero")):
        actor = Actor(actor_id=actor_id, name=actor_id, actor_type=actor_type,
                      stats=StatBlock(hp=100, spd=10), summoner_id=owner_id)
        engine.state.actors[actor_id] = ActorState(actor=actor, current_hp=100)
    for actor_id, modifier_ids in (("hero", ("b1",)), ("h2", ("b1", "b2")),
                                   ("hero_pet", ("b1", "b2", "b3"))):
        for modifier_id in modifier_ids:
            engine.state.actors[actor_id].modifiers[modifier_id] = Modifier(
                modifier_id=modifier_id, name=modifier_id, modifier_type="buff", duration=0)
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    selector = {
        "$type": "RPG.GameCore.AITaskTargetTypeSelector",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "Monster_W4_Claymore_01_Skill02_Target"},
    }
    assert not unsupported_config_nodes(selector, set())
    assert interpreter._select_target_candidates(selector)[0] is engine.state.actors["h2"]

    engine.state.actors["hero"].modifiers["b2"] = Modifier(
        modifier_id="b2", name="b2", modifier_type="buff", duration=0)
    assert interpreter._select_target_candidates(selector)[0] is engine.state.actors["hero"]


def test_task_target_type_selector_supports_target_sequence():
    from hsr_nous.sim.state import ActorState

    engine = _engine({}, {})
    h2_actor = Actor(actor_id="h2", name="h2", actor_type="character",
                     stats=StatBlock(hp=100, spd=10))
    h2 = ActorState(actor=h2_actor, current_hp=100)
    engine.state.actors["h2"] = h2
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    sequence = {
        "$type": "RPG.GameCore.TargetSequence",
        "Sequence": [
            {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam"},
            {"$type": "RPG.GameCore.TargetSortByFormation"},
            {"$type": "RPG.GameCore.TargetIndex",
             "IndexValue": {"IsDynamic": False, "FixedValue": {"Value": 1}}},
        ],
    }
    selector = {"$type": "RPG.GameCore.AITaskTargetTypeSelector", "TargetType": sequence}
    assert not unsupported_config_nodes(selector, set())
    assert interpreter._select_target_candidates(selector) == [h2]

    sequence["Sequence"][1]["HighestFirst"] = True
    assert interpreter._select_target_candidates(selector) == [engine.state.actors["hero"]]


def test_by_target_list_any_filters_each_candidate():
    from hsr_nous.sim.state import ActorState

    engine = _engine({}, {})
    for actor_id, actor_type, owner_id in (("h2", "character", ""),
                                           ("hero_pet", "memosprite", "hero")):
        actor = Actor(actor_id=actor_id, name=actor_id, actor_type=actor_type,
                      stats=StatBlock(hp=100, spd=10), summoner_id=owner_id)
        engine.state.actors[actor_id] = ActorState(actor=actor, current_hp=100)
    engine.state.actors["hero"].modifiers["Ate"] = Modifier(
        modifier_id="Ate", name="Ate", modifier_type="debuff", duration=0)
    interpreter = ConfigAIInterpreter(engine, engine.state.actors["enemy"])
    predicate = {
        "$type": "RPG.GameCore.ByTargetListAny",
        "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "AllLightTeam.RemoveServant"},
        "Predicate": {
            "$type": "RPG.GameCore.ByIsContainModifier",
            "TargetType": {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"},
            "ModifierName": {"Value": "Ate"}, "Inverse": True,
        },
    }
    assert not unsupported_config_nodes(predicate, set())
    assert interpreter._predicate(predicate)

    engine.state.actors["h2"].modifiers["Ate"] = Modifier(
        modifier_id="Ate", name="Ate", modifier_type="debuff", duration=0)
    assert not interpreter._predicate(predicate)

    equivalent = dict(predicate)
    equivalent["TargetType"] = {
        "$type": "RPG.GameCore.TargetAlias", "Alias": "TauntOrAggroEnemy.RemoveServant"}
    assert not unsupported_config_nodes(equivalent, set())
    assert not interpreter._predicate(equivalent)

    bad = dict(predicate)
    bad["TargetType"] = {"$type": "RPG.GameCore.TargetAlias", "Alias": "TauntOrAggroEnemy.Unknown"}
    assert "target:TauntOrAggroEnemy.Unknown" in unsupported_config_nodes(bad, set())


def test_custom_string_tag_selector_and_template_groups(tmp_path):
    import yaml

    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.compile.stage_compiler import StageCompiler

    engine = _engine({}, {})
    enemy = engine.state.actors["enemy"]
    enemy.actor.groups = ["W1_Ice"]
    interpreter = ConfigAIInterpreter(engine, enemy)
    selector = {"$type": "RPG.GameCore.AICustomStringTagSelector", "CustomStringTag": "W1_Ice"}
    assert not unsupported_config_nodes(selector, set())
    assert interpreter._select_target_candidates(selector) == [enemy]
    inverse = {**selector, "InverseResultFlag": True}
    assert interpreter._select_target_candidates(inverse) == [engine.state.actors["hero"]]

    template = generate_enemy_template("1004031")
    assert template["groups"] == ["W1_Bronya", "RL", "Summon"]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1004031.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    compiled = StageCompiler().compile({
        "enemies": [{"enemy_template": "1004031"}],
        "termination": {"mode": "fixed_av", "max_action_value": 100},
    }, template_roots=[str(tmp_path), "data/sim_templates"])
    assert compiled.enemies[0].groups == ["W1_Bronya", "RL", "Summon"]


def test_inspire_config_ai_selects_unbuffed_other_friendly(tmp_path):
    """Vagrant Inspire：真实 ConfigAI 排除自身与已增益者，buff 后立即行动."""
    import yaml

    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.compile import compile_encounter

    template = generate_enemy_template("1002020")
    assert template["policy"]["config"]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1002020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 100, "max_toughness": 30},
        "actions": [{"action_id": "dummy_basic", "name": "测试普攻", "action_type": "skill",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    }
    (tmp_path / "enemies" / "dummy.yaml").write_text(
        yaml.safe_dump(dummy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1002020", "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    engine._enemy_policy_state["1002020"]["cooldown_left"] = {}
    seen = []
    engine.bus.subscribe("on_action", lambda _et, payload, _ctx: seen.append(
        (payload["actor"], payload["action_id"])))

    engine._enemy_turn(engine.state.actors["1002020"])

    dummy_state = engine.state.actors["dummy"]
    modifier = dummy_state.modifiers["Monster_W1_Soldier01_03_Buff"]
    assert ("1002020", "100202002") in seen and engine._last_target_id == "dummy"
    assert modifier.stat_effects == {"atk_pct": 0.3, "spd": 0.0} and modifier.duration == 2
    assert engine.pipeline.effective_stats(dummy_state)["atk"] == 130.0
    assert engine.scheduler._remaining[engine.scheduler.handle_of("dummy")] == 0.0
    assert "Monster_W1_Soldier01_03_Buff" not in engine.state.actors["1002020"].modifiers

    engine._enemy_turn(engine.state.actors["1002020"])
    assert seen[-1] == ("1002020", "100202001")


def test_tutorial_inspire_variant_and_action_delay_exception(tmp_path):
    """教程 Vagrant 按 Ability 使用 ATK +10000%，指定实例则不立即行动."""
    import yaml

    from hsr_nous.adapters.template_generator import _enemy_inspire_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.compile import compile_encounter

    raw = next(r for r in get_enemy_skills("1002021") if r["skill_id"] == "100202102")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("1002021")["en"])["skills"]
                    if s["name"] == "Inspire")
    _action, exception_hook = _enemy_inspire_action(raw, semantic, {"MonsterID": "100202104"})
    assert [effect["effect_type"] for effect in exception_hook["effects"]] == ["apply_modifier"]

    template = generate_enemy_template("1002021")
    assert [action["action_id"] for action in template["actions"]] == ["100202101", "100202102"]
    assert len(template["policy"]["config"]["DecisionList"]) == 5
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1002021.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    dummy = {
        "enemy_id": "101201012", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 100, "max_toughness": 30},
        "actions": [{"action_id": "dummy_basic", "name": "测试普攻", "action_type": "skill",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    }
    (tmp_path / "enemies" / "101201012.yaml").write_text(
        yaml.safe_dump(dummy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1002021", "level": 80},
                    {"enemy_template": "101201012"}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    engine._enemy_policy_state["1002021"]["cooldown_left"] = {}
    seen = []
    engine.bus.subscribe("on_action", lambda _et, payload, _ctx: seen.append(
        (payload["actor"], payload["action_id"])))

    engine._enemy_turn(engine.state.actors["1002021"])

    dummy_state = engine.state.actors["101201012"]
    assert ("1002021", "100202102") in seen and engine._last_target_id == "101201012"
    modifier = dummy_state.modifiers["Monster_W1_Soldier01_03_Buff"]
    assert modifier.stat_effects == {"atk_pct": 100.0, "spd": 0.0} and modifier.duration == 2
    assert engine.pipeline.effective_stats(dummy_state)["atk"] == 10100.0
    assert engine.scheduler._remaining[engine.scheduler.handle_of("101201012")] == 0.0


def test_silvermane_rl_skill09_and_reinforcement_one_more(tmp_path):
    """RL Skill09 条件追加回合；Reinforcement 双召唤后同样追加回合."""
    import yaml

    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.compile import compile_encounter

    template = generate_enemy_template("1003012")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1003012.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1003012", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(
        build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["1003012"]
    flag = "MW1_Soldier03_00_RL_AIFlag"
    enemy.modifiers[flag] = Modifier(
        modifier_id=flag, name=flag, modifier_type="buff", duration=0)
    engine._enemy_policy_state["1003012"]["cooldown_left"] = {}
    seen = []
    engine.bus.subscribe("on_action", lambda _et, payload, _ctx: seen.append(
        (payload["actor"], payload["action_id"])))

    engine._enemy_turn(enemy)

    handle = engine.scheduler.handle_of("1003012")
    assert seen == [("1003012", "100301201")]
    assert engine._enemy_policy_state["1003012"]["dynamic_values"][
        "W1_Soldier03_00_AICounter"] == 4
    assert engine.scheduler._extra_queue == [(handle, "normal_extra")]

    engine.scheduler._extra_queue.clear()
    reinforcement = next(
        action for action in engine.actions_by_actor["1003012"] if action.action_id == "100301204")
    engine.trigger_action(enemy, reinforcement, tag="test")
    for spec in template["summons"]:
        summoned = engine.state.actors.get(f"{spec['summon_id']}__1003012")
        assert summoned is not None and summoned.alive, list(engine.state.actors)
    assert engine.scheduler._extra_queue == [(handle, "normal_extra")]

    engine.scheduler._extra_queue.clear()
    del enemy.modifiers[flag]
    assault = next(
        action for action in engine.actions_by_actor["1003012"] if action.action_id == "100301201")
    engine.trigger_action(enemy, assault, tag="test")
    assert not engine.scheduler._extra_queue


def test_direwolf_felling_unshielded_insert_and_shield_gate(tmp_path):
    """无盾 Felling 追加 Dismantle；首击前有盾即不追加，哪怕盾随后被打穿."""
    import yaml

    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.compile import compile_encounter

    template = generate_enemy_template("1013020")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1013020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1013020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["1013020"]
    hero = engine.state.actors["hero"]
    enemy.actor.stats.effect_hit = 1.0
    seen = []
    hits = []
    engine.bus.subscribe("on_action", lambda _et, payload, _ctx: seen.append(payload["action_id"])
                         if payload.get("actor") == "1013020" else None)
    engine.bus.subscribe("after_being_hit", lambda _et, payload, _ctx: hits.append(payload)
                         if payload.get("source") == "1013020" and payload.get("target") == "hero" else None)
    runtime = engine._enemy_policy_state["1013020"]
    runtime.setdefault("dynamic_values", {})["WMonster_W1_Mecha_02_AIFlag_P2"] = 3
    runtime["cooldown_left"] = {}

    engine._enemy_turn(enemy)

    assert seen[-1] == "101302001" and len(hits) == 10
    bleed = hero.modifiers["ENEMY_101302001_BLEED"]
    assert bleed.stacks == 10 and bleed.max_stack == 10
    assert runtime["dynamic_values"]["Monster_W1_Mecha04_00_InsertFlag"] == 1
    handle = engine.scheduler.handle_of("1013020")
    assert engine.scheduler._extra_queue == [(handle, "normal_extra")]

    engine.step()
    assert seen[-1] == "101302004"
    assert runtime["dynamic_values"]["Monster_W1_Mecha04_00_InsertFlag"] == 0
    assert not engine.scheduler._extra_queue

    engine._apply_modifier_spec(hero, {
        "modifier_id": "TEST_SHIELD", "name": "测试护盾", "modifier_type": "buff",
        "shield": {"flat": 1.0}, "duration": 3,
    }, enemy)
    runtime["dynamic_values"]["WMonster_W1_Mecha_02_AIFlag_P2"] = 3
    runtime["cooldown_left"] = {}
    hits.clear()
    engine._enemy_turn(enemy)

    assert len(hits) == 10 and "TEST_SHIELD" not in hero.modifiers
    assert runtime["dynamic_values"]["Monster_W1_Mecha04_00_InsertFlag"] == 0
    assert not engine.scheduler._extra_queue


def test_just_war_config_ai_applies_proselytize_to_friendly(tmp_path):
    """Furiae Philosopher Just War：ConfigAI 选友方并施加常驻 SPD/DMG 增益."""
    import yaml

    from hsr_nous.adapters.template_generator import _enemy_just_war_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_ai, get_enemy_ai_config, get_enemy_mechanics, get_enemy_skills, get_monster_meta)
    from hsr_nous.sim.compile import compile_encounter

    raw = next(r for r in get_enemy_skills("4012020") if r["skill_id"] == "401202001")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("4012020")["en"])["skills"]
                    if s["name"] == "Just War")
    action, hook = _enemy_just_war_action(raw, semantic)
    ai = get_enemy_ai("4012020")
    config = get_enemy_ai_config(ai["ai_path"])
    decision = next(d for d in config["DecisionList"] if d["DecisionName"] == "UseSkill01")
    template = generate_enemy_template("4012020")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": [], "cooldown": {}, "initial_cooldown": {},
                   "skill_ids": {"Skill01": "401202001"}, "config": {"DecisionList": [decision]}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4012020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 100, "max_toughness": 30},
        "actions": [{"action_id": "dummy_basic", "name": "测试普攻", "action_type": "skill",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    }
    (tmp_path / "enemies" / "dummy.yaml").write_text(
        yaml.safe_dump(dummy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "dummy"}, {"enemy_template": "4012020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    engine._enemy_policy_state["4012020"]["cooldown_left"] = {}
    seen = []
    engine.bus.subscribe("on_action", lambda _et, payload, _ctx: seen.append(
        (payload["actor"], payload["action_id"])))

    engine._enemy_turn(engine.state.actors["4012020"])

    dummy_state = engine.state.actors["dummy"]
    modifier = dummy_state.modifiers["ENEMY_401202001_PROSELYTIZE"]
    assert ("4012020", "401202001") in seen and engine._last_target_id == "dummy"
    assert modifier.stat_effects == {"spd_pct": 0.3, "all_dmg": 0.3} and modifier.duration == 0
    assert engine.pipeline.effective_stats(dummy_state)["spd"] == 130.0
    assert engine.pipeline.effective_stats(dummy_state)["dmg_bonus"]["all"] == 0.3


def test_covering_support_follow_up_hits_primary_and_adjacent(tmp_path):
    """Silvermane Cannoneer：支援标记只在友方攻击后触发主邻追击."""
    import yaml

    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_ai, get_enemy_ai_config
    from hsr_nous.sim.compile import compile_encounter

    template = generate_enemy_template("1002030")
    ai = get_enemy_ai("1002030")
    config = get_enemy_ai_config(ai["ai_path"])
    decision = next(d for d in config["DecisionList"] if d["DecisionName"] == "UseSkill02")
    template["policy"]["config"] = {"DecisionList": [decision]}
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1002030.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 100, "max_toughness": 30},
        "actions": [{"action_id": "dummy_basic", "name": "测试普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "energy_gain": 0}],
    }
    (tmp_path / "enemies" / "dummy.yaml").write_text(
        yaml.safe_dump(dummy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1002030", "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    engine._enemy_policy_state["1002030"]["cooldown_left"] = {}
    cannoneer = engine.state.actors["1002030"]
    dummy_state = engine.state.actors["dummy"]
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2")}

    engine._enemy_turn(cannoneer)

    assert "MMonster_W1_Soldier04_00_SkillP01_Supported" in dummy_state.modifiers
    assert engine._last_target_id == "dummy"
    assert all(engine.state.actors[actor_id].current_hp == old_hp[actor_id]
               for actor_id in ("h1", "h2")), "支援动作本身不得触发追击"

    engine._enemy_turn(dummy_state)

    assert all(engine.state.actors[actor_id].current_hp < old_hp[actor_id]
               for actor_id in ("h1", "h2")), "主目标与相邻目标都应受到追击"
