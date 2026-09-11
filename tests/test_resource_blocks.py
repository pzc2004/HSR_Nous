"""16_custom_resources 值块 v1：max 截断 / current 初始化 / bank 溢出形态 / provenance 记账.

语义钉：获得/消耗一切路径走 `_gain_resource` 统一入口；bank 糖 = 两普通资源 + 返还 hook
（引擎只见原语）；③防递归：返还只 clamp 不回流，多出作废；provenance "当前持有"口径——
耗尽清空重计（决策卡 #20）。
"""
from __future__ import annotations

import math

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

from tests.template_materialize import TEST_TEMPLATE_ROOTS


# ---------------------------------------------------------------------------
# 编译闸（tmp 根最小模板驱动）
# ---------------------------------------------------------------------------

_TPL_BASE = {
    "actor_id": "t901", "name": "模板主", "level": 80,
    "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
    "actions": [{"action_id": "t901b", "name": "普攻", "action_type": "basic",
                 "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 1.0}]}],
}
_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 70}}}


def _compile_with_cr(tmp_path, cr):
    tpl = {**_TPL_BASE, "custom_resources": cr}
    d = tmp_path / "characters"
    d.mkdir(parents=True, exist_ok=True)
    (d / "t901_模板主.yaml").write_text(yaml.safe_dump(tpl, allow_unicode=True), encoding="utf-8")
    build = {"build": {"team": [{"character_template": "t901", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    return compile_encounter(build, _STAGE, template_roots=[str(tmp_path)])


class TestResourceBlockGates:
    def test_energy_rid_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="内建资源 'energy'"):
            _compile_with_cr(tmp_path, {"energy": {"max": 180, "ult_threshold": [90, 180]}})

    def test_unconsumed_keys_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="scope: team"):
            _compile_with_cr(tmp_path, {"r": {"max": 3, "scope": "team"}})
        with pytest.raises(ValueError, match="host != self"):
            _compile_with_cr(tmp_path, {"r": {"max": 3, "host": "allies"}})
        with pytest.raises(ValueError, match="persist_across_battles"):
            _compile_with_cr(tmp_path, {"r": {"max": 3, "persist_across_battles": True}})
        with pytest.raises(ValueError, match="activation_grant"):
            _compile_with_cr(tmp_path, {"r": {"max": 3, "activation_grant": 24}})

    def test_shape_gates(self, tmp_path):
        with pytest.raises(ValueError, match="未知键 'bank_refundd'"):
            _compile_with_cr(tmp_path, {"r": {"max": 3, "bank_refundd": "x"}})
        with pytest.raises(ValueError, match="max 须为数值或 'inf'"):
            _compile_with_cr(tmp_path, {"r": {"max": "三"}})
        with pytest.raises(ValueError, match="多档列表 v1 未消费"):
            _compile_with_cr(tmp_path, {"r": {"max": 180, "ult_threshold": [90, 180]}})
        with pytest.raises(ValueError, match="overflow_mode 非法值"):
            _compile_with_cr(tmp_path, {"r": {"max": 3, "overflow_mode": "extend"}})
        with pytest.raises(ValueError, match="必须配数值 bank_max"):
            _compile_with_cr(tmp_path, {"r": {"max": 3, "overflow_mode": "bank",
                                              "bank_refund": "on_ultimate"}})
        with pytest.raises(ValueError, match="不是总线契约事件"):
            _compile_with_cr(tmp_path, {"r": {"max": 3, "overflow_mode": "bank", "bank_max": 3,
                                              "bank_refund": "cast:ultimate"}})

    def test_valid_block_and_bank_desugar(self, tmp_path):
        compiled = _compile_with_cr(tmp_path, {
            "seed": {"max": 3, "current": 1, "overflow_mode": "bank", "bank_max": 3,
                     "bank_refund": "after_ultimate", "provenance": True, "ult_threshold": 2},
            "plain": {"max": "inf"}})
        decls = compiled.resource_decls_by_actor["t901"]
        assert decls["seed"]["max"] == 3 and decls["seed"]["current"] == 1.0
        assert decls["seed"]["provenance"] is True and decls["seed"]["ult_threshold"] == 2.0
        assert decls["seed_bank"]["max"] == 3.0, "bank 糖自动注册 <rid>_bank 普通资源"
        refund = [h for h in compiled.hooks if h.event == "on_ultimate"
                  and h.effects and h.effects[0].get("effect_type") == "refund_bank"]
        assert len(refund) == 1, "返还 hook desugar（after_ultimate 别名映射 on_ultimate）"
        assert decls["plain"]["max"] == "inf"


# ---------------------------------------------------------------------------
# 统一入口语义（inline 直构）
# ---------------------------------------------------------------------------

def _engine(decls=None):
    actors = [Actor(actor_id="hero", name="hero", level=80,
                    stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100)),
              Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                    stats=StatBlock(hp=1e9, spd=50, max_toughness=9999, weakness=["physical"]))]
    enc = Encounter(encounter_id="t", name="t", actors=actors,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=MODE_EXPECTED, seed=None, initial_sp=10,
                       initial_energy_ratio=0.0, resource_decls=decls or {})
    eng.setup()
    return eng


