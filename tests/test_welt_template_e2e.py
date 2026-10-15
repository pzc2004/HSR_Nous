"""瓦尔特 1004 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 弹射/减速掷/天赋附加段/
禁锢失重/延后计数/星魂全链 → 手算全等.

过堂两件：失重减防 40% 收编（def_pct 负值——1507 先例，draft 误判键缺）；
11004101 主件方向勘正摘除（all_dmg 挂敌方=强化敌方输出方向反，目标条件增伤通道缺待收）。

口径常数：瓦尔特 atk 620.928（白值——行迹无 ATK 节点（B1 11004201-210 为 效果命中+虚数+效果抵抗 三族）；2026-09-24 勘正：旧值误按双轨聚合且多抄 ATK 节点 0.28）、虚数伤池 1.144（行迹 dmg_imaginary 0.144 同回填）、crit 0.05/0.5
（期望暴击区 1.025）；假人 def 0 → 防御区 0.5、虚数弱点 → 抗性区 1.0、
未击破 0.9。天赋段 = param(1100404,1)×ATK 虚数附加伤害全乘区（B-WT① 换绑：
category additional——旧 category true 平值跳乘区退役）。expected 模式：
mechanic_chance ≥0.5 恒生效（lv10 减速概率 0.75）、mode random 按序取首
（弹射段全落 e1）。

语义在案（e2e 按现写语义钉死，官方口径待实测）：减速掷触发域 = 战技命中（主段+4
弹射段——2026-09-24 勘正收窄，旧版任一虚数命中过宽：普攻/终结技/Judgment/E1 段
误入掷域）；天赋触发域 = 瓦尔特全虚数命中（含 Judgment/弹射/E1 追加段，天赋段
自身经 _tw_proc 闩出集）；同 hit 序 = §23 快照分发（首挂减速的 hit 不触发天赋，
后续 hit 才触发，与官方 "already Slowed" 构造一致）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

WELT_ATK = 620.928 * 1.0             # 620.928（行迹无 ATK 节点——B1 三族无攻击，2026-09-24 勘正双轨+多抄）
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)      # 防御区×未击破×期望暴击区
IM = 1.144                            # 虚数伤池（行迹 dmg_imaginary 0.144 回填——B-TR①，同日勘正）
TAL10 = 1.0 * WELT_ATK * Z * IM       # 天赋附加段 lv10（param(1100404,1)=1.0——全乘区）
TAL12 = 1.1 * WELT_ATK * Z * IM       # E5 天赋+2 → lv12=1.1


def _build(*, eidolon: int = 0):
    member = {"character_template": "1004", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "physical",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", 'action': "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _welt(eng):
    return eng.state.actors["1004"]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng._pick_ally_target = lambda attacker=None: tgt
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    m7 = _welt(eng)
    m7.current_energy = 120.0
    ult = next(a for a in eng.actions_by_actor["1004"] if a.action_id == "1100403")
    assert eng._fire_ultimate(m7, ult) is True


class TestWeltCompile:
    def test_resources_actions(self, compiled):
        decls = compiled.resource_decls_by_actor["1004"]
        assert {"_welt_slow_p", "_wl_n", "_e1_proc"} <= set(decls), "概率宿主/延后计数/E1 递归闩齐备"
        acts = {a.action_id: a for a in compiled.actions_by_actor["1004"]}
        assert set(acts) == {"1100401", "1100402", "1100403"}, "天赋 1100404 无行动块（hook 真伤）"
        assert acts["1100403"].energy_cost == 120
        mids = [m["modifier_id"] for m in acts["1100403"].apply_modifiers]
        assert "WELT_IMPRISON" in mids and "WELT_WEIGHTLESS" in mids
        wl = next(m for m in acts["1100403"].apply_modifiers if m["modifier_id"] == "WELT_WEIGHTLESS")
        assert wl["stat_effects"].get("def_pct") == -0.4, (
            "失重减防 40% 过堂收编（def_pct 负值——1507 先例；编译期 param 已求值 lv10=0.4）")


class TestBattleStart:
    def test_latches_and_trace_energy(self, compiled):
        eng = _make(compiled)
        w = _welt(eng)
        assert math.isclose(w.resources["_welt_slow_p"], 0.75), "减速概率宿主 lv10 #2=0.75（E4 覆写已随版本更迭摘除——E0 本位档）"
        assert math.isclose(w.current_energy, 30.0), "11004101 开场 +30 能量"


class TestSkillBounce:
    def test_skill_main_plus_bounces_and_slow_chain(self, compiled):
        """战技：主段 + 4 弹射（expected 全落 e1）+ Judgment 战技段；逐 hit 减速掷（0.75≥0.5
        恒中）→ 天赋真伤按 §23 快照分发：主段快照无减速不触发，后续 5 段各触发."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1004", "1100402")
        dmg = (5 * 0.72 + 1.2 * 0.72) * WELT_ATK * Z * IM + 5 * TAL10
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "主+4 弹射+Judgment 段（0.72/0.864 lv10）；天赋 5 段附加（快照见旧值实证）")
        assert "WELT_SLOW" in e1.modifiers, "减速掷命中（mechanic_chance 0.75≥0.5 恒生效）"
        assert math.isclose(
            eng.pipeline.effective_stats(e1)["spd"], 100 * (1 - 0.1), rel_tol=1e-9), (
            "减速 10%（param(1100402,3)）")


