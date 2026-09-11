"""丹恒•腾荒（1414）龙灵全族端到端对轴：真模板 YAML → 编译 → 召唤/165 速行动/净化/护盾/强化追击/消失全链 → 手算全等.

链：T1 战技（同袍自指 + 神秀快照 + 全队护盾 + 召唤龙灵）→ 龙灵 165 速上行动条
→ 龙灵行动（净化全体 1 负面 LIFO + 全体护盾 10%+200 + 峥嵘最低护盾补盾 5%+100）
→ 开大（强化计数 2 层）→ 强化龙灵行动（物理 AoE 80% atk + 削韧 20，逐次耗层）
→ 同袍阵亡 → 龙灵消失；地坼秘技进战全件。数值全按 expected 模式手算对轴（lv10 档）。

口径常数：丹恒有效攻击 = 582.12×1.28 = 745.1136（行迹 atk_pct 28% 初始 modifier）；
神秀快照后 = 856.88064（自指场景——神秀先于护盾挂上，同 test_terra_template 口径）；
假人 def 0 → 防御区 0.5、物理弱点 → 抗性区 1.0、未击破 0.9；丹恒暴击 0.05/0.5 → 期望暴击区 1.025。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests._data_env import data_available, data_skip_reason
from tests.template_materialize import TEST_TEMPLATE_ROOTS

pytestmark = pytest.mark.skipif(not data_available(), reason=data_skip_reason())

TERRA_ATK_EFF = 582.12 * 1.28          # 745.1136
PANEL = TERRA_ATK_EFF * 1.15           # 856.88064（含神秀快照的自指面板）
SHIELD_SKILL = PANEL * 0.2 + 400       # 571.376128（战技/终结技/秘技同式）
SHIELD_DRAGON = PANEL * 0.1 + 200      # 285.688064（141404 龙灵行动护盾）
SHIELD_ZR = PANEL * 0.05 + 100         # 142.844032（1414103 峥嵘补盾）
FUA_BASE = PANEL * 0.8                 # 685.504512（强化龙灵追击基数）
FUA_DMG = FUA_BASE * 0.5 * 1.0 * 0.9 * 1.025   # 316.18896（防御/抗性/未击破/期望暴击）
DH_AV = 10000 / 102                    # 98.0392（丹恒 102 速）
DH_T1 = DH_AV * 0.6                    # 58.8235（葳蕤开局提前 40%）
DRAGON_AV = 10000 / 165                # 60.6061（龙灵 165 速）


def _build(*, pre_battle=None, ult_rule=True):
    rules = []
    if ult_rule:
        rules.append({"condition": "energy >= max_energy", "action": "ultimate", "priority": 90})
    rules += [
        {"condition": "true", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0},
    ]
    b = {"build": {"team": [
        {"character_template": "1414", "level": 80},
        {"actor_id": "ally", "name": "火攻手", "inline": True,
         "base_stats": {"atk": 2000, "spd": 80, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
    ], "policy": {"name": "p", "action_rules": rules}}}
    if pre_battle:
        b["build"]["pre_battle"] = pre_battle
    return b


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 100,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 800}}}


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=10)
    eng.setup()
    return eng


def _step_until(eng, pred, limit=40):
    """推进到 pred(rec) 命中的回合（含本拍）并返回该拍记录."""
    for _ in range(limit):
        rec = eng.step()
        if rec is None:
            break
        if pred(rec):
            return rec
    raise AssertionError("推进预算内未等到目标回合")


class TestSouldragonCompile:
    def test_summon_def_action_and_technique_registered(self):
        compiled = compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        sd = compiled.summon_defs["1414_souldragon"]
        assert sd.owner_id == "1414" and math.isclose(sd.actor.stats.spd, 165.0), (
            "141404 #5：龙灵初始速度 165（spd 不被继承覆写——列表化继承）")
        assert isinstance(sd.inheritance, tuple) and "spd" not in sd.inheritance
        acts = {a.action_id: a for a in compiled.actions_by_actor["1414_souldragon"]}
        assert "souldragon_act" in acts and acts["souldragon_act"].energy_gain == 0
        ult = next(a for a in compiled.actions_by_actor["1414"] if a.action_id == "141403")
        assert ult.toughness_dmg == 20, "终结技削韧 20（米游社/fandom 权威源改正）"


class TestSummonAndAvWalk:
    def test_summon_on_bondmate_and_165spd_first_turn(self):
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        enters = []
        eng.bus.subscribe("actor_enter", lambda et, p, ctx: enters.append(dict(p)))
        rec = _step_until(eng, lambda r: r["actor_id"] == "1414")          # T1 战技
        assert math.isclose(rec["clock"], DH_T1, rel_tol=1e-3), "葳蕤提前 40% 后 T1 时刻"
        assert eng.state.actors["1414_souldragon"].alive, "成为同袍即召唤龙灵（141404）"
        assert enters and enters[0]["actor"] == "1414_souldragon" and enters[0]["reason"] == "summon"
        rec = _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        assert math.isclose(rec["clock"], DH_T1 + DRAGON_AV, rel_tol=1e-3), (
            f"龙灵 165 速：召唤后 {DRAGON_AV:.4f} AV 首动（实得 {rec['clock']:.4f}）")

    def test_weiwei_advance_15pct_on_bondmate_action(self):
        """葳蕤：同袍（自指丹恒）行动 → 龙灵提前 15%（全行动条 15%——T2 战技后时刻对轴）."""
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        s1 = _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        t2 = _step_until(eng, lambda r: r["actor_id"] == "1414" and r["clock"] > s1["clock"])
        s2 = _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        # T2 战技（同袍攻击）提前 15%：S2 = S1 + 龙灵AV − 0.15×龙灵AV（余程充足，全额生效）
        exp = s1["clock"] + DRAGON_AV * 0.85
        assert math.isclose(s2["clock"], exp, rel_tol=1e-3), (
            f"葳蕤提前 15%：{s1['clock']:.2f} → {s2['clock']:.2f}（期望 {exp:.2f}）")
        assert s2["clock"] > t2["clock"], "提前后仍排在 T2 之后（余程未归零）"


class TestSouldragonActionSettlement:
    def _drive_first_dragon_action(self, eng):
        return _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")

    def test_purify_one_debuff_per_ally_lifo(self):
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        dh, ally = eng.state.actors["1414"], eng.state.actors["ally"]
        for st, mids in ((dh, ("D_OLD", "D_NEW")), (ally, ("D_X",))):
            for mid in mids:
                eng._apply_modifier(st, Modifier(
                    modifier_id=mid, name=mid, modifier_type="debuff", duration=2))
        eng._apply_modifier(dh, Modifier(
            modifier_id="D_LOCK", name="D_LOCK", modifier_type="debuff",
            duration=2, dispellable=False))
        self._drive_first_dragon_action(eng)
        assert "D_NEW" not in dh.modifiers and "D_X" not in ally.modifiers, (
            "龙灵行动：每人净化 1 个负面（141404 #6，LIFO 最新先摘）")
        assert "D_OLD" in dh.modifiers, "每人 1 个——早挂的保留"
        assert "D_LOCK" in dh.modifiers, "不可驱散件不命中（§4.6）"

    def test_dragon_shield_and_zhengrong_lowest_topup(self):
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        ally = eng.state.actors["ally"]
        _step_until(eng, lambda r: r["actor_id"] == "1414")               # T1 战技（自指）
        ally.shields.clear()                                              # 压低 ally 护盾值 → 最低
        self._drive_first_dragon_action(eng)
        for aid in ("1414", "ally", "1414_souldragon"):
            st = eng.state.actors[aid]
            mod = st.modifiers.get("TERRA_SHIELD_DRAGON")
            # 龙灵自身=施加当拍末走字（owner_turn_end 锚）：3→2，官方"持续 3 回合"覆盖
            # 本次+后两次行动在案；队友侧未到自己回合仍 3
            exp_dur = 2 if aid == "1414_souldragon" else 3
            assert mod is not None and mod.duration == exp_dur, (
                f"{aid} 龙灵行动护盾时长（实得 {mod and mod.duration}，期望 {exp_dur}）")
            sh = next((s for s in st.shields if s.modifier_id == "TERRA_SHIELD_DRAGON"), None)
            assert sh is not None and math.isclose(sh.remaining, SHIELD_DRAGON, rel_tol=1e-3), (
                f"{aid} 护盾 = 10%×{PANEL:.4f}+200 = {SHIELD_DRAGON:.4f}（实得 "
                f"{sh and sh.remaining}）——挂丹恒侧读现场面板")
        zr = next((s for s in ally.shields if s.modifier_id == "TERRA_SHIELD_ZHENGRONG"), None)
        assert zr is not None and math.isclose(zr.remaining, SHIELD_ZR, rel_tol=1e-3), (
            f"峥嵘补盾落在护盾值最低的 ally：5%×{PANEL:.4f}+100 = {SHIELD_ZR:.4f}")
        dh_zr = [s for s in eng.state.actors["1414"].shields
                 if s.modifier_id == "TERRA_SHIELD_ZHENGRONG"]
        assert not dh_zr, "峥嵘仅补最低者（丹恒护盾未压低，不中）"


class TestEnhancedFollowUp:
    def test_ult_enhances_two_dragon_actions_then_expires(self):
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        e1 = eng.state.actors["e1"]
        hits: list = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: hits.append(dict(p)))
        s1 = _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        tgh0 = e1.toughness
        assert not any(h.get("damage_type") == "physical" and h.get("source") == "1414"
                       for h in hits), "未强化：龙灵首行动无追击"
        dh = eng.state.actors["1414"]
        dh.current_energy = 105.0    # 战技 +30 → 满能当拍窗口开大（自然流——直接灌 135 会让
                                     # 窗口/回合行动双路各放一次终结技，测试架 artifact 避开）
        _step_until(eng, lambda r: r["actor_id"] == "1414" and r["clock"] > s1["clock"])
        enh = dh.modifiers.get("TERRA_ULT_ENH")
        assert enh is not None and enh.stacks == 2, "开大授强化计数 2 层（141403 #3）"
        assert math.isclose(e1.toughness, tgh0 - 20), "终结技 AoE 削韧 20（米游社口径）"
        # 强化行动 1：物理追击 + 削韧 20 + 耗 1 层
        _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        fua = [h for h in hits if h.get("source") == "1414" and h.get("damage_type") == "physical"
               and h.get("reason") == "hit"]
        assert fua and math.isclose(fua[-1]["amount"], FUA_DMG, rel_tol=1e-3), (
            f"强化追击 = 80%×{PANEL:.4f}×乘区 = {FUA_DMG:.4f}（实得 "
            f"{fua and fua[-1]['amount']}）")
        assert math.isclose(e1.toughness, tgh0 - 40), "追击削韧 20（fandom Souldragon 20）"
        assert dh.modifiers["TERRA_ULT_ENH"].stacks == 1
        # 强化行动 2：再追击 + 耗尽
        _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        assert math.isclose(e1.toughness, tgh0 - 60)
        assert dh.modifiers["TERRA_ULT_ENH"].stacks == 0, "2 次强化行动耗尽（141403 #3）"
        # 第 3 次龙灵行动：无追击
        n_hits = len([h for h in hits if h.get("source") == "1414"
                      and h.get("damage_type") == "physical" and h.get("reason") == "hit"])
        _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        fua = [h for h in hits if h.get("source") == "1414" and h.get("damage_type") == "physical"
               and h.get("reason") == "hit"]
        assert len(fua) == n_hits, "强化耗尽后龙灵行动不再追击"


class TestDismissAndTechnique:
    def test_bondmate_death_dismisses_and_resummon(self):
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        ally = eng.state.actors["ally"]
        _step_until(eng, lambda r: r["actor_id"] == "1414")               # T1 战技（自指丹恒）
        dragon = eng.state.actors["1414_souldragon"]
        assert dragon.alive
        dh = eng.state.actors["1414"]
        dh.current_hp = 0.0                                               # 同袍=丹恒（自指）
        eng._check_death(dh, "e1")
        assert not dragon.alive, ("同袍无法战斗 → 龙灵消失（141404 末句；本场景同袍=丹恒，"
                                  "owner 死亡联动 + actor_exit 双通道同指）")
        exits = [l for l in eng.state.log if "龙灵 离场" in l]
        assert exits, f"离场日志缺失：{eng.state.log[-5:]}"

    def test_bondmate_death_dismisses_ally_case(self):
        """同袍=队友阵亡：actor_exit 通道摘龙灵（与 owner 死亡内建区分）."""
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        dh, ally = eng.state.actors["1414"], eng.state.actors["ally"]
        # 手动战技指 ally（_execute_action 不发 on_action——调用方补发，同 _run_turn 口径）
        a = next(x for x in eng.actions_by_actor["1414"] if x.action_id == "141402")
        eng._execute_action(dh, a)
        eng.bus.emit("on_action", {"actor": "1414", "action_type": "skill",
                                   "action_id": "141402", "target_type": "ally_single",
                                   "target": "ally", "actor_type": "character"}, eng.state)
        assert "TONGPAO" in ally.modifiers and eng.state.actors["1414_souldragon"].alive
        ally.current_hp = 0.0
        eng._check_death(ally, "e1")
        assert not eng.state.actors["1414_souldragon"].alive, (
            "同袍（队友）阵亡 → 龙灵消失（actor_exit reason=death + TONGPAO 识别）")
        assert dh.alive, "丹恒未倒——离场不走 owner 联动"

    def test_technique_earthrend_battle_start_full_pack(self):
        compiled = compile_encounter(
            _build(pre_battle=[{"actor_id": "1414", "technique": "141407"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        dh = eng.state.actors["1414"]
        assert "TONGPAO" in dh.modifiers, "地坼：同袍自指建模（sim 无前台概念在案）"
        assert "TERRA_SHENXIU" in dh.modifiers, "自动战技全件：神秀快照"
        sh = next((s for s in dh.shields if s.modifier_id == "TERRA_SHIELD"), None)
        assert sh is not None and math.isclose(sh.remaining, SHIELD_SKILL, rel_tol=1e-3), (
            f"自动战技全队护盾 20%+400 = {SHIELD_SKILL:.4f}（神秀先挂，自指面板 {PANEL:.4f}）")
        assert math.isclose(dh.current_energy, 30.0), "自动战技=真施放：回能 30（仅免战技点）"
        assert eng.state.actors["1414_souldragon"].alive, "成为同袍 → 进战即召唤龙灵"
        assert eng.state.skill_points == 10, "不耗战技点（官方 without consuming any Skill Points）"
