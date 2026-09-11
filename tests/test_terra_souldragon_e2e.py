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
               and h.get("reason") == "hit" and h.get("action_type") == "follow_up"]
        assert fua and math.isclose(fua[-1]["amount"], FUA_DMG, rel_tol=1e-3), (
            f"强化追击 = 80%×{PANEL:.4f}×乘区 = {FUA_DMG:.4f}（实得 "
            f"{fua and fua[-1]['amount']}）")
        # 同袍自指 → 两笔附加段同为 physical（属性随同袍）：AoE 80% + 峥嵘单体 40%（同袍 atk=自指面板）
        add_seg = [h for h in hits if h.get("source") == "1414" and h.get("reason") == "hit"
                   and h.get("action_type") == "additional"]
        assert len(add_seg) == 2 and all(h["damage_type"] == "physical" for h in add_seg), (
            "同袍自指：附加段属性随之为 physical（动态元素——异元素同袍场景见 TestBondmateElementalSegments）")
        assert math.isclose(add_seg[0]["amount"], FUA_DMG, rel_tol=1e-3), (
            "同袍附加 AoE = 80%×自指面板（141403 #8——自指与物理追击同值）")
        assert math.isclose(add_seg[1]["amount"], FUA_DMG / 2, rel_tol=1e-3), (
            "峥嵘强化段 = 40%×自指面板（1414103 #1——恰为 80% 档之半）")
        assert math.isclose(e1.toughness, tgh0 - 40), "追击削韧 20（fandom Souldragon 20）"
        assert dh.modifiers["TERRA_ULT_ENH"].stacks == 1
        # 强化行动 2：再追击 + 耗尽
        _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        assert math.isclose(e1.toughness, tgh0 - 60)
        assert dh.modifiers["TERRA_ULT_ENH"].stacks == 0, "2 次强化行动耗尽（141403 #3）"
        # 第 3 次龙灵行动：无追击（附加段同灭——同一强化计数门控）
        n_hits = len([h for h in hits if h.get("source") == "1414"
                      and h.get("damage_type") == "physical" and h.get("reason") == "hit"])
        _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        fua = [h for h in hits if h.get("source") == "1414" and h.get("damage_type") == "physical"
               and h.get("reason") == "hit"]
        assert len(fua) == n_hits, "强化耗尽后龙灵行动不再追击（附加段同灭）"


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


