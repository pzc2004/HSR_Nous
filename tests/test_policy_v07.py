"""v0.7B PolicyInterpreter 测试：target_rules 接线 + 选择器集合.

数值口径同 v0.7A：atk=2000 crit(0.5,1.0) 期望模式单发倍率 1.0 = 1350（未击破 ×0.9）/ 1500（已击破 ×1.0）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile.compiled import CompiledPolicy, CompiledPolicyRule
from hsr_nous.sim.engine import CombatEngine, CompiledPolicyRuntime
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

_HP = {"e1": 1e9, "e2": 5e8, "e3": 2e9}  # e2 最低，e3 最高


def _attacker():
    return Actor(actor_id="atk", name="攻手", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy(eid):
    return Actor(actor_id=eid, name=f"假人{eid[1]}", actor_type="monster", level=80,
                 stats=StatBlock(hp=_HP[eid], spd=100, max_toughness=9999, weakness=["fire"]))


def _rule(selector, condition=None):
    return CompiledPolicyRule(action="basic", priority=0,
                              condition_expr=condition, selector=selector)


def _engine(target_rules, action=None):
    dummies = [_dummy(f"e{i}") for i in (1, 2, 3)]
    enc = Encounter(encounter_id="t", name="t", actors=[_attacker()] + dummies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70.0))
    eng = CombatEngine(enc, actions_by_actor={"atk": [action or _basic()]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.decision = CompiledPolicyRuntime(CompiledPolicy(
        name="t", action_rules=(), target_rules=tuple(target_rules), parameters={}))
    eng.setup()
    return eng


def _basic():
    return Action(action_id="basic", name="普攻", action_type="basic", target_type="single",
                  damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10)


class TestTargetSelector:
    def test_lowest_hp(self):
        state = _engine([_rule("lowest_hp")]).run()
        assert math.isclose(state.actors["e2"].current_hp, _HP["e2"] - 1350.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"])
        assert math.isclose(state.actors["e3"].current_hp, _HP["e3"])

    def test_dict_max_key(self):
        state = _engine([_rule({"type": "max", "key": "stats.hp"})]).run()
        assert math.isclose(state.actors["e3"].current_hp, _HP["e3"] - 1350.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"])

    def test_broken_selector(self):
        eng = _engine([_rule("broken")])
        eng.state.actors["e1"].broken = True
        state = eng.run()
        # 已击破目标 base_universal=1.0（未击破 0.9）→ 1350/0.9=1500
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"] - 1500.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e2"].current_hp, _HP["e2"])

    def test_no_rule_falls_back_to_first(self):
        """空 target_rules：主目标=第一个存活敌人（默认行为不变）."""
        state = _engine([]).run()
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"] - 1350.0, rel_tol=1e-9)


class TestLowestAtkSelector:
    def test_lowest_atk_picks_weakest(self):
        """lowest_atk 选中攻击最低者（曾是漏网选择器：测试在用但未实现，静默兜底 candidates[0]）."""
        def atk_dummy(eid, atk):
            return Actor(actor_id=eid, name=f"假人{eid[1]}", actor_type="monster", level=80,
                         stats=StatBlock(hp=1e9, atk=atk, spd=100, max_toughness=9999,
                                         weakness=["fire"]))
        enc = Encounter(encounter_id="t", name="t",
                        actors=[_attacker(), atk_dummy("e1", 500), atk_dummy("e2", 100),
                                atk_dummy("e3", 200)],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=70.0))
        eng = CombatEngine(enc, actions_by_actor={"atk": [_basic()]},
                           policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.decision = CompiledPolicyRuntime(CompiledPolicy(
            name="t", action_rules=(), target_rules=(_rule("lowest_atk"),), parameters={}))
        eng.setup()
        state = eng.run()
        assert math.isclose(state.actors["e2"].current_hp, 1e9 - 1350.0, rel_tol=1e-9), \
            "atk 最低者 e2(100) 应被选中"
        assert math.isclose(state.actors["e1"].current_hp, 1e9)
        assert math.isclose(state.actors["e3"].current_hp, 1e9)


class TestPolicySelectorGate:
    """policy 选择器编译期闸（与 hook 选择器同纪律；词表 = effect_types 单一事实源）."""

    def test_unknown_selector_rejected_at_compile(self):
        from hsr_nous.sim.compile.build_compiler import BuildCompiler
        with pytest.raises(ValueError, match="selector 非法值 'lowest_atkk'"):
            BuildCompiler()._compile_policy(
                {"target_rules": [{"condition": "true", "selector": "lowest_atkk"}]})

    def test_unknown_dict_type_rejected_at_compile(self):
        from hsr_nous.sim.compile.build_compiler import BuildCompiler
        with pytest.raises(ValueError, match="selector.type 非法值 'median'"):
            BuildCompiler()._compile_policy(
                {"target_rules": [{"condition": "true", "selector": {"type": "median"}}]})

    def test_legal_selectors_pass_compile(self):
        from hsr_nous.sim.compile.build_compiler import BuildCompiler
        from hsr_nous.sim_schema.effect_types import POLICY_TARGET_SELECTORS
        for sel in sorted(POLICY_TARGET_SELECTORS):
            BuildCompiler()._compile_policy(
                {"target_rules": [{"condition": "true", "selector": sel}]})

    def test_runtime_unknown_selector_raises(self):
        """绕过编译层手写 CompiledPolicy：运行期同口径炸（曾静默兜底 candidates[0] 咬人）."""
        eng = _engine([_rule("lowest_atkk")])
        with pytest.raises(ValueError, match="未知 policy target 选择器 'lowest_atkk'"):
            eng.run()


class TestBlastPrimaryViaPolicy:
    def test_blast_expands_around_picked_primary(self):
        """policy 选中中间目标时，扩散以它为中心向两侧展开."""
        blast = Action(action_id="blast", name="扩散", action_type="basic", target_type="blast",
                       damage_type="fire", scaling=[{"atk": 1.0}],
                       scaling_blast=[{"atk": 0.5}], toughness_dmg=20)
        state = _engine([_rule("lowest_hp")], action=blast).run()
        # 主目标 e2（hp 最低），相邻 e1+e3 各吃副倍率
        assert math.isclose(state.actors["e2"].current_hp, _HP["e2"] - 1350.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e1"].current_hp, _HP["e1"] - 675.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e3"].current_hp, _HP["e3"] - 675.0, rel_tol=1e-9)
        assert math.isclose(state.total_damage, 2700.0, rel_tol=1e-6)


class TestPolicyContextMaxHp:
    """策略上下文 max_hp = effective 口径（与 hook $self.max_hp 同口径；曾读裸面板 stats.hp）."""

    def test_context_max_hp_reads_effective(self):
        from hsr_nous.sim.state import Modifier
        eng = _engine([])
        st = eng.state.actors["atk"]
        assert math.isclose(eng.decision._context(st, eng)["max_hp"], 3000.0)
        eng._apply_modifier(st, Modifier(
            modifier_id="HP_UP", name="生命提升", modifier_type="buff", duration=0,
            stat_effects={"hp_pct": 0.5}))
        ctx = eng.decision._context(st, eng)
        assert math.isclose(ctx["max_hp"], 4500.0, rel_tol=1e-9), \
            "HP%+50% 后策略条件应读到有效上限 4500（裸面板口径会得 3000）"

    def test_action_rule_condition_uses_effective_max_hp(self):
        """行为面：hp < max_hp×0.8 在 HP% buff 下翻转（3000<2400 否 → 3000<3600 是）."""
        from hsr_nous.sim.compile.expr_compiler import ExprCompiler
        from hsr_nous.sim.state import Modifier
        eng = _engine([])
        st = eng.state.actors["atk"]
        cond = ExprCompiler().compile("hp < max_hp * 0.8", layer="effect")
        eng.decision = CompiledPolicyRuntime(CompiledPolicy(
            name="t", parameters={},
            action_rules=(CompiledPolicyRule(action="skill", priority=50, condition_expr=cond),
                          CompiledPolicyRule(action="basic", priority=0)),
            target_rules=()))
        assert eng.decision.select_action_type(st, eng) == "basic"
        eng._apply_modifier(st, Modifier(
            modifier_id="HP_UP", name="生命提升", modifier_type="buff", duration=0,
            stat_effects={"hp_pct": 0.5}))
        assert eng.decision.select_action_type(st, eng) == "skill", \
            "带上限 buff 后同一 HP 值应命中另一分支（条件读到有效上限）"
