"""残梅绽端到端（阮梅 130303 原文口径）.

场景用**火**击破（冰击破会冻结，冻结分支"跳过行动+提前 50%"会抢走恢复分支，盖住残梅绽路径）；
残梅绽的触发伤害仍是阮•梅的冰击破（与击破者属性无关）。

原文：结界中我方攻击对命中敌人施加残梅绽；被施加者尝试从击破恢复时触发——
延长击破（阻止恢复）+ 按击破特攻延后行动 + 冰属性击破伤害；恢复前不可重复附加。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS


@pytest.fixture(scope="module")
def engine_factory():
    build = {"build": {"team": [
        {"character_template": "1303", "level": 80},
        {"actor_id": "ally", "name": "火攻手", "inline": True,
         "base_stats": {"atk": 2000, "spd": 80, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 30}]},
    ], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
         "max_toughness": 30, "weakness": ["fire"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 600}}}

    def make():
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=1.0)
        eng.setup()
        return eng
    return make


def _ult_zone(eng):
    """阮梅开大展开结界（130303）."""
    rm = eng.state.actors["1303"]
    ult = next(a for a in eng.actions_by_actor["1303"] if a.action_id == "130303")
    eng._execute_action(rm, ult)


def _ally_hit(eng):
    ally = eng.state.actors["ally"]
    basic = next(a for a in eng.actions_by_actor["ally"] if a.action_id == "ally_basic")
    eng._execute_action(ally, basic)


def _broken_marked_enemy(eng):
    """结界已展开 + 一击击破（toughness_dmg 30 = 满韧 30）+ 残梅绽挂标."""
    _ult_zone(eng)
    _ally_hit(eng)
    e = eng.state.actors["e1"]
    assert e.broken, "一击满削韧应已击破"
    assert "THANATOPLUM" in e.modifiers, "结界中命中应挂残梅绽标记"
    assert "THANATOPLUM_LOCK" in e.modifiers, "挂标同时上重挂锁"
    return e


def _simulate_pop_and_enemy_turn(eng, e):
    """模拟调度器弹出敌方回合（remaining 无条件重置满条）后走敌方回合."""
    h = eng.scheduler.handle_of(e.actor.actor_id)
    eng.scheduler._remaining[h] = 10000.0
    eng._enemy_turn(e)
    return h


class TestThanatoplum:
    def test_marker_applied_only_in_zone(self, engine_factory):
        """结界外命中不挂标；结界中命中才挂."""
        eng = engine_factory()
        _ally_hit(eng)
        e = eng.state.actors["e1"]
        assert "THANATOPLUM" not in e.modifiers, "无结界不挂标"
        _ult_zone(eng)
        _ally_hit(eng)
        assert "THANATOPLUM" in e.modifiers

    def test_rebloom_blocks_recovery_delays_and_deals_ice_break(self, engine_factory):
        """触发三件：恢复被阻（保持击破）+ 延后 BE×20%+10% + 冰击破伤害；标记摘除、锁保留."""
        eng = engine_factory()
        e = _broken_marked_enemy(eng)
        rm = eng.state.actors["1303"]
        be = eng.pipeline.effective_stats(rm)["break_effect"]
        # 数额锚（pipeline 纯结算，调用无副作用）：残梅绽 = 0.5 × 阮梅冰击破值
        expected_dmg = eng.pipeline.break_damage(rm, e, "ice").value * 0.5
        hp_before = e.current_hp
        h = _simulate_pop_and_enemy_turn(eng, e)
        assert e.broken, "残梅绽阻止恢复——击破状态延长"
        assert math.isclose(e.toughness, 0.0), "韧性未恢复"
        expected_delay = (be * 0.20 + 0.10) * 10000.0
        assert math.isclose(eng.scheduler._remaining[h], expected_delay, rel_tol=1e-6), \
            f"延后量 = 击破特攻×20%+10%（BE={be:.3f} → {expected_delay:.0f}）"
        # 数额断言：HP 恰降 0.5×击破值（双扣血 bug 时为 1.5×——pipeline 1.0× + hook 0.5×）
        assert math.isclose(hp_before - e.current_hp, expected_dmg, rel_tol=1e-9), \
            f"残梅绽伤害应恰为 0.5×击破值（{expected_dmg:,.0f}），实际 {hp_before - e.current_hp:,.0f}"
        assert "THANATOPLUM" not in e.modifiers, "标记触发后摘除"
        assert "THANATOPLUM_LOCK" in e.modifiers, "重挂锁保留（本次恢复被阻）"

    def test_lock_released_on_real_recovery_then_reapply(self, engine_factory):
        """真正恢复（无标记）→ 重挂锁解除 → 结界中可再次挂标."""
        eng = engine_factory()
        e = _broken_marked_enemy(eng)
        _simulate_pop_and_enemy_turn(eng, e)  # 触发残梅绽，保持击破
        assert e.broken
        _simulate_pop_and_enemy_turn(eng, e)  # 第二次尝试：无标记 → 真恢复
        assert not e.broken, "无标记时正常恢复"
        assert math.isclose(e.toughness, 30.0), "韧性回满"
        assert "THANATOPLUM_LOCK" not in e.modifiers, "真恢复后重挂锁解除"
        _ally_hit(eng)
        assert "THANATOPLUM" in e.modifiers, "解锁后可重新挂标"
