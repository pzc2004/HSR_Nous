"""瓦尔特 1004 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 弹射/减速掷/天赋真伤/
禁锢失重/延后计数/星魂全链 → 手算全等.

过堂两件：失重减防 40% 收编（def_pct 负值——1507 先例，draft 误判键缺）；
11004101 主件方向勘正摘除（all_dmg 挂敌方=强化敌方输出方向反，目标条件增伤通道缺待收）。

口径常数：瓦尔特白值 atk 620.928、crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 →
防御区 0.5、虚数弱点 → 抗性区 1.0、未击破 0.9。天赋真伤段 = param(1100404,1)×ATK 直写
（category true 跳乘区）。expected 模式：mechanic_chance ≥0.5 恒生效（lv10 减速概率
0.75）、mode random 按序取首（弹射段全落 e1）。

语义在案（e2e 按现写语义钉死，官方口径待实测）：减速与天赋同 hit 链——hook 声明序
先挂减速后判天赋，同 hit 即触发真伤；天赋触发域 = 瓦尔特全虚数命中（含 Judgment/
弹射/E1 追加段，真伤段天然出集）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

WELT_ATK = 620.928
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)      # 防御区×未击破×期望暴击区
TRUE10 = 1.0 * WELT_ATK               # 天赋真伤 lv10（param(1100404,1)=1.0）
TRUE12 = 1.1 * WELT_ATK               # E5 天赋+2 → lv12=1.1


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
        assert {"_welt_slow_p", "_wl_n", "_e1_n"} <= set(decls), "概率宿主/延后计数/E1 闩齐备"
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
        assert math.isclose(w.resources["_welt_slow_p"], 0.75), "减速概率宿主 lv10 #2=0.75"
        assert math.isclose(w.resources["_e1_n"], 0.0), "E1 闩读前必写（1501 教训）"
        assert math.isclose(w.current_energy, 30.0), "11004101 开场 +30 能量"


class TestSkillBounce:
    def test_skill_main_plus_bounces_and_slow_chain(self, compiled):
        """战技：主段 + 4 弹射（expected 全落 e1）+ Judgment 战技段；逐 hit 减速掷（0.75≥0.5
        恒中）→ 天赋真伤按 §23 快照分发：主段快照无减速不触发，后续 5 段各触发."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1004", "1100402")
        dmg = (5 * 0.72 + 1.2 * 0.72) * WELT_ATK * Z + 5 * TRUE10
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "主+4 弹射+Judgment 段（0.72/0.864 lv10）；天赋 5 段真伤（快照见旧值实证）")
        assert "WELT_SLOW" in e1.modifiers, "减速掷命中（mechanic_chance 0.75≥0.5 恒生效）"
        assert math.isclose(
            eng.pipeline.effective_stats(e1)["spd"], 100 * (1 - 0.1), rel_tol=1e-9), (
            "减速 10%（param(1100402,3)）")


class TestTalentAndJudgment:
    def test_basic_on_preslowed_double_true(self, compiled):
        """天赋+Judgment：预挂减速后普攻——普攻段与 Judgment 段各触发 1 次真伤（2×TRUE）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="WELT_SLOW", name="减速", modifier_type="debuff", duration=2,
            stat_effects={"spd_pct": -0.1}))
        hp1 = e1.current_hp
        _cast(eng, "1004", "1100401")
        dmg = (1.0 + 0.8) * WELT_ATK * Z + 2 * TRUE10
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "普攻 1.0 + Judgment 0.8×普攻倍率（params [0.8,1.2] 实证）+ 双真伤")


class TestUltimate:
    def test_ult_aoe_imprison_weightless(self, compiled):
        """大招：AoE 1.5 对轴（快照无减速 → 本发不触发天赋）+ 禁锢/失重双件
        （spd 100→85：禁锢 10%+失重 5%）+ 失重被击延后计数 2（两敌各 1）+ 能量分槽 10."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        dmg = 1.5 * WELT_ATK * Z
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "快照分发：大招自身命中首挂减速，天赋真伤不发（后续攻击才吃）")
        assert math.isclose(hp2 - e2.current_hp, dmg, rel_tol=1e-9)
        assert "WELT_IMPRISON" in e1.modifiers and "WELT_WEIGHTLESS" in e1.modifiers
        assert "WELT_SLOW" in e1.modifiers, "大招命中同掷战技减速（On hit 触发域含终结技）"
        assert math.isclose(
            eng.pipeline.effective_stats(e1)["spd"], 100 * (1 - 0.10 - 0.05 - 0.10), rel_tol=1e-9), (
            "禁锢 10% + 失重 5% + 战技减速 10% 三件叠加")
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
    def test_e1_empowered_two_charges(self):
        """E1：大招后 _e1_n=2；随后普攻多 1 段 0.5×普攻倍率并耗 1（普攻/Judgment/E1 段
        各触发天赋真伤——3×TRUE；大招已挂减速）."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _ult(eng)
        assert math.isclose(_welt(eng).resources["_e1_n"], 2.0)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1004", "1100401")
        dmg = (1.0 + 0.8 + 0.5) * WELT_ATK * Z + 3 * TRUE10
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9)
        assert math.isclose(_welt(eng).resources["_e1_n"], 1.0)

    def test_e6_fifth_bounce(self):
        """E6：第 5 段随机段（E3 战技+2 → lv12=0.792；E5 天赋+2 → 真伤 lv12=1.1×ATK；
        E4 减速概率 min(1, 0.77+0.35)=1.0）——主段快照无减速不触发，5 弹射+Judgment
        共 6 段各带真伤."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        assert math.isclose(_welt(eng).resources["_welt_slow_p"], 1.0), "E4 覆写后写胜"
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1004", "1100402")
        dmg = (6 * 0.792 + 1.2 * 0.792) * WELT_ATK * Z + 6 * TRUE12
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "6×0.792（主+5 弹射）+ 0.9504（Judgment）+ 6×真伤 lv12（主段快照不发）")
