"""modifier spec 四通道接线：DSL 声明 → 生效.

四通道曾是半接线：Modifier 字段与引擎/pipeline 消费点早已存在，但 dict 声明层
（_MODIFIER_SPEC_KEYS 键闸 + engine._modifier_from_spec 读取）不通——模板写出来
编译期炸或被静默丢掉。本文件逐通道钉"声明→生效"：
forced_taunt（引擎 _pick_ally_target 分支）/ scaling_effects（Layer 2a 转化）/
override_effects（Layer 2b 覆写）/ hit_condition（scoped 命中域加成）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier, ShieldInstance
from hsr_nous.sim_schema.expression import PreparedExpression


def _engine(apply_mods, *, enemy_hp=1e9) -> CombatEngine:
    build = {"build": {"team": [
        {"character_template": "inline", "actor_id": "hero", "name": "测试员", "level": 80,
         "base_stats": {"hp": 5000, "atk": 2000, "spd": 200, "max_energy": 100,
                        "crit_rate": 0.0, "taunt": 100},
         "actions": [
             {"action_id": "basic", "name": "普攻", "action_type": "basic",
              "target_type": "single", "damage_type": "fire",
              "scaling": [{"atk": 1.0}], "toughness_dmg": 0},
             {"action_id": "mark", "name": "标记", "action_type": "skill",
              "target_type": "single", "apply_modifiers": apply_mods},
         ]},
        {"character_template": "inline", "actor_id": "ally", "name": "队友", "level": 80,
         "base_stats": {"hp": 4000, "atk": 1000, "spd": 100, "max_energy": 100, "taunt": 150},
         "actions": [{"action_id": "basic2", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}]}]},
    ]}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "level": 80, "hp": enemy_hp, "spd": 100,
         "max_toughness": 9999, "weakness": ["fire"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 300}}}
    eng = CombatEngine.from_compiled(compile_encounter(build, stage), mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=5)
    eng.setup()
    return eng


def _action(eng: CombatEngine, action_id: str):
    return next(a for a in eng.actions_by_actor["hero"] if a.action_id == action_id)


class TestForcedTauntChannel:
    def test_dsl_to_targeting_override(self):
        """DSL 声明 forced_taunt → 敌人加权选目标被覆盖，必打施加者."""
        eng = _engine([{"modifier_id": "FT", "name": "嘲讽", "modifier_type": "debuff",
                        "duration": 2, "target": "all_enemies", "forced_taunt": True}])
        hero_st = eng.state.actors["hero"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        e1 = eng.state.actors["e1"]
        assert e1.modifiers["FT"].forced_taunt is True
        assert e1.modifiers["FT"].source_id == "hero"
        # 队友 taunt 150 > 测试员 100——无强制嘲讽时期望模式必选队友
        for _ in range(5):
            assert eng._pick_ally_target(e1) is hero_st


class TestScalingEffectsChannel:
    def test_dsl_to_layer2a_conversion(self):
        """DSL 声明 scaling_effects → Layer 2a 转化：atk += l1_hp × 0.5."""
        eng = _engine([{"modifier_id": "CONV", "name": "转化", "duration": 2,
                        "scaling_effects": {"atk": ["hp", 0.5]}}])
        hero_st = eng.state.actors["hero"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        se = eng.pipeline.effective_stats(hero_st)
        assert math.isclose(se["atk"], 2000 + 5000 * 0.5, rel_tol=1e-9), \
            "转化读 Layer 1 白值域（l1 hp=5000），不读 effective"

    def test_bad_shape_rejected_at_compile(self):
        """形状错（非 [source_stat, ratio] 二元组）编译期炸."""
        with pytest.raises(ValueError, match="scaling_effects"):
            _engine([{"modifier_id": "CONV", "scaling_effects": {"atk": "hp*0.5"}}])


class TestOverrideEffectsChannel:
    def test_dsl_to_layer2b_override(self):
        """DSL 声明 override_effects → Layer 2b 覆写：def_ = 0（真·零防，不吃白板兜底）."""
        eng = _engine([{"modifier_id": "DEF0", "name": "减防归零", "modifier_type": "debuff",
                        "duration": 2, "target": "all_enemies",
                        "override_effects": {"def_": 0.0}}])
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        r0 = eng.pipeline.deal_damage(_action(eng, "basic"), hero_st, e1)
        assert math.isclose(r0.node["defMulti"], 0.5, rel_tol=1e-9), "前置：白板防兜底 1000"
        eng._execute_action(hero_st, _action(eng, "mark"))
        assert math.isclose(eng.pipeline.effective_stats(e1)["def_"], 0.0)
        r1 = eng.pipeline.deal_damage(_action(eng, "basic"), hero_st, e1)
        assert math.isclose(r1.node["defMulti"], 1.0, rel_tol=1e-9)


class TestHitConditionChannel:
    _SPEC = {"modifier_id": "HUNT", "name": "对受控增伤", "duration": 0,
             "stat_effects": {"all_dmg": 0.5},
             "hit_condition": "$event.target_controlled"}

    def test_dsl_compiled_not_raw_string(self):
        """声明期预编译：modifier 上存 PreparedExpression，不存裸字符串."""
        eng = _engine([dict(self._SPEC)])
        hero_st = eng.state.actors["hero"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        assert isinstance(hero_st.modifiers["HUNT"].hit_condition_expr, PreparedExpression)

    def test_scoped_boost_vs_controlled_target(self):
        """对受控目标增伤族：受控 +0.5 增伤，未受控不加；面板域恒忽略 scoped 件."""
        eng = _engine([dict(self._SPEC)])
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        se = eng.pipeline.effective_stats(hero_st)
        assert math.isclose(se["dmg_bonus"].get("all", 0.0), 0.0), \
            "面板求值一律忽略带 hit_condition 的 modifier（spec 两域语义）"
        act = _action(eng, "basic")
        r0 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r0.node["dmgBoostMulti"], 1.0, rel_tol=1e-9)
        eng._apply_modifier(e1, Modifier(
            modifier_id="FRZ", name="冻结", modifier_type="control", debuff_kind="control",
            duration=1, control_kind="freeze"))
        r1 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r1.node["dmgBoostMulti"], 1.5, rel_tol=1e-9)

    def test_illegal_expression_rejected_at_compile(self):
        """hit_condition 非法表达式编译期炸（B8 同口径，不进运行时）."""
        with pytest.raises(ValueError, match="hit_condition 表达式非法"):
            _engine([{**self._SPEC, "hit_condition": "$event.x >="}])


class TestHitStatExprsChannel:
    """hit_stat_exprs 命中域表达式值（2026-09-23 落地——per-hit 按目标状态伸缩值槽）."""

    _SPEC = {"modifier_id": "WK", "name": "弱点增伤", "duration": 0,
             "hit_stat_exprs": {"all_dmg": "0.04 * min(weakness_count($event.target), 7)"}}

    def test_dsl_compiled_not_raw_string(self):
        eng = _engine([dict(self._SPEC)])
        hero_st = eng.state.actors["hero"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        exprs = hero_st.modifiers["WK"].hit_stat_exprs
        assert isinstance(exprs["all_dmg"], PreparedExpression)

    def test_per_hit_value_and_panel_exclusion(self):
        """per-hit 按目标现场弱点计数计值；面板域一律忽略（与 hit_condition 件同纪律）."""
        eng = _engine([dict(self._SPEC)])
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        se = eng.pipeline.effective_stats(hero_st)
        assert math.isclose(se["dmg_bonus"].get("all", 0.0), 0.0), \
            "面板求值一律忽略 hit_stat_exprs 携带件（防面板/命中双计）"
        act = _action(eng, "basic")
        r0 = eng.pipeline.deal_damage(act, hero_st, e1)   # e1 面板弱点 ["fire"]=1 种
        assert math.isclose(r0.node["dmgBoostMulti"], 1.04, rel_tol=1e-9)
        eng._apply_modifier(e1, Modifier(
            modifier_id="IMPLANT", name="弱点植入", modifier_type="debuff",
            duration=1, dispellable=False, weakness_add=["ice", "thunder"]))
        r1 = eng.pipeline.deal_damage(act, hero_st, e1)   # 1+2=3 种（含植入）
        assert math.isclose(r1.node["dmgBoostMulti"], 1.12, rel_tol=1e-9)

    def test_illegal_expression_rejected_at_compile(self):
        with pytest.raises(ValueError, match="hit_stat_exprs"):
            _engine([{**self._SPEC, "hit_stat_exprs": {"all_dmg": "$event.x >="}}])

    def test_unknown_function_rejected_at_compile(self):
        """未登记宿主函数编译期炸（白名单唯一事实来源=expression.py）."""
        with pytest.raises(ValueError, match="不在 effect 层白名单"):
            _engine([{**self._SPEC, "hit_stat_exprs": {"all_dmg": "has_weakness($event.target, 'fire') * 0.1"}}])


class TestHitDomainTargetFields:
    """伤害命中域 $event 目标字段（2026-09-23——target_hp_ratio / target_control_kinds）."""

    def test_target_hp_ratio_condition(self):
        """HP≥50% 条件增伤：满血触发、半血不触发（结算前现场值）."""
        eng = _engine([{"modifier_id": "HP50", "name": "压制", "duration": 0,
                        "stat_effects": {"all_dmg": 0.45},
                        "hit_condition": "$event.target_hp_ratio >= 0.5"}])
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        act = _action(eng, "basic")
        r0 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r0.node["dmgBoostMulti"], 1.45, rel_tol=1e-9)
        e1.current_hp = 0.4 * eng.pipeline.effective_stats(e1)["hp"]
        r1 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r1.node["dmgBoostMulti"], 1.0, rel_tol=1e-9)

    def test_target_control_kinds_membership(self):
        """控制类型列表 + in 成员判定：冻结触发、禁锢不触发（可分类型粒度）."""
        eng = _engine([{"modifier_id": "ICING", "name": "冻结增伤", "duration": 0,
                        "stat_effects": {"all_dmg": 0.2},
                        "hit_condition": "'freeze' in $event.target_control_kinds"}])
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        act = _action(eng, "basic")
        eng._apply_modifier(e1, Modifier(
            modifier_id="IMP", name="禁锢", modifier_type="control", debuff_kind="control",
            duration=1, control_kind="imprison"))
        r0 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r0.node["dmgBoostMulti"], 1.0, rel_tol=1e-9), "禁锢不触发"
        eng._apply_modifier(e1, Modifier(
            modifier_id="FRZ", name="冻结", modifier_type="control", debuff_kind="control",
            duration=1, control_kind="freeze"))
        r1 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r1.node["dmgBoostMulti"], 1.2, rel_tol=1e-9)


class TestTargetStateQueries:
    """has_stat_penalty / has_shield 目标状态检索宿主函数（2026-09-23）."""

    def test_has_stat_penalty(self):
        """负值修饰扫描：减速（spd_pct 负）触发、无修饰不触发；buff 件不计."""
        eng = _engine([{"modifier_id": "SLOW_DMG", "name": "对减速增伤", "duration": 0,
                        "stat_effects": {"all_dmg": 0.24},
                        "hit_condition": "has_stat_penalty($event.target, 'spd_pct') || has_stat_penalty($event.target, 'def_pct')"}])
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        act = _action(eng, "basic")
        r0 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r0.node["dmgBoostMulti"], 1.0, rel_tol=1e-9), "无修饰不触发"
        eng._apply_modifier(e1, Modifier(
            modifier_id="SPD_DOWN", name="减速", modifier_type="debuff",
            duration=1, dispellable=False, stat_effects={"spd_pct": -0.2}))
        r1 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r1.node["dmgBoostMulti"], 1.24, rel_tol=1e-9), "减速触发"
        eng._apply_modifier(e1, Modifier(
            modifier_id="BUFF_SPD", name="加速 buff", modifier_type="buff",
            duration=1, dispellable=False, stat_effects={"spd_pct": 0.2}))
        r2 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r2.node["dmgBoostMulti"], 1.24, rel_tol=1e-9), (
            "buff 件正负都不计入（只扫非 buff 件——减速 debuff 仍在，值不变）")
        e1.modifiers.pop("SPD_DOWN")
        r3 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r3.node["dmgBoostMulti"], 1.0, rel_tol=1e-9), (
            "减速摘除后只剩 buff 件 → 不触发")

    def test_has_shield(self):
        """持盾判定：shields 非空触发、空不触发（逐目标；函数直读 + 命中域路径双验）."""
        eng = _engine([{"modifier_id": "SH", "name": "持盾增伤", "duration": 0,
                        "stat_effects": {"all_dmg": 0.15},
                        "hit_condition": "has_shield($event.target)"}])
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._execute_action(hero_st, _action(eng, "mark"))
        fns = eng._hooks._hook_functions(hero_st)
        assert fns["has_shield"](e1) == 0.0
        e1.shields.append(ShieldInstance(shield_id="S1", name="盾", remaining=100.0,
                                         source_id="hero", modifier_id=""))
        assert fns["has_shield"](e1) == 1.0
        assert fns["has_shield"](hero_st) == 0.0
        act = _action(eng, "basic")
        r = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r.node["dmgBoostMulti"], 1.15, rel_tol=1e-9), "命中域路径同触发"
        e1.shields.clear()
        r2 = eng.pipeline.deal_damage(act, hero_st, e1)
        assert math.isclose(r2.node["dmgBoostMulti"], 1.0, rel_tol=1e-9)


class TestSpConsumedPayload:
    """on_action 载荷 sp_consumed 槽（2026-09-23——实际耗点净值）."""

    def test_sp_consumed_tracked(self):
        """耗点行动发 sp_consumed=实际净值；产点行动发 0；抵扣后按净值."""
        seen = []
        build = {"build": {"team": [
            {"character_template": "inline", "actor_id": "hero", "name": "测试员", "level": 80,
             "base_stats": {"hp": 5000, "atk": 2000, "spd": 200, "max_energy": 100,
                            "crit_rate": 0.0, "taunt": 100},
             "actions": [
                 {"action_id": "skill1", "name": "战技", "action_type": "skill",
                  "target_type": "single", "damage_type": "fire",
                  "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "skill_point_cost": 1},
                 {"action_id": "basic", "name": "普攻", "action_type": "basic",
                  "target_type": "single", "damage_type": "fire",
                  "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "skill_point_gain": 1},
             ]},
        ]}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "level": 80, "hp": 1e9, "spd": 100,
             "max_toughness": 9999, "weakness": ["fire"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 300}}}
        eng = CombatEngine.from_compiled(compile_encounter(build, stage), mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        eng.bus.subscribe("on_action", lambda et, p, ctx: seen.append(p["sp_consumed"]))
        hero_st = eng.state.actors["hero"]
        eng._execute_action(hero_st, _action(eng, "skill1"))
        eng.bus.emit("on_action", {"actor": "hero", "action_type": "skill",
                                   "action_id": "skill1", "target_type": "single",
                                   "target": "e1", "actor_type": "character",
                                   "sp_consumed": eng._last_sp_consumed}, eng.state)
        eng._execute_action(hero_st, _action(eng, "basic"))
        eng.bus.emit("on_action", {"actor": "hero", "action_type": "basic",
                                   "action_id": "basic", "target_type": "single",
                                   "target": "e1", "actor_type": "character",
                                   "sp_consumed": eng._last_sp_consumed}, eng.state)
        assert seen == [1, 0], "战技耗 1 → sp_consumed=1；普攻产 1 → 0"
        assert eng.state.skill_points == 3   # 3-1+1 净不变


def test_expr_compiler_shared_one_instance():
    """ExprCompiler 三实例合一：build 编译期创建，engine 注入 pipeline 与 policy runtime."""
    eng = _engine([])
    assert eng.decision is not None
    assert eng.pipeline._expr is eng._expr
    assert eng.decision.expr is eng._expr
