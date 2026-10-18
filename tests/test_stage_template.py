"""stage_template 引用与 Hakushin 关卡模板生成（正反例）."""

from __future__ import annotations

import pytest
import yaml

from hsr_nous.adapters.template_generator import generate_stage_template, write_stage_template
from hsr_nous.sim.compile.build_compiler import DEFAULT_TEMPLATE_ROOTS
from hsr_nous.sim.compile.stage_compiler import StageCompiler


def test_hakushin_generate_write_and_compile_with_overrides(tmp_path):
    tpl = generate_stage_template("moc", "1035")
    assert tpl["stage_id"] == "moc_1035_5401_s1"
    assert tpl["mode"] == "forgotten_hall"
    assert [(wave["wave_index"], len(wave["enemies"])) for wave in tpl["waves"]] == [(1, 3), (2, 2)]
    actor_ids = [enemy["actor_id"] for wave in tpl["waves"] for enemy in wave["enemies"]]
    assert len(actor_ids) == len(set(actor_ids)), "actor_id 必须跨波/同型怪去重"

    write_stage_template("moc", "1035", out_dir=str(tmp_path / "stages"))
    enemy_id = tpl["waves"][0]["enemies"][0]["enemy_template"]
    compiled = StageCompiler().compile({
        "stage_template": tpl["stage_id"],
        "stage_id": "custom_stage",
        "enemy_level_overrides": {enemy_id: 95},
    }, template_roots=[str(tmp_path), *DEFAULT_TEMPLATE_ROOTS])
    assert compiled.stage_id == "custom_stage"
    assert compiled.termination_mode == "fixed_av" and compiled.max_action_value == 450
    assert compiled.cycle.reset_on_wave is True
    assert {index: len(wave) for index, wave in compiled.waves.items()} == {1: 3, 2: 2}
    overridden = compiled.waves[1][0]
    assert overridden.actor_id == tpl["waves"][0]["enemies"][0]["actor_id"]
    assert overridden.level == 95


def test_stage_template_rejections(tmp_path):
    with pytest.raises(ValueError, match="不得与 inline"):
        StageCompiler().compile({"stage_template": "x", "waves": []})
    with pytest.raises(ValueError, match="单个模板 id"):
        StageCompiler().compile({"stage_template": "../x"})
    with pytest.raises(NotImplementedError, match="environment_overrides"):
        StageCompiler().compile({"environment_overrides": {}})
    with pytest.raises(ValueError, match="仅可与 stage_template"):
        StageCompiler().compile({"enemy_level_overrides": {"1002011": 95}})
    with pytest.raises(ValueError, match="引用侧只允许"):
        StageCompiler().compile({"stage_template": "x", "name": "静默覆盖"})

    (tmp_path / "stages").mkdir()
    (tmp_path / "stages" / "nested.yaml").write_text("stage_template: other\n", encoding="utf-8")
    with pytest.raises(ValueError, match="不得嵌套"):
        StageCompiler().compile({"stage_template": "nested"},
                                template_roots=[str(tmp_path), *DEFAULT_TEMPLATE_ROOTS])

    tpl = generate_stage_template("moc", "1035")
    write_stage_template("moc", "1035", out_dir=str(tmp_path / "stages"))
    with pytest.raises(ValueError, match="不在 stage 模板怪物清单"):
        StageCompiler().compile({
            "stage_template": tpl["stage_id"], "enemy_level_overrides": {"999999": 95},
        }, template_roots=[str(tmp_path), *DEFAULT_TEMPLATE_ROOTS])

    enemy_id = tpl["waves"][0]["enemies"][0]["enemy_template"]
    with pytest.raises(ValueError, match="越界"):
        StageCompiler().compile({
            "stage_template": tpl["stage_id"], "enemy_level_overrides": {enemy_id: 0},
        }, template_roots=[str(tmp_path), *DEFAULT_TEMPLATE_ROOTS])


def test_stage_generation_mode_side_floor_validation():
    with pytest.raises(ValueError, match="暂不支持"):
        generate_stage_template("aa", "3001")
    with pytest.raises(ValueError, match="side"):
        generate_stage_template("moc", "1035", side=2)
    with pytest.raises(ValueError, match="floor_index"):
        generate_stage_template("moc", "1035", floor_index=99)