class TestTalentAndJudgment:
    def test_basic_on_preslowed_double_talent(self, compiled):
        """天赋+Judgment：预挂减速后普攻——普攻段与 Judgment 段各触发 1 次附加段（2×TAL）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="WELT_SLOW", name="减速", modifier_type="debuff", duration=2,
            stat_effects={"spd_pct": -0.1}))
        hp1 = e1.current_hp
        _cast(eng, "1004", "1100401")
        dmg = (1.0 + 0.8) * WELT_ATK * Z * IM + 2 * TAL10
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "普攻 1.0 + Judgment 0.8×普攻倍率（params [0.8,1.2] 实证）+ 双天赋附加段")


class TestUltimate:
    def test_ult_aoe_imprison_weightless(self, compiled):
        """大招：AoE 1.5 对轴（快照无减速 → 本发不触发天赋）+ 禁锢/失重双件
        （spd 100→85：禁锢 10%+失重 5%）+ 失重被击延后计数 2（两敌各 1）+ 能量分槽 10."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        dmg = 1.5 * WELT_ATK * Z * IM
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "大招不掷战技减速 → 目标无 WELT_SLOW 可判，天赋附加段不发")
        assert math.isclose(hp2 - e2.current_hp, dmg, rel_tol=1e-9)
        assert "WELT_IMPRISON" in e1.modifiers and "WELT_WEIGHTLESS" in e1.modifiers
        assert "WELT_SLOW" not in e1.modifiers, (
            "大招不掷战技减速（2026-09-24 勘正：减速掷触发域=战技命中，官方 'On hit' 属"
            "战技文本——旧版任一虚数命中过宽，终结技/普攻/Judgment 段误入掷域）")
        assert math.isclose(
            eng.pipeline.effective_stats(e1)["spd"], 100 * (1 - 0.10 - 0.05), rel_tol=1e-9), (
            "禁锢 10% + 失重 5% 两件叠加（spd 100→85——旧版误叠战技减速 10% 三件 75 作废）")
        assert math.isclose(_welt(eng).resources["_wl_n"], 2.0), (
            "失重被击延后：副作用先于伤害段挂载 → 大招自身两敌命中各计 1")
        assert math.isclose(_welt(eng).current_energy, 10.0), (
            "行动回能 5（tbgd）+ 11004103 大招 +5 分槽")

    def test_weightless_advance_counter_and_reset(self, compiled):
        """失重计数：队友攻击失重目标 +1（≤8 闩）；目标回合开始清零."""
        eng = _make(compiled)
        _ult(eng)
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(_welt(eng).resources["_wl_n"], 3.0), "大招 2 + 辅手攻击 1"
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(_welt(eng).resources["_wl_n"], 0.0), "目标回合开始清零"


class TestEidolons:
    def test_e1_weightless_bonus_hits(self):
        """E1 名的传承（新版）：战技击中失重目标 → 主+4 弹射+Judgment 共 6 hit 各追加
        0.4×终结技倍率（lv10=1.5 → 0.6×ATK/击；_e1_proc 闩挡递归）；E1 段虚数 hit
        同发天赋附加段（减速已在）——附加段 5 基础段+6 E1 段=11 段."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        e1.modifiers["WELT_WEIGHTLESS"] = Modifier(
            modifier_id="WELT_WEIGHTLESS", name="失重", modifier_type="debuff",
            duration=2, dispellable=True)
        hp1 = e1.current_hp
        _cast(eng, "1004", "1100402")
        dmg = ((5 * 0.72 + 1.2 * 0.72) * WELT_ATK * Z * IM    # 基础链（同主干测试）
               + 6 * (0.4 * 1.5 * WELT_ATK) * Z * IM           # E1 段 6 击（0.6×ATK×Z）
               + 11 * TAL10)                                   # 附加段 5+6（主段快照不发）
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9)

    def test_e6_old_model_removed(self):
        """版本更迭实证（E4/E6 新版均待收）：eidolon=6 时战技仍 4 弹射（旧版 E6 第 5 段
        已摘除）、减速概率仍基础 0.75（旧版 E4 覆写已摘除）；E3/E5 随档 lv12 联动."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        assert math.isclose(_welt(eng).resources["_welt_slow_p"], 0.77), (
            "旧版 E4 +0.35 覆写已摘除——基础档（E3 战技+2 → lv12 #2=0.77）")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1004", "1100402")
        dmg = (5 * 0.792 + 1.2 * 0.792) * WELT_ATK * Z * IM + 5 * TAL12
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "4 弹射+主+Judgment（E3 lv12=0.792）+ 5 段天赋附加 lv12——旧版 E6 第 5 段不在")
