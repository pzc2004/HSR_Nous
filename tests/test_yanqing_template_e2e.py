"""彦卿 1209 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → Soulsteel Sync
门控/追击冻结链/终结技 crit 双件/星魂归位全链 → 手算全等.

过堂勘正六件（fixture 头注同录）：列幻视两件（大招 #3 列 3.5/追击 #4 列 0.50）/
星魂泄漏四件归位 eidolons / chance→mechanic_chance / 秘技真伤 damage_type 留源元素 /
ULT_CRIT_DMG on_become_target 通道 / E6 refresh 近似在案。

口径常数：彦卿白值 atk 679.14、spd 109、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、冰弱点 → 抗性区 1.0、未击破 0.9。
Sync lv10：暴击 +20%/暴伤 +30%（区 0.25/0.8→crit 1.2）；追击 lv10 倍率 0.50。
**时序钉**：战技本发不吃 Sync crit（Sync 于伤害后 on_action 挂上）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

YQ_ATK = 679.14
Z = 0.5 * 0.9


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1209", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member],
         "policy": {"name": "p", "action_rules": [
             {"condition": "true", "action": "skill", "priority": 50},
             {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _yq(eng):
    return eng.state.actors["1209"]


def _cast(eng, aid, target_id="e1"):
    yq = _yq(eng)
    a = next(x for x in eng.actions_by_actor["1209"] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(yq, a)
    eng.bus.emit("on_action", {
        "actor": "1209", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": yq.actor.actor_type}, eng.state)


class TestYanqingCompile:
    def test_resources_and_gating(self, compiled):
        decls = compiled.resource_decls_by_actor["1209"]
        assert {"_e1_lock", "_tech_lock"} <= set(decls)
        evs = [h.event for h in compiled.hooks if h.owner_id == "1209"]
        assert len(evs) == 9 and evs.count("on_kill") == 0, "E0 主干 9 钩无星魂件（归位实证）"


class TestSoulsteelSync:
    def test_skill_sync_and_timing(self, compiled):
        """战技 2.2 lv10 对轴：本发不吃 Sync crit（时序钉）；追击+Icing 按挂后 crit 1.2."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "120902")
        yq = _yq(eng)
        assert "SOULSTEEL_SYNC" in yq.modifiers
        # 战技 2.2（crit 1.025——Sync 未挂）+ 追击 0.5（expected 恒触发，crit 1.2）+ Icing 0.3（crit 1.2）
        assert math.isclose(hp1 - e1.current_hp,
                            2.2 * YQ_ATK * Z * 1.025 + (0.5 + 0.3) * YQ_ATK * Z * 1.2, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.3 * YQ_ATK * Z * 1.2, rel_tol=1e-9), (
            "Icing AoE 全体（冰弱点门控上位近似在案）")

    def test_sync_gated_stats_and_strip(self, compiled):
        """Sync 门控件：暴击 0.25/暴伤 0.8 双态——受击（reason==hit）摘除即回基线."""
        eng = _make(compiled)
        _cast(eng, "120902")
        es = eng.pipeline.effective_stats(_yq(eng))
        assert math.isclose(es["crit_rate"], 0.05 + 0.20, rel_tol=1e-9)
        assert math.isclose(es["crit_dmg"], 0.5 + 0.30, rel_tol=1e-9)
        assert math.isclose(es["effect_res"], 0.2, rel_tol=1e-9), "行迹 1209102 同门控"
        eng.bus.emit("on_hp_decrease", {"amount": 10.0, "source": "e1",
                                        "reason": "hit", "target": "1209"}, eng.state)
        assert "SOULSTEEL_SYNC" not in _yq(eng).modifiers
        es2 = eng.pipeline.effective_stats(_yq(eng))
        assert math.isclose(es2["crit_rate"], 0.05, rel_tol=1e-9)
        assert math.isclose(es2["effect_res"], 0.0, rel_tol=1e-9), "门控件随 Sync 摘除即失效"


class TestUltimate:
    def test_ult_crit_buffs(self, compiled):
        """大招 3.5 lv10（#3 列）+ 暴击 +60% 全档恒定 + Sync 门控暴伤 +50%（本发可吃）."""
        eng = _make(compiled)
        _cast(eng, "120902")   # 先挂 Sync
        yq = _yq(eng)
        yq.current_energy = 140.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        ult = next(x for x in eng.actions_by_actor["1209"] if x.action_id == "120903")
        assert eng._fire_ultimate(yq, ult) is True
        assert "ULT_CRIT_RATE" in yq.modifiers
        assert "ULT_CRIT_DMG" in yq.modifiers, "on_become_target 施放时点判定挂"
        es = eng.pipeline.effective_stats(yq)
        assert math.isclose(es["crit_rate"], 0.05 + 0.6 + 0.2, rel_tol=1e-9)
        assert math.isclose(es["crit_dmg"], 0.5 + 0.5 + 0.3, rel_tol=1e-9)
        # 本发 crit 区 = 1+0.85×1.3=2.105；构成 = 大招 3.5 + 追击 0.5 + Icing 0.3
        crit_zone = 1 + 0.85 * 1.3
        assert math.isclose(hp1 - e1.current_hp,
                            (3.5 + 0.5 + 0.3) * YQ_ATK * Z * crit_zone, rel_tol=1e-9)
        # Sync 不在时放大：无 ULT_CRIT_DMG
        eng2 = _make(compiled)
        yq2 = _yq(eng2)
        yq2.current_energy = 140.0
        ult2 = next(x for x in eng2.actions_by_actor["1209"] if x.action_id == "120903")
        assert eng2._fire_ultimate(yq2, ult2) is True
        assert "ULT_CRIT_DMG" not in yq2.modifiers, "无 Sync 不授暴伤（施放时点判定）"


