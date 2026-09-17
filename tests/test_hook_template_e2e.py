"""虎克 1109 模板端到端对轴（验收型批·组2 收官）：真模板 YAML → 编译 → Burn 施加/
天赋附加/换技能互斥/强化战技/行迹/星魂全链 → 手算全等.

过堂两件（fixture 头注同录）：天赋回能 #2=5 收编 / A3 回能 #1=5 收编
（gain_energy 原语在库——draft 双误判"无能量通道"）。

口径常数：虎克 atk 790.272（白值 617.4×1.28——行迹 atk_pct 0.28 B-TR① 回填）、
hp 1581.9552（白值 1340.64×1.18——行迹 hp_pct 0.18 同回填）、crit 0.05/0.633
（0.5+行迹 crit_dmg 0.133 同回填——期望暴击区 1.03165）；假人 def 0 →
防御区 0.5、火弱点 → 抗性区 1.0、未击破 0.9。普攻 lv6=1.0。
快照语义（§23）：挂 Burn 的当发命中不触发天赋附加（条件见旧值），后续命中触发。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

HK_ATK = 617.4 * 1.28      # 790.272（行迹 atk_pct 0.28 回填——B-TR①）
HK_HP = 1340.64 * 1.18     # 1581.9552（行迹 hp_pct 0.18 回填——B-TR①）
Z = 0.5 * 0.9 * (1 + 0.05 * 0.633)   # 暴击区 1.03165（行迹 crit_dmg 0.133 回填——B-TR①）


def _build(*, eidolon: int = 0):
    member = {"character_template": "1109", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _hk(eng):
    return eng.state.actors["1109"]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


class TestHookCompile:
    def test_resources_and_available_if(self, compiled):
        decls = compiled.resource_decls_by_actor["1109"]
        assert {"_enhanced_skill", "_talent_lock"} <= set(decls)
        acts = {a.action_id: a for a in compiled.actions_by_actor["1109"]}
        assert acts["110902"].available_if == "res__enhanced_skill < 1"
        assert acts["110909"].available_if == "res__enhanced_skill >= 1"


class TestSkillBurn:
    def test_skill_burn_tick_and_snapshot_no_talent(self, compiled):
        """战技：2.4 对轴 + Burn 施加 2 回合——快照见旧值=当发不触发天赋（Welt 同族实证）;
        Burn tick = 0.65×ATK（lv10 #4）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1109", "110902")
        assert math.isclose(hp1 - e1.current_hp, 2.4 * HK_ATK * Z, rel_tol=1e-9), (
            "仅战技伤害——挂 Burn 的当发不触发天赋（快照语义）")
        assert "HOOK_BURN" in e1.modifiers and e1.modifiers["HOOK_BURN"].duration == 2
        a = _hk(eng)
        hp_e, e_e, hp_hk = e1.current_hp, a.current_energy, a.current_hp
        a.current_hp = 500.0
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp_e - e1.current_hp, (0.65 + 1.0) * HK_ATK * Z, rel_tol=1e-9), (
            "tick 0.65 + 天赋附加 1.0（DoT 跳伤经同通道触发天赋——口径在案：官方"
            "'attacking' 是否含 DoT 待实测，载荷无 name 键不可区分）")
        assert math.isclose(a.current_energy - e_e, 5.0), "跳伤触发天赋回能（同口径在案）"
        assert math.isclose(a.current_hp, 500.0 + 0.05 * HK_HP, rel_tol=1e-9), (
            "Innocence 同触发面自疗（同口径在案）")

    def test_talent_bonus_energy_innocence(self, compiled):
        """天赋：命中已 Burn 目标 → 追加 1.0×ATK + 回能 5（收编实证）+ Innocence 自疗 5% Max."""
        eng = _make(compiled)
        _cast(eng, "1109", "110902")   # 先挂 Burn
        a = _hk(eng)
        a.current_hp = 500.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1109", "110901")   # 普攻命中已 Burn 目标
        assert math.isclose(hp1 - e1.current_hp,
                            1.0 * HK_ATK * Z + 1.0 * HK_ATK * Z, rel_tol=1e-9), (
            "普攻 + 天赋附加 1.0（lv10 param(110904,1)）")
        assert math.isclose(a.current_energy, 30.0 + 20.0 + 5.0), (
            "战技 30 + 普攻 20 + 天赋回能 5（gain_energy 收编）")
        assert math.isclose(a.current_hp, 500.0 + 0.05 * HK_HP, rel_tol=1e-9), (
            "Innocence 自疗 5% Max（天赋同触发面）")


class TestUltimateEnhanced:
    def test_ult_grant_and_enhanced_skill(self, compiled):
        """大招：4.0 对轴 + 强化态授予 + 回能 5+5 分槽（A3 收编）；强化战技 Blast
        主 2.8/邻 0.8 + Burn 主邻同挂（口径在案）+ 闩消费互斥回落."""
        eng = _make(compiled)
        m7 = _hk(eng)
        m7.current_energy = 120.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1109"] if a.action_id == "110903")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 4.0 * HK_ATK * Z, rel_tol=1e-9)
        assert math.isclose(m7.resources["_enhanced_skill"], 1.0), "强化态授予"
        assert math.isclose(m7.current_energy, 10.0), "5 自身 + 5 Playing With Fire（收编）"
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1109", "110909")
        assert math.isclose(hp1 - e1.current_hp, 2.8 * HK_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.8 * HK_ATK * Z, rel_tol=1e-9), (
            "Blast 相邻段（lv10 #5=0.8）")
        assert "HOOK_BURN" in e1.modifiers and "HOOK_BURN" in e2.modifiers, (
            "相邻同挂 Burn（官方仅主目标——payload 无 blast 分段标记口径在案）")
        assert math.isclose(m7.resources["_enhanced_skill"], 0.0), "闩消费回落 110902"


class TestEidolons:
    def test_e2_burn_duration(self):
        """E2：Burn 时长 2→3（双 hook 互斥按标记分流）."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1109", "110902")
        assert e1.modifiers["HOOK_BURN"].duration == 3

    def test_e5_talent_lv12(self):
        """E5 天赋+2：附加伤 lv12=1.1×ATK；终结技 lv12=4.32 一并钉."""
        compiled = compile_encounter(_build(eidolon=5), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _cast(eng, "1109", "110902")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1109", "110901")
        assert math.isclose(hp1 - e1.current_hp,
                            1.1 * HK_ATK * Z + 1.1 * HK_ATK * Z, rel_tol=1e-9), (
            "E3 普攻 lv7=1.1 + E5 天赋 lv12=1.1（等级族全联动）")
        m7 = _hk(eng)
        m7.current_energy = 120.0
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1109"] if a.action_id == "110903")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, (4.32 + 1.1) * HK_ATK * Z, rel_tol=1e-9), (
            "终结技 lv12=4.32 + 天赋附加（e1 已 Burn——天赋命中域含终结技）")
