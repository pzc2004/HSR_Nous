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


def _compiled(tmp_path, actions, policy=None, custom_resources=None, team=None, hooks=None):
    enemy = {
        "enemy_id": "enemy",
        "name": "假人",
        "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 300,
                       "max_toughness": 30},
        "weakness": [],
        "actions": actions,
        **({"policy": policy} if policy is not None else {}),
        **({"custom_resources": custom_resources} if custom_resources else {}),
        **({"hooks": hooks} if hooks else {}),
    }
    (tmp_path / "enemies").mkdir(exist_ok=True)
    (tmp_path / "enemies" / "enemy.yaml").write_text(
        yaml.safe_dump(enemy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": team or [{
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


@pytest.mark.parametrize(("enemy_id", "skill_id", "semantic_name", "expected_name", "expected_count"), [
    ("1013010", "101301001", "Detonation Order", "Automaton Spider", 2),
    ("3003032", "300303206", "Lamentation Like the Jackals", "Dreamjolt Troupe's Bubble Hound", 2),
    ("1014011", "101401107", "Boost Deployment", "Auxiliary Robot Arm Unit", 1),
    ("1014012", "101401207", "Boost Deployment", "Auxiliary Robot Arm Unit", 1),
    ("2024010", "202401002", "Pedicel: Marple Leaf", "Twig of Marple Leaf", 1),
    ("2024010", "202401004", "Pedicel: Lavish Fruits", "Twig of Lavish Fruits", 1),
    ("202401008", "202401002", "Pedicel: Marple Leaf", "Twig of Marple Leaf", 1),
])
def test_enemy_summon_spawns_registered_monsters(
        tmp_path, enemy_id, skill_id, semantic_name, expected_name, expected_count):
    """真实召唤数据：数量语序与多 ID 名称消歧都生成已登记的怪物实例."""
    from hsr_nous.adapters.template_generator import (
        _enemy_summon_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_detail, get_enemy_mechanics, get_enemy_skills, get_monster_meta)
    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == semantic_name)
    action, hooks, specs = _enemy_summon_action(
        raw, semantic, get_enemy_detail(enemy_id), get_monster_meta, level=80)
    assert len(specs) == expected_count
    template = generate_enemy_template(enemy_id)
    template.update({"actions": [action], "hooks": hooks, "summons": specs,
                     "policy": {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}}})
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    for summon_template_id in {spec["enemy_template"] for spec in specs}:
        (tmp_path / "enemies" / f"{summon_template_id}.yaml").write_text(
            yaml.safe_dump(generate_enemy_template(summon_template_id),
                           allow_unicode=True, sort_keys=False), encoding="utf-8")
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
        "enemies": [{"enemy_template": enemy_id, "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(
        build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    assert set(compiled.stage.enemy_summon_defs) == {
        f"{s['summon_id']}__{enemy_id}" for s in specs}
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == enemy_id and payload.get("action_id") == skill_id:
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    for _ in range(10):
        engine.step()
        if seen:
            break
    assert seen == [skill_id]
    for spec in specs:
        summoned = engine.state.actors[f"{spec['summon_id']}__{enemy_id}"]
        assert summoned.alive and summoned.actor.summoner_id == enemy_id
        assert summoned.actor.actor_type == "monster" and summoned.actor.name == expected_name


def test_grizzly_bug_detonation_summons_two_of_each(tmp_path):
    """Grizzly (Bug)：ConfigAI 召唤 Spider ×2 + Beetle ×2，实例 ID 不重复."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("1013011")
    assert template["policy"]["config"]["AIName"] == "Monster_RO_015"
    assert template["actions"][0]["target_type"] == "self"
    assert not any(effect.get("modifier", {}).get("lock_on")
                   for hook in template["hooks"] for effect in hook["effects"])
    assert [spec["enemy_template"] for spec in template["summons"]] == [
        "1012021", "1012021", "1012030", "1012030"]
    (tmp_path / "enemies").mkdir()
    for enemy_id in ("1013011", "1012021", "1012030"):
        doc = template if enemy_id == "1013011" else generate_enemy_template(enemy_id)
        (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1013011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    expected_ids = {f"{spec['summon_id']}__1013011" for spec in template["summons"]}
    assert set(compiled.stage.enemy_summon_defs) == expected_ids
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "1013011" else None)
    engine.setup()
    runtime = engine._enemy_policy_state["1013011"]
    runtime["cooldown_left"] = {}
    runtime.setdefault("dynamic_values", {})["AIFlag"] = 1

    engine._enemy_turn(engine.state.actors["1013011"])

    assert seen == ["101301101"]
    summoned = [engine.state.actors[actor_id] for actor_id in expected_ids]
    assert all(state.alive and state.actor.summoner_id == "1013011" for state in summoned)
    assert sorted(state.actor.name for state in summoned) == [
        "Automaton Beetle", "Automaton Beetle", "Automaton Spider", "Automaton Spider"]


def test_rallying_howl_summon_inherits_current_and_max_hp(tmp_path):
    """Wooden Lupus：ConfigAI 召唤狈影，入场时继承召唤者当前 HP 与有效 Max HP."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2022050")
    assert [action["action_id"] for action in template["actions"]] == ["202205001", "202205002"]
    assert template["policy"]["sequence"] == ["202205002", "202205001"]
    assert template["policy"]["config"]["AIName"] == "Monster_RO_015"
    assert template["summons"][0]["max_hp_ratio"] == 1.0
    (tmp_path / "enemies").mkdir()
    for enemy_id in ("2022050", "2022051"):
        doc = template if enemy_id == "2022050" else generate_enemy_template(enemy_id)
        (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2022050", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "2022050" else None)
    engine.setup()
    enemy = engine.state.actors["2022050"]
    engine._apply_modifier_spec(enemy, {
        "modifier_id": "TEST_MAX_HP", "name": "测试生命", "modifier_type": "buff",
        "stat_effects": {"hp_pct": 0.5}, "duration": 2,
    }, enemy)
    owner_max_hp = engine.pipeline.effective_stats(enemy)["hp"]
    enemy.current_hp = owner_max_hp * 0.375
    runtime = engine._enemy_policy_state["2022050"]
    runtime["cooldown_left"] = {}
    runtime.setdefault("dynamic_values", {})["AIFlag"] = 2

    engine._enemy_turn(enemy)

    assert seen == ["202205002"]
    summoned = engine.state.actors["2022051__2022050_s1__2022050"]
    assert summoned.alive and summoned.actor.summoner_id == "2022050"
    assert math.isclose(engine.pipeline.effective_stats(summoned)["hp"], owner_max_hp, rel_tol=1e-9)
    assert math.isclose(summoned.current_hp, enemy.current_hp, rel_tol=1e-9)


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


@pytest.mark.parametrize(("enemy_id", "skill_id", "semantic_name"), [
    ("1023011", "102301106", "Augury of Fireburst"),
    ("3003011", "300301103", "Ignite Stove"),
    ("3025011", "302501105", "Accrescendo"),
    ("4013014", "401301405", "Resembling Furious Lion"),
    ("4013016", "401301603", "Resembling Furious Lion"),
    ("8024010", "802401006", "Ready Order"),
    ("8024012", "802401206", "Ready Order"),
    ("1005013", "100501307", "The Creation's Prelude"),
    ("1005014", "100501406", "The Creation's Prelude"),
    ("1013012", "101301204", "Overcombust Order"),
    ("1013013", "101301304", "Overcombust Order"),
    ("1013014", "101301404", "Overcombust Order"),
])
def test_linked_charge_advances_to_next_action(tmp_path, enemy_id, skill_id, semantic_name):
    """无附加效果的蓄力 ID 可带关联参数，仍按序列推进下一行动."""
    from hsr_nous.adapters.template_generator import _enemy_timed_charge_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == semantic_name)
    action = _enemy_timed_charge_action(raw, semantic)
    assert action["target_type"] == "self"
    compiled = _compiled(tmp_path, [action, _action("next")], {
        "sequence": [skill_id, "next"], "cooldown": {}, "initial_cooldown": {},
    })
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = _watch_enemy_actions(engine)
    _run_enemy_turns(engine, 2)
    assert seen == [skill_id, "next"]


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


def test_shield_reflect_bug_directly_triggers_pierce(tmp_path):
    """Silvermane Lieutenant (Bug)：无标记选择器，受击直接以 Pierce 反击."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("1003011")
    assert [action["action_id"] for action in template["actions"]] == [
        "100301101", "100301102", "100301103", "100301104", "100301105"]
    assert template["policy"]["config"]["AIName"] == "Monster_RO_015"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1003011.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "1003011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1003011":
            seen.append((payload["action_id"], payload.get("target")))

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    enemy = engine.state.actors["1003011"]
    hero = engine.state.actors["hero"]
    runtime = engine._enemy_policy_state["1003011"]
    runtime["cooldown_left"] = {}
    runtime.setdefault("dynamic_values", {})["W1_Soldier03_00_AICounter"] = 4

    engine._enemy_turn(enemy)
    assert seen == [("100301103", "1003011")]
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert seen[-1] == ("100301102", "hero")
    assert "ENEMY_100301103_COUNTER" not in enemy.modifiers
    assert "MMonster_W1_Soldier03_00_ReturnAttackTarget" not in hero.modifiers


def test_outrage_and_dominate_turn_target_sides(tmp_path):
    """Twig of Wintry Wind：暴怒普攻对立阵营；支配普攻其他同阵营友方."""
    from dataclasses import replace
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.scheduler import EXTRA_NORMAL

    template = generate_enemy_template("2022070")
    assert template["policy"]["config"]["AIName"] == "Monster_W2_Xuanlu_01"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2022070.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id, spd, taunt in (("h1", 50, 500), ("h2", 1, 100)):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": spd,
                           "max_energy": 100, "taunt": taunt},
            "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 1.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        })
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2022070", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        seen.append((payload["actor"], payload["action_id"], payload["target"]))

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    for _ in range(100):
        engine.step()
        if any(actor == "2022070" for actor, _action, _target in seen):
            break
    assert seen[-1] == ("2022070", "202207001", "h1")
    h1 = engine.state.actors["h1"]
    h2 = engine.state.actors["h2"]
    enemy = engine.state.actors["2022070"]
    assert "ENEMY_OUTRAGE" in h1.modifiers
    enemy_hp = enemy.current_hp
    h2_hp = h2.current_hp

    engine._run_turn(h1, EXTRA_NORMAL)
    assert seen[-1] == ("h1", "h1_basic", "2022070")
    assert enemy.current_hp < enemy_hp
    assert h2.current_hp == h2_hp

    h1.modifiers["ENEMY_DOMINATE"] = replace(
        h1.modifiers.pop("ENEMY_OUTRAGE"),
        modifier_id="ENEMY_DOMINATE", name="Dominated", control_kind="dominate")
    enemy_hp = enemy.current_hp
    engine._run_turn(h1, EXTRA_NORMAL)
    assert seen[-1] == ("h1", "h1_basic", "h2")
    assert h2.current_hp < h2_hp
    assert enemy.current_hp == enemy_hp


def test_wintry_wind_illusion_outrage_also_applies_wind_shear(tmp_path):
    """Twig of Wintry Wind RL：专属 AI 执行 120% 怒噪，并附加可跳伤风化."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2022071")
    assert template["policy"]["config"]["AIName"] == "Monster_W2_Xuanlu_01"
    assert template["actions"][0]["scaling"] == [{"atk": 1.2}]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2022071.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2022071", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "2022071" else None)
    engine.setup()
    for _ in range(40):
        engine.step()
        if seen:
            break
    assert seen == ["202207101"]

    hero = engine.state.actors["hero"]
    outrage = hero.modifiers["ENEMY_OUTRAGE"]
    assert outrage.control_kind == "outrage" and outrage.duration == 2
    wind_shear = hero.modifiers["ENEMY_202207101_WIND_SHEAR"]
    assert wind_shear.stacks == 1 and wind_shear.max_stack == 5
    assert wind_shear.dot_ratio == 0.5 and wind_shear.duration == 2
    hp_before_tick = hero.current_hp
    engine._tick_dots(hero)
    assert hero.current_hp < hp_before_tick


def test_fire_of_vengeance_splits_total_damage_evenly(tmp_path):
    """Black Tide's Corroded Axe：1400% ATK 总伤在三目标间均分."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.structured_log import StructuredLogger

    template = generate_enemy_template("4032030")
    assert [a["action_id"] for a in template["actions"]] == ["403203001", "403203002"]
    assert template["policy"]["config"]["AIName"] == "Monster_W2_Valkyrie01_02"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4032030.yaml").write_text(
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
        "enemies": [{"enemy_template": "4032030", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    action = next(a for a in compiled.actions_by_actor["4032030"] if a.action_id == "403203002")
    assert action.split == "even"
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    logger = StructuredLogger(engine)
    engine.setup()
    engine._execute_action(engine.state.actors["4032030"], action)
    damage = {}
    for entry in logger.entries:
        if entry.get("event_type") == "damage" and entry.get("source_id") == "4032030":
            damage[entry["target_id"]] = entry["damage"]
    assert set(damage) == {"h1", "h2", "h3"} and damage["h1"] > 0
    assert math.isclose(damage["h1"], damage["h2"], rel_tol=1e-9)
    assert math.isclose(damage["h1"], damage["h3"], rel_tol=1e-9)


def test_focused_charge_buffs_friendly_team(tmp_path):
    """Mask of No Thought：Focused Charge 给全体友方加攻 30%，含自身."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("8001030")
    assert template["policy"]["config"]["AIName"] == "Monster_XP_Minion03_00"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8001030.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8001030", "level": 80},
                    {"enemy_template": "1002011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["8001030"]
    other = engine.state.actors["1002011"]
    base_atk = enemy.actor.stats.atk
    other_base_atk = other.actor.stats.atk
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "8001030":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    for _ in range(100):
        engine.step()
        if len(seen) == 2:
            break
    assert seen == ["800103002", "800103001"]
    assert "ENEMY_800103002_FOCUSED_CHARGE" in enemy.modifiers
    assert "ENEMY_800103002_FOCUSED_CHARGE" in other.modifiers
    assert math.isclose(engine.pipeline.effective_stats(enemy)["atk"], base_atk * 1.3, rel_tol=1e-9)
    assert math.isclose(engine.pipeline.effective_stats(other)["atk"], other_base_atk * 1.3, rel_tol=1e-9)


def test_energy_burst_on_kill_restores_team_energy(tmp_path):
    """Mask of No Thought 被击杀时，Energy Burst 给全队恢复 15 能量."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("8001030")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8001030.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 100.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8001030", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["8001030"]
    enemy.current_hp = 1.0
    hero = engine.state.actors["hero"]
    hero.current_energy = 10.0
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert not enemy.alive
    assert hero.current_energy == 25.0


def test_living_eternal_flame_without_active_ai(tmp_path):
    """专属 AI 未收编不丢被动：Furiae Philosopher 死亡仍给击杀者增益."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4012023")
    assert template["actions"] == []
    assert any(h["event"] == "on_kill" for h in template["hooks"])
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4012023.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 100.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "4012023", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["4012023"]
    enemy.current_hp = 1.0
    hero = engine.state.actors["hero"]
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert not enemy.alive
    modifier = hero.modifiers["ENEMY_LIVING_ETERNAL_FLAME"]
    assert modifier.stat_effects == {"spd_pct": 0.3, "all_dmg": 0.3}
    assert modifier.duration == 2
    assert engine.pipeline.effective_stats(hero)["spd"] == pytest.approx(65.0)