class TestFollowUpFreeze:
    def test_followup_freeze_and_dot(self, compiled):
        """追击冻结：mechanic_chance 0.65 expected 恒挂 + 回合开始附加 0.5×atk（lv10 #5）."""
        eng = _make(compiled)
        _cast(eng, "120902")
        e1 = eng.state.actors["e1"]
        assert "FREEZE" in e1.modifiers, "追击冻结 expected 恒触发"
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 0.5 * YQ_ATK * Z * 1.2, rel_tol=1e-9), (
            "冻结附加伤按彦卿挂后 crit 面板")


class TestEidolons:
    def test_e1_frozen_bonus(self):
        """E1：攻击冻结目标追加 60% ATK（_e1_lock 递归闩）；E0 无此钩对照."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        e1 = eng.state.actors["e1"]
        e1.modifiers["FREEZE"] = Modifier(
            modifier_id="FREEZE", name="Frozen", modifier_type="debuff", duration=1)
        hp1 = e1.current_hp
        eng.bus.emit("on_hp_decrease", {"amount": 100.0, "source": "1209",
                                        "reason": "hit", "target": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 0.6 * YQ_ATK * Z * 1.025, rel_tol=1e-9), (
            "E1 追加段（Sync 未挂 crit 1.025）")
        assert math.isclose(_yq(eng).resources["_e1_lock"], 0.0), "闩复位（递归防御）"
        eng0 = _make(compiled := compile_encounter(_build(), _STAGE,
                                                   template_roots=TEST_TEMPLATE_ROOTS))
        evs = [h.event for h in compiled.hooks if h.owner_id == "1209"]
        assert len(evs) == 9, "E0 无 E1 钩（归位实证）"
        _ = eng0

    def test_e2_err_gated(self):
        """E2：Sync 期 ERR +10% 门控双态."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        yq = _yq(eng)
        assert math.isclose(
            eng.pipeline.effective_stats(yq).get("energy_regen", 0.0), 1.0), "无 Sync 基线 1.0"
        _cast(eng, "120902")
        assert math.isclose(
            eng.pipeline.effective_stats(yq).get("energy_regen", 0.0), 1.1), "Sync 期 ERR+10%"

    def test_e4_res_pen_gated(self):
        """E4：血线 ≥80% 冰抗穿 +12% 双态；E0 面板无 res_pen（泄漏修复实证）."""
        eng = _make(compile_encounter(_build(eidolon=4), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        yq = _yq(eng)
        assert math.isclose(
            eng.pipeline.effective_stats(yq).get("res_pen", 0.0), 0.12, rel_tol=1e-9)
        yq.current_hp = yq.current_hp * 0.5
        assert math.isclose(
            eng.pipeline.effective_stats(yq).get("res_pen", 0.0), 0.0), "血线跌破即失效"
        eng0 = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        assert math.isclose(
            eng0.pipeline.effective_stats(_yq(eng0)).get("res_pen", 0.0), 0.0), "E0 无泄漏"

    def test_e6_kill_refresh(self):
        """E6：击杀→Sync/ULT crit 双件 refresh 续时（近似在案）；E0 无 on_kill 钩."""
        c6 = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        evs6 = [h.event for h in c6.hooks if h.owner_id == "1209"]
        assert evs6.count("on_kill") == 3, "E6 三件 on_kill 归位"
        eng = _make(c6)
        _cast(eng, "120902")
        yq = _yq(eng)
        yq.modifiers["SOULSTEEL_SYNC"].duration = 1
        eng.bus.emit("on_kill", {"source": "1209", "target": "e1",
                                 "action_id": "120902"}, eng.state)
        assert "SOULSTEEL_SYNC" in yq.modifiers, "击杀 refresh（近似在案）"


class TestTechnique:
    def test_tech_mark_true_dmg(self):
        """秘技：HP≥50% 敌挂 TECH_MARK + 彦卿攻击标记目标附加真伤 30%×原伤."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1209", "technique": "120907"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        e1 = eng.state.actors["e1"]
        assert "TECH_MARK" in e1.modifiers
        hp1 = e1.current_hp
        eng.bus.emit("on_hp_decrease", {"amount": 1000.0, "source": "1209",
                                        "reason": "hit", "target": "e1"}, eng.state)
        dealt = hp1 - e1.current_hp
        # 真伤：0.3×1000=300——rulebook true_damage 式（常规乘区不命中）
        assert math.isclose(dealt, 300.0, rel_tol=1e-9), "真伤 30%×原伤（青雀同族压缩）"
        assert math.isclose(_yq(eng).resources["_tech_lock"], 0.0), "闩复位"