class TestShieldAccumulateCap:
    """护盾叠加封顶（141402 #4 / 141403 #7 / 141404 #4 / 1414103 #4——accumulate/cap 首实例）：
    四源同池 PERMANSON_SHIELD 跨件加算 + 授予时 3×当前战技护盾量动态封顶（04_modifier §4.15）."""

    CAP = SHIELD_SKILL * 3                     # 1714.128384（3×当前战技护盾量）

    @staticmethod
    def _cast_skill(eng):
        dh = eng.state.actors["1414"]
        a = next(x for x in eng.actions_by_actor["1414"] if x.action_id == "141402")
        eng._execute_action(dh, a)
        eng.bus.emit("on_action", {
            "actor": "1414", "action_type": a.action_type, "action_id": "141402",
            "target_type": a.target_type, "target": "1414", "actor_type": "character"}, eng.state)

    @staticmethod
    def _dragon_act(eng):
        """直接发射龙灵行动事件（净化 + 全体护盾 + 峥嵘补盾同 hook 链；峥嵘落护盾最低者——
        战技盾全体皆有，平手时按池序落编队首丹恒，各测试手算口径在案）."""
        eng.bus.emit("on_action", {
            "actor": "1414_souldragon", "action_type": "memosprite_skill",
            "action_id": "souldragon_act", "target_type": "self",
            "target": "1414_souldragon", "actor_type": "summon"}, eng.state)

    @staticmethod
    def _pool(eng, aid="1414"):
        return sum(s.remaining for s in eng.state.actors[aid].shields
                   if s.pool == "PERMANSON_SHIELD")

    @staticmethod
    def _inst(eng, mid, aid="1414"):
        return next((s for s in eng.state.actors[aid].shields if s.modifier_id == mid), None)

    def test_same_modifier_regrant_accumulates(self):
        """同 modifier 重复获得 = 旧剩余并入新实例（非整换——官方"重复获得可叠加"）."""
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        self._cast_skill(eng)
        self._cast_skill(eng)
        sh = self._inst(eng, "TERRA_SHIELD")
        assert sh is not None and math.isclose(sh.remaining, SHIELD_SKILL * 2), (
            f"两次战技护盾并入同一实例：{sh and sh.remaining}（期望 {SHIELD_SKILL * 2}）")
        assert math.isclose(self._pool(eng), SHIELD_SKILL * 2)
        assert len([s for s in eng.state.actors["1414"].shields
                    if s.modifier_id == "TERRA_SHIELD"]) == 1, "同 modifier 一盾一件"

    def test_cross_source_pool_and_cap_truncation(self):
        """跨件加算到帽：战技 + 龙灵×2 + 峥嵘 + 终结技 = 恰满 3v；再授予截断留痕池量不动.

        手算口径：战技盾全体皆有 → 首次龙灵行动后丹恒/ally 池量平手，峥嵘落编队首丹恒
        （丹恒池 = v + 2d + z）；终结技同 modifier 并入已先被帽截一次（room < 2v）。
        """
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        dh = eng.state.actors["1414"]
        self._cast_skill(eng)                       # TS = v
        self._dragon_act(eng)                       # DR = d + ZR 落丹恒（平手编队首）
        self._dragon_act(eng)                       # DR = 2d；ZR 落 ally（丹恒池更高）
        assert math.isclose(self._pool(eng), SHIELD_SKILL + SHIELD_DRAGON * 2 + SHIELD_ZR)
        dh.current_energy = 135.0
        ult = next(a for a in eng.actions_by_actor["1414"] if a.action_id == "141403")
        eng._fire_ultimate(dh, ult)                 # TS 并入至帽（v 段被截）→ 池 = 3v 恰满
        assert math.isclose(self._pool(eng), self.CAP), (
            f"四源同池加算至帽 3×当前战技量：{self._pool(eng)}（期望 {self.CAP}）")
        self._dragon_act(eng)                       # 已满 → DR 并入被帽截断
        assert math.isclose(self._pool(eng), self.CAP), "授予时闸：池合计不超帽"
        dr = self._inst(eng, "TERRA_SHIELD_DRAGON")
        assert math.isclose(dr.remaining, SHIELD_DRAGON * 2), "截断=超出部分作废（非排队）"
        assert any("封顶截断" in l for l in eng.state.log), "截断留痕"

    def test_absorption_fifo_and_cascade(self):
        """池作为一个吸收单元：FIFO 逐成员扣减，归零成员各自破盾级联摘 modifier.

        手算口径：首次龙灵行动后丹恒/ally 平手 → 峥嵘落丹恒，池成员序 = TS → DR → ZR."""
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        dh = eng.state.actors["1414"]
        self._cast_skill(eng)                       # TS = v
        self._dragon_act(eng)                       # DR = d、ZR = z（池 v+d+z）
        hp0 = dh.current_hp
        overflow = eng._absorb_with_shields(dh, SHIELD_SKILL + 100.0, "e1")
        assert overflow == 0.0 and math.isclose(dh.current_hp, hp0), "池合计 ≥ 伤害：零溢出"
        assert self._inst(eng, "TERRA_SHIELD") is None and "TERRA_SHIELD" not in dh.modifiers, (
            "FIFO：先获得的战技盾先扣穿 → 破盾级联摘 modifier")
        dr = self._inst(eng, "TERRA_SHIELD_DRAGON")
        assert dr is not None and math.isclose(
            dr.remaining, SHIELD_DRAGON - 100.0), "余量继续扣次早成员"
        overflow = eng._absorb_with_shields(dh, 500.0, "e1")
        rest = SHIELD_DRAGON - 100.0 + SHIELD_ZR
        assert math.isclose(overflow, 500.0 - rest), (
            "DR+ZR 依次打穿后溢出扣本体（取最高在单元间——无独立实例时单元=池）")
        assert "TERRA_SHIELD_DRAGON" not in dh.modifiers
        assert "TERRA_SHIELD_ZHENGRONG" not in dh.modifiers, "池成员归零各自破盾级联"

    def test_cap_floats_with_panel(self):
        """动态封顶：丹恒面板上涨 → 帽随"当前战技护盾量"上浮（授予时现场求值）."""
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        dh = eng.state.actors["1414"]
        self._cast_skill(eng)
        self._dragon_act(eng)
        self._dragon_act(eng)
        dh.current_energy = 135.0
        ult = next(a for a in eng.actions_by_actor["1414"] if a.action_id == "141403")
        eng._fire_ultimate(dh, ult)                 # 池满旧帽 3v
        assert math.isclose(self._pool(eng), self.CAP)
        eng._apply_modifier(dh, Modifier(
            modifier_id="ATK_UP", name="攻", modifier_type="buff", duration=0,
            stat_effects={"atk": 200.0}))
        new_cap = 3 * ((TERRA_ATK_EFF * 1.15 + 200.0) * 0.2 + 400)   # 神秀快照在 + 200
        self._dragon_act(eng)                       # 旧帽已满 → 新帽下仍可并入
        assert math.isclose(self._pool(eng), new_cap), (
            f"帽随面板浮动：{self._pool(eng)}（期望新帽 {new_cap} > 旧帽 {self.CAP}）")

    def test_standalone_parallel_with_pool(self):
        """单元化吸收：独立实例与池各自一单元并行吸收（取最高跨单元、全额同扣）。."""
        eng = _make(compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        dh = eng.state.actors["1414"]
        eng._apply_modifier_spec(dh, {
            "modifier_id": "SOLO", "name": "外援盾", "modifier_type": "buff",
            "duration": 3, "shield": {"flat": 500.0}}, dh)
        self._cast_skill(eng)                       # 池 v（571.376）+ 独立 500
        overflow = eng._absorb_with_shields(dh, 550.0, "e1")
        assert overflow == 0.0, "有效护盾 = max(独立 500, 池 571.376) ≥ 550"
        assert self._inst(eng, "SOLO") is None, "独立实例同扣 500 打穿"
        ts = self._inst(eng, "TERRA_SHIELD")
        assert ts is not None and math.isclose(ts.remaining, SHIELD_SKILL - 550.0), (
            "池作为单元同扣 550（两单元并行吸收互不转嫁）")


class TestBondmateElementalSegments:
    """同袍属性附加两笔（141403 #8 / 1414103 #1——动态元素族首实例，2026-09-10 收编）.

    同袍指到火攻手 ally（inline element: "fire"）→ 两笔附加段属性随之为 fire（非丹恒
    physical），基数 = 同袍 atk（2000 + 神秀快照 745.1136×0.15）×0.8/0.4；
    category additional（不吃类型限定增伤）；削韧无源在案 0。
    """

    def _build_fire_bondmate(self):
        b = _build(ult_rule=False)
        # 纯普攻政策：防政策续放 141402 把同袍重指回丹恒（自指默认目标）/ 防窗口再开大刷层
        b["build"]["policy"]["action_rules"] = [
            {"condition": "true", "action": "basic", "priority": 0}]
        b["build"]["team"][1]["element"] = "fire"    # 动态元素取数源（inline member element 键）
        return b

    def test_segments_follow_bondmate_element_and_atk(self):
        eng = _make(compile_encounter(self._build_fire_bondmate(), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        dh, ally = eng.state.actors["1414"], eng.state.actors["ally"]
        hits: list = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: hits.append(dict(p)))
        # 手动战技指 ally：同袍+神秀+龙灵召唤全链（$event.target 寻址——_cast 同口径补发）
        skill = next(a for a in eng.actions_by_actor["1414"] if a.action_id == "141402")
        eng._execute_action(dh, skill)
        eng.bus.emit("on_action", {
            "actor": "1414", "action_type": skill.action_type, "action_id": "141402",
            "target_type": skill.target_type, "target": "ally",
            "actor_type": dh.actor.actor_type}, eng.state)
        assert "TONGPAO" in ally.modifiers and eng.state.actors["1414_souldragon"].alive
        ally_atk = eng.pipeline.effective_stats(ally)["atk"]
        assert math.isclose(ally_atk, 2000 + TERRA_ATK_EFF * 0.15, rel_tol=1e-3), (
            "同袍 atk = 2000 + 神秀快照（1414101：丹恒 atk×15%）")
        # 开大授强化 → 龙灵行动 → 三段（物理追击 + 同袍附加 AoE + 峥嵘附加单体）
        dh.current_energy = 135.0
        ult = next(a for a in eng.actions_by_actor["1414"] if a.action_id == "141403")
        assert eng._fire_ultimate(dh, ult) is True
        assert dh.modifiers["TERRA_ULT_ENH"].stacks == 2
        _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        zones = 0.5 * 0.8 * 0.9 * 1.025     # 火非弱点假人：def 0.5 × res 0.8 × 未击破 0.9 × 期望暴击
        seg_add = [h for h in hits if h.get("source") == "1414"
                   and h.get("reason") == "hit" and h.get("action_type") == "additional"]
        assert len(seg_add) == 2 and all(h["damage_type"] == "fire" for h in seg_add), (
            f"两笔同袍属性附加（实得 {[(h['damage_type'], h['action_type']) for h in seg_add]}）")
        assert math.isclose(seg_add[0]["amount"], 0.8 * ally_atk * zones, rel_tol=1e-3), (
            "强化追击第二段：全体 80% 同袍 atk 同袍属性（141403 #8）")
        assert math.isclose(seg_add[1]["amount"], 0.4 * ally_atk * zones, rel_tol=1e-3), (
            "峥嵘强化段：最高血敌单体 40% 同袍 atk 同袍属性（1414103 #1）")
        # 第二次强化行动同发两笔；耗尽后不再发
        _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        seg_add2 = [h for h in hits if h.get("source") == "1414"
                    and h.get("reason") == "hit" and h.get("action_type") == "additional"]
        assert len(seg_add2) == 4, "第二次强化行动同发两笔（耗第 2 层）"
        assert dh.modifiers["TERRA_ULT_ENH"].stacks == 0
        _step_until(eng, lambda r: r["actor_id"] == "1414_souldragon")
        assert len([h for h in hits if h.get("source") == "1414"
                    and h.get("action_type") == "additional"]) == 4, "强化耗尽后不再发附加段"