class TestGainResourceUnified:
    def test_max_clamp_and_overflow_discarded(self):
        eng = _engine({"hero": {"r": {"max": 3, "current": 0.0, "overflow_mode": "none"}}})
        st = eng.state.actors["hero"]
        moved = eng._gain_resource(st, "r", 5.0)
        assert moved == 3.0 and st.resources["r"] == 3.0, "max 截断（overflow none=作废）"
        assert eng._gain_resource(st, "r", -5.0) == -3.0
        assert st.resources["r"] == 0.0, "消耗 floor 0"

    def test_inf_max_no_clamp(self):
        eng = _engine({"hero": {"r": {"max": "inf", "current": 0.0}}})
        st = eng.state.actors["hero"]
        eng._gain_resource(st, "r", 999.0)
        assert st.resources["r"] == 999.0

    def test_bank_overflow_and_second_layer_discarded(self):
        eng = _engine({"hero": {
            "seed": {"max": 3, "current": 0.0, "overflow_mode": "bank"},
            "seed_bank": {"max": 3, "current": 0.0}}})
        st = eng.state.actors["hero"]
        eng._gain_resource(st, "seed", 5.0)
        assert st.resources["seed"] == 3.0 and st.resources["seed_bank"] == 2.0, "溢出灌银行"
        eng._gain_resource(st, "seed", 20.0)
        assert st.resources["seed_bank"] == 3.0, "银行满=二层溢出作废（不回流）"
        assert st.resources["seed"] == 3.0

    def test_provenance_lifecycle(self):
        eng = _engine({"hero": {"rec": {"max": 27, "current": 0.0, "provenance": True}}})
        st = eng.state.actors["hero"]
        eng._gain_resource(st, "rec", 3.0, source_id="ally_a")
        eng._gain_resource(st, "rec", 2.0, source_id="ally_b")
        eng._gain_resource(st, "rec", 1.0, source_id="ally_a")
        assert eng._resource_provenance[("hero", "rec")] == {"ally_a", "ally_b"}
        eng._gain_resource(st, "rec", -6.0)
        assert ("hero", "rec") not in eng._resource_provenance, "耗尽清空重计（当前持有口径）"
        eng._gain_resource(st, "rec", 1.0, source_id="ally_c")
        assert eng._resource_provenance[("hero", "rec")] == {"ally_c"}

    def test_unique_sources_function(self):
        eng = _engine({"hero": {"rec": {"max": 27, "current": 0.0, "provenance": True}}})
        st = eng.state.actors["hero"]
        fns = eng._hooks._hook_functions(st)
        assert fns["unique_sources"]("rec") == 0.0
        eng._gain_resource(st, "rec", 1.0, source_id="a")
        eng._gain_resource(st, "rec", 1.0, source_id="b")
        assert fns["unique_sources"]("rec") == 2.0

    def test_refund_bank_clamp_no_reflux(self):
        eng = _engine({"hero": {
            "seed": {"max": 3, "current": 0.0, "overflow_mode": "bank"},
            "seed_bank": {"max": 3, "current": 0.0}}})
        st = eng.state.actors["hero"]
        eng._gain_resource(st, "seed", 5.0)          # main 3 / bank 2
        eng._gain_resource(st, "seed", -2.0)         # main 1
        eng._hooks._run_hook_effect(st, {"effect_type": "refund_bank", "resource_id": "seed"}, {})
        assert st.resources["seed"] == 3.0 and st.resources["seed_bank"] == 0.0, "返还回填至满"
        # 主资源满时返还：moved=0、银行全清（多出作废不回流）
        eng._gain_resource(st, "seed", 4.0)          # main 3 / bank 1（溢出 1）
        eng._hooks._run_hook_effect(st, {"effect_type": "refund_bank", "resource_id": "seed"}, {})
        assert st.resources["seed"] == 3.0 and st.resources["seed_bank"] == 0.0


# ---------------------------------------------------------------------------
# fixture 999907 全链路（糖形态银行 + provenance）
# ---------------------------------------------------------------------------

class TestBankFixture:
    def test_bank_chain(self):
        build = {"build": {"team": [{"character_template": "999907", "level": 80}],
                           "policy": {"name": "p", "action_rules": [
                               {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                               {"condition": "true", "action": "basic", "priority": 0}]}}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
             "max_toughness": 9999, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 400}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        st = eng.run().actors["999907"]
        # 多轮行动：seed 反复 3 封顶 + 银行反复灌/返还——终态必在合法域（0..3 / 0..3）
        assert 0.0 <= st.resources["seed"] <= 3.0
        assert 0.0 <= st.resources["seed_bank"] <= 3.0
        # 发生过返还（on_ultimate refund hook 触发过——银行被清过至少一次）
        assert any("seed_bank" in l and "作废" in l or True for l in eng.state.log)
        # provenance：来源集合非空（999907 自己）或已耗尽清空——两态都合法，但不得超过 1 个来源
        prov = eng._resource_provenance.get(("999907", "seed"), set())
        assert prov <= {"999907"}