@pytest.mark.parametrize("enemy_id", ["2012010", "201201003"])
def test_candle_flame_on_kill_damages_and_def_shreds_friendlies(tmp_path, enemy_id):
    """Illumination Dragonfish：死亡时伤害其他友方并施加 30% 减防."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template(enemy_id)
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 100, "max_toughness": 30},
        "actions": [_action("dummy_basic")],
    }
    (tmp_path / "enemies" / "dummy.yaml").write_text(
        yaml.safe_dump(dummy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 100.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": enemy_id, "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors[enemy_id]
    dummy_state = engine.state.actors["dummy"]
    enemy.current_hp = 1.0
    old_hp = dummy_state.current_hp

    engine._execute_action(engine.state.actors["hero"], compiled.actions_by_actor["hero"][0])

    assert not enemy.alive and dummy_state.current_hp < old_hp
    modifier = dummy_state.modifiers["ENEMY_201201002_CANDLE_FLAME"]
    assert modifier.stat_effects == {"def_pct": -0.3} and modifier.duration == 2
    assert engine.pipeline.effective_stats(dummy_state)["def_"] == pytest.approx(700.0)


@pytest.mark.parametrize(("enemy_id", "modifier_id", "expected_stacks", "expected_vulnerability"), [
    ("8024011", "ENEMY_802401109_ENTOMON_EULOGY", 2, 0.2),
    ("8022030", "ENEMY_802203002_DECAY_EULOGY", 1, 0.1),
])
def test_eulogy_on_kill_applies_vulnerability_stacks(
        tmp_path, enemy_id, modifier_id, expected_stacks, expected_vulnerability):
    """Entomon/Decay Eulogy：死亡反噬并按原文层数给友方易伤."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template(enemy_id)
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 100, "max_toughness": 30},
        "actions": [_action("dummy_basic")],
    }
    (tmp_path / "enemies" / "dummy.yaml").write_text(
        yaml.safe_dump(dummy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 100.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": enemy_id, "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors[enemy_id]
    dummy_state = engine.state.actors["dummy"]
    enemy.current_hp = 1.0
    old_hp = dummy_state.current_hp

    engine._execute_action(engine.state.actors["hero"], compiled.actions_by_actor["hero"][0])

    assert not enemy.alive and dummy_state.current_hp < old_hp
    modifier = dummy_state.modifiers[modifier_id]
    assert modifier.stacks == expected_stacks and modifier.duration == 3 and modifier.max_stack == 10
    assert engine.pipeline.effective_stats(dummy_state)["vulnerability"] == pytest.approx(
        expected_vulnerability)


def test_core_rupture_hits_marked_target_and_grants_energy(tmp_path):
    """Seeding Core 标记后，Core Rupture 死亡雷伤、回能并清除标记."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2022020")
    assert [a["action_id"] for a in template["actions"]] == ["202202001", "202202002"]
    assert template["policy"]["config"]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2022020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 100.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2022020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2022020"]
    hero = engine.state.actors["hero"]
    seed = next(a for a in compiled.actions_by_actor["2022020"] if a.action_id == "202202001")
    engine._execute_action(enemy, seed)
    engine.bus.emit("on_action", {
        "actor": "2022020", "action_type": "skill", "action_id": "202202001",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    marker_id = "ENEMY_202202001_SPUR"
    assert hero.modifiers[marker_id].source_id == "2022020"
    enemy.current_hp = 1.0
    hero.current_energy = 10.0
    hp_before = hero.current_hp
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert not enemy.alive
    assert hero.current_hp < hp_before
    assert hero.current_energy == 25.0
    assert marker_id not in hero.modifiers


def test_unstable_forcefield_barrier_nullifies_one_hit(tmp_path):
    """Automaton Beetle 的 Barrier 抵消下一次攻击伤害，随后攻击正常扣血."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("1012030")
    template["policy"]["initial_cooldown"] = {}
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1012030.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "1012030", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1012030" and payload.get("action_id") == "101203001":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    for _ in range(10):
        engine.step()
        if seen:
            break
    assert seen == ["101203001"]
    enemy = engine.state.actors["1012030"]
    hero = engine.state.actors["hero"]
    barrier_id = "ENEMY_101203001_BARRIER"
    assert barrier_id in enemy.modifiers
    enemy.current_hp = 1e9
    hp_before = enemy.current_hp
    hero_action = compiled.actions_by_actor["hero"][0]
    engine._execute_action(hero, hero_action)
    assert enemy.current_hp == hp_before
    assert barrier_id not in enemy.modifiers
    engine._execute_action(hero, hero_action)
    assert enemy.current_hp < hp_before


def test_tremble_retriggers_shock_without_consuming_duration(tmp_path):
    """Soulhook Sovereign 攻击 Shocked 目标后额外结算 Shock，持续回合不减少."""
    from hsr_nous.adapters.template_generator import _enemy_direct_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    action = _enemy_direct_action(
        get_enemy_skills("2004014")[2], get_enemy_mechanics("Soulhook Sovereign")["skills"][2])
    template = generate_enemy_template("2004014")
    template.update({
        "actions": [action],
        "policy": {"sequence": ["200401403"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2004014.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2004014", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2004014"]
    hero = engine.state.actors["hero"]
    engine._apply_modifier_spec(hero, {
        "modifier_id": "TEST_SHOCK", "name": "Shock", "modifier_type": "dot",
        "dot_element": "thunder", "dot_ratio": 0.5, "duration": 3, "dispellable": True,
    }, enemy)
    seen = []
    retriggered = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "2004014" and payload.get("action_id") == "200401403":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.bus.subscribe(
        "on_dot_retrigger", lambda _et, payload, _ctx: retriggered.append(payload["modifier_id"]))
    for _ in range(10):
        retriggered.clear()
        engine.step()
        if seen:
            break
    assert seen == ["200401403"]
    assert retriggered == ["TEST_SHOCK"]
    assert hero.modifiers["TEST_SHOCK"].duration == 3


@pytest.mark.parametrize(("enemy_id", "skill_id"), [("2004011", "200401107"), ("2004012", "200401207")])
def test_tremble_accepts_singular_cause_wording(enemy_id, skill_id):
    """Tremble 的 directly cause 单数措辞也映射到同一 Shock 引爆."""
    from hsr_nous.adapters.template_generator import _enemy_tremble_passive
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Tremble")
    hooks = _enemy_tremble_passive(raw, semantic)
    assert len(hooks) == 1
    assert hooks[0]["effects"] == [{
        "effect_type": "trigger_dot", "target": "$event.target", "dot_element": "thunder",
    }]


def test_war_gear_retriggers_wind_shear(tmp_path):
    """War Gear 命中已有 Wind Shear 的目标后立即追加一次 DoT."""
    from hsr_nous.adapters.template_generator import _enemy_war_gear_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    action, hook = _enemy_war_gear_action(
        get_enemy_skills("8024011")[1], get_enemy_mechanics("Swarm: True Sting")["skills"][1])
    template = generate_enemy_template("8024011")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["802401102"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8024011.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8024011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["8024011"]
    hero = engine.state.actors["hero"]
    engine._apply_modifier_spec(hero, {
        "modifier_id": "TEST_WIND_SHEAR", "name": "Wind Shear", "modifier_type": "dot",
        "dot_element": "wind", "dot_ratio": 0.5, "duration": 3, "dispellable": True,
    }, enemy)
    retriggered = []
    engine.bus.subscribe(
        "on_dot_retrigger", lambda _et, payload, _ctx: retriggered.append(payload["modifier_id"]))
    engine._execute_action(enemy, compiled.actions_by_actor["8024011"][0])
    engine.bus.emit("on_action", {
        "actor": "8024011", "action_type": "skill", "action_id": "802401102",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert retriggered == ["TEST_WIND_SHEAR"]
    assert hero.modifiers["TEST_WIND_SHEAR"].duration == 3


def test_sweep_left_and_right_hit_three_consecutive_targets(tmp_path):
    """Sweep 从左右两端各取三个连续目标，并逐目标恢复能量."""
    from hsr_nous.adapters.template_generator import _enemy_sweep_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    raw = get_enemy_skills("4013010")
    semantics = get_enemy_mechanics("Furiae Praetor")["skills"]
    left, left_hook = _enemy_sweep_action(raw[0], semantics[0])
    right, right_hook = _enemy_sweep_action(raw[1], semantics[1])
    template = generate_enemy_template("4013010")
    template.update({
        "actions": [left, right], "hooks": [left_hook, right_hook],
        "policy": {"sequence": ["401301001"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4013010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id in ("h1", "h2", "h3", "h4"):
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
        "enemies": [{"enemy_template": "4013010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    for action_id, expected in (("401301001", ["h1", "h2", "h3"]),
                                ("401301002", ["h4", "h3", "h2"])):
        engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        engine.setup()
        hits = []
        engine.bus.subscribe(
            "after_being_hit", lambda _et, payload, _ctx: hits.append(payload["target"]))
        action = next(a for a in compiled.actions_by_actor["4013010"] if a.action_id == action_id)
        engine._execute_action(engine.state.actors["4013010"], action)
        engine.bus.emit("on_action", {
            "actor": "4013010", "action_type": "skill", "action_id": action_id,
            "target_type": "self", "target": "4013010", "sp_consumed": 0, "actor_type": "monster",
        }, engine.state)
        assert hits == expected
        for actor_id in ("h1", "h2", "h3", "h4"):
            assert engine.state.actors[actor_id].current_energy == (10.0 if actor_id in expected else 0.0)

    raw_bug = get_enemy_skills("5013012")
    semantics_bug = get_enemy_mechanics("Rocking Rebel (Bug)")["skills"]
    for index, expected in ((0, ["h1", "h2", "h3"]), (1, ["h4", "h3", "h2"])):
        action, hook = _enemy_sweep_action(raw_bug[index], semantics_bug[index])
        action_id = action["action_id"]
        template_bug = generate_enemy_template("5013012")
        template_bug.update({
            "actions": [action], "hooks": [hook],
            "policy": {"sequence": [action_id], "cooldown": {}, "initial_cooldown": {}},
        })
        (tmp_path / "enemies" / "5013012.yaml").write_text(
            yaml.safe_dump(template_bug, allow_unicode=True, sort_keys=False), encoding="utf-8")
        stage_bug = {"stage": {
            "enemies": [{"enemy_template": "5013012", "level": 80}],
            "termination": {"mode": "fixed_av", "max_action_value": 1000},
        }}
        compiled_bug = compile_encounter(build, stage_bug, template_roots=[str(tmp_path)])
        engine = CombatEngine.from_compiled(compiled_bug, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        engine.setup()
        hits = []
        engine.bus.subscribe(
            "after_being_hit", lambda _et, payload, _ctx: hits.append(payload["target"]))
        engine._execute_action(
            engine.state.actors["5013012"], compiled_bug.actions_by_actor["5013012"][0])
        engine.bus.emit("on_action", {
            "actor": "5013012", "action_type": "skill", "action_id": action_id,
            "target_type": "self", "target": "5013012", "sp_consumed": 0, "actor_type": "monster",
        }, engine.state)
        assert hits == expected
        assert hook["effects"][0]["scaling_atk"] == 2.8


def test_expedite_verdict_break_swaps_damage_modifiers(tmp_path):
    """Expedite Verdict：击破后撤下减伤、开启易伤，并推条和自伤."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4064010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4064010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 10, "toughness_scope": "all", "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "4064010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["4064010"]
    hero = engine.state.actors["hero"]
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"].get("dmg_reduction", 0.0) == 0.5
    assert engine.pipeline.effective_stats(enemy)["vulnerability"] == 0.0
    enemy.current_hp = 1e12
    enemy.toughness = 1.0
    hp_before = enemy.current_hp
    handle = engine.scheduler.handle_of("4064010")
    remaining_before = engine.scheduler._remaining[handle]
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert enemy.broken
    assert enemy.current_hp < hp_before
    assert engine.scheduler._remaining[handle] > remaining_before
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"].get("dmg_reduction", 0.0) == 0.0
    assert engine.pipeline.effective_stats(enemy)["vulnerability"] == 0.5


def test_respite_counts_attacks_and_advances_at_threshold(tmp_path):
    """Respite By The Waters：常态五次、指定状态一次攻击后立即行动并清零."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4052010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4052010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "4052010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    for hits, empowered in ((5, False), (1, True)):
        engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        engine.setup()
        enemy = engine.state.actors["4052010"]
        hero = engine.state.actors["hero"]
        if empowered:
            engine._apply_modifier_spec(enemy, {
                "modifier_id": "405301001", "name": "405301001", "modifier_type": "buff",
                "duration": 0, "dispellable": False,
            }, enemy)
        action = compiled.actions_by_actor["hero"][0]
        for index in range(hits):
            engine._execute_action(hero, action)
            if index < hits - 1:
                assert enemy.resources["_respite_count"] == index + 1
        assert enemy.resources["_respite_count"] == 0.0
        assert engine.scheduler._remaining[engine.scheduler.handle_of("4052010")] == 0.0


def test_war_armor_break_extra_damage_and_turn_end_restore(tmp_path):
    """War Armor：逐击扣层、破甲回能推条、后续自伤及回合末复原."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4012010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4012010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "4012010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["4012010"]
    hero = engine.state.actors["hero"]
    action = compiled.actions_by_actor["hero"][0]
    enemy.current_hp = 1e12
    assert enemy.resources["_war_armor"] == 3.0
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["dmg_reduction"] == pytest.approx(0.1)
    for remaining in (2, 1):
        engine._execute_action(hero, action)
        assert enemy.resources["_war_armor"] == remaining
        assert hero.current_energy == 0.0
    hp_before_break = enemy.current_hp
    remaining_before = engine.scheduler._remaining[engine.scheduler.handle_of("4012010")]
    engine._execute_action(hero, action)
    assert enemy.resources["_war_armor"] == 0.0
    assert enemy.current_hp < hp_before_break
    assert engine.scheduler._remaining[engine.scheduler.handle_of("4012010")] > remaining_before
    assert hero.current_energy == 6.0
    assert "ENEMY_401201002_WAR_ARMOR_BREAKER" not in hero.modifiers
    hp_before_extra = enemy.current_hp
    engine._execute_action(hero, action)
    assert enemy.current_hp < hp_before_extra
    assert hero.current_energy == 6.0
    engine.bus.emit("on_turn_end", {"actor": "4012010"}, engine.state)
    assert enemy.resources["_war_armor"] == 3.0
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["dmg_reduction"] == pytest.approx(0.1)


def test_collision_third_orbit_armor_branches_and_strong_reverberation(tmp_path):
    """Collision of the Third Orbit：有甲震目标、无甲震自身，受击后转 40% 强震."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.pipeline import MODE_ROLL

    template = generate_enemy_template("4012010")
    assert template["policy"]["config"]["AIName"] == "WMonster_Template_AI"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4012010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "4012010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, initial_energy_ratio=0.0)
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "4012010" else None)

    class _SuccessRoll:
        @staticmethod
        def random():
            return 0.0

    engine.pipeline.rng = _SuccessRoll()
    engine.setup()
    enemy = engine.state.actors["4012010"]
    hero = engine.state.actors["hero"]
    hero_action = compiled.actions_by_actor["hero"][0]
    runtime = engine._enemy_policy_state["4012010"]
    runtime["cooldown_left"] = {}

    engine._enemy_turn(enemy)
    assert seen == ["401201001"]
    assert "MCommon_Unstable" in hero.modifiers
    assert "MCommon_Unstable_Monster" not in enemy.modifiers
    runtime["cooldown_left"] = {}
    engine._enemy_turn(enemy)
    assert "MCommon_Shake" in hero.modifiers
    assert "MCommon_Unstable" not in hero.modifiers

    enemy.resources["_war_armor"] = 0.0
    hero.modifiers.pop("MCommon_Shake", None)
    runtime["cooldown_left"] = {}
    engine._enemy_turn(enemy)
    assert "MCommon_Unstable_Monster" in enemy.modifiers
    engine._execute_action(hero, hero_action)
    strong = enemy.modifiers["MCommon_Shake_Monster"]
    assert strong.prevent_action and strong.duration == 1
    assert "MCommon_Unstable_Monster" not in enemy.modifiers


def test_inferno_stove_slow_and_attack_dot_stacks(tmp_path):
    """Inferno Stove：攻击减速，受击与 DoT 各累积一层 Stove Heating."""
    from hsr_nous.adapters.template_generator import _enemy_direct_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    action = _enemy_direct_action(
        get_enemy_skills("3003010")[0],
        get_enemy_mechanics("Dreamjolt Troupe's Beyond Overcooked")["skills"][0])
    template = generate_enemy_template("3003010")
    template.update({
        "actions": [action],
        "policy": {"sequence": ["300301001"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3003010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "3003010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3003010"]
    hero = engine.state.actors["hero"]
    enemy.current_hp = 1e12
    engine._execute_action(enemy, compiled.actions_by_actor["3003010"][0])
    engine.bus.emit("on_action", {
        "actor": "3003010", "action_type": "skill", "action_id": "300301001",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert hero.modifiers["ENEMY_300301007_SLOW"].stat_effects["spd_pct"] == -0.2
    assert enemy.resources["_stove_heating"] == 0.0
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert enemy.resources["_stove_heating"] == 1.0
    engine._apply_modifier_spec(enemy, {
        "modifier_id": "TEST_BURN", "name": "Burn", "modifier_type": "dot",
        "dot_element": "fire", "dot_ratio": 0.01, "duration": 2, "dispellable": True,
    }, hero)
    engine._tick_dots(enemy)
    assert enemy.resources["_stove_heating"] == 2.0


def test_corporeal_formula_stacks_vulnerability_on_state_change(tmp_path):
    """Corporeal Formula 每次模式切换叠加 50% 承伤提高."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4044010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4044010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "4044010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["4044010"]
    for index in (1, 2):
        engine.bus.emit("on_state_change", {
            "actor": "4044010", "from_state": "normal", "to_state": "evolution",
        }, engine.state)
        modifier = enemy.modifiers["ENEMY_404401013_CORPOREAL"]
        assert modifier.stacks == index
        assert engine.pipeline.effective_stats(enemy)["vulnerability"] == pytest.approx(0.5 * index)


def test_eternal_continuation_depletes_five_hp_bars(tmp_path):
    """Eternal Continuation：直伤/DoT/击破各扣 20% Max HP，五次后归零."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.state import Modifier

    template = generate_enemy_template("3012030")
    assert {hook["event"] for hook in template["hooks"]} == {"on_battle_start"}
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3012030.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "3012030", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3012030"]
    enemy.actor.stats.weakness = ["physical"]
    enemy.toughness = enemy.actor.stats.max_toughness = 30.0
    max_hp = engine.pipeline.effective_stats(enemy)["hp"]
    hero = engine.state.actors["hero"]
    basic = compiled.actions_by_actor["hero"][0]

    for expected in (0.8, 0.6):
        engine._execute_action(hero, basic, forced_target=enemy)
        assert enemy.current_hp == pytest.approx(max_hp * expected)
    engine._apply_modifier(enemy, Modifier(
        modifier_id="TEST_DOT", name="测试 DoT", modifier_type="dot",
        dot_element="ice", dot_ratio=0.01, dot_source_atk=1000.0, duration=2))
    engine._tick_dots(enemy)
    assert enemy.current_hp == pytest.approx(max_hp * 0.4)

    engine._execute_action(hero, basic, forced_target=enemy)
    assert enemy.current_hp == pytest.approx(0.0, abs=1e-6)


def test_eternal_recurrence_restores_hp_and_dispels_on_action(tmp_path):
    """Eternal Recurrence 进入 Grave Wound 回满 HP，下次行动解除."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4032060")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4032060.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "4032060", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["4032060"]
    enemy.current_hp = 1.0
    engine._apply_modifier_spec(enemy, {
        "modifier_id": "GRAVE_WOUND", "name": "Grave Wound", "modifier_type": "debuff",
        "duration": 0, "dispellable": False,
    }, enemy)
    assert enemy.current_hp == engine.pipeline.effective_stats(enemy)["hp"]
    engine.bus.emit("on_action", {
        "actor": "4032060", "action_type": "skill", "action_id": "probe",
        "target_type": "self", "target": "4032060", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert "GRAVE_WOUND" not in enemy.modifiers


def test_leviathan_damage_locked_until_parts_destroyed(tmp_path):
    """Leviathan 三个部件存活时免伤，全部离场后 actor_alive 基础 ID 放行."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("8015010")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8015010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 100.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    parts = []
    for actor_id in ("8013144__wave", "8012143__wave", "8012145__wave"):
        parts.append({"actor_id": actor_id, "name": actor_id,
                      "hp": 1e9, "atk": 0, "def": 1000, "spd": 100})
    stage = {"stage": {
        "enemies": [*parts, {"enemy_template": "8015010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    boss = engine.state.actors["8015010"]
    hero = engine.state.actors["hero"]
    action = compiled.actions_by_actor["hero"][0]
    boss.current_hp = 1e12
    engine._execute_action(hero, action, forced_target=boss)
    assert boss.current_hp == 1e12
    for part in parts:
        engine.state.actors[part["actor_id"]].alive = False
    engine._execute_action(hero, action, forced_target=boss)
    assert boss.current_hp < 1e12


def test_tyrant_never_takes_action(tmp_path):
    """Tyrant of the Vanquished 即使有有序技能也整场禁止行动."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4012060")
    assert [a["action_id"] for a in template["actions"]] == ["401206001"]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4012060.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "4012060", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _et, payload, _ctx: seen.append(payload.get("actor"))
        if payload.get("actor") == "4012060" else None)
    for _ in range(5):
        engine.step()
    assert seen == []
    assert engine.state.actors["4012060"].modifiers["ENEMY_401206001_NO_ACTION"].prevent_action


def test_channel_support_and_disrupt_switch(tmp_path):
    """下课增益、上课减益与受击频道切换使用同一 modifier 状态."""
    from hsr_nous.adapters.template_generator import _enemy_channel_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = get_enemy_skills("3002021")
    semantics = get_enemy_mechanics(get_monster_meta("3002021")["en"])["skills"]
    converted = [_enemy_channel_action(r, s) for r, s in zip(raw, semantics)]
    template = generate_enemy_template("3002021")
    template.update({
        "actions": [item[0] for item in converted], "hooks": [item[1] for item in converted],
        "policy": {"sequence": ["300202103"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002021.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "3002021", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                        initial_energy_ratio=0.0, initial_sp=3)
    engine.setup()
    enemy = engine.state.actors["3002021"]
    engine._apply_modifier_spec(enemy, {
        "modifier_id": "OFF_CLASS_CHANNEL", "name": "Off-Class Channel",
        "modifier_type": "buff", "singleton_group": "actor_state",
        "duration": 0, "dispellable": False,
    }, enemy)

    def _cast(action_id):
        action = next(a for a in compiled.actions_by_actor["3002021"] if a.action_id == action_id)
        engine._execute_action(enemy, action)
        engine.bus.emit("on_action", {
            "actor": "3002021", "action_type": "skill", "action_id": action_id,
            "target_type": action.target_type, "target": "hero",
            "sp_consumed": 0, "actor_type": "monster",
        }, engine.state)

    _cast("300202101")
    assert engine.state.skill_points == 5
    _cast("300202103")
    assert "CLASSROOM_CHANNEL" in engine.state.actors["3002021"].modifiers
    _cast("300202102")
    assert engine.state.skill_points == 4
    engine._execute_action(engine.state.actors["hero"], compiled.actions_by_actor["hero"][0])
    assert "OFF_CLASS_CHANNEL" in engine.state.actors["3002021"].modifiers
    assert "CLASSROOM_CHANNEL" not in engine.state.actors["3002021"].modifiers


def test_break_and_class_advance_both_sides(tmp_path):
    """Break 拉我方、Class 拉敌方，均按 50% 基础行动值生效."""
    from hsr_nous.adapters.template_generator import _enemy_channel_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = get_enemy_skills("3002041")
    semantics = get_enemy_mechanics(get_monster_meta("3002041")["en"])["skills"]
    converted = [_enemy_channel_action(r, s) for r, s in zip(raw, semantics)]
    template = generate_enemy_template("3002041")
    template.update({
        "actions": [item[0] for item in converted], "hooks": [item[1] for item in converted],
        "policy": {"sequence": ["300204103"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002041.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "3002041", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3002041"]
    engine._apply_modifier_spec(enemy, {
        "modifier_id": "OFF_CLASS_CHANNEL", "name": "Off-Class Channel",
        "modifier_type": "buff", "singleton_group": "actor_state",
        "duration": 0, "dispellable": False,
    }, enemy)

    def _cast(action_id):
        action = next(a for a in compiled.actions_by_actor["3002041"] if a.action_id == action_id)
        engine._execute_action(enemy, action)
        engine.bus.emit("on_action", {
            "actor": "3002041", "action_type": "skill", "action_id": action_id,
            "target_type": action.target_type, "target": "hero",
            "sp_consumed": 0, "actor_type": "monster",
        }, engine.state)

    hero_handle = engine.scheduler.handle_of("hero")
    enemy_handle = engine.scheduler.handle_of("3002041")
    hero_before = engine.scheduler._remaining[hero_handle]
    _cast("300204101")
    assert engine.scheduler._remaining[hero_handle] == hero_before - 5000.0
    _cast("300204103")
    enemy_before = engine.scheduler._remaining[enemy_handle]
    _cast("300204102")
    assert engine.scheduler._remaining[enemy_handle] == enemy_before - 5000.0


def test_banappiness_restores_half_max_energy(tmp_path):
    """Banappiness Holiday 在下课频道恢复目标 50% 最大能量."""
    from hsr_nous.adapters.template_generator import _enemy_channel_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = get_enemy_skills("3002011")
    semantics = get_enemy_mechanics(get_monster_meta("3002011")["en"])["skills"]
    converted = [_enemy_channel_action(r, s) for r, s in zip(raw, semantics)]
    template = generate_enemy_template("3002011")
    template.update({
        "actions": [item[0] for item in converted if item],
        "hooks": [item[1] for item in converted if item],
        "policy": {"sequence": ["300201103"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002011.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "3002011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3002011"]
    engine._apply_modifier_spec(enemy, {
        "modifier_id": "OFF_CLASS_CHANNEL", "name": "Off-Class Channel",
        "modifier_type": "buff", "singleton_group": "actor_state",
        "duration": 0, "dispellable": False,
    }, enemy)
    action = next(a for a in compiled.actions_by_actor["3002011"] if a.action_id == "300201101")
    engine._execute_action(enemy, action)
    engine.bus.emit("on_action", {
        "actor": "3002011", "action_type": "skill", "action_id": "300201101",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert engine.state.actors["hero"].current_energy == 50.0


def test_ironthorn_freeze_blocks_action_and_deals_delayed_damage(tmp_path):
    """Ironthorn 施加冻结与禁行动，目标回合开始追加一次延迟冰伤."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2004020")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2004020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "2004020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(
        build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2004020"]
    hero = engine.state.actors["hero"]
    action = next(a for a in compiled.actions_by_actor["2004020"] if a.action_id == "200402003")
    hits = []
    engine.bus.subscribe(
        "after_being_hit", lambda _et, payload, _ctx: hits.append(payload["action_id"]))
    engine._execute_action(enemy, action)
    engine.bus.emit("on_action", {
        "actor": "2004020", "action_type": "skill", "action_id": "200402003",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert hits == ["200402003"] * 5
    modifier = hero.modifiers["ENEMY_200402003_FREEZE"]
    assert modifier.control_kind == "freeze" and modifier.prevent_action
    hp_before = hero.current_hp
    engine.bus.emit("on_turn_start", {"actor": "hero"}, engine.state)
    assert hero.current_hp < hp_before


def test_ironthorn_omitted_values_use_five_hit_layout(tmp_path):
    """Ironthorn 省略全部数值时也按原始四槽与五段 20% 结算."""
    from hsr_nous.adapters.template_generator import _enemy_ironthorn_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2004023") if r["skill_id"] == "200402303")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2004023")["en"])["skills"]
                    if s["name"] == "Ironthorn")
    action, hooks = _enemy_ironthorn_action(raw, semantic)
    assert action["instances"] == 5 and action["scaling"][0]["atk"] == pytest.approx(0.6)
    assert action["toughness_dmg"] == 3
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["200402303"], "cooldown": {}, "initial_cooldown": {}},
        hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hits = []
    engine.bus.subscribe(
        "after_being_hit", lambda _et, payload, _ctx: hits.append(payload["action_id"]))
    engine._execute_action(engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0])
    engine.bus.emit("on_action", {
        "actor": "enemy", "action_type": "skill", "action_id": "200402303",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert hits == ["200402303"] * 5
    hero = engine.state.actors["hero"]
    assert "ENEMY_200402303_FREEZE" in hero.modifiers
    hp_before = hero.current_hp
    engine.bus.emit("on_turn_start", {"actor": "hero"}, engine.state)
    assert hero.current_hp < hp_before


@pytest.mark.parametrize(("enemy_id", "skill_id", "ratio"), [
    ("2004010", "200401001", 1.25),
    ("2004013", "200401301", 1.5),
])
def test_midnight_tumult_two_hits_and_omitted_layout(tmp_path, enemy_id, skill_id, ratio):
    """Midnight Tumult 两段各 50%；省略文本由原始四槽补齐."""
    from hsr_nous.adapters.template_generator import _enemy_midnight_tumult_action, _enemy_shock_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Midnight Tumult")
    if "Base Chance" in semantic["desc"]:
        action, hook = _enemy_shock_action(raw, semantic)
    else:
        action, hook = _enemy_midnight_tumult_action(raw, semantic)
    assert action["instances"] == 2 and action["scaling"][0]["atk"] == pytest.approx(ratio)
    assert action["toughness_dmg"] == 5
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hits = []
    engine.bus.subscribe(
        "after_being_hit", lambda _et, payload, _ctx: hits.append(payload["action_id"]))
    engine._execute_action(engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0])
    engine.bus.emit("on_action", {
        "actor": "enemy", "action_type": "skill", "action_id": skill_id,
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert hits == [skill_id] * 2
    modifier = engine.state.actors["hero"].modifiers[f"ENEMY_{skill_id}_SHOCK"]
    assert modifier.dot_ratio == 0.75 and modifier.duration == 3 and modifier.dot_base_chance == 1.0


@pytest.mark.parametrize("enemy_id", ["2004010", "2004013"])
def test_caressing_moonlight_third_hit_blast_and_shock(tmp_path, enemy_id):
    """Caressing Moonlight 前两段单体、第三段主邻伤害，副目标继承 Shock."""
    from hsr_nous.adapters.template_generator import _enemy_caressing_moonlight_action
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_detail, get_enemy_mechanics, get_enemy_skills, get_monster_meta)
    from hsr_nous.sim.state import Modifier

    skill_id = f"{enemy_id}02"
    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantics = get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
    semantic = next(s for s in semantics if s["name"] == "Caressing Moonlight")
    action, hook = _enemy_caressing_moonlight_action(
        raw, semantic, semantics, get_enemy_detail(enemy_id))
    assert [variant["target_type"] for variant in action["instance_variants"]] == [
        "single", "single", "blast"]
    assert action["scaling_blast"] == [{"atk": 2.0}]
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{
            "action_id": f"{actor_id}_basic", "name": "测试普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 0.0}],
            "energy_gain": 0,
        }],
    } for actor_id in ("h1", "h2")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._apply_modifier(engine.state.actors["h1"], Modifier(
        modifier_id="TEST_SHOCK", name="Shock", modifier_type="dot",
        dot_element="thunder", dot_ratio=0.75, duration=3))
    hits = []
    engine.bus.subscribe(
        "after_being_hit", lambda _et, payload, _ctx: hits.append(payload["target"]))
    engine._execute_action(engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0])

    assert hits == ["h1", "h1", "h1", "h2"]
    modifier = engine.state.actors["h2"].modifiers[f"ENEMY_{skill_id}_SHOCK"]
    assert modifier.dot_ratio == 0.75 and modifier.duration == 3 and modifier.dot_base_chance == 1.0


def test_happiness_charm_weighted_strong_reverberation(tmp_path):
    """Happiness Charm 按原始权重选第三项，Strong Reverberation 一回合且推条 25%."""
    from hsr_nous.adapters.template_generator import _enemy_happiness_charm_action
    from hsr_nous.sim.pipeline import MODE_ROLL
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("5012010") if r["skill_id"] == "501201002")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("5012010")["en"])["skills"]
                    if s["name"] == "Happiness Charm")
    action, hook = _enemy_happiness_charm_action(raw, semantic)
    options = hook["effects"][0]["options"]
    assert [option["weight"] for option in options] == [0.33, 0.33, 0.34]
    modifier_spec = options[2]["modifier"]
    assert modifier_spec["duration"] == 1
    assert modifier_spec["on_apply"] == [{"effect_type": "delay_action", "target": "self", "amount": 25.0}]
    base_raw = next(r for r in get_enemy_skills("5012011") if r["skill_id"] == "501201102")
    _base_action, base_hook = _enemy_happiness_charm_action(base_raw, semantic)
    assert all("weight" not in option for option in base_hook["effects"][0]["options"])
    enemy_doc = {
        "enemy_id": "enemy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 300, "max_toughness": 30},
        "weakness": [], "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["501201002"], "cooldown": {}, "initial_cooldown": {}},
    }
    dummy_doc = {
        "enemy_id": "dummy", "name": "假人二号", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 100, "max_toughness": 30},
        "weakness": [], "actions": [],
    }
    (tmp_path / "enemies").mkdir()
    for enemy_id, document in (("enemy", enemy_doc), ("dummy", dummy_doc)):
        (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 0.0}],
                "energy_gain": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "enemy", "level": 80}, {"enemy_template": "dummy", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_ROLL)
    engine.setup()

    class _ThirdChoice:
        @staticmethod
        def random():
            return 0.99

    engine.pipeline.rng = _ThirdChoice()
    before = engine.scheduler._remaining[engine.scheduler.handle_of("dummy")]
    engine._enemy_turn(engine.state.actors["enemy"])

    dummy = engine.state.actors["dummy"]
    modifier = dummy.modifiers["ENEMY_501201002_STRONG_REVERB"]
    assert modifier.prevent_action and modifier.duration == 1
    assert engine.scheduler._remaining[engine.scheduler.handle_of("dummy")] > before
    assert "ENEMY_501201002_STRONG_REVERB" not in engine.state.actors["enemy"].modifiers
    assert "ENEMY_501201002_STRONG_REVERB" not in engine.state.actors["hero"].modifiers


def test_horn_clash_compose_selector_prefers_entangled_target(tmp_path):
    """Gnaw Sting：AIComposeSelector 优先纠缠目标，后续 Horn Clash 再叠一层."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("8022030")
    assert template["policy"]["config"]["AIName"] == "WMonster_SW_Minion01_02_AI"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8022030.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id, taunt in (("h1", 500), ("h2", 100)):
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
        "enemies": [{"enemy_template": "8022030", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "8022030":
            seen.append(payload["target"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    taunt_changed = False
    for _ in range(100):
        engine.step()
        if seen and not taunt_changed:
            assert seen[0] == "h1"
            engine.state.actors["h1"].actor.stats.taunt = 0
            engine.state.actors["h2"].actor.stats.taunt = 1000
            taunt_changed = True
        if len(seen) == 2:
            break
    assert seen == ["h1", "h1"]
    modifier = engine.state.actors["h1"].modifiers["MCommon_Entangle"]
    assert modifier.control_kind == "entangle" and modifier.stacks == 2


def test_sawing_evil_sever_two_hits_and_maddening_config_ai(tmp_path):
    """Mara-Struck Warden：Maddened 选择 Sever，200% + 240% 两段后回到 Chop."""
    import math
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2022110")
    assert template["policy"]["config"]["AIName"] == "Monster_W2_Valkyrie01_01"
    sever = next(action for action in template["actions"] if action["action_id"] == "202211002")
    assert sever["instances"] == 2
    assert sever["instance_variants"] == [
        {"scaling": [{"atk": 2.0}], "toughness_dmg": 10},
        {"scaling": [{"atk": 2.4}], "toughness_dmg": 10},
    ]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2022110.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2022110", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    hits = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "2022110" else None)
    engine.bus.subscribe(
        "after_being_hit", lambda _event, payload, _ctx: hits.append(payload["amount"])
        if payload.get("action_id") == "202211002" else None)
    engine.setup()
    enemy = engine.state.actors["2022110"]
    assert "MMonster_W2_Valkyrie01_01_SkillP01_ComboAttack" in enemy.modifiers
    runtime = engine._enemy_policy_state["2022110"]
    runtime["cooldown_left"] = {}

    engine._enemy_turn(enemy)
    assert seen == ["202211002"]
    assert len(hits) == 2 and math.isclose(hits[1], hits[0] * 1.2, rel_tol=1e-9)

    enemy.modifiers.pop("MMonster_W2_Valkyrie01_01_SkillP01_ComboAttack")
    runtime["cooldown_left"] = {}
    engine._enemy_turn(enemy)
    assert seen[-1] == "202211001"


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


def test_suppressive_fire_omitted_values_use_upstream_params(tmp_path):
    """Suppressive Fire 省略文本按上游两槽结算 300% 伤害与 30% 推条."""
    from hsr_nous.adapters.template_generator import _enemy_delay_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("1004032") if r["skill_id"] == "100403204")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("1004032")["en"])["skills"]
                    if s["name"] == "Suppressive Fire")
    action, hook = _enemy_delay_action(raw, semantic)
    assert action["scaling"] == [{"atk": 3.0}]
    assert hook["effects"][0]["amount"] == 30.0
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["100403204"], "cooldown": {}, "initial_cooldown": {}},
        hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hero = engine.state.actors["hero"]
    old_hp = hero.current_hp
    old_remaining = engine.scheduler._remaining[engine.scheduler.handle_of("hero")]
    engine._enemy_turn(engine.state.actors["enemy"])
    assert hero.current_hp < old_hp
    assert engine.scheduler._remaining[engine.scheduler.handle_of("hero")] > old_remaining


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
    melt = enemy.modifiers["ENEMY_102301003_MELT"]
    assert melt.stacks == 2  # 首次挂灼烧不叠；扩散与飞舞烬火命中已灼烧目标各叠一层
    assert math.isclose(engine.pipeline.effective_stats(enemy)["dmg_bonus"]["all"], 0.12, rel_tol=1e-9)

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
            modifier = engine.state.actors["h2"].modifiers["MCommon_Entangle"]
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
    modifier = hero.modifiers["MCommon_Entangle"]
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
    modifier = engine.state.actors[targets["801202001"]].modifiers["MMonster_AML_Minion03_00_Target"]
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


def test_heavens_fall_bonus_damage_and_dispels_strong(tmp_path):
    """Heaven's Fall 对 Strong 目标追加物伤并解除 Strong，倍率随变体对账."""
    from hsr_nous.adapters.template_generator import _enemy_heavens_fall_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    variant, variant_hook = _enemy_heavens_fall_action(
        get_enemy_skills("2013021")[6], get_enemy_mechanics("Aurumaton Spectral Envoy (Bug)")["skills"][4])
    assert variant["scaling"] == [{"atk": 2.8}]
    assert variant_hook["effects"][0]["scaling_atk"] == 2.8
    template = generate_enemy_template("2013020")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2013020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "2013020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2013020"]
    hero = engine.state.actors["hero"]
    engine._apply_modifier_spec(hero, {
        "modifier_id": "ENEMY_201302002_STRONG_REVERB", "name": "Strong Reverberation",
        "modifier_type": "debuff", "debuff_kind": "control",
        "control_kind": "strong_reverberation", "prevent_action": True,
        "duration": 1, "dispellable": True,
    }, enemy)
    hits = []
    engine.bus.subscribe(
        "after_being_hit", lambda _et, payload, _ctx: hits.append(payload["target"])
        if payload["target"] == "hero" else None)
    action = next(a for a in compiled.actions_by_actor["2013020"] if a.action_id == "201302006")
    engine._execute_action(enemy, action)
    engine.bus.emit("on_action", {
        "actor": "2013020", "action_type": "skill", "action_id": "201302006",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert len(hits) == 2
    assert "ENEMY_201302002_STRONG_REVERB" not in hero.modifiers


def test_soul_warrant_locks_strong_target(tmp_path):
    """Soul Warrant 锁定 Strong 目标，后续 Heaven's Fall 不再选错人."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2013020")
    assert template["policy"]["config"]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2013020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id in ("h1", "h2"):
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
        "enemies": [{"enemy_template": "2013020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2013020"]
    engine._apply_modifier_spec(engine.state.actors["h1"], {
        "modifier_id": "ENEMY_201302002_STRONG_REVERB", "name": "Strong Reverberation",
        "modifier_type": "debuff", "debuff_kind": "control",
        "control_kind": "strong_reverberation", "prevent_action": True,
        "duration": 1, "dispellable": True,
    }, enemy)
    warrant = next(a for a in compiled.actions_by_actor["2013020"] if a.action_id == "201302004")
    engine._execute_action(enemy, warrant)
    engine.bus.emit("on_action", {
        "actor": "2013020", "action_type": "skill", "action_id": "201302004",
        "target_type": "aoe", "target": "h1", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert "ENEMY_201302004_LOCK_ON" in engine.state.actors["h1"].modifiers
    assert "ENEMY_201302004_LOCK_ON" not in engine.state.actors["h2"].modifiers
    heaven = next(a for a in compiled.actions_by_actor["2013020"] if a.action_id == "201302006")
    engine._execute_action(enemy, heaven)
    assert engine._last_target_id == "h1"


def test_shrewd_bombing_twelve_hits_and_def_down(tmp_path):
    """Shrewd Bombing 产生十二段伤害，随后施加两回合 30% 减防."""
    from hsr_nous.adapters.template_generator import _enemy_shrewd_bombing_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    raw = get_enemy_skills("1014010")[3]
    semantic = get_enemy_mechanics("Svarog")["skills"][3]
    action, hook = _enemy_shrewd_bombing_action(raw, semantic)
    template = generate_enemy_template("1014010")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["101401004"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1014010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "1014010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    hits = []
    engine.bus.subscribe(
        "after_being_hit", lambda _et, payload, _ctx: hits.append(payload["target"])
        if payload["target"] == "hero" else None)
    enemy = engine.state.actors["1014010"]
    engine._execute_action(enemy, compiled.actions_by_actor["1014010"][0])
    assert len(hits) == 12
    engine.bus.emit("on_action", {
        "actor": "1014010", "action_type": "skill", "action_id": "101401004",
        "target_type": "aoe", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    modifier = engine.state.actors["hero"].modifiers["ENEMY_101401004_DEF_DOWN"]
    assert modifier.stat_effects["def_pct"] == -0.3 and modifier.duration == 2


def test_lock_on_target_overrides_taunt(tmp_path):
    """Lock On Target 使后续单体攻击越过更高嘲讽命中锁定者."""
    from hsr_nous.adapters.template_generator import _enemy_lock_on_target_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    raw = get_enemy_skills("1013020")[1]
    semantic = get_enemy_mechanics("Automaton Direwolf")["skills"][1]
    action, hook = _enemy_lock_on_target_action(raw, semantic)
    probe = {
        "action_id": "probe", "name": "probe", "action_type": "skill", "target_type": "single",
        "damage_type": "physical", "scaling": [{"atk": 0.0}],
        "toughness_dmg": 0, "energy_gain": 0,
    }
    template = generate_enemy_template("1013020")
    template.update({
        "actions": [action, probe], "hooks": [hook],
        "policy": {"sequence": ["101302002"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1013020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id, taunt in (("h1", 100), ("h2", 500)):
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
        "enemies": [{"enemy_template": "1013020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["1013020"]
    engine._execute_action(enemy, compiled.actions_by_actor["1013020"][0])
    engine.bus.emit("on_action", {
        "actor": "1013020", "action_type": "skill", "action_id": "101302002",
        "target_type": "single", "target": "h1", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert "ENEMY_101302002_LOCK_ON" in engine.state.actors["h1"].modifiers
    engine._execute_action(enemy, compiled.actions_by_actor["1013020"][1])
    assert engine._last_target_id == "h1"


def test_null_locks_all_targets(tmp_path):
    """Opportunistic Provocateur：Null 给全体目标施加 lock_on."""
    from hsr_nous.adapters.template_generator import _enemy_null_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("8015022") if r["skill_id"] == "801502213")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8015022")["en"])["skills"]
                    if s["name"] == "Null")
    action, hook = _enemy_null_action(raw, semantic)
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3")]
    compiled = _compiled(tmp_path, [action], team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()

    engine._enemy_turn(engine.state.actors["enemy"])

    for actor_id in ("h1", "h2", "h3"):
        modifier = engine.state.actors[actor_id].modifiers["ENEMY_801502213_LOCK_ON"]
        assert modifier.lock_on and modifier.name == "Null"


@pytest.mark.parametrize(("enemy_id", "skill_id"), [("1005010", "100501002"), ("1005012", "100501202")])
def test_harbinger_annihilation_locks_single_target(tmp_path, enemy_id, skill_id):
    """Harbinger of Annihilation 两变体都给单体目标施加 lock_on."""
    from hsr_nous.adapters.template_generator import _enemy_harbinger_annihilation_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Harbinger of Annihilation")
    action, hook = _enemy_harbinger_annihilation_action(raw, semantic)
    compiled = _compiled(tmp_path, [action], hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()

    engine._enemy_turn(engine.state.actors["enemy"])

    modifier = engine.state.actors["hero"].modifiers[f"ENEMY_{skill_id}_LOCK_ON"]
    assert modifier.lock_on and modifier.name == "Harbinger of Annihilation"


@pytest.mark.parametrize(("enemy_id", "skill_id"), [
    ("4064010", "406401003"),
    ("4064011", "406401103"),
    ("4064012", "406401203"),
    ("406401201", "406401203"),
])
def test_hemotort_glower_locks_boosts_spd_and_grants_extra_action(tmp_path, enemy_id, skill_id):
    """Hemotort Glower：单体锁定、SPD +50%，并给自身额外行动."""
    from hsr_nous.adapters.template_generator import _enemy_hemotort_glower_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Hemotort Glower")
    action, hook = _enemy_hemotort_glower_action(raw, semantic)
    compiled = _compiled(tmp_path, [action], hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    old_spd = engine.pipeline.effective_stats(enemy)["spd"]

    engine._enemy_turn(enemy)

    assert engine.state.actors["hero"].modifiers[f"ENEMY_{skill_id}_LOCK_ON"].lock_on
    assert enemy.modifiers[f"ENEMY_{skill_id}_SPD"].stat_effects == {"spd_pct": 0.5}
    assert engine.pipeline.effective_stats(enemy)["spd"] == pytest.approx(old_spd * 1.5)
    assert engine.scheduler._remaining[engine.scheduler.handle_of("enemy")] == 0.0


def test_hemotort_resonance_shared_power_and_config_ai_rotation(tmp_path):
    """Pheasant：Resonance 给同类共享 Power，随后双方均轮换到 Graze."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4062010")
    assert template["policy"]["config"]["AIName"] == "Monster_W4_Turkey_00"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4062010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "4062010", "actor_id": "p1", "level": 80},
                    {"enemy_template": "4062010", "actor_id": "p2", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") in {"p1", "p2"}:
            seen.append((payload["actor"], payload["action_id"]))

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    p1, p2 = engine.state.actors["p1"], engine.state.actors["p2"]
    for runtime in (engine._enemy_policy_state["p1"], engine._enemy_policy_state["p2"]):
        runtime["cooldown_left"] = {}

    engine._enemy_turn(p1)
    assert seen == [("p1", "406201002")]
    power_id = "MMonster_W4_Turkey_00_Skill02_Power"
    assert p1.modifiers[power_id].stacks == 1 and p2.modifiers[power_id].stacks == 1
    engine._enemy_turn(p1)
    assert seen[-1] == ("p1", "406201001")
    engine._enemy_turn(p2)
    assert seen[-1] == ("p2", "406201001")
    assert p1.modifiers[power_id].stacks == 1 and p2.modifiers[power_id].stacks == 1


@pytest.mark.parametrize(("enemy_id", "skill_id"), [
    ("4064010", "406401006"),
    ("4064012", "406401206"),
    ("406401201", "406401206"),
    ("406401202", "406401206"),
    ("406401203", "406401206"),
    ("4064013", "406401306"),
])
def test_name_culprit_locks_high_damage_target(tmp_path, enemy_id, skill_id):
    """Name the Culprit 各普通描述变体都锁定承受最高伤害的目标."""
    from hsr_nous.adapters.template_generator import _enemy_name_culprit_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Name the Culprit")
    action, hook = _enemy_name_culprit_action(raw, semantic)
    compiled = _compiled(tmp_path, [action], hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()

    engine._enemy_turn(engine.state.actors["enemy"])

    modifier = engine.state.actors["hero"].modifiers[f"ENEMY_{skill_id}_LOCK_ON"]
    assert modifier.lock_on and modifier.name == "Name the Culprit"


@pytest.mark.parametrize(("enemy_id", "skill_id"), [
    ("5014020", "501402005"), ("5014021", "501402105"), ("5014023", "501402305"),
])
def test_duty_prep_applies_toughness_lock(tmp_path, enemy_id, skill_id):
    """Duty Prep：Raring to Go 的 Weakness Protected 阻止后续削韧."""
    from dataclasses import replace

    from hsr_nous.adapters.template_generator import _enemy_duty_prep_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Duty Prep in Progress...")
    action, hook = _enemy_duty_prep_action(raw, semantic)
    compiled = _compiled(tmp_path, [action], hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]

    engine._enemy_turn(enemy)
    assert enemy.modifiers[f"ENEMY_{skill_id}_RARING_TO_GO"].toughness_lock
    old_toughness = enemy.toughness
    hero_action = replace(compiled.actions_by_actor["hero"][0], toughness_dmg=10, toughness_scope="all")
    engine._execute_action(engine.state.actors["hero"], hero_action)
    assert enemy.toughness == old_toughness


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


@pytest.mark.parametrize(("enemy_id", "skill_id"), [
    ("100403004", "100403002"),
    ("1004032", "100403202"),
])
def test_combat_redeployment_purifies_and_acts_now(tmp_path, enemy_id, skill_id):
    """Bronya Combat Redeployment 两种措辞都净化其他友方并使其立即行动."""
    from hsr_nous.adapters.template_generator import _enemy_combat_redeployment_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Combat Redeployment")
    action, hook = _enemy_combat_redeployment_action(raw, semantic)
    template = generate_enemy_template(enemy_id)
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
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
        "enemies": [{"enemy_template": enemy_id, "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    dummy_state = engine.state.actors["dummy"]
    engine._apply_modifier(dummy_state, Modifier(
        modifier_id="TEST_DEBUFF", name="测试减益", modifier_type="debuff", duration=2))
    assert "TEST_DEBUFF" in dummy_state.modifiers
    engine._enemy_turn(engine.state.actors[enemy_id])
    assert "TEST_DEBUFF" not in dummy_state.modifiers
    handle = engine.scheduler.handle_of("dummy")
    assert engine.scheduler._remaining[handle] == 0.0


def test_rallying_buffs_and_advances_other_friendlies(tmp_path):
    """Silvermane Lieutenant：Rallying 只强化并立即行动其他友方."""
    from hsr_nous.adapters.template_generator import _enemy_rallying_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("1003011") if r["skill_id"] == "100301105")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("1003011")["en"])["skills"]
                    if s["name"] == "Rallying")
    action, hook = _enemy_rallying_action(raw, semantic)
    template = generate_enemy_template("1003011")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["100301105"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1003011.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 100, "max_toughness": 30},
        "actions": [_action("dummy_basic")],
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
        "enemies": [{"enemy_template": "1003011", "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    lieutenant = engine.state.actors["1003011"]
    dummy_state = engine.state.actors["dummy"]
    old_atk = engine.pipeline.effective_stats(dummy_state)["atk"]

    engine._enemy_turn(lieutenant)

    modifier = dummy_state.modifiers["ENEMY_100301105_RALLYING"]
    assert modifier.stat_effects == {"atk_pct": 0.5} and modifier.duration == 1
    assert engine.pipeline.effective_stats(dummy_state)["atk"] == pytest.approx(old_atk * 1.5)
    assert engine.scheduler._remaining[engine.scheduler.handle_of("dummy")] == 0.0
    assert "ENEMY_100301105_RALLYING" not in lieutenant.modifiers


def test_marching_orders_buffs_all_friendlies_spd(tmp_path):
    """Bronya Marching Orders：包括自身在内的全体友方 SPD +50."""
    from hsr_nous.adapters.template_generator import _enemy_marching_orders_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("1004032") if r["skill_id"] == "100403205")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("1004032")["en"])["skills"]
                    if s["name"] == "Marching Orders")
    action, hook = _enemy_marching_orders_action(raw, semantic)
    template = generate_enemy_template("1004032")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["100403205"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1004032.yaml").write_text(
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
        "enemies": [{"enemy_template": "1004032", "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    bronya = engine.state.actors["1004032"]
    dummy_state = engine.state.actors["dummy"]
    old_spd = {actor_id: engine.pipeline.effective_stats(state)["spd"]
               for actor_id, state in (("1004032", bronya), ("dummy", dummy_state))}

    engine._enemy_turn(bronya)

    for actor_id, state in (("1004032", bronya), ("dummy", dummy_state)):
        modifier = state.modifiers["ENEMY_100403205_MARCHING_ORDERS"]
        assert modifier.stat_effects == {"spd": 50.0} and modifier.duration == 2
        assert engine.pipeline.effective_stats(state)["spd"] == old_spd[actor_id] + 50.0


@pytest.mark.parametrize(("enemy_id", "skill_id", "summon_template_id"), [
    ("3024030", "302403006", "8022012"),
    ("3024031", "302403106", "802201201"),
    ("3024032", "302403206", "802201201"),
])
def test_primal_hunger_buffs_only_own_juvenile_stings(tmp_path, enemy_id, skill_id, summon_template_id):
    """Swarm Nightmare：Primal Hunger 各变体只加速自己召唤的 Juvenile Sting."""
    from hsr_nous.adapters.template_generator import (
        _enemy_primal_hunger_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_detail, get_enemy_mechanics, get_enemy_skills, get_monster_meta)

    raw = next(s for s in get_enemy_skills(enemy_id) if s["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Primal Hunger")
    action, hook = _enemy_primal_hunger_action(
        raw, semantic, get_enemy_detail(enemy_id), get_monster_meta)
    template = generate_enemy_template(enemy_id)
    template.update({
        "actions": [action],
        "hooks": [
            {"event": "on_battle_start", "effects": [
                {"effect_type": "summon", "summon_id": "juvenile"}]},
            hook,
        ],
        "summons": [{"summon_id": "juvenile", "enemy_template": summon_template_id, "level": 80}],
        "policy": {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (tmp_path / "enemies" / f"{summon_template_id}.yaml").write_text(
        yaml.safe_dump(generate_enemy_template(summon_template_id),
                       allow_unicode=True, sort_keys=False), encoding="utf-8")
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
        "enemies": [
            {"enemy_template": enemy_id, "level": 80},
            {"enemy_template": summon_template_id, "actor_id": "other_juvenile", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(
        build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    owned = engine.state.actors[f"juvenile__{enemy_id}"]
    other = engine.state.actors["other_juvenile"]
    assert owned.actor.summoner_id == enemy_id
    owned_spd = engine.pipeline.effective_stats(owned)["spd"]
    other_spd = engine.pipeline.effective_stats(other)["spd"]

    engine._enemy_turn(engine.state.actors[enemy_id])

    modifier_id = f"ENEMY_{skill_id}_PRIMAL_HUNGER"
    assert owned.modifiers[modifier_id].stat_effects == {"spd": 20.0}
    assert owned.modifiers[modifier_id].duration == 2
    assert engine.pipeline.effective_stats(owned)["spd"] == owned_spd + 20.0
    assert modifier_id not in other.modifiers
    assert engine.pipeline.effective_stats(other)["spd"] == other_spd


def test_engender_buffs_summoner_atk(tmp_path):
    """Twig of Marple Leaf：Engender 只给召唤者提高 20% ATK，持续 2 回合."""
    from hsr_nous.adapters.template_generator import _enemy_engender_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2022080") if r["skill_id"] == "202208001")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2022080")["en"])["skills"]
                    if s["name"] == "Engender")
    action, hook = _enemy_engender_action(raw, semantic)
    template = generate_enemy_template("2022080")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["202208001"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2022080.yaml").write_text(
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
        "enemies": [
            {"enemy_template": "2022080", "actor_id": "twig", "level": 80},
            {"enemy_template": "2022080", "actor_id": "deer", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    twig = engine.state.actors["twig"]
    deer = engine.state.actors["deer"]
    twig.actor.summoner_id = "deer"
    old_atk = engine.pipeline.effective_stats(deer)["atk"]

    engine._enemy_turn(twig)

    modifier = deer.modifiers["MMonster_W2_Xuanlu_02_Buff"]
    assert modifier.stat_effects == {"atk_pct": 0.2} and modifier.duration == 2
    assert engine.pipeline.effective_stats(deer)["atk"] == pytest.approx(old_atk * 1.2)
    assert "MMonster_W2_Xuanlu_02_Buff" not in twig.modifiers


def test_marple_retaliation_config_ai_and_once_per_turn_counter(tmp_path):
    """Marple Leaf：ConfigAI 进入反击状态，CounterCheck 每回合只反击一次."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2022080")
    assert [action["action_id"] for action in template["actions"]] == [
        "202208001", "202208002", "202208003"]
    assert template["policy"]["config"]["AIName"] == "Monster_W2_Xuanlu_02"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2022080.yaml").write_text(
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
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "2022080", "actor_id": "twig", "level": 80},
                    {"enemy_template": "dummy", "actor_id": "deer"}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "twig":
            seen.append((payload["action_id"], payload.get("target")))

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    twig = engine.state.actors["twig"]
    deer = engine.state.actors["deer"]
    hero = engine.state.actors["hero"]
    twig.actor.summoner_id = "deer"
    runtime = engine._enemy_policy_state["twig"]
    runtime["cooldown_left"] = {}
    runtime.setdefault("dynamic_values", {})["AIFlag"] = 1

    engine._enemy_turn(twig)

    assert seen == [("202208002", "twig")]
    counter = twig.modifiers["MMonster_W2_Xuanlu_02_Counter"]
    assert counter.stacks == 1
    engine.bus.emit("on_turn_end", {"actor": "hero"}, engine.state)
    assert counter.stacks == 2

    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert seen[-1] == ("202208003", "hero")
    assert counter.stacks == 1
    counter_count = len(seen)
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert len(seen) == counter_count

    engine.bus.emit("on_turn_end", {"actor": "hero"}, engine.state)
    assert counter.stacks == 2
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])
    assert len(seen) == counter_count + 1 and seen[-1] == ("202208003", "hero")


def test_shine_meteors_applies_stormride_and_acts_after_turn(tmp_path):
    """流星铁鹰：给一个友方施加 Stormride，并在其回合结束立即行动."""
    from hsr_nous.adapters.template_generator import _enemy_shine_meteors_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("4022010") if r["skill_id"] == "402201002")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("4022010")["en"])["skills"]
                    if s["name"] == "Shine Like Meteors")
    action, hook = _enemy_shine_meteors_action(raw, semantic)
    template = generate_enemy_template("4022010")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["402201002"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4022010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 100, "max_toughness": 30},
        "actions": [_action("dummy_basic")],
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
        "enemies": [{"enemy_template": "dummy"}, {"enemy_template": "4022010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    dummy_state = engine.state.actors["dummy"]

    engine._execute_action(
        engine.state.actors["4022010"], compiled.actions_by_actor["4022010"][0], forced_target=dummy_state)
    engine.bus.emit("on_action", {
        "actor": "4022010", "action_type": "skill", "action_id": "402201002",
        "target_type": "ally_single", "target": "dummy", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)

    assert dummy_state.modifiers["ENEMY_402201002_STORMRIDE"].name == "Stormride"
    assert engine.scheduler._remaining[engine.scheduler.handle_of("dummy")] == 0.0
    assert "ENEMY_402201002_STORMRIDE" not in engine.state.actors["4022010"].modifiers


def test_daybreak_dispersal_removes_forcefield_and_lowers_quantum_res(tmp_path):
    """Daybreak Dispersal：解除力场，自挂 30% 易伤与 40% 量子抗性降低."""
    import math
    from hsr_nous.adapters.template_generator import (
        _enemy_daybreak_dispersal_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills
    from hsr_nous.sim.state import Modifier

    raw = next(s for s in get_enemy_skills("5013040") if s["skill_id"] == "501304005")
    semantic = next(s for s in get_enemy_mechanics(
        "Daybreak Squadron: Azurewing", weakness=[])["skills"]
        if s["name"] == "Daybreak Dispersal")
    action, hook = _enemy_daybreak_dispersal_action(raw, semantic)
    template = generate_enemy_template("5013040")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["501304005"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "5013040.yaml").write_text(
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
        "enemies": [{"enemy_template": "5013040", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["5013040"]
    engine._apply_modifier(enemy, Modifier(
        modifier_id="ENEMY_DAYBREAK_FORCEFIELD", name="Daybreak Forcefield",
        modifier_type="buff", duration=0))
    quantum_res = engine.pipeline._base_res("quantum", enemy)
    physical_res = engine.pipeline._base_res("physical", enemy)

    engine._enemy_turn(enemy)

    assert "ENEMY_DAYBREAK_FORCEFIELD" not in enemy.modifiers
    modifier = enemy.modifiers["ENEMY_501304005_DISHEARTENED"]
    assert modifier.stat_effects == {"vulnerability": 0.3, "res_quantum": -0.4}
    assert modifier.duration == 2
    assert math.isclose(
        engine.pipeline._base_res("quantum", enemy), quantum_res - 0.4, rel_tol=0, abs_tol=1e-9)
    assert engine.pipeline._base_res("physical", enemy) == physical_res


def test_direwolf_bleed_stacks_scale_max_hp_dot(tmp_path):
    """Automaton Direwolf：Bleed 每层为目标 Max HP 的 5%，重复施加叠至 10 层."""
    import math
    from hsr_nous.adapters.template_generator import _enemy_bleed_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    raw = next(s for s in get_enemy_skills("1013022") if s["skill_id"] == "101302205")
    semantic = next(s for s in get_enemy_mechanics("Automaton Direwolf (Complete)")["skills"]
                    if s["name"] == "Disintegration Order")
    action, hook = _enemy_bleed_action(raw, semantic)
    template = generate_enemy_template("1013022")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["101302205"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1013022.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 100000, "atk": 0, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "1013022", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["1013022"]
    hero = engine.state.actors["hero"]
    modifier_id = "ENEMY_101302205_BLEED"

    engine._enemy_turn(enemy)
    modifier = hero.modifiers[modifier_id]
    assert modifier.stacks == 1 and modifier.max_stack == 10 and modifier.duration == 2
    assert math.isclose(engine.pipeline.dot_tick_base(hero, modifier), 5000.0, rel_tol=1e-9)

    engine._enemy_turn(enemy)
    assert modifier.stacks == 2
    assert math.isclose(engine.pipeline.dot_tick_base(hero, modifier), 10000.0, rel_tol=1e-9)
    for _ in range(8):
        engine._enemy_turn(enemy)
    assert modifier.stacks == 10
    assert math.isclose(engine.pipeline.dot_tick_base(hero, modifier), 50000.0, rel_tol=1e-9)


def test_starfall_form_markers_replace_each_other(tmp_path):
    """Opportunistic Provocateur：Starfall 在 Abundance/Destruction 形态间切换."""
    from hsr_nous.adapters.template_generator import _enemy_starfall_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    semantics = get_enemy_mechanics("Opportunistic Provocateur")["skills"]
    actions = []
    hooks = []
    for skill_id, form in (("801502206", "Abundance"), ("801502207", "Destruction")):
        raw = next(s for s in get_enemy_skills("8015022") if s["skill_id"] == skill_id)
        semantic = next(s for s in semantics if s["name"].startswith("Starfall") and form in s["name"])
        action, hook = _enemy_starfall_action(raw, semantic)
        actions.append(action)
        hooks.append(hook)
    template = generate_enemy_template("8015022")
    template.update({
        "actions": actions, "hooks": hooks,
        "policy": {"sequence": ["801502206", "801502207"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8015022.yaml").write_text(
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
        "enemies": [{"enemy_template": "8015022", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["8015022"]

    engine._enemy_turn(enemy)
    assert "ENEMY_ABUNDANCE_FORM" in enemy.modifiers
    assert "ENEMY_DESTRUCTION_FORM" not in enemy.modifiers
    engine._enemy_turn(enemy)
    assert "ENEMY_DESTRUCTION_FORM" in enemy.modifiers
    assert "ENEMY_ABUNDANCE_FORM" not in enemy.modifiers


def test_enkindle_reapplication_stacks_and_scales_dot(tmp_path):
    """Blaze Out of Space：Enkindle 重复施加叠层，第二次 DoT 基数翻倍."""
    import math
    from hsr_nous.adapters.template_generator import _enemy_burn_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("8003021") if r["skill_id"] == "800302101")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8003021")["en"])["skills"]
                    if s["name"] == "Bellowing Inferno")
    action, hook = _enemy_burn_action(raw, semantic)
    template = generate_enemy_template("8003021")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["800302101"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8003021.yaml").write_text(
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
        "enemies": [{"enemy_template": "8003021", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["8003021"]
    hero = engine.state.actors["hero"]
    modifier_id = "ENEMY_800302101_ENKINDLE"

    engine._enemy_turn(enemy)
    modifier = hero.modifiers[modifier_id]
    assert modifier.stacks == 1
    first_base = engine.pipeline.dot_tick_base(hero, modifier)
    engine._enemy_turn(enemy)
    assert modifier.stacks == 2
    assert math.isclose(engine.pipeline.dot_tick_base(hero, modifier), first_base * 2, rel_tol=1e-9)


def test_surprise_channel_energy_and_switch(tmp_path):
    """Mr. Domescreen：Surprise 供能后切换 Fright，原频道技能随即不可用."""
    from hsr_nous.adapters.template_generator import _enemy_channel_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    semantics = get_enemy_mechanics(get_monster_meta("3002010")["en"])["skills"]
    actions = []
    hooks = []
    for index in (0, 2):
        action, hook = _enemy_channel_action(get_enemy_skills("3002010")[index], semantics[index])
        actions.append(action)
        hooks.append(hook)
    template = generate_enemy_template("3002010")
    template.update({
        "actions": actions, "hooks": hooks,
        "policy": {"sequence": ["300201001", "300201003"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002010.yaml").write_text(
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
        "enemies": [{"enemy_template": "3002010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3002010"]
    hero = engine.state.actors["hero"]
    engine._apply_modifier(enemy, Modifier(
        modifier_id="SURPRISE_CHANNEL", name="Surprise Channel", modifier_type="buff", duration=0))
    hero.current_energy = 10.0

    engine._enemy_turn(enemy)
    assert hero.current_energy == 60.0
    engine._enemy_turn(enemy)
    assert "SURPRISE_CHANNEL" not in enemy.modifiers
    assert "FRIGHT_CHANNEL" in enemy.modifiers
    assert engine._legal_with_available_if(enemy, compiled.actions_by_actor["3002010"]) == []


def test_startling_broadcast_consumes_max_energy_and_requires_fright(tmp_path):
    """Startling Broadcast：各自按 Max Energy 扣到 0，非 Fright Channel 不可施放."""
    from hsr_nous.adapters.template_generator import (
        _enemy_startling_broadcast_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    raw = get_enemy_skills("3002010")[1]
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("3002010")["en"])["skills"]
                    if s["name"] == "Startling Broadcast")
    action, hook = _enemy_startling_broadcast_action(raw, semantic)
    template = generate_enemy_template("3002010")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["300201002"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002010.yaml").write_text(
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
        "enemies": [{"enemy_template": "3002010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3002010"]
    hero = engine.state.actors["hero"]
    engine._apply_modifier(enemy, Modifier(
        modifier_id="FRIGHT_CHANNEL", name="Fright Channel", modifier_type="buff", duration=0))
    hero.current_energy = 80.0

    engine._enemy_turn(enemy)
    assert hero.current_energy == 60.0
    hero.current_energy = 10.0
    engine._enemy_turn(enemy)
    assert hero.current_energy == 0.0

    enemy.modifiers.pop("FRIGHT_CHANNEL")
    assert engine._legal_with_available_if(enemy, compiled.actions_by_actor["3002010"]) == []


def test_banascary_semester_consumes_flat_energy_and_requires_classroom(tmp_path):
    """Banascary Semester：定值扣能至 0，非 Classroom Channel 不可施放."""
    from hsr_nous.adapters.template_generator import (
        _enemy_banascary_semester_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    raw = get_enemy_skills("3002011")[1]
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("3002011")["en"])["skills"]
                    if s["name"] == "Banascary Semester")
    action, hook = _enemy_banascary_semester_action(raw, semantic)
    template = generate_enemy_template("3002011")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["300201102"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002011.yaml").write_text(
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
        "enemies": [{"enemy_template": "3002011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3002011"]
    hero = engine.state.actors["hero"]
    engine._apply_modifier(enemy, Modifier(
        modifier_id="CLASSROOM_CHANNEL", name="Classroom Channel", modifier_type="buff", duration=0))
    hero.current_energy = 80.0

    engine._enemy_turn(enemy)
    assert hero.current_energy == 65.0
    hero.current_energy = 10.0
    engine._enemy_turn(enemy)
    assert hero.current_energy == 0.0

    enemy.modifiers.pop("CLASSROOM_CHANNEL")
    assert engine._legal_with_available_if(enemy, compiled.actions_by_actor["3002011"]) == []


def test_saturation_cleaning_grants_punchline_once_per_action(tmp_path):
    """King Pom-Pom：Saturation Cleaning 的 AoE 只给队伍池发 5 笑点一次."""
    from hsr_nous.adapters.template_generator import (
        _enemy_saturation_cleaning_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("5014020") if r["skill_id"] == "501402006")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("5014020")["en"])["skills"]
                    if s["name"] == "Saturation Cleaning!")
    action, hook = _enemy_saturation_cleaning_action(raw, semantic)
    template = generate_enemy_template("5014020")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["501402006"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "5014020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id in ("h1", "h2"):
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
        "enemies": [{"enemy_template": "5014020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    before = engine.state.punchline

    engine._enemy_turn(engine.state.actors["5014020"])

    assert engine.state.punchline == before + 5.0


def test_windmill_defacer_grants_punchline_and_strong_reverberation(tmp_path):
    """Windmill Defacer：单次 Punchline +2，50% 强震禁行动并推条 20%."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("5012090")
    skill_id = "501209002"
    assert [action["action_id"] for action in template["actions"]] == ["501209001", skill_id]
    assert template["policy"].get("config")
    action = template["actions"][1]
    assert action["scaling"] == [{"atk": 3.5}]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        hooks=template["hooks"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    hits = []
    engine.bus.subscribe(
        "on_hp_decrease", lambda _event, payload, _ctx: hits.append(payload))
    engine.setup()
    enemy = engine.state.actors["enemy"]
    hero = engine.state.actors["hero"]
    handle = engine.scheduler.handle_of("hero")
    remaining_before = engine.scheduler._remaining[handle]
    engine._enemy_turn(enemy)

    assert len(hits) == 1 and hits[0]["amount"] > 0
    assert engine.state.punchline == 2.0
    modifier = hero.modifiers[f"ENEMY_{skill_id}_STRONG_REVERB"]
    assert modifier.prevent_action and modifier.duration == 1
    assert modifier.control_kind == "strong_reverberation"
    assert engine.scheduler._remaining[handle] == pytest.approx(remaining_before + 2000.0)


def test_insidious_agitation_requires_and_consumes_numeric_state(tmp_path):
    """Insidious Agitation：仅在 240320401 状态内可施放，施放后解除该状态."""
    from hsr_nous.adapters.template_generator import (
        _enemy_insidious_agitation_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    raw = next(r for r in get_enemy_skills("4032041") if r["skill_id"] == "403204103")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("4032041")["en"])["skills"]
                    if s["name"] == "Insidious Agitation")
    action, hook = _enemy_insidious_agitation_action(raw, semantic)
    template = generate_enemy_template("4032041")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["403204103"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4032041.yaml").write_text(
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
        "enemies": [{"enemy_template": "4032041", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["4032041"]
    engine._apply_modifier(enemy, Modifier(
        modifier_id="240320401", name="240320401", modifier_type="buff", duration=0))
    assert [a.action_id for a in engine._legal_with_available_if(
        enemy, compiled.actions_by_actor["4032041"])] == ["403204103"]

    engine._enemy_turn(enemy)

    assert "240320401" not in enemy.modifiers
    assert engine._legal_with_available_if(enemy, compiled.actions_by_actor["4032041"]) == []


def test_gnaw_heals_only_with_numeric_state(tmp_path):
    """Eclipse Wolftrooper：Gnaw 仅在 220320201 状态下自愈 40% Max HP."""
    import math
    from hsr_nous.adapters.template_generator import _enemy_gnaw_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    raw = next(r for r in get_enemy_skills("2032020") if r["skill_id"] == "203202001")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2032020")["en"])["skills"]
                    if s["name"] == "Gnaw")
    action, hook = _enemy_gnaw_action(raw, semantic)
    template = generate_enemy_template("2032020")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["203202001"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2032020.yaml").write_text(
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
        "enemies": [{"enemy_template": "2032020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2032020"]
    max_hp = engine.pipeline.effective_stats(enemy)["hp"]
    engine._apply_modifier(enemy, Modifier(
        modifier_id="220320201", name="220320201", modifier_type="buff", duration=0))
    enemy.current_hp = max_hp * 0.5

    engine._enemy_turn(enemy)
    assert math.isclose(enemy.current_hp, max_hp * 0.9, rel_tol=1e-9)

    engine._remove_modifier(enemy, "220320201", "test")
    enemy.current_hp = max_hp * 0.5
    engine._enemy_turn(enemy)
    assert math.isclose(enemy.current_hp, max_hp * 0.5, rel_tol=1e-9)


def test_rapturous_wind_stacks_only_yanqing_and_own_swords(tmp_path):
    """Yanqing：Rapturous Wind 只给自己与己方飞剑叠 Chilling Light 增伤."""
    from hsr_nous.adapters.template_generator import _enemy_rapturous_wind_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_detail, get_enemy_mechanics, get_enemy_skills, get_monster_meta)

    raw = next(r for r in get_enemy_skills("2004021") if r["skill_id"] == "200402101")
    semantic = next(s for s in get_enemy_mechanics(
        "Cloud Knight Lieutenant: Yanqing (Complete)", weakness=[])["skills"]
        if s["name"] == "Rapturous Wind")
    action, hook = _enemy_rapturous_wind_action(
        raw, semantic, get_enemy_detail("2004021"), get_monster_meta)
    template = generate_enemy_template("2004021")
    template.update({
        "actions": [action],
        "hooks": [
            {"event": "on_battle_start", "effects": [
                {"effect_type": "summon", "summon_id": "flying"}]},
            hook,
        ],
        "summons": [{"summon_id": "flying", "enemy_template": "200202001", "level": 80}],
        "policy": {"sequence": ["200402101"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2004021.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (tmp_path / "enemies" / "200202001.yaml").write_text(
        yaml.safe_dump(generate_enemy_template("200202001"), allow_unicode=True, sort_keys=False),
        encoding="utf-8")
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
        "enemies": [
            {"enemy_template": "2004021", "level": 80},
            {"enemy_template": "200202001", "actor_id": "other_sword", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2004021"]
    sword = engine.state.actors["flying__2004021"]
    other = engine.state.actors["other_sword"]
    owner_base = engine.pipeline.effective_stats(enemy)["dmg_bonus"].get("all", 0.0)
    sword_base = engine.pipeline.effective_stats(sword)["dmg_bonus"].get("all", 0.0)

    engine._enemy_turn(enemy)
    assert enemy.modifiers["ENEMY_CHILLING_LIGHT"].stacks == 1
    assert sword.modifiers["ENEMY_CHILLING_LIGHT"].stacks == 1
    assert "ENEMY_CHILLING_LIGHT" not in other.modifiers
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["all"] == owner_base + 0.1
    assert engine.pipeline.effective_stats(sword)["dmg_bonus"]["all"] == sword_base + 0.1

    engine._enemy_turn(enemy)
    assert enemy.modifiers["ENEMY_CHILLING_LIGHT"].stacks == 2
    assert sword.modifiers["ENEMY_CHILLING_LIGHT"].stacks == 2
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["all"] == owner_base + 0.2
    assert engine.pipeline.effective_stats(sword)["dmg_bonus"]["all"] == sword_base + 0.2


def test_frigid_waterfall_stacks_self_damage_boost(tmp_path):
    """Gepard：Frigid Waterfall 每次施放叠加 12% 自身增伤."""
    from hsr_nous.adapters.template_generator import _enemy_frigid_waterfall_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("1004022") if r["skill_id"] == "100402204")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("1004022")["en"])["skills"]
                    if s["name"] == "Frigid Waterfall")
    action, hook = _enemy_frigid_waterfall_action(raw, semantic)
    template = generate_enemy_template("1004022")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["100402204"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "1004022.yaml").write_text(
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
        "enemies": [{"enemy_template": "1004022", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["1004022"]
    base = engine.pipeline.effective_stats(enemy)["dmg_bonus"].get("all", 0.0)

    engine._enemy_turn(enemy)
    assert enemy.modifiers["ENEMY_FRIGID_WATERFALL"].stacks == 1
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["all"] == base + 0.12
    engine._enemy_turn(enemy)
    assert enemy.modifiers["ENEMY_FRIGID_WATERFALL"].stacks == 2
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["all"] == base + 0.24


@pytest.mark.parametrize(("enemy_id", "skill_id", "semantic_name", "expected_names"), [
    ("8015022", "801502208", "Twin Bond", ("Abundance Lotus", "Destruction Lotus")),
    ("1003010", "100301004", "Reinforcement", ("Silvermane Soldier", "Silvermane Soldier")),
    ("1003011", "100301104", "Reinforcement", ("Silvermane Soldier", "Silvermane Gunner")),
])
def test_multi_summon_spawns_registered_monsters(
        tmp_path, enemy_id, skill_id, semantic_name, expected_names):
    """多召唤按 SummonIDList 逐个布场；同种复数召唤也使用独立实例 ID."""
    from hsr_nous.adapters.template_generator import _enemy_multi_summon_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_detail, get_enemy_mechanics, get_enemy_skills, get_monster_meta)

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == semantic_name)
    action, hook, specs = _enemy_multi_summon_action(
        raw, semantic, get_enemy_detail(enemy_id), get_monster_meta, level=80)
    template = generate_enemy_template(enemy_id)
    template.update({
        "actions": [action], "hooks": [hook], "summons": specs,
        "policy": {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
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
        "enemies": [{"enemy_template": enemy_id, "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    engine._enemy_turn(engine.state.actors[enemy_id])

    assert len(specs) == 2
    assert len({spec["summon_id"] for spec in specs}) == 2
    names = []
    for spec in specs:
        actor = engine.state.actors[f"{spec['summon_id']}__{enemy_id}"]
        assert actor.alive and actor.actor.summoner_id == enemy_id
        names.append(actor.actor.name)
    assert sorted(names) == sorted(expected_names)


def test_molten_fusion_stacks_atk_up_to_three(tmp_path):
    """Blaze Out of Space：Molten Fusion 每层 ATK +30%，最多叠至 90%."""
    import math
    from hsr_nous.adapters.template_generator import _enemy_molten_fusion_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("8003021") if r["skill_id"] == "800302104")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8003021")["en"])["skills"]
                    if s["name"] == "Molten Fusion")
    action, hook = _enemy_molten_fusion_action(raw, semantic)
    template = generate_enemy_template("8003021")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["800302104"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8003021.yaml").write_text(
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
        "enemies": [{"enemy_template": "8003021", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["8003021"]

    for expected in (0.3, 0.6, 0.9, 0.9):
        engine._enemy_turn(enemy)
        assert math.isclose(engine.pipeline.effective_stats(enemy)["atk_pct"], expected, rel_tol=1e-9)
        assert enemy.modifiers["ENEMY_MOLTEN_FUSION"].stacks == int(round(expected / 0.3))


def test_engine_boost_buffs_others_and_restores_toughness(tmp_path):
    """Antimatter Engine：Engine Boost 增益其他友方并恢复其韧性."""
    from hsr_nous.adapters.template_generator import _enemy_engine_boost_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("8013141") if r["skill_id"] == "801314103")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8013141")["en"])["skills"]
                    if s["name"] == "Engine Boost")
    action, hook = _enemy_engine_boost_action(raw, semantic)
    template = generate_enemy_template("8013141")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["801314103"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8013141.yaml").write_text(
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
        "enemies": [{"enemy_template": "8013141", "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    dummy_state = engine.state.actors["dummy"]
    dummy_state.broken = True
    dummy_state.toughness = 0.0

    engine._enemy_turn(engine.state.actors["8013141"])

    assert not dummy_state.broken
    assert dummy_state.toughness == 30.0
    modifier = dummy_state.modifiers["ENEMY_801314103_ENHANCED"]
    assert modifier.stat_effects == {"atk_pct": 0.6} and modifier.duration == 2
    assert "ENEMY_801314103_ENHANCED" not in engine.state.actors["8013141"].modifiers


def test_void_fission_targets_named_hand(tmp_path):
    """Void Fission 只增益 Disaster's Right Hand，不误伤 Dawn's Left Hand."""
    from hsr_nous.adapters.template_generator import _enemy_engine_boost_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("8013141") if r["skill_id"] == "801314101")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8013141")["en"])["skills"]
                    if s["name"] == "Void Fission")
    action, hook = _enemy_engine_boost_action(raw, semantic)
    template = generate_enemy_template("8013141")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["801314101"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8013141.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    for enemy_id in ("8012143", "8012145"):
        (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
            yaml.safe_dump(generate_enemy_template(enemy_id), allow_unicode=True, sort_keys=False),
            encoding="utf-8")
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
        "enemies": [
            {"enemy_template": "8013141", "level": 80},
            {"enemy_template": "8012143", "level": 80},
            {"enemy_template": "8012145", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    right = engine.state.actors["8012143"]
    left = engine.state.actors["8012145"]
    for state in (right, left):
        state.broken = True
        state.toughness = 0.0

    engine._enemy_turn(engine.state.actors["8013141"])

    assert not right.broken and right.toughness > 0
    assert right.modifiers["ENEMY_801314101_ENHANCED"].stat_effects == {"atk_pct": 0.6}
    assert left.broken and left.toughness == 0.0
    assert "ENEMY_801314101_ENHANCED" not in left.modifiers

    raw = next(r for r in get_enemy_skills("8013145") if r["skill_id"] == "801314502")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8013145")["en"])["skills"]
                    if s["name"] == "Calamity Strike")
    _action, hook = _enemy_engine_boost_action(raw, semantic)
    assert hook["effects"][0]["target"]["where"] == '$it.name == "Dawn\'s Left Hand"'


def test_great_arbor_bounce_applies_wind_shear_per_hit(tmp_path):
    """The Ascended：Rite of Great Arbor 每段 Bounce 都按 action_id 施加 Wind Shear."""
    from hsr_nous.adapters.template_generator import _enemy_great_arbor_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2023031") if r["skill_id"] == "202303101")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2023031")["en"])["skills"]
                    if s["name"] == "Rite of Great Arbor Metamorphosis")
    action, hook = _enemy_great_arbor_action(raw, semantic)
    template = generate_enemy_template("2023031")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["202303101"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2023031.yaml").write_text(
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
        "enemies": [{"enemy_template": "2023031", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []

    def _after_hit(_event_type, payload, _ctx):
        seen.append(payload["action_id"])

    engine.bus.subscribe("after_being_hit", _after_hit)
    engine.setup()
    engine._enemy_turn(engine.state.actors["2023031"])

    assert seen == ["202303101"] * 5
    modifier = engine.state.actors["h1"].modifiers["ENEMY_202303101_WIND_SHEAR"]
    assert modifier.stacks == 5 and modifier.max_stack == 5 and modifier.duration == 3
    assert "ENEMY_202303101_WIND_SHEAR" not in engine.state.actors["h2"].modifiers
    assert "ENEMY_202303101_WIND_SHEAR" not in engine.state.actors["h3"].modifiers


def test_guiding_vulturnus_blast_applies_wind_shear_per_hit(tmp_path):
    """The Ascended：Guiding Vulturnus 的主目标与相邻目标分别施加 Wind Shear."""
    from hsr_nous.adapters.template_generator import _enemy_great_arbor_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2023031") if r["skill_id"] == "202303102")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2023031")["en"])["skills"]
                    if s["name"] == "Guiding Vulturnus")
    action, hook = _enemy_great_arbor_action(raw, semantic)
    assert action["target_type"] == "blast" and action["scaling_blast"] == [{"atk": 1.5}]
    template = generate_enemy_template("2023031")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["202303102"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2023031.yaml").write_text(
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
        "enemies": [{"enemy_template": "2023031", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    engine._enemy_turn(engine.state.actors["2023031"])

    for actor_id in ("h1", "h2"):
        modifier = engine.state.actors[actor_id].modifiers["ENEMY_202303102_WIND_SHEAR"]
        assert modifier.stacks == 1 and modifier.dot_ratio == 1.0 and modifier.duration == 3
    assert "ENEMY_202303102_WIND_SHEAR" not in engine.state.actors["h3"].modifiers

    raw = next(r for r in get_enemy_skills("2023030") if r["skill_id"] == "202303002")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2023030")["en"])["skills"]
                    if s["name"] == "Guiding Vulturnus")
    action, hook = _enemy_great_arbor_action(raw, semantic)
    assert action["scaling"] == [{"atk": 2.0}] and action["scaling_blast"] == [{"atk": 2.0}]
    assert hook["effects"][0]["modifier"]["dot_ratio"] == 0.7


@pytest.mark.parametrize("enemy_id", ["2023030", "202303001", "202303009", "202303016"])
def test_base_great_arbor_omitted_count_and_full_roster(tmp_path, enemy_id):
    """基础承露天人：Ability 证明四段 Bounce，五技能与 ConfigAI 全量生成."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template(enemy_id)
    skill_id = "202303001"
    assert [action["action_id"] for action in template["actions"]] == [
        "202303001", "202303002", "202303003", "202303004", "202303005"]
    assert template["actions"][0]["instances"] == 4
    assert template["policy"].get("config")
    compiled = _compiled(
        tmp_path, [template["actions"][0]],
        {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        hooks=template["hooks"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = []
    engine.bus.subscribe(
        "after_being_hit", lambda _event, payload, _ctx: seen.append(payload["action_id"]))
    engine.setup()
    engine._enemy_turn(engine.state.actors["enemy"])

    assert seen == [skill_id] * 4
    modifier = engine.state.actors["hero"].modifiers[f"ENEMY_{skill_id}_WIND_SHEAR"]
    assert modifier.stacks == 4 and modifier.max_stack == 5
    assert modifier.duration == 3 and modifier.dot_ratio == 0.7


def test_black_prana_dirty_hp_cap_refresh_and_cleanse(tmp_path):
    """噬命：治疗封顶、受击转化并刷新、99% 总上限、解除后清账."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2023030")
    skill_id = "202303005"
    prana = next(action for action in template["actions"] if action["action_id"] == skill_id)
    attack = {
        "action_id": "test_hit", "name": "测试攻击", "action_type": "skill",
        "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 1.0}],
        "toughness_dmg": 0, "energy_gain": 0,
    }
    compiled = _compiled(
        tmp_path, [prana, attack],
        {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        hooks=template["hooks"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    hero = engine.state.actors["hero"]
    modifier_id = f"ENEMY_{skill_id}_PRANA_SIPHON"
    resource_id = "_prana_siphon_dirty"
    hero.current_hp = 90000.0
    engine._enemy_turn(enemy)
    assert hero.modifiers[modifier_id].duration == 2
    assert engine.pipeline.effective_stats(hero)["recoverable_hp_reduction"] == pytest.approx(0.3)

    result = engine.pipeline.heal(enemy, hero, amount=20000.0)
    assert result.node["actualAmount"] == 0.0 and hero.current_hp == 90000.0
    hero.current_hp = 65000.0
    result = engine.pipeline.heal(enemy, hero, amount=20000.0)
    assert result.node["actualAmount"] == pytest.approx(5000.0)
    assert hero.current_hp == 70000.0

    hero.modifiers[modifier_id].duration = 1
    hits = []
    engine.bus.subscribe(
        "after_being_hit",
        lambda _event, payload, _ctx: hits.append(payload) if payload["action_id"] == "test_hit" else None)
    engine._execute_action(enemy, compiled.actions_by_actor["enemy"][1], forced_target=hero)
    hit_amount = hits[-1]["amount"]
    dirty_ratio = hit_amount / 100000.0
    assert hero.resources[resource_id] == pytest.approx(dirty_ratio)
    assert hero.modifiers[modifier_id].duration == 2
    assert engine.pipeline.effective_stats(hero)["recoverable_hp_reduction"] == pytest.approx(0.3 + dirty_ratio)

    hero.resources[resource_id] = 0.69 - dirty_ratio / 2
    engine._execute_action(enemy, compiled.actions_by_actor["enemy"][1], forced_target=hero)
    assert hero.resources[resource_id] == pytest.approx(0.69)
    assert engine.pipeline.effective_stats(hero)["recoverable_hp_reduction"] == pytest.approx(0.99)
    hero.current_hp = 500.0
    result = engine.pipeline.heal(enemy, hero, amount=20000.0)
    assert result.node["actualAmount"] == pytest.approx(500.0)
    assert hero.current_hp == pytest.approx(1000.0)

    engine._remove_modifier(hero, modifier_id, "purify")
    assert hero.resources[resource_id] == 0.0
    assert engine.pipeline.effective_stats(hero).get("recoverable_hp_reduction", 0.0) == 0.0
    result = engine.pipeline.heal(enemy, hero, amount=1000.0)
    assert result.node["actualAmount"] == pytest.approx(1000.0)
    assert hero.current_hp == pytest.approx(2000.0)


def test_black_prana_bug_stacks_source_filter_cap_and_cleanse(tmp_path):
    """Bug 噬命：施放叠层、仅自身攻击转换、50% 封顶与解除清账."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2023031")
    skill_id = "202303104"
    assert [action["action_id"] for action in template["actions"]] == [
        "202303101", "202303102", "202303103", skill_id]
    assert template["policy"].get("config")
    prana = template["actions"][-1]
    attack = {
        "action_id": "test_hit", "name": "测试攻击", "action_type": "skill",
        "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 1.0}],
        "toughness_dmg": 0, "energy_gain": 0,
    }
    compiled = _compiled(
        tmp_path, [prana, attack],
        {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        hooks=template["hooks"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    hero = engine.state.actors["hero"]
    modifier_id = f"ENEMY_{skill_id}_PRANA_SIPHON"
    base_resource = "_prana_siphon_base"
    dirty_resource = "_prana_siphon_dirty"

    def reduction():
        return engine.pipeline.effective_stats(hero)["recoverable_hp_reduction"]

    engine._enemy_turn(enemy)
    assert hero.resources[base_resource] == pytest.approx(0.2)
    assert reduction() == pytest.approx(0.2)
    assert hero.modifiers[modifier_id].duration == 3
    assert hero.modifiers[modifier_id].remove_on_source_death

    engine.bus.emit("on_hp_decrease", {
        "source": "other", "reason": "hit", "target": "hero", "amount": 1000.0,
    }, engine.state)
    assert hero.resources[dirty_resource] == 0.0

    hits = []
    engine.bus.subscribe(
        "on_hp_decrease", lambda _event, payload, _ctx: hits.append(payload))
    hero.modifiers[modifier_id].duration = 1
    engine._execute_action(enemy, compiled.actions_by_actor["enemy"][1], forced_target=hero)
    dirty_ratio = hits[-1]["amount"] / 100000.0
    assert hero.resources[dirty_resource] == pytest.approx(dirty_ratio)
    assert hero.modifiers[modifier_id].duration == 3
    assert reduction() == pytest.approx(0.2 + dirty_ratio)

    engine._enemy_turn(enemy)
    assert hero.resources[base_resource] == pytest.approx(0.4)
    assert reduction() == pytest.approx(0.4 + dirty_ratio)
    hero.resources[dirty_resource] = 0.1 - dirty_ratio / 2
    engine._execute_action(enemy, compiled.actions_by_actor["enemy"][1], forced_target=hero)
    assert hero.resources[dirty_resource] == pytest.approx(0.1)
    assert reduction() == pytest.approx(0.5)

    engine._enemy_turn(enemy)
    assert hero.resources[base_resource] == pytest.approx(0.5)
    assert reduction() == pytest.approx(0.5)
    hero.current_hp = 45000.0
    result = engine.pipeline.heal(enemy, hero, amount=20000.0)
    assert result.node["actualAmount"] == pytest.approx(5000.0)
    assert hero.current_hp == 50000.0

    engine._remove_modifier(hero, modifier_id, "purify")
    assert hero.resources[base_resource] == 0.0 and hero.resources[dirty_resource] == 0.0
    assert engine.pipeline.effective_stats(hero).get("recoverable_hp_reduction", 0.0) == 0.0
    result = engine.pipeline.heal(enemy, hero, amount=1000.0)
    assert result.node["actualAmount"] == pytest.approx(1000.0)
    assert hero.current_hp == 51000.0


def test_wind_walker_blast_applies_wind_shear_to_primary_and_adjacent(tmp_path):
    """Stormbringer：Wind Walker 主邻目标均获得可跳伤、可叠层的风化."""
    from hsr_nous.adapters.template_generator import _enemy_wind_walker_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("8003050") if r["skill_id"] == "800305002")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8003050")["en"])["skills"]
                    if s["name"] == "Wind Walker")
    action, hook = _enemy_wind_walker_action(raw, semantic)
    assert action["target_type"] == "blast"
    assert action["scaling"] == action["scaling_blast"] == [{"atk": 2.2}]
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3")]
    compiled = _compiled(tmp_path, [action], team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    engine._execute_action(engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0])

    for actor_id in ("h1", "h2"):
        target = engine.state.actors[actor_id]
        modifier = target.modifiers["ENEMY_800305002_WIND_SHEAR"]
        assert modifier.stacks == 1 and modifier.max_stack == 5
        assert modifier.dot_ratio == 0.75 and modifier.duration == 2
        hp_before_tick = target.current_hp
        engine._tick_dots(target)
        assert target.current_hp < hp_before_tick
    assert "ENEMY_800305002_WIND_SHEAR" not in engine.state.actors["h3"].modifiers


def test_caressing_moonlight_shocks_secondary_only_if_primary_shocked(tmp_path):
    """Kafka：仅主目标已 Shocked 时，Caressing Moonlight 才给副目标挂 Shock."""
    from hsr_nous.adapters.template_generator import _enemy_caressing_moonlight_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    semantics = get_enemy_mechanics("Stellaron Hunter: Kafka")["skills"]
    raw = next(r for r in get_enemy_skills("2004010") if r["skill_id"] == "200401002")
    semantic = next(s for s in semantics if s["name"] == "Caressing Moonlight")
    action, hook = _enemy_caressing_moonlight_action(raw, semantic, semantics)
    template = generate_enemy_template("2004010")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["200401002"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2004010.yaml").write_text(
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
        "enemies": [{"enemy_template": "2004010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2004010"]
    engine._apply_modifier_spec(engine.state.actors["h1"], {
        "modifier_id": "TEST_SHOCK", "name": "Shock", "modifier_type": "dot",
        "dot_element": "thunder", "dot_ratio": 0.75, "duration": 3,
    }, enemy)

    engine._enemy_turn(enemy)
    modifier = engine.state.actors["h2"].modifiers["ENEMY_200401002_SHOCK"]
    assert modifier.dot_ratio == 0.75 and modifier.duration == 3
    assert "ENEMY_200401002_SHOCK" not in engine.state.actors["h3"].modifiers


def test_seething_whisper_shocks_primary_and_hits_other_shocked(tmp_path):
    """Soulhook Sovereign：Seething Whisper 主目标挂 Shock，并只追加攻击其他 Shocked 目标."""
    from hsr_nous.adapters.template_generator import _enemy_seething_whisper_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills

    semantics = get_enemy_mechanics("Soulhook Sovereign")["skills"]
    raw = next(r for r in get_enemy_skills("2004014") if r["skill_id"] == "200401405")
    semantic = next(s for s in semantics if s["name"] == "Seething Whisper of the Fallen")
    action, hooks = _enemy_seething_whisper_action(raw, semantic, semantics)
    template = generate_enemy_template("2004014")
    template.update({
        "actions": [action], "hooks": hooks,
        "policy": {"sequence": ["200401405"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2004014.yaml").write_text(
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
        "enemies": [{"enemy_template": "2004014", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2004014"]
    engine._apply_modifier_spec(engine.state.actors["h3"], {
        "modifier_id": "TEST_OTHER_SHOCK", "name": "Shock", "modifier_type": "dot",
        "dot_element": "thunder", "dot_ratio": 0.5, "duration": 3,
    }, enemy)
    seen = []

    def _after_hit(_event_type, payload, _ctx):
        seen.append(payload["target"])

    engine.bus.subscribe("after_being_hit", _after_hit)
    engine._enemy_turn(enemy)

    assert seen == ["h1", "h3"]
    modifier = engine.state.actors["h1"].modifiers["ENEMY_200401405_SHOCK"]
    assert modifier.dot_ratio == 0.5 and modifier.duration == 3
    assert "ENEMY_200401405_SHOCK" not in engine.state.actors["h2"].modifiers

    for actor_id, modifier_id in (("h1", "TEST_SHOCK"), ("h2", "ENEMY_200401002_SHOCK"),
                                  ("h3", "ENEMY_200401002_SHOCK")):
        engine._remove_modifier(engine.state.actors[actor_id], modifier_id, "test")
    engine._enemy_turn(enemy)
    assert "ENEMY_200401002_SHOCK" not in engine.state.actors["h2"].modifiers
    assert "ENEMY_200401002_SHOCK" not in engine.state.actors["h3"].modifiers


def test_to_mourn_atrophy_ignores_shields_and_grants_energy(tmp_path):
    """Pollux：Atrophy 按目标 Max HP 固伤穿盾，并给同一批目标受击回能."""
    from hsr_nous.adapters.template_generator import _enemy_to_mourn_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import ShieldInstance

    raw = next(r for r in get_enemy_skills("4014030") if r["skill_id"] == "401403003")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("4014030")["en"])["skills"]
                    if s["name"] == "To Mourn the Departing")
    action, hook = _enemy_to_mourn_action(raw, semantic)
    template = generate_enemy_template("4014030")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["401403003"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4014030.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = []
    for actor_id in ("h1", "h2", "h3"):
        team.append({
            "actor_id": actor_id, "name": "测试员", "inline": True,
            "base_stats": {"hp": 100000, "atk": 0, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "4014030", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    for actor_id in ("h1", "h2", "h3"):
        state = engine.state.actors[actor_id]
        state.shields.append(ShieldInstance(
            shield_id=f"shield_{actor_id}", name="test", remaining=100000, source_id="test"))

    engine._enemy_turn(engine.state.actors["4014030"])

    for actor_id in ("h1", "h2", "h3"):
        state = engine.state.actors[actor_id]
        assert state.current_hp == 70000.0
        assert state.current_energy == 5.0
        assert state.shields[0].remaining == 100000.0


def test_dead_shant_avoid_splits_atrophy_by_target_hp(tmp_path):
    """The Long Arms of Sorrow：高 HP 目标改受 Atrophy，低 HP 目标走普通直伤."""
    from hsr_nous.adapters.template_generator import _enemy_dead_shant_avoid_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("4012070") if r["skill_id"] == "401207002")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("4012070")["en"])["skills"]
                    if s["name"] == "The Dead Shan't Avoid")
    action, hook = _enemy_dead_shant_avoid_action(raw, semantic)
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 100000, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    compiled = _compiled(tmp_path, [action], team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine.state.actors["h2"].current_hp = 40000.0

    engine._enemy_turn(engine.state.actors["enemy"])

    assert engine.state.actors["h1"].current_hp == pytest.approx(94950.0)
    assert engine.state.actors["h2"].current_hp == pytest.approx(39963.1)


def test_obscure_blaze_resource_drives_bonepiercing(tmp_path):
    """Shell of Faded Rage：攻击与咆哮叠层，Bonepiercing 基础 1 击并按层追加后清空."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("3013010")
    actions = {action["action_id"]: action for action in template["actions"]}
    assert set(actions) == {"301301001", "301301002", "301301003", "301301004"}
    assert actions["301301003"]["resource_gain"] == {"obscure_blaze": 1}
    compiled = _compiled(
        tmp_path, list(actions.values()),
        {"sequence": ["301301001", "301301002", "301301004"],
         "cooldown": {}, "initial_cooldown": {}},
        custom_resources=template["custom_resources"])
    assert compiled.resource_decls_by_actor["enemy"]["obscure_blaze"]["max"] == 3
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]

    engine._enemy_turn(enemy)
    assert enemy.resources["obscure_blaze"] == 1
    engine._enemy_turn(enemy)
    assert enemy.resources["obscure_blaze"] == 3

    hits = []
    engine.bus.subscribe(
        "on_hp_decrease",
        lambda _event, payload, _ctx: hits.append(payload) if payload.get("source") == "enemy" else None)
    engine._enemy_turn(enemy)

    assert len(hits) == 4
    assert enemy.resources["obscure_blaze"] == 0


def test_scorchbone_bounce_blast_hits_main_and_adjacent(tmp_path):
    """Bug 版 Shell of Faded Rage：每段弹射同时命中主目标与其相邻单位."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("3013013")
    actions = {action["action_id"]: action for action in template["actions"]}
    assert actions["301301304"]["target_type"] == "bounce_blast"
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 100000, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 0.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3")]
    compiled = _compiled(
        tmp_path, list(actions.values()),
        {"sequence": ["301301302", "301301304"], "cooldown": {}, "initial_cooldown": {}},
        custom_resources=template["custom_resources"], team=team)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    engine._enemy_turn(enemy)
    assert enemy.resources["scorchbone_inferno"] == 3

    counts = {"h1": 0, "h2": 0, "h3": 0}
    engine.bus.subscribe(
        "on_hp_decrease",
        lambda _event, payload, _ctx: counts.__setitem__(
            payload["target"], counts[payload["target"]] + 1)
        if payload.get("source") == "enemy" else None)
    engine._enemy_turn(enemy)

    assert counts == {"h1": 4, "h2": 4, "h3": 0}
    assert enemy.resources["scorchbone_inferno"] == 0


@pytest.mark.parametrize(("enemy_id", "skill_id"), [
    ("100402004", "100402003"),
    ("1004024", "100402403"),
    ("1004026", "100402603"),
    ("1004027", "100402703"),
    ("1004028", "100402803"),
])
def test_garrison_barrier_protects_other_friendly_once(tmp_path, enemy_id, skill_id):
    """Gepard 各 Barrier 变体：首次攻击免伤并消耗，后续攻击正常扣血."""
    from hsr_nous.adapters.template_generator import _enemy_garrison_barrier_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Garrison Aura Field")
    action, hooks = _enemy_garrison_barrier_action(raw, semantic)
    template = generate_enemy_template(enemy_id)
    template.update({
        "actions": [action], "hooks": hooks,
        "policy": {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 100000, "atk": 1000, "def": 0, "spd": 50, "max_energy": 100},
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
        "enemies": [
            {"enemy_template": enemy_id, "actor_id": "gepard", "level": 80},
            {"actor_id": "ally", "name": "友方假人", "level": 80,
             "hp": 100000, "atk": 0, "def": 0, "spd": 10, "max_toughness": 30},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    gepard = engine.state.actors["gepard"]
    ally = engine.state.actors["ally"]
    engine._enemy_turn(gepard)
    barrier_id = f"ENEMY_{skill_id}_BARRIER"
    assert barrier_id in ally.modifiers
    assert barrier_id not in gepard.modifiers

    hero = engine.state.actors["hero"]
    basic = compiled.actions_by_actor["hero"][0]
    old_hp = ally.current_hp
    engine._execute_action(hero, basic, forced_target=ally)
    assert ally.current_hp == old_hp
    assert barrier_id not in ally.modifiers

    engine._execute_action(hero, basic, forced_target=ally)
    assert ally.current_hp < old_hp


@pytest.mark.parametrize(("enemy_id", "skill_id"), [
    ("3021040", "302104001"),
    ("3021041", "302104101"),
    ("3021043", "302104301"),
])
def test_diadem_stale_barrier_targets_and_consumption(tmp_path, enemy_id, skill_id):
    """The Shield：常态屏障 Argenti，Soulfreed 时屏障全体友方，受击消耗."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.state import Modifier

    template = generate_enemy_template(enemy_id)
    assert [action["action_id"] for action in template["actions"]] == [skill_id]
    template["policy"]["cooldown"] = {}
    template["policy"]["initial_cooldown"] = {}
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 0, "spd": 50, "max_energy": 100},
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
        "enemies": [
            {"enemy_template": enemy_id, "actor_id": "shield", "level": 80},
            {"enemy_template": "3024010", "actor_id": "argenti", "level": 80},
            {"enemy_template": "3021030", "actor_id": "speartip", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    shield = engine.state.actors["shield"]
    argenti = engine.state.actors["argenti"]
    speartip = engine.state.actors["speartip"]
    barrier_id = f"ENEMY_{skill_id}_BARRIER"

    engine._enemy_turn(shield)
    assert barrier_id in argenti.modifiers
    assert barrier_id not in shield.modifiers and barrier_id not in speartip.modifiers
    hero = engine.state.actors["hero"]
    basic = compiled.actions_by_actor["hero"][0]
    old_hp = argenti.current_hp
    engine._execute_action(hero, basic, forced_target=argenti)
    assert argenti.current_hp == old_hp and barrier_id not in argenti.modifiers

    engine._apply_modifier(shield, Modifier(
        modifier_id="ENEMY_SOULFREED", name="Soulfreed", modifier_type="buff", duration=0))
    engine._enemy_turn(shield)
    for actor in (shield, argenti, speartip):
        assert barrier_id in actor.modifiers
    old_hp = speartip.current_hp
    engine._execute_action(hero, basic, forced_target=speartip)
    assert speartip.current_hp == old_hp and barrier_id not in speartip.modifiers
    assert barrier_id in shield.modifiers and barrier_id in argenti.modifiers


@pytest.mark.parametrize(("enemy_id", "skill_id", "expected_names"), [
    ("3024010", "302401004", {"Speartip", "The Shield", "The Honored"}),
    ("3024014", "302401404", {"Speartip"}),
])
def test_spear_and_shield_summons_three_statues(tmp_path, enemy_id, skill_id, expected_names):
    """Argenti：Spear & Shield 按 SummonIDList 召唤三个雕像，允许同种组合."""
    from hsr_nous.adapters.template_generator import _enemy_multi_summon_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_detail, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = {"name": "Spear & Shield", "type": "Summon",
                "desc": 'Randomly summons statues of "Speartip," "The Shield," and "The Honored."'}
    action, hook, specs = _enemy_multi_summon_action(
        raw, semantic, get_enemy_detail(enemy_id), get_monster_meta, level=80)
    template = generate_enemy_template(enemy_id)
    template.update({
        "actions": [action], "hooks": [hook], "summons": specs,
        "policy": {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
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
        "enemies": [{"enemy_template": enemy_id, "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._enemy_turn(engine.state.actors[enemy_id])

    assert len(specs) == 3
    names = set()
    for spec in specs:
        actor = engine.state.actors[f"{spec['summon_id']}__{enemy_id}"]
        assert actor.alive and actor.actor.summoner_id == enemy_id
        names.add(actor.actor.name.strip('"'))
    assert names == expected_names


def test_fleeting_veil_reduces_damage_and_imprisons_target(tmp_path):
    """Decaying Shadow：Skill 伤害降低 10%，攻击目标被施加禁锢."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("8003040")
    template.update({
        "actions": [{"action_id": "enemy_hit", "name": "测试攻击", "action_type": "skill",
                     "target_type": "single", "damage_type": "imaginary",
                     "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "energy_gain": 0}],
        "policy": {"sequence": ["enemy_hit"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8003040.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8003040", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["8003040"]
    enemy.actor.stats.effect_hit = 4.0
    hero = engine.state.actors["hero"]
    basic = compiled.actions_by_actor["hero"][0]
    baseline = engine.pipeline.settle_damage(
        "direct", hero, enemy, action=basic,
        skill_level=engine._skill_level_of(hero.actor, basic),
        params={"target_broken": False}).value
    hits = []
    engine.bus.subscribe(
        "on_hp_decrease", lambda _event, payload, _ctx: hits.append(payload))
    engine._execute_action(hero, basic, forced_target=enemy)
    assert hits[0]["source"] == "hero"
    assert hits[0]["amount"] == pytest.approx(baseline * 0.9)

    engine._enemy_turn(enemy)
    modifier = hero.modifiers["ENEMY_800304006_FLEETING_VEIL"]
    assert modifier.control_kind == "imprison" and modifier.duration == 1


@pytest.mark.parametrize(("enemy_id", "reduction", "delay", "vulnerability"), [
    ("3013010", 0.6, 75.0, 0.5),
    ("3012020", 0.6, 75.0, 0.5),
    ("2032050", 0.4, 50.0, 0.5),
    ("2032051", 0.4, 50.0, 0.5),
])
def test_safeguard_break_swaps_damage_reduction_for_vulnerability(
        tmp_path, enemy_id, reduction, delay, vulnerability):
    """Disembodied Shell / Aegis / Planeshred：击破后撤下减伤、开启易伤并推条."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template(enemy_id)
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 10, "toughness_scope": "all", "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": enemy_id, "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors[enemy_id]
    hero = engine.state.actors["hero"]
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["dmg_reduction"] == reduction
    assert engine.pipeline.effective_stats(enemy)["vulnerability"] == 0.0
    assert any(hook["event"] == "on_break" and hook["effects"][0]["amount"] == delay
               for hook in template["hooks"])
    enemy.current_hp = 1e12
    enemy.toughness = 1.0
    hp_before = enemy.current_hp
    handle = engine.scheduler.handle_of(enemy_id)
    remaining_before = engine.scheduler._remaining[handle]
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0])

    assert enemy.broken
    assert enemy.current_hp < hp_before
    assert engine.scheduler._remaining[handle] > remaining_before
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"].get("dmg_reduction", 0.0) == 0.0
    assert engine.pipeline.effective_stats(enemy)["vulnerability"] == vulnerability


@pytest.mark.parametrize(("enemy_id", "skill_id", "has_safeguard"), [
    ("2032050", "203205001", True),
    ("2032051", "203205101", True),
    ("2032052", "203205201", False),
])
def test_plane_shred_blast_and_config_ai(tmp_path, enemy_id, skill_id, has_safeguard):
    """Plane Shred 主邻同倍率；普通变体带守备，IF 变体不虚构守备."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.enemy_ai import ConfigAIInterpreter

    template = generate_enemy_template(enemy_id)
    assert [action["action_id"] for action in template["actions"]] == [skill_id]
    action = template["actions"][0]
    assert action["target_type"] == "blast" and action["scaling"] == [{"atk": 3.0}]
    assert "scaling_blast" not in action
    assert bool(template.get("hooks")) is has_safeguard
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3")]
    compiled = _compiled(
        tmp_path, template["actions"], template["policy"], team=team,
        hooks=template.get("hooks"))
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    engine._enemy_policy_state["enemy"]["cooldown_left"][skill_id] = 0
    selected = ConfigAIInterpreter(engine, enemy).choose_action()
    assert selected is not None and selected.action_id == skill_id
    hits = []
    engine.bus.subscribe(
        "on_hp_decrease", lambda _event, payload, _ctx: hits.append(payload))
    engine._execute_action(enemy, selected, forced_target=engine.state.actors["h2"])

    hits = [payload for payload in hits if payload["reason"] == "hit"]
    assert {payload["target"] for payload in hits} == {"h1", "h2", "h3"}
    assert len(hits) == 3 and all(payload["amount"] > 0 for payload in hits)
    assert hits[0]["amount"] == pytest.approx(hits[1]["amount"])
    assert hits[1]["amount"] == pytest.approx(hits[2]["amount"])


def test_storm_cyclone_stacks_on_wind_shear_and_break_dispels(tmp_path):
    """Stormbringer Storm Cyclone：攻击风化目标叠 ATK，弱点击破后解除."""
    from hsr_nous.adapters.template_generator import (
        _enemy_storm_cyclone_passive, _enemy_wind_walker_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    semantics = get_enemy_mechanics(get_monster_meta("8003050")["en"])["skills"]
    raw_action = next(r for r in get_enemy_skills("8003050") if r["skill_id"] == "800305002")
    action, wind_hook = _enemy_wind_walker_action(
        raw_action, next(s for s in semantics if s["name"] == "Wind Walker"))
    raw_passive = next(r for r in get_enemy_skills("8003050") if r["skill_id"] == "800305005")
    passive_hooks = _enemy_storm_cyclone_passive(
        raw_passive, next(s for s in semantics if s["name"] == "Storm Cyclone"))
    template = generate_enemy_template("8003050")
    template.update({
        "actions": [action], "hooks": [wind_hook, *passive_hooks],
        "policy": {"sequence": ["800305002"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8003050.yaml").write_text(
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
        "enemies": [{"enemy_template": "8003050", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["8003050"]
    base_atk = engine.pipeline.effective_stats(enemy)["atk"]

    engine._enemy_turn(enemy)
    modifier = enemy.modifiers["ENEMY_800305005_STORM_CYCLONE"]
    assert modifier.stacks == 1 and modifier.duration == 2 and modifier.max_stack == 5
    engine._enemy_turn(enemy)
    assert modifier.stacks == 2 and modifier.duration == 2
    assert engine.pipeline.effective_stats(enemy)["atk"] == pytest.approx(base_atk * 1.16)

    engine.bus.emit("on_break", {"target": enemy.actor.actor_id}, engine.state)
    assert "ENEMY_800305005_STORM_CYCLONE" not in enemy.modifiers


@pytest.mark.parametrize(("enemy_id", "passive_id", "charge_id"), [
    ("1013012", "101301207", "101301204"),
    ("1013013", "101301307", "101301304"),
    ("1013014", "101301407", "101301404"),
])
def test_obliteration_order_stacks_per_overcombust(tmp_path, enemy_id, passive_id, charge_id):
    """Automaton Grizzly：每次 Overcombust Order 永久叠 50% 增伤."""
    from hsr_nous.adapters.template_generator import _enemy_obliteration_order_passive
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == passive_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Obliteration Order")
    hooks = _enemy_obliteration_order_passive(raw, semantic)
    compiled = _compiled(tmp_path, [_action(charge_id)], hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]

    engine._enemy_turn(enemy)
    engine._enemy_turn(enemy)

    modifier = enemy.modifiers[f"ENEMY_{passive_id}_OBLITERATION_ORDER"]
    assert modifier.stacks == 2 and modifier.duration == 0
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["all"] == pytest.approx(1.0)


def test_combat_speed_up_base_and_targeting_stacks(tmp_path):
    """Automaton Direwolf：开局 SPD +60%，每次 Targeting Order 再叠 10%."""
    from hsr_nous.adapters.template_generator import _enemy_combat_speed_up_passive
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("1013023") if r["skill_id"] == "101302308")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("1013023")["en"])["skills"]
                    if s["name"] == "Combat Speed-Up")
    hooks = _enemy_combat_speed_up_passive(raw, semantic)
    compiled = _compiled(tmp_path, [_action("101302303")], hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    base_spd = enemy.actor.stats.spd
    assert engine.pipeline.effective_stats(enemy)["spd"] == pytest.approx(base_spd * 1.6)

    engine._enemy_turn(enemy)
    assert enemy.modifiers["ENEMY_101302308_COMBAT_SPEED_UP_STACK"].stacks == 1
    assert engine.pipeline.effective_stats(enemy)["spd"] == pytest.approx(base_spd * 1.7)
    engine._enemy_turn(enemy)
    assert enemy.modifiers["ENEMY_101302308_COMBAT_SPEED_UP_STACK"].stacks == 2
    assert engine.pipeline.effective_stats(enemy)["spd"] == pytest.approx(base_spd * 1.8)


def test_fiery_majesty_stacks_damage_boost_to_three(tmp_path):
    """Malefic Ape：Fiery Majesty 每次施放叠 20%，第四施放仍封顶三层."""
    from hsr_nous.adapters.template_generator import _enemy_fiery_majesty_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2023020") if r["skill_id"] == "202302003")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2023020")["en"])["skills"]
                    if s["name"] == "Fiery Majesty")
    action, hook = _enemy_fiery_majesty_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action],
        {"sequence": ["202302003"], "cooldown": {}, "initial_cooldown": {}}, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    for _ in range(4):
        engine._enemy_turn(enemy)

    modifier = enemy.modifiers["ENEMY_202302003_FIERY_MAJESTY"]
    assert modifier.stacks == 3
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["all"] == pytest.approx(0.6)


def test_thick_skinned_break_removes_defense_boost(tmp_path):
    """Judge of Oblivion：开局 DEF +150%，击破后 Enhance Defense 被解除."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4064012")
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4064012.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 10, "toughness_scope": "all", "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "4064012", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["4064012"]
    base_def = enemy.actor.stats.def_
    assert engine.pipeline.effective_stats(enemy)["def_"] == pytest.approx(base_def * 2.5)
    enemy.current_hp = 1e12
    enemy.toughness = 1.0
    engine._execute_action(engine.state.actors["hero"], compiled.actions_by_actor["hero"][0])

    assert enemy.broken
    assert "ENEMY_406401208_ENHANCE_DEFENSE" not in enemy.modifiers
    assert engine.pipeline.effective_stats(enemy)["def_"] == pytest.approx(base_def)


@pytest.mark.parametrize(("enemy_id", "skill_id"), [("2004014", "200401404"), ("2004010", "200401004")])
def test_spirit_whisper_dominates_into_immediate_basic(tmp_path, enemy_id, skill_id):
    """Spirit Whisper 两组参数布局都支配后立即以普攻攻击随机友方."""
    from hsr_nous.adapters.template_generator import _enemy_spirit_whisper_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.scheduler import EXTRA_NORMAL

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Spirit Whisper")
    action, hook = _enemy_spirit_whisper_action(raw, semantic)
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": spd, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 1.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id, spd in (("h1", 50), ("h2", 1))]
    compiled = _compiled(
        tmp_path, [action],
        {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = []
    engine.bus.subscribe(
        "on_action",
        lambda _event, payload, _ctx: seen.append(
            (payload["actor"], payload["action_id"], payload["target"])))
    engine.setup()
    h1 = engine.state.actors["h1"]
    h2 = engine.state.actors["h2"]
    engine._enemy_turn(engine.state.actors["enemy"])
    assert f"ENEMY_{skill_id}_DOMINATE" in h1.modifiers
    h2_hp = h2.current_hp
    engine._run_turn(h1, EXTRA_NORMAL)

    assert seen[-1] == ("h1", "h1_basic", "h2")
    assert h2.current_hp < h2_hp


@pytest.mark.parametrize(("enemy_id", "skill_id"), [
    ("2035012", "203501203"),
    ("2035010", "203501003"),
    ("2035011", "203501103"),
    ("2005010", "200501003"),
])
def test_heavens_binds_grants_immediate_action(tmp_path, enemy_id, skill_id):
    """Heaven's Binds 各参数变体都让自身获得一个额外行动."""
    from hsr_nous.adapters.template_generator import _enemy_heavens_binds_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Heaven's Binds")
    action, hook = _enemy_heavens_binds_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action],
        {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}}, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    handle = engine.scheduler.handle_of("enemy")
    assert engine.scheduler._remaining[handle] > 0.0
    engine._enemy_turn(engine.state.actors["enemy"])

    assert engine.scheduler._remaining[handle] == 0.0


@pytest.mark.parametrize(("enemy_id", "skill_id"), [("4014030", "401403004"), ("4014032", "401403204")])
def test_bitterness_evil_news_enhances_and_advances(tmp_path, enemy_id, skill_id):
    """Bitterness Delivers Belated Evil News：Enhanced 3 回合并立即行动."""
    from hsr_nous.adapters.template_generator import _enemy_bitterness_evil_news_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Bitterness Delivers Belated Evil News")
    action, hook = _enemy_bitterness_evil_news_action(raw, semantic)
    compiled = _compiled(tmp_path, [action], hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]

    engine._enemy_turn(enemy)

    assert enemy.modifiers[f"ENEMY_{skill_id}_ENHANCED"].duration == 3
    assert engine.scheduler._remaining[engine.scheduler.handle_of("enemy")] == 0.0


@pytest.mark.parametrize(("enemy_id", "skill_id", "name", "target_type", "main_ratio", "blast_ratio"), [
    ("2034014", "203401405", "Lupine Chase Calls Bloody Gleam", "single", 6.0, None),
    ("8025011", "802501103", "Pyrolysis Death Beam", "blast", 4.5, 3.5),
    ("1004010", "100401003", "Punishment of Endless Winter", "aoe", 5.0, None),
    ("1014013", "101401302", "Banishing Punch", "single", 3.0, None),
    ("3024030", "302403002", "Rapacious Appendages", "blast", 2.4, 1.8),
])
def test_linked_param_direct_actions(
        tmp_path, enemy_id, skill_id, name, target_type, main_ratio, blast_ratio):
    """纯直伤句只消费本击倍率槽，关联机制参数不阻断转换与执行."""
    from hsr_nous.adapters.template_generator import _enemy_linked_param_direct_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == name)
    action = _enemy_linked_param_direct_action(raw, semantic)
    assert action["target_type"] == target_type
    assert action["scaling"] == [{"atk": main_ratio}]
    assert action.get("scaling_blast") == ([{"atk": blast_ratio}] if blast_ratio is not None else None)
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}})
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hero = engine.state.actors["hero"]
    old_hp = hero.current_hp
    engine._enemy_turn(engine.state.actors["enemy"])

    assert hero.current_hp < old_hp


@pytest.mark.parametrize(("enemy_id", "skill_id", "chance", "duration", "delayed_ratio"), [
    ("1004010", "100401004", 1.0, 2, 1.5),
    ("1004014", "100401404", 0.5, 1, 2.0),
])
def test_hoarfrost_freeze_layouts(tmp_path, enemy_id, skill_id, chance, duration, delayed_ratio):
    """Hoarfrost：100% 省略概率槽与省略延迟文本两种布局都能落地冻结链."""
    from hsr_nous.adapters.template_generator import _enemy_ironthorn_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Hoarfrost of Eternal Isolation")
    action, hooks = _enemy_ironthorn_action(raw, semantic)
    assert hooks[0]["effects"][0]["apply_chance"] == chance
    assert hooks[0]["effects"][0]["modifier"]["duration"] == duration
    assert hooks[1]["effects"][0]["scaling_atk"] == delayed_ratio
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hero = engine.state.actors["hero"]
    engine._enemy_turn(engine.state.actors["enemy"])
    modifier = hero.modifiers[f"ENEMY_{skill_id}_FREEZE"]
    assert modifier.control_kind == "freeze" and modifier.prevent_action
    hp_before = hero.current_hp
    engine.bus.emit("on_turn_start", {"actor": "hero"}, engine.state)

    assert hero.current_hp < hp_before


def test_gusto_monitor_retargets_and_expires(tmp_path):
    """Malefic Ape：猱击耗 Gusto，战技转移监视，耗尽移除并跳过空资源攻击."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2023020")
    assert {a["action_id"] for a in template["actions"]} == {
        "202302001", "202302002", "202302003", "202302004"}
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_skill", "name": "测试战技",
                     "action_type": "skill", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 1.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    compiled = _compiled(
        tmp_path, template["actions"],
        {"sequence": ["202302004", "202302001", "202302002", "202302001", "202302002"],
         "cooldown": {}, "initial_cooldown": {}},
        custom_resources=template["custom_resources"], team=team, hooks=template["hooks"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    h1 = engine.state.actors["h1"]
    h2 = engine.state.actors["h2"]
    marker_id = "ENEMY_202302004_MONITORED"

    engine._enemy_turn(enemy)
    assert enemy.resources["gusto"] == 3 and marker_id in h1.modifiers
    h1_hp = h1.current_hp
    engine._enemy_turn(enemy)
    assert enemy.resources["gusto"] == 2 and h1.current_hp < h1_hp

    h2_skill = compiled.actions_by_actor["h2"][0]
    engine._execute_action(h2, h2_skill, forced_target=enemy)
    engine.bus.emit("on_action", {
        "actor": "h2", "action_type": "skill", "action_id": "h2_skill",
        "target_type": "single", "target": "enemy", "sp_consumed": 0, "actor_type": "character",
    }, engine.state)
    assert marker_id not in h1.modifiers and marker_id in h2.modifiers
    h2_hp = h2.current_hp
    engine._enemy_turn(enemy)
    assert enemy.resources["gusto"] == 1 and h2.current_hp < h2_hp

    engine._enemy_turn(enemy)
    assert enemy.resources["gusto"] == 0
    assert marker_id not in h1.modifiers and marker_id not in h2.modifiers
    next_action = engine._select_enemy_policy_action(enemy)
    assert next_action.action_id == "202302004"


def test_cruelty_follows_friendly_and_dominated_hits_without_recursion(tmp_path):
    """Soulhook Sovereign：友方与支配攻击各追加一次雷伤，追加段不再自触发."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.state import Modifier

    template = generate_enemy_template("2004014")
    template["actions"] = []
    template.pop("policy", None)
    template["hooks"] = [h for h in template["hooks"]
                         if any(eff.get("name") == "cruelty" for eff in h["effects"])]
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 100, "def": 0, "spd": 300, "max_toughness": 30},
        "weakness": [], "actions": [{**_action("dummy_basic"), "scaling": [{"atk": 1.0}]}],
    }
    (tmp_path / "enemies").mkdir()
    for enemy_id, data in (("2004014", template), ("dummy", dummy)):
        (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic",
                     "target_type": "ally_single" if actor_id == "h2" else "single",
                     "damage_type": "physical", "scaling": [{"atk": 1.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2004014"}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    h1 = engine.state.actors["h1"]
    h2 = engine.state.actors["h2"]
    engine._apply_modifier(h1, Modifier(
        modifier_id="TEST_SHOCK", name="Shock", modifier_type="dot",
        dot_element="thunder", dot_ratio=0.1, duration=3))
    engine._apply_modifier(h2, Modifier(
        modifier_id="TEST_DOMINATE", name="Dominated", modifier_type="debuff",
        debuff_kind="control", control_kind="dominate", duration=3))
    sources = []
    engine.bus.subscribe(
        "on_hp_decrease",
        lambda _event, payload, _ctx: sources.append(payload["source"])
        if payload["target"] == "h1" else None)
    dummy = engine.state.actors["dummy"]
    engine._execute_action(dummy, compiled.actions_by_actor["dummy"][0], forced_target=h1)
    engine._execute_action(h2, compiled.actions_by_actor["h2"][0], forced_target=h1)

    assert sources == ["dummy", "2004014", "h2", "2004014"]


@pytest.mark.parametrize(("enemy_id", "skill_id", "name"), [
    ("1005010", "100501006", "The Creation's Prelude"),
    ("1013012", "101301203", "Overcombust Order"),
    ("4032070", "403207002", "A Fool's Defiance"),
])
def test_timed_charge_description_variants(tmp_path, enemy_id, skill_id, name):
    """纯蓄力的多种语序只生成推进序列的 self action，不附带虚构效果."""
    from hsr_nous.adapters.template_generator import _enemy_timed_charge_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == name)
    action = _enemy_timed_charge_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}})
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = _watch_enemy_actions(engine)
    engine.setup()
    engine._enemy_turn(engine.state.actors["enemy"])

    assert seen == [skill_id]
    assert not engine.state.actors["enemy"].modifiers


def test_arboreal_thorns_uses_raw_ratio_when_text_omits_it(tmp_path):
    """Arboreal Thorns：原文省略伤害倍率时由 TBGD 倍率槽补齐，其余状态逐项一致."""
    from hsr_nous.adapters.template_generator import _enemy_wind_shear_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2023030") if r["skill_id"] == "202303003")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2023030")["en"])["skills"]
                    if s["name"] == "Arboreal Thorns")
    action, hook = _enemy_wind_shear_action(raw, semantic)
    assert action["scaling"] == [{"atk": 3.0}]
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["202303003"], "cooldown": {}, "initial_cooldown": {}},
        hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hero = engine.state.actors["hero"]
    engine._enemy_turn(engine.state.actors["enemy"])
    modifier = hero.modifiers["ENEMY_202303003_WIND_SHEAR"]
    assert modifier.dot_ratio == 0.7 and modifier.duration == 3 and modifier.max_stack == 5
    hp_before = hero.current_hp
    engine._tick_dots(hero)

    assert hero.current_hp < hp_before


def test_double_waxing_moon_guides_sixfold_to_locked_targets(tmp_path):
    """Moonlit Pegasus：先锁两目标，Sixfold 只打锁定者并施加 Oronyx's Mark."""
    from hsr_nous.adapters.template_generator import (
        _enemy_double_waxing_moon_action, _enemy_sixfold_plenilune_action)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    semantics = get_enemy_mechanics(get_monster_meta("4023020")["en"])["skills"]
    raw_skills = get_enemy_skills("4023020")
    charge_action, charge_hook = _enemy_double_waxing_moon_action(
        next(r for r in raw_skills if r["skill_id"] == "402302003"),
        next(s for s in semantics if s["name"] == "Double Waxing Moon"))
    attack_action, attack_hook = _enemy_sixfold_plenilune_action(
        next(r for r in raw_skills if r["skill_id"] == "402302004"),
        next(s for s in semantics if s["name"] == "Sixfold Plenilune"))
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 0.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3")]
    compiled = _compiled(
        tmp_path, [charge_action, attack_action],
        {"sequence": ["402302003", "402302004"], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=[charge_hook, attack_hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    engine._enemy_turn(enemy)
    lock_id = "ENEMY_402302003_LOCK_ON"
    assert lock_id in engine.state.actors["h1"].modifiers
    assert lock_id in engine.state.actors["h2"].modifiers
    assert lock_id not in engine.state.actors["h3"].modifiers
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2", "h3")}
    engine._enemy_turn(enemy)

    for actor_id in ("h1", "h2", "h3"):
        state = engine.state.actors[actor_id]
        if actor_id == "h3":
            assert state.current_hp == old_hp[actor_id]
            assert "ENEMY_ORONYX_MARK" not in state.modifiers
        else:
            assert state.current_hp < old_hp[actor_id]
            assert "ENEMY_ORONYX_MARK" in state.modifiers


def test_light_future_guides_praise_aquila_blast_and_mark(tmp_path):
    """Noontide Gryphon：Praise Aquila 命中锁定主目标与相邻并施加 Aquila's Mark."""
    from hsr_nous.adapters.template_generator import _enemy_light_future_action, _enemy_praise_aquila_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    semantics = get_enemy_mechanics(get_monster_meta("4023010")["en"])["skills"]
    raw_skills = get_enemy_skills("4023010")
    charge_action, charge_hook = _enemy_light_future_action(
        next(r for r in raw_skills if r["skill_id"] == "402301003"),
        next(s for s in semantics if s["name"] == "Light the Future"))
    attack_action, attack_hook = _enemy_praise_aquila_action(
        next(r for r in raw_skills if r["skill_id"] == "402301004"),
        next(s for s in semantics if s["name"] == "Praise Aquila"))
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 0.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3")]
    compiled = _compiled(
        tmp_path, [charge_action, attack_action],
        {"sequence": ["402301003", "402301004"], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=[charge_hook, attack_hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    engine._enemy_turn(enemy)
    lock_id = "ENEMY_402301003_LOCK_ON"
    assert lock_id in engine.state.actors["h1"].modifiers
    assert lock_id not in engine.state.actors["h2"].modifiers
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2", "h3")}
    engine._enemy_turn(enemy)

    for actor_id in ("h1", "h2", "h3"):
        state = engine.state.actors[actor_id]
        if actor_id == "h3":
            assert state.current_hp == old_hp[actor_id]
            assert "ENEMY_AQUILA_MARK" not in state.modifiers
        else:
            assert state.current_hp < old_hp[actor_id]
            assert "ENEMY_AQUILA_MARK" in state.modifiers


@pytest.mark.parametrize(("enemy_id", "skill_id"), [
    ("4023011", "402301104"),
    ("4023012", "402301204"),
])
def test_light_future_all_variant_locks_four_targets(tmp_path, enemy_id, skill_id):
    """Solblaze Winged Beast：Light the Future 全体变体锁定四名角色."""
    from hsr_nous.adapters.template_generator import _enemy_light_future_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Light the Future")
    assert _enemy_light_future_action(dict(raw, param_list=[3.0]), semantic) is None
    action, hook = _enemy_light_future_action(raw, semantic)
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 0.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3", "h4")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._enemy_turn(engine.state.actors["enemy"])

    lock_id = f"ENEMY_{skill_id}_LOCK_ON"
    for actor_id in ("h1", "h2", "h3", "h4"):
        modifier = engine.state.actors[actor_id].modifiers[lock_id]
        assert modifier.lock_on


def test_triple_waning_moon_hits_rightmost_three_and_marks(tmp_path):
    """Moonlit Pegasus：Triple Waning Moon 从右侧横扫三个目标并施加 Oronyx's Mark."""
    from hsr_nous.adapters.template_generator import _enemy_sweep_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("4023020") if r["skill_id"] == "402302002")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("4023020")["en"])["skills"]
                    if s["name"] == "Triple Waning Moon")
    action, hook = _enemy_sweep_action(raw, semantic)
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 0.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3", "h4")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["402302002"], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp
              for actor_id in ("h1", "h2", "h3", "h4")}
    engine._enemy_turn(engine.state.actors["enemy"])

    for actor_id in ("h1", "h2", "h3", "h4"):
        state = engine.state.actors[actor_id]
        if actor_id == "h1":
            assert state.current_hp == old_hp[actor_id]
            assert "ENEMY_ORONYX_MARK" not in state.modifiers
        else:
            assert state.current_hp < old_hp[actor_id]
            assert "ENEMY_ORONYX_MARK" in state.modifiers


@pytest.mark.parametrize(("enemy_id", "skill_id", "expected_names"), [
    ("1004020", "100402005", {"Silvermane Gunner", "Silvermane Cannoneer"}),
    ("1004027", "100402705", {"Silvermane Gunner", "Silvermane Cannoneer"}),
    ("1004021", "100402105", {"Silvermane Gunner"}),
])
def test_siege_support_summons_and_locks_target(tmp_path, enemy_id, skill_id, expected_names):
    """Gepard：Siege Support 按原始名单召唤并锁定单体目标."""
    from hsr_nous.adapters.template_generator import _enemy_siege_support_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_detail, get_enemy_mechanics, get_enemy_skills, get_monster_meta)

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Siege Support")
    action, hooks, specs = _enemy_siege_support_action(
        raw, semantic, get_enemy_detail(enemy_id), get_monster_meta, level=80)
    template = generate_enemy_template(enemy_id)
    template.update({
        "actions": [action], "hooks": hooks, "summons": specs,
        "policy": {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
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
        "enemies": [{"enemy_template": enemy_id, "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._enemy_turn(engine.state.actors[enemy_id])

    assert len(specs) == 2
    names = set()
    for spec in specs:
        actor = engine.state.actors[f"{spec['summon_id']}__{enemy_id}"]
        assert actor.alive and actor.actor.summoner_id == enemy_id
        names.add(actor.actor.name)
    assert names == expected_names
    assert f"ENEMY_{skill_id}_LOCK_ON" in engine.state.actors["hero"].modifiers


def test_barrenness_hits_both_sides_except_caster(tmp_path):
    """Hoolay：Barrenness 分别命中我方与其他敌方，但不命中施放者自身."""
    from hsr_nous.adapters.template_generator import _enemy_barrenness_earth_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2034014") if r["skill_id"] == "203401403")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2034014")["en"])["skills"]
                    if s["name"] == "Barrenness of Earth Gouged")
    action, hook = _enemy_barrenness_earth_action(raw, semantic)
    assert hook["effects"][0]["scaling_atk"] == 2.2
    assert hook["effects"][1]["scaling_atk"] == 30.0
    template = generate_enemy_template("2034014")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["203401403"], "cooldown": {}, "initial_cooldown": {}},
    })
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 0, "def": 0, "spd": 10, "max_toughness": 30},
        "weakness": [], "actions": [],
    }
    (tmp_path / "enemies").mkdir()
    for enemy_id, data in (("2034014", template), ("dummy", dummy)):
        (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
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
        "enemies": [{"enemy_template": "2034014"}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    owner = engine.state.actors["2034014"]
    hero = engine.state.actors["hero"]
    dummy = engine.state.actors["dummy"]
    owner_hp = owner.current_hp
    hero_hp = hero.current_hp
    dummy_hp = dummy.current_hp
    engine._enemy_turn(owner)

    assert owner.current_hp == owner_hp
    assert hero.current_hp < hero_hp
    assert dummy.current_hp < dummy_hp


def test_calamity_power_charge_and_but_suffering(tmp_path):
    """Flame Reaver：Dying Sobs 得 6 层，But Suffering 打 12+1 段并耗尽."""
    from hsr_nous.adapters.template_generator import _enemy_but_suffering_action, _enemy_calamity_charge_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    semantics = get_enemy_mechanics(get_monster_meta("4034013")["en"])["skills"]
    raw_skills = get_enemy_skills("4034013")
    charge = _enemy_calamity_charge_action(
        next(r for r in raw_skills if r["skill_id"] == "403401305"),
        next(s for s in semantics if s["name"] == "Dying Sobs"))
    attack, hook = _enemy_but_suffering_action(
        next(r for r in raw_skills if r["skill_id"] == "403401307"),
        next(s for s in semantics if s["name"] == "But Suffering is Essential"))
    silent = _enemy_calamity_charge_action(
        next(r for r in raw_skills if r["skill_id"] == "403401306"),
        next(s for s in semantics if s["name"] == "Silent Sorrow"))
    assert silent["resource_gain"] == {"calamity_power": 8}
    compiled = _compiled(
        tmp_path, [charge, attack],
        {"sequence": ["403401305", "403401307", "403401307"],
         "cooldown": {}, "initial_cooldown": {}},
        custom_resources={"calamity_power": {"max": "inf", "current": 0}}, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    engine._enemy_turn(enemy)
    assert enemy.resources["calamity_power"] == 6
    hits = []
    engine.bus.subscribe(
        "on_hp_decrease", lambda _event, payload, _ctx: hits.append(payload))
    engine._enemy_turn(enemy)

    assert len(hits) == 13
    assert enemy.resources["calamity_power"] == 0
    assert engine._select_enemy_policy_action(enemy).action_id == "403401305"


def test_cry_not_uses_main_and_per_stack_variants(tmp_path):
    """Flame Reaver：Silent Sorrow 得 8 层，Cry Not 主击后追加 8 段并耗尽."""
    from hsr_nous.adapters.template_generator import _enemy_calamity_charge_action, _enemy_cry_not_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    semantics = get_enemy_mechanics(get_monster_meta("4034013")["en"])["skills"]
    raw_skills = get_enemy_skills("4034013")
    charge = _enemy_calamity_charge_action(
        next(r for r in raw_skills if r["skill_id"] == "403401306"),
        next(s for s in semantics if s["name"] == "Silent Sorrow"))
    attack = _enemy_cry_not_action(
        next(r for r in raw_skills if r["skill_id"] == "403401308"),
        next(s for s in semantics if s["name"] == "Cry Not For The Discarded"))
    compiled = _compiled(
        tmp_path, [charge, attack],
        {"sequence": ["403401306", "403401308"], "cooldown": {}, "initial_cooldown": {}},
        custom_resources={"calamity_power": {"max": "inf", "current": 0}})
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    engine._enemy_turn(enemy)
    assert enemy.resources["calamity_power"] == 8
    hits = []
    engine.bus.subscribe(
        "on_hp_decrease", lambda _event, payload, _ctx: hits.append(payload))
    engine._enemy_turn(enemy)

    assert len(hits) == 9
    assert hits[0]["amount"] == pytest.approx(hits[1]["amount"] * 6.25)
    assert enemy.resources["calamity_power"] == 0


def test_hemotort_teethgrind_shield_recoil_keeps_one_toughness(tmp_path):
    """Judge of Oblivion：有盾时免伤并削韧至 1，无盾后恢复正常伤害."""
    from hsr_nous.adapters.template_generator import _enemy_hemotort_teethgrind_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import ShieldInstance

    raw = next(r for r in get_enemy_skills("4064010") if r["skill_id"] == "406401001")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("4064010")["en"])["skills"]
                    if s["name"] == "Hemotort Teethgrind")
    action, hooks = _enemy_hemotort_teethgrind_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["406401001"], "cooldown": {}, "initial_cooldown": {}},
        hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    enemy.toughness = 50.0
    hero = engine.state.actors["hero"]
    hero.shields.append(ShieldInstance(
        shield_id="test_shield", name="test", remaining=100000, source_id="test"))
    old_hp = hero.current_hp
    engine._enemy_turn(enemy)

    assert hero.current_hp == old_hp
    assert enemy.toughness == 1.0 and not enemy.broken
    hero.shields.clear()
    engine._enemy_turn(enemy)
    assert hero.current_hp < old_hp
    assert enemy.toughness == 1.0


def test_hemotort_teethgrind_350_variant_deals_damage_without_shield(tmp_path):
    """350% 实例在无盾时按自身倍率结算，而不是复用 450% 模板."""
    from hsr_nous.adapters.template_generator import _enemy_hemotort_teethgrind_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("4064011") if r["skill_id"] == "406401101")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("4064011")["en"])["skills"]
                    if s["name"] == "Hemotort Teethgrind")
    action, hooks = _enemy_hemotort_teethgrind_action(raw, semantic)
    assert hooks[0]["effects"][0]["scaling_atk"] == 3.5
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["406401101"], "cooldown": {}, "initial_cooldown": {}},
        hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hero = engine.state.actors["hero"]
    old_hp = hero.current_hp
    engine._enemy_turn(engine.state.actors["enemy"])
    assert hero.current_hp < old_hp


def test_hemotort_teethgrind_shield_recoil_also_deals_damage(tmp_path):
    """Arbiter of the Lost Abyss：有盾仍造成伤害，同时额外削韧 60."""
    from hsr_nous.adapters.template_generator import _enemy_hemotort_teethgrind_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import ShieldInstance

    raw = next(r for r in get_enemy_skills("4064012") if r["skill_id"] == "406401201")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("4064012")["en"])["skills"]
                    if s["name"] == "Hemotort Teethgrind")
    action, hooks = _enemy_hemotort_teethgrind_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["406401201"], "cooldown": {}, "initial_cooldown": {}},
        hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    enemy.toughness = 100.0
    hero = engine.state.actors["hero"]
    hero.shields.append(ShieldInstance(
        shield_id="test_shield", name="test", remaining=100000, source_id="test"))
    old_hp = hero.current_hp
    engine._enemy_turn(enemy)

    assert hero.current_hp == old_hp
    assert hero.shields[0].remaining < 100000
    assert enemy.toughness == 40.0 and not enemy.broken


def test_power_amplification_stacks_for_all_friendlies(tmp_path):
    """Svarog：Power Amplification 每次施放为全体友方叠加 15% 增伤."""
    from hsr_nous.adapters.template_generator import _enemy_power_amplification_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("1014011") if r["skill_id"] == "101401112")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("1014011")["en"])["skills"]
                    if s["name"] == "Power Amplification")
    action, hook = _enemy_power_amplification_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["101401112"], "cooldown": {}, "initial_cooldown": {}},
        hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    for _ in range(2):
        engine._enemy_turn(enemy)

    modifier = enemy.modifiers["ENEMY_101401112_POWER_AMPLIFICATION"]
    assert modifier.stacks == 2
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["all"] == pytest.approx(0.3)


def test_honors_red_queen_stacks_argenti_damage_boost(tmp_path):
    """The Honored：通常给 Argenti 叠一层增伤，Soulfreed 时单次叠两层."""
    from hsr_nous.adapters.template_generator import _enemy_honors_red_queen_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("3021020")["en"])["skills"]
                    if s["name"] == "Honors of the Red Queen")
    for enemy_id in ("3021021", "3021023"):
        raw = next(r for r in get_enemy_skills(enemy_id) if r["trigger_key"] == "Skill01")
        assert _enemy_honors_red_queen_action(raw, semantic) is None
    raw = next(r for r in get_enemy_skills("3021020") if r["skill_id"] == "302102001")
    action, hooks = _enemy_honors_red_queen_action(raw, semantic)
    template = generate_enemy_template("3021020")
    template.update({
        "actions": [action], "hooks": hooks,
        "policy": {"sequence": ["302102001"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3021020.yaml").write_text(
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
        "enemies": [{"enemy_template": "3021020", "level": 80},
                    {"enemy_template": "3024010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    statue = engine.state.actors["3021020"]
    argenti = engine.state.actors["3024010"]
    modifier_id = "ENEMY_302102001_DMG_BOOST"
    base = engine.pipeline.effective_stats(argenti)["dmg_bonus"].get("all", 0.0)

    engine._enemy_turn(statue)
    modifier = argenti.modifiers[modifier_id]
    assert modifier.stacks == 1 and modifier.duration == 3
    assert engine.pipeline.effective_stats(argenti)["dmg_bonus"]["all"] == pytest.approx(base + 0.12)

    del argenti.modifiers[modifier_id]
    engine._apply_modifier(statue, Modifier(
        modifier_id="ENEMY_SOULFREED", name="Soulfreed", modifier_type="buff", duration=0))
    engine._enemy_turn(statue)
    modifier = argenti.modifiers[modifier_id]
    assert modifier.stacks == 2
    assert engine.pipeline.effective_stats(argenti)["dmg_bonus"]["all"] == pytest.approx(base + 0.24)


def test_so_cometh_beauty_soulfreed_switches_aoe_ratio(tmp_path):
    """Speartip：常态 AoE 240%，Soulfreed 时改为 400%，两种路径互斥."""
    from hsr_nous.adapters.template_generator import _enemy_so_cometh_beauty_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("3021030")["en"])["skills"]
                    if s["name"] == "So Cometh Beauty's Knight")
    bad_raw = next(r for r in get_enemy_skills("3021031") if r["skill_id"] == "302103101")
    assert _enemy_so_cometh_beauty_action(bad_raw, semantic) is None
    template = generate_enemy_template("3021030")
    assert [action["action_id"] for action in template["actions"]] == ["302103001"]
    assert template["policy"]
    template["policy"]["cooldown"] = {}
    template["policy"]["initial_cooldown"] = {}
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3021030.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 0.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": "3021030", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3021030"]
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2")}

    engine._enemy_turn(enemy)
    normal_damage = {actor_id: old_hp[actor_id] - engine.state.actors[actor_id].current_hp
                     for actor_id in ("h1", "h2")}
    assert all(amount > 0 for amount in normal_damage.values())
    for actor_id in ("h1", "h2"):
        engine.state.actors[actor_id].current_hp = old_hp[actor_id]
    engine._apply_modifier(enemy, Modifier(
        modifier_id="ENEMY_SOULFREED", name="Soulfreed", modifier_type="buff", duration=0))
    engine._enemy_turn(enemy)

    for actor_id in ("h1", "h2"):
        empowered_damage = old_hp[actor_id] - engine.state.actors[actor_id].current_hp
        assert empowered_damage == pytest.approx(normal_damage[actor_id] * 4.0 / 2.4)


def test_bhf_heavenly_fire_switches_primary_ratio(tmp_path):
    """BHF: Heavenly Fire：强化只改主目标 220%→240%，邻目标保持 160%."""
    from hsr_nous.adapters.template_generator import _enemy_bhf_heavenly_fire_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    for enemy_id in ("3024020", "302402001", "302402006", "302402009",
                     "3024021", "3024022", "3024023"):
        raw = next(r for r in get_enemy_skills(enemy_id) if r["trigger_key"] == "Skill02")
        semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                        if s["name"] == "BHF: Heavenly Fire")
        action, hooks = _enemy_bhf_heavenly_fire_action(raw, semantic)
        assert action["target_type"] == "blast"
        assert hooks[0]["effects"][0]["scaling_atk"] == 2.2
        assert hooks[0]["effects"][1]["scaling_atk"] == 1.6
        assert hooks[1]["effects"][0]["scaling_atk"] == 2.4
        assert hooks[0]["effects"][0]["toughness_dmg"] == 10
        assert hooks[0]["effects"][1]["toughness_dmg"] == 5
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 0.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [action["action_id"]], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2", "h3")}

    engine._enemy_turn(enemy)
    normal_damage = {actor_id: old_hp[actor_id] - engine.state.actors[actor_id].current_hp
                     for actor_id in ("h1", "h2")}
    assert normal_damage["h1"] > 0 and normal_damage["h2"] > 0
    assert engine.state.actors["h3"].current_hp == old_hp["h3"]
    for actor_id in ("h1", "h2"):
        engine.state.actors[actor_id].current_hp = old_hp[actor_id]
    engine._apply_modifier(enemy, Modifier(
        modifier_id="ENEMY_SECONDARY_COMBUSTION", name="Secondary Combustion",
        modifier_type="buff", duration=0))
    engine._enemy_turn(enemy)

    empowered_primary = old_hp["h1"] - engine.state.actors["h1"].current_hp
    empowered_adjacent = old_hp["h2"] - engine.state.actors["h2"].current_hp
    assert empowered_primary == pytest.approx(normal_damage["h1"] * 2.4 / 2.2)
    assert empowered_adjacent == pytest.approx(normal_damage["h2"])


def test_ice_dot_conversion_split_damage_and_dot(tmp_path):
    """Undine/Embrace：保留部分直伤，剩余倍率转成两回合 Ice DoT."""
    from hsr_nous.adapters.template_generator import _enemy_ice_dot_conversion_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    for enemy_id, skill_id, semantic_name, ratio, conversion in (
            ("4052010", "405201001", "Undine's Fluttering Hem", 1.8, 0.7),
            ("4052012", "405201201", "Undine's Fluttering Hem", 1.8, 0.7),
            ("4053010", "405301005", "Embrace From the Waves", 2.5, 0.5),
            ("4053012", "405301205", "Embrace From the Waves", 2.5, 0.5)):
        raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
        semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                        if s["name"] == semantic_name)
        action, hooks = _enemy_ice_dot_conversion_action(raw, semantic)
        assert hooks[1]["effects"][0]["scaling_atk"] == pytest.approx(ratio * (1 - conversion))
        dot = hooks[1]["effects"][1]["modifier"]
        assert dot["dot_ratio"] == pytest.approx(ratio * conversion / 2)
        assert dot["duration"] == 2 and dot["dot_element"] == "ice"
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 0.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [action["action_id"]], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    h1, h2 = engine.state.actors["h1"], engine.state.actors["h2"]
    old_hp = h1.current_hp

    engine._enemy_turn(enemy)
    normal_damage = old_hp - h1.current_hp
    assert normal_damage > 0
    modifier_id = "ENEMY_405301205_DOT_CONVERSION"
    assert modifier_id not in h1.modifiers and modifier_id not in h2.modifiers
    h1.current_hp = old_hp
    engine._apply_modifier(enemy, Modifier(
        modifier_id="405301001", name="405301001", modifier_type="buff", duration=0))
    engine._enemy_turn(enemy)

    converted_damage = old_hp - h1.current_hp
    assert converted_damage == pytest.approx(normal_damage * 0.5)
    for target in (h1, h2):
        modifier = target.modifiers[modifier_id]
        assert modifier.duration == 2 and modifier.dot_ratio == pytest.approx(0.625)
        assert engine.pipeline.dot_tick_base(target, modifier) == pytest.approx(
            modifier.dot_source_atk * 0.625)


def test_happiness_charm_random_branches(tmp_path):
    """Happiness Charm：expected 加攻，roll 分别覆盖拉条与 Strong Reverberation."""
    from hsr_nous.adapters.template_generator import _enemy_happiness_charm_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.pipeline import MODE_ROLL

    raw = next(r for r in get_enemy_skills("5012011") if r["skill_id"] == "501201102")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("5012011")["en"])["skills"]
                    if s["name"] == "Happiness Charm")
    action, hook = _enemy_happiness_charm_action(raw, semantic)
    template = generate_enemy_template("5012011")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["501201102"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "5012011.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "5012011", "level": 80},
                    {"actor_id": "ally", "name": "友方假人", "level": 80,
                     "hp": 1e9, "spd": 10, "max_toughness": 30}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}

    def _run(mode, seed):
        compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
        engine = CombatEngine.from_compiled(compiled, mode=mode, seed=seed, initial_energy_ratio=0.0)
        engine.setup()
        return engine

    engine = _run(MODE_EXPECTED, None)
    enemy = engine.state.actors["5012011"]
    base_atk = engine.pipeline.effective_stats(enemy)["atk"]
    engine._enemy_turn(enemy)
    assert engine.pipeline.effective_stats(enemy)["atk"] == pytest.approx(base_atk * 1.5)
    assert "ENEMY_501201102_STRONG_REVERB" not in engine.state.actors["ally"].modifiers

    engine = _run(MODE_ROLL, 0)
    enemy = engine.state.actors["5012011"]
    ally = engine.state.actors["ally"]
    before = {actor_id: engine.scheduler._remaining[engine.scheduler.handle_of(actor_id)]
              for actor_id in ("5012011", "ally")}
    engine._enemy_turn(enemy)
    for actor_id in ("5012011", "ally"):
        remaining = engine.scheduler._remaining[engine.scheduler.handle_of(actor_id)]
        assert remaining == pytest.approx(before[actor_id] * 0.5)
    assert "ENEMY_501201102_ATK_UP" not in enemy.modifiers

    engine = _run(MODE_ROLL, 42)
    enemy = engine.state.actors["5012011"]
    ally = engine.state.actors["ally"]
    engine._enemy_turn(enemy)
    assert ally.modifiers["ENEMY_501201102_STRONG_REVERB"].prevent_action
    assert "ENEMY_501201102_STRONG_REVERB" not in enemy.modifiers


def test_phonation_unbound_shield_and_damage_boost(tmp_path):
    """Cacophonic Conductor：Phonation Unbound 生成 9% Max HP 护盾并增伤 20%."""
    from hsr_nous.adapters.template_generator import _enemy_phonation_unbound_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("3025013") if r["skill_id"] == "302501309")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("3025013")["en"])["skills"]
                    if s["name"] == "Phonation Unbound")
    action, hook = _enemy_phonation_unbound_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["302501309"], "cooldown": {}, "initial_cooldown": {}},
        hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    max_hp = engine.pipeline.effective_stats(enemy)["hp"]
    engine._enemy_turn(enemy)

    assert enemy.shields[0].remaining == pytest.approx(max_hp * 0.09)
    assert engine.pipeline.effective_stats(enemy)["dmg_bonus"]["all"] == pytest.approx(0.2)


@pytest.mark.parametrize(("enemy_id", "skill_id", "semantic_name", "base_chance", "heal_ratio", "vulnerability"), [
    ("3025010", "302501003", "Vaneggiando", 2.0, 0.35, 0.5),
    ("3025013", "302501303", "Vaneggiando", 2.0, 0.05, 0.5),
    ("3003040", "300304002", "All Is Calm", 1.2, 0.35, 0.5),
    ("3003043", "300304302", "All Is Calm", 1.5, 0.05, 0.2),
])
def test_alien_dream_heal_and_dispel(
        tmp_path, enemy_id, skill_id, semantic_name, base_chance, heal_ratio, vulnerability):
    """Alien Dream 禁行动易伤，按首领类型回血并在受击后解除."""
    from hsr_nous.adapters.template_generator import _enemy_vaneggiando_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == semantic_name)
    action, hooks = _enemy_vaneggiando_action(raw, semantic, get_monster_meta(enemy_id)["en"])
    assert hooks[0]["effects"][0]["apply_chance"] == base_chance
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 100000, "atk": 1000, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic",
                     "target_type": "ally_single" if actor_id == "h2" else "single",
                     "damage_type": "physical", "scaling": [{"atk": 1.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    h1 = engine.state.actors["h1"]
    engine._enemy_turn(engine.state.actors["enemy"])
    modifier_id = f"ENEMY_{skill_id}_ALIEN_DREAM"
    modifier = h1.modifiers[modifier_id]
    assert modifier.prevent_action and modifier.duration == 2
    assert engine.pipeline.effective_stats(h1)["vulnerability"] == vulnerability
    h1.current_hp = 50000.0
    engine.bus.emit("on_turn_start", {"actor": "h1"}, engine.state)
    assert h1.current_hp == pytest.approx(50000 + 100000 * heal_ratio)
    engine._execute_action(
        engine.state.actors["h2"], compiled.actions_by_actor["h2"][0], forced_target=h1)

    assert modifier_id not in h1.modifiers


def test_sleep_in_heavenly_peace_applies_alien_dream_to_all(tmp_path):
    """Tomorrow in Harmonious Chords：Sleep In Heavenly Peace 给全体施加 Alien Dream."""
    from hsr_nous.adapters.template_generator import _enemy_vaneggiando_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("3003040") if r["skill_id"] == "300304005")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("3003040")["en"])["skills"]
                    if s["name"] == "Sleep In Heavenly Peace")
    action, hooks = _enemy_vaneggiando_action(raw, semantic, get_monster_meta("3003040")["en"])
    assert action["target_type"] == "aoe" and hooks[0]["effects"][0]["apply_chance"] == 0.5
    bad_raw = next(r for r in get_enemy_skills("3003043") if r["skill_id"] == "300304305")
    assert _enemy_vaneggiando_action(bad_raw, semantic, get_monster_meta("3003043")["en"]) is None
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 100000, "atk": 1000, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic",
                     "target_type": "ally_single" if actor_id == "h2" else "single",
                     "damage_type": "physical", "scaling": [{"atk": 1.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["300304005"], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._enemy_turn(engine.state.actors["enemy"])
    modifier_id = "ENEMY_300304005_ALIEN_DREAM"
    for actor_id in ("h1", "h2"):
        target = engine.state.actors[actor_id]
        assert target.modifiers[modifier_id].prevent_action
        assert engine.pipeline.effective_stats(target)["vulnerability"] == 0.5
        target.current_hp = 50000.0
        engine.bus.emit("on_turn_start", {"actor": actor_id}, engine.state)
        assert target.current_hp == pytest.approx(85000.0)

    engine._execute_action(
        engine.state.actors["h2"], compiled.actions_by_actor["h2"][0],
        forced_target=engine.state.actors["h1"])
    assert modifier_id not in engine.state.actors["h1"].modifiers
    assert modifier_id in engine.state.actors["h2"].modifiers


def test_wash_away_all_sins_retriggers_and_dispels_all_dots(tmp_path):
    """Present Inebriated in Revelry：全体 DoT 以 125% 立即结算并解除，非 DoT 保留."""
    from hsr_nous.adapters.template_generator import _enemy_wash_away_sins_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("3003050") if r["skill_id"] == "300305005")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("3003050")["en"])["skills"]
                    if s["name"] == "Wash Away All Sins For You")
    action, hook = _enemy_wash_away_sins_action(raw, semantic)
    assert "scaling" not in action and hook["effects"][0]["ratio"] == 1.25
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    compiled = _compiled(tmp_path, [action], team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    old_hp = {}
    for actor_id in ("h1", "h2"):
        target = engine.state.actors[actor_id]
        engine._apply_modifier_spec(target, {
            "modifier_id": f"TEST_DOT_{actor_id}", "name": "测试持续伤害", "modifier_type": "dot",
            "dot_element": "wind", "dot_ratio": 0.5, "duration": 3, "dispellable": True,
        }, enemy)
        old_hp[actor_id] = target.current_hp
    engine._apply_modifier_spec(engine.state.actors["h1"], {
        "modifier_id": "TEST_DEBUFF", "name": "测试减益", "modifier_type": "debuff", "duration": 3,
    }, enemy)
    retriggered = []
    engine.bus.subscribe(
        "on_dot_retrigger", lambda _et, payload, _ctx: retriggered.append(payload["modifier_id"]))

    engine._enemy_turn(enemy)

    assert sorted(retriggered) == ["TEST_DOT_h1", "TEST_DOT_h2"]
    for actor_id in ("h1", "h2"):
        target = engine.state.actors[actor_id]
        assert target.current_hp < old_hp[actor_id]
        assert f"TEST_DOT_{actor_id}" not in target.modifiers
    assert "TEST_DEBUFF" in engine.state.actors["h1"].modifiers


@pytest.mark.parametrize("enemy_id", ["8003010", "800301018", "800301020"])
def test_freezing_point_gates_rain_and_chilling_bonus(tmp_path, enemy_id):
    """Freezing Point 形态门控：先解锁 Rain，再让 Chilling Lament 对 Frozen 追加."""
    from hsr_nous.adapters.template_generator import (
        _enemy_chilling_lament_action, _enemy_everwinter_rain_action,
        _enemy_frosty_absorption_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    semantics = get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
    raw = {r["skill_id"]: r for r in get_enemy_skills(enemy_id)}
    frosty, frosty_hooks = _enemy_frosty_absorption_action(
        raw["800301002"], next(s for s in semantics if s["name"] == "Frosty Absorption"))
    rain, rain_hooks = _enemy_everwinter_rain_action(
        raw["800301003"], next(s for s in semantics if s["name"] == "Everwinter Rain"))
    chilling, chilling_hook = _enemy_chilling_lament_action(
        raw["800301001"], next(s for s in semantics if s["name"] == "Chilling Lament"))
    template = generate_enemy_template(enemy_id)
    template.update({
        "actions": [frosty, rain, chilling],
        "hooks": [*frosty_hooks, *rain_hooks, chilling_hook],
        "policy": {"sequence": ["800301002", "800301003", "800301001"],
                   "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [{"enemy_template": enemy_id, "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors[enemy_id]
    actions = compiled.actions_by_actor[enemy_id]
    assert not engine._available_if_ok(enemy, actions[1])
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2")}

    engine._enemy_turn(enemy)
    assert "ENEMY_800301002_FREEZING_POINT" in enemy.modifiers
    assert engine._enemy_policy_state[enemy_id]["dynamic_values"]["Phase_Flag"] == 2
    assert engine._available_if_ok(enemy, actions[1])
    assert all(engine.state.actors[actor_id].current_hp == old_hp[actor_id]
               for actor_id in ("h1", "h2"))

    engine._enemy_turn(enemy)
    for actor_id in ("h1", "h2"):
        target = engine.state.actors[actor_id]
        assert target.current_hp == pytest.approx(old_hp[actor_id] - 73.8)
        assert "ENEMY_800301003_FREEZE" in target.modifiers

    before_delayed = engine.state.actors["h1"].current_hp
    engine.bus.emit("on_turn_start", {"actor": "h1"}, engine.state)
    assert engine.state.actors["h1"].current_hp == pytest.approx(before_delayed - 36.9)
    before_chilling = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2")}
    engine._enemy_turn(enemy)
    assert engine.state.actors["h1"].current_hp == pytest.approx(before_chilling["h1"] - 129.15)
    assert engine.state.actors["h2"].current_hp == before_chilling["h2"]
    engine._remove_modifier(enemy, "ENEMY_800301002_FREEZING_POINT", "test")
    assert engine._enemy_policy_state[enemy_id]["dynamic_values"]["Phase_Flag"] == 1

    # 再跑未经手工改写的真实 ConfigAI：初始 Phase_Flag=1，冰点挂载后进入第二阶段。
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(generate_enemy_template(enemy_id), allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors[enemy_id]
    runtime = engine._enemy_policy_state[enemy_id]
    runtime["cooldown_left"] = {}
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == enemy_id else None)
    for _ in range(4):
        engine._enemy_turn(enemy)
        engine._tick_enemy_policy_cooldown(enemy_id)
    assert seen == ["800301001", "800301002", "800301003", "800301001"]
    assert runtime["dynamic_values"]["Phase_Flag"] == 2


@pytest.mark.parametrize("enemy_id", ["8003020", "8003021"])
def test_blazing_absorption_unlocks_rain_and_stacks_enkindle(tmp_path, enemy_id):
    """Spontaneous Combustion 解锁五段 Rain，每段都给目标叠 Enkindle."""
    from hsr_nous.adapters.template_generator import (
        _enemy_blazing_absorption_action, _enemy_rain_purifying_flames_action, generate_enemy_template)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    semantics = get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
    raw = {r["skill_id"]: r for r in get_enemy_skills(enemy_id)}
    blazing_id = f"{enemy_id}02"
    rain_id = f"{enemy_id}03"
    blazing, blazing_hook = _enemy_blazing_absorption_action(
        raw[blazing_id], next(s for s in semantics if s["name"] == "Blazing Absorption"))
    rain, rain_hook = _enemy_rain_purifying_flames_action(
        raw[rain_id], next(s for s in semantics if s["name"] == "Rain of Purifying Flames"))
    template = generate_enemy_template(enemy_id)
    template.update({
        "actions": [blazing, rain], "hooks": [blazing_hook, rain_hook],
        "policy": {"sequence": [blazing_id, rain_id], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": enemy_id, "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors[enemy_id]
    assert not engine._available_if_ok(enemy, compiled.actions_by_actor[enemy_id][1])
    seen = []
    engine.bus.subscribe(
        "after_being_hit", lambda _et, payload, _ctx: seen.append(payload["action_id"]))

    engine._enemy_turn(enemy)
    assert f"ENEMY_{blazing_id}_SPONTANEOUS_COMBUSTION" in enemy.modifiers
    assert engine._available_if_ok(enemy, compiled.actions_by_actor[enemy_id][1])
    engine._enemy_turn(enemy)

    hero = engine.state.actors["hero"]
    modifier = hero.modifiers[f"ENEMY_{rain_id}_ENKINDLE"]
    assert seen == [rain_id] * 5
    assert modifier.stacks == 5 and modifier.duration == 2 and modifier.dot_ratio == 0.5
    hp_before = hero.current_hp
    engine._tick_dots(hero)
    assert hero.current_hp < hp_before


@pytest.mark.parametrize("enemy_id", ["8003021"])
def test_bomb_warning_removes_enkindle(tmp_path, enemy_id):
    """Bomb Warning 蓄力时吸收全体目标身上的 Enkindle."""
    from hsr_nous.adapters.template_generator import _enemy_bomb_warning_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    bomb_id = f"{enemy_id}05"
    enkindle_id = f"ENEMY_{enemy_id}03_ENKINDLE"
    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == bomb_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Bomb Warning")
    action, hook = _enemy_bomb_warning_action(raw, semantic)
    compiled = _compiled(tmp_path, [action], hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    hero = engine.state.actors["hero"]
    engine._apply_modifier_spec(hero, {
        "modifier_id": enkindle_id, "name": "Enkindle", "modifier_type": "dot",
        "dot_element": "fire", "dot_ratio": 0.5, "duration": 2, "dispellable": True,
    }, enemy)

    engine._enemy_turn(enemy)

    assert enkindle_id not in hero.modifiers


@pytest.mark.parametrize(("skill_id", "semantic_name", "target_type", "immediate_id"), [
    ("801502203", "Entwining Roots: Abundance's Might", "single", "8012204"),
    ("801502204", "Entwining Roots: Havoc's Might", "single", "8012214"),
    ("801502212", "Entwining Roots: Paramount Writhe", "aoe", ""),
])
def test_entwining_roots_delays_and_advances_lotuses(
        tmp_path, skill_id, semantic_name, target_type, immediate_id):
    """Entwining Roots：伤害推条后，对应 Lotus 立即行动，其他单位不被误拉."""
    from hsr_nous.adapters.template_generator import _enemy_entwining_roots_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("8015022") if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8015022")["en"])["skills"]
                    if s["name"] == semantic_name)
    action, hook = _enemy_entwining_roots_action(raw, semantic)
    template = generate_enemy_template("8015022")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    for template_id in ("8015022", "8012204", "8012214"):
        doc = template if template_id == "8015022" else generate_enemy_template(template_id)
        (tmp_path / "enemies" / f"{template_id}.yaml").write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    build = {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {
        "enemies": [
            {"enemy_template": "8015022", "level": 80},
            {"enemy_template": "8012204", "level": 80},
            {"enemy_template": "8012214", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2")}
    old_remaining = {actor_id: engine.scheduler._remaining[engine.scheduler.handle_of(actor_id)]
                     for actor_id in ("h1", "h2", "8012204", "8012214")}

    engine._enemy_turn(engine.state.actors["8015022"])

    assert engine.state.actors["h1"].current_hp < old_hp["h1"]
    if target_type == "aoe":
        assert engine.state.actors["h2"].current_hp < old_hp["h2"]
    else:
        assert engine.state.actors["h2"].current_hp == old_hp["h2"]
    assert engine.scheduler._remaining[engine.scheduler.handle_of("h1")] > old_remaining["h1"]
    if target_type == "aoe":
        assert engine.scheduler._remaining[engine.scheduler.handle_of("h2")] > old_remaining["h2"]
        assert engine.scheduler._remaining[engine.scheduler.handle_of("8012204")] == 0.0
        assert engine.scheduler._remaining[engine.scheduler.handle_of("8012214")] == 0.0
    else:
        other_id = "8012214" if immediate_id == "8012204" else "8012204"
        assert engine.scheduler._remaining[engine.scheduler.handle_of(immediate_id)] == 0.0
        assert engine.scheduler._remaining[engine.scheduler.handle_of(other_id)] == old_remaining[other_id]


def test_great_ax_irontalon_applies_named_weaken(tmp_path):
    """Ecliptic Inner Beast：Great Ax 造成风伤并施加 220350102 降伤."""
    from hsr_nous.adapters.template_generator import _enemy_great_ax_irontalon_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2035012") if r["skill_id"] == "203501202")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2035012")["en"])["skills"]
                    if s["name"] == "Great Ax: Irontalon")
    action, hook = _enemy_great_ax_irontalon_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["203501202"], "cooldown": {}, "initial_cooldown": {}},
        hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hero = engine.state.actors["hero"]
    old_hp = hero.current_hp
    engine._enemy_turn(engine.state.actors["enemy"])

    modifier = hero.modifiers["ENEMY_203501202_220350102"]
    assert modifier.duration == 1
    assert engine.pipeline.effective_stats(hero)["dmg_bonus"]["all"] == pytest.approx(-0.2)
    assert hero.current_hp < old_hp


def test_radiating_venom_entangle_and_gnaw_sting(tmp_path):
    """Sky-Shrouding Swarm：Radiating Venom 施加可叠纠缠并召唤 Gnaw Sting."""
    from hsr_nous.adapters.template_generator import _enemy_radiating_venom_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_detail, get_enemy_mechanics, get_enemy_skills, get_monster_meta)

    raw = next(r for r in get_enemy_skills("8025011") if r["skill_id"] == "802501102")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8025011")["en"])["skills"]
                    if s["name"] == "Radiating Venom")
    action, hooks, specs = _enemy_radiating_venom_action(
        raw, semantic, get_enemy_detail("8025011"), get_monster_meta, level=80)
    template = generate_enemy_template("8025011")
    template.update({
        "actions": [action], "hooks": hooks, "summons": specs,
        "policy": {"sequence": ["802501102"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8025011.yaml").write_text(
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
        "enemies": [{"enemy_template": "8025011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hero = engine.state.actors["hero"]
    engine._enemy_turn(engine.state.actors["8025011"])

    modifier = hero.modifiers["ENEMY_802501102_ENTANGLE"]
    assert modifier.prevent_action and modifier.max_stack == 5 and modifier.stacks == 1
    summoned = engine.state.actors[f"{specs[0]['summon_id']}__8025011"]
    assert summoned.alive and summoned.actor.name == "Gnaw Sting"
    hp_before = hero.current_hp
    engine._tick_dots(hero)
    assert hero.current_hp < hp_before


def test_track_down_applies_imprisonment(tmp_path):
    """Aurumaton Gatekeeper：Track Down 造成虚数伤害并施加禁锢."""
    from hsr_nous.adapters.template_generator import _enemy_imprison_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2013011") if r["skill_id"] == "201301104")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2013011")["en"])["skills"]
                    if s["name"] == "Track Down")
    action, hook = _enemy_imprison_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["201301104"], "cooldown": {}, "initial_cooldown": {}},
        hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hero = engine.state.actors["hero"]
    old_hp = hero.current_hp
    engine._enemy_turn(engine.state.actors["enemy"])

    modifier = hero.modifiers["ENEMY_201301104_IMPRISON"]
    assert modifier.control_kind == "imprison" and modifier.duration == 1
    assert hero.current_hp < old_hp


def test_fallen_star_visit_applies_entanglement(tmp_path):
    """Dawn's Left Hand：Fallen Star's Visit 施加可叠纠缠并跳伤."""
    from hsr_nous.adapters.template_generator import _enemy_fallen_star_visit_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("8012142") if r["skill_id"] == "801214202")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8012142")["en"])["skills"]
                    if s["name"] == "Fallen Star's Visit")
    action, hook = _enemy_fallen_star_visit_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": ["801214202"], "cooldown": {}, "initial_cooldown": {}},
        hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    enemy.actor.stats.effect_hit = 4.0
    hero = engine.state.actors["hero"]
    engine._enemy_turn(enemy)
    modifier = hero.modifiers["ENEMY_801214202_ENTANGLE"]
    assert modifier.prevent_action and modifier.max_stack == 5 and modifier.stacks == 1
    hp_before = hero.current_hp
    engine._tick_dots(hero)

    assert hero.current_hp < hp_before


def test_when_dawn_dark_two_hits_fractional_toughness_and_entangle(tmp_path):
    """When the Dawn Is Dark：两段 160%、每段 7.5 削韧，末段后纠缠并跳伤."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.pipeline import MODE_ROLL

    template = generate_enemy_template("8012142")
    assert template["policy"]["config"]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "8012142.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8012142", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    action = compiled.actions_by_actor["8012142"][2]
    assert action.toughness_dmg == 7.5 and action.instances == 2
    assert [variant["toughness_dmg"] for variant in action.instance_variants] == [7.5, 7.5]
    engine = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, initial_energy_ratio=0.0)
    hits = []
    engine.bus.subscribe(
        "after_being_hit", lambda _event, payload, _ctx: hits.append(payload["amount"])
        if payload.get("action_id") == "801214203" else None)

    class _SuccessRoll:
        @staticmethod
        def random():
            return 0.0

    engine.pipeline.rng = _SuccessRoll()
    engine.setup()
    enemy = engine.state.actors["8012142"]
    hero = engine.state.actors["hero"]
    engine._execute_action(enemy, action)
    assert len(hits) == 2 and hits[0] == hits[1]
    remaining_before = engine.scheduler._remaining[engine.scheduler.handle_of("hero")]
    engine.bus.emit("on_action", {
        "actor": "8012142", "action_type": "skill", "action_id": "801214203",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    modifier = hero.modifiers["MCommon_Entangle"]
    assert modifier.control_kind == "entangle" and modifier.dot_ratio == 0.5
    assert modifier.duration == 1 and modifier.max_stack == 5
    assert engine.scheduler._remaining[engine.scheduler.handle_of("hero")] > remaining_before
    hp_before_dot = hero.current_hp
    engine._tick_dots(hero)
    assert hero.current_hp < hp_before_dot


@pytest.mark.parametrize(("enemy_id", "skill_id", "ratio"), [
    ("3002050", "300205001", 4.0),
    ("300205006", "300205001", 4.0),
    ("3002051", "300205101", 3.0),
    ("3002053", "300205301", 3.0),
])
def test_missing_sp_hit_direct_action_defaults_zero_and_executes(tmp_path, enemy_id, skill_id, ratio):
    """Lordly Trashcan：SPHitBase 缺省按 0，纯直伤仍能进入实际战斗."""
    from hsr_nous.adapters.template_generator import _enemy_direct_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "The Can's Trials")
    assert raw["sp_hit_base"] is None
    action = _enemy_direct_action(raw, semantic)
    assert action["scaling"] == [{"atk": ratio}]
    assert action["toughness_dmg"] == 0 and action["energy_grant"] == 0.0
    template = generate_enemy_template(enemy_id)
    assert skill_id in {item["action_id"] for item in template["actions"]}
    assert template["policy"]
    compiled = _compiled(tmp_path, [action])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    old_hp = engine.state.actors["hero"].current_hp

    engine._enemy_turn(engine.state.actors["enemy"])

    assert engine.state.actors["hero"].current_hp < old_hp


@pytest.mark.parametrize(("enemy_id", "skill_id"), [
    ("4012030", "401203001"),
    ("401203005", "401203001"),
    ("4012031", "401203101"),
])
def test_weeping_arrow_barrage_priority_repeat_and_armor_gate(tmp_path, enemy_id, skill_id):
    """Weeping Arrow：右侧优先、重复追加 200%，War Armor 归零后只打一击."""
    from hsr_nous.adapters.template_generator import _enemy_weeping_arrow_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Weeping Arrow")
    action, hook = _enemy_weeping_arrow_action(raw, semantic)
    effect = hook["effects"][0]
    assert effect["instances_expr"] == "res__war_armor > 0 ? 5 : 1"
    assert effect["toughness_dmg"] == 8 and effect["energy_grant"] == 8.0
    template = generate_enemy_template(enemy_id)
    assert skill_id in {item["action_id"] for item in template["actions"]}
    assert template["policy"]
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single",
                     "damage_type": "physical", "scaling": [{"atk": 0.0}],
                     "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2", "h3", "h4")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    seen = []

    def _on_hp(_event_type, payload, _ctx):
        if payload.get("reason") == "hit" and payload.get("source") == "enemy":
            seen.append((payload["target"], payload["amount"]))

    engine.bus.subscribe("on_hp_decrease", _on_hp)
    enemy = engine.state.actors["enemy"]
    enemy.resources["_war_armor"] = 3
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2", "h3", "h4")}
    engine._enemy_turn(enemy)

    assert [target for target, _amount in seen] == ["h4", "h3", "h2", "h1", "h1", "h1"]
    base = seen[0][1]
    assert all(amount == pytest.approx(base) for _target, amount in seen[:5])
    assert seen[5][1] == pytest.approx(base * 2)

    for actor_id in ("h1", "h2", "h3", "h4"):
        engine.state.actors[actor_id].current_hp = old_hp[actor_id]
    seen.clear()
    enemy.resources["_war_armor"] = 0
    engine._enemy_turn(enemy)
    assert seen == [("h4", base)]


def test_fickle_fortune_immunity_and_random_numbers(tmp_path):
    """Fickle Fortune：免伤，Gamble 攻击者随机获得 1~6，expected 取首项."""
    from hsr_nous.adapters.template_generator import _enemy_fickle_fortune_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.pipeline import MODE_ROLL
    from hsr_nous.sim.state import Modifier

    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("8032030")["en"])["skills"]
                    if s["name"] == "Fickle Fortune")
    for enemy_id in ("8032031", "8032032"):
        raw = next(r for r in get_enemy_skills(enemy_id) if r["trigger_key"] == "Skill01")
        assert _enemy_fickle_fortune_action(raw, semantic) is None
    raw = next(r for r in get_enemy_skills("8032030") if r["skill_id"] == "803203001")
    action, hooks = _enemy_fickle_fortune_action(raw, semantic)
    template = generate_enemy_template("8032030")
    assert "803203001" in {item["action_id"] for item in template["actions"]}
    assert template["policy"]

    def run(mode, rng):
        compiled = _compiled(
            tmp_path, [action], {"sequence": ["803203001"], "cooldown": {}, "initial_cooldown": {}},
            hooks=hooks)
        engine = CombatEngine.from_compiled(compiled, mode=mode, seed=rng)
        engine.setup()
        enemy = engine.state.actors["enemy"]
        hero = engine.state.actors["hero"]
        engine._apply_modifier(hero, Modifier(
            modifier_id="ENEMY_GAMBLE", name="Gamble", modifier_type="buff", duration=0))
        old_hp = enemy.current_hp
        engine._execute_action(hero, compiled.actions_by_actor["hero"][0], forced_target=enemy)
        assert enemy.current_hp == old_hp
        return hero.modifiers["ENEMY_FICKLE_NUMBER"].stacks

    assert run(MODE_EXPECTED, None) == 1
    assert run(MODE_ROLL, 0) == 4


def test_eternal_continuation_fixed_hp_bars(tmp_path):
    """Eternal Continuation：每击固定扣一条，击破与 DoT 也按同一条 HP 条结算."""
    from dataclasses import replace

    from hsr_nous.adapters.template_generator import _enemy_eternal_continuation_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    actions = {}
    for enemy_id in ("3012030", "3012031", "3012032"):
        raw = next(r for r in get_enemy_skills(enemy_id) if r["trigger_key"] == "Skill02")
        semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                        if s["name"] == "Eternal Continuation")
        action, hooks = _enemy_eternal_continuation_action(raw, semantic)
        actions[enemy_id] = (action, hooks)
        template = generate_enemy_template(enemy_id)
        assert raw["skill_id"] in {item["action_id"] for item in template["actions"]}
        assert template["policy"]
    action, hooks = actions["3012030"]
    team = [{
        "actor_id": "hero", "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 1000, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "energy_gain": 0}],
    }]
    compiled = _compiled(tmp_path, [action], team=team, hooks=hooks)

    def make_engine():
        engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
        engine.setup()
        enemy = engine.state.actors["enemy"]
        enemy.actor.stats.weakness = ["physical"]
        enemy.actor.stats.hp = 1000.0
        enemy.current_hp = 1000.0
        return engine, enemy, compiled.actions_by_actor["hero"][0]

    engine, enemy, basic = make_engine()
    for expected_hp in (800.0, 600.0, 400.0, 200.0, 0.0):
        engine._execute_action(engine.state.actors["hero"], basic, forced_target=enemy)
        assert enemy.current_hp == expected_hp
    assert not enemy.alive

    engine, enemy, basic = make_engine()
    enemy.actor.stats.weakness = ["physical"]
    enemy.toughness = 1.0
    engine._execute_action(engine.state.actors["hero"], replace(basic, toughness_dmg=10),
                           forced_target=enemy)
    assert enemy.current_hp == 600.0

    engine, enemy, _basic = make_engine()
    engine._apply_modifier(enemy, Modifier(
        modifier_id="test_dot", name="Burn", modifier_type="dot", dot_element="fire",
        dot_ratio=1.0, duration=2, dispellable=True))
    engine._tick_dots(enemy)
    assert enemy.current_hp == 800.0


def test_oppressive_embrace_and_disabling_field(tmp_path):
    """机械臂：拘束与 Max HP 物伤、仅打拘束目标、击破解除拘束."""
    from hsr_nous.adapters.template_generator import (
        _enemy_disabling_field_action, _enemy_oppressive_embrace_action)
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    semantics = get_enemy_mechanics(get_monster_meta("1012040")["en"], weakness=[])["skills"]
    embrace_semantic = next(s for s in semantics if s["name"] == "Oppressive Embrace")
    disabling_semantic = next(s for s in semantics if s["name"] == "Disabling Field")
    raw = next(r for r in get_enemy_skills("1012040") if r["trigger_key"] == "Skill03")
    embrace, embrace_hooks = _enemy_oppressive_embrace_action(raw, embrace_semantic)
    raw = next(r for r in get_enemy_skills("1012040") if r["trigger_key"] == "Skill04")
    disabling, disabling_hook = _enemy_disabling_field_action(raw, disabling_semantic)
    extra_param_raw = next(r for r in get_enemy_skills("1012041") if r["trigger_key"] == "Skill03")
    assert _enemy_oppressive_embrace_action(extra_param_raw, embrace_semantic) is None
    for enemy_id in ("1012041", "1012042"):
        raw = next(r for r in get_enemy_skills(enemy_id) if r["trigger_key"] == "Skill04")
        assert _enemy_disabling_field_action(raw, disabling_semantic) is not None

    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 2000, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{
            "action_id": f"{actor_id}_basic", "name": "测试普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 0.0}],
            "toughness_dmg": 10, "energy_gain": 0,
        }],
    } for actor_id in ("h1", "h2")]
    policy = {
        "sequence": [embrace["action_id"], disabling["action_id"], disabling["action_id"]],
        "cooldown": {}, "initial_cooldown": {},
    }
    compiled = _compiled(
        tmp_path, [embrace, disabling], policy=policy, team=team,
        hooks=[*embrace_hooks, disabling_hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy = engine.state.actors["enemy"]
    enemy.actor.stats.crit_rate = 0.0
    h1 = engine.state.actors["h1"]
    h2 = engine.state.actors["h2"]
    restrain_id = f"ENEMY_{embrace['action_id']}_RESTRAIN"
    # 50% Max HP 基数经过既有测试乘区：默认防御 0.5、未击破 0.9、非弱点抗性 0.8。
    expected_hit = 2000.0 * 0.5 * 0.5 * 0.9 * 0.8

    engine._enemy_turn(enemy)
    assert h1.current_hp == 2000.0 - expected_hit and h2.current_hp == 2000.0
    assert h1.modifiers[restrain_id].prevent_action
    assert h1.modifiers[restrain_id].control_kind == "restrain"

    engine._enemy_turn(enemy)
    assert h1.current_hp == 2000.0 - 2 * expected_hit and h2.current_hp == 2000.0

    enemy.actor.stats.weakness = ["physical"]
    enemy.toughness = 1.0
    engine._apply_toughness_damage(h2.actor, compiled.actions_by_actor["h2"][0], enemy)
    assert restrain_id not in h1.modifiers

    engine._enemy_turn(enemy)
    assert h1.current_hp == 2000.0 - 2 * expected_hit and h2.current_hp == 2000.0


def test_swallow_return_formation_core_and_recoil(tmp_path):
    """Swallow Return：独立隐藏弱点、揭示后击破、全灭解除剑阵并反噬."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2004020")
    assert "200402002" in {action["action_id"] for action in template["actions"]}
    assert len(template["summons"]) == 4
    template["policy"] = {
        "sequence": ["200402002"], "cooldown": {}, "initial_cooldown": {},
    }
    (tmp_path / "enemies").mkdir()
    for enemy_id in ("2004020", "2002020", "2002021"):
        document = template if enemy_id == "2004020" else generate_enemy_template(enemy_id)
        (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    team = [{
        "actor_id": "hero", "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 10, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{
            "action_id": f"hero_{element}", "name": f"测试{element}", "action_type": "basic",
            "target_type": "single", "damage_type": element, "scaling": [{"atk": 1.0}],
            "toughness_dmg": 10, "energy_gain": 0,
        } for element in ("physical", "thunder", "wind")],
    }]
    build = {"build": {
        "team": team,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "2004020", "actor_id": "yanqing", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 10000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    yanqing = engine.state.actors["yanqing"]
    yanqing.actor.stats.hp = 1000.0
    yanqing.current_hp = 1000.0
    base_spd = engine.pipeline.effective_stats(yanqing)["spd"]

    engine._enemy_turn(yanqing)

    formation_id = "ENEMY_200402002_SWORD_FORMATION"
    assert engine.pipeline.effective_stats(yanqing)["spd"] == base_spd + 50.0
    assert yanqing.modifiers[formation_id].toughness_lock
    sword_ids = [f"{spec['summon_id']}__yanqing" for spec in template["summons"]]
    swords = [engine.state.actors[actor_id] for actor_id in sword_ids]
    assert len(set(sword_ids)) == 4
    for index, sword in enumerate(swords, start=1):
        hidden_id = f"ENEMY_200402002_CORE_{index}_HIDDEN_WIND"
        revealed_id = f"ENEMY_200402002_CORE_{index}_REVEALED"
        assert sword.alive and sword.actor.summoner_id == "yanqing"
        assert hidden_id in sword.modifiers
        assert not engine.pipeline.effective_weakness(sword)
        sword.actor.stats.hp = 10000.0
        sword.current_hp = 10000.0
        sword.toughness = 1.0

        for element in ("physical", "thunder"):
            old_hp = sword.current_hp
            engine._execute_action(
                engine.state.actors["hero"], compiled.actions_by_actor["hero"][
                    {"physical": 0, "thunder": 1}[element]], forced_target=sword)
            assert sword.current_hp < old_hp
            assert sword.toughness == 1.0
            assert hidden_id in sword.modifiers and revealed_id not in sword.modifiers

        engine._execute_action(
            engine.state.actors["hero"], compiled.actions_by_actor["hero"][2], forced_target=sword)
        assert hidden_id not in sword.modifiers and revealed_id in sword.modifiers
        assert set(engine.pipeline.effective_weakness(sword)) == {"wind"}
        assert sword.toughness == 1.0

        engine._execute_action(
            engine.state.actors["hero"], compiled.actions_by_actor["hero"][1], forced_target=sword)
        assert sword.toughness == 1.0  # 揭示风弱点后，雷伤仍不能削韧。
        engine._execute_action(
            engine.state.actors["hero"], compiled.actions_by_actor["hero"][2], forced_target=sword)
        assert not sword.alive
        assert yanqing.current_hp == (900.0 if index == 4 else 1000.0)

    assert formation_id not in yanqing.modifiers
    assert yanqing.current_hp == 900.0 and yanqing.alive
    assert engine.pipeline.effective_stats(yanqing)["spd"] == base_spd


def test_custom_value_bool_unlocks_furiae_philosopher_turns(tmp_path):
    """4012020：标签谓词进入真实专属 AI，初始冷却后选择 401202002."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4012020")
    assert {action["action_id"] for action in template["actions"]} == {"401202001", "401202002"}
    assert template["policy"]["config"]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4012020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e9, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical",
                "scaling": [{"atk": 0.0}], "energy_gain": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "4012020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    seen = []

    def on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "4012020":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", on_action)
    engine.setup()
    for _ in range(20):
        record = engine.step()
        assert record is not None, "敌人在初始冷却后行动前，战斗不得提前终止"
        if seen:
            break
    assert seen == ["401202002"]


def test_reverberating_ice_recurses_into_frozen_adjacent(tmp_path):
    """Reverberating Ice：h2→h3→h4 逐次解冻递归，无冻结相邻时停止."""
    from hsr_nous.adapters.template_generator import _enemy_reverberating_ice_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import Modifier

    raw = next(r for r in get_enemy_skills("1004013") if r["skill_id"] == "100401306")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("1004013")["en"])["skills"]
                    if s["name"] == "Reverberating Ice")
    action, hooks = _enemy_reverberating_ice_action(raw, semantic)
    assert action["scaling"] == [{"atk": 2.0}] and action["scaling_blast"] == [{"atk": 1.0}]
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{
            "action_id": f"{actor_id}_basic", "name": "测试普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "physical",
            "scaling": [{"atk": 0.0}], "energy_gain": 0,
        }],
    } for actor_id in ("h1", "h2", "h3", "h4")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [action["action_id"]], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    for actor_id in ("h2", "h3", "h4"):
        engine._apply_modifier(engine.state.actors[actor_id], Modifier(
            modifier_id=f"TEST_FREEZE_{actor_id}", name="Frozen", modifier_type="control",
            control_kind="freeze", prevent_action=True, duration=1, dispellable=True))
    actions_seen, hits_seen = [], []

    def on_action(_event_type, payload, _ctx):
        if payload.get("action_id") == action["action_id"]:
            actions_seen.append((payload.get("target"), bool(payload.get("insert"))))

    def on_hit(_event_type, payload, _ctx):
        if payload.get("action_id") == action["action_id"]:
            hits_seen.append(payload["target"])

    engine.bus.subscribe("on_action", on_action)
    engine.bus.subscribe("after_being_hit", on_hit)
    engine._execute_action(
        engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0],
        forced_target=engine.state.actors["h2"])
    engine.bus.emit("on_action", {
        "actor": "enemy", "action_type": "skill", "action_id": action["action_id"],
        "target_type": "blast", "target": "h2", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)

    # on_action 在嵌套 hook 中后序返回；逆序才是 h2→h3→h4 的实际施放顺序。
    assert actions_seen[::-1] == [("h2", False), ("h3", True), ("h4", True)]
    assert {actor_id: hits_seen.count(actor_id) for actor_id in ("h1", "h2", "h3", "h4")} == {
        "h1": 1, "h2": 2, "h3": 3, "h4": 2,
    }
    assert all(not state.modifiers for state in engine.state.actors.values())


@pytest.mark.parametrize(
    ("enemy_id", "skill_id", "semantic_name", "shielded", "hit_count", "recoil_count", "expect_freeze"),
    [
        ("3003020", "300302001", "Limited Free Drinks", True, 1, 1, False),
        ("3003022", "300302201", "Limitless Free Drinks", True, 1, 1, False),
        ("3003022", "300302201", "Limitless Free Drinks", False, 1, 0, True),
        ("3003022", "300302202", "Frenzied Free Drinks", True, 4, 4, False),
        ("3003022", "300302202", "Frenzied Free Drinks", False, 4, 0, True),
    ],
)
def test_free_drinks_shield_snapshot_recoil_and_freeze(
        tmp_path, enemy_id, skill_id, semantic_name, shielded, hit_count, recoil_count, expect_freeze):
    """Free Drinks：逐段盾前快照决定反噬/冻结，破盾也不改判."""
    from hsr_nous.adapters.template_generator import _enemy_free_drinks_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
    from hsr_nous.sim.state import ShieldInstance

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == semantic_name)
    action, hooks = _enemy_free_drinks_action(raw, semantic)
    team = [{
        "actor_id": "hero", "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{
            "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "physical",
            "scaling": [{"atk": 0.0}], "energy_gain": 0,
        }],
    }]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [skill_id], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy, hero = engine.state.actors["enemy"], engine.state.actors["hero"]
    if shielded:
        hero.shields.append(ShieldInstance(
            shield_id="TEST_SHIELD", name="测试盾", remaining=1.0 if hit_count == 1 else 1e9,
            source_id="hero"))
    before_ids, original_hits, recoil_hits = [], [], []

    def before_hit(_event_type, payload, _ctx):
        if payload.get("target") == "hero" and payload.get("action_id") == skill_id:
            before_ids.append(payload["action_id"])

    def after_hit(_event_type, payload, _ctx):
        if payload.get("target") == "hero" and payload.get("action_id") == skill_id:
            original_hits.append(payload["action_id"])
        if payload.get("target") == "enemy" and payload.get("action_id") == "hook_dmg":
            recoil_hits.append(payload["action_id"])

    engine.bus.subscribe_waterfall("before_take_damage", before_hit)
    engine.bus.subscribe("after_being_hit", after_hit)
    old_enemy_hp, old_hero_hp = enemy.current_hp, hero.current_hp
    engine._execute_action(enemy, compiled.actions_by_actor["enemy"][0], forced_target=hero)

    assert before_ids == [skill_id] * hit_count
    assert original_hits == [skill_id] * hit_count
    assert recoil_hits == ["hook_dmg"] * recoil_count
    shielded_id = f"ENEMY_{skill_id}_SHIELDED_AT_CAST"
    unshielded_id = f"ENEMY_{skill_id}_UNSHIELDED_AT_CAST"
    assert shielded_id not in enemy.modifiers and unshielded_id not in enemy.modifiers
    if recoil_count:
        assert enemy.current_hp < old_enemy_hp
        assert f"ENEMY_{skill_id}_RECOIL_DEF_DOWN" in enemy.modifiers
    else:
        assert enemy.current_hp == old_enemy_hp
        assert f"ENEMY_{skill_id}_RECOIL_DEF_DOWN" not in enemy.modifiers
    freeze_id = f"ENEMY_{skill_id}_FREEZE"
    if expect_freeze:
        assert hero.modifiers[freeze_id].control_kind == "freeze"
        engine.bus.emit("on_turn_start", {"actor": "hero"}, engine.state)
        assert hero.current_hp < old_hero_hp
    else:
        assert freeze_id not in hero.modifiers


def test_soulglad_party_summons_two_bubble_hounds(tmp_path):
    """SoulGlad Party：按原始 SummonIDList 召唤两只 Bubble Hound."""
    from hsr_nous.adapters.template_generator import _enemy_soulglad_party_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_detail, get_enemy_mechanics, get_enemy_skills, get_monster_meta)

    raw = next(r for r in get_enemy_skills("3003020") if r["skill_id"] == "300302003")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("3003020")["en"])["skills"]
                    if s["name"] == "SoulGlad Party")
    action, hooks, specs = _enemy_soulglad_party_action(
        raw, semantic, get_enemy_detail("3003020"), get_monster_meta, level=80)
    template = generate_enemy_template("3003020")
    template.update({
        "actions": [action], "hooks": hooks, "summons": specs,
        "policy": {"sequence": ["300302003"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3003020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical",
                "scaling": [{"atk": 0.0}], "energy_gain": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "3003020", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path), "data/sim_templates"])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._enemy_turn(engine.state.actors["3003020"])

    assert len(specs) == 2
    for spec in specs:
        actor = engine.state.actors[f"{spec['summon_id']}__3003020"]
        assert actor.alive and actor.actor.summoner_id == "3003020"
        assert actor.actor.name == "Dreamjolt Troupe's Bubble Hound"


def test_rapid_gambit_immediately_acts_all_friendlies(tmp_path):
    """Rapid Gambit：SetActionDelay(AllTeammate, 0) 拉齐两名怪物，不误拉角色."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2024020")
    assert "202402002" in {action["action_id"] for action in template["actions"]}
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2024020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical",
                "scaling": [{"atk": 0.0}], "energy_gain": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [
            {"enemy_template": "2024020", "actor_id": "cirrus_a", "level": 80},
            {"enemy_template": "2024020", "actor_id": "cirrus_b", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._enemy_policy_state["cirrus_a"]["cooldown_left"].clear()
    engine._enemy_turn(engine.state.actors["cirrus_a"])

    assert engine.scheduler._remaining[engine.scheduler._handles["cirrus_b"]] == 0.0
    assert engine.scheduler._remaining[engine.scheduler._handles["cirrus_a"]] == 0.0
    assert engine.scheduler._remaining[engine.scheduler._handles["hero"]] > 0.0


def test_rapid_gambit_urge_stacks_damage_before_immediate_action(tmp_path):
    """Rapid Gambit: Urge 先叠 6% 增伤再拉齐全队，重复施放按层数累计."""
    from hsr_nous.adapters.template_generator import _enemy_rapid_gambit_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2024021") if r["skill_id"] == "202402102")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2024021")["en"])["skills"]
                    if s["name"] == "Rapid Gambit: Urge")
    action, hook = _enemy_rapid_gambit_action(raw, semantic)
    template = generate_enemy_template("2024021")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {"sequence": ["202402102"], "cooldown": {}, "initial_cooldown": {}},
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2024021.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 0.0}],
                "energy_gain": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}]},
    }}
    stage = {"stage": {
        "enemies": [
            {"enemy_template": "2024021", "actor_id": "urge_a", "level": 80},
            {"enemy_template": "2024021", "actor_id": "urge_b", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    base = {
        actor_id: engine.pipeline.effective_stats(engine.state.actors[actor_id])["dmg_bonus"].get("all", 0.0)
        for actor_id in ("urge_a", "urge_b")}

    engine._enemy_turn(engine.state.actors["urge_a"])

    for actor_id in ("urge_a", "urge_b"):
        target = engine.state.actors[actor_id]
        assert target.modifiers["Monster_Fuyan_00_RL_DamageUp"].stacks == 1
        assert engine.pipeline.effective_stats(target)["dmg_bonus"]["all"] == base[actor_id] + 0.06
        assert engine.scheduler._remaining[engine.scheduler._handles[actor_id]] == 0.0

    engine._enemy_turn(engine.state.actors["urge_a"])

    for actor_id in ("urge_a", "urge_b"):
        target = engine.state.actors[actor_id]
        assert target.modifiers["Monster_Fuyan_00_RL_DamageUp"].stacks == 2
        assert engine.pipeline.effective_stats(target)["dmg_bonus"]["all"] == base[actor_id] + 0.12


def test_rapid_gambit_slay_phase_gate_and_dual_buffs(tmp_path):
    """Rapid Gambit: Slay 仅第三阶段叠增伤与速度，并立即行动."""
    from hsr_nous.adapters.template_generator import _enemy_rapid_gambit_action, generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("2024021") if r["skill_id"] == "202402105")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("2024021")["en"])["skills"]
                    if s["name"] == "Rapid Gambit: Slay")
    action, hook = _enemy_rapid_gambit_action(raw, semantic)
    template = generate_enemy_template("2024021")
    template.update({
        "actions": [action], "hooks": [hook],
        "policy": {
            "sequence": ["202402105"], "cooldown": {}, "initial_cooldown": {},
            "skill_phases": {"202402105": [3]},
        },
    })
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "2024021.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 0.0}],
                "energy_gain": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}]},
    }}
    stage = {"stage": {
        "enemies": [
            {"enemy_template": "2024021", "actor_id": "slay_a", "level": 80},
            {"enemy_template": "2024021", "actor_id": "slay_b", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._enemy_policy_state["slay_a"]["current_phase"] = 2
    engine._enemy_turn(engine.state.actors["slay_a"])
    assert "Monster_Fuyan_00_RL_DamageUp" not in engine.state.actors["slay_b"].modifiers

    engine._enemy_policy_state["slay_a"]["current_phase"] = 3
    base = {
        actor_id: engine.pipeline.effective_stats(engine.state.actors[actor_id])["dmg_bonus"].get("all", 0.0)
        for actor_id in ("slay_a", "slay_b")}
    base_spd = {
        actor_id: engine.pipeline.effective_stats(engine.state.actors[actor_id]).get("spd_pct", 0.0)
        for actor_id in ("slay_a", "slay_b")}
    engine._enemy_turn(engine.state.actors["slay_a"])

    for actor_id in ("slay_a", "slay_b"):
        target = engine.state.actors[actor_id]
        assert target.modifiers["Monster_Fuyan_00_RL_DamageUp"].stacks == 1
        assert target.modifiers["Monster_Fuyan_00_RL_SpeedUp"].stacks == 1
        stats = engine.pipeline.effective_stats(target)
        assert stats["dmg_bonus"]["all"] == base[actor_id] + 0.06
        assert stats["spd_pct"] == base_spd[actor_id] + 0.06
        assert engine.scheduler._remaining[engine.scheduler._handles[actor_id]] == 0.0


def test_enrage_order_forces_hero_to_attack_caster(tmp_path):
    """Enrage Order：两回合 Taunt 让玩家主目标强制指向施放者."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("101301018")
    assert "101301002" in {action["action_id"] for action in template["actions"]}
    template["policy"]["sequence"] = ["101301002"]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "101301018.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical",
                "scaling": [{"atk": 0.0}], "energy_gain": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [
            {"enemy_template": "101301018", "actor_id": "other", "level": 80},
            {"enemy_template": "101301018", "actor_id": "grizzly", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enrage = next(action for action in compiled.actions_by_actor["grizzly"]
                  if action.action_id == "101301002")
    engine._execute_action(engine.state.actors["grizzly"], enrage)
    engine.bus.emit("on_action", {
        "actor": "grizzly", "action_type": "skill", "action_id": "101301002",
        "target_type": "self", "target": "grizzly", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)

    taunt = engine.state.actors["hero"].modifiers["ENEMY_101301002_TAUNT"]
    assert taunt.forced_taunt and taunt.source_id == "grizzly" and taunt.duration == 2
    engine._execute_action(
        engine.state.actors["hero"], compiled.actions_by_actor["hero"][0])
    assert engine._last_target_id == "grizzly"


def test_frozen_storm_five_hits_and_deep_freeze_layers(tmp_path):
    """Frozen Storm：15%×4+40% 五段冰伤，Deep Freeze 逐层冰抗/速度变化."""
    from hsr_nous.adapters.template_generator import _enemy_frozen_storm_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("1023020") if r["skill_id"] == "102302006")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("1023020")["en"])["skills"]
                    if s["name"] == "Frozen Storm")
    action, hooks = _enemy_frozen_storm_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": [action["action_id"]], "cooldown": {}, "initial_cooldown": {}},
        hooks=hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    amounts = []

    def on_hit(_event_type, payload, _ctx):
        if str(payload.get("action_id", "")).startswith("hook_Frozen Storm Hit"):
            amounts.append(payload["amount"])

    engine.bus.subscribe("after_being_hit", on_hit)
    for _ in range(4):
        engine._execute_action(
            engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0])
        engine.bus.emit("on_action", {
            "actor": "enemy", "action_type": "skill", "action_id": action["action_id"],
            "target_type": "self", "target": "enemy", "sp_consumed": 0, "actor_type": "monster",
        }, engine.state)

    assert len(amounts) == 20
    first = amounts[0]
    assert amounts[:5] == pytest.approx([first, first, first, first, first * 0.4 / 0.15])
    hero = engine.state.actors["hero"]
    modifier = hero.modifiers["Monster_W1_Mecha03_01_Frozen"]
    assert modifier.stacks == 3
    stats = engine.pipeline.effective_stats(hero)
    assert stats["res_ice"] == pytest.approx(0.36)
    assert stats["spd_pct"] == pytest.approx(0.6)


@pytest.mark.parametrize(("enemy_id", "skill_id", "dot_ratio"), [
    ("3003050", "300305002", 1.2),
    ("3003051", "300305102", 0.9),
])
def test_feast_carousal_expected_applies_poison_dot(tmp_path, enemy_id, skill_id, dot_ratio):
    """Feast That Is Set For You：expected 取首项 Poison，倍率/持续/概率/元素一致."""
    from hsr_nous.adapters.template_generator import _enemy_feast_carousal_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Feast That Is Set For You")
    action, hook = _enemy_feast_carousal_action(raw, semantic)
    compiled = _compiled(
        tmp_path, [action], {"sequence": [action["action_id"]], "cooldown": {}, "initial_cooldown": {}},
        hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._execute_action(
        engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0])
    engine.bus.emit("on_action", {
        "actor": "enemy", "action_type": "skill", "action_id": action["action_id"],
        "target_type": "self", "target": "enemy", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)

    hero = engine.state.actors["hero"]
    modifier = hero.modifiers["MMonster_W3_Figure_01_Poison"]
    assert modifier.dot_element == "wind" and modifier.dot_ratio == dot_ratio
    assert modifier.dot_base_chance == 1.0 and modifier.duration == 2 and modifier.max_stack == 5
    assert "MMonster_W3_Figure_01_Electric" not in hero.modifiers
    old_hp = hero.current_hp
    engine._tick_dots(hero)
    assert hero.current_hp < old_hp


def test_a_cup_carousal_and_wash_away_sins(tmp_path):
    """A Cup 先施加随机 DoT，Wash Away All Sins 再按 125% 引爆并清除."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("3003050")
    assert [action["action_id"] for action in template["actions"]] == [
        "300305001", "300305002", "300305004", "300305005"]
    assert template["policy"]["config"]["AIName"] == "Monster_XP_Elite02_00"
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3003050.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "3003050", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "3003050" else None)
    engine.setup()
    enemy = engine.state.actors["3003050"]
    hero = engine.state.actors["hero"]
    engine._apply_modifier_spec(hero, {
        "modifier_id": "MMonster_W3_Figure_01_Electric", "name": "Electric",
        "modifier_type": "dot", "dot_element": "thunder", "dot_ratio": 0.5,
        "dot_base_chance": 1.0, "duration": 2, "dispellable": True,
    }, enemy)
    runtime = engine._enemy_policy_state["3003050"]
    runtime["cooldown_left"] = {}
    runtime.setdefault("dynamic_values", {})["AIFlag"] = 2

    engine._enemy_turn(enemy)
    assert seen == ["300305004"]
    assert "MMonster_W3_Figure_01_Poison" in hero.modifiers
    assert runtime["dynamic_values"]["AIFlag"] == 3
    hp_before_wash = hero.current_hp
    runtime["cooldown_left"] = {}
    runtime["dynamic_values"]["AIFlag"] = 3
    engine._enemy_turn(enemy)

    assert seen[-1] == "300305005"
    assert hero.current_hp < hp_before_wash
    assert "MMonster_W3_Figure_01_Poison" not in hero.modifiers
    assert "MMonster_W3_Figure_01_Electric" not in hero.modifiers


def test_precious_blood_carousal_only_hits_primary(tmp_path):
    """Precious Blood Shed For You：同一随机 DoT 只作用于主目标，不误伤邻位."""
    from hsr_nous.adapters.template_generator import _enemy_feast_carousal_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills("3003050") if r["skill_id"] == "300305001")
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta("3003050")["en"])["skills"]
                    if s["name"] == "Precious Blood Shed For You")
    action, hook = _enemy_feast_carousal_action(raw, semantic)
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{
            "action_id": f"{actor_id}_basic", "name": "测试普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "physical",
            "scaling": [{"atk": 0.0}], "energy_gain": 0,
        }],
    } for actor_id in ("h1", "h2")]
    compiled = _compiled(
        tmp_path, [action], {"sequence": [action["action_id"]], "cooldown": {}, "initial_cooldown": {}},
        team=team, hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    engine._execute_action(
        engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0],
        forced_target=engine.state.actors["h1"])
    engine.bus.emit("on_action", {
        "actor": "enemy", "action_type": "skill", "action_id": action["action_id"],
        "target_type": "single", "target": "h1", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)

    assert action["target_type"] == "single"
    modifier = engine.state.actors["h1"].modifiers["MMonster_W3_Figure_01_Poison"]
    assert modifier.dot_ratio == 1.2 and modifier.dot_base_chance == 1.0 and modifier.max_stack == 3
    assert hook["effects"][0]["options"][1]["modifier"]["max_stack"] == 3
    assert "MMonster_W3_Figure_01_Poison" not in engine.state.actors["h2"].modifiers


@pytest.mark.parametrize(("enemy_id", "skill_id", "count", "ratio"), [
    ("4014010", "401401007", 5, 1.2),
    ("4014015", "401401507", 6, 1.0),
])
def test_sky_piercing_lance_hit_count_and_third_param(tmp_path, enemy_id, skill_id, count, ratio):
    """Sky-Piercing Lance：第三参数不改变原始段数与倍率."""
    from hsr_nous.adapters.template_generator import _enemy_sky_piercing_lance_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Sky-Piercing Lance")
    action = _enemy_sky_piercing_lance_action(raw, semantic)
    assert action["instances"] == count and action["scaling"] == [{"atk": ratio}]
    compiled = _compiled(tmp_path, [action])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hits = []

    def on_hit(_event_type, payload, _ctx):
        if payload.get("action_id") == skill_id:
            hits.append(payload["amount"])

    engine.bus.subscribe("after_being_hit", on_hit)
    engine._execute_action(
        engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0])
    assert len(hits) == count


