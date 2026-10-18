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
        "seq_idx": 3, "cooldown_left": {"a": 0},
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


def test_restore_action_heals_enemy_side_with_caster_hp_ratio():
    """Hound Restore：序列真正执行支援 action，并按施放者 HP 25% 治疗敌方而非我方."""
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
        "enemies": [{"enemy_template": "1012010", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 1000},
    }}
    compiled = compile_encounter(build, stage, template_roots=["data/sim_templates"])
    assert any(h.owner_id == "1012010" and h.event == "on_action"
               and any(e.get("effect_type") == "heal" and e.get("ratio") == 0.25
                       for e in h.effects)
               for h in compiled.hooks)
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    logger = StructuredLogger(engine)
    seen = []

    def _on_action(_event_type, payload, _ctx):
        if payload.get("actor") == "1012010" and payload.get("action_id") == "101201002":
            seen.append(payload["action_id"])

    engine.bus.subscribe("on_action", _on_action)
    engine.setup()
    hp_before = None
    for _ in range(100):
        hp_before = engine.state.actors["1012010"].current_hp
        engine.step()
        if seen:
            break
    assert seen == ["101201002"] and hp_before is not None
    enemy = engine.state.actors["1012010"]
    healed = enemy.current_hp - hp_before
    max_hp = engine.pipeline.effective_stats(enemy)["hp"]
    assert math.isclose(healed, 0.25 * max_hp, rel_tol=1e-9)
    heals = [e for e in logger.entries if e.get("event_type") == "heal"]
    assert heals and all(e["target_id"] == "1012010" for e in heals)
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
    assert set(compiled.stage.enemy_summon_defs) == {s["summon_id"] for s in specs}
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
        summoned = engine.state.actors[spec["summon_id"]]
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
