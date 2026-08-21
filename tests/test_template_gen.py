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
        expected = atk * 0.5 * 1.0 * 0.5 * 1.0 * 0.9 * 1.0 * crit_expected
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
