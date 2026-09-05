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

    def test_set_stacks_clamped_to_bounds(self):
        """set 超上限被 clamp 到 max_stack；stacks_value=0 被钳到 1（无 clamp 时产出 0 层死挂）."""
        eng = self._fresh_setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(modifier_id="S", name="叠层", modifier_type="buff",
                                         duration=1, stacks=1, max_stack=3))
        eng._apply_modifier(st, Modifier(modifier_id="S", name="叠层", modifier_type="buff",
                                         duration=1, stack_mode="set", stacks_value=99))
        assert st.modifiers["S"].stacks == 3, "set 超上限应 clamp 到 max_stack"
        eng._apply_modifier(st, Modifier(modifier_id="S", name="叠层", modifier_type="buff",
                                         duration=1, stack_mode="set", stacks_value=0))
        assert st.modifiers["S"].stacks == 1, "set 0 层应钳到 1（0 层=死挂）"

    def test_dict_spec_channel_set_stacks(self):
        """dict 声明通道（模板 YAML 入口）：stacks_value 经 _modifier_from_spec 接线生效."""
        eng = self._fresh_setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier_spec(st, {"modifier_id": "S", "duration": 1}, None)
        assert eng._apply_modifier_spec(
            st, {"modifier_id": "S", "duration": 1, "stack_mode": "set",
                 "stacks_value": 3, "max_stack": 5}, None)
        assert st.modifiers["S"].stacks == 3, "dict 通道 set 3 层应生效（曾整键丢失）"

    def test_singleton_group_swaps(self):
        eng = self._fresh_setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(modifier_id="A", name="旧植入", modifier_type="debuff",
                                         duration=2, singleton_group="implant"))
        eng._apply_modifier(st, Modifier(modifier_id="B", name="新植入", modifier_type="debuff",
                                         duration=2, singleton_group="implant"))
        assert "A" not in st.modifiers and "B" in st.modifiers

    def test_dict_spec_channel_singleton_group(self):
        """dict 声明通道：singleton_group 经 _modifier_from_spec 接线，同组互斥新挂替换旧挂."""
        eng = self._fresh_setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier_spec(st, {"modifier_id": "A", "modifier_type": "debuff",
                                      "duration": 2, "singleton_group": "implant"}, None)
        eng._apply_modifier_spec(st, {"modifier_id": "B", "modifier_type": "debuff",
                                      "duration": 2, "singleton_group": "implant"}, None)
        assert "A" not in st.modifiers and "B" in st.modifiers, \
            "dict 通道同组互斥应生效（曾 singleton_group 整键丢失，两件并存）"

    def test_compiler_gate_accepts_wired_keys(self):
        """键闸放行：singleton_group / stacks_value 是合法 modifier spec 键（曾编译期炸）."""
        from hsr_nous.sim.compile.build_compiler import BuildCompiler
        BuildCompiler()._validate_modifier_spec(
            {"modifier_id": "M", "stack_mode": "set", "stacks_value": 3,
             "singleton_group": "g"}, "模板 X")


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
        """scoped：'$event.action_type == skill'（04_modifier spec 形式）的增伤只加成战技，不加成普攻."""
        hero = _hero(atk=2000)
        skill = Action(action_id="s1", name="战技", action_type="skill", target_type="single",
                       damage_type="fire", scaling=[{"atk": 1.0}], skill_point_cost=1)
        expr = ExprCompiler().compile("$event.action_type == 'skill'")
        from hsr_nous.sim.policy_api import ScriptedPolicy
        enc = Encounter(encounter_id="t", name="t", actors=[hero, _enemy()],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=100))
        eng = CombatEngine(enc, actions_by_actor={"hero": [_basic(), skill]},
                           policy=ScriptedPolicy(rotation=["basic", "skill"]),
                           mode=MODE_EXPECTED, initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
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


class TestAdjustStacksClamp:
    def test_clamp_zero_max_stack_not_raised_to_one(self):
        """adjust_stacks 钳 [0, max_stack]（05_effects §adjust_stacks）：max_stack=0 的
        0 层件加层后仍为 0——旧钳 [1, max] 下界压上界，会被退化抬到 1."""
        hero = _hero()
        eng = _engine(hero, [_enemy()], {"hero": [_basic()]}, av=50)
        eng.setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(
            modifier_id="ZERO", name="零层件", modifier_type="buff", duration=0,
            stacks=0, max_stack=0, dispellable=False))
        eng._run_hook_effect(st, {"effect_type": "adjust_stacks",
                                  "modifier_id": "ZERO", "delta": 1}, {})
        assert st.modifiers["ZERO"].stacks == 0, "clamp [0, 0]：不得被下界 1 抬升"

    def test_clamp_normal_upper_bound_unchanged(self):
        """正常上界行为不变：3 + 5 → 钳到 max_stack=4."""
        hero = _hero()
        eng = _engine(hero, [_enemy()], {"hero": [_basic()]}, av=50)
        eng.setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(
            modifier_id="STK", name="叠层", modifier_type="buff", duration=0,
            stacks=3, max_stack=4, dispellable=False))
        eng._run_hook_effect(st, {"effect_type": "adjust_stacks",
                                  "modifier_id": "STK", "delta": 5}, {})
        assert st.modifiers["STK"].stacks == 4


# ---------------------------------------------------------------------------
# F2 来源记账（source_kind/source_ref：附加字段，行为无关）
# ---------------------------------------------------------------------------