def test_hakushin_monster_roster_covers_instance_references():
    from hsr_nous.pipeline.stages.loader import list_hakushin_monster_ids
    roster = set(list_hakushin_monster_ids("as"))
    tpl = generate_stage_template("as", "3001")
    referenced = {enemy["enemy_template"] for wave in tpl["waves"] for enemy in wave["enemies"]}
    assert referenced <= roster
    assert "100401401" in roster  # 同模板多阶段实例，不能只生成 MonsterTemplateID 花名册


def test_wave_index_continues_across_multiple_events():
    from hsr_nous.pipeline.stages.loader import get_stage_hakushin
    data = get_stage_hakushin("moc", "100")
    floor_index = next(i for i, floor in enumerate(data["floors"]) if floor["id"] == 8)
    tpl = generate_stage_template("moc", "100", floor_index=floor_index)
    assert [wave["wave_index"] for wave in tpl["waves"]] == [1, 2]
    actor_ids = [enemy["actor_id"] for wave in tpl["waves"] for enemy in wave["enemies"]]
    assert len(actor_ids) == len(set(actor_ids))


def test_same_summoner_across_waves_namespaces_summons():
    compiled = StageCompiler().compile(
        {"stage_template": "moc_1001_2009_s2"}, template_roots=["data/sim_templates"])
    defs = compiled.enemy_summon_defs
    assert len(defs) == 4 and len(set(defs)) == 4
    assert {d.owner_id for d in defs.values()} == {
        "2023010__moc_1001_2009_s2_w1_p1", "2023010__moc_1001_2009_s2_w2_p1"}
    for hook in compiled.enemy_hooks:
        for effect in hook.effects:
            if effect.get("summon_id"):
                assert effect["summon_id"] in defs


def test_enemy_resistance_compiled_from_template():
    compiled = StageCompiler().compile(
        {"stage_template": "as_3001_30011_s1"}, template_roots=["data/sim_templates"])
    actor = next(a for a in compiled.waves[1] if a.actor_id.startswith("100401401__"))
    assert actor.stats.resistance == {"physical": 0.4, "ice": 0.6, "imaginary": 0.6}


def test_real_stage_engine_smoke_with_enemy_actions():
    """真实双波次关卡跑通：敌方真实技能执行、转波与击杀终止均留结构化证据."""
    from dataclasses import replace
    from hsr_nous.sim.compile import compile_encounter
    from hsr_nous.sim.engine import CombatEngine
    from hsr_nous.sim.pipeline import MODE_EXPECTED
    from hsr_nous.sim.structured_log import StructuredLogger

    build = {"build": {
        "team": [{
            "actor_id": "hero", "name": "测试员", "inline": True,
            "base_stats": {"hp": 1e12, "atk": 1e6, "def": 1e9, "spd": 40,
                           "max_energy": 100},
            "actions": [{"action_id": "hero_aoe", "name": "测试群攻", "action_type": "basic",
                         "target_type": "aoe", "damage_type": "fire",
                         "scaling": [{"atk": 10.0}], "toughness_dmg": 1000, "energy_gain": 0}],
        }],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0},
        ]},
    }}
    compiled = compile_encounter(
        build, {"stage": {"stage_template": "moc_100_8_s1"}},
        template_roots=["data/sim_templates"])
    # smoke 只放宽 AV 预算让双波次跑完，不改编成、技能、速度或策略。
    compiled = replace(compiled, stage=replace(compiled.stage, max_action_value=5000.0))
    engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    logger = StructuredLogger(engine)
    state = engine.run()

    assert not [s.actor_id for s in state.actors.values()
                if s.actor.actor_type == "monster" and s.alive]
    enemy_actions = [e for e in logger.entries if e.get("event_type") == "action"
                     and e.get("actor_id") in compiled.stage.enemy_actions]
    assert {e["action_id"] for e in enemy_actions} == {"101201001", "101201002", "101203001"}
    wave_starts = [e["wave_index"] for e in logger.entries if e.get("event_type") == "wave_start"]
    assert {1, 2} <= set(wave_starts)
    battle_ends = [e for e in logger.entries if e.get("event_type") == "battle_end"]
    assert battle_ends[-1]["reason"] == "target_killed"
