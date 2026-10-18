"""敌人模板测试：calc_enemy_stats 公式链对轴 + 特殊怪容错 + 模板形状.

对轴方式：测试独立从 json 重算 base×HardLevel×Elite×Modify（测公式链装配，不依赖数据快照值）。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from hsr_nous.adapters.template_generator import generate_enemy_template
from hsr_nous.pipeline.enemies.loader import calc_enemy_stats

from tests._data_env import data_skip_reason, stage_data_available

pytestmark = pytest.mark.skipif(not stage_data_available(), reason=data_skip_reason())

_ROOT = Path(__file__).parent.parent / "data" / "stages" / "hakushin"


def _independent_calc(enemy_id: str, level: int) -> dict:
    """独立重算（与实现不同路径：直接读三张表）."""
    mv = json.loads((_ROOT / "monstervalue.json").read_text(encoding="utf-8"))
    hard = json.loads((_ROOT / "HardLevelGroup.json").read_text(encoding="utf-8"))
    elite = json.loads((_ROOT / "EliteGroup.json").read_text(encoding="utf-8"))
    d = mv[enemy_id]
    child = next((c for c in d.get("child") or [] if str(c["Id"]) == enemy_id),
                 (d.get("child") or [{}])[0] if d.get("child") else {})
    g = {e["Level"]: e for e in hard if e["HardLevelGroup"] == child.get("HardLevelGroup", 1)}
    h = g[min(level, max(g))]
    e = next((x for x in elite if x["EliteGroup"] == child.get("EliteGroup", 1)), {})
    el = lambda k: float(e.get(k, 1) or 1)
    return {
        "hp": d["HPBase"] * h["HPRatio"] * el("HPRatio") * float(child.get("HPModifyRatio", 1) or 1),
        "atk": d["AttackBase"] * h["AttackRatio"] * el("AttackRatio") * float(child.get("AttackModifyRatio", 1) or 1),
        "spd": d["SpeedBase"] * h["SpeedRatio"] * el("SpeedRatio") * float(child.get("SpeedModifyRatio", 1) or 1)
        + float(child.get("SpeedModifyValue") or 0),
    }


class TestCalcEnemyStats:
    def test_formula_chain_matches_independent_calc(self):
        """公式链装配对轴：hp/atk/spd 与独立重算逐字段相等（rel_tol 1e-6——两源
        dump 浮点精度差异：tbgd HPRatio 148.01102 vs hakushin 148.011024）."""
        s = calc_enemy_stats("1002011", 80)
        ref = _independent_calc("1002011", 80)
        assert math.isclose(s["hp"], ref["hp"], rel_tol=1e-6)
        assert math.isclose(s["atk"], ref["atk"], rel_tol=1e-6)
        assert math.isclose(s["spd"], ref["spd"], rel_tol=1e-6)

    def test_effect_res_level_bonus(self):
        """效果抗性 = base + min((level-50)×0.4%, 10%)（Lv80 → +10% 上限）."""
        s = calc_enemy_stats("1002011", 80)  # base 0.2
        assert math.isclose(s["effect_res"], 0.2 + 0.10, rel_tol=1e-9)

    def test_elemental_resistance_from_structured_data(self):
        s = calc_enemy_stats("100401401", 80)
        expected = {"physical": 0.4, "ice": 0.6, "imaginary": 0.6}
        assert s["resistance"] == expected
        assert generate_enemy_template("100401401")["resistance"] == expected

    def test_level_clamped_beyond_table(self):
        """超出 HardLevelGroup 表级数 → 钳级并标记."""
        s = calc_enemy_stats("1002011", 999)
        assert s["_level_clamped"] is True

    def test_null_stance_base_tolerated(self):
        """StanceBase=null（无韧性条特殊怪）→ toughness 0 + 缺失名单."""
        s = calc_enemy_stats("2024020", 80)
        assert s["max_toughness"] == 0.0
        assert "StanceBase" in s["_missing_bases"]

    def test_empty_child_default_coefficients(self):
        """child=[]（无形态变体）→ 顶层 base + 默认系数，可正常生成."""
        s = calc_enemy_stats("4034020", 80)
        assert s is not None and s["hp"] > 0


class TestEnemyTemplate:
    def test_template_shape(self):
        tpl = generate_enemy_template("1002011", level=80)
        assert tpl["enemy_id"] == "1002011" and tpl["name"]  # 官方英文名（命名两态合法）
        assert tpl["weakness"] == ["fire", "thunder"]
        assert tpl["base_stats"]["hp"] > 0 and tpl["base_stats"]["spd"] > 0
        assert tpl["actions"] == [{
            "action_id": "100201101", "name": "Icy Wind", "action_type": "skill",
            "target_type": "aoe", "damage_type": "ice", "scaling": [{"atk": 2.0}],
            "toughness_dmg": 10, "energy_gain": 0, "energy_grant": 10.0,
        }]
        assert tpl["policy"]["sequence"] == ["100201101"]
        assert tpl["policy"]["cooldown"] == {"100201101": 1}
        assert tpl["policy"]["initial_cooldown"] == {"100201101": 1}
        assert tpl["policy"]["skill_ids"] == {"Skill04": "100201101"}
        assert tpl["policy"]["config"]["AIName"] == "Monster_Common_SequenceThree"
        assert any("DelayRatio" in note for note in tpl["notes"])

    def test_blast_main_and_adjacent_scaling(self):
        tpl = generate_enemy_template("4032010")
        assert tpl["actions"] == [{
            "action_id": "403201001", "name": "Tip of Destruction", "action_type": "skill",
            "target_type": "blast", "damage_type": "physical",
            "scaling": [{"atk": 3.5}], "scaling_blast": [{"atk": 2.4}],
            "toughness_dmg": 10, "energy_gain": 0, "energy_grant": 10.0,
        }]
        assert any("副目标削韧" in note for note in tpl["notes"])

    def test_blast_shared_scaling_and_purity_filter(self):
        tpl = generate_enemy_template("202301008")
        shared = next(a for a in tpl["actions"] if a["action_id"] == "202301002")
        assert shared["target_type"] == "blast" and shared["scaling"] == [{"atk": 3.0}]
        assert "scaling_blast" not in shared  # 主邻同倍率，引擎沿用主倍率
        assert generate_enemy_template("2032010")["actions"] == []  # 条件 Bleed 不收编
        spider = generate_enemy_template("1012020")
        assert "101202003" in {a["action_id"] for a in spider["actions"]}
        assert any(eff.get("effect_type") == "set_hp_to_percent" and eff.get("percent") == 0.0
                   for hook in spider["hooks"] for eff in hook["effects"])

    def test_def_impair_omits_explicit_chance_param_at_certainty(self):
        """银鬃近卫三项参数省略 100% 概率槽，仍与描述逐项对齐."""
        tpl = generate_enemy_template("1002040")
        assert tpl["actions"][0]["scaling"] == [{"atk": 3.0}]
        effect = tpl["hooks"][0]["effects"][0]
        assert effect["apply_chance"] == 1.0
        assert effect["target"] == "$event.target"
        assert effect["modifier"]["stat_effects"] == {"def_pct": -0.5}
        assert effect["modifier"]["duration"] == 2

    def test_def_impair_reduces_wording_variant(self):
        """Alloy Pommy 的 reduces 描述省略概率槽，按确定减防收编."""
        tpl = generate_enemy_template("5012120")
        assert [a["action_id"] for a in tpl["actions"]] == ["501212001", "501212002"]
        assert tpl["policy"]["config"]
        action = tpl["actions"][1]
        assert action["scaling"] == [{"atk": 2.0}] and action["target_type"] == "single"
        effect = tpl["hooks"][0]["effects"][0]
        assert effect["apply_chance"] == 1.0
        assert effect["modifier"]["stat_effects"] == {"def_pct": -0.5}
        assert effect["modifier"]["duration"] == 2

    def test_distribute_locked_on_text_variant(self):
        from hsr_nous.adapters.template_generator import _enemy_distribute_action
        from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
        action = _enemy_distribute_action(
            get_enemy_skills("3003030")[3],
            get_enemy_mechanics(get_monster_meta("3003030")["en"])["skills"][3])
        assert action["scaling"] == [{"atk": 15.0}]
        assert action["target_type"] == "aoe" and action["split"] == "even"

    def test_biting_obituary_enhance_and_break_hook(self):
        from hsr_nous.adapters.template_generator import _enemy_biting_obituary_action
        from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
        action, hooks = _enemy_biting_obituary_action(
            get_enemy_skills("3014020")[2],
            get_enemy_mechanics(get_monster_meta("3014020")["en"])["skills"][2])
        assert action["target_type"] == "self"
        modifier = hooks[0]["effects"][0]["modifier"]
        assert modifier["stat_effects"] == {"all_dmg": 1.0}
        assert modifier["duration"] == 2
        assert hooks[1]["event"] == "on_break"
        assert hooks[1]["effects"][0]["modifier_id"] == modifier["modifier_id"]

    def test_allargando_shield_buff_and_toughness_lock(self):
        from hsr_nous.adapters.template_generator import _enemy_allargando_action
        from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
        action, hook = _enemy_allargando_action(
            get_enemy_skills("3025010")[8],
            next(s for s in get_enemy_mechanics(get_monster_meta("3025010")["en"])["skills"]
                 if s["name"] == "Allargando"))
        assert action["target_type"] == "self"
        modifier = hook["effects"][0]["modifier"]
        assert modifier["shield"] == {"scaling": {"hp": 0.125}}
        assert modifier["stat_effects"] == {"all_dmg": 0.3, "dmg_dmg_reduction": 0.75}
        assert modifier["toughness_lock"] is True

    def test_living_eternal_flame_passive(self):
        from hsr_nous.adapters.template_generator import _enemy_convert_passive
        from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
        hooks = _enemy_convert_passive(
            get_enemy_skills("4012023")[1],
            get_enemy_mechanics(get_monster_meta("4012023")["en"])["skills"][2])
        assert hooks[0]["event"] == "on_kill"
        effect = hooks[0]["effects"][0]
        assert effect["target"] == "$event.source"
        assert effect["modifier"]["stat_effects"] == {"spd_pct": 0.3, "all_dmg": 0.3}
        assert effect["modifier"]["duration"] == 2

    def test_dot_stack_caps_and_omitted_max_stack_param(self):
        shock = generate_enemy_template("2004010")["hooks"][0]["effects"][0]
        assert shock["apply_chance"] == 1.0
        assert shock["modifier"]["max_stack"] == 1  # 非叠层 Shock 重挂不得放大 DoT
        wind = generate_enemy_template("8001050")["hooks"][0]["effects"][0]
        assert wind["modifier"]["dot_ratio"] == 0.8
        assert wind["modifier"]["max_stack"] == 5  # 原始四项省略上限槽，文本 Max 5 对齐

    def test_aoe_dot_layouts(self):
        from hsr_nous.adapters.template_generator import _enemy_burn_action, _enemy_wind_shear_action
        from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
        burn_action, burn_hook = _enemy_burn_action(
            get_enemy_skills("3024020")[4],
            next(s for s in get_enemy_mechanics(get_monster_meta("3024020")["en"])["skills"]
                 if s["name"] == "DHGDR: Supernova Overload"))
        assert burn_action["target_type"] == "aoe" and burn_action["scaling"] == [{"atk": 2.7}]
        burn = burn_hook["effects"][0]
        assert burn["target"] == "all_allies" and burn["apply_chance"] == 1.2
        assert burn["modifier"]["dot_ratio"] == 0.8 and burn["modifier"]["duration"] == 3

        wind_action, wind_hook = _enemy_wind_shear_action(
            get_enemy_skills("8024010")[2],
            next(s for s in get_enemy_mechanics(get_monster_meta("8024010")["en"])["skills"]
                 if s["name"] == "Cyclonic Swarm"))
        assert wind_action["target_type"] == "aoe" and wind_action["scaling"] == [{"atk": 1.5}]
        wind = wind_hook["effects"][0]
        assert wind["target"] == "all_allies"
        assert wind["modifier"]["dot_ratio"] == 0.5 and wind["modifier"]["max_stack"] == 5

    def test_wind_shear_direct_stack_layout(self):
        from hsr_nous.adapters.template_generator import _enemy_wind_shear_action
        from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills, get_monster_meta
        _action, hook = _enemy_wind_shear_action(
            get_enemy_skills("8024010")[0],
            next(s for s in get_enemy_mechanics(get_monster_meta("8024010")["en"])["skills"]
                 if s["name"] == "Time to Battle"))
        modifier = hook["effects"][0]["modifier"]
        assert modifier["stacks"] == 2 and modifier["duration"] == 3
        assert modifier["dot_ratio"] == 0.5 and modifier["max_stack"] == 5

    def test_bleed_uses_explicit_tick_expression(self):
        effect = generate_enemy_template("3001020")["hooks"][0]["effects"][0]
        assert effect["apply_chance"] == 0.5
        assert effect["modifier"]["dot_ratio_expr"] == "0.2 * $self.max_hp"
        assert "dot_ratio" not in effect["modifier"]

    def test_shock_reversed_params_and_certainty_slot(self):
        effect = generate_enemy_template("2022051")["hooks"][0]["effects"][0]
        assert effect["apply_chance"] == 1.0
        assert effect["modifier"]["dot_ratio"] == 1.5
        assert effect["modifier"]["duration"] == 3

    def test_crimson_blade_burn_omits_chance_param(self):
        from hsr_nous.adapters.template_generator import _enemy_burn_action
        from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics, get_enemy_skills
        action, hook = _enemy_burn_action(
            get_enemy_skills("1023010")[0],
            get_enemy_mechanics("Searing Prowler")["skills"][0])
        assert action["scaling"] == [{"atk": 3.0}]
        modifier = hook["effects"][0]["modifier"]
        assert modifier["dot_ratio"] == 0.5 and modifier["duration"] == 3

    def test_wind_shear_layouts_and_initial_stacks(self):
        juvenile = generate_enemy_template("8022010")["hooks"][0]["effects"][0]["modifier"]
        assert juvenile["stacks"] == 1 and juvenile["duration"] == 3
        assert juvenile["dot_ratio"] == 0.5
        mara = generate_enemy_template("2022010")["hooks"][0]["effects"][0]["modifier"]
        assert mara["stacks"] == 2 and mara["duration"] == 3
        assert mara["dot_ratio"] == 0.5

    def test_cloud_edge_alternate_vulnerability_layout(self):
        effect = generate_enemy_template("2002010")["hooks"][0]["effects"][0]
        assert effect["modifier"]["stat_effects"] == {"vulnerability": 0.25}
        assert effect["modifier"]["duration"] == 2

    def test_special_ai_path_requires_full_sequence_coverage(self):
        baryon = generate_enemy_template("8011010")
        assert baryon["actions"][0]["action_id"] == "801101001"
        assert baryon["policy"]["sequence"] == ["801101001"]
        kafka = generate_enemy_template("2004010")
        assert kafka["actions"][0]["action_id"] == "200401001"
        assert kafka["policy"]["sequence"] == ["200401001"]
        grizzly = generate_enemy_template("1013010")
        assert grizzly["actions"] == [] and "policy" not in grizzly  # Enrage 首参数语义未定，专属序列不收编
        trampler = generate_enemy_template("8013010")
        assert "config" not in trampler["policy"]
        assert any("initial:no-executable-decision" in note for note in trampler["notes"])
        bronya = generate_enemy_template("1004030")
        assert bronya["actions"] == [] and "policy" not in bronya  # config-only 无可执行覆盖同样不留空 policy

    def test_timed_charge_action_text_variants(self):
        from hsr_nous.adapters.template_generator import _enemy_timed_charge_action
        descriptions = [
            ("Charge", "The next action uses Self-Exploding Module."),
            ("Charge", "Enters the Charging state. Uses Work Culture Shock in the next action."),
            ("Charging", 'Enters the Charging state. Uses "Drowned in the Crimson Sea" in the next turn.'),
            ("Charge", "Enters the Charging state. Casts Liberation in the next action."),
        ]
        for index, (skill_type, desc) in enumerate(descriptions):
            action = _enemy_timed_charge_action(
                {"skill_id": f"T{index}", "param_list": []},
                {"name": "Charge", "type": skill_type, "desc": desc})
            assert action["action_id"] == f"T{index}" and action["target_type"] == "self"
        assert _enemy_timed_charge_action(
            {"skill_id": "BAD", "param_list": [1.0]},
            {"name": "Charge", "type": "Charge", "desc": descriptions[1][1]}) is None

    def test_lesser_sting_outrage_detonation(self):
        tpl = generate_enemy_template("8022020")
        assert [a["action_id"] for a in tpl["actions"]] == ["802202001", "802202002"]
        assert tpl["policy"]["config"]["AIName"] == "WMonster_TY_Elite01_03"
        action = tpl["actions"][1]
        assert action["scaling"] == [{"atk": 3.0}]
        assert action["scaling_blast"] == [{"atk": 3.0}]
        effects = tpl["hooks"][0]["effects"]
        assert effects[0]["modifier"]["control_kind"] == "outrage"
        assert effects[0]["modifier"]["duration"] == 2
        assert effects[1] == {"effect_type": "set_hp_to_percent", "target": "self", "percent": 0.0}

    def test_trotter_giant_scared_text_variant(self):
        tpl = generate_enemy_template("8002109")
        assert [a["action_id"] for a in tpl["actions"]] == [
            "800210901", "800210902", "800210903"]
        assert tpl["policy"]["config"]["AIName"] == "Monster_XP_Minion04_01"
        modifiers = [hook["effects"][0]["modifier"] for hook in tpl["hooks"]
                     if hook["effects"][0].get("effect_type") == "apply_modifier"]
        assert [m["modifier_id"] for m in modifiers] == [
            "MMonster_XP_Minion04_01_EscapingCharge01",
            "MMonster_XP_Minion04_01_EscapingCharge02",
        ]

    def test_end_of_bow_omits_explicit_base_chance(self):
        tpl = generate_enemy_template("8013011")
        action = next(a for a in tpl["actions"] if a["action_id"] == "801301105")
        assert action["scaling"] == [{"atk": 8.0}]
        effect = next(eff for hook in tpl["hooks"] for eff in hook["effects"]
                      if eff.get("modifier", {}).get("control_kind") == "entangle")
        assert effect["apply_chance"] == 1.0
        assert effect["modifier"]["dot_ratio"] == 0.8
        assert effect["modifier"]["on_apply"][0]["amount"] == 100.0

    def test_trotter_charge_markers_come_from_config(self):
        hooks = generate_enemy_template("8002050")["hooks"]
        modifiers = [hook["effects"][0]["modifier"] for hook in hooks
                     if hook["effects"][0].get("effect_type") == "apply_modifier"]
        assert [m["modifier_id"] for m in modifiers] == [
            "MMonster_XP_Minion04_01_EscapingCharge01",
            "MMonster_XP_Minion04_01_EscapingCharge02",
        ]
        assert all(m["singleton_group"] == "escape_charge" for m in modifiers)

    def test_numbered_fandom_variant_disambiguated_by_weakness(self):
        from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics
        matched = get_enemy_mechanics("Ice Edge", weakness=["fire", "thunder"])
        assert matched and matched["_page_title"] == "Ice Edge (1)"
        assert get_enemy_mechanics("Ice Edge") is None
        assert get_enemy_mechanics("Ice Edge", weakness=["fire", "ice"]) is None

    def test_boss_title_alias(self):
        from hsr_nous.pipeline.enemies.loader import get_enemy_mechanics
        matched = get_enemy_mechanics("Cocolia")
        assert matched and matched["_page_title"] == "Cocolia (Boss)"
        assert get_enemy_mechanics("Gepard")["_page_title"] == "Gepard (Boss)"

    def test_full_smoke_all_monsters(self):
        """全量冒烟：模板花名册 + Hakushin 关卡实例花名册生成不炸."""
        from hsr_nous.pipeline.stages.loader import list_hakushin_monster_ids
        mv = json.loads((_ROOT / "monstervalue.json").read_text(encoding="utf-8"))
        enemy_ids = set(mv)
        for mode in ("moc", "pf", "as"):
            enemy_ids.update(list_hakushin_monster_ids(mode))
        for eid in sorted(enemy_ids):
            tpl = generate_enemy_template(eid, level=80)
            assert tpl["base_stats"]["hp"] >= 0


class TestMonsterMetaQuery:
    """A2：monster.json 读取下沉 pipeline 查询函数（生成器不拼数据路径）."""

    def test_get_monster_meta_default(self):
        from hsr_nous.pipeline.enemies.loader import get_monster_meta
        meta = get_monster_meta("1002011")
        assert meta and meta["en"] == "Ice Edge"
        assert get_monster_meta("9999999_不存在") is None

    def test_instance_meta_resolves_template_name(self):
        from hsr_nous.pipeline.enemies.loader import get_monster_meta
        instance = get_monster_meta("100401401")
        template = get_monster_meta("1004014")
        assert instance and template and instance["en"] == template["en"]


class TestEnemyAIConfig:
    def test_load_missing_and_path_guard(self, tmp_path):
        from hsr_nous.pipeline.enemies.loader import get_enemy_ai_config
        path = tmp_path / "Config" / "ConfigAI"
        path.mkdir(parents=True)
        (path / "demo.json").write_text('{"AIName": "demo"}', encoding="utf-8")
        assert get_enemy_ai_config(
            "Config/ConfigAI/demo.json", tbgd_dir=str(tmp_path)) == {"AIName": "demo"}
        assert get_enemy_ai_config("Config/ConfigAI/missing.json", tbgd_dir=str(tmp_path)) is None
        with pytest.raises(ValueError, match="非法 AIPath"):
            get_enemy_ai_config("../demo.json", tbgd_dir=str(tmp_path))

    def test_update_downloads_referenced_config_ai(self, tmp_path, monkeypatch):
        from hsr_nous.pipeline.enemies import update as enemies_update
        tables = {
            "MonsterTemplateConfig.json": [{
                "MonsterTemplateID": 1, "AIPath": "Config/ConfigAI/A.json",
            }],
            "MonsterConfig.json": [{
                "MonsterID": 1, "MonsterTemplateID": 1,
                "OverrideAIPath": "Config/ConfigAI/B.json",
            }],
            "MonsterSkillConfig.json": [],
            "EliteGroup.json": [],
            "HardLevelGroup.json": [],
        }
        configs = {
            "Config/ConfigAI/A.json": {"AIName": "A"},
            "Config/ConfigAI/B.json": {"AIName": "B"},
        }
        calls = []

        def _fake_download(url, *, timeout):
            filename = url.rsplit("ExcelOutput/", 1)[1]
            calls.append(filename)
            if filename in tables:
                return json.dumps(tables[filename]).encode(), "etag"
            if filename in configs:
                return json.dumps(configs[filename]).encode(), "etag"
            raise AssertionError(f"不应下载未引用文件 {filename}")

        monkeypatch.setattr(
            "hsr_nous.pipeline.build.update.download_with_etag", _fake_download)
        assert enemies_update.run_update(data_dir=str(tmp_path)) == 0
        assert (tmp_path / "Config" / "ConfigAI" / "A.json").exists()
        assert (tmp_path / "Config" / "ConfigAI" / "B.json").exists()
        assert max(calls.index(name) for name in enemies_update.TBGD_FILES) < min(
            calls.index("Config/ConfigAI/A.json"), calls.index("Config/ConfigAI/B.json"))
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["failed"] == []


class TestEnemyDataDirInjection:
    """A2：data_dir 注入——生成器读注入根的 tbgd/monster/fandom 数据（缺省走缺省根）."""

    @pytest.fixture()
    def mini_data(self, tmp_path):
        import json as j
        tbgd = tmp_path / "turnbasedgamedata"
        tbgd.mkdir(parents=True)
        (tbgd / "MonsterTemplateConfig.json").write_text(j.dumps([{
            "MonsterTemplateID": 9001, "AttackBase": {"Value": 100.0},
            "DefenceBase": {"Value": 50.0}, "HPBase": {"Value": 1000.0},
            "SpeedBase": {"Value": 100.0}, "StanceBase": {"Value": 30.0},
            "StatusResistanceBase": {"Value": 0.1}}]), encoding="utf-8")
        (tbgd / "MonsterConfig.json").write_text(j.dumps([{
            "MonsterID": 9001, "MonsterTemplateID": 9001,
            "HardLevelGroup": 1, "EliteGroup": 1,
            "StanceWeakList": ["Fire"]}]), encoding="utf-8")
        (tbgd / "HardLevelGroup.json").write_text(j.dumps([{
            "HardLevelGroup": 1, "Level": 80, "HPRatio": {"Value": 1.0},
            "AttackRatio": {"Value": 1.0}, "DefenceRatio": {"Value": 1.0},
            "SpeedRatio": {"Value": 1.0}, "StanceRatio": {"Value": 1.0}}]), encoding="utf-8")
        (tbgd / "EliteGroup.json").write_text(j.dumps([{
            "EliteGroup": 1, "HPRatio": {"Value": 1.0}, "AttackRatio": {"Value": 1.0},
            "DefenceRatio": {"Value": 1.0}, "SpeedRatio": {"Value": 1.0},
            "StanceRatio": {"Value": 1.0}}]), encoding="utf-8")
        (tbgd / "MonsterSkillConfig.json").write_text("[]", encoding="utf-8")
        hak = tmp_path / "stages" / "hakushin"
        hak.mkdir(parents=True)
        (hak / "monster.json").write_text(j.dumps({
            "9001": {"en": "Test Dummy"}}), encoding="utf-8")
        (tmp_path / "fandom_enemy_data.json").write_text(j.dumps({
            "Test Dummy": {"skills": [{"name": "Slap", "type": "Basic ATK",
                                       "desc": "Deals damage."}]}}), encoding="utf-8")
        return str(tmp_path)

    def test_generate_reads_injected_data_dir(self, mini_data):
        tpl = generate_enemy_template("9001", level=80, data_dir=mini_data)
        assert tpl["name"] == "Test Dummy"          # monster.json 来自注入根
        assert tpl["base_stats"]["hp"] == 1000.0    # tbgd 公式链来自注入根
        assert tpl["weakness"] == ["fire"]
        assert any("Slap" in n for n in tpl["notes"])  # fandom 技能 notes 来自注入根

    def test_default_data_dir_unchanged(self):
        """缺省行为不变：生产根读真数据（命名两态——官方英文名）."""
        tpl = generate_enemy_template("1002011", level=80)
        assert tpl["name"] == "Ice Edge"