def _prov_char(root, ref="9001", **extra):
    """tmp 根下落一个测试角色模板（可选附加键：trace_stat_effects / hooks / state_config）。"""
    import yaml
    doc = {"actor_id": ref, "name": "测试员", "level": 80,
           "base_stats": {"atk": 1000, "spd": 200, "hp": 3000, "max_energy": 100},
           "actions": [{"action_id": "a1", "name": "普攻", "action_type": "basic",
                        "target_type": "single", "damage_type": "fire",
                        "scaling": [{"atk": 1.0}]}]}
    doc.update(extra)
    (root / "characters").mkdir(parents=True, exist_ok=True)
    (root / "characters" / f"{ref}_测试员.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")


def _prov_engine(root, member_extra=None):
    """tmp 根角色 + 木桩 → 编译好的引擎（已 setup；角色 spd200 必先手）。"""
    from hsr_nous.sim.compile import compile_encounter
    member = {"character_template": "9001", "level": 80}
    member.update(member_extra or {})
    build = {"build": {"team": [member],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}],
                           "target_rules": [], "parameters": {}}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "max_toughness": 60}],
        "termination": {"mode": "fixed_av", "max_action_value": 500}}}
    eng = CombatEngine.from_compiled(
        compile_encounter(build, stage, template_roots=[str(root)]),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestSourceProvenance:
    """F2 施加通道逐点记账：action / hook / trace / relic / state；零行为差（snapshot 不含新字段）。"""

    def test_action_apply_modifiers(self):
        """action apply_modifiers → kind=action、ref=action_id；snapshot 键集不变（全等口径零差异）。"""
        hero = _hero()
        buff_action = Action(action_id="a_buff", name="激励", action_type="basic",
                             target_type="single", damage_type="fire", scaling=[{"atk": 1.0}],
                             apply_modifiers=[{"target": "self", "modifier_id": "M1",
                                               "name": "鼓舞", "stat_effects": {"atk_pct": 0.2}}])
        eng = _engine(hero, [_enemy()], {"hero": [buff_action]}, av=50)
        eng.setup()
        eng.step()  # hero 先动（spd200>100）
        mod = eng.state.actors["hero"].modifiers["M1"]
        assert mod.source_kind == "action" and mod.source_ref == "a_buff"
        assert mod.source_id == "hero"
        assert set(mod.snapshot()) == {"modifier_id", "type", "duration", "stacks", "source_id"}

    def test_hook_apply_modifier(self, tmp_path):
        """hook apply_modifier（模板 hooks 块）→ kind=hook、ref=修饰件可展示名。"""
        root = tmp_path / "templates"
        _prov_char(root, hooks=[
            {"event": "on_battle_start",
             "effects": [{"effect_type": "apply_modifier", "target": "self",
                          "modifier": {"modifier_id": "ZHANYI", "name": "战意",
                                       "stat_effects": {"atk_pct": 0.1}}}]}])
        eng = _prov_engine(root)
        mod = eng.state.actors["9001"].modifiers["ZHANYI"]
        assert mod.source_kind == "hook" and mod.source_ref == "战意"

    def test_trace_and_relic_initial_modifiers(self, tmp_path):
        """编译期初始件：行迹聚合件 kind=trace（ref 空）；遗器套装件 kind=relic、ref=套装名。"""
        import yaml
        root = tmp_path / "templates"
        _prov_char(root, trace_stat_effects={"atk_pct": 0.1})
        (root / "relics").mkdir(parents=True)
        (root / "relics" / "301_测试套.yaml").write_text(yaml.safe_dump(
            {"relic_set_id": 301, "name": "测试套",
             "set_2pc": {"desc": "两件", "stat_effects": {"atk_pct": 0.12}}},
            allow_unicode=True), encoding="utf-8")
        eng = _prov_engine(root, member_extra={
            "relics": {"head": {"set_id": "301", "main": "hp", "subs": {}},
                       "hand": {"set_id": "301", "main": "atk", "subs": {}}}})
        mods = eng.state.actors["9001"].modifiers
        assert mods["TRACE_9001"].source_kind == "trace" and mods["TRACE_9001"].source_ref == ""
        relic = mods["RELIC_301_2PC"]
        assert relic.source_kind == "relic" and relic.source_ref == "测试套"

    def test_state_marker(self, tmp_path):
        """形态标记件 → kind=state、ref=形态显示名。"""
        root = tmp_path / "templates"
        _prov_char(root, state_config={
            "state": "testform", "name": "测试形态", "entry_action_id": "",
            "exit_conditions": [{"trigger": "on_action_count", "value": 2}],
            "stat_effects": {"atk_pct": 0.5}})
        eng = _prov_engine(root)
        st = eng.state.actors["9001"]
        config = eng.state_configs_by_actor["9001"][0]
        eng.enter_state(st, config)
        marker = st.modifiers["STATE_testform"]
        assert marker.source_kind == "state" and marker.source_ref == "测试形态"

    def test_uninstrumented_paths_stay_empty(self):
        """附加式兜底：引擎内部直挂件（击破/月茧族）与默认构造 → 两字段空串。"""
        hero = _hero()
        eng = _engine(hero, [_enemy()], {"hero": [_basic()]}, av=50)
        eng.setup()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(
            modifier_id="PLAIN", name="素件", modifier_type="buff", duration=0))
        mod = st.modifiers["PLAIN"]
        assert mod.source_kind == "" and mod.source_ref == ""
