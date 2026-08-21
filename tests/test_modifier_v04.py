"""v0.4 modifier 完整版测试：两层求值 / 生命周期 / 驱散净化 / 效果命中 / scoped 加成."""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile.expr_compiler import ExprCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL, SettlementPipeline
from hsr_nous.sim.state import ActorState, Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _hero(atk=2000, hp=2000, **kw):
    return Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=atk, hp=hp, spd=200, crit_rate=0.5, crit_dmg=1.0,
                                 max_energy=100, **kw))


def _enemy(**kw):
    base = dict(hp=1e9, spd=100, max_toughness=120.0, weakness=["fire"])
    base.update(kw)
    return Actor(actor_id="e1", name="精英", actor_type="monster", level=80,
                 stats=StatBlock(**base))


def _basic(element="fire"):
    return Action(action_id="a1", name="普攻", action_type="basic", target_type="single",
                  damage_type=element, scaling=[{"atk": 1.0}], toughness_dmg=10)


def _engine(hero, enemies, actions, mode=MODE_EXPECTED, seed=None, av=500):
    enc = Encounter(encounter_id="t", name="t", actors=[hero] + enemies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    return CombatEngine(enc, actions_by_actor=actions, mode=mode, seed=seed,
                        initial_sp=10, initial_energy_ratio=0.0)


class TestTwoLayerEval:
    def test_flat_atk_buff_scales_damage(self):
        """flat 攻击 buff +1000：1350 → 2025（3000×0.5×0.9×1.5）."""
        hero = _hero()
        eng = _engine(hero, [_enemy()], {"hero": [_basic()]}, av=50); eng.setup()
        hero_state = eng.state.actors.get("hero") or eng.state.actors["hero"]
        eng._apply_modifier(hero_state, Modifier(
            modifier_id="ATK_UP", name="攻击提升", modifier_type="buff", duration=3,
            stat_effects={"atk": 1000.0}))
        state = eng.run()
        assert math.isclose(state.total_damage, 2025.0, rel_tol=1e-6)

    def test_conversion_reads_layer1(self):
        """转化 atk += hp×10%（hp=2000 → +200）：(2000+200)×0.5×0.9×1.5 = 1485."""
        hero = _hero()
        eng = _engine(hero, [_enemy()], {"hero": [_basic()]}, av=50); eng.setup()
        eng._apply_modifier(eng.state.actors["hero"], Modifier(
            modifier_id="HP2ATK", name="生命转攻击", modifier_type="buff", duration=0,
            scaling_effects={"atk": ("hp", 0.1)}))
        state = eng.run()
        assert math.isclose(state.total_damage, 1485.0, rel_tol=1e-6)

    def test_pct_atk_base_only_flat_excluded(self):
        """pct 族基数=白值：atk_pct 0.5 + flat 500 → atk=2000×1.5+500=3500 → 2362.5.

        错误口径（pct 乘 flat）会得 (2500×1.5)=3750 → 2531.25——本断言可区分.
        """
        hero = _hero()
        eng = _engine(hero, [_enemy()], {"hero": [_basic()]}, av=50); eng.setup()
        eng._apply_modifier(eng.state.actors["hero"], Modifier(
            modifier_id="PCT", name="攻击百分比", modifier_type="buff", duration=0,
            stat_effects={"atk_pct": 0.5}))
        eng._apply_modifier(eng.state.actors["hero"], Modifier(
            modifier_id="FLAT", name="攻击固定", modifier_type="buff", duration=0,
            stat_effects={"atk": 500.0}))
        state = eng.run()
        assert math.isclose(state.total_damage, 2362.5, rel_tol=1e-6)

    def test_override_def_zero(self):
        """覆写 def_=0 于敌：def_multi = 1000/(0+1000) = 1.0 → 2000×0.5×1.0×0.9×1.5×1.0... 
        即 1350/0.5 = 2700."""
        hero = _hero()
        enemy = _enemy(def_=1000)
        eng = _engine(hero, [enemy], {"hero": [_basic()]}, av=50); eng.setup()
        eng._apply_modifier(eng.state.actors["e1"], Modifier(
            modifier_id="DEF0", name="防御归零", modifier_type="debuff", duration=0,
            override_effects={"def_": 0.0}))
        state = eng.run()
        assert math.isclose(state.total_damage, 2700.0, rel_tol=1e-6)


class TestStackMode:
    def _fresh_setup(self):
        eng = _engine(_hero(), [_enemy()], {"hero": [_basic()]})
        eng.setup()
        return eng

    def test_refresh_stacks_and_cap(self):
        eng = self._fresh_setup()
        st = eng.state.actors["hero"]
        for _ in range(3):
            eng._apply_modifier(st, Modifier(modifier_id="S", name="叠层", modifier_type="buff",
                                             duration=2, stacks=1, max_stack=2))
        assert st.modifiers["S"].stacks == 2  # 上限封顶

    def test_replace_swaps(self):
        eng = self._fresh_setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(modifier_id="S", name="旧", modifier_type="buff",
                                         duration=1, stacks=5))
        eng._apply_modifier(st, Modifier(modifier_id="S", name="新", modifier_type="buff",
                                         duration=1, stacks=1, stack_mode="replace"))
        assert st.modifiers["S"].stacks == 1 and st.modifiers["S"].name == "新"

    def test_set_stacks(self):
        eng = self._fresh_setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(modifier_id="S", name="叠层", modifier_type="buff",
                                         duration=1, stacks=1))
        eng._apply_modifier(st, Modifier(modifier_id="S", name="叠层", modifier_type="buff",
                                         duration=1, stack_mode="set", stacks_value=7))
        assert st.modifiers["S"].stacks == 7

    def test_singleton_group_swaps(self):
        eng = self._fresh_setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(modifier_id="A", name="旧植入", modifier_type="debuff",
                                         duration=2, singleton_group="implant"))
        eng._apply_modifier(st, Modifier(modifier_id="B", name="新植入", modifier_type="debuff",
                                         duration=2, singleton_group="implant"))
        assert "A" not in st.modifiers and "B" in st.modifiers


