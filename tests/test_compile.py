"""编译层测试：DSL 模板(YAML inline) → CompiledEncounter → 引擎 → 对轴 golden case.

v0.1 的 4050 手算基准必须经"模板→编译→执行"的正式路径复现——
这才叫"引擎能吃 DSL 模板"。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter, desugar, list_sugars
from hsr_nous.sim.compile.sugar import SugarError
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

HERO_YAML = {
    "build": {
        "team": [{
            "character_template": "inline",
            "actor_id": "hero",
            "name": "黄泉",
            "level": 80,
            "base_stats": {
                "atk": 3000, "spd": 134, "hp": 1200, "max_energy": 110,
                "crit_rate": 0.5, "crit_dmg": 1.0,
            },
            "actions": [{
                "action_id": "hero_basic", "name": "普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "thunder",
                "scaling": [{"atk": 1.0}],
            }],
        }],
        "policy": {
            "name": "default",
            "action_rules": [
                {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                {"condition": "true", "action": "basic", "priority": 0},
            ],
            "target_rules": [],
            "parameters": {},
        },
    }
}

STAGE_YAML = {
    "stage": {
        "stage_id": "dummy_150",
        "enemies": [{
            "actor_id": "enemy", "name": "假人", "level": 80,
            "hp": 1_000_000_000, "spd": 100, "weakness": ["thunder"],
        }],
        "termination": {"mode": "fixed_av", "max_action_value": 150},
    }
}


class TestCompileEndToEnd:
    def test_template_to_battle_hand_calc(self):
        """模板→编译→执行：134 速两动 × 2025 = 4050（与手写对象路径全等）."""
        compiled = compile_encounter(HERO_YAML, STAGE_YAML)
        engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        state = engine.run()
        hits = [l for l in state.log if "黄泉" in l and "伤害" in l]
        assert len(hits) == 2, f"134 速 150AV 应两动：{hits}"
        assert math.isclose(state.total_damage, 4050.0, rel_tol=1e-6)

    def test_compiled_is_frozen(self):
        """编译产物不可变（纯净不变量前提）."""
        compiled = compile_encounter(HERO_YAML, STAGE_YAML)
        with pytest.raises(Exception):
            compiled.stage.enemies = ()  # type: ignore


class TestSugarDesugar:
    def test_trigger_limit_per_turn(self):
        out = desugar("trigger_limit", {"per_turn": 1}, owner_modifier_id="MOD_X")
        assert out["resource"] == {"resource_id": "_tl_MOD_X", "max": 1.0}
        assert out["reset_hooks"][0]["event"] == "on_turn_start"
        assert out["reset_hooks"][0]["effects"][0]["amount"] == "full"
        assert out["gate_condition"] == "$resource._tl_MOD_X > 0"
        assert out["consume_effect"]["amount"] == 1

    def test_trigger_limit_custom_reset(self):
        out = desugar("trigger_limit", {"count": 2, "reset_on": "cast:ultimate"}, owner_modifier_id="M")
        assert out["resource"]["max"] == 2.0
        assert out["reset_hooks"][0]["event"] == "cast:ultimate"

    def test_unknown_window_rejected(self):
        with pytest.raises(SugarError):
            desugar("trigger_limit", {"per_hour": 1}, owner_modifier_id="M")

    def test_unregistered_sugar_rejected(self):
        with pytest.raises(SugarError):
            desugar("my_custom_sugar", {})

    def test_registry_closed(self):
        assert "trigger_limit" in list_sugars()


class TestCompiledPolicyRuntime:
    def test_ult_rule_fires_when_full(self):
        """action_rule 'energy >= max_energy → ultimate'：满能时选 ultimate."""
        build = {
            "build": {
                "team": [{
                    "character_template": "inline", "actor_id": "h", "name": "h", "level": 80,
                    "base_stats": {"atk": 100, "spd": 300, "max_energy": 100},
                    "actions": [
                        {"action_id": "b", "name": "b", "action_type": "basic", "target_type": "single", "damage_type": "fire", "scaling": [{"atk": 1.0}]},
                        {"action_id": "u", "name": "u", "action_type": "ultimate", "target_type": "single", "damage_type": "fire", "scaling": [{"atk": 3.0}], "energy_cost": 100},
                    ],
                }],
                "policy": {
                    "name": "p",
                    "action_rules": [
                        {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                        {"condition": "true", "action": "basic", "priority": 0},
                    ],
                },
            }
        }
        stage = {"stage": {"stage_id": "s", "enemies": [{"actor_id": "e", "hp": 1e9, "spd": 100, "weakness": ["fire"]}]}}
        compiled = compile_encounter(build, stage)
        engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=1.0)
        state = engine.run()
        assert any("u" in l.split("使用")[1].split("造成")[0] for l in state.log if "使用" in l), f"满能应开大：{state.log[:5]}"


class TestRelicComputation:
    def test_relic_stats_accumulate(self):
        """精确对账：hp=1705.6 / def=851 / spd=105.2.

        head 主 hp(+705.6 flat)、副 def_pct×3(+0.162×500=81)、副 spd×2(+5.2)；
        body 主 def_pct(+0.54×500=270)。百分比按白值乘算。
        """
        from hsr_nous.sim.compile.build_compiler import BuildCompiler
        from hsr_nous.sim_schema.actor import StatBlock
        stats = StatBlock(hp=1000, def_=500)
        BuildCompiler().apply_relics(stats, {
            "head": {"main": "hp", "subs": {"def_pct": 3, "spd": 2}},
            "body": {"main": "def_pct", "subs": {}},
        })
        assert math.isclose(stats.hp, 1705.6, rel_tol=1e-6)
        assert math.isclose(stats.def_, 851.0, rel_tol=1e-6)
        assert math.isclose(stats.spd, 105.2, rel_tol=1e-6)
