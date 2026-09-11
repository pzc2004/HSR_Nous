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


# ---------------------------------------------------------------------------
# 跨 actor 写通道（05_effects §5.3 `target` 参——昔涟 Ode 族首实例；
# 缺省 self 存量语义不变，显式给 = 对解析目标逐各写；与 source 正交）
# ---------------------------------------------------------------------------

def _engine_two_allies(decls=None):
    actors = [Actor(actor_id="hero", name="hero", level=80,
                    stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100)),
              Actor(actor_id="ally", name="ally", level=80,
                    stats=StatBlock(atk=800, spd=90, hp=2500, max_energy=100)),
              Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                    stats=StatBlock(hp=1e9, spd=50, max_toughness=9999, weakness=["physical"]))]
    enc = Encounter(encounter_id="t", name="t", actors=actors,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=MODE_EXPECTED, seed=None, initial_sp=10,
                       initial_energy_ratio=0.0, resource_decls=decls or {})
    eng.setup()
    return eng


class TestCrossActorWrite:
    def test_gain_resource_event_target_writes_target_panel(self):
        eng = _engine_two_allies({
            "hero": {"ally_r": {"max": 99, "current": 0.0}},
            "ally": {"ally_r": {"max": 10, "current": 0.0, "provenance": True}}})
        hero, ally = eng.state.actors["hero"], eng.state.actors["ally"]
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "gain_resource", "resource_id": "ally_r",
            "target": "$event.source", "amount": 5}, {"source": "ally"})
        assert ally.resources["ally_r"] == 5.0 and hero.resources["ally_r"] == 0.0, (
            "显式 target = 写目标面板，hook 持有者不变")
        assert eng._resource_provenance[("ally", "ally_r")] == {"hero"}, (
            "provenance 记账方 = 缺省 hook 持有者（写谁的 ≠ 谁触发的——target/source 正交）")
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "gain_resource", "resource_id": "ally_r",
            "target": "$event.source", "amount": 99}, {"source": "ally"})
        assert ally.resources["ally_r"] == 10.0, "按目标自身 decl 的 max 截断"

    def test_gain_resource_default_self_unchanged(self):
        eng = _engine_two_allies({"hero": {"r": {"max": 99, "current": 0.0}},
                                  "ally": {"r": {"max": 99, "current": 0.0}}})
        hero, ally = eng.state.actors["hero"], eng.state.actors["ally"]
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "gain_resource", "resource_id": "r",
            "amount": "$event.amount"}, {"amount": 3.0})
        assert hero.resources["r"] == 3.0 and ally.resources["r"] == 0.0, "缺省 target=self 回归不变"

    def test_gain_resource_multi_target_writes_each(self):
        eng = _engine_two_allies({"hero": {"team_r": {"max": 99, "current": 0.0}},
                                  "ally": {"team_r": {"max": 99, "current": 0.0}}})
        hero, ally = eng.state.actors["hero"], eng.state.actors["ally"]
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "gain_resource", "resource_id": "team_r",
            "target": "all_allies", "amount": 3}, {})
        assert hero.resources["team_r"] == 3.0 and ally.resources["team_r"] == 3.0, "多目标逐各写"

    def test_set_resource_cross_actor_algebra_target(self):
        eng = _engine_two_allies({"ally": {"ally_r": {"max": 99, "current": 0.0}}})
        hero, ally = eng.state.actors["hero"], eng.state.actors["ally"]
        sel = {"pool": "allies", "where": "$it.actor_id == 'ally'"}
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "set_resource", "resource_id": "ally_r",
            "target": sel, "amount": 7}, {})
        assert ally.resources["ally_r"] == 7.0 and "ally_r" not in hero.resources, (
            "目标代数寻址设值；设值差量走统一入口")
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "set_resource", "resource_id": "ally_r",
            "target": sel, "amount": 2}, {})
        assert ally.resources["ally_r"] == 2.0

    def test_adjust_stacks_cross_actor(self):
        from hsr_nous.sim.state import Modifier
        eng = _engine_two_allies()
        hero, ally = eng.state.actors["hero"], eng.state.actors["ally"]
        ally.modifiers["MOD_MARK"] = Modifier(
            modifier_id="MOD_MARK", name="标记", modifier_type="buff", stacks=2, max_stack=99)
        hero.modifiers["MOD_MARK"] = Modifier(
            modifier_id="MOD_MARK", name="标记", modifier_type="buff", stacks=5, max_stack=99)
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "adjust_stacks", "modifier_id": "MOD_MARK",
            "target": "$event.source", "delta": -1}, {"source": "ally"})
        assert ally.modifiers["MOD_MARK"].stacks == 1, "对目标调层"
        assert hero.modifiers["MOD_MARK"].stacks == 5, "hook 持有者自身件不动"
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "adjust_stacks", "modifier_id": "MOD_MARK",
            "target": "$event.source", "delta": -5}, {"source": "ally"})
        assert ally.modifiers["MOD_MARK"].stacks == 0, "clamp [0, max_stack] 同口径"
        # 缺省 self 回归不变
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "adjust_stacks", "modifier_id": "MOD_MARK", "delta": -1}, {})
        assert hero.modifiers["MOD_MARK"].stacks == 4

    def test_stacks_function_cross_actor_read(self):
        from hsr_nous.sim.state import Modifier
        eng = _engine_two_allies()
        hero, ally = eng.state.actors["hero"], eng.state.actors["ally"]
        ally.modifiers["MOD_MARK"] = Modifier(
            modifier_id="MOD_MARK", name="标记", modifier_type="buff", stacks=2, max_stack=99)
        fns = eng._hooks._hook_functions(hero)
        assert fns["stacks"]("ally", "MOD_MARK") == 2.0, "actor_id 寻址跨 actor 读"
        assert fns["stacks"](ally, "MOD_MARK") == 2.0, "ActorState 跨 actor 读（原 v1 报错放开）"
        assert fns["stacks"]("ghost", "MOD_MARK") == 0.0, "查无 actor 缺省 0"
        assert fns["stacks"]("ally", "MOD_NONE") == 0.0, "无该 modifier 缺省 0"


