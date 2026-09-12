"""景元 1204 全机制模板端到端对轴（打标 staging 过堂修正版）：真模板 YAML → 编译
→ 开战召唤神君/段数计数/段速公式/战技终结技加段/神君分段弹射/秘技首回合加段/星魂全链 → 手算全等.

过堂修正三件（打标稿实证 bug）：① LORD_SPD 段速公式（draft 写 10×(3+hits) 开局 30 误
——官方"基础速度 60，每叠加一段 +10"=60+增量×10，base_stats.spd=60 承载基础值）；
② E6 易伤键 dmg_taken（未知 stat 键=静默死键）→ vulnerability 0.12；
③ WAR_MARSHAL crit_rate 字面量归 stat_effects（stat_exprs 是动态求值槽，通道误用）。

口径常数：景元白值 atk 698.544（无行迹攻击节点——神君烘焙同源）；
假人 def 0 → 防御区 0.5、雷弱点 → 抗性区 1.0、未击破 0.9；暴击 0.05/0.5 → 期望暴击区 1.025。
神君基础段数 3、基础速度 60、每段削韧 5、每段倍率 lv10 #2=1.0。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

JY_ATK = 698.544
DEF_RES, UNBROKEN = 0.5, 0.9
CRIT_EXP = 1 + 0.05 * 0.5             # 1.025
ZONES = DEF_RES * UNBROKEN * CRIT_EXP
SEG_DMG = JY_ATK * 0.66 * ZONES       # 神君每段 lv10 #2=0.66×景元 ATK（lv15=1.0）


def _build(*, eidolon: int = 0, pre_battle=None):
    member = {"character_template": "1204", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"build": {"team": [member],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        b["build"]["pre_battle"] = pre_battle
    return b


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _jy(eng):
    return eng.state.actors["1204"]


def _lord(eng):
    return eng.state.actors.get("1204_lord")


def _cast(eng, owner, aid):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": "e1",
        "actor_type": st.actor.actor_type}, eng.state)


class TestJingyuanCompile:
    def test_summon_actions_resources(self, compiled):
        sd = compiled.summon_defs["1204_lord"]
        assert sd.inheritance == "none" and sd.control == "auto", "神君独立面板+全自动"
        assert math.isclose(sd.actor.stats.spd, 60.0), "基础速度 60（120404 #1）"
        assert math.isclose(sd.actor.stats.atk, JY_ATK), "面板=景元白值烘焙（官方倍率基数）"
        decls = set(compiled.resource_decls_by_actor["1204"]) | \
            set(compiled.resource_decls_by_actor.get("1204_lord", {}))
        assert {"_tech_armed", "lord_hits"} <= decls
        acts = {a.action_id: a for a in compiled.actions_by_actor["1204"]}
        assert acts["120402"].skill_point_cost == 1 and acts["120403"].energy_cost == 130
        lord_acts = {a.action_id: a for a in compiled.actions_by_actor["1204_lord"]}
        assert lord_acts["120404"].action_type == "follow_up", "天赋类攻击归 follow_up"


class TestBattleStartAndSegments:
    def test_lord_summoned_and_base_segments(self, compiled):
        eng = _make(compiled)
        lord = _lord(eng)
        assert lord is not None, "开战未召唤神君"
        assert math.isclose(lord.resources["lord_hits"], 0.0), "段数增量从零起"
        e1 = eng.state.actors["e1"]
        hp1, t1 = e1.current_hp, e1.toughness
        _cast(eng, "1204_lord", "120404")
        assert math.isclose(hp1 - e1.current_hp, 3 * SEG_DMG, rel_tol=1e-9), (
            "基础 3 段×1.0×景元 ATK（expected 随机确定化全落首敌）")
        assert math.isclose(t1 - e1.toughness, 3 * 5.0), "每段削韧 5"
        assert math.isclose(lord.resources["lord_hits"], 0.0), "行动末段数清零"

    def test_skill_and_ult_add_segments(self, compiled):
        eng = _make(compiled)
        lord = _lord(eng)
        _cast(eng, "1204", "120402")
        assert math.isclose(lord.resources["lord_hits"], 2.0), "战技 +2 段（120402 #2=2）"
        jy = _jy(eng)
        jy.current_energy = 130.0
        ult = next(a for a in eng.actions_by_actor["1204"] if a.action_id == "120403")
        eng._fire_ultimate(jy, ult)
        assert math.isclose(lord.resources["lord_hits"], 5.0), "终结技再 +3 段（120403 #2=3）"
        # 段速：60 + 增量 5×10 = 110（公式修正实证）
        eff = eng.pipeline.effective_stats(lord)
        assert math.isclose(eff["spd"], 60.0 + 10 * 5.0, rel_tol=1e-9), (
            "段速 = 60 + 增量×10（draft 10×(3+hits) 公式误读修正实证）")
        # 满 6 段暴伤件激活（Battalia Crush enable_if 门控——res_ 平铺条件域实证）
        crush = lord.modifiers.get("LORD_BATTALIA_CRUSH")
        assert crush is not None
        # 神君行动：3+5=8 段（基础 3 + 条件 ≥4..≥8 共 5 段额外）
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1204_lord", "120404")
        assert math.isclose(hp1 - e1.current_hp, 8 * SEG_DMG / CRIT_EXP * 1.0375, rel_tol=1e-9), (
            "8 段 = 基础 3 + 增量 5，全段吃 Battalia Crush 暴伤 +0.25（3+5≥6 门控实证）")


class TestTechnique:
    def test_tech_armed_first_turn_plus_3(self):
        """秘技：神君首回合 +3 段（读到闩）+ 回合末清闩（不再加）."""
        b = _build(pre_battle=[{"actor_id": "1204", "technique": "120407"}])
        compiled = compile_encounter(b, _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        jy = _jy(eng)
        assert math.isclose(jy.resources["_tech_armed"], 1.0), "秘技进战武装"
        eng.bus.emit("on_turn_start", {"actor": "1204_lord"}, eng.state)
        lord = _lord(eng)
        assert math.isclose(lord.resources["lord_hits"], 3.0), "首回合 +3 段"
        eng.bus.emit("on_turn_end", {"actor": "1204_lord"}, eng.state)
        assert math.isclose(jy.resources["_tech_armed"], 0.0), "回合末清闩"
        lord.resources["lord_hits"] = 0.0
        eng.bus.emit("on_turn_start", {"actor": "1204_lord"}, eng.state)
        assert math.isclose(lord.resources["lord_hits"], 0.0), "清闩后不再加"


class TestEidolon2And6:
    def test_e2_lord_turn_end_team_dmg(self):
        """E2：神君行动结束 → 景元 all_dmg +0.2 两回合（作用域超范围含 follow_up 在案）."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        eng.bus.emit("on_turn_end", {"actor": "1204_lord"}, eng.state)
        jy = _jy(eng)
        assert math.isclose(jy.modifiers["S2_SKY_SQUASHED"].stat_effects["all_dmg"], 0.2)

    def test_e0_no_vulnerable(self, compiled):
        """E0：神君命中不挂易伤（E6 钩已归 E6 块——draft 错挂常驻致 E0 也生效的实证）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1204_lord", "120404")
        assert "S6_LORD_VULNERABLE" not in e1.modifiers, "E0 不得挂 E6 易伤"
        assert math.isclose(hp1 - e1.current_hp, 3 * SEG_DMG, rel_tol=1e-9), (
            "E0 三段同倍率 0.66（无易伤递增）")

    def test_e6_vulnerable_stacks(self):
        """E6：首段挂易伤 +0.12 → 后段吃 vuln（首段 0.66×1.0 / 后段 0.66×1.12 对轴）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1204_lord", "120404")
        vul = e1.modifiers.get("S6_LORD_VULNERABLE")
        assert vul is not None, "E6 易伤未挂"
        assert math.isclose(vul.stat_effects["vulnerability"], 0.12), (
            "易伤 +12%（dmg_taken 未知键修正为 vulnerability 实证）")
        seg_e6 = JY_ATK * 0.726 * ZONES   # E6 含 E5 天赋+2 → 段倍率实取 lv12=0.726（随档实证）
        assert math.isclose(hp1 - e1.current_hp, seg_e6 + 2 * seg_e6 * 1.12, rel_tol=1e-9), (
            "首段无易伤 + 后两段吃 +12%（同事件快照：易伤挂在首段结算后；E5 随档 0.726）")


class TestWarMarshalAndEnergy:
    def test_war_marshal_and_seg_energy(self, compiled):
        """战技后暴击率 +10%（stat_effects 归位实证）；神君每段命中 → 景元回能 2."""
        eng = _make(compiled)
        jy = _jy(eng)
        _cast(eng, "1204", "120402")
        assert math.isclose(jy.modifiers["WAR_MARSHAL"].stat_effects["crit_rate"], 0.1)
        e0 = jy.current_energy
        _cast(eng, "1204_lord", "120404")
        assert math.isclose(jy.current_energy, e0 + 5 * 2.0), (
            "每段命中回能 2（E4 通道）：3 基础段 + 战技加 2 段 = 5 段 → +10")
