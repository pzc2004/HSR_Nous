"""银狼 1006 模板端到端对轴（验收型批）：真模板 YAML → 编译 → LV.999 单轨/战技纯伤害/
AoE 终结技减防/天赋缺陷/星魂全链 → 手算全等.

过堂四件（fixture 头注同录）：LV.999 单轨重构（原版行动块摘除+天赋切轨 1100604）/
终结技 single→AoE 勘正 / 抗性双降死件摘除（res_pen 挂敌方零消费，抗性修饰通道缺）/
E2 actor_enter 契约验证。

口径常数：银狼白值 atk 640.332、crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 →
防御区 0.5、量子弱点 → 抗性区 1.0、未击破 0.9。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

SW_ATK = 640.332
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1006", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "quantum",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _stage(enemy_def=0.0):
    return {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
         "def": enemy_def, "max_toughness": 9999, "weakness": ["quantum"]},
        {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
         "def": enemy_def, "max_toughness": 9999, "weakness": ["quantum"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _stage(), template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _sw(eng):
    return eng.state.actors["1006"]


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


def _ult(eng):
    m7 = _sw(eng)
    m7.current_energy = 110.0
    ult = next(a for a in eng.actions_by_actor["1006"] if a.action_id == "1100603")
    assert eng._fire_ultimate(m7, ult) is True


class TestSilverWolfCompile:
    def test_single_track_actions(self, compiled):
        """LV.999 单轨（过堂①）：原版 1006xx 行动块摘除——仅存 11006xx 三件；
        终结技 AoE（过堂②官方 all enemies）；战技抗性死件摘除（过堂③）."""
        acts = {a.action_id: a for a in compiled.actions_by_actor["1006"]}
        assert set(acts) == {"1100601", "1100602", "1100603"}, (
            "原版 100601/100602/100603 已摘除（双轨并列过堂修正）")
        assert acts["1100603"].target_type == "aoe", "官方 all enemies——draft 误 single 勘正"
        assert acts["1100603"].energy_cost == 110
        assert acts["1100602"].apply_modifiers == [], "抗性双降死件摘除落待收"
        mids = [m["modifier_id"] for m in acts["1100603"].apply_modifiers]
        assert "SW_DEF_DOWN" in mids


class TestSkill:
    def test_skill_damage_only_and_bug(self, compiled):
        """战技：单体 1.96 对轴（lv10 1100602 #1）；命中触发天赋减攻缺陷 10%（持续 4）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1006", "1100602")
        assert math.isclose(hp1 - e1.current_hp, 1.96 * SW_ATK * Z, rel_tol=1e-9)
        assert "SW_WEAKNESS_RES_DOWN" not in e1.modifiers, "抗性件已摘除（死键不落件）"
        bug = e1.modifiers.get("SW_BUG_ATK")
        assert bug is not None and bug.duration == 4, "缺陷 3+Generate 1=4 回合"
        assert math.isclose(eng.pipeline.effective_stats(e1)["atk"], 1000 * 0.9, rel_tol=1e-9), (
            "减攻缺陷 10%（1100604 #1 lv10=0.1）")


class TestUltimate:
    def test_ult_aoe_damage(self, compiled):
        """大招 AoE：全体 3.8 对轴（lv10）+ 双敌各挂减防/缺陷（命中域=全体）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        dmg = 3.8 * SW_ATK * Z
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, dmg, rel_tol=1e-9), "AoE 勘正实证——e2 同吃"
        assert "SW_DEF_DOWN" in e1.modifiers and "SW_DEF_DOWN" in e2.modifiers
        assert "SW_BUG_ATK" in e1.modifiers and "SW_BUG_ATK" in e2.modifiers
        assert math.isclose(_sw(eng).current_energy, 5.0)

    def test_ult_def_down_value(self):
        """减防数值：def 200 假人 → 200×(1−0.45)=110（def_pct 负值——1507 先例）."""
        compiled = compile_encounter(_build(), _stage(enemy_def=200.0),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(e1)["def_"], 110.0, rel_tol=1e-9)


class TestEidolons:
    def test_e2_enter_vulnerability(self):
        """E2（新版）：敌方入场受到伤害 +20%（vulnerability 承伤区；旧版效果抵抗件
        随版本更迭摘除——effect_res 键词表未验证死键风险连带消除）."""
        compiled = compile_encounter(_build(eidolon=2), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng.bus.emit("actor_enter", {"actor": "e1", "actor_type": "monster"}, eng.state)
        assert "E2_VULNERABILITY" in e1.modifiers
        assert "E2_EFFECT_RES_DOWN" not in e1.modifiers
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"], 0.2, rel_tol=1e-9)

    def test_e3_talent_lv12_bug(self):
        """E3 天赋+2：缺陷减攻随档 lv12=0.11（E3 战技+2 → 战技 lv12=2.156 一并钉）."""
        compiled = compile_encounter(_build(eidolon=3), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1006", "1100602")
        assert math.isclose(hp1 - e1.current_hp, 2.156 * SW_ATK * Z, rel_tol=1e-9), (
            "E3 战技+2 → lv12 #1=2.156")
        assert math.isclose(eng.pipeline.effective_stats(e1)["atk"], 1000 * 0.89, rel_tol=1e-9), (
            "E3 天赋+2 → 减攻 lv12=0.11")
