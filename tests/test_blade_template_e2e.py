"""刃 1205 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 耗血循环/
HELLSCAPE 换技能/天赋充能/终结技 tally 链/行迹/星魂全链 → 手算全等.

过堂两件（fixture 头注同录）：1120508 主倍率列幻视勘正 / set_hp_to_percent 收编。
SP 消歧：刃（1205）≠ 千冶•刃（1507）。

口径常数：刃白值 hp 1358.28、atk 543.312、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、风弱点 → 抗性区 1.0、未击破 0.9。HELLSCAPE 增伤
lv10 all_dmg 0.4（区 1.4）。战技耗血 0.3×1358.28=407.48；强化普攻耗血 0.1×
=135.83。set_hp 发 on_hp_decrease（reason='set_hp'——tally/charge 钩无 reason
过滤故计入，官方是否计入待实测在案）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

BL_HP = 1358.28
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
BOOST = 1.4          # HELLSCAPE 增伤区
TALLY_CAP = 0.9 * BL_HP


def _build(*, eidolon: int = 0):
    member = {"character_template": "1205", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "wind",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["wind"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["wind"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _bl(eng):
    return eng.state.actors["1205"]


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


class TestBladeCompile:
    def test_scaling_column_and_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1205"]
        assert decls["_talent_charge"]["max"] == 5 and decls["_hp_tally"]["max"] == "inf"
        acts = {a.action_id: a for a in compiled.actions_by_actor["1205"]}
        assert acts["1120508"].scaling[5] == {"hp": 1.3}, (
            "主倍率 lv6=1.3×Max（params 第 2 列——耗血列幻视勘正实证）")
        assert acts["1120501"].available_if != acts["1120508"].available_if


class TestHellscape:
    def test_skill_drain_and_zone(self, compiled):
        """战技：耗 0.3×Max（407.48，tally 同记账 + charge 1）+ HELLSCAPE 3 回合
        增伤 40%（区 1.4）."""
        eng = _make(compiled)
        s = _bl(eng)
        _cast(eng, "1205", "1120502")
        assert math.isclose(s.current_hp, BL_HP - 407.484, rel_tol=1e-9)
        assert math.isclose(s.resources["_hp_tally"], 407.484)
        assert math.isclose(s.resources["_talent_charge"], 1.0)
        assert "HELLSCAPE" in s.modifiers
        assert math.isclose(eng.pipeline.effective_stats(s)["dmg_bonus"].get("all", 0.0),
                            0.4, rel_tol=1e-9)

    def test_enhanced_basic(self, compiled):
        """强化普攻：主 1.3×Max×1.4 / 邻 0.52×Max×1.4 + 耗 135.83（tally/charge 同记）."""
        eng = _make(compiled)
        _cast(eng, "1205", "1120502")   # 开 HELLSCAPE
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1205", "1120508")
        assert math.isclose(hp1 - e1.current_hp, 1.3 * BL_HP * Z * BOOST, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.52 * BL_HP * Z * BOOST, rel_tol=1e-9)
        s = _bl(eng)
        assert math.isclose(s.resources["_hp_tally"], 407.484 + 135.828, rel_tol=1e-9)
        assert math.isclose(s.resources["_talent_charge"], 2.0)


class TestTalent:
    def test_gift_of_shorthand(self, compiled):
        """倏忽恩赐：满 5 层 → 0.85×Max×1.4 追加（A3 并入）+ 自疗 25%×Max×1.25
        （incoming_heal）+ 回能 15 + 清层."""
        eng = _make(compiled)
        _cast(eng, "1205", "1120502")
        s = _bl(eng)
        s.resources["_talent_charge"] = 4.0
        s.current_hp = 500.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        eng.bus.emit("on_hp_decrease", {
            "amount": 100.0, "source": "e1", "reason": "hit",
            "target": "1205", "damage_type": "wind"}, eng.state)
        gift = (1.3 + 0.2) * BL_HP * Z * BOOST   # param(1120504,2) lv10=1.3 + A3 0.2
        assert math.isclose(hp1 - e1.current_hp, gift, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, gift, rel_tol=1e-9)
        assert math.isclose(s.current_hp, 500.0 + 0.25 * BL_HP * 1.25, rel_tol=1e-9)
        assert math.isclose(s.current_energy, 15.0)
        assert math.isclose(s.resources["_talent_charge"], 0.0)


class TestUltimate:
    def test_ult_set_hp_tally_reset(self, compiled):
        """大招：HP 设 50%（set_hp 收编——差量计入 tally/charge 在案）+ Blast
        主 1.5×Max/邻 0.6×Max×1.4 + tally 段 1.2×累计 + 回能 5 + Vita 清半."""
        eng = _make(compiled)
        _cast(eng, "1205", "1120502")
        s = _bl(eng)   # hp 950.8 / tally 407.48 / charge 1
        m7 = s
        m7.current_energy = 130.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        ult = next(a for a in eng.actions_by_actor["1205"] if a.action_id == "1120503")
        assert eng._fire_ultimate(m7, ult) is True
        # set_hp 50%：950.796 → 679.14，差量 271.66 计入 tally（cap 内）→ 679.14
        assert math.isclose(s.current_hp, 0.5 * BL_HP, rel_tol=1e-9)
        tally_after_set = 407.484 + (BL_HP - 407.484 - 0.5 * BL_HP)
        dmg = (1.5 * BL_HP + 1.2 * tally_after_set) * Z * BOOST
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "主 = Blast 1.5×Max + tally 1.2×(407.48+set 差量)")
        assert math.isclose(hp2 - e2.current_hp,
                            (0.6 * BL_HP + 1.2 * tally_after_set) * Z * BOOST, rel_tol=1e-9)
        assert math.isclose(s.current_energy, 5.0)
        assert math.isclose(s.resources["_hp_tally"], 0.5 * tally_after_set, rel_tol=1e-9), (
            "Vita Infinita 清 50%")


class TestEidolons:
    def test_e2_hellscape_crit(self):
        """E2：HELLSCAPE 期间暴击 +15%（enable_if 门控）."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        s = _bl(eng)
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_rate"], 0.05, rel_tol=1e-9)
        _cast(eng, "1205", "1120502")
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_rate"], 0.20, rel_tol=1e-9)

    def test_e4_low_hp_hpup(self):
        """E4：HP≤50% → HP+20%（enable_if 条件光环）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        s = _bl(eng)
        s.current_hp = 0.4 * BL_HP
        assert math.isclose(eng.pipeline.effective_stats(s)["hp"], BL_HP * 1.2, rel_tol=1e-9)
