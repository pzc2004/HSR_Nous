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


class TestSourceTurnStartAnchor:
    def test_source_turn_start_ticks_only_start_anchors(self):
        """source_turn_start（第五锚，长夜月 141302 忆灵光环族）：施加者回合开始走字，
        与 source_turn_end 互不串锚；走字到 0 按到期移除."""
        hero = _hero()
        eng = _engine(hero, [_enemy()], {"hero": [_basic()]}, av=500)
        eng.setup()
        hero_st = eng.state.actors["hero"]
        e_st = eng.state.actors["e1"]
        eng._apply_modifier(e_st, Modifier(
            modifier_id="AURA_S", name="源始锚", modifier_type="buff", duration=2,
            tick_anchor="source_turn_start", source_id="hero"))
        eng._apply_modifier(e_st, Modifier(
            modifier_id="AURA_E", name="源末锚", modifier_type="buff", duration=2,
            tick_anchor="source_turn_end", source_id="hero"))
        eng._apply_modifier(e_st, Modifier(
            modifier_id="AURA_X", name="他人锚", modifier_type="buff", duration=2,
            tick_anchor="source_turn_start", source_id="someone_else"))
        eng._tick_source_modifiers(hero_st.actor, "source_turn_start")
        assert e_st.modifiers["AURA_S"].duration == 1, "施加者回合开始 → start 锚走字"
        assert e_st.modifiers["AURA_E"].duration == 2, "start 调用不动 end 锚"
        assert e_st.modifiers["AURA_X"].duration == 2, "非其施加者不走字"
        eng._tick_source_modifiers(hero_st.actor)   # 缺省 = source_turn_end（旧口径不变）
        assert e_st.modifiers["AURA_S"].duration == 1, "end 调用不动 start 锚"
        assert e_st.modifiers["AURA_E"].duration == 1
        eng._tick_source_modifiers(hero_st.actor, "source_turn_start")
        assert "AURA_S" not in e_st.modifiers, "走字到 0 按到期移除"


