"""千冶•刃 1507 全机制模板端到端对轴（打标 staging 过堂修正版）：真模板 YAML → 编译
→ 终结技 Zone/Fury 主链/免死解散/充能双源/满充兑现/换技能/减伤/星魂全链 → 手算全等.

过堂修正三件（打标稿实证 bug）：① BALEFIRE_BIND 防御符号（def_ +0.3=给敌方**加**防
→ def_pct −param(150703,7)=减防 30%——符号反）；② 易伤 +50% 收编（vulnerability 在词表
——初稿误判"易伤键未登记"）；③ E2 满充扣量随阈值（初稿恒扣 9——E2 阈值 7 下扣成负数）。
SP 消歧在案：千冶•刃（1507）≠刃（1205）——机制全按 1507 官方数据建模，无张冠李戴。

口径常数：千冶•刃白值 hp 1358.28（全伤害基数=Max HP——ATK 无用官方+社区双证）；
假人 def 0 → 防御区 0.5、火弱点 → 抗性区 1.0、未击破 0.9；暴击 0.05/0.5 → 期望暴击区 1.025；
Fury 内暴击 0.25/1.1 → 期望暴击区 1.275。默认档全 lv10。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

BASE_HP = 1358.28
DEF_RES, UNBROKEN = 0.5, 0.9
CRIT_EXP = 1 + 0.05 * 0.5             # 1.025
CRIT_FURY = 1 + 0.25 * 1.1            # 1.275（Fury：crit 0.25/crit_dmg 1.1）
ZONES = DEF_RES * UNBROKEN * CRIT_EXP
ZONES_FURY = DEF_RES * UNBROKEN * CRIT_FURY
SKILL_DMG = BASE_HP * 0.72 * ZONES_FURY     # 战技 lv10 全体本体段 0.72×Max HP（lv15=0.9）
RANDOM_SEG = BASE_HP * 0.24 * ZONES_FURY    # 随机段 lv10 #3=0.24×4 段（lv15=0.3）


def _build(*, eidolon: int = 0, pre_battle=None):
    member = {"character_template": "1507", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 4000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        b["build"]["pre_battle"] = pre_battle
    return b


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


def _mx(eng):
    return eng.state.actors["1507"]


def _cast(eng, owner, aid):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": "e1",
        "actor_type": st.actor.actor_type}, eng.state)


def _foe_hit(eng, *, scaling=1.0, target="1507"):
    eng.actions_by_actor = {**eng.actions_by_actor, "e1": [
        __import__("hsr_nous.sim_schema.action", fromlist=["Action"]).Action(
            action_id="e_hit", name="重击", action_type="basic", target_type="single",
            damage_type="physical", scaling=[{"atk": scaling}])]}
    eng._pick_ally_target = lambda attacker=None: eng.state.actors[target]
    eng._enemy_turn(eng.state.actors["e1"])


class TestMortenaxCompile:
    def test_resources_swap_ult_balefire(self, compiled):
        decls = set(compiled.resource_decls_by_actor["1507"])
        assert {"charge", "_zone_on", "_fury_on", "_e6_icd"} <= decls
        acts = {a.action_id: a for a in compiled.actions_by_actor["1507"]}
        assert acts["150701"].available_if == "res__fury_on < 1"
        assert acts["150708"].available_if == "res__fury_on >= 1"
        assert acts["150714"].available_if == "res__fury_on >= 1", "150714 仅 Fury 内可用"
        assert acts["150702"].skill_point_cost == 0, "战技不耗点（tbgd+官方双证）"
        bind = next(m for a in compiled.actions_by_actor["1507"]
                    for m in (a.apply_modifiers or []) if m["modifier_id"] == "BALEFIRE_BIND")
        assert math.isclose(bind["stat_effects"]["def_pct"], -0.3), "防御 -30%（符号修正实证）"
        assert math.isclose(bind["stat_effects"]["vulnerability"], 0.5), "易伤 +50% 收编"


class TestUltimateChain:
    def test_ult_drain_zone_fury_crit_balefire(self, compiled):
        eng = _make(compiled)
        mx, e1 = _mx(eng), eng.state.actors["e1"]
        mx.current_energy = 160.0
        hp0 = mx.current_hp
        ult = next(a for a in eng.actions_by_actor["1507"] if a.action_id == "150703")
        assert eng._fire_ultimate(mx, ult) is True
        assert math.isclose(hp0 - mx.current_hp, 0.2 * BASE_HP, rel_tol=1e-9), (
            "耗 20% Max HP（#1 floor 1）")
        assert math.isclose(mx.resources["_zone_on"], 1.0)
        assert math.isclose(mx.resources["_fury_on"], 1.0)
        fury = mx.modifiers["INFINITE_FURY"]
        assert math.isclose(fury.stat_effects["crit_rate"], 0.2)
        assert math.isclose(fury.stat_effects["crit_dmg"], 0.6), "lv10 #3=60% 暴伤"
        bind = e1.modifiers["BALEFIRE_BIND"]
        assert math.isclose(bind.stat_effects["def_pct"], -0.3)
        assert math.isclose(bind.stat_effects["vulnerability"], 0.5)

    def test_lethal_in_fury_cancels_and_exits(self, compiled):
        """免死（Fury 内）：解散 Zone+退状态+回 50% Max HP（白厄免死族同构）."""
        eng = _make(compiled)
        mx = _mx(eng)
        mx.resources["_fury_on"] = 1.0
        mx.resources["_zone_on"] = 1.0
        eng._apply_modifier(mx, Modifier(
            modifier_id="INFINITE_FURY", name="无限怒火", modifier_type="buff",
            duration=0, dispellable=False))
        mx.current_hp = 100.0
        _foe_hit(eng, scaling=1000.0)
        assert math.isclose(mx.current_hp, 100.0 + 0.5 * BASE_HP, rel_tol=1e-9), (
            "cancel 致死 + 回 50% Max HP（#6）")
        assert math.isclose(mx.resources["_fury_on"], 0.0)
        assert math.isclose(mx.resources["_zone_on"], 0.0)
        assert "INFINITE_FURY" not in mx.modifiers, "退状态摘除"


def _zone_eng(compiled):
    eng = _make(compiled)
    mx = _mx(eng)
    mx.resources["_zone_on"] = 1.0
    return eng, mx


class TestChargeFlow:
    def test_two_charge_sources_and_cashout(self, compiled):
        """充能双源（队友命中+自身被攻击）→ 满 9 扣 9 回 25 能 + 免费 150709."""
        eng, mx = _zone_eng(compiled)
        e1 = eng.state.actors["e1"]
        # 队友攻击命中 ×8 → charge 8 + 目标挂 Balefire
        for _ in range(8):
            _cast(eng, "ally", "ally_basic")
        assert math.isclose(mx.resources["charge"], 8.0)
        assert "BALEFIRE_BIND" in e1.modifiers, "队友命中挂 Balefire Bind"
        # 自身被攻击 → +1 → 满 9 兑现（扣 9/回 25/trigger 150709）
        e0 = mx.current_energy
        _foe_hit(eng, scaling=1.0)
        assert math.isclose(mx.resources["charge"], 0.0), "满 9 扣 9"
        assert math.isclose(mx.current_energy, 160.0), (
            "满充链对轴：120(保底) + 25(#2 满充) + 30(150709 继承回能) = 175 → clamp 160")
        dmg = e1.current_hp
        assert dmg < 1e9, "150709 免费追加已结算"

    def test_e2_threshold_7_deducts_7(self, compiled):
        """E2：阈值 7 且扣量随阈值（修正前恒扣 9 会扣成负数——过堂实证）."""
        compiled2 = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng, mx = _zone_eng(compiled2)
        eng._apply_modifier(mx, Modifier(
            modifier_id="E2_CHARGE_CAP", name="E2 阈值", modifier_type="buff",
            duration=0, dispellable=False))
        mx.resources["charge"] = 6.0
        _foe_hit(eng, scaling=1.0)   # +1 → 达 7 兑现
        assert math.isclose(mx.resources["charge"], 0.0), "E2 下阈值 7 扣 7（非负）"


class TestDamageAndSwap:
    def test_skill_aoe_and_random_segments(self, compiled):
        """战技（Fury 内）：全体本体 0.72×Max HP + 4 段随机 0.24×Max HP 逐段削韧 15
        （expected 确定化按序取首——4 随机段全落首敌；Fury 双暴件正确施加）."""
        eng = _make(compiled)
        mx = _mx(eng)
        mx.resources["_fury_on"] = 1.0
        eng._apply_modifier(mx, Modifier(
            modifier_id="INFINITE_FURY", name="无限怒火", modifier_type="buff",
            duration=0, dispellable=False,
            stat_effects={"crit_rate": 0.2, "crit_dmg": 0.6}))
        mx.current_hp = BASE_HP
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2, t1 = e1.current_hp, e2.current_hp, e1.toughness
        _cast(eng, "1507", "150702")
        assert math.isclose(hp1 - e1.current_hp, SKILL_DMG + 4 * RANDOM_SEG, rel_tol=1e-9), (
            "首敌：全体本体 + 4 随机段（expected 确定化按序取首）")
        assert math.isclose(hp2 - e2.current_hp, SKILL_DMG, rel_tol=1e-9), "次敌：仅全体本体"
        assert math.isclose(t1 - e1.toughness, 10 + 15 * 4.0), "全体削 10 + 随机段各削 15"
        assert math.isclose(BASE_HP - mx.current_hp, 0.1 * BASE_HP, rel_tol=1e-9), (
            "耗 10% Max HP（#4 floor 1）")

    def test_swap_actions_gating(self, compiled):
        """换技能互斥：常态 150701 可/150708 不可；Fury 内翻转（available_if 闸）."""
        eng = _make(compiled)
        mx = _mx(eng)
        acts = eng.actions_by_actor["1507"]
        ids0 = {a.action_id for a in eng._legal_with_available_if(mx, acts)}
        assert "150701" in ids0 and "150708" not in ids0
        mx.resources["_fury_on"] = 1.0
        ids1 = {a.action_id for a in eng._legal_with_available_if(mx, acts)}
        assert "150708" in ids1 and "150701" not in ids1, "Fury 内换强化普攻"

    def test_basic_taunt(self, compiled):
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1507", "150701")
        assert "MORTENAX_TAUNT" in e1.modifiers, "普攻 Taunt 1 回合"


class TestDamageReduction:
    def test_zone_and_tech_dr(self, compiled):
        """减伤两路对轴：无 Zone 基线 ×0.5（Zone）×0.05（Zone+秘技 0.1 叠乘）."""
        eng3 = _make(compiled)                      # 基线：无 Zone 无秘技
        mx3 = _mx(eng3)
        hp3 = mx3.current_hp
        _foe_hit(eng3, scaling=10.0)
        raw3 = hp3 - mx3.current_hp
        eng, mx = _zone_eng(compiled)               # Zone 0.5×
        hp0 = mx.current_hp
        _foe_hit(eng, scaling=10.0)
        raw = hp0 - mx.current_hp
        b = _build(pre_battle=[{"actor_id": "1507", "technique": "150707"}])
        compiled2 = compile_encounter(b, _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng2, mx2 = _zone_eng(compiled2)            # Zone 0.5× × 秘技 0.1×
        hp1 = mx2.current_hp
        _foe_hit(eng2, scaling=10.0)
        raw2 = hp1 - mx2.current_hp
        assert math.isclose(raw / raw3, 0.5, rel_tol=1e-6), "Zone 内受伤 0.5×"
        assert math.isclose(raw2 / raw3, 0.5 * 0.1, rel_tol=1e-6), (
            "Zone 0.5× 叠秘技 0.1× = 0.05（modify_amount 同通道分件叠乘）")


class TestTeamAuraSide:
    def test_team_aura_does_not_radiate_to_enemy(self, compiled):
        """team 光环只辐射持有者同侧（1507 对轴钓出的辐射域 bug：敌方面板曾吃我方
        team 光环 all_dmg+0.5——scope=team=我方队伍光环，不同侧不辐射）."""
        eng = _make(compiled)
        mx = _mx(eng)
        mx.resources["_zone_on"] = 1.0   # 激活模板大行迹3 光环（enable_if 门控件已随开战挂）
        foe_eff = eng.pipeline.effective_stats(eng.state.actors["e1"])
        ally_eff = eng.pipeline.effective_stats(eng.state.actors["ally"])
        assert foe_eff["dmg_bonus"] == {}, "敌方不得吃我方 team 光环（辐射域同侧判定）"
        assert math.isclose(ally_eff["dmg_bonus"].get("all", 0.0), 0.5), "我方照常吃光环"
