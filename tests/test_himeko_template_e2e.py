"""姬子 1003 模板端到端对轴（验收型批）：真模板 YAML → 编译 → Charge 三源（开战/击破/
E4 待收）/满层追击清层/大招每杀回能/基准门控/星魂全链 → 手算全等.

过堂收编实证：天赋 Charge 击破加层 draft 误判 "DEFAULT_CONTRACT 无击破事件键"——
on_break 已登记（载荷 {bar_index, element, source, target}），直接收编；粒度差异在案
（on_break 按韧性条逐条发射，多血条精英非末条破亦 +1 层，待实测）。

口径常数：姬子 atk 892.97208（白值 756.756×1.18——行迹 atk_pct 0.18 B-TR①
回填；伤害基数）、火伤池 1.224（行迹 dmg_fire 0.224 同回填）、crit 0.05/0.5；
大行迹「基准」HP≥80% → crit_rate +0.15（满血 crit_exp = 1+0.2×0.5 = 1.1）；
假人 def 0 → 防御区 0.5、火弱点 → 抗性区 1.0、未击破 0.9。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

HMK_ATK = 756.756 * 1.18   # 892.97208（行迹 atk_pct 0.18 回填——B-TR①）
DEF_RES, UNBROKEN = 0.5, 0.9
CRIT_EXP = 1 + 0.2 * 0.5   # 0.05 白值 + 0.15 基准（满血门控成立）
FIRE = 1.224               # 火伤池（行迹 dmg_fire 0.224 回填——B-TR①）


def _build(*, eidolon: int = 0):
    member = {"character_template": "1003", "level": 80}
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


def _stage(toughness=9999):
    return {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
         "max_toughness": toughness, "weakness": ["fire"]},
        {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
         "max_toughness": toughness, "weakness": ["fire"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _stage(), template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _hmk(eng):
    return eng.state.actors["1003"]


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


class TestHimekoCompile:
    def test_resources_actions(self, compiled):
        decl = compiled.resource_decls_by_actor["1003"]["charge"]
        assert decl["max"] == 3, "Charge 上限 3 = param(100304,2) 全档恒 3"
        acts = {a.action_id: a for a in compiled.actions_by_actor["1003"]}
        assert acts["100304"].action_type == "follow_up", "天赋追击归 follow_up（无 talent 键）"
        assert acts["100304"].energy_gain == 10
        assert acts["100303"].energy_cost == 120 and acts["100303"].energy_gain == 5
        assert acts["100302"].skill_point_cost == 1
        hooks = [h for h in compiled.hooks
                 if h.owner_id == "1003" and h.event == "on_break"]
        assert hooks, "on_break 击破加层钩已收编（draft 误判通道缺，过堂勘正）"


class TestChargeChain:
    def test_battle_start_charge_and_benchmark(self, compiled):
        """开战：Charge +1（天赋）；基准 HP≥80% 门控 → crit_rate 0.05+0.15=0.20."""
        eng = _make(compiled)
        m7 = _hmk(eng)
        assert math.isclose(m7.resources["charge"], 1.0), "战斗开始 +1 层（官方文本）"
        eff = eng.pipeline.effective_stats(m7)
        assert math.isclose(eff["crit_rate"], 0.20), "基准满血生效：0.05+0.15"

    def test_break_grants_charge(self):
        """击破加层（过堂收编）：战技主削 20 破 20 韧假人 → Charge 1→2（on_break 已登记）."""
        compiled = compile_encounter(_build(), _stage(toughness=20),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        assert math.isclose(_hmk(eng).resources["charge"], 1.0)
        _cast(eng, "1003", "100302")
        assert e1.broken, "主削 20 = 满韧 20 → 弱点击破"
        assert math.isclose(_hmk(eng).resources["charge"], 2.0), (
            "on_break → +1 层（draft 误判'无击破事件键'，过堂收编实证）")

    def test_full_charge_triggers_followup_and_clears(self, compiled):
        """满 3 层：任一我方攻击 → 追击 100304（全体 lv10=1.4 对轴）+ 清空 Charge."""
        eng = _make(compiled)
        _hmk(eng).resources["charge"] = 3.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "ally", "ally_basic")
        ally_basic = 1500 * 1.0 * DEF_RES * UNBROKEN * (1 + 0.05 * 0.5)   # 辅手自身普攻
        fu = HMK_ATK * 1.4 * DEF_RES * UNBROKEN * CRIT_EXP * FIRE
        assert math.isclose(hp1 - e1.current_hp, ally_basic + fu, rel_tol=1e-9), (
            "e1 = 辅手普攻 + 追击 lv10 #1=1.4 全体")
        assert math.isclose(hp2 - e2.current_hp, fu, rel_tol=1e-9), "e2 仅吃追击"
        assert math.isclose(_hmk(eng).resources["charge"], 0.0), "触发后清空（gain_resource -3）"


class TestUltimate:
    def test_ult_aoe_and_kill_energy(self, compiled):
        """大招：全体 lv10=2.3 对轴；每杀回能 param(100303,2)=5（on_kill 逐杀口径）."""
        eng = _make(compiled)
        m7 = _hmk(eng)
        m7.current_energy = 120.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e2.current_hp = 100.0   # 一杀饵
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1003"] if a.action_id == "100303")
        assert eng._fire_ultimate(m7, ult) is True
        assert not e2.alive, "e2 被击杀（on_kill 逐杀口径承载）"
        assert math.isclose(hp1 - e1.current_hp,
                            HMK_ATK * 2.3 * DEF_RES * UNBROKEN * CRIT_EXP * FIRE, rel_tol=1e-9), (
            "终结技 lv10 #1=2.3 全体对轴")
        assert math.isclose(m7.current_energy, 10.0), (
            "扣 120 → 行动回能 5（tbgd）+ 每杀回能 param(100303,2)=5")


class TestEidolons:
    def test_e1_speed_after_followup(self):
        """E1：天赋追击落地后速度 +20% 2 回合（官方 "After 'Victory Rush' is triggered"——
        100304 只经 trigger_action 插入执行（insert=True），旧闸 `!$event.insert` 恒假
        =死件，2026-09-24 勘正摘除实证）."""
        compiled = compile_encounter(_build(eidolon=1), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        m7 = _hmk(eng)
        m7.resources["charge"] = 3.0
        _cast(eng, "ally", "ally_basic")   # 满层 → trigger_action 插入 100304
        assert "E1_SPEED" in m7.modifiers, "追击落地 → E1 速度件挂载（旧闸下永不触发）"
        assert math.isclose(eng.pipeline.effective_stats(m7)["spd"], 96 * 1.2, rel_tol=1e-9), (
            "spd 96×1.2（spd_pct 白值口径）")

    def test_e2_low_hp_true_damage(self):
        """E2：受击后 HP≤50% → 追加真伤 0.15×原伤害（category true 跳乘区，雪地的圣女先例）."""
        compiled = compile_encounter(_build(eidolon=2), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        e1.current_hp = 500.0   # 满值 1e9 下血档 ≤50% 恒成立（吃完原伤害仍存活）
        basic = HMK_ATK * 1.0 * DEF_RES * UNBROKEN * CRIT_EXP * FIRE
        hp1 = e1.current_hp
        _cast(eng, "1003", "100301")
        assert math.isclose(hp1 - e1.current_hp, basic * 1.15, rel_tol=1e-9), (
            "原伤害 + 0.15 真伤追加（受击后血档判读 ≤50% 成立）")

    def test_e6_random_segments_expected_first(self):
        """E6：大招后 2 段×原伤害 40% 随机单体——expected 确定化按序取首（e1 吃两段）."""
        compiled = compile_encounter(_build(eidolon=6), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        m7 = _hmk(eng)
        m7.current_energy = 120.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        ult = next(a for a in eng.actions_by_actor["1003"] if a.action_id == "100303")
        assert eng._fire_ultimate(m7, ult) is True
        aoe = HMK_ATK * 2.484 * DEF_RES * UNBROKEN * CRIT_EXP * FIRE   # E5 终结技+2 → lv12=2.484
        seg = 0.4 * 2.484 * HMK_ATK * DEF_RES * UNBROKEN * CRIT_EXP * FIRE
        assert math.isclose(hp1 - e1.current_hp, aoe + 2 * seg, rel_tol=1e-9), (
            "e1 = 大招 + 2 段（expected 按序取首）")
        assert math.isclose(hp2 - e2.current_hp, aoe, rel_tol=1e-9), "e2 仅吃大招全体"