class TestDispelPurify:
    def test_purify_removes_dispellable_debuff(self):
        eng = _engine(_hero(), [_enemy()], {"hero": [_basic()]})
        eng.setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(modifier_id="D1", name="可解负面", modifier_type="debuff", duration=2))
        eng._apply_modifier(st, Modifier(modifier_id="D2", name="不可解负面", modifier_type="debuff",
                                         duration=2, dispellable=False))
        removed = eng.purify(st, max_count=5)
        assert removed == 1 and "D2" in st.modifiers

    def test_dispel_removes_enemy_buff(self):
        eng = _engine(_hero(), [_enemy()], {"hero": [_basic()]})
        eng.setup()
        st = eng.state.actors["e1"]
        eng._apply_modifier(st, Modifier(modifier_id="B1", name="敌方增益", modifier_type="buff", duration=2))
        assert eng.dispel(st, max_count=1) == 1
        assert "B1" not in st.modifiers


class TestHitChance:
    def test_expected_applies_above_half(self):
        """期望模式：命中率 ≥0.5 生效，<0.5 抵抗."""
        hero = _hero(effect_hit=1.0)  # +100% 命中
        eng = _engine(hero, [_enemy()], {"hero": [_basic()]}, mode=MODE_EXPECTED)
        eng.setup()
        st = eng.state.actors["e1"]
        applied = eng._apply_modifier(st, Modifier(
            modifier_id="D", name="负面", modifier_type="debuff", duration=1, source_id="hero"),
            apply_chance=0.4)  # 0.4×(1+1.0)=0.8 ≥0.5 → 生效
        assert applied
        st2 = eng.state.actors["e1"]
        applied2 = eng._apply_modifier(st2, Modifier(
            modifier_id="D2", name="负面2", modifier_type="debuff", duration=1, source_id="hero"),
            apply_chance=0.1)  # 0.1×2.0=0.2 <0.5 → 抵抗
        assert not applied2 and "D2" not in st2.modifiers


class TestScopedBoost:
    def test_hit_condition_scoped_dmg(self):
        """scoped：'action_type == skill' 的增伤只加成战技，不加成普攻."""
        hero = _hero(atk=2000)
        skill = Action(action_id="s1", name="战技", action_type="skill", target_type="single",
                       damage_type="fire", scaling=[{"atk": 1.0}], skill_point_cost=1)
        expr = ExprCompiler().compile("action_type == 'skill'")
        from hsr_nous.sim.policy_api import ScriptedPolicy
        enc = Encounter(encounter_id="t", name="t", actors=[hero, _enemy()],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=100))
        eng = CombatEngine(enc, actions_by_actor={"hero": [_basic(), skill]},
                           policy=ScriptedPolicy(rotation=["basic", "skill"]),
                           mode=MODE_EXPECTED, initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        from hsr_nous.sim.compile.expr_compiler import ExprCompiler as EC
        eng.pipeline._expr = EC()
        eng._apply_modifier(eng.state.actors["hero"], Modifier(
            modifier_id="SCOPED", name="战技强化", modifier_type="buff", duration=0,
            stat_effects={"all_dmg": 0.5}, hit_condition_expr=expr))
        state = eng.run()
        # basic@50 无 scoped → 1350；skill@100 有 scoped(+0.5) → 2000×1.5×0.5×0.9×1.5=2025
        assert math.isclose(state.total_damage, 1350.0 + 2025.0, rel_tol=1e-6), (
            f"普攻应 1350、战技应 2025：总伤 {state.total_damage}"
        )


class TestPurityV04:
    @pytest.mark.parametrize("mode,seed", [(MODE_EXPECTED, None), (MODE_ROLL, 42)])
    def test_purity(self, mode, seed):
        def build():
            hero = _hero()
            return _engine(hero, [_enemy()], {"hero": [_basic()]}, mode=mode, seed=seed)
        s1 = build().run().snapshot()
        s2 = build().run().snapshot()
        assert s1 == s2
