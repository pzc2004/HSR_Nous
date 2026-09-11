"""B31 通用目标选择代数：pool → where → order_by → take → mode 一台求值器.

验证三层：存量选择器⇔代数等价（模板零改动的硬承诺）；代数直写（dict 全槽）；
random 的 zagreus/expected 双口径（roll 抽 N、expected 按序取前 N 不掷骰）。
"""
from __future__ import annotations

import random as _random

import pytest

from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _mk_engine(mode=MODE_EXPECTED, seed=None):
    hero = Actor(actor_id="hero", name="hero", level=80,
                 stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100))
    allies = [Actor(actor_id=f"a{i}", name=f"队友{i}", level=80,
                    stats=StatBlock(atk=500 * i, spd=100, hp=1000 * i, max_energy=100))
              for i in (1, 2)]
    enemies = [Actor(actor_id=f"e{i}", name=f"敌{i}", actor_type="monster", level=80,
                     stats=StatBlock(atk=100 * i, spd=100, hp=2000 * i, max_toughness=100,
                                     weakness=["fire"]))
               for i in (1, 2, 3)]
    enc = Encounter(encounter_id="t", name="t", actors=[hero] + allies + enemies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=mode, seed=seed, initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestHookSelectorEquivalence:
    """存量 hook 字符串选择器 ⇔ 目标代数：结果必须逐项一致（脱糖别名的等价电池）."""

    def test_self_and_allies(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        rt = eng._hooks._hook_target_states
        assert [s.actor.actor_id for s in rt("self", hero, {})] == ["hero"]
        assert [s.actor.actor_id for s in rt("all_allies", hero, {})] == ["hero", "a1", "a2"]
        assert [s.actor.actor_id for s in rt("other_allies", hero, {})] == ["a1", "a2"]
        assert [s.actor.actor_id for s in rt("all_enemies", hero, {})] == ["e1", "e2", "e3"]

    def test_enemy_first_and_highest_hp(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        rt = eng._hooks._hook_target_states
        assert rt("enemy_first", hero, {})[0].actor.actor_id == "e1"
        assert rt("highest_hp", hero, {})[0].actor.actor_id == "e3", "e3 hp 最大（2000×3）"

    def test_highest_hp_hit_pool(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        picked = eng._hooks._hook_target_states(
            "highest_hp_hit", hero, {"hit_targets": ["e1", "e3"]})[0]
        assert picked.actor.actor_id == "e3"


class TestHookAlgebraDirect:
    def test_where_order_take(self):
        """代数直写：where $it 过滤 + order_by 降序 + take 2."""
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        picked = eng._hooks._hook_target_states(
            {"pool": "enemies", "where": "$it.hp > 2000", "order_by": "$it.hp", "take": 2},
            hero, {})
        assert [s.actor.actor_id for s in picked] == ["e2", "e3"], "过滤 e1 后按 hp 升序取前 2"

    def test_take_int_random_targets(self):
        """实例垫底（敌方 "Deals … to 3 random targets"）：take 3 + mode random——
        roll 同 seed 复现；expected 按序取前 N 不掷骰（B22 确定化口径）."""
        spec = {"pool": "enemies", "take": 3, "mode": "random"}
        eng_r1 = _mk_engine(mode=MODE_ROLL, seed=42)
        eng_r2 = _mk_engine(mode=MODE_ROLL, seed=42)
        h1 = eng_r1.state.actors["hero"]
        h2 = eng_r2.state.actors["hero"]
        p1 = [s.actor.actor_id for s in eng_r1._hooks._hook_target_states(spec, h1, {})]
        p2 = [s.actor.actor_id for s in eng_r2._hooks._hook_target_states(spec, h2, {})]
        assert p1 == p2 and len(p1) == 3, "roll 同 seed 抽样逐项复现"
        eng_e = _mk_engine()
        he = eng_e.state.actors["hero"]
        pe = [s.actor.actor_id for s in eng_e._hooks._hook_target_states(spec, he, {})]
        assert pe == ["e1", "e2", "e3"], "expected 确定化：按序取前 N（不掷骰）"

    def test_where_has_modifier_named(self):
        """实例垫底（按修饰符点名，1224 师父族）：where: has_modifier($it, 'M')."""
        eng = _mk_engine()
        eng._apply_modifier(eng.state.actors["e2"], Modifier(
            modifier_id="MARK", name="标记", modifier_type="debuff", duration=2))
        hero = eng.state.actors["hero"]
        picked = eng._hooks._hook_target_states(
            {"pool": "enemies", "where": "has_modifier($it, 'MARK')", "take": 1}, hero, {})
        assert [s.actor.actor_id for s in picked] == ["e2"]

    def test_order_by_shield_lowest(self):
        """$it.shield（当前护盾值=栈剩余合计——峥嵘"护盾值最低的我方目标"族，2026-09-08）：
        order_by 升序 + take 1 取最低；无盾=0 参与排序."""
        from hsr_nous.sim.state import ShieldInstance
        eng = _mk_engine()
        a1, a2 = eng.state.actors["a1"], eng.state.actors["a2"]
        a1.shields.append(ShieldInstance(
            shield_id="S1", name="盾1", remaining=500.0, source_id="hero"))
        a2.shields.append(ShieldInstance(
            shield_id="S2", name="盾2", remaining=100.0, source_id="hero"))
        a2.shields.append(ShieldInstance(
            shield_id="S3", name="盾3", remaining=50.0, source_id="hero"))
        hero = eng.state.actors["hero"]
        picked = eng._hooks._hook_target_states(
            {"pool": "allies", "order_by": "$it.shield", "take": 1}, hero, {})
        assert picked[0].actor.actor_id == "hero", "hero 无盾=0 最低"
        picked = eng._hooks._hook_target_states(
            {"pool": "allies", "where": "$it.shield > 0", "order_by": "$it.shield", "take": 2},
            hero, {})
        assert [s.actor.actor_id for s in picked] == ["a2", "a1"], (
            "有盾者按剩余合计升序（a2=150 < a1=500）")


class TestPolicyAlgebra:
    def _rt(self, eng):
        from hsr_nous.sim.policy_api import CompiledPolicyRuntime
        return eng.decision._apply_selector if isinstance(
            eng.decision, CompiledPolicyRuntime) else None

    def test_string_alias_equivalence(self):
        from hsr_nous.sim.policy_api import CompiledPolicyRuntime
        from hsr_nous.sim.compile.compiled import CompiledPolicy
        eng = _mk_engine()
        rt = CompiledPolicyRuntime(CompiledPolicy(
            name="p", action_rules=(), target_rules=(), parameters={}))
        cands = [eng.state.actors[f"e{i}"] for i in (1, 2, 3)]
        hero = eng.state.actors["hero"]
        assert rt._apply_selector("highest_hp", cands, hero, {}, eng).actor.actor_id == "e3"
        assert rt._apply_selector("lowest_hp_pct", cands, hero, {}, eng).actor.actor_id == "e1"
        assert rt._apply_selector("highest_atk", cands, hero, {}, eng).actor.actor_id == "e3"

    def test_legacy_dict_forms(self):
        from hsr_nous.sim.policy_api import CompiledPolicyRuntime
        from hsr_nous.sim.compile.compiled import CompiledPolicy
        eng = _mk_engine()
        rt = CompiledPolicyRuntime(CompiledPolicy(
            name="p", action_rules=(), target_rules=(), parameters={}))
        cands = [eng.state.actors[f"e{i}"] for i in (1, 2, 3)]
        cands[0].current_hp = 1000.0   # e1 残血（区分 hp_pct 档，防全员满血并列）
        cands[1].current_hp = 2500.0   # e2 半血+（>2000 档用）
        hero = eng.state.actors["hero"]
        assert rt._apply_selector({"type": "max", "key": "hp_pct"}, cands, hero, {}, eng).actor.actor_id == "e3"
        eng._apply_modifier(cands[0], Modifier(
            modifier_id="M2", name="标", modifier_type="debuff", duration=1))
        assert rt._apply_selector({"type": "has_modifier", "modifier_id": "M2"},
                                  cands, hero, {}, eng).actor.actor_id == "e1"
        assert rt._apply_selector({"type": "first", "condition": "target_hp > 2000"},
                                  cands, hero, {}, eng).actor.actor_id == "e2"

    def test_algebra_direct(self):
        from hsr_nous.sim.policy_api import CompiledPolicyRuntime
        from hsr_nous.sim.compile.compiled import CompiledPolicy
        eng = _mk_engine()
        rt = CompiledPolicyRuntime(CompiledPolicy(
            name="p", action_rules=(), target_rules=(), parameters={}))
        cands = [eng.state.actors[f"e{i}"] for i in (1, 2, 3)]
        hero = eng.state.actors["hero"]
        picked = rt._apply_selector({"order_by": "-$it.hp", "take": 1},
                                    cands, hero, {}, eng)
        assert picked.actor.actor_id == "e3"


class TestAlgebraCompileGates:
    def test_hook_dict_gates(self):
        bc = BuildCompiler()
        bad_pool = [{"effect_type": "deal_damage", "scaling_atk": 1.0,
                     "target": {"pool": "galaxy"}}]
        with pytest.raises(ValueError, match="非法 pool"):
            bc._validate_effects(bad_pool, "模板 X")
        with pytest.raises(ValueError, match="take 非法值"):
            bc._validate_effects([{"effect_type": "deal_damage", "scaling_atk": 1.0,
                                   "target": {"take": 0}}], "模板 X")
        with pytest.raises(ValueError, match="非法 mode"):
            bc._validate_effects([{"effect_type": "deal_damage", "scaling_atk": 1.0,
                                   "target": {"mode": "chaos"}}], "模板 X")
        with pytest.raises(ValueError, match="未知键"):
            bc._validate_effects([{"effect_type": "deal_damage", "scaling_atk": 1.0,
                                   "target": {"pool": "enemies", "pooll": "x"}}], "模板 X")
        with pytest.raises(Exception):
            bc._validate_effects([{"effect_type": "deal_damage", "scaling_atk": 1.0,
                                   "target": {"where": "$it =!=> 1"}}], "模板 X")

    def test_hook_dict_valid_compiles(self):
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0,
            "target": {"pool": "enemies", "where": "$it.broken",
                       "order_by": "-$it.hp", "take": 2, "mode": "random"}}], "模板 X")

    def test_policy_dict_pool_rejected(self):
        with pytest.raises(ValueError, match="不允许 pool 键"):
            BuildCompiler()._compile_policy({
                "target_rules": [{"condition": "true",
                                  "selector": {"pool": "enemies", "take": 1}, "priority": 0}]})

    def test_policy_algebra_compiles(self):
        p = BuildCompiler()._compile_policy({
            "target_rules": [{"condition": "true",
                              "selector": {"order_by": "-$it.hp", "take": 1}, "priority": 0}]})
        assert p.target_rules
