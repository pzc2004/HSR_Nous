"""赛飞儿 1406 模板端到端对轴（验收型批）：真模板 YAML → 编译 →
老主顾/tally 记录/追加攻击/终结技真伤/行迹/星魂全链 → 手算全等.

口径常数：赛飞儿 atk 640.332、crit 0.05/0.5（期望暴击区 1.025）、spd 106+行迹 14=120、
量子增伤行迹 +0.144（增伤区 1.144）；假人 def 1000 → 防御区 0.5、量子/火弱点 → 抗性区 1.0、
未击破 0.9（max_toughness 9999 全场不破）；A6 偷天换日常驻易伤 +0.4（承伤区 1.4）、
E2 命中后再 +0.3（1.7）。默认档：basic 6 / skill 10 / ult 10 / talent 10（index=等级-1）。
真伤段跳全部乘区（fixed_value 直写）；装填预置序 = 秘技钩先于模板钩（秘技伤害不吃
A6 光环/E1 闩——在案，见模板头注⑤）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 640.332
DEF_Z, RES, UNB, CRIT, QDMG = 0.5, 1.0, 0.9, 1.025, 1.144
V0, V2 = 1.4, 1.7          # 承伤区：A6 常驻 / +E2 命中后

# 手算全等式（白值×倍率×防御区×抗性区×未击破×期望暴击×增伤区×承伤区）：
BASIC = ATK * 1.0 * DEF_Z * UNB * CRIT * QDMG * V0            # 普攻 lv6=100%（第 6 行）：473.0376
SKILL_M = ATK * 1.3 * 2.0 * DEF_Z * UNB * CRIT * QDMG * V0    # 战技 lv10 主 200%（ATK+30% 先挂）：1229.8977
SKILL_A = ATK * 1.3 * 1.0 * DEF_Z * UNB * CRIT * QDMG * V0    # 战技 lv10 邻 100%：614.9489
FUA = ATK * 1.5 * DEF_Z * UNB * CRIT * QDMG * V0              # 天赋追加 lv10=150%：709.5564
ALLY = 1500 * 1.0 * DEF_Z * UNB * CRIT * V0                   # 辅手普攻（无增伤桶）：968.625
ULT_S1 = ATK * 1.2 * DEF_Z * UNB * CRIT * QDMG * V0           # 终结 seg1 lv10=120%：567.6451
ULT_S2 = ATK * 0.4 * DEF_Z * UNB * CRIT * QDMG * V0           # 终结 seg2 lv10=40%：189.2150
TECH = ATK * 1.0 * DEF_Z * UNB * CRIT * QDMG                  # 秘技 100%（装填序无易伤）：337.8840
BASIC_E2 = ATK * 1.0 * DEF_Z * UNB * CRIT * QDMG * V2         # E2 后普攻：574.4028


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1406", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1406", "technique": "140607"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["quantum", "fire"]},
    {"actor_id": "e2", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["quantum", "fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _cipher(eng):
    return eng.state.actors["1406"]


def _cast(eng, owner, aid, *, target="e1"):
    """手动施放（_execute_action 不发 on_action——调用方补发；on_become_target/受击链引擎自发）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    st = _cipher(eng)
    st.current_energy = 130.0
    ult = next(a for a in eng.actions_by_actor["1406"] if a.action_id == "140603")
    assert eng._fire_ultimate(st, ult) is True   # 内部自发 on_action/on_ultimate


def _drops(eng):
    out = []
    eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: out.append(p))
    return out