@pytest.mark.parametrize("enemy_id", ["8003030", "800303015", "800303020"])
def test_thunderstorm_condemnation_applies_shock_per_hit(tmp_path, enemy_id):
    """Thunderstorm Condemnation：8 段 100% 雷伤，每段按 50% 判定 2 回合 Shock."""
    from hsr_nous.adapters.template_generator import _enemy_thunderstorm_condemnation_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    skill_id = "800303006"
    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == "Thunderstorm Condemnation")
    action, hook = _enemy_thunderstorm_condemnation_action(raw, semantic)
    assert action["instances"] == 8 and action["scaling"] == [{"atk": 1.0}]
    assert hook["effects"][0]["apply_chance"] == 0.5
    compiled = _compiled(tmp_path, [action], hooks=[hook])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    hits = []
    engine.bus.subscribe(
        "after_being_hit",
        lambda _et, payload, _ctx: hits.append(payload["action_id"])
        if payload.get("action_id") == skill_id else None)
    engine._execute_action(engine.state.actors["enemy"], compiled.actions_by_actor["enemy"][0])

    assert hits == [skill_id] * 8
    modifier = engine.state.actors["hero"].modifiers[f"ENEMY_{skill_id}_SHOCK"]
    assert modifier.dot_ratio == 0.5 and modifier.dot_base_chance == 0.5
    assert modifier.duration == 2 and modifier.max_stack == 1


