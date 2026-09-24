"""死后清理族收官测试（B27#10，2026-09-17）：alive 闸使「自己听自己 actor_exit」hook
结构性不触发——两件引擎层通道的行为钉：

① modifier `remove_on_source_death` 生命周期旗标（04_modifier §4.15）：1313 星期日
   「陷入无法战斗状态时【蒙福者】效果也会被解除」——真死定论全场摘除 + 不误伤未挂旗件；
② `actor_alive` 在场谓词（22_syntax_reference §22.4）：1222 灵砂死亡牵连浮元离场后
   谓词即假——旧 `_fy_on_field` 手工闩「真死→闩卡 1→复活后闩说在场实际不在」错位病灶
   的绝育钉（引擎无真死复活路径，复活用手工 alive 翻位模拟）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS


# ---------------------------------------------------------------------------
# ① remove_on_source_death（1313 蒙福者）
# ---------------------------------------------------------------------------

def _sunday_build():
    return {"build": {"team": [
        {"actor_id": "ally", "name": "电池", "inline": True,
         "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 135},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "physical",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
        {"character_template": "1313", "level": 80},
    ], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE_1E = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 800}}}


def _make(build, stage):
    eng = CombatEngine.from_compiled(
        compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestRemoveOnSourceDeath:
    def test_sunday_death_strips_beatified(self):
        """蒙福者：星期日开大挂上（活着时正常存在）→ 打死星期日 → 全场摘除（reason=source_death）；
        未挂旗的战技增伤件不误伤."""
        eng = _make(_sunday_build(), _STAGE_1E)
        sun, ally = eng.state.actors["1313"], eng.state.actors["ally"]
        removed = []
        eng.bus.subscribe("after_remove_modifier", lambda et, p, ctx: removed.append(dict(p)))
        # 战技（未挂旗对照件）+ 终结技（蒙福者）——政策缺省目标=编队首=ally
        sk = next(x for x in eng.actions_by_actor["1313"] if x.action_id == "131302")
        eng._execute_action(sun, sk)
        eng.bus.emit("on_action", {
            "actor": "1313", "action_type": "skill", "action_id": "131302",
            "target_type": sk.target_type, "target": eng._last_target_id,
            "actor_type": "character"}, eng.state)
        assert "SUNDAY_SKILL_DMG" in ally.modifiers
        sun.current_energy = 130.0
        ult = next(x for x in eng.actions_by_actor["1313"] if x.action_id == "131303")
        assert eng._fire_ultimate(sun, ult) is True
        beat = ally.modifiers.get("BEATIFIED")
        assert beat is not None, "活着时蒙福者正常存在"
        assert beat.source_id == "1313", "施加者账（hook owner）是摘除判定锚"
        assert beat.remove_on_source_death is True, "旗标消费端（fixture 声明已物化）"
        # 打死星期日（真死定论——无锁血/月茧/复活件）
        sun.current_hp = 0.0
        eng._check_death(sun, "e1")
        assert not sun.alive
        assert "BEATIFIED" not in ally.modifiers, "真死→旗标件全场摘除"
        hits = [p for p in removed if p.get("modifier_id") == "BEATIFIED"]
        assert hits and all(p.get("reason") == "source_death" for p in hits), (
            f"摘除走 source_death 常轨：{removed}")
        assert "SUNDAY_SKILL_DMG" in ally.modifiers, "未挂旗件不误伤"

    def test_unflagged_source_death_keeps_modifiers(self):
        """反向钉：无任何旗标件时，施加者死亡不波及其施加的 modifier（默认行为零变化）."""
        eng = _make(_sunday_build(), _STAGE_1E)
        sun, ally = eng.state.actors["1313"], eng.state.actors["ally"]
        sk = next(x for x in eng.actions_by_actor["1313"] if x.action_id == "131302")
        eng._execute_action(sun, sk)
        eng.bus.emit("on_action", {
            "actor": "1313", "action_type": "skill", "action_id": "131302",
            "target_type": sk.target_type, "target": eng._last_target_id,
            "actor_type": "character"}, eng.state)
        sun.current_hp = 0.0
        eng._check_death(sun, "e1")
        assert "SUNDAY_SKILL_DMG" in ally.modifiers


# ---------------------------------------------------------------------------
# ② actor_alive 谓词（1222 浮元在场）
# ---------------------------------------------------------------------------

def _lingsha_build():
    return {"build": {"team": [
        {"character_template": "1222", "level": 80},
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE_2E = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _cast_skill(eng):
    ls = eng.state.actors["1222"]
    a = next(x for x in eng.actions_by_actor["1222"] if x.action_id == "122202")
    eng._execute_action(ls, a)
    eng.bus.emit("on_action", {
        "actor": "1222", "action_type": "skill", "action_id": "122202",
        "target_type": "aoe", "target": "e1",
        "actor_type": ls.actor.actor_type}, eng.state)


def _emit_hit_on_ally(eng):
    eng.bus.emit("on_hp_decrease", {
        "amount": 300.0, "source": "e1", "reason": "hit", "target": "ally",
        "damage_type": "fire", "action_type": "basic"}, eng.state)


class TestActorAlivePredicate:
    def test_echo_fires_while_fuyuan_present(self):
        """正控：浮元在场 → 余烬回响门控谓词为真，受击低血触发浮元追击."""
        eng = _make(_lingsha_build(), _STAGE_2E)
        _cast_skill(eng)
        assert eng.state.actors["1222_fuyuan"].alive
        eng.state.actors["ally"].current_hp = 1000.0   # 33% ≤60%
        hp1 = eng.state.actors["e1"].current_hp
        _emit_hit_on_ally(eng)
        assert eng.state.actors["e1"].current_hp < hp1, "浮元在场：余烬回响触发"

    def test_owner_death_cascade_no_stale_latch(self):
        """灵砂真死 → 浮元级联离场 → 谓词即假；模拟复活（手工 alive 翻位——引擎无真死
        复活路径）后余烬回响不误发（旧 _fy_on_field 闩卡 1 的错位病灶绝育钉）."""
        eng = _make(_lingsha_build(), _STAGE_2E)
        _cast_skill(eng)
        ls = eng.state.actors["1222"]
        fy = eng.state.actors["1222_fuyuan"]
        ls.current_hp = 0.0
        eng._check_death(ls, "e1")
        assert not ls.alive and not fy.alive, "真死 → 召唤物级联离场（owner_leave 漏斗）"
        assert "_fy_on_field" not in ls.resources, "在场闩已绝育——无手账可错位"
        # 模拟复活（把灵砂拉回战场）：浮元不会自己回来——谓词保持为假
        ls.alive = True
        ls.current_hp = 1000.0
        eng.state.actors["ally"].current_hp = 1000.0   # 33% ≤60%（触发条件其余全满足）
        assert math.isclose(ls.resources["_echo_cd"], 0.0)
        hp1 = eng.state.actors["e1"].current_hp
        _emit_hit_on_ally(eng)
        assert math.isclose(eng.state.actors["e1"].current_hp, hp1), (
            "浮元不在场：余烬回响不误发（旧闩卡 1 时本拍会误发）")
        assert math.isclose(ls.resources["_echo_cd"], 0.0), "未触发不进冷却"