class TestConditionalAura:
    """条件光环（04_modifier §4.16）：enable_if 门控 + stat_exprs 现场求值 + count_team/stat_of 宿主."""

    def _mk(self, **kw):
        from hsr_nous.sim_schema.expression import parse
        eng = _engine(_hero(**{k: v for k, v in kw.items() if k in ("spd",)}),
                      [_enemy()], {"hero": [_basic()]}, av=500)
        eng.setup()
        return eng, parse

    def test_enable_if_active_and_inactive(self):
        """条件成立生效 / 不成立不生效：$self.spd >= 150 → atk +1000（hero spd 200 成立、100 不成立）."""
        eng, parse = self._mk()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(
            modifier_id="COND", name="条件件", modifier_type="buff", duration=0,
            stat_effects={"atk": 1000.0},
            enable_if_expr=parse("$self.spd >= 150", layer="effect")))
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], 3000.0), "条件成立：加成计入"
        eng._apply_modifier(st, Modifier(
            modifier_id="SPD_DOWN", name="减速", modifier_type="debuff", duration=0,
            stat_effects={"spd": -150.0}))
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], 2000.0), (
            "无条件件面板 spd=50 < 150 → 条件件不计（门控读不到条件件，但读得到无条件减速件）")

    def test_hp_flip_reval_and_scheduler_resync(self):
        """战中翻转重估：HP≥50% → spd +100；HP 掉到 30% → 面板翻回 + 调度器 AV 重同步."""
        eng, parse = self._mk()
        st = eng.state.actors["hero"]
        handle = eng.scheduler.handle_of("hero")
        spd0 = eng.scheduler.spd_of(handle)
        eng._apply_modifier(st, Modifier(
            modifier_id="TORCH", name="倒置的火炬", modifier_type="buff", duration=0,
            stat_effects={"spd": 100.0},
            enable_if_expr=parse("$self.hp / $self.max_hp >= 0.5", layer="effect")))
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 300.0)
        assert math.isclose(eng.scheduler.spd_of(handle), 300.0), "挂上即经 _sync_speed 上路"
        # HP 掉到 30%：面板懒求值立即翻回 + HP 事件推式重同步调度器
        st.current_hp = 0.3 * eng.pipeline.effective_stats(st)["hp"]
        eng.bus.emit("on_hp_decrease", {"amount": 1.0, "source": "e1", "reason": "hit",
                                        "target": "hero"}, eng.state)
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 200.0), "条件翻转：数值翻回"
        assert math.isclose(eng.scheduler.spd_of(handle), spd0), "调度器速度经 HP 事件重同步回 200 档"
        assert "TORCH" in st.modifiers, "门控非挂摘——件仍在挂载"
        # 奶回 80%：条件翻回成立即恢复
        st.current_hp = 0.8 * eng.pipeline.effective_stats(st)["hp"]
        eng.bus.emit("on_hp_increase", {"amount": 1.0, "source": "hero", "reason": "heal",
                                        "target": "hero"}, eng.state)
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 300.0), "翻回成立即恢复"
        assert math.isclose(eng.scheduler.spd_of(handle), 300.0)

    def test_stat_exprs_live_tier(self):
        """档位现场求值：heal_bonus = min(spd-150, 200)×1%——速度源变化立即变档."""
        eng, parse = self._mk()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(
            modifier_id="CALM", name="暴风停歇", modifier_type="buff", duration=0,
            enable_if_expr=parse("$self.spd > 150", layer="effect"),
            stat_exprs={"heal_bonus": parse("min(max($self.spd - 150, 0), 200) * 0.01",
                                            layer="effect")}))
        assert math.isclose(eng.pipeline.effective_stats(st)["heal_bonus"], 0.5), "spd 200 → 50 档"
        eng._apply_modifier(st, Modifier(
            modifier_id="SPD_UP", name="加速", modifier_type="buff", duration=0,
            stat_effects={"spd": 150.0}))
        assert math.isclose(eng.pipeline.effective_stats(st)["heal_bonus"], 2.0), (
            "spd 350 → min(200,200) 满档（live 变档，非快照）")
        eng._remove_modifier(st, "SPD_UP")
        assert math.isclose(eng.pipeline.effective_stats(st)["heal_bonus"], 0.5), "摘除即回档"

    def test_team_scope_aura_reads_holder_panel(self):
        """光环 holder 语义：scope=team 条件件辐射队友，条件读**携带者**面板."""
        from hsr_nous.sim_schema.actor import Actor as _A
        ally = _A(actor_id="ally", name="队友", level=80,
                  stats=StatBlock(atk=1000, hp=2000, spd=120, max_energy=100))
        hero = _hero()
        enc = Encounter(encounter_id="t", name="t", actors=[hero, ally, _enemy()],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=500))
        eng = CombatEngine(enc, actions_by_actor={"hero": [_basic()]}, mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        from hsr_nous.sim_schema.expression import parse
        ally_st, hero_st = eng.state.actors["ally"], eng.state.actors["hero"]
        eng._apply_modifier(ally_st, Modifier(
            modifier_id="AURA", name="全队增伤", modifier_type="buff", duration=0,
            effect_scope="team", stat_effects={"all_dmg": 0.5},
            enable_if_expr=parse("$self.spd >= 150", layer="effect")))
        assert math.isclose(eng.pipeline.effective_stats(hero_st)["dmg_bonus"].get("all", 0.0), 0.0), (
            "携带者 spd 120 < 150 → 队友吃不到")
        eng._apply_modifier(ally_st, Modifier(
            modifier_id="SPD_UP", name="加速", modifier_type="buff", duration=0,
            stat_effects={"spd": 100.0}))
        assert math.isclose(eng.pipeline.effective_stats(hero_st)["dmg_bonus"].get("all", 0.0), 0.5), (
            "携带者 spd 220 ≥ 150 → 队友吃到（条件按携带者面板，非目标面板）")

    def test_count_team_and_stat_of_hosts(self):
        """count_team 编成计数（含阵亡/忆灵不计）+ stat_of 跨 actor 读 + 条件域防环."""
        from hsr_nous.sim_schema.actor import Actor as _A
        from hsr_nous.sim_schema.expression import parse
        m2 = _A(actor_id="m2", name="记忆二号", level=80, path="remembrance",
                stats=StatBlock(atk=1000, hp=2000, spd=100, max_energy=100))
        m3 = _A(actor_id="m3", name="记忆三号", level=80, path="remembrance",
                stats=StatBlock(atk=1000, hp=2000, spd=100, max_energy=100))
        hero = _A(actor_id="hero", name="测试员", level=80, path="remembrance",
                  stats=StatBlock(atk=2000, hp=2000, spd=200, crit_rate=0.5, crit_dmg=1.0,
                                  max_energy=100))
        enc = Encounter(encounter_id="t", name="t", actors=[hero, m2, m3, _enemy()],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=500))
        eng = CombatEngine(enc, actions_by_actor={"hero": [_basic()]}, mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        assert eng._count_team_path("remembrance") == 3.0
        eng.state.actors["m3"].alive = False
        assert eng._count_team_path("remembrance") == 3.0, "含阵亡——编成口径与存活无关"
        st = eng.state.actors["hero"]
        # stat_exprs 里用 count_team 变档 + stat_of 跨 actor 读
        eng._apply_modifier(st, Modifier(
            modifier_id="DAWN", name="天亮了", modifier_type="buff", duration=0,
            stat_exprs={"crit_dmg": parse("count_team(path='remembrance') >= 4 ? 0.65 : "
                                          "count_team(path='remembrance') == 3 ? 0.5 : 0.15",
                                          layer="effect"),
                        "atk": parse("stat_of('m2', 'atk') * 0.1", layer="effect")}))
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_dmg"], 1.0 + 0.5), "3 记忆 → 0.5 档（C 风格三元链）"
        assert math.isclose(eff["atk"], 2000 + 100.0), "stat_of 读 m2 白值 atk×0.1"
        # 防环钉：条件件产出对另一条件件不可见（m2 条件件读 hero atk —— 看不到 DAWN 的 +100）
        eng._apply_modifier(eng.state.actors["m2"], Modifier(
            modifier_id="RING", name="环测", modifier_type="buff", duration=0,
            stat_effects={"crit_rate": 1.0},
            enable_if_expr=parse("stat_of('hero', 'atk') > 2050", layer="effect")))
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["m2"])["crit_rate"], 0.05), (
            "条件域读无条件件面板：hero atk=2100（含 DAWN 档）不可见 → 按 2000 判 → 不生效")

    def test_modifier_from_spec_keys(self):
        """dict 声明物化：enable_if/stat_exprs 编译进 Modifier；未知键/坏表达式编译期炸."""
        from hsr_nous.sim.compile.build_compiler import BuildCompiler
        bc = BuildCompiler()
        bc._validate_modifier_spec({
            "modifier_id": "OK", "enable_if": "$self.spd > 200",
            "stat_exprs": {"heal_bonus": "min($self.spd, 200) * 0.01"}}, where="t")
        with pytest.raises(ValueError, match="未知键"):
            bc._validate_modifier_spec({"modifier_id": "X", "enable_iff": "true"}, where="t")
        with pytest.raises(ValueError, match="enable_if 表达式非法"):
            bc._validate_modifier_spec({"modifier_id": "X", "enable_if": "foo("}, where="t")
        with pytest.raises(ValueError, match="stat_exprs.*表达式非法"):
            bc._validate_modifier_spec(
                {"modifier_id": "X", "stat_exprs": {"atk": "foo("}}, where="t")
        eng, _ = self._mk()
        st = eng.state.actors["hero"]
        eng._apply_modifier_spec(st, {
            "modifier_id": "SPEC", "enable_if": "$self.spd >= 200",
            "stat_effects": {"atk": 500}, "stat_exprs": {"heal_bonus": "0.01"}}, None)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], 2500.0) and math.isclose(eff["heal_bonus"], 0.01)