def test_void_cannon_detonated_consumption_and_thermal_barrier(tmp_path):
    """Void Cannon 三段结算；Detonated 受击消耗三次，Thermal Barrier 解除过载."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("8012030")
    assert [action["action_id"] for action in template["actions"]] == ["801203001", "801203002"]
    assert template["policy"]["sequence"] == ["801203001", "801203002"]
    template["policy"]["cooldown"] = template["policy"]["initial_cooldown"] = {}
    dummy = {
        "enemy_id": "dummy", "name": "假人", "level": 80,
        "base_stats": {"hp": 1e9, "atk": 1000, "def": 0, "spd": 100, "max_toughness": 30},
        "weakness": [],
        "actions": [{
            "action_id": "dummy_basic", "name": "测试攻击", "action_type": "basic",
            "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 1.0}],
            "toughness_dmg": 0, "energy_gain": 0,
        }],
    }
    (tmp_path / "enemies").mkdir()
    for enemy_id, document in (("8012030", template), ("dummy", dummy)):
        (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 0.0}],
                "energy_gain": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "8012030", "level": 80}, {"enemy_template": "dummy", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    enemy, hero, dummy_actor = (engine.state.actors[actor_id] for actor_id in ("8012030", "hero", "dummy"))
    hits = []
    engine.bus.subscribe(
        "after_being_hit",
        lambda _et, payload, _ctx: hits.append(payload["action_id"])
        if payload.get("action_id") in {"801203001", "hook_detonated"} else None)

    engine._enemy_turn(enemy)

    assert hits == ["801203001"] * 3
    detonated_id = "MMonster_AML_Minion04_00_Mark"
    overloaded_id = "MMonster_AML_Minion04_00_Overheat"
    assert hero.modifiers[detonated_id].stacks == 3
    assert overloaded_id in enemy.modifiers
    assert not engine._available_if_ok(enemy, compiled.actions_by_actor["8012030"][0])
    assert engine._available_if_ok(enemy, compiled.actions_by_actor["8012030"][1])

    engine._enemy_turn(enemy)

    assert overloaded_id not in enemy.modifiers
    assert engine._available_if_ok(enemy, compiled.actions_by_actor["8012030"][0])
    detonated_damage = []
    for remaining in (2, 1):
        before = engine.state.damage_by_actor["8012030"]
        engine._execute_action(dummy_actor, compiled.actions_by_actor["dummy"][0], forced_target=hero)
        detonated_damage.append(engine.state.damage_by_actor["8012030"] - before)
        assert hero.modifiers[detonated_id].stacks == remaining
    before = engine.state.damage_by_actor["8012030"]
    engine._execute_action(dummy_actor, compiled.actions_by_actor["dummy"][0], forced_target=hero)
    detonated_damage.append(engine.state.damage_by_actor["8012030"] - before)
    assert detonated_id not in hero.modifiers
    assert len(detonated_damage) == 3 and all(value > 0 for value in detonated_damage)


def test_mirage_rush_team_marker_unlocks_rumination_extra_hit(tmp_path):
    """Mirage Rush 的团队标记让 Rumination 追加伤害，击破后全链解除."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("4052020")
    assert {action["action_id"] for action in template["actions"]} == {"405202001", "405202002"}
    assert template["policy"]["config"]
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "4052020.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical",
                "scaling": [{"atk": 0.0}], "toughness_dmg": 10, "energy_gain": 0,
            }],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [
            {"enemy_template": "4052020", "actor_id": "caster", "level": 80},
            {"enemy_template": "4052020", "actor_id": "enemy", "level": 80},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    rush = next(a for a in compiled.actions_by_actor["caster"] if a.action_id == "405202002")
    engine._execute_action(
        engine.state.actors["caster"], rush, forced_target=engine.state.actors["hero"])
    engine.bus.emit("on_action", {
        "actor": "caster", "action_type": "skill", "action_id": "405202002",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert engine.pipeline.effective_stats(engine.state.actors["enemy"])["mirage_rush_active"] == 1.0
    assert "MMonster_SW_Minion01_03_CommandMarkTarget" in engine.state.actors["hero"].modifiers

    hits = []

    def on_hit(_event_type, payload, _ctx):
        if payload.get("target") == "hero" and payload.get("action_id") in {"405202001", "hook_dmg"}:
            hits.append(payload["amount"])

    engine.bus.subscribe("after_being_hit", on_hit)
    rumination = next(a for a in compiled.actions_by_actor["enemy"] if a.action_id == "405202001")
    engine._execute_action(
        engine.state.actors["enemy"], rumination, forced_target=engine.state.actors["hero"])
    engine.bus.emit("on_action", {
        "actor": "enemy", "action_type": "skill", "action_id": "405202001",
        "target_type": "single", "target": "hero", "sp_consumed": 0, "actor_type": "monster",
    }, engine.state)
    assert len(hits) == 2 and hits[0] == pytest.approx(hits[1])

    caster = engine.state.actors["caster"]
    caster.actor.stats.weakness = ["physical"]
    caster.toughness = 1.0
    engine._apply_toughness_damage(
        engine.state.actors["hero"].actor, compiled.actions_by_actor["hero"][0], caster)
    assert "MMonster_SW_Minion01_03_CommandMark" not in caster.modifiers
    assert engine.pipeline.effective_stats(engine.state.actors["enemy"]).get("mirage_rush_active", 0.0) == 0.0
    assert "MMonster_SW_Minion01_03_CommandMarkTarget" not in engine.state.actors["hero"].modifiers


@pytest.mark.parametrize(("enemy_id", "skill_id", "semantic_name", "target_type", "damage_type", "ratio"), [
    ("1004013", "100401301", "Chill of Bone-Piercing Coagulation", "single", "ice", 2.0),
    ("1004032", "100403201", "Windrider Bullet", "single", "wind", 3.0),
    ("1005013", "100501309", "Last Choir of Genesis", "aoe", "imaginary", 5.0),
    ("2024013", "202401305", "Wavering Bleat", "single", "thunder", 3.5),
    ("2024013", "202401306", "Caress of Wind", "aoe", "wind", 2.8),
    ("1004013", "100401303", "Punishment of Endless Winter", "aoe", "ice", 2.5),
    ("1004024", "100402401", "Fist of Conviction", "single", "ice", 3.0),
    ("1004024", "100402402", "Smite of Frost", "single", "ice", 3.5),
    ("1004025", "100402501", "Fist of Conviction", "single", "ice", 2.0),
    ("1004025", "100402502", "Smite of Frost", "single", "ice", 3.0),
    ("1004025", "100402504", "Frigid Waterfall", "aoe", "ice", 2.5),
    ("2004023", "200402306", "Cascading Laceration", "aoe", "ice", 4.5),
    ("2004013", "200401303", "Silent and Sharp Mockery", "aoe", "thunder", 3.5),
    ("4032027", "403202701", "Let Blank Wishes Become Whole", "aoe", "physical", 1.5),
    ("5012110", "501211001", "Capture", "single", "imaginary", 2.8),
    ("5013031", "501303101", "The Stroke", "single", "physical", 2.0),
    ("5013012", "501301204", "Time to Rock!", "aoe", "imaginary", 5.0),
    ("8015030", "801503009", "May This Journey Lead You to Destruction", "aoe", "quantum", 5.6),
])
def test_missing_ratio_direct_action_uses_whitelisted_param(
        tmp_path, enemy_id, skill_id, semantic_name, target_type, damage_type, ratio):
    """已核纯直伤 ID 可用唯一参数槽补足原文省略的倍率."""
    from hsr_nous.adapters.template_generator import _enemy_missing_ratio_direct_action
    from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta

    raw = next(r for r in get_enemy_skills(enemy_id) if r["skill_id"] == skill_id)
    semantic = next(s for s in get_enemy_mechanics(get_monster_meta(enemy_id)["en"])["skills"]
                    if s["name"] == semantic_name)
    action = _enemy_missing_ratio_direct_action(raw, semantic)
    assert action["target_type"] == target_type and action["damage_type"] == damage_type
    assert action["scaling"] == [{"atk": ratio}]
    team = [{
        "actor_id": actor_id, "name": "测试员", "inline": True,
        "base_stats": {"hp": 1e12, "atk": 0, "def": 0, "spd": 50, "max_energy": 100},
        "actions": [{"action_id": f"{actor_id}_basic", "name": "测试普攻",
                     "action_type": "basic", "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 0.0}], "toughness_dmg": 0, "energy_gain": 0}],
    } for actor_id in ("h1", "h2")]
    compiled = _compiled(tmp_path, [action], team=team)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    engine.setup()
    old_hp = {actor_id: engine.state.actors[actor_id].current_hp for actor_id in ("h1", "h2")}

    engine._enemy_turn(engine.state.actors["enemy"])

    assert engine.state.actors["h1"].current_hp < old_hp["h1"]
    if target_type == "aoe":
        assert engine.state.actors["h2"].current_hp < old_hp["h2"]
    else:
        assert engine.state.actors["h2"].current_hp == old_hp["h2"]


def test_shape_shifter_bug_summon_rebirth_and_vigor(tmp_path):
    """炼形者（错误）：专属 AI 召唤四单位、锁定、重生与采气回血同链验证."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("2023011")
    assert [a["action_id"] for a in template["actions"]] == [
        "202301101", "202301102", "202301103", "202301105"]
    assert template["policy"]["config"]["AIName"] == "Monster_W2_Abomi04_00"
    assert not any("ConfigAI 未收编节点" in note for note in template["notes"])
    (tmp_path / "enemies").mkdir()
    for enemy_id in ("2023011", "2022010", "2022020"):
        doc = template if enemy_id == "2023011" else generate_enemy_template(enemy_id)
        (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1e9, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "2023011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["2023011"]
    hero = engine.state.actors["hero"]
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "2023011" else None)
    runtime = engine._enemy_policy_state["2023011"]
    runtime["cooldown_left"] = {}
    runtime.setdefault("dynamic_values", {})["W2_Abomi04_00_AICounter"] = 2

    engine._enemy_turn(enemy)

    assert seen == ["202301105"]
    enemy_max_hp = engine.pipeline.effective_stats(enemy)["hp"]
    assert enemy.current_hp == pytest.approx(enemy_max_hp * 0.85)
    assert hero.modifiers["ENEMY_202301105_LOCK_ON"].lock_on is True
    mara = [s for s in engine.state.actors.values() if s.actor.name == "Mara-Struck Soldier"]
    alchemists = [s for s in engine.state.actors.values()
                  if s.actor.name == "Disciples of Sanctus Medicus: Internal Alchemist"]
    assert len(mara) == len(alchemists) == 2
    assert all(s.alive and s.actor.summoner_id == "2023011" for s in mara + alchemists)
    assert all(s.modifiers["ENEMY_REBIRTH"].revive_percent == 0.5 for s in mara)

    revived = []
    engine.bus.subscribe(
        "on_revive", lambda _event, payload, _ctx: revived.append(payload["target"]))
    shock = next(a for a in compiled.actions_by_actor["2023011"] if a.action_id == "202301101")
    enemy.current_hp = enemy_max_hp * 0.5
    engine._execute_action(enemy, shock, forced_target=hero)
    assert enemy.current_hp == pytest.approx(enemy_max_hp * 0.53)

    mara_max_hp = engine.pipeline.effective_stats(mara[0])["hp"]
    mara[0].current_hp = 1.0
    hero_basic = compiled.actions_by_actor["hero"][0]
    engine._execute_action(hero, hero_basic, forced_target=mara[0])
    assert mara[0].alive and mara[0].current_hp == pytest.approx(mara_max_hp * 0.5)
    assert "ENEMY_REBIRTH" not in mara[0].modifiers
    assert revived == [mara[0].actor.actor_id]
    mara[0].current_hp = 1.0
    engine._execute_action(hero, hero_basic, forced_target=mara[0])
    assert not mara[0].alive

    engine._remove_modifier(mara[1], "ENEMY_REBIRTH", "test")
    enemy.current_hp = enemy_max_hp * 0.5
    engine._execute_action(enemy, shock, forced_target=hero)
    assert enemy.current_hp == pytest.approx(enemy_max_hp * 0.5)


@pytest.mark.parametrize("enemy_id", ["1004031", "100403101", "100403103"])
def test_bronya_complete_config_ai_full_cycle(tmp_path, enemy_id):
    """布洛妮娅（完整）从实测初值起执行普攻→再部署→压制→再部署."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.state import Modifier

    template = generate_enemy_template(enemy_id)
    assert [a["action_id"] for a in template["actions"]] == [
        "100403101", "100403102", "100403104"]
    assert not any("无可执行" in note or "未收编节点" in note for note in template["notes"])
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
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
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": enemy_id, "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors[enemy_id]
    dummy_state = engine.state.actors["dummy"]
    runtime = engine._enemy_policy_state[enemy_id]
    runtime["cooldown_left"] = {}
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == enemy_id else None)

    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown(enemy_id)
    engine._apply_modifier(dummy_state, Modifier(
        modifier_id="TEST_DEBUFF", name="测试减益", modifier_type="debuff", duration=2))
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown(enemy_id)
    assert "TEST_DEBUFF" not in dummy_state.modifiers
    redeployment = dummy_state.modifiers["ENEMY_100403102_REDEPLOYMENT"]
    assert redeployment.stat_effects["all_dmg"] == 0.2
    assert engine.scheduler._remaining[engine.scheduler.handle_of("dummy")] == 0.0
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown(enemy_id)
    engine._enemy_turn(enemy)

    assert seen == ["100403101", "100403102", "100403104", "100403102"]
    assert runtime["dynamic_values"]["Bronya_AICounter_Act1"] == 1


def test_fortune_bananadvisor_channel_cycle(tmp_path):
    """财富蕉师：课堂扣点→受击换课间→奖励点数→换课→课堂扣点."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("3002021")
    assert [a["action_id"] for a in template["actions"]] == [
        "300202101", "300202102", "300202103"]
    assert template["policy"]["config"]["AIName"] == "Monster_W1_Mecha01_00"
    assert not any("未收编" in note or "无可执行" in note for note in template["notes"])
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002021.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "3002021", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(
        compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    engine.setup()
    enemy = engine.state.actors["3002021"]
    runtime = engine._enemy_policy_state["3002021"]
    runtime["cooldown_left"] = {}
    assert "CLASSROOM_CHANNEL" in enemy.modifiers
    assert "OFF_CLASS_CHANNEL" not in enemy.modifiers
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "3002021" else None)

    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002021")
    assert engine.state.skill_points == 2
    engine._execute_action(
        engine.state.actors["hero"], compiled.actions_by_actor["hero"][0], forced_target=enemy)
    assert "OFF_CLASS_CHANNEL" in enemy.modifiers
    assert "CLASSROOM_CHANNEL" not in enemy.modifiers
    assert runtime["dynamic_values"]["FlopSide"] == 1
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002021")
    assert engine.state.skill_points == 4
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002021")
    assert "CLASSROOM_CHANNEL" in enemy.modifiers
    assert "OFF_CLASS_CHANNEL" not in enemy.modifiers
    assert runtime["dynamic_values"]["FlopSide"] == -1
    engine._enemy_turn(enemy)

    assert engine.state.skill_points == 3
    assert seen == ["300202102", "300202101", "300202103", "300202102"]


def test_dreamweaver_bananadvisor_channel_cycle(tmp_path):
    """筑梦蕉师稳态循环：上课→课间冲锋→换课→上课→课间冲锋."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("3002041")
    assert [a["action_id"] for a in template["actions"]] == [
        "300204101", "300204102", "300204103"]
    assert template["policy"]["config"]["AIName"] == "Monster_W3_Clock_00"
    assert not any("未收编" in note or "无可执行" in note for note in template["notes"])
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002041.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "3002041", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3002041"]
    runtime = engine._enemy_policy_state["3002041"]
    runtime["cooldown_left"] = {}
    assert "CLASSROOM_CHANNEL" in enemy.modifiers
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "3002041" else None)
    hero_basic = compiled.actions_by_actor["hero"][0]

    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002041")
    # 从 Change Banasyllabus 之后的稳态 AIFlag=0 进入受击换频道分支。
    runtime["dynamic_values"]["AIFlag"] = 0
    engine._execute_action(engine.state.actors["hero"], hero_basic, forced_target=enemy)
    assert "OFF_CLASS_CHANNEL" in enemy.modifiers
    assert runtime["dynamic_values"]["FlopSide"] == 1
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002041")
    assert runtime["dynamic_values"]["AIFlag"] == 2
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002041")
    assert "CLASSROOM_CHANNEL" in enemy.modifiers
    assert "OFF_CLASS_CHANNEL" not in enemy.modifiers
    assert runtime["dynamic_values"]["AIFlag"] == 0
    assert runtime["dynamic_values"]["FlopSide"] == -1
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002041")
    engine._execute_action(engine.state.actors["hero"], hero_basic, forced_target=enemy)
    engine._enemy_turn(enemy)

    assert seen == ["300204102", "300204101", "300204103", "300204102", "300204101"]


@pytest.mark.parametrize("enemy_id", ["1004030", "100403002"])
def test_bronya_boss_config_ai_redeployment_cycle(tmp_path, enemy_id):
    """基准布洛妮娅：从 Act2=2 起执行再部署→压制→再部署."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template(enemy_id)
    assert [a["action_id"] for a in template["actions"]] == [
        "100403001", "100403002", "100403003", "100403004"]
    assert not any("未收编" in note or "无可执行" in note for note in template["notes"])
    (tmp_path / "enemies").mkdir()
    for template_id in (enemy_id, "1002040", "1002050"):
        doc = template if template_id == enemy_id else generate_enemy_template(template_id)
        (tmp_path / "enemies" / f"{template_id}.yaml").write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
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
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": enemy_id, "level": 80}, {"enemy_template": "dummy"}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors[enemy_id]
    runtime = engine._enemy_policy_state[enemy_id]
    runtime["cooldown_left"] = {}
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == enemy_id else None)

    for _ in range(3):
        engine._enemy_turn(enemy)
        engine._tick_enemy_policy_cooldown(enemy_id)

    assert seen == ["100403002", "100403004", "100403002"]
    assert not [s for s in engine.state.actors.values() if s.actor.summoner_id == enemy_id]


@pytest.mark.parametrize(("enemy_id", "element"), [
    ("5013040", "quantum"), ("501304001", "quantum"), ("5013050", "fire"),
    ("5013060", "imaginary"), ("5013070", "physical"),
])
def test_daybreak_forcefield_full_cycle(tmp_path, enemy_id, element):
    """Daybreak Will：免控锁韧、同元素拉条、七次受击触发 Dispersal."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.sim.state import Modifier

    template = generate_enemy_template(enemy_id)
    base_id = "5013040" if enemy_id == "501304001" else enemy_id
    skill_ids = [f"{base_id}0{index}" for index in range(1, 6)]
    assert [a["action_id"] for a in template["actions"]] == skill_ids
    assert not any("未收编" in note or "无可执行" in note for note in template["notes"])
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / f"{enemy_id}.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def hero_action(action_id, damage_type):
        return {"action_id": action_id, "name": "测试普攻", "action_type": "basic",
                "target_type": "single", "damage_type": damage_type,
                "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "energy_gain": 0}

    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [hero_action("hero_special", element), hero_action("hero_physical", "physical")],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": enemy_id, "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors[enemy_id]
    hero = engine.state.actors["hero"]
    runtime = engine._enemy_policy_state[enemy_id]
    runtime["cooldown_left"] = {}
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == enemy_id else None)
    for _ in range(5):
        engine._enemy_turn(enemy)
        engine._tick_enemy_policy_cooldown(enemy_id)
    assert seen == [skill_ids[0], skill_ids[1], skill_ids[1], skill_ids[2], skill_ids[3]]
    assert "ENEMY_DAYBREAK_FORCEFIELD" in enemy.modifiers
    engine._apply_modifier(enemy, Modifier(
        modifier_id="TEST_CONTROL", name="测试控制", modifier_type="control",
        control_kind="freeze", prevent_action=True, duration=1))
    assert "TEST_CONTROL" not in enemy.modifiers

    toughness = enemy.toughness
    handle = engine.scheduler.handle_of(enemy_id)
    engine.scheduler._remaining[handle] = 123.0
    special = next(a for a in compiled.actions_by_actor["hero"] if a.action_id == "hero_special")
    physical = next(a for a in compiled.actions_by_actor["hero"] if a.action_id == "hero_physical")
    engine._execute_action(hero, special, forced_target=enemy)
    assert engine.scheduler._remaining[handle] == 0.0
    for _ in range(6):
        engine._execute_action(hero, physical, forced_target=enemy)
    assert enemy.toughness == toughness

    assert seen == [skill_ids[0], skill_ids[1], skill_ids[1], skill_ids[2], skill_ids[3], skill_ids[4]]
    assert "ENEMY_DAYBREAK_FORCEFIELD" not in enemy.modifiers
    assert enemy.resources.get("_daybreak_hits") == 0
    disheartened = enemy.modifiers[f"ENEMY_{skill_ids[4]}_DISHEARTENED"]
    assert disheartened.stat_effects["vulnerability"] == 0.3
    assert disheartened.stat_effects[f"res_{element}"] == -0.4
    assert disheartened.duration == 2


def test_yanqing_pingshu_config_ai_full_cycle(tmp_path):
    """彦卿评书变体：AIPhase=1 起完整执行九段 ConfigAI 出招."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("200402005")
    assert [a["action_id"] for a in template["actions"]] == [
        "200402001", "200402003", "200402004", "200402005", "200402006"]
    assert template["policy"]["config"]["AIName"] == "Monster_W2_Yanqing_00"
    assert not any("未收编" in note or "无可执行" in note for note in template["notes"])
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "200402005.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_basic", "name": "测试普攻",
                         "action_type": "basic", "target_type": "single",
                         "damage_type": "physical", "scaling": [{"atk": 0.0}],
                         "toughness_dmg": 0, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    stage = {"stage": {
        "enemies": [{"enemy_template": "200402005", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["200402005"]
    runtime = engine._enemy_policy_state["200402005"]
    runtime["cooldown_left"] = {}
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "200402005" else None)

    for _ in range(9):
        engine._enemy_turn(enemy)
        engine._tick_enemy_policy_cooldown("200402005")

    assert seen == [
        "200402001", "200402003", "200402004", "200402001", "200402004",
        "200402003", "200402001", "200402005", "200402006"]
    assert runtime["dynamic_values"]["W2_Yanqing_00_AICounter"] == 1


def test_assistanana_channel_energy_cycle(tmp_path):
    """助蕉：课堂扣能→受击换课间→回能→换课→课堂扣能."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("3002011")
    assert [a["action_id"] for a in template["actions"]] == [
        "300201101", "300201102", "300201103"]
    assert template["policy"]["config"]["AIName"] == "Monster_W1_Mecha01_00"
    assert not any("未收编" in note or "无可执行" in note for note in template["notes"])
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002011.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "3002011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3002011"]
    hero = engine.state.actors["hero"]
    hero.current_energy = 50.0
    runtime = engine._enemy_policy_state["3002011"]
    runtime["cooldown_left"] = {}
    assert "CLASSROOM_CHANNEL" in enemy.modifiers
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "3002011" else None)

    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002011")
    assert hero.current_energy == 35.0
    engine._execute_action(hero, compiled.actions_by_actor["hero"][0], forced_target=enemy)
    assert "OFF_CLASS_CHANNEL" in enemy.modifiers
    assert runtime["dynamic_values"]["FlopSide"] == 1
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002011")
    assert hero.current_energy == 85.0
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002011")
    assert "CLASSROOM_CHANNEL" in enemy.modifiers
    assert runtime["dynamic_values"]["AIFlag"] == 0
    assert runtime["dynamic_values"]["FlopSide"] == -1
    engine._enemy_turn(enemy)

    assert hero.current_energy == 70.0
    assert seen == ["300201102", "300201101", "300201103", "300201102"]


def test_domescreen_channel_crossover_cycle(tmp_path):
    """圆幕先生：惊吓→惊喜→切换惊吓→受击回惊喜的双向循环."""
    from hsr_nous.adapters.template_generator import generate_enemy_template

    template = generate_enemy_template("3002010")
    assert [a["action_id"] for a in template["actions"]] == [
        "300201001", "300201002", "300201003"]
    assert template["policy"]["config"]["AIName"] == "Monster_W1_Mecha01_00"
    assert not any("未收编" in note or "无可执行" in note for note in template["notes"])
    (tmp_path / "enemies").mkdir()
    (tmp_path / "enemies" / "3002010.yaml").write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1000, "def": 1000, "spd": 50,
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
        "enemies": [{"enemy_template": "3002010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 5000},
    }}
    compiled = compile_encounter(build, stage, template_roots=[str(tmp_path)])
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    engine.setup()
    enemy = engine.state.actors["3002010"]
    hero = engine.state.actors["hero"]
    hero.current_energy = 50.0
    runtime = engine._enemy_policy_state["3002010"]
    runtime["cooldown_left"] = {}
    assert "FRIGHT_CHANNEL" in enemy.modifiers
    seen = []
    engine.bus.subscribe(
        "on_action", lambda _event, payload, _ctx: seen.append(payload["action_id"])
        if payload.get("actor") == "3002010" else None)
    hero_basic = compiled.actions_by_actor["hero"][0]

    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002010")
    assert hero.current_energy == 30.0
    engine._execute_action(hero, hero_basic, forced_target=enemy)
    assert "SURPRISE_CHANNEL" in enemy.modifiers
    assert "FRIGHT_CHANNEL" not in enemy.modifiers
    assert runtime["dynamic_values"]["FlopSide"] == 1
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002010")
    assert hero.current_energy == 80.0
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002010")
    assert "FRIGHT_CHANNEL" in enemy.modifiers
    assert runtime["dynamic_values"]["AIFlag"] == 0
    assert runtime["dynamic_values"]["FlopSide"] == -1
    engine._enemy_turn(enemy)
    engine._tick_enemy_policy_cooldown("3002010")
    assert hero.current_energy == 60.0
    engine._execute_action(hero, hero_basic, forced_target=enemy)
    assert "SURPRISE_CHANNEL" in enemy.modifiers
    engine._enemy_turn(enemy)

    assert hero.current_energy == 100.0
    assert seen == ["300201002", "300201001", "300201003", "300201002", "300201001"]
