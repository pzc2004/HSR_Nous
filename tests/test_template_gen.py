"""v0.5 adapters 模板生成测试：真角色数据 → 模板 → 编译 → 引擎.

首个真角色：丹恒（1002，纯 atk 直伤，无机制依赖）。
"""
from __future__ import annotations

import math

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

DAN_HENG_ID = "1002"


@pytest.fixture(scope="module")
def dan_heng_template():
    """生成丹恒模板（module 级，只生成一次）."""
    from hsr_nous.adapters.template_generator import write_character_template
    path = write_character_template(DAN_HENG_ID, level=80, lang="cn")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestTemplateGeneration:
    def test_template_shape(self, dan_heng_template):
        tpl = dan_heng_template
        assert tpl["actor_id"] == DAN_HENG_ID and tpl["name"] == "丹恒"
        assert tpl["base_stats"]["atk"] > 0 and tpl["base_stats"]["hp"] > 0
        types = {a["action_type"] for a in tpl["actions"]}
        assert types == {"basic", "skill", "ultimate"}
        for a in tpl["actions"]:
            assert a["scaling"] and a["scaling"][0]["atk"] > 0
            assert a["damage_type"] == "wind"

    def test_scaling_values(self, dan_heng_template):
        """倍率对轴：普攻 lvl1=0.5、战技 lvl1=1.3、终结 lvl1=2.4（StarRailRes 参数）."""
        by_type = {a["action_type"]: a for a in dan_heng_template["actions"]}
        assert math.isclose(by_type["basic"]["scaling"][0]["atk"], 0.5)
        assert math.isclose(by_type["skill"]["scaling"][0]["atk"], 1.3)
        assert math.isclose(by_type["ultimate"]["scaling"][0]["atk"], 2.4)


class TestTemplateToEngine:
    def _build(self):
        return {
            "build": {
                "team": [{"character_template": DAN_HENG_ID, "level": 80}],
                "policy": {"name": "p", "action_rules": [
                    {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                    {"condition": "true", "action": "basic", "priority": 0},
                ]},
            }
        }

    def _stage(self):
        return {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e", "name": "假人", "hp": 1e9, "spd": 100, "max_toughness": 9999, "weakness": ["wind"]},
        ], "termination": {"mode": "fixed_av", "max_action_value": 200}}}

    def test_template_ref_compiles(self, dan_heng_template):
        """character_template 引用路径打通."""
        compiled = compile_encounter(self._build(), self._stage())
        assert compiled.build_team[0].actor_id == DAN_HENG_ID
        assert len(compiled.actions_by_actor[DAN_HENG_ID]) == 3

    def test_real_character_damage_hand_calc(self, dan_heng_template):
        """真丹恒打风弱假人：伤害 = atk×0.5×0.5×0.9×crit期望（普攻 lvl1，期望模式）."""
        compiled = compile_encounter(self._build(), self._stage())
        engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        state = engine.run()

        base = dan_heng_template["base_stats"]
        atk = base["atk"]
        crit_expected = base["crit_rate"] * (1 + base["crit_dmg"]) + (1 - base["crit_rate"])
        # def：假人无面板防御 → 200+10×80=1000；attacker_const = 80×10+200=1000 → 0.5
        # 行迹：dmg_bonus.wind 进面板（直加）；atk_pct 经 trace modifier 白值乘算（atk_eff = atk×(1+pct)）
        wind_boost = 1.0 + (base.get("dmg_bonus") or {}).get("wind", 0.0)
        atk_eff = atk * (1.0 + (dan_heng_template.get("trace_stat_effects") or {}).get("atk_pct", 0.0))
        expected = atk_eff * 0.5 * 1.0 * 0.5 * 1.0 * 0.9 * wind_boost * crit_expected
        hits = [l for l in state.log if "丹恒" in l and "伤害" in l]
        assert hits, f"丹恒应有伤害记录：{state.log[:5]}"
        # 丹恒 spd 高于假人，先手两动内敌人不反击；按实际动数×单动期望比对总量
        assert math.isclose(state.total_damage, expected * len(hits), rel_tol=1e-4), (
            f"期望每动 {expected:.1f} × {len(hits)} 动 = {expected * len(hits):.1f}，"
            f"实际 {state.total_damage:.1f}"
        )


class TestScalingNotes:
    def test_hp_scaling_characters_flagged(self):
        """HP/DEF 倍率角色会打 scaling_note 警示（不静默错生成）."""
        from hsr_nous.adapters.template_generator import generate_character_template
        tpl = generate_character_template("1205", level=80, lang="cn")  # 刃：生命倍率
        assert "scaling_notes" in tpl, "刃应有 HP 倍率警示"