class TestCipherCompile:
    def test_actions_resources_and_ult_segments(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1406"]}
        assert acts == {"140601", "140602", "140603"}
        decls = compiled.resource_decls_by_actor["1406"]
        assert {"tally", "_fua_used", "_e1_tally", "_e6_flag"} <= set(decls)
        ult = next(a for a in compiled.actions_by_actor["1406"] if a.action_id == "140603")
        assert ult.instances == 2 and ult.target_type == "single"
        assert ult.instance_variants[1]["target_type"] == "blast", (
            "勘正⑩：seg1 单体 #1 / seg2 blast #4——官方 #4 覆盖主+邻")
        skill = next(a for a in compiled.actions_by_actor["1406"] if a.action_id == "140602")
        assert skill.apply_modifiers[0]["modifier_id"] == "SKILL_ATK_UP", (
            "勘正①：战技自身 ATK+30% 落 apply_modifiers（伤害段前挂载）")


class TestBattleStart:
    def test_patron_assign_and_sleight_aura(self, compiled):
        """开局：老主顾=最高 Max HP 敌（同值稳定序=e1）；A6 全体易伤 0.4；A2 未达档."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        assert "PATRON" in e1.modifiers and "PATRON" not in e2.modifiers
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"], 0.4)
        assert math.isclose(eng.pipeline.effective_stats(e2)["vulnerability"], 0.4), "A6 常驻光环"
        st = _cipher(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 120.0), "106+行迹 14"
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.05), (
            "SPD 120 < 140——A2 暴击件 enable_if 全不启用")
        assert math.isclose(st.resources["tally"], 0.0)


class TestBasicAndSkill:
    def test_basic_damage_and_tally(self, compiled):
        """普攻 lv6=100%（第 6 行=1.0）：473.0376；tally 12%（A2/E1 未激活——系数 1）；回能 20."""
        eng = _make(compiled)
        drops = _drops(eng)
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "1406", "140601")
        assert math.isclose(drops[0]["amount"], BASIC, rel_tol=1e-6)
        assert math.isclose(hp0 - e1.current_hp, BASIC, rel_tol=1e-6)
        assert math.isclose(_cipher(eng).resources["tally"], 0.12 * BASIC, rel_tol=1e-6), (
            "12%×473.0376 = 56.7645")
        assert math.isclose(_cipher(eng).current_energy, 20.0)

    def test_skill_blast_atk_buff_weaken(self, compiled):
        """战技：ATK+30% 先挂（伤害段前）→ 主 1229.8977 / 邻 614.9489；虚弱挂主目标；
        tally = 12%×主 + 8%×邻 = 196.7836."""
        eng = _make(compiled)
        drops = _drops(eng)
        _cast(eng, "1406", "140602")
        st = _cipher(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.3, rel_tol=1e-9), (
            "战技 ATK+30% 2 回合")
        assert [math.isclose(d["amount"], v, rel_tol=1e-6)
                for d, v in zip(drops, (SKILL_M, SKILL_A))] == [True, True]
        e1 = eng.state.actors["e1"]
        assert "SKILL_WEAKEN" in e1.modifiers, "勘正①：虚弱挂主目标"
        assert math.isclose(eng.pipeline.effective_stats(e1)["dmg_bonus"]["dmg_reduction"],
                            0.1, rel_tol=1e-9), "虚弱减伤 10%（dmg_dmg_reduction 乘区在案）"
        assert math.isclose(st.resources["tally"], 0.12 * SKILL_M + 0.08 * SKILL_A, rel_tol=1e-6), (
            "12%×1229.8977 + 8%×614.9489 = 147.5877 + 49.1959")
        assert math.isclose(st.current_energy, 30.0)
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点（tbgd BPNeed 权威）"


class TestPatronOverride:
    def test_skill_retarget_moves_patron(self, compiled):
        """战技主目标覆盖老主顾：打 e2 → 标记移 e2；结算序在案——伤害先于覆盖（on_action），
        本次主目标按 300 侠盗 8% 计、相邻（旧老主顾 e1）按 12% 计 → 待实测（头注⑦）."""
        eng = _make(compiled)
        _cast(eng, "1406", "140602", target="e2")
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        assert "PATRON" not in e1.modifiers and "PATRON" in e2.modifiers, "单标记最新覆盖"
        assert math.isclose(_cipher(eng).resources["tally"],
                            0.12 * SKILL_A + 0.08 * SKILL_M, rel_tol=1e-6), (
            "12%×614.9489 + 8%×1229.8977 = 73.7939 + 98.3918 = 172.1857")

    def test_kill_reassigns_patron(self, compiled):
        """递补①：老主顾死亡 → 存活最高 Max HP 敌递补（on_kill 时死者标记未清账可判）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.current_hp = 0.0
        eng._check_death(e1, "ally")
        assert not e1.alive
        assert "PATRON" in e2.modifiers, "死亡递补存活敌"


class TestTalentFollowUp:
    def test_fua_chain_once_per_turn_and_reset(self, compiled):
        """追加攻击链：辅手打老主顾 → 追加 709.5564 + 回能 5 + tally 双账（12% 两笔）；
        每回合 1 次（第二次辅手攻击不触发）；赛飞儿回合开始重置 → 再触发."""
        eng = _make(compiled)
        drops = _drops(eng)
        st = _cipher(eng)
        _cast(eng, "ally", "ally_basic")
        assert [math.isclose(d["amount"], v, rel_tol=1e-6)
                for d, v in zip(drops, (ALLY, FUA))] == [True, True]
        assert drops[1]["action_type"] == "follow_up" and drops[1]["source"] == "1406"
        assert math.isclose(st.resources["_fua_used"], 1.0)
        assert math.isclose(st.current_energy, 5.0), "勘正③：追加攻击回能 5"
        assert math.isclose(st.resources["tally"], 0.12 * (ALLY + FUA), rel_tol=1e-6), (
            "12%×(968.625 + 709.5564) = 201.3818——辅手与追加攻击各一笔")
        n = len(drops)
        _cast(eng, "ally", "ally_basic")   # 每回合 1 次——第二发辅手普攻只留自己一跳
        assert len(drops) == n + 1, "触发计数封顶"
        eng.bus.emit("on_turn_start", {"actor": "1406"}, eng.state)   # 重置
        _cast(eng, "ally", "ally_basic")
        assert len(drops) == n + 3 and math.isclose(drops[-1]["amount"], FUA, rel_tol=1e-6)
        assert math.isclose(st.current_energy, 10.0), "两发追加攻击各回 5"


class TestUltimate:
    def test_ult_segments_true_damage_and_clear(self, compiled):
        """终结链（E0）：tally = 12%×(辅手+追加+seg1+seg2主) + 8%×seg2邻 = 307.3422 →
        真伤 25%×tally 主点 + 75%×tally 全体均摊（2 敌各 37.5%）→ tally 清空（无 E6 返 0）."""
        eng = _make(compiled)
        drops = _drops(eng)
        st = _cipher(eng)
        _cast(eng, "ally", "ally_basic")               # tally = 0.12×(968.625+709.5564) = 201.3818
        _ult(eng)
        tally_pre = 0.12 * (ALLY + FUA + ULT_S1 + ULT_S2) + 0.08 * ULT_S2   # 307.3422
        expect = [ALLY, FUA, ULT_S1, ULT_S2, ULT_S2,
                  0.25 * tally_pre, 0.375 * tally_pre, 0.375 * tally_pre]
        assert len(drops) == len(expect)
        for d, v in zip(drops, expect):
            assert math.isclose(d["amount"], v, rel_tol=1e-6), f"{d['amount']} != {v}"
        assert drops[5]["damage_type"] == "true" and drops[5]["target"] == "e1", "真伤单点 25%"
        assert drops[6]["damage_type"] == "true" and drops[7]["damage_type"] == "true", (
            "勘正⑨：75% 由所有技能目标均分——2 敌各 37.5%×tally（staging 只对主除 3 少一半）")
        assert math.isclose(st.resources["tally"], 0.0, abs_tol=1e-6), "施放终结技后清空记录值"
        assert math.isclose(st.current_energy, 5.0), "满能 130 全扣 + 施放回能 5（_ult 置能覆盖追加的 5）"


class TestTraces:
    def test_a2_crit_live_gate(self, compiled):
        """A2 神行宝鞋取代式分档（enable_if 现场变档）：120→无件；+20 → 140 档 +25%；
        再 +30 → 170 档 +50%（140 件退、170 件进）."""
        eng = _make(compiled)
        st = _cipher(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.05)
        eng._apply_modifier(st, Modifier(
            modifier_id="T_SPD1", name="测速", modifier_type="buff", duration=0,
            dispellable=False, stat_effects={"spd": 20}))
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 140.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.30, rel_tol=1e-9)
        eng._apply_modifier(st, Modifier(
            modifier_id="T_SPD2", name="测速", modifier_type="buff", duration=0,
            dispellable=False, stat_effects={"spd": 30}))
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.55, rel_tol=1e-9), (
            "170 档取代 140 档（互斥 enable_if——非累加 0.80）")

    def test_trace_flat_stats(self, compiled):
        """行迹平铺（勘正⑪）：spd +14 flat / 量子增伤 0.144 / 效果命中 0.10."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_cipher(eng))
        assert math.isclose(eff["spd"], 120.0)
        assert math.isclose(eff["dmg_bonus"]["quantum"], 0.144, rel_tol=1e-9)
        assert math.isclose(eff["effect_hit"], 0.10, rel_tol=1e-9)


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技：进战全体 337.8840（装填序不吃 A6 光环——在案）；tally 直接入账 12%×3×
        单敌实伤 + 三百侠盗自然钩 8%×2 敌 → 合计 0.52×337.8840 = 175.6997；老主顾随后指派."""
        eng = CombatEngine.from_compiled(_compiled(pre_battle=True), mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        drops = _drops(eng)
        eng.setup()
        assert len(drops) == 2
        for d in drops:
            assert math.isclose(d["amount"], TECH, rel_tol=1e-6)
        st = _cipher(eng)
        assert math.isclose(st.resources["tally"], 0.52 * TECH, rel_tol=1e-6), (
            "0.36×337.8840（12%×(+200%) 直接入账）+ 0.16×337.8840（侠盗 8%×2 敌）")
        assert "PATRON" in eng.state.actors["e1"].modifiers
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["e1"])["vulnerability"], 0.4)


