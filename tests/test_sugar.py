"""B24 trigger_limit 首糖：desugar 展开 + 编译接线 + 运行期限次/重置.

语义钉：展开 = 计数器四联件（资源注册 + 充满 hooks + 门控并入 condition + 消耗追加），
VM 只见展开产物；初始即满额度（on_battle_start 充满）；消耗复用 gain_resource 负值，
不立 consume_resource 新 effect_type。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.bus import DEFAULT_CONTRACT
from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.compile.sugar import SugarError, desugar
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

from tests.template_materialize import TEST_TEMPLATE_ROOTS


# ---------------------------------------------------------------------------
# desugar 单元
# ---------------------------------------------------------------------------

class TestDesugarTriggerLimit:
    def _ds(self, spec):
        return desugar("trigger_limit", spec, owner_hook_desc="测试 hook",
                       contract=DEFAULT_CONTRACT)

    def test_default_window_and_count(self):
        exp = self._ds({"per_turn": 1})
        assert exp["count"] == 1 and exp["window"] == "per_turn"
        assert exp["gate"].startswith("res__tl_") and exp["gate"].endswith("> 0")
        assert exp["consume_effect"] == {
            "effect_type": "gain_resource", "resource_id": exp["resource_id"], "amount": -1}
        events = [ch["event"] for ch in exp["charge_hooks"]]
        assert events == ["on_battle_start", "on_turn_start"], "开局充满 + 窗口重置点充满"
        for ch in exp["charge_hooks"]:
            assert ch["effects"][0]["effect_type"] == "set_resource"
            assert ch["effects"][0]["amount"] == 1

    def test_window_count_and_reset_on(self):
        exp = self._ds({"per_turn": 3})
        assert exp["count"] == 3
        exp2 = self._ds({"count": 2, "reset_on": "on_ultimate"})
        assert exp2["count"] == 2
        assert [ch["event"] for ch in exp2["charge_hooks"]] == ["on_battle_start", "on_ultimate"]
        exp3 = self._ds({"per_battle": 2})
        assert [ch["event"] for ch in exp3["charge_hooks"]] == ["on_battle_start"], "全场限次不重置"
        exp4 = self._ds({"once_per_battle": True})
        assert exp4["count"] == 1
        assert [ch["event"] for ch in exp4["charge_hooks"]] == ["on_battle_start"]

    def test_errors_are_loud(self):
        with pytest.raises(SugarError, match="未知窗口档"):
            self._ds({"per_minute": 1})
        with pytest.raises(SugarError, match="v1 未收"):
            self._ds({"per_attack": 1})
        with pytest.raises(SugarError, match="不是总线契约事件"):
            self._ds({"reset_on": "cast:ultimate"})
        with pytest.raises(SugarError, match="须 ≥1"):
            self._ds({"per_turn": 1, "count": 0})
        with pytest.raises(SugarError, match="须为非空 dict"):
            self._ds({})


# ---------------------------------------------------------------------------
# 编译接线
# ---------------------------------------------------------------------------

class TestTriggerLimitCompile:
    def test_expansion_wired(self):
        out: list = []
        resources: dict = {}
        BuildCompiler()._compile_hooks([{
            "event": "after_being_hit",
            "condition": "$event.amount > 100",
            "trigger_limit": {"per_turn": 1},
            "effects": [{"effect_type": "gain_skill_point", "amount": 1}],
        }], "模板 X", "t900", out, resources_out=resources)
        assert len(resources["t900"]) == 1, "计数资源注册进 owner 资源表"
        rid, decl = next(iter(resources["t900"].items()))
        assert decl["max"] == 1.0, "计数资源 decl 的 max=额度（统一入口白拿 clamp 语义）"
        owner = next(h for h in out if h.event == "after_being_hit")
        # 门控并入原条件（AND 语义；表达式预编译过闸）
        assert owner.condition_expr is not None
        # 消耗追加到 effects 末尾（gain_resource 负值）
        assert owner.effects[-1]["effect_type"] == "gain_resource"
        assert owner.effects[-1]["amount"] == -1 and owner.effects[-1]["resource_id"] == rid
        # 充满 hooks（开局 + 重置点）
        charges = [h for h in out if h.event in ("on_battle_start", "on_turn_start")]
        assert len(charges) == 2 and all(
            h.effects[0]["effect_type"] == "set_resource" for h in charges)

    def test_gate_without_condition(self):
        out: list = []
        BuildCompiler()._compile_hooks([{
            "event": "after_being_hit", "trigger_limit": {"per_wave": 1},
            "effects": [{"effect_type": "gain_skill_point", "amount": 1}],
        }], "模板 X", "t900", out, resources_out={})
        owner = next(h for h in out if h.event == "after_being_hit")
        assert owner.condition_expr is not None, "无条件时门控独立成 condition"
        assert any(h.event == "on_wave_start" for h in out), "per_wave 重置点=on_wave_start"

    def test_on_battle_start_rejected(self):
        with pytest.raises(ValueError, match="v1 不收"):
            BuildCompiler()._compile_hooks([{
                "event": "on_battle_start", "trigger_limit": {"per_turn": 1},
                "effects": [{"effect_type": "gain_skill_point", "amount": 1}],
            }], "模板 X", "t900", [], resources_out={})

    def test_no_resources_channel_rejected(self):
        with pytest.raises(ValueError, match="v1 仅角色模板/星魂"):
            BuildCompiler()._compile_hooks([{
                "event": "after_being_hit", "trigger_limit": {"per_turn": 1},
                "effects": [{"effect_type": "gain_skill_point", "amount": 1}],
            }], "模板 X", "t900", [])          # resources_out 缺省=None → 指路炸

    def test_other_sugar_keys_still_named_rejected(self):
        with pytest.raises(ValueError, match="糖键 'every_n'"):
            BuildCompiler()._compile_hooks([{
                "event": "after_being_hit", "every_n": {"n": 3},
                "effects": [{"effect_type": "gain_skill_point", "amount": 1}],
            }], "模板 X", "t900", [], resources_out={})


# ---------------------------------------------------------------------------
# 运行期：fixture 999906 限次/重置
# ---------------------------------------------------------------------------

class TestTriggerLimitRuntime:
    def _engine(self):
        build = {"build": {"team": [{"character_template": "999906", "level": 80}],
                           "policy": {"name": "p", "action_rules": [
                               {"condition": "true", "action": "basic", "priority": 0}]}}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
             "max_toughness": 9999, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 70}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        return eng

    def _hit(self, eng):
        eng.bus.emit("after_being_hit", {
            "amount": 100.0, "absorbed": 100.0, "damage_type": "physical",
            "source": "e1", "target": "999906", "is_critical": False,
            "seg_index": 0, "actor_type": "monster", "action_type": "basic",
            "hit_targets": ["999906"]}, eng.state)

    def test_once_per_turn_then_reset(self):
        eng = self._engine()
        sp0 = eng.state.skill_points
        for _ in range(3):
            self._hit(eng)
        assert eng.state.skill_points == sp0 + 1, "每回合限 1 次（3 次受击只回 1 点）"
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)   # 重置点充满
        self._hit(eng)
        assert eng.state.skill_points == sp0 + 2, "回合开始重置后可再触发"
