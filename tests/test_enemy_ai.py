"""ConfigAI 行为树解释器：动态值、阶段分支与静态收编闸."""
from __future__ import annotations

from hsr_nous.sim.compile.compiled import CompiledEnemyPolicy
from hsr_nous.sim.enemy_ai import ConfigAIInterpreter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.config_ai import unsupported_config_nodes
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _engine(config, skill_ids, allies=None):
    heroes = allies or [Actor(actor_id="hero", name="测试员", stats=StatBlock(hp=1e9, spd=50))]
    enemy = Actor(actor_id="enemy", name="假人", actor_type="monster",
                  stats=StatBlock(hp=1e9, atk=0, spd=100))
    actions = [Action(action_id=action_id, name=action_id, action_type="skill",
                      target_type="single", damage_type="physical",
                      scaling=[{"atk": 0.0}], energy_gain=0)
               for action_id in set(skill_ids.values())]
    policy = CompiledEnemyPolicy(config=config, skill_ids=skill_ids)
    encounter = Encounter(
        encounter_id="t", name="t", actors=[*heroes, enemy],
        termination=TerminationConfig(mode="fixed_av", max_action_value=1000),
    )
    engine = CombatEngine(
        encounter, actions_by_actor={"enemy": actions}, enemy_policies={"enemy": policy},
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
            {"$type": "RPG.GameCore.SwitchCaseByDynamicValue",
             "Switch": {"IsDynamic": False, "FixedValue": {"Value": 1}}, "CaseTaskList": []},
            {"$type": "RPG.GameCore.UseSkill", "SkillName": "Skill02"},
        ]},
    }]}
    bad = unsupported_config_nodes(config, {"Skill01"})
    assert "RPG.GameCore.SwitchCaseByDynamicValue" in bad
    assert "skill:Skill02" in bad


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
