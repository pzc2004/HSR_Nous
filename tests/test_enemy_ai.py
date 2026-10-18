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