@pytest.fixture(scope="module")
def phainon_actions():
    from hsr_nous.adapters.template_generator import generate_character_template
    tpl = generate_character_template("1408", level=80, lang="cn")  # 白厄
    return {a["action_id"]: a for a in tpl["actions"]}


class TestTargetTypeFromRawData:
    """v0.7 写法二（决策卡 #18 补注）：target_type / scaling_blast 忠于原始数据."""

    def test_blast_scaling_blast_from_params(self, phainon_actions):
        """血棘渡亡 140808：blast 形态，副倍率照抄 params（lvl1 主 1.25/副 0.375）."""
        a = phainon_actions["140808"]
        assert a["target_type"] == "blast"
        assert math.isclose(a["scaling"][0]["atk"], 1.25)
        assert math.isclose(a["scaling_blast"][0]["atk"], 0.375)
        # 按等级数组各自成长（lvl2 主 1.5/副 0.45——非固定比例）
        assert math.isclose(a["scaling"][1]["atk"], 1.5)
        assert math.isclose(a["scaling_blast"][1]["atk"], 0.45)

    def test_aoe_and_bounce_from_effect(self, phainon_actions):
        """终结技 140803=AoEAttack→aoe；死星天裁 140811=Bounce→bounce."""
        assert phainon_actions["140803"]["target_type"] == "aoe"
        assert phainon_actions["140811"]["target_type"] == "bounce"

    def test_enhance_has_no_damage_scaling(self, phainon_actions):
        """Enhance 类（140809）：params[0] 不是伤害倍率，清空防误进伤害结算."""
        a = phainon_actions["140809"]
        assert a["target_type"] == "self"
        assert a["scaling"] == [] and a["damage_type"] is None


class TestLightConeTemplate:
    """光锥模板：白值 + properties 语义命名列 + params 占位列."""

    def test_lc_23042_shape(self):
        from hsr_nous.adapters.template_generator import generate_light_cone_template
        tpl = generate_light_cone_template("23042")
        assert tpl["light_cone_id"] == "23042" and tpl["name"] == "愿虹光永驻天空"
        assert tpl["base_stats"]["atk"] > 0 and tpl["base_stats"]["hp"] > 0
        # properties（SpeedAddedRatio）同值对齐并成语义列，顶替 params 第 1 列
        assert math.isclose(tpl["lookup_tables"]["spd_pct"][0], 0.18)
        assert math.isclose(tpl["lookup_tables"]["spd_pct"][4], 0.30)
        assert "param_1" not in tpl["lookup_tables"]
        # 未命中列保留占位名；全 0 列（param_3）跳过
        assert "param_2" in tpl["lookup_tables"]
        assert "param_3" not in tpl["lookup_tables"]
        # bindings 与表一一对应
        assert len(tpl["variable_bindings"]) == len(tpl["lookup_tables"])
        assert tpl["notes"], "机制 desc 应留存 notes 待收编"


class TestRelicSetTemplate:
    def test_relic_102_stat_effects(self):
        from hsr_nous.adapters.template_generator import generate_relic_set_template
        tpl = generate_relic_set_template("102")
        assert tpl["relic_set_id"] == "102"
        # properties 结构化映射：2pc 攻击 12%、4pc 速度 6%
        assert math.isclose(tpl["set_2pc"]["stat_effects"]["atk_pct"], 0.12)
        assert math.isclose(tpl["set_4pc"]["stat_effects"]["spd_pct"], 0.06)
        # desc 未覆盖部分（普攻伤害 10%）不在 properties → notes 留存
        assert tpl["notes"]


class TestFullSmoke:
    """全量生成冒烟：光锥/遗器全量不炸（生成器铁律：不静默错生成）."""

    def test_all_light_cones_generate(self):
        from hsr_nous.pipeline.loader import list_light_cones
        from hsr_nous.adapters.template_generator import generate_light_cone_template
        for lc_id, _ in list_light_cones(lang="cn"):
            tpl = generate_light_cone_template(lc_id)
            assert tpl["base_stats"]["atk"] >= 0

    def test_all_relic_sets_generate(self):
        from hsr_nous.pipeline.loader import list_relic_sets
        from hsr_nous.adapters.template_generator import generate_relic_set_template
        for set_id, _ in list_relic_sets(lang="cn"):
            tpl = generate_relic_set_template(set_id)
            assert tpl["name"]