class TestEidolons:
    def test_e1_tally_boost_and_atk_on_fua(self):
        """E1：tally×1.5 闩（0.12→0.18）——辅手+追加两笔 = 0.18×1678.1814 = 302.0726；
        追加攻击后自身 ATK+80%（2 回合）."""
        eng = _make(_compiled(eidolon=1))
        st = _cipher(eng)
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(st.resources["tally"], 0.18 * (ALLY + FUA), rel_tol=1e-6)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.8, rel_tol=1e-9), (
            "察言观色看笑脸：施放追加攻击时 ATK+80%")

    def test_e2_vuln_on_hit(self):
        """E2（eidolon=2 含 E1 闩）：赛飞儿命中 → 目标易伤 +0.3（与 A6 加算 0.7）；
        第二发普攻吃 1.7 承伤区 = 516.9625."""
        eng = _make(_compiled(eidolon=2))
        drops = _drops(eng)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1406", "140601")
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"], 0.7, rel_tol=1e-9)
        assert math.isclose(_cipher(eng).resources["tally"], 0.18 * BASIC, rel_tol=1e-6)
        _cast(eng, "1406", "140601")
        assert math.isclose(drops[-1]["amount"], BASIC_E2, rel_tol=1e-6), (
            "473.0376 × 1.7/1.4 = 574.4028")

    def test_e4_additional_on_ally_and_self_hit(self):
        """E4（勘正⑦——「我方目标」含赛飞儿本人；挡因③解——官方含追加攻击命中）：
        辅手命中 → 追加 + E4 附加两笔——追加内 E4 先于 E1 攻击件（287.2014）、
        同盟层 E4 后于 E1 攻击件（×1.8=516.9625，E2 易伤 1.7、category additional
        不吃类型桶）；赛飞儿自己命中也触发 E4（无 E1 件 → 287.2014）."""
        eng = _make(_compiled(eidolon=4))
        drops = _drops(eng)
        _cast(eng, "ally", "ally_basic")
        e4 = ATK * 1.8 * 0.5 * DEF_Z * UNB * CRIT * QDMG * V2      # 516.9625
        e4_fua = ATK * 0.5 * DEF_Z * UNB * CRIT * QDMG * V2        # 287.2014
        assert [math.isclose(d["amount"], v, rel_tol=1e-6)
                for d, v in zip(drops, (ALLY, FUA, e4_fua, e4))] == [True, True, True, True]
        assert drops[2]["action_type"] == "additional" and drops[3]["action_type"] == "additional", (
            "附加伤害伪类——不冒 follow_up")
        assert math.isclose(_cipher(eng).resources["tally"],
                            0.18 * (ALLY + FUA + e4_fua + e4), rel_tol=1e-6), (
            "E4 双笔同记 tally（446.8221）")
        eng2 = _make(_compiled(eidolon=4))   # 本人命中自闭环（无 E1 件——E3 普攻 7 档=110%）
        drops2 = _drops(eng2)
        _cast(eng2, "1406", "140601")
        basic7 = ATK * 1.1 * DEF_Z * UNB * CRIT * QDMG * V0        # 520.3413
        e4_self = ATK * 0.5 * DEF_Z * UNB * CRIT * QDMG * V2       # 287.2014
        assert [math.isclose(d["amount"], v, rel_tol=1e-6)
                for d, v in zip(drops2, (basic7, e4_self))] == [True, True]
        assert drops2[1]["action_type"] == "additional"

    def test_e6_fua_boost_tally_and_refund(self):
        """E6 全链（含 E1..E5 联动：E3 终结 lv12、E5 天赋 lv12）：
        追加攻击 = 640.332×1.65×(1.144+3.5 增伤区桶)×0.5×0.9×1.025×1.4 = 3168.4421（勘正⑤——
        dmg_follow_up_dmg_boost 零递归）；E6② 额外记录 16%×追加非溢出伤；挡因③解——
        追加命中补 E4 一笔（追加内先于 E1 攻击件）；
        终结清空改返还 20%：tally 链 1954.9838 → 返 390.9968."""
        eng = _make(_compiled(eidolon=6))
        drops = _drops(eng)
        st = _cipher(eng)
        _cast(eng, "ally", "ally_basic")
        fua6 = ATK * 1.65 * DEF_Z * UNB * CRIT * (QDMG + 3.5) * V0     # 3168.4421
        e4 = ATK * 1.8 * 0.5 * DEF_Z * UNB * CRIT * QDMG * V2          # 516.9625
        e4_fua = ATK * 0.5 * DEF_Z * UNB * CRIT * QDMG * V2            # 287.2014
        assert [math.isclose(d["amount"], v, rel_tol=1e-6)
                for d, v in zip(drops, (ALLY, fua6, e4_fua, e4))] == [True, True, True, True]
        tally_pre_ult = 0.18 * ALLY + (0.18 + 0.16) * fua6 + 0.18 * (e4_fua + e4)   # 1396.3724
        assert math.isclose(st.resources["tally"], tally_pre_ult, rel_tol=1e-6), (
            "12%×1.5 双笔 + E6② 16%×追加 + E4 双笔 18%")
        drops.clear()
        _ult(eng)
        s1 = ATK * 1.8 * 1.32 * DEF_Z * UNB * CRIT * QDMG * V2         # seg1 lv12=132%：1364.7810
        s2m = ATK * 1.8 * 0.44 * DEF_Z * UNB * CRIT * QDMG * V2        # seg2 主 lv12=44%：454.9270
        s2a = ATK * 1.8 * 0.44 * DEF_Z * UNB * CRIT * QDMG * V0        # seg2 邻（E2 未挂）：374.6458
        tally = (tally_pre_ult + 0.18 * (s1 + e4 + s2m) + 0.12 * s2a + 0.18 * e4)  # 1954.9838
        # 段内逐目标结算：E4 在 seg1 与 seg2 主目标受击后即插（after_being_hit 逐目标发射）
        expect = [s1, e4, s2m, e4, s2a, 0.25 * tally, 0.375 * tally, 0.375 * tally]
        assert len(drops) == len(expect)
        for d, v in zip(drops, expect):
            assert math.isclose(d["amount"], v, rel_tol=1e-6), f"{d['amount']} != {v}"
        assert math.isclose(st.resources["tally"], 0.2 * tally, rel_tol=1e-6), (
            "勘正⑥：清空折返 20%——0.2×1954.9838 = 390.9968（staging 独立钩永读 0 已拆）")