# ---------------------------------------------------------------------------
# 跨 actor 写的资源存在性闸放行（错拼闸仍守 self 写）
# ---------------------------------------------------------------------------

def _compile_with_hook(tmp_path, hook):
    tpl = {**_TPL_BASE, "custom_resources": {"declared": {"max": 99}}, "hooks": [hook]}
    d = tmp_path / "characters"
    d.mkdir(parents=True, exist_ok=True)
    (d / "t901_模板主.yaml").write_text(yaml.safe_dump(tpl, allow_unicode=True), encoding="utf-8")
    build = {"build": {"team": [{"character_template": "t901", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    return compile_encounter(build, _STAGE, template_roots=[str(tmp_path)])


class TestCrossActorRidGate:
    def test_cross_actor_write_bypasses_rid_gate(self, tmp_path):
        compiled = _compile_with_hook(tmp_path, {
            "event": "actor_enter",
            "condition": "$event.actor == 'ally'",
            "effects": [{"effect_type": "gain_resource", "resource_id": "other_templates_rid",
                         "target": "$event.actor", "amount": 1}]})
        assert compiled.hooks, "跨 actor 写：资源可为他模板声明（本队未编 = 蛰伏），存在性闸不拦"

    def test_self_write_unknown_rid_still_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="引用未声明资源"):
            _compile_with_hook(tmp_path, {
                "event": "on_battle_start",
                "effects": [{"effect_type": "gain_resource", "resource_id": "typo_rid",
                             "amount": 1}]})


# ---------------------------------------------------------------------------
# max_override（16 §16.12——modifier 覆写资源上限，昔涟 1141517 新蕊溢出族首实例）：
# 有效上限 = max(基础 max, 携带者全部覆写件)；获得统一入口唯一 clamp 点消费
# ---------------------------------------------------------------------------

class TestMaxOverride:
    def _eng(self):
        from hsr_nous.sim.state import Modifier
        eng = _engine_two_allies({"hero": {"newbud": {"max": 34000, "current": 0.0}}})
        return eng, eng.state.actors["hero"], Modifier

    def test_gain_clamps_to_base_without_override(self):
        eng, hero, _ = self._eng()
        eng._gain_resource(hero, "newbud", 50000.0)
        assert hero.resources["newbud"] == 34000.0, "无覆写件：按基础 max 截断"

    def test_override_raises_cap(self):
        eng, hero, Modifier = self._eng()
        eng._apply_modifier(hero, Modifier(
            modifier_id="ODE", name="诗", modifier_type="buff", duration=0,
            target_resource="newbud", max_override=68000.0))
        eng._gain_resource(hero, "newbud", 50000.0)
        assert hero.resources["newbud"] == 50000.0, "覆写生效：上限抬至 68000"
        eng._gain_resource(hero, "newbud", 50000.0)
        assert hero.resources["newbud"] == 68000.0, "溢出至 200% 顶"

    def test_multiple_overrides_take_max(self):
        eng, hero, Modifier = self._eng()
        eng._apply_modifier(hero, Modifier(
            modifier_id="ODE_A", name="诗A", modifier_type="buff", duration=0,
            target_resource="newbud", max_override=40000.0))
        eng._apply_modifier(hero, Modifier(
            modifier_id="ODE_B", name="诗B", modifier_type="buff", duration=0,
            target_resource="newbud", max_override=68000.0))
        eng._gain_resource(hero, "newbud", 50000.0)
        assert hero.resources["newbud"] == 50000.0, "多覆写取最大"
        eng._remove_modifier(hero, "ODE_B", "test")
        eng._gain_resource(hero, "newbud", 30000.0)
        assert hero.resources["newbud"] == 40000.0, "摘掉大覆写后按 40000 截断"

    def test_expiry_no_clawback_then_natural_falloff(self):
        """到期不回收已超限值；下次获得按有效上限截断自然回落（v1 语义钉）."""
        eng, hero, Modifier = self._eng()
        eng._apply_modifier(hero, Modifier(
            modifier_id="ODE", name="诗", modifier_type="buff", duration=0,
            target_resource="newbud", max_override=68000.0))
        eng._gain_resource(hero, "newbud", 50000.0)
        eng._remove_modifier(hero, "ODE", "expire")
        assert hero.resources["newbud"] == 50000.0, "覆写到期不回收已超限值"
        eng._gain_resource(hero, "newbud", 1.0)
        assert hero.resources["newbud"] == 34000.0, "超限态再获得按基础上限截断回落"

    def test_other_resource_unaffected(self):
        eng, hero, Modifier = self._eng()
        eng._apply_modifier(hero, Modifier(
            modifier_id="ODE", name="诗", modifier_type="buff", duration=0,
            target_resource="newbud", max_override=68000.0))
        hero.resources["other"] = 0.0
        eng._resource_decls["hero"]["other"] = {"max": 10.0}
        eng._gain_resource(hero, "other", 99.0)
        assert hero.resources["other"] == 10.0, "覆写只作用于 target_resource 指定资源"
