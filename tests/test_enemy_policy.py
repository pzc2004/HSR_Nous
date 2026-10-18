"""敌人序列/冷却策略：模板编译、候选状态机与存档世界线."""
from __future__ import annotations

import json

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.stage_compiler import StageCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED


def _action(action_id: str) -> dict:
    return {
        "action_id": action_id,
        "name": action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "physical",
        "scaling": [{"atk": 0.0}],
        "toughness_dmg": 0,
        "energy_gain": 0,
    }


def _compiled(tmp_path, actions, policy=None):
    enemy = {
        "enemy_id": "enemy",
        "name": "假人",
        "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 300,
                       "max_toughness": 30},
        "weakness": [],
        "actions": actions,
        **({"policy": policy} if policy is not None else {}),
    }
    (tmp_path / "enemies").mkdir(exist_ok=True)
    (tmp_path / "enemies" / "enemy.yaml").write_text(
        yaml.safe_dump(enemy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 100000, "atk": 0, "def": 0, "spd": 50,
                           "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical",
                "scaling": [{"atk": 0.0}], "toughness_dmg": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "stage_id": "s",
        "enemies": [{"enemy_template": "enemy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 10000},
    }}
    return compile_encounter(build, stage, template_roots=[str(tmp_path)])


def _watch_enemy_actions(engine) -> list[str]:
    seen: list[str] = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "enemy":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    return seen


def _run_enemy_turns(engine, count: int) -> None:
    completed = 0
    for _ in range(100):
        record = engine.step()
        assert record is not None, "战斗在预期敌方回合前提前终止"
        if record["actor_id"] == "enemy":
            completed += 1
            if completed == count:
                return
    raise AssertionError(f"100 步内只完成 {completed}/{count} 个敌方回合")


def test_initial_cooldown_then_single_skill_repeats(tmp_path):
    compiled = _compiled(tmp_path, [_action("a")], {
        "sequence": ["a"], "cooldown": {"a": 1}, "initial_cooldown": {"a": 1},
    })
    assert compiled.stage.enemy_policies["enemy"].sequence == ("a",)
    assert compiled.actions_by_actor["enemy"][0].energy_gain == 0
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = _watch_enemy_actions(engine)
    _run_enemy_turns(engine, 3)
    assert seen == ["a", "a"]  # 首回合 AI_ICD=1 跳过；AI_CD=1 在执行回合并末归零
    assert engine._enemy_policy_state["enemy"] == {
        "seq_idx": 3, "cooldown_left": {"a": 0}, "current_phase": 1,
    }


def test_cooldown_skip_advances_sequence_and_execution_resets(tmp_path):
    compiled = _compiled(tmp_path, [_action("a"), _action("b")], {
        "sequence": ["a", "b"], "cooldown": {"a": 2, "b": 0},
        "initial_cooldown": {"a": 0, "b": 0},
    })
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = _watch_enemy_actions(engine)
    _run_enemy_turns(engine, 3)
    # T1=a（a 冷却 2→1）；T2 跳过 a 并推进到 b；T3 a 已归零再次执行。
    assert seen == ["a", "b", "a"]


def test_all_cooldown_means_no_action_not_basic_fallback(tmp_path):
    compiled = _compiled(tmp_path, [_action("a"), _action("b")], {
        "sequence": ["a", "b"], "cooldown": {"a": 1, "b": 1},
        "initial_cooldown": {"a": 1, "b": 1},
    })
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = _watch_enemy_actions(engine)
    _run_enemy_turns(engine, 2)
    assert seen == ["a"]
    assert any("序列无可执行行动，空过" in line for line in engine.state.log)


def test_uncompiled_sequence_skill_is_explicitly_skipped(tmp_path):
    compiled = _compiled(tmp_path, [_action("a")], {
        "sequence": ["not_compiled", "a"], "cooldown": {"a": 0},
    })
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = _watch_enemy_actions(engine)
    _run_enemy_turns(engine, 1)
    assert seen == ["a"]
    assert engine._enemy_policy_state["enemy"]["seq_idx"] == 2
    assert any("not_compiled 未收编，跳过" in line for line in engine.state.log)


def test_no_policy_preserves_legacy_first_action(tmp_path):
    compiled = _compiled(tmp_path, [_action("a"), _action("b")])
    assert not compiled.stage.enemy_policies
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = _watch_enemy_actions(engine)
    _run_enemy_turns(engine, 1)
    assert seen == ["a"]


def test_policy_rejects_empty_unknown_and_negative_values():
    with pytest.raises(ValueError, match="sequence 不能为空"):
        StageCompiler().compile({"enemies": [
            {"actor_id": "e", "policy": {"sequence": []}},
        ]})
    with pytest.raises(ValueError, match="未知键"):
        StageCompiler().compile({"enemies": [
            {"actor_id": "e", "policy": {"sequence": ["a"], "cooldowns": {}}},
        ]})
    with pytest.raises(ValueError, match="非负整数"):
        StageCompiler().compile({"enemies": [
            {"actor_id": "e", "policy": {"sequence": ["a"], "cooldown": {"a": -1}}},
        ]})


def test_policy_rejects_wrong_shapes_and_duplicate_actions(tmp_path):
    with pytest.raises(ValueError, match="必须是数组"):
        StageCompiler().compile({"enemies": [
            {"actor_id": "e", "policy": {"sequence": "a"}},
        ]})
    with pytest.raises(ValueError, match="非负整数"):
        StageCompiler().compile({"enemies": [
            {"actor_id": "e", "policy": {"sequence": ["a"], "cooldown": {"a": 1.5}}},
        ]})
    with pytest.raises(ValueError, match="必须是 mapping"):
        StageCompiler().compile({"enemies": [
            {"actor_id": "e", "policy": {"sequence": ["a"], "cooldown": []}},
        ]})
    with pytest.raises(ValueError, match="非空阶段数组"):
        StageCompiler().compile({"enemies": [
            {"actor_id": "e", "policy": {"sequence": ["a"], "skill_phases": {"a": []}}},
        ]})
    with pytest.raises(ValueError, match="非法阶段号"):
        StageCompiler().compile({"enemies": [
            {"actor_id": "e", "policy": {"sequence": ["a"], "skill_phases": {"a": [0]}}},
        ]})
    with pytest.raises(ValueError, match="action_id.*重复"):
        _compiled(tmp_path, [_action("a"), _action("a")])


def test_save_restore_preserves_policy_worldline(tmp_path):
    compiled = _compiled(tmp_path, [_action("a")], {
        "sequence": ["a"], "cooldown": {"a": 2}, "initial_cooldown": {"a": 0},
    })
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    _run_enemy_turns(engine, 1)  # a 执行后冷却在回合末从 2 降到 1
    save = json.loads(json.dumps(engine.save_state()))
    restored = CombatEngine.load_state(compiled, save)

    expected_seen = _watch_enemy_actions(engine)
    restored_seen = _watch_enemy_actions(restored)
    _run_enemy_turns(engine, 2)   # 先全冷却空过，再执行 a
    _run_enemy_turns(restored, 2)
    assert restored_seen == expected_seen == ["a"]
    assert restored._enemy_policy_state == engine._enemy_policy_state
    assert restored.save_state() == engine.save_state()


def test_blast_enemy_action_main_and_adjacent_scaling():
    """4032010 真模板：主目标 350% / 相邻 240%，编译与敌方目标链一致."""
    import math
    from hsr_nous.sim.structured_log import StructuredLogger

    team = []
    for actor_id, taunt in (("h1", 100), ("h2", 500), ("h3", 100)):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100, "taunt": taunt},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "fire", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "4032010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=["data/sim_templates"])
    action = compiled.actions_by_actor["4032010"][0]
    assert action.target_type == "blast"
    assert action.scaling == [{"atk": 3.5}]
    assert action.scaling_blast == [{"atk": 2.4}]
    assert action.energy_grant == 10.0

    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    logger = StructuredLogger(engine)
    engine.run()
    first_damage = {}
    for entry in logger.entries:
        if entry.get("event_type") == "damage" and entry.get("source_id") == "4032010":
            first_damage.setdefault(entry["target_id"], entry["damage"])
    assert set(first_damage) == {"h1", "h2", "h3"}
    assert first_damage["h2"] > first_damage["h1"] > 0
    adjacent_mean = (first_damage["h1"] + first_damage["h3"]) / 2
    # StructuredLogger 伤害保留 1 位小数，比例断言需容纳末端舍入。
    assert math.isclose(first_damage["h2"] / adjacent_mean, 3.5 / 2.4, rel_tol=1e-4)


def test_aoe_enemy_energy_grant_per_target():
    """冰锋 AoE 的 Fandom energy=10：每个被命中我方单位各回 10，而非施放者回能."""
    team = []
    for actor_id in ("h1", "h2", "h3"):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "fire", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1002011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=["data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1002011":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    for _ in range(100):
        engine.step()
        if seen:
            break
    assert seen == ["100201101"]
    assert compiled.actions_by_actor["1002011"][0].energy_grant == 10.0
    assert {actor_id: engine.state.actors[actor_id].current_energy
            for actor_id in ("h1", "h2", "h3")} == {"h1": 10.0, "h2": 10.0, "h3": 10.0}
    assert engine.state.actors["1002011"].current_energy == 0.0


@pytest.mark.parametrize(("enemy_id", "heal_action_id"), [
    ("1012010", "101201002"),
    ("2022090", "202209001"),
])
def test_restore_action_heals_enemy_side_with_caster_hp_ratio(enemy_id, heal_action_id):
    """Restore 两种英文措辞：按施放者 HP 25% 治疗敌方而非我方."""
    import math
    from hsr_nous.sim.structured_log import StructuredLogger

    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 10000, "def": 1000, "spd": 100,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": enemy_id, "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=["data/sim_templates"])
    assert any(h.owner_id == enemy_id and h.event == "on_action"
               and any(e.get("effect_type") == "heal" and e.get("ratio") == 0.25
                       for e in h.effects)
               for h in compiled.hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    logger = StructuredLogger(engine)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == enemy_id and payload.get("action_id") == heal_action_id:
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    hp_before = None
    for _ in range(100):
        hp_before = engine.state.actors[enemy_id].current_hp
        engine.step()
        if seen:
            break
    assert seen == [heal_action_id] and hp_before is not None
    enemy = engine.state.actors[enemy_id]
    healed = enemy.current_hp - hp_before
    max_hp = engine.pipeline.effective_stats(enemy)["hp"]
    assert math.isclose(healed, min(0.25 * max_hp, max_hp - hp_before), rel_tol=1e-9)
    heals = [e for e in logger.entries if e.get("event_type") == "heal"]
    assert heals and all(e["target_id"] == enemy_id for e in heals)
    assert all(e["target_id"] != "hero" for e in heals)


def test_kafka_shock_applies_dot_and_ticks_with_snapshot():
    """Kafka 首个 Boss 切片：250% 单体雷伤后挂 Shock，75% ATK DoT 按快照跳伤."""
    import math
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 100,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2004010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=["data/sim_templates"])
    assert any(h.owner_id == "2004010" and any(
        eff.get("effect_type") == "apply_modifier"
        and eff["modifier"]["dot_ratio"] == 0.75
        and eff["modifier"]["duration"] == 3
        and eff["modifier"]["dot_base_chance"] == 1.0
        for eff in h.effects) for h in compiled.hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    dot_events = []

    def _on_hp_decrease(_event_type, payload, _ctx):
        if payload.get("reason") == "dot" and payload.get("target") == "hero":
            dot_events.append(payload)

    engine.bus.subscribe("on_hp_decrease", _on_hp_decrease)
    engine.setup()
    for _ in range(30):
        engine.step()
        if dot_events:
            break
    hero = engine.state.actors["hero"]
    assert "ENEMY_200401001_SHOCK" in hero.modifiers and dot_events
    modifier = hero.modifiers["ENEMY_200401001_SHOCK"]
    expected = 0.75 * modifier.dot_source_atk * 0.5 * 0.8 * 0.9
    assert math.isclose(dot_events[0]["amount"], expected, rel_tol=1e-9)


def test_enemy_summon_spawns_registered_monsters(tmp_path):
    """真实 Grizzly 召唤数据：一个 on_action 召唤出两个独立 Spider 实例."""
    from hsr_nous.adapters.template_generator import (
        _enemy_summon_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_detail, get_enemy_mechanics, get_enemy_skills, get_monster_meta)
    action, hook, specs = _enemy_summon_action(
        get_enemy_skills("1013010")[0],
        get_enemy_mechanics("Automaton Grizzly")["skills"][0],
        get_enemy_detail("1013010"), get_monster_meta, level=80)
    template = generate_enemy_template("1013010")
    template.update({"actions": [action], "hooks": [hook], "summons": specs,
                     "policy": {"sequence": ["101301001"], "cooldown": {}, "initial_cooldown": {}}})
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1013010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1013010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(
        build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    assert set(compiled.stage.enemy_summon_defs) == {
        f"{s['summon_id']}__1013010" for s in specs}
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1013010" and payload.get("action_id") == "101301001":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    for _ in range(10):
        engine.step()
        if seen:
            break
    assert seen == ["101301001"]
    for spec in specs:
        summoned = engine.state.actors[f"{spec['summon_id']}__1013010"]
        assert summoned.alive and summoned.actor.summoner_id == "1013010"
        assert summoned.actor.actor_type == "monster"


def test_charge_buff_applies_to_next_aoe(tmp_path):
    """Grizzly 蓄力：下一击 Purge 的 400% 物理伤害再乘 1.5."""
    from hsr_nous.adapters.template_generator import (
        _enemy_charge_action, _enemy_direct_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills
    raw = {s["skill_id"]: s for s in get_enemy_skills("1013010")}
    semantic = {s["name"]: s for s in get_enemy_mechanics("Automaton Grizzly")["skills"]}
    charge_action, charge_hook = _enemy_charge_action(
        raw["101301003"], semantic["Overcombust Order"])
    purge_action = _enemy_direct_action(raw["101301004"], semantic["Purge Order"])
    template = generate_enemy_template("1013010")
    template.update({
        "actions": [charge_action, purge_action], "hooks": [charge_hook],
        "policy": {"sequence": ["101301003", "101301004"], "cooldown": {},
                   "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1013010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1013010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    from hsr_nous.sim.structured_log import StructuredLogger
    logger = StructuredLogger(engine)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1013010" and payload.get("action_id") == "101301004":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    for _ in range(10):
        engine.step()
        if seen:
            break
    assert seen == ["101301004"]
    enemy = engine.state.actors["1013010"]
    assert any(e.get("event_type") == "action" and e.get("action_id") == "101301003"
               for e in logger.entries)
    damage = next(e for e in logger.entries if e.get("event_type") == "damage"
                  and e.get("source_id") == "1013010")
    enemy_atk = engine.pipeline.effective_stats(enemy)["atk"]
    expected = 4.0 * enemy_atk * 1.5 * 0.5 * 0.8 * 0.9 * 1.025
    import math
    assert math.isclose(damage["damage"], expected, rel_tol=1e-4)


def test_shield_reflect_marks_attacker_and_counters_with_pierce(tmp_path):
    """Silvermane Lieutenant：盾反受击后立即以穿刺反击攻击者."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("100301016")
    assert [a["action_id"] for a in template["actions"]] == [
        "100301001", "100301002", "100301003"]
    assert template["policy"]["config"]["AIName"] == "Monster_RO_015"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "100301016.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 1,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 1.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "100301016", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "100301016":
            seen.append((payload["action_id"], payload["target"]))

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(100):
        engine.step()
        if seen and seen[-1][0] == "100301003":
            break
    assert [action_id for action_id, _target in seen] == ["100301001", "100301003"]
    enemy = engine.state.actors["100301016"]
    hero = engine.state.actors["hero"]
    assert "ENEMY_100301003_COUNTER" in enemy.modifiers

    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    for _ in range(20):
        engine.step()
        if any(action_id == "100301002" for action_id, _target in seen):
            break
    assert seen[-1] == ("100301002", "hero")
    assert "ENEMY_100301003_COUNTER" not in enemy.modifiers
    assert "MMonster_W1_Soldier03_00_ReturnAttackTarget" not in hero.modifiers
    runtime = engine._enemy_policy_state["100301016"]
    assert runtime["dynamic_values"]["W1_Soldier03_00_AICounter"] == 2


def test_def_impair_aoe_applies_chance_per_target(tmp_path):
    """灯昼龙鱼 AoE：80% 基础概率逐目标结算，低抗单位减防、高抗单位抵抗."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2012010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2012010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id, effect_res in (("h1", 0.0), ("h2", 0.75), ("h3", 0.0)):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100, "effect_res": effect_res},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2012010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    effect = next(eff for hook in compiled.hooks for eff in hook.effects
                  if eff.get("effect_type") == "apply_modifier")
    assert effect["apply_chance"] == 0.8
    assert effect["modifier"]["stat_effects"] == {"def_pct": -0.3}

    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "2012010" and payload.get("action_id") == "201201001":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(30):
        engine.step()
        if seen:
            break
    assert seen == ["201201001"]
    modifier_id = "ENEMY_201201001_DEF_DOWN"
    assert modifier_id in engine.state.actors["h1"].modifiers
    assert modifier_id not in engine.state.actors["h2"].modifiers
    assert modifier_id in engine.state.actors["h3"].modifiers
    assert engine.pipeline.effective_stats(engine.state.actors["h1"])["def_"] == 700.0
    assert engine.pipeline.effective_stats(engine.state.actors["h2"])["def_"] == 1000.0


def test_delay_action_pushes_target_gauge(tmp_path):
    """Everwinter Shadewalker：300% 冰伤同时将目标行动条延后 50%."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("1022010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1022010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1022010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    effect = next(eff for hook in compiled.hooks for eff in hook.effects
                  if eff.get("effect_type") == "delay_action")
    assert effect["amount"] == 50.0 and effect["target"] == "$event.target"
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    before = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1022010" and payload.get("action_id") == "102201001":
            seen.append(payload["action_id"])
            before.append(engine.scheduler._remaining[engine.scheduler.handle_of("hero")])

    # 先于 compiled hooks 订阅，排除本步时钟推进对剩余距离的扣减，只量 hook 推条。
    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    handle = engine.scheduler.handle_of("hero")
    delayed = None
    for _ in range(30):
        engine.step()
        if seen:
            delayed = engine.scheduler._remaining[handle] - before[0]
            break
    assert seen == ["102201001"]
    assert math.isclose(delayed, 5000.0, rel_tol=1e-9)


def test_bounce_action_executes_six_random_target_hits(tmp_path):
    """Ballistarius Mounted Crossbow：100% 雷伤弹射六段，逐段从存活我方选目标."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.pipeline import MODE_ROLL
    from hsr_nous.sim.structured_log import StructuredLogger

    template = generate_enemy_template("2022060")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2022060.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id in ("h1", "h2", "h3"):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2022060", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    action = compiled.actions_by_actor["2022060"][0]
    assert action.target_type == "bounce" and action.instances == 6
    assert action.scaling == [{"atk": 1.0}]
    engine = CombatEngine.from_compiled(
        compiled, mode=MODE_ROLL, seed=42, initial_energy_ratio=0.0)
    logger = StructuredLogger(engine)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "2022060" and payload.get("action_id") == "202206001":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(30):
        engine.step()
        if seen:
            break
    assert seen == ["202206001"]
    hits = [entry for entry in logger.entries
            if entry.get("event_type") == "damage" and entry.get("source_id") == "2022060"]
    assert len(hits) == 6
    assert {entry["target_id"] for entry in hits} <= {"h1", "h2", "h3"}


def test_wind_shear_reapplication_stacks_and_scales_dot(tmp_path):
    """Rusher 风化重复施加叠层：第二回合 DoT 基数随 2 层翻倍，上限为 5."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("5012050")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "5012050.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            # 我方略快于敌人（172.8），两次敌方施加之间恰好只有一次 DoT 跳伤。
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 180,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "5012050", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    effect = next(eff for hook in compiled.hooks for eff in hook.effects
                  if eff.get("effect_type") == "apply_modifier")
    assert effect["apply_chance"] == 1.0
    assert effect["modifier"]["max_stack"] == 5
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    dot_events = []
    dot_stacks = []

    def _on_hp_decrease(_event_type, payload, _ctx):
        if payload.get("reason") == "dot" and payload.get("target") == "hero":
            dot_events.append(payload)
            modifier = engine.state.actors["hero"].modifiers["ENEMY_501205001_WIND_SHEAR"]
            dot_stacks.append(modifier.stacks)

    engine.bus.subscribe("on_hp_decrease", _on_hp_decrease)
    engine.setup()
    for _ in range(80):
        engine.step()
        if len(dot_events) >= 2:
            break
    assert len(dot_events) >= 2
    assert dot_stacks[:2] == [1, 2]
    assert math.isclose(dot_events[1]["amount"], dot_events[0]["amount"] * 2, rel_tol=1e-9)


def test_imprisonment_apply_is_atomic_per_target(tmp_path):
    """Disaster's Right Hand：禁锢命中则同时推条/减速，抵抗则两者都不发生."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.state import Modifier

    template = generate_enemy_template("8012140")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8012140.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id, effect_res in (("h1", 0.0), ("h2", 0.9)):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100, "effect_res": effect_res},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8012140", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    assert next(a for a in compiled.actions_by_actor["8012140"]
                if a.action_id == "801214003").instances == 2
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    before = {}

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "8012140" and payload.get("action_id") == "801214002":
            seen.append(payload["action_id"])
            for actor_id in ("h1", "h2"):
                handle = engine.scheduler.handle_of(actor_id)
                before[actor_id] = engine.scheduler._remaining[handle]

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    enemy = engine.state.actors["8012140"]
    # 20%×(1+200%)：普通目标命中率 60% 生效；90% 抵抗目标仅 6%，推条也不能漏执行。
    enemy.actor.stats.effect_hit = 2.0
    engine._apply_modifier(enemy, Modifier(
        modifier_id="MMonster_W0_Boss_00_Part2_AttackUp",
        name="MMonster_W0_Boss_00_Part2_AttackUp", modifier_type="buff"))
    for _ in range(100):
        engine.step()
        if seen:
            break
    assert seen == ["801214002"]
    for actor_id in ("h1", "h2"):
        handle = engine.scheduler.handle_of(actor_id)
        delta = engine.scheduler._remaining[handle] - before[actor_id]
        assert math.isclose(delta, 3000.0 if actor_id == "h1" else 0.0, abs_tol=1e-9)
    modifier_id = "ENEMY_801214002_IMPRISON"
    assert modifier_id in engine.state.actors["h1"].modifiers
    assert modifier_id not in engine.state.actors["h2"].modifiers
    assert engine.pipeline.effective_stats(engine.state.actors["h1"])["spd"] == 40.0
    assert engine.pipeline.effective_stats(engine.state.actors["h2"])["spd"] == 50.0


def test_phase_list_gates_sequence_and_config_ai(tmp_path):
    """Disaster's Right Hand：PhaseList 同时约束普通序列与 ConfigAI UseSkill."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.enemy_ai import ConfigAIInterpreter

    template = generate_enemy_template("8012140")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8012140.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8012140", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    policy = compiled.stage.enemy_policies["8012140"]
    assert policy.skill_phases == {
        "801214001": (1,), "801214002": (1, 2), "801214003": (2,),
    }
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["8012140"]
    runtime = engine._enemy_policy_state["8012140"]
    runtime.update({"seq_idx": 2, "current_phase": 1})
    runtime["cooldown_left"] = {action_id: 0 for action_id in policy.skill_phases}
    selected = engine._select_enemy_policy_action(enemy)
    assert selected.action_id == "801214002" and runtime["seq_idx"] == 5
    assert sum("不适用阶段 1" in line for line in engine.state.log) == 2

    engine2 = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine2.setup()
    enemy2 = engine2.state.actors["8012140"]
    runtime2 = engine2._enemy_policy_state["8012140"]
    runtime2.update({"seq_idx": 0, "current_phase": 2})
    runtime2["cooldown_left"] = {action_id: 0 for action_id in policy.skill_phases}
    selected2 = engine2._select_enemy_policy_action(enemy2)
    assert selected2.action_id == "801214003" and runtime2["seq_idx"] == 3
    assert sum("不适用阶段 2" in line for line in engine2.state.log) == 2

    runtime2["cooldown_left"] = {action_id: 0 for action_id in policy.skill_phases}
    interpreter = ConfigAIInterpreter(engine2, enemy2)
    assert not interpreter._cooldown_ready("801214001")
    assert interpreter._cooldown_ready("801214003")
    runtime2["current_phase"] = 1
    assert interpreter._cooldown_ready("801214001")
    assert not interpreter._cooldown_ready("801214003")


def test_vulnerability_action_applies_damage_taken_debuff(tmp_path):
    """Assistant Graffiti: Slacker：单体冰伤后目标承伤提高 30%."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("5012040")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "5012040.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "5012040", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    assert compiled.actions_by_actor["5012040"][0].scaling == [{"atk": 2.0}]
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "5012040" and payload.get("action_id") == "501204001":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(30):
        engine.step()
        if seen:
            break
    assert seen == ["501204001"]
    hero = engine.state.actors["hero"]
    modifier = hero.modifiers["ENEMY_501204001_VULNERABILITY"]
    assert modifier.stat_effects == {"vulnerability": 0.3}
    assert modifier.max_stack == 1
    assert engine.pipeline.effective_stats(hero)["vulnerability"] == 0.3


def test_spider_timed_charge_then_self_destructs(tmp_path):
    """Automaton Spider：定时蓄力推进到自爆，Blast 命中主邻目标并走死亡链."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.structured_log import StructuredLogger

    template = generate_enemy_template("1012020")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1012020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id, taunt in (("h1", 100), ("h2", 500), ("h3", 100)):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100, "taunt": taunt},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1012020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    assert next(a for a in compiled.actions_by_actor["1012020"]
                if a.action_id == "101202002").target_type == "self"
    assert next(a for a in compiled.actions_by_actor["1012020"]
                if a.action_id == "101202003").scaling == [{"atk": 5.0}]
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    logger = StructuredLogger(engine)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1012020":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(100):
        engine.step()
        if "101202003" in seen:
            break
    assert seen == ["101202001", "101202002", "101202003"]
    hits = [entry for entry in logger.entries
            if entry.get("event_type") == "damage" and entry.get("source_id") == "1012020"]
    assert {entry["target_id"] for entry in hits[-3:]} == {"h1", "h2", "h3"}
    assert not engine.state.actors["1012020"].alive


def test_mara_summon_consumes_hp_and_spawns_two(tmp_path):
    """Shape Shifter：Mara-Summon 先消耗 10% Max HP，再召唤两名士兵."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("202301008")
    assert len(template["summons"]) == 2
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "202301008.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "202301008", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    hp_before = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "202301008" and payload.get("action_id") == "202301004":
            seen.append(payload["action_id"])
            hp_before.append(engine.state.actors["202301008"].current_hp)

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(100):
        engine.step()
        if seen:
            break
    assert seen == ["202301004"] and hp_before
    caster = engine.state.actors["202301008"]
    max_hp = engine.pipeline.effective_stats(caster)["hp"]
    assert math.isclose(caster.current_hp, hp_before[0] - max_hp * 0.1, rel_tol=1e-9)
    for spec in template["summons"]:
        summoned = engine.state.actors[f"{spec['summon_id']}__202301008"]
        assert summoned.alive and summoned.actor.summoner_id == "202301008"


def test_bleed_dot_scales_with_target_max_hp(tmp_path):
    """Silvermane Gunner：Bleed 跳伤基数是目标 Max HP 的 15%，不是施放者面板."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("1002050")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1002050.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 100000, "atk": 0, "def": 1000, "spd": 180,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1002050", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    dot_events = []
    tick_bases = []

    def _on_hp_decrease(_event_type, payload, _ctx):
        if payload.get("reason") == "dot" and payload.get("target") == "hero":
            dot_events.append(payload)
            hero = engine.state.actors["hero"]
            modifier = hero.modifiers["ENEMY_100205001_BLEED"]
            tick_bases.append(engine.pipeline.dot_tick_base(hero, modifier))

    engine.bus.subscribe("on_hp_decrease", _on_hp_decrease)
    engine.setup()
    for _ in range(40):
        engine.step()
        if dot_events:
            break
    assert dot_events and dot_events[0]["amount"] > 0
    assert math.isclose(tick_bases[0], 15000.0, rel_tol=1e-9)


def test_trashcan_atk_bonus_doubles_on_every_use(tmp_path):
    """Lordly Trashcan：初次 ATK +100%，随后每次使用翻倍且不可驱散."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("3002050")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002050.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "3002050", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "3002050" and payload.get("action_id") == "300205002":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(100):
        engine.step()
        if len(seen) >= 3:
            break
    assert len(seen) == 3
    enemy = engine.state.actors["3002050"]
    modifier = enemy.modifiers["ENEMY_300205002_ATK_UP"]
    assert modifier.stacks == 3 and modifier.stat_effects == {"atk_pct": 4.0}
    assert not modifier.dispellable
    assert math.isclose(
        engine.pipeline.effective_stats(enemy)["atk"], enemy.actor.stats.atk * 5.0, rel_tol=1e-9)
    variant = generate_enemy_template("3002052")["hooks"][0]["effects"][0]
    assert variant["modifier"]["stat_effects"]["atk_pct"].startswith("0.2 *")


def test_delay_action_uses_shared_effect_hit_channel(tmp_path):
    """Memory Zone Meme Allseer：100% 基础概率仍受 EHR/效果抵抗影响."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("3011010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3011010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100, "effect_res": 0.6},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "3011010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    effect = next(eff for hook in compiled.hooks for eff in hook.effects
                  if eff.get("effect_type") == "delay_action")
    assert effect["amount"] == 20.0 and effect["apply_chance"] == 1.0

    def _run(effect_hit):
        engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        seen = []
        resisted = []
        before = []

        def _on_action(_event_type, payload, _ctx):
            if payload.get("actor") == "3011010" and payload.get("action_id") == "301101001":
                seen.append(payload["action_id"])
                handle = engine.scheduler.handle_of("hero")
                before.append(engine.scheduler._remaining[handle])

        engine.bus.subscribe("on_action", _on_action)
        engine.bus.subscribe("on_resist", lambda _t, payload, _c: resisted.append(payload))
        engine.setup()
        engine.state.actors["3011010"].actor.stats.effect_hit = effect_hit
        for _ in range(40):
            engine.step()
            if seen:
                break
        assert seen == ["301101001"] and before
        handle = engine.scheduler.handle_of("hero")
        return engine.scheduler._remaining[handle] - before[0], len(resisted)

    resisted_delta, resist_count = _run(0.0)   # 1×(1−60%)=40%，期望模式抵抗
    applied_delta, applied_resist_count = _run(1.0)  # 1×2×(1−60%)=80%，生效
    assert math.isclose(resisted_delta, 0.0, abs_tol=1e-9) and resist_count == 1
    assert math.isclose(applied_delta, 2000.0, rel_tol=1e-9) and applied_resist_count == 0


def test_burn_dot_ticks_with_atk_snapshot(tmp_path):
    """Incineration Shadewalker：Burn 按施放者 ATK 快照的 50% 跳伤."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("1022020")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1022020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 100000, "atk": 0, "def": 1000, "spd": 180,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1022020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    dot_events = []
    tick_bases = []

    def _on_hp_decrease(_event_type, payload, _ctx):
        if payload.get("reason") == "dot" and payload.get("target") == "hero":
            dot_events.append(payload)
            hero = engine.state.actors["hero"]
            modifier = hero.modifiers["ENEMY_102202001_BURN"]
            tick_bases.append(engine.pipeline.dot_tick_base(hero, modifier))

    engine.bus.subscribe("on_hp_decrease", _on_hp_decrease)
    engine.setup()
    for _ in range(40):
        engine.step()
        if dot_events:
            break
    assert dot_events and dot_events[0]["amount"] > 0
    modifier = engine.state.actors["hero"].modifiers.get("ENEMY_102202001_BURN")
    assert modifier is not None and modifier.dot_element == "fire"
    assert math.isclose(tick_bases[0], modifier.dot_source_atk * 0.5, rel_tol=1e-9)


def test_combustion_slash_prefers_burned_target_over_taunt(tmp_path):
    """Searing Prowler：Crimson Blade 挂灼烧后，Combustion Slash 越过更高嘲讽优先该目标."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("1023010")
    assert [a["action_id"] for a in template["actions"][:2]] == ["102301001", "102301002"]
    assert template["policy"]["sequence"] == ["102301001", "102301002"]
    assert template["actions"][1]["prefer_target"] == "dot:burn"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1023010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id, taunt in (("h1", 100), ("h2", 500), ("h3", 100)):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100, "taunt": taunt},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1023010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1023010":
            seen.append((payload["action_id"], payload["target"]))

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    taunt_changed = False
    for _ in range(100):
        engine.step()
        if seen and not taunt_changed:
            assert seen[0] == ("102301001", "h2")
            assert "ENEMY_102301001_BURN" in engine.state.actors["h2"].modifiers
            # 若第二击仍只按嘲讽选主目标，必然改打 h3；灼烧偏好应继续打 h2。
            engine.state.actors["h2"].actor.stats.taunt = 0
            engine.state.actors["h3"].actor.stats.taunt = 1000
            taunt_changed = True
        if len(seen) == 2:
            break
    assert seen == [("102301001", "h2"), ("102301002", "h2")]


def test_searing_prowler_config_ai_enhance_cinders_and_break_dispel(tmp_path):
    """完整 ConfigAI：高温运转增益，飞舞烬火附伤并解灼烧，击破解除增益."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("1023010")
    assert [a["action_id"] for a in template["actions"]] == [
        "102301001", "102301002", "102301004", "102301005"]
    assert template["policy"]["config"]["AIName"] == "Monster_W1_Mecha04_01"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1023010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 1,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "ice", "scaling": [{"atk": 1.0}],
                         "toughness_dmg": 1000, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1023010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    additional = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1023010":
            seen.append((payload["action_id"], payload["target"]))

    def _on_hp_decrease(_event_type, payload, _ctx):
        if (payload.get("source") == "1023010" and payload.get("reason") == "hit"
                and payload.get("action_type") == "additional"):
            additional.append(payload["target"])

    engine.bus.subscribe("on_action", _on_action)
    engine.bus.subscribe("on_hp_decrease", _on_hp_decrease)
    engine.setup()
    enemy = engine.state.actors["1023010"]
    base_atk = enemy.actor.stats.atk
    base_spd = enemy.actor.stats.spd
    buff_checked = False
    for _ in range(200):
        engine.step()
        if len(seen) == 3 and not buff_checked:
            assert seen == [("102301001", "hero"), ("102301002", "hero"),
                            ("102301004", "1023010")]
            assert "Monster_W1_Mecha_Fire_Burning" in enemy.modifiers
            effective = engine.pipeline.effective_stats(enemy)
            assert math.isclose(effective["atk"], base_atk * 1.2, rel_tol=1e-9)
            assert math.isclose(effective["spd"], base_spd + 100.0, rel_tol=1e-9)
            buff_checked = True
        if len(seen) == 4:
            break
    assert seen[-1] == ("102301005", "hero")
    assert additional == ["hero"]
    assert "ENEMY_102301001_BURN" not in engine.state.actors["hero"].modifiers

    hero = engine.state.actors["hero"]
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert enemy.broken
    assert "Monster_W1_Mecha_Fire_Burning" not in enemy.modifiers
    effective = engine.pipeline.effective_stats(enemy)
    assert math.isclose(effective["atk"], base_atk, rel_tol=1e-9)
    assert math.isclose(effective["spd"], base_spd, rel_tol=1e-9)


def test_hardy_sheath_boosts_def_and_locks_toughness(tmp_path):
    """Abundant Ebon Deer：Hardy Leaf Sheath 加防 200%，存续期间不可削韧."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2024014")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2024014.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": template["weakness"][0],
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 10, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2024014", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "2024014" and payload.get("action_id") == "202401407":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(100):
        engine.step()
        if seen:
            break
    assert seen == ["202401407"]
    enemy = engine.state.actors["2024014"]
    modifier = enemy.modifiers["ENEMY_202401407_HARDY_SHEATH"]
    assert modifier.toughness_lock
    assert math.isclose(
        engine.pipeline.effective_stats(enemy)["def_"], enemy.actor.stats.def_ * 3.0, rel_tol=1e-9)
    enemy.toughness = enemy.actor.stats.max_toughness
    before = enemy.toughness
    hero = engine.state.actors["hero"]
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert enemy.toughness == before


def test_weaken_reduces_target_outgoing_damage(tmp_path):
    """Obedient Dracolion：Weaken 使目标造成的伤害降低 30%."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.structured_log import StructuredLogger

    template = generate_enemy_template("2011010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2011010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2011010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    logger = StructuredLogger(engine)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "2011010" and payload.get("action_id") == "201101001":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(40):
        engine.step()
        if seen:
            break
    assert seen == ["201101001"]
    hero = engine.state.actors["hero"]
    modifier_id = "ENEMY_201101001_WEAKEN"
    assert hero.modifiers[modifier_id].stat_effects == {"all_dmg": -0.3}
    action = compiled.actions_by_actor["hero"][0]
    engine._execute_action(hero, action)
    weakened = next(entry["damage"] for entry in reversed(logger.entries)
                    if entry.get("event_type") == "damage" and entry.get("source_id") == "hero")
    engine._remove_modifier(hero, modifier_id, "test")
    engine._execute_action(hero, action)
    baseline = next(entry["damage"] for entry in reversed(logger.entries)
                    if entry.get("event_type") == "damage" and entry.get("source_id") == "hero")
    assert math.isclose(weakened, baseline * 0.7, rel_tol=1e-4)


def test_effect_res_down_changes_later_debuff_hit(tmp_path):
    """Spring Loader：Effect RES -20% 使后续同一 debuff 从抵抗变为命中."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.state import Modifier

    template = generate_enemy_template("3001010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3001010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100, "effect_res": 0.5},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "3001010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "3001010" and payload.get("action_id") == "300101001":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    enemy = engine.state.actors["3001010"]
    enemy.actor.stats.effect_hit = 0.5
    hero = engine.state.actors["hero"]
    probe = Modifier(
        modifier_id="PROBE", name="测试减益", modifier_type="debuff",
        source_id="3001010", duration=1)
    assert not engine._apply_modifier(hero, probe, apply_chance=0.5)  # 0.5×1.5×0.5=37.5%
    for _ in range(40):
        engine.step()
        if seen:
            break
    assert seen == ["300101001"]
    assert engine.pipeline.effective_stats(hero)["effect_res"] == 0.3
    assert engine._apply_modifier(hero, probe, apply_chance=0.5)  # 0.5×1.5×0.7=52.5%


def test_trampler_lock_on_entangle_and_delayed_damage(tmp_path):
    """Voidranger Trampler：锁定目标后 End of Bow 纠缠推条并产生延迟伤害."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("8013010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8013010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id, taunt in (("h1", 100), ("h2", 500), ("h3", 100)):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 180,
                           "max_energy": 100, "taunt": taunt},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8013010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    target = []
    before = []
    dot_bases = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "8013010":
            seen.append(payload["action_id"])
            if payload.get("action_id") == "801301005":
                target.append(payload.get("target"))
                handle = engine.scheduler.handle_of("h2")
                before.append(engine.scheduler._remaining[handle])

    def _on_hp_decrease(_event_type, payload, _ctx):
        if payload.get("reason") == "dot" and payload.get("target") == "h2":
            modifier = engine.state.actors["h2"].modifiers["ENEMY_801301005_ENTANGLE"]
            dot_bases.append(engine.pipeline.dot_tick_base(engine.state.actors["h2"], modifier))

    engine.bus.subscribe("on_action", _on_action)
    engine.bus.subscribe("on_hp_decrease", _on_hp_decrease)
    engine.setup()
    delayed = None
    for _ in range(100):
        engine.step()
        if "801301005" in seen:
            handle = engine.scheduler.handle_of("h2")
            delayed = engine.scheduler._remaining[handle] - before[0]
            break
    assert "801301004" in seen and target == ["h2"]
    assert math.isclose(delayed, 5000.0, rel_tol=1e-9)
    hero = engine.state.actors["h2"]
    assert "ENEMY_8013010_LOCK_ON" not in hero.modifiers
    modifier = hero.modifiers["ENEMY_801301005_ENTANGLE"]
    assert modifier.control_kind == "entangle" and modifier.dot_ratio == 0.8
    for _ in range(100):
        engine.step()
        if dot_bases:
            break
    assert dot_bases and math.isclose(dot_bases[0], modifier.dot_source_atk * 0.8, rel_tol=1e-9)


def test_nihility_command_locks_all_followup_attacks(tmp_path):
    """Voidranger Distorter：随机锁定后，后续单体攻击也指向同一目标并带 10% 易伤."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.pipeline import MODE_ROLL

    template = generate_enemy_template("8012020")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8012020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id in ("h1", "h2", "h3"):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 180,
                           "max_energy": 100},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8012020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42, initial_energy_ratio=0.0)
    targets = {}

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "8012020":
            targets[payload["action_id"]] = payload.get("target")

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(100):
        engine.step()
        if "801202002" in targets:
            break
    assert "801202001" in targets and "801202002" in targets
    assert targets["801202002"] == targets["801202001"]
    modifier = engine.state.actors[targets["801202001"]].modifiers["ENEMY_8012020_LOCK_ON"]
    assert modifier.lock_on and modifier.stat_effects == {"vulnerability": 0.1}


def test_trotter_flee_sequence_leaves_without_kill(tmp_path):
    """Warp Trotter：两次倒计时后逃跑，actor_exit=flee 且不发 on_kill."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("8002040")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8002040.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8002040", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    exits = []
    kills = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "8002040":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.bus.subscribe("actor_exit", lambda _t, payload, _c: exits.append(payload))
    engine.bus.subscribe("on_kill", lambda _t, payload, _c: kills.append(payload))
    engine.setup()
    for _ in range(100):
        engine.step()
        if exits:
            break
    assert seen == ["800204001", "800204002", "800204003"]
    assert len(exits) == 1 and exits[0]["reason"] == "flee"
    assert not engine.state.actors["8002040"].alive and not kills


def test_reverberation_strong_blocks_next_action(tmp_path):
    """Wraith Warden：Reverberation 受击转 Strong，推 70% 并禁止下次行动."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2002030")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2002030.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 180,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2002030", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    enemy_actions = []
    hero_actions = []
    hits = []
    before = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "2002030" and payload.get("action_id") == "200203001":
            enemy_actions.append(payload["action_id"])
        elif payload.get("actor") == "hero":
            hero_actions.append(payload["action_id"])

    def _after_hit(_event_type, payload, _ctx):
        if payload.get("target") == "hero":
            hits.append(payload)
            if len(hits) == 2:
                handle = engine.scheduler.handle_of("hero")
                before.append(engine.scheduler._remaining[handle])

    engine.bus.subscribe("on_action", _on_action)
    engine.bus.subscribe("after_being_hit", _after_hit)
    engine.setup()
    engine.state.actors["2002030"].actor.stats.effect_hit = 1.0  # 35%×2=70%，期望模式可施加
    for _ in range(100):
        engine.step()
        if len(enemy_actions) >= 2:
            break
    assert len(enemy_actions) == 2 and before
    handle = engine.scheduler.handle_of("hero")
    assert math.isclose(engine.scheduler._remaining[handle] - before[0], 7000.0, rel_tol=1e-9)
    hero = engine.state.actors["hero"]
    assert "ENEMY_200203001_REVERB" not in hero.modifiers
    strong = hero.modifiers["ENEMY_200203001_STRONG_REVERB"]
    assert strong.prevent_action and strong.control_kind == "strong_reverberation"
    hero_action_count = len(hero_actions)
    engine._run_turn(hero, "normal")
    assert len(hero_actions) == hero_action_count
    assert "ENEMY_200203001_STRONG_REVERB" not in hero.modifiers


def test_mara_wind_shear_starts_with_two_stacks(tmp_path):
    """Mara-Struck Soldier：首次施加 Wind Shear 即为 2 层."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2022010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2022010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2022010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "2022010" and payload.get("action_id") == "202201001":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(40):
        engine.step()
        if seen:
            break
    assert seen == ["202201001"]
    modifier = engine.state.actors["hero"].modifiers["ENEMY_202201001_WIND_SHEAR"]
    assert modifier.stacks == 2 and modifier.dot_ratio == 0.5 and modifier.duration == 3


def test_combat_redeployment_purifies_and_acts_now(tmp_path):
    """Bronya Combat Redeployment：净化其他友方并使其立即行动，不影响自己."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.state import Modifier

    template = generate_enemy_template("100403004")
    template["policy"] = {"sequence": ["100403002"], "cooldown": {}, "initial_cooldown": {}}
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "100403004.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 0, "def": 0, "spd": 100, "max_toughness": 30},
        "actions": [_action("dummy_basic")],
    }
    (tmp_path / "enemies" / "dummy.yaml").write_text(
        yaml.safe_dump(dummy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "100403004", "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    dummy_state = engine.state.actors["dummy"]
    engine._apply_modifier(dummy_state, Modifier(
        modifier_id="TEST_DEBUFF", name="测试减益", modifier_type="debuff", duration=2))
    assert "TEST_DEBUFF" in dummy_state.modifiers
    engine._enemy_turn(engine.state.actors["100403004"])
    assert "TEST_DEBUFF" not in dummy_state.modifiers
    handle = engine.scheduler.handle_of("dummy")
    assert engine.scheduler._remaining[handle] == 0.0
